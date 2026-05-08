"""
Libby launcher — entry point for both development and the PyInstaller frozen exe.

Dev usage:   python launcher.py
Frozen exe:  double-click Libby.exe (PyInstaller sets sys.frozen = True)
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
else:
    # Dev mode: add backend/ so we can `from app import create_app`.
    sys.path.insert(0, str(Path(__file__).parent / 'backend'))

from app import create_app  # noqa: E402  (path configured above)

# ── Server config ─────────────────────────────────────────────────────────────

PORT = int(os.getenv('PORT', '5000'))
URL  = f'http://127.0.0.1:{PORT}'


def _open_browser() -> None:
    """Open the app URL in the default browser after a short delay."""
    time.sleep(1.5)
    webbrowser.open(URL)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app = create_app()

    print(f'Libby  {URL}')
    print('Press Ctrl+C to stop.\n')

    threading.Thread(target=_open_browser, daemon=True).start()

    try:
        from waitress import serve
        serve(app, host='127.0.0.1', port=PORT, threads=4)
    except ImportError:
        # Fallback for dev environments where waitress isn't installed.
        app.run(host='127.0.0.1', port=PORT, debug=False, use_reloader=False)
