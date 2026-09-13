from __future__ import annotations

import shutil
from pathlib import Path
from typing import BinaryIO

from app.paths import unique_path
from app.platform import ProjectContext
from app.policy import decide_label_status


def store_incoming_file(ctx: ProjectContext, fileobj: BinaryIO, filename: str) -> Path:
    target = unique_path(ctx.paths.incoming, filename or "upload.jpg")
    with target.open("wb") as output:
        shutil.copyfileobj(fileobj, output)
    return target


def store_existing_image(ctx: ProjectContext, image_path: Path, source: str = "local") -> Path:
    if not image_path.exists() or not image_path.is_file():
        raise FileNotFoundError(f"image was not found: {image_path}")
    target = unique_path(ctx.paths.incoming, image_path.name)
    shutil.copy2(image_path, target)
    return target


def infer_and_store_sample(ctx: ProjectContext, image_path: Path, source: str) -> int:
    label_path = ctx.paths.review / f"{image_path.stem}.txt"
    accepted_samples = ctx.db.one("SELECT COUNT(*) AS count FROM samples WHERE status = 'accepted'")["count"]
    result = ctx.inference.predict_with_configured_teachers(
        ctx.registry.current_model_path(),
        image_path,
        label_path,
        accepted_samples=accepted_samples,
    )
    status = decide_label_status(
        result["max_conf"],
        result["detections"],
        result.get("conf_accept", ctx.cfg.inference.conf_accept),
        result.get("conf_review", ctx.cfg.inference.conf_review),
        ctx.cfg.review.require_human_review,
        ctx.cfg.review.auto_accept_high_confidence,
    )
    return ctx.db.execute(
        "INSERT INTO samples(image_path, label_path, source, status, max_conf, detections) VALUES (?, ?, ?, ?, ?, ?)",
        (str(image_path), str(label_path), source, status, result["max_conf"], result["detections"]),
    )


def ingest_existing_image(ctx: ProjectContext, image_path: Path, source: str = "local") -> dict:
    stored = store_existing_image(ctx, image_path, source)
    sample_id = infer_and_store_sample(ctx, stored, source)
    return {"status": "processed", "project_id": ctx.project_id, "sample_id": sample_id, "image_path": str(stored)}
