"""
IncidentEngine — Pillar 2: Incident Intelligence for Project Garuda.

Transforms individual camera observations:
OBSERVATION -> TRACK -> TIME -> SPACE -> BEHAVIOR -> OBJECT INTERACTION -> CROSS-CAMERA CONTEXT -> EVENT CORRELATION -> INCIDENT -> PRIORITY -> EXPLAINABLE ALERT

Key Capabilities:
1. Person-Object Interaction & Abandoned Object correlation:
   - Tracks person carrying object -> placing object -> spatial separation -> stationary threshold -> POTENTIAL_ABANDONED_OBJECT.
   - Non-alarmist, calibrated language: "Potential Abandoned Object — Verification Required".
2. Multi-Signal Incident Aggregator:
   - Combines multiple raw events (e.g., person detected + zone breach + perimeter approach + after-hours) into one cohesive Incident entity.
3. 6-Stage Incident Lifecycle:
   DETECTED -> CORRELATED -> PRIORITIZED -> ACKNOWLEDGED -> INVESTIGATED -> RESOLVED
4. Explainability Reasons Panel & Forensic Timeline:
   - Explicit checklist of why an incident was prioritized with supporting evidence timestamps.
"""

from __future__ import annotations

import time
import uuid
import math
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Dict, Set, Any

from ai_engine.events.event_engine import Event, EventType, Severity, TimelineItem

logger = logging.getLogger("garuda.incident_engine")


class IncidentType(str, Enum):
    POTENTIAL_ABANDONED_OBJECT = "potential_abandoned_object"
    RESTRICTED_ZONE_INTRUSION = "restricted_zone_intrusion"
    MULTI_POINT_PERIMETER_BREACH = "multi_point_perimeter_breach"
    SUSPICIOUS_LOITERING_RECONNAISSANCE = "suspicious_loitering_reconnaissance"
    WATCHLIST_VEHICLE_SURVEILLANCE = "watchlist_vehicle_surveillance"
    SUSPECT_HANDOVER_CONTINUATION = "suspect_handover_continuation"
    WEAPON_THREAT_EVENT = "weapon_threat_event"
    UNAUTHORIZED_ACCESS_ATTEMPT = "unauthorized_access_attempt"
    GENERAL_SECURITY_INCIDENT = "general_security_incident"


class IncidentStatus(str, Enum):
    DETECTED = "DETECTED"
    CORRELATED = "CORRELATED"
    PRIORITIZED = "PRIORITIZED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATED = "INVESTIGATED"
    RESOLVED = "RESOLVED"
    FALSE_ALARM = "FALSE_ALARM"


@dataclass
class ExplainabilitySignal:
    signal_name: str
    confidence: float
    description: str
    evidence_timestamp: float = field(default_factory=time.time)
    supporting_camera: str = ""

    def to_dict(self) -> dict:
        return {
            "signal_name": self.signal_name,
            "confidence": round(self.confidence, 3),
            "description": self.description,
            "evidence_timestamp": self.evidence_timestamp,
            "supporting_camera": self.supporting_camera,
        }


@dataclass
class Incident:
    incident_id: str
    incident_type: IncidentType
    title: str
    status: IncidentStatus
    priority_score: int  # 0 - 100
    severity: Severity
    start_time: float
    last_update_time: float
    cameras_involved: list[str] = field(default_factory=list)
    primary_track_ids: list[int] = field(default_factory=list)
    timeline: list[TimelineItem] = field(default_factory=list)
    explainability_signals: list[ExplainabilitySignal] = field(default_factory=list)
    evidence_snapshots: list[dict] = field(default_factory=list)
    operator_notes: Optional[str] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[float] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "incident_id": self.incident_id,
            "incident_type": self.incident_type.value,
            "title": self.title,
            "status": self.status.value,
            "priority_score": self.priority_score,
            "severity": self.severity.value,
            "start_time": self.start_time,
            "last_update_time": self.last_update_time,
            "cameras_involved": list(self.cameras_involved),
            "primary_track_ids": list(self.primary_track_ids),
            "timeline": [
                {"timestamp": t.timestamp, "event_type": t.event_type, "description": t.description}
                for t in self.timeline
            ],
            "explainability_signals": [s.to_dict() for s in self.explainability_signals],
            "evidence_snapshots": self.evidence_snapshots,
            "operator_notes": self.operator_notes,
            "acknowledged_by": self.acknowledged_by,
            "resolved_at": self.resolved_at,
            "metadata": self.metadata,
        }


