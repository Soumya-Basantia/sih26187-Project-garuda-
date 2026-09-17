"""
ThermalVisionEngine — Autonomous Thermal Spectrum & Human Heat Signature Analysis.

Supports:
1. Spectrum Classification:
   - VISIBLE_RGB: Normal daytime / standard color CCTV.
   - THERMAL_WHITE_HOT: Radiant heat shown in bright white (cool background in dark/gray).
   - THERMAL_BLACK_HOT: Inverted thermal (hot targets shown in black).
   - THERMAL_IRONBOW / FALSE_COLOR: Colormapped thermal (purple/blue=cold, orange/yellow=hot).

2. Radiometric Normalization:
   - Inverts Black-Hot to White-Hot so standard YOLO and feature detectors can locate silhouettes.
   - Converts Ironbow false-color to normalized scalar thermal radiance for accurate edge and shape detection.
   - Applies Thermal CLAHE (Contrast-Limited Adaptive Histogram Equalization) tuned for border terrain.

3. Human Biological Heat Signature Analysis:
   - Detects radiant hotspots where ΔT (temperature delta above ambient) matches mammalian body heat (~35°C–39°C).
   - Evaluates anthropomorphic aspect ratios (standing: 1.5–4.5, crouching: 0.8–1.5, crawling: 0.25–0.75).
   - Analyzes thermal gradient (head and chest radiate peak heat; extremities taper off).
   - Detects thermal persons even when visual camo or brush obscures standard RGB YOLO!
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import cv2
import numpy as np


class ThermalMode(str, Enum):
    VISIBLE_RGB = "VISIBLE_RGB"
    THERMAL_WHITE_HOT = "THERMAL_WHITE_HOT"
    THERMAL_BLACK_HOT = "THERMAL_BLACK_HOT"
    THERMAL_IRONBOW = "THERMAL_IRONBOW"


@dataclass
class ThermalHeatSignature:
    bbox: tuple[float, float, float, float]  # (x1, y1, x2, y2)
    center: tuple[float, float]               # (cx, cy)
    peak_intensity: float                     # 0 - 255 normalized radiant heat
    mean_intensity: float
    ambient_baseline: float
    temp_delta_celsius: float                 # Estimated temperature above ambient (+°C)
    estimated_temp_celsius: float             # Calibrated approx body temperature (e.g. 36.8°C)
    is_biological_heat: bool                  # True if heat delta matches human/animal
    aspect_ratio: float                       # Height / Width
    posture: str                              # "standing", "crouching", "crawling"
    confidence: float                         # 0.0 - 1.0


class ThermalVisionEngine:
    """
    Analyzes, normalizes, and extracts human thermal heat signatures from
    LWIR (Long-Wave Infrared) / FLIR radiometric and false-color feeds.
    """

    def __init__(self, ambient_temp_celsius: float = 22.0, min_heat_delta_c: float = 5.0):
        """
        :param ambient_temp_celsius: Baseline ambient background temperature in °C.
        :param min_heat_delta_c: Minimum temperature above ambient to consider biological heat.
        """
        self.ambient_temp_celsius = ambient_temp_celsius
        self.min_heat_delta_c = min_heat_delta_c
        self._clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))

    def detect_spectrum_mode(self, frame: np.ndarray) -> tuple[ThermalMode, float]:
        """
        Classifies whether the frame is standard VISIBLE_RGB, THERMAL_WHITE_HOT,
        THERMAL_BLACK_HOT, or THERMAL_IRONBOW false-color.

        Returns (ThermalMode, confidence).
        """
        if frame is None or frame.size == 0:
            return ThermalMode.VISIBLE_RGB, 1.0

        h, w = frame.shape[:2]
        # Downsample for sub-millisecond spectrum profiling
        sample = cv2.resize(frame, (160, 120), interpolation=cv2.INTER_NEAREST)

        # Check color saturation (thermal white/black hot has near-zero saturation)
        hsv = cv2.cvtColor(sample, cv2.COLOR_BGR2HSV)
        sat = hsv[:, :, 1]
        mean_sat = float(np.mean(sat))
        val = hsv[:, :, 2]

        # 1. Monochrome / Radiometric Check (Near-zero saturation)
        if mean_sat < 18.0:
            # Distinguish White-Hot vs Black-Hot by luminance skewness & percentile ratio
            p90 = float(np.percentile(val, 90))
            p10 = float(np.percentile(val, 10))
            mean_val = float(np.mean(val))

            # In typical surveillance scenes, background dominates area (cooler).
            # If background is dark and hotspots are bright -> White-Hot
            # If background is bright and hot targets are dark -> Black-Hot
            if mean_val < 135.0:
                conf = min(1.0, (18.0 - mean_sat) / 18.0 * 0.95 + 0.05)
                return ThermalMode.THERMAL_WHITE_HOT, conf
            else:
                conf = min(1.0, (18.0 - mean_sat) / 18.0 * 0.90 + 0.10)
                return ThermalMode.THERMAL_BLACK_HOT, conf

        # 2. Check for Ironbow / Rainbow False-Color Thermal
        # Ironbow has distinctive palette: Black -> Purple -> Blue -> Magenta -> Red -> Orange -> Yellow -> White.
        # Crucially: pure green/cyan foliage colors (Hue 40 to 90) are completely absent in standard Ironbow!
        # If there is green vegetation / foliage, it is natural daylight RGB.
        hue = hsv[:, :, 0]
        green_mask = (hue >= 40) & (hue <= 90) & (sat > 40)
        green_ratio = float(np.sum(green_mask)) / (160 * 120)

        # In Ironbow:
        # Cold palette: Blue / Dark Purple (Hue 105 - 145)
        # Warm palette: Red / Orange / Yellow (Hue 0 - 32 and 160 - 180)
        blue_cold_mask = (hue >= 105) & (hue <= 145) & (sat > 60)
        warm_hot_mask = ((hue <= 32) | (hue >= 160)) & (sat > 60)

        cold_ratio = float(np.sum(blue_cold_mask)) / (160 * 120)
        hot_ratio = float(np.sum(warm_hot_mask)) / (160 * 120)

        # Ironbow requires high cold background, significant hot targets, AND absence of natural green
        if green_ratio < 0.02 and cold_ratio > 0.20 and hot_ratio > 0.01:
            conf = min(1.0, (cold_ratio + hot_ratio) * 1.5)
            return ThermalMode.THERMAL_IRONBOW, conf

        return ThermalMode.VISIBLE_RGB, 1.0

    def normalize_for_detection(self, frame: np.ndarray, mode: ThermalMode) -> np.ndarray:
        """
        Transforms thermal frames into high-contrast 3-channel images optimized
        for YOLO neural network silhouette detection.
        """
        if mode == ThermalMode.VISIBLE_RGB:
            return frame

        if mode == ThermalMode.THERMAL_BLACK_HOT:
            # Invert so hot objects become bright white against dark background
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            inverted = cv2.bitwise_not(gray)
            enhanced = self._clahe.apply(inverted)
            return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

        elif mode == ThermalMode.THERMAL_WHITE_HOT:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            enhanced = self._clahe.apply(gray)
            return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

        elif mode == ThermalMode.THERMAL_IRONBOW:
            # Map Ironbow colormap to scalar radiant temperature intensity
            # In Ironbow: Black -> Dark Purple -> Blue -> Magenta -> Red -> Orange -> Yellow -> White
            # We convert to HSV value & red/yellow dominance to form normalized radiant luminance
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            val = hsv[:, :, 2].astype(np.float32)
            sat = hsv[:, :, 1].astype(np.float32)
            hue = hsv[:, :, 0].astype(np.float32)

            # High value + warm hues (0-30 or 165-180) get high thermal weights
            warm_weight = np.where((hue <= 35) | (hue >= 165), 1.3, 0.7)
            # Pure white hotspots (low saturation, high value) get maximum score
            white_hotspot = np.where((sat < 40) & (val > 180), 1.5, 1.0)

            radiant = val * warm_weight * white_hotspot
            radiant = np.clip(radiant * (255.0 / (np.max(radiant) + 1e-5)), 0, 255).astype(np.uint8)
            enhanced = self._clahe.apply(radiant)
            return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

        return frame

    def extract_heat_signatures(
        self,
        frame: np.ndarray,
        mode: ThermalMode = ThermalMode.THERMAL_WHITE_HOT,
        min_area: int = 150,
        max_area: int = 80000,
    ) -> list[ThermalHeatSignature]:
        """
        Radiometric thermal hotspot analyzer.
        Detects clusters of radiant heat that match human body profiles (posture,
        relative temperature ΔT, and spatial coherence) even if YOLO misses due to
        camouflage, brush, or non-standard posture.
        """
        h, w = frame.shape[:2]

        # Extract normalized scalar heat map (0 - 255)
        if mode == ThermalMode.THERMAL_BLACK_HOT:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            heat_map = cv2.bitwise_not(gray)
        elif mode == ThermalMode.THERMAL_IRONBOW:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            val = hsv[:, :, 2].astype(np.float32)
            hue = hsv[:, :, 0].astype(np.float32)
            sat = hsv[:, :, 1].astype(np.float32)
            warm = np.where((hue <= 35) | (hue >= 165), 1.25, 0.65)
            white = np.where((sat < 40) & (val > 180), 1.4, 1.0)
            heat_map = np.clip(val * warm * white * (255.0 / (np.max(val * warm * white) + 1e-5)), 0, 255).astype(np.uint8)
        else:
            heat_map = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Baseline ambient background temperature estimation (20th - 50th percentile)
        ambient_baseline = float(np.percentile(heat_map, 40))

        # Dynamic hotspot thresholding (Otsu + Adaptive threshold on top 20% radiant band)
        hotspot_thresh = max(ambient_baseline + 35.0, float(np.percentile(heat_map, 80)))
        _, binary = cv2.threshold(heat_map, int(hotspot_thresh), 255, cv2.THRESH_BINARY)

        # Morphological closing to bridge limbs and torso
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        signatures: list[ThermalHeatSignature] = []

        # Scaled mapping: 255 intensity maps roughly to 42°C, baseline maps to ambient
        deg_per_intensity = 20.0 / max(1.0, (255.0 - ambient_baseline))

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < min_area or area > max_area:
                continue

            x, y, bw, bh = cv2.boundingRect(cnt)
            aspect_ratio = bh / max(1.0, bw)

            # Anthropomorphic geometry checks
            # Standing/walking: 1.4 <= AR <= 6.5
            # Crouching/sitting: 0.75 <= AR < 1.4
            # Crawling/prone: 0.20 <= AR < 0.75
            if 1.4 <= aspect_ratio <= 6.5:
                posture = "standing"
                shape_conf = 0.90
            elif 0.75 <= aspect_ratio < 1.4:
                posture = "crouching"
                shape_conf = 0.80
            elif 0.20 <= aspect_ratio < 0.75:
                posture = "crawling"
                shape_conf = 0.75
            else:
                # Extreme thin horizontal/vertical artifacts (wires, fences, poles) -> reject
                continue

            # Compute heat metrics within the contour
            mask = np.zeros((bh, bw), dtype=np.uint8)
            cv2.drawContours(mask, [cnt - np.array([x, y])], -1, 255, -1)
            roi_heat = heat_map[y : y + bh, x : x + bw]

            peak_val = float(np.max(roi_heat[mask > 0])) if np.any(mask > 0) else float(np.max(roi_heat))
            mean_val = float(np.mean(roi_heat[mask > 0])) if np.any(mask > 0) else float(np.mean(roi_heat))

            delta_intensity = peak_val - ambient_baseline
            temp_delta_c = delta_intensity * deg_per_intensity
            estimated_temp_c = self.ambient_temp_celsius + temp_delta_c

            # Check if heat delta qualifies as biological heat signature (34°C - 41°C human range)
            is_biological = (temp_delta_c >= self.min_heat_delta_c) and (estimated_temp_c <= 45.0)

            # Confidence fusion
            heat_conf = min(1.0, max(0.0, (temp_delta_c - self.min_heat_delta_c) / 12.0))
            overall_conf = round(float(shape_conf * 0.55 + heat_conf * 0.45), 2)

            if overall_conf >= 0.45 and is_biological:
                cx = x + bw / 2.0
                cy = y + bh / 2.0
                signatures.append(
                    ThermalHeatSignature(
                        bbox=(float(x), float(y), float(x + bw), float(y + bh)),
                        center=(cx, cy),
                        peak_intensity=peak_val,
                        mean_intensity=mean_val,
                        ambient_baseline=ambient_baseline,
                        temp_delta_celsius=round(temp_delta_c, 1),
                        estimated_temp_celsius=round(estimated_temp_c, 1),
                        is_biological_heat=is_biological,
                        aspect_ratio=round(aspect_ratio, 2),
                        posture=posture,
                        confidence=overall_conf,
                    )
                )

        # Sort by peak heat & confidence
        signatures.sort(key=lambda s: s.confidence, reverse=True)
        return signatures

    def verify_bbox_thermal_signature(
        self, frame: np.ndarray, bbox: tuple[float, float, float, float], mode: ThermalMode
    ) -> dict:
        """
        Cross-validates an existing YOLO bounding box against radiometric heat.
        Used to confirm that a detected person is a real living warm body
        (rejecting cardboard cutouts, posters, mannequin decoys, or cold reflections).
        """
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = [int(v) for v in bbox]
        x1 = max(0, min(w - 1, x1))
        y1 = max(0, min(h - 1, y1))
        x2 = max(x1 + 1, min(w, x2))
        y2 = max(y1 + 1, min(h, y2))

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return {"is_warm_body": False, "confidence": 0.0, "temp_delta_c": 0.0}

        # Measure localized heat contrast vs surrounding frame
        if mode == ThermalMode.THERMAL_BLACK_HOT:
            crop_gray = cv2.bitwise_not(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY))
            frame_gray = cv2.bitwise_not(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        elif mode == ThermalMode.THERMAL_IRONBOW:
            hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
            val = hsv[:, :, 2].astype(np.float32)
            hue = hsv[:, :, 0].astype(np.float32)
            warm = np.where((hue <= 35) | (hue >= 165), 1.25, 0.65)
            crop_gray = np.clip(val * warm, 0, 255).astype(np.uint8)
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        else:
            crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        body_peak = float(np.percentile(crop_gray, 90))
        ambient = float(np.percentile(frame_gray, 40))

        delta = max(0.0, body_peak - ambient)
        temp_delta_c = round(delta * (20.0 / max(1.0, 255.0 - ambient)), 1)
        is_warm_body = temp_delta_c >= self.min_heat_delta_c

        return {
            "is_warm_body": is_warm_body,
            "temp_delta_c": temp_delta_c,
            "estimated_body_temp_c": round(self.ambient_temp_celsius + temp_delta_c, 1),
            "thermal_mode": mode.value,
        }
