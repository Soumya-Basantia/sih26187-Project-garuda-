"""
Project Garuda — Adaptive Learning Engine
Milestone 4: Camera Environmental Adaptation Core

Implements lightweight online adaptation for individual cameras without modifying
underlying model weights:
1. Lighting conditions (mean luminance, RMS contrast, glare ratio, IR night mode).
2. Scene statistics & background characteristics (running background model, activity density).
3. Typical object distributions & class priors per camera.
4. Movement patterns (trajectory vectors, entry/exit zones).
5. Detection statistics (false alarm rates, average confidence, validation tallies).
6. Calibration state (temperature scaling, ambient factors).
7. Adaptive parameters (adapted detection threshold, persistence frames, tracker parameters).
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional, Tuple, Dict, List

import cv2
import numpy as np

from ai_engine.learning.data_foundation import CameraProfile

logger = logging.getLogger("garuda.camera_adapter")


# -----------------------------------------------------------------------------
# 1. Lighting Profile
# -----------------------------------------------------------------------------

@dataclass
class LightingProfile:
    condition: str = "DAYLIGHT"          # DAYLIGHT | LOW_LIGHT | IR_NIGHT | GLARE | OVERCAST
    mean_luminance: float = 128.0        # 0 - 255
    contrast: float = 50.0               # Standard deviation of luminance
    glare_ratio: float = 0.0             # Fraction of saturated pixels (>240)
    color_saturation: float = 40.0       # Mean HSV saturation (0 - 255)
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------------
# 2. Scene Baseline
# -----------------------------------------------------------------------------

@dataclass
class SceneBaseline:
    activity_level: float = 0.05         # Fraction of scene containing dynamic motion
    stability_score: float = 0.95        # 0.0 (erratic/stormy) to 1.0 (static)
    background_noise: float = 1.0        # Variance of background pixels
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------------
# 3. Movement Patterns
# -----------------------------------------------------------------------------

@dataclass
class MovementPatterns:
    frequent_directions: list[dict[str, Any]] = field(default_factory=list)
    entry_zones: list[tuple[float, float]] = field(default_factory=list)
    exit_zones: list[tuple[float, float]] = field(default_factory=list)
    dominant_heading_deg: float = 0.0
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------------
# 4. Detection Statistics
# -----------------------------------------------------------------------------

@dataclass
class DetectionStatistics:
    total_detections: int = 0
    avg_confidence: float = 0.50
    false_alarms: int = 0
    confirmations: int = 0
    rejections: int = 0
    false_alarm_rate: float = 0.0
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------------
# 5. Adaptive Parameters
# -----------------------------------------------------------------------------

@dataclass
class AdaptiveParameters:
    adapted_confidence: float = 0.25
    persistence_frames: int = 3
    track_match_thresh: float = 0.70
    max_track_age: int = 30
    spatial_noise_penalty: float = 0.0
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------------
# Camera Environment Adapter Engine
# -----------------------------------------------------------------------------

class CameraEnvironmentAdapter:
    """
    Per-camera online adaptation engine. Continuously inspects video frames,
    detection streams, and track trajectories to evolve a persistent CameraProfile
    without model weight modification.
    """

    def __init__(self, camera_id: str, base_confidence: float = 0.25):
        self.camera_id = camera_id
        self.base_confidence = base_confidence

        # 7-Domain Profile Components
        self.lighting = LightingProfile()
        self.scene = SceneBaseline()
        self.typical_objects: dict[str, int] = {}
        self.movement = MovementPatterns()
        self.stats = DetectionStatistics()
        self.calibration: dict[str, Any] = {
            "temperature": 1.0,
            "ambient_factor": 1.0,
            "sector_modifiers": {},
        }
        self.parameters = AdaptiveParameters(adapted_confidence=base_confidence)

        # Internal Background Modeling Buffers (downsampled for zero latency impact)
        self._bg_model: Optional[np.ndarray] = None
        self._bg_var: Optional[np.ndarray] = None
        self._alpha_bg: float = 0.03
        self._alpha_lighting: float = 0.15

        # Track history for motion pattern estimation: {track_id: [(x, y, t), ...]}
        self._track_trajectories: dict[int, list[tuple[float, float, float]]] = {}
        self._max_trajectory_history = 100

        # Milestone 5: Self-Supervised Environment Learner
        from ai_engine.learning.self_supervised_learner import SelfSupervisedEnvironmentLearner
        self.ssl_learner = SelfSupervisedEnvironmentLearner(camera_id=camera_id)

        # Frame adaptation interval limiter
        self._last_adapt_time: float = 0.0
        self._frame_count: int = 0

    # -------------------------------------------------------------------------
    # 1. Online Lighting Adaptation
    # -------------------------------------------------------------------------

    def adapt_lighting(self, frame: np.ndarray) -> LightingProfile:
        """
        Analyzes illumination, contrast, saturation, and glare on downsampled frame.
        Takes <0.4ms on CPU.
        """
        if frame is None or frame.size == 0:
            return self.lighting

        # Downsample for fast execution
        h, w = frame.shape[:2]
        step = max(1, min(h, w) // 120)
        sample = frame[::step, ::step]

        if len(sample.shape) == 3 and sample.shape[2] == 3:
            # Grayscale for luminance & contrast
            gray = cv2.cvtColor(sample, cv2.COLOR_BGR2GRAY)
            # HSV for saturation & IR night mode detection
            hsv = cv2.cvtColor(sample, cv2.COLOR_BGR2HSV)
            sat = float(np.mean(hsv[:, :, 1]))
        else:
            gray = sample
            sat = 0.0

        mean_lum = float(np.mean(gray))
        contrast = float(np.std(gray))
        glare_ratio = float(np.count_nonzero(gray >= 240) / gray.size)

        # Smooth via EMA
        self.lighting.mean_luminance = round(
            (1 - self._alpha_lighting) * self.lighting.mean_luminance + self._alpha_lighting * mean_lum, 2
        )
        self.lighting.contrast = round(
            (1 - self._alpha_lighting) * self.lighting.contrast + self._alpha_lighting * contrast, 2
        )
        self.lighting.glare_ratio = round(
            (1 - self._alpha_lighting) * self.lighting.glare_ratio + self._alpha_lighting * glare_ratio, 3
        )
        self.lighting.color_saturation = round(
            (1 - self._alpha_lighting) * self.lighting.color_saturation + self._alpha_lighting * sat, 2
        )

        # Classify lighting condition
        if self.lighting.glare_ratio >= 0.07 or self.lighting.mean_luminance >= 210:
            condition = "GLARE"
        elif self.lighting.mean_luminance < 45 and self.lighting.color_saturation < 18:
            condition = "IR_NIGHT"
        elif self.lighting.mean_luminance < 55:
            condition = "LOW_LIGHT"
        elif self.lighting.contrast < 8.0 and 80 <= self.lighting.mean_luminance <= 160:
            condition = "OVERCAST"
        else:
            condition = "DAYLIGHT"

        self.lighting.condition = condition
        self.lighting.last_updated = time.time()
        return self.lighting

    # -------------------------------------------------------------------------
    # 2. Scene Baseline & Dynamic Activity Adaptation
    # -------------------------------------------------------------------------

    def adapt_scene_baseline(self, frame: np.ndarray) -> SceneBaseline:
        """
        Lightweight running background accumulator. Computes scene activity index
        and spatial stability score.
        """
        if frame is None or frame.size == 0:
            return self.scene

        h, w = frame.shape[:2]
        step = max(1, min(h, w) // 80)
        sample = cv2.cvtColor(frame[::step, ::step], cv2.COLOR_BGR2GRAY).astype(np.float32)

        if self._bg_model is None or self._bg_model.shape != sample.shape:
            self._bg_model = sample.copy()
            self._bg_var = np.full_like(sample, 25.0)
            self.scene.activity_level = 0.02
            self.scene.stability_score = 0.98
            return self.scene

        # Difference from running background
        diff = np.abs(sample - self._bg_model)
        dev = np.sqrt(np.maximum(self._bg_var, 4.0))

        # Dynamic motion mask (pixels deviating by > 2.5 standard deviations)
        motion_mask = diff > (2.5 * dev)
        activity = float(np.count_nonzero(motion_mask) / sample.size)

        # Update background model with adaptive learning rate
        # Slower update for moving regions to prevent absorption
        alpha_eff = np.where(motion_mask, self._alpha_bg * 0.1, self._alpha_bg)
        self._bg_model = (1.0 - alpha_eff) * self._bg_model + alpha_eff * sample
        self._bg_var = (1.0 - alpha_eff) * self._bg_var + alpha_eff * (diff ** 2)

        self.scene.activity_level = round(
            0.85 * self.scene.activity_level + 0.15 * activity, 3
        )
        self.scene.stability_score = round(
            max(0.0, min(1.0, 1.0 - (self.scene.activity_level * 2.0))), 2
        )
        self.scene.background_noise = round(float(np.mean(dev)), 2)
        self.scene.last_updated = time.time()
        return self.scene

    # -------------------------------------------------------------------------
    # 3. Typical Objects & Class Distribution
    # -------------------------------------------------------------------------

    def record_detections(self, detections: list[dict[str, Any]]):
        """
        Updates camera-specific object frequency priors and detection statistics.
        """
        if not detections:
            return

        conf_sum = 0.0
        for det in detections:
            label = det.get("label") or det.get("class_name") or det.get("object_type", "object")
            conf = float(det.get("confidence", 0.5))
            conf_sum += conf
            self.typical_objects[label] = self.typical_objects.get(label, 0) + 1

        n = len(detections)
        if self.stats.total_detections == 0:
            self.stats.avg_confidence = round(conf_sum / n, 3)
        else:
            curr_avg = self.stats.avg_confidence
            self.stats.avg_confidence = round(
                (curr_avg * 0.9) + ((conf_sum / n) * 0.1), 3
            )
        self.stats.total_detections += n
        self.stats.last_updated = time.time()

    # -------------------------------------------------------------------------
    # 4. Movement Patterns & Trajectory Heatmap
    # -------------------------------------------------------------------------

    def record_tracks(self, tracks: list[Any], frame_shape: Tuple[int, int] = (480, 640)):
        """
        Updates movement patterns, directional vectors, and entry/exit zones.
        tracks can be ByteTrack STrack objects or dicts with track_id, bbox.
        """
        now = time.time()
        fh, fw = frame_shape

        for trk in tracks:
            track_id = getattr(trk, "track_id", None)
            if track_id is None and isinstance(trk, dict):
                track_id = trk.get("track_id")
            if track_id is None:
                continue

            # Extract center point
            if hasattr(trk, "tlbr"):
                x1, y1, x2, y2 = trk.tlbr
            elif isinstance(trk, dict) and "bbox" in trk:
                x1, y1, x2, y2 = trk["bbox"]
            else:
                continue

            cx = (x1 + x2) / (2.0 * max(1, fw))
            cy = (y1 + y2) / (2.0 * max(1, fh))

            if track_id not in self._track_trajectories:
                self._track_trajectories[track_id] = []
                # First observation: potential entry zone
                if len(self.movement.entry_zones) < 20:
                    self.movement.entry_zones.append((round(cx, 2), round(cy, 2)))

            traj = self._track_trajectories[track_id]
            traj.append((cx, cy, now))

            # Maintain trajectory history length
            if len(traj) > 30:
                traj.pop(0)

            # Calculate direction vector if track has traveled sufficiently
            if len(traj) >= 5:
                dx = traj[-1][0] - traj[0][0]
                dy = traj[-1][1] - traj[0][1]
                dist = math.hypot(dx, dy)
                if dist > 0.08:
                    angle_deg = (math.degrees(math.atan2(dy, dx)) + 360) % 360
                    self.movement.dominant_heading_deg = round(
                        (self.movement.dominant_heading_deg * 0.85) + (angle_deg * 0.15), 1
                    )
                    # Add to frequent direction clusters
                    dir_name = self._angle_to_direction(angle_deg)
                    found = False
                    for d in self.movement.frequent_directions:
                        if d["name"] == dir_name:
                            d["count"] += 1
                            found = True
                            break
                    if not found:
                        self.movement.frequent_directions.append({"name": dir_name, "count": 1})

        # Trim old trajectories
        if len(self._track_trajectories) > self._max_trajectory_history:
            oldest = sorted(self._track_trajectories.keys())[:len(self._track_trajectories) - self._max_trajectory_history]
            for oid in oldest:
                del self._track_trajectories[oid]

        self.movement.last_updated = now

    @staticmethod
    def _angle_to_direction(deg: float) -> str:
        if 45 <= deg < 135:
            return "DOWN"
        elif 135 <= deg < 225:
            return "LEFT"
        elif 225 <= deg < 315:
            return "UP"
        else:
            return "RIGHT"

    # -------------------------------------------------------------------------
    # 5. Dynamic Parameter Adaptation (Zero Retraining)
    # -------------------------------------------------------------------------

    def adapt_parameters(self) -> AdaptiveParameters:
        """
        Dynamically calculates optimal detection thresholds, persistence frames,
        and tracking parameters according to environmental baselines and feedback.
        """
        base_conf = self.base_confidence
        cond = self.lighting.condition
        fa_rate = self.stats.false_alarm_rate
        activity = self.scene.activity_level

        # 1. Adapted Confidence Threshold
        adapted_conf = base_conf

        if cond == "LOW_LIGHT":
            # In low light, reduce threshold slightly for recall, but compensate with persistence
            adapted_conf = max(0.18, base_conf - 0.04)
        elif cond == "IR_NIGHT":
            adapted_conf = max(0.20, base_conf - 0.02)
        elif cond == "GLARE":
            # Raise threshold to avoid false positive glare reflections
            adapted_conf = min(0.48, base_conf + 0.10)
        elif cond == "OVERCAST":
            adapted_conf = base_conf

        # Adjust for camera false alarm rate (RLHF penalty)
        if fa_rate > 0.15:
            fa_penalty = min(0.15, fa_rate * 0.25)
            adapted_conf = min(0.50, adapted_conf + fa_penalty)

        # 2. Persistence Frames
        persistence = 3
        if cond in ("LOW_LIGHT", "IR_NIGHT") or activity > 0.20:
            persistence = 4
        if fa_rate > 0.30:
            persistence = 5

        # 3. Tracker Match Threshold
        # Dynamic scenes with fast motion need slightly looser IoU matching
        match_thresh = 0.70
        if activity > 0.15 or self.lighting.contrast < 30:
            match_thresh = 0.60
        elif cond == "GLARE":
            match_thresh = 0.75

        # 4. Max Track Age
        max_age = 30
        if cond in ("LOW_LIGHT", "IR_NIGHT"):
            # Hold tracks longer through low-contrast occlusions
            max_age = 45
        elif activity > 0.30:
            # Drop stale tracks faster in crowded scenes to avoid id switching
            max_age = 20

        self.parameters.adapted_confidence = round(adapted_conf, 2)
        self.parameters.persistence_frames = persistence
        self.parameters.track_match_thresh = round(match_thresh, 2)
        self.parameters.max_track_age = max_age
        self.parameters.spatial_noise_penalty = round(fa_rate * 0.2, 2)
        self.parameters.last_updated = time.time()
        return self.parameters

    # -------------------------------------------------------------------------
    # 6. Full Frame Online Adaptation Hook
    # -------------------------------------------------------------------------

    def adapt_frame(
        self,
        frame: np.ndarray,
        detections: Optional[list[dict[str, Any]]] = None,
        tracks: Optional[list[Any]] = None,
        force: bool = False,
    ) -> CameraProfile:
        """
        Master online adaptation cycle for this camera.
        Executed periodically (e.g. 1-2 Hz). Zero GPU/CPU bottleneck.
        """
        now = time.time()
        self._frame_count += 1

        # Adapt every ~15 frames or when forced
        if not force and (now - self._last_adapt_time) < 0.8:
            return self.get_camera_profile()

        self._last_adapt_time = now

        # Run domain adaptations
        if frame is not None and frame.size > 0:
            self.adapt_lighting(frame)
            self.adapt_scene_baseline(frame)
            # Milestone 5: Unsupervised scene representation & circadian updates
            self.ssl_learner.process_unlabeled_frame(
                frame=frame,
                timestamp=now,
                motion_energy=self.scene.activity_level,
            )

        if detections:
            self.record_detections(detections)

        if tracks and frame is not None:
            self.record_tracks(tracks, frame.shape[:2])
            for trk_id, traj in self._track_trajectories.items():
                if len(traj) >= 3:
                    coords = [(p[0], p[1]) for p in traj]
                    self.ssl_learner.process_unlabeled_trajectory(coords)

        # Recalculate adaptive parameters
        self.adapt_parameters()

        # Update calibration ambient factor
        if self.lighting.condition == "LOW_LIGHT":
            self.calibration["ambient_factor"] = 0.85
        elif self.lighting.condition == "GLARE":
            self.calibration["ambient_factor"] = 1.20
        else:
            self.calibration["ambient_factor"] = 1.0

        return self.get_camera_profile()

    # -------------------------------------------------------------------------
    # 7. Operator Feedback Integration
    # -------------------------------------------------------------------------

    def record_feedback(self, is_false_alarm: bool, was_confirmed: bool = False, was_rejected: bool = False):
        """Records operator validation reinforcement to auto-tune false alarm rate."""
        if is_false_alarm:
            self.stats.false_alarms += 1
        elif was_confirmed:
            self.stats.confirmations += 1
        elif was_rejected:
            self.stats.rejections += 1

        total_fb = self.stats.false_alarms + self.stats.confirmations + self.stats.rejections
        if total_fb > 0:
            self.stats.false_alarm_rate = round(self.stats.false_alarms / total_fb, 3)

        self.adapt_parameters()

    # -------------------------------------------------------------------------
    # 8. Profile Export
    # -------------------------------------------------------------------------

    def get_camera_profile(self) -> CameraProfile:
        """
        Constructs and returns canonical CameraProfile containing all 7 domains.
        """
        status = "OPTIMAL"
        if self.stats.false_alarm_rate > 0.25:
            status = "NOISE_SUPPRESSED"
        elif self.lighting.condition != "DAYLIGHT":
            status = "ENVIRONMENT_ADAPTED"

        # Top 5 typical objects
        top_objects = sorted(
            self.typical_objects.keys(),
            key=lambda k: self.typical_objects[k],
            reverse=True
        )[:5] or ["person", "car"]

        return CameraProfile(
            camera_id=self.camera_id,
            base_confidence=self.base_confidence,
            adapted_confidence=self.parameters.adapted_confidence,
            persistence_frames=self.parameters.persistence_frames,
            false_alarm_rate=self.stats.false_alarm_rate,
            ambient_noise=self.scene.background_noise,
            lighting_baseline=self.lighting.condition,
            status=status,
            typical_objects=top_objects,
            last_calibrated=time.time(),
            lighting_profile=self.lighting.to_dict(),
            scene_baseline=self.scene.to_dict(),
            typical_objects_distribution=dict(self.typical_objects),
            movement_patterns=self.movement.to_dict(),
            detection_statistics=self.stats.to_dict(),
            calibration=dict(self.calibration),
            adaptive_parameters=self.parameters.to_dict(),
            metadata={
                "frame_count": self._frame_count,
                "dominant_heading_deg": self.movement.dominant_heading_deg,
                "stability_score": self.scene.stability_score,
                "scene_representation": (
                    [round(float(v), 4) for v in self.ssl_learner.baseline_scene_descriptor[:8]]
                    if self.ssl_learner.baseline_scene_descriptor is not None else []
                ),
                "circadian_baseline_ready": self.ssl_learner.is_baseline_ready,
            },
        )
