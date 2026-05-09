"""
Libby launcher — entry point for both development and the PyInstaller frozen exe.

Dev usage:   python launcher.py          (console visible, Ctrl-C to stop)
Frozen exe:  double-click Libby.exe      (system tray icon, app-mode browser window)
"""

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

# ── Path / environment setup ──────────────────────────────────────────────────
# Must happen before importing any backend module so config.py picks up the
# correct DATA_PATH.

if getattr(sys, 'frozen', False):
    # Running as a PyInstaller one-file exe.
    # Python modules land flat in sys._MEIPASS; user data (DB, covers) should
    # persist next to Libby.exe rather than in the temp extraction dir.
    _exe_dir = Path(sys.executable).parent
    os.environ.setdefault('DATA_PATH', str(_exe_dir / 'data'))
    # Backend modules are at the top level of sys._MEIPASS — already on path.

    # console=False means sys.stdout/stderr are None — redirect to a log file
    # so errors are still capturable without a terminal window.
    _log = open(_exe_dir / 'libby.log', 'w', buffering=1, encoding='utf-8')
    sys.stdout = _log
    sys.stderr = _log
else:
    # Dev mode: add backend/ so we can `from app import create_app`.
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from app import create_app  # noqa: E402  (path configured above)

# ── Server config ─────────────────────────────────────────────────────────────

PORT = int(os.getenv('PORT', '5000'))
URL  = f'http://127.0.0.1:{PORT}'


# ── Server ────────────────────────────────────────────────────────────────────

def _run_server(flask_app) -> None:
    """Start the WSGI server. Intended to run in a daemon thread."""
    try:
        from waitress import serve
        serve(flask_app, host='127.0.0.1', port=PORT, threads=4)
    except ImportError:
        # Fallback for dev environments where waitress isn't installed.
        flask_app.run(host='127.0.0.1', port=PORT, debug=False, use_reloader=False)


# ── Browser helpers ───────────────────────────────────────────────────────────

def _find_app_browser() -> str | None:
    """
    Return the path to Chrome or Edge if available, for app-mode launch.
    Checks standard Windows install locations; returns None if neither is found.
    """
    candidates = [
        # Edge is pre-installed on Windows 11 — check first
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(r"C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
        Path(r"C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
        # Chrome
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        Path(r"C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path(r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
    ]
    for p in candidates:
        if p.exists():
            return str(p)
    return None


def _open_browser() -> None:
    """Open the app in the default browser (dev-mode fallback)."""
    time.sleep(1.5)
    webbrowser.open(URL)


def _open_app_window() -> None:
    """
    Open the app in a dedicated app-mode browser window (no tabs, no URL bar).
    Falls back to a regular browser tab if Chrome/Edge is not found.
    """
    time.sleep(1.5)
    browser = _find_app_browser()
    if browser:
        import subprocess
        subprocess.Popen([browser, f"--app={URL}"])
    else:
        webbrowser.open(URL)


# ── System tray ───────────────────────────────────────────────────────────────

def _make_tray_icon():
    """
    Generate a simple book icon for the system tray using Pillow.
    Returns a PIL Image — no external image file required.
    """
    from PIL import Image, ImageDraw

    size = 64
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Book body (rounded purple rectangle)
    draw.rounded_rectangle([6, 4, 58, 60], radius=5, fill="#7c6af7")
    # Spine (darker left strip)
    draw.rounded_rectangle([6, 4, 18, 60], radius=5, fill="#5a4fd4")
    draw.rectangle([14, 4, 18, 60], fill="#5a4fd4")   # square off right edge of spine
    # Pages (white area)
    draw.rectangle([20, 10, 54, 54], fill="#f0f0f8")
    # Page lines
    for y in (20, 28, 36, 44):
        draw.line([(25, y), (49, y)], fill="#c8c8dc", width=2)

    return img


def _run_tray() -> None:
    """
    Show the system tray icon and block until the user clicks Quit.
    Must be called on the main thread on Windows.
    """
    import pystray

    def _on_open(icon, item):
        """Re-open the browser window."""
        threading.Thread(target=_open_app_window, daemon=True).start()

    def _on_quit(icon, item):
        """Stop the tray icon and terminate the process."""
        icon.stop()
        os._exit(0)

    icon = pystray.Icon(
        name="Libby",
        icon=_make_tray_icon(),
        title="Libby",
        menu=pystray.Menu(
            pystray.MenuItem("Open Libby", _on_open, default=True),
            pystray.MenuItem("Quit Libby", _on_quit),
        ),
    )
    icon.run()   # blocks until icon.stop() is called


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    flask_app = create_app()

    if getattr(sys, 'frozen', False):
        # ── Frozen exe ────────────────────────────────────────────────────────
        # No console. Server and browser open in daemon threads; tray runs on
        # the main thread and is the only way to quit.
        threading.Thread(target=_run_server,    args=(flask_app,), daemon=True).start()
        threading.Thread(target=_open_app_window,                  daemon=True).start()
        _run_tray()   # blocks; Quit menu item calls os._exit(0)

    else:
        # ── Dev mode ──────────────────────────────────────────────────────────
        # Console is visible; Ctrl-C stops the server as usual.
        print(f'Libby  {URL}')
        print('Press Ctrl-C to stop.\n')
        threading.Thread(target=_open_browser, daemon=True).start()
        _run_server(flask_app)   # blocks until Ctrl-C
