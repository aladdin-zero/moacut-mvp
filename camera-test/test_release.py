from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock,patch

import numpy as np
from product_detector import ProductDetector,current_product
from server import Trial


class HardwareTests(unittest.TestCase):
    def test_cuda_failure_retries_on_cpu_but_cpu_failure_is_reported(self):
        detector=ProductDetector.__new__(ProductDetector)
        detector.device='cuda';original_model=Mock();detector.model=original_model;detector.torch=Mock()
        detector._detect=Mock(side_effect=[RuntimeError('GPU unavailable'),{'device':'cpu'}])
        self.assertEqual(detector.detect(None),{'device':'cpu'})
        self.assertEqual(detector.device,'cpu')
        original_model.to.assert_called_once_with('cpu')
        self.assertIn('CPU',detector.fallback_reason)
        detector._detect=Mock(side_effect=RuntimeError('CPU error'))
        with self.assertRaises(RuntimeError):detector.detect(None)
        self.assertEqual(detector._detect.call_count,1)

    def detection_loop(self,trial,change=False):
        entered=threading.Event();release=threading.Event()
        def detect(frame):
            entered.set();release.wait(3)
            return {'present':True,'device':'cpu','objects':[{'box':[.1,.1,.9,.9]}]}
        trial.product_model=Mock();trial.product_model.detect.side_effect=detect
        thread=threading.Thread(target=trial.product_loop);thread.start()
        self.assertTrue(entered.wait(1))
        if change:
            # Even a change that returned to the original frame invalidates this inference.
            trial.inference_watch['changed']=True
        release.set()
        deadline=time.monotonic()+2
        while trial.product_model.detect.call_count<2 and time.monotonic()<deadline:time.sleep(.01)
        with trial.lock:trial.running=False
        thread.join(3)
        self.assertFalse(thread.is_alive())

    def test_slow_static_inference_can_be_used_without_relaxing_expiration(self):
        with tempfile.TemporaryDirectory() as folder:
            trial=Trial(folder);trial.running=True;trial.frame=np.zeros((60,80,3),np.uint8)
            trial.frame_times.append(time.monotonic()-5)
            self.detection_loop(trial)
            result=trial.product_result
            self.assertIsNotNone(result)
            self.assertLess(result['source_frame_time'],result['frame_time']-4)
            result['seen']=2
            self.assertTrue(current_product(result,trial.gray(trial.frame),time.monotonic(),trial.generation))
            self.assertFalse(current_product(result,trial.gray(trial.frame),result['frame_time']+1,trial.generation))

    def test_motion_during_inference_is_discarded(self):
        with tempfile.TemporaryDirectory() as folder:
            trial=Trial(folder);trial.running=True;trial.frame=np.zeros((60,80,3),np.uint8)
            self.detection_loop(trial,change=True)
            # The first changed inference cannot contribute to the two-result gate.
            if trial.product_result:self.assertLessEqual(trial.product_result['seen'],1)

    def test_camera_watches_change_even_when_the_frame_returns(self):
        with tempfile.TemporaryDirectory() as folder:
            trial=Trial(folder);trial.running=True
            original=np.zeros((60,80,3),np.uint8);changed=original.copy();changed[10:50,10:70]=150
            trial.frame=original;watch={'gray':trial.gray(original),'changed':False};trial.inference_watch=watch
            trial.camera=Mock();trial.camera.read.side_effect=[(True,changed),(True,original),(False,None)]
            trial.detector.update=Mock(return_value={'state':'moving','capture':False})
            trial.loop()
            self.assertTrue(watch['changed'])
            self.assertTrue(np.array_equal(trial.gray(trial.frame),watch['gray']))


if __name__=='__main__':unittest.main()
