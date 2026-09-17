"""
Project Garuda — Adaptive Learning Engine
Milestone 8: Synthetic Edge Case Augmentation & Data Diversity Generator

Implements physics-grounded CCTV degradation transformations and camera-targeted
dataset expansion to harden detectors against hostile real-world conditions:
1. CCTVDegradationSynthesizer: Weather (rain, fog), sensor noise (Poisson, CMOS, IR bloom),
   motion artifacts, and lens occlusions (water droplets, glare blooms).
2. Geometry & Bounding Box Co-Transformation: Perspective and scale jitter with strict label alignment.
3. TargetedAugmentationPolicy: Maps camera environmental profiles to targeted counter-examples.
4. DataDiversityEvaluator: Quantifies 64-dim representation diversity gain (target >= 25%).
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import asdict, dataclass, field
from typing import Any, List, Optional, Tuple

import cv2
import numpy as np

from ai_engine.learning.adaptive_filter import extract_visual_descriptor

logger = logging.getLogger("garuda.synthetic_augmentor")


# -----------------------------------------------------------------------------
# 1. Physics-Grounded CCTV Degradation Synthesizer
# -----------------------------------------------------------------------------

class CCTVDegradationSynthesizer:
    """
    Implements realistic, domain-specific CCTV degradation transforms
    operating directly on BGR image arrays.
    """

    @staticmethod
    def apply_rain_streaks(image: np.ndarray, intensity: float = 0.5, angle: float = 75.0) -> np.ndarray:
        """
        Simulates directional rain streaks with specular light scattering.
        """
        if image is None or image.size == 0:
            return image

        h, w = image.shape[:2]
        intensity = max(0.1, min(1.0, intensity))

        # Generate noise mask with directional streaks
        num_drops = int(h * w * 0.002 * intensity)
        streak_len = int(12 + 18 * intensity)
        rad = math.radians(angle)
        dx = int(math.cos(rad) * streak_len)
        dy = int(math.sin(rad) * streak_len)

        rain_layer = np.zeros((h, w), dtype=np.uint8)
        for _ in range(num_drops):
            x1 = random.randint(0, max(0, w - abs(dx) - 1))
            y1 = random.randint(0, max(0, h - abs(dy) - 1))
            x2 = x1 + dx
            y2 = y1 + dy
            cv2.line(rain_layer, (x1, y1), (x2, y2), 200, 1)

        # Smooth rain streaks slightly
        rain_layer = cv2.blur(rain_layer, (2, 2))

        # Alpha composite with original image
        res = image.astype(np.float32)
        rain_3ch = cv2.cvtColor(rain_layer, cv2.COLOR_GRAY2BGR).astype(np.float32)
        alpha = 0.35 * intensity
        res = cv2.addWeighted(res, 1.0, rain_3ch, alpha, 0.0)
        return np.clip(res, 0, 255).astype(np.uint8)

    @staticmethod
    def apply_fog_haze(image: np.ndarray, thickness: float = 0.4) -> np.ndarray:
        """
        Simulates atmospheric Koschmieder scattering (fog/smoke hazing):
        I_fog = I * t + A * (1 - t), where A is atmospheric airlight.
        """
        if image is None or image.size == 0:
            return image

        thickness = max(0.05, min(0.90, thickness))
        transmission = math.exp(-thickness * 1.8)
        airlight = np.array([215.0, 220.0, 225.0], dtype=np.float32)  # Daylight gray haze

        img_f = image.astype(np.float32)
        foggy = img_f * transmission + airlight * (1.0 - transmission)
        return np.clip(foggy, 0, 255).astype(np.uint8)

    @staticmethod
    def apply_low_light_noise(image: np.ndarray, gain: float = 2.0, dark_level: float = 0.45) -> np.ndarray:
        """
        Simulates photon shot noise (Poisson) and CMOS sensor thermal read noise
        in severe underexposure / night settings.
        """
        if image is None or image.size == 0:
            return image

        gain = max(1.0, min(5.0, gain))
        dark_level = max(0.1, min(0.8, dark_level))

        # Attenuate brightness
        darkened = image.astype(np.float32) * (1.0 - dark_level)

        # Poisson shot noise + Gaussian read noise
        poisson_noise = np.random.poisson(np.maximum(0.0, darkened / gain)) * gain
        read_noise = np.random.normal(0.0, 10.0 * (gain / 2.0), image.shape)

        noisy = poisson_noise + read_noise
        return np.clip(noisy, 0, 255).astype(np.uint8)

    @staticmethod
    def apply_motion_blur(image: np.ndarray, angle: float = 0.0, kernel_size: int = 9) -> np.ndarray:
        """
        Simulates camera pan or fast vehicle transit motion blur using a directional PSF.
        """
        if image is None or image.size == 0:
            return image

        k_size = max(3, min(25, int(kernel_size)))
        if k_size % 2 == 0:
            k_size += 1

        kernel = np.zeros((k_size, k_size), dtype=np.float32)
        center = k_size // 2
        rad = math.radians(angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        for i in range(k_size):
            offset = i - center
            x = int(round(center + offset * cos_a))
            y = int(round(center + offset * sin_a))
            if 0 <= x < k_size and 0 <= y < k_size:
                kernel[y, x] = 1.0

        s = np.sum(kernel)
        if s > 0:
            kernel /= s
        else:
            kernel[center, center] = 1.0

        return cv2.filter2D(image, -1, kernel)

    @staticmethod
    def apply_lens_droplets_and_glare(
        image: np.ndarray,
        num_droplets: int = 6,
        glare_pos: Optional[Tuple[float, float]] = None,
    ) -> np.ndarray:
        """
        Simulates water droplets on the camera glass dome and specular headlight glare blooms.
        """
        if image is None or image.size == 0:
            return image

        res = image.copy()
        h, w = image.shape[:2]

        # 1. Lens droplets (refractive circular distortion)
        for _ in range(num_droplets):
            cx = random.randint(15, max(16, w - 15))
            cy = random.randint(15, max(16, h - 15))
            radius = random.randint(8, 20)

            # Circular refractive blur & specular highlight rim
            mask = np.zeros((h, w), dtype=np.uint8)
            cv2.circle(mask, (cx, cy), radius, 255, -1)
            blurred_patch = cv2.GaussianBlur(res, (15, 15), 0)
            res[mask == 255] = blurred_patch[mask == 255]
            # Highlight rim
            cv2.circle(res, (cx, cy), radius, (240, 240, 240), 1)

        # 2. Specular glare bloom
        if glare_pos is not None:
            gx = int(glare_pos[0] * w)
            gy = int(glare_pos[1] * h)
            glare_rad = int(min(h, w) * 0.25)
            glare_overlay = np.zeros((h, w, 3), dtype=np.float32)
            cv2.circle(glare_overlay, (gx, gy), glare_rad, (255, 255, 255), -1)
            glare_overlay = cv2.GaussianBlur(glare_overlay, (51, 51), 0)
            res = cv2.addWeighted(res.astype(np.float32), 0.85, glare_overlay, 0.45, 0.0)
            res = np.clip(res, 0, 255).astype(np.uint8)

        return res

    @staticmethod
    def apply_geometric_jitter(
        image: np.ndarray,
        bounding_boxes: list[tuple[float, float, float, float]],
        max_scale_delta: float = 0.10,
        max_perspective_delta: float = 0.05,
    ) -> Tuple[np.ndarray, list[tuple[float, float, float, float]]]:
        """
        Applies subtle perspective and scaling jitter while strictly co-transforming
        and clipping normalized bounding box coordinates.
        Bounding boxes: [(x1, y1, x2, y2), ...] in normalized [0.0, 1.0].
        """
        if image is None or image.size == 0:
            return image, bounding_boxes

        h, w = image.shape[:2]
        pts1 = np.float32([[0, 0], [w, 0], [0, h], [w, h]])

        # Mild 4-corner perspective jitter
        d = max_perspective_delta
        dx1, dy1 = random.uniform(-d, d) * w, random.uniform(-d, d) * h
        dx2, dy2 = random.uniform(-d, d) * w, random.uniform(-d, d) * h
        dx3, dy3 = random.uniform(-d, d) * w, random.uniform(-d, d) * h
        dx4, dy4 = random.uniform(-d, d) * w, random.uniform(-d, d) * h

        pts2 = np.float32([
            [max(0, dx1), max(0, dy1)],
            [min(w - 1, w + dx2), max(0, dy2)],
            [max(0, dx3), min(h - 1, h + dy3)],
            [min(w - 1, w + dx4), min(h - 1, h + dy4)],
        ])

        matrix = cv2.getPerspectiveTransform(pts1, pts2)
        transformed_img = cv2.warpPerspective(image, matrix, (w, h), borderMode=cv2.BORDER_REFLECT)

        # Co-transform bounding boxes
        transformed_bboxes = []
        for bbox in bounding_boxes:
            bx1, by1, bx2, by2 = bbox
            corners = np.float32([
                [bx1 * w, by1 * h],
                [bx2 * w, by1 * h],
                [bx2 * w, by2 * h],
                [bx1 * w, by2 * h],
            ]).reshape(-1, 1, 2)

            t_corners = cv2.perspectiveTransform(corners, matrix).reshape(-1, 2)
            nx1 = float(np.min(t_corners[:, 0]) / w)
            ny1 = float(np.min(t_corners[:, 1]) / h)
            nx2 = float(np.max(t_corners[:, 0]) / w)
            ny2 = float(np.max(t_corners[:, 1]) / h)

            # Strict clipping to [0.0, 1.0] with valid dimensions
            nx1 = max(0.0, min(0.95, nx1))
            ny1 = max(0.0, min(0.95, ny1))
            nx2 = max(nx1 + 0.02, min(1.0, nx2))
            ny2 = max(ny1 + 0.02, min(1.0, ny2))

            transformed_bboxes.append((round(nx1, 4), round(ny1, 4), round(nx2, 4), round(ny2, 4)))

        return transformed_img, transformed_bboxes


# -----------------------------------------------------------------------------
# 2. Camera-Targeted Augmentation Policy
# -----------------------------------------------------------------------------

@dataclass
class AugmentedSampleVariation:
    variation_id: str
    original_sample_id: str
    camera_id: str
    transform_type: str
    augmented_crop_b64: Optional[str] = None
    bounding_box: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    descriptor: list[float] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TargetedAugmentationPolicy:
    """
    Analyzes a camera's operational profile and selects targeted transforms
    to build resilient representations against the camera's specific vulnerabilities.
    """

    def __init__(self):
        self.synthesizer = CCTVDegradationSynthesizer()

    def generate_variations(
        self,
        sample: dict,
        image_crop: np.ndarray,
        camera_profile: Optional[dict | Any] = None,
        count: int = 3,
    ) -> list[AugmentedSampleVariation]:
        """
        Generates targeted variations of an edge case crop based on camera conditions.
        """
        if image_crop is None or image_crop.size == 0:
            return []

        import uuid
        sample_id = sample.get("sample_id", f"s_{uuid.uuid4().hex[:6]}")
        camera_id = sample.get("camera_id", "CAM-UNKNOWN")
        orig_bbox = tuple(sample.get("bounding_box", sample.get("bbox", (0.1, 0.1, 0.8, 0.8))))

        # Determine camera conditions
        lighting_cond = "DAYLIGHT"
        glare_ratio = 0.0
        stability = 0.95

        if camera_profile is not None:
            if isinstance(camera_profile, dict):
                lighting_cond = camera_profile.get("lighting", {}).get("condition", "DAYLIGHT")
                glare_ratio = camera_profile.get("lighting", {}).get("glare_ratio", 0.0)
                stability = camera_profile.get("scene", {}).get("stability_score", 0.95)
            else:
                lighting_cond = getattr(getattr(camera_profile, "lighting", None), "condition", "DAYLIGHT")
                glare_ratio = getattr(getattr(camera_profile, "lighting", None), "glare_ratio", 0.0)
                stability = getattr(getattr(camera_profile, "scene", None), "stability_score", 0.95)

        # Select candidate transforms based on environmental vulnerability
        candidate_transforms = []
        if glare_ratio > 0.05 or lighting_cond == "GLARE":
            candidate_transforms.extend(["GLARE_BLOOM", "LENS_DROPLETS"])
        if lighting_cond in ("LOW_LIGHT", "IR_NIGHT"):
            candidate_transforms.extend(["LOW_LIGHT_NOISE", "MOTION_BLUR"])
        if stability < 0.70:
            candidate_transforms.extend(["RAIN_STREAKS", "FOG_HAZE"])

        # Fallback standard diverse set
        if not candidate_transforms:
            candidate_transforms = ["RAIN_STREAKS", "FOG_HAZE", "LOW_LIGHT_NOISE", "MOTION_BLUR", "GEOMETRIC_JITTER"]

        variations: list[AugmentedSampleVariation] = []
        selected_types = random.sample(candidate_transforms, min(count, len(candidate_transforms)))

        for t_type in selected_types:
            aug_img = image_crop.copy()
            aug_bbox = orig_bbox

            if t_type == "RAIN_STREAKS":
                aug_img = self.synthesizer.apply_rain_streaks(aug_img, intensity=0.6)
            elif t_type == "FOG_HAZE":
                aug_img = self.synthesizer.apply_fog_haze(aug_img, thickness=0.45)
            elif t_type == "LOW_LIGHT_NOISE":
                aug_img = self.synthesizer.apply_low_light_noise(aug_img, gain=2.2, dark_level=0.4)
            elif t_type == "MOTION_BLUR":
                aug_img = self.synthesizer.apply_motion_blur(aug_img, angle=45, kernel_size=9)
            elif t_type == "GLARE_BLOOM" or t_type == "LENS_DROPLETS":
                aug_img = self.synthesizer.apply_lens_droplets_and_glare(aug_img, num_droplets=5, glare_pos=(0.3, 0.3))
            elif t_type == "GEOMETRIC_JITTER":
                aug_img, bboxes = self.synthesizer.apply_geometric_jitter(aug_img, [orig_bbox])
                if bboxes:
                    aug_bbox = bboxes[0]

            # Extract 64-dim visual descriptor
            desc = extract_visual_descriptor(aug_img).tolist()

            # Encode thumbnail b64
            import base64
            success, buf = cv2.imencode(".jpg", aug_img, [cv2.IMWRITE_JPEG_QUALITY, 80])
            b64_str = f"data:image/jpeg;base64,{base64.b64encode(buf).decode('utf-8')}" if success else None

            var_obj = AugmentedSampleVariation(
                variation_id=f"aug_{uuid.uuid4().hex[:8]}",
                original_sample_id=sample_id,
                camera_id=camera_id,
                transform_type=t_type,
                augmented_crop_b64=b64_str,
                bounding_box=aug_bbox,
                descriptor=desc,
                metadata={"lighting_target": lighting_cond},
            )
            variations.append(var_obj)

        return variations


# -----------------------------------------------------------------------------
# 3. Data Diversity Evaluator
# -----------------------------------------------------------------------------

class DataDiversityEvaluator:
    """
    Measures coverage and dispersion in 64-dimensional representation space.
    Calculates percentage gain in average pairwise Euclidean distance.
    """

    @staticmethod
    def compute_average_pairwise_distance(descriptors: list[list[float] | np.ndarray]) -> float:
        """
        Computes mean pairwise Euclidean distance between all descriptors.
        """
        if len(descriptors) < 2:
            return 0.0

        arr = np.array(descriptors, dtype=np.float32)
        # Pairwise Euclidean distances
        diffs = arr[:, np.newaxis, :] - arr[np.newaxis, :, :]
        dists = np.sqrt(np.sum(diffs ** 2, axis=-1))

        # Mean of upper triangular entries
        n = len(descriptors)
        upper_indices = np.triu_indices(n, k=1)
        pairwise_vals = dists[upper_indices]
        return float(np.mean(pairwise_vals))

    @classmethod
    def evaluate_diversity_gain(
        cls,
        seed_descriptors: list[list[float] | np.ndarray],
        augmented_descriptors: list[list[float] | np.ndarray],
    ) -> dict[str, Any]:
        """
        Evaluates whether synthetic augmentation achieved the target diversity gain (>=25%).
        """
        seed_div = cls.compute_average_pairwise_distance(seed_descriptors)
        all_descriptors = list(seed_descriptors) + list(augmented_descriptors)
        combined_div = cls.compute_average_pairwise_distance(all_descriptors)

        gain_pct = ((combined_div - seed_div) / max(1e-5, seed_div)) * 100.0 if seed_div > 0 else 0.0

        return {
            "seed_count": len(seed_descriptors),
            "augmented_count": len(augmented_descriptors),
            "seed_diversity_distance": round(seed_div, 4),
            "augmented_diversity_distance": round(combined_div, 4),
            "diversity_gain_pct": round(gain_pct, 2),
            "meets_target_diversity": gain_pct >= 25.0,
        }


# Global singleton
synthetic_augmentor = TargetedAugmentationPolicy()
