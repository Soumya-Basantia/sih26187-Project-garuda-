import uuid
from fastapi import APIRouter, Depends, HTTPException

from app.database import zones_col
from app.auth import get_current_user, require_role
from app.models.schemas import ZoneCreate, ZoneOut, UserRole
from app.services.pipeline_manager import pipeline_manager

router = APIRouter(prefix="/api/zones", tags=["zones"])


@router.get("", response_model=list[ZoneOut])
async def list_zones(camera_id: str = None, user=Depends(get_current_user)):
    query = {"camera_id": camera_id} if camera_id else {}
    zones = await zones_col.find(query).to_list(length=200)
    return [ZoneOut(zone_id=z["zone_id"], **{k: v for k, v in z.items() if k not in ("_id", "zone_id")}) for z in zones]


@router.post("", response_model=ZoneOut)
async def create_zone(zone: ZoneCreate, _admin=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    if len(zone.polygon) < 3:
        raise HTTPException(status_code=400, detail="A zone polygon needs at least 3 points")
    zone_id = f"zone_{uuid.uuid4().hex[:8]}"
    doc = {"zone_id": zone_id, **zone.model_dump()}
    await zones_col.insert_one(doc)
    await pipeline_manager.reload_zones()
    return ZoneOut(zone_id=zone_id, **zone.model_dump())


@router.patch("/{zone_id}", response_model=ZoneOut)
async def update_zone(zone_id: str, zone: ZoneCreate, _admin=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR))):
    result = await zones_col.update_one({"zone_id": zone_id}, {"$set": zone.model_dump()})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Zone not found")
    await pipeline_manager.reload_zones()
    return ZoneOut(zone_id=zone_id, **zone.model_dump())


@router.delete("/{zone_id}")
async def delete_zone(zone_id: str, _admin=Depends(require_role(UserRole.ADMIN))):
    result = await zones_col.delete_one({"zone_id": zone_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Zone not found")
    await pipeline_manager.reload_zones()
    return {"deleted": zone_id}
