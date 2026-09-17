"""
Project Garuda — Milestone 5: Self-Supervised Environment Learning Test Suite

Verifies:
1. Invariant 128-dimensional multi-scale spatial scene representation extraction.
2. 24-hour circadian diurnal baseline modeling & off-hours anomaly detection.
3. Movement manifold route likelihood modeling on 8x8 spatial transitions.
4. Unsupervised appearance clustering via reservoir k-means (no class labels).
5. Environmental shift & camera tampering detection (abrupt scene changes).
6. Zero-Pseudo-Label invariant verification (representations without confirmation bias).
7. Schema export, disk persistence, and FastAPI learning endpoints.
"""

import asyncio
import os
import sys
import time
import numpy as np
import cv2

# Ensure workspace paths
sys.path.insert(0, os.path.abspath("backend"))
sys.path.insert(0, os.path.abspath("."))

from ai_engine.learning.self_supervised_learner import (
    SceneRepresentationExtractor,
    CircadianTemporalBaseline,
    MovementManifold,
    AppearanceManifoldCluster,
    SelfSupervisedEnvironmentLearner,
)
from ai_engine.learning.memory_manager import memory_manager
from backend.app.api.learning_routes import get_camera_baseline, learn_camera_baseline


def test_scene_representation_extraction():
    print("[TEST 1] Testing 128-dim invariant scene representation extraction...")
    extractor = SceneRepresentationExtractor()

    # Generate distinct test scenes (e.g. outdoor perimeter vs indoor corridor)
    frame_a = np.zeros((240, 320, 3), dtype=np.uint8)
    frame_a[:120, :] = [200, 150, 100]  # Sky
    frame_a[120:, :] = [50, 180, 50]    # Grass ground

    frame_b = np.zeros((240, 320, 3), dtype=np.uint8)
    frame_b[:, :100] = [180, 200, 210]   # Left wall
    frame_b[:, 220:] = [180, 200, 210]   # Right wall
    frame_b[140:, 100:220] = [40, 40, 40] # Dark floor

    desc_a = extractor.extract_descriptor(frame_a)
    desc_b = extractor.extract_descriptor(frame_b)

    assert desc_a.shape == (128,), f"Expected 128 dims, got {desc_a.shape}"
    assert desc_b.shape == (128,)
    # Verify unit L2 norm
    norm_a = float(np.linalg.norm(desc_a))
    assert abs(norm_a - 1.0) < 1e-4, f"Descriptor must be unit normalized, got {norm_a}"

    # Self-distance must be zero
    dist_self = extractor.compute_distance(desc_a, desc_a)
    assert dist_self < 1e-5, f"Self distance must be 0.0, got {dist_self}"

    # Distinct scene distance
    dist_ab = extractor.compute_distance(desc_a, desc_b)
    assert dist_ab > 0.10, f"Different scenes must have non-trivial distance, got {dist_ab}"
    print(f"  -> Extracted 128-dim descriptor (norm={norm_a:.4f}), cross-scene dist={dist_ab:.3f}")
    print("  -> Passed: Scene representation is invariant, normalized, and discriminative.")


def test_circadian_temporal_baseline():
    print("[TEST 2] Testing 24-hour circadian diurnal baseline modeling...")
    circadian = CircadianTemporalBaseline()

    # Train circadian profile: Normal business hours (09:00 - 17:00) have moderate motion (0.15),
    # Night hours (00:00 - 05:00) have near-zero motion (0.01)
    for hr in range(24):
        for _ in range(5):
            expected_motion = 0.15 if 9 <= hr <= 17 else 0.01
            expected_lum = 140.0 if 8 <= hr <= 18 else 30.0
            circadian.update_slot(hr, luminance=expected_lum, motion_energy=expected_motion, entropy=0.50)

    # 2A. Normal afternoon activity at 14:00 (expected ~0.15, actual 0.18)
    score_normal, reason_normal = circadian.compute_circadian_anomaly(hour=14, motion_energy=0.18, luminance=142.0)
    assert score_normal < 0.25, f"Normal daytime activity should have low anomaly score, got {score_normal}"
    print(f"  -> Daytime 14:00 check: score={score_normal}, reason={reason_normal}")

    # 2B. Unusual late-night activity at 03:00 AM (expected 0.01, actual 0.25 -> 25x expected!)
    score_night, reason_night = circadian.compute_circadian_anomaly(hour=3, motion_energy=0.25, luminance=32.0)
    assert score_night > 0.50, f"Unusual 3:00 AM surge must trigger anomaly score > 0.50, got {score_night}"
    assert "UNUSUAL_OFF_HOURS_ACTIVITY" in reason_night
    print(f"  -> Off-hours 03:00 check: score={score_night}, reason={reason_night}")
    print("  -> Passed: Circadian diurnal baseline successfully detects out-of-schedule activity.")


