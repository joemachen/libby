"""
Libby launcher — entry point for both development and the PyInstaller frozen exe.

Dev usage:   python launcher.py          (console visible, Ctrl-C to stop)
Frozen exe:  double-click Libby.exe      (system tray icon, app-mode browser window)
"""

import ctypes
from ctypes import wintypes
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
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

# Tracks the most-recently opened app-mode browser process so Quit can close it.
_browser_proc: subprocess.Popen | None = None

# Dedicated Chromium user-data-dir forces Edge/Chrome to spawn a separate
# browser instance for Libby (instead of handing the URL off to the user's
# already-running browser). Every child process inherits the flag in its
# cmdline, which lets _on_quit reliably enumerate and terminate the whole tree.
_USER_DATA_DIR = Path(tempfile.gettempdir()) / "libby-app-profile"


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


def _libby_browser_pids() -> list[int]:
    """Return PIDs of every browser process running our dedicated Libby profile."""
    import psutil
    target = f"--user-data-dir={_USER_DATA_DIR}"
    pids: list[int] = []
    for p in psutil.process_iter(['pid', 'cmdline']):
        try:
            if any(target in arg for arg in (p.info['cmdline'] or [])):
                pids.append(p.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return pids


def _focus_libby_window() -> bool:
    """Bring an existing Libby app-mode window to the foreground.

    Enumerates top-level visible windows and matches by owning PID against the
    set of browser processes running our dedicated --user-data-dir profile.
    PID matching is more robust than title matching (page title can change).
    Returns True if a window was focused.
    """
    if sys.platform != 'win32':
        return False

    libby_pids = set(_libby_browser_pids())
    if not libby_pids:
        return False

    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum_cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in libby_pids and user32.GetWindowTextLengthW(hwnd) > 0:
            found.append(hwnd)
            return False  # stop enumeration
        return True

    user32.EnumWindows(_enum_cb, 0)
    if not found:
        return False

    hwnd = found[0]
    user32.ShowWindow(hwnd, 9)              # SW_RESTORE — un-minimize
    user32.SetForegroundWindow(hwnd)        # may fail silently per MSDN focus rules
    return True


def _ensure_app_window() -> None:
    """Bring the Libby window to the foreground, or spawn one if none exists.

    Used by both the tray "Open Libby" item and the second-instance handoff,
    so clicking the tray icon repeatedly never spawns duplicate windows.
    """
    global _browser_proc
    if _focus_libby_window():
        return
    browser = _find_app_browser()
    if browser:
        _USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        _browser_proc = subprocess.Popen([
            browser,
            f"--app={URL}",
            f"--user-data-dir={_USER_DATA_DIR}",
        ])
    else:
        webbrowser.open(URL)


def _open_app_window() -> None:
    """Initial post-startup window open: wait for the server, then ensure window."""
    time.sleep(1.5)
    _ensure_app_window()


def _check_existing_instance() -> bool:
    """Return True if another Libby is already serving on PORT."""
    try:
        with urllib.request.urlopen(f"{URL}/api/health", timeout=0.5) as resp:
            return resp.status == 200
    except Exception:
        return False


# ── System tray ───────────────────────────────────────────────────────────────

def _icon_path() -> Path:
    """
    Return the path to assets/icon.png.

    In the frozen exe the assets folder is extracted next to the executable
    (listed under datas in libby.spec).  In dev mode it sits at
    <project-root>/assets/icon.png relative to this file.
    """
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / 'assets' / 'icon.png'
    return Path(__file__).parent / 'assets' / 'icon.png'


def _make_tray_icon():
    """
    Load assets/icon.png as the system-tray image.
    Falls back to a minimal Pillow-drawn icon if the file is missing.
    """
    from PIL import Image

    icon_file = _icon_path()
    if icon_file.exists():
        return Image.open(icon_file).convert("RGBA")

    # ── Fallback: draw a simple purple book ───────────────────────────────
    from PIL import ImageDraw
    size = 64
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([6, 4, 58, 60], radius=5, fill="#7c6af7")
    draw.rounded_rectangle([6, 4, 18, 60], radius=5, fill="#5a4fd4")
    draw.rectangle([14, 4, 18, 60], fill="#5a4fd4")
    draw.rectangle([20, 10, 54, 54], fill="#f0f0f8")
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
        """Focus the existing window, or open one if none exists."""
        threading.Thread(target=_ensure_app_window, daemon=True).start()

    def _on_quit(icon, item):
        """Close the browser window, stop the tray icon, and terminate the process.

        Edge/Chrome inherit --user-data-dir to every child process (renderer,
        GPU, utility), and our launch uses a dedicated Libby profile dir, so
        scanning process cmdlines for that path reliably matches the entire
        Libby browser tree without touching the user's normal browser.
        """
        import psutil
        target = f"--user-data-dir={_USER_DATA_DIR}"
        for proc in psutil.process_iter(['pid', 'cmdline']):
            try:
                if any(target in arg for arg in (proc.info['cmdline'] or [])):
                    proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
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
    # Single-instance gate: if another Libby is already serving, hand off to it
    # (focus its window or spawn one against its server) and exit silently.
    # This must run before create_app() so we don't even touch the DB.
    if getattr(sys, 'frozen', False) and _check_existing_instance():
        _ensure_app_window()
        sys.exit(0)

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
