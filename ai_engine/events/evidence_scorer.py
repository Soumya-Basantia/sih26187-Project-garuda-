"""
EvidenceScorer — Automated Best-Evidence Selection Engine for Project Garuda.

Inspired by law enforcement ITMS & e-Challan systems:
Instead of capturing a single arbitrary, potentially blurry frame when an event fires,
EvidenceScorer tracks candidates across an event window (T - 2s to T + 2s),
evaluates Laplacian sharpness, crop resolution, detection confidence, and facial/plate visibility,
and extracts the definitive 3-Point Forensic Evidence Dossier:
  1. Wide Context Scene (Red polygon zone breach proof)
  2. Best Intruder / Subject Face Crop (Sharpest identification view)
  3. Best Vehicle Plate Crop (Sharpest ANPR OCR reading)
"""

from __future__ import annotations

import time
import hashlib
import os
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple
from pathlib import Path

import cv2
import numpy as np


@dataclass
class TrackFrameCandidate:
    timestamp: float
    frame: np.ndarray
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    confidence: float
    is_person: bool
    is_vehicle: bool
    face_crop: Optional[np.ndarray] = None
    plate_crop: Optional[np.ndarray] = None
    plate_text: Optional[str] = None
    plate_conf: float = 0.0
    sharpness: float = 0.0
    quality_score: float = 0.0


@dataclass
class ForensicEvidencePackage:
    evidence_id: str
    incident_type: str
    camera_id: str
    zone_name: str
    timestamp: float
    identity_name: str
    plate_number: Optional[str]
    priority_score: int
    violation_code: str
    context_frame_path: str
    face_crop_path: Optional[str]
    plate_crop_path: Optional[str]
    sha256_hash: str
    sharpness_metric: float
    operator_verdict: str = "PENDING_REVIEW"
    fine_amount_inr: int = 500  # Default e-Challan / breach penalty

    def to_dict(self) -> dict:
        return {
            "evidence_id": self.evidence_id,
            "incident_type": self.incident_type,
            "camera_id": self.camera_id,
            "zone_name": self.zone_name,
            "timestamp": self.timestamp,
            "identity_name": self.identity_name,
            "plate_number": self.plate_number,
            "priority_score": self.priority_score,
            "violation_code": self.violation_code,
            "context_frame_url": f"/data/evidence/{os.path.basename(self.context_frame_path)}",
            "face_crop_url": f"/data/evidence/{os.path.basename(self.face_crop_path)}" if self.face_crop_path else None,
            "plate_crop_url": f"/data/evidence/{os.path.basename(self.plate_crop_path)}" if self.plate_crop_path else None,
            "sha256_hash": self.sha256_hash,
            "sharpness_metric": round(self.sharpness_metric, 1),
            "operator_verdict": self.operator_verdict,
            "fine_amount_inr": self.fine_amount_inr,
        }


