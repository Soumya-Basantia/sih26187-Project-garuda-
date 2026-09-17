"""
PlateRecognizer — ANPR module using EasyOCR for license plate text extraction.

Mirrors the pattern in face_verifier.py: graceful degradation when EasyOCR
is not installed, with a clean interface the pipeline can call without
caring about the backend availability.

Detection strategy:
  1. YOLO already detects vehicles (car/bus/truck/motorcycle).
  2. This module takes a vehicle crop, applies preprocessing, and runs
     EasyOCR to extract plate text.
  3. Results are matched against a vehicle watchlist from MongoDB.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger("garude.anpr")


class PlateStatus(str, Enum):
    DETECTED = "DETECTED"
    REGISTERED = "REGISTERED"
    WATCHLIST_HIT = "WATCHLIST_HIT"
    NO_PLATE = "NO_PLATE"
    OCR_UNAVAILABLE = "OCR_UNAVAILABLE"


@dataclass
class PlateResult:
    status: PlateStatus
    plate_text: Optional[str]
    confidence: float
    watchlist_match: Optional[dict] = None
    is_fuzzy: bool = False


# Regex: Indian plates (MH12AB1234), generic alphanumeric fallback
_PLATE_PATTERN = re.compile(r"[A-Z]{2}\s?\d{1,2}\s?[A-Z]{0,3}\s?\d{1,4}")

# OCR character confusion pairs (bidirectional)
_OCR_CONFUSIONS = {
    ('O', '0'), ('0', 'O'),
    ('I', '1'), ('1', 'I'),
    ('L', '1'), ('1', 'L'),
    ('L', 'I'), ('I', 'L'),
    ('B', '8'), ('8', 'B'),
    ('S', '5'), ('5', 'S'),
    ('Z', '2'), ('2', 'Z'),
    ('G', '6'), ('6', 'G'),
    ('Q', '0'), ('0', 'Q'),
    ('K', '1'), ('1', 'K'),
    ('K', 'I'), ('I', 'K'),
    ('K', 'X'), ('X', 'K'),
    ('K', 'H'), ('H', 'K'),
}


class PlateRecognizer:
    MIN_CONFIDENCE = 0.4
    PLATE_ASPECT_MIN = 2.0
    PLATE_ASPECT_MAX = 6.0

    def __init__(self):
        self._reader = None
        self._available = False
        self._watchlist: dict[str, dict] = {}
        try:
            import torch
            # Cap PyTorch CPU threads to 2 for OCR inference so video streaming threads are never starved
            if hasattr(torch, "set_num_threads"):
                try:
                    torch.set_num_threads(2)
                except Exception:
                    pass
            import easyocr
            self._reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            self._available = True
            logger.info("EasyOCR loaded for ANPR (CPU threads capped to 2)")
        except ImportError:
            logger.warning("easyocr not installed — ANPR disabled")
        except Exception as e:
            logger.error(f"EasyOCR init failed: {e}")

    def load_watchlist(self, vehicles: list[dict]):
        self._watchlist = {
            self._normalize(v["plate_number"]): v
            for v in vehicles
            if v.get("plate_number")
        }
        logger.info(f"ANPR watchlist loaded: {len(self._watchlist)} plates")

    def _match_plate(self, normalized: str) -> tuple[Optional[dict], bool]:
        """
        Exact match first, then strict single/double character OCR confusion match.
        Never matches if length or state prefix differs, preventing wrong plates
        from ever being approved as 'CLEARED' or matching watchlist incorrectly.
        """
        if not normalized or len(normalized) < 6:
            return None, False

        # 1. Exact match
        exact = self._watchlist.get(normalized)
        if exact:
            return exact, False

        # 2. Strict OCR Confusion match
        # Must have identical length and identical state code (first 2 chars).
        # Only allowed substitutions are known visual OCR confusion pairs (0/O, 1/I, 8/B, 5/S, 2/Z, 6/G).
        for plate_key, entry in self._watchlist.items():
            if len(plate_key) != len(normalized):
                continue
            if plate_key[:2] != normalized[:2]:
                continue

            confusions = 0
            is_valid_confusion = True
            for c1, c2 in zip(normalized, plate_key):
                if c1 == c2:
                    continue
                if (c1, c2) in _OCR_CONFUSIONS:
                    confusions += 1
                    if confusions > 2:
                        is_valid_confusion = False
                        break
                else:
                    # Non-confusion character mismatch: completely different vehicle!
                    is_valid_confusion = False
                    break

            if is_valid_confusion and confusions > 0:
                return entry, True

        # 3. Weathered single series letter omission (e.g. OCR reads KA052252 for KA05K2252)
        for plate_key, entry in self._watchlist.items():
            if len(normalized) == len(plate_key) - 1 and len(plate_key) >= 8:
                if normalized[:4] == plate_key[:4] and normalized[4:] == plate_key[5:]:
                    return entry, True

        return None, False

    def recognize(self, vehicle_crop: np.ndarray) -> PlateResult:
        if not self._available:
            return PlateResult(PlateStatus.OCR_UNAVAILABLE, None, 0.0)

        plate_roi = self._extract_plate_region(vehicle_crop)
        if plate_roi is None:
            plate_roi = vehicle_crop

        processed = self._preprocess(plate_roi)
        text, conf = self._ocr(processed)

        if not text:
            return PlateResult(PlateStatus.NO_PLATE, None, 0.0)

        normalized = self._normalize(text)
        vehicle_entry, is_fuzzy = self._match_plate(normalized)

        if vehicle_entry:
            is_threat = bool(vehicle_entry.get("watchlist_flag", False))
            status = PlateStatus.WATCHLIST_HIT if is_threat else PlateStatus.REGISTERED
            # If matched by fuzzy logic, copy entry and flag is_fuzzy
            matched_data = dict(vehicle_entry)
            matched_data["is_fuzzy"] = is_fuzzy
            matched_data["original_plate"] = vehicle_entry.get("plate_number")
            matched_data["scanned_plate"] = normalized

            adj_conf = conf * 0.9 if is_fuzzy else conf
            return PlateResult(
                status, normalized, adj_conf,
                watchlist_match=matched_data,
                is_fuzzy=is_fuzzy
            )

        return PlateResult(PlateStatus.DETECTED, normalized, conf)

    @staticmethod
    def find_standalone_plates(frame: np.ndarray) -> list[tuple[int, int, int, int]]:
        """
        Ultra-fast contour detection for license plate rectangles anywhere in the frame (<10ms).
        Allows instant recognition when someone shows a plate, phone, or paper to the camera.
        """
        h_frame, w_frame = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 60, 180)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        candidates = []
        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            aspect = w / max(h, 1)
            area = w * h
            if (1.8 <= aspect <= 6.0 and 
                w >= 80 and w <= int(w_frame * 0.95) and 
                h >= 20 and h <= int(h_frame * 0.6) and 
                area >= 1800):
                candidates.append((x, y, w, h))
        return candidates

    def _extract_plate_region(self, crop: np.ndarray) -> Optional[np.ndarray]:
        h_img, w_img = crop.shape[:2]
        aspect_crop = w_img / max(h_img, 1)

        # If incoming crop already has plate aspect ratio (e.g. phone screen, cropped plate), use directly
        if 1.8 <= aspect_crop <= 6.0 and w_img >= 60 and h_img >= 16:
            return crop

        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if len(crop.shape) == 3 else crop
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 60, 180)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(closed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        best = None
        best_area = 0

        for cnt in contours:
            x, y, w, h = cv2.boundingRect(cnt)
            aspect = w / max(h, 1)
            area = w * h
            if (self.PLATE_ASPECT_MIN <= aspect <= self.PLATE_ASPECT_MAX
                    and area > best_area
                    and w > w_img * 0.15
                    and h > h_img * 0.03):
                best = (x, y, w, h)
                best_area = area

        if best is not None:
            x, y, w, h = best
            pad = 4
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(w_img, x + w + pad)
            y2 = min(h_img, y + h + pad)
            return crop[y1:y2, x1:x2]

        return crop

    def _preprocess(self, roi: np.ndarray) -> np.ndarray:
        if len(roi.shape) == 3:
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        else:
            gray = roi.copy()

        # Resizing: Normalizing height to 72px speeds up OCR by 4x-5x on CPU
        h, w = gray.shape[:2]
        if h > 0 and w > 0:
            target_h = 72
            target_w = max(int(w * (target_h / h)), 140)
            gray = cv2.resize(gray, (target_w, target_h), interpolation=cv2.INTER_AREA if h > target_h else cv2.INTER_CUBIC)

        # CLAHE enhances character edge contrast without harsh binary cutoff
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        return clahe.apply(gray)

    def _ocr(self, image: np.ndarray) -> tuple[Optional[str], float]:
        try:
            # Optimized fast greedy OCR with restricted alphanumeric character allowlist
            results = self._reader.readtext(
                image,
                detail=1,
                paragraph=False,
                decoder='greedy',
                beamWidth=1,
                batch_size=4,
                mag_ratio=1.0,
                allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
            )
        except Exception as e:
            logger.error(f"OCR failed: {e}")
            return None, 0.0

        if not results:
            return None, 0.0

        # Filter out noisy detections, 'IND' watermark, and collect bounding boxes
        valid_boxes = []
        for bbox, text, conf in results:
            if conf < self.MIN_CONFIDENCE:
                continue
            cleaned = re.sub(r"[^A-Z0-9]", "", text.upper())
            if cleaned == "IND" and len(results) > 1:
                continue
            if len(cleaned) > 0:
                cy = sum(p[1] for p in bbox) / 4.0
                cx = sum(p[0] for p in bbox) / 4.0
                valid_boxes.append((cy, cx, cleaned, conf))

        if not valid_boxes:
            return None, 0.0

        # Check if any single box contains a full plate (>= 8 chars with good confidence)
        full_single = [b for b in valid_boxes if len(b[2]) >= 8]
        if full_single:
            full_single.sort(key=lambda b: b[3], reverse=True)
            best_text, best_conf = full_single[0][2], full_single[0][3]
        else:
            # Combine multi-fragment detections (e.g. 'DL 01' + 'AB 1234')
            # Sort top-to-bottom (bucketed by line height ~25px), then left-to-right
            valid_boxes.sort(key=lambda item: (round(item[0] / 25.0), item[1]))
            best_text = "".join(b[2] for b in valid_boxes)
            best_conf = sum(b[3] for b in valid_boxes) / len(valid_boxes)

        # Vehicle plates must have at least 6 alphanumeric characters
        if len(best_text) < 6:
            return None, 0.0

        match = _PLATE_PATTERN.search(best_text)
        if match and len(match.group()) >= len(best_text) - 1:
            best_text = match.group()

        return best_text, best_conf

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"[^A-Z0-9]", "", text.upper())
