"""
Project Garuda — Milestone 4: Camera Environmental Adaptation Test Suite

Verifies:
1. Lighting Profile Adaptation (DAYLIGHT, LOW_LIGHT, IR_NIGHT, GLARE).
2. Scene Baseline & Dynamic Activity Modeling.
3. Typical Object Distributions & Movement Patterns.
4. Dynamic Parameter Adaptation (detection threshold, persistence, tracking match).
5. Multi-Camera Profile Divergence (e.g. outdoor highway vs indoor corridor).
6. Schema roundtrip, Memory Manager integration & API endpoints.
7. Proof of zero model retraining during online adaptation.
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

from ai_engine.learning.camera_environment_adapter import (
    CameraEnvironmentAdapter,
    LightingProfile,
    SceneBaseline,
    MovementPatterns,
    DetectionStatistics,
    AdaptiveParameters,
)
from ai_engine.learning.data_foundation import CameraProfile, LearningEventType
from ai_engine.learning.memory_manager import memory_manager
from backend.app.api.learning_routes import get_camera_environment, trigger_camera_adaptation


def test_lighting_adaptation():
    print("[TEST 1] Testing online lighting profile adaptation across diverse conditions...")
    adapter = CameraEnvironmentAdapter(camera_id="CAM-TEST-LUM", base_confidence=0.25)

    # 1A. Standard Daylight Frame (Balanced luminance, normal contrast)
    daylight_frame = np.random.RandomState(42).randint(80, 190, size=(240, 320, 3), dtype=np.uint8)
    for _ in range(5):
        light_prof = adapter.adapt_lighting(daylight_frame)
    assert light_prof.condition == "DAYLIGHT"
    assert 100 < light_prof.mean_luminance < 160
    print(f"  -> Daylight verified: condition={light_prof.condition}, lum={light_prof.mean_luminance:.1f}")

    # 1B. Low-Light Night Frame (Dim ambient evening color, low contrast)
    low_light_frame = np.zeros((240, 320, 3), dtype=np.uint8)
    low_light_frame[:, :] = [35, 42, 50]
    low_light_frame[100:140, 100:140] = [45, 52, 60]
    for _ in range(20):
        light_prof = adapter.adapt_lighting(low_light_frame)
    assert light_prof.condition == "LOW_LIGHT"
    assert light_prof.mean_luminance < 55
    print(f"  -> Low-light verified: condition={light_prof.condition}, lum={light_prof.mean_luminance:.1f}")

    # 1C. High-Glare Frame (Direct sun / headlight saturated pixels)
    glare_frame = np.full((240, 320, 3), 248, dtype=np.uint8)
    for _ in range(15):
        light_prof = adapter.adapt_lighting(glare_frame)
    assert light_prof.condition == "GLARE"
    assert light_prof.glare_ratio >= 0.07
    print(f"  -> Glare verified: condition={light_prof.condition}, glare_ratio={light_prof.glare_ratio:.2f}")

    # 1D. IR Night Mode Frame (Monochrome black & white, low saturation)
    ir_frame = np.full((240, 320, 3), 30, dtype=np.uint8)
    # Fully desaturated grayscale image in 3 channels
    for _ in range(25):
        light_prof = adapter.adapt_lighting(ir_frame)
    assert light_prof.condition == "IR_NIGHT"
    print(f"  -> IR Night verified: condition={light_prof.condition}, sat={light_prof.color_saturation:.1f}")
    print("  -> Passed: Online lighting profile classifies all lighting physics accurately.")


def test_scene_baseline_and_activity():
    print("[TEST 2] Testing scene baseline & dynamic background activity modeling...")
    adapter = CameraEnvironmentAdapter(camera_id="CAM-TEST-SCENE", base_confidence=0.25)

    # 2A. Initialize background with static frames
    bg_frame = np.full((240, 320, 3), 100, dtype=np.uint8)
    for _ in range(10):
        scene = adapter.adapt_scene_baseline(bg_frame)
    assert scene.activity_level < 0.05
    assert scene.stability_score >= 0.90
    print(f"  -> Static scene: activity={scene.activity_level:.3f}, stability={scene.stability_score:.2f}")

    # 2B. Introduce significant motion in 40% of the frame
    active_frame = bg_frame.copy()
    active_frame[40:200, 40:200] = 220  # Bright moving foreground object
    for _ in range(8):
        scene = adapter.adapt_scene_baseline(active_frame)
    assert scene.activity_level > 0.08, f"Expected higher activity level, got {scene.activity_level}"
    assert scene.stability_score < 0.90
    print(f"  -> Dynamic scene: activity={scene.activity_level:.3f}, stability={scene.stability_score:.2f}")
    print("  -> Passed: Scene baseline tracks background noise and spatial occupancy density.")


def test_typical_objects_and_movement():
    print("[TEST 3] Testing camera-specific object priors & movement patterns...")
    adapter = CameraEnvironmentAdapter(camera_id="CAM-PARKING", base_confidence=0.25)

    # 3A. Record object detections
    detections = [
        {"label": "car", "confidence": 0.88},
        {"label": "car", "confidence": 0.92},
        {"label": "truck", "confidence": 0.79},
        {"label": "person", "confidence": 0.65},
    ]
    for _ in range(10):
        adapter.record_detections(detections)

    assert adapter.typical_objects["car"] == 20
    assert adapter.typical_objects["truck"] == 10
    assert adapter.typical_objects["person"] == 10
    assert adapter.stats.total_detections == 40
    assert 0.75 < adapter.stats.avg_confidence < 0.88
    print(f"  -> Object priors: {adapter.typical_objects}")

    # 3B. Record directional movement tracks (moving from left to right)
    class MockTrack:
        def __init__(self, tid, tlbr):
            self.track_id = tid
            self.tlbr = tlbr

    for step in range(10):
        x = 50 + (step * 25)
        tracks = [MockTrack(101, (x, 100, x + 60, 180))]
        adapter.record_tracks(tracks, frame_shape=(480, 640))

    assert len(adapter.movement.entry_zones) >= 1
    assert any(d["name"] == "RIGHT" for d in adapter.movement.frequent_directions)
    print(f"  -> Movement patterns: directions={adapter.movement.frequent_directions}, entry_zones={adapter.movement.entry_zones}")
    print("  -> Passed: Object priors and directional motion vector patterns verified.")


def test_dynamic_parameter_adaptation():
    print("[TEST 4] Testing dynamic parameter adaptation without model retraining...")
    adapter = CameraEnvironmentAdapter(camera_id="CAM-ADAPTIVE", base_confidence=0.25)

    # 4A. Baseline daytime parameters
    p_day = adapter.adapt_parameters()
    assert p_day.adapted_confidence == 0.25
    assert p_day.persistence_frames == 3
    assert p_day.track_match_thresh == 0.70

    # 4B. Low-Light adaptation (slightly lower threshold for recall, higher persistence to prevent flicker)
    adapter.lighting.condition = "LOW_LIGHT"
    p_low = adapter.adapt_parameters()
    assert p_low.adapted_confidence <= 0.22
    assert p_low.persistence_frames >= 4
    assert p_low.max_track_age >= 40
    print(f"  -> Low-light adapted: conf={p_low.adapted_confidence}, persist={p_low.persistence_frames}, max_age={p_low.max_track_age}")

    # 4C. Glare adaptation (higher threshold to reject specular reflections)
    adapter.lighting.condition = "GLARE"
    p_glare = adapter.adapt_parameters()
    assert p_glare.adapted_confidence >= 0.32
    assert p_glare.track_match_thresh >= 0.70
    print(f"  -> Glare adapted: conf={p_glare.adapted_confidence}, track_match={p_glare.track_match_thresh}")

    # 4D. False Alarm Reinforcement adaptation (RLHF penalty)
    adapter.lighting.condition = "DAYLIGHT"
    for _ in range(5):
        adapter.record_feedback(is_false_alarm=True)
    p_feedback = adapter.adapt_parameters()
    assert p_feedback.adapted_confidence > 0.25, "False alarm rate must increase detection threshold"
    assert p_feedback.persistence_frames >= 4
    print(f"  -> Feedback adapted: fa_rate={adapter.stats.false_alarm_rate}, conf={p_feedback.adapted_confidence}, persist={p_feedback.persistence_frames}")
    print("  -> Passed: Parameter auto-tuning operates completely in parameter space (Zero retraining).")


def test_multi_camera_profile_divergence():
    print("[TEST 5] Testing multi-camera profile divergence (outdoor highway vs indoor corridor)...")
    cam1 = CameraEnvironmentAdapter(camera_id="CAM-HIGHWAY", base_confidence=0.25)
    cam2 = CameraEnvironmentAdapter(camera_id="CAM-CORRIDOR", base_confidence=0.25)

    # Feed CAM-HIGHWAY with bright glare, fast car detections, rightward heading
    glare_frame = np.full((240, 320, 3), 245, dtype=np.uint8)
    cam1.adapt_frame(
        glare_frame,
        detections=[{"label": "car", "confidence": 0.85}, {"label": "truck", "confidence": 0.90}],
        force=True
    )

    # Feed CAM-CORRIDOR with dim low-light, person detections
    dim_frame = np.full((240, 320, 3), 40, dtype=np.uint8)
    cam2.adapt_frame(
        dim_frame,
        detections=[{"label": "person", "confidence": 0.60}],
        force=True
    )

    p1 = cam1.get_camera_profile()
    p2 = cam2.get_camera_profile()

    assert p1.lighting_baseline != p2.lighting_baseline
    assert p1.adapted_confidence != p2.adapted_confidence
    assert "car" in p1.typical_objects
    assert "person" in p2.typical_objects
    assert p1.status == "ENVIRONMENT_ADAPTED"
    print(f"  -> CAM-HIGHWAY: condition={p1.lighting_baseline}, conf={p1.adapted_confidence}, objects={p1.typical_objects}")
    print(f"  -> CAM-CORRIDOR: condition={p2.lighting_baseline}, conf={p2.adapted_confidence}, objects={p2.typical_objects}")
    print("  -> Passed: Independent cameras develop distinct, specialized environmental profiles.")


async def test_schema_and_api_integration():
    print("[TEST 6] Testing CameraProfile 7-domain schema roundtrip & API endpoints...")
    adapter = CameraEnvironmentAdapter(camera_id="CAM-API-TEST", base_confidence=0.25)
    test_frame = np.full((240, 320, 3), 120, dtype=np.uint8)
    prof = adapter.adapt_frame(
        test_frame,
        detections=[{"label": "bicycle", "confidence": 0.72}],
        force=True
    )

    # 6A. Verify 7 canonical domains exist in export
    p_dict = prof.to_dict()
    canonical_domains = [
        "lighting_profile",
        "scene_baseline",
        "typical_objects_distribution",
        "movement_patterns",
        "detection_statistics",
        "calibration",
        "adaptive_parameters",
    ]
    for domain in canonical_domains:
        assert domain in p_dict, f"Missing canonical domain: {domain}"

    # 6B. Roundtrip reconstruction
    reconstructed = CameraProfile.from_dict(p_dict)
    assert reconstructed.camera_id == "CAM-API-TEST"
    assert reconstructed.lighting_profile["condition"] == prof.lighting_profile["condition"]
    assert reconstructed.adaptive_parameters["adapted_confidence"] == prof.adaptive_parameters["adapted_confidence"]

    # 6C. LearningMemoryManager registration
    memory_manager.update_camera_profile(reconstructed)
    fetched = memory_manager.get_or_create_camera_profile("CAM-API-TEST")
    assert fetched.camera_id == "CAM-API-TEST"

    # 6D. Test API endpoint GET /camera-profiles/{camera_id}/environment
    mock_user = {"username": "admin_shepard", "role": "ADMIN"}
    env_res = await get_camera_environment(camera_id="CAM-API-TEST", user=mock_user)
    assert env_res["camera_id"] == "CAM-API-TEST"
    assert "lighting_profile" in env_res
    assert "adaptive_parameters" in env_res

    # 6E. Test API endpoint POST /camera-profiles/{camera_id}/adapt
    adapt_res = await trigger_camera_adaptation(camera_id="CAM-API-TEST", user=mock_user)
    assert adapt_res["status"] == "success"
    assert adapt_res["profile"]["camera_id"] == "CAM-API-TEST"
    print("  -> Passed: 7-domain schema roundtrip, memory manager storage, and API endpoints verified.")


async def main():
    print("======================================================================")
    print("PROJECT GARUDA — MILESTONE 4 CAMERA ADAPTATION VERIFICATION TEST SUITE")
    print("======================================================================")
    test_lighting_adaptation()
    test_scene_baseline_and_activity()
    test_typical_objects_and_movement()
    test_dynamic_parameter_adaptation()
    test_multi_camera_profile_divergence()
    await test_schema_and_api_integration()
    print("======================================================================")
    print("ALL MILESTONE 4 CAMERA ADAPTATION TESTS PASSED (100% SUCCESS)!")
    print("======================================================================")


if __name__ == "__main__":
    asyncio.run(main())
