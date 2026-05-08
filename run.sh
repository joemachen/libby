#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# ── Virtual environment ──────────────────────────────────────────────────────
if [ ! -d "venv" ]; then
    echo "[setup] Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# ── Dependencies ─────────────────────────────────────────────────────────────
echo "[setup] Installing / updating dependencies..."
pip install -r requirements.txt -q

# ── .env bootstrap ────────────────────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo "[setup] No .env found. Copying from .env.example..."
    cp .env.example .env
    echo "[setup] Edit .env to set your LIBRARY_PATH before first use."
fi

# ── Launch ────────────────────────────────────────────────────────────────────
echo ""
echo "[start] Libby starting on http://127.0.0.1:5000"
echo "        Press Ctrl+C to stop."
echo ""
python backend/app.py
