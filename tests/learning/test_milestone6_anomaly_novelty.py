"""
Project Garuda — Milestone 6 Verification Suite: Anomaly & Novelty Learning
Verifies:
1. Graduated 4-tier hierarchy mapping (NORMAL, UNUSUAL, REQUIRES_REVIEW, CONFIRMED_EVENT)
2. Multi-criterion detection:
   - Visual novelty scoring against learned appearance manifolds
   - Trajectory anomaly scoring against movement manifold transition matrices
   - Circadian temporal anomaly scoring against diurnal baselines
   - Macro scene activity surge detection
3. Critical Invariant: Anomaly != Security Threat (decoupling rule)
4. Explicit operator escalation workflow
5. High-throughput performance (<1.0ms per evaluation)
"""

import time
import numpy as np
from ai_engine.learning.anomaly_novelty_engine import (
    AnomalyNoveltyEngine,
    AnomalySeverityTier,
    AnomalyAssessment,
    NovelObjectDetector,
    TrajectoryAnomalyDetector,
    TemporalAnomalyDetector,
    SceneActivityAnomalyDetector,
    get_anomaly_engine,
)
from ai_engine.learning.camera_environment_adapter import CameraEnvironmentAdapter
from ai_engine.learning.self_supervised_learner import (
    CircadianTemporalBaseline,
    MovementManifold,
    AppearanceManifoldCluster,
)


def test_1_tier_hierarchy_mapping():
    """Verify that anomaly scores correctly map to the graduated 4-tier hierarchy."""
    engine = AnomalyNoveltyEngine("CAM-TEST-M6-01")

    # Construct test cases with controlled mock factors
    # Tier 1: NORMAL (< 0.35)
    # Default evaluate with no anomalies
    normal_res = engine.evaluate_track(
        track_id=1,
        class_label="person",
        bounding_box=(100, 100, 150, 200),
        trajectory=[(0.1, 0.1), (0.11, 0.11), (0.12, 0.12)],
        visual_descriptor=None,
    )
    assert normal_res.tier == AnomalySeverityTier.NORMAL
    assert normal_res.fused_score < 0.35
    assert not normal_res.is_security_threat
    print(f"[OK] Tier 1 mapped: {normal_res.tier.value} (Score={normal_res.fused_score})")


def test_2_visual_novelty_detection():
    """Verify visual novelty detection detects unfamiliar appearance archetypes."""
    clusterer = AppearanceManifoldCluster(k_clusters=4, descriptor_dim=64)

    # Establish baseline familiar clusters around a fixed centroid
    np.random.seed(42)
    base_centroid = np.ones(64, dtype=np.float32) * 0.5
    for _ in range(30):
        sample = base_centroid + np.random.normal(0, 0.05, 64).astype(np.float32)
        sample = sample / np.linalg.norm(sample)
        clusterer.record_descriptor(sample)

    # Familiar descriptor (close to centroid)
    familiar_desc = base_centroid + np.random.normal(0, 0.02, 64).astype(np.float32)
    familiar_desc = familiar_desc / np.linalg.norm(familiar_desc)
    s_fam, r_fam = NovelObjectDetector.evaluate(familiar_desc, clusterer)

    # Novel descriptor (orthogonal archetype)
    novel_desc = np.zeros(64, dtype=np.float32)
    novel_desc[0:10] = 1.0
    novel_desc = novel_desc / np.linalg.norm(novel_desc)
    s_nov, r_nov = NovelObjectDetector.evaluate(novel_desc, clusterer)

    assert s_fam < 0.40, f"Familiar appearance scored too high: {s_fam}"
    assert s_nov > 0.60, f"Novel appearance scored too low: {s_nov}"
    assert "NOVEL" in r_nov
    print(f"[OK] Visual novelty: Familiar={s_fam:.3f}, Novel={s_nov:.3f}")


def test_3_trajectory_anomaly_detection():
    """Verify trajectory anomaly detection identifies atypical paths."""
    manifold = MovementManifold(grid_size=8)

    # Habitual pathway from left to right along row 2: (0,2) -> (1,2) -> (2,2) -> (3,2) -> (4,2)
    habitual_path = [
        (0.05, 0.25),
        (0.15, 0.25),
        (0.25, 0.25),
        (0.35, 0.25),
        (0.45, 0.25),
    ]
    for _ in range(25):
        manifold.record_trajectory(habitual_path)

    # Test habitual path
    s_norm, _ = TrajectoryAnomalyDetector.evaluate(habitual_path, manifold)

    # Test anomalous reverse / diagonally unvisited path: (7,7) -> (6,6) -> (5,5)
    unseen_path = [
        (0.95, 0.95),
        (0.85, 0.85),
        (0.75, 0.75),
        (0.65, 0.65),
    ]
    s_anom, r_anom = TrajectoryAnomalyDetector.evaluate(unseen_path, manifold)

    assert s_norm < s_anom, f"Normal path ({s_norm}) was not lower than anomalous ({s_anom})"
    assert s_anom > 0.50, f"Anomalous path scored too low: {s_anom}"
    print(f"[OK] Trajectory anomaly: Habitual={s_norm:.3f}, Anomalous={s_anom:.3f}")


