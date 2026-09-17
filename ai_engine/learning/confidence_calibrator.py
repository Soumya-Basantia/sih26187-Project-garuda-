"""
Project Garuda — Milestone 2: Confidence Calibration & Active Learning
Provides:
1. Multi-head output extraction & confidence scoring (Entropy, Margin, BBox Stability).
2. Camera-specific confidence calibration: Temperature scaling per camera node
   and ambient lighting factor adjustments.
3. Multi-criterion Sample Selection Policy for active learning.
"""

from __future__ import annotations

import math
import logging
from dataclasses import dataclass, field
from typing import Optional, Sequence

from ai_engine.learning.data_foundation import SelectionReason

logger = logging.getLogger("garuda.confidence_calibrator")


# -----------------------------------------------------------------------------
# 1. Confidence Scoring Functions
# -----------------------------------------------------------------------------

def compute_entropy(prob_or_probs: float | Sequence[float]) -> float:
    """
    Computes normalized Shannon entropy in [0, 1].
    - If a single confidence p is provided, computes binary entropy.
    - If a distribution of class probabilities is provided, computes categorical entropy.
    Higher entropy indicates higher model ambiguity/uncertainty.
    """
    if isinstance(prob_or_probs, (float, int)):
        p = max(1e-6, min(1.0 - 1e-6, float(prob_or_probs)))
        # Binary entropy: -p log2(p) - (1-p) log2(1-p)
        h = -(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p))
        return float(max(0.0, min(1.0, h)))

    probs = [max(1e-6, float(x)) for x in prob_or_probs]
    total = sum(probs)
    if total <= 0:
        return 0.0
    norm_probs = [x / total for x in probs]
    k = len(norm_probs)
    if k <= 1:
        return 0.0
    max_h = math.log2(k)
    h = -sum(p * math.log2(p) for p in norm_probs)
    return float(max(0.0, min(1.0, h / max_h)))


def compute_class_margin(top1_conf: float, top2_conf: float) -> float:
    """
    Computes margin between top-2 predicted classes: Margin = p1 - p2.
    A small margin (< 0.15) indicates high class ambiguity between competing classes.
    """
    return float(max(0.0, top1_conf - top2_conf))


def compute_bbox_iou(
    box1: tuple[float, float, float, float],
    box2: tuple[float, float, float, float]
) -> float:
    """Computes Intersection over Union (IoU) for two bounding boxes (x1, y1, x2, y2)."""
    x1 = max(box1[0], box2[0])
    y1 = max(box1[1], box2[1])
    x2 = min(box1[2], box2[2])
    y2 = min(box1[3], box2[3])

    inter_w = max(0.0, x2 - x1)
    inter_h = max(0.0, y2 - y1)
    inter_area = inter_w * inter_h

    area1 = max(0.0, box1[2] - box1[0]) * max(0.0, box1[3] - box1[1])
    area2 = max(0.0, box2[2] - box2[0]) * max(0.0, box2[3] - box2[1])
    union_area = area1 + area2 - inter_area

    if union_area <= 0:
        return 0.0
    return float(inter_area / union_area)


def compute_bbox_stability(bbox_history: Sequence[tuple[float, float, float, float]]) -> float:
    """
    Measures track bounding box stability across consecutive frames [0.0 to 1.0].
    Computes average IoU between consecutive positions.
    Low stability (< 0.5) indicates bounding box jitter, partial occlusion, or tracker disorientation.
    """
    if len(bbox_history) < 2:
        return 1.0
    ious = [
        compute_bbox_iou(bbox_history[i], bbox_history[i + 1])
        for i in range(len(bbox_history) - 1)
    ]
    return float(sum(ious) / len(ious))


def detect_confidence_drop(
    conf_history: Sequence[float],
    drop_threshold: float = 0.25,
    window: int = 4,
) -> tuple[bool, float]:
    """
    Detects sudden confidence drop on a tracked object across recent frames.
    Returns (has_dropped, drop_magnitude).
    """
    if len(conf_history) < 2:
        return False, 0.0
    recent = list(conf_history[-window:])
    if len(recent) < 2:
        return False, 0.0
    max_prev = max(recent[:-1])
    curr = recent[-1]
    drop = max_prev - curr
    return (drop >= drop_threshold), float(max(0.0, drop))


# -----------------------------------------------------------------------------
# 2. Camera-Specific Confidence Calibration (Temperature Scaling + Ambient)
# -----------------------------------------------------------------------------

