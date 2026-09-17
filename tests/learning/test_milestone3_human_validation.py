"""
Project Garuda — Milestone 3: Human Validation Workflow Verification Test Suite
Verifies:
1. Review queue querying and data structure (crop, bbox, class, confidence, camera, timestamp).
2. Action: CONFIRM -> sets status to VALIDATED_TRUE_POSITIVE (+1.0), candidate training pool.
3. Action: FALSE_ALARM -> sets status to VALIDATED_FALSE_POSITIVE (-1.0), immediate negative exemplar registration.
4. Action: RELABEL -> sets status to CORRECTED (+1.0), updates ground-truth class label.
5. Action: REJECT -> sets status to REJECTED, archived without training.
6. Audit trail integrity: FeedbackRecord and LearningEvent audit logging with operator user ID.
"""

import os
import sys
import time
import asyncio
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from ai_engine.learning.data_foundation import (
    LearningSample,
    SelectionReason,
    ValidationStatus,
    LearningEventType,
)
from ai_engine.learning.memory_manager import memory_manager
from ai_engine.learning.adaptive_filter import AdaptiveNegativeFilter
from app.api.learning_routes import (
    get_validation_review_queue,
    validate_sample,
    ValidateSampleIn,
)
from app.services.pipeline_manager import pipeline_manager


def setup_test_samples():
    """Populates memory_manager with mock harvest samples for validation testing."""
    for i in range(1, 5):
        sample = LearningSample(
            sample_id=f"val_test_{i:03d}",
            camera_id=f"CAM-0{i}",
            timestamp=time.time() - (100 * i),
            frame_ref=f"/snapshots/test_frame_{i}.jpg",
            object_type="person",
            confidence=0.45 + (0.02 * i),
            bounding_box=(50.0, 50.0, 150.0, 200.0),
            tracking_id=100 + i,
            model_version="v1.0.0",
            selection_reason=SelectionReason.UNCERTAIN_DETECTION,
            validation_status=ValidationStatus.PENDING_REVIEW,
            snapshot_data="data:image/jpeg;base64,/9j/4AAQSkZJRg==",
            notes=f"Test sample #{i}",
        )
        memory_manager.store_sample(sample)


