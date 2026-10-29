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
from server import Trial,write_record


class DailyWorkTests(unittest.TestCase):
    def make_trial(self, folder):
        trial=Trial(folder)
        trial.running=True;trial.frame=np.zeros((60,80,3),np.uint8)
        trial.action({'action':'brand','brand':'테스트'})
        return trial

    def test_legacy_backup_and_photos_survive_migration(self):
        with tempfile.TemporaryDirectory() as folder:
            trial=self.make_trial(folder);name=trial.capture('manual')
            legacy=copy.deepcopy(trial.data)
            for key in ('work_id','work_date','work_name','resume_group'):
                legacy.pop(key,None)
            original=json.dumps(legacy,ensure_ascii=False).encode()
            trial.file.write_bytes(original)
            photo=(Path(folder)/name).read_bytes()
            restored=Trial(folder)
            self.assertEqual((Path(folder)/'session.before-work-sessions.json').read_bytes(),original)
            self.assertEqual(restored.data['groups'],legacy['groups'])
            self.assertEqual((Path(folder)/name).read_bytes(),photo)
            self.assertTrue(restored.data['legacy_work'])
            self.assertEqual(restored.active_group,legacy['groups'][-1]['id'])

    def test_new_and_continue_isolate_photos_and_resume_partial_product(self):
        with tempfile.TemporaryDirectory() as folder:
            trial=self.make_trial(folder)
            trial.action({'action':'guide','steps':['특별한 안내','라벨']})
            old=trial.data['work_id'];first=trial.capture('manual');gid=trial.active_group
            chosen=Path(folder)/'결과';chosen.mkdir()
            trial.set_export_directory(str(chosen.resolve()))
            trial.switch_work({'mode':'new','name':'오늘 두 번째'})
            new=trial.data['work_id']
            self.assertNotEqual(old,new);self.assertEqual(trial.data['groups'],[])
            self.assertEqual(trial.data['brand'],'')
            self.assertEqual(trial.data['guide_steps'],['특별한 안내','라벨'])
            self.assertFalse(trial.automatic)
            trial.action({'action':'brand','brand':'다음 브랜드'})
            second=trial.capture('manual')
            self.assertNotEqual(first,second)
            trial.action({'action':'review','group':trial.active_group})
            self.assertEqual([p['file'] for g in trial.export_selection() for p in g['photos']],[second])
            trial.switch_work({'mode':'continue','work_id':old})
            self.assertEqual(trial.active_group,gid)
            self.assertEqual([p['file'] for p in trial.group(gid)['photos']],[first])
            self.assertEqual(trial.export_directory,chosen.resolve())
            trial.action({'action':'review','group':gid})
            self.assertEqual([p['file'] for g in trial.export_selection() for p in g['photos']],[first])
            restored=Trial(folder)
            self.assertEqual(restored.active_group,gid)
            self.assertEqual(len(restored.public_state()['works']),2)
            restored.switch_work({'mode':'continue','work_id':new})
            self.assertEqual(restored.data['groups'][0]['photos'][0]['file'],second)

    def test_day_change_stops_both_capture_modes_but_keeps_review_export(self):
        with tempfile.TemporaryDirectory() as folder:
            trial=self.make_trial(folder);trial.capture('manual');gid=trial.active_group
            trial.action({'action':'review','group':gid});trial.automatic=True
            with patch('server.today',return_value='2099-01-02'):
                self.assertFalse(trial.public_state()['can_capture'])
                self.assertFalse(trial.automatic)
                with self.assertRaises(ValueError):trial.capture('manual')
                self.assertIsNone(trial.capture('auto'))
                with self.assertRaises(ValueError):trial.action({'action':'automatic','enabled':True})
                self.assertEqual(len(trial.export_selection()),1)
                previous=trial.data['work_id']
                trial.switch_work({'mode':'new','name':'다음날 촬영'})
                self.assertEqual(trial.data['work_date'],'2099-01-02')
                self.assertNotEqual(trial.data['work_id'],previous)

    def test_delete_restore_and_export_keep_original_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            trial=self.make_trial(folder);names=[trial.capture('manual') for _ in range(4)]
            gid=trial.data['groups'][0]['id']
            before={name:hashlib.sha256((Path(folder)/name).read_bytes()).hexdigest() for name in names}
            trial.action({'action':'review','group':gid})
            trial.action({'action':'delete_photo','group':gid,'file':names[1]})
            self.assertFalse(trial.group(gid)['reviewed'])
            trial.action({'action':'review','group':gid})
            with zipfile.ZipFile(BytesIO(trial.export())) as archive:
                exported=json.loads(archive.read('manifest.json'))[0]
                self.assertEqual([p['file'] for p in exported['photos']],[names[0],names[2],names[3]])
                self.assertEqual(exported['work_id'],trial.data['work_id'])
            restored=Trial(folder)
            self.assertTrue(restored.group(gid)['photos'][1]['deleted_at'])
            restored.action({'action':'restore_photo','group':gid,'file':names[1]})
            self.assertFalse(restored.group(gid)['reviewed'])
            self.assertIsNone(restored.active_group)
            self.assertEqual(before,{name:hashlib.sha256((Path(folder)/name).read_bytes()).hexdigest() for name in names})

    def test_deleted_slot_can_be_replaced_before_four_and_completed_group_stays_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            trial=self.make_trial(folder);first=trial.capture('manual');gid=trial.active_group
            trial.action({'action':'delete_photo','group':gid,'file':first})
            for _ in range(4):trial.capture('manual')
            self.assertEqual(len(trial.data['groups']),1)
            self.assertEqual(len(trial.group(gid)['photos']),5)
            self.assertTrue(trial.group(gid)['capture_complete'])
            trial.action({'action':'restore_photo','group':gid,'file':first})
            trial.capture('manual')
            self.assertEqual(len(trial.data['groups']),2)

    def test_invalid_work_and_failed_switch_do_not_lose_current_session(self):
        with tempfile.TemporaryDirectory() as folder:
            trial=self.make_trial(folder);trial.capture('manual');original=copy.deepcopy(trial.data)
            for payload in ({'mode':'x'},{'mode':'continue','work_id':'../../a'},{'mode':'new','name':''}):
                with self.assertRaises(ValueError):trial.switch_work(payload)
                self.assertEqual(trial.data,original)
            trial.export_lock.acquire()
            try:
                with self.assertRaises(ValueError):trial.switch_work({'mode':'new','name':'blocked'})
            finally:trial.export_lock.release()
            with patch('server.write_record',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):trial.switch_work({'mode':'new','name':'failed'})
            self.assertEqual(json.loads(trial.file.read_text(encoding='utf-8')),original)
            self.assertEqual(trial.data,original)

    def test_camera_reconnect_and_calibration_keep_unfinished_product(self):
        with tempfile.TemporaryDirectory() as folder:
            trial=self.make_trial(folder);trial.capture('manual');gid=trial.active_group
            trial=Trial(folder)
            with patch('server.cv2.VideoCapture'),patch('server.threading.Thread'):
                trial.start()
            self.assertEqual(trial.active_group,gid)
            trial.frame=np.zeros((60,80,3),np.uint8)
            trial.camera_started=time.monotonic()-3
            now=time.monotonic()
            for i in range(10):trial.gray_history.append((now-.9+i*.09,trial.gray(trial.frame)))
            trial.action({'action':'calibrate','roi':trial.roi})
            self.assertEqual(trial.active_group,gid)
            trial.capture('manual')
            self.assertEqual(len(trial.group(gid)['photos']),2)

    def test_failed_delete_or_final_work_switch_keeps_old_data(self):
        with tempfile.TemporaryDirectory() as folder:
            trial=self.make_trial(folder);name=trial.capture('manual');gid=trial.active_group
            original=copy.deepcopy(trial.data)
            with patch.object(trial,'persist',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):trial.action({'action':'delete_photo','group':gid,'file':name})
            self.assertEqual(trial.data,original)
            def fail_new(path,data):
                if data['work_id']!=original['work_id']:raise OSError('disk full')
                write_record(path,data)
            with patch('server.write_record',side_effect=fail_new):
                with self.assertRaises(OSError):trial.switch_work({'mode':'new','name':'실패 시험'})
            self.assertEqual(trial.data,original)
            self.assertEqual(json.loads(trial.file.read_text(encoding='utf-8')),original)
