"""
AdaptiveNegativeFilter — Online Few-Shot Negative Exemplar Memory Bank & Spatial Bayesian Prior.

Provides immediate, zero-downtime false-alarm suppression and sector-specific noise filtering:
1. Negative Exemplar Memory: Extracts lightweight visual descriptors for false-positive crops
   (swaying branches, fans, glare, reflections) and suppresses matching detections via cosine similarity.
2. Spatial Bayesian Prior: Maintains a 16x16 2D spatial grid per camera to track persistent false-alarm
   sectors and down-weight recurring static noise while keeping corridors and gates at peak sensitivity.
"""

from __future__ import annotations

import logging
import time
import math
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
import cv2
import numpy as np

logger = logging.getLogger("garuda.adaptive_filter")


def extract_visual_descriptor(crop: np.ndarray, feature_dim: int = 64) -> np.ndarray:
    """
    Extracts a fast, normalized 64-dimensional visual descriptor combining spatial color
    distribution and directional gradient energy. Runs in <0.2ms on CPU.
    """
    if crop is None or crop.size == 0:
        return np.zeros((feature_dim,), dtype=np.float32)

    try:
        # Resize crop to standard patch
        resized = cv2.resize(crop, (32, 32), interpolation=cv2.INTER_AREA)

        # 1. Color/intensity distribution (32 dims: 16-bin Luma + 8-bin Cr + 8-bin Cb)
        ycrcb = cv2.cvtColor(resized, cv2.COLOR_BGR2YCrCb) if resized.ndim == 3 else resized
        if ycrcb.ndim == 3:
            h_y = cv2.calcHist([ycrcb], [0], None, [16], [0, 256]).flatten()
            h_cr = cv2.calcHist([ycrcb], [1], None, [8], [0, 256]).flatten()
            h_cb = cv2.calcHist([ycrcb], [2], None, [8], [0, 256]).flatten()
            color_feat = np.concatenate([h_y, h_cr, h_cb])
        else:
            h_gray = cv2.calcHist([resized], [0], None, [32], [0, 256]).flatten()
            color_feat = h_gray

        color_feat = color_feat / (np.linalg.norm(color_feat) + 1e-6)

        # 2. Spatial gradient texture (32 dims: 4x4 spatial blocks of Sobel gradient magnitudes)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY) if resized.ndim == 3 else resized
        gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        mag = cv2.magnitude(gx, gy)
        
        # 4x4 spatial pooling (16 blocks x 2 stats: mean, std) -> 32 dims
        grad_blocks = []
        for r in range(4):
            for c in range(4):
                block = mag[r * 8 : (r + 1) * 8, c * 8 : (c + 1) * 8]
                grad_blocks.append(float(np.mean(block)))
                grad_blocks.append(float(np.std(block)))

        grad_feat = np.array(grad_blocks, dtype=np.float32)
        grad_feat = grad_feat / (np.linalg.norm(grad_feat) + 1e-6)

        # Combined 64-dim normalized descriptor
        combined = np.concatenate([color_feat, grad_feat]).astype(np.float32)
        norm = np.linalg.norm(combined)
        return combined / (norm + 1e-6)
    except Exception as e:
        logger.error(f"Error extracting visual descriptor: {e}")
        return np.zeros((feature_dim,), dtype=np.float32)


def cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Computes cosine similarity between two unit vectors."""
    dot = float(np.dot(vec_a, vec_b))
    return max(0.0, min(1.0, dot))


@dataclass
class NegativeExemplar:
    exemplar_id: str
    camera_id: str
    class_label: str
    descriptor: list[float]  # 64-dim unit vector
    spatial_coords: tuple[float, float, float, float]  # normalized cx, cy, w, h
    timestamp: float
    alert_id: Optional[str] = None
    notes: str = ""
    match_count: int = 0
    confidence_penalty: float = 0.45

    def to_dict(self) -> dict:
        d = asdict(self)
        d["descriptor"] = [round(float(v), 4) for v in self.descriptor]
        return d


class SpatialBayesianPrior:
    """
    16x16 2D spatial grid tracking false-alarm probability P(FalseAlarm | x, y) per camera.
    Learns recurring static clutter sectors without user intervention.
    """
    GRID_SIZE = 16

    def __init__(self, camera_id: str):
        self.camera_id = camera_id
        self.grid_false = np.zeros((self.GRID_SIZE, self.GRID_SIZE), dtype=np.float32)
        self.grid_total = np.zeros((self.GRID_SIZE, self.GRID_SIZE), dtype=np.float32)

    def record_observation(self, cx_norm: float, cy_norm: float, is_false_alarm: bool):
        gx = min(self.GRID_SIZE - 1, max(0, int(cx_norm * self.GRID_SIZE)))
        gy = min(self.GRID_SIZE - 1, max(0, int(cy_norm * self.GRID_SIZE)))
        self.grid_total[gy, gx] += 1.0
        if is_false_alarm:
            self.grid_false[gy, gx] += 1.0

    def get_false_alarm_penalty(self, cx_norm: float, cy_norm: float) -> float:
        """Returns a penalty in [0.0, 0.40] based on historical noise in this sector."""
        gx = min(self.GRID_SIZE - 1, max(0, int(cx_norm * self.GRID_SIZE)))
        gy = min(self.GRID_SIZE - 1, max(0, int(cy_norm * self.GRID_SIZE)))
        total = self.grid_total[gy, gx]
        if total < 3.0:
            return 0.0
        fa_rate = self.grid_false[gy, gx] / total
        return float(min(0.40, fa_rate * 0.50))

    def get_heatmap_matrix(self) -> list[list[float]]:
        probs = np.zeros((self.GRID_SIZE, self.GRID_SIZE), dtype=np.float32)
        mask = self.grid_total >= 2.0
        probs[mask] = self.grid_false[mask] / self.grid_total[mask]
        return [[round(float(v), 3) for v in row] for row in probs]


class AdaptiveNegativeFilter:
    """
    Main manager for negative exemplars and spatial bayesian priors across all camera feeds.
    Provides sub-millisecond suppression checks on live detection candidate boxes.
    """

    def __init__(self, similarity_threshold: float = 0.82, max_exemplars_per_cam: int = 150):
        self.similarity_threshold = similarity_threshold
        self.max_exemplars_per_cam = max_exemplars_per_cam
        self.exemplars: dict[str, list[NegativeExemplar]] = {}  # camera_id -> list
        self.spatial_priors: dict[str, SpatialBayesianPrior] = {}  # camera_id -> prior
        self.total_suppressed_count: int = 0

    def get_or_create_prior(self, camera_id: str) -> SpatialBayesianPrior:
        if camera_id not in self.spatial_priors:
            self.spatial_priors[camera_id] = SpatialBayesianPrior(camera_id)
        return self.spatial_priors[camera_id]

    def register_negative_exemplar(
        self,
        camera_id: str,
        crop: np.ndarray,
        bbox: tuple[float, float, float, float],
        frame_shape: tuple[int, int],
        class_label: str = "threat",
        alert_id: Optional[str] = None,
        notes: str = "",
    ) -> NegativeExemplar:
        """
        Stores an operator-confirmed or self-mined false alarm as a negative exemplar.
        Immediately suppresses future matching detections in that area.
        """
        fh, fw = frame_shape[:2]
        x1, y1, x2, y2 = bbox
        cx_norm = ((x1 + x2) / 2.0) / max(1.0, float(fw))
        cy_norm = ((y1 + y2) / 2.0) / max(1.0, float(fh))
        w_norm = (x2 - x1) / max(1.0, float(fw))
        h_norm = (y2 - y1) / max(1.0, float(fh))

        desc = extract_visual_descriptor(crop)
        exemplar_id = f"neg_{int(time.time() * 1000) % 1000000}"

        ex = NegativeExemplar(
            exemplar_id=exemplar_id,
            camera_id=camera_id,
            class_label=class_label,
            descriptor=desc.tolist(),
            spatial_coords=(cx_norm, cy_norm, w_norm, h_norm),
            timestamp=time.time(),
            alert_id=alert_id,
            notes=notes or "Operator marked false alarm",
        )

        if camera_id not in self.exemplars:
            self.exemplars[camera_id] = []

        # Keep within max buffer per camera
        if len(self.exemplars[camera_id]) >= self.max_exemplars_per_cam:
            self.exemplars[camera_id].pop(0)

        self.exemplars[camera_id].append(ex)

        # Update spatial prior
        prior = self.get_or_create_prior(camera_id)
        prior.record_observation(cx_norm, cy_norm, is_false_alarm=True)

        logger.info(
            f"Registered Negative Exemplar {exemplar_id} for camera {camera_id} at ({cx_norm:.2f}, {cy_norm:.2f})"
        )
        return ex

    def check_suppression(
        self,
        camera_id: str,
        frame: np.ndarray,
        bbox: tuple[float, float, float, float],
        confidence: float,
        class_label: str = "threat",
    ) -> tuple[bool, float, Optional[str]]:
        """
        Evaluates an active detection against the camera's negative exemplar bank and spatial prior.
        Returns: (is_suppressed, adjusted_confidence, reason)
        """
        if frame is None or frame.size == 0:
            return False, confidence, None

        fh, fw = frame.shape[:2]
        x1, y1, x2, y2 = (int(max(0, v)) for v in bbox)
        x2 = min(fw, max(x1 + 1, x2))
        y2 = min(fh, max(y1 + 1, y2))

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return False, confidence, None

        cx_norm = ((x1 + x2) / 2.0) / max(1.0, float(fw))
        cy_norm = ((y1 + y2) / 2.0) / max(1.0, float(fh))

        # 1. Spatial Bayesian penalty check
        prior = self.get_or_create_prior(camera_id)
        spatial_penalty = prior.get_false_alarm_penalty(cx_norm, cy_norm)
        adjusted_conf = max(0.05, confidence - spatial_penalty)

        # 2. Negative Exemplar feature matching
        cam_exemplars = self.exemplars.get(camera_id, [])
        if not cam_exemplars:
            return (adjusted_conf < 0.20), adjusted_conf, "spatial_penalty" if spatial_penalty > 0.1 else None

        desc = extract_visual_descriptor(crop)

        best_sim = 0.0
        best_ex: Optional[NegativeExemplar] = None

        for ex in reversed(cam_exemplars):
            ex_cx, ex_cy, _, _ = ex.spatial_coords
            # Spatial gating: only check exemplars in roughly adjacent sector (dist < 0.35 norm)
            dist_sq = (cx_norm - ex_cx) ** 2 + (cy_norm - ex_cy) ** 2
            if dist_sq > 0.12:
                continue

            sim = cosine_similarity(desc, np.array(ex.descriptor, dtype=np.float32))
            if sim > best_sim:
                best_sim = sim
                best_ex = ex

        if best_ex is not None and best_sim >= self.similarity_threshold:
            best_ex.match_count += 1
            self.total_suppressed_count += 1
            suppressed_conf = max(0.02, adjusted_conf - best_ex.confidence_penalty)
            logger.debug(
                f"[{camera_id}] Suppressed recurring false alarm (sim={best_sim:.2f} to {best_ex.exemplar_id})"
            )
            return True, suppressed_conf, f"Matched Negative Exemplar {best_ex.exemplar_id} (sim={best_sim:.2f})"

        return False, adjusted_conf, None

    def get_summary(self) -> dict:
        total_exemplars = sum(len(exs) for exs in self.exemplars.values())
        cam_counts = {cid: len(exs) for cid, exs in self.exemplars.items()}
        return {
            "total_negative_exemplars": total_exemplars,
            "total_suppressed_detections": self.total_suppressed_count,
            "camera_exemplar_counts": cam_counts,
        }
