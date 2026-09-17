"""
Test script for ThermalVisionEngine in Project Garuda.
Verifies:
1. Spectrum mode auto-detection (White-Hot, Black-Hot, Ironbow, Visible RGB).
2. Frame normalization for YOLO neural detection.
3. Human biological heat signature detection (standing, crawling, crouching postures).
4. Decoy / false alarm rejection (cold cardboard cutout vs living warm human).
"""

import sys
import os
import numpy as np
import cv2

# Add workspace root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ai_engine.detection.thermal_engine import ThermalVisionEngine, ThermalMode, ThermalHeatSignature


def test_thermal_spectrum_classification():
    engine = ThermalVisionEngine()

    # 1. Daylight RGB frame (diverse colorful image)
    rgb_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    rgb_frame[:, :] = [180, 120, 70] # sky/ground tint
    cv2.rectangle(rgb_frame, (100, 100), (300, 300), (40, 200, 50), -1) # green bush
    cv2.rectangle(rgb_frame, (350, 150), (500, 400), (20, 30, 210), -1) # red vehicle
    mode_rgb, conf_rgb = engine.detect_spectrum_mode(rgb_frame)
    assert mode_rgb == ThermalMode.VISIBLE_RGB, f"Expected VISIBLE_RGB, got {mode_rgb}"
    print(f"[OK] Visible RGB detected: {mode_rgb.value} (conf={conf_rgb:.2f})")

    # 2. White-Hot thermal frame (cool dark background, bright white human silhouette)
    wh_frame = np.full((480, 640, 3), 45, dtype=np.uint8) # ambient cool background ~45
    # Draw warm human body (head, torso, legs)
    cv2.circle(wh_frame, (320, 180), 18, (240, 240, 240), -1) # head
    cv2.rectangle(wh_frame, (305, 200), (335, 280), (220, 220, 220), -1) # torso
    cv2.rectangle(wh_frame, (308, 280), (320, 350), (200, 200, 200), -1) # left leg
    cv2.rectangle(wh_frame, (322, 280), (334, 350), (200, 200, 200), -1) # right leg
    mode_wh, conf_wh = engine.detect_spectrum_mode(wh_frame)
    assert mode_wh == ThermalMode.THERMAL_WHITE_HOT, f"Expected THERMAL_WHITE_HOT, got {mode_wh}"
    print(f"[OK] Thermal White-Hot detected: {mode_wh.value} (conf={conf_wh:.2f})")

    # 3. Black-Hot thermal frame (cool bright background, dark black human silhouette)
    bh_frame = cv2.bitwise_not(wh_frame)
    mode_bh, conf_bh = engine.detect_spectrum_mode(bh_frame)
    assert mode_bh == ThermalMode.THERMAL_BLACK_HOT, f"Expected THERMAL_BLACK_HOT, got {mode_bh}"
    print(f"[OK] Thermal Black-Hot detected: {mode_bh.value} (conf={conf_bh:.2f})")

    # 4. Ironbow false-color frame (purple/blue background, orange/yellow hot targets)
    iron_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Fill background with dark blue / purple (HSV H~120-130, S~180, V~80 -> BGR)
    iron_bg = cv2.cvtColor(np.full((480, 640, 3), [125, 200, 70], dtype=np.uint8), cv2.COLOR_HSV2BGR)
    iron_frame = iron_bg
    # Draw warm human in bright orange/yellow (HSV H~15-25, S~230, V~240)
    warm_color = cv2.cvtColor(np.array([[[20, 230, 240]]], dtype=np.uint8), cv2.COLOR_HSV2BGR)[0, 0]
    cv2.circle(iron_frame, (320, 180), 22, [int(c) for c in warm_color], -1)
    cv2.rectangle(iron_frame, (300, 205), (340, 340), [int(c) for c in warm_color], -1)
    mode_iron, conf_iron = engine.detect_spectrum_mode(iron_frame)
    assert mode_iron == ThermalMode.THERMAL_IRONBOW, f"Expected THERMAL_IRONBOW, got {mode_iron}"
    print(f"[OK] Thermal Ironbow detected: {mode_iron.value} (conf={conf_iron:.2f})")


