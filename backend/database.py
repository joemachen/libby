"""
SQLite database initialization, schema creation, migrations, and connection helper.
All consumers should use `get_db()` as a context manager — never hold raw connections.
"""

import sqlite3
from contextlib import contextmanager
from math import ceil
from pathlib import Path
from typing import Generator

import config

# Increment this when adding a new migration step below.
CURRENT_SCHEMA_VERSION = 1


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Yield an open SQLite connection that auto-commits on clean exit
    and auto-rolls-back on exception.
    """
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    # Enforce foreign key constraints for every connection
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    Ensure the data directories exist, create tables on first run,
    and apply any pending schema migrations.
    """
    config.DATA_PATH.mkdir(parents=True, exist_ok=True)
    config.COVERS_PATH.mkdir(parents=True, exist_ok=True)

    with get_db() as conn:
        _create_base_schema(conn)
        _run_migrations(conn)


def _create_base_schema(conn: sqlite3.Connection) -> None:
    """Create all tables if they do not already exist (idempotent)."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version (
            lock    INTEGER PRIMARY KEY DEFAULT 1 CHECK (lock = 1),
            version INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS books (
            id          TEXT PRIMARY KEY,
            title       TEXT NOT NULL,
            author      TEXT,
            publisher   TEXT,
            language    TEXT,
            description TEXT,
            file_path   TEXT NOT NULL UNIQUE,
            cover_path  TEXT,
            file_size   INTEGER,
            date_added  TEXT NOT NULL,
            read_status TEXT NOT NULL DEFAULT 'unread'
        );

        CREATE INDEX IF NOT EXISTS idx_books_author   ON books(author);
        CREATE INDEX IF NOT EXISTS idx_books_title    ON books(title);
        CREATE INDEX IF NOT EXISTS idx_books_status   ON books(read_status);

        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)

    # Seed version row if this is a brand-new database (lock=1 enforces single row)
    conn.execute(
        "INSERT OR IGNORE INTO schema_version (lock, version) VALUES (1, 0)"
    )


def _get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the current schema version stored in the DB."""
    row = conn.execute("SELECT version FROM schema_version WHERE lock = 1").fetchone()
    return row["version"] if row else 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Update the stored schema version (single-row table keyed by lock=1)."""
    conn.execute("UPDATE schema_version SET version = ? WHERE lock = 1", (version,))


def _run_migrations(conn: sqlite3.Connection) -> None:
    """
    Apply any migrations whose version number exceeds the stored version.
    Add new migration functions to the `migrations` list in order.
    """
    migrations: list[tuple[int, callable]] = [
        # (target_version, migration_function)
        # Example for future migrations:
        # (2, _migrate_v2),
    ]

    current = _get_schema_version(conn)

    for target_version, migrate_fn in migrations:
        if current < target_version:
            migrate_fn(conn)
            _set_schema_version(conn, target_version)
            current = target_version

    # Ensure version reflects the base schema if no migrations have run
    if current == 0:
        _set_schema_version(conn, CURRENT_SCHEMA_VERSION)


def row_to_dict(row: sqlite3.Row) -> dict:
    """Convert a sqlite3.Row to a plain Python dict."""
    return dict(row)


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

_VALID_SORTS = {"title", "author", "date_added"}


def get_books(
    page: int = 1,
    limit: int = 50,
    search: str | None = None,
    author: str | None = None,
    status: str | None = None,
    sort: str = "title",
) -> dict:
    """
    Return a paginated, filtered list of books.

    Result dict keys: books (list), total (int), page (int), pages (int).
    The sort column is whitelisted against _VALID_SORTS to prevent SQL injection.
    """
    sort_col = sort if sort in _VALID_SORTS else "title"
    limit = min(max(1, limit), 200)

    conditions: list[str] = []
    params: list = []

    if search:
        conditions.append(
            "(LOWER(title) LIKE ? OR LOWER(COALESCE(author, '')) LIKE ?)"
        )
        term = f"%{search.lower()}%"
        params.extend([term, term])

    if author:
        conditions.append("author = ?")
        params.append(author)

    if status and status in {"unread", "reading", "read"}:
        conditions.append("read_status = ?")
        params.append(status)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    offset = (max(1, page) - 1) * limit

    with get_db() as conn:
        total: int = conn.execute(
            f"SELECT COUNT(*) FROM books {where}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"SELECT * FROM books {where}"
            f" ORDER BY LOWER(COALESCE({sort_col}, '')) ASC"
            f" LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()

    return {
        "books": [row_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "pages": max(1, ceil(total / limit)),
    }


def get_authors() -> list[str]:
    """Return a sorted list of distinct non-null author names."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT author FROM books"
            " WHERE author IS NOT NULL ORDER BY LOWER(author)"
        ).fetchall()
    return [r["author"] for r in rows]


def get_book_by_id(book_id: str) -> dict | None:
    """Return a single book as a dict by its UUID, or None if not found."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM books WHERE id = ?", (book_id,)
        ).fetchone()
    return row_to_dict(row) if row else None


def get_setting(key: str) -> str | None:
    """Return the stored value for key, or None if absent."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else None


def set_setting(key: str, value: str) -> None:
    """Insert or replace a setting value."""
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )


def update_book_metadata(
    book_id: str,
    title: str | None,
    author: str | None,
    cover_path: str | None,
) -> dict | None:
    """Update title/author/cover_path for a book. Only updates fields that are not None."""
    updates: list[str] = []
    params: list = []

    if title is not None:
        updates.append("title = ?")
        params.append(title)

    if author is not None:
        updates.append("author = ?")
        params.append(author)

    if cover_path is not None:
        updates.append("cover_path = ?")
        params.append(cover_path)

    if not updates:
        return get_book_by_id(book_id)

    params.append(book_id)

    with get_db() as conn:
        conn.execute(
            f"UPDATE books SET {', '.join(updates)} WHERE id = ?",
            params,
        )
        row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()

    return row_to_dict(row) if row else None


def update_read_status(book_id: str, status: str) -> dict | None:
    """
    Update the read_status for a single book.
    Returns the updated book dict, or None if the id was not found.
    """
    if status not in {"unread", "reading", "read"}:
        raise ValueError(f"Invalid read_status: {status!r}")

    with get_db() as conn:
        conn.execute(
            "UPDATE books SET read_status = ? WHERE id = ?", (status, book_id)
        )
        row = conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()

    return row_to_dict(row) if row else None
