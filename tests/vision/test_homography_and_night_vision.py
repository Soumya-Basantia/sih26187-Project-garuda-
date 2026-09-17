"""
Automated Test Suite for Ground-Plane Homography, Metric Metrology & Night IR Vision Enhancer.
"""

import time
import numpy as np
import cv2

from ai_engine.zones.homography import HomographyEngine
from ai_engine.detection.vision_enhancer import AdaptiveVisionEnhancer
from ai_engine.zones.zone_engine import Zone, ZoneType, ZoneEngine
from ai_engine.events.event_engine import TemporalEventEngine, TrackState, EventType


def test_homography_engine():
    print("=" * 70)
    print("TEST 1: 3D Ground-Plane Homography & Metric Distance Engine")
    print("=" * 70)

    engine = HomographyEngine(frame_width=1280, frame_height=720)
    print("  [OK] HomographyEngine initialized with default border geometry.")

    # Far point (near horizon)
    p_far = (640, 305)  # center top
    g_far = engine.pixel_to_ground(p_far)
    print(f"  Pixel {p_far} -> Ground: X={g_far[0]}m, Y={g_far[1]}m")
    assert g_far[1] > 20.0, f"Expected deep ground distance > 20m, got {g_far[1]}"

    # Near point (near foreground)
    p_near = (640, 680)  # center bottom
    g_near = engine.pixel_to_ground(p_near)
    print(f"  Pixel {p_near} -> Ground: X={g_near[0]}m, Y={g_near[1]}m")
    assert g_near[1] < 10.0, f"Expected near ground distance < 10m, got {g_near[1]}"

    # Test Euclidean distance in meters
    dist_m = engine.distance_meters(g_far, g_near)
    print(f"  Ground distance between far and near: {dist_m} meters")
    assert dist_m > 15.0, "Expected significant metric ground displacement"

    # Test velocity calculation
    t0 = time.time()
    history = [
        (t0 - 2.0, (640, 450)),
        (t0 - 1.0, (640, 520)),
        (t0, (640, 590)),
    ]
    speed_kmh, m_type = engine.calculate_velocity_kmh(history)
    print(f"  Simulated human approach speed: {speed_kmh} km/h (Classification: {m_type})")
    assert speed_kmh > 0.0, "Expected non-zero speed"
    assert m_type in ("WALKING", "RUNNING", "VEHICULAR"), f"Unexpected movement type: {m_type}"

    # Test distance to a restricted perimeter polygon
    perimeter_polygon = [(200, 300), (1080, 300), (1080, 350), (200, 350)]
    intruder_px = (640, 450)
    dist_to_fence = engine.distance_to_polygon_meters(intruder_px, perimeter_polygon)
    print(f"  Intruder at {intruder_px} is {dist_to_fence} meters from Zero-Line polygon")
    assert dist_to_fence > 0.0, "Distance to fence should be positive"

    print("  >>> TEST 1 PASSED: Metric Homography & Velocity Engine Verified!\n")


