# Libby — CLAUDE.md

Read this file at the start of every session before writing any code.

## Project overview

**Libby** is a local-only Windows desktop app for managing a personal EPUB library
and copying books to an e-reader (Kobo, PocketBook, Tolino, ONYX Boox).  
No cloud sync, no DRM handling, no format conversion.

Delivered as a single `Libby.exe` (PyInstaller one-file, console-less).  
In dev mode it's a plain Flask server at `http://127.0.0.1:5000`.

## Current version: 0.3.2

## Phase history

| Phase | Description                     | Status      |
|-------|---------------------------------|-------------|
| 1     | Foundation (Flask + SQLite)     | ✅ Complete |
| 2     | EPUB Scanner                    | ✅ Complete |
| 3     | Frontend Library View           | ✅ Complete |
| 4     | Device Integration (Kobo first) | ✅ Complete |
| 5     | Polish (search, sort, settings) | ✅ Complete |
| 6     | Metadata Editing                | ✅ Complete |
| 7     | Device-agnostic support         | ✅ Complete |
| 8     | System tray + app-mode window   | ✅ Complete |
| 9     | App icon (PNG + ICO)            | ✅ Complete |

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+, Flask 3.x, SQLite (stdlib) |
| Frontend | Vanilla JS (ES modules), HTML, CSS — **no build step, no npm** |
| EPUB parsing | `ebooklib` + `Pillow` |
| Device detection | `psutil` |
| Config | `python-dotenv` → `backend/config.py` |
| WSGI server | `waitress` (production), Flask dev server (fallback) |
| System tray | `pystray` (Windows Win32 message loop, runs on main thread) |
| Packaging | PyInstaller 6.x, one-file exe, `console=False` |

## Project structure

```
kobo-library/
├── assets/
│   ├── icon.png          256×256 RGBA — tray icon source (Pillow-drawn, committed)
│   └── icon.ico          Multi-size ICO (16–256 px) — exe/taskbar icon
├── backend/
│   ├── app.py            Flask factory + route wiring only
│   ├── config.py         All config (reads .env)
│   ├── database.py       SQLite init, migrations, get_db() context manager
│   ├── models.py         Book and Device dataclasses
│   ├── scanner.py        EPUB scanner
│   ├── editor.py         Metadata writer (title, author, cover)
│   └── device.py         Device detection + transfer (all brands)
├── frontend/
│   ├── public/index.html SPA shell
│   └── src/
│       ├── api.js                All fetch() calls
│       ├── app.js                Entry point + state
│       └── components/
│           ├── bookCard.js
│           ├── bookGrid.js
│           ├── bookList.js
│           ├── searchBar.js
│           ├── sidebar.js
│           ├── devicePanel.js    Header status pill + send/eject buttons
│           ├── deviceShelf.js    Slide-out drawer listing books on device
│           ├── editModal.js      Metadata edit dialog
│           └── settingsModal.js
│       └── styles/
│           ├── main.css
│           ├── grid.css
│           ├── modal.css
│           ├── settings.css
│           ├── device.css        Connected-device state on #app
│           └── device-shelf.css  Shelf drawer styles
├── tests/
│   ├── test_database.py
│   ├── test_device.py
│   ├── test_editor.py
│   └── test_scanner.py
├── .github/workflows/
│   ├── ci.yml            ubuntu-latest, pytest on every push to main
│   └── release.yml       windows-latest, pytest + pyinstaller on version tags
├── assets/               icon.png + icon.ico (committed)
├── data/                 DB and covers (gitignored)
├── docs/api.md           Endpoint reference
├── launcher.py           Entry point (dev + frozen exe)
├── libby.spec            PyInstaller spec
├── requirements.txt
├── VERSION               Plain semver file — must match git tag on release
├── run.bat / run.sh
└── .env                  (copy from .env.example, never commit)
```

## Known issues / cleanup needed

These exist in the repo right now and should be fixed:

### 1. Bug — `app.js` line 56: `KoboPanel` is not imported

```js
// WRONG — KoboPanel is not in scope
onSend: (id, title) => KoboPanel.sendBook(id, title),

// FIX
onSend: (id, title) => DevicePanel.sendBook(id, title),
```

`DevicePanel` is already imported at the top of `app.js`; only the callback
body needs updating.

