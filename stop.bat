@echo off
setlocal enabledelayedexpansion
title Project Garuda - Shutdown
color 0C

echo.
echo  =============================================================
echo    PROJECT GARUDA - Service Shutdown Utility
echo  =============================================================
echo.
echo [*] Terminating running Project Garuda services...

:: Stop processes listening on Port 8000 (Backend FastAPI)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo     [x] Terminating Backend process on port 8000 (PID %%a)...
    taskkill /F /PID %%a >nul 2>&1
)

:: Stop processes listening on Port 5173 (Frontend Vite)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":5173" ^| findstr "LISTENING"') do (
    echo     [x] Terminating Frontend process on port 5173 (PID %%a)...
    taskkill /F /PID %%a >nul 2>&1
)

:: Stop processes listening on Port 4173 (God's Eye View Console if active)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":4173" ^| findstr "LISTENING"') do (
    echo     [x] Terminating God's Eye View process on port 4173 (PID %%a)...
    taskkill /F /PID %%a >nul 2>&1
)

:: Close any lingering cmd windows titled with Project Garuda
taskkill /FI "WINDOWTITLE eq Project Garuda*" /F >nul 2>&1

echo.
echo  [+] All Project Garuda services have been stopped.
echo  [+] Ports 8000 and 5173 are now free.
echo.
timeout /t 2 /nobreak >nul
