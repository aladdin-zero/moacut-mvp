"""Single-PC camera trial. No remote services, no image deletion."""
import argparse
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid
import zipfile
import webbrowser
import hashlib
import unicodedata
import copy
import shutil
import tempfile
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from urllib.parse import urlparse, parse_qs

import cv2

from detector import Detector, compensated_difference
from product_detector import ProductDetector, current_product, product_gate
from voice_guidance import LocalVoice
from folder_picker import local_folder, list_folders
from work_sessions import WorkSessions, identify, today, write_record

ROOT = Path(__file__).resolve().parent
SHOTS_PER_PRODUCT = 4


def stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def capture_feedback(state):
    product=state['product']
    if state.get('work_date',today()) != today():
        code,title,detail='work_day','오늘 작업을 시작해 주세요','지난 작업은 사진 확인·저장만 가능합니다. 작업 선택에서 오늘 새 작업을 만드세요.'
    elif state['error']:
        code,title,detail='camera_error','카메라를 확인해 주세요',state['error']
    elif not state['running']:
        code,title,detail='stopped','카메라 연결 전','카메라를 연결하면 상품 인식 상태와 촬영 대기 이유를 보여줍니다.'
    elif product.get('state')=='error':
        code,title,detail='model_error','상품 인식기를 확인해 주세요',product.get('message','상품 인식 오류로 자동 촬영을 멈췄습니다.')
    elif product.get('state')!='ready':
        code,title,detail='loading','상품 인식기를 준비하고 있습니다','준비가 끝나면 인식을 시작합니다.'
    elif not state['brand'].strip():
        code,title,detail='brand','브랜드 입력이 필요합니다','촬영 준비에서 브랜드를 입력하고 적용해 주세요.'
    elif not state['calibrated']:
        code,title,detail='calibration','빈 배경 등록이 필요합니다','상품과 손이 없는 배경을 한 번 등록해 주세요.'
    elif state.get('waiting_for_product_change'):
        code,title,detail='next_product','4컷 완료 · 다음 상품 준비','버튼을 누를 필요 없이 다음 상품을 보여 주세요. 같은 화면의 자동 중복 촬영은 막고 있습니다.'
    elif not state['automatic']:
        code,title,detail='paused','자동 촬영이 멈춰 있습니다','준비되면 자동 촬영 시작을 누르세요. 상품 인식은 계속 표시합니다.'
    elif not product['eligible']:
        code=product['reason']
        title,detail={
            'no_product':('상품을 확인하지 못했습니다','현재 인식 결과에 상품이 없습니다. 직접 촬영으로 라벨·상세 컷을 보완할 수 있습니다.'),
            'confirming':('상품을 한 번 더 확인 중입니다','연속 인식을 확인하면 촬영을 진행합니다.'),
            'stale':('최신 인식 결과를 기다리고 있습니다','이전 결과가 오래되어 자동 촬영을 잠시 보류합니다.'),
            'image_changed':('화면이 바뀌어 다시 인식 중입니다','옷을 움직이거나 뒤집은 뒤 새 인식 결과를 기다립니다.'),
            'region_changed':('새 촬영 영역을 확인 중입니다','변경한 영역의 인식 결과를 기다립니다.')
        }.get(code,('상품 확인 중입니다','최신 상품 인식 결과를 기다립니다.'))
    else:
        code=state['status'].get('state','settling')
        title,detail={
            'moving':('상품 인식됨 · 움직임 대기','잠시 멈추면 촬영합니다. 가이드 선에 딱 맞출 필요는 없습니다.'),
            'settling':('상품 인식됨 · 안정 확인 중','움직임이 약 0.65초 멈추면 한 컷 촬영합니다.'),
            'captured':('촬영한 구도입니다 · 다음 면 대기','같은 사진은 반복 저장하지 않습니다. 다음 면을 보여주거나 직접 촬영하세요.'),
            'empty':('상품 인식됨 · 배경 차이 부족','등록한 빈 배경과 차이가 작습니다. 상품을 놓은 채 배경을 등록했다면 빈 상태로 다시 등록해 주세요.'),
            'uncertain':('상품 인식됨 · 배경 변화 확인 중','배경과 상품의 변화가 충분히 구분되지 않아 촬영을 보류합니다.'),
            'scene_changed':('상품 인식됨 · 큰 화면 변화로 대기','카메라 위치·조명 변화 또는 화면을 채운 상품 때문에 배경 비교가 어렵습니다.'),
            'awaiting_product':('상품 인식됨 · 촬영 조건 재확인 중','최신 인식 결과와 정지 상태를 함께 확인합니다.')
        }.get(code,('상품 인식됨 · 촬영 준비 중','움직임과 촬영 조건을 확인합니다.'))
    return {'code':code,'title':title,'detail':detail}


