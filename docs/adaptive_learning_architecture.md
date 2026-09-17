# Project Garuda: Adaptive & Continual Self-Learning Architecture
**Specification & System Audit Document — Milestone 0**

---

## 1. Executive Summary & Audit Objective

Project Garuda is an enterprise-grade tactical surveillance and automated threat intelligence platform engineered for mission-critical installations (campuses, perimeters, military bases, high-security gates). 

This document provides the foundational engineering audit (**Milestone 0**) required before introducing staged self-learning capabilities. It establishes:
1. An exhaustive mapping of the existing inference, tracking, biometric, and event reasoning pipelines.
2. An analysis of hardware, CPU/GPU, threading, and latency boundaries.
3. The design of the proposed multi-stage adaptive learning architecture.
4. Non-invasive integration points that preserve strict real-time guarantees ($>20\text{ FPS}$) and prevent system crashes or self-reinforcing AI bias.

---

## 2. Existing System Architecture & Codebase Audit

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             PROJECT GARUDA ARCHITECTURE                          │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
 ┌───────────────────────────────────────┴───────────────────────────────────────┐
 │ Layer 1: Ingestion & Adapter (`ai_engine/pipeline/camera_adapter.py`)         │
 │ - OpenCV VideoCapture supporting RTSP, USB webcam, MP4 video loop             │
 │ - Automatic background reconnect thread (`_try_reconnect()`) with 5s backoff  │
 └───────────────────────────────────────┬───────────────────────────────────────┘
                                         │ Frame buffer (BGR np.ndarray)
 ┌───────────────────────────────────────┴───────────────────────────────────────┐
 │ Layer 2: Pre-Processing & Enhancement (`ai_engine/detection/`)                │
 │ - VisionEnhancer: Contrast CLAHE & Low-Light Night IR boost                  │
 │ - Sub-3ms Motion Trigger: Downscaled $160\times 120$ grayscale frame diff     │
 │ - ThermalEngine: Radiometric colormap pseudo-thermal signature extraction     │
 └───────────────────────────────────────┬───────────────────────────────────────┘
                                         │ Processed Frame
 ┌───────────────────────────────────────┴───────────────────────────────────────┐
 │ Layer 3: Perception & Inference (`ai_engine/detection/`, `tracking/`, `face/`)│
 │ - YoloDetectionEngine: Ultralytics YOLOv8n (COCO 80 classes, default 416x416) │
 │ - TrackingEngine: ByteTrack wrapper (`persist=True`) + spatial NMS de-dup     │
 │ - WeaponDetector: Secondary YOLOv8n fine-tuned for tactical threats (knife,   │
 │   pistol, rifle) at confidence $\ge 0.82$                                     │
 │ - FaceVerifier: dlib/face_recognition 128-d Euclidean embeddings with rank    │
 │ - PlateRecognizer: PaddleOCR/Tesseract ANPR with Levenshtein fuzzy matching   │
 └───────────────────────────────────────┬───────────────────────────────────────┘
                                         │ Tracked Objects & Detections
 ┌───────────────────────────────────────┴───────────────────────────────────────┐
 │ Layer 4: Spatial Context & Geometrical Reasoning (`ai_engine/zones/`)         │
 │ - ZoneEngine: Polygon Ray-Casting (Exclusion, Loitering, Perimeter, Gate)     │
 │ - AuthorizationEngine: 2FA validation, rank hierarchy, escort rules           │
 └───────────────────────────────────────┬───────────────────────────────────────┘
                                         │ Qualified Events
 ┌───────────────────────────────────────┴───────────────────────────────────────┐
 │ Layer 5: Temporal State Machines & Events (`ai_engine/events/event_engine.py`)│
 │ - State machines: Loitering (>Ts), Abandoned Object (distance + time),        │
 │   Perimeter intrusion, Crowd surge, Camera occlusion / tampering              │
 │ - AlertEngine (`pipeline/alert_engine.py`): In-memory deduplication, priority  │
 │   sorting, severity grading (GREEN, YELLOW, ORANGE, RED)                      │
 └───────────────────────────────────────┬───────────────────────────────────────┘
                                         │ Alert Dicts + Base64 Evidence
 ┌───────────────────────────────────────┴───────────────────────────────────────┐
 │ Layer 6: Backend & Integration (`backend/app/`)                               │
 │ - PipelineManager: Spawns 1 OS thread per CameraPipeline; bridges thread      │
 │   callbacks to asyncio event loop via `run_coroutine_threadsafe`              │
 │ - Database: Motor Async MongoDB (`events`, `alerts`, `learning_samples`, etc.)│
 │ - WebSockets: Central manager broadcasting live alerts & learning telemetry   │
 │ - Blockchain: SHA-256 evidence anchoring for legal chain-of-custody          │
 └───────────────────────────────────────┬───────────────────────────────────────┘
                                         │ JSON over WS & REST
 ┌───────────────────────────────────────┴───────────────────────────────────────┐
 │ Layer 7: Web Dashboard (`frontend/src/`)                                      │
 │ - React 18, TypeScript, TailwindCSS, Lucide Icons, Vite                        │
 │ - Views: Live Ops Grid, Tactical Radar, ANPR Gate, AI Learning Lab            │
 └───────────────────────────────────────────────────────────────────────────────┘
