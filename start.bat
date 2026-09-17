@echo off
setlocal enabledelayedexpansion
title Project Garuda - Launcher
color 0B

echo.
echo  =============================================================
echo    PROJECT GARUDA - Adaptive Edge Video Intelligence Platform
echo  =============================================================
echo.

:: 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] ERROR: Python is not detected in your PATH.
    echo     Please install Python 3.10+ from https://www.python.org/
    echo     Ensure you check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

:: 2. Check Node.js
node -v >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] ERROR: Node.js is not detected in your PATH.
    echo     Please install Node.js 18+ from https://nodejs.org/
    echo.
    pause
    exit /b 1
)

:: 3. Check / Start MongoDB Service (if installed as a Windows service)
echo [*] Checking Database Service (MongoDB)...
sc query MongoDB >nul 2>&1
if %errorlevel% equ 0 (
    sc query MongoDB | find "RUNNING" >nul 2>&1
    if %errorlevel% neq 0 (
        echo     Attempting to start MongoDB service...
        net start MongoDB >nul 2>&1
        if %errorlevel% equ 0 (
            echo     [+] MongoDB service started successfully.
        ) else (
            echo     [!] Notice: Could not start MongoDB service automatically.
            echo         If using a remote/Atlas URI or manual mongod, ignore this.
        )
    ) else (
        echo     [+] MongoDB service is running.
    )
) else (
    echo     [*] Local MongoDB Windows Service not found.
    echo         Ensure MongoDB is running locally or configured via .env MONGO_URI.
)

:: 4. Verify Virtual Environment
if not exist "%~dp0backend\venv\Scripts\activate.bat" (
    echo.
    echo [*] Python virtual environment not found in backend\venv.
    echo     Running automated setup first...
    call "%~dp0setup.bat"
    if %errorlevel% neq 0 (
        echo [!] Setup encountered an error. Please review output above.
        pause
        exit /b 1
    )
)

:: 5. Verify .env file
if not exist "%~dp0.env" (
    if exist "%~dp0.env.example" (
        copy "%~dp0.env.example" "%~dp0.env" >nul
        echo     [+] Created .env file from .env.example
    )
)

:: 6. Start Backend Service (FastAPI)
echo.
echo [*] Starting Backend Server (FastAPI on http://127.0.0.1:8000)...
start "Project Garuda - Backend" /min cmd /c "cd /d "%~dp0backend" && call .\venv\Scripts\activate && uvicorn app.main:app --host 0.0.0.0 --port 8000"

:: 7. Start Frontend Service (React + Vite)
echo [*] Starting Frontend Console (Vite on http://localhost:5173)...
start "Project Garuda - Frontend" /min cmd /c "cd /d "%~dp0frontend" && npm run dev"

:: 8. Wait for services to initialize
echo [*] Waiting for services to initialize...
timeout /t 4 /nobreak >nul

:: 9. Open Browser
echo.
echo  =============================================================
echo    ALL SERVICES INITIALIZED SUCCESSFULLY
echo  =============================================================
echo    Portal URL    : http://localhost:5173/login
echo    Backend API   : http://127.0.0.1:8000
echo    API Docs      : http://127.0.0.1:8000/docs
echo    Default Login : admin / admin
echo  =============================================================
echo.
echo  Launching Security Command Center in default browser...
start http://localhost:5173/login

echo.
echo  To stop all services at any time, run: stop.bat
echo.
pause