class Trial:
    def __init__(self, directory, camera_index=0, export_directory=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.file = self.directory / "session.json"
        self.voice=LocalVoice(self.directory/'.voice-cache')
        self.export_directory=Path(export_directory or self.directory.parent/'exports').resolve()
        self.export_lock=threading.Lock()
        self.lock = threading.RLock()
        self.frame_ready = threading.Condition(self.lock)
        self.sequence = 0
        self.frame_times = deque(maxlen=120)
        self.gray_history = deque(maxlen=30)
        self.camera_started = None
        self.preview_published = None
        self.thumb_cache = {}
        self.product_model = None
        self.product_thread = None
        self.product_result = None
        self.inference_watch = None
        self.product_status = {"state":"not_loaded"}
        self.generation = 0
        self.automatic = False
        self.camera_index = camera_index
        self.camera = None
        self.running = False
        self.frame = None
        self.preview = None
        self.thread = None
        self.error = ""
        self.detector = Detector()
        self.roi = [0.05, 0.05, 0.95, 0.95]
        self.status = {"state": "stopped"}
        self.data = json.loads(self.file.read_text(encoding="utf-8")) if self.file.exists() else {
            "created": stamp(), "brand": "", "groups": [], "events": [], "active_seconds": 0}
        if self.file.exists() and 'work_id' not in self.data:
            backup=self.directory/'session.before-work-sessions.json'
            if not backup.exists():
                with backup.open('xb') as output:
                    output.write(self.file.read_bytes())
        identify(self.data,legacy=self.file.exists() and 'work_id' not in self.data)
        self.works=WorkSessions(self.directory)
        self.data.setdefault('guide_steps',[])
        if self.data.get('export_directory'):
            self.export_directory=Path(self.data['export_directory']).resolve()
        last_desk = next((e for e in reversed(self.data["events"]) if e["event"] == "desk_calibrated"), None)
        if last_desk:
            self.roi = last_desk["roi"]
        self.active_group = self.resume_group()
        self.waiting_for_product_change=False
        self.completed_gray=None
        self.last_completed_group=None
        self.persist()

    def persist(self):
        self.data['resume_group']=self.active_group
        write_record(self.file,self.data)

    def resume_group(self):
        last=self.data['groups'][-1] if self.data['groups'] else {}
        gid=self.data.get('resume_group',last.get('id') if last.get('capture_limit')==SHOTS_PER_PRODUCT else None)
        group=next((g for g in self.data['groups'] if g['id']==gid),None)
        if group and not group.get('capture_complete') and sum(not p.get('deleted_at') for p in group['photos'])<SHOTS_PER_PRODUCT:
            return gid
        return None

    def switch_work(self,payload):
        if not self.export_lock.acquire(blocking=False):
            raise ValueError('사진을 저장 중입니다. 완료 후 작업을 바꿔 주세요.')
        try:
            with self.lock:
                self.automatic=False
                mode=payload.get('mode')
                if mode=='new':
                    name=payload.get('name',today()+' 촬영')
                    if not isinstance(name,str) or not 1<=len(name.strip())<=100 or any(ord(c)<32 for c in name):
                        raise ValueError('작업 이름을 1~100자로 입력해 주세요.')
                    candidate=identify({'created':stamp(),'brand':'','groups':[],'events':[],
                        'active_seconds':0,'guide_steps':list(self.data['guide_steps'])})
                    candidate['work_date']=today()
                    candidate['work_name']=name.strip()
                elif mode=='continue':
                    work_id=payload.get('work_id')
                    if work_id==self.data['work_id']:
                        self.event('work_opened');self.persist()
                        return
                    candidate=self.works.load(work_id)
                else:
                    raise ValueError('이어하기 또는 새 작업을 선택해 주세요.')
                self.persist()
                self.works.archive(self.data)
                # Keep the chosen output location when changing the work being viewed.
                if self.data.get('export_directory'):
                    candidate['export_directory']=self.data['export_directory']
                else:
                    candidate.pop('export_directory',None)
                write_record(self.file,candidate)
                self.data=candidate
                self.active_group=self.resume_group()
                self.waiting_for_product_change=False
                self.last_completed_group=None;self.completed_gray=None
                self.detector.last_capture=None;self.detector.stable_since=None
                self.detector.armed=True
        finally:
            self.export_lock.release()

    def event(self, name, **values):
        self.data["events"].append({"at": stamp(), "event": name, **values})

    def state(self):
        with self.lock:
            return {**copy.deepcopy(self.data), "running": self.running, "error": self.error,
                    "status": self.status, "roi": self.roi,
                    "resolution": None if self.frame is None else [self.frame.shape[1], self.frame.shape[0]],
                    "save_directory": str(self.directory), "active_group": self.active_group,
                    "shots_per_product": SHOTS_PER_PRODUCT,"stable_seconds":self.detector.stable_seconds,
                    "waiting_for_product_change":self.waiting_for_product_change,
                    "last_completed_group":self.last_completed_group,
                    "sequence": self.sequence,
                    "preview_fps": round((len(self.frame_times)-1)/(self.frame_times[-1]-self.frame_times[0]), 1) if len(self.frame_times)>1 and self.running else 0,
                    "frame_age_ms": round((time.monotonic()-self.preview_published)*1000) if self.preview_published is not None and self.running else None}

    def public_state(self):
        with self.lock:
            if self.data['work_date']!=today():
                self.automatic=False
            result = self.state()
            result['today']=today()
            result.update(application='MOACUT',version='0.1.0')
            result['works']=self.works.list(self.data)
            result['can_capture']=self.data['work_date']==today()
            product = {k:v for k,v in (self.product_result or {}).items() if k not in ('gray','frame_time','generation')}
            result.update(automatic=self.automatic, product={**self.product_status,**product},
                calibrated=self.detector.reference is not None)
            gate=product_gate(self.product_result,self.gray(self.frame) if self.frame is not None else None,time.monotonic(),self.generation)
            if not self.running:
                gate.update(current=False,eligible=False)
            result['product'].update(gate)
            result['capture_status']=capture_feedback(result)
        result['export_directory']=str(self.export_directory)
        result['local_export']=next((e for e in reversed(result['events']) if e['event']=='local_export'),None)
        try:
            result['export_preview']=[{'id':g['id'],'folder':g['folder'],'count':len(g['photos'])} for g in self.export_selection()]
        except ValueError:
            result['export_preview']=[]
        return result

    def gray(self, frame):
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = self.roi
        crop = frame[int(y1*h):int(y2*h), int(x1*w):int(x2*w)]
        return cv2.GaussianBlur(cv2.cvtColor(cv2.resize(crop, (160, 100)), cv2.COLOR_BGR2GRAY), (5, 5), 0)

    def start(self):
        with self.lock:
            if self.running:
                return
            camera = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not camera.isOpened():
                camera.release()
                raise ValueError("카메라를 열 수 없습니다. 다른 카메라 앱을 닫고 다시 연결해 주세요.")
            camera.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
            camera.set(cv2.CAP_PROP_FPS, 30)
            self.camera = camera
            self.frame = None
            self.preview = None
            self.frame_times.clear()
            self.gray_history.clear()
            self.camera_started = time.monotonic()
            self.generation += 1
            self.automatic = False
            self.product_result = None
            self.running = True
            self.error = ""
            self.detector = Detector()
            self.status = {"state": "uncalibrated"}
            self.event("camera_start")
            self.persist()
            self.thread = threading.Thread(target=self.loop, daemon=True)
            self.thread.start()
            self.product_thread = threading.Thread(target=self.product_loop, daemon=True)
            self.product_thread.start()

    def stop(self):
        self.running = False
        self.automatic = False
        if self.thread:
            self.thread.join(timeout=5)
        if self.product_thread:
            self.product_thread.join(timeout=10)
        with self.lock:
            self.preview = None
            self.frame_ready.notify_all()
            self.event("camera_stop")
            self.persist()

    def loop(self):
        previous_time = time.monotonic()
        last_save = previous_time
        try:
            while self.running:
                ok, frame = self.camera.read()
                if not ok:
                    raise ValueError("카메라 영상이 끊겼습니다. 다시 연결해 주세요.")
                now = time.monotonic()
                small = cv2.resize(frame, (800, round(frame.shape[0]*800/frame.shape[1])))
                ok_jpeg, jpeg = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 75])
                with self.lock:
                    if self.data['work_date']!=today():self.automatic=False
                    self.data["active_seconds"] += now - previous_time
                    previous_time = now
                    self.frame = frame
                    gray = self.gray(frame)
                    if self.inference_watch is not None and float(cv2.absdiff(gray,self.inference_watch['gray']).mean())>=8:
                        self.inference_watch['changed']=True
                    self.gray_history.append((now, gray))
                    self.observe_product_change(gray)
                    allowed = self.automatic and not self.waiting_for_product_change and current_product(self.product_result,gray,now,self.generation)
                    self.status = self.detector.update(gray, now, allow_capture=allowed)
                    if self.status.get("boundary"):
                        self.event("possible_boundary", group=self.active_group,
                                   reason="desk_absent_1.2s_needs_review")
                        self.persist()
                    if self.status.get("capture") and allowed and self.data["brand"].strip():
                        self.capture("auto")
                    if ok_jpeg:
                        self.preview = jpeg.tobytes()
                        self.sequence += 1
                        self.preview_published = time.monotonic()
                        self.frame_times.append(self.preview_published)
                        self.frame_ready.notify_all()
                    if now - last_save >= 5:
                        self.persist()
                        last_save = now
        except Exception as exc:
            with self.lock:
                self.error = str(exc)
                self.event("camera_error", message=self.error)
                self.persist()
        finally:
            self.camera.release()
            with self.lock:
                self.running = False
                self.preview = None
                self.status = {"state": "stopped"}
                self.frame_ready.notify_all()

    def product_loop(self):
        try:
            self.product_status = {"state":"loading"}
            if self.product_model is None:
                self.product_model = ProductDetector()
            self.product_status = {"state":"ready"}
            seen = 0
            previous_generation = -1
            while self.running:
                start = time.monotonic()
                with self.lock:
                    frame = self.frame
                    generation = self.generation
                    roi = list(self.roi)
                    frame_time = self.frame_times[-1] if self.frame_times else start
                    if frame is not None:
                        h,w = frame.shape[:2]
                        x1,y1,x2,y2=roi
                        crop=frame[int(y1*h):int(y2*h),int(x1*w):int(x2*w)].copy()
                        gray=self.gray(frame)
                        watch={'gray':gray,'changed':False}
                        self.inference_watch=watch
                if frame is None:
                    time.sleep(.1)
                    continue
                detected = self.product_model.detect(crop)
                with self.lock:
                    self.inference_watch=None
                    if self.running and self.generation==generation and not watch['changed'] and float(cv2.absdiff(self.gray(self.frame),gray).mean())<8:
                        seen = seen+1 if detected['present'] and previous_generation==generation else (1 if detected['present'] else 0)
                        previous_generation = generation
                        self.product_result={**detected,'seen':seen,'gray':gray,'roi':roi,
                            'frame_time':time.monotonic(),'source_frame_time':frame_time,'generation':generation}
                    else:
                        seen=0;previous_generation=None
                time.sleep(max(0,.25-(time.monotonic()-start)))
        except Exception:
            with self.lock:
                self.product_status={"state":"error","message":"상품 검출기를 준비하지 못했습니다. 모델 파일과 실행 환경을 확인해 주세요."}
                self.product_result=None
                self.automatic=False

    def group(self, gid):
        group = next((g for g in self.data["groups"] if g["id"] == gid), None)
        if group is None:
            raise ValueError("묶음을 찾지 못했습니다.")
        return group

    def thumbnail(self, name):
        cached = self.thumb_cache.get(name)
        if cached is None:
            frame = cv2.imread(str(self.directory / name))
            if frame is None:
                raise FileNotFoundError(name)
            h, w = frame.shape[:2]
            small = cv2.resize(frame, (320, max(1, round(h*320/w))))
            ok, jpeg = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if not ok:
                raise ValueError("미리보기를 만들 수 없습니다.")
            if len(self.thumb_cache) >= 128:
                self.thumb_cache.clear()
            cached = jpeg.tobytes()
            self.thumb_cache[name] = cached
        return cached

    def observe_product_change(self,gray):
        if self.waiting_for_product_change and self.completed_gray is not None:
            difference=float(compensated_difference(gray.astype('float32'),self.completed_gray).mean())
            if difference>=6:
                self.waiting_for_product_change=False

    def capture(self, reason):
        with self.lock:
            if self.data['work_date']!=today():
                self.automatic=False
                if reason=='auto':return None
                raise ValueError('날짜가 바뀌었습니다. 오늘 새 작업을 시작해 주세요.')
            if not self.running or self.frame is None:
                raise ValueError("카메라를 먼저 연결해 주세요.")
            if not self.data["brand"].strip():
                raise ValueError("브랜드를 먼저 입력해 주세요.")
            self.observe_product_change(self.gray(self.frame))
            if reason=='auto' and (self.waiting_for_product_change or not self.automatic or not current_product(self.product_result,self.gray(self.frame),time.monotonic(),self.generation)):
                return None
            gid = self.active_group
            if gid is not None and (self.group(gid).get('capture_complete') or sum(not p.get('deleted_at') for p in self.group(gid)['photos'])>=SHOTS_PER_PRODUCT):
                gid=None
            if gid is None:
                gid = uuid.uuid4().hex
                self.data["groups"].append({"id": gid, "brand": self.data["brand"],
                    "created": stamp(), "reviewed": False, "photos": [],"capture_limit":SHOTS_PER_PRODUCT})
                self.active_group = gid
                self.waiting_for_product_change=False
            group = self.group(gid)
            name = uuid.uuid4().hex + ".jpg"
            ok, image = cv2.imencode(".jpg", self.frame, [cv2.IMWRITE_JPEG_QUALITY, 96])
            if not ok:
                raise ValueError("사진을 저장하지 못했습니다.")
            with (self.directory / name).open("xb") as output:
                output.write(image.tobytes())
            photo={"file": name, "at": stamp(), "reason": reason,
                "excluded": False, "width": self.frame.shape[1], "height": self.frame.shape[0]}
            if reason=='auto':
                photo['product_detection']={k:copy.deepcopy(v) for k,v in self.product_result.items()
                    if k in ('objects','inference_ms','roi','seen')}
                photo['framing_warning']=product_gate(self.product_result,self.gray(self.frame),time.monotonic(),self.generation)['edge_warning']
            group["photos"].append(photo)
            group["reviewed"] = False
            shot_number=sum(not p.get('deleted_at') for p in group['photos'])
            complete=shot_number==SHOTS_PER_PRODUCT
            self.event("capture", group=gid, file=name, reason=reason,shot_number=shot_number,product_complete=complete)
            if complete:
                group['capture_complete']=True
                self.last_completed_group=gid
                self.active_group=None
                self.waiting_for_product_change=True
                self.completed_gray=self.gray(self.frame).astype('float32')
                self.detector.last_capture=self.completed_gray.copy()
                self.detector.armed=False
                self.event('product_complete',group=gid,shots=SHOTS_PER_PRODUCT)
            self.persist()
            return name

    def action(self, payload):
        with self.lock:
            action = payload.get("action")
            if action == 'guide':
                steps=payload.get('steps')
                if not isinstance(steps,list) or len(steps)>20 or any(not isinstance(s,str) or not s.strip() or len(s)>100 or any(ord(c)<32 for c in s) for s in steps):
                    raise ValueError('촬영 항목은 최대 20개, 항목마다 1~100자로 입력해 주세요.')
                self.data['guide_steps']=[s.strip() for s in steps]
                self.automatic=False
                self.event('guide_changed',count=len(steps))
            elif action == "brand":
                brand = payload.get("brand", "")
                if not isinstance(brand, str) or not 1 <= len(brand.strip()) <= 100:
                    raise ValueError("브랜드를 1~100자로 입력해 주세요.")
                if brand.strip() != self.data["brand"]:
                    self.data["brand"] = brand.strip()
                    self.active_group = None
                    self.waiting_for_product_change=False
                    self.detector.last_capture = None
                    self.event("brand_changed", brand=brand.strip())
            elif action == "automatic":
                enabled=payload.get('enabled')
                if type(enabled) is not bool:
                    raise ValueError('촬영 상태가 올바르지 않습니다.')
                if enabled and self.data['work_date']!=today():
                    raise ValueError('오늘 새 작업을 시작한 뒤 촬영해 주세요.')
                if enabled and (not self.running or not self.data['brand'].strip() or self.detector.reference is None or self.product_status.get('state')!='ready'):
                    raise ValueError('카메라·브랜드·빈 책상 등록·상품 검출기 준비를 먼저 완료해 주세요.')
                self.automatic=enabled
                if not self.waiting_for_product_change:
                    self.detector.last_capture=None
                    self.detector.armed=True
                self.detector.stable_since=None
                self.event('automatic_changed',enabled=enabled)
            elif action == "calibrate":
                if self.frame is None or not self.running:
                    raise ValueError("카메라를 먼저 연결해 주세요.")
                roi = payload.get("roi", self.roi)
                if not isinstance(roi, list) or len(roi) != 4 or any(type(v) not in (int, float) for v in roi):
                    raise ValueError("책상 영역을 다시 지정해 주세요.")
                x1, y1, x2, y2 = roi
                if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1 and x2-x1 >= .1 and y2-y1 >= .1):
                    raise ValueError("책상 영역은 화면의 가로·세로 10% 이상으로 지정해 주세요.")
                if self.camera_started is None or time.monotonic()-self.camera_started < 2:
                    raise ValueError("카메라 노출이 안정되도록 연결 후 2초 정도 기다려 주세요.")
                if roi != self.roi:
                    self.roi = roi
                    self.gray_history.clear()
                    self.detector = Detector()
                    self.automatic=False
                    self.generation+=1
                    self.product_result=None
                    raise ValueError("영역을 변경했습니다. 손과 상품을 치우고 1초 뒤 빈 책상을 등록해 주세요.")
                samples = [(t, g) for t, g in self.gray_history if time.monotonic()-t <= 1.2]
                if len(samples)<8 or samples[-1][0]-samples[0][0] < .6:
                    raise ValueError("빈 책상 화면을 모으는 중입니다. 잠깐 뒤 다시 등록해 주세요.")
                motion = max(float(compensated_difference(b[1].astype('float32'), a[1].astype('float32')).mean()) for a, b in zip(samples, samples[1:]))
                if motion > 2.5:
                    raise ValueError("책상 영역이 움직이고 있습니다. 손과 상품을 치운 뒤 다시 등록해 주세요.")
                self.detector.calibrate([g for _, g in samples])
                self.generation += 1
                self.product_result=None
                self.automatic=False
                self.waiting_for_product_change=False
                self.event("desk_calibrated", roi=roi)
            elif action == "capture":
                return self.capture("manual")
            elif action == "new_group":
                self.active_group = None
                self.waiting_for_product_change=False
                self.detector.last_capture = None
                self.event("manual_boundary")
            elif action == "review":
                group = self.group(payload.get("group"))
                group["reviewed"] = not group["reviewed"]
                self.event("review", group=group["id"], reviewed=group["reviewed"])
            elif action in ('delete_photo','restore_photo','exclude'):
                group = self.group(payload.get("group"))
                photo = next((p for p in group["photos"] if p["file"] == payload.get("file")), None)
                if photo is None:
                    raise ValueError("사진을 찾지 못했습니다.")
                previous_photo=copy.deepcopy(photo)
                previous_review=group['reviewed'];previous_active=self.active_group
                if action=='delete_photo':
                    photo['deleted_at']=stamp()
                elif action=='restore_photo':
                    if self.active_group==group['id'] and sum(not p.get('deleted_at') for p in group['photos'])+1>=SHOTS_PER_PRODUCT:
                        self.active_group=None
                    photo.pop('deleted_at',None)
                else:
                    photo["excluded"] = not photo["excluded"]
                group["reviewed"] = False
                self.event(action, file=photo['file'],group=group['id'])
                try:self.persist()
                except OSError:
                    photo.clear();photo.update(previous_photo)
                    group['reviewed']=previous_review;self.active_group=previous_active
                    self.data['resume_group']=previous_active
                    self.data['events'].pop()
                    raise
                return
            elif action == "merge":
                group = self.group(payload.get("group"))
                index = self.data["groups"].index(group)
                if index == 0:
                    raise ValueError("앞 묶음이 없습니다.")
                previous = self.data["groups"][index-1]
                if previous["brand"] != group["brand"]:
                    raise ValueError("브랜드가 다른 묶음은 합칠 수 없습니다.")
                previous["photos"].extend(group["photos"])
                previous["reviewed"] = False
                self.data["groups"].remove(group)
                if self.active_group == group["id"]:
                    self.active_group = previous["id"]
                self.event("merge", source=group["id"], target=previous["id"])
            elif action == "split":
                group = self.group(payload.get("group"))
                index = next((i for i, p in enumerate(group["photos"]) if p["file"] == payload.get("file")), -1)
                if index <= 0:
                    raise ValueError("두 번째 사진부터 나눌 수 있습니다.")
                new = {"id": uuid.uuid4().hex, "brand": group["brand"], "created": stamp(),
                       "reviewed": False, "photos": group["photos"][index:]}
                group["photos"] = group["photos"][:index]
                group["reviewed"] = False
                self.data["groups"].insert(self.data["groups"].index(group)+1, new)
                if self.active_group == group["id"]:
                    self.active_group = new["id"]
                self.event("split", source=group["id"], target=new["id"])
            else:
                raise ValueError("지원하지 않는 작업입니다.")
            self.persist()

    def export(self):
        selection=self.export_selection()
        archive=BytesIO()
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_STORED) as output:
            for group in selection:
                for i,photo in enumerate(group['photos'],1):
                    output.write(self.directory/photo['file'],f"{group['folder']}/{i:02d}.jpg")
            output.writestr('manifest.json',json.dumps(selection,ensure_ascii=False,indent=2))
        return archive.getvalue()

    def export_selection(self):
        with self.lock:
            groups=copy.deepcopy(self.data['groups'])
            work={k:self.data[k] for k in ('work_id','work_date','work_name')}
        result=[]
        for index,group in enumerate(groups,1):
            if not group['reviewed']:
                continue
            photos=[p for p in group['photos'] if not p['excluded'] and not p.get('deleted_at')]
            if not photos:
                continue
            if any(not re.fullmatch(r'[0-9a-f]{32}\.jpg',p['file']) for p in photos):
                raise ValueError('저장 사진 이름이 올바르지 않습니다.')
            original=group['brand']
            brand=re.sub(r'[\\/<>:"|?*\x00-\x1f]','_',unicodedata.normalize('NFKC',original)).strip(' .')[:70] or '미지정'
            reserved=brand.split('.')[0].upper() in ('CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(10)),*(f'LPT{i}' for i in range(10)))
            if brand!=original or reserved:
                brand=('_' if reserved else '')+brand+'_'+hashlib.sha256(original.encode()).hexdigest()[:6]
            result.append({**group,'photos':photos,'folder':f'{brand}/상품_{index:03d}','brand_folder':brand,'number':index,
                **work})
        if not result:
            raise ValueError('검토 완료한 묶음이 없습니다. 사진 확인 단계에서 묶음을 확인해 주세요.')
        return result

    def set_export_directory(self,path):
        candidate=local_folder(path)
        if not self.export_lock.acquire(blocking=False):
            raise ValueError('사진을 저장 중입니다. 완료 후 저장 위치를 바꿔 주세요.')
        try:
            try:
                with tempfile.TemporaryFile(dir=candidate,prefix='.moacut-check-') as probe:
                    probe.write(b'folder check')
            except OSError as exc:
                raise ValueError('선택한 폴더에 저장할 수 없습니다. 다른 폴더를 선택해 주세요.') from exc
            with self.lock:
                previous=self.export_directory;stored=self.data.get('export_directory')
                self.export_directory=candidate;self.data['export_directory']=str(candidate)
                self.event('export_directory_changed',path=str(candidate))
                try:self.persist()
                except OSError:
                    self.export_directory=previous
                    if stored is None:self.data.pop('export_directory',None)
                    else:self.data['export_directory']=stored
                    self.data['events'].pop()
                    raise
        finally:self.export_lock.release()

    def save_local(self):
        if not self.export_lock.acquire(blocking=False):
            raise ValueError('폴더에 저장 중입니다. 잠시 기다려 주세요.')
        try:
            return self._save_local()
        finally:
            self.export_lock.release()

    def _save_local(self):
        selected=self.export_selection()
        if self.data.get('export_directory') and not self.export_directory.is_dir():
            raise ValueError('선택한 저장 폴더를 찾을 수 없습니다. 저장 위치를 다시 선택해 주세요.')
        self.export_directory.mkdir(parents=True,exist_ok=True)
        name='촬영_'+self.data['work_date'].replace('-','')+'_'+time.strftime('%H%M%S')+'_'+uuid.uuid4().hex[:8]
        destination=self.export_directory/name
        staging=self.export_directory/('.저장중_'+uuid.uuid4().hex)
        staging.mkdir()
        count=0
        for group in selected:
            folder=staging/group['folder']
            folder.mkdir(parents=True)
            for index,photo in enumerate(group['photos'],1):
                source=self.directory/photo['file']
                target=folder/f'{index:02d}.jpg'
                shutil.copyfile(source,target)
                with source.open('rb') as stream: original_hash=hashlib.file_digest(stream,'sha256').hexdigest()
                with target.open('rb') as stream: copied_hash=hashlib.file_digest(stream,'sha256').hexdigest()
                if original_hash!=copied_hash:
                    raise OSError('사진 복사 검증에 실패했습니다.')
                photo.update(export_file=f"{group['folder']}/{index:02d}.jpg",sha256=copied_hash)
                count+=1
        (staging/'manifest.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding='utf-8')
        # Publish only a fully copied result; a failed staging folder is never shown as complete.
        staging.rename(destination)
        with self.lock:
            self.event('local_export',path=str(destination),root=str(self.export_directory),groups=len(selected),photos=count)
            self.persist()
        return destination

    def open_export(self):
        with self.lock:
            saved=next((e for e in reversed(self.data['events']) if e['event']=='local_export'),None)
        path=Path(saved['path']).resolve() if saved else self.export_directory
        saved_root=Path(saved.get('root',path.parent)).resolve() if saved else self.export_directory
        if saved and (path.parent!=saved_root or not re.fullmatch(r'촬영_\d{8}_\d{6}_[0-9a-f]{8}',path.name)):
            raise ValueError('저장 폴더 위치를 확인할 수 없습니다.')
        if not path.is_dir():
            raise ValueError('저장 폴더가 없습니다. 먼저 폴더로 저장해 주세요.')
        os.startfile(str(path))


def handler_for(trial, port):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send(self, data, kind="application/json; charset=utf-8", code=200, cache="no-store"):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def local(self):
            host = self.headers.get("Host", "")
            if host not in (f"127.0.0.1:{port}", f"localhost:{port}"):
                return False
            origin = self.headers.get("Origin")
            return origin is None or origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")

        def do_GET(self):
            if not self.local():
                self.send(b'{}', code=403)
                return
            path = urlparse(self.path).path
            try:
                if path == "/api/state":
                    self.send(json.dumps(trial.public_state(), ensure_ascii=False).encode())
                elif path == '/api/local/folders':
                    selected_path=parse_qs(urlparse(self.path).query).get('path',[None])[0]
                    self.send(json.dumps(list_folders(selected_path),ensure_ascii=False).encode())
                elif path == '/api/voice':
                    text=parse_qs(urlparse(self.path).query).get('text',[''])[0]
                    try:
                        data=trial.voice.render(text)
                    except OSError:
                        self.send(json.dumps({'error':'음성 안내를 준비하지 못했습니다. 촬영음과 화면 알림은 계속 사용할 수 있습니다.'},ensure_ascii=False).encode(),code=503)
                        return
                    self.send(data,'audio/wav',cache='private, max-age=31536000, immutable')
                elif path == "/api/stream":
                    self.stream()
                elif path == "/api/preview":
                    with trial.lock:
                        picture = trial.preview
                    self.send(picture or b"", "image/jpeg", 200 if picture else 204)
                elif path == "/api/export":
                    self.send(trial.export(), "application/zip")
                elif re.fullmatch(r"/photos/[0-9a-f]{32}\.jpg", path):
                    self.send((trial.directory / path.split("/")[-1]).read_bytes(), "image/jpeg")
                elif re.fullmatch(r"/thumbs/[0-9a-f]{32}\.jpg", path):
                    self.send(trial.thumbnail(path.split("/")[-1]), "image/jpeg", cache="private, max-age=3600")
                elif path in ("/", "/app.js", "/capture-flow.js", "/detector-ui.css"):
                    file = ROOT / "web" / ("index.html" if path == "/" else path[1:])
                    kind = {".html": "text/html", ".js": "text/javascript", ".css": "text/css"}[file.suffix]
                    self.send(file.read_bytes(), kind + "; charset=utf-8")
                else:
                    self.send(b'{}', code=404)
            except ValueError as exc:
                self.send(json.dumps({"error": str(exc)}, ensure_ascii=False).encode(), code=400)
            except FileNotFoundError:
                self.send(b'{}', code=404)

        def stream(self):
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            last = -1
            try:
                while True:
                    with trial.frame_ready:
                        trial.frame_ready.wait_for(lambda: not trial.running or
                            (trial.preview is not None and trial.sequence != last), timeout=2)
                        if not trial.running:
                            break
                        if trial.sequence == last or trial.preview is None:
                            continue
                        last = trial.sequence
                        picture = trial.preview
                        age = round((time.monotonic()-trial.preview_published)*1000)
                    # Each client gets the newest frame; no per-client frame queue.
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n" +
                        f"Content-Length: {len(picture)}\r\nX-Sequence: {last}\r\nX-Age-Ms: {age}\r\n\r\n".encode() + picture + b"\r\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def do_POST(self):
            if not self.local() or self.headers.get("Content-Type") != "application/json":
                self.send(b'{}', code=403)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    raise ValueError("요청 크기가 올바르지 않습니다.")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("잘못된 요청입니다.")
                path = urlparse(self.path).path
                if path == "/api/start":
                    trial.start()
                elif path == "/api/stop":
                    trial.stop()
                elif path == "/api/action":
                    trial.action(payload)
                elif path == '/api/work':
                    trial.switch_work(payload)
                elif path == '/api/local/save':
                    trial.save_local()
                elif path == '/api/local/destination':
                    trial.set_export_directory(payload.get('path'))
                elif path == '/api/local/open':
                    trial.open_export()
                else:
                    raise ValueError("알 수 없는 작업입니다.")
                self.send(json.dumps(trial.public_state(), ensure_ascii=False).encode())
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.send(json.dumps({"error": str(exc)}, ensure_ascii=False).encode(), code=400)
            except OSError:
                self.send(json.dumps({"error": "저장에 실패했습니다. 디스크 공간과 폴더 권한을 확인해 주세요."}, ensure_ascii=False).encode(), code=500)
    return Handler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--data", type=Path, default=ROOT / "captures")
    parser.add_argument("--open", action="store_true", help="Open the local screen after server startup")
    args = parser.parse_args()
    trial = Trial(args.data, args.camera)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), lambda *a:None)
    server.RequestHandlerClass=handler_for(trial,server.server_port)
    url=f'http://127.0.0.1:{server.server_port}'
    print(f"MOACUT: {url}", flush=True)
    if args.open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    finally:
        trial.stop()
        server.server_close()


if __name__ == "__main__":
    main()
