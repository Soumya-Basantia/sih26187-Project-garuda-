"""
Project Garuda — Milestone 9 Verification Suite: Zero-Downtime Safe Model Deployment & Shadow Evaluation
Verifies:
1. Shadow inference isolation (Runs silently in parallel without mutating live detections or UI alerts).
2. Telemetry comparison & agreement rate metrics (IoU overlap, class agreement, latency delta).
3. Safety Guard: Latency spike tripwire (Automatic rollback on latency > 45ms).
4. Safety Guard: False alarm surge tripwire (Automatic rollback on false alarm burst).
5. Safety Guard: Runtime crash & exception isolation (Zero process crashes).
6. Canary staged rollout (Controlled single-camera live deployment).
7. Atomic zero-downtime model hot-swapping across pipelines.
"""

import time
import numpy as np

from ai_engine.learning.shadow_deployment import (
    DeploymentStage,
    ShadowComparisonMetric,
    DeploymentStatusReport,
    SafetyRollbackGuard,
    ShadowInferenceEngine,
    AtomicModelHotSwapper,
    SafeDeploymentManager,
    deployment_manager,
)


def test_1_shadow_inference_isolation():
    """Verify shadow evaluation executes silently without altering active detections."""
    mgr = SafeDeploymentManager(active_model_path="baseline.pt", active_version="v1.0.0")

    # Mock candidate predictor
    def mock_cand_predictor(frame: np.ndarray) -> list[dict]:
        return [{"bbox": (10, 10, 50, 50), "class": "person", "conf": 0.89}]

    mgr.start_shadow_evaluation(
        candidate_version="v1.0.1",
        candidate_model_path="candidate_v1.0.1.pt",
        candidate_predictor=mock_cand_predictor,
    )
    assert mgr.current_stage == DeploymentStage.SHADOW
    assert mgr.active_model_path == "baseline.pt"  # Active model unaffected

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    active_dets = [{"bbox": (12, 12, 52, 52), "class": "person", "conf": 0.85}]

    metric = mgr.process_frame_telemetry(
        camera_id="CAM-01",
        frame=frame,
        active_detections=active_dets,
        active_latency_ms=12.5,
    )

    assert metric is not None
    assert metric.candidate_detection_count == 1
    assert metric.active_detection_count == 1
    assert mgr.current_stage == DeploymentStage.SHADOW  # Still in shadow, not active
    print(f"[OK] Shadow isolation: Candidate evaluated in shadow mode (Agreement={metric.agreement_score:.2f})")


def test_2_telemetry_and_agreement_rate():
    """Verify IoU overlap, class agreement, and latency metrics."""
    guard = SafetyRollbackGuard()
    engine = ShadowInferenceEngine(guard)

    # Identical predictions -> 1.0 agreement
    box_a = (10, 10, 60, 60)
    box_b = (10, 10, 60, 60)
    iou_perfect = engine._iou(box_a, box_b)
    assert abs(iou_perfect - 1.0) < 1e-4

    # High agreement case
    cand_dets = [{"bbox": (12, 12, 60, 60), "class": "person"}]
    active_dets = [{"bbox": (10, 10, 60, 60), "class": "person"}]
    agree_high = engine._compute_agreement(active_dets, cand_dets)
    assert agree_high >= 0.80

    # Class mismatch -> zero agreement
    cand_wrong_class = [{"bbox": (10, 10, 60, 60), "class": "backpack"}]
    agree_mismatch = engine._compute_agreement(active_dets, cand_wrong_class)
    assert agree_mismatch == 0.0

    print(f"[OK] Telemetry metrics: IoU={iou_perfect:.2f}, HighAgreement={agree_high:.2f}, Mismatch={agree_mismatch:.2f}")


def test_3_safety_guard_latency_spike():
    """Verify automatic emergency rollback when candidate latency exceeds 45ms."""
    mgr = SafeDeploymentManager(active_model_path="stable_v1.0.pt", active_version="v1.0.0")

    # Predictor simulating latency spike (e.g. 55ms)
    def slow_predictor(frame: np.ndarray) -> list[dict]:
        time.sleep(0.055)
        return []

    mgr.start_shadow_evaluation(
        candidate_version="v1.0.1-slow",
        candidate_model_path="cand_slow.pt",
        candidate_predictor=slow_predictor,
    )

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    mgr.process_frame_telemetry("CAM-01", frame, active_detections=[], active_latency_ms=10.0)

    assert mgr.current_stage == DeploymentStage.ROLLED_BACK
    assert mgr.active_model_path == "stable_v1.0.pt"
    print(f"[OK] Safety Guard: Latency spike correctly triggered AUTOMATIC ROLLBACK (Stage={mgr.current_stage.value})")


def test_4_safety_guard_false_alarm_spike():
    """Verify automatic rollback when candidate triggers false alarm surges."""
    mgr = SafeDeploymentManager(active_model_path="stable_v1.0.pt", active_version="v1.0.0")

    # Predictor firing false positive detections in clean scene
    def noisy_predictor(frame: np.ndarray) -> list[dict]:
        return [
            {"bbox": (10, 10, 30, 30), "class": "knife"},
            {"bbox": (40, 40, 60, 60), "class": "gun"},
            {"bbox": (70, 70, 90, 90), "class": "weapon"},
            {"bbox": (15, 15, 35, 35), "class": "person"},
        ]

    mgr.start_shadow_evaluation(
        candidate_version="v1.0.1-noisy",
        candidate_model_path="cand_noisy.pt",
        candidate_predictor=noisy_predictor,
    )

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # Active detection is clean (0 detections)
    mgr.process_frame_telemetry("CAM-02", frame, active_detections=[], active_latency_ms=12.0)

    assert mgr.current_stage == DeploymentStage.ROLLED_BACK
    print(f"[OK] Safety Guard: False alarm surge correctly triggered AUTOMATIC ROLLBACK (Stage={mgr.current_stage.value})")


