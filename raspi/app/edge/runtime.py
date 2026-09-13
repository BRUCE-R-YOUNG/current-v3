import contextlib
import json
import os
import threading
import time
from pathlib import Path
from urllib import request

import cv2
import numpy as np

from .aggregate import summarize
from .config import EdgeConfig
from .store import Store


def service_root(config_path: Path) -> Path:
    root = config_path.resolve().parent / "runtime" / config_path.stem
    root.mkdir(parents=True, exist_ok=True)
    return root


@contextlib.contextmanager
def service_lock(root: Path, name: str):
    with (root / f"{name}.lock").open("a+b") as lock:
        lock.seek(0)
        lock.write(b'0')
        lock.flush()
        lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


class LatestCamera:
    def __init__(self, source):
        self.source = int(source) if source.isdecimal() else source
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.value = None
        self.sequence = 0
        self.thread = threading.Thread(target=self.read, daemon=True)

    def read(self):
        while not self.stop.is_set():
            cap = cv2.VideoCapture(self.source)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            try:
                while not self.stop.is_set():
                    ok, frame = cap.read()
                    if not ok:
                        break
                    with self.lock:
                        self.sequence += 1
                        self.value = (self.sequence, time.time(), frame)
            finally:
                cap.release()
            self.stop.wait(2)

    def get(self, previous):
        with self.lock:
            if self.value and self.value[0] != previous and time.time()-self.value[1] < 2:
                return self.value[0], self.value[1], self.value[2].copy()
        return previous, None, None

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.stop.set()
        self.thread.join(timeout=3)


def crop(frame, cfg):
    h,w = frame.shape[:2]
    x1,y1,x2,y2 = cfg.roi
    return frame[int(y1*h):max(int(y2*h),int(y1*h)+1),int(x1*w):max(int(x2*w),int(x1*w)+1)]


class Predictor:
    def __init__(self, cfg):
        from ultralytics import YOLO
        for path in (cfg.people_model, cfg.elevator_model):
            if not path or not Path(path).is_file():
                raise ValueError("Select existing people_model and elevator_model files")
        self.people = YOLO(cfg.people_model)
        self.elevator = YOLO(cfg.elevator_model)
        self.cfg = cfg

    def detect(self, model, frame):
        results = model.predict(frame, imgsz=self.cfg.imgsz, conf=self.cfg.confidence, device=self.cfg.device, verbose=False)
        return [dict(label=str(r.names[int(b.cls.item())]), confidence=float(b.conf.item()), xyxy=b.xyxy[0].tolist()) for r in results if r.boxes is not None for b in r.boxes]

    def __call__(self, frame):
        people = self.detect(self.people, frame)
        panel = self.detect(self.elevator, crop(frame,self.cfg))
        floors = sorted([d for d in panel if d['label'] in self.cfg.floor_map], key=lambda d:d['confidence'], reverse=True)
        arrows = sorted([d for d in panel if d['label'] in self.cfg.up_classes+self.cfg.down_classes], key=lambda d:d['confidence'], reverse=True)
        floor = self.cfg.floor_map[floors[0]['label']] if floors else None
        direction = ('UP' if arrows[0]['label'] in self.cfg.up_classes else 'DOWN') if arrows else None
        if len(arrows)>1 and (arrows[0]['label'] in self.cfg.up_classes) != (arrows[1]['label'] in self.cfg.up_classes) and arrows[0]['confidence']-arrows[1]['confidence'] < 0.1:
            direction = None
        return dict(people=sum(d['label'] in self.cfg.people_classes for d in people),floor=floor,direction=direction,
                    confidence=min([d['confidence'] for d in floors[:1]+arrows[:1]],default=0),detections=panel)


class Collector:
    def __init__(self, cfg, store):
        self.cfg,self.store = cfg,store
        self.last_time = -float('inf')
        self.last_small = None

    def capture(self, frame, observation=None):
        now = time.monotonic()
        if now-self.last_time < self.cfg.capture_seconds:
            return
        if observation is not None and self.cfg.difficult_only and observation['floor'] is not None and observation['direction'] is not None and observation['confidence'] >= self.cfg.difficult_confidence:
            return
        panel = crop(frame,self.cfg)
        small = cv2.resize(cv2.cvtColor(panel,cv2.COLOR_BGR2GRAY),(32,32)).astype(np.float32)/255
        if self.last_small is not None and float(np.mean(np.abs(small-self.last_small))) < self.cfg.duplicate_threshold:
            return
        ratio = min(1,self.cfg.jpeg_long_edge/max(panel.shape[:2]))
        panel = cv2.resize(panel,(max(1,int(panel.shape[1]*ratio)),max(1,int(panel.shape[0]*ratio))))
        ok, jpeg = cv2.imencode('.jpg',panel,[cv2.IMWRITE_JPEG_QUALITY,self.cfg.jpeg_quality])
        if not ok:
            raise RuntimeError('JPEG encoding failed')
        # Predictions describe the original ROI coordinates, not training labels for resized JPEGs.
        self.store.add('image',dict(project_id=self.cfg.project_id,device_id=self.cfg.device_id,timestamp=time.time(),roi=self.cfg.roi,
                                  prediction=observation,original_shape=list(frame.shape[:2]),image_shape=list(panel.shape[:2]),review_required=True),
                       jpeg.tobytes(),limit=self.cfg.spool_limit_bytes)
        self.last_time,self.last_small = now,small


