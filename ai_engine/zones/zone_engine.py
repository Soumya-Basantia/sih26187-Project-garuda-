"""
ZoneEngine — pure geometry, no AI involved. Zones are polygons drawn by an
admin on a specific camera's frame; this module answers "is this point
inside this zone right now" and nothing more. All "restricted area" logic
lives here as deterministic checks, not learned behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time

import numpy as np
import cv2


class ZoneType(str, Enum):
    RESTRICTED = "restricted"
    HIGH_SECURITY = "high_security"
    MONITORED = "monitored"
    GENERAL = "general"
    ENTRY = "entry"
    EXIT = "exit"
    VEHICLE_ONLY = "vehicle_only"
    SENSITIVE = "sensitive"


@dataclass
class Zone:
    zone_id: str
    camera_id: str
    name: str
    zone_type: ZoneType
    polygon: list  # [(x, y), ...] pixel coordinates on this camera's frame
    threshold_seconds: float = 5.0
    enabled: bool = True
    active_hours: Optional[tuple] = None  # (start_hour, end_hour) 24h, e.g. (22, 6) for night-only
    # access control: empty list = open to everyone; otherwise only these identities are authorized
    authorized_identity_ids: list = field(default_factory=list)
    min_rank_stars: int = 0  # 0 = Open/Patrol, 1 = Guard, 2 = Duty Off., 3 = Field Off., 4 = Division Cmd, 5 = Supreme Command
    allow_escort: bool = False  # If True, lower ranks may enter if accompanied
    authority_custom_level: Optional[str] = None

    def is_rank_cleared(self, rank_stars: int, has_escort: bool = False) -> bool:
        if self.min_rank_stars <= 0:
            return True
        if rank_stars >= self.min_rank_stars:
            return True
        if self.allow_escort and has_escort:
            return True
        return False

    def contains_point(self, point: tuple) -> bool:
        if not self.enabled or len(self.polygon) < 3:
            return False
        poly_np = np.array(self.polygon, dtype=np.float32)
        result = cv2.pointPolygonTest(poly_np, point, False)
        return result >= 0

    def distance_to_point(self, point: tuple) -> float:
        """Returns distance in pixels from point to the zone polygon boundary. 0 if inside."""
        if not self.enabled or len(self.polygon) < 3:
            return float("inf")
        poly_np = np.array(self.polygon, dtype=np.float32)
        dist = cv2.pointPolygonTest(poly_np, (float(point[0]), float(point[1])), True)
        if dist >= 0:
            return 0.0
        return abs(dist)

    def distance_to_point_meters(self, point: tuple, homography: Optional[Any] = None) -> float:
        """Returns distance in real-world METERS from point to the zone boundary."""
        if not self.enabled or len(self.polygon) < 3:
            return float("inf")
        if self.contains_point(point):
            return 0.0
        if homography is not None:
            return homography.distance_to_polygon_meters(point, self.polygon)
        # Fallback approximate conversion (1 pixel ≈ 0.05m)
        return round(self.distance_to_point(point) * 0.05, 2)

    def is_active_now(self, hour: int) -> bool:
        """Some zones (night-movement) are only meaningful during a time window."""
        if self.active_hours is None:
            return True
        start, end = self.active_hours
        if start <= end:
            return start <= hour < end
        return hour >= start or hour < end  # wraps past midnight, e.g. (22, 6)

    def is_zone_open_access(self) -> bool:
        return len(self.authorized_identity_ids) == 0


from ai_engine.zones.homography import HomographyEngine


class ZoneEngine:
    """
    Holds all zones for all cameras in memory (loaded/synced from MongoDB),
    manages 3D ground-plane homography calibrations, and answers zone-membership
    and metric distance queries for tracked objects.
    """

    def __init__(self):
        self._zones_by_camera: dict[str, list[Zone]] = {}
        self._homography_by_camera: dict[str, HomographyEngine] = {}

    def get_homography(self, camera_id: str) -> HomographyEngine:
        if camera_id not in self._homography_by_camera:
            self._homography_by_camera[camera_id] = HomographyEngine(camera_id=camera_id)
        return self._homography_by_camera[camera_id]

    def set_homography_calibration(
        self,
        camera_id: str,
        src_points: list[tuple[float, float]],
        dst_points: list[tuple[float, float]]
    ) -> bool:
        engine = self.get_homography(camera_id)
        return engine.set_calibration(src_points, dst_points)

    def load_zones(self, zones: list[Zone]):
        self._zones_by_camera.clear()
        for z in zones:
            self._zones_by_camera.setdefault(z.camera_id, []).append(z)

    def get_zones_for_camera(self, camera_id: str) -> list[Zone]:
        return self._zones_by_camera.get(camera_id, [])

    def check_point(self, camera_id: str, point: tuple, current_hour: int) -> list[Zone]:
        """Returns every active, time-eligible zone that currently contains this point."""
        matches = []
        for zone in self.get_zones_for_camera(camera_id):
            if not zone.enabled:
                continue
            if not zone.is_active_now(current_hour):
                continue
            if zone.contains_point(point):
                matches.append(zone)
        return matches

    def distance_to_zone_meters(self, camera_id: str, zone: Zone, point: tuple) -> float:
        """Returns metric distance in meters from point to a zone boundary."""
        homography = self.get_homography(camera_id)
        return zone.distance_to_point_meters(point, homography)

    def calculate_velocity_kmh(self, camera_id: str, position_history: list) -> tuple[float, str]:
        """Calculates physical speed in km/h from trajectory position history."""
        homography = self.get_homography(camera_id)
        return homography.calculate_velocity_kmh(position_history)
