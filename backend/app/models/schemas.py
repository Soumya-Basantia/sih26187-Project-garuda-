"""
Pydantic schemas for request/response validation and MongoDB document shape.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime


# ---- auth / users -----------------------------------------------------

class UserRole(str, Enum):
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"


class UserCreate(BaseModel):
    username: str
    password: str
    role: UserRole = UserRole.VIEWER


class UserLogin(BaseModel):
    username: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole


# ---- cameras ------------------------------------------------------------

class SourceType(str, Enum):
    RTSP = "rtsp"
    WEBCAM = "webcam"
    FILE = "file"
    DEMO = "demo"


class CameraCreate(BaseModel):
    name: str
    location: str
    source_type: SourceType
    source_uri: str
    target_fps: int = 35
    device_category: Optional[str] = "cctv"
    protocol: Optional[str] = None
    ai_enabled: Optional[bool] = True
    rotation: Optional[int] = 0


class CameraOut(BaseModel):
    camera_id: str
    name: str
    location: str
    source_type: SourceType
    source_uri: str
    status: str
    device_category: Optional[str] = "cctv"
    protocol: Optional[str] = None
    resolution: Optional[str] = None
    fps: Optional[int] = None
    last_heartbeat: Optional[float] = None
    ai_enabled: Optional[bool] = True
    rotation: Optional[int] = 0


# ---- zones ---------------------------------------------------------------

class ZoneType(str, Enum):
    RESTRICTED = "restricted"
    HIGH_SECURITY = "high_security"
    MONITORED = "monitored"
    GENERAL = "general"
    ENTRY = "entry"
    EXIT = "exit"
    VEHICLE_ONLY = "vehicle_only"
    SENSITIVE = "sensitive"


class ZoneCreate(BaseModel):
    camera_id: str
    name: str
    zone_type: ZoneType
    polygon: list[list[float]]  # [[x,y], ...]
    threshold_seconds: float = 5.0
    active_hours: Optional[list[int]] = None  # [start_hour, end_hour]
    authorized_identity_ids: list[str] = Field(default_factory=list)
    enabled: bool = True
    min_rank_stars: int = 0  # 0 = Open/Patrol, 1 = Guard, 2 = Duty Off., 3 = Field Off., 4 = Division Cmd, 5 = Supreme Command
    allow_escort: bool = False  # Lower rank allowed if accompanied by officer
    authority_custom_level: Optional[str] = None  # e.g. "LEVEL_5_COMMAND", "STRICT_LOCKDOWN"


class ZoneOut(ZoneCreate):
    zone_id: str


# ---- identities ------------------------------------------------------------

class IdentityCreate(BaseModel):
    demo_id: str
    name: str
    role: str
    department: Optional[str] = None
    plate_number: Optional[str] = None   # Optional vehicle plate linked to owner
    vehicle_type: Optional[str] = None   # Car, Motorcycle, Truck, etc.
    consent_given: bool = True
    rank_stars: int = 1  # 1 to 5 stars
    rank_title: Optional[str] = "Officer"  # e.g., General, Colonel, Captain, Guard


class IdentityOut(IdentityCreate):
    identity_id: str
    has_face_enrolled: bool = False


# ---- vehicles ------------------------------------------------------------

class VehicleCreate(BaseModel):
    plate_number: str
    vehicle_type: Optional[str] = None   # Car, Truck, Motorcycle, etc.
    owner_name: Optional[str] = None     # Name of the registered owner
    owner_ref: Optional[str] = None      # Optional identity_id if owner is enrolled
    watchlist_flag: bool = False
    notes: Optional[str] = None


class VehicleOut(VehicleCreate):
    vehicle_id: str


# ---- events / alerts ------------------------------------------------------

class Severity(str, Enum):
    GREEN = "GREEN"    # Normal
    YELLOW = "YELLOW"  # Attention
    ORANGE = "ORANGE"  # Suspicious Pattern
    RED = "RED"        # High Priority Security Alert


class EventOut(BaseModel):
    event_id: str
    event_type: str
    track_id: int
    camera_id: str
    zone_id: Optional[str]
    timestamp: float
    severity: Severity = Severity.GREEN
    risk_score: int = 0
    confidence: float
    description: str
    person_name: Optional[str] = None
    person_role: Optional[str] = None
    display_name: Optional[str] = None
    rank_stars: Optional[int] = None
    rank_title: Optional[str] = None
    snapshot_path: Optional[str] = None
    snapshot_url: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class AlertStatus(str, Enum):
    NEW = "NEW"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    INVESTIGATING = "INVESTIGATING"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class BehavioralEvidence(BaseModel):
    timestamp: float
    event_type: str
    description: str


class AlertOut(BaseModel):
    alert_id: str
    event_id: Optional[str] = None
    event_type: str
    camera_id: str
    location: Optional[str]
    zone_id: Optional[str]
    track_id: Optional[int]
    person_name: Optional[str] = None
    person_role: Optional[str] = None
    display_name: Optional[str] = None
    rank_stars: Optional[int] = None
    rank_title: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    severity: Severity = Severity.GREEN
    risk_score: int = 0
    confidence: float
    description: str
    behavioral_evidence: list[BehavioralEvidence] = Field(default_factory=list)
    snapshot_path: Optional[str] = None
    snapshot_url: Optional[str] = None
    video_clip_path: Optional[str] = None
    timestamp: float
    status: AlertStatus
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[float] = None


class AlertUpdate(BaseModel):
    status: AlertStatus


# ---- authorization rules -------------------------------------------------

class TimeRestrictions(BaseModel):
    """Time-based access restrictions"""
    weekdays: Optional[dict] = None  # {"start": "08:00", "end": "18:00"}
    weekends: Optional[dict] = None  # {"start": "09:00", "end": "14:00"}
    all_days: Optional[dict] = None  # {"start": "08:00", "end": "20:00"}
    special_dates: Optional[dict] = None  # {"2026-09-10": {"start": "08:00", "end": "16:00"}}


class AuthorizationRuleCreate(BaseModel):
    """Schema for creating new authorization rules"""
    name: str
    tag_colors: list[str]  # ["red", "blue", "green", "yellow"]
    allowed_zones: list[str] = Field(default_factory=list)  # ["library", "cafeteria"] or ["*"] for all
    forbidden_zones: list[str] = Field(default_factory=list)  # ["server_room", "principal_office"]
    time_restrictions: Optional[TimeRestrictions] = None
    allowed_objects: list[str] = Field(default_factory=list)  # ["backpack", "laptop", "books"]
    forbidden_objects: list[str] = Field(default_factory=list)  # ["weapons", "large_bags"]
    priority: int = 1  # 0 = highest priority, higher numbers = lower priority
    override_all_rules: bool = False  # Master access - overrides all other rules
    escort_privileges: bool = False  # Can escort others into restricted areas
    requires_escort: bool = False  # Requires escort by someone with escort_privileges


class AuthorizationRuleUpdate(BaseModel):
    """Schema for updating existing authorization rules"""
    name: Optional[str] = None
    tag_colors: Optional[list[str]] = None
    allowed_zones: Optional[list[str]] = None
    forbidden_zones: Optional[list[str]] = None
    time_restrictions: Optional[TimeRestrictions] = None
    allowed_objects: Optional[list[str]] = None
    forbidden_objects: Optional[list[str]] = None
    priority: Optional[int] = None
    override_all_rules: Optional[bool] = None
    escort_privileges: Optional[bool] = None
    requires_escort: Optional[bool] = None
    active: Optional[bool] = None


class AuthorizationRuleOut(AuthorizationRuleCreate):
    """Schema for returning authorization rules"""
    rule_id: str
    created_by: str
    created_at: datetime
    active: bool = True


class AuthorizationTestRequest(BaseModel):
    """Schema for testing authorization rules"""
    tag_color: str
    zone: str
    current_time: Optional[str] = None  # Format: "14:30" or "2026-09-04 14:30"
    objects_carried: list[str] = Field(default_factory=list)


class AuthorizationTestResult(BaseModel):
    """Result of an authorization test"""
    authorized: bool
    reason: str
    matched_rule: Optional[str] = None
    violated_rule: Optional[str] = None
    severity: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    actions_required: list[str] = Field(default_factory=list)
    can_be_escorted: bool = False
    escort_required: bool = False


# ---- attendance / entry logs ----------------------------------------------

class AttendanceEntryOut(BaseModel):
    """Entry log record for face-verified attendance"""
    entry_id: str
    camera_id: str
    camera_name: str
    identity_id: Optional[str] = None  # None if unrecognized
    identity_name: Optional[str] = None
    identity_role: Optional[str] = None
    rank_stars: Optional[int] = None
    rank_title: Optional[str] = None
    verification_confidence: float  # 0-1
    snapshot_path: Optional[str] = None
    timestamp: float
    entry_type: str = "FACE_VERIFIED"  # FACE_VERIFIED, UNKNOWN_FACE
    notes: Optional[str] = None


# ---- incidents & explainability (Pillar 2) --------------------------------

class ExplainabilitySignalOut(BaseModel):
    signal_name: str
    confidence: float
    description: str
    evidence_timestamp: float
    supporting_camera: str = ""


class IncidentTimelineItemOut(BaseModel):
    timestamp: float
    event_type: str
    description: str


class IncidentOut(BaseModel):
    incident_id: str
    incident_type: str
    title: str
    status: str
    priority_score: int
    severity: str
    start_time: float
    last_update_time: float
    cameras_involved: list[str] = Field(default_factory=list)
    primary_track_ids: list[int] = Field(default_factory=list)
    timeline: list[IncidentTimelineItemOut] = Field(default_factory=list)
    explainability_signals: list[ExplainabilitySignalOut] = Field(default_factory=list)
    evidence_snapshots: list[dict] = Field(default_factory=list)
    operator_notes: Optional[str] = None
    acknowledged_by: Optional[str] = None
    resolved_at: Optional[float] = None
    metadata: dict = Field(default_factory=dict)


class IncidentUpdate(BaseModel):
    status: Optional[str] = None  # ACKNOWLEDGED, RESOLVED, FALSE_ALARM
    operator_notes: Optional[str] = None

