from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.config import AppConfig, load_config_from_path
from app.db import Database
from app.inference import YoloInference
from app.model_registry import ModelRegistry
from app.paths import AppPaths
from app.trainer import Trainer


PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


@dataclass
class ProjectContext:
    project_id: str
    root: Path
    cfg: AppConfig
    paths: AppPaths
    db: Database
    registry: ModelRegistry
    inference: YoloInference
    trainer: Trainer


def validate_project_id(project_id: str) -> str:
    normalized = project_id.strip().lower()
    if not PROJECT_ID_RE.fullmatch(normalized):
        raise ValueError("project_id must use lowercase letters, numbers, hyphen, or underscore")
    return normalized


class ProjectManager:
    def __init__(self, base_cfg: AppConfig):
        self.base_cfg = base_cfg
        self.projects_dir = Path(base_cfg.platform.projects_dir)
        self.default_project = base_cfg.platform.default_project
        self.projects_dir.mkdir(parents=True, exist_ok=True)

    def project_root(self, project_id: str) -> Path:
        project_id = validate_project_id(project_id)
        if project_id == self.default_project:
            return Path.cwd()
        return self.projects_dir / project_id

    def config_path(self, project_id: str) -> Path:
        project_id = validate_project_id(project_id)
        if project_id == self.default_project:
            return Path(os.environ.get("SVL_APP_CONFIG") or os.environ.get("YOLO_APP_CONFIG", "config/default.yaml"))
        return self.project_root(project_id) / "config.yaml"

    def exists(self, project_id: str) -> bool:
        project_id = validate_project_id(project_id)
        return project_id == self.default_project or self.config_path(project_id).exists()

    def delete_project(self, project_id: str, delete_files: bool = True) -> dict:
        project_id = validate_project_id(project_id)
        if project_id == self.default_project:
            raise ValueError("default project cannot be deleted")
        root = self.project_root(project_id).resolve()
        projects_root = self.projects_dir.resolve()
        if not self.config_path(project_id).exists():
            raise KeyError(f"project not found: {project_id}")
        if not (root == projects_root or projects_root in root.parents):
            raise ValueError("project path is outside projects_dir")
        if delete_files:
            shutil.rmtree(root)
        else:
            self.config_path(project_id).unlink()
        return {"status": "deleted", "project_id": project_id, "deleted_files": delete_files}

    def create_project(
        self,
        project_id: str,
        project_name: str | None = None,
        class_names: list[str] | None = None,
        base_model: str | None = None,
    ) -> dict:
        project_id = validate_project_id(project_id)
        if project_id == self.default_project:
            raise ValueError("default project already exists")
        root = self.project_root(project_id)
        if self.config_path(project_id).exists():
            raise ValueError(f"project already exists: {project_id}")
        root.mkdir(parents=True, exist_ok=True)
        cfg = self.base_cfg.model_copy(deep=True)
        cfg.project_name = project_name or project_id
        if class_names:
            cfg.class_names = class_names
        if base_model:
            cfg.base_model = base_model
        cfg.paths.data_dir = Path("data")
        cfg.paths.model_dir = Path("models")
        cfg.paths.run_dir = Path("runs")
        cfg.paths.database = Path("data/state.sqlite3")
        cfg.training.dataset_yaml = None
        data = cfg.model_dump(mode="json")
        self.config_path(project_id).write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
        ctx = self.context(project_id)
        return self.describe(ctx)

    def save_config(self, project_id: str, cfg: AppConfig) -> None:
        path = self.config_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        saved = cfg.model_copy(deep=True)
        if validate_project_id(project_id) != self.default_project:
            saved.paths.data_dir = Path("data")
            saved.paths.model_dir = Path("models")
            saved.paths.run_dir = Path("runs")
            saved.paths.database = Path("data/state.sqlite3")
            for teacher in saved.teacher_models:
                teacher_path = Path(teacher.model_path)
                try:
                    teacher.model_path = str(teacher_path.resolve().relative_to(self.project_root(project_id).resolve()))
                except ValueError:
                    pass
            if saved.training.dataset_yaml:
                dataset_path = Path(saved.training.dataset_yaml)
                try:
                    saved.training.dataset_yaml = dataset_path.resolve().relative_to(self.project_root(project_id).resolve())
                except ValueError:
                    saved.training.dataset_yaml = dataset_path
        data = saved.model_dump(mode="json")
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

    def update_training_device(self, project_id: str, device: str) -> dict:
        project_id = validate_project_id(project_id)
        if device not in {"auto", "cpu", "0", "1", "2", "3", "0,1"}:
            raise ValueError("device must be auto, cpu, 0, 1, 2, 3, or 0,1")
        ctx = self.context(project_id)
        ctx.cfg.training.device = device
        if project_id == self.default_project:
            self.base_cfg.training.device = device
        self.save_config(project_id, ctx.cfg)
        return self.describe(self.context(project_id))

    def update_training_dataset(self, project_id: str, dataset_yaml: str | None) -> dict:
        project_id = validate_project_id(project_id)
        ctx = self.context(project_id)
        value = (dataset_yaml or "").strip()
        if value:
            path = Path(value)
            if not path.is_absolute():
                path = ctx.root / path
            if not path.exists() or path.suffix.lower() not in {".yaml", ".yml"}:
                raise ValueError(f"dataset yaml was not found: {path}")
            ctx.cfg.training.dataset_yaml = path
        else:
            ctx.cfg.training.dataset_yaml = None
        if project_id == self.default_project:
            self.base_cfg.training.dataset_yaml = ctx.cfg.training.dataset_yaml
        self.save_config(project_id, ctx.cfg)
        return self.describe(self.context(project_id))

    def update_training_settings(self, project_id: str, settings: dict) -> dict:
        project_id = validate_project_id(project_id)
        ctx = self.context(project_id)
        for key, value in settings.items():
            if hasattr(ctx.cfg.training, key):
                setattr(ctx.cfg.training, key, value)
        if project_id == self.default_project:
            self.base_cfg.training = ctx.cfg.training
        self.save_config(project_id, ctx.cfg)
        return self.describe(self.context(project_id))

    def update_realtime_settings(self, project_id: str, settings: dict) -> dict:
        project_id = validate_project_id(project_id)
        ctx = self.context(project_id)
        for key, value in settings.items():
            if hasattr(ctx.cfg.camera, key):
                setattr(ctx.cfg.camera, key, value)
        if project_id == self.default_project:
            self.base_cfg.camera = ctx.cfg.camera
        self.save_config(project_id, ctx.cfg)
        return self.describe(self.context(project_id))

    def update_labeling_settings(self, project_id: str, settings: dict) -> dict:
        project_id = validate_project_id(project_id)
        mode = settings.get("mode")
        if mode not in {"teacher_only", "self_only", "teacher_then_self", "ensemble"}:
            raise ValueError("mode must be teacher_only, self_only, teacher_then_self, or ensemble")
        if float(settings.get("self_conf_accept", 0.0)) < float(settings.get("self_conf_review", 0.0)):
            raise ValueError("self_conf_accept must be greater than or equal to self_conf_review")
        ctx = self.context(project_id)
        for key, value in settings.items():
            if hasattr(ctx.cfg.labeling, key):
                setattr(ctx.cfg.labeling, key, value)
        if project_id == self.default_project:
            self.base_cfg.labeling = ctx.cfg.labeling
        self.save_config(project_id, ctx.cfg)
        return self.describe(self.context(project_id))

    def context(self, project_id: str | None = None) -> ProjectContext:
        project_id = validate_project_id(project_id or self.default_project)
        if not self.exists(project_id):
            raise KeyError(f"project not found: {project_id}")

        if project_id == self.default_project:
            root = Path.cwd()
            cfg = self.base_cfg.model_copy(deep=True)
        else:
            root = self.project_root(project_id)
            cfg = load_config_from_path(self.config_path(project_id), base_dir=root)

        paths = AppPaths(cfg)
        paths.ensure()
        db = Database(paths.db)
        db.init()
        registry = ModelRegistry(cfg, paths, db)
        registry.ensure_base_model()
        registry.sync_imported_models()
        inference = YoloInference(cfg)
        trainer = Trainer(cfg, paths, db, registry)
        return ProjectContext(project_id, root, cfg, paths, db, registry, inference, trainer)

    def list_projects(self) -> list[dict]:
        projects = [self.describe(self.context(self.default_project))]
        for config_file in sorted(self.projects_dir.glob("*/config.yaml")):
            project_id = config_file.parent.name
            try:
                projects.append(self.describe(self.context(project_id)))
            except Exception as exc:
                projects.append({"project_id": project_id, "status": "error", "error": str(exc)})
        return projects

    def describe(self, ctx: ProjectContext) -> dict:
        counts = {
            "accepted": ctx.db.one("SELECT COUNT(*) AS count FROM samples WHERE status = 'accepted'")["count"],
            "review_pending": ctx.db.one("SELECT COUNT(*) AS count FROM samples WHERE status = 'review_pending'")["count"],
            "rejected": ctx.db.one("SELECT COUNT(*) AS count FROM samples WHERE status = 'rejected'")["count"],
        }
        current = ctx.registry.current()
        return {
            "project_id": ctx.project_id,
            "project_name": ctx.cfg.project_name,
            "root": str(ctx.root),
            "class_names": ctx.cfg.class_names,
            "teacher_models": [teacher.model_dump() for teacher in ctx.cfg.teacher_models],
            "labeling": ctx.cfg.labeling.model_dump(),
            "training": ctx.cfg.training.model_dump(),
            "camera": ctx.cfg.camera.model_dump(),
            "paths": {
                "data": str(ctx.paths.data),
                "models": str(ctx.paths.models),
                "imported_models": str(ctx.paths.imported),
                "model_registry": str(ctx.paths.registry),
                "runs": str(ctx.paths.runs),
                "platform_outputs": str(ctx.paths.platform),
                "app_outputs": str(ctx.paths.platform_apps),
                "logs": str(ctx.paths.logs),
            },
            "current_model": current,
            "sample_counts": counts,
        }
