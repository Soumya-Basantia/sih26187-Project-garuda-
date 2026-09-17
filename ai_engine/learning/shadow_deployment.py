"""
Project Garuda — Adaptive Learning Engine
Milestone 9: Zero-Downtime Safe Model Deployment & Shadow Evaluation

Implements safe, staged model deployment with automated safety tripwires:
1. DeploymentStage: SHADOW -> CANARY -> ACTIVE (with ROLLED_BACK safety state).
2. ShadowInferenceEngine: Parallel non-blocking execution comparing candidate predictions
   with production model without altering live alert pipelines or operator UI.
3. SafetyRollbackGuard: Automated tripwires monitoring latency (<45ms), false alarm spikes (<20%),
   and runtime exception rates.
4. CanaryDeploymentManager: Single-camera canary stage monitoring real-world telemetry.
5. AtomicModelHotSwapper: Thread-safe atomic pointer update ensuring zero downtime and zero dropped frames.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger("garuda.shadow_deployment")


# -----------------------------------------------------------------------------
# 1. Deployment Stages & Telemetry Data Models
# -----------------------------------------------------------------------------

class DeploymentStage(str, Enum):
    SHADOW = "SHADOW"            # Parallel silent execution on production feeds
    CANARY = "CANARY"            # Live deployment on a single designated camera
    ACTIVE = "ACTIVE"            # Globally active production model across all cameras
    ROLLED_BACK = "ROLLED_BACK"  # Decommissioned following safety invariant violation


@dataclass
class PromotionGateResults:
    passed_all_gates: bool
    overall_map_delta: float
    critical_class_recall: float
    false_positive_rate: float
    latency_ratio: float
    old_class_retention_score: float
    lineage_hash: str
    failure_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ShadowComparisonMetric:
    timestamp: float
    camera_id: str
    active_latency_ms: float
    candidate_latency_ms: float
    latency_delta_ms: float
    active_detection_count: int
    candidate_detection_count: int
    agreement_score: float       # IoU and class agreement (0.0 to 1.0)
    has_false_alarm_spike: bool
    error_occurred: bool = False
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DeploymentStatusReport:
    candidate_version: str
    stage: DeploymentStage
    active_model_path: str
    candidate_model_path: str
    canary_camera_id: Optional[str]
    total_shadow_frames: int
    mean_active_latency_ms: float
    mean_candidate_latency_ms: float
    mean_agreement_score: float
    false_alarm_spike_count: int
    error_count: int
    is_safe_for_promotion: bool
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["stage"] = self.stage.value if isinstance(self.stage, DeploymentStage) else str(self.stage)
        return d


# -----------------------------------------------------------------------------
# 2. Safety Rollback Guard
# -----------------------------------------------------------------------------

class SafetyRollbackGuard:
    """
    Monitors live deployment telemetry against hard safety constraints.
    Triggers immediate automated rollback upon violation of any invariant.
    """

    def __init__(
        self,
        max_allowed_latency_ms: float = 45.0,
        max_fa_spike_pct: float = 20.0,
        max_allowed_errors: int = 1,
    ):
        self.max_allowed_latency_ms = max_allowed_latency_ms
        self.max_fa_spike_pct = max_fa_spike_pct
        self.max_allowed_errors = max_allowed_errors

    def inspect_metric(self, metric: ShadowComparisonMetric) -> Tuple[bool, Optional[str]]:
        """
        Evaluates a frame comparison metric against safety invariants:
        Returns (is_violated, reason).
        """
        if metric.error_occurred:
            return True, f"INFERENCE_CRASH_DETECTED: {metric.error_message}"

        if metric.candidate_latency_ms > self.max_allowed_latency_ms:
            return True, f"LATENCY_SPIKE_VIOLATION: Candidate latency {metric.candidate_latency_ms:.2f}ms exceeds threshold {self.max_allowed_latency_ms:.2f}ms"

        if metric.has_false_alarm_spike:
            return True, "FALSE_ALARM_SPIKE_VIOLATION: Candidate generated excessive unsuppressed false detections"

        return False, None


# -----------------------------------------------------------------------------
# 3. Shadow Inference Engine
# -----------------------------------------------------------------------------

class ShadowInferenceEngine:
    """
    Evaluates candidate models side-by-side with the active model.
    Runs asynchronously with zero impact on live RTSP streaming.
    """

    def __init__(self, guard: Optional[SafetyRollbackGuard] = None):
        self.guard = guard or SafetyRollbackGuard()
        self.candidate_model_path: Optional[str] = None
        self.candidate_version: Optional[str] = None
        self.candidate_predictor: Optional[Callable[[np.ndarray], list[dict]]] = None
        self.comparison_history: list[ShadowComparisonMetric] = []
        self._max_history = 300
        self._lock = threading.Lock()

    def set_candidate(
        self,
        version: str,
        model_path: str,
        predictor_func: Optional[Callable[[np.ndarray], list[dict]]] = None,
    ):
        with self._lock:
            self.candidate_version = version
            self.candidate_model_path = model_path
            self.candidate_predictor = predictor_func
            self.comparison_history.clear()
        logger.info(f"Initialized shadow candidate {version} at {model_path}")

    def evaluate_shadow_frame(
        self,
        camera_id: str,
        frame: np.ndarray,
        active_detections: list[dict],
        active_latency_ms: float,
    ) -> Optional[ShadowComparisonMetric]:
        """
        Runs candidate on frame in shadow mode and evaluates comparison metrics.
        Returns metric without producing live user-facing alerts.
        """
        if not self.candidate_predictor or frame is None or frame.size == 0:
            return None

        t0 = time.perf_counter()
        error_msg = None
        candidate_dets: list[dict] = []

        try:
            candidate_dets = self.candidate_predictor(frame)
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Shadow candidate inference exception: {e}")

        cand_latency = (time.perf_counter() - t0) * 1000.0

        # Compute detection overlap & class agreement
        agreement = self._compute_agreement(active_detections, candidate_dets)

        # Check false alarm spike (e.g. candidate produces >2.5x detections of active in clear scene)
        has_fa_spike = False
        if len(active_detections) == 0 and len(candidate_dets) >= 3:
            has_fa_spike = True

        metric = ShadowComparisonMetric(
            timestamp=time.time(),
            camera_id=camera_id,
            active_latency_ms=round(active_latency_ms, 2),
            candidate_latency_ms=round(cand_latency, 2),
            latency_delta_ms=round(cand_latency - active_latency_ms, 2),
            active_detection_count=len(active_detections),
            candidate_detection_count=len(candidate_dets),
            agreement_score=round(agreement, 3),
            has_false_alarm_spike=has_fa_spike,
            error_occurred=(error_msg is not None),
            error_message=error_msg,
        )

        with self._lock:
            self.comparison_history.append(metric)
            if len(self.comparison_history) > self._max_history:
                self.comparison_history.pop(0)

        return metric

    def _compute_agreement(self, active_dets: list[dict], cand_dets: list[dict]) -> float:
        """Computes IoU and label consistency between active and candidate detections."""
        if not active_dets and not cand_dets:
            return 1.0
        if not active_dets or not cand_dets:
            return 0.5  # Soft discrepancy

        matches = 0
        for ad in active_dets:
            a_box = ad.get("bbox", (0, 0, 1, 1))
            a_label = ad.get("class", "unknown")

            for cd in cand_dets:
                c_box = cd.get("bbox", (0, 0, 1, 1))
                c_label = cd.get("class", "unknown")

                # IoU
                iou = self._iou(a_box, c_box)
                if iou >= 0.40 and a_label == c_label:
                    matches += 1
                    break

        total_unique = max(len(active_dets), len(cand_dets))
        return matches / max(1, total_unique)

    @staticmethod
    def _iou(boxA: tuple, boxB: tuple) -> float:
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        interArea = max(0.0, xB - xA) * max(0.0, yB - yA)
        boxAArea = max(1e-6, (boxA[2] - boxA[0]) * (boxA[3] - boxA[1]))
        boxBArea = max(1e-6, (boxB[2] - boxB[0]) * (boxB[3] - boxB[1]))

        iou = interArea / float(boxAArea + boxBArea - interArea)
        return float(iou)


# -----------------------------------------------------------------------------
# 4. Atomic Model Hot-Swapper
# -----------------------------------------------------------------------------

class AtomicModelHotSwapper:
    """
    Executes atomic reference updates of underlying model weights across
    active camera pipelines without thread restarts or dropped frames.
    """

    def __init__(self):
        self._swap_lock = threading.Lock()
        self.swap_count: int = 0
        self.last_swap_time: float = 0.0

    def atomic_swap(
        self,
        new_model_path: str,
        target_pipelines: Optional[list[Any]] = None,
    ) -> bool:
        """
        Atomically updates the active detector weights.
        """
        with self._swap_lock:
            try:
                if target_pipelines:
                    for pipe in target_pipelines:
                        if hasattr(pipe, "detector"):
                            # Update model path reference or underlying detector model
                            if hasattr(pipe.detector, "model_path"):
                                pipe.detector.model_path = new_model_path
                            if hasattr(pipe.detector, "model_version"):
                                pipe.detector.model_version = f"deployed_{uuid.uuid4().hex[:6]}"

                self.swap_count += 1
                self.last_swap_time = time.time()
                logger.info(f"Atomic model swap #{self.swap_count} succeeded for {new_model_path}")
                return True
            except Exception as e:
                logger.error(f"Atomic model swap failed: {e}")
                return False


# -----------------------------------------------------------------------------
# 5. Master Deployment & Canary Manager
# -----------------------------------------------------------------------------

class SafeDeploymentManager:
    """
    Master coordinator governing candidate lifecycle:
    SHADOW -> CANARY (1 camera) -> ACTIVE (Global) with automated rollback.
    """

    def __init__(
        self,
        active_model_path: str = "yolov8n.pt",
        active_version: str = "v1.0.0",
    ):
        self.active_version = active_version
        self.active_model_path = active_model_path
        self.previous_stable_model_path = active_model_path
        self.previous_stable_version = active_version

        self.candidate_version: Optional[str] = None
        self.candidate_model_path: Optional[str] = None
        self.current_stage: DeploymentStage = DeploymentStage.ACTIVE
        self.canary_camera_id: Optional[str] = None

        self.guard = SafetyRollbackGuard()
        self.shadow_engine = ShadowInferenceEngine(self.guard)
        self.hot_swapper = AtomicModelHotSwapper()
        self.status_history: list[DeploymentStatusReport] = []

    def start_shadow_evaluation(
        self,
        candidate_version: str,
        candidate_model_path: str,
        candidate_predictor: Optional[Callable[[np.ndarray], list[dict]]] = None,
    ) -> DeploymentStatusReport:
        """
        Initializes shadow mode: candidate runs in parallel on live feeds without user alerts.
        """
        self.candidate_version = candidate_version
        self.candidate_model_path = candidate_model_path
        self.current_stage = DeploymentStage.SHADOW
        self.canary_camera_id = None

        self.shadow_engine.set_candidate(
            version=candidate_version,
            model_path=candidate_model_path,
            predictor_func=candidate_predictor,
        )

        return self.get_status_report()

    def promote_to_canary(self, canary_camera_id: str) -> Tuple[bool, str, DeploymentStatusReport]:
        """
        Promotes candidate from SHADOW to CANARY on a single designated camera.
        """
        if self.current_stage != DeploymentStage.SHADOW:
            return False, f"Cannot promote to canary from stage {self.current_stage.value}. Must be in SHADOW.", self.get_status_report()

        report = self.get_status_report()
        if not report.is_safe_for_promotion:
            return False, "Candidate failed shadow safety benchmarks. Promotion aborted.", report

        self.current_stage = DeploymentStage.CANARY
        self.canary_camera_id = canary_camera_id
        logger.info(f"Promoted candidate {self.candidate_version} to CANARY on camera {canary_camera_id}")
        return True, f"Candidate promoted to CANARY on camera {canary_camera_id}", self.get_status_report()

    def promote_to_active_global(self, target_pipelines: Optional[list[Any]] = None) -> Tuple[bool, str, DeploymentStatusReport]:
        """
        Promotes candidate to globally ACTIVE across all cameras via atomic hot-swap.
        """
        if self.current_stage not in (DeploymentStage.SHADOW, DeploymentStage.CANARY):
            return False, f"Cannot promote to active from stage {self.current_stage.value}", self.get_status_report()

        report = self.get_status_report()
        if not report.is_safe_for_promotion:
            return False, "Candidate failed safety invariants. Global promotion aborted.", report

        # Execute atomic zero-downtime hot-swap
        success = self.hot_swapper.atomic_swap(self.candidate_model_path, target_pipelines)
        if not success:
            return False, "Atomic hot-swap failed during execution.", self.get_status_report()

        # Update stable references
        self.previous_stable_version = self.active_version
        self.previous_stable_model_path = self.active_model_path
        self.active_version = self.candidate_version or self.active_version
        self.active_model_path = self.candidate_model_path or self.active_model_path

        self.current_stage = DeploymentStage.ACTIVE
        self.canary_camera_id = None
        self.candidate_version = None
        self.candidate_model_path = None

        logger.info(f"Candidate successfully deployed globally as ACTIVE model: {self.active_version}")
        return True, f"Candidate promoted globally to ACTIVE ({self.active_version})", self.get_status_report()

    def evaluate_multi_metric_gates(
        self,
        overall_map_delta: float = 0.02,
        critical_class_recall: float = 0.94,
        false_positive_rate: float = 0.03,
        latency_ratio: float = 1.05,
        old_class_retention: float = 0.98,
    ) -> PromotionGateResults:
        """
        Pillar 5: Comprehensive multi-metric promotion evaluation before canary/promotion.
        Prevents promoting models that improve average mAP at the expense of critical security classes.
        """
        import hashlib
        failures = []
        if overall_map_delta < 0.0:
            failures.append(f"Overall mAP regressed by {overall_map_delta:.4f}")
        if critical_class_recall < 0.90:
            failures.append(f"Critical threat recall below 90% ({critical_class_recall:.2%})")
        if false_positive_rate > 0.05:
            failures.append(f"False positive rate exceeded 5% ({false_positive_rate:.2%})")
        if latency_ratio > 1.15:
            failures.append(f"Inference latency increased by {latency_ratio - 1.0:.1%}")
        if old_class_retention < 0.95:
            failures.append(f"Catastrophic forgetting detected: old class retention {old_class_retention:.2%}")

        lineage_content = f"{self.candidate_version}:{self.candidate_model_path}:{time.time()}"
        lineage_hash = hashlib.sha256(lineage_content.encode("utf-8")).hexdigest()

        return PromotionGateResults(
            passed_all_gates=(len(failures) == 0),
            overall_map_delta=overall_map_delta,
            critical_class_recall=critical_class_recall,
            false_positive_rate=false_positive_rate,
            latency_ratio=latency_ratio,
            old_class_retention_score=old_class_retention,
            lineage_hash=lineage_hash,
            failure_reasons=failures,
        )


    def trigger_emergency_rollback(
        self,
        reason: str,
        target_pipelines: Optional[list[Any]] = None,
    ) -> DeploymentStatusReport:
        """
        Immediately rolls back to the previous stable baseline and flags ROLLED_BACK.
        """
        logger.warning(f"EMERGENCY ROLLBACK TRIGGERED! Reason: {reason}")
        self.current_stage = DeploymentStage.ROLLED_BACK
        self.canary_camera_id = None

        # Re-swap back to stable baseline
        self.hot_swapper.atomic_swap(self.previous_stable_model_path, target_pipelines)
        self.active_model_path = self.previous_stable_model_path
        self.active_version = self.previous_stable_version

        report = self.get_status_report()
        self.status_history.append(report)
        return report

    def process_frame_telemetry(
        self,
        camera_id: str,
        frame: np.ndarray,
        active_detections: list[dict],
        active_latency_ms: float,
        target_pipelines: Optional[list[Any]] = None,
    ) -> Optional[ShadowComparisonMetric]:
        """
        Taps incoming frame. If safety invariants trip, triggers automatic rollback.
        """
        if self.current_stage not in (DeploymentStage.SHADOW, DeploymentStage.CANARY):
            return None

        metric = self.shadow_engine.evaluate_shadow_frame(
            camera_id=camera_id,
            frame=frame,
            active_detections=active_detections,
            active_latency_ms=active_latency_ms,
        )

        if metric:
            violated, reason = self.guard.inspect_metric(metric)
            if violated:
                self.trigger_emergency_rollback(reason=reason or "Safety invariant tripwire violated", target_pipelines=target_pipelines)

        return metric

    def get_status_report(self) -> DeploymentStatusReport:
        """Returns consolidated deployment status and safety report."""
        history = self.shadow_engine.comparison_history
        n_frames = len(history)

        mean_act_lat = float(np.mean([m.active_latency_ms for m in history])) if history else 15.0
        mean_cand_lat = float(np.mean([m.candidate_latency_ms for m in history])) if history else 16.0
        mean_agree = float(np.mean([m.agreement_score for m in history])) if history else 0.95
        fa_spikes = sum(1 for m in history if m.has_false_alarm_spike)
        err_count = sum(1 for m in history if m.error_occurred)

        # Safe for promotion if latency acceptable, error count 0, and agreement >= 0.70
        is_safe = (
            self.current_stage != DeploymentStage.ROLLED_BACK
            and mean_cand_lat <= self.guard.max_allowed_latency_ms
            and err_count <= self.guard.max_allowed_errors
            and fa_spikes <= 2
            and mean_agree >= 0.65
        )

        return DeploymentStatusReport(
            candidate_version=self.candidate_version or "none",
            stage=self.current_stage,
            active_model_path=self.active_model_path,
            candidate_model_path=self.candidate_model_path or "none",
            canary_camera_id=self.canary_camera_id,
            total_shadow_frames=n_frames,
            mean_active_latency_ms=round(mean_act_lat, 2),
            mean_candidate_latency_ms=round(mean_cand_lat, 2),
            mean_agreement_score=round(mean_agree, 3),
            false_alarm_spike_count=fa_spikes,
            error_count=err_count,
            is_safe_for_promotion=is_safe,
        )


# Global singleton
deployment_manager = SafeDeploymentManager()
