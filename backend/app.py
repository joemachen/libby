"""
Flask application factory and route registration.
All business logic lives in the backend modules — this file only wires things together.
"""

import sys
import tempfile
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

import config
from database import init_db, get_books, get_authors, get_book_by_id, update_read_status, update_book_metadata, get_setting, set_setting
from scanner import scan_library
from device import (
    get_status as device_get_status,
    send_book as device_send_book,
    eject_device as device_eject,
    list_device_books as device_list_books,
)
from editor import write_metadata, replace_cover

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# In a frozen exe all modules land flat in sys._MEIPASS; frontend data is
# bundled there too. In dev mode use the normal source tree layout.
if getattr(sys, 'frozen', False):
    _root = Path(getattr(sys, '_MEIPASS', Path(__file__).parent.parent))
else:
    _root = Path(__file__).parent.parent

FRONTEND_PUBLIC = _root / "frontend" / "public"
FRONTEND_SRC    = _root / "frontend" / "src"

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, static_folder=None)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload limit

    # Initialise the database (creates tables / runs migrations if needed)
    init_db()

    # Restore saved library path so it survives restarts
    saved_path = get_setting("library_path")
    if saved_path:
        config.LIBRARY_PATH = Path(saved_path)

    # Register route blueprints / modules
    _register_api_routes(app)
    _register_static_routes(app)

    return app


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


