"""
Project Garuda — Milestone 2: Confidence Calibration & Active Learning Verification Test Suite
Verifies:
1. Multi-head confidence scoring functions:
   - Shannon Entropy (high on ambiguous detections, low on confident detections).
   - Class margin between top-2 classes.
   - Track bounding box stability & jitter calculation.
   - Sudden confidence drop detection on tracked targets.
2. Camera-specific confidence calibration:
   - Temperature scaling per camera node.
   - Ambient lighting adjustment factors (Daylight, Low-Light, Glare).
3. Multi-criterion Sample Selection Policy:
   - Uncertainty range boundary sampling.
   - Sudden confidence drops triggering tracking failure pseudo-labels.
   - Class ambiguity triggering active learning.
   - Critical threat exemplars (weapons).
4. Asynchronous disk storage pipeline & zero FPS impact:
   - Bounding box crop, full frame, metadata JSON, and 64-dim visual descriptor.
   - Integration with LearningMemoryManager as canonical LearningSample.
"""

import os
import sys
import time
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from ai_engine.learning.confidence_calibrator import (
    compute_entropy,
    compute_class_margin,
    compute_bbox_iou,
    compute_bbox_stability,
    detect_confidence_drop,
    CameraCalibrator,
    SampleSelectionPolicy,
)
from ai_engine.learning.active_learner import (
    ActiveLearningHarvester,
    TriggerType,
    SampleLabel,
)
from ai_engine.learning.data_foundation import SelectionReason, ValidationStatus
from ai_engine.learning.memory_manager import memory_manager
from ai_engine.detection.detector import Detection


def test_confidence_scoring_functions():
    print("[TEST 1] Testing multi-criterion confidence scoring functions...")
    # Entropy: p=0.5 -> max uncertainty (1.0), p=0.95 -> low uncertainty (< 0.3)
    ent_high = compute_entropy(0.50)
    ent_low = compute_entropy(0.95)
    assert ent_high > 0.95, f"Expected high entropy near 0.5, got {ent_high}"
    assert ent_low < 0.35, f"Expected low entropy near 0.95, got {ent_low}"

    # Class margin
    margin_ambiguous = compute_class_margin(0.48, 0.44)
    margin_clear = compute_class_margin(0.90, 0.10)
    assert abs(margin_ambiguous - 0.04) < 1e-4
    assert abs(margin_clear - 0.80) < 1e-4

    # Bbox stability
    stable_boxes = [
        (100.0, 100.0, 200.0, 200.0),
        (102.0, 101.0, 202.0, 201.0),
        (104.0, 102.0, 204.0, 202.0),
    ]
    jitter_boxes = [
        (100.0, 100.0, 200.0, 200.0),
        (140.0, 150.0, 240.0, 250.0),
        (80.0, 70.0, 180.0, 170.0),
    ]
    stab_high = compute_bbox_stability(stable_boxes)
    stab_low = compute_bbox_stability(jitter_boxes)
    assert stab_high > 0.85, f"Expected high stability, got {stab_high}"
    assert stab_low < 0.55, f"Expected low stability on jitter, got {stab_low}"

    # Sudden confidence drop
    conf_steady = [0.80, 0.82, 0.79, 0.81]
    conf_dropped = [0.85, 0.82, 0.80, 0.45]
    has_drop_false, _ = detect_confidence_drop(conf_steady, drop_threshold=0.25)
    has_drop_true, drop_val = detect_confidence_drop(conf_dropped, drop_threshold=0.25)
    assert not has_drop_false, "Steady track should not report confidence drop"
    assert has_drop_true, "Drop from 0.85 to 0.45 must trigger confidence drop"
    assert drop_val >= 0.35
    print("  -> Passed: Entropy, class margin, bbox stability, and confidence drop functions verified.")


def test_camera_confidence_calibration():
    print("[TEST 2] Testing camera-specific confidence calibration (temperature & ambient)...")
    cal = CameraCalibrator(camera_id="CAM-T1", temperature=1.0)

    # 1. Neutral calibration in daylight
    p_neutral = cal.calibrate(0.70, lighting_condition="DAYLIGHT")
    assert abs(p_neutral - 0.70) < 0.02

    # 2. Temperature scaling: softening overconfidence with T=1.5
    cal.temperature = 1.5
    p_softened = cal.calibrate(0.85, lighting_condition="DAYLIGHT")
    assert p_softened < 0.85, f"T=1.5 should soften extreme confidence: {p_softened}"

    # 3. Ambient lighting adjustment: LOW_LIGHT and GLARE scaling
    cal.temperature = 1.0
    p_day = cal.calibrate(0.60, lighting_condition="DAYLIGHT")
    p_night = cal.calibrate(0.60, lighting_condition="LOW_LIGHT")
    p_glare = cal.calibrate(0.60, lighting_condition="GLARE")
    assert p_night < p_day, "LOW_LIGHT should down-weight raw detection confidence"
    assert p_glare < p_day, "GLARE should down-weight raw detection confidence"
    print(f"  -> Passed: Calibrator adjusted: Day={p_day:.2f}, Low-Light={p_night:.2f}, Glare={p_glare:.2f}")


def test_multi_criterion_selection_policy():
    print("[TEST 3] Testing multi-criterion active learning selection policy...")
    policy = SampleSelectionPolicy(
        uncertainty_min=0.28,
        uncertainty_max=0.58,
        margin_threshold=0.15,
        confidence_drop_threshold=0.25,
    )

    # Criteria A: Decision boundary uncertainty (0.42)
    h_a, r_a, _ = policy.evaluate(confidence=0.42, object_type="person")
    assert h_a is True
    assert r_a == SelectionReason.UNCERTAIN_DETECTION

    # Criteria B: High-confidence non-threat (0.88) -> Should NOT harvest
    h_b, r_b, _ = policy.evaluate(confidence=0.88, object_type="person")
    assert h_b is False

    # Criteria C: Sudden confidence drop on established track
    h_c, r_c, tel_c = policy.evaluate(
        confidence=0.48,
        object_type="person",
        track_id=12,
        conf_history=[0.82, 0.80, 0.79, 0.78, 0.48],
    )
    assert h_c is True
    assert r_c == SelectionReason.TRACKING_FAILURE
    assert tel_c["policy_rule"] == "SUDDEN_TRACK_CONF_DROP"

    # Criteria D: Class margin ambiguity (person 0.50 vs backpack 0.44)
    h_d, r_d, tel_d = policy.evaluate(
        confidence=0.50,
        object_type="person",
        top2_confidence=0.44,
    )
    assert h_d is True
    assert tel_d["policy_rule"] == "LOW_CLASS_MARGIN_AMBIGUITY"

    # Criteria E: Critical threat override (weapon)
    h_e, r_e, _ = policy.evaluate(confidence=0.92, object_type="gun")
    assert h_e is True
    assert r_e == SelectionReason.HIGH_RISK_ANOMALY
    print("  -> Passed: Multi-criterion selection policy triggers all expected active learning conditions.")


def test_storage_pipeline_and_memory_manager_integration():
    print("[TEST 4] Testing storage pipeline & LearningMemoryManager integration...")
    sample_dir = "./data/active_learning/test_samples"
    harvester = ActiveLearningHarvester(
        uncertainty_min=0.28,
        uncertainty_max=0.58,
        sample_dir=sample_dir,
    )

    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    dummy_frame[100:300, 100:200] = (180, 180, 180)

    # Harvest an ambiguous detection
    det = Detection(label="person", confidence=0.44, bbox=(100, 100, 200, 300), class_id=0)
    sample = harvester.consider_detection(
        camera_id="CAM-TEST",
        frame=dummy_frame,
        obj=det,
        track_history_len=6,
        lighting_condition="DAYLIGHT",
    )
    assert sample is not None, "Candidate must qualify for harvesting"
    assert sample.embedding_ref is not None and len(sample.embedding_ref) == 64
    assert sample.snapshot_data is not None
    assert "entropy" in sample.telemetry

    # Verify canonical LearningSample was registered in memory_manager
    stored_ls = memory_manager.get_sample(sample.sample_id)
    assert stored_ls is not None, f"Sample {sample.sample_id} must exist in LearningMemoryManager"
    assert stored_ls.confidence == sample.confidence
    assert stored_ls.object_type == "person"
    assert stored_ls.validation_status == ValidationStatus.PENDING_REVIEW
    assert len(stored_ls.embedding_ref) == 64

    # Wait for async background disk writer to flush
    time.sleep(0.5)
    crop_disk_path = os.path.join(harvester.crops_dir, f"{sample.sample_id}_crop.jpg")
    meta_disk_path = os.path.join(harvester.metadata_dir, f"{sample.sample_id}_meta.json")

    assert os.path.exists(crop_disk_path), f"Crop file missing: {crop_disk_path}"
    assert os.path.exists(meta_disk_path), f"Metadata file missing: {meta_disk_path}"
    print(f"  -> Passed: Sample {sample.sample_id} persisted with 64-dim visual descriptor and disk artifacts.")


def test_zero_fps_impact_latency():
    print("[TEST 5] Testing inference latency / zero FPS drop benchmark...")
    harvester = ActiveLearningHarvester(sample_dir="./data/active_learning/test_samples")
    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    dummy_frame[100:300, 100:200] = (180, 180, 180)
    det = Detection(label="person", confidence=0.45, bbox=(100, 100, 200, 200), class_id=0)

    # Warmup call
    harvester._last_camera_harvest["CAM-BENCH"] = 0.0
    harvester.consider_detection("CAM-BENCH", dummy_frame, det, track_history_len=4)

    # Benchmark 20 consideration calls
    t0 = time.perf_counter()
    for i in range(20):
        harvester._last_camera_harvest["CAM-BENCH"] = 0.0  # reset rate limit
        harvester.consider_detection("CAM-BENCH", dummy_frame, det, track_history_len=4)
    elapsed_ms = (time.perf_counter() - t0) * 1000 / 20

    print(f"  -> Average consider_detection latency: {elapsed_ms:.2f} ms per call")
    assert elapsed_ms < 10.0, f"Harvester latency too high: {elapsed_ms:.2f} ms (must be < 10ms to prevent FPS drops)"
    print("  -> Passed: Harvester execution satisfies real-time zero FPS impact constraints.")


if __name__ == "__main__":
    print("=" * 70)
    print("PROJECT GARUDA — MILESTONE 2 VERIFICATION TEST SUITE")
    print("=" * 70)
    test_confidence_scoring_functions()
    test_camera_confidence_calibration()
    test_multi_criterion_selection_policy()
    test_storage_pipeline_and_memory_manager_integration()
    test_zero_fps_impact_latency()
    print("=" * 70)
    print("ALL MILESTONE 2 ACTIVE LEARNING TESTS PASSED (100% SUCCESS)!")
    print("=" * 70)
