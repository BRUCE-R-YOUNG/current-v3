import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'raspi'))
from app.edge import runtime
from app.edge.config import EdgeConfig
from app.edge.store import Store
from check_connection import check


def test_capture_does_not_construct_predictor(tmp_path, monkeypatch):
    class Camera:
        def __init__(self, source):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, previous):
            return previous + 1, 1.0, np.zeros((48, 64, 3), dtype=np.uint8)

    def forbidden(*args):
        raise AssertionError('Capture-only must not load inference models')

    monkeypatch.setattr(runtime, 'LatestCamera', Camera)
    monkeypatch.setattr(runtime, 'Predictor', forbidden)
    cfg = EdgeConfig(window_seconds=1, frames_per_window=2)
    store = Store(tmp_path / 'events.sqlite3')
    runtime.camera_service(cfg, tmp_path, store, 'capture', windows=1)
    rows = store.pending('image')
    assert len(rows) == 1
    assert rows[0]['image'].startswith(b'\xff\xd8')
    assert json.loads(rows[0]['payload'])['prediction'] is None
    assert store.pending('telemetry') == []
    state = store.snapshot()['states']['capture']
    assert state['actual_frames'] == 2
    assert state['inference_frames'] == 0


def test_periodic_transfer_schedule(tmp_path, monkeypatch):
    clock = [0.0]
    calls = []

    def sleep(seconds):
        clock[0] += seconds
        if clock[0] > 10.5:
            (tmp_path / 'transfer.stop').touch()

    monkeypatch.setattr(runtime.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(runtime.time, 'sleep', sleep)
    monkeypatch.setattr(runtime, 'send_pending',
                        lambda cfg, store, kind, stop: calls.append((kind, clock[0])))
    cfg = EdgeConfig(transfer_seconds=5, telemetry_seconds=3)
    runtime.transfer_service(cfg, tmp_path, Store(tmp_path / 'events.sqlite3'))
    images = [t for kind, t in calls if kind == 'image']
    assert len(images) == 3
    assert images[0] == 0
    assert 5 <= images[1] < 5.3
    assert 10 <= images[2] < 10.5


@pytest.fixture
def receiver():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            assert self.path == '/v3/status'
            self.reply({'counts': []})

        def do_POST(self):
            assert self.path == '/v3/ingest'
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            received.append(payload)
            self.reply({'event_id': payload['event_id']})

        def reply(self, payload):
            if self.headers.get('Authorization') != 'Bearer test-token':
                self.send_error(401)
                return
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}', received
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_http_capture_upload_ack_and_restart(tmp_path, monkeypatch, receiver):
    url, received = receiver
    monkeypatch.setenv('SVL_EDGE_TOKEN', 'test-token')
    cfg = EdgeConfig(server_url=url)
    store = Store(tmp_path / 'events.sqlite3')
    runtime.Collector(cfg, store).capture(np.zeros((48, 64, 3), dtype=np.uint8))
    store = Store(store.path)
    assert check(cfg)['counts'] == []
    assert received == []
    runtime.transfer_service(cfg, tmp_path, store, once=True)
    assert len(received) == 1
    assert received[0]['prediction'] is None
    assert received[0]['jpeg_base64']
    assert store.pending('image') == []
    runtime.transfer_service(cfg, tmp_path, store, once=True)
    assert len(received) == 1


def test_http_failure_keeps_queue_and_retries(tmp_path, monkeypatch, receiver):
    url, received = receiver
    monkeypatch.setenv('SVL_EDGE_TOKEN', 'wrong-token')
    cfg = EdgeConfig(server_url=url)
    store = Store(tmp_path / 'events.sqlite3')
    runtime.Collector(cfg, store).capture(np.zeros((48, 64, 3), dtype=np.uint8))
    runtime.send_pending(cfg, store, 'image')
    with store.connect() as db:
        event = dict(db.execute('SELECT * FROM events').fetchone())
        assert event['sent'] == 0
        assert event['attempts'] == 1
        assert '401' in event['error']
        assert event['next_try'] > event['created']
        db.execute('UPDATE events SET next_try=0')
    monkeypatch.setenv('SVL_EDGE_TOKEN', 'test-token')
    runtime.send_pending(cfg, Store(store.path), 'image')
    assert store.pending('image') == []


def test_capture_example_and_missing_token():
    path = Path(__file__).resolve().parents[1] / 'raspi/config/capture-only.example.yaml'
    cfg = EdgeConfig.load(path)
    assert cfg.people_model == cfg.elevator_model == ''
    cfg.token_env = 'SVL_TEST_DEFINITELY_MISSING_TOKEN'
    with pytest.raises(ValueError):
        check(cfg)
