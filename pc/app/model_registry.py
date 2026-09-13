from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from app.config import AppConfig
from app.db import Database
from app.paths import AppPaths


def now_version(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}"


class ModelRegistry:
    def __init__(self, cfg: AppConfig, paths: AppPaths, db: Database):
        self.cfg = cfg
        self.paths = paths
        self.db = db

    def ensure_base_model(self) -> None:
        current = self.current()
        if current:
            return
        version = "base"
        self.db.execute(
            "INSERT OR IGNORE INTO model_versions(version, path, role, metrics_json) VALUES (?, ?, ?, ?)",
            (version, self.cfg.base_model, "current", "{}"),
        )
        self.paths.current_link.write_text(version, encoding="utf-8")

    def sync_imported_models(self) -> None:
        self.paths.imported.mkdir(parents=True, exist_ok=True)
        for model_path in sorted(self.paths.imported.glob("*.pt")):
            version = f"imported-{model_path.stem}"
            existing = self.db.one("SELECT * FROM model_versions WHERE version = ?", (version,))
            if existing:
                if existing["path"] != str(model_path):
                    self.db.execute("UPDATE model_versions SET path = ? WHERE version = ?", (str(model_path), version))
                continue
            self.db.execute(
                "INSERT INTO model_versions(version, path, role, metrics_json) VALUES (?, ?, ?, ?)",
                (version, str(model_path), "imported", "{}"),
            )

    def current(self) -> dict | None:
        if self.paths.current_link.exists():
            version = self.paths.current_link.read_text(encoding="utf-8").strip()
            row = self.db.one("SELECT * FROM model_versions WHERE version = ?", (version,))
            if row:
                return row
        return self.db.one("SELECT * FROM model_versions WHERE role = 'current' ORDER BY created_at DESC LIMIT 1")

    def current_model_path(self) -> str:
        current = self.current()
        return current["path"] if current else self.cfg.base_model

    def register_candidate(self, model_path: Path, parent_version: str | None, metrics: dict | None = None) -> str:
        version = now_version("candidate")
        target = self.paths.registry / f"{version}.pt"
        shutil.copy2(model_path, target)
        self.db.execute(
            "INSERT INTO model_versions(version, path, role, parent_version, metrics_json) VALUES (?, ?, ?, ?, ?)",
            (version, str(target), "candidate", parent_version, json.dumps(metrics or {}, ensure_ascii=False)),
        )
        return version

    def set_metrics(self, version: str, metrics: dict) -> None:
        self.db.execute(
            "UPDATE model_versions SET metrics_json = ? WHERE version = ?",
            (json.dumps(metrics, ensure_ascii=False), version),
        )

    def promote(self, version: str) -> None:
        row = self.db.one("SELECT * FROM model_versions WHERE version = ?", (version,))
        if not row:
            raise ValueError(f"Unknown model version: {version}")
        self.db.execute("UPDATE model_versions SET role = 'archived' WHERE role = 'current'")
        self.db.execute(
            "UPDATE model_versions SET role = 'current', promoted_at = CURRENT_TIMESTAMP WHERE version = ?",
            (version,),
        )
        self.paths.current_link.write_text(version, encoding="utf-8")

    def rollback(self, version: str) -> None:
        row = self.db.one("SELECT * FROM model_versions WHERE version = ?", (version,))
        if not row:
            raise ValueError(f"Unknown model version: {version}")
        self.promote(version)

    def list_models(self) -> list[dict]:
        self.sync_imported_models()
        rows = self.db.query("SELECT * FROM model_versions ORDER BY created_at DESC")
        for row in rows:
            row["metrics"] = json.loads(row.get("metrics_json") or "{}")
        return rows
