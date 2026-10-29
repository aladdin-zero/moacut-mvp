"""Offline product-presence detector. This does not identify individual SKUs."""
import os
from pathlib import Path
import time
import sys

import cv2
import numpy as np

TARGETS = ['shirt', 'trousers', 'coat', 'dress', 'skirt', 'shoe', 'handbag', 'folded garment']
NEGATIVES = ['empty table', 'hand', 'person', 'cup', 'mobile phone', 'shadow']
THRESHOLD = .18
MODEL_PATH = Path(__file__).resolve().parents[1] / 'models/owlv2'
EXTRA_DEPENDENCIES = Path(__file__).resolve().parents[1] / '.deps-camera'


def product_gate(result, gray, now, generation):
    gate={'recognized':False,'current':False,'eligible':False,'reason':'no_product','edge_warning':False}
    if not result:
        return gate
    gate['recognized']=bool(result.get('present') and result.get('objects'))
    # Box edges cannot distinguish a tight crop/detail view from a cut garment.
    gate['edge_warning']=gate['recognized'] and any(v<=.015 or v>=.985 for v in result['objects'][0]['box'])
    if result.get('generation')!=generation:
        return {**gate,'reason':'region_changed'}
    age=now-result['frame_time']
    gate['age_ms']=round(age*1000)
    if not 0<=age<=.75:
        return {**gate,'reason':'stale'}
    if gray is None or float(np.abs(gray.astype(np.float32)-result['gray'].astype(np.float32)).mean())>=8:
        return {**gate,'reason':'image_changed'}
    if not gate['recognized']:
        return gate
    gate['current']=True
    if result.get('seen',0)<2:
        return {**gate,'reason':'confirming'}
    return {**gate,'eligible':True,'reason':'ready'}


def current_product(result, gray, now, generation):
    return product_gate(result,gray,now,generation)['eligible']


class ProductDetector:
    def __init__(self, force_cpu=False):
        if EXTRA_DEPENDENCIES.exists():
            sys.path.insert(0,str(EXTRA_DEPENDENCIES))
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        import torch
        from transformers import Owlv2Processor, Owlv2ForObjectDetection
        self.torch = torch
        torch.set_num_threads(min(8,max(1,os.cpu_count() or 1)))
        self.device = 'cpu'
        self.fallback_reason = ''
        if not force_cpu:
            try:
                if torch.cuda.is_available():self.device='cuda'
            except Exception:
                self.fallback_reason='그래픽카드를 확인하지 못해 CPU를 사용합니다.'
        self.processor = Owlv2Processor.from_pretrained(MODEL_PATH, local_files_only=True,use_fast=False)
        self.model = Owlv2ForObjectDetection.from_pretrained(MODEL_PATH, local_files_only=True,
            dtype=torch.float32).eval()
        if self.device=='cuda':
            try:self.model=self.model.half().to('cuda')
            except (RuntimeError,OSError):self.use_cpu()
        self.texts = [[f'a photo of a {name}' for name in TARGETS + NEGATIVES]]

    def use_cpu(self):
        self.device='cpu'
        self.fallback_reason='GPU를 사용할 수 없어 CPU로 전환했습니다.'
        self.model=self.model.to('cpu').float().eval()
        try:self.torch.cuda.empty_cache()
        except (RuntimeError,OSError):pass

    def detect(self, frame):
        try:return self._detect(frame)
        except (RuntimeError,OSError):
            if self.device!='cuda':raise
            self.use_cpu()
            return self._detect(frame)

    def _detect(self, frame):
        torch = self.torch
        start = time.perf_counter()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        inputs = self.processor(text=self.texts, images=rgb, return_tensors='pt').to(self.device)
        if self.device == 'cuda':
            inputs['pixel_values'] = inputs['pixel_values'].half()
        with torch.inference_mode():
            outputs = self.model(**inputs)
        h,w = frame.shape[:2]
        result = self.processor.post_process_object_detection(outputs,
            target_sizes=torch.tensor([[h,w]],device=self.device), threshold=THRESHOLD)[0]
        proposals = []
        for box, score, label in zip(result['boxes'].float().cpu().tolist(),
                                     result['scores'].float().cpu().tolist(), result['labels'].cpu().tolist()):
            if label >= len(TARGETS):
                continue
            x1,y1,x2,y2 = box
            normalized = [max(0,min(1,x1/w)),max(0,min(1,y1/h)),max(0,min(1,x2/w)),max(0,min(1,y2/h))]
            area = (normalized[2]-normalized[0])*(normalized[3]-normalized[1])
            if .025 <= area <= 1:
                proposals.append({'label':TARGETS[label],'score':round(score,4),'box':normalized})
        proposals.sort(key=lambda p:p['score'],reverse=True)
        if self.device == 'cuda':
            torch.cuda.synchronize()
        return {'present':bool(proposals),'objects':proposals[:3],
                'inference_ms':round((time.perf_counter()-start)*1000,1),'device':self.device,
                'device_name':torch.cuda.get_device_name(0) if self.device=='cuda' else 'CPU',
                'fallback_reason':getattr(self,'fallback_reason','')}
