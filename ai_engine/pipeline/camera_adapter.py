"""
CameraAdapter — unifies RTSP streams, webcams, and recorded video files
behind one interface so the rest of the pipeline never needs to know
what kind of source it's reading from.

This is the abstraction that lets GARUDE claim "works with existing CCTV":
an RTSP URL from a real IP camera, a phone running an IP-camera app,
a laptop webcam, and a recorded .mp4 file are all just "a thing that
gives us frames" from here on.
"""

from __future__ import annotations

import time
from datetime import datetime
import logging
import threading
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
import os

import cv2
import numpy as np

logger = logging.getLogger("garude.camera_adapter")


from abc import ABC, abstractmethod


class SensorModality(str, Enum):
    VISIBLE_RGB = "VISIBLE_RGB"
    IR_NIGHT = "IR_NIGHT"
    THERMAL = "THERMAL"
    FUTURE_RADAR = "FUTURE_RADAR"
    FUTURE_SENSOR = "FUTURE_SENSOR"


class SourceType(str, Enum):
    RTSP = "rtsp"
    WEBCAM = "webcam"
    FILE = "file"
    DEMO = "demo"
    ONVIF = "onvif"
    SENSOR = "sensor"


class CameraStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"
    INITIALIZING = "INITIALIZING"


@dataclass
class CameraConfig:
    camera_id: str
    name: str
    location: str
    source_type: SourceType
    source_uri: str          # rtsp://..., an int index (as str) for webcam, or a file path
    target_fps: int = 35     # inference FPS — NOT the same as camera's native FPS
    loop_file: bool = True   # for recorded video, loop back to start for a continuous demo
    ai_enabled: bool = True  # True = full AI (YOLO, ANPR, Face); False = low-power passthrough video only
    modality: Optional[SensorModality] = None  # Sensor modality tag
    rotation: int = 0        # 0, 90, 180, 270 degrees clockwise


@dataclass
class FrameResult:
    frame: Optional[np.ndarray]
    timestamp: float
    ok: bool
    camera_id: str
    modality: SensorModality = SensorModality.VISIBLE_RGB


class BaseVideoSource(ABC):
    """
    Abstract Base Class for all existing infrastructure video and sensor feeds.
    Guarantees thread-safe reading, health telemetry, and camera-level fault isolation.
    """

    def __init__(self, config: CameraConfig):
        self.config = config
        self.camera_id = config.camera_id
        self.status = CameraStatus.INITIALIZING
        self.last_heartbeat: Optional[float] = None
        self.modality = self._detect_modality()
        self.reconnect_count = 0
        self.dropped_frames = 0
        self.total_frames_read = 0

    def _detect_modality(self) -> SensorModality:
        if self.config.modality:
            return self.config.modality
        text = f"{self.config.name} {self.config.source_uri}".lower()
        if any(k in text for k in ("thermal", "flir", "heat", "lwir")):
            return SensorModality.THERMAL
        if any(k in text for k in ("ir_", "night", "infrared")):
            return SensorModality.IR_NIGHT
        if "radar" in text:
            return SensorModality.FUTURE_RADAR
        if any(k in text for k in ("sensor", "piezo", "pids", "fence")):
            return SensorModality.FUTURE_SENSOR
        return SensorModality.VISIBLE_RGB

    @abstractmethod
    def open(self) -> bool:
        """Open the video stream or sensor connection."""
        pass

    @abstractmethod
    def read_frame(self) -> FrameResult:
        """Read the next frame respecting target_fps throttling."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close source and release resources."""
        pass

    def get_health(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "name": self.config.name,
            "status": self.status.value,
            "modality": self.modality.value,
            "source_type": self.config.source_type.value,
            "last_heartbeat": self.last_heartbeat,
            "reconnect_count": self.reconnect_count,
            "dropped_frames": self.dropped_frames,
            "total_frames_read": self.total_frames_read,
        }


