from __future__ import annotations

from pathlib import Path

from app.config import AppConfig, TeacherModelSettings


def _box_to_yolo(box, width: int, height: int, class_id: int) -> tuple[str, float]:
    conf = float(box.conf.item())
    x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
    x = ((x1 + x2) / 2.0) / width
    y = ((y1 + y2) / 2.0) / height
    w = (x2 - x1) / width
    h = (y2 - y1) / height
    return f"{class_id} {x:.6f} {y:.6f} {w:.6f} {h:.6f}", conf


class YoloInference:
    def __init__(self, cfg: AppConfig):
        self.cfg = cfg

    def predict_to_yolo_label(self, model_path: str, image_path: Path, label_path: Path) -> dict:
        teacher = TeacherModelSettings(name="current", model_path=model_path, class_map={})
        return self.predict_with_teachers([teacher], image_path, label_path)

    def predict_with_configured_teachers(
        self,
        fallback_model_path: str,
        image_path: Path,
        label_path: Path,
        accepted_samples: int = 0,
    ) -> dict:
        teachers = self.configured_labelers(fallback_model_path, accepted_samples)
        result = self.predict_with_teachers(teachers, image_path, label_path)
        result["labeling_mode"] = self.effective_labeling_mode(accepted_samples)
        if result["labeling_mode"] == "self_only":
            result["conf_review"] = self.cfg.labeling.self_conf_review
            result["conf_accept"] = self.cfg.labeling.self_conf_accept
        return result

    def effective_labeling_mode(self, accepted_samples: int = 0) -> str:
        mode = self.cfg.labeling.mode
        if mode == "teacher_then_self":
            if accepted_samples >= self.cfg.labeling.teacher_until_min_samples:
                return "self_only"
            return "teacher_only"
        return mode

    def configured_labelers(self, fallback_model_path: str, accepted_samples: int = 0) -> list[TeacherModelSettings]:
        enabled_teachers = [teacher for teacher in self.cfg.teacher_models if teacher.enabled]
        self_labeler = TeacherModelSettings(
            name="current_self",
            model_path=fallback_model_path,
            class_map={},
            conf_accept=self.cfg.labeling.self_conf_accept,
            conf_review=self.cfg.labeling.self_conf_review,
        )
        mode = self.effective_labeling_mode(accepted_samples)
        if mode == "self_only":
            return [self_labeler]
        if mode == "ensemble":
            return [*enabled_teachers, self_labeler] if enabled_teachers else [self_labeler]
        return enabled_teachers or [self_labeler]

    def predict_with_teachers(self, teachers: list[TeacherModelSettings], image_path: Path, label_path: Path) -> dict:
        from PIL import Image
        from ultralytics import YOLO

        width, height = Image.open(image_path).size
        lines: list[str] = []
        max_conf = 0.0
        detections = 0
        teacher_stats: list[dict] = []

        for teacher in teachers:
            model = YOLO(teacher.model_path)
            review_conf = teacher.conf_review if teacher.conf_review is not None else self.cfg.inference.conf_review
            results = model.predict(
                source=str(image_path),
                imgsz=self.cfg.inference.image_size,
                conf=review_conf,
                iou=self.cfg.inference.iou,
                max_det=self.cfg.inference.max_detections,
                verbose=False,
            )
            teacher_count = 0
            teacher_max = 0.0
            for result in results:
                boxes = getattr(result, "boxes", None)
                if boxes is None:
                    continue
                for box in boxes:
                    local_cls = int(box.cls.item())
                    if teacher.class_map and local_cls not in teacher.class_map:
                        continue
                    global_cls = teacher.class_map.get(local_cls, local_cls)
                    line, conf = _box_to_yolo(box, width, height, global_cls)
                    lines.append(line)
                    max_conf = max(max_conf, conf)
                    teacher_max = max(teacher_max, conf)
                    detections += 1
                    teacher_count += 1
            teacher_stats.append({"name": teacher.name, "detections": teacher_count, "max_conf": teacher_max})

        label_path.parent.mkdir(parents=True, exist_ok=True)
        label_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        return {"max_conf": max_conf, "detections": detections, "label_path": str(label_path), "teachers": teacher_stats}
