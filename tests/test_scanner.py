"""
Unit tests for scanner.py — EPUB discovery, metadata extraction, and cover handling.
Run with: python -m pytest tests/test_scanner.py -v
"""

import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_epub(
    path: Path,
    title: str = "Fixture Book",
    author: str = "Fixture Author",
    identifier: str | None = None,
    publisher: str | None = None,
    language: str = "en",
) -> Path:
    """
    Create a minimal but valid EPUB3 file at path.
    Returns path for convenience.
    """
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier(identifier or str(uuid.uuid4()))
    book.set_title(title)
    book.add_author(author)
    book.set_language(language)
    if publisher:
        book.add_metadata("DC", "publisher", publisher)

    chapter = epub.EpubHtml(title="Ch1", file_name="chap_01.xhtml", lang=language)
    chapter.set_content(f"<html><body><h1>{title}</h1></body></html>")
    book.add_item(chapter)

    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]

    epub.write_epub(str(path), book)
    return path


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------

class TestFindEpubs(unittest.TestCase):
    """Tests for _find_epubs()."""

    def test_finds_epub_in_flat_folder(self):
        """A single .epub file in a directory is found."""
        from scanner import _find_epubs
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "book.epub"
            p.touch()
            result = _find_epubs(Path(tmp))
        self.assertEqual(len(result), 1)

    def test_finds_epubs_recursively(self):
        """EPUBs in subdirectories are discovered."""
        from scanner import _find_epubs
        with tempfile.TemporaryDirectory() as tmp:
            sub = Path(tmp) / "subdir"
            sub.mkdir()
            (sub / "deep.epub").touch()
            (Path(tmp) / "top.epub").touch()
            result = _find_epubs(Path(tmp))
        self.assertEqual(len(result), 2)

    def test_ignores_non_epub_files(self):
        """Non-.epub files are not returned."""
        from scanner import _find_epubs
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "book.pdf").touch()
            (Path(tmp) / "book.epub").touch()
            result = _find_epubs(Path(tmp))
        self.assertEqual(len(result), 1)


class TestExtractIdentifier(unittest.TestCase):
    """Tests for _extract_identifier()."""

    def _epub_with_id(self, raw_id: str):
        """Return a minimal EpubBook with the given DC:identifier."""
        from ebooklib import epub
        book = epub.EpubBook()
        book.set_identifier(raw_id)
        book.set_title("X")
        return book

    def test_valid_uuid_identifier(self):
        """A plain UUID in DC:identifier is returned as-is."""
        from scanner import _extract_identifier
        uid = str(uuid.uuid4())
        book = self._epub_with_id(uid)
        with tempfile.NamedTemporaryFile(suffix=".epub") as f:
            result = _extract_identifier(book, Path(f.name))
        self.assertEqual(result, uid)

    def test_urn_uuid_prefix_stripped(self):
        """urn:uuid: prefix is stripped before validation."""
        from scanner import _extract_identifier
        uid = str(uuid.uuid4())
        book = self._epub_with_id(f"urn:uuid:{uid}")
        with tempfile.NamedTemporaryFile(suffix=".epub") as f:
            result = _extract_identifier(book, Path(f.name))
        self.assertEqual(result, uid)

    def test_non_uuid_identifier_falls_back_to_uuid5(self):
        """A non-UUID identifier causes a UUID5 fallback."""
        from scanner import _extract_identifier
        book = self._epub_with_id("isbn:978-3-16-148410-0")
        with tempfile.NamedTemporaryFile(suffix=".epub") as f:
            result = _extract_identifier(book, Path(f.name))
        # Must be a valid UUID
        parsed = uuid.UUID(result)
        self.assertEqual(parsed.version, 5)

    def test_uuid5_is_deterministic(self):
        """Same file path always produces the same UUID5 fallback."""
        from scanner import _extract_identifier
        book = self._epub_with_id("not-a-uuid")
        with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as f:
            path = Path(f.name)
        r1 = _extract_identifier(book, path)
        r2 = _extract_identifier(book, path)
        self.assertEqual(r1, r2)


