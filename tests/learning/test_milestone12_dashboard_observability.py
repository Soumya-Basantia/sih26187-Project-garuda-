"""
Project Garuda — Milestone 12 Verification Test Suite
Tests Dashboard & Observability UI Contracts: Orchestrator Status, Decision Explainability,
and Cryptographic Lineage Provenance Graphs.
"""

import time
import json
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
    get_learning_orchestrator,
)


def test_1_orchestrator_status_contract():
    orchestrator = get_learning_orchestrator()
    status = orchestrator.get_status()
    triggers = orchestrator.check_triggers()

    # Schema verification matching frontend OrchestratorStatusResponse
    assert "lifecycle_state" in status
    assert "cycle_count" in status
    assert "last_cycle_timestamp" in status
    assert "subsystems" in status
    assert "last_cycle_report" in status

    subsystems = status["subsystems"]
    assert "active_learning_harvester" in subsystems
    assert "continual_learning_engine" in subsystems
    assert "staged_deployment_manager" in subsystems
    assert "decision_attribution_engine" in subsystems
    assert "lineage_graph_tracker" in subsystems

    assert "sample_volume_trigger" in triggers
    assert "time_elapsed_trigger" in triggers
    assert "should_run_cycle" in triggers
    assert "validated_sample_count" in triggers
    assert "threshold_required" in triggers

    # Verify JSON serializability
    payload = {"status": "success", "orchestrator": status, "triggers": triggers}
    serialized = json.dumps(payload)
    assert len(serialized) > 100
    print("[OK] Orchestrator status API contract: Schema verified and 100% JSON-serializable.")


def test_2_explainability_attribution_contract():
    orchestrator = get_learning_orchestrator()
    profile = CameraProfile(camera_id="CAM-02")
    if isinstance(profile.lighting_profile, dict):
        profile.lighting_profile["condition"] = "GLARE"
    else:
        setattr(profile.lighting_profile, "condition", "GLARE")

    # Add negative exemplar for CAM-02
    np.random.seed(42)
    desc = np.random.randn(64).astype(np.float32)
    desc /= np.linalg.norm(desc)
    ex = NegativeExemplar(
        exemplar_id="neg_branch_test",
        camera_id="CAM-02",
        class_label="backpack",
        descriptor=desc.tolist(),
        spatial_coords=(0.4, 0.4, 0.3, 0.3),
        timestamp=time.time(),
        notes="Recurring foliage false alarm",
        confidence_penalty=0.45,
    )
    if "CAM-02" not in orchestrator.adaptive_filter.exemplars:
        orchestrator.adaptive_filter.exemplars["CAM-02"] = []
    orchestrator.adaptive_filter.exemplars["CAM-02"].append(ex)

    attribution = orchestrator.attribution_engine.explain_detection(
        camera_id="CAM-02",
        class_label="backpack",
        raw_confidence=0.68,
        bbox=(0.4, 0.4, 0.3, 0.3),
        visual_descriptor=desc.tolist(),
        camera_profile=profile,
        adaptive_filter=orchestrator.adaptive_filter,
    )

    d = attribution.to_dict()
    # Contract fields matching frontend DecisionAttribution
    assert "decision_id" in d
    assert "camera_id" in d
    assert "class_label" in d
    assert "raw_confidence" in d
    assert "final_confidence" in d
    assert "is_suppressed" in d
    assert "threshold_applied" in d
    assert "factors" in d
    assert "human_explanation" in d
    assert isinstance(d["factors"], list)
    assert len(d["factors"]) >= 2
    for f in d["factors"]:
        assert "name" in f
        assert "impact" in f
        assert "description" in f

    assert d["is_suppressed"] is True
    assert "Recurring foliage" in d["human_explanation"]
    print(f"[OK] Explainability attribution contract: Verified {len(d['factors'])} factors -> {d['human_explanation'][:60]}...")


def test_3_lineage_graph_contract():
    orchestrator = get_learning_orchestrator()

    # Trigger cycle to generate a model lineage node
    report = orchestrator.run_learning_cycle(force=True)
    assert report["status"] == "COMPLETED"
    candidate_id = report["model_candidate"]

    # Test get_lineage & verify_integrity
    lineage = orchestrator.lineage_tracker.get_lineage(candidate_id)
    assert lineage is not None
    is_valid = orchestrator.lineage_tracker.verify_integrity(candidate_id)
    assert is_valid is True

    d = lineage.to_dict()
    assert "model_version_id" in d
    assert "dataset_version_id" in d
    assert "sample_count" in d
    assert "sample_ids" in d
    assert "synthetic_transforms_applied" in d
    assert "validation_metrics" in d
    assert "shadow_agreement_score" in d
    assert "manifest_hash" in d
    assert len(d["manifest_hash"]) == 64

    # Full graph contract
    graph = orchestrator.lineage_tracker.get_full_graph()
    assert len(graph) >= 1
    assert candidate_id in graph
    print(f"[OK] Cryptographic lineage contract: SHA-256 Digest = {d['manifest_hash'][:16]}... (Integrity Valid = {is_valid})")


def test_4_ui_schema_data_integrity():
    """Validates complete serialization of all dashboard payloads matching frontend UI expectations."""
    orchestrator = get_learning_orchestrator()
    status_payload = orchestrator.get_status()
    graph_payload = orchestrator.lineage_tracker.get_full_graph()

    # Ensure no NaN or infinite values
    status_json = json.dumps(status_payload)
    graph_json = json.dumps(graph_payload)
    assert "NaN" not in status_json
    assert "Infinity" not in status_json
    assert "NaN" not in graph_json
    assert "Infinity" not in graph_json
    print("[OK] UI schema integrity: Clean JSON structures with zero NaN/Infinity values.")


if __name__ == "__main__":
    print("\n=======================================================")
    print("PROJECT GARUDA — MILESTONE 12 DASHBOARD & OBSERVABILITY")
    print("=======================================================")
    test_1_orchestrator_status_contract()
    test_2_explainability_attribution_contract()
    test_3_lineage_graph_contract()
    test_4_ui_schema_data_integrity()
    print("\n=======================================================")
    print("ALL 4 MILESTONE 12 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=======================================================\n")
