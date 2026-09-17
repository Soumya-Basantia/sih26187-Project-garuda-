@echo off
setlocal enabledelayedexpansion
title Project Garuda - Management Console
color 0F

:MENU
cls
echo.
echo  =============================================================
echo    PROJECT GARUDA - Operations & Management Console
echo    Adaptive Edge Video Intelligence Platform
echo  =============================================================
echo.
echo    [1] Start Platform (Backend API + Frontend Surveillance Console)
echo    [2] Start Full Tri-Portal (Backend + Frontend + God's Eye View)
echo    [3] Stop All Running Project Garuda Services
echo.
echo    [4] Run Automated Setup & Dependency Installation
echo    [5] Pre-flight Diagnostics & Port Availability Check
echo    [6] Seed Database with Administrator & Demo Profiles
echo    [7] Run Full Test Suite (21 Verification Suites)
echo.
echo    [8] Prepare & Push Project Garuda to Your Personal GitHub
echo    [9] View Comprehensive Instructions Guide (INSTRUCTIONS.md)
echo    [0] Exit Console
echo.
echo  =============================================================
set /p choice="  Enter option number [0-9]: "

if "%choice%"=="1" goto START_PLATFORM
if "%choice%"=="2" goto START_TRIPORTAL
if "%choice%"=="3" goto STOP_SERVICES
if "%choice%"=="4" goto RUN_SETUP
if "%choice%"=="5" goto RUN_DIAGNOSTICS
if "%choice%"=="6" goto SEED_DATABASE
if "%choice%"=="7" goto RUN_TESTS
if "%choice%"=="8" goto GITHUB_HELPER
if "%choice%"=="9" goto VIEW_DOCS
if "%choice%"=="0" goto EXIT_APP

echo [!] Invalid selection. Please try again.
timeout /t 2 >nul
goto MENU

:START_PLATFORM
call "%~dp0start.bat"
goto MENU

:START_TRIPORTAL
echo.
echo [*] Launching Full Tri-Portal System...
call "%~dp0start.bat"
echo [*] Starting God's Eye View Console (port 4173)...
start "Project Garuda - God's Eye View" /min cmd /c "cd /d "%~dp0gods-eye-view" && npm run dev"
echo [+] Tri-Portal Active!
pause
goto MENU

:STOP_SERVICES
call "%~dp0stop.bat"
pause
goto MENU

:RUN_SETUP
call "%~dp0setup.bat"
goto MENU

:RUN_DIAGNOSTICS
cls
echo.
echo  =============================================================
echo    PRE-FLIGHT DIAGNOSTICS & SYSTEM AUDIT
echo  =============================================================
echo.
echo [*] Python Runtime:
python --version 2>&1
echo [*] Node.js Runtime:
node -v 2>&1
echo [*] npm Package Manager:
npm -v 2>&1
echo [*] Git Version:
git --version 2>&1
echo.
echo [*] Checking Port Allocations:
netstat -aon | findstr ":8000" >nul 2>&1
if %errorlevel% equ 0 (
    echo     [!] Port 8000 is currently OCCUPIED (Backend running or port in use)
) else (
    echo     [+] Port 8000 is FREE
)

netstat -aon | findstr ":5173" >nul 2>&1
if %errorlevel% equ 0 (
    echo     [!] Port 5173 is currently OCCUPIED (Frontend running or port in use)
) else (
    echo     [+] Port 5173 is FREE
)

echo.
echo [*] Checking Database:
sc query MongoDB | find "RUNNING" >nul 2>&1
if %errorlevel% equ 0 (
    echo     [+] MongoDB Windows Service is RUNNING
) else (
    echo     [*] MongoDB Windows Service is not running or running standalone.
)

echo.
pause
goto MENU

:SEED_DATABASE
cls
echo.
echo  =============================================================
echo    DATABASE SEED UTILITY
echo  =============================================================
echo.
cd /d "%~dp0backend"
if exist ".\venv\Scripts\activate.bat" (
    call .\venv\Scripts\activate
    echo [*] Seeding default administrator account...
    python seed.py
    echo.
    echo [*] Seeding demo personnel profiles...
    if exist "seed_demo_personnel.py" (
        python seed_demo_personnel.py
    )
) else (
    echo [!] Backend virtual environment not found. Run Setup first.
)
cd /d "%~dp0"
echo.
pause
goto MENU

:RUN_TESTS
cls
echo.
echo  =============================================================
echo    EXECUTING 21 GARUDA TEST SUITES
echo  =============================================================
echo.
cd /d "%~dp0backend"
if exist ".\venv\Scripts\activate.bat" (
    call .\venv\Scripts\activate
    cd /d "%~dp0"
    python tests\run_all_tests.py
) else (
    cd /d "%~dp0"
    python tests\run_all_tests.py
)
echo.
pause
goto MENU

:GITHUB_HELPER
cls
echo.
echo  =============================================================
echo    PUSH PROJECT GARUDA TO YOUR PERSONAL GITHUB REPOSITORY
echo  =============================================================
echo.
echo  Follow these 4 simple steps to push Garuda to your GitHub:
echo.
echo  1. Create a NEW repository on GitHub (https://github.com/new)
echo     Name it: "project-garuda" or any name you prefer.
echo     (Do NOT initialize with README, .gitignore, or license)
echo.
echo  2. Copy your new GitHub repository URL:
echo     e.g., https://github.com/<YOUR-USERNAME>/project-garuda.git
echo.
echo  3. Run these commands inside this directory:
echo.
echo     cd /d "%~dp0"
echo     git init
echo     git add .
echo     git commit -m "Initial commit: Project Garuda AI Video Analytics Platform"
echo     git branch -M main
echo     git remote add origin https://github.com/<YOUR-USERNAME>/<YOUR-REPO>.git
echo     git push -u origin main
echo.
echo  NOTE: Models (*.pt) and virtual environments (venv/, node_modules/)
echo        are already configured in .gitignore to keep your repo fast and clean!
echo.
echo  =============================================================
pause
goto MENU

:VIEW_DOCS
if exist "%~dp0INSTRUCTIONS.md" (
    start notepad "%~dp0INSTRUCTIONS.md"
) else (
    echo [!] INSTRUCTIONS.md not found.
)
goto MENU

:EXIT_APP
exit /b 0
