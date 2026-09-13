import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS events (
                  id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
                  image BLOB, created REAL NOT NULL, sent INTEGER NOT NULL DEFAULT 0,
                  attempts INTEGER NOT NULL DEFAULT 0, next_try REAL NOT NULL DEFAULT 0,
                  error TEXT, imported INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS usage (day TEXT, month TEXT, kind TEXT, bytes INTEGER);
                CREATE TABLE IF NOT EXISTS states (name TEXT PRIMARY KEY, payload TEXT, updated REAL);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, kind, payload, image=None, event_id=None, limit=256_000_000):
        event_id = event_id or uuid.uuid4().hex
        payload = dict(payload, event_id=event_id, kind=kind)
        encoded = json.dumps(payload, allow_nan=False)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT kind,payload,image FROM events WHERE id=?", (event_id,)).fetchone()
            if old:
                if old['kind'] != kind or json.loads(old['payload']) != payload or old['image'] != image:
                    raise ValueError("event_id already exists with different content")
                return event_id
            used = db.execute("SELECT COALESCE(SUM(length(payload)+COALESCE(length(image),0)),0) FROM events").fetchone()[0]
            if used + len(encoded.encode()) + len(image or b'') > limit:
                raise RuntimeError("Storage budget reached; archive acknowledged events before continuing")
            db.execute("INSERT INTO events(id,kind,payload,image,created) VALUES (?,?,?,?,?)", (event_id, kind, encoded, image, time.time()))
        return event_id

    def pending(self, kind, limit=20):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM events WHERE kind=? AND sent=0 AND next_try<=? ORDER BY created LIMIT ?", (kind,time.time(),limit))]

    def charge(self, kind, amount, cfg):
        day = time.strftime('%Y-%m-%d', time.gmtime())
        month = day[:7]
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            daily, monthly, images = db.execute("SELECT COALESCE(SUM(CASE WHEN day=? THEN bytes ELSE 0 END),0), COALESCE(SUM(bytes),0), COALESCE(SUM(CASE WHEN day=? AND kind='image' THEN bytes ELSE 0 END),0) FROM usage WHERE month=?", (day,day,month)).fetchone()
            if daily+amount > cfg.daily_transfer_bytes or monthly+amount > cfg.monthly_transfer_bytes or (kind == 'image' and images+amount > cfg.daily_image_bytes):
                return False
            updated = db.execute("UPDATE usage SET bytes=bytes+? WHERE day=? AND kind=?",(amount,day,kind))
            if not updated.rowcount:
                db.execute("INSERT INTO usage VALUES (?,?,?,?)", (day,month,kind,amount))
            return True

    def prune(self, days=7):
        with self.connect() as db:
            db.execute("DELETE FROM events WHERE (sent=1 OR imported=1) AND created<?",(time.time()-days*86400,))

    def result(self, event_id, error=None):
        with self.connect() as db:
            if error:
                row = db.execute("SELECT attempts FROM events WHERE id=?", (event_id,)).fetchone()
                delay = min(3600, 2 ** min(row[0]+1, 11))
                db.execute("UPDATE events SET attempts=attempts+1,error=?,next_try=? WHERE id=?", (str(error)[:500],time.time()+delay,event_id))
            else:
                db.execute("UPDATE events SET sent=1,error=NULL WHERE id=?", (event_id,))

    def state(self, name, payload):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO states VALUES (?,?,?)", (name,json.dumps(payload,allow_nan=False),time.time()))

    def snapshot(self):
        with self.connect() as db:
            counts = [dict(r) for r in db.execute("SELECT kind,sent,COUNT(*) AS count FROM events GROUP BY kind,sent")]
            recent = [json.loads(r[0]) for r in db.execute("SELECT payload FROM events WHERE kind='telemetry' ORDER BY created DESC LIMIT 60")]
            states = {r['name']:dict(json.loads(r['payload']),updated=r['updated']) for r in db.execute("SELECT * FROM states")}
            errors = [dict(r) for r in db.execute("SELECT id,kind,error,attempts FROM events WHERE error IS NOT NULL LIMIT 10")]
            usage = [dict(r) for r in db.execute("SELECT day,kind,SUM(bytes) AS bytes FROM usage GROUP BY day,kind ORDER BY day DESC LIMIT 20")]
        return dict(counts=counts,recent=recent,states=states,errors=errors,usage=usage)
