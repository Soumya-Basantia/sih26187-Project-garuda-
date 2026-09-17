"""
Project Garuda — Milestone 1: Learning Data & Memory Foundation
Defines standardized data contracts and schemas for continual self-learning:
1. LearningSample (12 canonical attributes: sample_id, camera_id, timestamp, frame_ref,
   object_type, confidence, bounding_box, tracking_id, model_version, selection_reason,
   validation_status, embedding_ref).
2. CameraProfile (environment & sensitivity profile per camera).
3. LearningEvent (audit log of learning events).
4. DatasetVersion (immutable, versioned dataset slices).
5. ModelVersion (model registry, candidate evaluations, approval status).
6. FeedbackRecord (human-in-the-loop validated corrections).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any


class ValidationStatus(str, Enum):
    PENDING_REVIEW = "PENDING_REVIEW"
    VALIDATED_TRUE_POSITIVE = "VALIDATED_TRUE_POSITIVE"
    VALIDATED_FALSE_POSITIVE = "VALIDATED_FALSE_POSITIVE"
    CORRECTED = "CORRECTED"
    REJECTED = "REJECTED"
    AUTO_LABELED = "AUTO_LABELED"


class SelectionReason(str, Enum):
    UNCERTAIN_DETECTION = "UNCERTAIN_DETECTION"
    OCCLUSION_RECOVERY = "OCCLUSION_RECOVERY"
    OPERATOR_FEEDBACK = "OPERATOR_FEEDBACK"
    HIGH_RISK_ANOMALY = "HIGH_RISK_ANOMALY"
    NOVELTY_OUTLIER = "NOVELTY_OUTLIER"
    ENVIRONMENTAL_BASELINE = "ENVIRONMENTAL_BASELINE"
    TRACKING_FAILURE = "TRACKING_FAILURE"
    UNUSUAL_SCENE = "UNUSUAL_SCENE"


class LearningEventType(str, Enum):
    SAMPLE_HARVESTED = "SAMPLE_HARVESTED"
    FEEDBACK_RECORDED = "FEEDBACK_RECORDED"
    DATASET_VERSIONED = "DATASET_VERSIONED"
    MODEL_REGISTERED = "MODEL_REGISTERED"
    MODEL_APPROVED = "MODEL_APPROVED"
    MODEL_REJECTED = "MODEL_REJECTED"
    MODEL_DEPLOYED = "MODEL_DEPLOYED"
    MODEL_ROLLED_BACK = "MODEL_ROLLED_BACK"
    CAMERA_CALIBRATED = "CAMERA_CALIBRATED"


@dataclass
class LearningSample:
    """
    Core data structure for every edge case harvested from live video.
    Retains all 12 canonical attributes required by Project Garuda specification.
    """
    sample_id: str
    camera_id: str
    timestamp: float
    frame_ref: str
    object_type: str
    confidence: float
    bounding_box: tuple[float, float, float, float]  # (x1, y1, x2, y2)
    tracking_id: Optional[int]
    model_version: str
    selection_reason: SelectionReason
    validation_status: ValidationStatus
    embedding_ref: Optional[list[float]] = None  # Normalized 64-dim visual descriptor
    snapshot_data: Optional[str] = None         # Base64 thumbnail for UI
    notes: Optional[str] = None
    reinforcement_score: float = 0.0            # -1.0 for false alarm, +1.0 for confirmed
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["selection_reason"] = self.selection_reason.value if isinstance(self.selection_reason, SelectionReason) else str(self.selection_reason)
        d["validation_status"] = self.validation_status.value if isinstance(self.validation_status, ValidationStatus) else str(self.validation_status)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> LearningSample:
        d = dict(data)
        d.pop("_id", None)
        sel_reason = d.get("selection_reason", SelectionReason.UNCERTAIN_DETECTION)
        if isinstance(sel_reason, str):
            try:
                sel_reason = SelectionReason(sel_reason)
            except ValueError:
                sel_reason = SelectionReason.UNCERTAIN_DETECTION

        val_status = d.get("validation_status", ValidationStatus.PENDING_REVIEW)
        if isinstance(val_status, str):
            try:
                val_status = ValidationStatus(val_status)
            except ValueError:
                val_status = ValidationStatus.PENDING_REVIEW

        bbox = d.get("bounding_box", (0.0, 0.0, 0.0, 0.0))
        if isinstance(bbox, list):
            bbox = tuple(float(v) for v in bbox)

        return cls(
            sample_id=d["sample_id"],
            camera_id=d["camera_id"],
            timestamp=float(d["timestamp"]),
            frame_ref=d.get("frame_ref", ""),
            object_type=d.get("object_type", "object"),
            confidence=float(d.get("confidence", 0.0)),
            bounding_box=bbox,
            tracking_id=d.get("tracking_id"),
            model_version=d.get("model_version", "v1.0.0"),
            selection_reason=sel_reason,
            validation_status=val_status,
            embedding_ref=d.get("embedding_ref"),
            snapshot_data=d.get("snapshot_data"),
            notes=d.get("notes"),
            reinforcement_score=float(d.get("reinforcement_score", 0.0)),
            metadata=d.get("metadata", {}),
        )


@dataclass
class CameraProfile:
    """
    Environmental profile per camera node. Tracks ambient statistics,
    lighting baselines, scene characteristics, movement patterns,
    detection statistics, calibration, and dynamic sensitivity parameters.
    """
    camera_id: str
    base_confidence: float = 0.25
    adapted_confidence: float = 0.25
    persistence_frames: int = 3
    false_alarm_rate: float = 0.0
    ambient_noise: float = 1.0
    lighting_baseline: str = "DAYLIGHT"  # DAYLIGHT | LOW_LIGHT | IR_NIGHT | GLARE | OVERCAST
    status: str = "OPTIMAL"               # OPTIMAL | NOISE_SUPPRESSED | BALANCED | ENVIRONMENT_ADAPTED
    typical_objects: list[str] = field(default_factory=lambda: ["person", "car"])
    last_calibrated: float = field(default_factory=time.time)
    lighting_profile: dict = field(default_factory=lambda: {
        "condition": "DAYLIGHT", "mean_luminance": 128.0, "contrast": 50.0, "glare_ratio": 0.0, "color_saturation": 40.0
    })
    scene_baseline: dict = field(default_factory=lambda: {
        "activity_level": 0.05, "stability_score": 0.95, "background_noise": 1.0
    })
    typical_objects_distribution: dict[str, int] = field(default_factory=lambda: {"person": 0, "car": 0})
    movement_patterns: dict = field(default_factory=lambda: {
        "frequent_directions": [], "entry_zones": [], "exit_zones": [], "dominant_heading_deg": 0.0
    })
    detection_statistics: dict = field(default_factory=lambda: {
        "total_detections": 0, "avg_confidence": 0.50, "false_alarms": 0, "confirmations": 0, "rejections": 0, "false_alarm_rate": 0.0
    })
    calibration: dict = field(default_factory=lambda: {
        "temperature": 1.0, "ambient_factor": 1.0, "sector_modifiers": {}
    })
    adaptive_parameters: dict = field(default_factory=lambda: {
        "adapted_confidence": 0.25, "persistence_frames": 3, "track_match_thresh": 0.70, "max_track_age": 30
    })
    metadata: dict = field(default_factory=dict)

    @property
    def environmental_baseline(self) -> str:
        return self.lighting_baseline

    @property
    def lighting_condition(self) -> str:
        return self.lighting_baseline

    @property
    def adapted_thresholds(self) -> dict[str, Any]:
        return {
            "confidence": self.adapted_confidence,
            "persistence_frames": self.persistence_frames,
        }

    def to_dict(self) -> dict:
        d = asdict(self)
        d["environmental_baseline"] = self.environmental_baseline
        d["lighting_condition"] = self.lighting_condition
        d["adapted_thresholds"] = self.adapted_thresholds
        return d

    @classmethod
    def from_dict(cls, data: dict) -> CameraProfile:
        d = dict(data)
        d.pop("_id", None)
        d.pop("environmental_baseline", None)
        d.pop("lighting_condition", None)
        d.pop("adapted_thresholds", None)
        
        # Ensure new 7-domain keys exist
        if "lighting_profile" not in d:
            d["lighting_profile"] = {"condition": d.get("lighting_baseline", "DAYLIGHT")}
        if "scene_baseline" not in d:
            d["scene_baseline"] = {"activity_level": 0.05, "background_noise": d.get("ambient_noise", 1.0)}
        if "typical_objects_distribution" not in d:
            d["typical_objects_distribution"] = {obj: 1 for obj in d.get("typical_objects", ["person", "car"])}
        if "movement_patterns" not in d:
            d["movement_patterns"] = {"frequent_directions": [], "entry_zones": [], "exit_zones": []}
        if "detection_statistics" not in d:
            d["detection_statistics"] = {"false_alarm_rate": d.get("false_alarm_rate", 0.0)}
        if "calibration" not in d:
            d["calibration"] = {"temperature": 1.0, "ambient_factor": 1.0}
        if "adaptive_parameters" not in d:
            d["adaptive_parameters"] = {
                "adapted_confidence": d.get("adapted_confidence", 0.25),
                "persistence_frames": d.get("persistence_frames", 3),
            }
        return cls(**d)


@dataclass
class LearningEvent:
    """
    Immutable audit log entry recording every self-learning action across Project Garuda.
    """
    event_id: str
    event_type: LearningEventType
    timestamp: float
    camera_id: Optional[str] = None
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["event_type"] = self.event_type.value if isinstance(self.event_type, LearningEventType) else str(self.event_type)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> LearningEvent:
        d = dict(data)
        d.pop("_id", None)
        ev_type = d.get("event_type", LearningEventType.SAMPLE_HARVESTED)
        if isinstance(ev_type, str):
            ev_type = LearningEventType(ev_type)
        return cls(
            event_id=d["event_id"],
            event_type=ev_type,
            timestamp=float(d["timestamp"]),
            camera_id=d.get("camera_id"),
            details=d.get("details", {}),
        )


@dataclass
class DatasetVersion:
    """
    Immutable versioned snapshot of harvested and validated samples prepared for training.
    """
    version_id: str
    created_at: float
    sample_ids: list[str]
    sample_count: int
    classes_distribution: dict[str, int]
    validation_split_ratio: float = 0.20
    dataset_path: str = "./data/active_learning/datasets"
    notes: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def description(self) -> str:
        return self.notes

    @property
    def class_distribution(self) -> dict[str, int]:
        return self.classes_distribution

    def to_dict(self) -> dict:
        d = asdict(self)
        d["description"] = self.description
        d["class_distribution"] = self.class_distribution
        return d

    @classmethod
    def from_dict(cls, data: dict) -> DatasetVersion:
        d = dict(data)
        d.pop("_id", None)
        d.pop("description", None)
        d.pop("class_distribution", None)
        return cls(**d)


@dataclass
class ModelVersion:
    """
    Registry record tracking every model iteration, performance delta, approval status,
    and checkpoint lineage.
    """
    version: str
    model_id: str
    created_at: float
    model_path: str
    base_model: str = "yolov8n.pt"
    dataset_version: Optional[str] = None
    is_active: bool = False
    approval_status: str = "APPROVED"  # PENDING_EVAL | APPROVED | REJECTED | ROLLED_BACK
    metrics: dict[str, float] = field(default_factory=lambda: {
        "accuracy_gain": 0.0,
        "false_alarm_reduction": 0.0,
        "mAP50": 0.85,
    })
    notes: str = ""
    metadata: dict = field(default_factory=dict)

    @property
    def version_id(self) -> str:
        return self.version

    @property
    def file_path(self) -> str:
        return self.model_path

    @property
    def validation_score(self) -> float:
        return float(self.metrics.get("mAP50", 0.85))

    @property
    def status(self) -> str:
        return self.approval_status

    def to_dict(self) -> dict:
        d = asdict(self)
        d["version_id"] = self.version_id
        d["file_path"] = self.file_path
        d["validation_score"] = self.validation_score
        d["status"] = self.status
        return d

    @classmethod
    def from_dict(cls, data: dict) -> ModelVersion:
        d = dict(data)
        d.pop("_id", None)
        d.pop("version_id", None)
        d.pop("file_path", None)
        d.pop("validation_score", None)
        d.pop("status", None)
        return cls(**d)


@dataclass
class FeedbackRecord:
    """
    Dual-record representation preserving both the original AI inference
    and the human-operator correction (1-Click RLHF).
    """
    feedback_id: str
    alert_id: str
    camera_id: str
    timestamp: float
    original_prediction: dict  # {"label": "threat", "confidence": 0.54, "bbox": [...]}
    corrected_label: Optional[str] = None  # e.g., "backpack"
    is_false_alarm: bool = False
    operator_notes: str = ""
    sample_id: Optional[str] = None
    validation_status: ValidationStatus = ValidationStatus.VALIDATED_FALSE_POSITIVE
    metadata: dict = field(default_factory=dict)

    @property
    def operator_label(self) -> Optional[str]:
        return self.corrected_label

    def to_dict(self) -> dict:
        d = asdict(self)
        d["validation_status"] = self.validation_status.value if isinstance(self.validation_status, ValidationStatus) else str(self.validation_status)
        d["operator_label"] = self.operator_label
        return d

    @classmethod
    def from_dict(cls, data: dict) -> FeedbackRecord:
        d = dict(data)
        d.pop("_id", None)
        d.pop("operator_label", None)
        val_status = d.get("validation_status", ValidationStatus.VALIDATED_FALSE_POSITIVE)
        if isinstance(val_status, str):
            val_status = ValidationStatus(val_status)
        return cls(
            feedback_id=d["feedback_id"],
            alert_id=d["alert_id"],
            camera_id=d["camera_id"],
            timestamp=float(d["timestamp"]),
            original_prediction=d.get("original_prediction", {}),
            corrected_label=d.get("corrected_label"),
            is_false_alarm=bool(d.get("is_false_alarm", False)),
            operator_notes=d.get("operator_notes", ""),
            sample_id=d.get("sample_id"),
            validation_status=val_status,
            metadata=d.get("metadata", {}),
        )
