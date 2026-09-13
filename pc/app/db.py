from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  image_path TEXT NOT NULL,
  label_path TEXT,
  source TEXT NOT NULL,
  status TEXT NOT NULL,
  max_conf REAL DEFAULT 0,
  detections INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS model_versions (
  version TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  role TEXT NOT NULL,
  parent_version TEXT,
  metrics_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  promoted_at TEXT
);

CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  status TEXT NOT NULL,
  progress_percent REAL DEFAULT 0,
  progress_message TEXT,
  started_at TEXT,
  finished_at TEXT,
  detail_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

RUN_MIGRATIONS = {
    "progress_percent": "ALTER TABLE runs ADD COLUMN progress_percent REAL DEFAULT 0",
    "progress_message": "ALTER TABLE runs ADD COLUMN progress_message TEXT",
    "started_at": "ALTER TABLE runs ADD COLUMN started_at TEXT",
    "finished_at": "ALTER TABLE runs ADD COLUMN finished_at TEXT",
}


class Database:
    def __init__(self, path: Path):
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def init(self) -> None:
        conn = self.connect()
        try:
            conn.executescript(SCHEMA)
            existing = {row["name"] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
            for column, sql in RUN_MIGRATIONS.items():
                if column not in existing:
                    conn.execute(sql)
            conn.commit()
        finally:
            conn.close()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        conn = self.connect()
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None
