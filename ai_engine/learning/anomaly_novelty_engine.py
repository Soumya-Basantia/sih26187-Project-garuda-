"""
Project Garuda — Adaptive Learning Engine
Milestone 6: Anomaly & Novelty Learning Core

Implements environmental anomaly and visual novelty learning:
1. Graduated 4-tier hierarchy:
   NORMAL -> UNUSUAL -> REQUIRES_REVIEW -> CONFIRMED_EVENT
2. Multi-criterion anomaly assessment:
   - Visual novelty detection (unseen appearance archetypes)
   - Trajectory anomaly detection (atypical path likelihood)
   - Temporal anomaly detection (circadian schedule deviation)
   - Scene activity anomaly detection (abrupt motion/crowd surges)
3. Decoupling invariant:
   Anomaly != Security Threat (avoids false alarm panic)
4. Camera-specific anomaly scoring and review queue routing.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("garuda.anomaly_engine")


# -----------------------------------------------------------------------------
# 1. Graduated 4-Tier Hierarchy
# -----------------------------------------------------------------------------

class AnomalySeverityTier(str, Enum):
    NORMAL = "NORMAL"                     # Score < 0.35: Standard baseline behavior
    UNUSUAL = "UNUSUAL"                   # 0.35 <= Score < 0.60: Soft deviation, logged
    REQUIRES_REVIEW = "REQUIRES_REVIEW"   # 0.60 <= Score < 0.85: Significant, routed to human review
    CONFIRMED_EVENT = "CONFIRMED_EVENT"   # Score >= 0.85: Extreme multi-criterion deviation


@dataclass
class AnomalyAssessment:
    """
    Comprehensive record of an evaluated track or scene deviation.
    Strictly preserves that an anomaly is NOT automatically a security threat.
    """
    assessment_id: str
    camera_id: str
    timestamp: float
    fused_score: float
    tier: AnomalySeverityTier
    contributing_factors: dict[str, float]  # {"novelty": 0.2, "trajectory": 0.7, "temporal": 0.1, "scene": 0.0}
    explanation: str
    track_id: Optional[int] = None
    class_label: Optional[str] = None
    bounding_box: Optional[tuple[float, float, float, float]] = None
    is_security_threat: bool = False       # Crucial: Anomaly != Threat
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["tier"] = self.tier.value if isinstance(self.tier, AnomalySeverityTier) else str(self.tier)
        return d


# -----------------------------------------------------------------------------
# 2. Multi-Criterion Detectors
# -----------------------------------------------------------------------------

class NovelObjectDetector:
    """
    Evaluates visual novelty by comparing object 64-dim visual descriptors
    against the camera's learned appearance manifold cluster centers.
    """

    @staticmethod
    def evaluate(
        descriptor: Optional[list[float] | np.ndarray],
        appearance_clusterer: Any,
    ) -> Tuple[float, str]:
        if descriptor is None or appearance_clusterer is None:
            return 0.0, "NO_DESCRIPTOR"

        nov_score = appearance_clusterer.compute_novelty_score(descriptor)
        if nov_score > 0.60:
            return nov_score, f"HIGH_VISUAL_NOVELTY (Score={nov_score:.2f}, novel appearance archetype)"
        elif nov_score > 0.35:
            return nov_score, f"MODERATE_VISUAL_NOVELTY (Score={nov_score:.2f})"
        else:
            return nov_score, "FAMILIAR_APPEARANCE"


class TrajectoryAnomalyDetector:
    """
    Evaluates transit route likelihood by checking track coordinates
    against the camera's learned 8x8 movement manifold transition matrix.
    """

    @staticmethod
    def evaluate(
        trajectory: list[tuple[float, float]],
        movement_manifold: Any,
    ) -> Tuple[float, str]:
        if not trajectory or movement_manifold is None or len(trajectory) < 3:
            return 0.0, "INSUFFICIENT_TRACK_HISTORY"

        score, reason = movement_manifold.evaluate_route_anomaly(trajectory)
        return score, reason


class TemporalAnomalyDetector:
    """
    Evaluates temporal consistency by checking current activity against
    the camera's learned 24-hour circadian diurnal baseline.
    """

    @staticmethod
    def evaluate(
        hour: int,
        motion_energy: float,
        luminance: float,
        circadian_baseline: Any,
    ) -> Tuple[float, str]:
        if circadian_baseline is None:
            return 0.0, "NO_CIRCADIAN_BASELINE"

        score, reason = circadian_baseline.compute_circadian_anomaly(hour, motion_energy, luminance)
        return score, reason


class SceneActivityAnomalyDetector:
    """
    Evaluates macro scene activity by comparing spatial motion density
    against the camera's running background stability baseline.
    """

    @staticmethod
    def evaluate(
        current_activity: float,
        stability_score: float,
    ) -> Tuple[float, str]:
        # High activity (>0.25) with low stability indicates abrupt crowd surges / macro anomalies
        if current_activity > 0.35 and stability_score < 0.60:
            score = min(1.0, current_activity * 2.2)
            return round(score, 3), f"MACRO_ACTIVITY_SURGE (Activity={current_activity:.2f}, Stability={stability_score:.2f})"
        elif current_activity > 0.20:
            score = round(current_activity * 1.5, 3)
            return score, f"MODERATE_ACTIVITY_ELEVATION (Activity={current_activity:.2f})"
        else:
            return 0.0, "NORMAL_SCENE_ACTIVITY"


# -----------------------------------------------------------------------------
# 3. Master Anomaly & Novelty Engine
# -----------------------------------------------------------------------------

class AnomalyNoveltyEngine:
    """
    Unifies visual novelty, trajectory deviation, temporal irregularity,
    and macro scene activity into a calibrated multi-criterion anomaly assessment.
    Enforces the graduated hierarchy and strictly isolates anomalies from threats.
    """

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        # Criterion fusion weights (sum to 1.0)
        self.weights = {
            "novelty": 0.25,
            "trajectory": 0.35,
            "temporal": 0.25,
            "scene": 0.15,
        }
        # Buffer of recent assessments (up to 200)
        self.recent_assessments: list[AnomalyAssessment] = []
        self._max_buffer = 200

    def evaluate_track(
        self,
        track_id: int,
        class_label: str,
        bounding_box: tuple[float, float, float, float],
        trajectory: list[tuple[float, float]],
        visual_descriptor: Optional[list[float] | np.ndarray] = None,
        environment_adapter: Optional[Any] = None,
        timestamp: Optional[float] = None,
    ) -> AnomalyAssessment:
        """
        Full multi-criterion anomaly evaluation for an active track.
        Takes <0.5ms on CPU.
        """
        now = timestamp or time.time()
        import uuid
        from datetime import datetime
        hour = datetime.fromtimestamp(now).hour

        # Pull components from environment adapter if provided
        ssl_learner = getattr(environment_adapter, "ssl_learner", None) if environment_adapter else None
        appearance_clusterer = getattr(ssl_learner, "appearance_clusters", None) if ssl_learner else None
        movement_manifold = getattr(ssl_learner, "manifold", None) if ssl_learner else None
        circadian_baseline = getattr(ssl_learner, "circadian", None) if ssl_learner else None

        scene_activity = getattr(environment_adapter.scene, "activity_level", 0.05) if environment_adapter else 0.05
        scene_stability = getattr(environment_adapter.scene, "stability_score", 0.95) if environment_adapter else 0.95
        scene_lum = getattr(environment_adapter.lighting, "mean_luminance", 128.0) if environment_adapter else 128.0

        # 1. Visual Novelty
        s_nov, r_nov = NovelObjectDetector.evaluate(visual_descriptor, appearance_clusterer)

        # 2. Trajectory Anomaly
        s_traj, r_traj = TrajectoryAnomalyDetector.evaluate(trajectory, movement_manifold)

        # 3. Temporal Anomaly
        s_temp, r_temp = TemporalAnomalyDetector.evaluate(hour, scene_activity, scene_lum, circadian_baseline)

        # 4. Scene Macro Activity Anomaly
        s_scene, r_scene = SceneActivityAnomalyDetector.evaluate(scene_activity, scene_stability)

        # Fused Anomaly Score: weighted combination with non-linear boost for strong outliers
        fused = (
            self.weights["novelty"] * s_nov
            + self.weights["trajectory"] * s_traj
            + self.weights["temporal"] * s_temp
            + self.weights["scene"] * s_scene
        )
        # If any single dimension has an extreme outlier (>0.85), boost score
        max_single = max(s_nov, s_traj, s_temp, s_scene)
        if max_single >= 0.85:
            fused = max(fused, max_single * 0.90)

        fused = round(min(1.0, max(0.0, fused)), 3)

        # Graduated 4-Tier Hierarchy Mapping
        if fused >= 0.85:
            tier = AnomalySeverityTier.CONFIRMED_EVENT
        elif fused >= 0.60:
            tier = AnomalySeverityTier.REQUIRES_REVIEW
        elif fused >= 0.35:
            tier = AnomalySeverityTier.UNUSUAL
        else:
            tier = AnomalySeverityTier.NORMAL

        # Construct primary explanation from top contributing factor
        factors = {
            "novelty": round(s_nov, 3),
            "trajectory": round(s_traj, 3),
            "temporal": round(s_temp, 3),
            "scene": round(s_scene, 3),
        }
        dominant_factor = max(factors.keys(), key=lambda k: factors[k])
        reasons_map = {
            "novelty": r_nov,
            "trajectory": r_traj,
            "temporal": r_temp,
            "scene": r_scene,
        }
        dominant_reason = reasons_map[dominant_factor]

        explanation = f"Tier={tier.value} (Score={fused:.2f}) -> Primary: {dominant_factor.upper()} ({dominant_reason})"

        assessment = AnomalyAssessment(
            assessment_id=f"anom_{uuid.uuid4().hex[:10]}",
            camera_id=self.camera_id,
            timestamp=now,
            fused_score=fused,
            tier=tier,
            contributing_factors=factors,
            explanation=explanation,
            track_id=track_id,
            class_label=class_label,
            bounding_box=bounding_box,
            is_security_threat=False,  # Anomaly != Threat
            metadata={"dominant_factor": dominant_factor},
        )

        self._record_assessment(assessment)
        return assessment

    def _record_assessment(self, assessment: AnomalyAssessment):
        """Buffers assessment in memory."""
        self.recent_assessments.append(assessment)
        if len(self.recent_assessments) > self._max_buffer:
            self.recent_assessments.pop(0)

    def get_recent_anomalies(
        self,
        tier: Optional[AnomalySeverityTier | str] = None,
        limit: int = 50,
    ) -> list[AnomalyAssessment]:
        """Returns buffered assessments filtered by tier."""
        res = self.recent_assessments
        if tier:
            tier_val = tier.value if isinstance(tier, AnomalySeverityTier) else str(tier).upper()
            if tier_val != "ALL":
                res = [a for a in res if a.tier.value == tier_val]
        return sorted(res, key=lambda a: a.timestamp, reverse=True)[:limit]


# Global dictionary of anomaly engines per camera
anomaly_engines: dict[str, AnomalyNoveltyEngine] = {}


def get_anomaly_engine(camera_id: str) -> AnomalyNoveltyEngine:
    if camera_id not in anomaly_engines:
        anomaly_engines[camera_id] = AnomalyNoveltyEngine(camera_id)
    return anomaly_engines[camera_id]
