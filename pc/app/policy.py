from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromotionDecision:
    promote: bool
    reason: str


def decide_label_status(max_conf: float, detections: int, conf_accept: float, conf_review: float, require_human_review: bool, auto_accept: bool) -> str:
    if detections <= 0:
        return "rejected"
    if max_conf >= conf_accept and auto_accept and not require_human_review:
        return "accepted"
    if max_conf >= conf_accept and auto_accept:
        return "review_pending"
    if max_conf >= conf_review:
        return "review_pending"
    return "rejected"


def decide_promotion(
    candidate_map50: float | None,
    current_map50: float | None,
    min_map50: float,
    max_map50_drop: float,
    require_better_or_equal: bool,
) -> PromotionDecision:
    if candidate_map50 is None:
        return PromotionDecision(False, "candidate_map50 is missing")
    if candidate_map50 < min_map50:
        return PromotionDecision(False, f"candidate mAP50 {candidate_map50:.4f} is below minimum {min_map50:.4f}")
    if current_map50 is None:
        return PromotionDecision(True, "no current baseline metric is available")
    if require_better_or_equal and candidate_map50 + max_map50_drop < current_map50:
        return PromotionDecision(False, f"candidate mAP50 dropped more than {max_map50_drop:.4f}")
    if require_better_or_equal and candidate_map50 < current_map50:
        return PromotionDecision(False, "candidate is below current model")
    return PromotionDecision(True, "candidate passed promotion policy")