class CameraAdapter:
    """
    Wraps cv2.VideoCapture with reconnection logic and heartbeat tracking.
    Works identically for:
      - RTSP:    source_uri = "rtsp://user:pass@192.168.1.50:554/stream1"
      - Webcam:  source_uri = "0" (or phone IP-webcam URL, e.g. "http://192.168.1.20:8080/video")
      - File:    source_uri = "demo/videos/abandoned_bag.mp4"
    """

    RECONNECT_INTERVAL_SEC = 5
    MAX_CONSECUTIVE_FAILURES = 10

    def __init__(self, config: CameraConfig):
        self.config = config
        self.cap: Optional[cv2.VideoCapture] = None
        self.status = CameraStatus.INITIALIZING
        self.last_heartbeat: Optional[float] = None
        self._consecutive_failures = 0
        self._last_reconnect_attempt = 0.0
        self._last_frame_time = 0.0
        self._min_frame_interval = 1.0 / max(config.target_fps, 1)
        self.rotation = getattr(config, "rotation", 0)

        self._running = False
        self._latest_frame = None
        self._latest_ok = False
        self._frame_seq = 0
        self._last_consumed_seq = -1
        self._last_new_frame_time = 0.0
        self._reader_thread: Optional[threading.Thread] = None
        self._frame_lock = threading.Lock()

    def set_target_fps(self, fps: int):
        """Dynamically throttles reading frame rate (e.g. 3 FPS for passthrough vs 15-20 FPS for AI core)."""
        self.config.target_fps = max(1, fps)
        self._min_frame_interval = 1.0 / self.config.target_fps
        logger.info(f"[{self.config.camera_id}] Target FPS dynamically updated to {self.config.target_fps}")

    def set_rotation(self, rotation: int):
        """Dynamically sets software rotation (0, 90, 180, 270 degrees clockwise)."""
        self.rotation = int(rotation) % 360
        self.config.rotation = self.rotation
        logger.info(f"[{self.config.camera_id}] Rotation updated to {self.rotation}°")

    # ---- connection lifecycle -------------------------------------------------

    @staticmethod
    def get_project_root() -> Path:
        """Returns the project root directory (containing 'demo/videos', 'backend', etc.)."""
        return Path(__file__).resolve().parent.parent.parent

    @classmethod
    def get_demo_video_path(cls, demo_key: str) -> Optional[str]:
        """Maps any demo camera request (drone, thermal, cctv, biometric, barrier) to real surveillance video loops."""
        root = cls.get_project_root()
        demo_dir = root / "demo" / "videos"
        k = str(demo_key).lower()

        if "drone" in k or "aerial" in k or "uav" in k or "air" in k:
            candidate = demo_dir / "drone_crowd.mp4"
        elif "thermal" in k or "flir" in k or "heat" in k or "lwir" in k:
            candidate = demo_dir / "thermal_patrol.mp4"
        elif "biometric" in k or "face" in k or "pacs" in k or "turnstile" in k:
            candidate = demo_dir / "biometric_face.mp4"
            if not candidate.exists():
                candidate = demo_dir / "people_patrol.mp4"
        elif "barrier" in k or "gate" in k or "anpr" in k or "vehicle" in k or "boom" in k:
            candidate = demo_dir / "cctv_traffic.mp4"
        elif "cctv" in k or "traffic" in k or "optical" in k or "road" in k or "checkpoint" in k:
            candidate = demo_dir / "cctv_traffic.mp4"
        elif "people" in k or "patrol" in k or "crowd" in k:
            candidate = demo_dir / "people_patrol.mp4"
        else:
            candidate = demo_dir / "drone_crowd.mp4"

        if candidate.exists():
            return str(candidate)
        return None

    def _resolve_source(self):
        """Resolves source URI to integer index for webcams, real demo video path, or stream URL."""
        uri = str(self.config.source_uri).strip()
        lower_uri = uri.lower()

        # Check for sensor / acoustic synthetic oscilloscope
        if lower_uri in ("demo_sensor", "demo_pids") or "sensor" in lower_uri or "piezo" in lower_uri:
            return "demo_sensor"

        # Check for demo camera views -> map to real surveillance video loops
        demo_path = self.get_demo_video_path(lower_uri)
        if demo_path and (
            self.config.source_type == SourceType.DEMO
            or lower_uri.startswith("demo")
            or lower_uri in ("demo", "synthetic", "mock", "virtual", "demo_cam")
            or "demo_" in lower_uri
            or (self.config.source_type == SourceType.FILE and not os.path.exists(uri))
        ):
            self.config.source_type = SourceType.FILE
            self.config.loop_file = True
            return demo_path

        if self.config.source_type == SourceType.FILE:
            self.config.loop_file = True
            if demo_path and not os.path.exists(uri):
                return demo_path
            if not os.path.isabs(uri):
                root = self.get_project_root()
                abs_path = root / uri
                if abs_path.exists():
                    return str(abs_path)
            return uri

        if self.config.source_type == SourceType.WEBCAM:
            clean = lower_uri
            if clean in ("0", "webcam", "default", "system", "local", "pc", "laptop", "integrated", ""):
                return 0
            if clean in ("1", "usb", "external", "secondary"):
                return 1
            if clean.isdigit():
                return int(clean)
            # Auto-prepend http:// if the user forgot it (otherwise OpenCV thinks it's a file)
            if not uri.startswith(("http://", "https://", "rtsp://")):
                uri = f"http://{uri}"
            # If user provided standard Android IP Webcam URL without the stream endpoint
            if uri.startswith(("http://", "https://")):
                parts = uri.rstrip("/").split("/")
                if len(parts) == 3:  # e.g. ['http:', '', '192.168.1.20:8080']
                    uri = uri.rstrip("/") + "/video"
            return uri
        elif self.config.source_type == SourceType.RTSP:
            if uri.isdigit():
                return int(uri)
            if not uri.startswith(("rtsp://", "http://", "https://")):
                uri = f"rtsp://{uri}"
            if uri.startswith(("http://", "https://")):
                parts = uri.rstrip("/").split("/")
                if len(parts) == 3:
                    uri = uri.rstrip("/") + "/video"
            return uri
        return uri

    def _connect(self) -> bool:
        try:
            source = self._resolve_source()
            if source in ("demo_sensor", "demo_synthetic", "demo"):
                self.status = CameraStatus.ONLINE
                self.last_heartbeat = time.time()
                self._consecutive_failures = 0
                self._running = True
                logger.info(f"[{self.config.camera_id}] connected to Synthetic Virtual Demo Camera feed ({source})")
                return True

            # Set transport timeout to prevent OpenCV read thread from hanging indefinitely on network jitter
            if isinstance(source, str) and (source.startswith("http://") or source.startswith("https://") or source.startswith("rtsp://")):
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|timeout;3000000|stimeout;3000000|rw_timeout;3000000"

            # Seamless zero-stutter in-memory looping for recorded demo video files
            if self.config.source_type == SourceType.FILE and isinstance(source, str) and os.path.isfile(source) and self.config.loop_file:
                temp_cap = cv2.VideoCapture(source)
                self._cached_video_frames = []
                while True:
                    ok, f = temp_cap.read()
                    if not ok or f is None:
                        break
                    if f.shape[1] > 960:
                        h, w = f.shape[:2]
                        f = cv2.resize(f, (960, int(h * 960.0 / w)))
                    _, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    self._cached_video_frames.append(buf)
                temp_cap.release()
                if self._cached_video_frames:
                    self._cached_frame_idx = 0
                    self.status = CameraStatus.ONLINE
                    self.last_heartbeat = time.time()
                    self._consecutive_failures = 0
                    self._running = True
                    logger.info(f"[{self.config.camera_id}] pre-buffered {len(self._cached_video_frames)} seamless frames into ultra-low-latency RAM loop")
                    return True

            if self.config.source_type == SourceType.WEBCAM and isinstance(source, int):
                import sys
                if sys.platform == "win32":
                    self.cap = cv2.VideoCapture(source, cv2.CAP_DSHOW)
                else:
                    self.cap = cv2.VideoCapture(source)
            else:
                self.cap = cv2.VideoCapture(source)

            if self.cap is not None:
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if self.cap is not None and self.cap.isOpened():
                self.status = CameraStatus.ONLINE
                self.last_heartbeat = time.time()
                self._consecutive_failures = 0
                with self._frame_lock:
                    self._frame_seq = 0
                    self._last_new_frame_time = time.time()
                    self._latest_ok = True
                logger.info(f"[{self.config.camera_id}] connected ({self.config.source_type}: {source})")

                self._running = True
                if self.config.source_type != SourceType.FILE:
                    # Start background thread to constantly drain buffer for live streams
                    # This prevents the 10-15s latency delay caused by cv2 buffering
                    self._reader_thread = threading.Thread(target=self._update_frames, daemon=True)
                    self._reader_thread.start()

                return True
            else:
                self.status = CameraStatus.OFFLINE
                self._consecutive_failures += 1
                logger.warning(f"[{self.config.camera_id}] failed to open source: {source}")
                return False
        except Exception as e:
            logger.error(f"[{self.config.camera_id}] connection error: {e}")
            self.status = CameraStatus.ERROR
            self._consecutive_failures += 1
            return False

    def _update_frames(self):
        consecutive_drops = 0
        while self._running and self.cap and self.cap.isOpened():
            ok, frame = self.cap.read()
            if ok and frame is not None:
                consecutive_drops = 0
                # Apply rotation if configured
                rot = self.rotation
                if rot == 90:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif rot == 180:
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                elif rot == 270:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

                # Balance resolution: Keep up to 960px width so distant people/objects retain crisp details
                h, w = frame.shape[:2]
                if w > 960:
                    scale = 960 / w
                    frame = cv2.resize(frame, (960, int(h * scale)))
                with self._frame_lock:
                    self._latest_frame = frame
                    self._latest_ok = True
                    self._frame_seq += 1
                    self._last_new_frame_time = time.time()
            else:
                consecutive_drops += 1
                time.sleep(0.04)
                # Keep ok=True using buffered frame during transient drops; only flag false after 4s
                with self._frame_lock:
                    if time.time() - self._last_new_frame_time > 4.0:
                        self._latest_ok = False
                # Allow high tolerance (150 drops ~ 6.0s) before breaking thread to reconnect
                if consecutive_drops >= 150:
                    logger.warning(f"[{self.config.camera_id}] reader thread detected {consecutive_drops} consecutive frame drops (>6s), triggering reconnect")
                    break

    def _try_reconnect(self):
        now = time.time()
        # Fast progressive backoff: 1s, 2s, up to 3s max for local/LAN streams, 8s for remote
        source_str = str(self.config.source_uri).lower()
        max_backoff = 3.0 if ("192.168." in source_str or "127.0.0.1" in source_str or "localhost" in source_str or source_str.isdigit() or source_str == "0") else 8.0
        fail_step = min(self._consecutive_failures // 3, 3)
        backoff = min(max_backoff, 1.0 * (1.5 ** fail_step))
        if now - self._last_reconnect_attempt < backoff:
            return  # wait until backoff interval passes
        self._last_reconnect_attempt = now
        self.status = CameraStatus.RECONNECTING
        logger.info(f"[{self.config.camera_id}] attempting reconnect (backoff: {backoff:.1f}s)...")
        self.release()
        time.sleep(0.4)
        self._connect()

    # ---- frame reading ----------------------------------------------------

    def _generate_synthetic_frame(self, demo_type: str = "demo_drone") -> np.ndarray:
        t = time.time()
        dtype = demo_type.lower()
        if "cctv" in dtype or "optical" in dtype:
            return self._generate_cctv_frame(t)
        elif "thermal" in dtype or "flir" in dtype:
            return self._generate_thermal_frame(t)
        elif "biometric" in dtype or "pacs" in dtype or "face" in dtype:
            return self._generate_biometric_frame(t)
        elif "barrier" in dtype or "gate" in dtype:
            return self._generate_barrier_frame(t)
        elif "sensor" in dtype or "pids" in dtype or "fence" in dtype:
            return self._generate_sensor_frame(t)
        else:
            return self._generate_drone_frame(t)

    def _generate_cctv_frame(self, t: float) -> np.ndarray:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:180, :] = (48, 42, 38)
        cv2.line(frame, (0, 180), (640, 180), (70, 75, 80), 2)
        for fx in range(0, 640, 40):
            cv2.line(frame, (fx, 140), (fx, 180), (55, 60, 65), 1)

        pts_road = np.array([[180, 180], [460, 180], [640, 480], [0, 480]], np.int32)
        cv2.fillPoly(frame, [pts_road], (26, 28, 32))
        cv2.line(frame, (180, 180), (0, 480), (0, 200, 240), 2)
        cv2.line(frame, (460, 180), (640, 480), (0, 200, 240), 2)
        
        for dy in range(200, 480, 50):
            cv2.line(frame, (320, dy), (320, min(480, dy + 25)), (220, 220, 220), 3)

        cv2.rectangle(frame, (490, 170), (620, 340), (45, 52, 60), -1)
        cv2.rectangle(frame, (490, 170), (620, 340), (80, 95, 110), 2)
        cv2.rectangle(frame, (510, 200), (590, 250), (120, 140, 160), -1)
        cv2.putText(frame, "POST #01", (515, 192), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 200), 1)

        v_cycle = (t * 0.35) % 1.0
        scale = 0.5 + 0.5 * v_cycle
        car_w = int(140 * scale)
        car_h = int(90 * scale)
        car_x = int(320 - car_w // 2 + 25 * np.sin(t * 0.5))
        car_y = int(210 + (420 - 210 - car_h) * v_cycle)

        cv2.rectangle(frame, (car_x, car_y + int(car_h * 0.3)), (car_x + car_w, car_y + car_h), (40, 60, 85), -1)
        cv2.rectangle(frame, (car_x + int(car_w * 0.15), car_y), (car_x + int(car_w * 0.85), car_y + int(car_h * 0.4)), (20, 30, 45), -1)
        hl_r = max(3, int(6 * scale))
        cv2.circle(frame, (car_x + int(car_w * 0.15), car_y + int(car_h * 0.7)), hl_r, (180, 240, 255), -1)
        cv2.circle(frame, (car_x + int(car_w * 0.85), car_y + int(car_h * 0.7)), hl_r, (180, 240, 255), -1)
        
        np_w = int(70 * scale)
        np_h = int(18 * scale)
        np_x = car_x + (car_w - np_w) // 2
        np_y = car_y + int(car_h * 0.75)
        cv2.rectangle(frame, (np_x, np_y), (np_x + np_w, np_y + np_h), (240, 240, 240), -1)
        cv2.rectangle(frame, (np_x, np_y), (np_x + np_w, np_y + np_h), (10, 10, 10), 1)
        if scale > 0.65:
            cv2.putText(frame, "DL 01 AB 1234", (np_x + 3, np_y + np_h - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.32 * scale, (0, 0, 0), 1)

        cv2.rectangle(frame, (car_x - 4, car_y - 4), (car_x + car_w + 4, car_y + car_h + 4), (0, 255, 200), 2)
        cv2.putText(frame, "VEHICLE #104 [CAR 96%]", (car_x - 4, car_y - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 200), 1)
        if scale > 0.65:
            cv2.rectangle(frame, (np_x - 2, np_y - 2), (np_x + np_w + 2, np_y + np_h + 2), (0, 255, 0), 1)
            cv2.putText(frame, "PLATE: DL 01 AB 1234", (np_x - 10, np_y + np_h + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 255, 0), 1)

        cv2.putText(frame, f"[CCTV] {self.config.name.upper()}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (220, 240, 255), 2)
        time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cv2.putText(frame, f"{time_str}  25.0 FPS  BITRATE: 4096 kbps", (20, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 200), 1)
        cv2.circle(frame, (600, 25), 6, (0, 0, 255), -1)
        cv2.putText(frame, "REC", (612, 29), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)
        return frame

    def _generate_drone_frame(self, t: float) -> np.ndarray:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:, :] = (20, 26, 22)
        for gy in range(0, 480, 60):
            cv2.line(frame, (0, gy), (640, gy), (30, 40, 34), 1)
        for gx in range(0, 640, 60):
            cv2.line(frame, (gx, 0), (gx, 480), (30, 40, 34), 1)

        pts_runway = np.array([[80, 480], [180, 480], [540, 0], [440, 0]], np.int32)
        cv2.fillPoly(frame, [pts_runway], (38, 42, 40))
        cv2.line(frame, (130, 480), (490, 0), (180, 190, 170), 1)

        cv2.rectangle(frame, (80, 100), (200, 220), (30, 35, 32), -1)
        cv2.rectangle(frame, (80, 100), (200, 220), (50, 60, 54), 1)
        cv2.putText(frame, "HANGAR-A", (85, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 120, 95), 1)

        cv2.rectangle(frame, (420, 280), (580, 420), (32, 36, 34), -1)
        cv2.rectangle(frame, (420, 280), (580, 420), (52, 62, 56), 1)
        cv2.putText(frame, "DEPOT-B", (425, 300), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (80, 120, 95), 1)

        target_x = int(130 + (490 - 130) * ((t * 0.1) % 1.0))
        target_y = int(480 - (480) * ((t * 0.1) % 1.0))
        cv2.circle(frame, (target_x, target_y), 14, (0, 220, 255), 2)
        cv2.line(frame, (target_x - 20, target_y), (target_x + 20, target_y), (0, 220, 255), 1)
        cv2.line(frame, (target_x, target_y - 20), (target_x, target_y + 20), (0, 220, 255), 1)
        cv2.putText(frame, "TARGET #UAV-88 | SPD: 38 KM/H", (target_x + 24, target_y + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 220, 255), 1)

        cv2.drawMarker(frame, (320, 240), (0, 255, 180), cv2.MARKER_CROSS, 30, 1)
        cv2.circle(frame, (320, 240), 60, (0, 255, 180), 1)
        heading = int((t * 5) % 360)
        cv2.putText(frame, f"HDG: {heading:03d} DEG [NW] | GIMBAL: -54 DEG", (220, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 180), 1)
        cv2.putText(frame, f"[DRONE] {self.config.name.upper()}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 200), 2)
        cv2.putText(frame, "ALT: 86.4M AGL | BATT: 86% [22.1V] | RTK-FIX (19 SATS)", (20, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 180), 1)
        return frame

    def _generate_thermal_frame(self, t: float) -> np.ndarray:
        raw_heat = np.full((480, 640), 28, dtype=np.uint8)
        for y in range(480):
            raw_heat[y, :] = int(22 + (y / 480.0) * 18)

        cv2.rectangle(raw_heat, (80, 120), (220, 320), 45, -1)
        cv2.rectangle(raw_heat, (110, 150), (160, 200), 95, -1)

        hx1, hy1 = 180, 360
        cv2.ellipse(raw_heat, (hx1, hy1 - 50), (8, 12), 0, 0, 360, 240, -1)
        cv2.rectangle(raw_heat, (hx1 - 12, hy1 - 38), (hx1 + 12, hy1), 220, -1)
        cv2.line(raw_heat, (hx1 - 6, hy1), (hx1 - 8, hy1 + 35), 200, 5)
        cv2.line(raw_heat, (hx1 + 6, hy1), (hx1 + 8, hy1 + 35), 200, 5)

        hx2 = int(340 + 160 * np.sin(t * 0.7))
        hy2 = 380
        cv2.ellipse(raw_heat, (hx2, hy2 - 45), (7, 10), 0, 0, 360, 245, -1)
        cv2.rectangle(raw_heat, (hx2 - 10, hy2 - 35), (hx2 + 10, hy2), 225, -1)
        cv2.line(raw_heat, (hx2 - 5, hy2), (hx2 - 7, hy2 + 30), 205, 4)
        cv2.line(raw_heat, (hx2 + 5, hy2), (hx2 + 7, hy2 + 30), 205, 4)

        frame = cv2.applyColorMap(raw_heat, cv2.COLORMAP_INFERNO)

        cv2.drawMarker(frame, (hx1, hy1 - 25), (255, 255, 255), cv2.MARKER_CROSS, 24, 1)
        cv2.putText(frame, "SPOT: 37.1 C [HUMAN CORE]", (hx1 + 16, hy1 - 25), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 255), 1)

        for sy in range(120, 360):
            val = int(255 - ((sy - 120) / 240.0) * 230)
            cv2.line(frame, (600, sy), (618, sy), (val, val, val), 1)
        cv2.putText(frame, "42 C", (600, 112), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
        cv2.putText(frame, "18 C", (600, 375), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)

        cv2.putText(frame, f"[FLIR] {self.config.name.upper()}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        cv2.putText(frame, "COLORMAP: IRONBOW | NUC: CALIBRATED | EMISSIVITY: 0.95", (20, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (220, 240, 255), 1)
        return frame

    def _generate_biometric_frame(self, t: float) -> np.ndarray:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:, :] = (20, 24, 30)
        cv2.rectangle(frame, (30, 20), (610, 460), (45, 55, 70), 2)
        
        box_x, box_y, box_w, box_h = 220, 90, 200, 250
        cv2.rectangle(frame, (box_x, box_y), (box_x + box_w, box_y + box_h), (0, 255, 220), 2)
        
        cx, cy = box_x + box_w // 2, box_y + box_h // 2 - 10
        cv2.ellipse(frame, (cx, cy), (65, 85), 0, 0, 360, (0, 200, 180), 1)
        cv2.circle(frame, (cx - 24, cy - 18), 5, (0, 255, 200), -1)
        cv2.circle(frame, (cx + 24, cy - 18), 5, (0, 255, 200), -1)

        
        laser_y = int(box_y + (box_h) * ((np.sin(t * 3.0) + 1.0) / 2.0))
        cv2.line(frame, (box_x, laser_y), (box_x + box_w, laser_y), (0, 255, 255), 2)

        cv2.rectangle(frame, (40, 90), (205, 340), (28, 34, 44), -1)
        cv2.rectangle(frame, (40, 90), (205, 340), (0, 200, 160), 1)
        cv2.putText(frame, "BIOMETRIC PACS", (48, 115), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 200), 1)
        cv2.putText(frame, "ID: SEC-88412", (48, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 220, 240), 1)
        cv2.putText(frame, "NAME: CAPT. VERMA", (48, 175), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 220, 240), 1)
        cv2.putText(frame, "RANK: VIP LEVEL-4", (48, 205), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 220, 240), 1)
        cv2.putText(frame, "FACENET: 99.4%", (48, 235), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

        cv2.rectangle(frame, (45, 275), (200, 320), (0, 80, 40), -1)
        cv2.rectangle(frame, (45, 275), (200, 320), (0, 255, 100), 1)
        cv2.putText(frame, "ACCESS GRANTED", (54, 302), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 100), 2)

        cv2.putText(frame, f"[PACS] {self.config.name.upper()}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 200), 2)
        cv2.putText(frame, "RFID/NFC: CARD PRESENT | ANTI-TAILGATING: ARMED (0 DETECTED)", (20, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 200, 220), 1)
        return frame

    def _generate_barrier_frame(self, t: float) -> np.ndarray:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:, :] = (26, 28, 32)
        cv2.rectangle(frame, (80, 140), (560, 480), (22, 24, 28), -1)
        cv2.rectangle(frame, (460, 200), (540, 440), (220, 180, 0), -1)
        for hy in range(210, 440, 30):
            cv2.line(frame, (460, hy), (540, hy + 20), (20, 20, 20), 8)

        cycle = (t % 8.0)
        is_open = cycle > 4.0
        angle_deg = 65.0 if is_open else 0.0
        rad = np.radians(angle_deg)
        pivot_x, pivot_y = 470, 240
        length = 360
        arm_end_x = int(pivot_x - length * np.cos(rad))
        arm_end_y = int(pivot_y - length * np.sin(rad))
        
        arm_color = (0, 255, 100) if is_open else (0, 0, 255)
        cv2.line(frame, (pivot_x, pivot_y), (arm_end_x, arm_end_y), arm_color, 8)
        for d in range(40, length, 50):
            seg_x = int(pivot_x - d * np.cos(rad))
            seg_y = int(pivot_y - d * np.sin(rad))
            cv2.circle(frame, (seg_x, seg_y), 5, (255, 255, 255), -1)

        cv2.rectangle(frame, (160, 280), (420, 460), (45, 55, 75), -1)
        cv2.circle(frame, (200, 350), 12, (200, 240, 255), -1)
        cv2.circle(frame, (380, 350), 12, (200, 240, 255), -1)
        cv2.rectangle(frame, (240, 380), (340, 415), (240, 240, 240), -1)
        cv2.rectangle(frame, (240, 380), (340, 415), (10, 10, 10), 2)
        cv2.putText(frame, "KA 05 K 2252", (246, 403), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)

        cv2.rectangle(frame, (235, 375), (345, 420), (0, 255, 0), 2)
        cv2.putText(frame, "ANPR: KA 05 K 2252 [WHITELIST VIP]", (170, 370), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

        status_text = "BOOM: RAISED [VEHICLE CLEARED]" if is_open else "BOOM: ARMED [SCANNING PLATE]"
        status_bg = (0, 100, 40) if is_open else (0, 0, 120)
        cv2.rectangle(frame, (170, 430), (440, 465), status_bg, -1)
        cv2.putText(frame, status_text, (180, 452), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

        cv2.putText(frame, f"[GATE] {self.config.name.upper()}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 220, 255), 2)
        cv2.putText(frame, "INDUCTIVE SENSOR: ACTIVE (1850 KG) | 2FA RELAY: ENERGIZED", (20, 470), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (180, 200, 220), 1)
        return frame

    def _generate_sensor_frame(self, t: float) -> np.ndarray:
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:, :] = (16, 20, 25)
        cv2.rectangle(frame, (40, 120), (600, 340), (22, 28, 36), -1)
        cv2.rectangle(frame, (40, 120), (600, 340), (45, 60, 80), 1)
        for gy in range(140, 340, 40):
            cv2.line(frame, (40, gy), (600, gy), (30, 40, 50), 1)
        for gx in range(80, 600, 60):
            cv2.line(frame, (gx, 120), (gx, 340), (30, 40, 50), 1)

        pts_wave = []
        for x in range(40, 601, 4):
            freq1 = np.sin((x * 0.04) + t * 4.0)
            freq2 = 0.5 * np.cos((x * 0.08) - t * 2.5)
            y = int(230 + (freq1 + freq2) * 35)
            pts_wave.append([x, y])
        cv2.polylines(frame, [np.array(pts_wave, np.int32)], False, (0, 255, 180), 2)

        cv2.putText(frame, f"[PIDS] {self.config.name.upper()}", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 200), 2)
        for s in range(8):
            sx = 50 + s * 68
            cv2.rectangle(frame, (sx, 55), (sx + 60, 85), (0, 80, 40), -1)
            cv2.rectangle(frame, (sx, 55), (sx + 60, 85), (0, 255, 100), 1)
            cv2.putText(frame, f"S-0{s+1}", (sx + 14, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 100), 1)

        cv2.line(frame, (40, 370), (600, 370), (0, 100, 255), 2)
        cv2.putText(frame, "ACTIVE INFRARED TRIPWIRE BEAM: SECURE [0 FAULTS]", (40, 395), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 200, 255), 1)
        cv2.putText(frame, "STRAIN: 104.2 N | VIBRATION: 0.03g | ACOUSTIC FLOOR: -42.8 dB", (40, 425), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 210, 240), 1)
        cv2.putText(frame, "16/16 PIEZO SENSORS NOMINAL | ZERO INTRUSION ATTEMPTS", (20, 465), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 255, 180), 1)
        return frame

    def read_frame(self) -> FrameResult:
        """
        Returns the next frame respecting target_fps throttling.
        Never raises — always returns a FrameResult so the pipeline can keep
        running even if this one camera is having problems (graceful degradation).
        """
        now = time.time()

        if self.status != CameraStatus.ONLINE:
            self._try_reconnect()
            if self.status != CameraStatus.ONLINE:
                return FrameResult(frame=None, timestamp=now, ok=False, camera_id=self.config.camera_id)

        # throttle to target inference FPS regardless of source's native FPS
        if now - self._last_frame_time < self._min_frame_interval:
            time.sleep(max(0.0, self._min_frame_interval - (now - self._last_frame_time)))

        uri_clean = str(self.config.source_uri).strip().lower()
        # Only use synthetic generator for sensor/pids or if video cap is completely unavailable
        if (uri_clean in ("demo_sensor", "demo_pids") or "sensor" in uri_clean or "piezo" in uri_clean) or (
            (uri_clean.startswith("demo") or uri_clean in ("synthetic", "mock", "virtual"))
            and (self.cap is None or not self.cap.isOpened())
        ):
            frame = self._generate_synthetic_frame(uri_clean)
            self._consecutive_failures = 0
            self.last_heartbeat = time.time()
            self._last_frame_time = time.time()
        # Zero-delay seamless in-memory loop for recorded demo video files
        if getattr(self, "_cached_video_frames", None) and len(self._cached_video_frames) > 0:
            buf = self._cached_video_frames[self._cached_frame_idx]
            self._cached_frame_idx = (self._cached_frame_idx + 1) % len(self._cached_video_frames)
            frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)

            if self.rotation in (90, 180, 270):
                if self.rotation == 90:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif self.rotation == 180:
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                elif self.rotation == 270:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

            self.status = CameraStatus.ONLINE
            self._consecutive_failures = 0
            self.last_heartbeat = time.time()
            self._last_frame_time = time.time()
            return FrameResult(frame=frame, timestamp=time.time(), ok=True, camera_id=self.config.camera_id)

        if self.config.source_type == SourceType.FILE:
            ok, frame = self.cap.read() if self.cap else (False, None)
        else:
            with self._frame_lock:
                last_new_t = self._last_new_frame_time
                ok = getattr(self, '_latest_ok', False)
                frame = getattr(self, '_latest_frame', None)

            # Stall Watchdog: If reader thread hasn't received a fresh frame for > 6.0s, or thread died, mark dropped
            reader_alive = hasattr(self, '_reader_thread') and self._reader_thread and self._reader_thread.is_alive()
            if self.status == CameraStatus.ONLINE and ((now - last_new_t > 6.0 and last_new_t > 0) or not reader_alive):
                ok = False
                logger.warning(f"[{self.config.camera_id}] Stream stalled (no frame in {now - last_new_t:.1f}s, thread={reader_alive}). Triggering failure.")

        if not ok or frame is None:
            self._consecutive_failures += 1
            if self.config.source_type == SourceType.FILE and self.config.loop_file:
                # recorded video reached EOF -> loop back to start for a continuous 24/7 video demo
                if self.cap:
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    ok, frame = self.cap.read()
                # If seeking in-place failed (common with H.264 MP4 containers), reopen video source
                if not ok or frame is None:
                    source = self._resolve_source()
                    if self.cap:
                        try:
                            self.cap.release()
                        except Exception:
                            pass
                    self.cap = cv2.VideoCapture(source)
                    if self.cap and self.cap.isOpened():
                        ok, frame = self.cap.read()

                if ok and frame is not None:
                    self._consecutive_failures = 0
                    self.last_heartbeat = time.time()
                    self._last_frame_time = time.time()
                    # Keep up to 960px width so distant people/objects retain crisp details
                    if frame.shape[1] > 960:
                        h, w = frame.shape[:2]
                        frame = cv2.resize(frame, (960, int(h * 960.0 / w)))
                    return FrameResult(frame=frame, timestamp=time.time(), ok=True, camera_id=self.config.camera_id)

            if self._consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                logger.warning(f"[{self.config.camera_id}] marking OFFLINE after repeated read failures")
                self.status = CameraStatus.OFFLINE
            return FrameResult(frame=None, timestamp=time.time(), ok=False, camera_id=self.config.camera_id)

        # Apply rotation for file sources
        if self.config.source_type == SourceType.FILE and self.rotation in (90, 180, 270):
            if self.rotation == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif self.rotation == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            elif self.rotation == 270:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

        # Balance resolution: Keep up to 960px width so distant people/objects retain crisp details
        if frame.shape[1] > 960:
            h, w = frame.shape[:2]
            frame = cv2.resize(frame, (960, int(h * 960.0 / w)))

        self._consecutive_failures = 0
        self.last_heartbeat = time.time()
        self._last_frame_time = time.time()
        
        # Ensure we return a copy if from background thread so it doesn't get mutated
        ret_frame = frame.copy() if self.config.source_type != SourceType.FILE else frame
        
        return FrameResult(frame=ret_frame, timestamp=time.time(), ok=True, camera_id=self.config.camera_id)

    def get_status(self) -> dict:
        return {
            "camera_id": self.config.camera_id,
            "status": self.status.value,
            "last_heartbeat": self.last_heartbeat,
            "modality": getattr(self, "modality", SensorModality.VISIBLE_RGB).value,
            "rotation": self.rotation,
        }

    def get_health(self) -> dict:
        return {
            "camera_id": self.config.camera_id,
            "name": self.config.name,
            "status": self.status.value,
            "modality": getattr(self, "modality", SensorModality.VISIBLE_RGB).value,
            "source_type": self.config.source_type.value,
            "last_heartbeat": self.last_heartbeat,
            "consecutive_failures": self._consecutive_failures,
            "target_fps": self.config.target_fps,
            "reconnect_count": getattr(self, "_reconnect_count", 0),
            "dropped_frames": getattr(self, "_dropped_frames", 0),
            "total_frames_read": getattr(self, "_total_frames_read", 0),
        }

    def release(self):
        self._running = False
        if hasattr(self, '_reader_thread') and self._reader_thread and self._reader_thread.is_alive():
            if threading.current_thread() != self._reader_thread:
                self._reader_thread.join(timeout=1.0)
        self._reader_thread = None
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                pass
            self.cap = None


