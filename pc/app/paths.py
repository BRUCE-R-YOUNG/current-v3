from __future__ import annotations

from pathlib import Path

from app.config import AppConfig


class AppPaths:
    def __init__(self, cfg: AppConfig):
        self.data = cfg.paths.data_dir
        self.models = cfg.paths.model_dir
        self.runs = cfg.paths.run_dir
        self.db = cfg.paths.database
        self.incoming = self.data / "incoming"
        self.review = self.data / "review"
        self.images_train = self.data / "images" / "train"
        self.images_val = self.data / "images" / "val"
        self.labels_train = self.data / "labels" / "train"
        self.labels_val = self.data / "labels" / "val"
        self.imported = self.models / "imported"
        self.registry = self.models / "registry"
        self.current_link = self.models / "current.txt"
        self.platform = self.runs / "platform"
        self.platform_apps = self.platform / "apps"
        self.platform_datasets = self.platform / "datasets"
        self.logs = self.platform / "logs"
        self.tests = self.platform_apps / "test"
        self.live = self.platform_apps / "live"
        self.dataset_yaml = self.data / "dataset.yaml"

    def ensure(self) -> None:
        for path in [
            self.incoming,
            self.review,
            self.images_train,
            self.images_val,
            self.labels_train,
            self.labels_val,
            self.imported,
            self.registry,
            self.runs,
            self.platform,
            self.platform_apps,
            self.platform_datasets,
            self.logs,
            self.tests,
            self.live,
        ]:
            path.mkdir(parents=True, exist_ok=True)
        self.db.parent.mkdir(parents=True, exist_ok=True)


def safe_name(name: str) -> str:
    keep = []
    for ch in name:
        keep.append(ch if ch.isalnum() or ch in "._-" else "_")
    return "".join(keep).strip("._") or "image"


def unique_path(directory: Path, filename: str) -> Path:
    stem = safe_name(Path(filename).stem)
    suffix = Path(filename).suffix.lower() or ".jpg"
    candidate = directory / f"{stem}{suffix}"
    counter = 1
    while candidate.exists():
        candidate = directory / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate
