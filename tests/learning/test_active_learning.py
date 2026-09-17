"""
Comprehensive verification test for Project Garuda's Self-Training AI Engine.
Tests:
1. Active Learning Harvester (Uncertainty sampling & hard-sample mining)
2. Operator Reinforcement Learning (1-Click RLHF)
3. Dynamic Camera Sensitivity Auto-Calibration
4. Background Self-Training worker & Checkpoint versioning
5. Zero-downtime hot-reload & baseline rollback
"""

import os
import sys
import time
import numpy as np

# Add project root and backend to path
project_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.join(project_root, "backend"))

from ai_engine.learning.active_learner import ActiveLearningHarvester, TriggerType, SampleLabel
from ai_engine.learning.self_trainer import SelfTrainingEngine
from ai_engine.learning.adaptive_filter import AdaptiveNegativeFilter, extract_visual_descriptor, cosine_similarity
from ai_engine.detection.detector import Detection

def test_active_learning():
    print("==================================================================")
    print("TESTING PROJECT GARUDA SELF-TRAINING & ACTIVE LEARNING ENGINE")
    print("==================================================================")

    # 1. Initialize ActiveLearningHarvester
    harvested = []
    def on_harvest(sample):
        harvested.append(sample)

    harvester = ActiveLearningHarvester(
        uncertainty_min=0.28,
        uncertainty_max=0.58,
        on_sample_harvested=on_harvest
    )

    dummy_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    dummy_frame[100:300, 100:200] = (150, 150, 150)

    # Test 1A: High confidence normal detection (> 0.85) -> should NOT be harvested as uncertain
    high_conf_det = Detection(label="person", confidence=0.92, bbox=(100, 100, 200, 300), class_id=0)
    sample_none = harvester.consider_detection("CAM-01", dummy_frame, high_conf_det, track_history_len=5)
    assert sample_none is None, "High confidence person detection should not trigger uncertainty harvesting"
    print("[OK] Test 1A Passed: High-confidence non-critical detections bypass harvester.")

    # Test 1B: Borderline detection (conf = 0.42) -> SHOULD be harvested
    uncertain_det = Detection(label="person", confidence=0.42, bbox=(100, 100, 200, 300), class_id=0)
    harvester._last_camera_harvest["CAM-01"] = 0.0
    sample_uncertain = harvester.consider_detection("CAM-01", dummy_frame, uncertain_det, track_history_len=5)
    assert sample_uncertain is not None, "Borderline detection must be harvested"
    assert sample_uncertain.trigger_type == TriggerType.UNCERTAIN_DETECTION
    assert sample_uncertain.sample_label == SampleLabel.BORDERLINE_UNCERTAIN
    assert sample_uncertain.snapshot_data is not None
    print(f"[OK] Test 1B Passed: Borderline sample harvested ({sample_uncertain.sample_id}, conf={sample_uncertain.confidence}).")

    # Test 1C: High-Risk Critical Anomaly Detection (e.g. Weapon) -> SHOULD be harvested for tactical reinforcement
    weapon_det = Detection(label="knife", confidence=0.88, bbox=(120, 120, 210, 290), class_id=43)
    harvester._last_camera_harvest["CAM-01"] = 0.0
    sample_weapon = harvester.consider_detection("CAM-01", dummy_frame, weapon_det, track_history_len=5)
    assert sample_weapon is not None, "Critical weapon threat must be harvested for tactical model reinforcement"
    assert sample_weapon.trigger_type == TriggerType.HIGH_RISK_ANOMALY
    assert sample_weapon.sample_label == SampleLabel.POSITIVE_CONFIRMED
    print(f"[OK] Test 1C Passed: High-Risk Anomaly harvested ({sample_weapon.sample_id}, label={sample_weapon.class_label}).")

    # Test 2: Operator Feedback Reinforcement (1-Click RLHF)
    fb_false_alarm = harvester.record_operator_feedback(
        camera_id="CAM-02",
        frame=dummy_frame,
        snapshot_data=None,
        alert_id="alert_test_99",
        is_false_alarm=True,
        notes="Foliage motion mistaken for person",
    )
    assert fb_false_alarm.trigger_type == TriggerType.OPERATOR_FALSE_ALARM
    assert fb_false_alarm.reinforcement_score == -1.0
    print("[OK] Test 2A Passed: Operator False Alarm negative reinforcement recorded (-1.0).")

    fb_confirmed = harvester.record_operator_feedback(
        camera_id="CAM-01",
        frame=dummy_frame,
        snapshot_data=None,
        alert_id="alert_test_100",
        is_false_alarm=False,
        notes="Verified intruder perimeter scaling",
    )
    assert fb_confirmed.trigger_type == TriggerType.OPERATOR_CONFIRMED
    assert fb_confirmed.reinforcement_score == 1.0
    print("[OK] Test 2B Passed: Operator Confirmed positive reinforcement recorded (+1.0).")

    # Test 3: Online Adaptive Negative Filter & Spatial Bayesian Prior
    adaptive_filter = AdaptiveNegativeFilter(similarity_threshold=0.80)
    crop_false_alarm = dummy_frame[100:250, 100:200]
    exemplar = adaptive_filter.register_negative_exemplar(
        camera_id="CAM-02",
        crop=crop_false_alarm,
        bbox=(100, 100, 200, 250),
        frame_shape=dummy_frame.shape[:2],
        class_label="person",
        alert_id="alert_test_99",
        notes="Branch fluttering in wind",
    )
    assert exemplar is not None
    assert len(exemplar.descriptor) == 64
    print("[OK] Test 3A Passed: Negative Exemplar 64-dim visual descriptor successfully registered.")

    # Check suppression on recurring identical detection in same sector
    is_suppressed, adj_conf, reason = adaptive_filter.check_suppression(
        camera_id="CAM-02",
        frame=dummy_frame,
        bbox=(100, 100, 200, 250),
        confidence=0.45,
        class_label="person",
    )
    assert is_suppressed is True, "Recurring false alarm in same sector must be suppressed"
    assert adj_conf < 0.45, "Suppression must discount confidence below alert threshold"
    print(f"[OK] Test 3B Passed: Real-time suppression active (adj_conf={adj_conf:.2f}, reason={reason}).")

    # Check that detection in a different sector is NOT suppressed
    is_suppressed_other, adj_conf_other, _ = adaptive_filter.check_suppression(
        camera_id="CAM-02",
        frame=dummy_frame,
        bbox=(450, 300, 550, 450),
        confidence=0.75,
        class_label="person",
    )
    assert is_suppressed_other is False, "Detection in a clean corridor sector must not be falsely suppressed"
    print("[OK] Test 3C Passed: Spatial gating protects clean sectors from false suppression.")

    # Test 4: Dynamic Camera Sensitivity Auto-Calibration
    reloaded_models = []
    def on_hot_reload(path):
        reloaded_models.append(path)

    trainer = SelfTrainingEngine(
        baseline_model_path="yolov8n.pt",
        checkpoints_dir="./data/models/checkpoints",
        on_hot_reload=on_hot_reload,
        adaptive_filter=adaptive_filter,
    )

    camera_stats = {
        "CAM-01": {"false_positives": 0, "total_events": 15, "ambient_noise": 0.8},
        "CAM-02": {"false_positives": 4, "total_events": 10, "ambient_noise": 3.2},
    }
    profiles = trainer.auto_calibrate_all(camera_stats)
    assert profiles["CAM-01"]["status"] == "OPTIMAL"
    assert profiles["CAM-01"]["adapted_confidence"] == 0.25
    assert profiles["CAM-02"]["status"] == "NOISE_SUPPRESSED"
    assert profiles["CAM-02"]["adapted_confidence"] > 0.30
    assert profiles["CAM-02"]["persistence_frames"] > 3
    print(f"[OK] Test 4 Passed: Dynamic auto-tuning successfully elevated CAM-02 threshold to {profiles['CAM-02']['adapted_confidence']} (status: {profiles['CAM-02']['status']}).")

    # Test 5: Background Self-Training Cycle & Progress Hook
    samples_for_training = [s.to_dict() for s in harvester.get_recent_samples(limit=10)]
    completed_checkpoints = []
    progress_updates = []

    def on_train_done(chk):
        completed_checkpoints.append(chk)

    def on_progress(p):
        progress_updates.append(p)

    success = trainer.start_training_cycle_async(
        samples_for_training, on_complete=on_train_done, on_progress=on_progress
    )
    assert success is True, "Background self-training worker must launch asynchronously"
    assert trainer.is_training() is True, "Training state must be active"
    print("[OK] Test 5A Passed: Background self-training worker started with progress tracking.")

    # Wait for completion (simulated adaptation takes ~2.5s)
    wait_time = 0
    while trainer.is_training() and wait_time < 10:
        time.sleep(0.4)
        wait_time += 0.4

    assert trainer.is_training() is False, "Training should finish cleanly"
    assert len(completed_checkpoints) == 1, "New checkpoint must be emitted"
    assert len(progress_updates) > 0, "Progress updates must be triggered"
    new_chk = completed_checkpoints[0]
    print(f"[OK] Test 5B Passed: New checkpoint generated: {new_chk.version} (+{new_chk.accuracy_gain}% acc, -{new_chk.false_alarm_reduction}% FA drop).")
    assert len(reloaded_models) > 0, "Model hot-reload hook must be called"
    print(f"[OK] Test 5C Passed: Zero-downtime hot-reload triggered with model {reloaded_models[-1]}.")

    # Test 6: Model Rollback
    rollback_chk = trainer.rollback_to_baseline()
    assert rollback_chk.version == "v1.0.0", "Rollback must restore baseline v1.0.0"
    assert trainer.current_active_version == "Garuda-Vision-v1.0.0 (Baseline)"
    print("[OK] Test 6 Passed: Safety rollback successfully restored baseline factory weights.")

    summary = trainer.get_summary()
    assert "adaptive_filter" in summary
    assert summary["adaptive_filter"]["total_negative_exemplars"] >= 1
    print("[OK] Test 7 Passed: Adaptive filter statistics correctly embedded in engine summary.")

    print("==================================================================")
    print("ALL SELF-TRAINING & ADAPTIVE LEARNING TESTS PASSED (100% SUCCESS)!")
    print("==================================================================")

if __name__ == "__main__":
    test_active_learning()
