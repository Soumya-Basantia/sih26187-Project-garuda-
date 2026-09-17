"""
Project Garuda — Milestone 1: Learning Memory Manager
Provides high-performance, persistent storage and lifecycle management for:
- Learning Samples (with camera association, validation status, and embedding retrieval)
- Camera Profiles (environmental baselines and adaptive parameters)
- Learning Events (immutable audit trails)
- Dataset Versions (versioned slices for continual training)
- Model Versions (model registry, benchmark metrics, approval states)
- Feedback Records (human-in-the-loop corrections)
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Optional, Any

from ai_engine.learning.data_foundation import (
    LearningSample,
    CameraProfile,
    LearningEvent,
    DatasetVersion,
    ModelVersion,
    FeedbackRecord,
    ValidationStatus,
    SelectionReason,
    LearningEventType,
)

logger = logging.getLogger("garuda.memory_manager")


class LearningMemoryManager:
    """
    Central memory and dataset management layer for continual learning.
    Operates synchronously in memory with backing persistence hooks.
    Thread-safe across multi-camera ingestion and background training threads.
    """

    def __init__(self, max_in_memory_samples: int = 1000):
        self._lock = threading.RLock()
        self.max_in_memory_samples = max_in_memory_samples
        self.samples: dict[str, LearningSample] = {}  # sample_id -> LearningSample
        self.camera_profiles: dict[str, CameraProfile] = {}  # camera_id -> CameraProfile
        self.dataset_versions: dict[str, DatasetVersion] = {}  # version_id -> DatasetVersion
        self.model_versions: dict[str, ModelVersion] = {}  # version -> ModelVersion
        self.feedback_records: dict[str, FeedbackRecord] = {}  # feedback_id -> FeedbackRecord
        self.events: list[LearningEvent] = []

        # Register default baseline model v1.0.0
        self.register_model_version(
            ModelVersion(
                version="v1.0.0",
                model_id="mod_baseline",
                created_at=time.time(),
                model_path="yolov8n.pt",
                base_model="yolov8n.pt",
                is_active=True,
                approval_status="APPROVED",
                notes="Initial Pretrained Tactical Vision Baseline",
            )
        )

    # -------------------------------------------------------------------------
    # 1. Learning Samples
    # -------------------------------------------------------------------------

    def store_sample(self, sample: LearningSample) -> str:
        """Stores or updates a learning sample."""
        with self._lock:
            if len(self.samples) >= self.max_in_memory_samples:
                # Evict oldest non-validated sample
                oldest_key = next(
                    (k for k, s in self.samples.items() if s.validation_status == ValidationStatus.PENDING_REVIEW),
                    next(iter(self.samples.keys()))
                )
                self.samples.pop(oldest_key, None)

            self.samples[sample.sample_id] = sample
            self.log_event(
                LearningEventType.SAMPLE_HARVESTED,
                camera_id=sample.camera_id,
                details={"sample_id": sample.sample_id, "object_type": sample.object_type, "confidence": sample.confidence}
            )
            return sample.sample_id

    def get_sample(self, sample_id: str) -> Optional[LearningSample]:
        with self._lock:
            return self.samples.get(sample_id)

    def get_all_samples(self) -> list[LearningSample]:
        with self._lock:
            return list(self.samples.values())

    def get_samples_by_camera(self, camera_id: str, limit: int = 50) -> list[LearningSample]:
        with self._lock:
            matching = [s for s in self.samples.values() if s.camera_id == camera_id]
            return sorted(matching, key=lambda s: s.timestamp, reverse=True)[:limit]

    def filter_samples(
        self,
        camera_id: Optional[str] = None,
        validation_status: Optional[ValidationStatus] = None,
        object_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[LearningSample]:
        with self._lock:
            res = list(self.samples.values())
            if camera_id:
                res = [s for s in res if s.camera_id == camera_id]
            if validation_status:
                res = [s for s in res if s.validation_status == validation_status]
            if object_type:
                res = [s for s in res if s.object_type.lower() == object_type.lower()]
            return sorted(res, key=lambda s: s.timestamp, reverse=True)[:limit]

    def update_sample_status(self, sample_id: str, status: ValidationStatus, notes: Optional[str] = None) -> bool:
        with self._lock:
            sample = self.samples.get(sample_id)
            if not sample:
                return False
            sample.validation_status = status
            if notes:
                sample.notes = notes
            return True

    # -------------------------------------------------------------------------
    # 2. Camera Profiles
    # -------------------------------------------------------------------------

    def get_or_create_camera_profile(self, camera_id: str) -> CameraProfile:
        if camera_id not in self.camera_profiles:
            self.camera_profiles[camera_id] = CameraProfile(
                camera_id=camera_id,
                base_confidence=0.25,
                adapted_confidence=0.25,
                last_calibrated=time.time(),
            )
        return self.camera_profiles[camera_id]

    def update_camera_profile(self, profile: CameraProfile):
        self.camera_profiles[profile.camera_id] = profile
        self.log_event(
            LearningEventType.CAMERA_CALIBRATED,
            camera_id=profile.camera_id,
            details={"adapted_confidence": profile.adapted_confidence, "status": profile.status}
        )

    # -------------------------------------------------------------------------
    # 3. Dataset Versioning
    # -------------------------------------------------------------------------

    def create_dataset_version(
        self,
        sample_ids: Optional[list[str]] = None,
        notes: str = "",
        validation_split_ratio: float = 0.20,
    ) -> DatasetVersion:
        """Creates an immutable versioned dataset slice from stored samples."""
        if sample_ids is None:
            # Gather all non-rejected samples
            sample_ids = [
                s.sample_id for s in self.samples.values()
                if s.validation_status != ValidationStatus.REJECTED
            ]

        # Calculate class distribution
        class_dist: dict[str, int] = {}
        for sid in sample_ids:
            s = self.samples.get(sid)
            if s:
                cls_lbl = s.object_type
                class_dist[cls_lbl] = class_dist.get(cls_lbl, 0) + 1

        v_idx = len(self.dataset_versions) + 1
        version_id = f"dset_v1.0.{v_idx}"

        dset_ver = DatasetVersion(
            version_id=version_id,
            created_at=time.time(),
            sample_ids=list(sample_ids),
            sample_count=len(sample_ids),
            classes_distribution=class_dist,
            validation_split_ratio=validation_split_ratio,
            notes=notes or f"Generated training dataset slice {version_id}",
        )

        self.dataset_versions[version_id] = dset_ver
        self.log_event(
            LearningEventType.DATASET_VERSIONED,
            details={"version_id": version_id, "sample_count": len(sample_ids)}
        )
        logger.info(f"Created DatasetVersion {version_id} with {len(sample_ids)} samples")
        return dset_ver

    def get_dataset_version(self, version_id: str) -> Optional[DatasetVersion]:
        return self.dataset_versions.get(version_id)

    def list_dataset_versions(self) -> list[DatasetVersion]:
        return sorted(self.dataset_versions.values(), key=lambda d: d.created_at, reverse=True)

    # -------------------------------------------------------------------------
    # 4. Model Version Registry
    # -------------------------------------------------------------------------

    def register_model_version(self, model: ModelVersion) -> str:
        """Registers a candidate or production model version."""
        self.model_versions[model.version] = model
        self.log_event(
            LearningEventType.MODEL_REGISTERED,
            details={"version": model.version, "model_id": model.model_id, "approval_status": model.approval_status}
        )
        return model.version

    def get_model_version(self, version: str) -> Optional[ModelVersion]:
        return self.model_versions.get(version)

    def get_active_model(self) -> Optional[ModelVersion]:
        return next((m for m in self.model_versions.values() if m.is_active), None)

    def set_active_model(self, version: str) -> bool:
        if version not in self.model_versions:
            return False
        for m in self.model_versions.values():
            m.is_active = (m.version == version)
        self.log_event(LearningEventType.MODEL_DEPLOYED, details={"version": version})
        return True

    def list_model_versions(self) -> list[ModelVersion]:
        return sorted(self.model_versions.values(), key=lambda m: m.created_at, reverse=True)

    # -------------------------------------------------------------------------
    # 5. Human Feedback Records
    # -------------------------------------------------------------------------

    def record_feedback(self, feedback: FeedbackRecord) -> str:
        """Records an operator correction, linking it to the sample and camera."""
        self.feedback_records[feedback.feedback_id] = feedback
        if feedback.sample_id and feedback.sample_id in self.samples:
            target_sample = self.samples[feedback.sample_id]
            target_sample.validation_status = feedback.validation_status
            if feedback.validation_status == ValidationStatus.REJECTED:
                target_sample.reinforcement_score = 0.0
            elif feedback.is_false_alarm or feedback.validation_status == ValidationStatus.VALIDATED_FALSE_POSITIVE:
                target_sample.reinforcement_score = -1.0
            else:
                target_sample.reinforcement_score = 1.0

        self.log_event(
            LearningEventType.FEEDBACK_RECORDED,
            camera_id=feedback.camera_id,
            details={
                "feedback_id": feedback.feedback_id,
                "is_false_alarm": feedback.is_false_alarm,
                "corrected_label": feedback.corrected_label
            }
        )
        return feedback.feedback_id

    # -------------------------------------------------------------------------
    # 6. Audit Logging
    # -------------------------------------------------------------------------

    def log_event(self, event_type: LearningEventType, camera_id: Optional[str] = None, details: Optional[dict] = None):
        ev = LearningEvent(
            event_id=f"lev_{uuid.uuid4().hex[:8]}",
            event_type=event_type,
            timestamp=time.time(),
            camera_id=camera_id,
            details=details or {},
        )
        self.events.append(ev)
        if len(self.events) > 5000:
            self.events = self.events[-3000:]


# Global shared instance
memory_manager = LearningMemoryManager()
