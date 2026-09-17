"""
TemporalEventEngine & BehavioralCorrelationEngine — SIH 260187 Core Intelligence.

Features:
1. 4-Level Severity System:
   🟢 GREEN   (Normal activity / Expected)
   🟡 YELLOW  (Attention / Unusual / Loitering / Minor anomaly)
   🟠 ORANGE  (Suspicious pattern / Multi-signal correlation)
   🔴 RED     (High priority security alert / Zone intrusion / Weapon / Breach)

2. Behavioral Timeline:
   Maintains a chronological trace of observable actions per tracked identity/person.

3. Explainable Risk Scoring (0 - 100):
   0-29   -> 🟢 NORMAL
   30-49  -> 🟡 ATTENTION
   50-74  -> 🟠 SUSPICIOUS PATTERN
   75-100 -> 🔴 HIGH PRIORITY
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, List, Any
import math
import time
import uuid


from ai_engine.zones.homography import HomographyEngine


class EventType(str, Enum):
    # Category A: Movement & Presence
    PERSON_DETECTED = "person_detected"
    VEHICLE_DETECTED = "vehicle_detected"
    NORMAL_WALKING = "normal_walking"
    PROLONGED_STANDING = "prolonged_standing"
    LOITERING = "loitering"
    UNUSUAL_MOVEMENT = "unusual_movement"
    REPEATED_APPROACH = "repeated_approach"
    ZONE_INTRUSION = "zone_intrusion"
    AFTER_HOURS_PRESENCE = "after_hours_presence"
    NIGHT_MOVEMENT = "night_movement"

    # Category B: Observation & Interaction
    REPEATED_OBSERVATION = "repeated_observation"
    PHONE_USAGE_PROLONGED = "phone_usage_prolonged"
    GROUP_FORMATION = "group_formation"
    PROLONGED_CONGREGATION = "prolonged_congregation"
    BEHAVIORAL_ANOMALY = "behavioral_anomaly"

    # Category C: Human + Object Interaction
    OBJECT_CARRIED = "object_carried"
    OBJECT_UNATTENDED = "object_unattended"
    ABANDONED_OBJECT = "abandoned_object"
    PROLONGED_PARKING = "prolonged_parking"
    UNAUTHORIZED_PARKING = "unauthorized_parking"
    WEAPON_DETECTED = "weapon_detected"

    # Category D: Security & Access Control
    UNAUTHORIZED_WRONG_ZONE = "unauthorized_wrong_zone"
    UNAUTHORIZED_UNKNOWN = "unauthorized_unknown"
    LOW_CONFIDENCE_VERIFICATION = "low_confidence_verification"
    AUTHORIZED_ACCESS = "authorized_access"
    CAMERA_OFFLINE = "camera_offline"
    WATCHLIST_VEHICLE = "watchlist_vehicle"
    UNAUTHORIZED_DRIVER = "unauthorized_driver"

    # Category E: Enhanced Face Intelligence (New — Upgrades face detection to Exceeds)
    UNKNOWN_FACE_RESTRICTED = "unknown_face_restricted"   # Unregistered face in HIGH_SECURITY / RESTRICTED zone
    DISGUISE_DETECTED = "disguise_detected"               # Mask / balaclava / heavy face cover near perimeter

    # Category F: Crowd Intelligence (New)
    CROWD_SURGE = "crowd_surge"                           # Sudden rise in person count in a zone
    MOB_ASSEMBLY = "mob_assembly"                         # Sustained high-density crowd in restricted area

    # Category G: Vehicle Intelligence Upgrades (New — Upgrades vehicle detection to Exceeds)
    VEHICLE_RECONNAISSANCE = "vehicle_reconnaissance"     # Vehicle passes same zone 3+ times (circling)
    VEHICLE_SPEED_ALERT = "vehicle_speed_alert"           # Vehicle exceeds safe speed near checkpoint

    # Category H: Night Intelligence Upgrades (New — Upgrades night detection to Exceeds)
    NIGHT_TORCH_DETECTED = "night_torch_detected"         # Moving bright point-source in dark frame (flashlight/torch)

    # Category I: Human Kinematic Action Intelligence (YOLOv8-Pose Estimation)
    FALL_DETECTED = "fall_detected"                       # Person collapsed / fallen down (Medical / Ambush emergency)
    CRAWLING_INTRUSION = "crawling_intrusion"             # Person crawling / prone under perimeter sensors
    HANDS_RAISED = "hands_raised"                         # Surrender / compliance posture


class Severity(str, Enum):
    GREEN = "GREEN"    # Normal / Expected
    YELLOW = "YELLOW"  # Attention / Unusual
    ORANGE = "ORANGE"  # Suspicious Pattern
    RED = "RED"        # High Priority Security Alert

    # Backward compatibility mappings
    LOW = "GREEN"
    MEDIUM = "YELLOW"
    HIGH = "RED"


class IdentityStatus(str, Enum):
    VERIFIED = "VERIFIED"
    UNKNOWN = "UNKNOWN"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    NOT_ATTEMPTED = "NOT_ATTEMPTED"


@dataclass
class TimelineItem:
    timestamp: float
    event_type: str
    description: str


@dataclass
class Event:
    event_id: str
    event_type: EventType
    track_id: int
    camera_id: str
    zone_id: Optional[str]
    timestamp: float
    severity: Severity
    confidence: float
    description: str
    risk_score: int = 0
    behavioral_evidence: list[TimelineItem] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class TrackState:
    """Persistent behavioral state maintained for a tracked entity."""
    track_id: int
    label: str
    camera_id: str
    first_seen: float
    last_seen: float
    last_position: tuple
    position_history: list = field(default_factory=list)  # [(t, (x,y)), ...]
    current_zone_ids: set = field(default_factory=set)
    zone_entry_times: dict = field(default_factory=dict)  # zone_id -> entry timestamp
    zone_exit_times: dict = field(default_factory=dict)   # zone_id -> exit timestamp (hysteresis)
    fired_zone_events: set = field(default_factory=set)   # deduplication cache

    # Behavioral Timeline & Risk Correlation
    timeline: list[TimelineItem] = field(default_factory=list)
    risk_score: int = 0
    stationary_duration: float = 0.0
    direction_changes: int = 0
    last_heading_vector: Optional[tuple] = None
    observation_count: int = 0

    # Identity
    identity_status: IdentityStatus = IdentityStatus.NOT_ATTEMPTED
    identity_name: Optional[str] = None
    identity_id: Optional[str] = None
    tag_color: Optional[str] = None
    visual_signature: Optional[Any] = None
    role_detected: Optional[str] = None
    rank_stars: int = 1
    rank_title: Optional[str] = "Officer"
    has_escort: bool = False
    carried_objects: set = field(default_factory=set)

    # Object / Bag association
    associated_person_track_id: Optional[int] = None
    stationary_since: Optional[float] = None
    last_moved_position: Optional[tuple] = None
    unattended_event_fired: bool = False
    abandoned_event_fired: bool = False
    nearby_bag_track_ids: set = field(default_factory=set)

    # Perimeter Reconnaissance & Group Activity (SIH 26187 Categories 1 & 2)
    approach_count: int = 0
    was_near_restricted: bool = False
    last_approach_time: float = 0.0
    direction_change_timestamps: list[float] = field(default_factory=list)
    group_dwell_start: Optional[float] = None
    pending_handover_alert: Optional[str] = None

    # Ground-Plane Homography (3D Metric Metrology)
    velocity_kmh: float = 0.0
    movement_type: str = "STATIONARY"
    ground_coord_m: tuple = (0.0, 0.0)
    distance_to_fence_m: float = 999.0

    @property
    def display_name(self) -> str:
        if self.identity_name and getattr(self.identity_status, "value", "").upper() == "VERIFIED":
            return self.identity_name
        return f"Person #{self.track_id}"


# Thresholds (Configurable)
STATIONARY_MOVEMENT_THRESHOLD_PX = 15.0
PERSON_BAG_ASSOCIATION_DISTANCE_PX = 140.0
UNATTENDED_OBJECT_DISTANCE_PX = 130.0
ABANDONED_OBJECT_STATIONARY_SECONDS = 12.0
PERSON_DEPARTURE_DISTANCE_PX = 200.0
PROLONGED_STANDING_THRESHOLD_SECONDS = 15.0
LOITERING_THRESHOLD_SECONDS = 45.0
RESTRICTED_APPROACH_DISTANCE_PX = 90.0
GROUP_CONVERGENCE_DISTANCE_PX = 110.0
GROUP_CONVERGENCE_SECONDS = 12.0
PROLONGED_CONGREGATION_SECONDS = 45.0
PROLONGED_PARKING_THRESHOLD_SECONDS = 30.0
UNAUTHORIZED_PARKING_THRESHOLD_SECONDS = 120.0


from ai_engine.authorization.authorization_engine import AuthorizationEngine, PersonContext
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ai_engine.tracking.global_threat_registry import GlobalThreatRegistry


class TemporalEventEngine:
    """
    Evaluates temporal and spatial behaviors of tracked entities.
    Emits explainable events with multi-signal behavioral risk scoring.
    Maintains cross-camera continuity through GlobalThreatRegistry.
    Calculates 3D ground-plane metric speed (km/h) and distance (meters) via Homography.
    """

    def __init__(
        self,
        auth_engine: Optional[AuthorizationEngine] = None,
        threat_registry: Optional[Any] = None
    ):
        self.states: dict[int, TrackState] = {}
        self.auth_engine = auth_engine
        self.threat_registry = threat_registry
        self.homography_engines: dict[str, HomographyEngine] = {}

    def _get_homography(self, camera_id: str) -> HomographyEngine:
        if camera_id not in self.homography_engines:
            self.homography_engines[camera_id] = HomographyEngine(camera_id=camera_id)
        return self.homography_engines[camera_id]

    def _get_or_create_state(self, tracked_obj, camera_id: str, now: float, visual_signature: Optional[Any] = None) -> TrackState:
        state = self.states.get(tracked_obj.track_id)
        if state is None:
            state = TrackState(
                track_id=tracked_obj.track_id,
                label=tracked_obj.label,
                camera_id=camera_id,
                first_seen=now,
                last_seen=now,
                last_position=tracked_obj.foot_point,
            )
            state.timeline.append(TimelineItem(
                timestamp=now,
                event_type="first_detected",
                description=f"First detected in camera {camera_id}"
            ))

            # Query Global Threat Registry for cross-camera suspect handover
            if self.threat_registry:
                matched_suspect = self.threat_registry.query_handover_match(
                    current_camera_id=camera_id,
                    tag_color=getattr(state, "tag_color", None),
                    identity_id=getattr(state, "identity_id", None),
                    visual_signature=visual_signature
                )
                if matched_suspect:
                    state.risk_score = matched_suspect.risk_score
                    state.pending_handover_alert = matched_suspect.last_seen_camera_id
                    state.timeline.extend(matched_suspect.timeline[-5:])  # copy recent history
                    state.timeline.append(TimelineItem(
                        timestamp=now,
                        event_type="cross_camera_handover",
                        description=f"Cross-camera suspect handover from Camera {matched_suspect.last_seen_camera_id}. Inherited Risk Score: {matched_suspect.risk_score}"
                    ))
                    if matched_suspect.carried_objects:
                        state.carried_objects.update(matched_suspect.carried_objects)

            self.states[tracked_obj.track_id] = state
        return state

    def _distance(self, p1: tuple, p2: tuple) -> float:
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    def _is_distinct_and_nearby(self, p1, p2) -> bool:
        """
        Validates that p1 and p2 are two physically distinct human bodies
        (not duplicate detections or split tracks of the same body) and
        are within genuine group proximity.
        """
        b1, b2 = p1.bbox, p2.bbox
        ix1, iy1 = max(b1[0], b2[0]), max(b1[1], b2[1])
        ix2, iy2 = min(b1[2], b2[2]), min(b1[3], b2[3])
        iw = max(0.0, ix2 - ix1)
        ih = max(0.0, iy2 - iy1)
        intersection = iw * ih

        area1 = max(1.0, (b1[2] - b1[0]) * (b1[3] - b1[1]))
        area2 = max(1.0, (b2[2] - b2[0]) * (b2[3] - b2[1]))
        min_area = min(area1, area2)
        union = area1 + area2 - intersection
        iou = intersection / max(1.0, union)
        containment = intersection / min_area

        # Duplicate detection check: heavy overlap or identical horizontal centerline
        if iou > 0.28 or containment > 0.45:
            return False

        # Two separate people have distinct horizontal centers
        dx = abs(p1.centroid[0] - p2.centroid[0])
        if dx < 35.0:
            return False

        # Ground foot point distance check
        dist = self._distance(p1.foot_point, p2.foot_point)
        return 40.0 <= dist <= GROUP_CONVERGENCE_DISTANCE_PX

    def _new_event(self, event_type: EventType, state: TrackState, zone_id: Optional[str],
                   severity: Severity, confidence: float, description: str,
                   risk_boost: int = 0, metadata: Optional[dict] = None) -> Event:
        now = time.time()

        # Add to state timeline
        timeline_entry = TimelineItem(
            timestamp=now,
            event_type=event_type.value,
            description=description
        )
        state.timeline.append(timeline_entry)
        if len(state.timeline) > 50:
            state.timeline.pop(0)

        # Update dynamic risk score
        state.risk_score = min(100, max(0, state.risk_score + risk_boost))

        # Strict Severity Policy: ONLY lethal weapons (Gun, Knife) are permitted to escalate to Severity.RED.
        # All other security and behavioral alerts are clamped to Severity.ORANGE or Severity.YELLOW.
        final_severity = severity
        if event_type == EventType.WEAPON_DETECTED:
            final_severity = Severity.RED
        else:
            if final_severity == Severity.RED:
                final_severity = Severity.ORANGE
            if state.risk_score >= 50 and final_severity not in (Severity.ORANGE,):
                final_severity = Severity.ORANGE
            elif state.risk_score >= 30 and final_severity not in (Severity.ORANGE, Severity.YELLOW):
                final_severity = Severity.YELLOW

        # Enrich metadata with verified person identity and 3D ground metrology
        meta = dict(metadata or {})
        meta.setdefault("velocity_kmh", getattr(state, "velocity_kmh", 0.0))
        meta.setdefault("movement_type", getattr(state, "movement_type", "STATIONARY"))
        meta.setdefault("distance_to_fence_m", getattr(state, "distance_to_fence_m", 999.0))
        meta.setdefault("ground_coord_m", getattr(state, "ground_coord_m", (0.0, 0.0)))
        if state.identity_name and getattr(state.identity_status, "value", "").upper() == "VERIFIED":
            meta.setdefault("person_name", state.identity_name)
            meta.setdefault("person_role", getattr(state, "role_detected", None))
        meta.setdefault("display_name", state.display_name)

        return Event(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            track_id=state.track_id,
            camera_id=state.camera_id,
            zone_id=zone_id,
            timestamp=now,
            severity=final_severity,
            confidence=confidence,
            description=description,
            risk_score=state.risk_score,
            behavioral_evidence=list(state.timeline),
            metadata=meta
        )

    def update(self, tracked_obj, camera_id: str, matched_zones: list, current_hour: int,
               identity_result=None, camera_zones: Optional[list] = None,
               all_tracked_objects: Optional[list] = None,
               visual_signature: Optional[Any] = None) -> list[Event]:
        now = time.time()
        events: list[Event] = []
        state = self._get_or_create_state(tracked_obj, camera_id, now, visual_signature)

        if visual_signature is not None:
            state.visual_signature = visual_signature

        moved = self._distance(state.last_position, tracked_obj.foot_point)
        state.last_seen = now
        state.position_history.append((now, tracked_obj.foot_point))
        if len(state.position_history) > 300:
            state.position_history.pop(0)

        # 3D Ground-Plane Homography computation (metric coordinates & velocity)
        homo = self._get_homography(camera_id)
        state.ground_coord_m = homo.pixel_to_ground(tracked_obj.foot_point)
        state.velocity_kmh, state.movement_type = homo.calculate_velocity_kmh(state.position_history)

        if camera_zones:
            restricted_zones = [
                z for z in camera_zones
                if z.zone_type.value in ("restricted", "high_security", "sensitive")
            ]
            if restricted_zones:
                state.distance_to_fence_m = min(
                    homo.distance_to_polygon_meters(tracked_obj.foot_point, z.polygon)
                    for z in restricted_zones
                )

        if identity_result is not None:
            if len(identity_result) >= 6:
                state.identity_status, state.identity_name, state.identity_id, state.role_detected, state.rank_stars, state.rank_title = identity_result[:6]
            elif len(identity_result) >= 4:
                state.identity_status, state.identity_name, state.identity_id, state.role_detected = identity_result[:4]
            else:
                state.identity_status, state.identity_name, state.identity_id = identity_result[:3]


        # Emit multi-camera repeated observation event if handed over from prior camera
        if state.pending_handover_alert:
            src_cam = state.pending_handover_alert
            state.pending_handover_alert = None
            events.append(self._new_event(
                EventType.REPEATED_OBSERVATION, state, None,
                Severity.ORANGE if state.risk_score >= 50 else Severity.YELLOW,
                tracked_obj.confidence,
                f"Multi-camera repeated observation: Track #{state.track_id} re-observed on Camera {camera_id} (Correlated from Camera {src_cam})",
                risk_boost=15
            ))

        # Analyze trajectory / movement speed
        if moved < STATIONARY_MOVEMENT_THRESHOLD_PX:
            state.stationary_duration += (now - state.position_history[-2][0]) if len(state.position_history) >= 2 else 0.5
        else:
            state.stationary_duration = 0.0

        if tracked_obj.is_person:
            events.extend(self._evaluate_person(
                state, tracked_obj, matched_zones, current_hour,
                camera_zones=camera_zones, all_tracked_objects=all_tracked_objects
            ))
        elif tracked_obj.is_bag:
            events.extend(self._evaluate_bag(state, tracked_obj, moved))
        elif tracked_obj.is_vehicle:
            events.extend(self._evaluate_vehicle(state, tracked_obj, matched_zones))

        state.last_position = tracked_obj.foot_point
        return events

    # ---- Person Rules with Multi-Signal Behavioral Scoring --------------

    def _evaluate_person(self, state: TrackState, tracked_obj, matched_zones, current_hour: int,
                         camera_zones: Optional[list] = None,
                         all_tracked_objects: Optional[list] = None) -> list[Event]:
        now = time.time()
        events = []
        new_zone_ids = {z.zone_id for z in matched_zones}
        entered_zone_ids = new_zone_ids - state.current_zone_ids

        for zone in matched_zones:
            if zone.zone_id in entered_zone_ids:
                state.zone_entry_times[zone.zone_id] = now
                state.timeline.append(TimelineItem(
                    timestamp=now,
                    event_type="zone_entered",
                    description=f"Entered zone '{zone.name}'"
                ))

        # Emit Verified Personnel Clearance Event when identity is confirmed
        if state.identity_status == IdentityStatus.VERIFIED and "verified_person_alert" not in state.fired_zone_events:
            state.fired_zone_events.add("verified_person_alert")
            role_desc = f" ({state.role_detected})" if state.role_detected else ""
            events.append(self._new_event(
                EventType.AUTHORIZED_ACCESS, state, None,
                Severity.GREEN, tracked_obj.confidence,
                f"✓ Authorized Personnel Cleared: {state.identity_name}{role_desc}",
                risk_boost=0,
                metadata={
                    "is_verified_person": True,
                    "person_name": state.identity_name,
                    "person_role": state.role_detected,
                    "display_name": state.identity_name,
                    "identity_id": state.identity_id
                }
            ))

        # Once verified as authorized personnel, cease all behavioral tracking & security alarms for this person.
        # Surveillance attention and anomaly detection remain focused strictly on tracking others.
        if state.identity_status == IdentityStatus.VERIFIED:
            return events

        # For unverified personnel, perform behavioral trajectory, loitering, and reconnaissance checks
        if state.identity_status != IdentityStatus.VERIFIED:
            # 1. Prolonged standing / loitering check
            if state.stationary_duration >= LOITERING_THRESHOLD_SECONDS and "loitering" not in state.fired_zone_events:
                state.fired_zone_events.add("loitering")
                events.append(self._new_event(
                    EventType.LOITERING, state, None,
                    Severity.ORANGE, tracked_obj.confidence,
                    f"{state.display_name} stationary/loitering for {int(state.stationary_duration)}s",
                    risk_boost=25
                ))
            elif state.stationary_duration >= PROLONGED_STANDING_THRESHOLD_SECONDS and "prolonged_standing" not in state.fired_zone_events:
                state.fired_zone_events.add("prolonged_standing")
                events.append(self._new_event(
                    EventType.PROLONGED_STANDING, state, None,
                    Severity.YELLOW, tracked_obj.confidence,
                    f"{state.display_name} standing/waiting for {int(state.stationary_duration)}s",
                    risk_boost=10
                ))

            # 2. Wandering / Erratic Trajectory (Category 1: Movement & Presence)
            if len(state.position_history) >= 3:
                p1 = state.position_history[-3][1]
                p2 = state.position_history[-2][1]
                p3 = state.position_history[-1][1]
                v1 = (p2[0] - p1[0], p2[1] - p1[1])
                v2 = (p3[0] - p2[0], p3[1] - p2[1])
                d1 = math.hypot(v1[0], v1[1])
                d2 = math.hypot(v2[0], v2[1])
                if d1 > 8.0 and d2 > 8.0:
                    dot = v1[0] * v2[0] + v1[1] * v2[1]
                    cos_theta = dot / (d1 * d2)
                    if cos_theta < -0.4:  # direction reversal > 115 deg
                        state.direction_change_timestamps.append(now)

                state.direction_change_timestamps = [t for t in state.direction_change_timestamps if (now - t) <= 20.0]
                if len(state.direction_change_timestamps) >= 3 and "unusual_movement" not in state.fired_zone_events:
                    state.fired_zone_events.add("unusual_movement")
                    events.append(self._new_event(
                        EventType.UNUSUAL_MOVEMENT, state, None,
                        Severity.YELLOW, tracked_obj.confidence,
                        f"Wandering/erratic movement: {state.display_name} reversed direction {len(state.direction_change_timestamps)} times in 20s",
                        risk_boost=20
                    ))

            # 3. Repeated Approach toward Restricted Perimeter (Category 1 & 2: Reconnaissance)
            if camera_zones:
                restricted_zones = [
                    z for z in camera_zones
                    if z.zone_type.value in ("restricted", "high_security", "sensitive")
                ]
                if restricted_zones:
                    min_dist = min(z.distance_to_point(tracked_obj.foot_point) for z in restricted_zones)
                    if 0 < min_dist < RESTRICTED_APPROACH_DISTANCE_PX:
                        if not state.was_near_restricted:
                            state.was_near_restricted = True
                            state.approach_count += 1
                            state.last_approach_time = now
                            if state.approach_count == 2 and "approach_2" not in state.fired_zone_events:
                                state.fired_zone_events.add("approach_2")
                                events.append(self._new_event(
                                    EventType.REPEATED_APPROACH, state, None,
                                    Severity.YELLOW, tracked_obj.confidence,
                                    f"Repeated approach: {state.display_name} approached perimeter ({state.distance_to_fence_m}m out | {state.velocity_kmh} km/h [{state.movement_type}])",
                                    risk_boost=20
                                ))
                            elif state.approach_count >= 3 and "approach_3" not in state.fired_zone_events:
                                state.fired_zone_events.add("approach_3")
                                events.append(self._new_event(
                                    EventType.REPEATED_APPROACH, state, None,
                                    Severity.ORANGE, tracked_obj.confidence,
                                    f"Suspicious reconnaissance pattern: {state.display_name} approached perimeter {state.approach_count} times ({state.distance_to_fence_m}m out | {state.velocity_kmh} km/h)",
                                    risk_boost=35
                                ))

                    elif min_dist > (RESTRICTED_APPROACH_DISTANCE_PX + 40.0):
                        state.was_near_restricted = False

        # 4. Group Formation / Convergence (Category 2: Observation & Interaction)
        if all_tracked_objects:
            nearby_persons = [
                o for o in all_tracked_objects
                if o.is_person and o.track_id != state.track_id
                and not (self.states.get(o.track_id) and getattr(self.states.get(o.track_id).identity_status, "value", "").upper() == "VERIFIED")
                and self._is_distinct_and_nearby(tracked_obj, o)
            ]
            if nearby_persons:
                if state.group_dwell_start is None:
                    state.group_dwell_start = now
                else:
                    duration = now - state.group_dwell_start
                    if duration >= PROLONGED_CONGREGATION_SECONDS and "prolonged_congregation" not in state.fired_zone_events:
                        state.fired_zone_events.add("prolonged_congregation")
                        other_ids = ", ".join(f"#{p.track_id}" for p in nearby_persons)
                        events.append(self._new_event(
                            EventType.PROLONGED_CONGREGATION, state, None,
                            Severity.ORANGE, tracked_obj.confidence,
                            f"Prolonged group congregation: {state.display_name} with {other_ids} for {int(duration)}s",
                            risk_boost=40
                        ))
                    elif duration >= GROUP_CONVERGENCE_SECONDS and "group_formation" not in state.fired_zone_events:
                        state.fired_zone_events.add("group_formation")
                        other_ids = ", ".join(f"#{p.track_id}" for p in nearby_persons)
                        events.append(self._new_event(
                            EventType.GROUP_FORMATION, state, None,
                            Severity.YELLOW if not matched_zones else Severity.ORANGE,
                            tracked_obj.confidence,
                            f"Group convergence: {state.display_name} congregating with {other_ids} for {int(duration)}s",
                            risk_boost=25
                        ))
            else:
                state.group_dwell_start = None
                state.fired_zone_events.discard("group_formation")
                state.fired_zone_events.discard("prolonged_congregation")

        # 2. Zone-specific evaluation
        for zone in matched_zones:
            entry_time = state.zone_entry_times.get(zone.zone_id)
            if entry_time is None:
                continue
            dwell = time.time() - entry_time
            fired_key = f"{zone.zone_id}"

            if dwell < zone.threshold_seconds:
                continue
            if fired_key in state.fired_zone_events:
                continue

            # Authorization Rule evaluation
            if self.auth_engine and self.auth_engine.rules:
                from datetime import datetime
                tag_color = state.tag_color or "unknown"
                context = PersonContext(
                    tag_color=tag_color,
                    role=self.auth_engine.get_role_for_tag(tag_color),
                    zone=zone.name,
                    current_time=datetime.now(),
                    objects_carried=list(state.carried_objects),
                    track_id=state.track_id
                )
                auth_result = self.auth_engine.check_authorization(context)
                if not auth_result.authorized:
                    sev = Severity.ORANGE
                    events.append(self._new_event(
                        EventType.UNAUTHORIZED_WRONG_ZONE, state, zone.zone_id,
                        sev, tracked_obj.confidence,
                        f"Access Denied: {auth_result.reason} for {state.display_name} in '{zone.name}'",
                        risk_boost=50,
                        metadata={"auth_details": auth_result.__dict__}
                    ))

                else:
                    events.append(self._new_event(
                        EventType.AUTHORIZED_ACCESS, state, zone.zone_id,
                        Severity.GREEN, tracked_obj.confidence,
                        f"Authorized access in '{zone.name}' ({auth_result.matched_rule})",
                        risk_boost=-10
                    ))
            elif zone.zone_type.value == "entry":
                # Attendance / Entry Gate logging
                person_stars = getattr(state, "rank_stars", 1)
                rank_title = getattr(state, "rank_title", "Officer")
                stars_display = "⭐" * person_stars
                if state.identity_status == IdentityStatus.VERIFIED:
                    events.append(self._new_event(
                        EventType.AUTHORIZED_ACCESS, state, zone.zone_id,
                        Severity.GREEN, tracked_obj.confidence,
                        f"Entry logged: [{stars_display}] {state.identity_name} ({rank_title}) via '{zone.name}'",
                        risk_boost=-10,
                        metadata={
                            "is_entry_log": True,
                            "identity_id": state.identity_id,
                            "identity_name": state.identity_name,
                            "identity_role": state.role_detected,
                            "rank_stars": person_stars,
                            "rank_title": rank_title,
                            "entry_type": "FACE_VERIFIED"
                        }
                    ))
                else:
                    events.append(self._new_event(
                        EventType.PERSON_DETECTED, state, zone.zone_id,
                        Severity.GREEN, tracked_obj.confidence,
                        f"Unrecognized person entry at '{zone.name}'",
                        risk_boost=5,
                        metadata={
                            "is_entry_log": True,
                            "entry_type": "UNKNOWN_FACE"
                        }
                    ))
            elif zone.zone_type.value in ("restricted", "sensitive", "high_security", "general", "monitored"):
                is_zero_line = zone.zone_type.value == "high_security"
                min_stars = getattr(zone, "min_rank_stars", 0)
                allow_escort = getattr(zone, "allow_escort", False)
                person_stars = getattr(state, "rank_stars", 1)
                rank_title = getattr(state, "rank_title", "Officer")
                person_star_badge = "⭐" * person_stars
                zone_star_badge = f"[{'⭐' * min_stars} Clearance]" if min_stars > 0 else ""
                prefix = "🚨 CRITICAL ZERO-LINE BREACH:" if is_zero_line else "Perimeter breach:"

                if state.identity_status == IdentityStatus.VERIFIED:
                    # Enforce Star Rank Clearance & Boundary Rules
                    if min_stars > 0 and person_stars < min_stars and not (allow_escort and getattr(state, "has_escort", False)):
                        # Rank clearance violation
                        events.append(self._new_event(
                            EventType.UNAUTHORIZED_WRONG_ZONE, state, zone.zone_id,
                            Severity.ORANGE, tracked_obj.confidence,
                            f"🚨 RANK CLEARANCE BREACH: [{person_star_badge}] {state.identity_name} ({rank_title}) breached {zone_star_badge} '{zone.name}' (Requires Level {min_stars} Stars)! Threat Risk Escallated.",
                            risk_boost=90 if is_zero_line or min_stars >= 4 else 75,
                            metadata={
                                "person_name": state.identity_name,
                                "person_role": state.role_detected,
                                "rank_stars": person_stars,
                                "rank_title": rank_title,
                                "min_rank_stars": min_stars,
                                "zone_name": zone.name,
                            }
                        ))
                    else:
                        events.append(self._new_event(
                            EventType.AUTHORIZED_ACCESS, state, zone.zone_id,
                            Severity.GREEN, tracked_obj.confidence,
                            f"🎖️ CLEARANCE GRANTED: [{person_star_badge}] {state.identity_name} ({rank_title}) authorized in {zone_star_badge} '{zone.name}'",
                            risk_boost=-20,
                            metadata={
                                "person_name": state.identity_name,
                                "person_role": state.role_detected,
                                "rank_stars": person_stars,
                                "rank_title": rank_title,
                                "min_rank_stars": min_stars,
                                "zone_name": zone.name,
                            }
                        ))
                elif state.identity_status == IdentityStatus.LOW_CONFIDENCE:
                    events.append(self._new_event(
                        EventType.LOW_CONFIDENCE_VERIFICATION, state, zone.zone_id,
                        Severity.YELLOW, tracked_obj.confidence,
                        f"Low-confidence identity match for Person #{state.track_id} in {zone_star_badge} '{zone.name}'",
                        risk_boost=30
                    ))
                else:
                    # Unverified person inside restricted/high security zone -> High alert
                    if zone.zone_type.value in ("restricted", "sensitive", "high_security") or min_stars > 0:
                        events.append(self._new_event(
                            EventType.UNAUTHORIZED_UNKNOWN, state, zone.zone_id,
                            Severity.ORANGE, tracked_obj.confidence,
                            f"{prefix} Unverified person #{state.track_id} in {zone_star_badge} {zone.zone_type.value} zone '{zone.name}'",
                            risk_boost=95 if is_zero_line or min_stars >= 4 else 80,
                            metadata={
                                "min_rank_stars": min_stars,
                                "zone_name": zone.name,
                            }
                        ))
                    elif zone.zone_type.value == "monitored":
                        events.append(self._new_event(
                            EventType.ZONE_INTRUSION, state, zone.zone_id,
                            Severity.YELLOW, tracked_obj.confidence,
                            f"Person #{state.track_id} entered monitored zone '{zone.name}'",
                            risk_boost=20
                        ))

            # Night / after-hours check
            if zone.active_hours is not None and zone.is_active_now(current_hour):
                events.append(self._new_event(
                    EventType.AFTER_HOURS_PRESENCE, state, zone.zone_id,
                    Severity.ORANGE, tracked_obj.confidence,
                    f"After-hours presence in '{zone.name}' at {current_hour}:00",
                    risk_boost=40
                ))

            state.fired_zone_events.add(fired_key)

        # Clear exit timers for zones currently active
        for zone_id in new_zone_ids:
            state.zone_exit_times.pop(zone_id, None)

        # Apply 3.0s hysteresis on zone exits to prevent bounding-box boundary jitter from flapping
        left_zone_ids = state.current_zone_ids - new_zone_ids
        for zone_id in left_zone_ids:
            if zone_id not in state.zone_exit_times:
                state.zone_exit_times[zone_id] = now
            elif (now - state.zone_exit_times[zone_id]) > 3.0:
                state.fired_zone_events.discard(zone_id)
                state.zone_entry_times.pop(zone_id, None)
                state.zone_exit_times.pop(zone_id, None)
                state.current_zone_ids.discard(zone_id)

        state.current_zone_ids.update(new_zone_ids)
        return events

    # ---- Bag / Abandoned-Object Rule ------------------------------------

    def _evaluate_bag(self, state: TrackState, tracked_obj, moved_px: float) -> list[Event]:
        events = []

        if moved_px > STATIONARY_MOVEMENT_THRESHOLD_PX:
            state.stationary_since = None
            state.unattended_event_fired = False
            state.abandoned_event_fired = False
            return events

        now = time.time()
        if state.stationary_since is None:
            state.stationary_since = now
            return events

        stationary_duration = now - state.stationary_since

        owner_departed = True
        owner_state = None
        owner_distance = float("inf")
        if state.associated_person_track_id is not None:
            owner_state = self.states.get(state.associated_person_track_id)
            if owner_state is not None:
                owner_distance = self._distance(owner_state.last_position, tracked_obj.foot_point)
                # If owner has exited the camera frame (not seen in > 1.5s), they have departed
                owner_in_frame = (now - owner_state.last_seen) <= 1.5
                if not owner_in_frame:
                    owner_departed = True
                else:
                    owner_departed = owner_distance > PERSON_DEPARTURE_DISTANCE_PX

        # Check if ANY person in camera view is currently attending to this object
        nearest_person_dist = float("inf")
        for pstate in self.states.values():
            if pstate.label == "person" and (now - pstate.last_seen) <= 1.5:
                d = self._distance(pstate.last_position, tracked_obj.foot_point)
                if d < nearest_person_dist:
                    nearest_person_dist = d

        # If any person is right next to the bag (<= 130px), someone is actively attending to it
        if nearest_person_dist <= UNATTENDED_OBJECT_DISTANCE_PX:
            state.unattended_event_fired = False
            state.abandoned_event_fired = False
            return events

        # Effective separation distance
        effective_dist = min(owner_distance, nearest_person_dist)

        # Stage 1: Object left unattended (Category 3: Yellow Attention)
        if (UNATTENDED_OBJECT_DISTANCE_PX < effective_dist <= PERSON_DEPARTURE_DISTANCE_PX
                and not state.unattended_event_fired):
            state.unattended_event_fired = True
            owner_desc = f"owner ({owner_state.display_name})" if owner_state else "people in area"
            events.append(self._new_event(
                EventType.OBJECT_UNATTENDED, state, None,
                Severity.YELLOW, tracked_obj.confidence,
                f"Object left unattended: {tracked_obj.label} #{state.track_id} separated from {owner_desc} by {int(effective_dist)}px",
                risk_boost=30,
                metadata={
                    "stationary_seconds": int(stationary_duration),
                    "owner_distance": int(effective_dist),
                    "owner_track_id": state.associated_person_track_id,
                    "owner_name": owner_state.identity_name if owner_state else None
                }
            ))

        # Stage 2: High-priority Abandoned Object (Category 3: Red Alert)
        if (stationary_duration > ABANDONED_OBJECT_STATIONARY_SECONDS
                and (owner_departed or nearest_person_dist > PERSON_DEPARTURE_DISTANCE_PX)
                and not state.abandoned_event_fired):
            state.abandoned_event_fired = True
            owner_desc = f"(Left by {owner_state.display_name})" if owner_state else \
                (f"(Associated Person #{state.associated_person_track_id})" if state.associated_person_track_id else "(Unassociated Object)")

            events.append(self._new_event(
                EventType.ABANDONED_OBJECT, state, None,
                Severity.ORANGE, tracked_obj.confidence,
                f"🚨 High-priority abandoned object: {tracked_obj.label} #{state.track_id} stationary for {int(stationary_duration)}s {owner_desc}",
                risk_boost=80,
                metadata={
                    "stationary_seconds": int(stationary_duration),
                    "owner_distance": int(effective_dist) if effective_dist != float("inf") else -1,
                    "owner_track_id": state.associated_person_track_id,
                    "owner_name": owner_state.identity_name if owner_state else None
                }
            ))
        return events

    def associate_bag_with_nearest_person(self, bag_track_id: int, all_person_states: list[TrackState]):
        bag_state = self.states.get(bag_track_id)
        if bag_state is None or not all_person_states:
            return
        closest = min(
            all_person_states,
            key=lambda p: self._distance(p.last_position, bag_state.last_position),
            default=None,
        )
        if closest and self._distance(closest.last_position, bag_state.last_position) < PERSON_BAG_ASSOCIATION_DISTANCE_PX:
            bag_state.associated_person_track_id = closest.track_id
            closest.carried_objects.add(bag_state.label)

    # ---- Vehicle Evaluation ----------------------------------------------

    def _evaluate_vehicle(self, state: TrackState, tracked_obj, matched_zones) -> list[Event]:
        events = []
        new_zone_ids = {z.zone_id for z in matched_zones}
        for zone in matched_zones:
            if zone.zone_type.value in ("restricted", "sensitive"):
                fired_key = f"vehicle_{zone.zone_id}"
                if fired_key not in state.fired_zone_events:
                    state.fired_zone_events.add(fired_key)
                    events.append(self._new_event(
                        EventType.ZONE_INTRUSION, state, zone.zone_id,
                        Severity.ORANGE, tracked_obj.confidence,
                        f"Vehicle #{state.track_id} entered monitored zone '{zone.name}'",
                        risk_boost=45
                    ))

        # Tiered parking logic
        if state.stationary_duration >= UNAUTHORIZED_PARKING_THRESHOLD_SECONDS and "unauthorized_parking" not in state.fired_zone_events:
            state.fired_zone_events.add("unauthorized_parking")
            events.append(self._new_event(
                EventType.UNAUTHORIZED_PARKING, state, None,
                Severity.ORANGE, tracked_obj.confidence,
                f"Vehicle #{state.track_id} unauthorized parking for {int(state.stationary_duration)}s",
                risk_boost=45
            ))
        elif state.stationary_duration >= PROLONGED_PARKING_THRESHOLD_SECONDS and "prolonged_parking" not in state.fired_zone_events:
            state.fired_zone_events.add("prolonged_parking")
            events.append(self._new_event(
                EventType.PROLONGED_PARKING, state, None,
                Severity.YELLOW, tracked_obj.confidence,
                f"Vehicle #{state.track_id} parked/stopped for {int(state.stationary_duration)}s",
                risk_boost=15
            ))

        left_zone_ids = state.current_zone_ids - new_zone_ids
        for zone_id in left_zone_ids:
            state.fired_zone_events.discard(f"vehicle_{zone_id}")

        state.current_zone_ids = new_zone_ids
        return events

    def prune_stale_tracks(self, active_track_ids: set, max_age_seconds: float = 30.0):
        now = time.time()
        stale = [tid for tid, s in self.states.items()
                 if tid not in active_track_ids and (now - s.last_seen) > max_age_seconds]
        for tid in stale:
            state = self.states[tid]
            # Publish BOLO to GlobalThreatRegistry for all departing persons
            if self.threat_registry:
                self.threat_registry.publish_suspect_departure(
                    camera_id=state.camera_id,
                    track_id=state.track_id,
                    risk_score=state.risk_score,
                    severity=self._risk_to_severity(state.risk_score),
                    timeline=list(state.timeline),
                    tag_color=state.tag_color,
                    identity_id=state.identity_id,
                    identity_name=state.identity_name,
                    carried_objects=state.carried_objects,
                    visual_signature=getattr(state, 'visual_signature', None)
                )
            del self.states[tid]

    def _risk_to_severity(self, risk_score: int) -> str:
        if risk_score >= 75:
            return "RED"
        if risk_score >= 50:
            return "ORANGE"
        if risk_score >= 30:
            return "YELLOW"
        return "GREEN"
