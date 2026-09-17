"""
CameraPipeline — the full per-camera processing loop:

  CameraAdapter -> YOLO detect+track -> TrackingEngine -> ZoneEngine
  -> TemporalEventEngine -> (optional) FaceVerifier -> AlertEngine
  -> snapshot capture -> callback out to the backend (persist + WebSocket push)

One CameraPipeline instance runs per camera, in its own thread, so a
failure or slowdown on one camera never blocks the others — this is the
concrete mechanism behind "continue processing other cameras" in the
graceful-degradation requirement.
"""

from __future__ import annotations

import concurrent.futures
import logging
import math
import threading
import time
import uuid
from datetime import datetime
from typing import Callable, Optional, Any

import cv2
import numpy as np

from ai_engine.pipeline.camera_adapter import CameraAdapter, CameraConfig, CameraStatus, SensorModality
from ai_engine.detection.detector import YoloDetectionEngine
from ai_engine.tracking.tracker import TrackingEngine, TrackedObject
from ai_engine.zones.zone_engine import ZoneEngine
from ai_engine.events.event_engine import TemporalEventEngine, Event, EventType, Severity, IdentityStatus
from ai_engine.face.face_verifier import FaceVerifier, VerificationStatus
from ai_engine.pipeline.alert_engine import AlertEngine, Alert
from ai_engine.anpr.plate_recognizer import PlateRecognizer, PlateStatus
from ai_engine.detection.weapon_detector import WeaponDetector, WeaponDetection
from ai_engine.detection.vision_enhancer import AdaptiveVisionEnhancer
from ai_engine.detection.thermal_engine import ThermalVisionEngine, ThermalMode, ThermalHeatSignature
from ai_engine.detection.light_source_detector import LightSourceDetector, LightSourceDetection
from ai_engine.detection.pose_action_engine import PoseActionEngine, PoseAction
from ai_engine.events.evidence_scorer import EvidenceScorer

logger = logging.getLogger("garude.pipeline")


class SnapshotSelector:
    """
    Picks the clearest frame for a track rather than trying to fuse faces
    across multiple cameras (deliberately NOT cross-camera re-identification
    to avoid privacy issues). Simple sharpness heuristic via Laplacian variance.
    """
    def __init__(self, min_box_size: int = 40):
        self.min_box_size = min_box_size
        self._best_scores: dict[int, float] = {}
        self._best_frames: dict[int, tuple[float, np.ndarray]] = {}

    def consider(self, track_id: int, frame: np.ndarray, bbox: tuple[float, float, float, float]):
        x1, y1, x2, y2 = [int(v) for v in bbox]
        crop = frame[max(0, y1):max(0, y2), max(0, x1):max(0, x2)]
        if crop.shape[0] < self.min_box_size or crop.shape[1] < self.min_box_size:
            return
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        score = cv2.Laplacian(gray, cv2.CV_64F).var()
        if score > self._best_scores.get(track_id, -1):
            self._best_scores[track_id] = score
            self._best_frames[track_id] = (time.time(), frame.copy())

    def get_best(self, track_id: int) -> Optional[tuple[float, np.ndarray]]:
        return self._best_frames.get(track_id)

    def prune(self, active_track_ids: set[int]):
        for tid in list(self._best_scores.keys()):
            if tid not in active_track_ids:
                self._best_scores.pop(tid, None)
                self._best_frames.pop(tid, None)


