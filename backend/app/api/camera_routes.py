import uuid
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.database import cameras_col
from app.auth import get_current_user, require_role, verify_token_string
from app.models.schemas import CameraCreate, CameraOut, UserRole
from app.services.pipeline_manager import pipeline_manager

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


from urllib.parse import urlsplit, urlunsplit

def mask_source_uri(uri: str) -> str:
    """Masks embedded RTSP/HTTP credentials: rtsp://user:pass@host -> rtsp://***:***@host"""
    if not uri:
        return uri
    try:
        parts = urlsplit(uri)
        if parts.username or parts.password:
            host_port = parts.hostname or ""
            if parts.port:
                host_port += f":{parts.port}"
            masked_netloc = f"***:***@{host_port}"
            return urlunsplit((parts.scheme, masked_netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        pass
    return re.sub(r'://.*@', r'://***:***@', uri)


@router.get("", response_model=list[CameraOut])
async def list_cameras(user=Depends(get_current_user)):
    cameras = await cameras_col.find().to_list(length=100)
    out = []
    for c in cameras:
        live_status = pipeline_manager.get_camera_status(c["camera_id"])
        out.append(CameraOut(
            camera_id=c["camera_id"], name=c["name"], location=c["location"],
            source_type=c["source_type"], source_uri=mask_source_uri(c.get("source_uri", "")),
            device_category=c.get("device_category", "cctv"),
            protocol=c.get("protocol"),
            status=live_status.get("status", "OFFLINE") if live_status else "OFFLINE",
            fps=live_status.get("target_fps") if live_status else c.get("target_fps"),
            last_heartbeat=live_status.get("last_heartbeat") if live_status else None,
            ai_enabled=live_status.get("ai_enabled", True) if live_status else c.get("ai_enabled", True),
            rotation=live_status.get("rotation", 0) if live_status else c.get("rotation", 0),
        ))
    return out


@router.post("", response_model=CameraOut)
async def add_camera(camera: CameraCreate, _admin=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    camera_id = f"cam_{uuid.uuid4().hex[:8]}"
    doc = {
        "camera_id": camera_id,
        "name": camera.name,
        "location": camera.location,
        "source_type": camera.source_type.value,
        "source_uri": camera.source_uri,
        "target_fps": camera.target_fps,
        "device_category": camera.device_category or "cctv",
        "protocol": camera.protocol,
        "ai_enabled": camera.ai_enabled,
        "rotation": camera.rotation or 0,
    }
    await cameras_col.insert_one(doc)
    pipeline_manager.start_camera(doc)
    status_info = pipeline_manager.get_camera_status(camera_id)
    return CameraOut(camera_id=camera_id, name=camera.name, location=camera.location,
                      source_type=camera.source_type, source_uri=mask_source_uri(camera.source_uri),
                      device_category=camera.device_category or "cctv",
                      protocol=camera.protocol,
                      fps=status_info.get("target_fps") if status_info else camera.target_fps,
                      ai_enabled=status_info.get("ai_enabled", True) if status_info else True,
                      rotation=status_info.get("rotation", 0) if status_info else (camera.rotation or 0),
                      status="ONLINE")


@router.post("/{camera_id}/toggle-ai")
async def toggle_camera_ai(camera_id: str, _user=Depends(get_current_user)):
    """Dynamically toggles a camera between AI Core and Passthrough Standby mode."""
    live_status = pipeline_manager.get_camera_status(camera_id)
    if not live_status:
        raise HTTPException(status_code=404, detail="Camera not running")
    
    current_ai = live_status.get("ai_enabled", True)
    new_ai = not current_ai
    ok = pipeline_manager.set_camera_ai_mode(camera_id, new_ai)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to toggle camera AI mode")
    
    await cameras_col.update_one({"camera_id": camera_id}, {"$set": {"ai_enabled": new_ai}})
    return {"camera_id": camera_id, "ai_enabled": new_ai, "message": f"Camera {camera_id} switched to {'AI CORE' if new_ai else 'PASSTHROUGH STANDBY'}"}


@router.post("/{camera_id}/rotate")
async def rotate_camera(camera_id: str, payload: Optional[dict] = None, _user=Depends(get_current_user)):
    """Dynamically rotates camera feed by 90 degrees clockwise (0, 90, 180, 270)."""
    live_status = pipeline_manager.get_camera_status(camera_id)
    if not live_status:
        raise HTTPException(status_code=404, detail="Camera not running")
    
    current_rot = live_status.get("rotation", 0)
    if payload and "rotation" in payload:
        new_rot = int(payload["rotation"]) % 360
    else:
        new_rot = (current_rot + 90) % 360
    
    ok = pipeline_manager.set_camera_rotation(camera_id, new_rot)
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to rotate camera")
    
    await cameras_col.update_one({"camera_id": camera_id}, {"$set": {"rotation": new_rot}})
    return {"camera_id": camera_id, "rotation": new_rot, "message": f"Camera {camera_id} rotation set to {new_rot}°"}


@router.delete("/{camera_id}")
async def remove_camera(camera_id: str, _admin=Depends(require_role(UserRole.ADMIN))):
    pipeline_manager.stop_camera(camera_id)
    result = await cameras_col.delete_one({"camera_id": camera_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"deleted": camera_id}


@router.get("/{camera_id}/stream")
async def stream_camera(camera_id: str, token: Optional[str] = Query(None)):
    """
    MJPEG live stream WITH annotations burned in by the pipeline.
    Secured by JWT passed via ?token= query parameter (for standard browser <img> tags).
    """
    if token:
        verify_token_string(token)
    generator = pipeline_manager.mjpeg_generator(camera_id)
    if generator is None:
        raise HTTPException(status_code=404, detail="Camera not found or not running")
    return StreamingResponse(generator, media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/{camera_id}/snapshot")
async def get_snapshot(camera_id: str, token: Optional[str] = Query(None)):
    """Single current frame — secured by JWT token."""
    if token:
        verify_token_string(token)
    frame_bytes = pipeline_manager.get_snapshot_jpeg(camera_id)
    if frame_bytes is None:
        raise HTTPException(status_code=404, detail="No frame available for this camera yet")
    from fastapi.responses import Response
    return Response(content=frame_bytes, media_type="image/jpeg")
