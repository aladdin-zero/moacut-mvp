"""Offline Windows speech, cached independently of camera locks."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import wave


SCRIPT = r'''
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$speechInput = [Console]::In.ReadToEnd() | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $voice = $speaker.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'ko-KR' } | Select-Object -First 1
    if (-not $voice) { throw 'Korean voice unavailable' }
    $speaker.SelectVoice($voice.VoiceInfo.Name)
    $speaker.Volume = 100
    $speaker.Rate = 1
    $speaker.SetOutputToWaveFile($speechInput.path)
    $speaker.Speak($speechInput.text)
} finally { $speaker.Dispose() }
'''


class LocalVoice:
    def __init__(self, directory):
        self.directory=Path(directory)
        self.lock=threading.Lock()

    def render(self, text):
        if not isinstance(text,str) or not text.strip() or len(text)>200 or any(ord(c)<32 for c in text):
            raise ValueError('음성 안내는 1~200자의 한 줄 문장으로 입력해 주세요.')
        text=text.strip()
        digest=hashlib.sha256(('ko-KR-rate1-v1:'+text).encode()).hexdigest()
        with self.lock:
            self.directory.mkdir(parents=True,exist_ok=True)
            target=self.directory/(digest+'.wav')
            if target.exists():
                return target.read_bytes()
            if os.name!='nt':
                raise OSError('Windows speech required')
            with tempfile.NamedTemporaryFile(dir=self.directory,suffix='.wav',delete=False) as temporary:
                path=Path(temporary.name)
            try:
                encoded=base64.b64encode(SCRIPT.encode('utf-16-le')).decode('ascii')
                subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-EncodedCommand',encoded],
                    input=json.dumps({'text':text,'path':str(path)},ensure_ascii=False).encode('utf-8'),
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=20,
                    creationflags=subprocess.CREATE_NO_WINDOW)
                with wave.open(str(path),'rb') as audio:
                    if audio.getnframes()==0:
                        raise OSError('Empty speech')
                path.replace(target)
                return target.read_bytes()
            except (subprocess.SubprocessError,EOFError,wave.Error) as exc:
                raise OSError('Local speech unavailable') from exc
            finally:
                path.unlink(missing_ok=True)
