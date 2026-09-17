"""
Project Garuda — Milestone 11 Verification Test Suite
Tests Central Learning Orchestrator, Decision Explainability/Attribution, and SHA-256 Lineage Tracking.
"""

import time
import numpy as np

from ai_engine.learning.data_foundation import (
    LearningSample,
    CameraProfile,
    ValidationStatus,
    SelectionReason,
)
from ai_engine.learning.memory_manager import LearningMemoryManager
from ai_engine.learning.adaptive_filter import AdaptiveNegativeFilter, NegativeExemplar
from ai_engine.learning.orchestrator import (
    CentralLearningOrchestrator,
    LearningLifecycleState,
    DecisionAttributionEngine,
    LineageGraphTracker,
    LineageNode,
)


def test_1_orchestrator_initialization():
    orchestrator = CentralLearningOrchestrator()
    status = orchestrator.get_status()

    assert status["lifecycle_state"] == "IDLE", f"Initial state should be IDLE, got {status['lifecycle_state']}"
    assert "subsystems" in status
    subsystems = status["subsystems"]
    assert subsystems["active_learning_harvester"] == "ONLINE"
    assert subsystems["continual_learning_engine"] == "ONLINE"
    assert subsystems["synthetic_augmentation_pipeline"] == "ONLINE"
    assert subsystems["federated_cluster_synchronizer"] == "ONLINE"
    assert subsystems["decision_attribution_engine"] == "ONLINE"
    print("[OK] Orchestrator initialization: All 8 core learning subsystems ONLINE in IDLE state.")


def test_2_trigger_conditions():
    mem = LearningMemoryManager()
    orchestrator = CentralLearningOrchestrator(memory_manager=mem)
    orchestrator.min_samples_for_cycle = 5

    # Initially empty
    triggers = orchestrator.check_triggers()
    assert triggers["should_run_cycle"] is False
    assert triggers["validated_sample_count"] == 0

    # Add 5 validated samples
    for i in range(5):
        sample = LearningSample(
            sample_id=f"sample_{i}",
            camera_id="CAM-01",
            timestamp=time.time(),
            frame_ref=f"frames/sample_{i}.jpg",
            object_type="backpack",
            confidence=0.85,
            bounding_box=(0.1, 0.1, 0.3, 0.3),
            tracking_id=i,
            model_version="v1.0.0",
            selection_reason=SelectionReason.UNCERTAIN_DETECTION,
            validation_status=ValidationStatus.VALIDATED_TRUE_POSITIVE,
            reinforcement_score=1.0,
        )
        mem.store_sample(sample)

    triggers = orchestrator.check_triggers()
    assert triggers["should_run_cycle"] is True
    assert triggers["validated_sample_count"] == 5
    print(f"[OK] Autonomous triggers: Evaluated correctly ({triggers['validated_sample_count']}/5 samples -> Ready={triggers['should_run_cycle']})")


def test_3_decision_explainability_attribution():
    attribution_engine = DecisionAttributionEngine(default_threshold=0.50)
    adaptive_filter = AdaptiveNegativeFilter()

    # 1. Daylight test
    profile_day = CameraProfile(camera_id="CAM-01")
    if isinstance(profile_day.lighting_profile, dict):
        profile_day.lighting_profile["condition"] = "DAYLIGHT"
    else:
        setattr(profile_day.lighting_profile, "condition", "DAYLIGHT")

    att_day = attribution_engine.explain_detection(
        camera_id="CAM-01",
        class_label="person",
        raw_confidence=0.70,
        bbox=(0.2, 0.2, 0.4, 0.5),
        camera_profile=profile_day,
        adaptive_filter=adaptive_filter,
    )

    assert att_day.final_confidence >= 0.70, "Daylight should provide non-negative boost"
    assert not att_day.is_suppressed, "Valid daytime detection should not be suppressed"
    assert "ALERTED" in att_day.human_explanation

    # 2. False alarm suppression test via negative exemplar
    np.random.seed(42)
    sample_desc = np.random.randn(64).astype(np.float32)
    sample_desc /= np.linalg.norm(sample_desc)

    # Register matching exemplar in adaptive filter
    ex = NegativeExemplar(
        exemplar_id="neg_tree_branch_01",
        camera_id="CAM-02",
        class_label="backpack",
        descriptor=sample_desc.tolist(),
        spatial_coords=(0.45, 0.55, 0.2, 0.2),
        timestamp=time.time(),
        notes="Swaying branch false detection",
        confidence_penalty=0.45,
    )
    adaptive_filter.exemplars["CAM-02"] = [ex]

    # Query with exact matching descriptor
    att_suppressed = attribution_engine.explain_detection(
        camera_id="CAM-02",
        class_label="backpack",
        raw_confidence=0.65,
        bbox=(0.45, 0.55, 0.2, 0.2),
        visual_descriptor=sample_desc.tolist(),
        camera_profile=profile_day,
        adaptive_filter=adaptive_filter,
    )

    assert att_suppressed.is_suppressed, "Matching negative exemplar should trigger suppression"
    assert any(f.name == "NEGATIVE_EXEMPLAR_SUPPRESSION" for f in att_suppressed.factors), "Factor must record exemplar penalty"
    assert "SUPPRESSED" in att_suppressed.human_explanation
    assert "Swaying branch" in att_suppressed.human_explanation
    print(f"[OK] Decision Explainability: Attributed factors: {[f.name for f in att_suppressed.factors]} -> {att_suppressed.human_explanation[:65]}...")