class RTSPSource(BaseVideoSource):
    """Concrete video source for IP cameras over RTSP/H.264 streams."""

    def __init__(self, config: CameraConfig):
        super().__init__(config)
        self._adapter = CameraAdapter(config)

    def open(self) -> bool:
        ok = self._adapter._connect()
        self.status = self._adapter.status
        self.last_heartbeat = self._adapter.last_heartbeat
        return ok

    def read_frame(self) -> FrameResult:
        res = self._adapter.read_frame()
        self.status = self._adapter.status
        self.last_heartbeat = self._adapter.last_heartbeat
        if res.ok:
            self.total_frames_read += 1
        else:
            self.dropped_frames += 1
        res.modality = self.modality
        return res

    def close(self) -> None:
        self._adapter.release()
        self.status = CameraStatus.OFFLINE


class WebcamSource(BaseVideoSource):
    """Concrete video source for USB / DirectShow / V4L2 webcams."""

    def __init__(self, config: CameraConfig):
        super().__init__(config)
        self._adapter = CameraAdapter(config)

    def open(self) -> bool:
        ok = self._adapter._connect()
        self.status = self._adapter.status
        self.last_heartbeat = self._adapter.last_heartbeat
        return ok

    def read_frame(self) -> FrameResult:
        res = self._adapter.read_frame()
        self.status = self._adapter.status
        self.last_heartbeat = self._adapter.last_heartbeat
        if res.ok:
            self.total_frames_read += 1
        else:
            self.dropped_frames += 1
        res.modality = self.modality
        return res

    def close(self) -> None:
        self._adapter.release()
        self.status = CameraStatus.OFFLINE