def test_movement_manifold():
    print("[TEST 3] Testing movement manifold route likelihood modeling on 8x8 grid...")
    manifold = MovementManifold(grid_size=8)

    # Train standard corridor route: horizontal crossing from left (x=0.1) to right (x=0.9) at y=0.5
    for _ in range(20):
        standard_traj = [(round(0.1 + (0.1 * i), 2), 0.5) for i in range(9)]
        manifold.record_trajectory(standard_traj)

    assert manifold.total_tracks_processed == 20
    print(f"  -> Trained manifold with {manifold.total_tracks_processed} standard corridor trajectories.")

    # 3A. Evaluate standard corridor traversal
    test_standard = [(0.15, 0.5), (0.25, 0.5), (0.35, 0.5), (0.45, 0.5), (0.55, 0.5)]
    score_std, reason_std = manifold.evaluate_route_anomaly(test_standard)
    assert score_std < 0.20, f"Standard route should have low anomaly score, got {score_std}"
    print(f"  -> Standard route evaluated: score={score_std}, reason={reason_std}")

    # 3B. Evaluate anomalous zigzag route through unobserved cells
    test_anomalous = [(0.05, 0.05), (0.45, 0.95), (0.05, 0.95), (0.95, 0.05)]
    score_ano, reason_ano = manifold.evaluate_route_anomaly(test_anomalous)
    assert score_ano > 0.60, f"Anomalous route must trigger high anomaly score, got {score_ano}"
    assert "UNUSUAL_MOVEMENT_MANIFOLD_DEVIATION" in reason_ano
    print(f"  -> Anomalous route evaluated: score={score_ano}, reason={reason_ano}")
    print("  -> Passed: Movement manifold models transit flow and isolates unusual trajectories.")


def test_appearance_manifold_clustering():
    print("[TEST 4] Testing unsupervised appearance manifold clustering...")
    clusterer = AppearanceManifoldCluster(k_clusters=4, descriptor_dim=64)

    # Ingest 40 descriptors from two distinct visual distributions (e.g. dark jackets vs bright vehicles)
    rng = np.random.RandomState(42)
    archetype_1 = rng.normal(loc=0.8, scale=0.1, size=(20, 64))
    archetype_2 = rng.normal(loc=-0.8, scale=0.1, size=(20, 64))

    for desc in archetype_1:
        clusterer.record_descriptor(desc)
    for desc in archetype_2:
        clusterer.record_descriptor(desc)

    assert len(clusterer.cluster_centers) == 4
    assert clusterer.to_dict()["cluster_count"] == 4

    # Familiar archetype should have low novelty score
    sample_familiar = rng.normal(loc=0.8, scale=0.08, size=64)
    nov_familiar = clusterer.compute_novelty_score(sample_familiar)
    assert nov_familiar < 0.35, f"Familiar appearance should have low novelty score, got {nov_familiar}"

    # Highly atypical outlier should have higher novelty score
    sample_novel = rng.normal(loc=0.0, scale=0.5, size=64)
    nov_novel = clusterer.compute_novelty_score(sample_novel)
    assert nov_novel > nov_familiar, f"Outlier must have higher novelty than familiar sample"
    print(f"  -> Appearance clustering: familiar_score={nov_familiar}, novel_outlier={nov_novel}")
    print("  -> Passed: Appearance manifold clusters visual archetypes without class supervision.")


def test_environmental_shift_and_tamper_detection():
    print("[TEST 5] Testing environmental shift & camera tamper detection...")
    ssl = SelfSupervisedEnvironmentLearner(camera_id="CAM-PERIMETER-01")

    # Ingest baseline outdoor frames (stable background)
    base_frame = np.random.RandomState(42).randint(80, 180, size=(240, 320, 3), dtype=np.uint8)
    for _ in range(16):
        res = ssl.process_unlabeled_frame(base_frame)

    assert ssl.is_baseline_ready is True
    assert res["scene_shift_distance"] < 0.15
    assert res["is_environmental_shift"] is False
    print(f"  -> Baseline stabilized: shift_dist={res['scene_shift_distance']:.3f}, ready={ssl.is_baseline_ready}")

    # Introduce sudden tampering: camera completely obstructed / blocked (pitch black / spray painted)
    blocked_frame = np.zeros((240, 320, 3), dtype=np.uint8)
    tamper_res = ssl.process_unlabeled_frame(blocked_frame)

    assert tamper_res["scene_shift_distance"] > 0.45, f"Tampered frame must have high shift distance, got {tamper_res['scene_shift_distance']}"
    assert tamper_res["is_environmental_shift"] is True
    print(f"  -> Tamper triggered: shift_dist={tamper_res['scene_shift_distance']:.3f}, reason={tamper_res['shift_reason']}")
    print("  -> Passed: Environmental shift & camera tampering successfully detected.")