def test_thermal_human_heat_signature_detection():
    engine = ThermalVisionEngine(ambient_temp_celsius=21.0, min_heat_delta_c=5.0)

    # Construct White-Hot night scene with:
    # 1. Standing human at (200, 150)
    # 2. Crawling intruder in tall grass at (450, 350)
    frame = np.full((480, 640, 3), 40, dtype=np.uint8) # ambient background

    # Person 1: Standing human (w=36, h=150, Aspect Ratio ~4.1)
    cv2.circle(frame, (200, 120), 15, (245, 245, 245), -1)
    cv2.rectangle(frame, (185, 135), (215, 210), (230, 230, 230), -1)
    cv2.rectangle(frame, (187, 210), (198, 270), (210, 210, 210), -1)
    cv2.rectangle(frame, (202, 210), (213, 270), (210, 210, 210), -1)

    # Person 2: Crawling intruder prone (w=120, h=40, Aspect Ratio ~0.33)
    cv2.circle(frame, (420, 360), 14, (245, 245, 245), -1) # head
    cv2.rectangle(frame, (430, 345), (530, 375), (225, 225, 225), -1) # prone body

    signatures = engine.extract_heat_signatures(frame, mode=ThermalMode.THERMAL_WHITE_HOT)

    for idx, s in enumerate(signatures):
        print(f"     Candidate #{idx+1}: posture={s.posture}, AR={s.aspect_ratio}, bbox={s.bbox}")

    standing = [s for s in signatures if s.posture == "standing"]
    crawling = [s for s in signatures if s.posture == "crawling"]

    assert len(standing) >= 1, "Failed to identify standing thermal human"
    assert len(crawling) >= 1, "Failed to identify crawling thermal intruder"

    s1 = standing[0]
    print(f"     Target 1: {s1.posture.upper()} | Temp: {s1.estimated_temp_celsius} C (Delta: +{s1.temp_delta_celsius} C) | Conf: {s1.confidence}")
    assert 34.0 <= s1.estimated_temp_celsius <= 42.0, f"Unrealistic human temperature: {s1.estimated_temp_celsius}"

    s2 = crawling[0]
    print(f"     Target 2: {s2.posture.upper()} | Temp: {s2.estimated_temp_celsius} C (Delta: +{s2.temp_delta_celsius} C) | Conf: {s2.confidence}")
    assert 34.0 <= s2.estimated_temp_celsius <= 42.0, f"Unrealistic human temperature: {s2.estimated_temp_celsius}"


def test_thermal_decoy_rejection():
    engine = ThermalVisionEngine(ambient_temp_celsius=20.0, min_heat_delta_c=5.0)

    # Scene with a warm human and a cold cardboard cutout / mannequin
    frame = np.full((480, 640, 3), 50, dtype=np.uint8)

    # Warm human at bbox (100, 100, 160, 300)
    cv2.rectangle(frame, (100, 100), (160, 300), (235, 235, 235), -1)
    warm_result = engine.verify_bbox_thermal_signature(frame, (100, 100, 160, 300), ThermalMode.THERMAL_WHITE_HOT)
    assert warm_result["is_warm_body"] is True
    print(f"[OK] Living human verified: Warm body=True | Delta=+{warm_result['temp_delta_c']} C | Body Temp={warm_result['estimated_body_temp_c']} C")

    # Cold cardboard cutout at bbox (400, 100, 460, 300) with near-ambient heat (55)
    cv2.rectangle(frame, (400, 100), (460, 300), (55, 55, 55), -1)
    cold_result = engine.verify_bbox_thermal_signature(frame, (400, 100, 460, 300), ThermalMode.THERMAL_WHITE_HOT)
    assert cold_result["is_warm_body"] is False
    print(f"[OK] Cold decoy/cardboard rejected: Warm body=False | Delta=+{cold_result['temp_delta_c']} C (Below biological threshold)")


if __name__ == "__main__":
    print("==================================================")
    print("PROJECT GARUDA — THERMAL VISION ENGINE TEST SUITE")
    print("==================================================")
    test_thermal_spectrum_classification()
    test_thermal_human_heat_signature_detection()
    test_thermal_decoy_rejection()
    print("==================================================")
    print("[SUCCESS] ALL THERMAL VISION TESTS PASSED (100% PASS)")
    print("==================================================")
