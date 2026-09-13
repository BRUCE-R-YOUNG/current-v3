import base64
import hmac
import io
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import EdgeConfig
from .runtime import service_root
from .store import Store


class Telemetry(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    window_start: float = Field(ge=0)
    window_end: float = Field(ge=0)
    expected_frames: int = Field(ge=1,le=60)
    actual_frames: int = Field(ge=0,le=60)
    people_mean: float | None = Field(default=None,ge=0,le=10000)
    floor_mean: float | None = Field(default=None,ge=1,le=200)
    floor: int | None = Field(default=None,ge=1,le=200)
    direction: Literal['UP','DOWN'] | None = None
    up_ratio: float | None = Field(default=None,ge=0,le=1)
    down_ratio: float | None = Field(default=None,ge=0,le=1)
    return_seconds_mean: float | None = Field(default=None,ge=0)

    @model_validator(mode='after')
    def valid_window(self):
        if self.window_end < self.window_start or self.actual_frames > self.expected_frames:
            raise ValueError('Invalid inference window')
        return self


def create_app(config_path: Path):
    config_path = config_path.resolve()
    root = service_root(config_path)
    store = Store(root/'events.sqlite3')
    app = FastAPI(title='Sustainable Vision Learning',version='3.0.0')
    jobs = {}
    job_lock = threading.Lock()

    def auth(req: Request):
        cfg = EdgeConfig.load(config_path)
        token = os.environ.get(cfg.token_env,'')
        value = req.headers.get('authorization','')
        if not token or not hmac.compare_digest(value,f'Bearer {token}'):
            raise HTTPException(401,'Bearer token required')

    def manager():
        from app.config import load_config
        from app.platform import ProjectManager
        return ProjectManager(load_config())

    @app.get('/',response_class=HTMLResponse)
    @app.get('/v3',response_class=HTMLResponse)
    def dashboard():
        return Path(__file__).with_name('dashboard.html').read_text(encoding='utf-8')

    @app.get('/v3/config',dependencies=[Depends(auth)])
    def get_config():
        return EdgeConfig.load(config_path).model_dump(mode='json')

    @app.put('/v3/config',dependencies=[Depends(auth)])
    def save_config(cfg: EdgeConfig):
        with job_lock:
            if any(p.poll() is None for p in jobs.values()):
                raise HTTPException(409,'Stop services before changing configuration')
            # CLI jobs also hold these OS locks. Settings are a startup snapshot.
            from contextlib import ExitStack
            from .runtime import service_lock
            try:
                with ExitStack() as stack:
                    for name in ('camera','transfer','train','label'):
                        stack.enter_context(service_lock(root,name))
                    cfg.save(config_path)
            except OSError:
                raise HTTPException(409,'A standalone service is running')
        return cfg.model_dump(mode='json')

    @app.get('/v3/status',dependencies=[Depends(auth)])
    def status():
        data = store.snapshot()
        data['role'] = EdgeConfig.load(config_path).role
        data['processes'] = {name:dict(pid=p.pid,running=p.poll() is None,exit_code=p.poll()) for name,p in jobs.items()}
        return data

    @app.post('/v3/services/{name}/{action}',dependencies=[Depends(auth)])
    def service(name: str,action: str):
        cfg = EdgeConfig.load(config_path)
        allowed = ('production','capture','transfer') if cfg.role == 'edge' else ('train','label')
        if name not in allowed or action not in ('start','stop'):
            raise HTTPException(400,'Service is not available for this device role')
        with job_lock:
            if action == 'stop':
                (root/f'{name}.stop').touch()
                return {'status':'stop_requested'}
            if name in jobs and jobs[name].poll() is None:
                raise HTTPException(409,'Already running')
            if name in ('production','capture') and any(jobs.get(n) and jobs[n].poll() is None for n in ('production','capture')):
                raise HTTPException(409,'The camera is already in use')
            with (root/f'{name}.log').open('ab') as log:
                jobs[name] = subprocess.Popen([sys.executable,'-m','app.edge',name,'--config',str(config_path)],
                    stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            return {'status':'starting','pid':jobs[name].pid}

    @app.get('/v3/files',dependencies=[Depends(auth)])
    def files(path: str = ''):
        target = Path(path).expanduser() if path else Path.cwd()
        if target.is_file():
            target = target.parent
        try:
            target = target.resolve(strict=True)
            entries = sorted(target.iterdir(),key=lambda p:(not p.is_dir(),p.name.lower()))
            entries = [dict(path=str(p),name=p.name,directory=p.is_dir()) for p in entries if p.is_dir() or p.suffix.lower() in ('.pt','.onnx','.yaml','.yml','.mp4','.avi')][:250]
        except OSError as exc:
            raise HTTPException(400,str(exc))
        return dict(path=str(target),parent=str(target.parent),entries=entries)

    @app.get('/v3/preview',dependencies=[Depends(auth)])
    def preview():
        if EdgeConfig.load(config_path).role == 'edge':
            path = root/'preview.jpg'
            if path.exists():
                return Response(path.read_bytes(),media_type='image/jpeg',headers={'Cache-Control':'no-store'})
        with store.connect() as db:
            row = db.execute("SELECT image FROM events WHERE kind='image' ORDER BY created DESC LIMIT 1").fetchone()
        if not row:
            raise HTTPException(404,'No captured image yet')
        return Response(row[0],media_type='image/jpeg',headers={'Cache-Control':'no-store'})

    @app.get('/v3/projects',dependencies=[Depends(auth)])
    def projects():
        return manager().list_projects()

    @app.post('/v3/projects',dependencies=[Depends(auth)])
    def create_project(payload: dict):
        if EdgeConfig.load(config_path).role != 'server':
            raise HTTPException(400,'Create training projects on PC')
        try:
            return manager().create_project(payload['project_id'],payload.get('project_name'),payload.get('class_names'))
        except (KeyError,ValueError) as exc:
            raise HTTPException(400,str(exc))

    @app.post('/v3/ingest',dependencies=[Depends(auth)])
    async def ingest(req: Request):
        cfg = EdgeConfig.load(config_path)
        if cfg.role != 'server':
            raise HTTPException(400,'Receiver requires role=server')
        body = bytearray()
        async for chunk in req.stream():
            body.extend(chunk)
            if len(body)>2_000_000:
                raise HTTPException(413,'Event exceeds 2 MB')
        try:
            data = json.loads(body,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Non-finite JSON')))
            if not isinstance(data,dict):
                raise ValueError('JSON object required')
            event_id = data.get('event_id','')
            if not isinstance(event_id,str) or not re.fullmatch('[0-9a-f]{32}',event_id):
                raise ValueError('event_id must be a lowercase UUID hex string')
            kind = data.get('kind')
            if kind not in ('image','telemetry'):
                raise ValueError('kind must be image or telemetry')
            if not re.fullmatch('[a-zA-Z0-9_-]{1,64}',str(data.get('device_id',''))):
                raise ValueError('Invalid device_id')
            project = data.get('project_id','')
            if not isinstance(project,str) or not re.fullmatch('[a-z0-9][a-z0-9_-]{0,62}',project):
                raise ValueError('Invalid project_id')
            if not manager().exists(project):
                raise HTTPException(404,'Create the project on PC before receiving events')
            image = None
            if kind == 'image':
                image = base64.b64decode(data.pop('jpeg_base64'),validate=True)
                with Image.open(io.BytesIO(image)) as im:
                    if im.format != 'JPEG' or im.width*im.height>4_000_000:
                        raise ValueError('JPEG image up to 4 megapixels required')
                    im.verify()
            elif len(body)>32_000:
                raise ValueError('Telemetry exceeds 32 KB')
            else:
                Telemetry.model_validate(data)
            store.add(kind,data,image,event_id=event_id,limit=cfg.spool_limit_bytes)
        except (ValueError,KeyError,TypeError,OSError) as exc:
            raise HTTPException(400,str(exc))
        except RuntimeError as exc:
            raise HTTPException(507,str(exc))
        return dict(event_id=event_id,status='stored')

    return app