class FileSource(BaseVideoSource):
    """Concrete video source for disk video files with looping."""

    def __init__(self, config: CameraConfig):
        super().__init__(config)
        self._adapter = CameraAdapter(config)

    def open(self) -> bool:
        ok = self._adapter._connect()
        self.status = self._adapter.status
        self.last_heartbeat = self._adapter.last_heartbeat
        return ok

    def read_frame(self) -> FrameResult:
        res = self._adapter.read_frame()
        self.status = self._adapter.status
        self.last_heartbeat = self._adapter.last_heartbeat
        if res.ok:
            self.total_frames_read += 1
        else:
            self.dropped_frames += 1
        res.modality = self.modality
        return res

    def close(self) -> None:
        self._adapter.release()
        self.status = CameraStatus.OFFLINE


class SyntheticSensorSource(BaseVideoSource):
    """Concrete source for synthetic tactical feeds (drone, thermal, biometric, radar)."""

    def __init__(self, config: CameraConfig):
        super().__init__(config)
        self._adapter = CameraAdapter(config)

    def open(self) -> bool:
        ok = self._adapter._connect()
        self.status = self._adapter.status
        self.last_heartbeat = self._adapter.last_heartbeat
        return ok

    def read_frame(self) -> FrameResult:
        res = self._adapter.read_frame()
        self.status = self._adapter.status
        self.last_heartbeat = self._adapter.last_heartbeat
        if res.ok:
            self.total_frames_read += 1
        res.modality = self.modality
        return res

    def close(self) -> None:
        self._adapter.release()
        self.status = CameraStatus.OFFLINE


class FutureSensorSource(BaseVideoSource):
    """Interface stub for future hardware (e.g. Ground Radar, PIDS, UAV telem)."""

    def __init__(self, config: CameraConfig):
        super().__init__(config)
        self._adapter = CameraAdapter(config)

    def open(self) -> bool:
        self.status = CameraStatus.ONLINE
        self.last_heartbeat = time.time()
        return True

    def read_frame(self) -> FrameResult:
        res = self._adapter.read_frame()
        res.modality = self.modality
        return res

    def close(self) -> None:
        self.status = CameraStatus.OFFLINE


def create_video_source(config: CameraConfig) -> BaseVideoSource:
    """Factory creating the appropriate BaseVideoSource based on source_type."""
    st = config.source_type
    if st in (SourceType.RTSP, SourceType.ONVIF):
        return RTSPSource(config)
    elif st == SourceType.WEBCAM:
        return WebcamSource(config)
    elif st == SourceType.FILE:
        return FileSource(config)
    elif st == SourceType.SENSOR:
        return FutureSensorSource(config)
    else:
        return SyntheticSensorSource(config)