@dataclass
class CameraCalibrator:
    """
    Applies camera-specific temperature scaling and ambient lighting calibration.
    Calibrated Logit: z_cal = z / Temperature
    Calibrated Conf:  p_cal = 1 / (1 + exp(-z_cal)) * Ambient_Factor
    """
    camera_id: str
    temperature: float = 1.0  # T > 1 softens overconfidence; T < 1 sharpens underconfidence
    ambient_scale_factors: dict[str, float] = field(default_factory=lambda: {
        "DAYLIGHT": 1.0,
        "LOW_LIGHT": 0.88,
        "IR_NIGHT": 0.82,
        "GLARE": 0.78,
    })

    def calibrate(self, raw_confidence: float, lighting_condition: str = "DAYLIGHT") -> float:
        """
        Calibrates raw detector confidence with temperature scaling and lighting adjustment.
        """
        conf = max(1e-5, min(1.0 - 1e-5, raw_confidence))
        # Logit: z = ln(p / (1-p))
        logit = math.log(conf / (1.0 - conf))
        # Temperature scaling
        temp = max(0.1, min(5.0, self.temperature))
        scaled_logit = logit / temp
        # Sigmoid back to probability
        cal_p = 1.0 / (1.0 + math.exp(-scaled_logit))

        # Ambient lighting scaling factor
        factor = self.ambient_scale_factors.get(lighting_condition.upper(), 1.0)
        final_conf = cal_p * factor
        return float(max(0.01, min(0.99, final_conf)))


# -----------------------------------------------------------------------------
# 3. Multi-Criterion Sample Selection Policy
# -----------------------------------------------------------------------------

@dataclass
class SampleSelectionPolicy:
    """
    Configurable multi-criterion policy for active learning candidate selection.
    """
    uncertainty_min: float = 0.28
    uncertainty_max: float = 0.58
    margin_threshold: float = 0.15          # Class ambiguity threshold
    confidence_drop_threshold: float = 0.25 # Sudden track confidence drop
    bbox_stability_min: float = 0.45        # Jitter / occlusion recovery
    min_track_history_for_drop: int = 5

    def evaluate(
        self,
        confidence: float,
        object_type: str,
        track_id: Optional[int] = None,
        conf_history: Optional[Sequence[float]] = None,
        bbox_history: Optional[Sequence[tuple[float, float, float, float]]] = None,
        top2_confidence: Optional[float] = None,
        novelty_score: Optional[float] = None,
        is_critical_threat: bool = False,
    ) -> tuple[bool, Optional[SelectionReason], dict]:
        """
        Evaluates a detection candidate against all active learning selection criteria.
        Returns: (should_harvest, selection_reason, telemetry_metrics)
        """
        telemetry: dict = {
            "confidence": round(confidence, 3),
            "entropy": round(compute_entropy(confidence), 3),
        }

        # 1. High-Risk Tactical Threat override (always harvest critical exemplars)
        if is_critical_threat or object_type.lower() in ("gun", "knife", "weapon", "pistol", "rifle"):
            telemetry["policy_rule"] = "CRITICAL_THREAT_REINFORCEMENT"
            return True, SelectionReason.HIGH_RISK_ANOMALY, telemetry

        # 2. Sudden confidence drop on established tracked object
        if conf_history and len(conf_history) >= self.min_track_history_for_drop:
            dropped, drop_val = detect_confidence_drop(conf_history, self.confidence_drop_threshold)
            telemetry["conf_drop"] = round(drop_val, 3)
            if dropped:
                telemetry["policy_rule"] = "SUDDEN_TRACK_CONF_DROP"
                return True, SelectionReason.TRACKING_FAILURE, telemetry

        # 3. Class Ambiguity (low margin between top 2 classes)
        if top2_confidence is not None:
            margin = compute_class_margin(confidence, top2_confidence)
            telemetry["class_margin"] = round(margin, 3)
            if margin < self.margin_threshold and confidence >= self.uncertainty_min:
                telemetry["policy_rule"] = "LOW_CLASS_MARGIN_AMBIGUITY"
                return True, SelectionReason.UNCERTAIN_DETECTION, telemetry

        # 4. Bounding Box Jitter / Occlusion
        if bbox_history and len(bbox_history) >= 3:
            stability = compute_bbox_stability(bbox_history)
            telemetry["bbox_stability"] = round(stability, 3)
            if stability < self.bbox_stability_min and confidence >= self.uncertainty_min:
                telemetry["policy_rule"] = "BBOX_JITTER_OCCLUSION"
                return True, SelectionReason.OCCLUSION_RECOVERY, telemetry

        # 5. Visual Novelty Outlier
        if novelty_score is not None:
            telemetry["novelty_score"] = round(novelty_score, 3)
            if novelty_score >= 0.70:
                telemetry["policy_rule"] = "NOVEL_VISUAL_PATTERN"
                return True, SelectionReason.NOVELTY_OUTLIER, telemetry

        # 6. Primary Uncertainty Boundary Sampling
        if self.uncertainty_min <= confidence <= self.uncertainty_max:
            telemetry["policy_rule"] = "DECISION_BOUNDARY_UNCERTAINTY"
            return True, SelectionReason.UNCERTAIN_DETECTION, telemetry

        return False, None, telemetry