### 2. Orphaned files — old Kobo-specific components

These files were superseded by the device-agnostic refactor but not deleted:

| File | Replaced by |
|---|---|
| `frontend/src/components/koboPanel.js` | `devicePanel.js` |
| `frontend/src/components/koboShelf.js` | `deviceShelf.js` |
| `frontend/src/styles/kobo.css` | `device.css` |
| `frontend/src/styles/kobo-shelf.css` | `device-shelf.css` |

None of these are imported anywhere active — safe to `git rm` all four.

---

## Device support (backend/device.py)

```python
DEVICE_PROFILES = {
    "kobo":       markers=[".kobo"],   system_dirs={".kobo"},
    "pocketbook": markers=[".adds"],   system_dirs={".adds","System","thumbnails"},
    "tolino":     markers=[".tolino"], system_dirs={".tolino"},
    "boox":       markers=["Android"], system_dirs={"Android",".android_secure",...},
}
```

Detection: `find_device()` iterates `psutil.disk_partitions()` and checks
markers in the order above (first match wins).  
The `Device` dataclass uses `device_type: str = "unknown"` (not `is_kobo: bool`).

## API routes (all under /api/)

| Method | Route | Description |
|---|---|---|
| GET | `/api/books` | Paginated library list |
| POST | `/api/books/scan` | Trigger EPUB scan |
| POST | `/api/books/<id>/read` | Cycle read status |
| POST | `/api/books/<id>/edit` | Edit metadata (multipart) |
| GET | `/api/device/status` | Device connection status |
| POST | `/api/device/send` | Send one book |
| POST | `/api/device/send/bulk` | Send multiple books |
| POST | `/api/device/eject` | Safely eject device |
| GET | `/api/device/books` | List EPUBs on device |

## API envelope

```json
{ "status": "ok",    "data": <payload> }
{ "status": "error", "message": "...", "code": 404 }
```

## launcher.py — how the exe works

```
Frozen exe:
  main thread → _run_tray()           # blocks; Quit menu calls os._exit(0)
  daemon thread → _run_server()       # waitress WSGI
  daemon thread → _open_app_window()  # Edge/Chrome --app=URL, or webbrowser fallback

Dev mode:
  main thread → _run_server()         # blocks until Ctrl-C
  daemon thread → _open_browser()
```

- `console=False` in spec → stdout/stderr redirected to `libby.log` next to exe
- `DATA_PATH` env var controls where DB + covers go (defaults to `<exe dir>/data`)
- Icon loaded from `sys._MEIPASS/assets/icon.png` in frozen, `./assets/icon.png` in dev

## CI / Release workflow

- **CI** (`ci.yml`): runs pytest on ubuntu-latest on every push to main
- **Release** (`release.yml`): triggered by a `v*` tag
  1. Runs pytest
  2. Verifies `git tag == v$(cat VERSION)` — they must match
  3. Builds `dist/Libby.exe` with pyinstaller
  4. Creates a GitHub Release and uploads the exe

**To release a new version:**
```
# 1. Bump VERSION file
echo "0.4.0" > VERSION
# 2. Commit, push, tag — in that order
git add VERSION && git commit -m "feat: ..."
git push
git tag v0.4.0 && git push origin v0.4.0
```

## Rules — never break these

1. **No hardcoded paths.** All paths from `config.py`.
2. **No inline styles.** CSS lives in `frontend/src/styles/`.
3. **`app.py` is a router only.** All logic in module files.
4. **Every function gets a docstring.** One-liners are fine.
5. **No silent failures.** All exceptions → JSON error responses.
6. **Use `pathlib.Path` everywhere.** Never `os.path`.
7. **Database access via `with get_db() as conn:` only.** Never leave connections open.
8. **All API calls go through `api.js`.** No raw `fetch()` in component files.
9. **VERSION file must match git tag** before pushing a release tag.

## Python conventions

- Python 3.10+ features: `match`, `|` union types
- Type hints on every function signature
- `from __future__ import annotations` not required — 3.10+ handles it natively

## Running the app

```bat
run.bat                   # Windows: set up venv, install deps, start server
python -m pytest tests/   # Run all 62 tests
python launcher.py        # Dev mode (console + Ctrl-C)
```