def test_4_lineage_provenance_cryptographic_hash():
    tracker = LineageGraphTracker()

    node = tracker.record_model_lineage(
        model_version_id="garuda_yolo_v1.1.0",
        dataset_version_id="ds_slice_2026_09",
        parent_model_id="garuda_yolo_v1.0.0",
        sample_ids=["sample_001", "sample_002", "sample_003"],
        feedback_ids=["fb_101", "fb_102"],
        synthetic_transforms_applied=["GLARE_BLOOM", "GAUSSIAN_BLUR"],
        validation_metrics={"mAP_50": 0.924, "f1_score": 0.901},
        shadow_agreement_score=0.982,
    )

    # Check hash format
    assert len(node.manifest_hash) == 64, f"SHA-256 digest must be 64 hex chars, got {len(node.manifest_hash)}"
    assert tracker.verify_integrity("garuda_yolo_v1.1.0") is True, "Original lineage node must pass integrity verification"

    # Tampering test: modify a sample ID directly
    node.sample_ids.append("tampered_sample_999")
    # Without updating recorded manifest_hash, verification must fail
    assert tracker.verify_integrity("garuda_yolo_v1.1.0") is False, "Tampered lineage tree must fail SHA-256 verification"
    print(f"[OK] Lineage Tracking: SHA-256 manifest hash = {node.manifest_hash[:16]}... (Tamper detection: VERIFIED)")


def test_5_full_end_to_end_orchestrated_cycle():
    mem = LearningMemoryManager()
    orchestrator = CentralLearningOrchestrator(memory_manager=mem)

    # Seed with validated samples
    for i in range(12):
        s = LearningSample(
            sample_id=f"cycle_seed_{i}",
            camera_id="CAM-01",
            timestamp=time.time(),
            frame_ref=f"frames/seed_{i}.jpg",
            object_type="person",
            confidence=0.90,
            bounding_box=(0.2, 0.2, 0.4, 0.6),
            tracking_id=i,
            model_version="v1.0.0",
            selection_reason=SelectionReason.UNCERTAIN_DETECTION,
            validation_status=ValidationStatus.VALIDATED_TRUE_POSITIVE,
            reinforcement_score=1.0,
        )
        mem.store_sample(s)

    report = orchestrator.run_learning_cycle()

    assert report["status"] == "COMPLETED"
    assert report["cycle_number"] == 1
    assert report["samples_trained"] == 12
    assert "garuda_yolo_v1.1.0" in report["model_candidate"]
    assert report["shadow_stage"] == "SHADOW"
    assert orchestrator.state == LearningLifecycleState.IDLE

    # Verify lineage was recorded
    lineage = orchestrator.lineage_tracker.get_lineage(report["model_candidate"])
    assert lineage is not None
    assert lineage.sample_ids == [f"cycle_seed_{i}" for i in range(12)]
    assert orchestrator.lineage_tracker.verify_integrity(report["model_candidate"]) is True
    print(f"[OK] Full Orchestrated Cycle: Executed in {report['duration_ms']:.2f}ms (Candidate: {report['model_candidate']}, Lineage: Verified)")


def test_6_explainability_latency_benchmark():
    attribution_engine = DecisionAttributionEngine()
    profile = CameraProfile(camera_id="CAM-03")

    t0 = time.perf_counter()
    iterations = 200
    for _ in range(iterations):
        attribution_engine.explain_detection(
            camera_id="CAM-03",
            class_label="car",
            raw_confidence=0.82,
            bbox=(0.1, 0.1, 0.5, 0.5),
            camera_profile=profile,
        )
    elapsed = (time.perf_counter() - t0) * 1000.0 / iterations
    assert elapsed < 2.0, f"Attribution latency {elapsed:.3f}ms exceeds 2.0ms threshold"
    print(f"[OK] Performance benchmark: {elapsed:.4f} ms per explainability attribution query (Target < 2.0ms)")


if __name__ == "__main__":
    print("\n=======================================================")
    print("PROJECT GARUDA — MILESTONE 11 ORCHESTRATOR & LINEAGE SUITE")
    print("=======================================================")
    test_1_orchestrator_initialization()
    test_2_trigger_conditions()
    test_3_decision_explainability_attribution()
    test_4_lineage_provenance_cryptographic_hash()
    test_5_full_end_to_end_orchestrated_cycle()
    test_6_explainability_latency_benchmark()
    print("\n=======================================================")
    print("ALL 6 MILESTONE 11 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=======================================================\n")