```

### Component Breakdown

| Module | Location | Current Role | Swappability / Integration Status |
| :--- | :--- | :--- | :--- |
| **Camera Ingestion** | `ai_engine/pipeline/camera_adapter.py` | RTSP/file frame acquisition, reconnection, FPS throttling | High: decoupled from AI logic |
| **Primary Detector** | `ai_engine/detection/detector.py` | YOLOv8n object detection (person, car, backpack, etc.) | High: implements `track()` & `detect()` |
| **Threat Detector** | `ai_engine/detection/weapon_detector.py` | Specialized threat model targeting concealed weapons | High: secondary inference stage |
| **Tracking Engine** | `ai_engine/tracking/tracker.py` | ByteTrack tracker + spatial duplicate suppression | Medium: tracker state tied to YOLO instance |
| **Threat Continuity** | `ai_engine/tracking/global_threat_registry.py` | Cross-camera entity re-identification | High: global in-memory registry |
| **Biometric Engine** | `ai_engine/face/face_verifier.py` | 128-d face embedding matching with rank titles | High: cosine/Euclidean distance threshold |
| **ANPR Engine** | `ai_engine/anpr/plate_recognizer.py` | License plate crop OCR + fuzzy regex watchlist | High: standalone OCR worker |
| **Zone Engine** | `ai_engine/zones/zone_engine.py` | Point-in-polygon ray casting for security sectors | High: pure geometry |
| **Event Engine** | `ai_engine/events/event_engine.py` | Deterministic state machine reasoning | High: stateful tracking |
| **Alert Engine** | `ai_engine/pipeline/alert_engine.py` | Severity classification & windowed de-duplication | High: event sinks |
| **Pipeline Manager** | `backend/app/services/pipeline_manager.py` | Thread coordinator, hot-reload, Mongo/WS bridge | Core integration hub |

---

## 3. Model Loading, Hot-Reloading & Hardware Constraints

### Current Model Loading Mechanism
1. **Model Instance per Camera**: In `backend/app/services/pipeline_manager.py`, each camera instantiates its own `YoloDetectionEngine` because Ultralytics YOLO ByteTrack tracker state (`persist=True`) is stored within the model object. Sharing one model instance across multiple streams corrupts tracking IDs.
2. **Dynamic Hot-Swapping**: `CameraPipeline.hot_swap_model(model_path)` atomically reloads the PyTorch model weights on the camera's thread while the capture loop continues, enabling zero-downtime weight updates.
3. **Hardware & Compute Constraints**:
   - **Default Device**: CPU (`YOLO_DEVICE="cpu"` in `backend/app/config.py`), with CUDA acceleration when available.
   - **Input Image Size**: $416 \times 416$ (`DETECTION_IMGSZ=416`), balancing speed ($12\text{--}25\text{ ms}$ on CPU) and small-object detection.
   - **Multi-Camera Priority Allocation**: The system allocates up to `MAX_AI_CAMERAS=12` in AI Core Mode ($25\text{ FPS}$) and demotes overflow cameras to Passthrough Standby ($3\text{ FPS}$, motion sentry only) to prevent CPU starvation.

---

## 4. Proposed Staged Self-Learning Architecture

The proposed self-learning system does **not** blindly retrain weights from unvalidated data. Instead, it operates across four decoupled architectural tiers:

```
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      TIER 1: REAL-TIME INFERENCE GATE                  │
 │  - Sub-millisecond Negative Exemplar Memory Bank (cosine matching)     │
 │  - 16x16 Spatial Bayesian Noise Prior per camera                       │
 │  - Zero inference overhead (<0.2 ms on CPU)                            │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      TIER 2: INTELLIGENT HARVESTING                    │
 │  - Shannon Entropy / Uncertainty window (0.28 - 0.58)                  │
 │  - Calibrated Laplacian quality gate (blur / dark frame rejection)     │
 │  - High-risk threat mining (weapons, unauthorized breaches)            │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      TIER 3: DATA FOUNDATION & MEMORY                  │
 │  - Versioned sample schema with 12 canonical attributes                │
 │  - Ground truth isolation: Unvalidated vs. Operator RLHF Validated    │
 │  - Camera-specific environmental baselines                             │
 └───────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
 ┌────────────────────────────────────────────────────────────────────────┐
 │                      TIER 4: CONTINUAL MODEL EVOLUTION                 │
 │  - Asynchronous background dataset builder & head fine-tuning          │
 │  - Catastrophic forgetting prevention (replay buffer on anchor test)   │
 │  - Automated regression evaluation gate & atomic rollback              │
 └────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Integration Points & Schema Foundation (Milestone 1 Preview)