class CameraPipeline:
    def __init__(
        self,
        camera_config: CameraConfig,
        detector: YoloDetectionEngine,
        zone_engine: ZoneEngine,
        face_verifier: Optional[FaceVerifier],
        alert_engine: AlertEngine,
        on_frame: Optional[Callable[[str, np.ndarray], None]] = None,
        on_event: Optional[Callable[[Event], None]] = None,
        face_verification_enabled: bool = False,
        auth_engine: Optional[Any] = None,
        threat_registry: Optional[Any] = None,
        plate_recognizer: Optional[PlateRecognizer] = None,
        weapon_detector: Optional[WeaponDetector] = None,
        active_learner: Optional[Any] = None,
        adaptive_filter: Optional[Any] = None,
        environment_adapter: Optional[Any] = None,
        pose_engine: Optional[PoseActionEngine] = None,
    ):
        self.config = camera_config
        self.camera = CameraAdapter(camera_config)
        self.detector = detector           # shared across cameras (one model in memory)
        self.tracker = TrackingEngine()
        self.zone_engine = zone_engine     # shared, holds zones for all cameras
        self.event_engine = TemporalEventEngine(auth_engine=auth_engine, threat_registry=threat_registry)  # per-camera: track IDs are camera-local
        self.face_verifier = face_verifier
        self.alert_engine = alert_engine   # shared, so all cameras feed one alert list
        self.snapshot_selector = SnapshotSelector()
        self.evidence_scorer = EvidenceScorer()
        self._evidence_captured_tracks: set = set()
        self.active_learner = active_learner
        self.adaptive_filter = adaptive_filter
        
        if environment_adapter is not None:
            self.environment_adapter = environment_adapter
        else:
            from ai_engine.learning.camera_environment_adapter import CameraEnvironmentAdapter
            self.environment_adapter = CameraEnvironmentAdapter(
                camera_id=camera_config.camera_id,
                base_confidence=getattr(detector, "confidence_threshold", 0.25),
            )

        self.on_frame = on_frame           # callback: (camera_id, annotated_frame) -> None, for MJPEG stream
        self.on_event = on_event           # callback: (Event) -> None, for logging/WebSocket

        self.face_verification_enabled = face_verification_enabled
        self.ai_enabled = getattr(camera_config, "ai_enabled", True)
        self.plate_recognizer = plate_recognizer
        self.weapon_detector = weapon_detector
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._verify_every_n_frames = 5    # face verification is expensive; don't run every frame
        self._anpr_every_n_frames = 4      # ANPR re-check frequency
        self._weapon_every_n_frames = 3    # Weapon inference frequency
        self._frame_counter = 0
        self._vehicle_plates: dict[int, dict] = {}  # track_id -> plate & driver metadata
        self._standalone_tracks: dict[int, dict] = {}  # track_id -> {bbox, last_seen, unseen_count}
        self._logged_anpr_tracks: set[int] = set()  # prevent spamming DB on every frame
        self._alerted_watchlist_tracks: set[int] = set()
        self._alerted_2fa_tracks: set[int] = set()
        self._active_weapons: list[dict] = []  # list of currently detected weapons
        self._weapon_incident_active: bool = False  # Stateful incident session flag
        self._last_weapon_seen_time: float = 0.0
        self._weapon_incident_cooldown: float = 12.0  # seconds of no weapon before incident session clears
        self._anpr_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=f"anpr-{self.config.camera_id}"
        )
        self._anpr_in_flight: set[int] = set()
        self._last_anpr_attempt: dict[int, float] = {}
        self._track_identities: dict[int, dict] = {}  # track_id -> identity verification cache
        self.vision_enhancer = AdaptiveVisionEnhancer()
        self.thermal_engine = ThermalVisionEngine()
        self.light_source_detector = LightSourceDetector()
        self._current_thermal_mode: ThermalMode = ThermalMode.VISIBLE_RGB
        self._thermal_signatures: list[ThermalHeatSignature] = []
        self._prev_frame_gray: Optional[np.ndarray] = None
        self._cached_yolo_results: Optional[Any] = None
        self._motion_trigger_active: bool = True
        self._idle_motion_frames: int = 0
        self._last_night_enhanced: bool = False
        self._active_torch_detections: list[LightSourceDetection] = []
        self._torch_alert_cooldown: float = 0.0       # prevents torch alert spam

        # --- NEW: Crowd density tracking per camera ---
        self._zone_person_counts: dict[str, list[float]] = {}  # zone_id -> rolling timestamps of person presence
        self._crowd_alerted_zones: dict[str, float] = {}       # zone_id -> last alert time
        CROWD_DENSITY_THRESHOLD = 6                            # persons in zone to trigger CROWD_SURGE
        MOB_DENSITY_THRESHOLD = 10                             # persons to trigger MOB_ASSEMBLY
        self._crowd_threshold = CROWD_DENSITY_THRESHOLD
        self._mob_threshold = MOB_DENSITY_THRESHOLD

        # --- NEW: Vehicle intelligence tracking ---
        self._vehicle_zone_pass_times: dict[int, list[float]] = {}   # track_id -> list of zone-entry timestamps
        self._vehicle_recon_alerted: set[int] = set()                # already-alerted recon tracks
        self._vehicle_colors: dict[int, str] = {}                    # track_id -> detected dominant color name

        # --- Human Action Recognition (HAR) & Pose Kinematics ---
        self.pose_engine = pose_engine if pose_engine is not None else PoseActionEngine()
        self._track_poses: dict[int, PoseAction] = {}
        self._alerted_pose_tracks: dict[int, set[str]] = {}

    def _find_driver(self, vehicle_obj: TrackedObject, tracked_objects: list[TrackedObject], person_identities: dict):
        """Locates any tracked person inside or immediately adjacent to the vehicle."""
        vx1, vy1, vx2, vy2 = vehicle_obj.bbox
        v_w = vx2 - vx1
        v_h = vy2 - vy1
        v_cx = (vx1 + vx2) / 2
        v_cy = (vy1 + vy2) / 2

        for p in tracked_objects:
            if not p.is_person:
                continue
            px1, py1, px2, py2 = p.bbox
            p_cx = (px1 + px2) / 2
            p_cy = (py1 + py2) / 2

            # Proximity or bounding-box overlap
            overlap_x = max(0, min(vx2, px2) - max(vx1, px1))
            overlap_y = max(0, min(vy2, py2) - max(vy1, py1))
            overlap_area = overlap_x * overlap_y

            dist = math.hypot(v_cx - p_cx, v_cy - p_cy)
            if overlap_area > 0 or dist < max(v_w, v_h) * 0.75:
                identity = person_identities.get(p.track_id)
                return p, identity
        return None, None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info(f"[{self.config.camera_id}] pipeline started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        self.camera.release()
        try:
            self._anpr_executor.shutdown(wait=False)
        except Exception:
            pass
        logger.info(f"[{self.config.camera_id}] pipeline stopped")

    def get_status(self) -> dict:
        return self.camera.get_status()

    def hot_swap_model(self, model_path: str):
        if hasattr(self.detector, "hot_swap_model"):
            self.detector.hot_swap_model(model_path)
            self._cached_yolo_results = None
            logger.info(f"[{self.config.camera_id}] Hot-swapped model weights to {model_path}")

    def set_confidence_threshold(self, conf: float):
        if hasattr(self.detector, "confidence_threshold"):
            self.detector.confidence_threshold = conf
            logger.info(f"[{self.config.camera_id}] Set confidence threshold to {conf}")

    def set_rotation(self, rotation: int):
        """Dynamically updates rotation angle for camera feed."""
        if hasattr(self.camera, "set_rotation"):
            self.camera.set_rotation(rotation)
            logger.info(f"[{self.config.camera_id}] Set rotation to {rotation}°")

    def set_ai_enabled(self, enabled: bool, target_fps: Optional[int] = None):
        """Switches pipeline between Tier-1 Full AI Core and Tier-2 Low-Power Passthrough."""
        self.ai_enabled = enabled
        self.config.ai_enabled = enabled
        if target_fps:
            self.camera.set_target_fps(target_fps)
        logger.info(f"[{self.config.camera_id}] ai_enabled updated to {enabled} (target_fps={self.camera.config.target_fps})")

    def _draw_passthrough_hud(self, frame: np.ndarray) -> np.ndarray:
        """Lightweight non-AI HUD overlay for secondary / standby cameras (near zero CPU usage)."""
        annotated = frame.copy()
        h, w = frame.shape[:2]

        # Sleek corner brackets
        b_len = min(22, w // 10)
        cv2.line(annotated, (12, 12), (12 + b_len, 12), (0, 240, 255), 2)
        cv2.line(annotated, (12, 12), (12, 12 + b_len), (0, 240, 255), 2)
        cv2.line(annotated, (w - 12, 12), (w - 12 - b_len, 12), (0, 240, 255), 2)
        cv2.line(annotated, (w - 12, 12), (w - 12, 12 + b_len), (0, 240, 255), 2)

        # Status badge background
        cv2.rectangle(annotated, (10, 10), (min(w - 10, 310), 38), (15, 20, 28), -1)
        cv2.rectangle(annotated, (10, 10), (min(w - 10, 310), 38), (50, 70, 90), 1)

        # Status text
        badge_txt = f"{self.config.camera_id}: PASSTHROUGH (STANDBY)"
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(annotated, badge_txt, (18, 28), font, 0.42, (0, 230, 255), 1, cv2.LINE_AA)

        # Timestamp on top right
        now_str = datetime.now().strftime("%H:%M:%S")
        cv2.putText(annotated, f"LIVE {now_str}", (w - 105, 28), font, 0.42, (100, 255, 120), 1, cv2.LINE_AA)
        return annotated

    # ---- main loop ----------------------------------------------------

    def _run_loop(self):
        while self._running:
            try:
                self._process_one_frame()
            except Exception as e:
                # never let one bad frame kill the whole camera's thread
                logger.error(f"[{self.config.camera_id}] frame processing error: {e}")
                time.sleep(0.5)

    def _process_one_frame(self):
        result = self.camera.read_frame()
        if not result.ok or result.frame is None:
            if self.camera.status != CameraStatus.ONLINE:
                self._push_error_frame(f"CAMERA {self.camera.status.value}")
            time.sleep(0.04)
            return
        try:
            self._process_main(result.frame)
        except Exception as e:
            logger.error(f"[{self.config.camera_id}] Error in _process_main: {e}")
            # Safety fallback: deliver the raw frame so the live feed never freezes
            if self.on_frame:
                try:
                    self.on_frame(self.config.camera_id, result.frame)
                except Exception:
                    pass

    def _push_error_frame(self, message: str):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size = cv2.getTextSize(message, font, 1.0, 2)[0]
        text_x = (frame.shape[1] - text_size[0]) // 2
        text_y = (frame.shape[0] + text_size[1]) // 2
        cv2.putText(frame, message, (text_x, text_y), font, 1.0, (0, 0, 255), 2)
        if self.on_frame:
            self.on_frame(self.config.camera_id, frame)

    def _process_main(self, frame: np.ndarray):
        """Runs detection, tracking, event logic and annotation on a valid frame."""
        self._frame_counter += 1

        # Fast path: If AI is disabled for this camera (Tier-2 Passthrough to save CPU/GPU for primary cameras)
        if not self.ai_enabled:
            annotated = self._draw_passthrough_hud(frame)
            if self.on_frame:
                self.on_frame(self.config.camera_id, annotated)
            return

        current_hour = datetime.now().hour

        # Tier 0A: Thermal Spectrum Classification (Explicit thermal/FLIR hardware only)
        is_explicit_thermal = (
            getattr(self.config, "modality", None) == SensorModality.THERMAL
            or any(k in f"{self.config.name} {self.config.source_uri}".lower() for k in ("thermal", "flir", "heat", "lwir"))
        )
        if is_explicit_thermal:
            if self._frame_counter % 20 == 1 or self._frame_counter == 1:
                detected_mode, _ = self.thermal_engine.detect_spectrum_mode(frame)
                self._current_thermal_mode = detected_mode
            proc_frame = self.thermal_engine.normalize_for_detection(frame, self._current_thermal_mode)
            self._thermal_signatures = self.thermal_engine.extract_heat_signatures(frame, self._current_thermal_mode)
            self._last_night_enhanced = False
        else:
            self._current_thermal_mode = ThermalMode.VISIBLE_RGB
            # Tier 0B: Adaptive Vision Enhancement for standard RGB feeds
            proc_frame, is_night_enh, night_metrics = self.vision_enhancer.process(frame)
            self._last_night_enhanced = is_night_enh
            self._thermal_signatures = []

        # Continuous high-accuracy ByteTrack inference (never skip frames to maintain Kalman filter continuity)
        yolo_results = self.detector.track(proc_frame)
        self._cached_yolo_results = yolo_results

        tracked_objects = self.tracker.extract(yolo_results)

        # Tier 1.5: Online Adaptive Negative Exemplar & Spatial Bayesian Suppression
        if self.adaptive_filter is not None and tracked_objects:
            filtered_objects = []
            for obj in tracked_objects:
                try:
                    is_suppressed, adj_conf, reason = self.adaptive_filter.check_suppression(
                        camera_id=self.config.camera_id,
                        frame=frame,
                        bbox=obj.bbox,
                        confidence=obj.confidence,
                        class_label=obj.label,
                    )
                    obj.confidence = adj_conf
                    if is_suppressed and adj_conf < 0.22:
                        # Suppressed recurring false alarm from triggering alert alarms
                        continue
                except Exception:
                    pass
                filtered_objects.append(obj)
            tracked_objects = filtered_objects

        # Tier 1.6: Online Camera Environmental Adaptation (Lighting, Scene, Priors, Thresholds)
        if self.environment_adapter is not None and (self._frame_counter % 15 == 0 or self._frame_counter == 1):
            try:
                det_list = [{"label": o.label, "confidence": o.confidence, "bbox": o.bbox} for o in tracked_objects]
                cam_prof = self.environment_adapter.adapt_frame(
                    frame=frame,
                    detections=det_list,
                    tracks=tracked_objects,
                )
                from ai_engine.learning.memory_manager import memory_manager
                memory_manager.update_camera_profile(cam_prof)
                if hasattr(self.tracker, "match_thresh") and "track_match_thresh" in cam_prof.adaptive_parameters:
                    self.tracker.match_thresh = cam_prof.adaptive_parameters["track_match_thresh"]
                if hasattr(self.tracker, "max_time_lost") and "max_track_age" in cam_prof.adaptive_parameters:
                    self.tracker.max_time_lost = cam_prof.adaptive_parameters["max_track_age"]
            except Exception as e:
                logger.debug(f"[{self.config.camera_id}] Environment adaptation error: {e}")

        # Active Learning & Hard-Sample Mining hook (non-blocking, rate-limited)
        if self.active_learner is not None and self._frame_counter % 2 == 0:
            lighting_cond = (
                self.environment_adapter.lighting.condition
                if self.environment_adapter is not None
                else "DAYLIGHT"
            )

        # Tier 1.7: Multi-Criterion Anomaly & Novelty Evaluation (Milestone 6)
        if self._frame_counter % 3 == 0 and tracked_objects:
            try:
                from ai_engine.learning.anomaly_novelty_engine import get_anomaly_engine, AnomalySeverityTier
                anom_engine = get_anomaly_engine(self.config.camera_id)
                for obj in tracked_objects:
                    traj_pts = []
                    if hasattr(self.event_engine, "states") and obj.track_id in self.event_engine.states:
                        raw_pts = getattr(self.event_engine.states[obj.track_id], "positions", [])
                        fh, fw = frame.shape[:2]
                        traj_pts = [(p[0] / max(1, fw), p[1] / max(1, fh)) for p in raw_pts[-12:]]

                    assessment = anom_engine.evaluate_track(
                        track_id=obj.track_id,
                        class_label=obj.label,
                        bounding_box=obj.bbox,
                        trajectory=traj_pts,
                        visual_descriptor=None,
                        environment_adapter=self.environment_adapter,
                    )
                    # If high anomaly tier, route into active learner review pool
                    if assessment.tier in (AnomalySeverityTier.REQUIRES_REVIEW, AnomalySeverityTier.CONFIRMED_EVENT):
                        if self.active_learner is not None:
                            self.active_learner.consider_detection(
                                camera_id=self.config.camera_id,
                                frame=frame,
                                obj=obj,
                                track_history_len=len(traj_pts),
                                lighting_condition=self.environment_adapter.lighting.condition if self.environment_adapter else "DAYLIGHT",
                            )
            except Exception as e:
                logger.debug(f"[{self.config.camera_id}] Anomaly evaluation error: {e}")

        # 1. Collect face verifications for all persons in this frame
        person_identities = {}
        now = time.time()
        for obj in tracked_objects:
            if obj.is_person and self.face_verification_enabled and self.face_verifier is not None:
                cached = self._track_identities.get(obj.track_id)
                is_verified = cached.get("is_verified", False) if cached else False

                # Tier-2 Hierarchical Face Verification: Immediate on new track; progressive backoff for unverified
                if cached is None:
                    should_verify = True
                elif not is_verified:
                    unv_retries = cached.get("retries", 0)
                    retry_interval = 0.5 if unv_retries < 2 else (2.0 if unv_retries < 6 else 6.0)
                    should_verify = (now - cached.get("last_checked", 0) > retry_interval) and (self._frame_counter % 2 == 0)
                else:
                    should_verify = (now - cached.get("last_checked", 0) > 30.0)

                if should_verify:
                    id_res = self._run_face_verification(frame, obj)
                    if id_res:
                        is_v = (getattr(id_res[0], "value", "").upper() == "VERIFIED")
                        # Preserve verified status during temporary head turns
                        if not is_v and is_verified and (now - cached.get("last_checked", 0) < 30.0):
                            pass
                        else:
                            prev_retries = cached.get("retries", 0) if cached else 0
                            self._track_identities[obj.track_id] = {
                                "identity_result": id_res,
                                "last_checked": now,
                                "is_verified": is_v,
                                "retries": (prev_retries + 1) if not is_v else 0,
                            }
                if obj.track_id in self._track_identities:
                    person_identities[obj.track_id] = self._track_identities[obj.track_id]["identity_result"]

        person_states = []
        bag_track_ids = []

        for obj in tracked_objects:
            events: list[Event] = []
            self.snapshot_selector.consider(obj.track_id, frame, obj.bbox)

            # Record candidate in EvidenceScorer ring-buffer for automated best-evidence selection
            try:
                p_crop = self._vehicle_plates.get(obj.track_id, {}).get("crop") if obj.is_vehicle else None
                p_text = self._vehicle_plates.get(obj.track_id, {}).get("plate") if obj.is_vehicle else None
                p_conf = self._vehicle_plates.get(obj.track_id, {}).get("confidence", 0.9) if obj.is_vehicle else 0.0
                f_crop = self._crop_object(frame, obj) if obj.is_person else None
                self.evidence_scorer.record_candidate(
                    track_id=obj.track_id,
                    frame=frame,
                    bbox=obj.bbox,
                    confidence=obj.confidence,
                    is_person=obj.is_person,
                    is_vehicle=obj.is_vehicle,
                    face_crop=f_crop,
                    plate_crop=p_crop,
                    plate_text=p_text,
                    plate_conf=p_conf,
                )
            except Exception as e:
                logger.debug(f"[{self.config.camera_id}] Candidate recording skipped: {e}")

            matched_zones = self.zone_engine.check_point(
                self.config.camera_id, obj.foot_point, current_hour
            )
            camera_zones = self.zone_engine.get_zones_for_camera(self.config.camera_id)

            identity_result = person_identities.get(obj.track_id) if obj.is_person else None

            # ANPR: High-speed asynchronous plate OCR (no stream stutter)
            if obj.is_plate_candidate and self.plate_recognizer is not None:
                has_plate = obj.track_id in self._vehicle_plates and bool(self._vehicle_plates[obj.track_id].get("plate"))
                last_try = self._last_anpr_attempt.get(obj.track_id, 0.0)
                should_scan = (not has_plate and obj.track_id not in self._anpr_in_flight and (now - last_try >= 0.8))
                if should_scan:
                    crop = self._crop_object(frame, obj)
                    if crop is not None and crop.size > 0:
                        self._last_anpr_attempt[obj.track_id] = now
                        self._anpr_in_flight.add(obj.track_id)
                        self._anpr_executor.submit(
                            self._async_anpr_worker, obj.track_id, crop, obj.label, obj.bbox
                        )

            # If this object has a detected plate, evaluate 2FA & alerts
            if obj.track_id in self._vehicle_plates:
                plate_data = self._vehicle_plates[obj.track_id]
                plate_data["bbox"] = obj.bbox
                plate_data["last_seen"] = time.time()

                # Driver 2FA verification check
                if plate_data.get("driver_2fa") in ("N/A", "UNVERIFIED"):
                    driver_person, driver_id_res = self._find_driver(obj, tracked_objects, person_identities)
                    owner_name = plate_data.get("owner")
                    owner_ref = plate_data.get("owner_ref")
                    if driver_id_res:
                        (d_status, d_name, d_id) = driver_id_res
                        if d_status == IdentityStatus.VERIFIED:
                            plate_data["driver_name"] = d_name
                            if owner_name and (d_name.lower() == owner_name.lower() or (owner_ref and d_id == owner_ref)):
                                plate_data["driver_2fa"] = "VERIFIED"
                            elif owner_name:
                                plate_data["driver_2fa"] = "MISMATCH"
                            else:
                                plate_data["driver_2fa"] = "VERIFIED_DRIVER"
                        else:
                            plate_data["driver_2fa"] = "UNVERIFIED"
                    elif driver_person:
                        plate_data["driver_2fa"] = "UNVERIFIED"

                # Check for Watchlist Threat event
                if plate_data.get("is_watchlist") and obj.track_id not in self._alerted_watchlist_tracks:
                    self._alerted_watchlist_tracks.add(obj.track_id)
                    state = self.event_engine.states.get(obj.track_id)
                    if state:
                        match_info = plate_data.get("match_info", {})
                        owner_str = f" | Owner: {match_info.get('owner_name')}" if match_info.get("owner_name") else ""
                        notes_str = f" | Notes: {match_info.get('notes')}" if match_info.get("notes") else ""
                        fuzzy_str = " [FUZZY OCR MATCH]" if plate_data.get("is_fuzzy") else ""
                        watchlist_event = self.event_engine._new_event(
                            EventType.WATCHLIST_VEHICLE, state, None,
                            Severity.ORANGE, plate_data.get("confidence", 0.90),
                            f"🚨 THREAT WATCHLIST VEHICLE — Plate: {plate_data['plate']}{fuzzy_str}{owner_str}{notes_str}",
                            risk_boost=90,
                            metadata={"plate_text": plate_data['plate'], "watchlist_match": match_info, "is_fuzzy": plate_data.get("is_fuzzy")}
                        )
                        events.append(watchlist_event)

                # Check for 2FA mismatch alert
                if plate_data.get("driver_2fa") == "MISMATCH" and obj.track_id not in self._alerted_2fa_tracks:
                    self._alerted_2fa_tracks.add(obj.track_id)
                    state = self.event_engine.states.get(obj.track_id)
                    if state:
                        d_name = plate_data.get("driver_name")
                        o_name = plate_data.get("owner")
                        p_num = plate_data.get("plate")
                        mismatch_event = self.event_engine._new_event(
                            EventType.UNAUTHORIZED_DRIVER, state, None,
                            Severity.ORANGE, 0.90,
                            f"🚨 2FA GATE VIOLATION: Unauthorized driver '{d_name}' operating vehicle {p_num} registered to '{o_name}'",
                            risk_boost=80,
                            metadata={"plate_text": p_num, "owner_name": o_name, "detected_driver": d_name}
                        )
                        events.append(mismatch_event)

                # Log ANPR Gate Audit detection
                if plate_data.get("plate") and obj.track_id not in self._logged_anpr_tracks:
                    self._logged_anpr_tracks.add(obj.track_id)
                    state = self.event_engine.states.get(obj.track_id)
                    if state:
                        anpr_log_event = self.event_engine._new_event(
                            EventType.VEHICLE_DETECTED, state, None,
                            Severity.GREEN, plate_data.get("confidence", 0.90),
                            f"ANPR Gate Log: Plate {plate_data['plate']} detected ({plate_data.get('owner') or 'Unregistered'})",
                            risk_boost=0,
                            metadata={
                                "is_anpr_log": True,
                                "plate_number": plate_data['plate'],
                                "vehicle_type": obj.label.title(),
                                "owner_name": plate_data.get("owner"),
                                "anpr_status": "WATCHLIST" if plate_data.get("is_watchlist") else ("CLEARED" if plate_data.get("is_registered") else "DETECTED"),
                                "driver_2fa": plate_data.get("driver_2fa", "N/A"),
                                "is_fuzzy": plate_data.get("is_fuzzy"),
                            }
                        )
                        events.append(anpr_log_event)

            visual_signature = self._extract_visual_signature(frame, obj)

            events.extend(self.event_engine.update(
                obj, self.config.camera_id, matched_zones, current_hour, identity_result,
                camera_zones=camera_zones, all_tracked_objects=tracked_objects,
                visual_signature=visual_signature
            ))

            if obj.is_person:
                state = self.event_engine.states.get(obj.track_id)
                if state:
                    person_states.append(state)

                # Human Action Recognition (HAR) via YOLOv8-Pose
                if getattr(self, "pose_engine", None) and self.pose_engine.is_available:
                    paction = self.pose_engine.evaluate_person(frame, obj.bbox, obj.track_id)
                    if paction:
                        self._track_poses[obj.track_id] = paction
                        if paction.action_type in ("FALL_DETECTED", "CRAWLING"):
                            alerted_set = self._alerted_pose_tracks.setdefault(obj.track_id, set())
                            if paction.action_type not in alerted_set:
                                alerted_set.add(paction.action_type)
                                is_fall = (paction.action_type == "FALL_DETECTED")
                                ev_type = EventType.FALL_DETECTED if is_fall else EventType.CRAWLING_INTRUSION
                                ev_sev = Severity.RED if is_fall else Severity.ORANGE
                                pose_event = Event(
                                    event_id=str(uuid.uuid4()),
                                    event_type=ev_type,
                                    track_id=obj.track_id,
                                    camera_id=self.config.camera_id,
                                    zone_id=matched_zones[0].zone_id if matched_zones else None,
                                    timestamp=now,
                                    severity=ev_sev,
                                    confidence=paction.confidence,
                                    description=f"{paction.description} — Track #{obj.track_id}",
                                    risk_score=90 if is_fall else 85,
                                    metadata={
                                        "action": paction.action_type,
                                        "confidence": round(float(paction.confidence), 2),
                                        "track_id": obj.track_id,
                                    }
                                )
                                events.append(pose_event)
                        elif paction.action_type == "HANDS_RAISED":
                            alerted_set = self._alerted_pose_tracks.setdefault(obj.track_id, set())
                            if "HANDS_RAISED" not in alerted_set:
                                alerted_set.add("HANDS_RAISED")
                                hands_event = Event(
                                    event_id=str(uuid.uuid4()),
                                    event_type=EventType.HANDS_RAISED,
                                    track_id=obj.track_id,
                                    camera_id=self.config.camera_id,
                                    zone_id=matched_zones[0].zone_id if matched_zones else None,
                                    timestamp=now,
                                    severity=Severity.YELLOW,
                                    confidence=paction.confidence,
                                    description=f"🏳️ HANDS RAISED / COMPLIANCE: Person #{obj.track_id} standing with arms raised",
                                    risk_score=20,
                                    metadata={
                                        "action": paction.action_type,
                                        "confidence": round(float(paction.confidence), 2),
                                        "track_id": obj.track_id,
                                    }
                                )
                                events.append(hands_event)

            if obj.is_bag:
                bag_track_ids.append(obj.track_id)

            # Automated Best-Evidence Capture for Security Breaches & Zone Violations
            high_sev_events = [ev for ev in events if ev.severity in (Severity.RED, Severity.ORANGE)]
            if high_sev_events and obj.track_id not in self._evidence_captured_tracks:
                self._evidence_captured_tracks.add(obj.track_id)
                trig_ev = high_sev_events[0]
                z_name = matched_zones[0].name if matched_zones else "Restricted Perimeter"
                z_poly = matched_zones[0].polygon if matched_zones else None
                
                intruder_id = "UNKNOWN INTRUDER"
                if obj.is_person:
                    id_cand = person_identities.get(obj.track_id)
                    if id_cand:
                        intruder_id = f"{id_cand[0].value}: {id_cand[1]}"
                elif obj.is_vehicle:
                    p_info = self._vehicle_plates.get(obj.track_id, {})
                    if p_info.get("plate"):
                        intruder_id = f"Vehicle: {p_info['plate']} ({p_info.get('owner') or 'Unregistered'})"

                p_num = self._vehicle_plates.get(obj.track_id, {}).get("plate")
                ev_pkg = self.evidence_scorer.build_evidence_package(
                    track_id=obj.track_id,
                    camera_id=self.config.name,
                    zone_name=z_name,
                    incident_type=trig_ev.event_type.value.upper(),
                    identity_name=intruder_id,
                    plate_number=p_num,
                    zone_polygon=z_poly,
                    priority_score=trig_ev.risk_score,
                    violation_code=f"SEC-{trig_ev.event_type.value[:4].upper()}-01"
                )
                if ev_pkg:
                    trig_ev.metadata["evidence_package"] = ev_pkg.to_dict()
                    trig_ev.metadata["breach_id"] = ev_pkg.evidence_id
                    try:
                        import asyncio
                        import threading
                        from backend.app.services.breach_service import BreachService
                        threading.Thread(
                            target=lambda pkg: asyncio.run(BreachService.create_breach_record(pkg)),
                            args=(ev_pkg.to_dict(),),
                            daemon=True
                        ).start()
                    except Exception as e:
                        logger.debug(f"Could not persist breach to MongoDB: {e}")

            for event in events:
                self._handle_event(event, frame, obj)

        # Tier-2 Hierarchical Standalone Plate Search:
        # Fast 2-frame interval if vehicles or active plate tracks are in view; relaxed 5-frame interval when scene is clear.
        scan_interval = 2 if (any(o.is_vehicle for o in tracked_objects) or self._standalone_tracks) else 5
        if self.plate_recognizer is not None and (self._frame_counter % scan_interval == 0):
            standalone_candidates = self.plate_recognizer.find_standalone_plates(frame)
            # Filter candidates: ignore rectangles inside an already detected vehicle
            valid_candidates = []
            for (sx, sy, sw, sh) in standalone_candidates[:3]:
                cand_cx = sx + sw / 2.0
                cand_cy = sy + sh / 2.0
                inside_vehicle = any(
                    (o.bbox[0] <= cand_cx <= o.bbox[2]) and (o.bbox[1] <= cand_cy <= o.bbox[3])
                    for o in tracked_objects if o.is_vehicle
                )
                if not inside_vehicle:
                    valid_candidates.append((sx, sy, sw, sh))

            matched_tracks = set()
            used_candidates = set()

            # 1. Match candidates with existing standalone tracks by centroid proximity
            for tid, tinfo in list(self._standalone_tracks.items()):
                tx1, ty1, tx2, ty2 = tinfo["bbox"]
                tcx, tcy = (tx1 + tx2) / 2.0, (ty1 + ty2) / 2.0
                best_cand_idx = None
                best_dist = 120.0  # max pixels movement
                for idx, (sx, sy, sw, sh) in enumerate(valid_candidates):
                    if idx in used_candidates:
                        continue
                    ccx, ccy = sx + sw / 2.0, sy + sh / 2.0
                    dist = math.hypot(ccx - tcx, ccy - tcy)
                    if dist < best_dist:
                        best_dist = dist
                        best_cand_idx = idx

                if best_cand_idx is not None:
                    sx, sy, sw, sh = valid_candidates[best_cand_idx]
                    used_candidates.add(best_cand_idx)
                    matched_tracks.add(tid)
                    tinfo["bbox"] = (sx, sy, sx + sw, sy + sh)
                    tinfo["last_seen"] = now
                    tinfo["unseen_count"] = 0
                    if tid in self._vehicle_plates:
                        self._vehicle_plates[tid]["bbox"] = (sx, sy, sx + sw, sy + sh)
                        self._vehicle_plates[tid]["last_seen"] = now
                    # Re-scan ANPR periodically only if no plate has been locked yet
                    has_plate = tid in self._vehicle_plates and bool(self._vehicle_plates[tid].get("plate"))
                    last_try = self._last_anpr_attempt.get(tid, 0.0)
                    if not has_plate and tid not in self._anpr_in_flight and (now - last_try >= 1.2):
                        crop = frame[max(0, sy):min(frame.shape[0], sy+sh), max(0, sx):min(frame.shape[1], sx+sw)]
                        if crop.size > 0:
                            self._last_anpr_attempt[tid] = now
                            self._anpr_in_flight.add(tid)
                            self._anpr_executor.submit(
                                self._async_anpr_worker, tid, crop, "plate", (sx, sy, sx+sw, sy+sh)
                            )

            # 2. Add new candidate tracks if slot available (IDs 9001, 9002)
            for idx, (sx, sy, sw, sh) in enumerate(valid_candidates):
                if idx in used_candidates:
                    continue
                for new_id in (9001, 9002):
                    if new_id not in self._standalone_tracks:
                        self._standalone_tracks[new_id] = {
                            "bbox": (sx, sy, sx + sw, sy + sh),
                            "last_seen": now,
                            "unseen_count": 0,
                        }
                        matched_tracks.add(new_id)
                        crop = frame[max(0, sy):min(frame.shape[0], sy+sh), max(0, sx):min(frame.shape[1], sx+sw)]
                        last_try = self._last_anpr_attempt.get(new_id, 0.0)
                        if crop.size > 0 and new_id not in self._anpr_in_flight and (now - last_try >= 1.0):
                            self._last_anpr_attempt[new_id] = now
                            self._anpr_in_flight.add(new_id)
                            self._anpr_executor.submit(
                                self._async_anpr_worker, new_id, crop, "plate", (sx, sy, sx+sw, sy+sh)
                            )
                        break

            # 3. Prune tracks only if unseen across multiple scans or older than 2.5s
            for tid, tinfo in list(self._standalone_tracks.items()):
                if tid not in matched_tracks:
                    tinfo["unseen_count"] += 1
                    if tinfo["unseen_count"] >= 8 or (now - tinfo["last_seen"]) > 2.5:
                        self._standalone_tracks.pop(tid, None)
                        self._vehicle_plates.pop(tid, None)
                        self._logged_anpr_tracks.discard(tid)
                        self._alerted_watchlist_tracks.discard(tid)

        # Handle standalone plate alerts & logging
        for vid, pinfo in list(self._vehicle_plates.items()):
            if vid >= 9000:
                if now - pinfo.get("last_seen", 0) > 2.5:
                    self._vehicle_plates.pop(vid, None)
                    continue
                if vid not in self._logged_anpr_tracks and pinfo.get("plate"):
                    self._logged_anpr_tracks.add(vid)
                    gate_event = Event(
                        event_id=str(uuid.uuid4()),
                        event_type=EventType.VEHICLE_DETECTED,
                        track_id=vid,
                        camera_id=self.config.camera_id,
                        zone_id=None,
                        timestamp=now,
                        severity=Severity.GREEN,
                        confidence=pinfo.get("confidence", 0.90),
                        description=f"ANPR Gate Log: Plate {pinfo['plate']} detected ({pinfo.get('owner') or 'Unregistered'})",
                        risk_score=0,
                        metadata={
                            "is_anpr_log": True,
                            "plate_number": pinfo['plate'],
                            "vehicle_type": "Plate",
                            "owner_name": pinfo.get("owner"),
                            "anpr_status": "WATCHLIST" if pinfo.get("is_watchlist") else ("CLEARED" if pinfo.get("is_registered") else "DETECTED"),
                            "driver_2fa": "N/A",
                            "is_fuzzy": pinfo.get("is_fuzzy"),
                        }
                    )
                    self._handle_event(gate_event, frame, None)

                    if pinfo.get("is_watchlist") and vid not in self._alerted_watchlist_tracks:
                        self._alerted_watchlist_tracks.add(vid)
                        match_info = pinfo.get("match_info", {})
                        owner_str = f" | Owner: {match_info.get('owner_name')}" if match_info.get("owner_name") else ""
                        notes_str = f" | Notes: {match_info.get('notes')}" if match_info.get("notes") else ""
                        fuzzy_str = " [FUZZY OCR MATCH]" if pinfo.get("is_fuzzy") else ""
                        watchlist_event = Event(
                            event_id=str(uuid.uuid4()),
                            event_type=EventType.WATCHLIST_VEHICLE,
                            track_id=vid,
                            camera_id=self.config.camera_id,
                            zone_id=None,
                            timestamp=now,
                            severity=Severity.ORANGE,
                            confidence=pinfo.get("confidence", 0.90),
                            description=f"🚨 THREAT WATCHLIST VEHICLE — Plate: {pinfo['plate']}{fuzzy_str}{owner_str}{notes_str}",
                            risk_score=90,
                            metadata={"plate_text": pinfo['plate'], "watchlist_match": match_info, "is_fuzzy": pinfo.get("is_fuzzy")}
                        )
                        self._handle_event(watchlist_event, frame, None)

        # associate each visible bag with its nearest person, for abandoned-object logic
        for bag_id in bag_track_ids:
            self.event_engine.associate_bag_with_nearest_person(bag_id, person_states)

        active_ids = {o.track_id for o in tracked_objects}
        self.event_engine.prune_stale_tracks(active_ids)
        # Clean up plate cache for departed vehicles
        for tid in list(self._vehicle_plates.keys()):
            if tid < 9000 and tid not in active_ids:
                del self._vehicle_plates[tid]
        for tid in list(self._logged_anpr_tracks):
            if tid < 9000 and tid not in active_ids:
                self._logged_anpr_tracks.remove(tid)
        for tid in list(self._alerted_watchlist_tracks):
            if tid < 9000 and tid not in active_ids:
                self._alerted_watchlist_tracks.remove(tid)
        for tid in list(self._alerted_2fa_tracks):
            if tid < 9000 and tid not in active_ids:
                self._alerted_2fa_tracks.remove(tid)
        for tid in list(self._track_identities.keys()):
            if tid not in active_ids:
                del self._track_identities[tid]
        for tid in list(self._track_poses.keys()):
            if tid not in active_ids:
                del self._track_poses[tid]
        for tid in list(self._alerted_pose_tracks.keys()):
            if tid not in active_ids:
                del self._alerted_pose_tracks[tid]


        # ---- Multi-Threat & Weapon Detection (SIH26187 Category 4: Firearms, Knives) ----
        # Two-Tier Hierarchical Inference: Heavy weapon YOLO ONLY runs if:
        # 1) At least one person is detected in the camera view, OR
        # 2) An active weapon incident is ongoing, OR
        # 3) Periodic background sweep (every 30 frames, ~2s)
        # Otherwise, skip running the heavy neural net on empty scenes, saving massive CPU.
        has_persons = any(o.is_person for o in tracked_objects)
        should_run_weapon = (
            self.weapon_detector is not None and 
            self.weapon_detector.is_available and 
            (has_persons or self._weapon_incident_active or (self._frame_counter % 30 == 0))
        )

        if should_run_weapon:
            threat_dets = self.weapon_detector.detect(frame)
            active_threats = []
            for tdet in threat_dets:
                active_threats.append({
                    "label": tdet.label,
                    "confidence": tdet.confidence,
                    "bbox": tdet.bbox,
                    "weapon_type": tdet.weapon_type,
                    "category_tag": tdet.category_tag,
                    "icon": tdet.icon,
                    "last_seen": now,
                    "track_id": tdet.track_id,
                })

            # Incorporate COCO knife from general tracker ONLY if confidence is very high (>= 0.85)
            # and passes smartphone anti-false-positive filtering
            for obj in tracked_objects:
                if obj.label == "knife" and obj.confidence >= 0.85:
                    bx1, by1, bx2, by2 = obj.bbox
                    bw = max(1.0, bx2 - bx1)
                    bh = max(1.0, by2 - by1)
                    aspect = bh / bw
                    if (aspect > 1.35 or aspect < 0.70) and obj.confidence < 0.90:
                        continue
                    if (bw * bh) < 3200 and obj.confidence < 0.90:
                        continue
                    active_threats.append({
                        "label": "Knife",
                        "confidence": obj.confidence,
                        "bbox": obj.bbox,
                        "weapon_type": "bladed",
                        "category_tag": "LETHAL BLADE",
                        "icon": "🗡️",
                        "last_seen": now,
                        "track_id": obj.track_id,
                    })

            # Negative Mutual Exclusion Filter:
            # Suppress any candidate threat if it overlaps with or is proximate to a detected cell phone,
            # or overlaps with a license plate, ensuring smartphones NEVER trigger weapon false alarms.
            phone_boxes = [obj.bbox for obj in tracked_objects if obj.is_phone or obj.label == "cell phone"]
            plate_boxes = [
                pinfo["bbox"] for pinfo in self._vehicle_plates.values()
                if isinstance(pinfo, dict) and pinfo.get("bbox")
            ]
            for obj in tracked_objects:
                if obj.is_plate_candidate:
                    plate_boxes.append(obj.bbox)

            filtered_threats = []
            for t in active_threats:
                t_bbox = t["bbox"]
                t_conf = t["confidence"]

                # Check overlap and proximity against phones (suppress if overlap > 5% or center dist < 70px, conf < 0.92)
                is_phone_fp = False
                for p_bbox in phone_boxes:
                    ix1 = max(t_bbox[0], p_bbox[0])
                    iy1 = max(t_bbox[1], p_bbox[1])
                    ix2 = min(t_bbox[2], p_bbox[2])
                    iy2 = min(t_bbox[3], p_bbox[3])
                    iarea = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
                    t_area = max(1.0, (t_bbox[2] - t_bbox[0]) * (t_bbox[3] - t_bbox[1]))
                    p_area = max(1.0, (p_bbox[2] - p_bbox[0]) * (p_bbox[3] - p_bbox[1]))
                    overlap = iarea / min(t_area, p_area) if iarea > 0 else 0.0

                    tcx = (t_bbox[0] + t_bbox[2]) / 2.0
                    tcy = (t_bbox[1] + t_bbox[3]) / 2.0
                    pcx = (p_bbox[0] + p_bbox[2]) / 2.0
                    pcy = (p_bbox[1] + p_bbox[3]) / 2.0
                    center_dist = math.hypot(tcx - pcx, tcy - pcy)

                    if (overlap > 0.05 or center_dist < 70.0) and t_conf < 0.92:
                        is_phone_fp = True
                        logger.info("Threat '%s' suppressed: overlaps (%.2f) or within %.1fpx of verified cell phone", t["label"], overlap, center_dist)
                        break
                if is_phone_fp:
                    continue

                # Check overlap against license plates (suppress if overlap > 25% and conf < 0.80)
                is_plate_fp = False
                for pl_bbox in plate_boxes:
                    ix1 = max(t_bbox[0], pl_bbox[0])
                    iy1 = max(t_bbox[1], pl_bbox[1])
                    ix2 = min(t_bbox[2], pl_bbox[2])
                    iy2 = min(t_bbox[3], pl_bbox[3])
                    iarea = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
                    if iarea > 0:
                        t_area = max(1.0, (t_bbox[2] - t_bbox[0]) * (t_bbox[3] - t_bbox[1]))
                        pl_area = max(1.0, (pl_bbox[2] - pl_bbox[0]) * (pl_bbox[3] - pl_bbox[1]))
                        overlap = iarea / min(t_area, pl_area)
                        if overlap > 0.25 and t_conf < 0.80:
                            is_plate_fp = True
                            logger.info("Threat '%s' suppressed: overlaps (%.2f) with license plate region", t["label"], overlap)
                            break
                if is_plate_fp:
                    continue

                filtered_threats.append(t)

            self._active_weapons = filtered_threats
        else:
            if not self._weapon_incident_active:
                self._active_weapons = []

        # Stateful Incident Session: Fire EXACTLY ONE high-priority alert when threat appears
        if self._active_weapons:
            self._last_weapon_seen_time = now

            if not self._weapon_incident_active:
                self._weapon_incident_active = True
                top_weapon = max(self._active_weapons, key=lambda w: w["confidence"])
                w_label = top_weapon["label"]
                w_conf = top_weapon["confidence"]
                w_type = top_weapon["weapon_type"]
                w_tag = top_weapon.get("category_tag", "THREAT")
                w_icon = top_weapon.get("icon", "🚨")
                wx1, wy1, wx2, wy2 = top_weapon["bbox"]
                wcx, wcy = (wx1 + wx2) / 2.0, (wy1 + wy2) / 2.0

                # Proximity match to identify who is holding/near the weapon
                # Prioritize unverified individuals over cleared authorized personnel
                associated_person = None
                unverified_candidates = []
                verified_candidates = []
                for p in tracked_objects:
                    if p.is_person:
                        px1, py1, px2, py2 = p.bbox
                        if (px1 - 60 <= wcx <= px2 + 60) and (py1 - 60 <= wcy <= py2 + 60):
                            p_state = self.event_engine.states.get(p.track_id)
                            is_p_v = (
                                (p_state and getattr(p_state.identity_status, "value", "").upper() == "VERIFIED") or
                                (self._track_identities.get(p.track_id, {}).get("is_verified", False))
                            )
                            if is_p_v:
                                verified_candidates.append(p)
                            else:
                                unverified_candidates.append(p)
                associated_person = unverified_candidates[0] if unverified_candidates else (verified_candidates[0] if verified_candidates else None)

                p_desc = f" held by Person #{associated_person.track_id}" if associated_person else ""
                weapon_event = Event(
                    event_id=str(uuid.uuid4()),
                    event_type=EventType.WEAPON_DETECTED,
                    track_id=associated_person.track_id if associated_person else 8888,
                    camera_id=self.config.camera_id,
                    zone_id=None,
                    timestamp=now,
                    severity=Severity.RED,
                    confidence=w_conf,
                    description=f"{w_icon} CRITICAL THREAT: {w_tag} ({w_label.upper()} - {int(w_conf * 100)}% conf) identified in camera view{p_desc}!",
                    risk_score=95,
                    metadata={
                        "weapon_type": w_type,
                        "weapon_label": w_label,
                        "category_tag": w_tag,
                        "icon": w_icon,
                        "confidence": round(float(w_conf), 3),
                        "bbox": list(top_weapon["bbox"]),
                        "associated_person_id": associated_person.track_id if associated_person else None,
                        "is_threat": True,
                    }
                )
                self._handle_event(weapon_event, frame, associated_person)
        else:
            # When threat leaves camera view for >= 12 seconds, close incident session
            if self._weapon_incident_active and (now - self._last_weapon_seen_time > self._weapon_incident_cooldown):
                self._weapon_incident_active = False

        # ---- Tier-2 Night Torch / Flashlight Detection ----
        # Only run if scene is dark/night or infrared enhanced (0% CPU during normal daylight)
        is_night_scene = self._last_night_enhanced or (current_hour < 6 or current_hour >= 19)
        if is_night_scene and (self._frame_counter % 2 == 0):
            torch_dets = self.light_source_detector.detect(frame)
        else:
            torch_dets = []
        self._active_torch_detections = torch_dets
        now_torch = time.time()
        if torch_dets and (now_torch - self._torch_alert_cooldown) > 90.0:
            self._torch_alert_cooldown = now_torch
            top_torch = max(torch_dets, key=lambda d: d.confidence)
            # Create a synthetic event — attach to a dummy track ID
            torch_event = Event(
                event_id=str(uuid.uuid4()),
                event_type=EventType.NIGHT_TORCH_DETECTED,
                track_id=7777,
                camera_id=self.config.camera_id,
                zone_id=None,
                timestamp=now_torch,
                severity=Severity.ORANGE,
                confidence=top_torch.confidence,
                description=(
                    f"🔦 NIGHT TORCH DETECTED: Moving light source ({int(top_torch.confidence * 100)}% conf) "
                    f"at pixel ({int(top_torch.centroid[0])}, {int(top_torch.centroid[1])}) — "
                    f"possible infiltrator with flashlight. Frame brightness: {top_torch.frame_brightness:.0f}/255"
                ),
                risk_score=55,
                metadata={
                    "centroid_x": int(top_torch.centroid[0]),
                    "centroid_y": int(top_torch.centroid[1]),
                    "area_px": top_torch.area_px,
                    "frame_brightness": round(top_torch.frame_brightness, 1),
                    "is_night_detection": True,
                }
            )
            self._handle_event(torch_event, frame, None)

        # ---- Crowd Density Intelligence (New Feature) ----
        if tracked_objects:
            # Count persons per zone in this frame
            zone_person_map: dict[str, int] = {}
            for obj in tracked_objects:
                if not obj.is_person:
                    continue
                mzones = self.zone_engine.check_point(self.config.camera_id, obj.foot_point, current_hour)
                for z in mzones:
                    zone_person_map[z.zone_id] = zone_person_map.get(z.zone_id, 0) + 1

            now_crowd = time.time()
            for zone_id, count in zone_person_map.items():
                last_alert = self._crowd_alerted_zones.get(zone_id, 0.0)
                cooldown_ok = (now_crowd - last_alert) > 120.0
                if count >= self._mob_threshold and cooldown_ok:
                    self._crowd_alerted_zones[zone_id] = now_crowd
                    mob_event = Event(
                        event_id=str(uuid.uuid4()),
                        event_type=EventType.MOB_ASSEMBLY,
                        track_id=6666,
                        camera_id=self.config.camera_id,
                        zone_id=zone_id,
                        timestamp=now_crowd,
                        severity=Severity.ORANGE,
                        confidence=0.90,
                        description=(
                            f"🚨 MOB ASSEMBLY: {count} persons simultaneously detected in zone — "
                            f"possible coordinated incursion or violent gathering"
                        ),
                        risk_score=85,
                        metadata={"person_count": count, "zone_id": zone_id}
                    )
                    self._handle_event(mob_event, frame, None)
                elif count >= self._crowd_threshold and cooldown_ok:
                    self._crowd_alerted_zones[zone_id] = now_crowd
                    surge_event = Event(
                        event_id=str(uuid.uuid4()),
                        event_type=EventType.CROWD_SURGE,
                        track_id=6667,
                        camera_id=self.config.camera_id,
                        zone_id=zone_id,
                        timestamp=now_crowd,
                        severity=Severity.ORANGE,
                        confidence=0.85,
                        description=(
                            f"👥 CROWD SURGE: {count} persons detected in zone simultaneously — "
                            f"threshold exceeded ({self._crowd_threshold})"
                        ),
                        risk_score=60,
                        metadata={"person_count": count, "zone_id": zone_id}
                    )
                    self._handle_event(surge_event, frame, None)

        # ---- Unknown Face in Restricted Zone Alert (Upgrades face detection to Exceeds) ----
        if self.face_verification_enabled and self.face_verifier is not None:
            for obj in tracked_objects:
                if not obj.is_person:
                    continue
                cached = self._track_identities.get(obj.track_id, {})
                is_unknown = not cached.get("is_verified", False)
                if not is_unknown:
                    continue
                # Check if this person is in a restricted / high_security zone
                mzones_p = self.zone_engine.check_point(self.config.camera_id, obj.foot_point, current_hour)
                in_restricted = any(
                    z.zone_type.value in ("restricted", "high_security", "sensitive")
                    for z in mzones_p
                )
                if not in_restricted:
                    continue
                # Fire alert (deduplication handled by alert_engine 60s window)
                state_unk = self.event_engine.states.get(obj.track_id)
                if state_unk and f"unknown_face_restricted_{obj.track_id}" not in getattr(state_unk, 'fired_zone_events', set()):
                    if state_unk.fired_zone_events is not None:
                        state_unk.fired_zone_events.add(f"unknown_face_restricted_{obj.track_id}")
                    zone_names = ", ".join(z.name for z in mzones_p if z.zone_type.value in ("restricted", "high_security", "sensitive"))
                    unk_face_event = Event(
                        event_id=str(uuid.uuid4()),
                        event_type=EventType.UNKNOWN_FACE_RESTRICTED,
                        track_id=obj.track_id,
                        camera_id=self.config.camera_id,
                        zone_id=mzones_p[0].zone_id if mzones_p else None,
                        timestamp=time.time(),
                        severity=Severity.ORANGE,
                        confidence=0.85,
                        description=(
                            f"🚨 UNKNOWN FACE IN RESTRICTED ZONE: Unregistered person #{obj.track_id} "
                            f"detected inside '{zone_names}' — not found in personnel database"
                        ),
                        risk_score=80,
                        metadata={"zone_names": zone_names, "track_id": obj.track_id}
                    )
                    self._handle_event(unk_face_event, frame, obj)

        annotated = self._draw_annotations(frame, tracked_objects)
        if self.on_frame:
            self.on_frame(self.config.camera_id, annotated)

    def _run_face_verification(self, frame: np.ndarray, obj: TrackedObject):
        x1, y1, x2, y2 = [int(v) for v in obj.bbox]
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        # Adaptive Face ROI crop:
        # Seated/webcam view (H < 380 or H/W < 1.6): Person bbox covers upper body; crop top 85% so mouth & chin are included.
        # Full-body view (H >= 380): Crop top 60% for head and neck.
        box_h = y2 - y1
        box_w = x2 - x1
        if box_h < 380 or (box_h / float(max(1, box_w)) < 1.6):
            crop_bottom = min(h, y1 + int(box_h * 0.85))
        else:
            crop_bottom = min(h, y1 + int(box_h * 0.60))
        face_region = frame[y1:crop_bottom, x1:x2]
        if face_region.size == 0:
            return None
        result = self.face_verifier.verify(face_region)

        status_map = {
            VerificationStatus.VERIFIED: IdentityStatus.VERIFIED,
            VerificationStatus.UNKNOWN: IdentityStatus.UNKNOWN,
            VerificationStatus.LOW_CONFIDENCE: IdentityStatus.LOW_CONFIDENCE,
            VerificationStatus.NO_FACE_DETECTED: IdentityStatus.NOT_ATTEMPTED,
            VerificationStatus.DISGUISE_DETECTED: IdentityStatus.UNKNOWN,
        }
        mapped_status = status_map.get(result.status, IdentityStatus.UNKNOWN)

        if result.status == VerificationStatus.DISGUISE_DETECTED:
            state_d = self.event_engine.states.get(obj.track_id)
            if state_d and f"disguise_{obj.track_id}" not in getattr(state_d, 'fired_zone_events', set()):
                if state_d.fired_zone_events is not None:
                    state_d.fired_zone_events.add(f"disguise_{obj.track_id}")
                disguise_event = Event(
                    event_id=str(uuid.uuid4()),
                    event_type=EventType.DISGUISE_DETECTED,
                    track_id=obj.track_id,
                    camera_id=self.config.camera_id,
                    zone_id=None,
                    timestamp=time.time(),
                    severity=Severity.ORANGE,
                    confidence=0.88,
                    description=f"⚠️ DISGUISE / FACE OCCLUSION DETECTED: Person #{obj.track_id} facial features obscured",
                    risk_score=75,
                    metadata={"track_id": obj.track_id}
                )
                self._handle_event(disguise_event, frame, obj)

        return (mapped_status, result.name, result.identity_id, result.role, result.rank_stars, result.rank_title)

    def _crop_object(self, frame: np.ndarray, obj) -> Optional[np.ndarray]:
        x1, y1, x2, y2 = [int(v) for v in obj.bbox]
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        crop = frame[y1:y2, x1:x2]
        return crop if crop.size > 0 else None

    def _async_anpr_worker(self, track_id: int, crop: np.ndarray, label: str, bbox: tuple):
        try:
            if self.plate_recognizer is None or crop.size == 0:
                return
            anpr_result = self.plate_recognizer.recognize(crop)
            if anpr_result and anpr_result.plate_text:
                match_info = anpr_result.watchlist_match or {}
                owner_name = match_info.get("owner_name")
                owner_ref = match_info.get("owner_ref")
                is_threat = (anpr_result.status == PlateStatus.WATCHLIST_HIT)
                is_reg = (anpr_result.status == PlateStatus.REGISTERED)

                self._vehicle_plates[track_id] = {
                    "plate": anpr_result.plate_text,
                    "owner": owner_name,
                    "owner_ref": owner_ref,
                    "is_watchlist": is_threat,
                    "is_registered": is_reg,
                    "is_fuzzy": anpr_result.is_fuzzy,
                    "driver_2fa": "N/A",
                    "driver_name": None,
                    "bbox": bbox,
                    "label": label,
                    "confidence": anpr_result.confidence,
                    "match_info": match_info,
                    "status": anpr_result.status,
                    "last_seen": time.time(),
                }
        except Exception as e:
            logger.error(f"Async ANPR failed for track {track_id}: {e}")
        finally:
            self._anpr_in_flight.discard(track_id)

    def _extract_visual_signature(self, frame: np.ndarray, obj: TrackedObject) -> Optional[np.ndarray]:
        x1, y1, x2, y2 = [int(v) for v in obj.bbox]
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 <= x1 or y2 <= y1:
            return None
        
        crop = frame[y1:y2, x1:x2]
        if crop.size == 0:
            return None
            
        if obj.is_person:
            # Focus on the torso (middle 20-70% height) to get clothing color
            crop_h = crop.shape[0]
            region = crop[int(crop_h * 0.2):int(crop_h * 0.7), :]
        else:
            # For bags and vehicles, use the central 80% to avoid background edges
            crop_h, crop_w = crop.shape[:2]
            region = crop[int(crop_h * 0.1):int(crop_h * 0.9), int(crop_w * 0.1):int(crop_w * 0.9)]
            
        if region.size == 0:
            return None
            
        # Convert to HSV and extract Hue and Saturation histogram
        hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [50, 60], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist

    def _detect_vehicle_color(self, frame: np.ndarray, bbox: tuple) -> Optional[str]:
        """
        Extracts dominant color of a vehicle from its bounding box crop.
        Maps HSV hue + saturation/value to a human-readable color name.
        Returns color string like 'Black', 'White', 'Red', 'Silver', 'Blue', etc.
        """
        try:
            x1, y1, x2, y2 = [int(v) for v in bbox]
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                return None
            # Use center 60% of crop to avoid background
            crop = frame[y1:y2, x1:x2]
            ch, cw = crop.shape[:2]
            region = crop[int(ch*0.1):int(ch*0.9), int(cw*0.1):int(cw*0.9)]
            if region.size == 0:
                return None

            hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
            # Compute mean H, S, V
            mean_h = float(np.mean(hsv[:, :, 0]))
            mean_s = float(np.mean(hsv[:, :, 1]))
            mean_v = float(np.mean(hsv[:, :, 2]))

            # Map to color names
            if mean_v < 40:
                return "Black"
            if mean_v > 210 and mean_s < 30:
                return "White"
            if mean_v > 150 and mean_s < 50:
                return "Silver"
            if mean_s < 40:
                return "Gray"
            # Hue-based classification (OpenCV H range: 0-179)
            if mean_h < 10 or mean_h > 160:
                return "Red"
            if 10 <= mean_h < 25:
                return "Orange"
            if 25 <= mean_h < 35:
                return "Yellow"
            if 35 <= mean_h < 85:
                return "Green"
            if 85 <= mean_h < 130:
                return "Blue"
            if 130 <= mean_h < 160:
                return "Purple"
            return None
        except Exception:
            return None

    def _handle_event(self, event: Event, frame: np.ndarray, obj: Optional[TrackedObject] = None):

        best = self.snapshot_selector.get_best(obj.track_id) if obj is not None else None
        base_frame = best[1].copy() if best else frame.copy()

        # Burn-in tactical evidence annotations & bounding box
        evidence_frame = base_frame.copy()
        if obj is not None:
            bx1, by1, bx2, by2 = [int(v) for v in obj.bbox]
            color = (0, 0, 255) if event.severity == Severity.RED else (0, 165, 255) if event.severity == Severity.ORANGE else (0, 220, 255)
            cv2.rectangle(evidence_frame, (bx1, by1), (bx2, by2), color, 2)

            # Tactical corner reticles
            line_len = max(6, min(18, (bx2 - bx1) // 4, (by2 - by1) // 4))
            cv2.line(evidence_frame, (bx1, by1), (bx1 + line_len, by1), color, 3)
            cv2.line(evidence_frame, (bx1, by1), (bx1, by1 + line_len), color, 3)
            cv2.line(evidence_frame, (bx2, by1), (bx2 - line_len, by1), color, 3)
            cv2.line(evidence_frame, (bx2, by1), (bx2, by1 + line_len), color, 3)
            cv2.line(evidence_frame, (bx1, by2), (bx1 + line_len, by2), color, 3)
            cv2.line(evidence_frame, (bx1, by2), (bx1, by2 - line_len), color, 3)
            cv2.line(evidence_frame, (bx2, by2), (bx2 - line_len, by2), color, 3)
            cv2.line(evidence_frame, (bx2, by2), (bx2, by2 - line_len), color, 3)

            # Target tag badge
            badge_text = f"TARGET #{obj.track_id} [{event.event_type.value}]"
            cv2.rectangle(evidence_frame, (bx1, max(0, by1 - 22)), (bx1 + len(badge_text) * 9, max(0, by1)), (20, 20, 30), -1)
            cv2.putText(evidence_frame, badge_text, (bx1 + 4, max(0, by1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

        # Draw forensic evidence watermark banner
        fh, fw = evidence_frame.shape[:2]
        banner_h = 30
        overlay = evidence_frame.copy()
        cv2.rectangle(overlay, (0, fh - banner_h), (fw, fh), (15, 18, 24), -1)
        cv2.addWeighted(overlay, 0.85, evidence_frame, 0.15, 0, evidence_frame)

        stamp_time = datetime.fromtimestamp(event.timestamp).strftime("%Y-%m-%d %H:%M:%S")
        forensic_text = f"GARUDA FORENSIC EVIDENCE | CAM: {event.camera_id} | {stamp_time} | SEV: {event.severity.value} | CONF: {int(event.confidence * 100)}%"
        cv2.putText(evidence_frame, forensic_text, (12, fh - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 240, 255), 1, cv2.LINE_AA)

        event.__dict__["_snapshot_frame"] = evidence_frame

        if self.on_event:
            self.on_event(event)

        alert = self.alert_engine.process_event(
            event, camera_location=self.config.location,
            snapshot_path=None,  # backend persistence layer writes the file and fills this in
        )
        if alert is not None:
            # attach the actual image bytes via a side-channel the backend picks up;
            # kept out of the dataclass to avoid coupling AI engine to disk I/O
            alert.__dict__["_snapshot_frame"] = evidence_frame

    def _draw_annotations(self, frame: np.ndarray, tracked_objects: list[TrackedObject]) -> np.ndarray:
        annotated = frame.copy()
        current_hour = datetime.now().hour
        for obj in tracked_objects:
            x1, y1, x2, y2 = [int(v) for v in obj.bbox]

            if obj.is_person:
                state = self.event_engine.states.get(obj.track_id)
                cached = self._track_identities.get(obj.track_id, {})
                is_verified = (
                    (state and state.identity_name and getattr(state.identity_status, "value", "").upper() == "VERIFIED") or
                    (cached.get("is_verified", False))
                )
                is_low_conf = state and getattr(state.identity_status, "value", "").upper() == "LOW_CONFIDENCE"

                has_breach = state and any("unauthorized_wrong_zone" in t.event_type for t in state.timeline[-3:])
                if is_verified and has_breach:
                    color = (0, 0, 255)       # Alert Red (BGR)
                    badge_bg = (0, 0, 220)
                    badge_fg = (255, 255, 255)
                    stars = "★" * getattr(state, "rank_stars", 1)
                    label = f"🚨 RANK BREACH: [{stars}] {state.identity_name}"
                elif is_verified:
                    color = (0, 200, 50)       # Emerald Green (BGR)
                    badge_bg = (0, 140, 30)
                    badge_fg = (255, 255, 255)
                    label = f"✓ AUTHORIZED: {state.identity_name if (state and state.identity_name) else 'Personnel'} #{obj.track_id}"
                elif is_low_conf:
                    color = (0, 165, 255)     # Amber
                    badge_bg = (0, 140, 255)
                    badge_fg = (0, 0, 0)
                    label = f"? VERIFY: {state.identity_name or 'Person'}"
                else:
                    is_drone_cam = "drone" in self.config.camera_id.lower() or "drone" in str(self.config.source_uri).lower()
                    is_thermal_cam = "thermal" in self.config.camera_id.lower() or "thermal" in str(self.config.source_uri).lower() or getattr(self, "_current_thermal_mode", ThermalMode.VISIBLE_RGB) != ThermalMode.VISIBLE_RGB
                    if is_drone_cam:
                        color = (0, 240, 255)     # Tactical Drone Yellow/Cyan
                        badge_bg = (0, 140, 180)
                        badge_fg = (0, 0, 0)
                        label = f"HEAD SCAN #{obj.track_id} [{int(obj.confidence * 100)}%]"
                    elif is_thermal_cam:
                        color = (0, 180, 255)     # Glowing Heat Gold
                        badge_bg = (180, 30, 220) # Thermal Violet
                        badge_fg = (255, 255, 255)
                        label = f"HEAT SIGNATURE #{obj.track_id} [37.2°C]"
                    else:
                        color = (0, 220, 0)       # Standard Green
                        badge_bg = (0, 140, 0)
                        badge_fg = (255, 255, 255)
                        metric_str = ""
                        dist_m = 999.0
                        vel_kmh = 0.0
                        if state:
                            dist_m = getattr(state, "distance_to_fence_m", 999.0)
                            vel_kmh = getattr(state, "velocity_kmh", 0.0)
                        if dist_m < 150.0:
                            metric_str = f" | {dist_m:.0f}m"
                        if vel_kmh > 0.5:
                            metric_str += f" | {vel_kmh:.1f}km/h"

                        thermal_tag = ""
                        if getattr(self, "_current_thermal_mode", ThermalMode.VISIBLE_RGB) != ThermalMode.VISIBLE_RGB:
                            thermal_tag = " [37°C HEAT]"
                        label = f"Person #{obj.track_id}{thermal_tag}{metric_str}"

            elif obj.is_bag:
                state = self.event_engine.states.get(obj.track_id)
                if state and state.abandoned_event_fired:
                    color = (0, 0, 255)       # Alert Red
                    badge_bg = (0, 0, 220)
                    badge_fg = (255, 255, 255)
                    owner_info = f" (Person #{state.associated_person_track_id})" if state.associated_person_track_id else ""
                    label = f"🚨 ABANDONED: {obj.label.title()} #{obj.track_id}{owner_info}"
                elif state and state.unattended_event_fired:
                    color = (0, 140, 255)     # Deep Amber/Orange
                    badge_bg = (0, 110, 220)
                    badge_fg = (255, 255, 255)
                    label = f"⚠️ UNATTENDED: {obj.label.title()} #{obj.track_id}"
                else:
                    color = (0, 165, 255)     # Amber-Gold (BGR)
                    badge_bg = (0, 130, 220)
                    badge_fg = (255, 255, 255)
                    assoc = f" (with #{state.associated_person_track_id})" if state and state.associated_person_track_id else ""
                    label = f"Bag: {obj.label.title()} #{obj.track_id}{assoc}"
            elif obj.is_phone or obj.label == "cell phone":
                color = (255, 50, 180)    # Vibrant Magenta (BGR)
                badge_bg = (200, 30, 140)
                badge_fg = (255, 255, 255)
                label = f"Phone #{obj.track_id} ({int(obj.confidence * 100)}%)"
            elif obj.is_vehicle:
                color = (255, 140, 0)     # Sky Blue (BGR)
                badge_bg = (200, 100, 0)
                badge_fg = (255, 255, 255)
                # --- Vehicle Color Detection ---
                vehicle_color_name = self._detect_vehicle_color(frame, obj.bbox)
                if vehicle_color_name:
                    self._vehicle_colors[obj.track_id] = vehicle_color_name
                stored_color = self._vehicle_colors.get(obj.track_id, "")
                color_tag = f" [{stored_color}]" if stored_color else ""

                # --- Vehicle Speed Alert ---
                state_v = self.event_engine.states.get(obj.track_id)
                speed_kmh = getattr(state_v, "velocity_kmh", 0.0) if state_v else 0.0
                movement_type = getattr(state_v, "movement_type", "STATIONARY") if state_v else "STATIONARY"
                speed_tag = ""
                if speed_kmh > 1.0:
                    speed_tag = f" | {speed_kmh:.1f} km/h"
                    # Alert only if vehicle is actually speeding (>35 km/h) with sustained trajectory history
                    if (
                        obj.track_id > 0
                        and speed_kmh > 35.0
                        and movement_type == "VEHICULAR"
                        and state_v
                        and len(getattr(state_v, "position_history", [])) >= 12
                        and f"speed_alert_{obj.track_id}" not in state_v.fired_zone_events
                    ):
                        state_v.fired_zone_events.add(f"speed_alert_{obj.track_id}")
                        speed_event = Event(
                            event_id=str(uuid.uuid4()),
                            event_type=EventType.VEHICLE_SPEED_ALERT,
                            track_id=obj.track_id,
                            camera_id=self.config.camera_id,
                            zone_id=None,
                            timestamp=time.time(),
                            severity=Severity.ORANGE,
                            confidence=0.88,
                            description=f"🚗 VEHICLE SPEED ALERT: {obj.label.title()}#{obj.track_id}{color_tag} travelling at {speed_kmh:.1f} km/h near checkpoint — above safe limit",
                            risk_score=50,
                            metadata={"speed_kmh": round(speed_kmh, 1), "vehicle_type": obj.label, "color": stored_color}
                        )
                        self._handle_event(speed_event, frame, obj)

                # --- Vehicle Reconnaissance (Circling) Detection ---
                if state_v and obj.track_id > 0:
                    matched_vz = self.zone_engine.check_point(self.config.camera_id, obj.foot_point, current_hour)
                    if matched_vz and obj.track_id not in self._vehicle_recon_alerted:
                        passes = self._vehicle_zone_pass_times.setdefault(obj.track_id, [])
                        now_vr = time.time()
                        # Record a new pass if last pass was >10s ago (not just lingering)
                        if not passes or (now_vr - passes[-1]) > 10.0:
                            passes.append(now_vr)
                        # Prune passes older than 5 minutes
                        self._vehicle_zone_pass_times[obj.track_id] = [t for t in passes if (now_vr - t) < 300]
                        if len(self._vehicle_zone_pass_times[obj.track_id]) >= 3:
                            self._vehicle_recon_alerted.add(obj.track_id)
                            recon_event = Event(
                                event_id=str(uuid.uuid4()),
                                event_type=EventType.VEHICLE_RECONNAISSANCE,
                                track_id=obj.track_id,
                                camera_id=self.config.camera_id,
                                zone_id=matched_vz[0].zone_id if matched_vz else None,
                                timestamp=now_vr,
                                severity=Severity.ORANGE,
                                confidence=0.85,
                                description=(
                                    f"🚗 VEHICLE RECONNAISSANCE: {obj.label.title()}#{obj.track_id}{color_tag} "
                                    f"has passed this zone {len(self._vehicle_zone_pass_times[obj.track_id])} times — "
                                    f"possible perimeter surveillance"
                                ),
                                risk_score=65,
                                metadata={"pass_count": len(self._vehicle_zone_pass_times[obj.track_id]), "color": stored_color}
                            )
                            self._handle_event(recon_event, frame, obj)

                if obj.label in ("bicycle", "motorcycle"):
                    has_rider = any(
                        p.is_person and (
                            max(0, min(obj.bbox[2], p.bbox[2]) - max(obj.bbox[0], p.bbox[0])) *
                            max(0, min(obj.bbox[3], p.bbox[3]) - max(obj.bbox[1], p.bbox[1])) > 0
                        ) for p in tracked_objects
                    )
                    v_title = f"{obj.label.title()} Rider" if has_rider else obj.label.title()
                else:
                    v_title = obj.label.title()
                label = f"{v_title}#{obj.track_id}{color_tag}{speed_tag}"
            else:
                color = (200, 200, 50)
                badge_bg = (150, 150, 40)
                badge_fg = (255, 255, 255)
                label = f"{obj.label.title()} #{obj.track_id}"

            # Draw bounding box
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)


            # Draw top badge pill
            badge_y = max(18, y1 - 6)
            badge_w = max(70, len(label) * 8 + 12)
            cv2.rectangle(annotated, (x1, badge_y - 15), (x1 + badge_w, badge_y + 3), badge_bg, -1)
            cv2.putText(annotated, label, (x1 + 4, badge_y - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, badge_fg, 1, cv2.LINE_AA)

            # Draw Human Action Skeleton & Action Badge
            if obj.is_person and getattr(self, "pose_engine", None) and obj.track_id in self._track_poses:
                paction = self._track_poses[obj.track_id]
                self.pose_engine.draw_skeleton(annotated, paction)

                # Draw Action Badge Pill
                if paction.action_type != "NORMAL":
                    if paction.action_type == "FALL_DETECTED":
                        act_text = f"🚨 FALL / MAN-DOWN ({int(paction.confidence * 100)}%)"
                        act_bg = (0, 0, 220)
                        act_fg = (255, 255, 255)
                    elif paction.action_type == "CRAWLING":
                        act_text = f"⚠️ CRAWLING / PRONE ({int(paction.confidence * 100)}%)"
                        act_bg = (0, 140, 255)
                        act_fg = (255, 255, 255)
                    elif paction.action_type == "HANDS_RAISED":
                        act_text = f"🏳️ HANDS UP ({int(paction.confidence * 100)}%)"
                        act_bg = (0, 200, 220)
                        act_fg = (0, 0, 0)
                    else:
                        act_text = paction.action_type
                        act_bg = (60, 60, 60)
                        act_fg = (255, 255, 255)

                    act_y = min(frame.shape[0] - 8, y2 + 16)
                    act_w = max(80, len(act_text) * 7 + 12)
                    cv2.rectangle(annotated, (x1, act_y - 12), (x1 + act_w, act_y + 4), act_bg, -1)
                    cv2.putText(annotated, act_text, (x1 + 4, act_y - 1),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.40, act_fg, 1, cv2.LINE_AA)

            # If we have a plate reading for this vehicle or plate candidate, render badge below
            if (obj.is_vehicle or obj.is_plate_candidate or obj.track_id in self._vehicle_plates) and obj.track_id in self._vehicle_plates:
                raw_info = self._vehicle_plates[obj.track_id]
                if isinstance(raw_info, dict):
                    plate_text = raw_info.get("plate", "")
                    owner = raw_info.get("owner")
                    is_threat = raw_info.get("is_watchlist", False)
                    is_reg = raw_info.get("is_registered", False)
                else:
                    plate_text = str(raw_info)
                    owner, is_threat, is_reg = None, False, False

                is_fuzzy = raw_info.get("is_fuzzy", False)
                fuzzy_tag = " ~" if is_fuzzy else ""
                driver_2fa = raw_info.get("driver_2fa")
                driver_name = raw_info.get("driver_name")

                if is_threat:
                    badge_label = f"🚨 WATCHLIST: {plate_text}{fuzzy_tag}"
                    badge_bg = (0, 0, 220)      # Bright Red (BGR)
                    badge_fg = (255, 255, 255)  # White
                elif driver_2fa == "VERIFIED":
                    badge_label = f"✓ 2FA VERIFIED: {plate_text} | Driver: {driver_name}"
                    badge_bg = (0, 180, 0)      # Rich Green
                    badge_fg = (255, 255, 255)  # White
                elif driver_2fa == "MISMATCH":
                    badge_label = f"🚨 2FA MISMATCH: {plate_text} | Driver: {driver_name}"
                    badge_bg = (0, 69, 255)     # Orange-Red
                    badge_fg = (255, 255, 255)  # White
                elif driver_2fa == "UNVERIFIED" and owner:
                    badge_label = f"⚠️ UNVERIFIED DRIVER: {plate_text} (Owner: {owner})"
                    badge_bg = (0, 140, 255)    # Amber-Orange
                    badge_fg = (0, 0, 0)        # Black
                elif is_reg:
                    badge_label = f"CLEARED: {plate_text} ({owner}){fuzzy_tag}" if owner else f"CLEARED: {plate_text}{fuzzy_tag}"
                    badge_bg = (0, 180, 0)      # Rich Green
                    badge_fg = (255, 255, 255)  # White
                else:
                    badge_label = f"PLATE: {plate_text}"
                    badge_bg = (0, 220, 255)    # Amber / Yellow
                    badge_fg = (0, 0, 0)        # Black

                badge_y2 = y2 + 20
                badge_w2 = max(100, len(badge_label) * 9 + 12)
                cv2.rectangle(annotated, (x1, y2 + 2), (x1 + badge_w2, badge_y2 + 4), badge_bg, -1)
                cv2.putText(annotated, badge_label, (x1 + 4, badge_y2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.48, badge_fg, 1, cv2.LINE_AA)

        # Render standalone plate detections (virtual tracks >= 9000)
        now = time.time()
        for vid, raw_info in self._vehicle_plates.items():
            if vid < 9000 or not isinstance(raw_info, dict):
                continue
            if now - raw_info.get("last_seen", 0) > 0.4:
                continue
            bbox = raw_info.get("bbox")
            if not bbox:
                continue
            x1, y1, x2, y2 = [int(v) for v in bbox]
            plate_text = raw_info.get("plate", "")
            if not plate_text:
                continue
            owner = raw_info.get("owner")
            is_threat = raw_info.get("is_watchlist", False)
            is_reg = raw_info.get("is_registered", False)
            is_fuzzy = raw_info.get("is_fuzzy", False)
            fuzzy_tag = " ~" if is_fuzzy else ""

            if is_threat:
                badge_label = f"🚨 WATCHLIST: {plate_text}{fuzzy_tag}"
                badge_bg = (0, 0, 220)      # Bright Red (BGR)
                badge_fg = (255, 255, 255)  # White
                box_color = (0, 0, 255)
            elif is_reg:
                badge_label = f"CLEARED: {plate_text} ({owner}){fuzzy_tag}" if owner else f"CLEARED: {plate_text}{fuzzy_tag}"
                badge_bg = (0, 180, 0)      # Rich Green
                badge_fg = (255, 255, 255)  # White
                box_color = (0, 220, 0)
            else:
                badge_label = f"PLATE: {plate_text}"
                badge_bg = (0, 220, 255)    # Amber / Yellow
                badge_fg = (0, 0, 0)        # Black
                box_color = (0, 220, 255)

            # Draw rectangle around standalone plate with glow border
            cv2.rectangle(annotated, (x1, y1), (x2, y2), box_color, 2)
            badge_y = max(20, y1 - 8)
            badge_w = max(100, len(badge_label) * 9 + 12)
            cv2.rectangle(annotated, (x1, badge_y - 16), (x1 + badge_w, badge_y + 4), badge_bg, -1)
            cv2.putText(annotated, badge_label, (x1 + 4, badge_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, badge_fg, 1, cv2.LINE_AA)

        # Render active threat & weapon detections (smoothed pulsating red bounding box & warning badge)
        now = time.time()
        for w in self._active_weapons:
            if now - w.get("last_seen", 0) > 0.45:
                continue
            bbox = w.get("bbox")
            if not bbox:
                continue
            wx1, wy1, wx2, wy2 = [int(v) for v in bbox]
            w_label = w.get("label", "Threat").upper()
            w_tag = w.get("category_tag", "THREAT")
            w_conf = int(w.get("confidence", 0.9) * 100)
            badge_text = f"🚨 {w_tag}: {w_label} ({w_conf}%)"

            # Draw glowing double red rectangle
            cv2.rectangle(annotated, (wx1 - 2, wy1 - 2), (wx2 + 2, wy2 + 2), (0, 0, 160), 1)
            cv2.rectangle(annotated, (wx1, wy1), (wx2, wy2), (0, 0, 255), 3)

            # Badge header above the weapon
            badge_w = max(130, len(badge_text) * 9 + 16)
            badge_y = max(24, wy1 - 6)
            cv2.rectangle(annotated, (wx1, badge_y - 20), (wx1 + badge_w, badge_y + 2), (0, 0, 220), -1)
            cv2.putText(annotated, badge_text, (wx1 + 4, badge_y - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, (255, 255, 255), 1, cv2.LINE_AA)

        zones = self.zone_engine.get_zones_for_camera(self.config.camera_id)
        if zones:
            overlay = annotated.copy()
            ZONE_COLORS = {
                "high_security": ((0, 0, 255), (0, 0, 180), "🚨 ZERO LINE"),
                "restricted": ((0, 140, 255), (0, 100, 200), "⛔ RESTRICTED"),
                "monitored": ((0, 220, 255), (0, 180, 200), "⚠️ MONITORED"),
                "sensitive": ((255, 50, 180), (180, 30, 140), "🔒 SENSITIVE"),
                "entry": ((0, 220, 100), (0, 160, 60), "🚪 ENTRY GATE"),
                "exit": ((200, 200, 50), (150, 150, 40), "🚪 EXIT GATE"),
                "vehicle_only": ((255, 140, 0), (200, 100, 0), "🚗 VEHICLE LANE"),
                "general": ((180, 180, 180), (120, 120, 120), "🌐 PATROL ZONE"),
            }

            has_overlay = False
            for zone in zones:
                if not zone.enabled or len(zone.polygon) < 3:
                    continue
                z_type = getattr(zone.zone_type, "value", str(zone.zone_type))
                color_line, color_bg, tag = ZONE_COLORS.get(z_type, ((0, 0, 255), (0, 0, 180), "ZONE"))
                pts = np.array(zone.polygon, dtype=np.int32).reshape((-1, 1, 2))
                cv2.fillPoly(overlay, [pts], color_bg)
                has_overlay = True

            if has_overlay:
                cv2.addWeighted(overlay, 0.18, annotated, 0.82, 0, annotated)

            # Draw crisp outlines and label pills
            for zone in zones:
                if not zone.enabled or len(zone.polygon) < 3:
                    continue
                z_type = getattr(zone.zone_type, "value", str(zone.zone_type))
                color_line, color_bg, tag = ZONE_COLORS.get(z_type, ((0, 0, 255), (0, 0, 180), "ZONE"))
                pts = np.array(zone.polygon, dtype=np.int32).reshape((-1, 1, 2))
                cv2.polylines(annotated, [pts], isClosed=True, color=color_line, thickness=2)

                top_vertex = min(zone.polygon, key=lambda p: (p[1], p[0]))
                bx, by = int(top_vertex[0]), max(18, int(top_vertex[1]) - 6)
                min_stars = getattr(zone, "min_rank_stars", 0)
                star_prefix = f"[{min_stars}★] " if min_stars > 0 else ""
                badge_text = f"{star_prefix}{tag}: {zone.name}"
                badge_w = max(80, len(badge_text) * 8 + 12)
                cv2.rectangle(annotated, (bx, by - 16), (bx + badge_w, by + 4), color_bg, -1)
                cv2.putText(annotated, badge_text, (bx + 4, by - 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 1, cv2.LINE_AA)

        # ---- Render Active Torch Detections on HUD ----
        now_td = time.time()
        for torch_det in getattr(self, "_active_torch_detections", []):
            tx1, ty1, tx2, ty2 = torch_det.bbox
            torch_color = (0, 200, 255)   # Amber-yellow for torch glow
            cv2.circle(annotated, (int(torch_det.centroid[0]), int(torch_det.centroid[1])),
                       max(8, int(torch_det.area_px ** 0.5)), torch_color, 2)
            cv2.rectangle(annotated, (tx1, ty1), (tx2, ty2), torch_color, 1)
            torch_label = self.light_source_detector.get_hud_label(torch_det)
            badge_w_t = max(80, len(torch_label) * 9 + 12)
            badge_y_t = max(20, ty1 - 8)
            cv2.rectangle(annotated, (tx1, badge_y_t - 18), (tx1 + badge_w_t, badge_y_t + 4), (30, 100, 150), -1)
            cv2.putText(annotated, torch_label, (tx1 + 4, badge_y_t - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 230, 255), 1, cv2.LINE_AA)

        # Draw Operational HUD Indicators (Night IR & Two-Tier Trigger Status)
        hud_x = annotated.shape[1] - 280
        hud_y = 28
        if getattr(self, "_last_night_enhanced", False):
            cv2.rectangle(annotated, (hud_x - 6, hud_y - 18), (hud_x + 270, hud_y + 6), (30, 30, 40), -1)
            cv2.rectangle(annotated, (hud_x - 6, hud_y - 18), (hud_x + 270, hud_y + 6), (0, 200, 255), 1)
            cv2.putText(annotated, "🌙 NIGHT IR ENHANCED [SNR BOOST]", (hud_x, hud_y - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, (0, 220, 255), 1, cv2.LINE_AA)
            hud_y += 30

        if getattr(self, "_current_thermal_mode", ThermalMode.VISIBLE_RGB) != ThermalMode.VISIBLE_RGB:
            t_mode_str = self._current_thermal_mode.value.replace("THERMAL_", "")
            cv2.rectangle(annotated, (hud_x - 6, hud_y - 18), (hud_x + 270, hud_y + 6), (40, 20, 50), -1)
            cv2.rectangle(annotated, (hud_x - 6, hud_y - 18), (hud_x + 270, hud_y + 6), (220, 50, 255), 1)
            cv2.putText(annotated, f"🔥 THERMAL: {t_mode_str} [HEAT ON]", (hud_x, hud_y - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, (240, 100, 255), 1, cv2.LINE_AA)
            hud_y += 30

        if not getattr(self, "_motion_trigger_active", True):
            cv2.rectangle(annotated, (hud_x - 6, hud_y - 18), (hud_x + 270, hud_y + 6), (30, 40, 30), -1)
            cv2.rectangle(annotated, (hud_x - 6, hud_y - 18), (hud_x + 270, hud_y + 6), (50, 200, 50), 1)
            cv2.putText(annotated, "⚡ TIER-1 IDLE ECO (SAVE 75% GPU)", (hud_x, hud_y - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.44, (100, 255, 100), 1, cv2.LINE_AA)

        # Tactical Drone Recon HUD Ribbon
        is_drone_cam = "drone" in self.config.camera_id.lower() or "drone" in str(self.config.source_uri).lower()
        if is_drone_cam:
            heads_scanned = sum(1 for o in tracked_objects if o.is_person)
            w = annotated.shape[1]
            cv2.rectangle(annotated, (10, 10), (min(w - 10, 480), 34), (16, 22, 30), -1)
            cv2.rectangle(annotated, (10, 10), (min(w - 10, 480), 34), (0, 220, 255), 1)
            hud_txt = f"🚁 UAV AERIAL SCAN · HEADS DETECTED: {heads_scanned} · ALT: 42M"
            cv2.putText(annotated, hud_txt, (18, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 240, 255), 1, cv2.LINE_AA)

        # Tactical Thermal FLIR HUD Ribbon
        is_thermal_cam = "thermal" in self.config.camera_id.lower() or "thermal" in str(self.config.source_uri).lower()
        if is_thermal_cam:
            heat_count = sum(1 for o in tracked_objects if o.is_person)
            w = annotated.shape[1]
            cv2.rectangle(annotated, (10, 10), (min(w - 10, 480), 34), (20, 16, 30), -1)
            cv2.rectangle(annotated, (10, 10), (min(w - 10, 480), 34), (200, 50, 255), 1)
            hud_txt = f"🔥 FLIR RADIOMETRIC · HEAT SIGNATURES: {heat_count} · RANGE: 37°C"
            cv2.putText(annotated, hud_txt, (18, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.40, (240, 100, 255), 1, cv2.LINE_AA)

        return annotated
