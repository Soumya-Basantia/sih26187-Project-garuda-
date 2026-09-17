# 📖 Project Garuda — Comprehensive Instruction Guide

Welcome to **Project Garuda** (Adaptive Edge Video Intelligence Platform). This document provides complete, step-by-step instructions on installation, service management, user operations, feature testing, and troubleshooting.

---

## 📑 Table of Contents
1. [Quick Launch (The Easiest Way)](#1-quick-launch-the-easiest-way)
2. [First-Time Automated Setup](#2-first-time-automated-setup)
3. [Manual Step-by-Step Setup](#3-manual-step-by-step-setup)
4. [Operator Login & Credentials](#4-operator-login--credentials)
5. [Connecting Cameras (Webcam, RTSP, Video Files)](#5-connecting-cameras-webcam-rtsp-video-files)
6. [Testing Core Surveillance Features](#6-testing-core-surveillance-features)
   - [Virtual Security Zones & Homography](#a-virtual-security-zones--homography)
   - [Abandoned Object Detection](#b-abandoned-object-detection)
   - [Contextual Weapon Detection](#c-contextual-weapon-threat-detection)
   - [Automated License Plate Recognition (ANPR)](#d-automated-license-plate-recognition-anpr)
   - [Facial Verification & Identity Management](#e-facial-verification--identity-management)
   - [Tactical Radar & Threat Map](#f-tactical-radar--threat-map)
   - [Blockchain Audit Vault & Cyber Breach Defense](#g-blockchain-audit-vault--cyber-breach-defense)
7. [Service Management & Shutdown](#7-service-management--shutdown)
8. [Automated Diagnostic Tests](#8-automated-diagnostic-tests)
9. [Troubleshooting & FAQ](#9-troubleshooting--faq)

---

## 1. Quick Launch (The Easiest Way)

We have provided clean Windows management scripts in the root directory:

* **To start the entire platform with one double-click:**
  👉 Double-click **`start.bat`** (or execute `.\start.bat` in PowerShell/CMD)
  * Starts Backend API on port `8000`.
  * Starts Frontend Dashboard on port `5173`.
  * Automatically opens your default browser to `http://localhost:5173/login`.

* **To stop all running services cleanly:**
  👉 Double-click **`stop.bat`** (or execute `.\stop.bat`)
  * Gracefully closes ports `8000`, `5173`, and any background workers without leaving orphan processes.

* **To access the Interactive Management Console:**
  👉 Double-click **`manage.bat`**
  * Provides a menu to start, stop, seed data, run diagnostics, run tests, or prepare GitHub deployments.

---

## 2. First-Time Automated Setup

If this is a fresh clone on a new machine:

1. Ensure **Python 3.10+**, **Node.js 18+**, and **MongoDB** are installed (see [REQUIRED_SOFTWARE.md](file:///REQUIRED_SOFTWARE.md)).
2. Double-click **`setup.bat`** (or run `.\setup.bat`).
3. The script will automatically:
   - Create the Python virtual environment (`backend/venv`).
   - Install all Python packages from `backend/requirements.txt`.
   - Create your local `.env` configuration file from `.env.example`.
   - Install frontend Node dependencies (`npm install`).
   - Seed the database with default administrator accounts and sample personnel.

---

## 3. Manual Step-by-Step Setup

If you prefer running services manually across two terminal windows:

### Terminal 1: Backend Server (FastAPI)
```powershell
cd "c:\Users\SOUMYA.B\Documents\project files\project garuda\backend"

# Activate virtual environment
.\venv\Scripts\activate

# (Optional: install requirements if not already done)
pip install -r requirements.txt

# Run initial seed script
python seed.py

# Start uvicorn server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
* **API Documentation (Swagger UI):** [http://localhost:8000/docs](http://localhost:8000/docs)
* **System Health Check:** [http://localhost:8000/api/system/health](http://localhost:8000/api/system/health)

### Terminal 2: Frontend Dashboard (Vite + React)
```powershell
cd "c:\Users\SOUMYA.B\Documents\project files\project garuda\frontend"

# (Optional: install packages if not already done)
npm install

# Start Vite development server
npm run dev
```
* **Web Surveillance Portal:** [http://localhost:5173](http://localhost:5173)

---

## 4. Operator Login & Credentials

When navigating to `http://localhost:5173/login`, use the pre-configured operator credentials:

| Role | Username | Password | Access Level |
| :--- | :--- | :--- | :--- |
| **Command Officer / Admin** | `admin` | `admin` | Full Administrative & System Configuration |
| **Field Operator** | `operator` | `operator123` | Surveillance Grid, Radar & Alert Dispatch |
| **Security Analyst** | `analyst` | `analyst123` | Event History, Blockchain Vault & Reports |

---

## 5. Connecting Cameras (Webcam, RTSP, Video Files)

Project Garuda ingests video through its unified `CameraAdapter` engine:

1. In the sidebar, navigate to **Camera Management** (`/cameras`).
2. Click **+ Add Camera** button.
3. Configure the source:
   * **Local USB Webcam / Laptop Camera:**
     - Name: `BOP Gate Cam 01`
     - Source Type: `webcam`
     - Source URI: `0` (or `1` if using an external USB cam)
   * **Recorded Video Clip (for demos / testing):**
     - Name: `Perimeter Test Clip`
     - Source Type: `file`
     - Source URI: `demo/videos/test_perimeter.mp4` (or absolute path)
   * **Live RTSP CCTV Network Camera:**
     - Name: `Zero-Line North Turret`
     - Source Type: `rtsp`
     - Source URI: `rtsp://admin:password@192.168.1.108:554/h264Preview_01_main`
4. Click **Save & Activate**. The stream will initialize and start streaming detections via WebSocket.

---

## 6. Testing Core Surveillance Features

### A. Virtual Security Zones & Homography
1. Navigate to **Zone Editor** (`/zones`).
2. Select your active camera feed.
3. Click **Add Zone** and choose a security tier:
   - 🟩 **Buffer Zone:** Early perimeter warning.
   - 🟨 **Restricted Patrol Zone:** Personnel must have valid authorization.
   - 🟥 **Zero-Line Exclusion Zone:** Strict non-entry buffer; triggers immediate `CRITICAL` alarm.
4. Click points on the video canvas to draw the boundary polygon.
5. Save the zone. When any person or vehicle intersects the boundary, an alert fires instantly.

### B. Abandoned Object Detection
1. Position an object (backpack, briefcase, box) in the camera field of view.
2. An individual places the bag and walks away.
3. Once the person moves beyond the proximity threshold for >10–15 seconds:
   - An alert transitions from `UNATTENDED_OBJECT` (Yellow) to `HIGH_PRIORITY_ABANDONED_OBJECT` (Red).
   - Tri-frame evidentiary timeline captures owner drop-off and departure.

### C. Contextual Weapon Threat Detection
1. Garuda uses **Person-ROI Contextual Gating** to eliminate false alarms from inanimate objects.
2. Threats (knives, firearms) are only flagged if correlated with a human bounding box and aggressive pose kinematics.

### D. Automated License Plate Recognition (ANPR)
1. Navigate to **Identities** or **Vehicle Monitoring**.
2. When vehicles enter the frame, Garuda crops the plate, performs perspective rectification, and extracts alphanumeric characters with OCR confusion correction (`8↔B`, `0↔O`, `1↔I`).

### E. Facial Verification & Identity Management
1. Navigate to **Identities** (`/identities`).
2. Click **Enroll Face** and upload an authorized personnel photo with their Service ID and Security Clearance.
3. When the person appears on camera, they are verified with a 128-dim biometric embedding.
4. Unrecognized individuals in restricted zones generate an `UNAUTHORIZED_INDIVIDUAL` incident.

### F. Tactical Radar & Threat Map
1. Navigate to **Tactical Radar** (`/radar`).
2. Displays an interactive aerial view of camera nodes, security sectors, and active track trajectories.
3. Real-time threat vectors show approaching targets, loitering clusters, and cross-camera handover paths.

### G. Blockchain Audit Vault & Cyber Breach Defense
1. Navigate to **Blockchain Vault** (`/blockchain`).
2. Every incident, snapshot hash, and operator dispatch is permanently recorded in a cryptographically linked SHA-256 evidence chain for legal and military court admissibility.
3. Navigate to **Cybersecurity Hub** (`/cybersecurity`) to monitor network port intrusion attempts, DDoS protection, and tamper-proof log verification.

---

## 7. Service Management & Shutdown

### Graceful Stopping
To stop all Project Garuda background servers cleanly without lingering processes:
* Double-click **`stop.bat`**
* Or run in PowerShell:
  ```powershell
  .\stop.bat
  ```

### Checking Active Services
Run `manage.bat` and select Option **[4] Verify Pre-flight Diagnostics & Port Availability** to inspect whether backend, frontend, and database services are healthy.

---

## 8. Automated Diagnostic Tests

Garuda includes 21 comprehensive test suites covering foundation architecture, active learning, zone engines, and pipeline stability:

```powershell
# Run all 21 test suites
.\backend\venv\Scripts\python.exe tests\run_all_tests.py
```
Expected Result:
```
======================================================================
TEST EXECUTION SUMMARY (21 / 21 SUITES PASSED — 100% SUCCESS)
======================================================================
```

---

## 9. Troubleshooting & FAQ

### Q1: MongoDB fails to connect or throws `ServerSelectionTimeoutError`
* **Fix:** Verify MongoDB is running:
  ```powershell
  net start MongoDB
  ```
  Or check that your connection URI in `.env` (`MONGO_URI=mongodb://localhost:27017`) is correct.

### Q2: Port 8000 or Port 5173 is already in use
* **Fix:** Run `stop.bat` to kill any hanging uvicorn or vite processes.
* Alternatively, identify and terminate the process:
  ```powershell
  # Find PID on port 8000:
  Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
  # Kill PID:
  Stop-Process -Id <PID> -Force
  ```

### Q3: Webcam feed fails to load (`source_uri=0`)
* **Fix:**
  1. Ensure no other application (Zoom, Teams, Camera App) is currently holding exclusive lock on the webcam.
  2. If using an external USB camera, change `source_uri` to `1` or `2` in Camera Management.
  3. Verify Windows Privacy settings allow desktop apps to access your camera.

### Q4: YOLO weights are missing
* **Fix:** The ultralytics engine automatically downloads `yolov8n.pt` on first boot. Pre-downloaded weights (`yolov8n.pt`, `yolov8s.pt`, `yolov8n-pose.pt`) are also already located in `backend/`.
