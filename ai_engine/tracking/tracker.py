"""
TrackingEngine — converts raw YOLO+ByteTrack results into persistent
TrackedObject records, so downstream code sees "Person #17" continuously
across frames instead of a fresh anonymous detection every frame.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import numpy as np

from ai_engine.detection.detector import COCO_CLASS_MAP, BAG_LABELS, VEHICLE_LABELS, PLATE_SURFACE_LABELS, WEAPON_LABELS


@dataclass
class TrackedObject:
    track_id: int
    label: str
    confidence: float
    bbox: tuple  # (x1, y1, x2, y2)
    centroid: tuple  # (cx, cy)
    foot_point: tuple  # (cx, y2) — used for zone/ground-plane checks

    @property
    def is_person(self) -> bool:
        return self.label == "person"

    @property
    def is_bag(self) -> bool:
        return self.label in BAG_LABELS

    @property
    def is_vehicle(self) -> bool:
        return self.label in VEHICLE_LABELS

    @property
    def is_plate_candidate(self) -> bool:
        return self.label in VEHICLE_LABELS or self.label in PLATE_SURFACE_LABELS

    @property
    def is_weapon(self) -> bool:
        return self.label in WEAPON_LABELS

    @property
    def is_phone(self) -> bool:
        return self.label == "cell phone"


import math


class TrackingEngine:
    """
    Thin wrapper around YoloDetectionEngine.track() that normalizes output.
    Applies spatial deduplication to eliminate duplicate/split person tracks
    (e.g., upper-torso + full-body simultaneous detections of 1 person).
    """

    def extract(self, yolo_track_results) -> list[TrackedObject]:
        tracked: list[TrackedObject] = []
        if not yolo_track_results:
            return tracked

        r = yolo_track_results[0]
        if r.boxes is None or len(r.boxes) == 0:
            return tracked

        ids = r.boxes.id.cpu().numpy() if (r.boxes.id is not None) else None
        for i, box in enumerate(r.boxes):
            cls_id = int(box.cls[0])
            label = COCO_CLASS_MAP.get(cls_id)
            if label is None:
                continue
            conf = float(box.conf[0])
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
            bw = max(1.0, x2 - x1)
            bh = max(1.0, y2 - y1)

            # Person filtering:
            if label == "person":
                if conf < 0.20:
                    continue
                # Reject extreme non-human slivers (width > 3x height at low confidence)
                if bw > bh * 3.0 and conf < 0.60:
                    continue

            # Vehicle & bag filtering
            if label in VEHICLE_LABELS and conf < 0.20:
                continue
            if label in BAG_LABELS and conf < 0.25:
                continue

            cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
            foot_point = (cx, y2)  # bottom-center = where the object touches the ground

            track_id = int(ids[i]) if (ids is not None and i < len(ids)) else -(i + 1)
            tracked.append(TrackedObject(
                track_id=track_id,
                label=label,
                confidence=conf,
                bbox=(x1, y1, x2, y2),
                centroid=(cx, cy),
                foot_point=foot_point,
            ))

        return self._deduplicate_tracks(tracked)

    def _deduplicate_tracks(self, tracked: list[TrackedObject]) -> list[TrackedObject]:
        """
        Deduplicates overlapping person tracks so 1 human body is never tracked
        as multiple separate people.
        """
        if len(tracked) <= 1:
            return tracked

        persons = [obj for obj in tracked if obj.is_person]
        others = [obj for obj in tracked if not obj.is_person]

        if len(persons) <= 1:
            return tracked

        # Sort candidates: prioritize higher confidence, then larger bounding box area
        sorted_persons = sorted(
            persons,
            key=lambda o: (o.confidence, (o.bbox[2] - o.bbox[0]) * (o.bbox[3] - o.bbox[1])),
            reverse=True
        )

        deduped_persons: list[TrackedObject] = []
        for cand in sorted_persons:
            is_dup = False
            for accepted in deduped_persons:
                if self._are_same_person(cand, accepted):
                    is_dup = True
                    break
            if not is_dup:
                deduped_persons.append(cand)

        return deduped_persons + others

    def _are_same_person(self, p1: TrackedObject, p2: TrackedObject) -> bool:
        """Returns True if p1 and p2 represent duplicate boxes of the same physical person."""
        b1, b2 = p1.bbox, p2.bbox
        ix1 = max(b1[0], b2[0])
        iy1 = max(b1[1], b2[1])
        ix2 = min(b1[2], b2[2])
        iy2 = min(b1[3], b2[3])
        iw = max(0.0, ix2 - ix1)
        ih = max(0.0, iy2 - iy1)
        intersection = iw * ih

        area1 = max(1.0, (b1[2] - b1[0]) * (b1[3] - b1[1]))
        area2 = max(1.0, (b2[2] - b2[0]) * (b2[3] - b2[1]))
        min_area = min(area1, area2)
        union = area1 + area2 - intersection
        iou = intersection / max(1.0, union)
        containment = intersection / min_area

        # 1. High IoU (overlap > 60% = duplicate box on same person)
        if iou > 0.60:
            return True

        # 2. High containment (one box is almost entirely inside another, e.g. torso inside full body > 75%)
        if containment > 0.75:
            return True

        return False