def _register_api_routes(app: Flask) -> None:
    """Attach all /api/* routes to the app."""

    @app.route("/api/health")
    def health():
        """Liveness check — confirms the server and DB are up."""
        return jsonify({"status": "ok"})

    @app.route("/api/scan", methods=["POST"])
    def scan():
        """Trigger a library scan; returns counts of scanned/added/updated/errors."""
        try:
            result = scan_library(config.LIBRARY_PATH)
            return jsonify({"status": "ok", "data": result})
        except FileNotFoundError as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 404}), 404
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 500}), 500

    @app.route("/api/books")
    def books():
        """Paginated, filtered list of books."""
        try:
            page = int(request.args.get("page", 1))
            limit = int(request.args.get("limit", 50))
            search = request.args.get("search") or None
            author = request.args.get("author") or None
            status = request.args.get("status") or None
            sort = request.args.get("sort", "title")
            result = get_books(
                page=page, limit=limit, search=search,
                author=author, status=status, sort=sort,
            )
            return jsonify({"status": "ok", "data": result})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 500}), 500

    @app.route("/api/books/<book_id>/status", methods=["PATCH"])
    def book_status(book_id: str):
        """Update the read status (unread / reading / read) for a single book."""
        try:
            body = request.get_json(force=True) or {}
            status = body.get("read_status", "")
            updated = update_read_status(book_id, status)
            if updated is None:
                return jsonify({"status": "error", "message": "Book not found", "code": 404}), 404
            return jsonify({"status": "ok", "data": updated})
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 400}), 400
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 500}), 500

    @app.route("/api/device/status")
    def device_status():
        """Check whether an e-reader device is connected and return its details."""
        try:
            return jsonify({"status": "ok", "data": device_get_status()})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 500}), 500

    @app.route("/api/device/send", methods=["POST"])
    def device_send():
        """Copy a book file to the connected device."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            book_id = body.get("book_id", "").strip()
            if not book_id:
                return jsonify({"status": "error", "message": "book_id is required", "code": 400}), 400

            book = get_book_by_id(book_id)
            if book is None:
                return jsonify({"status": "error", "message": "Book not found", "code": 404}), 404

            result = device_send_book(Path(book["file_path"]))
            return jsonify({"status": "ok", "data": result})
        except (RuntimeError, FileNotFoundError) as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 404}), 404
        except OSError as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 507}), 507
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 500}), 500

    @app.route("/api/device/eject", methods=["POST"])
    def device_eject_route():
        """Safely eject the connected device from the OS."""
        try:
            device_eject()
            return jsonify({"status": "ok"})
        except RuntimeError as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 404}), 404
        except OSError as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 500}), 500
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 500}), 500

    @app.route("/api/device/send/bulk", methods=["POST"])
    def device_send_bulk():
        """Send multiple books to the device in one call.

        Body: { "book_ids": ["id1", "id2", ...] }
        Returns per-book results so the UI can show partial success.
        """
        try:
            body = request.get_json(force=True, silent=True) or {}
            book_ids: list[str] = body.get("book_ids", [])
            if not book_ids:
                return jsonify({"status": "error", "message": "book_ids is required", "code": 400}), 400

            results: list[dict] = []
            for book_id in book_ids:
                book = get_book_by_id(book_id)
                if book is None:
                    results.append({"id": book_id, "title": None, "ok": False, "error": "Book not found"})
                    continue
                try:
                    device_send_book(Path(book["file_path"]))
                    results.append({"id": book_id, "title": book["title"], "ok": True})
                except Exception as exc:
                    results.append({"id": book_id, "title": book["title"], "ok": False, "error": str(exc)})

            return jsonify({"status": "ok", "data": {"results": results}})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 500}), 500

    @app.route("/api/device/books")
    def device_books():
        """List all EPUB files on the connected device, cross-referenced with the library."""
        try:
            books = device_list_books()
            return jsonify({"status": "ok", "data": books})
        except RuntimeError as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 404}), 404
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 500}), 500

    @app.route("/api/books/<book_id>/edit", methods=["POST"])
    def edit_book(book_id: str):
        """Multipart form: optional fields title, author, cover (file upload)."""
        try:
            book = get_book_by_id(book_id)
            if book is None:
                return jsonify({"status": "error", "message": "Book not found", "code": 404}), 404

            title = request.form.get("title") or None
            author = request.form.get("author") or None
            cover_file = request.files.get("cover")

            book_path = Path(book["file_path"])

            if title is not None or author is not None:
                write_metadata(book_path, title, author)

            new_cover_path = None
            if cover_file:
                suffix = Path(cover_file.filename or ".jpg").suffix or ".jpg"
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
                tmp.close()
                tmp_path = Path(tmp.name)
                try:
                    cover_file.save(str(tmp_path))
                    replace_cover(book_path, tmp_path)
                    # Re-extract the cover from the updated EPUB to COVERS_PATH
                    from ebooklib import epub as epub_lib
                    from scanner import _extract_cover
                    updated_epub = epub_lib.read_epub(str(book_path), options={"ignore_ncx": True})
                    result = _extract_cover(updated_epub, book_id)
                    new_cover_path = f"/covers/{book_id}.jpg" if result else None
                finally:
                    tmp_path.unlink(missing_ok=True)

            updated = update_book_metadata(book_id, title, author, new_cover_path)
            return jsonify({"status": "ok", "data": updated})

        except FileNotFoundError as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 404}), 404
        except ValueError as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 400}), 400
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 500}), 500

    @app.route("/api/settings/browse", methods=["GET"])
    def browse_folder():
        """Open a native OS folder-picker dialog; return the selected path.

        Runs tkinter in a subprocess so it gets a fresh main thread — required
        on Windows where GUI calls are not safe from Flask worker threads.
        """
        try:
            initial = str(config.LIBRARY_PATH) if config.LIBRARY_PATH.exists() else str(Path.home())

            if getattr(sys, 'frozen', False):
                # Frozen exe: sys.executable is Libby.exe, not a Python interpreter.
                # Call tkinter directly — on Windows it works from any thread.
                import tkinter as tk
                import tkinter.filedialog as fd
                _root = tk.Tk()
                _root.withdraw()
                _root.wm_attributes('-topmost', True)
                chosen = fd.askdirectory(title='Select Library Folder', initialdir=initial) or None
                _root.destroy()
            else:
                # Dev mode: subprocess gives tkinter a fresh main thread.
                import subprocess
                script = (
                    "import tkinter as tk, tkinter.filedialog as fd, sys\n"
                    "root = tk.Tk()\n"
                    "root.withdraw()\n"
                    "root.wm_attributes('-topmost', True)\n"
                    f"result = fd.askdirectory(title='Select Library Folder', initialdir={initial!r})\n"
                    "root.destroy()\n"
                    "sys.stdout.write(result or '')\n"
                )
                proc = subprocess.run(
                    [sys.executable, "-c", script],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                chosen = proc.stdout.strip() or None

            return jsonify({"status": "ok", "data": {"path": chosen}})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 500}), 500

    @app.route("/api/settings", methods=["GET"])
    def get_settings():
        """Return current user-editable settings."""
        try:
            library_path = get_setting("library_path") or str(config.LIBRARY_PATH)
            return jsonify({"status": "ok", "data": {"library_path": library_path}})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 500}), 500

    @app.route("/api/settings", methods=["POST"])
    def update_settings():
        """Update one or more settings. library_path must exist on disk."""
        try:
            body = request.get_json(force=True, silent=True) or {}
            updated: dict = {}

            if "library_path" in body:
                raw = str(body["library_path"]).strip()
                p = Path(raw)
                if not p.exists() or not p.is_dir():
                    return jsonify({
                        "status": "error",
                        "message": f"Directory not found: {raw}",
                        "code": 400,
                    }), 400
                set_setting("library_path", raw)
                config.LIBRARY_PATH = p
                updated["library_path"] = raw

            return jsonify({"status": "ok", "data": updated})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 500}), 500

    @app.route("/api/authors")
    def authors():
        """Return a sorted list of distinct author names in the library."""
        try:
            return jsonify({"status": "ok", "data": get_authors()})
        except Exception as exc:
            return jsonify({"status": "error", "message": str(exc), "code": 500}), 500

    @app.errorhandler(404)
    def not_found(e):
        """Return JSON 404 for unknown /api/* routes; fall through for others."""
        return jsonify({"status": "error", "message": "Not found", "code": 404}), 404

    @app.errorhandler(500)
    def server_error(e):
        """Catch-all JSON 500."""
        return (
            jsonify({"status": "error", "message": "Internal server error", "code": 500}),
            500,
        )


# ---------------------------------------------------------------------------
# Static / frontend routes
# ---------------------------------------------------------------------------


def _register_static_routes(app: Flask) -> None:
    """Serve the single-page frontend and its source assets."""

    @app.route("/covers/<path:filename>")
    def serve_cover(filename: str):
        """Serve extracted cover JPEG images."""
        return send_from_directory(str(config.COVERS_PATH), filename)

    @app.route("/src/<path:path>")
    def serve_src(path: str):
        """Serve JS, CSS, and other assets from frontend/src/."""
        return send_from_directory(str(FRONTEND_SRC), path)

    @app.route("/", defaults={"path": ""})
    @app.route("/<path:path>")
    def serve_frontend(path: str):
        """Serve index.html for all non-API routes (SPA catch-all)."""
        target = FRONTEND_PUBLIC / path
        if path and target.exists():
            return send_from_directory(str(FRONTEND_PUBLIC), path)
        return send_from_directory(str(FRONTEND_PUBLIC), "index.html")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=config.PORT, debug=config.DEBUG)