class TestProcessEpub(unittest.TestCase):
    """End-to-end tests for _process_epub()."""

    def setUp(self):
        # ignore_cleanup_errors avoids Windows file-lock failures on teardown
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        tmp_path = Path(self.tmp.name)
        import config as cfg
        self._orig = (cfg.DATA_PATH, cfg.DB_PATH, cfg.COVERS_PATH)
        cfg.DATA_PATH = tmp_path
        cfg.DB_PATH = tmp_path / "test.db"
        cfg.COVERS_PATH = tmp_path / "covers"
        cfg.COVERS_PATH.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import config as cfg
        cfg.DATA_PATH, cfg.DB_PATH, cfg.COVERS_PATH = self._orig
        self.tmp.cleanup()

    def test_returns_book_with_correct_metadata(self):
        """_process_epub() extracts title and author correctly."""
        from scanner import _process_epub
        uid = str(uuid.uuid4())
        epub_path = Path(self.tmp.name) / "test.epub"
        _make_epub(epub_path, title="Dune", author="Frank Herbert", identifier=uid)

        book = _process_epub(epub_path)
        self.assertIsNotNone(book)
        self.assertEqual(book.title, "Dune")
        self.assertEqual(book.author, "Frank Herbert")
        self.assertEqual(book.id, uid)

    def test_uses_filename_when_title_missing(self):
        """Falls back to the stem of the filename when DC:title is absent."""
        from scanner import _process_epub
        from ebooklib import epub as eblib

        book_obj = eblib.EpubBook()
        book_obj.set_identifier(str(uuid.uuid4()))
        # Intentionally no title — ebooklib still needs a non-empty body for nav
        chapter = eblib.EpubHtml(title="C", file_name="c.xhtml")
        chapter.set_content(
            '<html xmlns="http://www.w3.org/1999/xhtml">'
            "<head><title>C</title></head>"
            "<body><p>Content</p></body></html>"
        )
        book_obj.add_item(chapter)
        book_obj.add_item(eblib.EpubNcx())
        book_obj.add_item(eblib.EpubNav())
        book_obj.spine = ["nav", chapter]

        epub_path = Path(self.tmp.name) / "my_great_book.epub"
        eblib.write_epub(str(epub_path), book_obj)

        book = _process_epub(epub_path)
        self.assertIsNotNone(book)
        self.assertEqual(book.title, "my_great_book")

    def test_returns_none_for_corrupt_file(self):
        """_process_epub() returns None for a non-EPUB file."""
        from scanner import _process_epub
        bad = Path(self.tmp.name) / "corrupt.epub"
        bad.write_bytes(b"this is not an epub file at all")
        result = _process_epub(bad)
        self.assertIsNone(result)

    def test_file_size_recorded(self):
        """Book object has a positive file_size."""
        from scanner import _process_epub
        epub_path = Path(self.tmp.name) / "sized.epub"
        _make_epub(epub_path)
        book = _process_epub(epub_path)
        self.assertIsNotNone(book)
        self.assertGreater(book.file_size, 0)


