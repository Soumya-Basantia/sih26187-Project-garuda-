from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from app.database import vehicles_col, db
from app.auth import get_current_user, require_role
from app.models.schemas import VehicleCreate, VehicleOut, UserRole
from app.services.pipeline_manager import pipeline_manager
import uuid
import os
import numpy as np
import cv2

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


@router.get("", response_model=list[VehicleOut])
async def list_vehicles(watchlist_only: bool = False, user=Depends(get_current_user)):
    query = {"watchlist_flag": True} if watchlist_only else {}
    docs = await vehicles_col.find(query).to_list(length=500)
    return [VehicleOut(**d) for d in docs]


@router.post("", response_model=VehicleOut)
async def create_vehicle(data: VehicleCreate,
                         user=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    vehicle_id = f"veh-{uuid.uuid4().hex[:8]}"
    doc = {"vehicle_id": vehicle_id, **data.model_dump()}
    await vehicles_col.insert_one(doc)
    await pipeline_manager.reload_vehicles()
    return VehicleOut(**doc)


@router.delete("/{vehicle_id}")
async def delete_vehicle(vehicle_id: str,
                         user=Depends(require_role(UserRole.ADMIN))):
    result = await vehicles_col.delete_one({"vehicle_id": vehicle_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Vehicle not found")
    await pipeline_manager.reload_vehicles()
    return {"deleted": vehicle_id}


@router.get("/anpr-detections")
async def anpr_detections(limit: int = 50, user=Depends(get_current_user)):
    col = db["anpr_detections"]
    docs = await col.find().sort("timestamp", -1).to_list(length=limit)
    for d in docs:
        d.pop("_id", None)
        if not d.get("snapshot_url") and d.get("snapshot_path"):
            d["snapshot_url"] = f"/snapshots/{os.path.basename(d['snapshot_path'])}"
    return docs


@router.get("/stats")
async def vehicle_stats(user=Depends(get_current_user)):
    total = await vehicles_col.count_documents({})
    watchlist = await vehicles_col.count_documents({"watchlist_flag": True})
    detections = await db["anpr_detections"].count_documents({})
    return {"total_vehicles": total, "watchlist_count": watchlist, "total_detections": detections}


@router.post("/scan")
async def scan_plate_image(file: UploadFile = File(...), user=Depends(get_current_user)):
    """Test ANPR recognition directly on an uploaded vehicle/plate image."""
    contents = await file.read()
    np_arr = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Could not decode uploaded image")

    result = pipeline_manager.plate_recognizer.recognize(image)
    return {
        "plate_text": result.plate_text,
        "status": result.status.value,
        "confidence": round(result.confidence * 100, 1),
        "is_fuzzy": result.is_fuzzy,
        "match": result.watchlist_match,
    }

