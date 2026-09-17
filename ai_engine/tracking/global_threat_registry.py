"""
GlobalThreatRegistry — Cross-Camera Continuity & Suspect Handover Engine.

Solves the multi-camera blind spot:
When a person is marked as SUSPICIOUS (ORANGE) or HIGH PRIORITY (RED) on Camera 1
and moves to Camera 2, their threat status and behavioral timeline are preserved.

Supports two correlation mechanisms:
1. Verified Identity Correlation: Links tracks sharing the same identity_id.
2. Spatial-Temporal & Visual Profile Handover (BOLO - Be On The Lookout):
   When an unknown suspect leaves a camera, their visual profile (color tag/clothing),
   accumulated risk score, and behavioral timeline are broadcasted to other cameras.
"""

from __future__ import annotations

import logging
import threading
import time
import cv2
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

logger = logging.getLogger("garude.threat_registry")


@dataclass
class SuspectProfile:
    """A cross-camera suspect profile holding full behavioral context."""
    global_suspect_id: str
    identity_id: Optional[str] = None
    identity_name: Optional[str] = None
    tag_color: Optional[str] = None
    clothing_descriptor: Optional[str] = None
    risk_score: int = 0
    severity: str = "GREEN"  # GREEN, YELLOW, ORANGE, RED
    last_seen_camera_id: str = ""
    last_seen_timestamp: float = field(default_factory=time.time)
    last_seen_position: tuple = (0, 0)
    timeline: list = field(default_factory=list)
    carried_objects: set = field(default_factory=set)
    visual_signature: Optional[Any] = None
    is_active_in_transit: bool = True  # True if departed last camera and seeking handover


class GlobalThreatRegistry:
    """
    Thread-safe global registry shared across all active CameraPipelines.
    """

    HANDOVER_EXPIRY_SECONDS = 90.0  # Time window to match a suspect moving between cameras

    def __init__(self):
        self._lock = threading.Lock()
        # Identity-based tracking: identity_id -> SuspectProfile
        self._identity_profiles: Dict[str, SuspectProfile] = {}
        # In-transit unknown suspects: list of SuspectProfile
        self._in_transit_suspects: List[SuspectProfile] = []

    def register_or_update_identity(
        self,
        identity_id: str,
        identity_name: str,
        camera_id: str,
        risk_score: int,
        severity: str,
        timeline: list,
        tag_color: Optional[str] = None
    ):
        """Update threat profile for a verified identity."""
        with self._lock:
            profile = self._identity_profiles.get(identity_id)
            if profile is None:
                profile = SuspectProfile(
                    global_suspect_id=f"suspect_id_{identity_id}",
                    identity_id=identity_id,
                    identity_name=identity_name,
                    tag_color=tag_color,
                    risk_score=risk_score,
                    severity=severity,
                    last_seen_camera_id=camera_id,
                    last_seen_timestamp=time.time(),
                    timeline=list(timeline)
                )
                self._identity_profiles[identity_id] = profile
            else:
                profile.risk_score = max(profile.risk_score, risk_score)
                profile.severity = severity
                profile.last_seen_camera_id = camera_id
                profile.last_seen_timestamp = time.time()
                profile.timeline = list(timeline)
                if tag_color:
                    profile.tag_color = tag_color

    def publish_suspect_departure(
        self,
        camera_id: str,
        track_id: int,
        risk_score: int,
        severity: str,
        timeline: list,
        tag_color: Optional[str] = None,
        identity_id: Optional[str] = None,
        identity_name: Optional[str] = None,
        carried_objects: Optional[set] = None,
        visual_signature: Optional[Any] = None
    ):
        """Called when a suspect leaves a camera frame to enable handover to adjacent cameras."""

        now = time.time()
        with self._lock:
            # If verified identity, update their registry record
            if identity_id:
                self.register_or_update_identity(
                    identity_id=identity_id,
                    identity_name=identity_name or "Unknown",
                    camera_id=camera_id,
                    risk_score=risk_score,
                    severity=severity,
                    timeline=timeline,
                    tag_color=tag_color
                )
                return

            # Unknown suspect: publish as an in-transit handover candidate
            candidate = SuspectProfile(
                global_suspect_id=f"suspect_track_{camera_id}_{track_id}_{int(now)}",
                tag_color=tag_color,
                risk_score=risk_score,
                severity=severity,
                last_seen_camera_id=camera_id,
                last_seen_timestamp=now,
                timeline=list(timeline),
                carried_objects=set(carried_objects or set()),
                visual_signature=visual_signature,
                is_active_in_transit=True
            )
            self._in_transit_suspects.append(candidate)
            logger.info(
                f"[GlobalThreatRegistry] BOLO Broadcast: Track #{track_id} from Camera {camera_id} "
                f"departed with Risk Score {risk_score} ({severity}). Tag: {tag_color}"
            )
            self._prune_expired()

    def query_handover_match(
        self,
        current_camera_id: str,
        tag_color: Optional[str] = None,
        identity_id: Optional[str] = None,
        visual_signature: Optional[Any] = None
    ) -> Optional[SuspectProfile]:
        """
        Check if a newly detected track on current_camera_id matches an existing suspect in transit.
        """
        now = time.time()
        with self._lock:
            self._prune_expired()

            # 1. Check Identity Match
            if identity_id and identity_id in self._identity_profiles:
                profile = self._identity_profiles[identity_id]
                logger.info(
                    f"[GlobalThreatRegistry] Identity Match: {profile.identity_name} "
                    f"spotted on {current_camera_id}, carrying forward Risk Score: {profile.risk_score}"
                )
                return profile

            # 2. Check In-Transit Visual Match
            # Look for recent departure from a DIFFERENT camera with matching tag color or within handover window
            for idx, candidate in enumerate(self._in_transit_suspects):
                if not candidate.is_active_in_transit:
                    continue
                if candidate.last_seen_camera_id == current_camera_id:
                    continue  # Came from another camera

                time_diff = now - candidate.last_seen_timestamp
                if time_diff > self.HANDOVER_EXPIRY_SECONDS:
                    continue

                visual_match = False
                if visual_signature is not None and candidate.visual_signature is not None:
                    dist = cv2.compareHist(visual_signature, candidate.visual_signature, cv2.HISTCMP_BHATTACHARYYA)
                    if dist < 0.4:
                        visual_match = True

                # Match criteria: matching tag color or recent general suspect departure
                color_match = (
                    tag_color and candidate.tag_color and
                    tag_color.lower() == candidate.tag_color.lower()
                )

                # If matching color, high confidence visual match, or high confidence spatial-temporal transition
                if visual_match or color_match or (candidate.tag_color is None and candidate.visual_signature is None and time_diff < 45.0):
                    candidate.is_active_in_transit = False  # Handover accepted
                    logger.info(
                        f"[GlobalThreatRegistry] Cross-Camera Suspect Handover Successful! "
                        f"Camera {candidate.last_seen_camera_id} → Camera {current_camera_id}. "
                        f"Inherited Risk Score: {candidate.risk_score} ({candidate.severity})"
                    )
                    return candidate

            return None

    def _prune_expired(self):
        """Remove in-transit suspect profiles older than expiry window."""
        now = time.time()
        self._in_transit_suspects = [
            s for s in self._in_transit_suspects
            if (now - s.last_seen_timestamp) < self.HANDOVER_EXPIRY_SECONDS
        ]
