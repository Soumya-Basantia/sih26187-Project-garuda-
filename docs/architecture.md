# GARUDE Architecture

## Layered design

```
Layer 1  Camera/Data Ingestion    ai_engine/pipeline/camera_adapter.py
Layer 2  Video Processing          (frame throttling, inside camera_adapter + pipeline)
Layer 3  AI/Computer Vision        ai_engine/detection/, ai_engine/tracking/, ai_engine/face/
Layer 4  Tracking + Event Intel    ai_engine/events/event_engine.py   <-- core differentiator
Layer 5  Alert/Decision Support    ai_engine/pipeline/alert_engine.py
Layer 6  Backend + Database        backend/app/  (FastAPI + MongoDB + WebSocket)
Layer 7  Web Dashboard             frontend/src/
```

## Why a rule-based event engine instead of an ML "suspicious activity" classifier

A model trained to directly output "suspicious/not suspicious" would require:
- A labeled dataset of real threat footage, which doesn't exist publicly at usable quality and can't ethically be created in a hackathon timeframe
- Would be a black box: no way to explain *why* an alert fired, which is a serious problem in a security context where false positives/negatives need to be investigated
- High risk of severe overfitting on whatever small dataset was scraped together

Instead, GARUDE separates the problem into layers that are each individually solvable with pretrained tools:
1. **Perception** (what's in the frame) — pretrained YOLO, genuinely AI, no training needed
2. **Persistence** (is this the same object over time) — ByteTrack, algorithmic tracking
3. **Context** (where is it, is it authorized) — deterministic zone geometry + identity lookup
4. **Reasoning** (does this sequence of facts constitute an event) — explicit IF/AND/THEN rules over accumulated state

Every alert GARUDE raises can be explained in one sentence, e.g.: *"Bag #4 stationary for 47s while its associated person, #17, moved more than 250px away."* That explainability is a design goal, not a limitation.

## Core abstractions (why each is swappable)

| Interface | Current implementation | Swap in later |
|---|---|---|
| `CameraAdapter` | OpenCV VideoCapture (RTSP/webcam/file) | GStreamer pipeline, hardware decoder |
| `ObjectDetectionEngine` | YOLOv8n (Ultralytics) | Any detector exposing `.detect(frame)` |
| `Tracker` | ByteTrack | DeepSORT, StrongSORT |
| `FaceVerifier` | face_recognition (dlib) | InsightFace, or a licensed commercial SDK |
| `EventRule` | Deterministic Python rules in `event_engine.py` | Learned behavior models, once real labeled data exists |

## Data flow for the abandoned-object scenario (concrete trace)

```
Frame N:   Person #17 detected, tracked. Backpack #4 detected, tracked, near #17.
           -> bag_engine.associate_bag_with_nearest_person(4, [state of #17])
           -> Bag #4.associated_person_track_id = 17

Frame N+k: Bag #4 foot_point unchanged for > STATIONARY_MOVEMENT_THRESHOLD_PX
           -> state.stationary_since = now

Frame N+m: Person #17's last_position is now > 250px from Bag #4's position
           AND (now - stationary_since) > 15s
           AND not already fired for this bag
           -> Event(ABANDONED_OBJECT, severity=HIGH) emitted
           -> AlertEngine dedupes/persists -> WebSocket broadcast -> Dashboard
```

## Graceful degradation, concretely

- **Camera drops**: `CameraAdapter._try_reconnect()` attempts reconnection every 5s without blocking other cameras (each camera runs on its own thread in `CameraPipeline`). Status flips to `OFFLINE`/`RECONNECTING` and is visible on the dashboard immediately.
- **AI processing error on one frame**: caught in `CameraPipeline._run_loop()`'s try/except — logs and continues to the next frame rather than killing the thread.
- **MongoDB temporarily down**: `pipeline_manager._persist_event/_persist_and_broadcast_alert` catch write failures and log them; the live pipeline (detection/tracking/events) keeps running in memory regardless, so no camera goes dark just because the DB write failed. (A full offline write-queue with retry is a natural next step beyond hackathon scope.)
