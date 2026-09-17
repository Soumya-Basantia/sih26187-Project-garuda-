import uuid
import numpy as np
import cv2
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form

from app.database import identities_col, vehicles_col
from app.auth import get_current_user, require_role
from app.models.schemas import IdentityCreate, IdentityOut, UserRole
from app.services.pipeline_manager import pipeline_manager

router = APIRouter(prefix="/api/identities", tags=["identities"])


@router.get("", response_model=list[IdentityOut])
async def list_identities(user=Depends(get_current_user)):
    identities = await identities_col.find().to_list(length=500)
    return [
        IdentityOut(
            identity_id=i["identity_id"], demo_id=i["demo_id"], name=i["name"],
            role=i["role"], department=i.get("department"),
            plate_number=i.get("plate_number"), vehicle_type=i.get("vehicle_type"),
            consent_given=i.get("consent_given", True),
            has_face_enrolled=i.get("embedding") is not None,
            rank_stars=i.get("rank_stars", 1),
            rank_title=i.get("rank_title", "Officer"),
        ) for i in identities
    ]


@router.post("", response_model=IdentityOut)
async def enroll_identity(
    demo_id: str = Form(...),
    name: str = Form(...),
    role: str = Form(...),
    department: str = Form(None),
    plate_number: str = Form(None),
    vehicle_type: str = Form(None),
    consent_given: bool = Form(True),
    rank_stars: int = Form(1),
    rank_title: str = Form("Officer"),
    photo: UploadFile = File(...),
    _admin=Depends(require_role(UserRole.ADMIN, UserRole.OPERATOR)),
):
    """
    Enroll one authorized identity from a single reference photo.
    Optionally links a vehicle plate number so the ANPR engine recognizes
    the vehicle as authorized and matches it to this owner.
    """
    if not consent_given:
        raise HTTPException(status_code=400, detail="Consent is required to enroll a face identity")

    contents = await photo.read()
    np_arr = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Could not decode uploaded photo")

    identity_id = f"id_{uuid.uuid4().hex[:8]}"
    embedding = pipeline_manager.enroll_face(identity_id, name, role, image, rank_stars=int(rank_stars), rank_title=rank_title)
    if embedding is None:
        raise HTTPException(status_code=400, detail="No face detected in the uploaded photo — use a clearer, front-facing photo")

    clean_plate = plate_number.strip().upper().replace(" ", "") if plate_number and plate_number.strip() else None
    v_type = vehicle_type.strip() if vehicle_type and vehicle_type.strip() else "Car"

    doc = {
        "identity_id": identity_id, "demo_id": demo_id, "name": name, "role": role,
        "department": department, "plate_number": clean_plate, "vehicle_type": v_type if clean_plate else None,
        "consent_given": consent_given,
        "rank_stars": int(rank_stars),
        "rank_title": rank_title or "Officer",
        "embedding": embedding.tolist(),
    }
    await identities_col.insert_one(doc)

    # Automatically register vehicle and link to owner if plate was provided
    if clean_plate:
        veh_doc = {
            "vehicle_id": f"veh-{uuid.uuid4().hex[:8]}",
            "plate_number": clean_plate,
            "vehicle_type": v_type,
            "owner_name": name,
            "owner_ref": identity_id,
            "watchlist_flag": False,
            "notes": f"Assigned to {name} ({role})",
        }
        await vehicles_col.update_one(
            {"plate_number": clean_plate},
            {"$set": veh_doc},
            upsert=True
        )
        await pipeline_manager.reload_vehicles()

    return IdentityOut(
        identity_id=identity_id, demo_id=demo_id, name=name, role=role,
        department=department, plate_number=clean_plate, vehicle_type=v_type if clean_plate else None,
        consent_given=consent_given, has_face_enrolled=True,
        rank_stars=int(rank_stars), rank_title=rank_title or "Officer"
    )


@router.delete("/{identity_id}")
async def delete_identity(identity_id: str, _admin=Depends(require_role(UserRole.ADMIN))):
    result = await identities_col.delete_one({"identity_id": identity_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Identity not found")
    await vehicles_col.delete_many({"owner_ref": identity_id})
    await pipeline_manager.reload_identities()
    await pipeline_manager.reload_vehicles()
    return {"deleted": identity_id}
