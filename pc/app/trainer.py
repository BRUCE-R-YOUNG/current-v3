from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

from app.config import AppConfig
from app.dataset import active_dataset_yaml, describe_dataset_yaml, rebuild_dataset_split
from app.db import Database
from app.model_registry import ModelRegistry
from app.paths import AppPaths


def extract_map50(metrics: object) -> float | None:
    box = getattr(metrics, "box", None)
    if box is not None and hasattr(box, "map50"):
        return float(box.map50)
    if isinstance(metrics, dict):
        for key in ("metrics/mAP50(B)", "map50", "mAP50"):
            if key in metrics:
                return float(metrics[key])
    return None


class Trainer:
    def __init__(self, cfg: AppConfig, paths: AppPaths, db: Database, registry: ModelRegistry):
        self.cfg = cfg
        self.paths = paths
        self.db = db
        self.registry = registry

    def train_candidate(self, progress: Callable[[float, str], None] | None = None) -> dict:
        progress = progress or (lambda percent, message: None)
        progress(2, "Preparing dataset")
        if self.cfg.training.dataset_yaml:
            dataset_yaml = active_dataset_yaml(self.cfg, self.paths)
            counts = describe_dataset_yaml(dataset_yaml)
        else:
            counts = rebuild_dataset_split(self.cfg, self.paths, self.db)
            dataset_yaml = self.paths.dataset_yaml
            counts["source"] = "managed"
            counts["path"] = str(dataset_yaml)
        if counts["train"] < self.cfg.training.min_train_images:
            raise RuntimeError(f"train images are below min_train_images: {counts['train']}")
        progress(8, f"Dataset ready: {counts['train']} train / {counts['val']} val")

        from ultralytics import YOLO

        current = self.registry.current()
        current_path = self.registry.current_model_path()
        model = YOLO(current_path)
        total_epochs = max(1, int(self.cfg.training.epochs))
        started = time.monotonic()

        def on_train_epoch_end(trainer) -> None:
            epoch = int(getattr(trainer, "epoch", 0)) + 1
            percent = 10 + min(85, (epoch / total_epochs) * 85)
            elapsed = max(0.1, time.monotonic() - started)
            remaining = max(0.0, (elapsed / max(epoch, 1)) * (total_epochs - epoch))
            progress(percent, f"Training epoch {epoch}/{total_epochs}, about {format_seconds(remaining)} remaining")

        try:
            model.add_callback("on_train_epoch_end", on_train_epoch_end)
        except Exception:
            progress(10, "Training started")

        results = model.train(
            data=str(dataset_yaml),
            epochs=self.cfg.training.epochs,
            imgsz=self.cfg.training.image_size,
            batch=self.cfg.training.batch,
            patience=self.cfg.training.patience,
            device=resolve_training_device(self.cfg.training.device),
            workers=self.cfg.training.workers,
            project=str(self.paths.runs / "train"),
            name="candidate",
            exist_ok=True,
            pretrained=True,
            save=True,
            plots=True,
            degrees=self.cfg.training.degrees,
            translate=self.cfg.training.translate,
            scale=self.cfg.training.scale,
            shear=self.cfg.training.shear,
            perspective=self.cfg.training.perspective,
            fliplr=self.cfg.training.fliplr,
            flipud=self.cfg.training.flipud,
            hsv_h=self.cfg.training.hsv_h,
            hsv_s=self.cfg.training.hsv_s,
            hsv_v=self.cfg.training.hsv_v,
        )
        progress(96, "Registering trained model")
        save_dir = Path(getattr(results, "save_dir", self.paths.runs / "train" / "candidate"))
        best = save_dir / "weights" / "best.pt"
        if not best.exists():
            raise RuntimeError(f"training completed but best.pt was not found: {best}")
        version = self.registry.register_candidate(best, current["version"] if current else None, {"dataset": counts})
        progress(100, f"Training completed: {version}")
        return {"candidate_version": version, "best_model": str(best), "dataset": counts}

    def evaluate(self, version: str | None = None) -> dict:
        from ultralytics import YOLO

        row = self.registry.current() if version is None else self.db.one("SELECT * FROM model_versions WHERE version = ?", (version,))
        if not row:
            raise RuntimeError("model version not found")
        model = YOLO(row["path"])
        dataset_yaml = active_dataset_yaml(self.cfg, self.paths)
        metrics = model.val(data=str(dataset_yaml), device=resolve_training_device(self.cfg.training.device))
        result = {"map50": extract_map50(metrics)}
        if version:
            previous = json.loads(row.get("metrics_json") or "{}")
            previous.update(result)
            self.registry.set_metrics(version, previous)
        return result


def format_seconds(seconds: float) -> str:
    seconds = int(max(0, seconds))
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {sec}s"
    return f"{sec}s"


def resolve_training_device(device: str) -> str | int:
    if device != "auto":
        return device
    try:
        import torch

        return 0 if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"
