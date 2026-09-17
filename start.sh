#!/bin/bash
# =============================================================
# PROJECT GARUDA - Universal Unix/Linux/macOS Launcher
# =============================================================

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

echo ""
echo "============================================================="
echo "  PROJECT GARUDA - Adaptive Edge Video Intelligence Platform "
echo "============================================================="
echo ""

# 1. Check Python
if ! command -v python3 &> /dev/null; then
    echo "[!] ERROR: python3 is not installed."
    exit 1
fi

# 2. Check Node
if ! command -v node &> /dev/null; then
    echo "[!] ERROR: node is not installed."
    exit 1
fi

# 3. Setup Virtual Environment if missing
if [ ! -f "$DIR/backend/venv/bin/activate" ]; then
    echo "[*] Initializing backend virtual environment..."
    python3 -m venv "$DIR/backend/venv"
    source "$DIR/backend/venv/bin/activate"
    pip install --upgrade pip
    pip install -r "$DIR/backend/requirements.txt"
else
    source "$DIR/backend/venv/bin/activate"
fi

# 4. Copy .env if missing
if [ ! -f "$DIR/.env" ] && [ -f "$DIR/.env.example" ]; then
    cp "$DIR/.env.example" "$DIR/.env"
    echo "[+] Created .env from .env.example"
fi

# 5. Start Backend
echo "[*] Starting Backend Server on http://localhost:8000..."
cd "$DIR/backend"
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait for backend
sleep 3

# 6. Start Frontend
echo "[*] Starting Frontend Console on http://localhost:5173..."
cd "$DIR/frontend"
if [ ! -d "node_modules" ]; then
    echo "[*] Installing frontend dependencies..."
    npm install
fi
npm run dev &
FRONTEND_PID=$!

echo ""
echo "============================================================="
echo "  ALL SERVICES RUNNING"
echo "  Portal URL    : http://localhost:5173/login"
echo "  Backend API   : http://localhost:8000"
echo "  API Docs      : http://localhost:8000/docs"
echo "  Default Login : admin / admin"
echo "============================================================="
echo "  Press Ctrl+C to stop all servers."
echo ""

# Trap SIGINT and SIGTERM to kill background children
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGINT SIGTERM

wait $BACKEND_PID $FRONTEND_PID
