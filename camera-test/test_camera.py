import json
from pathlib import Path
import tempfile
import unittest
from io import BytesIO
import zipfile
import threading
import time
import cv2
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import numpy as np

from detector import Detector
from server import Trial, handler_for


class MotionTests(unittest.TestCase):
    def setUp(self):
        self.empty = np.zeros((100, 160), dtype=np.uint8)
        self.product = self.empty.copy()
        self.product[20:80, 40:120] = 100
        self.detector = Detector()

    def test_calibration_required_and_duplicate_suppressed(self):
        self.assertFalse(self.detector.update(self.product, 0)["capture"])
        self.detector.calibrate(self.empty)
        self.detector.update(self.product, 1)
        self.detector.update(self.product, 1.1)
        self.assertTrue(self.detector.update(self.product, 2)["capture"])
        self.assertFalse(self.detector.update(self.product, 8)["capture"])

    def test_changed_pose_rearms_and_six_is_not_a_limit(self):
        self.detector.calibrate(self.empty)
        captures = 0
        for i in range(8):
            pose = self.product.copy()
            pose[20:80, 40:120] = 50 + i * 25
            self.detector.update(pose, i*3)
            captures += self.detector.update(pose, i*3+1)["capture"]
            captures += self.detector.update(pose, i*3+2)["capture"]
        self.assertEqual(captures, 8)

    def test_short_absence_does_not_close_group(self):
        d = self.detector
        d.calibrate(self.empty)
        d.update(self.product, 0)
        d.update(self.product, 1)
        self.assertFalse(d.update(self.empty, 2)["boundary"])
        self.assertFalse(d.update(self.product, 2.5)["boundary"])
        self.assertFalse(d.update(self.empty, 3)["boundary"])
        self.assertTrue(d.update(self.empty, 4.3)["boundary"])
        self.assertFalse(d.update(self.empty, 6)["boundary"])

    def test_empty_desk_global_exposure_and_small_noise_do_not_capture(self):
        y, x = np.mgrid[:100, :160]
        desk = (65 + x//4 + y//5).astype(np.uint8)
        d = self.detector
        d.calibrate([desk] * 10)
        rng = np.random.default_rng(11)
        for i in range(90):
            gain = 1 + .2 * np.sin(i/12)
            brightness = 18 * np.sin(i/9)
            frame = np.clip(desk.astype(float)*gain+brightness+rng.normal(0, 1, desk.shape), 0, 255).astype(np.uint8)
            result = d.update(frame, i*.1)
            self.assertFalse(result['capture'], (i, result))
        speck = desk.copy()
        speck[20:25, 30:35] = 230
        for i in range(10):
            self.assertFalse(d.update(speck, 10+i)['capture'])

    def test_real_foreground_after_exposure_shift_still_captures(self):
        y, x = np.mgrid[:100, :160]
        desk = (65 + x//4 + y//5).astype(np.uint8)
        d = self.detector
        d.calibrate(desk)
        exposed = np.clip(desk.astype(float)*1.15+12,0,255).astype(np.uint8)
        d.update(exposed, 0)
        item = exposed.copy()
        item[20:80, 40:120] = 20
        d.update(item, 1)
        d.update(item, 1.2)
        self.assertTrue(d.update(item, 2)['capture'])
        self.assertFalse(d.update(item, 3)['capture'])

    def test_ambiguous_scene_change_does_not_capture(self):
        self.detector.calibrate(self.empty)
        # A new nonuniform scene covering almost the entire region is not an item insertion.
        scene = np.full_like(self.empty, 25)
        scene[:, 80:] = 230
        for i in range(10):
            self.assertFalse(self.detector.update(scene, i)['capture'])


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.trial = Trial(self.folder.name)
        self.trial.running = True
        self.trial.frame = np.zeros((60, 80, 3), dtype=np.uint8)


    def tearDown(self):
        self.folder.cleanup()

    def test_split_merge_exclude_and_export_safety(self):
        t = self.trial
        files = [t.capture("test") for _ in range(3)]
        gid = t.active_group
        with self.assertRaises(ValueError):
            t.export()
        t.action({'action':'assign_brand','groups':[gid],'brand':'테스트'});t.action({"action": "review", "group": gid})
        self.assertEqual(len(zipfile.ZipFile(BytesIO(t.export())).namelist()), 4)
        t.action({"action": "split", "group": gid, "file": files[1]})
        self.assertEqual([len(g["photos"]) for g in t.data["groups"]], [1, 2])
        self.assertTrue(all(not g["reviewed"] for g in t.data["groups"]))
        t.action({"action": "merge", "group": t.data["groups"][1]["id"]})
        t.action({"action": "exclude", "group": gid, "file": files[0]})
        t.action({'action':'assign_brand','groups':[gid],'brand':'테스트'});t.action({"action": "review", "group": gid})
        with zipfile.ZipFile(BytesIO(t.export())) as archive:
            names=archive.namelist()
            manifest=json.loads(archive.read('manifest.json'))
            self.assertEqual([p['file'] for p in manifest[0]['photos']],files[1:])
            self.assertEqual(names,['테스트/상품_001/01.jpg','테스트/상품_001/02.jpg','manifest.json'])
        self.assertTrue((Path(self.folder.name)/files[0]).exists())
        restored = Trial(self.folder.name)
        self.assertEqual(restored.data, t.data)
        # Daily work continuation now restores an unfinished product too.
        self.assertEqual(restored.active_group,t.active_group)

    def test_brand_assignment_keeps_product_and_validation(self):
        t=self.trial
        t.capture('test');first=t.active_group
        t.action({'action':'assign_brand','groups':[first],'brand':'다른 브랜드'})
        t.capture('test')
        self.assertEqual(t.active_group,first)
        self.assertEqual(len(t.group(first)['photos']),2)
        t.action({'action':'new_group'});t.capture('test')
        self.assertEqual(t.group(t.active_group)['brand'],'')
        with self.assertRaises(ValueError):t.action({'action':'merge','group':t.active_group})
        for roi in ([0,0,.01,1],[0,0,2,1],[0,'a',1,1],[0,0,float('nan'),1]):
            with self.assertRaises(ValueError):t.action({'action':'calibrate','roi':roi})

    def test_new_capture_invalidates_review(self):
        t = self.trial
        t.capture("test")
        t.action({'action':'assign_brand','groups':[t.active_group],'brand':'테스트'});t.action({"action": "review", "group": t.active_group})
        t.capture("test")
        self.assertFalse(t.group(t.active_group)["reviewed"])
        self.assertEqual(len(list(Path(self.folder.name).glob('*.jpg'))), 2)

    def test_calibration_requires_camera_warmup_and_stable_history(self):
        t = self.trial
        with self.assertRaises(ValueError):
            t.action({'action':'calibrate','roi':t.roi})
        t.camera_started = time.monotonic()-3
        with self.assertRaises(ValueError):
            t.action({'action':'calibrate','roi':t.roi})
        now = time.monotonic()
        for i in range(10):
            t.gray_history.append((now-.9+i*.09,t.gray(t.frame)))
        t.action({'action':'calibrate','roi':t.roi})
        self.assertIsNotNone(t.detector.reference)
        for i in range(40):
            self.assertFalse(t.detector.update(t.gray(t.frame), now+i*.1)['capture'])

    def test_thumbnails_keep_original_dimensions(self):
        name = self.trial.capture('test')
        thumb = self.trial.thumbnail(name)
        self.assertEqual(cv2.imdecode(np.frombuffer(thumb,np.uint8),cv2.IMREAD_COLOR).shape[1],320)
        self.assertEqual(cv2.imread(str(Path(self.folder.name)/name)).shape[:2],(60,80))


class HTTPTests(unittest.TestCase):
    def test_stream_delivers_latest_frame_without_client_queue(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            trial = Trial(directory)
            server = ThreadingHTTPServer(('127.0.0.1',0),lambda *args:None)
            server.RequestHandlerClass = handler_for(trial,server.server_port)
            thread = threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            connection = HTTPConnection('127.0.0.1',server.server_port,timeout=3)
            try:
                trial.running=True
                connection.request('GET','/api/stream')
                response=connection.getresponse()
                self.assertEqual(response.status,200)
                self.assertIn('multipart',response.getheader('Content-Type'))
                with trial.frame_ready:
                    trial.sequence=100
                    trial.preview=b'jpeg-test'
                    trial.preview_published=time.monotonic()
                    trial.frame_ready.notify_all()
                self.assertEqual(response.readline(),b'--frame\r\n')
                headers=[]
                while True:
                    line=response.readline()
                    if line==b'\r\n':break
                    headers.append(line)
                self.assertIn(b'X-Sequence: 100\r\n',headers)
                self.assertEqual(response.read(9),b'jpeg-test')
            finally:
                connection.close()
                with trial.frame_ready:
                    trial.running=False
                    trial.frame_ready.notify_all()
                server.shutdown();server.server_close();thread.join()

    def test_local_only_validation_and_static_allowlist(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            trial = Trial(directory)
            server = ThreadingHTTPServer(('127.0.0.1', 0), lambda *args: None)
            port = server.server_port
            server.RequestHandlerClass = handler_for(trial, port)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                def request(method, path, body=None, headers=None):
                    connection = HTTPConnection('127.0.0.1', port, timeout=5)
                    connection.request(method, path, body=body, headers=headers or {})
                    response = connection.getresponse()
                    result = response.status, response.read()
                    connection.close()
                    return result
                self.assertEqual(request('GET', '/')[0], 200)
                self.assertEqual(request('GET', '/api/state')[0], 200)
                self.assertEqual(request('GET', '/api/export')[0], 400)
                self.assertEqual(request('GET', '/../server.py')[0], 404)
                self.assertEqual(request('GET', '/api/state', headers={'Host': 'evil.test'})[0], 403)
                headers = {'Content-Type': 'application/json', 'Origin': 'https://evil.test'}
                self.assertEqual(request('POST', '/api/action', '{}', headers)[0], 403)
                headers.pop('Origin')
                self.assertEqual(request('POST', '/api/local/save', '{}', headers)[0], 400)
                self.assertEqual(request('POST', '/api/drive/save', '{}', headers)[0], 400)
                self.assertEqual(request('GET', '/oauth/callback')[0], 404)
                self.assertEqual(request('POST', '/api/action', '[]', headers)[0], 400)
                self.assertEqual(request('POST', '/api/action', '{"action":"guide","steps":["demo"]}', headers)[0], 200)
                self.assertEqual(Trial(directory).data['guide_steps'], ['demo'])
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()