class PersonObjectInteractionTracker:
    """
    Tracks relational state between persons and carried / placed objects.
    Fires explainable abandoned object events with confidence and separation metrics.
    """

    def __init__(
        self,
        association_dist_px: float = 120.0,
        separation_dist_px: float = 180.0,
        stationary_time_sec: float = 10.0,
    ):
        self.association_dist_px = association_dist_px
        self.separation_dist_px = separation_dist_px
        self.stationary_time_sec = stationary_time_sec

        # object_track_id -> {person_track_id, placed_time, last_pos, stationary_since}
        self.object_bindings: Dict[int, dict] = {}

    def update_associations(
        self,
        persons: list[dict],
        objects: list[dict],
        now: float,
        camera_id: str,
    ) -> list[dict]:
        """
        persons: [{"track_id": int, "bbox": [x1,y1,x2,y2], "pos": (cx, cy)}]
        objects: [{"track_id": int, "bbox": [x1,y1,x2,y2], "pos": (cx, cy), "label": str}]
        Returns list of newly triggered abandoned object notifications.
        """
        notifications = []

        for obj in objects:
            oid = obj["track_id"]
            opos = obj["pos"]

            if oid not in self.object_bindings:
                # Find closest person within association distance
                closest_pid = None
                min_dist = float("inf")
                for p in persons:
                    d = math.hypot(opos[0] - p["pos"][0], opos[1] - p["pos"][1])
                    if d < min_dist and d <= self.association_dist_px:
                        min_dist = d
                        closest_pid = p["track_id"]

                if closest_pid is not None:
                    self.object_bindings[oid] = {
                        "associated_person_id": closest_pid,
                        "initial_assoc_time": now,
                        "separation_time": None,
                        "stationary_since": now,
                        "last_pos": opos,
                        "camera_id": camera_id,
                        "alert_fired": False,
                    }
            else:
                binding = self.object_bindings[oid]
                pid = binding["associated_person_id"]

                # Check if object moved
                last_pos = binding["last_pos"]
                move_dist = math.hypot(opos[0] - last_pos[0], opos[1] - last_pos[1])
                if move_dist > 20.0:
                    binding["stationary_since"] = now
                    binding["last_pos"] = opos
                    binding["alert_fired"] = False

                # Find associated person's current position
                associated_person = next((p for p in persons if p["track_id"] == pid), None)
                if associated_person:
                    pdist = math.hypot(opos[0] - associated_person["pos"][0], opos[1] - associated_person["pos"][1])
                    if pdist > self.separation_dist_px:
                        if binding["separation_time"] is None:
                            binding["separation_time"] = now
                    else:
                        binding["separation_time"] = None  # Person returned
                else:
                    # Person left camera frame
                    if binding["separation_time"] is None:
                        binding["separation_time"] = now

                # Evaluate abandoned condition
                if binding["separation_time"] is not None and not binding["alert_fired"]:
                    stat_duration = now - binding["stationary_since"]
                    sep_duration = now - binding["separation_time"]
                    min_sep_sec = min(2.0, self.stationary_time_sec)
                    if stat_duration >= self.stationary_time_sec and sep_duration >= min_sep_sec:
                        binding["alert_fired"] = True
                        notifications.append({
                            "object_track_id": oid,
                            "person_track_id": pid,
                            "camera_id": camera_id,
                            "stationary_duration": round(stat_duration, 1),
                            "separation_duration": round(sep_duration, 1),
                            "position": opos,
                            "timestamp": now,
                        })

        return notifications


