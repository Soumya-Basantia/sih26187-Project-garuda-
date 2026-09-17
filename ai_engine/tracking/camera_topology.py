"""
CameraTopologyEngine — Cross-Camera Spatial-Temporal Correlation & Handover.

Transforms isolated camera detections:
CAM 01: Person #12 detected (Heading East)
↓
Expected transit window [8s - 25s]
↓
CAM 02: Candidate Track #87 detected (Entering from West)
↓
POSSIBLE CONTINUATION OF TRACK #12 (Confidence: 0.89)

Key Features:
1. Multi-camera topological adjacency graph (nodes, transit vectors, expected arrival windows).
2. Probabilistic candidate handover scoring:
   P_handover = w_t * S_time + w_d * S_direction + w_a * S_appearance
3. Non-speculative, calibrated evidence: preserves uncertainty and avoids false claims of absolute cross-camera identity.
"""

from __future__ import annotations

import time
import math
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any

logger = logging.getLogger("garuda.camera_topology")


@dataclass
class CameraNode:
    camera_id: str
    name: str
    ground_pos_m: Tuple[float, float]  # (X, Y) in meters
    orientation_deg: float  # 0 to 360 degrees
    fov_deg: float = 90.0


@dataclass
class TransitionEdge:
    from_camera_id: str
    to_camera_id: str
    min_transit_time_sec: float
    max_transit_time_sec: float
    distance_m: float
    expected_direction: Tuple[float, float] = (1.0, 0.0)


@dataclass
class DepartedTrackRecord:
    track_id: int
    camera_id: str
    departure_time: float
    ground_exit_pos: Tuple[float, float]
    velocity_mps: float
    heading_vector: Tuple[float, float]
    appearance_tag: Optional[str] = None
    color_hist: Optional[Any] = None
    risk_score: int = 0


@dataclass
class HandoverMatch:
    source_track_id: int
    candidate_track_id: int
    from_camera_id: str
    to_camera_id: str
    handover_confidence: float  # 0.0 to 1.0
    elapsed_time_sec: float
    expected_transit_sec: float
    explanation: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "source_track_id": self.source_track_id,
            "candidate_track_id": self.candidate_track_id,
            "from_camera_id": self.from_camera_id,
            "to_camera_id": self.to_camera_id,
            "handover_confidence": round(self.handover_confidence, 3),
            "elapsed_time_sec": round(self.elapsed_time_sec, 1),
            "expected_transit_sec": round(self.expected_transit_sec, 1),
            "explanation": self.explanation,
            "timestamp": self.timestamp,
        }


