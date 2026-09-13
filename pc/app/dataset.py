from __future__ import annotations

import random
import shutil
from pathlib import Path

import yaml

from app.config import AppConfig
from app.db import Database
from app.paths import AppPaths


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def write_dataset_yaml(cfg: AppConfig, paths: AppPaths) -> Path:
    data = {
        "path": str(paths.data.resolve()),
        "train": "images/train",
        "val": "images/val",
        "names": {i: name for i, name in enumerate(cfg.class_names)},
    }
    paths.dataset_yaml.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return paths.dataset_yaml


def active_dataset_yaml(cfg: AppConfig, paths: AppPaths) -> Path:
    if cfg.training.dataset_yaml:
        dataset_yaml = Path(cfg.training.dataset_yaml)
        if not dataset_yaml.exists():
            raise RuntimeError(f"dataset_yaml was not found: {dataset_yaml}")
        return normalize_dataset_yaml(dataset_yaml, paths)
    return paths.dataset_yaml


def normalize_dataset_yaml(dataset_yaml: Path, paths: AppPaths) -> Path:
    raw = yaml.safe_load(dataset_yaml.read_text(encoding="utf-8")) or {}
    changed = False
    root = resolve_dataset_root(dataset_yaml, raw)
    normalized = dict(raw)
    normalized["path"] = str(root)
    for key in ("train", "val", "test"):
        if key in normalized:
            entry = normalized[key]
            fixed = fix_dataset_entry(dataset_yaml, root, entry)
            if fixed != entry:
                normalized[key] = fixed
                changed = True
    if not changed and Path(str(raw.get("path") or root)).is_absolute():
        return dataset_yaml
    output_dir = paths.platform_datasets
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{dataset_yaml.stem}_normalized.yaml"
    output_path.write_text(yaml.safe_dump(normalized, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return output_path


def resolve_dataset_root(dataset_yaml: Path, raw: dict) -> Path:
    if raw.get("path"):
        root = Path(str(raw["path"]))
        if not root.is_absolute():
            root = dataset_yaml.parent / root
        return root.resolve()
    return dataset_yaml.parent.resolve()


def fix_dataset_entry(dataset_yaml: Path, root: Path, entry: object) -> object:
    if isinstance(entry, list):
        return [fix_dataset_entry(dataset_yaml, root, item) for item in entry]
    if not isinstance(entry, str):
        return entry
    target = Path(entry)
    if target.is_absolute():
        return entry
    if count_dataset_images(root, entry):
        return entry
    stripped = entry
    while stripped.startswith("../"):
        stripped = stripped[3:]
    if stripped != entry and count_dataset_images(dataset_yaml.parent, stripped):
        return stripped
    if count_dataset_images(dataset_yaml.parent, entry):
        return str((dataset_yaml.parent / entry).resolve())
    return entry


def describe_dataset_yaml(dataset_yaml: Path) -> dict:
    raw = yaml.safe_load(dataset_yaml.read_text(encoding="utf-8")) or {}
    root = Path(raw.get("path") or dataset_yaml.parent)
    if not root.is_absolute():
        root = dataset_yaml.parent / root
    return {
        "source": "external",
        "path": str(dataset_yaml),
        "train": count_dataset_images(root, raw.get("train")),
        "val": count_dataset_images(root, raw.get("val")),
    }


def dataset_split_dir(dataset_yaml: Path, split: str, kind: str = "images") -> Path:
    raw = yaml.safe_load(dataset_yaml.read_text(encoding="utf-8")) or {}
    root = resolve_dataset_root(dataset_yaml, raw)
    entry = fix_dataset_entry(dataset_yaml, root, raw.get(split) or f"{split}/images")
    if isinstance(entry, list):
        entry = entry[0] if entry else f"{split}/images"
    target = Path(str(entry))
    if not target.is_absolute():
        target = root / target
    if kind == "labels":
        parts = ["labels" if part == "images" else part for part in target.parts]
        target = Path(*parts)
    return target


def count_dataset_images(root: Path, entry: object) -> int:
    if not entry:
        return 0
    if isinstance(entry, list):
        return sum(count_dataset_images(root, item) for item in entry)
    target = Path(str(entry))
    if not target.is_absolute():
        target = root / target
    if target.is_file() and target.suffix.lower() == ".txt":
        return sum(1 for line in target.read_text(encoding="utf-8").splitlines() if line.strip())
    if target.is_file() and target.suffix.lower() in IMAGE_EXTS:
        return 1
    if target.is_dir():
        return sum(1 for file in target.rglob("*") if file.is_file() and file.suffix.lower() in IMAGE_EXTS)
    return 0


def rebuild_dataset_split(cfg: AppConfig, paths: AppPaths, db: Database) -> dict:
    accepted = db.query("SELECT * FROM samples WHERE status = 'accepted' AND label_path IS NOT NULL")
    for directory in [paths.images_train, paths.images_val, paths.labels_train, paths.labels_val]:
        directory.mkdir(parents=True, exist_ok=True)
        for file in directory.iterdir():
            if file.is_file():
                file.unlink()

    random.Random(42).shuffle(accepted)
    val_count = max(1, int(len(accepted) * cfg.training.val_ratio)) if len(accepted) > 1 else 0
    val_ids = {row["id"] for row in accepted[:val_count]}
    counts = {"train": 0, "val": 0}

    for row in accepted:
        image = Path(row["image_path"])
        label = Path(row["label_path"])
        if not image.exists() or not label.exists() or image.suffix.lower() not in IMAGE_EXTS:
            continue
        split = "val" if row["id"] in val_ids else "train"
        image_target = (paths.images_val if split == "val" else paths.images_train) / image.name
        label_target = (paths.labels_val if split == "val" else paths.labels_train) / f"{image.stem}.txt"
        shutil.copy2(image, image_target)
        shutil.copy2(label, label_target)
        counts[split] += 1

    write_dataset_yaml(cfg, paths)
    return counts
