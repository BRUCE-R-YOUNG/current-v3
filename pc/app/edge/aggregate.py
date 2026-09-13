from collections import Counter

import numpy as np

from .config import EdgeConfig


def return_seconds(floor: int | None, direction: str | None, cfg: EdgeConfig) -> float | None:
    if floor is None or not 1 <= floor <= cfg.highest_floor:
        return None
    if floor == 1:
        return 0.0
    if direction not in ("UP", "DOWN"):
        return None
    stops = cfg.floor_stop_seconds
    if direction == "DOWN":
        intermediate = range(2, floor)
        travel = (floor - 1) * cfg.seconds_per_floor
        return float(travel + np.sum([stops.get(f, cfg.stop_seconds) for f in intermediate]))
    # Assume travel to the configured top, turnaround, then stop at every intermediate floor.
    intermediate = list(range(floor + 1, cfg.highest_floor)) + list(range(2, cfg.highest_floor))
    travel = (cfg.highest_floor - floor + cfg.highest_floor - 1) * cfg.seconds_per_floor
    return float(travel + cfg.turnaround_seconds + np.sum([stops.get(f, cfg.stop_seconds) for f in intermediate]))


def mean(values):
    clean = [float(v) for v in values if v is not None and np.isfinite(v)]
    return float(np.mean(clean)) if clean else None


def mode(values):
    counts = Counter(v for v in values if v is not None)
    if not counts:
        return None
    winners = counts.most_common()
    return winners[0][0] if len(winners) == 1 or winners[0][1] > winners[1][1] else None


def summarize(frames: list[dict], cfg: EdgeConfig, start: float, end: float) -> dict:
    floors = [f.get("floor") for f in frames]
    directions = [f.get("direction") for f in frames]
    known_direction = [d for d in directions if d in ("UP", "DOWN")]
    eta = [return_seconds(f.get("floor"), f.get("direction"), cfg) for f in frames]
    return {
        "window_start": start, "window_end": end,
        "expected_frames": cfg.frames_per_window, "actual_frames": len(frames),
        "people_mean": mean([f.get("people") for f in frames]),
        "floor_mean": mean(floors), "floor": mode(floors),
        "floor_valid_frames": sum(v is not None for v in floors),
        "direction": mode(known_direction), "direction_valid_frames": len(known_direction),
        "up_ratio": mean([d == "UP" for d in known_direction]),
        "down_ratio": mean([d == "DOWN" for d in known_direction]),
        "return_seconds_mean": mean(eta), "eta_valid_frames": sum(v is not None for v in eta),
        "eta_method": "configured_all_stops_v1",
        "eta_parameters": {k: getattr(cfg, k) for k in ("highest_floor", "seconds_per_floor", "stop_seconds", "floor_stop_seconds", "turnaround_seconds")},
    }
