"""
AlertEngine — turns raw Events into operator-facing Alerts with a lifecycle.
This is deliberately decision-support only: it never takes automated action
(no auto-dispatch, no auto-lockdown). It creates a record for a human to review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable
import time
import uuid

from ai_engine.events.event_engine import Event, EventType, Severity


class AlertStatus(str, Enum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


# Which event types actually warrant an operator-facing alert
ALERTABLE_EVENT_TYPES = {
    EventType.AUTHORIZED_ACCESS,
    EventType.ZONE_INTRUSION,
    EventType.UNAUTHORIZED_WRONG_ZONE,
    EventType.UNAUTHORIZED_UNKNOWN,
    EventType.LOW_CONFIDENCE_VERIFICATION,
    EventType.ABANDONED_OBJECT,
    EventType.OBJECT_UNATTENDED,
    EventType.LOITERING,
    EventType.REPEATED_APPROACH,
    EventType.GROUP_FORMATION,
    EventType.PROLONGED_CONGREGATION,
    EventType.WATCHLIST_VEHICLE,
    EventType.UNAUTHORIZED_DRIVER,
    EventType.AFTER_HOURS_PRESENCE,
    EventType.NIGHT_MOVEMENT,
    EventType.CAMERA_OFFLINE,
    EventType.BEHAVIORAL_ANOMALY,
    EventType.WEAPON_DETECTED,
    EventType.UNUSUAL_MOVEMENT,
    EventType.REPEATED_OBSERVATION,
    # New upgraded events
    EventType.UNKNOWN_FACE_RESTRICTED,
    EventType.DISGUISE_DETECTED,
    EventType.CROWD_SURGE,
    EventType.MOB_ASSEMBLY,
    EventType.VEHICLE_RECONNAISSANCE,
    EventType.VEHICLE_SPEED_ALERT,
    EventType.NIGHT_TORCH_DETECTED,
    EventType.FALL_DETECTED,
    EventType.CRAWLING_INTRUSION,
}



@dataclass
class BehavioralEvidenceMsg:
    timestamp: float
    event_type: str
    description: str


@dataclass
class Alert:
    alert_id: str
    event_id: str
    event_type: EventType
    camera_id: str
    confidence: float
    description: str
    location: Optional[str] = None
    zone_id: Optional[str] = None
    track_id: Optional[int] = None
    severity: Severity = Severity.GREEN
    risk_score: int = 0
    behavioral_evidence: list[dict] = field(default_factory=list)
    snapshot_path: Optional[str] = None
    video_clip_path: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    status: AlertStatus = AlertStatus.NEW
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[float] = None
    metadata: dict = field(default_factory=dict)
    person_name: Optional[str] = None
    person_role: Optional[str] = None
    display_name: Optional[str] = None


class AlertEngine:
    """
    In-memory alert store for the live pipeline (mirrored to MongoDB by the
    backend's persistence layer — see backend/app/services/alert_service.py).
    Dedupes so the same track/event-type doesn't spam a new alert every frame.
    """

    DEDUPE_WINDOW_SECONDS = 60.0

    def __init__(self, on_new_alert: Optional[Callable[[Alert], None]] = None):
        self.alerts: dict[str, Alert] = {}
        self._recent_keys: dict[str, float] = {}  # dedupe_key -> last_fired_time
        self.on_new_alert = on_new_alert  # hook for WebSocket broadcast

    def _dedupe_key(self, event: Event) -> str:
        if event.event_type == EventType.WEAPON_DETECTED:
            return f"weapon:{event.camera_id}"
        if event.event_type == EventType.AUTHORIZED_ACCESS:
            p_id = event.metadata.get("identity_id") or event.metadata.get("person_name") or event.track_id
            return f"auth:{p_id}:{event.camera_id}"
        return f"{event.track_id}:{event.event_type.value}:{event.zone_id}"

    def process_event(self, event: Event, camera_location: Optional[str] = None,
                       snapshot_path: Optional[str] = None) -> Optional[Alert]:
        if event.event_type not in ALERTABLE_EVENT_TYPES:
            return None  # routine event (e.g. AUTHORIZED_ACCESS) — logged elsewhere, no alert noise

        key = self._dedupe_key(event)
        last_fired = self._recent_keys.get(key)
        now = time.time()

        # Strict deduplication across all alertable events to eliminate alert flooding
        if last_fired is not None and (now - last_fired) < self.DEDUPE_WINDOW_SECONDS:
            return None

        self._recent_keys[key] = now

        # Prune stale keys periodically
        if len(self._recent_keys) > 200:
            self._recent_keys = {k: t for k, t in self._recent_keys.items() if (now - t) < 120.0}

        evidence = [
            {
                "timestamp": ev.timestamp,
                "event_type": ev.event_type,
                "description": ev.description
            } for ev in getattr(event, 'behavioral_evidence', [])
        ]

        meta = getattr(event, 'metadata', {}) or {}
        # Strict Severity Policy: ONLY lethal weapons (Gun, Knife) are permitted to produce Severity.RED.
        # All other security and behavioral alerts are clamped to Severity.ORANGE or Severity.YELLOW.
        effective_severity = event.severity
        if effective_severity == Severity.RED and event.event_type != EventType.WEAPON_DETECTED:
            effective_severity = Severity.ORANGE

        alert = Alert(
            alert_id=str(uuid.uuid4()),
            event_id=event.event_id,
            event_type=event.event_type,
            camera_id=event.camera_id,
            location=camera_location,
            zone_id=event.zone_id,
            track_id=event.track_id,
            severity=effective_severity,
            risk_score=getattr(event, 'risk_score', 0),
            confidence=event.confidence,
            description=event.description,
            behavioral_evidence=evidence,
            snapshot_path=snapshot_path,
            timestamp=event.timestamp,
            metadata=meta,
            person_name=meta.get("person_name"),
            person_role=meta.get("person_role"),
            display_name=meta.get("display_name"),
        )
        self.alerts[alert.alert_id] = alert

        if self.on_new_alert:
            self.on_new_alert(alert)

        return alert

    def acknowledge(self, alert_id: str, operator: str) -> Optional[Alert]:
        alert = self.alerts.get(alert_id)
        if alert is None:
            return None
        alert.status = AlertStatus.ACKNOWLEDGED
        alert.acknowledged_by = operator
        return alert

    def resolve(self, alert_id: str, false_positive: bool = False) -> Optional[Alert]:
        alert = self.alerts.get(alert_id)
        if alert is None:
            return None
        alert.status = AlertStatus.FALSE_POSITIVE if false_positive else AlertStatus.RESOLVED
        alert.resolved_at = time.time()
        return alert

    def get_active_alerts(self) -> list[Alert]:
        return [a for a in self.alerts.values() if a.status in (AlertStatus.NEW, AlertStatus.ACKNOWLEDGED, AlertStatus.INVESTIGATING)]
