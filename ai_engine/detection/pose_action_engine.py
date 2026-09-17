"""
PoseActionEngine — Real-time 17-Keypoint Human Action & Posture Recognition for Project Garuda.
Uses YOLOv8-Pose for ultra-fast kinematic action intelligence:
- FALL_DETECTED / MAN_DOWN (Horizontal body axis / sudden floor impact)
- CRAWLING_INTRUSION (Prone crawling posture beneath perimeter sensors)
- HANDS_RAISED (Wrists elevated above head / surrender)
- NORMAL_POSTURE (Standing, walking)
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger("garude.pose_action")

# Standard COCO 17 Keypoints
# 0: Nose, 1: L_Eye, 2: R_Eye, 3: L_Ear, 4: R_Ear
# 5: L_Shoulder, 6: R_Shoulder, 7: L_Elbow, 8: R_Elbow, 9: L_Wrist, 10: R_Wrist
# 11: L_Hip, 12: R_Hip, 13: L_Knee, 14: R_Knee, 15: L_Ankle, 16: R_Ankle

# Exclude face connections (0: Nose, 1: L_Eye, 2: R_Eye, 3: L_Ear, 4: R_Ear) to keep face clean of lines
SKELETON_CONNECTIONS = [
    (5, 6), (5, 7), (7, 9),              # Left arm
    (6, 8), (8, 10),                     # Right arm
    (5, 11), (6, 12), (11, 12),          # Torso
    (11, 13), (13, 15),                  # Left leg
    (12, 14), (14, 16),                  # Right leg
]


@dataclass
class PoseAction:
    action_type: str        # "FALL_DETECTED" | "CRAWLING" | "HANDS_RAISED" | "NORMAL"
    confidence: float
    description: str
    keypoints: Optional[np.ndarray] = None  # (17, 2)
    keypoint_confs: Optional[np.ndarray] = None # (17,)


class PoseActionEngine:
    def __init__(self, model_path: str = "ai_engine/models/yolov8n-pose.pt"):
        self.model_path = model_path
        self._model = None
        self._available = False
        self._last_run_time: dict[int, float] = {}  # track_id -> last_eval_time
        self._cached_actions: dict[int, PoseAction] = {}

        if not os.path.exists(self.model_path) and os.path.exists("backend/" + self.model_path):
            self.model_path = "backend/" + self.model_path
        elif not os.path.exists(self.model_path) and os.path.exists("yolov8n-pose.pt"):
            self.model_path = "yolov8n-pose.pt"

        try:
            from ultralytics import YOLO
            self._model = YOLO(self.model_path)
            self._available = True
            logger.info(f"PoseActionEngine initialized with {self.model_path}")
        except Exception as e:
            logger.warning(f"PoseActionEngine unavailable: {e}")

    @property
    def is_available(self) -> bool:
        return self._available

    def evaluate_person(self, frame: np.ndarray, bbox: tuple, track_id: int) -> Optional[PoseAction]:
        """
        Runs gated pose estimation on a person crop with rate-limiting (~2Hz per track).
        Returns the recognized action and keypoints.
        """
        if not self._available or self._model is None:
            return None

        now = time.time()
        # Rate limit to ~2-3 evaluations per second per person to conserve CPU
        if track_id in self._cached_actions and (now - self._last_run_time.get(track_id, 0) < 0.45):
            return self._cached_actions[track_id]

        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1 - 10), max(0, y1 - 10)
        x2, y2 = min(w, x2 + 10), min(h, y2 + 10)

        if x2 - x1 < 30 or y2 - y1 < 30:
            return None

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        try:
            # Predict pose at fast resolution
            res = self._model.predict(crop, imgsz=256, verbose=False)
            if not res or len(res[0].keypoints) == 0:
                return None

            kpts = res[0].keypoints.xy.cpu().numpy()[0]   # (17, 2) in crop coords
            kconf = res[0].keypoints.conf.cpu().numpy()[0] if res[0].keypoints.conf is not None else np.ones(17)

            # Map back to original frame coordinates
            kpts_full = kpts.copy()
            kpts_full[:, 0] += x1
            kpts_full[:, 1] += y1

            action = self._classify_kinematics(kpts_full, kconf, bbox)
            action.keypoints = kpts_full
            action.keypoint_confs = kconf

            self._cached_actions[track_id] = action
            self._last_run_time[track_id] = now
            return action
        except Exception as e:
            logger.debug(f"Pose evaluation error on track {track_id}: {e}")
            return None

    def _classify_kinematics(self, kpts: np.ndarray, confs: np.ndarray, bbox: tuple) -> PoseAction:
        """
        Deterministic biomechanical classification over 17 body keypoints.
        """
        x1, y1, x2, y2 = bbox
        bw = max(1.0, x2 - x1)
        bh = max(1.0, y2 - y1)
        aspect = bh / bw

        # 1. Hands-Up / Surrender Check
        # Wrists (9, 10) higher than head (0) and shoulders (5, 6)
        l_wrist_y = kpts[9, 1] if confs[9] > 0.35 else 9999
        r_wrist_y = kpts[10, 1] if confs[10] > 0.35 else 9999
        nose_y = kpts[0, 1] if confs[0] > 0.35 else (y1 + bh * 0.2)
        shoulders_y = (kpts[5, 1] + kpts[6, 1]) / 2.0 if (confs[5] > 0.3 and confs[6] > 0.3) else (y1 + bh * 0.3)

        hands_above_head = (l_wrist_y < nose_y and r_wrist_y < nose_y)
        hands_above_shoulders = (l_wrist_y < shoulders_y and r_wrist_y < shoulders_y)

        if hands_above_head or (hands_above_shoulders and aspect > 1.2):
            return PoseAction(
                action_type="HANDS_RAISED",
                confidence=0.89,
                description="Person Hands Raised (Surrender / Compliance)",
            )

        # 2. Fall / Man-Down Check
        # A fallen person has a horizontal torso and low aspect ratio (width > height)
        sh_mid = (kpts[5] + kpts[6]) / 2.0
        hip_mid = (kpts[11] + kpts[12]) / 2.0
        torso_dx = abs(sh_mid[0] - hip_mid[0])
        torso_dy = abs(sh_mid[1] - hip_mid[1])

        # If torso is more horizontal than vertical, or aspect ratio < 0.8
        is_horizontal_torso = (torso_dx > torso_dy * 1.2) and (confs[5] > 0.3 and confs[11] > 0.3)
        is_flat_bbox = (aspect < 0.75)

        if is_horizontal_torso or is_flat_bbox:
            # Check if crawling or fallen
            ank_mid_y = (kpts[15, 1] + kpts[16, 1]) / 2.0 if (confs[15] > 0.25 and confs[16] > 0.25) else y2
            if abs(sh_mid[1] - ank_mid_y) < (bh * 0.45) or is_flat_bbox:
                return PoseAction(
                    action_type="FALL_DETECTED",
                    confidence=0.92,
                    description="⚠️ MAN-DOWN / FALL DETECTED (Horizontal posture)",
                )

        # 3. Crawling / Prone Infiltration Check
        # Person is low to ground, aspect ratio between 0.75 and 1.1 with horizontal body
        if aspect < 1.05 and torso_dx > (bh * 0.4):
            return PoseAction(
                action_type="CRAWLING",
                confidence=0.85,
                description="⚠️ CRAWLING / PRONE INFILTRATION (Low profile posture)",
            )

        return PoseAction(
            action_type="NORMAL",
            confidence=0.80,
            description="Upright Locomotion (Walking/Standing)",
        )

    def draw_skeleton(self, frame: np.ndarray, action: PoseAction) -> np.ndarray:
        """
        Draws glowing cyber-tactical skeleton bones and keypoints onto the frame.
        """
        if action.keypoints is None or action.keypoint_confs is None:
            return frame

        kpts = action.keypoints
        confs = action.keypoint_confs

        # Neon Cyan / Tactical Amber bones
        bone_color = (0, 255, 230) if action.action_type == "NORMAL" else (
            (0, 60, 255) if action.action_type == "FALL_DETECTED" else (0, 180, 255)
        )

        for p1, p2 in SKELETON_CONNECTIONS:
            if confs[p1] > 0.35 and confs[p2] > 0.35:
                pt1 = (int(kpts[p1, 0]), int(kpts[p1, 1]))
                pt2 = (int(kpts[p2, 0]), int(kpts[p2, 1]))
                cv2.line(frame, pt1, pt2, bone_color, 2, cv2.LINE_AA)

        # Draw joints for body skeleton (5..16: shoulders to ankles), skipping face keypoints
        n_kpts = min(17, len(confs), len(kpts))
        for i in range(5, n_kpts):
            if confs[i] > 0.35:
                pt = (int(kpts[i, 0]), int(kpts[i, 1]))
                cv2.circle(frame, pt, 3, (255, 255, 255), -1, cv2.LINE_AA)
                cv2.circle(frame, pt, 4, bone_color, 1, cv2.LINE_AA)

        return frame
