"""
EPUB folder scanner and metadata extractor.
Entry point: scan_library(). Processes EPUBs one-by-one and upserts into the DB.
"""

import io
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import ebooklib
from ebooklib import epub
from PIL import Image, UnidentifiedImageError

import config
from models import Book

# ebooklib is verbose about missing/optional elements — silence below ERROR
logging.getLogger("ebooklib").setLevel(logging.ERROR)
logging.getLogger("ebooklib.epub").setLevel(logging.ERROR)

MAX_COVER_WIDTH = 400
MAX_COVER_HEIGHT = 600


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scan_library(library_path: Path) -> dict[str, int]:
    """
    Recursively scan library_path for EPUBs, extract metadata, and upsert into DB.

    After upserting, deletes any DB records whose file_path is no longer present
    on disk (the folder is the source of truth).

    Returns a dict with keys: scanned, added, updated, removed, errors.
    Raises FileNotFoundError if library_path does not exist.
    """
    if not library_path.exists():
        raise FileNotFoundError(f"Library path does not exist: {library_path}")

    epub_paths = _find_epubs(library_path)
    counts: dict[str, int] = {"scanned": 0, "added": 0, "updated": 0, "removed": 0, "errors": 0}

    scanned_paths: set[str] = set()
    for path in epub_paths:
        counts["scanned"] += 1
        scanned_paths.add(str(path.resolve()))
        try:
            book = _process_epub(path)
            if book is not None:
                added, updated = _upsert_book(book)
                if added:
                    counts["added"] += 1
                elif updated:
                    counts["updated"] += 1
        except Exception as exc:
            counts["errors"] += 1
            logging.warning("Failed to process %s: %s", path.name, exc)

    counts["removed"] = _delete_stale_books(scanned_paths)
    return counts


def _find_epubs(path: Path) -> list[Path]:
    """Return all .epub files found recursively under path."""
    return sorted(path.rglob("*.epub"))


# ---------------------------------------------------------------------------
# Single-book processing
# ---------------------------------------------------------------------------


def _process_epub(epub_path: Path) -> Book | None:
    """
    Open a single EPUB and extract all metadata and cover image.
    Returns None if the file cannot be read by ebooklib.
    """
    try:
        epub_book = epub.read_epub(str(epub_path), options={"ignore_ncx": True})
    except Exception as exc:
        logging.warning("ebooklib could not read %s: %s", epub_path.name, exc)
        return None

    book_id = _extract_identifier(epub_book, epub_path)
    title = _get_dc(epub_book, "title") or epub_path.stem
    author = _get_dc(epub_book, "creator")
    publisher = _get_dc(epub_book, "publisher")
    language = _get_dc(epub_book, "language")
    description = _get_dc(epub_book, "description")

    cover_file = _extract_cover(epub_book, book_id)
    cover_url = f"/covers/{book_id}.jpg" if cover_file else None

    return Book(
        id=book_id,
        title=title,
        author=author,
        publisher=publisher,
        language=language,
        description=description,
        file_path=str(epub_path.resolve()),
        cover_path=cover_url,
        file_size=epub_path.stat().st_size,
        date_added=datetime.now(timezone.utc).isoformat(),
    )


def _get_dc(epub_book: epub.EpubBook, field: str) -> str | None:
    """Extract the first DC metadata value for field, or None if absent."""
    values = epub_book.get_metadata("DC", field)
    if values:
        val = values[0][0]
        return val.strip() if isinstance(val, str) and val.strip() else None
    return None


def _extract_identifier(epub_book: epub.EpubBook, epub_path: Path) -> str:
    """
    Return a stable UUID string for the book.
    Priority:
      1. Well-formed UUID from DC:identifier (strips urn:uuid: prefix)
      2. Deterministic UUID5 derived from the resolved file path URI
    """
    raw = _get_dc(epub_book, "identifier")
    if raw:
        candidate = raw.removeprefix("urn:uuid:").strip()
        try:
            return str(uuid.UUID(candidate))
        except ValueError:
            pass
    return str(uuid.uuid5(uuid.NAMESPACE_URL, epub_path.resolve().as_uri()))