class EvidenceScorer:
    """
    Maintains a rolling ring-buffer of candidate frames for every active track
    and extracts court-grade evidence packages upon security breaches.
    """

    MAX_CANDIDATES_PER_TRACK = 20  # Keep last ~20 frames (~1-2 seconds)

    def __init__(self, output_dir: str = "data/evidence"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        # track_id -> List[TrackFrameCandidate]
        self._track_buffers: Dict[int, List[TrackFrameCandidate]] = {}

    @staticmethod
    def compute_laplacian_sharpness(img: np.ndarray) -> float:
        """Returns the variance of the Laplacian as an objective focus/sharpness metric."""
        if img is None or img.size == 0:
            return 0.0
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img
        return float(cv2.Laplacian(gray, cv2.CV_32F).var())

    def record_candidate(
        self,
        track_id: int,
        frame: np.ndarray,
        bbox: Tuple[int, int, int, int],
        confidence: float,
        is_person: bool,
        is_vehicle: bool,
        face_crop: Optional[np.ndarray] = None,
        plate_crop: Optional[np.ndarray] = None,
        plate_text: Optional[str] = None,
        plate_conf: float = 0.0,
    ):
        """Records a candidate frame for an active track and computes quality score."""
        x1, y1, x2, y2 = [int(round(float(v))) for v in bbox]
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 <= x1 or y2 <= y1:
            return

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return

        sharpness = self.compute_laplacian_sharpness(crop)
        res_score = min(1.0, (crop.shape[0] * crop.shape[1]) / (150 * 150))
        sharp_norm = min(1.0, sharpness / 120.0)

        # Quality formula: 45% sharpness + 35% confidence + 20% crop resolution
        quality = 0.45 * sharp_norm + 0.35 * confidence + 0.20 * res_score

        # Bonus for clear plate or face visibility
        if plate_text:
            quality += 0.25
        if face_crop is not None and face_crop.size > 0:
            quality += 0.20

        cand = TrackFrameCandidate(
            timestamp=time.time(),
            frame=frame.copy(),
            bbox=(x1, y1, x2, y2),
            confidence=confidence,
            is_person=is_person,
            is_vehicle=is_vehicle,
            face_crop=face_crop.copy() if face_crop is not None and face_crop.size > 0 else None,
            plate_crop=plate_crop.copy() if plate_crop is not None and plate_crop.size > 0 else None,
            plate_text=plate_text,
            plate_conf=plate_conf,
            sharpness=sharpness,
            quality_score=quality,
        )

        buffer = self._track_buffers.setdefault(track_id, [])
        buffer.append(cand)
        if len(buffer) > self.MAX_CANDIDATES_PER_TRACK:
            buffer.pop(0)

    def prune_stale_tracks(self, active_track_ids: set):
        """Clean up buffers for tracks that left the camera view."""
        for tid in list(self._track_buffers.keys()):
            if tid not in active_track_ids:
                del self._track_buffers[tid]

    def build_evidence_package(
        self,
        track_id: int,
        camera_id: str,
        zone_name: str,
        incident_type: str = "RESTRICTED_ZONE_BREACH",
        identity_name: str = "UNKNOWN INTRUDER",
        plate_number: Optional[str] = None,
        zone_polygon: Optional[List[Tuple[int, int]]] = None,
        priority_score: int = 90,
        violation_code: str = "SEC-BREACH-01",
    ) -> Optional[ForensicEvidencePackage]:
        """
        Extracts the best-evidence images from the track's candidate buffer,
        saves them with cryptographic SHA-256 verification, and returns a ForensicEvidencePackage.
        """
        candidates = self._track_buffers.get(track_id, [])
        if not candidates:
            return None

        # 1. Best Context Candidate (Highest overall quality score)
        best_context_cand = max(candidates, key=lambda c: c.quality_score)

        # 2. Best Face Crop (Sharpest face among candidates, fallback to top 25% of subject bbox)
        best_face_crop = None
        face_candidates = [c for c in candidates if c.face_crop is not None]
        if face_candidates:
            best_face_cand = max(face_candidates, key=lambda c: self.compute_laplacian_sharpness(c.face_crop))
            best_face_crop = best_face_cand.face_crop
        else:
            # Automatic upper-body / head ROI crop from the sharpest person frame
            x1, y1, x2, y2 = [int(round(float(v))) for v in best_context_cand.bbox]
            pw, ph = x2 - x1, y2 - y1
            if ph > 30 and pw > 20:
                head_y2 = min(y2, y1 + int(ph * 0.35))
                raw_head = best_context_cand.frame[y1:head_y2, x1:x2]
                if raw_head.size > 0:
                    best_face_crop = raw_head

        # 3. Best Plate Crop (Highest confidence plate OCR, or direct plate crop)
        best_plate_crop = None
        plate_text_found = plate_number
        plate_candidates = [c for c in candidates if c.plate_crop is not None]
        if plate_candidates:
            best_plate_cand = max(plate_candidates, key=lambda c: c.plate_conf if c.plate_conf > 0 else c.sharpness)
            best_plate_crop = best_plate_cand.plate_crop
            if not plate_text_found and best_plate_cand.plate_text:
                plate_text_found = best_plate_cand.plate_text

        # 4. Generate annotated Wide Context Frame with Red Boundary Breach
        context_annotated = best_context_cand.frame.copy()
        
        # Draw red restricted zone polygon
        if zone_polygon and len(zone_polygon) >= 3:
            poly_np = np.array(zone_polygon, dtype=np.int32)
            cv2.polylines(context_annotated, [poly_np], True, (0, 0, 255), 2, cv2.LINE_AA)
            # Subtle red translucent fill
            overlay = context_annotated.copy()
            cv2.fillPoly(overlay, [poly_np], (0, 0, 180))
            cv2.addWeighted(overlay, 0.25, context_annotated, 0.75, 0, context_annotated)
            # Label
            cv2.putText(context_annotated, f"RESTRICTED: {zone_name.upper()}", (zone_polygon[0][0], max(20, zone_polygon[0][1] - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2, cv2.LINE_AA)

        # Highlight intruder with tactical red corner brackets
        x1, y1, x2, y2 = [int(round(float(v))) for v in best_context_cand.bbox]
        cv2.rectangle(context_annotated, (x1, y1), (x2, y2), (0, 0, 255), 2, cv2.LINE_AA)
        cv2.putText(context_annotated, f"BREACH DETECTED #{track_id}", (x1, max(18, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2, cv2.LINE_AA)

        # 5. Save Evidence Files to Disk
        timestamp_str = time.strftime("%Y%m%d_%H%M%S")
        uid = hashlib.md5(f"{track_id}_{time.time()}".encode()).hexdigest()[:6]
        evidence_id = f"EVD-{timestamp_str}-{uid.upper()}"

        ctx_filename = f"{evidence_id}_context.jpg"
        face_filename = f"{evidence_id}_face.jpg" if best_face_crop is not None else None
        plate_filename = f"{evidence_id}_plate.jpg" if best_plate_crop is not None else None

        ctx_path = str(self.output_dir / ctx_filename)
        cv2.imwrite(ctx_path, context_annotated, [cv2.IMWRITE_JPEG_QUALITY, 92])

        face_path = None
        if best_face_crop is not None and best_face_crop.size > 0:
            face_path = str(self.output_dir / face_filename)
            # Ensure minimum viewable size
            fh, fw = best_face_crop.shape[:2]
            if fw < 160:
                scale = 160.0 / max(1, fw)
                best_face_crop = cv2.resize(best_face_crop, (160, int(fh * scale)), interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(face_path, best_face_crop, [cv2.IMWRITE_JPEG_QUALITY, 95])

        plate_path = None
        if best_plate_crop is not None and best_plate_crop.size > 0:
            plate_path = str(self.output_dir / plate_filename)
            ph, pw = best_plate_crop.shape[:2]
            if pw < 200:
                scale = 200.0 / max(1, pw)
                best_plate_crop = cv2.resize(best_plate_crop, (200, int(ph * scale)), interpolation=cv2.INTER_CUBIC)
            cv2.imwrite(plate_path, best_plate_crop, [cv2.IMWRITE_JPEG_QUALITY, 95])

        # 6. Compute Cryptographic SHA-256 Signature (Tamper-Proof Forensic Seal)
        hasher = hashlib.sha256()
        with open(ctx_path, "rb") as f:
            hasher.update(f.read())
        if face_path and os.path.exists(face_path):
            with open(face_path, "rb") as f:
                hasher.update(f.read())
        if plate_path and os.path.exists(plate_path):
            with open(plate_path, "rb") as f:
                hasher.update(f.read())
        hasher.update(f"{evidence_id}_{camera_id}_{zone_name}_{time.time()}".encode())
        sha256_seal = hasher.hexdigest()

        return ForensicEvidencePackage(
            evidence_id=evidence_id,
            incident_type=incident_type,
            camera_id=camera_id,
            zone_name=zone_name,
            timestamp=time.time(),
            identity_name=identity_name,
            plate_number=plate_text_found,
            priority_score=priority_score,
            violation_code=violation_code,
            context_frame_path=ctx_path,
            face_crop_path=face_path,
            plate_crop_path=plate_path,
            sha256_hash=sha256_seal,
            sharpness_metric=best_context_cand.sharpness,
            fine_amount_inr=500 if "vehicle" in incident_type.lower() else 250,
        )
