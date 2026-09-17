"""
MongoDB connection (Motor async driver) + index setup.
"""

import logging
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

logger = logging.getLogger("garude.database")

client = AsyncIOMotorClient(settings.MONGO_URI)
db = client[settings.MONGO_DB_NAME]

# collections
users_col = db["users"]
cameras_col = db["cameras"]
zones_col = db["zones"]
identities_col = db["authorized_identities"]
vehicles_col = db["vehicles"]
events_col = db["events"]
alerts_col = db["alerts"]
authorization_rules_col = db["authorization_rules"]
attendance_entries_col = db["attendance_entries"]
logs_col = db["system_logs"]
settings_col = db["settings"]
learning_samples_col = db["learning_samples"]
model_checkpoints_col = db["model_checkpoints"]
adaptive_tuning_col = db["adaptive_tuning"]
dataset_versions_col = db["dataset_versions"]
learning_events_col = db["learning_events"]
feedback_records_col = db["feedback_records"]
camera_profiles_col = db["camera_profiles"]


async def ensure_indexes():
    """Called on startup. Safe to call repeatedly (idempotent)."""
    try:
        await users_col.create_index("username", unique=True)
        await cameras_col.create_index("camera_id", unique=True)
        await zones_col.create_index("camera_id")
        await identities_col.create_index("demo_id", unique=True)
        await vehicles_col.create_index("plate_number", unique=True)
        await events_col.create_index([("timestamp", -1)])
        await events_col.create_index("track_id")
        await events_col.create_index("camera_id")
        await alerts_col.create_index([("timestamp", -1)])
        await alerts_col.create_index("status")
        await authorization_rules_col.create_index("rule_id", unique=True)
        await authorization_rules_col.create_index("priority")
        await attendance_entries_col.create_index([("timestamp", -1)])
        await attendance_entries_col.create_index("camera_id")
        await attendance_entries_col.create_index("identity_id")
        await learning_samples_col.create_index("sample_id", unique=True)
        await learning_samples_col.create_index([("timestamp", -1)])
        await learning_samples_col.create_index("camera_id")
        await model_checkpoints_col.create_index("version", unique=True)
        await dataset_versions_col.create_index("version_id", unique=True)
        await learning_events_col.create_index([("timestamp", -1)])
        await feedback_records_col.create_index("feedback_id", unique=True)
        await camera_profiles_col.create_index("camera_id", unique=True)
        logger.info("MongoDB indexes ensured")
    except Exception as e:
        logger.error(f"Failed to create indexes (is MongoDB running?): {e}")
        # graceful degradation: don't crash startup if Mongo isn't reachable yet;
        # API calls that need it will surface a clear 503 instead
