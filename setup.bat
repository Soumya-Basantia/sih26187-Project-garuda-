@echo off
setlocal enabledelayedexpansion
title Project Garuda - Setup & Installer
color 0A

echo.
echo  =============================================================
echo    PROJECT GARUDA - Automated Environment Setup
echo  =============================================================
echo.

:: 1. Verify Python
echo [*] Step 1/5: Checking Python installation...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] ERROR: Python 3.10+ is required.
    echo     Download and install from: https://www.python.org/downloads/
    echo     Remember to check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)
python --version

:: 2. Verify Node.js & npm
echo.
echo [*] Step 2/5: Checking Node.js & npm...
node -v >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] ERROR: Node.js 18+ is required.
    echo     Download and install from: https://nodejs.org/
    echo.
    pause
    exit /b 1
)
node -v
npm -v

:: 3. Setup Python Virtual Environment & Install Requirements
echo.
echo [*] Step 3/5: Setting up Python virtual environment...
if not exist "%~dp0backend\venv\Scripts\activate.bat" (
    echo     Creating venv in backend\venv...
    python -m venv "%~dp0backend\venv"
    if %errorlevel% neq 0 (
        echo [!] ERROR: Failed to create Python virtual environment.
        pause
        exit /b 1
    )
)

echo     Upgrading pip and installing backend dependencies...
cd /d "%~dp0backend"
call .\venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [!] Warning: Some dependencies may have had installation issues.
)
cd /d "%~dp0"

:: 4. Setup Frontend npm Dependencies
echo.
echo [*] Step 4/5: Installing Frontend npm dependencies...
cd /d "%~dp0frontend"
call npm install
if %errorlevel% neq 0 (
    echo [!] Warning: Frontend npm install encountered warnings or errors.
)
cd /d "%~dp0"

:: 5. Environment Configuration & Database Seeding
echo.
echo [*] Step 5/5: Configuring environment and seeding initial data...
if not exist "%~dp0.env" (
    if exist "%~dp0.env.example" (
        copy "%~dp0.env.example" "%~dp0.env" >nul
        echo     [+] Created .env file from template.
    )
)

echo     Attempting initial database seed (admin credentials)...
cd /d "%~dp0backend"
call .\venv\Scripts\activate
python seed.py >nul 2>&1
if %errorlevel% equ 0 (
    echo     [+] Database seeded successfully with default admin user.
) else (
    echo     [*] Notice: Database seed could not reach MongoDB.
    echo         If MongoDB is not running yet, seed will apply upon starting MongoDB.
)
cd /d "%~dp0"

echo.
echo  =============================================================
echo    SETUP COMPLETE! YOU ARE READY TO RUN PROJECT GARUDA
echo  =============================================================
echo    To launch the platform, double-click: start.bat
echo    To access the management menu, run  : manage.bat
echo  =============================================================
echo.
pause
