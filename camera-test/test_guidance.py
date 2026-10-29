import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import wave
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import numpy as np

from server import Trial,handler_for
from voice_guidance import LocalVoice


class GuidanceTests(unittest.TestCase):
    def test_slow_voice_request_does_not_block_state_and_returns_wav(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=Trial(folder);entered=threading.Event();release=threading.Event()
            server=ThreadingHTTPServer(('127.0.0.1',0),lambda *args:None)
            port=server.server_port;server.RequestHandlerClass=handler_for(trial,port)
            thread=threading.Thread(target=server.serve_forever);thread.start()
            def voice(_):entered.set();release.wait(2);return b'RIFF-test-wave'
            responses=[]
            def request_voice():
                connection=HTTPConnection('127.0.0.1',port,timeout=3)
                try:
                    connection.request('GET','/api/voice?text=test')
                    result=connection.getresponse();responses.append((result.status,result.getheader('Content-Type'),result.read()))
                finally:connection.close()
            try:
                with patch.object(trial.voice,'render',side_effect=voice):
                    caller=threading.Thread(target=request_voice);caller.start()
                    self.assertTrue(entered.wait(1))
                    connection=HTTPConnection('127.0.0.1',port,timeout=1)
                    try:
                        connection.request('GET','/api/state');result=connection.getresponse()
                        self.assertEqual(result.status,200);result.read()
                    finally:connection.close();release.set()
                    caller.join(3)
                    self.assertEqual(responses,[(200,'audio/wav',b'RIFF-test-wave')])
            finally:
                release.set();server.shutdown();server.server_close();thread.join()

    def test_configurable_guide_persists_without_changing_photos_or_enforcing_six(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            trial=Trial(folder);trial.running=True;trial.frame=np.zeros((40,60,3),np.uint8)
            trial.action({'action':'brand','brand':'test'})
            for _ in range(7):trial.capture('manual')
            trial.action({'action':'guide','steps':[' 사용자가 정한 내용 ','특징 한 번 더']})
            restored=Trial(folder)
            self.assertEqual(restored.public_state()['guide_steps'],['사용자가 정한 내용','특징 한 번 더'])
            self.assertEqual([len(g['photos']) for g in restored.data['groups']],[4,3])
            self.assertFalse(restored.data['groups'][0]['reviewed'])
            self.assertFalse(restored.automatic)
            for bad in [None,'text',[''],['x'*101],['line\nbreak'],[1],['x']*21]:
                with self.assertRaises(ValueError):trial.action({'action':'guide','steps':bad})
            trial.action({'action':'guide','steps':[]})
            self.assertEqual(trial.data['guide_steps'],[])

    def test_voice_input_is_data_and_audio_cache_reused(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            voice=LocalVoice(Path(folder)/'voice')
            inputs=[]
            def synthesize(*args,**kwargs):
                value=json.loads(kwargs['input']);inputs.append(value)
                with wave.open(value['path'],'wb') as output:
                    output.setnchannels(1);output.setsampwidth(2);output.setframerate(22050)
                    output.writeframes(b'\0\1'*100)
            phrase='앞면; $(절대로 실행하지 않음) "확인"'
            with patch('voice_guidance.subprocess.run',side_effect=synthesize) as run:
                first=voice.render(phrase);self.assertEqual(first,voice.render(phrase))
                run.assert_called_once();self.assertEqual(inputs[0]['text'],phrase)
                self.assertNotIn(phrase,run.call_args.args[0])
            with wave.open(io.BytesIO(first),'rb') as audio:self.assertEqual(audio.getnframes(),100)
            for bad in ['',None,'x'*201,'two\nlines']:
                with self.assertRaises(ValueError):voice.render(bad)

    def test_failed_voice_does_not_leave_completed_cache(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            voice=LocalVoice(folder)
            with patch('voice_guidance.subprocess.run',side_effect=OSError('test')):
                with self.assertRaises(OSError):voice.render('테스트')
            self.assertEqual(list(Path(folder).glob('*.wav')),[])
