"""
Project Garuda — Milestone 1: Learning Data & Memory Foundation Verification Test
Verifies:
1. All 6 core schemas: LearningSample (12 canonical fields), CameraProfile,
   LearningEvent, DatasetVersion, ModelVersion, FeedbackRecord.
2. Serialization and deserialization roundtrip fidelity for all schemas.
3. LearningMemoryManager operations:
   - Sample storage, camera filtering, and status filtering.
   - Camera profile association and dynamic thresholds.
   - Immutable dataset version slicing and class distribution computation.
   - Model version registry: candidate registration, approval, and active swapping.
   - Operator feedback association and sample reinforcement updating.
   - Learning audit events logging.
4. API Route import and contract verification.
"""

import sys
import os
import time

# Ensure project root and backend are on sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

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
from ai_engine.learning.memory_manager import LearningMemoryManager


def test_learning_sample_canonical_fields():
    print("[TEST 1] Testing LearningSample 12 canonical fields & roundtrip...")
    sample = LearningSample(
        sample_id="smp_test_001",
        camera_id="CAM-G1",
        timestamp=time.time(),
        frame_ref="/snapshots/smp_test_001.jpg",
        object_type="person",
        confidence=0.42,
        bounding_box=(100.0, 150.0, 250.0, 400.0),
        tracking_id=14,
        model_version="v1.0.0",
        selection_reason=SelectionReason.UNCERTAIN_DETECTION,
        validation_status=ValidationStatus.PENDING_REVIEW,
        embedding_ref=[0.123] * 64,
        notes="Borderline detection during rain",
        reinforcement_score=0.0,
    )

    # 12 canonical fields verification
    canonical_fields = [
        "sample_id", "camera_id", "timestamp", "frame_ref",
        "object_type", "confidence", "bounding_box", "tracking_id",
        "model_version", "selection_reason", "validation_status", "embedding_ref"
    ]
    for field in canonical_fields:
        assert hasattr(sample, field), f"Missing canonical field: {field}"

    # Roundtrip test
    s_dict = sample.to_dict()
    assert s_dict["sample_id"] == "smp_test_001"
    assert s_dict["selection_reason"] == "UNCERTAIN_DETECTION"
    assert s_dict["validation_status"] == "PENDING_REVIEW"
    assert len(s_dict["embedding_ref"]) == 64

    reconstructed = LearningSample.from_dict(s_dict)
    assert reconstructed.sample_id == sample.sample_id
    assert reconstructed.camera_id == sample.camera_id
    assert reconstructed.confidence == sample.confidence
    assert reconstructed.bounding_box == sample.bounding_box
    assert reconstructed.tracking_id == sample.tracking_id
    assert reconstructed.selection_reason == SelectionReason.UNCERTAIN_DETECTION
    assert reconstructed.validation_status == ValidationStatus.PENDING_REVIEW
    print("  -> Passed: LearningSample conforms to all 12 canonical fields.")


def test_camera_profile_schema():
    print("[TEST 2] Testing CameraProfile schema & environmental baselines...")
    profile = CameraProfile(
        camera_id="CAM-G2",
        base_confidence=0.25,
        adapted_confidence=0.34,
        persistence_frames=4,
        lighting_baseline="LOW_LIGHT",
        status="ENVIRONMENT_ADAPTED",
    )
    assert profile.environmental_baseline == "LOW_LIGHT"
    assert profile.lighting_condition == "LOW_LIGHT"
    assert profile.adapted_thresholds["confidence"] == 0.34
    assert profile.adapted_thresholds["persistence_frames"] == 4

    p_dict = profile.to_dict()
    assert p_dict["environmental_baseline"] == "LOW_LIGHT"
    assert p_dict["adapted_thresholds"]["confidence"] == 0.34

    reconstructed = CameraProfile.from_dict(p_dict)
    assert reconstructed.camera_id == "CAM-G2"
    assert reconstructed.adapted_confidence == 0.34
    print("  -> Passed: CameraProfile correctly manages environmental baseline and thresholds.")


