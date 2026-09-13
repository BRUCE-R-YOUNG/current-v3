from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class PathSettings(BaseModel):
    data_dir: Path = Path("data")
    model_dir: Path = Path("models")
    run_dir: Path = Path("runs")
    database: Path = Path("data/state.sqlite3")


class PlatformSettings(BaseModel):
    projects_dir: Path = Path("projects")
    default_project: str = "default"


class InferenceSettings(BaseModel):
    image_size: int = 640
    conf_accept: float = 0.80
    conf_review: float = 0.45
    iou: float = 0.70
    max_detections: int = 100


class TeacherModelSettings(BaseModel):
    name: str
    model_path: str
    enabled: bool = True
    class_map: dict[int, int] = Field(default_factory=dict)
    conf_accept: float | None = None
    conf_review: float | None = None


class ReviewSettings(BaseModel):
    require_human_review: bool = True
    auto_accept_high_confidence: bool = True


class LabelingSettings(BaseModel):
    mode: str = "teacher_only"
    teacher_until_min_samples: int = 500
    self_conf_review: float = 0.60
    self_conf_accept: float = 0.90


class TrainingSettings(BaseModel):
    epochs: int = 30
    batch: int = 8
    patience: int = 10
    device: str = "cpu"
    image_size: int = 640
    workers: int = 0
    val_ratio: float = 0.20
    min_train_images: int = 10
    dataset_yaml: Path | None = None
    degrees: float = 0.0
    translate: float = 0.10
    scale: float = 0.50
    shear: float = 0.0
    perspective: float = 0.0
    fliplr: float = 0.0
    flipud: float = 0.0
    hsv_h: float = 0.015
    hsv_s: float = 0.70
    hsv_v: float = 0.40


class PromotionSettings(BaseModel):
    min_map50: float = 0.50
    max_map50_drop: float = 0.02
    require_candidate_better_or_equal: bool = True


class CameraSettings(BaseModel):
    source: int | str = 0
    capture_interval_seconds: float = 2.0
    max_frames_per_session: int = 100
    live_detect_confidence: float = 0.02
    floor_confidence: float = 0.06
    direction_confidence: float = 0.05
    live_iou: float = 0.35
    live_max_detections: int = 20


class AppConfig(BaseModel):
    project_name: str = "yolo-continuous-learning"
    base_model: str = "yolo26n.pt"
    class_names: list[str] = Field(default_factory=lambda: ["object"])
    teacher_models: list[TeacherModelSettings] = Field(default_factory=list)
    platform: PlatformSettings = Field(default_factory=PlatformSettings)
    paths: PathSettings = Field(default_factory=PathSettings)
    inference: InferenceSettings = Field(default_factory=InferenceSettings)
    review: ReviewSettings = Field(default_factory=ReviewSettings)
    labeling: LabelingSettings = Field(default_factory=LabelingSettings)
    training: TrainingSettings = Field(default_factory=TrainingSettings)
    promotion: PromotionSettings = Field(default_factory=PromotionSettings)
    camera: CameraSettings = Field(default_factory=CameraSettings)


def _normalize_paths(cfg: AppConfig, base_dir: Path | None = None) -> AppConfig:
    base = base_dir or Path.cwd()
    cfg.paths.data_dir = Path(cfg.paths.data_dir)
    cfg.paths.model_dir = Path(cfg.paths.model_dir)
    cfg.paths.run_dir = Path(cfg.paths.run_dir)
    cfg.paths.database = Path(cfg.paths.database)
    cfg.platform.projects_dir = Path(cfg.platform.projects_dir)
    if base_dir:
        if not cfg.paths.data_dir.is_absolute():
            cfg.paths.data_dir = base / cfg.paths.data_dir
        if not cfg.paths.model_dir.is_absolute():
            cfg.paths.model_dir = base / cfg.paths.model_dir
        if not cfg.paths.run_dir.is_absolute():
            cfg.paths.run_dir = base / cfg.paths.run_dir
        if not cfg.paths.database.is_absolute():
            cfg.paths.database = base / cfg.paths.database
        for teacher in cfg.teacher_models:
            teacher_path = Path(teacher.model_path)
            if not teacher_path.is_absolute() and teacher_path.parts:
                project_path = base / teacher_path
                if project_path.exists():
                    teacher.model_path = str(project_path)
        if cfg.training.dataset_yaml:
            dataset_path = Path(cfg.training.dataset_yaml)
            if not dataset_path.is_absolute():
                cfg.training.dataset_yaml = base / dataset_path
    return cfg


def load_config_from_path(config_path: Path, base_dir: Path | None = None) -> AppConfig:
    raw: dict[str, Any] = {}
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    cfg = AppConfig.model_validate(raw)
    return _normalize_paths(cfg, base_dir)


def load_config() -> AppConfig:
    config_path = Path(os.environ.get("SVL_APP_CONFIG") or os.environ.get("YOLO_APP_CONFIG", "config/default.yaml"))
    return load_config_from_path(config_path)