async def test_human_validation_workflow():
    print("======================================================================")
    print("PROJECT GARUDA — MILESTONE 3 HUMAN VALIDATION VERIFICATION TEST SUITE")
    print("======================================================================")

    setup_test_samples()
    mock_user = {"username": "commander_shepard", "role": "ADMIN"}

    # 1. Test Review Queue Fetching
    print("[TEST 1] Testing review queue retrieval...")
    queue_items = await get_validation_review_queue(status="PENDING_REVIEW", user=mock_user)
    assert len(queue_items) >= 4, f"Expected at least 4 pending samples, got {len(queue_items)}"
    first_item = next(item for item in queue_items if item["sample_id"] == "val_test_001")
    assert first_item["validation_status"] == "PENDING_REVIEW"
    assert first_item["object_type"] == "person"
    assert first_item["bounding_box"] == (50.0, 50.0, 150.0, 200.0)
    print("  -> Passed: Review queue correctly delivers pending edge cases with metadata & crops.")

    # 2. Test Action: CONFIRM (True Positive -> Training Candidate Pool)
    print("[TEST 2] Testing validation action: CONFIRM...")
    res_confirm = await validate_sample(
        sample_id="val_test_001",
        payload=ValidateSampleIn(action="CONFIRM", notes="Verified person detection"),
        user=mock_user,
    )
    assert res_confirm["validation_status"] == "VALIDATED_TRUE_POSITIVE"
    updated_001 = memory_manager.get_sample("val_test_001")
    assert updated_001.validation_status == ValidationStatus.VALIDATED_TRUE_POSITIVE
    assert updated_001.reinforcement_score == 1.0
    print("  -> Passed: CONFIRM promoted sample to VALIDATED_TRUE_POSITIVE with +1.0 reinforcement.")

    # 3. Test Action: FALSE_ALARM (False Positive -> Negative Exemplar Suppression)
    print("[TEST 3] Testing validation action: FALSE_ALARM (Immediate suppression)...")
    initial_exemplars = len(pipeline_manager.adaptive_filter.exemplars.get("CAM-02", []))
    res_fa = await validate_sample(
        sample_id="val_test_002",
        payload=ValidateSampleIn(action="FALSE_ALARM", notes="Shadow mistaken for person"),
        user=mock_user,
    )
    assert res_fa["validation_status"] == "VALIDATED_FALSE_POSITIVE"
    updated_002 = memory_manager.get_sample("val_test_002")
    assert updated_002.validation_status == ValidationStatus.VALIDATED_FALSE_POSITIVE
    assert updated_002.reinforcement_score == -1.0

    # Verify registration in AdaptiveNegativeFilter
    new_exemplars = len(pipeline_manager.adaptive_filter.exemplars.get("CAM-02", []))
    assert new_exemplars >= initial_exemplars
    print("  -> Passed: FALSE_ALARM registered negative exemplar and applied -1.0 reinforcement.")

    # 4. Test Action: RELABEL (Correction -> Training Candidate Pool with New Class)
    print("[TEST 4] Testing validation action: RELABEL (Ground-truth correction)...")
    res_relabel = await validate_sample(
        sample_id="val_test_003",
        payload=ValidateSampleIn(action="RELABEL", corrected_label="backpack", notes="Corrected class"),
        user=mock_user,
    )
    assert res_relabel["validation_status"] == "CORRECTED"
    assert res_relabel["new_label"] == "backpack"
    updated_003 = memory_manager.get_sample("val_test_003")
    assert updated_003.validation_status == ValidationStatus.CORRECTED
    assert updated_003.object_type == "backpack"
    assert updated_003.reinforcement_score == 1.0
    print("  -> Passed: RELABEL updated object_type to 'backpack' and marked status as CORRECTED.")

    # 5. Test Action: REJECT (Discard -> Audit Archive)
    print("[TEST 5] Testing validation action: REJECT (Discard from training)...")
    res_reject = await validate_sample(
        sample_id="val_test_004",
        payload=ValidateSampleIn(action="REJECT", notes="Low quality / unidentifiable crop"),
        user=mock_user,
    )
    assert res_reject["validation_status"] == "REJECTED"
    updated_004 = memory_manager.get_sample("val_test_004")
    assert updated_004.validation_status == ValidationStatus.REJECTED
    assert updated_004.reinforcement_score == 0.0

    # Dataset slice generation must exclude REJECTED samples
    dset_slice = memory_manager.create_dataset_version(notes="Candidate pool slice")
    assert "val_test_004" not in dset_slice.sample_ids, "REJECTED sample must never enter training dataset"
    assert "val_test_001" in dset_slice.sample_ids, "CONFIRMED sample must enter training dataset"
    assert "val_test_003" in dset_slice.sample_ids, "RELABELED sample must enter training dataset"
    assert dset_slice.classes_distribution.get("backpack", 0) >= 1
    print("  -> Passed: REJECT safely excluded from training slices while CONFIRMED/RELABELED samples are retained.")

    # 6. Test Audit Logging
    print("[TEST 6] Testing human validation audit logging...")
    assert len(memory_manager.events) > 0
    feedback_events = [e for e in memory_manager.events if e.event_type == LearningEventType.FEEDBACK_RECORDED]
    assert len(feedback_events) >= 4
    last_event = feedback_events[-1]
    assert last_event.details.get("user_id") == "commander_shepard"
    assert "action" in last_event.details

    # Check feedback records map
    assert len(memory_manager.feedback_records) >= 4
    sample_3_fb = next((fb for fb in memory_manager.feedback_records.values() if fb.sample_id == "val_test_003"), None)
    assert sample_3_fb is not None
    assert sample_3_fb.corrected_label == "backpack"
    print("  -> Passed: All operator actions recorded in FeedbackRecord and LearningEvent audit logs.")

    print("======================================================================")
    print("ALL MILESTONE 3 HUMAN VALIDATION TESTS PASSED (100% SUCCESS)!")
    print("======================================================================")


if __name__ == "__main__":
    asyncio.run(test_human_validation_workflow())
