"""
GARUDE CyberSentry & Zero-Trust REST API Endpoints
==================================================
Exposes endpoints for camera fleet hardening audits, MITRE ATT&CK telemetry,
anti-replay stream detection, and live cyber attack simulation.
"""

from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel

from app.auth import get_current_user, require_role
from app.models.schemas import UserRole
from app.database import cameras_col
from app.services.cybersecurity_service import cybersecurity_service

router = APIRouter(prefix="/api/cybersecurity", tags=["cybersecurity"])


class SimulateAttackRequest(BaseModel):
    attack_type: str = "replay_loop"  # "replay_loop" | "rtsp_mitm" | "brute_force" | "stream_flood"
    camera_id: str = "CAM-01"


@router.get("/posture")
async def get_fleet_cyber_posture(user=Depends(get_current_user)):
    """
    Returns full camera fleet cybersecurity score, vulnerability audit,
    and MITRE ATT&CK for ICS status matrix.
    """
    cameras = await cameras_col.find().to_list(length=100)
    posture = cybersecurity_service.compute_fleet_posture(cameras)
    return posture


@router.get("/threats")
async def get_cyber_threats(user=Depends(get_current_user)):
    """Returns real-time and historical cyber incident logs."""
    return {
        "active_threats": [t for t in cybersecurity_service.active_threats if t.get("status") == "ACTIVE"],
        "all_threats": cybersecurity_service.active_threats,
        "quarantined_cameras": list(cybersecurity_service.quarantined_cameras),
    }


@router.post("/simulate-attack")
async def simulate_cyber_attack(
    payload: SimulateAttackRequest,
    user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))
):
    """
    SIH Jury Demonstration Endpoint:
    Simulates a Video Stream Replay Loop Attack, RTSP MITM Hijack, or Port Brute-Force.
    Demonstrates CyberSentry's real-time detection and automated zero-trust mitigation.
    """
    threat = cybersecurity_service.simulate_attack(
        attack_type=payload.attack_type,
        camera_id=payload.camera_id
    )
    return threat


@router.post("/threats/{incident_id}/resolve")
async def resolve_threat(
    incident_id: str,
    user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))
):
    """Resolves an active cyber incident and de-quarantines the camera node."""
    result = cybersecurity_service.resolve_threat(incident_id)
    return result


@router.post("/reset")
async def reset_cyber_state(user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    """Resets all simulated threats and restores nominal green status."""
    result = cybersecurity_service.reset_all_threats()
    return result


@router.get("/antibodies")
async def get_digital_antibodies(user=Depends(get_current_user)):
    """
    Returns the Digital Antibody System state, pre-trained virus defense matrix,
    fleet resistance score, and dynamic neural synthesis logs.
    """
    return cybersecurity_service.get_immune_system_state()


class TrainAntibodyRequest(BaseModel):
    antibody_id: str


@router.post("/antibodies/train")
async def train_digital_antibody(
    payload: TrainAntibodyRequest,
    user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))
):
    """
    SIH Demonstration:
    Simulates exposure to a known or zero-day virus, extracts the antigen,
    and evolves the neural antibody to harden system defense speed and resistance.
    """
    result = cybersecurity_service.train_or_evolve_antibody(payload.antibody_id)
    return result

