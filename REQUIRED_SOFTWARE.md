# 🛠️ Project Garuda — Required Software & System Requirements

This document outlines all prerequisite software, runtimes, drivers, and libraries required to run, develop, and deploy the **Project Garuda Adaptive Edge Video Intelligence Platform**.

---

## 1. System Requirements & Hardware

| Specification | Minimum Required | Recommended (Production / Multi-Stream) |
| :--- | :--- | :--- |
| **Operating System** | Windows 10/11 (64-bit) or Ubuntu 20.04/22.04 LTS | Windows 11 Pro or Ubuntu 22.04 LTS |
| **Processor (CPU)** | Intel Core i5 (8th Gen+) or AMD Ryzen 5 | Intel Core i7/i9 (11th Gen+) or AMD Ryzen 7/9 |
| **Memory (RAM)** | 8 GB RAM | 16 GB+ DDR4 / DDR5 RAM |
| **Disk Storage** | 5 GB free SSD space | 20 GB+ NVMe SSD |
| **GPU (Optional)** | Integrated Intel Iris Xe / AMD Radeon (CPU Mode) | NVIDIA RTX 3060 / 4060 or higher (CUDA 12.x) |
| **Camera Feeds** | Integrated USB Webcam or sample `.mp4` video files | RTSP IP CCTV Streams / ONVIF Network Cameras |

> **Edge Optimization Note:** Project Garuda is engineered with an ultra-efficient runtime envelope (<250MB baseline RAM footprint) and achieves **30–35 FPS** real-time inference even on modern CPU-only environments.

---

## 2. Core Required Software

Ensure the following tools are installed on your machine and accessible in your system `PATH`:

### A. Python (Backend & AI Engine)
* **Version:** **Python 3.10, 3.11, or 3.12** (64-bit)
* **Download:** [https://www.python.org/downloads/](https://www.python.org/downloads/)
* **Important on Windows:** During installation, check the box:  
  ☑ **"Add Python to PATH"**
* **Verification:**
  ```powershell
  python --version
  pip --version
  ```

### B. Node.js & npm (Frontend Surveillance Console)
* **Version:** **Node.js 18.x, 20.x, or 22.x LTS**
* **Download:** [https://nodejs.org/](https://nodejs.org/)
* **Verification:**
  ```powershell
  node -v
  npm -v
  ```

### C. MongoDB Database Server
* **Version:** **MongoDB Community Server 6.0+ or 7.0+**
* **Download:** [https://www.mongodb.com/try/download/community](https://www.mongodb.com/try/download/community)
* **Installation Tip:** Install MongoDB as a Windows Service (default port `27017`) and optionally install **MongoDB Compass** for a visual GUI.
* **Alternative (Cloud):** You can also use a free cloud cluster on [MongoDB Atlas](https://www.mongodb.com/atlas) by updating `MONGO_URI` in `.env`.
* **Verification:**
  ```powershell
  mongod --version
  ```

### D. Git Version Control
* **Version:** **Git 2.30+**
* **Download:** [https://git-scm.com/downloads](https://git-scm.com/downloads)
* **Verification:**
  ```powershell
  git --version
  ```

### E. Microsoft Visual C++ Redistributable (Windows Only)
* Required by OpenCV, PyTorch, and NumPy on Windows.
* **Download:** [Microsoft VC++ 2015-2022 Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)

---

## 3. Python Package Ecosystem (`backend/requirements.txt`)

These packages are installed automatically inside the backend virtual environment:

| Package | Version | Purpose |
| :--- | :--- | :--- |
| **`fastapi`** | `^0.115.0` | High-throughput asynchronous REST API & WebSocket server |
| **`uvicorn[standard]`**| `^0.30.6` | Lightning-fast ASGI web server |
| **`motor`** | `^3.6.0` | Asynchronous MongoDB driver for Python |
| **`pydantic`** | `^2.9.2` | Data validation, schema modeling, and type enforcement |
| **`python-dotenv`** | `^1.0.1` | Environment variable management (`.env`) |
| **`pyjwt`** | `^2.9.0` | Secure JSON Web Token authentication for operators |
| **`passlib[bcrypt]`** | `^1.7.4` | Enterprise password hashing with Bcrypt |
| **`python-multipart`**| `^0.0.12`| Form data and file upload parsing |
| **`ultralytics`** | `^8.3.0` | YOLOv8 object detection, pose estimation & tracking |
| **`opencv-python`** | `^4.10.0` | Real-time computer vision, video capture & drawing |
| **`numpy`** | `^1.26.4` | High-performance tensor & matrix computations |
| **`easyocr`** | `^1.7.2` | Automated License Plate Recognition (ANPR) OCR |

---

## 4. Frontend Technology Stack (`frontend/package.json`)

The operator interface is built on modern web standards:

| Technology | Purpose |
| :--- | :--- |
| **React 18** | High-performance declarative component UI |
| **TypeScript** | Strict compile-time type safety across all API contracts |
| **Vite** | Ultra-fast HMR bundler and development server |
| **Tailwind CSS** | Tactical dark-mode theme, glassmorphism, and responsive styling |
| **Lucide React** | Tactical surveillance & security iconography |
| **HTML5 Canvas / SVG**| Low-latency radar map, live polygon zone drawing & homography |

---

## 5. Network Ports & Firewall Allocations

Before starting Project Garuda, verify that these default local ports are available:

| Port | Service | Description |
| :--- | :--- | :--- |
| **`8000`** | **Backend API** | FastAPI HTTP REST endpoints, WebSocket camera streams & `/docs` |
| **`5173`** | **Frontend UI** | Main Garuda Tactical Command & Operator Portal |
| **`27017`**| **Database** | Local MongoDB Community Server |
| **`4173`**| **God's Eye** | (Optional) 3D Geospatial Console (`gods-eye-view`) |

---

## 6. Pre-Flight Verification Checklist

Run these commands in PowerShell or Terminal to verify your setup:

```powershell
# 1. Check Python
python --version
# Expected: Python 3.10.x, 3.11.x, or 3.12.x

# 2. Check Node & npm
node -v
npm -v
# Expected: v18+, v20+, or v22+

# 3. Check MongoDB service status (Windows)
sc query MongoDB
# Expected: STATE : 4 RUNNING

# 4. Check Git
git --version
# Expected: git version 2.x.x
```
