"""
GARUDE Backend — FastAPI application entrypoint.

Run with:  uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

import asyncio
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import ensure_indexes
from app.database import users_col
from app.auth import hash_password, get_current_user, require_role
from app.models.schemas import UserRole

from app.services.pipeline_manager import pipeline_manager
from app.websocket.manager import manager as ws_manager

from app.api import auth_routes, camera_routes, zone_routes, identity_routes, alert_routes, vehicle_routes, authorization_routes, attendance_routes, learning_routes, blockchain_routes, cybersecurity_routes, breach_routes

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("garude.main")

app = FastAPI(title="GARUDE — AI-Powered Video Intelligence Platform", version="0.1.0")

# Security-hardened CORS origins policy
cors_origins = [orig.strip() for orig in settings.CORS_ORIGINS if orig.strip()]
if not cors_origins or cors_origins == ["*"]:
    # Fallback to local Vite origins
    cors_origins = ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

import os
from fastapi.staticfiles import StaticFiles

os.makedirs(settings.SNAPSHOT_DIR, exist_ok=True)
app.mount("/snapshots", StaticFiles(directory=settings.SNAPSHOT_DIR), name="snapshots")
app.mount("/api/snapshots", StaticFiles(directory=settings.SNAPSHOT_DIR), name="api_snapshots")

os.makedirs("data/evidence", exist_ok=True)
app.mount("/data/evidence", StaticFiles(directory="data/evidence"), name="evidence")

app.include_router(auth_routes.router)
app.include_router(camera_routes.router)
app.include_router(zone_routes.router)
app.include_router(identity_routes.router)
app.include_router(alert_routes.router)
app.include_router(vehicle_routes.router)
app.include_router(authorization_routes.router)
app.include_router(attendance_routes.router)
app.include_router(learning_routes.router)
app.include_router(blockchain_routes.router)
app.include_router(cybersecurity_routes.router)
app.include_router(breach_routes.router)


@app.on_event("startup")
async def on_startup():
    await ensure_indexes()
    
    # Auto-seed initial demo blockchain evidence blocks if only Genesis exists
    try:
        from app.services.blockchain_service import blockchain_ledger
        if len(blockchain_ledger.chain) == 1:
            import time as _t
            now = _t.time()
            blockchain_ledger.record_alert_evidence({
                "alert_id": "alt-sentry-001",
                "camera_id": "CAM-01",
                "camera_name": "Zero-Line Thermal Sentry",
                "event_type": "PERIMETER_BREACH_CROSSING",
                "severity": "RED",
                "timestamp": now - 7200,
                "snapshot_data": "/snapshots/alt-sentry-001.jpg",
                "composite_risk_score": 96,
            }, operator_name="AUTONOMOUS_AI_SENTRY")
            blockchain_ledger.record_alert_evidence({
                "alert_id": "alt-sentry-002",
                "camera_id": "CAM-02",
                "camera_name": "Vehicle Transit Gate Optical",
                "event_type": "UNAUTHORIZED_DRIVER_MISMATCH",
                "severity": "ORANGE",
                "timestamp": now - 3600,
                "snapshot_data": "/snapshots/alt-sentry-002.jpg",
                "composite_risk_score": 88,
            }, operator_name="CAPT_VIKRAM_SINGH")
            logger.info("Auto-seeded demo evidence blocks onto Garuda-Chain ledger.")
    except Exception as e:
        logger.warning(f"Could not auto-seed blockchain demo blocks: {e}")
    
    # Auto-seed admin for mock DB / new installation
    existing_admin = await users_col.find_one({"username": "admin"})
    if not existing_admin:
        initial_admin_pwd = os.getenv("ADMIN_INITIAL_PASSWORD", "admin")
        await users_col.insert_one({
            "username": "admin",
            "password_hash": hash_password(initial_admin_pwd),
            "role": "ADMIN",
        })
        if initial_admin_pwd == "admin":
            logger.warning("⚠️ SECURITY WARNING: Default admin credentials ('admin' / 'admin') seeded! Configure ADMIN_INITIAL_PASSWORD in .env for production.")
        else:
            logger.info("Auto-seeded admin user with secure ADMIN_INITIAL_PASSWORD from environment.")

    # Auto-seed demo vehicles for immediate ANPR checkpoint evaluation
    from app.database import vehicles_col
    existing_veh = await vehicles_col.count_documents({})
    if existing_veh == 0:
        await vehicles_col.insert_many([
            {
                "vehicle_id": "veh-demo-01",
                "plate_number": "DL01AB1234",
                "vehicle_type": "SUV",
                "owner_name": "Capt. Vikram Singh",
                "watchlist_flag": False,
                "notes": "Border Patrol Commander — High Priority Clearance",
            },
            {
                "vehicle_id": "veh-demo-02",
                "plate_number": "JK02XY9999",
                "vehicle_type": "Heavy Truck",
                "owner_name": "Unknown Suspect",
                "watchlist_flag": True,
                "notes": "🚨 BOLO Alert: Suspected infiltration logistics vehicle",
            }
        ])
        logger.info("Auto-seeded 2 demo vehicles: DL01AB1234 (Cleared) and JK02XY9999 (Watchlist)")

    pipeline_manager.set_event_loop(asyncio.get_running_loop())
    await pipeline_manager.startup()
    logger.info("GARUDE backend started")


@app.on_event("shutdown")
async def on_shutdown():
    for camera_id in list(pipeline_manager.pipelines.keys()):
        pipeline_manager.stop_camera(camera_id)


@app.get("/api/system/health")
async def health():
    import shutil, time as _time
    from app.database import cameras_col

    camera_statuses = {}
    all_cams = await cameras_col.find().to_list(length=100)
    for cam in all_cams:
        cid = cam["camera_id"]
        status = pipeline_manager.get_camera_status(cid)
        is_running = cid in pipeline_manager.pipelines
        camera_statuses[cid] = {
            "camera_id": cid,
            "name": cam.get("name", cid),
            "source_type": cam.get("source_type", "rtsp"),
            "location": cam.get("location", "Facility"),
            "status": "ONLINE" if is_running else "OFFLINE",
            "fps": status.get("fps", 0) if status else (cam.get("target_fps", 8) if is_running else 0),
            "latency_ms": status.get("latency_ms", 32) if status else 0,
            "is_alive": is_running,
        }

    # Disk usage telemetry
    total_b, used_b, free_b = shutil.disk_usage(settings.SNAPSHOT_DIR or ".")
    disk_telemetry = {
        "total_gb": round(total_b / (1024**3), 1),
        "used_gb": round(used_b / (1024**3), 1),
        "free_gb": round(free_b / (1024**3), 1),
        "percent_used": round((used_b / total_b) * 100, 1),
    }

    return {
        "status": "ok",
        "cameras": camera_statuses,
        "active_alerts": len(pipeline_manager.alert_engine.get_active_alerts()),
        "disk": disk_telemetry,
        "timestamp": _time.time(),
    }


@app.post("/api/system/cameras/{camera_id}/reconnect")
async def reconnect_camera(camera_id: str, _user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    """Gracefully restarts a camera pipeline to re-establish dropped RTSP or USB webcam streams."""
    from app.database import cameras_col
    cam_doc = await cameras_col.find_one({"camera_id": camera_id})
    if not cam_doc:
        raise HTTPException(status_code=404, detail="Camera not found")
    
    pipeline_manager.stop_camera(camera_id)
    await asyncio.sleep(0.3)
    pipeline_manager.start_camera(cam_doc)
    logger.info(f"Reconnected camera stream: {camera_id}")
    return {"status": "success", "message": f"Camera {camera_id} reconnected successfully."}


@app.post("/api/system/cleanup-snapshots")
async def cleanup_old_snapshots(payload: dict = None, _admin=Depends(require_role(UserRole.ADMIN))):
    """Prunes local snapshot evidence older than N days to prevent drive exhaustion."""
    import time as _time, os as _os
    days = (payload or {}).get("days", 7)
    cutoff = _time.time() - (days * 86400)
    removed = 0

    if _os.path.exists(settings.SNAPSHOT_DIR):
        for fname in _os.listdir(settings.SNAPSHOT_DIR):
            fpath = _os.path.join(settings.SNAPSHOT_DIR, fname)
            if _os.path.isfile(fpath):
                if _os.path.getmtime(fpath) < cutoff:
                    try:
                        _os.remove(fpath)
                        removed += 1
                    except Exception:
                        pass

    logger.info(f"Purged {removed} local snapshots older than {days} days")
    return {"status": "success", "removed_files": removed, "retention_days": days}


@app.post("/api/system/clear-all-snapshots")
async def clear_all_snapshots(_admin=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    """Completely purges all physical snapshot image files and clears snapshot_data/snapshot_url from MongoDB collections."""
    import os as _os
    from app.database import db, alerts_col, events_col, attendance_entries_col
    removed_files = 0
    if _os.path.exists(settings.SNAPSHOT_DIR):
        for fname in _os.listdir(settings.SNAPSHOT_DIR):
            if fname.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                fpath = _os.path.join(settings.SNAPSHOT_DIR, fname)
                try:
                    if _os.path.isfile(fpath):
                        _os.remove(fpath)
                        removed_files += 1
                except Exception as e:
                    logger.warning(f"Could not remove snapshot file {fpath}: {e}")

    res_anpr = await db["anpr_detections"].update_many(
        {},
        {"$unset": {"snapshot_data": "", "snapshot_path": "", "snapshot_url": ""}}
    )
    res_alerts = await alerts_col.update_many(
        {},
        {"$unset": {"snapshot_data": "", "snapshot_path": "", "snapshot_url": ""}}
    )
    res_events = await events_col.update_many(
        {},
        {"$unset": {"snapshot_data": "", "snapshot_path": "", "snapshot_url": ""}}
    )
    res_attendance = await attendance_entries_col.update_many(
        {},
        {"$unset": {"snapshot_data": "", "snapshot_path": "", "snapshot_url": ""}}
    )
    cleared_records = (
        res_anpr.modified_count +
        res_alerts.modified_count +
        res_events.modified_count +
        res_attendance.modified_count
    )
    logger.info(f"Cleared all snapshots: {removed_files} files deleted, {cleared_records} database records updated.")
    return {
        "status": "success",
        "removed_files": removed_files,
        "cleared_records": cleared_records,
        "message": f"Successfully freed space: deleted {removed_files} image files and cleared {cleared_records} database snapshot records."
    }


@app.get("/api/system/stats")
async def system_stats(_user=Depends(get_current_user)):
    from app.database import (
        cameras_col, zones_col, identities_col, alerts_col, events_col, vehicles_col,
    )
    import time as _time
    now = _time.time()
    day_ago = now - 86400
    return {
        "cameras_total": await cameras_col.count_documents({}),
        "cameras_online": len(pipeline_manager.pipelines),
        "zones_total": await zones_col.count_documents({}),
        "identities_total": await identities_col.count_documents({}),
        "vehicles_total": await vehicles_col.count_documents({}),
        "alerts_total": await alerts_col.count_documents({}),
        "alerts_new": await alerts_col.count_documents({"status": "NEW"}),
        "alerts_24h": await alerts_col.count_documents({"timestamp": {"$gte": day_ago}}),
        "events_total": await events_col.count_documents({}),
        "events_24h": await events_col.count_documents({"timestamp": {"$gte": day_ago}}),
    }


@app.get("/api/settings")
async def get_settings(_user=Depends(get_current_user)):
    from app.database import settings_col
    doc = await settings_col.find_one({"_id": "app_settings"})
    if doc:
        doc.pop("_id", None)
        return doc
    return {
        "detection_confidence": settings.DETECTION_CONFIDENCE,
        "default_inference_fps": settings.DEFAULT_INFERENCE_FPS,
        "face_verification_enabled": settings.FACE_VERIFICATION_ENABLED,
        "event_retention_days": settings.EVENT_RETENTION_DAYS,
        "abandoned_object_seconds": 15,
        "person_departure_distance": 250,
        "audio_alarm_enabled": True,
        "critical_siren_enabled": True,
    }


@app.put("/api/settings")
async def update_settings(payload: dict, _admin=Depends(require_role(UserRole.ADMIN))):
    from app.database import settings_col
    await settings_col.update_one(
        {"_id": "app_settings"},
        {"$set": payload},
        upsert=True,
    )

    # Hot-sync to all active in-memory camera pipelines
    conf = payload.get("detection_confidence")
    fps = payload.get("default_inference_fps")
    face_en = payload.get("face_verification_enabled")

    for pipe in pipeline_manager.pipelines.values():
        if conf is not None:
            pipe.confidence_threshold = float(conf)
        if fps is not None:
            pipe.target_fps = int(fps)
        if face_en is not None:
            pipe.face_verification_enabled = bool(face_en)

    logger.info(f"Hot-synced settings to {len(pipeline_manager.pipelines)} active pipelines: conf={conf}, fps={fps}")
    return {"status": "ok", "settings": payload}


@app.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    # Authenticate WebSocket handshake via ?token=...
    token = websocket.query_params.get("token")
    if token:
        try:
            from app.auth import decode_token
            decode_token(token)
        except Exception:
            logger.warning("Rejected WebSocket connection: invalid or expired token")
            await websocket.close(code=1008)
            return

    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep-alive loop
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
