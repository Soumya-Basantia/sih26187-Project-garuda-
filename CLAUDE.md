# CLAUDE.md — Instructions for AI Assistants on this Repository

You are working on **Project Garuda** (AI-Based Intelligent Video Analytics Platform for Border Surveillance), built for **Smart India Hackathon 2026 Problem Statement SIH26187** (Sponsor: Ministry of Home Affairs).

Read this file and `BUILD_STATUS.md` fully before performing any tasks.

---

## What this Project Is

An AI-driven video analytics platform that turns existing CCTV cameras (RTSP CCTV, phone-as-webcam, or recorded video) into an intelligent situational-awareness system for **Border Outposts (BOPs), checkposts, and zero-line buffer zones**.

The differentiator is **not** raw YOLO detection. It is a **deterministic, explainable temporal event engine** that reasons over tracked entities across time using 4 human activity categories and virtual security zones:
- **Category 1 (Movement & Presence):** Loitering, wandering / erratic trajectory, repeated perimeter approach / reconnaissance, after-hours presence.
- **Category 2 (Observation & Interaction):** Group convergence, gathering near perimeter boundaries.
- **Category 3 (Human + Object Interaction):** Carrying, object left unattended (`YELLOW`), and high-priority abandoned object (`RED`).
- **Category 4 (Security & Administrative):** Perimeter buffer and zero-line intrusions (`RED`).

---

## Current Build & Execution Status

| Component | Location | Status | Notes |
| :--- | :--- | :---: | :--- |
| **Camera Ingestion** | `ai_engine/pipeline/camera_adapter.py` | ✅ Working | RTSP, webcam (`0`), video files; auto-reconnects every 5s |
| **YOLOv8 Detection** | `ai_engine/detection/detector.py` | ✅ Working | Pretrained COCO model (`yolov8n.pt` in `backend/`) |
| **Multi-Object Tracking** | `ai_engine/tracking/tracker.py` | ✅ Working | ByteTrack Kalman filter tracking |
| **Zone Engine** | `ai_engine/zones/zone_engine.py` | ✅ Working | Polygon geometry, `distance_to_point()` metric, 4 zone tiers |
| **Temporal Event Engine** | `ai_engine/events/event_engine.py` | ✅ Working | All 4 MHA categories active; tested via `scratch/test_event_engine.py` |
| **Alert Engine** | `ai_engine/pipeline/alert_engine.py` | ✅ Working | 4-level severity (`GREEN`, `YELLOW`, `ORANGE`, `RED`), deduplication |
| **Pipeline Manager** | `backend/app/services/pipeline_manager.py` | ✅ Working | Thread-isolated per-camera loop with async WebSocket bridge |
| **FastAPI Backend** | `backend/app/` | ✅ Working | Auth, cameras, zones, alerts, WebSocket; mock DB layer active |
| **React Dashboard** | `frontend/src/` | ✅ Working | Vite + TS; surveillance grid, activity monitor, alert modal |
| **ANPR (License Plates)**| `ai_engine/anpr/` | ⏳ Deferred | Scaffolded empty directory (Priority 3) |

---

## Operating Commands (Windows / PowerShell)

```powershell
# 1. Run Backend Server
cd backend
.\venv\Scripts\uvicorn.exe app.main:app --host 127.0.0.1 --port 8000
# URL: http://127.0.0.1:8000 | Swagger Docs: http://127.0.0.1:8000/docs
# Default Admin: admin / admin

# 2. Run Frontend Dashboard
cd frontend
npm run dev
# URL: http://localhost:5173

# 3. Run Event Engine Automated Tests
.\backend\venv\Scripts\python.exe C:\Users\SOUMYA.B\.gemini\antigravity-ide\brain\950e6db5-d91e-4ba8-ad04-1f18f4b3c7ad\scratch\test_event_engine.py
```

---

## High-Impact Suggestions & Next Features to Implement

If continuing development on this repository, prioritize these five high-value additions to achieve a top-tier hackathon score:

1. **Ground-Plane Homography Calibration:**
   - Add a 4-point perspective transform in `ZoneEditor.tsx` and `zone_engine.py` using `cv2.getPerspectiveTransform()`.
   - Converts 2D pixel coordinates to real-world ground meters so alerts display: *"Owner moved **18.4 meters** away"*.
2. **Tri-Frame Evidence Capture:**
   - In `alert_engine.py` / `pipeline.py`, save a 3-frame carousel for abandoned objects:
     - $T_0$: Owner carrying/arriving with the object.
     - $T_1$: Object placed on the ground.
     - $T_2$: Owner departed and object unattended.
3. **Dual-FPS Inference Optimization:**
   - Decouple ingestion (25 FPS) from YOLO detection (5–6 FPS) with ByteTrack interpolating boxes to minimize edge compute load.
   - Export YOLOv8 to OpenVINO / ONNX for high-speed CPU inference.
4. **One-Click SOP Action Dispatch:**
   - Add operator buttons in the alert detail modal: `[🚨 Dispatch Patrol]` (trigger Telegram/SMS webhook) and `[📄 Export Incident PDF]`.
5. **Pre-configured Demo Scenarios:**
   - Populate `demo/videos/` with border scenario clips and add a quick-switch dropdown in the UI.

---

## Ground Rules for AI Assistants

- **Do not replace the rule-based event engine with a black-box model.** Explainability is the core requirement of MHA SIH26187.
- **Keep `ai_engine/` decoupled from `backend/`.** The backend imports from `ai_engine`, never the reverse.
- **Preserve graceful degradation.** Single camera drops or database write issues must never crash other camera threads.
