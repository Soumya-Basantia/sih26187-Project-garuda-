"""
PipelineManager — owns all running CameraPipeline instances and bridges
their synchronous, threaded callbacks (frames, events, alerts) into the
async FastAPI/MongoDB/WebSocket world.

This is the one place threading and asyncio meet: each CameraPipeline runs
its processing loop on its own background thread (see ai_engine/pipeline/
pipeline.py); when it produces an event or alert, we hop back onto the
main asyncio event loop with `run_coroutine_threadsafe` to persist it and
broadcast it over WebSocket.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
import uuid
from typing import Optional

import cv2
import numpy as np

from app.config import settings
from app.database import (
    zones_col, identities_col, alerts_col, events_col, cameras_col, authorization_rules_col,
    learning_samples_col, model_checkpoints_col, adaptive_tuning_col
)

from ai_engine.pipeline.camera_adapter import CameraConfig, SourceType
from ai_engine.pipeline.pipeline import CameraPipeline
from ai_engine.detection.detector import YoloDetectionEngine
from ai_engine.zones.zone_engine import ZoneEngine, Zone, ZoneType
from ai_engine.face.face_verifier import FaceVerifier, EnrolledIdentity
from ai_engine.authorization.authorization_engine import AuthorizationEngine
from ai_engine.tracking.global_threat_registry import GlobalThreatRegistry
from ai_engine.pipeline.alert_engine import AlertEngine
from ai_engine.events.event_engine import Event, Severity
from ai_engine.anpr.plate_recognizer import PlateRecognizer
from ai_engine.detection.weapon_detector import WeaponDetector
from ai_engine.learning.active_learner import ActiveLearningHarvester, HarvestedSample
from ai_engine.learning.self_trainer import SelfTrainingEngine, ModelCheckpoint
from ai_engine.learning.adaptive_filter import AdaptiveNegativeFilter
from ai_engine.detection.pose_action_engine import PoseActionEngine

logger = logging.getLogger("garude.pipeline_manager")


class PipelineManager:
    """
    Singleton that manages all active CameraPipeline instances, routes frames
    to MJPEG clients, and bridges threaded engine events into async FastAPI/MongoDB.
    """
    def __init__(self):
        self.pipelines: dict[str, CameraPipeline] = {}
        self.latest_frames: dict[str, np.ndarray] = {}

        self.zone_engine = ZoneEngine()
        self.face_verifier = FaceVerifier()
        self.auth_engine = AuthorizationEngine()
        self.threat_registry = GlobalThreatRegistry()  # Cross-camera threat continuity
        self.alert_engine = AlertEngine(on_new_alert=self._on_new_alert_sync)
        self.plate_recognizer = PlateRecognizer()
        self.weapon_detector = (
            WeaponDetector(
                model_path=settings.WEAPON_MODEL_PATH,
                confidence_threshold=settings.WEAPON_CONFIDENCE,
                device=settings.YOLO_DEVICE,
            )
            if settings.WEAPON_DETECTION_ENABLED else None
        )

        # Online Few-Shot Adaptive Negative Filter & Spatial Bayesian Prior
        self.adaptive_filter = AdaptiveNegativeFilter()

        # Active Learning Harvester & Self-Training Engine
        self.active_learner = ActiveLearningHarvester(
            uncertainty_min=0.28,
            uncertainty_max=0.58,
            sample_dir=os.path.join(settings.SNAPSHOT_DIR, "active_learning"),
            on_sample_harvested=self._on_sample_harvested_sync,
        )
        self.self_trainer = SelfTrainingEngine(
            baseline_model_path=settings.YOLO_MODEL_PATH,
            checkpoints_dir="./data/models/checkpoints",
            on_hot_reload=self.hot_reload_model,
            adaptive_filter=self.adaptive_filter,
        )
        self.environment_adapters: dict[str, Any] = {}
        self.pose_engine = (
            PoseActionEngine(model_path=settings.POSE_MODEL_PATH)
            if settings.POSE_ACTION_ENABLED else None
        )

        # We instantiate a new YOLO model per camera because Ultralytics YOLO tracker
        # state (`persist=True`) is stored within the model instance. Sharing it across
        # multiple streams causes tracking IDs to mix up and fail.
        # YOLOv8n is very lightweight so memory impact is minimal.
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        os.makedirs(settings.SNAPSHOT_DIR, exist_ok=True)

    def get_or_create_environment_adapter(self, camera_id: str):
        from ai_engine.learning.camera_environment_adapter import CameraEnvironmentAdapter
        if camera_id not in self.environment_adapters:
            self.environment_adapters[camera_id] = CameraEnvironmentAdapter(
                camera_id=camera_id,
                base_confidence=settings.DETECTION_CONFIDENCE,
            )
        return self.environment_adapters[camera_id]

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def _get_detector(self) -> YoloDetectionEngine:
        return YoloDetectionEngine(
            model_path=self.self_trainer.current_model_path if os.path.exists(self.self_trainer.current_model_path) else settings.YOLO_MODEL_PATH,
            confidence_threshold=settings.DETECTION_CONFIDENCE,
            imgsz=settings.DETECTION_IMGSZ,
            device=settings.YOLO_DEVICE,
        )

    # ---- startup: load persisted cameras/zones/identities ------------------

    async def startup(self):
        cameras = await cameras_col.find().to_list(length=100)
        for cam_doc in cameras:
            self.start_camera(cam_doc)
        await self.reload_zones()
        await self.reload_identities()
        await self.reload_authorization_rules()
        await self.reload_vehicles()

    def start_camera(self, cam_doc: dict):
        # Multi-Camera Priority Allocation:
        # First MAX_AI_CAMERAS (default 2: laptop cam + phone cam) get Full AI at 15-20 FPS.
        # Any subsequent cameras connect in lightweight Passthrough Sentry mode (3 FPS, no AI).
        active_ai_count = sum(1 for p in self.pipelines.values() if getattr(p, "ai_enabled", False))

        uri = str(cam_doc.get("source_uri", "")).strip().lower()
        is_demo = uri.startswith("demo") or "demo" in uri or str(cam_doc.get("source_type", "")).lower() == "demo"

        doc_ai_pref = cam_doc.get("ai_enabled")
        if doc_ai_pref is not None:
            enable_ai = bool(doc_ai_pref)
        elif is_demo:
            enable_ai = True  # Demo cameras MUST always have active AI detection enabled!
        else:
            enable_ai = (active_ai_count < settings.MAX_AI_CAMERAS)
        if enable_ai:
            fps_allocation = settings.DEFAULT_INFERENCE_FPS
        else:
            fps_allocation = settings.PASSTHROUGH_FPS
        
        st_val = str(cam_doc.get("source_type", "file")).lower()
        try:
            st = SourceType(st_val)
        except ValueError:
            st = SourceType.FILE

        config = CameraConfig(
            camera_id=cam_doc["camera_id"],
            name=cam_doc["name"],
            location=cam_doc["location"],
            source_type=st,
            source_uri=cam_doc["source_uri"],
            target_fps=fps_allocation,
            ai_enabled=enable_ai,
            rotation=int(cam_doc.get("rotation", 0)),
        )

        detector = self._get_detector()
        cam_conf = self.self_trainer.get_camera_confidence(cam_doc["camera_id"])
        detector.confidence_threshold = cam_conf

        pipeline = CameraPipeline(
            camera_config=config,
            detector=detector,
            zone_engine=self.zone_engine,
            face_verifier=self.face_verifier if settings.FACE_VERIFICATION_ENABLED else None,
            alert_engine=self.alert_engine,
            on_frame=self._on_frame_sync,
            on_event=self._on_event_sync,
            face_verification_enabled=settings.FACE_VERIFICATION_ENABLED,
            auth_engine=self.auth_engine,
            threat_registry=self.threat_registry,
            plate_recognizer=self.plate_recognizer,
            weapon_detector=self.weapon_detector,
            active_learner=self.active_learner,
            adaptive_filter=self.adaptive_filter,
            environment_adapter=self.get_or_create_environment_adapter(config.camera_id),
            pose_engine=self.pose_engine,
        )
        pipeline.start()
        self.pipelines[config.camera_id] = pipeline
        mode_str = "AI CORE (ANPR + DETECTION)" if enable_ai else f"PASSTHROUGH STANDBY ({fps_allocation} FPS)"
        logger.info(f"Started pipeline for camera {config.camera_id} in {mode_str} (fps={fps_allocation}, rot={config.rotation}°)")

    def stop_camera(self, camera_id: str):
        pipeline = self.pipelines.pop(camera_id, None)
        if pipeline:
            pipeline.stop()

    def set_camera_ai_mode(self, camera_id: str, enable_ai: bool) -> bool:
        """Dynamically promotes or demotes a camera between AI Core and Passthrough Standby."""
        pipeline = self.pipelines.get(camera_id)
        if not pipeline:
            return False
        
        target_fps = settings.DEFAULT_INFERENCE_FPS if enable_ai else settings.PASSTHROUGH_FPS
        pipeline.set_ai_enabled(enable_ai, target_fps=target_fps)
        logger.info(f"Switched camera {camera_id} to {'AI CORE' if enable_ai else 'PASSTHROUGH STANDBY'} (fps={target_fps})")
        return True

    def set_camera_rotation(self, camera_id: str, rotation: int) -> bool:
        """Dynamically updates rotation angle for a camera pipeline."""
        pipeline = self.pipelines.get(camera_id)
        if not pipeline:
            return False
        if hasattr(pipeline, "set_rotation"):
            pipeline.set_rotation(rotation)
        logger.info(f"Switched camera {camera_id} rotation to {rotation}°")
        return True

    def get_camera_status(self, camera_id: str) -> Optional[dict]:
        pipeline = self.pipelines.get(camera_id)
        if not pipeline:
            return None
        st = pipeline.get_status()
        st["ai_enabled"] = getattr(pipeline, "ai_enabled", True)
        st["target_fps"] = pipeline.camera.config.target_fps
        st["rotation"] = getattr(pipeline.camera, "rotation", 0)
        return st

    # ---- zones / identities sync from Mongo into the live AI engine --------

    async def reload_zones(self):
        docs = await zones_col.find().to_list(length=500)
        zones = [
            Zone(
                zone_id=d["zone_id"], camera_id=d["camera_id"], name=d["name"],
                zone_type=ZoneType(d["zone_type"]), polygon=[tuple(p) for p in d["polygon"]],
                threshold_seconds=d.get("threshold_seconds", 5.0),
                enabled=d.get("enabled", True),
                active_hours=tuple(d["active_hours"]) if d.get("active_hours") else None,
                authorized_identity_ids=d.get("authorized_identity_ids", []),
                min_rank_stars=d.get("min_rank_stars", 0),
                allow_escort=d.get("allow_escort", False),
                authority_custom_level=d.get("authority_custom_level"),
            )
            for d in docs
        ]
        self.zone_engine.load_zones(zones)
        logger.info(f"Reloaded {len(zones)} zones into the live pipeline")

    async def reload_identities(self):
        docs = await identities_col.find({"embedding": {"$exists": True}}).to_list(length=1000)
        identities = [
            EnrolledIdentity(
                identity_id=d["identity_id"], name=d["name"], role=d["role"],
                embedding=np.array(d["embedding"], dtype=np.float32),
                rank_stars=d.get("rank_stars", 1),
                rank_title=d.get("rank_title", "Officer"),
            )
            for d in docs
        ]
        self.face_verifier.load_enrolled(identities)
        logger.info(f"Reloaded {len(identities)} enrolled identities into the live pipeline")

    async def reload_authorization_rules(self):
        docs = await authorization_rules_col.find().to_list(length=500)
        self.auth_engine.load_rules(docs)
        logger.info(f"Reloaded {len(docs)} authorization rules into the live pipeline")

    async def reload_vehicles(self):
        from app.database import vehicles_col
        docs = await vehicles_col.find().to_list(length=1000)
        self.plate_recognizer.load_watchlist(docs)

    def enroll_face(self, identity_id: str, name: str, role: str, image: np.ndarray, rank_stars: int = 1, rank_title: str = "Officer") -> Optional[np.ndarray]:
        try:
            return self.face_verifier.enroll(identity_id, name, role, image, rank_stars, rank_title)
        except Exception as e:
            logger.error(f"Face enrollment failed for {name}: {e}")
            return None


    def reset_logs(self):
        """Reset all in-memory alert deduplication, ANPR tracking, threat sessions, and face verification sessions."""
        try:
            self.alert_engine._recent_keys.clear()
            self.alert_engine.alerts.clear()
            for p in self.pipelines.values():
                p.event_engine.states.clear()
                p._logged_anpr_tracks.clear()
                p._alerted_watchlist_tracks.clear()
                p._alerted_2fa_tracks.clear()
                p._weapon_incident_active = False
                p._track_identities.clear()
                p._standalone_tracks.clear()
                p._vehicle_plates.clear()
            logger.info("Pipeline manager in-memory logs, tracks, and deduplication states reset.")
        except Exception as e:
            logger.error(f"Error resetting pipeline logs: {e}")

    # ---- callbacks from pipeline threads -> async world ---------------------

    def _on_frame_sync(self, camera_id: str, frame: np.ndarray):
        self.latest_frames[camera_id] = frame

    def _on_event_sync(self, event: Event):
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._persist_event(event), self._loop)

    def _on_new_alert_sync(self, alert):
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._persist_and_broadcast_alert(alert), self._loop)

    def _on_sample_harvested_sync(self, sample: HarvestedSample):
        if self._loop is not None:
            asyncio.run_coroutine_threadsafe(self._persist_learning_sample(sample), self._loop)

    async def _persist_learning_sample(self, sample: HarvestedSample):
        try:
            sample_dict = sample.to_dict()
            await learning_samples_col.insert_one(sample_dict)
            sample_dict.pop("_id", None)
            from app.websocket.manager import manager
            await manager.broadcast({"type": "new_learning_sample", "data": sample_dict})
        except Exception as e:
            logger.error(f"Error persisting/broadcasting learning sample: {e}")

    def hot_reload_model(self, model_path: str):
        """Hot-reloads detector weights across all active camera pipelines with zero downtime."""
        logger.info(f"Hot-reloading model weights to {model_path} across {len(self.pipelines)} pipelines")
        for cam_id, pipeline in self.pipelines.items():
            try:
                pipeline.hot_swap_model(model_path)
            except Exception as e:
                logger.error(f"Failed to hot-reload model for camera {cam_id}: {e}")

    def apply_camera_sensitivity(self, camera_id: str, conf: float):
        """Applies an adaptive confidence threshold to a specific camera pipeline."""
        pipeline = self.pipelines.get(camera_id)
        if pipeline:
            pipeline.set_confidence_threshold(conf)

    @staticmethod
    def _frame_to_base64(frame: np.ndarray, max_width: int = 800) -> Optional[str]:
        if frame is None or frame.size == 0:
            return None
        try:
            h, w = frame.shape[:2]
            if w > max_width:
                scale = max_width / float(w)
                new_h = max(1, int(h * scale))
                frame_to_encode = cv2.resize(frame, (max_width, new_h), interpolation=cv2.INTER_AREA)
            else:
                frame_to_encode = frame
            success, buffer = cv2.imencode('.jpg', frame_to_encode, [int(cv2.IMWRITE_JPEG_QUALITY), 75])
            if not success:
                return None
            b64_str = base64.b64encode(buffer).decode('utf-8')
            return f"data:image/jpeg;base64,{b64_str}"
        except Exception as e:
            logger.error(f"Failed to encode frame to base64: {e}")
            return None

    async def _persist_event(self, event: Event):
        try:
            snapshot_path = None
            snapshot_data = None
            snapshot_frame = event.__dict__.pop("_snapshot_frame", None)
            if snapshot_frame is not None and (event.metadata.get("is_entry_log") or event.severity in (Severity.RED, Severity.YELLOW, Severity.ORANGE)):
                prefix = "entry" if event.metadata.get("is_entry_log") else "event"
                snapshot_path = self._save_snapshot(f"{prefix}_{event.event_id}", snapshot_frame)
                snapshot_data = self._frame_to_base64(snapshot_frame)

            await events_col.insert_one({
                "event_id": event.event_id, "event_type": event.event_type.value,
                "track_id": event.track_id, "camera_id": event.camera_id,
                "zone_id": event.zone_id, "timestamp": event.timestamp,
                "severity": event.severity.value, "confidence": event.confidence,
                "description": event.description, "metadata": event.metadata,
                "person_name": event.metadata.get("person_name"),
                "person_role": event.metadata.get("person_role"),
                "display_name": event.metadata.get("display_name"),
                "rank_stars": event.metadata.get("rank_stars"),
                "rank_title": event.metadata.get("rank_title"),
                "snapshot_path": snapshot_path,
                "snapshot_url": snapshot_path,
                "snapshot_data": snapshot_data,
            })

            # Handle attendance logging for entry events
            if event.metadata.get("is_entry_log"):
                from app.database import attendance_entries_col, cameras_col
                camera = await cameras_col.find_one({"camera_id": event.camera_id})
                camera_name = camera.get("name") if camera else event.camera_id

                await attendance_entries_col.insert_one({
                    'entry_id': f"ent_{int(event.timestamp * 1000)}",
                    'camera_id': event.camera_id,
                    'camera_name': camera_name,
                    'identity_id': event.metadata.get("identity_id"),
                    'identity_name': event.metadata.get("identity_name"),
                    'identity_role': event.metadata.get("identity_role"),
                    'rank_stars': event.metadata.get("rank_stars", 1),
                    'rank_title': event.metadata.get("rank_title", "Officer"),
                    'verification_confidence': event.confidence,
                    'snapshot_path': snapshot_path,
                    'snapshot_url': snapshot_path,
                    'snapshot_data': snapshot_data,
                    'timestamp': event.timestamp,
                    'entry_type': event.metadata.get("entry_type", "FACE_VERIFIED"),
                    'notes': f"Entry at zone {event.zone_id}"
                })

            # Handle ANPR vehicle gate detection logging
            if event.metadata.get("is_anpr_log"):
                from app.database import db, cameras_col
                camera = await cameras_col.find_one({"camera_id": event.camera_id})
                camera_name = camera.get("name") if camera else event.camera_id

                snapshot_url = None
                if snapshot_frame is not None and not snapshot_path:
                    snapshot_path = self._save_snapshot(f"anpr_{event.event_id}", snapshot_frame)
                    snapshot_url = f"/snapshots/anpr_{event.event_id}.jpg"
                    snapshot_data = self._frame_to_base64(snapshot_frame)
                elif snapshot_path:
                    snapshot_url = f"/snapshots/{os.path.basename(snapshot_path)}"
                    if snapshot_frame is not None and not snapshot_data:
                        snapshot_data = self._frame_to_base64(snapshot_frame)

                anpr_record = {
                    "detection_id": f"anpr_{uuid.uuid4().hex[:8]}",
                    "camera_id": event.camera_id,
                    "camera_name": camera_name,
                    "plate_number": event.metadata.get("plate_number"),
                    "vehicle_type": event.metadata.get("vehicle_type", "Vehicle"),
                    "owner_name": event.metadata.get("owner_name"),
                    "status": event.metadata.get("anpr_status", "DETECTED"),
                    "driver_2fa": event.metadata.get("driver_2fa", "N/A"),
                    "is_fuzzy": event.metadata.get("is_fuzzy", False),
                    "confidence": event.confidence,
                    "timestamp": event.timestamp,
                    "snapshot_path": snapshot_path,
                    "snapshot_url": snapshot_url,
                    "snapshot_data": snapshot_data,
                }
                await db["anpr_detections"].insert_one(anpr_record)
                anpr_record.pop("_id", None)

                from app.websocket.manager import manager
                await manager.broadcast({"type": "new_anpr_detection", "data": anpr_record})

            # Pillar 2: Correlate into IncidentEngine & broadcast
            try:
                from ai_engine.events.incident_engine import incident_engine
                incident = incident_engine.process_event(event, snapshot_data=snapshot_data)
                if incident:
                    from app.websocket.manager import manager
                    await manager.broadcast({"type": "incident_update", "data": incident.to_dict()})
            except Exception as inc_err:
                logger.debug(f"Incident correlation error: {inc_err}")
        except Exception as e:
            # graceful degradation: don't crash the pipeline if Mongo write fails;
            # log it so the operator/judge sees it and understands the failure mode
            logger.error(f"Failed to persist event (DB may be down): {e}")

    async def _persist_and_broadcast_alert(self, alert):
        snapshot_path = None
        snapshot_url = None
        snapshot_data = None
        snapshot_frame = alert.__dict__.pop("_snapshot_frame", None)
        if snapshot_frame is not None:
            snapshot_path = self._save_snapshot(alert.alert_id, snapshot_frame)
            snapshot_url = f"/snapshots/{alert.alert_id}.jpg"
            snapshot_data = self._frame_to_base64(snapshot_frame)

        meta = getattr(alert, "metadata", {}) or {}
        person_name = getattr(alert, "person_name", None) or meta.get("person_name")
        person_role = getattr(alert, "person_role", None) or meta.get("person_role")
        display_name = getattr(alert, "display_name", None) or meta.get("display_name")
        rank_stars = getattr(alert, "rank_stars", None) or meta.get("rank_stars")
        rank_title = getattr(alert, "rank_title", None) or meta.get("rank_title")

        doc = {
            "alert_id": alert.alert_id, "event_id": alert.event_id,
            "event_type": alert.event_type.value, "camera_id": alert.camera_id,
            "location": alert.location, "zone_id": alert.zone_id, "track_id": alert.track_id,
            "severity": alert.severity.value, "confidence": alert.confidence,
            "description": alert.description, "snapshot_path": snapshot_path,
            "snapshot_url": snapshot_url,
            "snapshot_data": snapshot_data,
            "timestamp": alert.timestamp, "status": alert.status.value,
            "acknowledged_by": None, "resolved_at": None,
            "metadata": meta,
            "person_name": person_name,
            "person_role": person_role,
            "display_name": display_name,
            "rank_stars": rank_stars,
            "rank_title": rank_title,
        }
        try:
            await alerts_col.insert_one(doc)
            doc.pop("_id", None)
        except Exception as e:
            logger.error(f"Failed to persist alert (DB may be down): {e}")

        # Cryptographic Blockchain Anchoring (Chain of Custody)
        try:
            from app.services.blockchain_service import blockchain_ledger
            blockchain_ledger.record_alert_evidence(doc)
        except Exception as e:
            logger.warning(f"Failed to record blockchain evidence anchor: {e}")

        from app.websocket.manager import manager
        await manager.broadcast({"type": "new_alert", "data": doc})

    def _save_snapshot(self, alert_id: str, frame: np.ndarray) -> str:
        filename = f"{alert_id}.jpg"
        path = os.path.join(settings.SNAPSHOT_DIR, filename)
        cv2.imwrite(path, frame)
        return f"/snapshots/{filename}"

    # ---- MJPEG streaming ------------------------------------------------

    def _get_status_frame(self, camera_id: str, message: Optional[str] = None) -> np.ndarray:
        frame = np.zeros((360, 640, 3), dtype=np.uint8)
        frame[:] = (20, 24, 30)  # Dark sleek UI background
        
        status = message
        if not status:
            cam_status = self.get_camera_status(camera_id)
            status = cam_status.get("status", "CONNECTING") if cam_status else "OFFLINE"

        if status == "ONLINE":
            color = (80, 220, 100)  # emerald
        elif status in ("INITIALIZING", "RECONNECTING"):
            color = (0, 165, 255)   # orange
        else:
            color = (80, 80, 230)   # red

        text = f"CAM {camera_id}: {status}"
        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size = cv2.getTextSize(text, font, 0.7, 2)[0]
        text_x = (frame.shape[1] - text_size[0]) // 2
        text_y = (frame.shape[0] + text_size[1]) // 2
        cv2.putText(frame, text, (text_x, text_y), font, 0.7, color, 2)
        cv2.putText(frame, "Waiting for video feed...", (frame.shape[1] // 2 - 95, text_y + 35), font, 0.45, (140, 140, 140), 1)
        return frame

    def get_snapshot_jpeg(self, camera_id: str) -> Optional[bytes]:
        frame = self.latest_frames.get(camera_id)
        if frame is None:
            frame = self._get_status_frame(camera_id)
        ok, buf = cv2.imencode(".jpg", frame)
        return buf.tobytes() if ok else None

    def mjpeg_generator(self, camera_id: str):
        if camera_id not in self.pipelines:
            return None

        def generate():
            last_frame_ref = None
            last_encoded_bytes = None
            while camera_id in self.pipelines:
                pipeline = self.pipelines.get(camera_id)
                ai_on = getattr(pipeline, "ai_enabled", True) if pipeline else True
                cam_cfg = getattr(getattr(pipeline, "camera", None), "config", None)
                target_fps = getattr(cam_cfg, "target_fps", settings.DEFAULT_INFERENCE_FPS) if cam_cfg else settings.DEFAULT_INFERENCE_FPS
                sleep_interval = (1.0 / max(15, target_fps)) if ai_on else 0.33  # Fluid inference for AI nodes

                frame = self.latest_frames.get(camera_id)
                cam_obj = getattr(pipeline, "camera", None)
                cam_status = getattr(cam_obj, "status", None)
                cam_status_str = cam_status.value if hasattr(cam_status, "value") else str(cam_status)
                last_hb = getattr(cam_obj, "last_heartbeat", None)
                now_t = time.time()
                is_stale = (last_hb is not None and (now_t - last_hb > 5.0))
                is_reconnecting = (cam_status_str in ("RECONNECTING", "OFFLINE", "ERROR"))

                # Fallback to status card if no frame exists, or camera is genuinely disconnected/stale
                if frame is None or is_stale or is_reconnecting:
                    status_msg = "STREAM RECONNECTING..." if (is_stale or is_reconnecting) else cam_status_str
                    frame = self._get_status_frame(camera_id, message=status_msg)

                # Avoid re-encoding identical frame buffer on idle streams
                if frame is not last_frame_ref or last_encoded_bytes is None:
                    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                    if ok:
                        last_encoded_bytes = buf.tobytes()
                        last_frame_ref = frame

                if last_encoded_bytes:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + last_encoded_bytes + b"\r\n")

                time.sleep(sleep_interval)

        return generate()


pipeline_manager = PipelineManager()