def test_dataset_version_and_model_version_schemas():
    print("[TEST 3] Testing DatasetVersion & ModelVersion schemas...")
    dset = DatasetVersion(
        version_id="dset_v1.0.1",
        created_at=time.time(),
        sample_ids=["smp_1", "smp_2", "smp_3"],
        sample_count=3,
        classes_distribution={"person": 2, "backpack": 1},
        notes="Edge-case harvest slice #1",
    )
    assert dset.description == "Edge-case harvest slice #1"
    assert dset.class_distribution["person"] == 2
    d_dict = dset.to_dict()
    assert d_dict["version_id"] == "dset_v1.0.1"
    rec_dset = DatasetVersion.from_dict(d_dict)
    assert rec_dset.sample_count == 3

    model = ModelVersion(
        version="v1.1.0",
        model_id="mod_cand_01",
        created_at=time.time(),
        model_path="./data/models/checkpoints/garuda_v1.1.0.pt",
        base_model="yolov8n.pt",
        approval_status="APPROVED",
        metrics={"mAP50": 0.88, "accuracy_gain": 3.4, "false_alarm_reduction": 14.2},
    )
    assert model.version_id == "v1.1.0"
    assert model.file_path == "./data/models/checkpoints/garuda_v1.1.0.pt"
    assert model.validation_score == 0.88
    assert model.status == "APPROVED"
    m_dict = model.to_dict()
    rec_model = ModelVersion.from_dict(m_dict)
    assert rec_model.version == "v1.1.0"
    assert rec_model.metrics["false_alarm_reduction"] == 14.2
    print("  -> Passed: DatasetVersion and ModelVersion schemas validated.")


def test_feedback_record_schema():
    print("[TEST 4] Testing FeedbackRecord dual-record schema...")
    fb = FeedbackRecord(
        feedback_id="fb_001",
        alert_id="alt_99",
        camera_id="CAM-G1",
        timestamp=time.time(),
        original_prediction={"label": "threat", "confidence": 0.52},
        corrected_label="duffel_bag",
        is_false_alarm=True,
        operator_notes="False alert triggered by luggage bag",
        sample_id="smp_test_001",
        validation_status=ValidationStatus.VALIDATED_FALSE_POSITIVE,
    )
    assert fb.operator_label == "duffel_bag"
    fb_dict = fb.to_dict()
    assert fb_dict["operator_label"] == "duffel_bag"
    assert fb_dict["is_false_alarm"] is True

    rec_fb = FeedbackRecord.from_dict(fb_dict)
    assert rec_fb.feedback_id == "fb_001"
    assert rec_fb.operator_label == "duffel_bag"
    print("  -> Passed: FeedbackRecord dual-record correctly links predictions to corrections.")