class TestScanLibrary(unittest.TestCase):
    """Integration tests for scan_library()."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp.name)
        import config as cfg
        self._orig = (cfg.DATA_PATH, cfg.DB_PATH, cfg.COVERS_PATH, cfg.LIBRARY_PATH)
        cfg.DATA_PATH = tmp_path / "data"
        cfg.DB_PATH = tmp_path / "data" / "test.db"
        cfg.COVERS_PATH = tmp_path / "data" / "covers"
        cfg.LIBRARY_PATH = tmp_path / "library"
        cfg.LIBRARY_PATH.mkdir()
        from database import init_db
        init_db()

    def tearDown(self):
        import config as cfg
        cfg.DATA_PATH, cfg.DB_PATH, cfg.COVERS_PATH, cfg.LIBRARY_PATH = self._orig
        self.tmp.cleanup()

    def test_raises_for_missing_library_path(self):
        """scan_library() raises FileNotFoundError for a non-existent path."""
        from scanner import scan_library
        with self.assertRaises(FileNotFoundError):
            scan_library(Path("/nonexistent/path/xyz"))

    def test_scan_empty_folder_returns_zero_counts(self):
        """Scanning an empty folder returns all-zero counts."""
        import config as cfg
        from scanner import scan_library
        result = scan_library(cfg.LIBRARY_PATH)
        self.assertEqual(result["scanned"], 0)
        self.assertEqual(result["added"], 0)

    def test_scan_adds_books_to_db(self):
        """Books found during scan are present in the database afterward."""
        import config as cfg
        from scanner import scan_library
        from database import get_books

        epub_path = cfg.LIBRARY_PATH / "book.epub"
        _make_epub(epub_path, title="Neuromancer", author="William Gibson")

        counts = scan_library(cfg.LIBRARY_PATH)
        self.assertEqual(counts["added"], 1)

        result = get_books()
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["books"][0]["title"], "Neuromancer")

    def test_rescan_updates_not_duplicates(self):
        """Re-scanning the same file increments updated, not added."""
        import config as cfg
        from scanner import scan_library
        from database import get_books

        epub_path = cfg.LIBRARY_PATH / "book.epub"
        _make_epub(epub_path, title="Foundation")

        scan_library(cfg.LIBRARY_PATH)
        counts = scan_library(cfg.LIBRARY_PATH)

        self.assertEqual(counts["added"], 0)
        self.assertEqual(counts["updated"], 1)
        # Still only one record in DB
        self.assertEqual(get_books()["total"], 1)

    def test_removed_count_is_zero_when_nothing_deleted(self):
        """scan_library() returns removed=0 when all files still exist."""
        import config as cfg
        from scanner import scan_library

        _make_epub(cfg.LIBRARY_PATH / "book.epub", title="Dune")
        scan_library(cfg.LIBRARY_PATH)
        counts = scan_library(cfg.LIBRARY_PATH)

        self.assertEqual(counts["removed"], 0)

    def test_deleted_file_removed_from_db(self):
        """A book whose EPUB is deleted is pruned from the DB on next scan."""
        import config as cfg
        from scanner import scan_library
        from database import get_books

        epub_path = cfg.LIBRARY_PATH / "gone.epub"
        _make_epub(epub_path, title="Gone Book")
        scan_library(cfg.LIBRARY_PATH)
        self.assertEqual(get_books()["total"], 1)

        epub_path.unlink()
        counts = scan_library(cfg.LIBRARY_PATH)

        self.assertEqual(counts["removed"], 1)
        self.assertEqual(get_books()["total"], 0)

    def test_only_stale_books_are_removed(self):
        """Pruning deletes only the record whose file was removed, not others."""
        import config as cfg
        from scanner import scan_library
        from database import get_books

        keep = cfg.LIBRARY_PATH / "keep.epub"
        remove = cfg.LIBRARY_PATH / "remove.epub"
        _make_epub(keep, title="Keeper")
        _make_epub(remove, title="Goner")
        scan_library(cfg.LIBRARY_PATH)

        remove.unlink()
        counts = scan_library(cfg.LIBRARY_PATH)

        self.assertEqual(counts["removed"], 1)
        result = get_books()
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["books"][0]["title"], "Keeper")

    def test_stale_cover_file_deleted(self):
        """The cover JPEG is removed from disk when its book record is pruned."""
        import config as cfg
        from scanner import scan_library
        from database import get_db

        epub_path = cfg.LIBRARY_PATH / "withcover.epub"
        _make_epub(epub_path, title="Covered")
        scan_library(cfg.LIBRARY_PATH)

        # Find the cover_path stored for this book
        with get_db() as conn:
            row = conn.execute("SELECT cover_path FROM books").fetchone()
        cover_path_url: str | None = row["cover_path"] if row else None

        epub_path.unlink()
        scan_library(cfg.LIBRARY_PATH)

        if cover_path_url:
            cover_file = cfg.COVERS_PATH / Path(cover_path_url).name
            self.assertFalse(cover_file.exists(), "Orphaned cover file should be deleted")


class TestGetBooks(unittest.TestCase):
    """Unit tests for the get_books() database query function."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp.name)
        import config as cfg
        self._orig = (cfg.DATA_PATH, cfg.DB_PATH, cfg.COVERS_PATH, cfg.LIBRARY_PATH)
        cfg.DATA_PATH = tmp_path
        cfg.DB_PATH = tmp_path / "test.db"
        cfg.COVERS_PATH = tmp_path / "covers"
        cfg.LIBRARY_PATH = tmp_path / "lib"
        cfg.LIBRARY_PATH.mkdir()
        from database import init_db
        init_db()
        # Seed a few books directly
        from database import get_db
        books_data = [
            ("id-1", "Dune", "Frank Herbert", "/f1.epub"),
            ("id-2", "Foundation", "Isaac Asimov", "/f2.epub"),
            ("id-3", "Neuromancer", "William Gibson", "/f3.epub"),
        ]
        with get_db() as conn:
            for bid, title, author, path in books_data:
                conn.execute(
                    "INSERT INTO books (id, title, author, file_path, date_added)"
                    " VALUES (?, ?, ?, ?, '2024-01-01')",
                    (bid, title, author, path),
                )

    def tearDown(self):
        import config as cfg
        cfg.DATA_PATH, cfg.DB_PATH, cfg.COVERS_PATH, cfg.LIBRARY_PATH = self._orig
        self.tmp.cleanup()

    def test_returns_all_books(self):
        from database import get_books
        result = get_books()
        self.assertEqual(result["total"], 3)
        self.assertEqual(len(result["books"]), 3)

    def test_search_filters_by_title(self):
        from database import get_books
        result = get_books(search="dune")
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["books"][0]["title"], "Dune")

    def test_search_filters_by_author(self):
        from database import get_books
        result = get_books(search="asimov")
        self.assertEqual(result["total"], 1)

    def test_author_filter(self):
        from database import get_books
        result = get_books(author="Frank Herbert")
        self.assertEqual(result["total"], 1)

    def test_pagination(self):
        from database import get_books
        result = get_books(page=1, limit=2)
        self.assertEqual(len(result["books"]), 2)
        self.assertEqual(result["pages"], 2)

    def test_sort_by_title(self):
        from database import get_books
        result = get_books(sort="title")
        titles = [b["title"] for b in result["books"]]
        self.assertEqual(titles, sorted(titles, key=str.lower))


if __name__ == "__main__":
    unittest.main()
