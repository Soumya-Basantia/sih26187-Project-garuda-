import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from app.database import alerts_col, events_col
from app.auth import get_current_user, require_role
from app.models.schemas import AlertOut, AlertUpdate, EventOut, UserRole, AlertStatus

from bson.objectid import ObjectId

logger = logging.getLogger("garuda.alert_routes")

router = APIRouter(prefix="/api", tags=["alerts", "events"])


def _clean_mongo_doc(d: dict) -> dict:
    """Recursively strip MongoDB _id and stringify any ObjectId to ensure clean Pydantic serialization."""
    if not isinstance(d, dict):
        return d
    cleaned = {}
    for k, v in d.items():
        if k == "_id":
            continue
        if isinstance(v, ObjectId):
            cleaned[k] = str(v)
        elif isinstance(v, dict):
            cleaned[k] = _clean_mongo_doc(v)
        elif isinstance(v, list):
            cleaned[k] = [_clean_mongo_doc(item) if isinstance(item, dict) else (str(item) if isinstance(item, ObjectId) else item) for item in v]
        else:
            cleaned[k] = v
    return cleaned


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(status: str = None, user=Depends(get_current_user)):
    query = {"status": status} if status else {}
    alerts = await alerts_col.find(query).sort("timestamp", -1).to_list(length=200)
    return [AlertOut(**_clean_mongo_doc(a)) for a in alerts]