# ---------------------------------------------------------------------------
# Cover extraction
# ---------------------------------------------------------------------------


def _extract_cover(epub_book: epub.EpubBook, book_id: str) -> Path | None:
    """
    Find the cover image in the EPUB, resize to at most 400×600, save as JPEG.
    Returns the saved Path or None if no cover is found / image is unreadable.
    """
    item = _find_cover_item(epub_book)
    if item is None:
        return None

    try:
        img = Image.open(io.BytesIO(item.get_content()))
        img.thumbnail((MAX_COVER_WIDTH, MAX_COVER_HEIGHT), Image.LANCZOS)
        img = img.convert("RGB")
        dest = config.COVERS_PATH / f"{book_id}.jpg"
        img.save(str(dest), "JPEG", quality=85, optimize=True)
        return dest
    except (UnidentifiedImageError, OSError, Exception) as exc:
        logging.warning("Cover extraction failed for %s: %s", book_id, exc)
        return None


def _find_cover_item(epub_book: epub.EpubBook):
    """
    Locate the cover image item using three strategies in priority order:
      1. Image item whose properties include 'cover-image' (EPUB 3)
      2. Image item whose ID or filename contains 'cover' (EPUB 2)
      3. First image in the manifest (last-resort fallback)
    Returns the item object or None if the manifest has no images.
    """
    images = list(epub_book.get_items_of_type(ebooklib.ITEM_IMAGE))
    if not images:
        return None

    for item in images:
        props = getattr(item, "properties", []) or []
        if "cover-image" in props:
            return item

    for item in images:
        name = (item.get_name() or "").lower()
        item_id = (item.id or "").lower()
        if "cover" in name or "cover" in item_id:
            return item

    return images[0]


# ---------------------------------------------------------------------------
# DB helpers (kept here to avoid circular import; thin wrappers around database)
# ---------------------------------------------------------------------------


def _delete_stale_books(scanned_paths: set[str]) -> int:
    """
    Remove DB records whose file_path is not in scanned_paths.

    Also deletes the corresponding cover file from COVERS_PATH when present.
    Returns the number of records deleted.
    """
    from database import get_db

    with get_db() as conn:
        rows = conn.execute("SELECT id, file_path, cover_path FROM books").fetchall()
        stale = [row for row in rows if row["file_path"] not in scanned_paths]
        if not stale:
            return 0

        stale_ids = [row["id"] for row in stale]
        placeholders = ",".join("?" * len(stale_ids))
        conn.execute(f"DELETE FROM books WHERE id IN ({placeholders})", stale_ids)

    for row in stale:
        cover_path: str | None = row["cover_path"]
        if cover_path:
            cover_file = config.COVERS_PATH / Path(cover_path).name
            try:
                cover_file.unlink(missing_ok=True)
            except OSError as exc:
                logging.warning("Could not delete cover %s: %s", cover_file, exc)

    return len(stale)


def _upsert_book(book: Book) -> tuple[bool, bool]:
    """
    Insert or update a book record in the database.
    Returns (was_inserted, was_updated).
    On update, read_status is preserved.
    """
    from database import get_db

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM books WHERE file_path = ?", (book.file_path,)
        ).fetchone()

        if existing is None:
            conn.execute(
                """INSERT INTO books
                       (id, title, author, publisher, language, description,
                        file_path, cover_path, file_size, date_added, read_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    book.id, book.title, book.author, book.publisher,
                    book.language, book.description, book.file_path,
                    book.cover_path, book.file_size, book.date_added,
                    book.read_status,
                ),
            )
            return True, False

        # Update mutable metadata fields; preserve id, date_added, read_status
        conn.execute(
            """UPDATE books SET
                   title = ?, author = ?, publisher = ?, language = ?,
                   description = ?, cover_path = ?, file_size = ?
               WHERE file_path = ?""",
            (
                book.title, book.author, book.publisher, book.language,
                book.description, book.cover_path, book.file_size,
                book.file_path,
            ),
        )
        return False, True