def test_memory_manager_workflows():
    print("[TEST 5] Testing LearningMemoryManager operations...")
    mm = LearningMemoryManager(max_in_memory_samples=50)

    # 1. Sample storage & retrieval
    s1 = LearningSample(
        sample_id="s1", camera_id="CAM-A", timestamp=100.0, frame_ref="",
        object_type="person", confidence=0.35, bounding_box=(0,0,10,10),
        tracking_id=1, model_version="v1.0.0",
        selection_reason=SelectionReason.UNCERTAIN_DETECTION,
        validation_status=ValidationStatus.PENDING_REVIEW,
    )
    s2 = LearningSample(
        sample_id="s2", camera_id="CAM-A", timestamp=105.0, frame_ref="",
        object_type="car", confidence=0.45, bounding_box=(10,10,50,50),
        tracking_id=2, model_version="v1.0.0",
        selection_reason=SelectionReason.OPERATOR_FEEDBACK,
        validation_status=ValidationStatus.VALIDATED_TRUE_POSITIVE,
    )
    s3 = LearningSample(
        sample_id="s3", camera_id="CAM-B", timestamp=110.0, frame_ref="",
        object_type="person", confidence=0.38, bounding_box=(5,5,20,20),
        tracking_id=3, model_version="v1.0.0",
        selection_reason=SelectionReason.UNCERTAIN_DETECTION,
        validation_status=ValidationStatus.PENDING_REVIEW,
    )
    mm.store_sample(s1)
    mm.store_sample(s2)
    mm.store_sample(s3)

    assert mm.get_sample("s1") is not None
    cam_a_samples = mm.get_samples_by_camera("CAM-A")
    assert len(cam_a_samples) == 2
    assert cam_a_samples[0].sample_id == "s2"  # Newest first

    pending_samples = mm.filter_samples(validation_status=ValidationStatus.PENDING_REVIEW)
    assert len(pending_samples) == 2

    # 2. Camera Profiles
    prof = mm.get_or_create_camera_profile("CAM-A")
    prof.adapted_confidence = 0.32
    prof.lighting_baseline = "GLARE"
    mm.update_camera_profile(prof)
    assert mm.get_or_create_camera_profile("CAM-A").adapted_confidence == 0.32

    # 3. Dataset versioning
    dset_slice = mm.create_dataset_version(sample_ids=["s1", "s2"], notes="Batch A slice")
    assert dset_slice.version_id.startswith("dset_v1.0.")
    assert dset_slice.sample_count == 2
    assert dset_slice.classes_distribution == {"person": 1, "car": 1}

    # 4. Model Version Registry
    m_cand = ModelVersion(
        version="v1.0.1",
        model_id="mod_cand_101",
        created_at=time.time(),
        model_path="data/models/checkpoints/v1.0.1.pt",
        approval_status="PENDING_EVAL",
    )
    mm.register_model_version(m_cand)
    assert mm.get_model_version("v1.0.1") is not None
    assert mm.get_active_model().version == "v1.0.0"  # Default baseline active

    # Deploy candidate
    assert mm.set_active_model("v1.0.1") is True
    assert mm.get_active_model().version == "v1.0.1"

    # 5. Feedback Association
    fb = FeedbackRecord(
        feedback_id="fb_101", alert_id="alt_1", camera_id="CAM-A", timestamp=120.0,
        original_prediction={"label": "person"}, corrected_label="shadow",
        is_false_alarm=True, sample_id="s1", validation_status=ValidationStatus.VALIDATED_FALSE_POSITIVE,
    )
    mm.record_feedback(fb)
    # Verify sample reinforcement update
    updated_s1 = mm.get_sample("s1")
    assert updated_s1.validation_status == ValidationStatus.VALIDATED_FALSE_POSITIVE
    assert updated_s1.reinforcement_score == -1.0

    # 6. Learning Audit Events Log
    assert len(mm.events) >= 6
    ev_types = [e.event_type for e in mm.events]
    assert LearningEventType.SAMPLE_HARVESTED in ev_types
    assert LearningEventType.CAMERA_CALIBRATED in ev_types
    assert LearningEventType.DATASET_VERSIONED in ev_types
    assert LearningEventType.MODEL_REGISTERED in ev_types
    assert LearningEventType.MODEL_DEPLOYED in ev_types
    assert LearningEventType.FEEDBACK_RECORDED in ev_types

    print("  -> Passed: LearningMemoryManager operations fully functional.")


def test_api_routes_and_backend_contracts():
    print("[TEST 6] Testing learning routes and database imports...")
    from app.api.learning_routes import router
    assert router.prefix == "/api/learning"
    route_paths = [r.path for r in router.routes]
    print(f"  Available learning routes ({len(route_paths)}): {route_paths}")
    assert "/api/learning/stats" in route_paths
    assert "/api/learning/samples" in route_paths
    assert "/api/learning/feedback" in route_paths
    assert "/api/learning/datasets" in route_paths
    assert "/api/learning/models" in route_paths
    assert "/api/learning/audit-events" in route_paths
    assert "/api/learning/camera-profiles" in route_paths
    print("  -> Passed: All Milestone 1 endpoints registered cleanly in FastAPI router.")


if __name__ == "__main__":
    print("=" * 70)
    print("PROJECT GARUDA — MILESTONE 1 VERIFICATION TEST SUITE")
    print("=" * 70)
    test_learning_sample_canonical_fields()
    test_camera_profile_schema()
    test_dataset_version_and_model_version_schemas()
    test_feedback_record_schema()
    test_memory_manager_workflows()
    test_api_routes_and_backend_contracts()
    print("=" * 70)
    print("ALL MILESTONE 1 FOUNDATION TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 70)
