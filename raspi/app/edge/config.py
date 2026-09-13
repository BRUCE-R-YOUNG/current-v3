from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class EdgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    role: Literal['edge', 'server'] = 'edge'
    project_id: str = Field(default="elevator-a", pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")
    device_id: str = Field(default="edge-01", pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    camera: str = "0"
    people_model: str = ""
    elevator_model: str = ""
    device: str = "cpu"
    imgsz: int = Field(default=640, ge=64, le=2048)
    confidence: float = Field(default=0.35, ge=0.01, le=1)
    people_classes: list[str] = Field(default_factory=lambda: ["person"])
    floor_map: dict[str, int] = Field(default_factory=lambda: {str(i): i for i in range(1, 21)})
    up_classes: list[str] = Field(default_factory=lambda: ["up", "UP"])
    down_classes: list[str] = Field(default_factory=lambda: ["down", "Down", "DOWN"])
    roi: tuple[float, float, float, float] = (0, 0, 1, 1)
    window_seconds: float = Field(default=3, ge=0.5, le=60)
    frames_per_window: int = Field(default=5, ge=1, le=60)
    highest_floor: int = Field(default=20, ge=2, le=200)
    seconds_per_floor: float = Field(default=3, gt=0, le=120)
    stop_seconds: float = Field(default=5, ge=0, le=300)
    floor_stop_seconds: dict[int, float] = Field(default_factory=dict)
    turnaround_seconds: float = Field(default=10, ge=0, le=600)
    capture_seconds: float = Field(default=30, ge=0.5, le=86400)
    difficult_only: bool = True
    difficult_confidence: float = Field(default=0.65, ge=0.01, le=1)
    duplicate_threshold: float = Field(default=0.02, ge=0, le=1)
    jpeg_long_edge: int = Field(default=640, ge=64, le=1920)
    jpeg_quality: int = Field(default=65, ge=10, le=95)
    server_url: str = ""
    token_env: str = "SVL_EDGE_TOKEN"
    transfer_seconds: float = Field(default=300, ge=3, le=86400)
    telemetry_seconds: float = Field(default=3, ge=1, le=3600)
    timeout_seconds: float = Field(default=10, ge=1, le=60)
    daily_image_bytes: int = Field(default=5_000_000, ge=0)
    daily_transfer_bytes: int = Field(default=12_000_000, ge=0)
    monthly_transfer_bytes: int = Field(default=400_000_000, ge=0)
    spool_limit_bytes: int = Field(default=256_000_000, ge=1_000_000)
    dataset_yaml: str = ""
    epochs: int = Field(default=120, ge=1, le=10000)
    batch: int = Field(default=16, ge=1, le=512)
    workers: int = Field(default=0, ge=0, le=32)
    promote_if_passed: bool = False
    export_onnx: bool = False

    @model_validator(mode="after")
    def check_ranges(self):
        x1, y1, x2, y2 = self.roi
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError("ROI must be normalized x1,y1,x2,y2 inside 0..1")
        if any(not 1 <= floor <= self.highest_floor for floor in self.floor_map.values()):
            raise ValueError("floor_map must be between 1 and highest_floor")
        if any(not 1 <= k <= self.highest_floor or not 0 <= v <= 300 for k, v in self.floor_stop_seconds.items()):
            raise ValueError("invalid floor stop time")
        if self.server_url and not self.server_url.startswith(("http://", "https://")):
            raise ValueError("server_url must use http:// or https://")
        return self

    @classmethod
    def load(cls, path: Path):
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(yaml.safe_dump(self.model_dump(mode="json"), allow_unicode=True, sort_keys=False), encoding="utf-8")
        tmp.replace(path)
