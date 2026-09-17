"""
LightSourceDetector — Detects moving bright point-light sources (torch, flashlight)
in dark/night-time frames. This is a classic infiltrator behavior: torch beams moving
along a fence line at 02:00 AM with no associated human silhouette.

Logic:
  1. Brightness gate — only activates when the frame is dark (night-time).
  2. HSV threshold — isolates very bright (V > 240) and near-white/saturated pixels.
  3. Blob detection — groups bright pixels into candidate light blobs with minimum area.
  4. Motion check — a blob must have moved from a previous frame to fire an alert
     (static overhead lights are ignored).
  5. Returns list of LightSourceDetection objects with bounding box and confidence.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger("garuda.light_source_detector")


@dataclass
class LightSourceDetection:
    bbox: Tuple[int, int, int, int]   # x1, y1, x2, y2
    centroid: Tuple[float, float]
    area_px: int
    confidence: float                 # 0.0 - 1.0
    is_moving: bool
    frame_brightness: float           # Average frame brightness (0-255)


class LightSourceDetector:
    """
    Detects moving bright point-light sources (torches, flashlights, headlamps)
    in low-light night frames. Designed to catch infiltrators using flashlights
    along border fences when no human silhouette is visible in IR.

    Only activates when average frame brightness is below NIGHT_BRIGHTNESS_THRESHOLD.
    """

    # Frame must be dark for torch detection to activate (night / low-light)
    NIGHT_BRIGHTNESS_THRESHOLD = 80.0     # avg pixel brightness 0-255

    # HSV thresholds for very bright near-white point sources
    BRIGHT_VALUE_THRESHOLD = 230          # V channel (brightness) minimum
    MIN_BLOB_AREA_PX = 12                 # ignore tiny sensor noise
    MAX_BLOB_AREA_PX = 8000              # ignore large lit areas (moon, lights)

    # Motion: centroid must move at least this many pixels between checks
    MIN_MOTION_DISTANCE_PX = 6.0

    # Confidence decay: how quickly we trust a static blob (if it hasn't moved, lower conf)
    STATIC_BLOB_MAX_CONFIDENCE = 0.45

    def __init__(self):
        self._prev_centroids: List[Tuple[float, float]] = []
        self._prev_check_time: float = 0.0
        self._history: List[LightSourceDetection] = []

    def _is_night_frame(self, frame: np.ndarray) -> Tuple[bool, float]:
        """Returns (is_dark, avg_brightness)."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        avg = float(np.mean(gray))
        return avg < self.NIGHT_BRIGHTNESS_THRESHOLD, avg

    def _find_bright_blobs(self, frame: np.ndarray) -> List[LightSourceDetection]:
        """Locates very bright point sources in the frame using HSV + contour analysis."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        v_channel = hsv[:, :, 2]

        # Threshold: keep only very bright pixels
        _, bright_mask = cv2.threshold(v_channel, self.BRIGHT_VALUE_THRESHOLD, 255, cv2.THRESH_BINARY)

        # Morphological closing to merge nearby bright pixels into blobs
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        bright_mask = cv2.morphologyEx(bright_mask, cv2.MORPH_CLOSE, kernel)
        bright_mask = cv2.morphologyEx(bright_mask, cv2.MORPH_DILATE, kernel)

        contours, _ = cv2.findContours(bright_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections = []
        for cnt in contours:
            area = int(cv2.contourArea(cnt))
            if area < self.MIN_BLOB_AREA_PX or area > self.MAX_BLOB_AREA_PX:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            cx = x + w / 2.0
            cy = y + h / 2.0

            # Confidence scaled by area (bigger torch = more confident)
            raw_conf = min(1.0, (area - self.MIN_BLOB_AREA_PX) / (500 - self.MIN_BLOB_AREA_PX))
            confidence = 0.5 + raw_conf * 0.5  # range 0.5 -> 1.0

            detections.append(LightSourceDetection(
                bbox=(x, y, x + w, y + h),
                centroid=(cx, cy),
                area_px=area,
                confidence=round(confidence, 2),
                is_moving=False,  # determined next
                frame_brightness=0.0,  # filled by caller
            ))

        return detections

    def detect(self, frame: np.ndarray) -> List[LightSourceDetection]:
        """
        Runs torch/flashlight detection on a single frame.
        Returns list of moving bright point-source detections (empty if daytime or no torch found).
        """
        if frame is None or frame.size == 0:
            return []

        is_night, avg_brightness = self._is_night_frame(frame)
        if not is_night:
            # Daytime — no torch detection needed, clear history
            self._prev_centroids = []
            return []

        blobs = self._find_bright_blobs(frame)
        if not blobs:
            self._prev_centroids = []
            return []

        now = time.time()
        results: List[LightSourceDetection] = []

        for blob in blobs:
            blob.frame_brightness = avg_brightness

            # Check if this blob is moving relative to previously seen centroids
            is_moving = False
            best_dist = float("inf")
            for prev_cx, prev_cy in self._prev_centroids:
                dist = np.hypot(blob.centroid[0] - prev_cx, blob.centroid[1] - prev_cy)
                if dist < best_dist:
                    best_dist = dist

            # Blob existed before AND has moved — confirmed moving light source
            if self._prev_centroids and best_dist < 200:
                if best_dist >= self.MIN_MOTION_DISTANCE_PX:
                    is_moving = True
                # If blob is there but NOT moving, reduce confidence
                elif best_dist < self.MIN_MOTION_DISTANCE_PX:
                    blob.confidence = min(blob.confidence, self.STATIC_BLOB_MAX_CONFIDENCE)
            elif not self._prev_centroids:
                # First frame — tentatively flag as suspicious (new torch appearing)
                is_moving = True

            blob.is_moving = is_moving

            # Only report moving or newly appearing light sources
            if blob.is_moving:
                results.append(blob)

        # Update centroid history
        self._prev_centroids = [b.centroid for b in blobs]
        self._prev_check_time = now

        return results

    def get_hud_label(self, det: LightSourceDetection) -> str:
        """Returns a HUD badge string for annotation overlay."""
        return f"🔦 TORCH DETECTED ({int(det.confidence * 100)}%)"
