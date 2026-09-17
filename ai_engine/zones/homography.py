"""
3D Ground-Plane Homography & Metric Metrology Engine.

Transforms 2D camera pixel coordinates into true real-world ground meters (X, Y)
and computes physical intruder velocity in km/h using perspective transformation.

Addresses the critical border surveillance gap:
- 2D pixel coordinates cannot determine if an intruder is 50 meters outside
  the fence or touching the perimeter wire.
- Perspective distortion causes 100 pixels near the camera to represent 1 meter,
  while 100 pixels in the distance represents 20+ meters.
"""

from __future__ import annotations

import math
from typing import List, Tuple, Optional, Dict
import cv2
import numpy as np


class HomographyEngine:
    """
    Computes real-world ground-plane metric projection (meters) and velocity (km/h)
    from 2D camera coordinates using a 4-point perspective transform.
    """

    def __init__(
        self,
        camera_id: str = "default",
        frame_width: int = 1280,
        frame_height: int = 720,
        custom_src_points: Optional[List[Tuple[float, float]]] = None,
        custom_dst_points: Optional[List[Tuple[float, float]]] = None,
    ):
        self.camera_id = camera_id
        self.frame_width = frame_width
        self.frame_height = frame_height

        self.src_points: np.ndarray
        self.dst_points: np.ndarray
        self.H: Optional[np.ndarray] = None
        self.H_inv: Optional[np.ndarray] = None

        if custom_src_points and custom_dst_points and len(custom_src_points) == 4 and len(custom_dst_points) == 4:
            self.set_calibration(custom_src_points, custom_dst_points)
        else:
            self._set_default_border_calibration()

    def _set_default_border_calibration(self):
        """
        Sets a realistic default ground plane calibration based on standard
        border fence CCTV geometry (camera mounted at 4-6m height on pole/tower,
        looking across a 30m wide by 35m deep perimeter corridor).
        """
        w, h = float(self.frame_width), float(self.frame_height)

        # 4 Source pixel points in camera perspective view:
        # Top-Left, Top-Right, Bottom-Right, Bottom-Left
        src = np.array([
            [0.22 * w, 0.42 * h],  # Far left fence line
            [0.78 * w, 0.42 * h],  # Far right fence line
            [0.92 * w, 0.94 * h],  # Near right foreground
            [0.08 * w, 0.94 * h],  # Near left foreground
        ], dtype=np.float32)

        # 4 Destination ground points in real METERS:
        # Coordinate system: X = lateral (-15m to +15m), Y = forward distance (3m to 35m)
        dst = np.array([
            [-15.0, 35.0],  # Far left (35 meters out)
            [15.0, 35.0],   # Far right (35 meters out)
            [10.0, 3.0],    # Near right (3 meters out)
            [-10.0, 3.0],   # Near left (3 meters out)
        ], dtype=np.float32)

        self.src_points = src
        self.dst_points = dst
        self._compute_matrices()

    def set_calibration(
        self,
        src_points: List[Tuple[float, float]],
        dst_points: List[Tuple[float, float]]
    ) -> bool:
        """
        Sets custom 4-point ground calibration points.
        src_points: 4 (x, y) coordinates in pixel space.
        dst_points: 4 (x, y) coordinates in real meters.
        """
        if len(src_points) != 4 or len(dst_points) != 4:
            return False

        self.src_points = np.array(src_points, dtype=np.float32)
        self.dst_points = np.array(dst_points, dtype=np.float32)
        return self._compute_matrices()

    def _compute_matrices(self) -> bool:
        try:
            self.H = cv2.getPerspectiveTransform(self.src_points, self.dst_points)
            self.H_inv = cv2.getPerspectiveTransform(self.dst_points, self.src_points)
            return True
        except Exception as e:
            # Fallback if points are collinear or invalid
            self.H = None
            self.H_inv = None
            return False

    def pixel_to_ground(self, point: Tuple[float, float]) -> Tuple[float, float]:
        """
        Transforms 2D pixel coordinate (u, v) to real-world ground meters (X, Y).
        """
        if self.H is None:
            # Fallback linear approximation if matrix not computed
            return (point[0] * 0.02, point[1] * 0.05)

        px = np.array([[[point[0], point[1]]]], dtype=np.float32)
        ground_pt = cv2.perspectiveTransform(px, self.H)
        gx = float(ground_pt[0][0][0])
        gy = float(ground_pt[0][0][1])
        return round(gx, 2), round(gy, 2)

    def ground_to_pixel(self, ground_point: Tuple[float, float]) -> Tuple[float, float]:
        """
        Transforms real-world ground meters (X, Y) back to 2D pixel space (u, v).
        """
        if self.H_inv is None:
            return (ground_point[0] * 50.0, ground_point[1] * 20.0)

        gpt = np.array([[[ground_point[0], ground_point[1]]]], dtype=np.float32)
        px_pt = cv2.perspectiveTransform(gpt, self.H_inv)
        u = float(px_pt[0][0][0])
        v = float(px_pt[0][0][1])
        return round(u, 1), round(v, 1)

    def distance_meters(self, pt1: Tuple[float, float], pt2: Tuple[float, float]) -> float:
        """
        Calculates physical Euclidean distance in meters between two ground points.
        """
        dx = pt1[0] - pt2[0]
        dy = pt1[1] - pt2[1]
        return round(math.hypot(dx, dy), 2)

    def distance_to_polygon_meters(
        self,
        foot_pixel: Tuple[float, float],
        polygon_pixels: List[Tuple[float, float]]
    ) -> float:
        """
        Calculates true metric distance in meters from a foot point to the nearest
        edge of a polygon (e.g. Zero-Line fence boundary).
        """
        if not polygon_pixels or len(polygon_pixels) < 2:
            return 999.0

        # Transform candidate foot point to ground meters
        gx, gy = self.pixel_to_ground(foot_pixel)
        foot_ground = (gx, gy)

        # Transform polygon vertices to ground meters
        poly_ground = [self.pixel_to_ground(pt) for pt in polygon_pixels]

        # Calculate minimum distance to polygon boundary in ground meters
        min_dist = float("inf")
        n = len(poly_ground)
        for i in range(n):
            p1 = poly_ground[i]
            p2 = poly_ground[(i + 1) % n]
            d = self._point_to_segment_distance(foot_ground, p1, p2)
            if d < min_dist:
                min_dist = d

        return round(min_dist, 2)

    def _point_to_segment_distance(
        self,
        p: Tuple[float, float],
        a: Tuple[float, float],
        b: Tuple[float, float]
    ) -> float:
        """Computes minimum distance from point p to line segment ab in meters."""
        ab = (b[0] - a[0], b[1] - a[1])
        ap = (p[0] - a[0], p[1] - a[1])
        ab_len_sq = ab[0]**2 + ab[1]**2

        if ab_len_sq < 1e-6:
            return math.hypot(ap[0], ap[1])

        # Project point p onto segment ab
        t = max(0.0, min(1.0, (ap[0] * ab[0] + ap[1] * ab[1]) / ab_len_sq))
        proj = (a[0] + t * ab[0], a[1] + t * ab[1])
        return math.hypot(p[0] - proj[0], p[1] - proj[1])

    def calculate_velocity_kmh(
        self,
        position_history: List[Tuple[float, Tuple[float, float]]],
        window_seconds: float = 1.5
    ) -> Tuple[float, str]:
        """
        Calculates metric speed in km/h over a rolling temporal window.
        Includes pixel deadband filtering and trajectory linearity checking
        to prevent camera shake and detection jitter from causing false speed readings.
        """
        if len(position_history) < 3:
            return 0.0, "STATIONARY"

        now = position_history[-1][0]
        latest_px = position_history[-1][1]

        # Find position closest to window_seconds ago
        target_time = now - window_seconds
        past_idx = 0
        past_entry = position_history[0]
        for idx in range(len(position_history) - 2, -1, -1):
            if position_history[idx][0] <= target_time:
                past_entry = position_history[idx]
                past_idx = idx
                break

        dt = now - past_entry[0]
        if dt < 0.25:  # Avoid division by micro-time
            return 0.0, "STATIONARY"

        # Check raw pixel displacement: if moved < 12 pixels across window, it's just detector jitter
        pixel_displacement = math.hypot(latest_px[0] - past_entry[1][0], latest_px[1] - past_entry[1][1])
        if pixel_displacement < 12.0:
            return 0.0, "STATIONARY"

        # Trajectory linearity & directionality check:
        # Camera shake causes rapid back-and-forth oscillation where total path length >> net displacement.
        # Genuine moving vehicles/persons have net_displacement / total_path_length >= 0.55.
        window_points = [p[1] for p in position_history[past_idx:]]
        if len(window_points) >= 4:
            total_path_px = 0.0
            for i in range(1, len(window_points)):
                total_path_px += math.hypot(
                    window_points[i][0] - window_points[i - 1][0],
                    window_points[i][1] - window_points[i - 1][1]
                )
            if total_path_px > 0:
                linearity_ratio = pixel_displacement / total_path_px
                # If linearity is low (< 0.50), the object is vibrating/oscillating in place (camera shake)
                if linearity_ratio < 0.50:
                    return 0.0, "STATIONARY"

        # Transform pixel positions to ground meters
        g_latest = self.pixel_to_ground(latest_px)
        g_past = self.pixel_to_ground(past_entry[1])

        # Distance moved in meters
        dist_m = self.distance_meters(g_latest, g_past)
        if dist_m < 0.6:  # Less than 60cm ground shift over window is considered stationary
            return 0.0, "STATIONARY"

        speed_mps = dist_m / dt
        speed_kmh = round(speed_mps * 3.6, 1)

        # Sanity check: If classified at high speed (> 30 km/h), vehicle must have traversed at least 3.0 meters
        # to rule out single-frame perspective projection jumps
        if speed_kmh > 30.0 and dist_m < 3.0:
            return 0.0, "STATIONARY"

        # Classify physical movement type
        if speed_kmh < 1.0:
            m_type = "STATIONARY"
            speed_kmh = 0.0
        elif speed_kmh < 3.0:
            m_type = "CRAWLING / CREEPING"
        elif speed_kmh < 6.5:
            m_type = "WALKING"
        elif speed_kmh < 20.0:
            m_type = "RUNNING"
        else:
            m_type = "VEHICULAR"

        return speed_kmh, m_type
