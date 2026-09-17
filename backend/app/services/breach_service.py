"""
BreachService — Backend service for storing and querying Security Breach Dossiers.
Manages court-grade forensic evidence packages with cryptographic SHA-256 seals.
"""

from __future__ import annotations

import time
import os
import hashlib
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
import logging

logger = logging.getLogger("garuda.breach_service")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB_NAME", "ibvap")

client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]


class BreachService:
    @staticmethod
    async def create_breach_record(evidence_data: dict) -> dict:
        """Stores a newly captured security breach evidence package into MongoDB."""
        now = time.time()
        breach_id = evidence_data.get("evidence_id") or f"BRC-{time.strftime('%Y%m%d')}-{hashlib.md5(str(now).encode()).hexdigest()[:6].upper()}"
        
        record = {
            "breach_id": breach_id,
            "incident_type": evidence_data.get("incident_type", "RESTRICTED_ZONE_BREACH"),
            "camera_id": evidence_data.get("camera_id", "cam_01"),
            "zone_name": evidence_data.get("zone_name", "Restricted Perimeter"),
            "timestamp": evidence_data.get("timestamp", now),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(evidence_data.get("timestamp", now))),
            "identity_name": evidence_data.get("identity_name", "UNKNOWN INTRUDER"),
            "plate_number": evidence_data.get("plate_number"),
            "priority_score": evidence_data.get("priority_score", 90),
            "violation_code": evidence_data.get("violation_code", "SEC-ZONE-01"),
            "context_frame_url": evidence_data.get("context_frame_url"),
            "face_crop_url": evidence_data.get("face_crop_url"),
            "plate_crop_url": evidence_data.get("plate_crop_url"),
            "sha256_hash": evidence_data.get("sha256_hash"),
            "sharpness_metric": evidence_data.get("sharpness_metric", 0.0),
            "status": "PENDING_REVIEW",  # PENDING_REVIEW | ACKNOWLEDGED | ESCORT_DISPATCHED | DISMISSED
            "fine_amount_inr": evidence_data.get("fine_amount_inr", 500),
            "operator_notes": None,
            "acknowledged_by": None,
            "resolved_at": None,
        }

        try:
            # Save in primary DB
            await db.security_breaches.update_one(
                {"breach_id": breach_id},
                {"$set": record},
                upsert=True
            )
            # Synchronize secondary DB if present
            alt_db = client["garuda_db"]
            await alt_db.security_breaches.update_one(
                {"breach_id": breach_id},
                {"$set": record},
                upsert=True
            )
            logger.info(f"Successfully recorded security breach {breach_id} for zone '{record['zone_name']}'")
        except Exception as e:
            logger.error(f"Failed to record security breach in MongoDB: {e}")

        return record

    @staticmethod
    async def list_breaches(limit: int = 50, status: Optional[str] = None) -> List[dict]:
        """Returns recent security breach dossiers ordered by latest first."""
        query = {}
        if status:
            query["status"] = status
        
        cursor = db.security_breaches.find(query).sort("timestamp", -1).limit(limit)
        results = []
        async for doc in cursor:
            doc["_id"] = str(doc["_id"])
            results.append(doc)
        return results

    @staticmethod
    async def get_breach(breach_id: str) -> Optional[dict]:
        """Fetch full forensic details for a specific breach ID."""
        doc = await db.security_breaches.find_one({"breach_id": breach_id})
        if doc:
            doc["_id"] = str(doc["_id"])
        return doc

    @staticmethod
    async def update_status(breach_id: str, new_status: str, operator_name: str = "Administrator", notes: Optional[str] = None) -> Optional[dict]:
        """Updates the status of a breach (e.g. ACKNOWLEDGED, ESCORT_DISPATCHED, DISMISSED)."""
        update_fields = {
            "status": new_status,
            "acknowledged_by": operator_name,
            "resolved_at": time.time() if new_status in ("ESCORT_DISPATCHED", "DISMISSED") else None,
        }
        if notes:
            update_fields["operator_notes"] = notes

        await db.security_breaches.update_one(
            {"breach_id": breach_id},
            {"$set": update_fields}
        )
        return await BreachService.get_breach(breach_id)