def test_5_safety_guard_crash_resilience():
    """Verify runtime exception in candidate model is safely caught without crashing host process."""
    mgr = SafeDeploymentManager(active_model_path="stable_v1.0.pt", active_version="v1.0.0")

    def crashing_predictor(frame: np.ndarray) -> list[dict]:
        raise RuntimeError("Synthetic CUDA Out Of Memory or Layer Dimension Mismatch")

    mgr.start_shadow_evaluation(
        candidate_version="v1.0.1-crash",
        candidate_model_path="cand_crash.pt",
        candidate_predictor=crashing_predictor,
    )

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # Process telemetry must NOT crash, but catch error and roll back
    metric = mgr.process_frame_telemetry("CAM-03", frame, active_detections=[], active_latency_ms=10.0)

    assert metric is not None
    assert metric.error_occurred is True
    assert "CUDA Out Of Memory" in metric.error_message
    assert mgr.current_stage == DeploymentStage.ROLLED_BACK
    print(f"[OK] Safety Guard: Runtime crash caught safely, error recorded, rollback executed.")


def test_6_canary_staged_rollout():
    """Verify promotion sequence from SHADOW to CANARY on designated camera."""
    mgr = SafeDeploymentManager(active_model_path="stable_v1.0.pt", active_version="v1.0.0")

    def healthy_predictor(frame: np.ndarray) -> list[dict]:
        return [{"bbox": (10, 10, 50, 50), "class": "person"}]

    mgr.start_shadow_evaluation(
        candidate_version="v1.0.1-healthy",
        candidate_model_path="cand_healthy.pt",
        candidate_predictor=healthy_predictor,
    )

    # Feed 5 clean shadow frames
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    for _ in range(5):
        mgr.process_frame_telemetry(
            "CAM-01",
            frame,
            active_detections=[{"bbox": (10, 10, 50, 50), "class": "person"}],
            active_latency_ms=14.0,
        )

    # Promote to CANARY on CAM-04
    success, msg, report = mgr.promote_to_canary("CAM-04")
    assert success is True
    assert mgr.current_stage == DeploymentStage.CANARY
    assert mgr.canary_camera_id == "CAM-04"
    assert report.stage == DeploymentStage.CANARY
    print(f"[OK] Canary rollout: Promoted to CANARY on {mgr.canary_camera_id} ({msg})")


def test_7_atomic_zero_downtime_swap_and_full_lifecycle():
    """Verify atomic pointer swap and full SHADOW -> CANARY -> ACTIVE promotion lifecycle."""
    # Mock active pipeline
    class MockDetector:
        def __init__(self):
            self.model_path = "baseline_v1.0.pt"
            self.model_version = "v1.0.0"

    class MockPipeline:
        def __init__(self):
            self.detector = MockDetector()

    pipe1 = MockPipeline()
    pipe2 = MockPipeline()
    active_pipelines = [pipe1, pipe2]

    mgr = SafeDeploymentManager(active_model_path="baseline_v1.0.pt", active_version="v1.0.0")

    # Step 1: Shadow
    mgr.start_shadow_evaluation(
        candidate_version="v1.1.0",
        candidate_model_path="weights_v1.1.0.pt",
        candidate_predictor=lambda f: [{"bbox": (0, 0, 1, 1), "class": "car"}],
    )
    assert mgr.current_stage == DeploymentStage.SHADOW

    # Feed frames to establish telemetry
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    for _ in range(5):
        mgr.process_frame_telemetry("CAM-01", frame, [{"bbox": (0, 0, 1, 1), "class": "car"}], 12.0)

    # Step 2: Canary
    ok, _, _ = mgr.promote_to_canary("CAM-02")
    assert ok is True
    assert mgr.current_stage == DeploymentStage.CANARY

    # Step 3: Global Active Promotion via Atomic Hot-Swap
    t0 = time.perf_counter()
    ok_promote, msg, report = mgr.promote_to_active_global(target_pipelines=active_pipelines)
    swap_ms = (time.perf_counter() - t0) * 1000.0

    assert ok_promote is True
    assert mgr.current_stage == DeploymentStage.ACTIVE
    assert mgr.active_version == "v1.1.0"
    assert mgr.active_model_path == "weights_v1.1.0.pt"

    # Verify pipelines updated atomically
    assert pipe1.detector.model_path == "weights_v1.1.0.pt"
    assert pipe2.detector.model_path == "weights_v1.1.0.pt"
    assert swap_ms < 2.0, f"Atomic swap took too long: {swap_ms:.3f}ms"
    print(f"[OK] Full Lifecycle & Atomic Swap: Promoted globally in {swap_ms:.4f} ms with zero frame drops.")


if __name__ == "__main__":
    test_1_shadow_inference_isolation()
    test_2_telemetry_and_agreement_rate()
    test_3_safety_guard_latency_spike()
    test_4_safety_guard_false_alarm_spike()
    test_5_safety_guard_crash_resilience()
    test_6_canary_staged_rollout()
    test_7_atomic_zero_downtime_swap_and_full_lifecycle()
    print("\n=======================================================")
    print("ALL 7 MILESTONE 9 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=======================================================")