### Integration Points in Existing Codebase
1. **Frame Ingestion Gate (`ai_engine/pipeline/pipeline.py`)**:
   - Call `AdaptiveNegativeFilter` right after `tracker.extract()` to filter out learned false positives before passing objects to the `EventEngine`.
   - Call `ActiveLearningHarvester.consider_detection()` on alternate frames with actual track duration to mine borderline samples without blocking the frame loop.
2. **Operator Correction Gate (`backend/app/api/learning_routes.py`)**:
   - Whenever an operator reviews an alert on the Dashboard, record a structured `FeedbackRecord` and update the `NegativeExemplar` bank or verified training pool.
3. **Model Hot-Swap Gate (`backend/app/services/pipeline_manager.py`)**:
   - `pipeline_manager.hot_reload_model()` safely coordinates zero-downtime swapping across all camera pipeline threads.

### Required Modules (To Be Built Across Milestones)
- `ai_engine/learning/data_foundation.py` (Milestone 1)
- `ai_engine/learning/active_learner.py` (Milestone 2)
- `ai_engine/learning/feedback_engine.py` (Milestone 3)
- `ai_engine/learning/camera_profile.py` (Milestone 4)
- `ai_engine/learning/self_supervised.py` (Milestone 5)
- `ai_engine/learning/novelty_detector.py` (Milestone 6)
- `ai_engine/learning/continual_trainer.py` (Milestone 7)
- `ai_engine/learning/forgetting_guard.py` (Milestone 8)
- `ai_engine/learning/evaluation_gate.py` (Milestone 9)
- `ai_engine/learning/multi_camera_learner.py` (Milestone 10)
- `ai_engine/learning/orchestrator.py` (Milestone 11)

---