@router.patch("/alerts/{alert_id}", response_model=AlertOut)
async def update_alert(alert_id: str, update: AlertUpdate,
                        user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    import time
    fields = {"status": update.status.value}
    if update.status == AlertStatus.ACKNOWLEDGED:
        fields["acknowledged_by"] = user["username"]
    elif update.status in (AlertStatus.RESOLVED, AlertStatus.FALSE_POSITIVE):
        fields["resolved_at"] = time.time()

    result = await alerts_col.update_one({"alert_id": alert_id}, {"$set": fields})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert = await alerts_col.find_one({"alert_id": alert_id})

    # Active Learning & RLHF Reinforcement Trigger
    try:
        from app.services.pipeline_manager import pipeline_manager
        from app.database import learning_samples_col
        if update.status == AlertStatus.FALSE_POSITIVE:
            sample = pipeline_manager.active_learner.record_operator_feedback(
                camera_id=alert.get("camera_id", "CAM-UNKNOWN"),
                frame=None,
                snapshot_data=alert.get("snapshot_data"),
                alert_id=alert_id,
                is_false_alarm=True,
                class_label=alert.get("event_type", "threat"),
            )
            await learning_samples_col.insert_one(sample.to_dict())
            cam_id = alert.get("camera_id")
            if cam_id:
                prof = pipeline_manager.self_trainer.get_or_create_profile(cam_id)
                prof.adapted_confidence = min(0.48, round(prof.adapted_confidence + 0.03, 2))
                prof.persistence_frames = min(6, prof.persistence_frames + 1)
                prof.status = "NOISE_SUPPRESSED"
                pipeline_manager.apply_camera_sensitivity(cam_id, prof.adapted_confidence)
        elif update.status == AlertStatus.RESOLVED and alert.get("severity") in ("RED", "ORANGE", "YELLOW"):
            sample = pipeline_manager.active_learner.record_operator_feedback(
                camera_id=alert.get("camera_id", "CAM-UNKNOWN"),
                frame=None,
                snapshot_data=alert.get("snapshot_data"),
                alert_id=alert_id,
                is_false_alarm=False,
                class_label=alert.get("event_type", "threat"),
            )
            await learning_samples_col.insert_one(sample.to_dict())
    except Exception as e:
        logger.error(f"Failed to record active learning feedback for alert {alert_id}: {e}")

    return AlertOut(**_clean_mongo_doc(alert))


@router.get("/events", response_model=list[EventOut])
async def list_events(camera_id: str = None, event_type: str = None,
                       severity: str = None, search: str = None,
                       from_ts: float = None, to_ts: float = None,
                       limit: int = 500, user=Depends(get_current_user)):
    query = {}
    if camera_id:
        query["camera_id"] = camera_id
    if event_type:
        query["event_type"] = event_type
    if severity:
        query["severity"] = severity
    if from_ts or to_ts:
        query["timestamp"] = {}
        if from_ts:
            query["timestamp"]["$gte"] = from_ts
        if to_ts:
            query["timestamp"]["$lte"] = to_ts
    if search:
        import re
        escaped_search = re.escape(search.strip())
        regex = {"$regex": escaped_search, "$options": "i"}
        query["$or"] = [
            {"description": regex},
            {"person_name": regex},
            {"camera_id": regex},
            {"event_type": regex},
        ]
    events = await events_col.find(query).sort("timestamp", -1).to_list(length=limit)
    return [EventOut(**_clean_mongo_doc(e)) for e in events]


@router.post("/alerts/clear")
async def clear_all_logs(user=Depends(get_current_user)):
    """Reset all active alerts, detection logs, and pipeline in-memory states."""
    from app.services.pipeline_manager import pipeline_manager
    await alerts_col.update_many({"status": "NEW"}, {"$set": {"status": "RESOLVED"}})
    pipeline_manager.reset_logs()
    return {"status": "success", "message": "All operational logs and deduplication states reset."}


@router.get("/alerts/{alert_id}/pdf")
async def export_alert_pdf(alert_id: str, user=Depends(get_current_user)):
    """
    Export a court-admissible PDF incident report for a Garuda alert.
    Includes evidence snapshot, blockchain Merkle hash, and Section 65B certification.
    """
    import base64
    from app.services.pdf_generator import generate_incident_pdf

    alert = await alerts_col.find_one({"alert_id": alert_id})
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")

    blockchain_hash = alert.get("blockchain_hash")

    snapshot_bytes = None
    snapshot_b64 = alert.get("snapshot_data")
    if snapshot_b64:
        try:
            if isinstance(snapshot_b64, str) and snapshot_b64.startswith("data:image"):
                snapshot_b64 = snapshot_b64.split(",", 1)[1]
            snapshot_bytes = base64.b64decode(snapshot_b64)
        except Exception:
            snapshot_bytes = None

    alert_dict = dict(alert)
    alert_dict.pop("_id", None)

    try:
        pdf_bytes = generate_incident_pdf(
            alert=alert_dict,
            blockchain_hash=blockchain_hash,
            snapshot_bytes=snapshot_bytes,
        )
        filename = f"garuda_incident_{alert_id[:8]}.pdf"
        media_type = "application/pdf"
        if pdf_bytes[:4] != b"%PDF":
            media_type = "text/plain; charset=utf-8"
            filename = f"garuda_incident_{alert_id[:8]}.txt"
        return Response(
            content=pdf_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        logger.error("PDF generation failed for alert %s: %s", alert_id, e)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


@router.get("/events/{event_id}/pdf")
async def export_event_pdf(event_id: str, user=Depends(get_current_user)):
    """
    Export a court-admissible PDF incident report for any forensic event.
    Includes evidence snapshot, blockchain Merkle hash, and Section 65B certification.
    """
    import base64
    from app.services.pdf_generator import generate_incident_pdf

    event = await events_col.find_one({"event_id": event_id})
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    blockchain_hash = event.get("blockchain_hash")

    snapshot_bytes = None
    snapshot_b64 = event.get("snapshot_data")
    if snapshot_b64:
        try:
            if isinstance(snapshot_b64, str) and snapshot_b64.startswith("data:image"):
                snapshot_b64 = snapshot_b64.split(",", 1)[1]
            snapshot_bytes = base64.b64decode(snapshot_b64)
        except Exception:
            snapshot_bytes = None

    event_dict = dict(event)
    event_dict.pop("_id", None)

    try:
        pdf_bytes = generate_incident_pdf(
            alert=event_dict,
            blockchain_hash=blockchain_hash,
            snapshot_bytes=snapshot_bytes,
        )
        filename = f"garuda_forensic_{event_id[:8]}.pdf"
        media_type = "application/pdf"
        if pdf_bytes[:4] != b"%PDF":
            media_type = "text/plain; charset=utf-8"
            filename = f"garuda_forensic_{event_id[:8]}.txt"
        return Response(
            content=pdf_bytes,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        logger.error("PDF generation failed for event %s: %s", event_id, e)
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


# ---- Incidents & Explainability (Pillar 2) ---------------------------------

@router.get("/incidents")
async def list_incidents(status: str = None, user=Depends(get_current_user)):
    from ai_engine.events.incident_engine import incident_engine
    active = incident_engine.get_active_incidents()
    resolved = list(incident_engine.resolved_incidents.values())
    all_incidents = active + resolved
    if status:
        all_incidents = [i for i in all_incidents if i.status.value.upper() == status.upper()]
    all_incidents.sort(key=lambda x: x.last_update_time, reverse=True)
    return [i.to_dict() for i in all_incidents]


@router.get("/incidents/{incident_id}")
async def get_incident(incident_id: str, user=Depends(get_current_user)):
    from ai_engine.events.incident_engine import incident_engine
    inc = incident_engine.active_incidents.get(incident_id) or incident_engine.resolved_incidents.get(incident_id)
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return inc.to_dict()


@router.patch("/incidents/{incident_id}")
async def update_incident(incident_id: str, update: dict,
                          user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    from ai_engine.events.incident_engine import incident_engine
    st = update.get("status")
    notes = update.get("operator_notes")

    if st == "ACKNOWLEDGED":
        inc = incident_engine.acknowledge_incident(incident_id, user.get("username", "operator"))
    elif st in ("RESOLVED", "FALSE_ALARM"):
        is_fa = (st == "FALSE_ALARM")
        inc = incident_engine.resolve_incident(incident_id, operator_notes=notes, is_false_alarm=is_fa)
    else:
        inc = incident_engine.active_incidents.get(incident_id) or incident_engine.resolved_incidents.get(incident_id)
        if inc and notes:
            inc.operator_notes = notes

    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")
    return inc.to_dict()


# ---- Edge Resource & Bandwidth Telemetry (Pillar 4) -----------------------

@router.get("/edge/telemetry")
async def get_edge_telemetry(user=Depends(get_current_user)):
    from app.services.store_and_forward import edge_telemetry_collector
    from app.services.pipeline_manager import pipeline_manager
    active_count = len(pipeline_manager.pipelines)
    return edge_telemetry_collector.get_telemetry_snapshot(active_pipeline_count=max(active_count, 1))


@router.post("/edge/simulate-disconnect")
async def simulate_edge_disconnect(duration_sec: float = 10.0,
                                   user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    from app.services.store_and_forward import store_and_forward_queue
    store_and_forward_queue.simulate_network_disconnect(duration_sec=duration_sec)
    return {
        "status": "OFFLINE",
        "duration_sec": duration_sec,
        "message": f"Simulated network outage started for {duration_sec}s. Edge processing continues locally.",
    }


@router.post("/edge/reconnect")
async def manual_edge_reconnect(user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    from app.services.store_and_forward import store_and_forward_queue, NetworkStatus
    synced = store_and_forward_queue.set_network_status(NetworkStatus.ONLINE)
    return {
        "status": "ONLINE",
        "synced_events_count": synced,
        "message": f"Edge reconnected successfully. {synced} spooled events synchronized with C2.",
    }



