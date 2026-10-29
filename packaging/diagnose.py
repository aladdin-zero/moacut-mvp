"""Offline installation check. Does not open a camera or read user photographs."""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import traceback

os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'


def run(force_cpu=False):
    import numpy as np
    from product_detector import ProductDetector
    from voice_guidance import LocalVoice
    root=Path(__file__).resolve().parents[1]
    started=time.perf_counter()
    detector=ProductDetector(force_cpu=force_cpu)
    results=[detector.detect(np.full((450,800,3),225,np.uint8)) for _ in range(2)]
    data={'application':'MOACUT','version':'0.1.0','python':sys.version.split()[0],
        'isolated_python':bool(sys.flags.isolated),'device':detector.device,
        'device_name':results[-1]['device_name'],'fallback_reason':detector.fallback_reason,
        'inference_ms':[r['inference_ms'] for r in results],
        'model_ready':True,'model_seconds':round(time.perf_counter()-started,2),
        'synthetic_input':True,'camera_opened':False,'voice_ready':False}
    location=Path(os.environ.get('LOCALAPPDATA',root))/'MOACUT'
    try:
        wave=LocalVoice(location/'diagnostic-voice').render('모아컷 환경 점검을 완료했습니다.')
        data['voice_ready']=wave[:4]==b'RIFF'
    except OSError:data['voice_note']='Windows 설정에서 한국어 음성 기능을 설치해 주세요. 화면과 촬영음은 사용할 수 있습니다.'
    return data


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cpu',action='store_true');parser.add_argument('--output',type=Path);args=parser.parse_args()
    output=args.output or Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'MOACUT/diagnostics.json'
    try:
        result=run(args.cpu)
    except Exception:
        result={'application':'MOACUT','model_ready':False,'error':traceback.format_exc()}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print('\n점검 결과:',output)
    sys.exit(0 if result['model_ready'] else 1)