def camera_service(cfg, root, store, mode, windows=None):
    predictor = Predictor(cfg) if mode == 'production' else None
    collector = Collector(cfg,store)
    stop = root / f'{mode}.stop'
    count, sequence = 0,0
    with service_lock(root,'camera'), LatestCamera(cfg.camera) as camera:
        stop.unlink(missing_ok=True)
        while not stop.exists() and (windows is None or count < windows):
            start = time.monotonic()
            wall = time.time()
            deadline = start+cfg.window_seconds
            frames = []
            captured_frames = 0
            for index in range(cfg.frames_per_window):
                target = start+index*cfg.window_seconds/cfg.frames_per_window
                while time.monotonic()<target and not stop.exists():
                    time.sleep(max(0,min(.05,target-time.monotonic())))
                if stop.exists() or time.monotonic()>=deadline:
                    break
                sequence, captured_at, frame = camera.get(sequence)
                if frame is None:
                    continue
                captured_frames += 1
                observation = predictor(frame) if predictor else None
                if observation is not None:
                    observation['captured_at'] = captured_at
                    frames.append(observation)
                collector.capture(frame,observation)
                ok, jpg = cv2.imencode('.jpg',cv2.resize(frame,(640,max(1,round(frame.shape[0]*640/frame.shape[1])))))
                if ok:
                    tmp = root/'preview.tmp'
                    tmp.write_bytes(jpg.tobytes())
                    tmp.replace(root/'preview.jpg')
            while time.monotonic()<deadline and not stop.exists():
                time.sleep(max(0,min(.05,deadline-time.monotonic())))
            if mode == 'production':
                payload = summarize(frames,cfg,wall,wall+time.monotonic()-start)
                payload.update(project_id=cfg.project_id,device_id=cfg.device_id,models=dict(people=Path(cfg.people_model).name,elevator=Path(cfg.elevator_model).name))
                store.add('telemetry',payload,limit=cfg.spool_limit_bytes)
            store.state(mode,dict(status='running',windows=count+1,actual_frames=captured_frames,inference_frames=len(frames),camera_sequence=sequence))
            count += 1


def send_pending(cfg, store, kind, should_stop=lambda: False):
    token = os.environ.get(cfg.token_env,'')
    if not cfg.server_url or not token:
        raise ValueError('Set server_url and the token environment variable before transfer')
    for event in store.pending(kind):
        if should_stop():
            break
        payload = json.loads(event['payload'])
        if kind == 'image':
            import base64
            payload['jpeg_base64'] = base64.b64encode(event['image']).decode('ascii')
        body = json.dumps(payload,separators=(',',':'),allow_nan=False).encode()
        # Reserve approximate headers and response bytes as well as body, including failed attempts.
        if not store.charge(kind,len(body)+2048,cfg):
            store.state('budget',dict(status='paused',reason='Transfer budget exhausted (UTC day/month)'))
            break
        store.state('budget',dict(status='available'))
        req = request.Request(cfg.server_url.rstrip('/')+'/v3/ingest',data=body,method='POST',
                              headers={'Content-Type':'application/json','Authorization':f'Bearer {token}'})
        try:
            with request.urlopen(req,timeout=cfg.timeout_seconds) as response:
                result = json.loads(response.read(65536))
                if result.get('event_id') != event['id']:
                    raise ValueError('Server acknowledgement did not match event_id')
            store.result(event['id'])
        except Exception as exc:
            store.result(event['id'],type(exc).__name__+': '+str(exc))


def transfer_service(cfg,root,store,once=False):
    stop = root/'transfer.stop'
    with service_lock(root,'transfer'):
        stop.unlink(missing_ok=True)
        next_image,next_telemetry = 0,0
        while not stop.exists():
            store.prune()
            now = time.monotonic()
            if now >= next_image:
                send_pending(cfg,store,'image',stop.exists)
                next_image = now+cfg.transfer_seconds
            if now >= next_telemetry:
                send_pending(cfg,store,'telemetry',stop.exists)
                next_telemetry = now+cfg.telemetry_seconds
            store.state('transfer',dict(status='running'))
            if once:
                break
            time.sleep(.2)