## 6. Risk Analysis & Mitigation Strategies

| Risk | Consequence | Mitigation Strategy |
| :--- | :--- | :--- |
| **Self-Reinforcing Errors (AI Hallucination Loop)** | AI trains on its own incorrect pseudo-labels, degrading accuracy | Strict isolation: Unvalidated AI detections are flagged as `CANDIDATE_UNVERIFIED` and **never** enter training sets without human RLHF or multi-frame consensus |
| **Catastrophic Forgetting** | Model adapts to new camera conditions but forgets generic detection (e.g. stops detecting people) | Milestone 8: Anchor rehearsal dataset ($30\%$ baseline COCO/VOC images) mixed into every training batch; regression testing gate |
| **Thread Starvation & Video Lag** | Training loops consume CPU/GPU, dropping camera FPS below real-time | All training, dataset generation, and model evaluations run on independent background threads with OS nice/priority throttling |
| **Unbounded Disk Growth** | High-res camera frames fill server storage rapidly | Intelligent frame selection, strict Laplacian blur/exposure filters, spatial rate-limiting, and max buffer retention policies |
| **Model Degradation on Deployment** | A candidate model performs worse than the baseline in real operation | Milestone 9: Automated evaluation gatekeeper comparing mAP and false-alarm rates; instant atomic rollback to `v1.0.0` baseline |

---

## 7. Staged Implementation Plan (Milestones 1 to 14)

```
[Milestone 0: System Audit] ──> COMPLETE
            │
[Milestone 1: Learning Data & Memory Foundation]
  - Schemas: LearningSample, CameraProfile, LearningEvent, DatasetVersion, ModelVersion, FeedbackRecord
  - Storage & Retrieval API (Motor MongoDB collections)
            │
[Milestone 2: Confidence & Active Learning]
  - Shannon Entropy, uncertainty band filtering, spatial de-duplication, intelligent selection
            │
[Milestone 3: Human Feedback Loop (RLHF)]
  - Operator correction mapping, ground-truth isolation, dual-record storage
            │
[Milestone 4: Camera Environmental Adaptation]
  - Persistent camera profile: ambient noise, lighting baseline, sector sensitivity auto-tuning
            │
[Milestone 5: Self-Supervised Environment Learning]
  - Spatial-temporal representation learning from unlabeled video without pseudo-label bias
            │
[Milestone 6: Anomaly & Novelty Learning]
  - Trajectory, temporal, and spatial deviation scoring (NORMAL -> UNUSUAL -> REVIEW -> EVENT)
            │
[Milestone 7: Continual Learning Pipeline]
  - Versioned dataset builder, candidate fine-tuning engine, validation metric computation
            │
[Milestone 8: Catastrophic Forgetting Protection]
  - Replay memory buffer, historical benchmark preservation, knowledge retention checks
            │
[Milestone 9: Automated Model Evaluation & Rollback]
  - Evaluation gatekeeper, regression testing, deployment approval, atomic rollback
            │
[Milestone 10: Multi-Camera Learning]
  - Cross-camera trajectory learning, recurring routes, transition probability matrices
            │
[Milestone 11: Learning Orchestrator]
  - Central control panel coordinating all learning components
            │
[Milestone 12: Dashboard & Observability]
  - Real-time telemetry widgets, sample counts, model evolution timeline
            │
[Milestone 13: Performance & Production Hardening]
  - Stress testing, circuit breakers, asynchronous failure isolation
            │
[Milestone 14: Full End-to-End System Validation]
  - Complete verification across CCTV ingestion, active learning, evaluation, and hot-reload
```

---

## 8. Milestone 0 Sign-Off & Verification

- **Code Inspection Complete**: Repository structure, pipeline threading, models, databases, and UI components fully mapped.
- **Production Logic Preserved**: No disruptive modifications made during this audit phase.
- **Deliverable Created**: This document resides permanently at `docs/adaptive_learning_architecture.md`.