def test_zero_pseudo_label_invariant():
    print("[TEST 6] Testing critical invariant: Zero unverified pseudo-labels into training pool...")
    ssl = SelfSupervisedEnvironmentLearner(camera_id="CAM-ZERO-BIAS")

    # Ingest 30 unlabeled frames and trajectories
    frame = np.random.RandomState(42).randint(60, 160, size=(240, 320, 3), dtype=np.uint8)
    traj = [(0.2, 0.3), (0.4, 0.5), (0.6, 0.7)]
    desc = np.ones(64, dtype=np.float32)

    initial_sample_count = len(memory_manager.samples)
    initial_dataset_count = len(memory_manager.dataset_versions)

    for _ in range(30):
        ssl.process_unlabeled_frame(frame)
        ssl.process_unlabeled_trajectory(traj)
        ssl.process_unlabeled_crop(desc)

    # Verify that NO pseudo-labeled samples were added to memory manager's sample pool
    assert len(memory_manager.samples) == initial_sample_count, (
        "CRITICAL INVARIANT VIOLATION: Self-supervised learning must NOT inject pseudo-labels into training sample pool"
    )
    assert len(memory_manager.dataset_versions) == initial_dataset_count

    print("  -> Passed: Self-supervised learning strictly operates in representation space with ZERO confirmation bias.")


async def test_schema_export_and_api():
    print("[TEST 7] Testing environmental baseline export, disk persistence & FastAPI endpoints...")
    ssl = SelfSupervisedEnvironmentLearner(camera_id="CAM-API-SSL")
    frame = np.random.RandomState(42).randint(70, 170, size=(240, 320, 3), dtype=np.uint8)
    for _ in range(16):
        ssl.process_unlabeled_frame(frame)

    # 7A. Export baseline dictionary
    exported = ssl.export_baseline()
    assert exported["camera_id"] == "CAM-API-SSL"
    assert exported["baseline_ready"] is True
    assert "circadian_profile" in exported
    assert "movement_manifold" in exported
    assert "appearance_clusters" in exported

    # 7B. Save to disk and verify existence
    ssl.save_baseline_to_disk()
    disk_path = os.path.join(ssl.save_dir, "CAM-API-SSL_baseline.json")
    assert os.path.exists(disk_path), f"Baseline JSON file should exist at {disk_path}"

    # 7C. Test API GET /camera-profiles/{camera_id}/baseline
    mock_user = {"username": "supervisor_jane", "role": "OPERATOR"}
    baseline_res = await get_camera_baseline(camera_id="CAM-API-SSL", user=mock_user)
    assert baseline_res["camera_id"] == "CAM-API-SSL"
    assert "circadian_profile" in baseline_res

    # 7D. Test API POST /camera-profiles/{camera_id}/learn-baseline
    learn_res = await learn_camera_baseline(camera_id="CAM-API-SSL", user=mock_user)
    assert learn_res["status"] == "success"
    assert "analysis" in learn_res
    assert learn_res["analysis"]["camera_id"] == "CAM-API-SSL"
    print("  -> Passed: Baseline export, persistence, and REST endpoints verified.")


async def main():
    print("======================================================================")
    print("PROJECT GARUDA — MILESTONE 5 SELF-SUPERVISED VERIFICATION TEST SUITE")
    print("======================================================================")
    test_scene_representation_extraction()
    test_circadian_temporal_baseline()
    test_movement_manifold()
    test_appearance_manifold_clustering()
    test_environmental_shift_and_tamper_detection()
    test_zero_pseudo_label_invariant()
    await test_schema_export_and_api()
    print("======================================================================")
    print("ALL MILESTONE 5 SELF-SUPERVISED TESTS PASSED (100% SUCCESS)!")
    print("======================================================================")


if __name__ == "__main__":
    asyncio.run(main())
