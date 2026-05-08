# Libby — CLAUDE.md

Read this file at the start of every session before writing any code.

## Project overview

A local-only web app for managing an EPUB ebook library and copying books to a Kobo Aura H2O Edition 2. No cloud sync, no DRM handling, no format conversion.

## Current status

| Phase | Description              | Status      |
|-------|--------------------------|-------------|
| 1     | Foundation               | ✅ Complete |
| 2     | EPUB Scanner             | ✅ Complete |
| 3     | Frontend Library View    | ✅ Complete |
| 4     | Kobo Integration         | ✅ Complete |
| 5     | Polish                   | ✅ Complete |
| 6     | Metadata Editing         | ✅ Complete |

## Tech stack

- **Backend**: Python 3.10+, Flask 3.x, SQLite (stdlib)
- **Frontend**: Vanilla JS (ES modules), HTML, CSS — no build step, no npm
- **EPUB parsing**: `ebooklib` + `Pillow`
- **Device detection**: `psutil`
- **Config**: `python-dotenv` → `backend/config.py`

## Project structure

```
kobo-library/
├── backend/
│   ├── app.py        Flask factory + route wiring only
│   ├── config.py     All config (reads .env)
│   ├── database.py   SQLite init, migrations, get_db() context manager
│   ├── models.py     Book and Device dataclasses
│   ├── scanner.py    EPUB scanner (Phase 2)
│   ├── editor.py     Metadata writer (Phase 6)
│   └── kobo.py       Device detection + transfer (Phase 4)
├── frontend/
│   ├── public/index.html   SPA shell
│   └── src/
│       ├── api.js          All fetch() calls
│       ├── app.js          Entry point
│       ├── components/     One file per component
│       └── styles/         main.css, grid.css, modal.css, kobo.css
├── data/             DB and covers (gitignored)
├── tests/            unittest-based tests
├── docs/api.md       Endpoint reference
├── requirements.txt
├── run.bat / run.sh
└── .env              (copy from .env.example, never commit)
```

## Rules — never break these

1. **No hardcoded paths.** All paths come from `config.py`.
2. **No inline styles.** CSS lives in `frontend/src/styles/`.
3. **`app.py` is a router only.** All logic lives in the module files.
4. **Every function gets a docstring.** One-liners are fine.
5. **No silent failures.** All exceptions → JSON error responses.
6. **Use `pathlib.Path` everywhere.** Never `os.path`.
7. **Database access via `with get_db() as conn:` only.** Never leave connections open.
8. **All API calls go through `api.js`.** No raw `fetch()` in component files.
9. **Build phases in order.** Complete the gate check before moving to the next phase.

## Python conventions

- Python 3.10+ features: `match`, `|` union types
- Type hints on every function signature
- `from __future__ import annotations` not required — 3.10+ handles it natively

## API envelope

```json
// Success
{"status": "ok", "data": <payload>}

// Error
{"status": "error", "message": "...", "code": 404}
```

## Running the app

```bat
run.bat          # Windows — sets up venv, installs deps, starts server
python -m pytest tests/    # Run tests
```

Server runs at `http://127.0.0.1:5000`.

---

## Phase 6 — Metadata Editing (next)

Allow the user to edit a book's title, author, and cover image. Changes are written back to the EPUB file and reflected in the database.

### Backend

**`backend/editor.py`** — implement two public functions:

```python
def write_metadata(book_path: Path, title: str | None, author: str | None) -> None:
    """Overwrite dc:title and dc:creator in the EPUB's OPF metadata."""

def replace_cover(book_path: Path, image_path: Path) -> None:
    """Replace the cover image item in the EPUB with a resized version of image_path.
    Resize to max 600×900 px (preserve aspect ratio), save as JPEG.
    Creates a backup at book_path.with_suffix('.epub.bak') before modifying."""
```

Rules:
- Always create `.epub.bak` before any write (`shutil.copy2`).
- Use `ebooklib` to read/write — open, mutate, save via `epub.write_epub`.
- Resize with Pillow: `Image.thumbnail((600, 900))`, save as JPEG quality 85.
- Raise `FileNotFoundError` if `book_path` doesn't exist.
- Raise `ValueError` for unsupported image formats (accept JPEG, PNG, WEBP).

**`backend/app.py`** — add one route (inside `_register_api_routes`):

```python
@app.route("/api/books/<book_id>/edit", methods=["POST"])
def edit_book(book_id: str):
    """Multipart form: optional fields title, author, cover (file upload)."""
```

Logic:
1. Look up book by `book_id`; 404 if missing.
2. If `title` or `author` in form data, call `write_metadata`.
3. If `cover` file in `request.files`, save to a temp file, call `replace_cover`, then re-extract cover to `COVERS_PATH` (reuse scanner's `_save_cover` logic — import it).
4. Call `update_book_metadata(book_id, title, author, cover_path)` (new DB helper — see below).
5. Return updated book dict.

**`backend/database.py`** — add one function:

```python
def update_book_metadata(book_id: str, title: str | None, author: str | None, cover_path: str | None) -> dict | None:
    """Update title/author/cover_path for a book. Only updates fields that are not None."""
```

### Frontend

**`frontend/src/components/editModal.js`** — new component:

```
EditModal.open(bookId, currentTitle, currentAuthor)
EditModal.close()
```

- Renders a `<dialog>` element (HTML native modal, not a div).
- Fields: Title (text input, pre-filled), Author (text input, pre-filled), Cover image (file input, accept="image/*").
- Cover preview: show current cover or placeholder; update preview on file select.
- Submit: calls `editBook(id, formData)` from `api.js` (already exists).
- On success: dispatch a custom event `book-updated` with `detail: updatedBook` so `app.js` can patch state.
- On error: show inline error message inside the modal (not a toast).
- Close on backdrop click and Escape key.

**`frontend/src/app.js`** — wire up:
- Import `EditModal` from `./components/editModal.js`.
- Change `onEdit` callback in `BookGrid.init` from the Phase 5 toast stub to: `onEdit: (id, title) => EditModal.open(id, title, ...)`.
- Listen for `book-updated` event on `document`; patch `state.books` and call `_render()`.

**`frontend/src/styles/modal.css`** — implement styles:
- Dialog backdrop: `dialog::backdrop { background: rgba(0,0,0,0.6); }`
- Modal card: dark surface, max-width 480px, centred.
- Form fields: consistent with existing `.search-input` / `.sort-select` style.
- Cover preview: 120×180 px thumbnail, object-fit cover, border-radius.
- Action row: Cancel (`.btn-ghost`) + Save (`.btn-primary`).

### Tests

Add `tests/test_editor.py`:
- `test_write_metadata_updates_title`
- `test_write_metadata_updates_author`
- `test_write_metadata_creates_no_backup` (metadata-only edit does NOT need backup — only cover replacement does)
- `test_replace_cover_creates_backup`
- `test_replace_cover_resizes_large_image`
- `test_replace_cover_raises_for_unsupported_format`
- `test_replace_cover_raises_for_missing_book`

### Gate check

1. `POST /api/books/<id>/edit` with `title=New Title` → returns book with updated title.
2. `POST /api/books/<id>/edit` with a JPEG file → cover updates in DB and `/covers/` directory.
3. Click Edit on a card → modal opens with pre-filled fields.
4. Save with new title → card title updates without page reload.
5. Upload a new cover → card shows new cover image.