def test_night_ir_vision_enhancer():
    print("=" * 70)
    print("TEST 2: Adaptive Vision Enhancer (Noisy Night IR & Zero-DCE Curve)")
    print("=" * 70)

    enhancer = AdaptiveVisionEnhancer(low_light_threshold=80.0)

    # 1. Daylight Frame Test (Should bypass)
    day_frame = np.full((720, 1280, 3), 160, dtype=np.uint8)
    # Add some natural texture
    day_frame += np.random.randint(-15, 15, day_frame.shape, dtype=np.int16).clip(-10, 10).astype(np.uint8)
    out_day, is_enh_day, meta_day = enhancer.process(day_frame)
    print(f"  Daylight frame: mean={meta_day['mean_luminance']}, enhanced={is_enh_day}, mode={meta_day['mode']}")
    assert not is_enh_day, "Daylight frame should bypass enhancement"

    # 2. Noisy Night IR Frame Test (Should detect low light, denoise, and curve boost)
    # Create dark frame (mean luminance ≈ 35)
    dark_frame = np.full((720, 1280, 3), 32, dtype=np.uint8)
    # Add synthetic IR camera speckle/salt-and-pepper noise
    noise = np.random.normal(0, 18, dark_frame.shape).astype(np.int16)
    noisy_night_frame = np.clip(dark_frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # Insert a faint human silhouette (luminance 55)
    cv2.rectangle(noisy_night_frame, (500, 250), (600, 500), (55, 55, 55), -1)

    # Warm up first frame
    enhancer.process(noisy_night_frame)

    t_start = time.perf_counter()
    iterations = 5
    for _ in range(iterations):
        out_night, is_enh_night, meta_night = enhancer.process(noisy_night_frame)
    elapsed_ms = ((time.perf_counter() - t_start) / iterations) * 1000.0

    print(f"  Night IR frame: original_mean={meta_night['mean_luminance']}, enhanced={is_enh_night}")
    print(f"  Enhancement mode: {meta_night['mode']}, factor={meta_night['darkness_factor']}")
    print(f"  Steady-state pre-processing latency: {elapsed_ms:.2f} ms")

    assert is_enh_night, "Night frame must trigger enhancement"
    assert elapsed_ms < 30.0, f"Latency too high: {elapsed_ms:.2f}ms (expected < 30ms on CPU)"

    # Check that shadow contrast was boosted
    mean_before = np.mean(noisy_night_frame)
    mean_after = np.mean(out_night)
    print(f"  Average luminance boosted from {mean_before:.1f} -> {mean_after:.1f}")
    assert mean_after > mean_before, "Enhanced frame should have higher average contrast/luminance"

    print("  >>> TEST 2 PASSED: Night IR Denoising & Low-Light Curve Verified!\n")


def test_zone_and_event_integration():
    print("=" * 70)
    print("TEST 3: ZoneEngine & TemporalEventEngine Metric Integration")
    print("=" * 70)

    zone_engine = ZoneEngine()
    test_zone = Zone(
        zone_id="zone-zero-line",
        camera_id="cam_01",
        name="Zero Line Strip",
        zone_type=ZoneType.HIGH_SECURITY,
        polygon=[(100, 250), (1180, 250), (1180, 320), (100, 320)]
    )
    zone_engine.load_zones([test_zone])

    # Test metric distance from ZoneEngine
    test_pt = (640, 500)
    metric_dist = zone_engine.distance_to_zone_meters("cam_01", test_zone, test_pt)
    print(f"  ZoneEngine.distance_to_zone_meters: {metric_dist} meters")
    assert metric_dist > 0.0, "Expected positive metric distance to zone"

    # Test TemporalEventEngine integration with dummy tracked object
    event_engine = TemporalEventEngine()

    class DummyObj:
        track_id = 42
        label = "person"
        confidence = 0.92
        foot_point = (640, 480)
        centroid = (640, 400)
        bbox = (600, 320, 680, 480)
        is_person = True
        is_bag = False
        is_vehicle = False

    t_now = time.time()
    events = event_engine.update(
        DummyObj(),
        camera_id="cam_01",
        matched_zones=[],
        current_hour=14,
        camera_zones=[test_zone]
    )

    state = event_engine.states.get(42)
    assert state is not None, "Track state should exist"
    print(f"  TrackState created: Ground meters={state.ground_coord_m}, Velocity={state.velocity_kmh} km/h")
    print(f"  Distance to Zero-Line: {state.distance_to_fence_m} meters")
    assert state.distance_to_fence_m < 900.0, "Distance to fence should be computed"

    print("  >>> TEST 3 PASSED: Full Event & Metrology Integration Verified!\n")


if __name__ == "__main__":
    test_homography_engine()
    test_night_ir_vision_enhancer()
    test_zone_and_event_integration()
    print("=" * 70)
    print("ALL VERIFICATION TESTS COMPLETED SUCCESSFULLY (100% PASS)")
    print("=" * 70)
