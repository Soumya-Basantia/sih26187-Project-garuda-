"""
ObjectDetectionEngine — abstraction over the detector so YOLO is a plug-in,
not the architecture. Swap in a different backend later by writing a new
class that implements `.detect(frame) -> list[Detection]`.

Uses Ultralytics YOLO (pretrained on COCO) — NO custom training required.
COCO classes we care about: person(0), bicycle(1), car(2), motorcycle(3),
bus(5), truck(7), backpack(24), handbag(26), suitcase(28).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
import numpy as np

# COCO class ids -> our internal semantic labels (Streamlined for presentation demo)
COCO_CLASS_MAP = {
    0: "person",
    1: "bicycle",
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
    24: "backpack",
    26: "handbag",
    28: "suitcase",
    43: "knife",
    67: "cell phone",
}

BAG_LABELS = {"backpack", "handbag", "suitcase"}
VEHICLE_LABELS = {"car", "motorcycle", "bus", "truck", "bicycle"}
PLATE_SURFACE_LABELS = {"cell phone", "phone"}
WEAPON_LABELS = {"knife", "gun", "firearm", "pistol", "rifle", "weapon"}


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: tuple  # (x1, y1, x2, y2) in pixel coords
    class_id: int


class ObjectDetectionEngine(Protocol):
    """Interface every detector backend must implement."""

    def detect(self, frame: np.ndarray) -> list[Detection]:
        ...


class YoloDetectionEngine:
    """
    Default detector backend for the hackathon prototype.
    Pretrained YOLOv8n on COCO — general object detector, zero custom training.
    Auto-detects GPU if available, and balances resolution for real-time FPS.
    """

    def __init__(self, model_path: str = "yolov8n.pt", confidence_threshold: float = 0.25,
                 imgsz: int = 640, device: str = "auto"):
        from ultralytics import YOLO  # imported lazily so the rest of the module
        if device == "auto" or device is None:
            try:
                import torch
                self.device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                self.device = "cpu"
        else:
            self.device = device

        self.model = YOLO(model_path)
        self.confidence_threshold = confidence_threshold
        self.imgsz = imgsz
        self.tracked_class_ids = set(COCO_CLASS_MAP.keys())

    def detect(self, frame: np.ndarray) -> list[Detection]:
        results = self.model.predict(
            frame,
            conf=self.confidence_threshold,
            imgsz=self.imgsz,
            classes=list(self.tracked_class_ids),
            device=self.device,
            verbose=False,
        )
        detections: list[Detection] = []
        if not results:
            return detections

        r = results[0]
        if r.boxes is None:
            return detections

        for box in r.boxes:
            cls_id = int(box.cls[0])
            label = COCO_CLASS_MAP.get(cls_id)
            if label is None:
                continue
            conf = float(box.conf[0])
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
            detections.append(Detection(
                label=label,
                confidence=conf,
                bbox=(x1, y1, x2, y2),
                class_id=cls_id,
            ))
        return detections

    def track(self, frame: np.ndarray):
        """
        Detection + tracking in one call via Ultralytics' built-in ByteTrack
        integration with high-resolution imgsz=960 for distant targets.
        Strict iou=0.40 suppresses duplicate overlapping boxes for the same entity.
        """
        return self.model.track(
            frame,
            conf=self.confidence_threshold,
            iou=0.40,
            imgsz=self.imgsz,
            classes=list(self.tracked_class_ids),
            device=self.device,
            persist=True,
            tracker="bytetrack.yaml",
            verbose=False,
        )

    def hot_swap_model(self, model_path: str):
        """Loads updated or fine-tuned model weights with zero downtime."""
        from ultralytics import YOLO
        self.model = YOLO(model_path)
