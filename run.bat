@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

:: ── Virtual environment ────────────────────────────────────────────────────
if not exist venv (
    echo [setup] Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo [error] Failed to create venv. Is Python 3.10+ on your PATH?
        pause & exit /b 1
    )
)

call venv\Scripts\activate.bat

:: ── Dependencies ───────────────────────────────────────────────────────────
echo [setup] Installing / updating dependencies...
pip install -r requirements.txt -q
if errorlevel 1 (
    echo [error] pip install failed. Check requirements.txt.
    pause & exit /b 1
)

:: ── .env bootstrap ─────────────────────────────────────────────────────────
if not exist .env (
    echo [setup] No .env found. Copying from .env.example...
    copy .env.example .env >nul
    echo [setup] Edit .env to set your LIBRARY_PATH before first use.
)

:: ── Launch ─────────────────────────────────────────────────────────────────
echo.
echo [start] Libby starting on http://127.0.0.1:5000
echo         Press Ctrl+C to stop.
echo.
python backend\app.py
