# 🚀 Quick Start — Project Garuda

Get Project Garuda up and running in less than 2 minutes.

---

## ⚡ Option 1: One-Click Windows Launch (Recommended)

1. **First-Time Setup (run once):**
   * Double-click **`setup.bat`**  
     *(Creates Python virtual environment, installs backend and frontend packages, copies `.env`, and seeds the admin user)*

2. **Start the Platform:**
   * Double-click **`start.bat`**  
     *(Starts FastAPI Backend on port 8000, Vite Frontend on port 5173, and launches `http://localhost:5173/login` in your browser)*

3. **Stop All Services:**
   * Double-click **`stop.bat`** to safely terminate all background servers.

---

## 💻 Option 2: Windows Management Console

Double-click **`manage.bat`** to access the interactive operations menu:
* `[1]` Start Platform (Backend + Frontend)
* `[2]` Start Full Tri-Portal (including God's Eye View)
* `[3]` Stop All Services
* `[4]` Run Setup & Install Dependencies
* `[5]` Pre-flight Diagnostics & Port Check
* `[6]` Seed Database
* `[7]` Run Full 21 Test Suites
* `[8]` GitHub Deployment Helper

---

## 🐧 Option 3: Linux / macOS / WSL

```bash
# Make executable and run
chmod +x start.sh
./start.sh
```

---

## 🔑 Access Credentials & Endpoints

| Portal | URL | Credentials |
| :--- | :--- | :--- |
| **Command Center** | [http://localhost:5173/login](http://localhost:5173/login) | **User:** `admin` \| **Pass:** `admin` |
| **REST API & Swagger Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | OpenAPI interactive documentation |
| **System Health Endpoint** | [http://localhost:8000/api/system/health](http://localhost:8000/api/system/health) | Real-time JSON health telemetry |

---

## 📹 Quick Camera Test

1. Log in to the dashboard → Navigate to **Camera Management** → Click **+ Add Camera**.
2. **For Laptop / USB Webcam:**
   - Source Type: `webcam`
   - Source URI: `0`
3. **For Video File:**
   - Source Type: `file`
   - Source URI: `demo/videos/test_perimeter.mp4` (or any `.mp4` file on your drive)
4. Click **Save & Activate** to start live real-time detection at 35 FPS!

---

## 📚 Complete Guides

* For comprehensive operations & testing: see [INSTRUCTIONS.md](file:///INSTRUCTIONS.md)
* For system requirements & dependencies: see [REQUIRED_SOFTWARE.md](file:///REQUIRED_SOFTWARE.md)
* For pushing to GitHub: see the [GitHub Deployment Section in README.md](file:///README.md#-how-to-push-project-garuda-to-your-own-github)