class CameraTopologyEngine:
    """
    Manages camera adjacency topology and computes cross-camera track handover candidate scores.
    """

    def __init__(self):
        self.nodes: Dict[str, CameraNode] = {}
        self.edges: List[TransitionEdge] = []
        self.departed_tracks: List[DepartedTrackRecord] = []
        self.active_handovers: List[HandoverMatch] = []
        self._init_default_topology()

    def _init_default_topology(self):
        """Initializes standard defense perimeter topology."""
        self.add_camera("CAM-01", "Perimeter South Gate", (0.0, 0.0), 45.0)
        self.add_camera("CAM-02", "Access Road East", (35.0, 15.0), 90.0)
        self.add_camera("CAM-03", "Main Checkpoint Plaza", (70.0, 30.0), 120.0)
        self.add_camera("CAM-04", "Restricted Armory Sector", (110.0, 45.0), 180.0)

        # Connect adjacent paths
        self.add_transition("CAM-01", "CAM-02", min_time=5.0, max_time=30.0, distance_m=38.0, direction=(1.0, 0.4))
        self.add_transition("CAM-02", "CAM-03", min_time=5.0, max_time=30.0, distance_m=38.0, direction=(1.0, 0.4))
        self.add_transition("CAM-03", "CAM-04", min_time=6.0, max_time=35.0, distance_m=42.0, direction=(1.0, 0.3))

    def add_camera(self, camera_id: str, name: str, ground_pos: Tuple[float, float], orientation_deg: float):
        self.nodes[camera_id] = CameraNode(camera_id, name, ground_pos, orientation_deg)

    def add_transition(
        self,
        from_cam: str,
        to_cam: str,
        min_time: float,
        max_time: float,
        distance_m: float,
        direction: Tuple[float, float] = (1.0, 0.0),
    ):
        self.edges.append(TransitionEdge(from_cam, to_cam, min_time, max_time, distance_m, direction))

    def record_track_departure(
        self,
        track_id: int,
        camera_id: str,
        exit_pos: Tuple[float, float],
        velocity_mps: float = 1.4,  # standard walking speed ~1.4 m/s (5 km/h)
        heading_vector: Tuple[float, float] = (1.0, 0.0),
        appearance_tag: Optional[str] = None,
        risk_score: int = 0,
        now: Optional[float] = None,
    ):
        """Called when a tracked target exits a camera's field of view."""
        t = now or time.time()
        # Clean up tracks older than 60s
        self.departed_tracks = [d for d in self.departed_tracks if t - d.departure_time <= 60.0]

        record = DepartedTrackRecord(
            track_id=track_id,
            camera_id=camera_id,
            departure_time=t,
            ground_exit_pos=exit_pos,
            velocity_mps=max(0.5, velocity_mps),
            heading_vector=heading_vector,
            appearance_tag=appearance_tag,
            risk_score=risk_score,
        )
        self.departed_tracks.append(record)
        logger.info(f"Recorded track #{track_id} departure from {camera_id} at t={t:.1f}")

    def evaluate_candidate_arrival(
        self,
        candidate_track_id: int,
        camera_id: str,
        entry_pos: Tuple[float, float],
        heading_vector: Tuple[float, float] = (1.0, 0.0),
        appearance_tag: Optional[str] = None,
        now: Optional[float] = None,
    ) -> Optional[HandoverMatch]:
        """
        Evaluates whether a newly appearing track on `camera_id` is a probable continuation
        of a track that recently departed an adjacent camera.
        """
        t = now or time.time()
        best_match: Optional[HandoverMatch] = None
        best_score = 0.0

        for dep in self.departed_tracks:
            if dep.camera_id == camera_id:
                continue  # Same camera

            # Find transition edge
            edge = next(
                (e for e in self.edges if e.from_camera_id == dep.camera_id and e.to_camera_id == camera_id),
                None,
            )
            if not edge:
                continue

            elapsed = t - dep.departure_time
            if elapsed < (edge.min_transit_time_sec * 0.6) or elapsed > (edge.max_transit_time_sec * 1.5):
                continue

            # 1. Temporal Score
            nominal_time = edge.distance_m / max(0.8, dep.velocity_mps)
            time_err = abs(elapsed - nominal_time)
            temporal_score = max(0.0, 1.0 - (time_err / max(nominal_time, 10.0)))

            # 2. Directional Consistency
            dot_prod = (
                dep.heading_vector[0] * edge.expected_direction[0]
                + dep.heading_vector[1] * edge.expected_direction[1]
            )
            dir_score = max(0.0, min(1.0, 0.5 + 0.5 * dot_prod))

            # 3. Appearance Consistency (if available)
            app_score = 0.7  # neutral default
            if dep.appearance_tag and appearance_tag:
                app_score = 1.0 if dep.appearance_tag.lower() == appearance_tag.lower() else 0.3

            # Combined Handover Probability
            total_score = (0.45 * temporal_score) + (0.30 * dir_score) + (0.25 * app_score)

            if total_score > 0.65 and total_score > best_score:
                best_score = total_score
                explanation = (
                    f"Possible continuation of Track #{dep.track_id} from {dep.camera_id} "
                    f"(Transit: {elapsed:.1f}s, Spatial-Temporal Confidence: {int(total_score * 100)}%)"
                )
                best_match = HandoverMatch(
                    source_track_id=dep.track_id,
                    candidate_track_id=candidate_track_id,
                    from_camera_id=dep.camera_id,
                    to_camera_id=camera_id,
                    handover_confidence=total_score,
                    elapsed_time_sec=elapsed,
                    expected_transit_sec=nominal_time,
                    explanation=explanation,
                    timestamp=t,
                )

        if best_match:
            self.active_handovers.append(best_match)
            # Retain only last 50 handovers
            if len(self.active_handovers) > 50:
                self.active_handovers.pop(0)

        return best_match


# Singleton instance
camera_topology_engine = CameraTopologyEngine()
