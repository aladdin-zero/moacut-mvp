from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock,patch

import numpy as np

from server import Trial


class FourShotTests(unittest.TestCase):
    def make_trial(self,folder):
        trial=Trial(folder);trial.running=True
        trial.frame=np.zeros((100,160,3),np.uint8)
        trial.action({'action':'brand','brand':'test'})
        return trial

    def test_saved_four_four_one_and_no_automatic_review(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=self.make_trial(folder)
            for _ in range(4):trial.capture('manual')
            self.assertIsNone(trial.active_group)
            self.assertTrue(trial.waiting_for_product_change)
            for _ in range(5):trial.capture('manual')
            self.assertEqual([len(g['photos']) for g in trial.data['groups']],[4,4,1])
            self.assertTrue(all(not g['reviewed'] for g in trial.data['groups']))
            events=[e for e in trial.data['events'] if e['event']=='capture']
            self.assertEqual([e['shot_number'] for e in events],[1,2,3,4,1,2,3,4,1])
            self.assertEqual([i for i,e in enumerate(events,1) if e['product_complete']],[4,8])

    def test_fourth_failure_does_not_advance_and_steady_screen_stays_blocked(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=self.make_trial(folder)
            for _ in range(3):trial.capture('manual')
            gid=trial.active_group
            with patch('server.cv2.imencode',return_value=(False,None)):
                with self.assertRaises(ValueError):trial.capture('manual')
            self.assertEqual(trial.active_group,gid)
            self.assertEqual(len(trial.group(gid)['photos']),3)
            trial.capture('manual');trial.automatic=True
            trial.product_status={'state':'ready'}
            def detection():
                trial.product_result={'present':True,'objects':[{'box':[.1,.1,.9,.9]}],
                    'seen':2,'gray':trial.gray(trial.frame),'frame_time':time.monotonic(),'generation':trial.generation}
            detection()
            self.assertIsNone(trial.capture('auto'))
            trial.frame[20:80,40:120]=150;detection()
            self.assertIsNotNone(trial.capture('auto'))
            self.assertEqual([len(g['photos']) for g in trial.data['groups']],[4,1])

    def test_empty_background_signal_keeps_partial_product(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=self.make_trial(folder);trial.capture('manual');gid=trial.active_group
            frame=trial.frame.copy();trial.camera=Mock()
            trial.camera.read.side_effect=[(True,frame),(False,None)]
            trial.detector.update=Mock(return_value={'boundary':True,'capture':False,'state':'empty'})
            trial.loop()
            self.assertEqual(trial.active_group,gid)
            self.assertEqual(len(trial.data['groups']),1)
