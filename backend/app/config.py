"""
Central configuration, loaded from environment variables (.env).
No secrets are hardcoded anywhere in the codebase — see .env.example.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=project_root / ".env")

sys.path.insert(0, str(project_root))


class Settings:
    MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    MONGO_DB_NAME: str = os.getenv("MONGO_DB_NAME", "garude")

    JWT_SECRET: str = os.getenv("JWT_SECRET", "")  # MUST be set in .env for real use
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))

    SNAPSHOT_DIR: str = os.getenv("SNAPSHOT_DIR", "./data/snapshots")
    DEMO_VIDEO_DIR: str = os.getenv("DEMO_VIDEO_DIR", "../demo/videos")

    YOLO_MODEL_PATH: str = os.getenv("YOLO_MODEL_PATH", "yolov8n.pt")
    YOLO_DEVICE: str = os.getenv("YOLO_DEVICE", "cpu")  # "cpu" or "cuda"
    DETECTION_CONFIDENCE: float = float(os.getenv("DETECTION_CONFIDENCE", "0.20"))
    DETECTION_IMGSZ: int = int(os.getenv("DETECTION_IMGSZ", "640"))
    DEFAULT_INFERENCE_FPS: int = int(os.getenv("DEFAULT_INFERENCE_FPS", "25"))

    # Priority Resource Allocation for Multi-Camera Grid
    MAX_AI_CAMERAS: int = int(os.getenv("MAX_AI_CAMERAS", "12"))
    PASSTHROUGH_FPS: int = int(os.getenv("PASSTHROUGH_FPS", "3"))

    FACE_VERIFICATION_ENABLED: bool = os.getenv("FACE_VERIFICATION_ENABLED", "true").lower() == "true"
    WEAPON_DETECTION_ENABLED: bool = os.getenv("WEAPON_DETECTION_ENABLED", "true").lower() == "true"
    WEAPON_MODEL_PATH: str = os.getenv("WEAPON_MODEL_PATH", "ai_engine/models/threat_yolov8n.pt")
    WEAPON_CONFIDENCE: float = float(os.getenv("WEAPON_CONFIDENCE", "0.82"))

    POSE_ACTION_ENABLED: bool = os.getenv("POSE_ACTION_ENABLED", "true").lower() == "true"
    POSE_MODEL_PATH: str = os.getenv("POSE_MODEL_PATH", "ai_engine/models/yolov8n-pose.pt")

    CORS_ORIGINS: list = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

    EVENT_RETENTION_DAYS: int = int(os.getenv("EVENT_RETENTION_DAYS", "30"))


settings = Settings()

if not settings.JWT_SECRET:
    import secrets
    import logging
    logging.warning(
        "JWT_SECRET not set in .env — generating a random one for this run only. "
        "Set JWT_SECRET explicitly before any real deployment."
    )
    settings.JWT_SECRET = secrets.token_hex(32)
