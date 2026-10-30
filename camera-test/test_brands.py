import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
from server import Trial


class BatchBrandTests(unittest.TestCase):
    def make_trial(self,folder,count=0):
        trial=Trial(Path(folder)/'captures')
        trial.running=True;trial.frame=np.zeros((60,80,3),np.uint8)
        for _ in range(count):trial.capture('manual')
        return trial

    def test_unassigned_capture_and_automatic_keep_four_shot_boundaries(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=self.make_trial(folder)
            trial.data['brand']='legacy global brand'
            for _ in range(9):trial.capture('manual')
            self.assertEqual([len(g['photos']) for g in trial.data['groups']],[4,4,1])
            self.assertEqual([g['brand'] for g in trial.data['groups']],['','',''])
            trial.detector.calibrate(trial.gray(trial.frame))
            trial.product_status={'state':'ready'}
            trial.action({'action':'automatic','enabled':True})
            trial.product_result={'present':True,'seen':2,'objects':[{'box':[.1,.1,.9,.9]}],
                'frame_time':time.monotonic(),'generation':trial.generation,'gray':trial.gray(trial.frame)}
            self.assertIsNotNone(trial.capture('auto'))
            self.assertEqual(len(trial.data['groups'][-1]['photos']),2)
            self.assertNotEqual(trial.public_state()['capture_status']['code'],'brand')

    def test_mixed_brands_roundtrip_folders_zip_and_unassigned_exclusion(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=self.make_trial(folder,12);groups=trial.data['groups'];ids=[g['id'] for g in groups]
            originals={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in trial.directory.glob('*.jpg')}
            trial.action({'action':'assign_brand','groups':[ids[0],ids[2]],'brand':'NIKE'})
            trial.action({'action':'assign_brand','groups':[ids[1]],'brand':'ADIDAS'})
            for gid in ids:trial.action({'action':'review','group':gid})
            trial.capture('manual');unassigned=trial.data['groups'][-1]
            with self.assertRaisesRegex(ValueError,'브랜드'):trial.action({'action':'review','group':unassigned['id']})
            unassigned['reviewed']=True # Old or corrupt records must still stay out of exports.
            trial.persist()
            selected=trial.export_selection()
            self.assertEqual([g['folder'] for g in selected],['NIKE/상품_001','ADIDAS/상품_002','NIKE/상품_003'])
            destination=trial.save_local()
            self.assertEqual(len(list(destination.rglob('*.jpg'))),12)
            with zipfile.ZipFile(BytesIO(trial.export())) as archive:
                self.assertEqual(len([n for n in archive.namelist() if n.endswith('.jpg')]),12)
                self.assertEqual([g['brand'] for g in json.loads(archive.read('manifest.json'))],['NIKE','ADIDAS','NIKE'])
            self.assertEqual([g['brand'] for g in Trial(trial.directory).data['groups']],['NIKE','ADIDAS','NIKE',''])
            self.assertTrue(all(hashlib.sha256((trial.directory/name).read_bytes()).hexdigest()==sha for name,sha in originals.items()))

    def test_invalid_batch_never_partially_changes_metadata(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=self.make_trial(folder,5);ids=[g['id'] for g in trial.data['groups']]
            original=copy.deepcopy(trial.data)
            bad=[{'groups':[],'brand':'A'},{'groups':[ids[0],'unknown'],'brand':'A'},
                {'groups':[ids[0],ids[0]],'brand':'A'},{'groups':[None],'brand':'A'},
                {'groups':ids[0],'brand':'A'},{'groups':ids,'brand':None},
                {'groups':ids,'brand':'x'*101},{'groups':ids,'brand':'A\nB'}]
            for payload in bad:
                with self.subTest(payload=payload):
                    with self.assertRaises(ValueError):trial.action({'action':'assign_brand',**payload})
                    self.assertEqual(trial.data,original)
                    self.assertEqual(json.loads(trial.file.read_text(encoding='utf-8')),original)

    def test_disk_failure_rolls_back_batch_and_review(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=self.make_trial(folder,5);ids=[g['id'] for g in trial.data['groups']]
            trial.action({'action':'assign_brand','groups':ids,'brand':'A'})
            trial.action({'action':'review','group':ids[0]})
            original=copy.deepcopy(trial.data)
            with patch.object(trial,'persist',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):trial.action({'action':'assign_brand','groups':ids,'brand':'B'})
            self.assertEqual(trial.data,original)
            self.assertEqual(json.loads(trial.file.read_text(encoding='utf-8')),original)

    def test_reassignment_and_clear_require_review_without_resetting_capture(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=self.make_trial(folder,8);ids=[g['id'] for g in trial.data['groups']]
            trial.action({'action':'assign_brand','groups':ids,'brand':'A'})
            for gid in ids:trial.action({'action':'review','group':gid})
            gate=(trial.active_group,trial.waiting_for_product_change,trial.detector.armed)
            trial.action({'action':'assign_brand','groups':ids,'brand':' A '})
            self.assertTrue(all(g['reviewed'] for g in trial.data['groups']))
            trial.action({'action':'assign_brand','groups':[ids[0]],'brand':'B'})
            self.assertFalse(trial.group(ids[0])['reviewed']);self.assertTrue(trial.group(ids[1])['reviewed'])
            trial.action({'action':'assign_brand','groups':[ids[1]],'brand':''})
            self.assertEqual(trial.group(ids[1])['brand'],'')
            with self.assertRaises(ValueError):trial.action({'action':'review','group':ids[1]})
            with self.assertRaises(ValueError):trial.export()
            self.assertEqual((trial.active_group,trial.waiting_for_product_change,trial.detector.armed),gate)

    def test_existing_work_brands_remain_and_new_work_starts_unassigned(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=self.make_trial(folder,4);gid=trial.data['groups'][0]['id']
            trial.action({'action':'assign_brand','groups':[gid],'brand':'기존 브랜드'})
            first=trial.data['work_id']
            trial.switch_work({'mode':'new','name':'다른 작업'})
            trial.capture('manual')
            self.assertEqual(trial.data['groups'][0]['brand'],'')
            trial.switch_work({'mode':'continue','work_id':first})
            self.assertEqual(trial.data['groups'][0]['brand'],'기존 브랜드')

    def test_large_batch_http_is_bounded_and_accepts_a_daily_workload(self):
        from http.client import HTTPConnection
        from http.server import ThreadingHTTPServer
        import threading
        import uuid
        from server import handler_for
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=self.make_trial(folder)
            trial.data['groups']=[{'id':uuid.uuid4().hex,'brand':'','reviewed':False,'photos':[{'file':uuid.uuid4().hex+'.jpg','excluded':False}]} for _ in range(600)]
            ids=[g['id'] for g in trial.data['groups']]
            server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(trial,0))
            port=server.server_address[1];server.RequestHandlerClass=handler_for(trial,port)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                body=json.dumps({'action':'assign_brand','groups':ids,'brand':'대량 촬영'})
                self.assertGreater(len(body),16384)
                connection=HTTPConnection('127.0.0.1',port,timeout=3)
                connection.request('POST','/api/action',body,{'Content-Type':'application/json'})
                response=connection.getresponse();data=json.loads(response.read());connection.close()
                self.assertEqual(response.status,200)
                self.assertTrue(all(g['brand']=='대량 촬영' for g in data['groups']))
                connection=HTTPConnection('127.0.0.1',port,timeout=3)
                connection.request('POST','/api/action',headers={'Content-Type':'application/json','Content-Length':'1048577'})
                response=connection.getresponse();response.read();connection.close()
                self.assertEqual(response.status,400)
            finally:server.shutdown();server.server_close();thread.join(2)

    def test_deleted_only_group_cannot_be_assigned(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=self.make_trial(folder,1);group=trial.data['groups'][0]
            trial.action({'action':'delete_photo','group':group['id'],'file':group['photos'][0]['file']})
            original=copy.deepcopy(trial.data)
            with self.assertRaises(ValueError):trial.action({'action':'assign_brand','groups':[group['id']],'brand':'A'})
            self.assertEqual(trial.data,original)


if __name__=='__main__':unittest.main()
