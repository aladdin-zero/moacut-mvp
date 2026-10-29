from io import BytesIO
import hashlib
import json
from pathlib import Path
import tempfile
import time
import threading
import unittest
from unittest.mock import patch
import zipfile

import numpy as np

from detector import Detector
from product_detector import ProductDetector, current_product, product_gate
from server import Trial, capture_feedback


class ProductGateTests(unittest.TestCase):
    def test_local_copy_does_not_lock_camera_frames(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=Trial(Path(folder)/'captures')
            trial.running=True;trial.frame=np.zeros((40,60,3),np.uint8)
            trial.action({'action':'brand','brand':'테스트'})
            trial.capture('test');trial.action({'action':'review','group':trial.active_group})
            entered=threading.Event();release=threading.Event()
            from shutil import copyfile
            def slow_copy(source,target):
                entered.set();release.wait(2);return copyfile(source,target)
            with patch('server.shutil.copyfile',side_effect=slow_copy):
                thread=threading.Thread(target=trial.save_local)
                thread.start()
                self.assertTrue(entered.wait(1))
                acquired=trial.lock.acquire(timeout=.3)
                if acquired:trial.lock.release()
                release.set();thread.join(2)
                self.assertTrue(acquired)

    def test_missing_stale_changed_and_single_detection_fail_closed(self):
        gray=np.zeros((20,20),np.uint8)
        now=time.monotonic()
        result={'present':True,'seen':2,'generation':3,'frame_time':now,'gray':gray,'objects':[{'box':[.1,.1,.9,.9]}]}
        self.assertTrue(current_product(result,gray,now,3))
        self.assertFalse(current_product(None,gray,now,3))
        self.assertFalse(current_product(result,gray,now+1,3))
        self.assertFalse(current_product(result,gray,now,4))
        self.assertFalse(current_product({**result,'seen':1},gray,now,3))
        self.assertFalse(current_product(result,gray+100,now,3))
        edge={**result,'objects':[{'box':[0,0,.5,1]}]}
        self.assertTrue(current_product(edge,gray,now,3))
        self.assertTrue(product_gate(edge,gray,now,3)['edge_warning'])
        self.assertEqual(product_gate(result,gray,now+1,3)['reason'],'stale')
        self.assertEqual(product_gate(result,gray+100,now,3)['reason'],'image_changed')
        self.assertEqual(product_gate({**result,'present':False,'objects':[]},gray,now+1,3)['reason'],'stale')

    def test_large_detected_product_is_not_discarded_by_area(self):
        import torch
        from unittest.mock import Mock
        class Batch(dict):
            def to(self,_):return self
        model=ProductDetector.__new__(ProductDetector)
        model.torch=torch;model.device='cpu';model.texts=[['shirt']]
        model.processor=Mock(return_value=Batch())
        model.model=Mock(return_value=None)
        model.processor.post_process_object_detection.return_value=[{
            'boxes':torch.tensor([[0.,0.,100.,100.]]),
            'scores':torch.tensor([.4]),'labels':torch.tensor([0])}]
        result=model.detect(np.zeros((100,100,3),np.uint8))
        self.assertTrue(result['present'])
        self.assertEqual(result['objects'][0]['box'],[0,0,1,1])

    def test_edge_contact_allows_capture_and_records_review_warning(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=Trial(folder);trial.running=True;trial.automatic=True
            trial.frame=np.zeros((40,60,3),np.uint8)
            trial.action({'action':'brand','brand':'test'})
            trial.product_status={'state':'ready'}
            trial.product_result={'present':True,'seen':2,'generation':trial.generation,
                'frame_time':time.monotonic(),'gray':trial.gray(trial.frame),
                'objects':[{'label':'shirt','score':.4,'box':[0,0,1,1]}],'roi':trial.roi}
            name=trial.capture('auto')
            self.assertTrue((Path(folder)/name).exists())
            photo=trial.data['groups'][0]['photos'][0]
            self.assertTrue(photo['framing_warning'])
            self.assertFalse(trial.data['groups'][0]['reviewed'])
            self.assertTrue(trial.public_state()['product']['current'])
            trial.product_result['frame_time']-=2
            self.assertIsNone(trial.capture('auto'))

    def test_capture_feedback_separates_product_and_motion_reasons(self):
        state={'running':True,'error':'','brand':'test','calibrated':True,'automatic':True,
            'product':{'state':'ready','eligible':True},'status':{'state':'moving'}}
        for code in ['moving','settling','captured','empty','scene_changed','uncertain']:
            result=capture_feedback({**state,'status':{'state':code}})
            self.assertEqual(result['code'],code)
            self.assertTrue(result['detail'])
        for reason in ['no_product','confirming','stale','region_changed','image_changed']:
            result=capture_feedback({**state,'product':{'state':'ready','eligible':False,'reason':reason}})
            self.assertEqual(result['code'],reason)
            self.assertTrue(result['detail'])
        self.assertEqual(capture_feedback({**state,'automatic':False})['code'],'paused')
        self.assertEqual(capture_feedback({**state,'calibrated':False})['code'],'calibration')

    def test_blocked_motion_candidate_does_not_consume_future_capture(self):
        empty=np.zeros((100,160),np.uint8)
        item=empty.copy();item[20:80,40:120]=100
        detector=Detector();detector.calibrate(empty)
        for i in range(30):
            self.assertFalse(detector.update(item,i*.1,allow_capture=False)['capture'])
        self.assertTrue(detector.update(item,4,allow_capture=True)['capture'])
        self.assertFalse(detector.update(item,5,allow_capture=True)['capture'])


class LocalFoldersTests(unittest.TestCase):
    def fixture(self,folder):
        trial=Trial(Path(folder)/'captures')
        trial.running=True;trial.frame=np.zeros((40,60,3),np.uint8)
        trial.action({'action':'brand','brand':'CON.txt'})
        for _ in range(2):
            trial.action({'action':'new_group'})
            trial.capture('test');trial.capture('test')
            trial.action({'action':'exclude','group':trial.active_group,'file':trial.data['groups'][-1]['photos'][-1]['file']})
            trial.action({'action':'review','group':trial.active_group})
        trial.action({'action':'new_group'});trial.capture('test')
        return trial

    def test_copy_only_reviewed_hashes_repeat_and_restore(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=self.fixture(folder)
            originals={p.name:p.read_bytes() for p in trial.directory.glob('*.jpg')}
            first=trial.save_local();second=trial.save_local()
            self.assertNotEqual(first,second)
            self.assertEqual(len(list(first.rglob('*.jpg'))),2)
            manifest=json.loads((first/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(len(manifest),2)
            for group in manifest:
                photo=group['photos'][0]
                self.assertEqual((first/photo['export_file']).read_bytes(),originals[photo['file']])
                self.assertEqual(photo['sha256'],hashlib.sha256(originals[photo['file']]).hexdigest())
                self.assertTrue(group['brand_folder'].startswith('_CON.txt_'))
            self.assertEqual(originals,{p.name:p.read_bytes() for p in trial.directory.glob('*.jpg')})
            restored=Trial(trial.directory)
            self.assertEqual(restored.public_state()['local_export']['path'],str(second))
            with patch('server.os.startfile',create=True) as opened:
                restored.open_export();opened.assert_called_once_with(str(second))

    def test_unreviewed_and_copy_failure_never_publish_complete(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=Trial(Path(folder)/'captures')
            with self.assertRaises(ValueError):trial.save_local()
            self.assertFalse(trial.export_directory.exists())
            trial=self.fixture(folder)
            with patch('server.shutil.copyfile',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):trial.save_local()
            self.assertIsNone(trial.public_state()['local_export'])
            self.assertEqual(list(trial.export_directory.glob('촬영_*')),[])
            self.assertFalse(trial.export_lock.locked())
            self.assertTrue(trial.save_local().is_dir())
            trial.export_lock.acquire()
            with self.assertRaises(ValueError):trial.save_local()
            trial.export_lock.release()


class ExportSafetyTests(unittest.TestCase):
    def test_export_hierarchy_exclusion_and_safe_paths(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            t=Trial(folder);t.running=True;t.frame=np.zeros((40,60,3),np.uint8)
            t.action({'action':'brand','brand':'../CON/테스트'})
            photo=t.capture('test');t.action({'action':'review','group':t.active_group})
            t.action({'action':'new_group'});t.capture('test')
            with zipfile.ZipFile(BytesIO(t.export())) as archive:
                self.assertEqual(len(archive.namelist()),2)
                self.assertTrue(all('..' not in Path(p).parts for p in archive.namelist()))
            self.assertTrue((Path(folder)/photo).exists())
            self.assertEqual(t.public_state()['export_preview'][0]['count'],1)


if __name__=='__main__':unittest.main()
