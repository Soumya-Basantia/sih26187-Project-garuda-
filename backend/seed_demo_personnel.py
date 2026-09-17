"""
Seed Demo Personnel & Vehicles for Project Garuda.
Generates reference biometric photos and registers 512-D FaceNet embeddings in MongoDB.
"""

import asyncio
import cv2
import numpy as np
import uuid
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
from ai_engine.face.face_verifier import FaceVerifier


def generate_reference_face(skin_bgr, hair_bgr, eye_y, mouth_y, seed_name: str) -> np.ndarray:
    """Generates a clean 300x300 portrait image suitable for neural facial embedding."""
    img = np.ones((300, 300, 3), dtype=np.uint8) * 235
    # Shoulders / uniform
    cv2.ellipse(img, (150, 310), (120, 80), 0, 0, 360, (50, 75, 45), -1) # Olive drab border uniform
    # Head & Neck
    cv2.rectangle(img, (130, 200), (170, 250), (int(skin_bgr[0]*0.9), int(skin_bgr[1]*0.9), int(skin_bgr[2]*0.9)), -1)
    cv2.ellipse(img, (150, 160), (80, 100), 0, 0, 360, skin_bgr, -1)
    # Hair / Cap
    cv2.ellipse(img, (150, 105), (85, 55), 0, 180, 360, hair_bgr, -1)
    # Eyebrows
    cv2.line(img, (105, eye_y - 14), (135, eye_y - 12), hair_bgr, 3)
    cv2.line(img, (165, eye_y - 12), (195, eye_y - 14), hair_bgr, 3)
    # Eyes
    cv2.circle(img, (120, eye_y), 8, (25, 20, 15), -1)
    cv2.circle(img, (180, eye_y), 8, (25, 20, 15), -1)
    cv2.circle(img, (122, eye_y - 2), 2, (255, 255, 255), -1)
    cv2.circle(img, (182, eye_y - 2), 2, (255, 255, 255), -1)
    # Nose
    cv2.line(img, (150, eye_y + 10), (150, eye_y + 35), (int(skin_bgr[0]*0.8), int(skin_bgr[1]*0.8), int(skin_bgr[2]*0.8)), 3)
    cv2.line(img, (140, eye_y + 35), (160, eye_y + 35), (int(skin_bgr[0]*0.8), int(skin_bgr[1]*0.8), int(skin_bgr[2]*0.8)), 2)
    # Mouth
    cv2.ellipse(img, (150, mouth_y), (25, 8), 0, 0, 180, (50, 50, 160), -1)
    return img


async def seed():
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB_NAME]

    identities_col = db["identities"]
    vehicles_col = db["vehicles"]

    existing_count = await identities_col.count_documents({})
    if existing_count > 0:
        print(f"MongoDB already contains {existing_count} identities. Skipping duplicate seed.")
        return

    print("Initializing Neural FaceVerifier for identity enrollment...")
    verifier = FaceVerifier()

    officers = [
        {
            "identity_id": "id_rajesh_01",
            "demo_id": "OFF-104",
            "name": "Capt. Rajesh Sharma",
            "role": "Patrol Commander",
            "department": "BSF Sector HQ",
            "plate_number": "MH12AB1234",
            "vehicle_type": "Gypsy / 4x4",
            "skin": (210, 185, 155),
            "hair": (25, 20, 15),
            "eye_y": 145,
            "mouth_y": 215,
        },
        {
            "identity_id": "id_priya_02",
            "demo_id": "OFF-208",
            "name": "Sub-Inspector Priya Verma",
            "role": "Security Lead",
            "department": "Border Surveillance Ops",
            "plate_number": "DL01XY5678",
            "vehicle_type": "Command SUV",
            "skin": (195, 165, 135),
            "hair": (35, 30, 25),
            "eye_y": 150,
            "mouth_y": 220,
        },
    ]

    for off in officers:
        img = generate_reference_face(off["skin"], off["hair"], off["eye_y"], off["mouth_y"], off["name"])
        emb = verifier.enroll(off["identity_id"], off["name"], off["role"], img)
        if emb is None:
            print(f"Failed to extract embedding for {off['name']}")
            continue

        doc = {
            "identity_id": off["identity_id"],
            "demo_id": off["demo_id"],
            "name": off["name"],
            "role": off["role"],
            "department": off["department"],
            "plate_number": off["plate_number"],
            "vehicle_type": off["vehicle_type"],
            "consent_given": True,
            "embedding": emb.tolist(),
        }
        await identities_col.insert_one(doc)

        veh_doc = {
            "vehicle_id": f"veh-{uuid.uuid4().hex[:8]}",
            "plate_number": off["plate_number"],
            "vehicle_type": off["vehicle_type"],
            "owner_name": off["name"],
            "owner_ref": off["identity_id"],
            "watchlist_flag": False,
            "notes": f"Assigned to {off['name']} ({off['role']})",
        }
        await vehicles_col.update_one(
            {"plate_number": off["plate_number"]},
            {"$set": veh_doc},
            upsert=True
        )
        print(f"[OK] Enrolled: {off['name']} | Plate: {off['plate_number']} | 512-D Face Embedding generated")

    # Add 1 Watchlist Vehicle for Threat Intercept Demo
    watchlist_plate = "HR26DQ5551"
    await vehicles_col.update_one(
        {"plate_number": watchlist_plate},
        {"$set": {
            "vehicle_id": f"veh-{uuid.uuid4().hex[:8]}",
            "plate_number": watchlist_plate,
            "vehicle_type": "Sedan",
            "owner_name": "UNKNOWN SUSPECT",
            "owner_ref": None,
            "watchlist_flag": True,
            "notes": "RED NOTICE: Vehicle associated with border smuggling syndicate. Intercept immediately.",
        }},
        upsert=True
    )
    print(f"[OK] Watchlist vehicle registered: {watchlist_plate}")

    print("\nSeeding complete! Identities and 2FA vehicle links stored in MongoDB.")


if __name__ == "__main__":
    asyncio.run(seed())