class IncidentEngine:
    """
    Correlates atomic events across space, time, and cameras into unified Incident entities.
    Provides explainable reasoning signals and lifecycle tracking.
    """

    INCIDENT_MERGE_TIME_WINDOW = 45.0  # seconds

    def __init__(self):
        self.active_incidents: Dict[str, Incident] = {}
        self.resolved_incidents: Dict[str, Incident] = {}
        self.interaction_tracker = PersonObjectInteractionTracker()

    def process_event(self, event: Event, snapshot_data: Optional[str] = None, sha256_hash: Optional[str] = None) -> Incident:
        """
        Ingests an atomic Event and associates it with an existing or new Incident.
        """
        now = event.timestamp
        matching_incident = self._find_matching_incident(event)

        if matching_incident is None:
            # Create a new correlated Incident
            incident_id = f"INC-{int(now)}-{uuid.uuid4().hex[:6].upper()}"
            incident_type = self._map_event_to_incident_type(event.event_type)
            title = self._generate_incident_title(incident_type, event)

            incident = Incident(
                incident_id=incident_id,
                incident_type=incident_type,
                title=title,
                status=IncidentStatus.CORRELATED if event.severity in (Severity.ORANGE, Severity.RED) else IncidentStatus.DETECTED,
                priority_score=event.risk_score,
                severity=event.severity,
                start_time=now,
                last_update_time=now,
                cameras_involved=[event.camera_id],
                primary_track_ids=[event.track_id] if event.track_id > 0 else [],
                timeline=[TimelineItem(timestamp=now, event_type=event.event_type.value, description=event.description)],
                explainability_signals=self._derive_explainability_signals(event),
                metadata=dict(event.metadata),
            )
            if snapshot_data:
                incident.evidence_snapshots.append({
                    "snapshot_data": snapshot_data,
                    "sha256_hash": sha256_hash or "",
                    "timestamp": now,
                    "camera_id": event.camera_id,
                })

            self.active_incidents[incident_id] = incident
            return incident
        else:
            # Update existing Incident
            matching_incident.last_update_time = now
            if event.camera_id not in matching_incident.cameras_involved:
                matching_incident.cameras_involved.append(event.camera_id)
            if event.track_id > 0 and event.track_id not in matching_incident.primary_track_ids:
                matching_incident.primary_track_ids.append(event.track_id)

            # Update priority score to highest observed
            matching_incident.priority_score = max(matching_incident.priority_score, event.risk_score)
            if event.severity == Severity.RED or (event.severity == Severity.ORANGE and matching_incident.severity != Severity.RED):
                matching_incident.severity = event.severity
                matching_incident.status = IncidentStatus.PRIORITIZED

            # Append to timeline
            matching_incident.timeline.append(
                TimelineItem(timestamp=now, event_type=event.event_type.value, description=event.description)
            )

            # Merge new explainability signals
            new_signals = self._derive_explainability_signals(event)
            existing_names = {s.signal_name for s in matching_incident.explainability_signals}
            for s in new_signals:
                if s.signal_name not in existing_names:
                    matching_incident.explainability_signals.append(s)

            if snapshot_data and len(matching_incident.evidence_snapshots) < 5:
                matching_incident.evidence_snapshots.append({
                    "snapshot_data": snapshot_data,
                    "sha256_hash": sha256_hash or "",
                    "timestamp": now,
                    "camera_id": event.camera_id,
                })

            return matching_incident

    def handle_abandoned_object_event(
        self,
        notification: dict,
        snapshot_data: Optional[str] = None,
        sha256_hash: Optional[str] = None,
    ) -> Incident:
        """Constructs an explainable potential abandoned object incident."""
        now = notification["timestamp"]
        incident_id = f"INC-ABN-{int(now)}-{uuid.uuid4().hex[:6].upper()}"

        signals = [
            ExplainabilitySignal(
                signal_name="Person-Object Association",
                confidence=0.92,
                description=f"Object #{notification['object_track_id']} previously carried by Person #{notification['person_track_id']}",
                evidence_timestamp=now,
                supporting_camera=notification["camera_id"],
            ),
            ExplainabilitySignal(
                signal_name="Spatial Separation",
                confidence=0.88,
                description=f"Person separated for {notification['separation_duration']}s without retrieval",
                evidence_timestamp=now,
                supporting_camera=notification["camera_id"],
            ),
            ExplainabilitySignal(
                signal_name="Stationary Persistence",
                confidence=0.95,
                description=f"Object remained motionless for {notification['stationary_duration']}s",
                evidence_timestamp=now,
                supporting_camera=notification["camera_id"],
            ),
        ]

        incident = Incident(
            incident_id=incident_id,
            incident_type=IncidentType.POTENTIAL_ABANDONED_OBJECT,
            title="Potential Abandoned Object — Verification Required",
            status=IncidentStatus.PRIORITIZED,
            priority_score=78,
            severity=Severity.ORANGE,
            start_time=now - notification["stationary_duration"],
            last_update_time=now,
            cameras_involved=[notification["camera_id"]],
            primary_track_ids=[notification["object_track_id"], notification["person_track_id"]],
            timeline=[
                TimelineItem(
                    timestamp=now - notification["stationary_duration"],
                    event_type="object_placed",
                    description=f"Object placed at coordinates {notification['position']}",
                ),
                TimelineItem(
                    timestamp=now - notification["separation_duration"],
                    event_type="person_separated",
                    description=f"Person #{notification['person_track_id']} moved away from object",
                ),
                TimelineItem(
                    timestamp=now,
                    event_type="abandoned_object_threshold_exceeded",
                    description="Stationary & separation thresholds exceeded",
                ),
            ],
            explainability_signals=signals,
            metadata={"position": notification["position"]},
        )

        if snapshot_data:
            incident.evidence_snapshots.append({
                "snapshot_data": snapshot_data,
                "sha256_hash": sha256_hash or "",
                "timestamp": now,
                "camera_id": notification["camera_id"],
            })

        self.active_incidents[incident_id] = incident
        return incident

    def _find_matching_incident(self, event: Event) -> Optional[Incident]:
        """Finds if this event belongs to an ongoing active incident within time/track/camera window."""
        now = event.timestamp
        for inc in self.active_incidents.values():
            if inc.status in (IncidentStatus.RESOLVED, IncidentStatus.FALSE_ALARM):
                continue

            # Check time proximity
            if now - inc.last_update_time > self.INCIDENT_MERGE_TIME_WINDOW:
                continue

            # Same track ID
            if event.track_id > 0 and event.track_id in inc.primary_track_ids:
                return inc

            # Same camera and overlapping zone
            if event.camera_id in inc.cameras_involved and event.zone_id and event.zone_id == inc.metadata.get("zone_id"):
                return inc

        return None

    def _map_event_to_incident_type(self, et: EventType) -> IncidentType:
        if et in (EventType.ZONE_INTRUSION, EventType.UNAUTHORIZED_WRONG_ZONE, EventType.UNAUTHORIZED_UNKNOWN):
            return IncidentType.RESTRICTED_ZONE_INTRUSION
        elif et == EventType.WEAPON_DETECTED:
            return IncidentType.WEAPON_THREAT_EVENT
        elif et in (EventType.ABANDONED_OBJECT, EventType.OBJECT_UNATTENDED):
            return IncidentType.POTENTIAL_ABANDONED_OBJECT
        elif et in (EventType.LOITERING, EventType.PROLONGED_STANDING, EventType.REPEATED_APPROACH):
            return IncidentType.SUSPICIOUS_LOITERING_RECONNAISSANCE
        elif et in (EventType.WATCHLIST_VEHICLE, EventType.VEHICLE_RECONNAISSANCE):
            return IncidentType.WATCHLIST_VEHICLE_SURVEILLANCE
        return IncidentType.GENERAL_SECURITY_INCIDENT

    def _generate_incident_title(self, itype: IncidentType, event: Event) -> str:
        if itype == IncidentType.RESTRICTED_ZONE_INTRUSION:
            return f"Restricted Zone Intrusion — {event.zone_id or 'Perimeter'}"
        elif itype == IncidentType.WEAPON_THREAT_EVENT:
            return "Visual Threat Alert — Possible Weapon Verification Required"
        elif itype == IncidentType.POTENTIAL_ABANDONED_OBJECT:
            return "Potential Abandoned Object — Verification Required"
        elif itype == IncidentType.SUSPICIOUS_LOITERING_RECONNAISSANCE:
            return "Persistent Loitering & Approach Pattern"
        elif itype == IncidentType.WATCHLIST_VEHICLE_SURVEILLANCE:
            return "Flagged Watchlist Vehicle Detected"
        return f"Correlated Security Incident ({event.event_type.value})"

    def _derive_explainability_signals(self, event: Event) -> list[ExplainabilitySignal]:
        signals = []
        now = event.timestamp
        cam = event.camera_id

        if event.zone_id:
            signals.append(ExplainabilitySignal(
                signal_name="Restricted Zone Breach",
                confidence=event.confidence,
                description=f"Subject entered monitored zone '{event.zone_id}'",
                evidence_timestamp=now,
                supporting_camera=cam,
            ))

        if event.event_type in (EventType.NIGHT_MOVEMENT, EventType.AFTER_HOURS_PRESENCE):
            signals.append(ExplainabilitySignal(
                signal_name="After-Hours Operational Window",
                confidence=0.90,
                description="Activity observed outside authorized working hours",
                evidence_timestamp=now,
                supporting_camera=cam,
            ))

        if event.event_type == EventType.REPEATED_APPROACH:
            signals.append(ExplainabilitySignal(
                signal_name="Perimeter Approach Pattern",
                confidence=0.85,
                description="Repeated boundary approach vectors detected",
                evidence_timestamp=now,
                supporting_camera=cam,
            ))

        if event.event_type == EventType.WEAPON_DETECTED:
            signals.append(ExplainabilitySignal(
                signal_name="Weapon Visual Signature",
                confidence=event.confidence,
                description=f"Weapon-class detector triggered with confidence {round(event.confidence * 100, 1)}%",
                evidence_timestamp=now,
                supporting_camera=cam,
            ))

        if not signals:
            signals.append(ExplainabilitySignal(
                signal_name="Behavioral Persistence",
                confidence=event.confidence,
                description=event.description,
                evidence_timestamp=now,
                supporting_camera=cam,
            ))

        return signals

    def acknowledge_incident(self, incident_id: str, operator_username: str) -> Optional[Incident]:
        inc = self.active_incidents.get(incident_id)
        if inc:
            inc.status = IncidentStatus.ACKNOWLEDGED
            inc.acknowledged_by = operator_username
            inc.last_update_time = time.time()
        return inc

    def resolve_incident(self, incident_id: str, operator_notes: Optional[str] = None, is_false_alarm: bool = False) -> Optional[Incident]:
        inc = self.active_incidents.pop(incident_id, None)
        if inc:
            inc.status = IncidentStatus.FALSE_ALARM if is_false_alarm else IncidentStatus.RESOLVED
            inc.operator_notes = operator_notes
            inc.resolved_at = time.time()
            inc.last_update_time = time.time()
            self.resolved_incidents[incident_id] = inc
        return inc

    def get_active_incidents(self) -> list[Incident]:
        return list(self.active_incidents.values())


# Singleton instance
incident_engine = IncidentEngine()