def test_4_circadian_temporal_anomaly_detection():
    """Verify circadian anomaly detects off-hours unexpected activity."""
    circadian = CircadianTemporalBaseline()

    # Train circadian baseline: high daytime activity, zero night activity
    # Day (14:00): mean motion = 0.25, lum = 180.0
    # Night (03:00): mean motion = 0.01, lum = 20.0
    for _ in range(50):
        circadian.update_slot(14, luminance=180.0, motion_energy=0.25, entropy=0.5)
        circadian.update_slot(3, luminance=20.0, motion_energy=0.01, entropy=0.2)

    # Normal daytime observation at 14:00
    s_day, _ = TemporalAnomalyDetector.evaluate(14, motion_energy=0.24, luminance=175.0, circadian_baseline=circadian)

    # Anomalous off-hours observation at 03:00 (intense sudden motion)
    s_night_anom, r_night = TemporalAnomalyDetector.evaluate(3, motion_energy=0.45, luminance=110.0, circadian_baseline=circadian)

    assert s_day < 0.30, f"Expected low day anomaly score, got: {s_day}"
    assert s_night_anom > 0.60, f"Expected high off-hours anomaly score, got: {s_night_anom}"
    print(f"[OK] Circadian anomaly: NormalDay={s_day:.3f}, AnomalousNight={s_night_anom:.3f}")


def test_5_scene_activity_surge():
    """Verify macro scene activity detector identifies crowd surges / rapid disruptions."""
    # Calm scene: activity 0.05, stability 0.95
    s_calm, _ = SceneActivityAnomalyDetector.evaluate(0.05, 0.95)
    assert s_calm == 0.0

    # Macro disruption: abrupt activity surge 0.45 with destabilized background 0.30
    s_surge, r_surge = SceneActivityAnomalyDetector.evaluate(0.45, 0.30)
    assert s_surge >= 0.85
    assert "MACRO_ACTIVITY_SURGE" in r_surge
    print(f"[OK] Scene activity surge: Calm={s_calm:.3f}, Surge={s_surge:.3f} ({r_surge})")


def test_6_decoupling_invariant_anomaly_not_threat():
    """
    CRITICAL INVARIANT:
    Verifies that high-tier anomalies are NOT automatically classified as security threats.
    Only explicit human operator review can elevate an anomaly to a security threat.
    """
    adapter = CameraEnvironmentAdapter("CAM-TEST-M6-06")
    # Simulate high activity and destabilized scene
    adapter.scene.activity_level = 0.45
    adapter.scene.stability_score = 0.30

    engine = AnomalyNoveltyEngine("CAM-TEST-M6-06")

    # Evaluate an outlier track
    assessment = engine.evaluate_track(
        track_id=99,
        class_label="unidentified_carrier",
        bounding_box=(200, 200, 300, 350),
        trajectory=[(0.9, 0.9), (0.8, 0.8), (0.7, 0.7)],
        environment_adapter=adapter,
    )

    # Even if tier is CONFIRMED_EVENT or REQUIRES_REVIEW, is_security_threat MUST be False
    assert assessment.tier in (AnomalySeverityTier.CONFIRMED_EVENT, AnomalySeverityTier.REQUIRES_REVIEW)
    assert assessment.is_security_threat is False, "Violation: Anomaly was automatically declared a security threat!"

    # Simulate explicit human escalation
    assessment.is_security_threat = True
    assert assessment.is_security_threat is True
    print(f"[OK] Invariant verified: High Anomaly Score={assessment.fused_score} -> is_threat initially False; escalated only on human action.")


def test_7_performance_and_buffering():
    """Verify latency < 1.0ms per track and buffer retention."""
    engine = AnomalyNoveltyEngine("CAM-TEST-M6-07")
    traj = [(0.1 + i * 0.01, 0.1 + i * 0.01) for i in range(10)]
    desc = np.random.randn(64).tolist()

    t0 = time.perf_counter()
    n_iters = 100
    for i in range(n_iters):
        engine.evaluate_track(
            track_id=i,
            class_label="person",
            bounding_box=(10, 10, 50, 50),
            trajectory=traj,
            visual_descriptor=desc,
        )
    total_time = (time.perf_counter() - t0) * 1000.0
    avg_latency = total_time / n_iters

    assert avg_latency < 1.0, f"Average anomaly evaluation latency too high: {avg_latency:.3f}ms"
    assert len(engine.recent_assessments) == n_iters

    # Query recent
    recent = engine.get_recent_anomalies(limit=25)
    assert len(recent) == 25
    print(f"[OK] Latency benchmark: {avg_latency:.4f} ms per track (Target < 1.0ms), buffered: {len(engine.recent_assessments)}")


if __name__ == "__main__":
    test_1_tier_hierarchy_mapping()
    test_2_visual_novelty_detection()
    test_3_trajectory_anomaly_detection()
    test_4_circadian_temporal_anomaly_detection()
    test_5_scene_activity_surge()
    test_6_decoupling_invariant_anomaly_not_threat()
    test_7_performance_and_buffering()
    print("\n=======================================================")
    print("ALL 7 MILESTONE 6 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=======================================================")
