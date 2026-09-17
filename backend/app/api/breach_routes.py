"""
FastAPI Routes for Security Breach & Unauthorized Zone Dossiers.
Provides endpoints for retrieving evidence packages, updating action status, and generating audit reports.
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional, List

from backend.app.services.breach_service import BreachService

router = APIRouter(prefix="/api/breaches", tags=["Security Breaches"])


class BreachStatusUpdate(BaseModel):
    status: str
    operator_name: Optional[str] = "Soumya (Admin)"
    notes: Optional[str] = None


class BreachCreateRequest(BaseModel):
    evidence_id: Optional[str] = None
    incident_type: str = "RESTRICTED_ZONE_BREACH"
    camera_id: str
    zone_name: str
    identity_name: str = "UNKNOWN INTRUDER"
    plate_number: Optional[str] = None
    priority_score: int = 90
    violation_code: str = "SEC-ZONE-01"
    context_frame_url: Optional[str] = None
    face_crop_url: Optional[str] = None
    plate_crop_url: Optional[str] = None
    sha256_hash: Optional[str] = None
    sharpness_metric: Optional[float] = 0.0
    fine_amount_inr: Optional[int] = 500


@router.get("/list")
async def list_breaches(limit: int = Query(50, ge=1, le=200), status: Optional[str] = None):
    """List all captured security breaches and evidence packages."""
    return await BreachService.list_breaches(limit=limit, status=status)


@router.get("/{breach_id}")
async def get_breach(breach_id: str):
    """Retrieve full forensic evidence package for a specific breach."""
    record = await BreachService.get_breach(breach_id)
    if not record:
        raise HTTPException(status_code=404, detail="Security breach dossier not found")
    return record


@router.post("/create")
async def create_breach(payload: BreachCreateRequest):
    """Record a newly captured security breach."""
    return await BreachService.create_breach_record(payload.dict())


@router.post("/{breach_id}/status")
async def update_status(breach_id: str, payload: BreachStatusUpdate):
    """Update operational review status (e.g. ACKNOWLEDGED, ESCORT_DISPATCHED)."""
    updated = await BreachService.update_status(
        breach_id=breach_id,
        new_status=payload.status,
        operator_name=payload.operator_name or "Administrator",
        notes=payload.notes
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Security breach not found")
    return updated


@router.get("/{breach_id}/report", response_class=HTMLResponse)
async def generate_forensic_html_report(breach_id: str):
    """Generates a printable court-grade HTML/PDF forensic security breach report."""
    record = await BreachService.get_breach(breach_id)
    if not record:
        raise HTTPException(status_code=404, detail="Breach record not found")

    face_html = f"""
    <div style="flex: 1; border: 1px solid #334155; border-radius: 8px; padding: 12px; background: #0f172a; text-align: center;">
        <h4 style="margin: 0 0 8px 0; color: #38bdf8; font-size: 12px; text-transform: uppercase;">Intruder Facial Crop</h4>
        <img src="{record.get('face_crop_url', '')}" style="max-height: 180px; max-width: 100%; border-radius: 4px; object-fit: cover;" onerror="this.parentElement.style.display='none';" />
        <div style="margin-top: 6px; font-size: 11px; color: #94a3b8;">Identity: <strong>{record.get('identity_name')}</strong></div>
    </div>
    """ if record.get("face_crop_url") else ""

    plate_html = f"""
    <div style="flex: 1; border: 1px solid #334155; border-radius: 8px; padding: 12px; background: #0f172a; text-align: center;">
        <h4 style="margin: 0 0 8px 0; color: #38bdf8; font-size: 12px; text-transform: uppercase;">Vehicle License Plate</h4>
        <img src="{record.get('plate_crop_url', '')}" style="max-height: 180px; max-width: 100%; border-radius: 4px; object-fit: contain;" onerror="this.parentElement.style.display='none';" />
        <div style="margin-top: 6px; font-size: 11px; color: #94a3b8;">Plate OCR: <strong>{record.get('plate_number', 'N/A')}</strong></div>
    </div>
    """ if record.get("plate_crop_url") else ""

    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>PROJECT GARUDA — Forensic Security Breach Report {breach_id}</title>
        <style>
            body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #020617; color: #f8fafc; margin: 0; padding: 24px; }}
            .container {{ max-width: 800px; margin: 0 auto; background: #0b1329; border: 1px solid #1e293b; border-radius: 12px; padding: 32px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }}
            .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #38bdf8; padding-bottom: 16px; margin-bottom: 24px; }}
            .badge {{ background: #dc2626; color: white; padding: 4px 10px; border-radius: 4px; font-weight: bold; font-size: 11px; letter-spacing: 1px; }}
            .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 24px; font-size: 13px; }}
            .label {{ color: #64748b; font-size: 11px; text-transform: uppercase; }}
            .val {{ font-weight: 600; color: #f1f5f9; }}
            .evidence-row {{ display: flex; gap: 16px; margin-bottom: 24px; }}
            .hash-box {{ background: #030712; padding: 12px; border: 1px dashed #334155; border-radius: 6px; font-family: monospace; font-size: 10px; color: #38bdf8; word-break: break-all; }}
            @media print {{ body {{ background: white; color: black; }} .container {{ border: none; box-shadow: none; }} }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div>
                    <h2 style="margin: 0; color: #38bdf8; letter-spacing: 1.5px;">PROJECT GARUDA</h2>
                    <div style="font-size: 11px; color: #94a3b8;">Tactical Video Intelligence & Facility Security Matrix</div>
                </div>
                <div style="text-align: right;">
                    <div class="badge">RESTRICTED ZONE BREACH</div>
                    <div style="font-size: 11px; color: #64748b; margin-top: 4px;">ID: {breach_id}</div>
                </div>
            </div>

            <div class="grid">
                <div><div class="label">Incident Type</div><div class="val">{record.get('incident_type')}</div></div>
                <div><div class="label">Breached Zone</div><div class="val">{record.get('zone_name')}</div></div>
                <div><div class="label">Date & Time</div><div class="val">{record.get('created_at')}</div></div>
                <div><div class="label">Camera Sensor</div><div class="val">{record.get('camera_id')}</div></div>
                <div><div class="label">Intruder Identity</div><div class="val" style="color: {'#4ade80' if 'authorized' in record.get('identity_name', '').lower() else '#f87171'};">{record.get('identity_name')}</div></div>
                <div><div class="label">Vehicle Plate</div><div class="val">{record.get('plate_number') or 'None (Pedestrian)'}</div></div>
                <div><div class="label">Risk Priority Score</div><div class="val" style="color: #ef4444;">{record.get('priority_score')}/100 [CRITICAL ALERT]</div></div>
                <div><div class="label">Current Status</div><div class="val">{record.get('status')}</div></div>
            </div>

            <h3 style="color: #f1f5f9; font-size: 13px; text-transform: uppercase; border-bottom: 1px solid #1e293b; padding-bottom: 6px;">Forensic Evidence Package</h3>
            
            <div style="margin-bottom: 16px; border: 1px solid #334155; border-radius: 8px; overflow: hidden; background: #0f172a; text-align: center;">
                <div style="padding: 6px 12px; background: #1e293b; font-size: 11px; color: #94a3b8; font-weight: 600; text-align: left;">Wide Context Scene (Zone Boundary Intersection)</div>
                <img src="{record.get('context_frame_url', '')}" style="width: 100%; max-height: 340px; object-fit: contain;" />
            </div>

            <div class="evidence-row">
                {face_html}
                {plate_html}
            </div>

            <div class="hash-box">
                <strong>CRYPTOGRAPHIC SHA-256 INTEGRITY SEAL:</strong><br/>
                {record.get('sha256_hash')}
            </div>

            <div style="margin-top: 24px; text-align: center;">
                <button onclick="window.print()" style="padding: 8px 18px; background: #38bdf8; color: #020617; border: none; border-radius: 6px; font-weight: bold; cursor: pointer;">Print / Save as PDF</button>
            </div>
        </div>
    </body>
    </html>
    """
