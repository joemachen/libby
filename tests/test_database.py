"""
Unit tests for database.py — schema creation and migration logic.
Run with: python -m pytest tests/ or python -m unittest discover tests/
"""

import sys
import tempfile
import unittest
from pathlib import Path

# Allow importing backend modules without installing as a package
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


class TestDatabaseInit(unittest.TestCase):
    """Tests for database initialisation and schema creation."""

    def setUp(self):
        """Redirect DB and covers paths to a temporary directory for each test."""
        self.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp.name)

        import config as cfg
        self._orig_data = cfg.DATA_PATH
        self._orig_db = cfg.DB_PATH
        self._orig_covers = cfg.COVERS_PATH

        cfg.DATA_PATH = tmp_path
        cfg.DB_PATH = tmp_path / "test.db"
        cfg.COVERS_PATH = tmp_path / "covers"

    def tearDown(self):
        import config as cfg
        cfg.DATA_PATH = self._orig_data
        cfg.DB_PATH = self._orig_db
        cfg.COVERS_PATH = self._orig_covers
        self.tmp.cleanup()

    def test_init_creates_data_directory(self):
        """init_db() should create the data and covers directories."""
        import config as cfg
        from database import init_db
        init_db()
        self.assertTrue(cfg.DATA_PATH.exists())
        self.assertTrue(cfg.COVERS_PATH.exists())

    def test_init_creates_db_file(self):
        """init_db() should create the SQLite database file."""
        import config as cfg
        from database import init_db
        init_db()
        self.assertTrue(cfg.DB_PATH.exists())

    def test_books_table_exists(self):
        """After init_db(), the books table should be present."""
        from database import init_db, get_db
        init_db()
        with get_db() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='books'"
            ).fetchone()
        self.assertIsNotNone(row)

    def test_schema_version_seeded(self):
        """After init_db(), the schema_version table should have a row."""
        from database import init_db, get_db
        init_db()
        with get_db() as conn:
            row = conn.execute("SELECT version FROM schema_version").fetchone()
        self.assertIsNotNone(row)
        self.assertGreaterEqual(row["version"], 1)

    def test_idempotent_init(self):
        """Calling init_db() twice should not raise or corrupt the schema."""
        from database import init_db
        init_db()
        init_db()  # Should not raise

    def test_get_db_context_manager(self):
        """get_db() should yield a usable connection and close it after."""
        from database import init_db, get_db
        init_db()
        with get_db() as conn:
            result = conn.execute("SELECT 1").fetchone()
        self.assertEqual(result[0], 1)


class TestBookCRUD(unittest.TestCase):
    """Basic CRUD smoke tests against the books table."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp_path = Path(self.tmp.name)
        import config as cfg
        self._orig = (cfg.DATA_PATH, cfg.DB_PATH, cfg.COVERS_PATH)
        cfg.DATA_PATH = tmp_path
        cfg.DB_PATH = tmp_path / "test.db"
        cfg.COVERS_PATH = tmp_path / "covers"
        from database import init_db
        init_db()

    def tearDown(self):
        import config as cfg
        cfg.DATA_PATH, cfg.DB_PATH, cfg.COVERS_PATH = self._orig
        self.tmp.cleanup()

    def test_insert_and_retrieve_book(self):
        """A book inserted via raw SQL should be retrievable as a dict."""
        from database import get_db, row_to_dict
        with get_db() as conn:
            conn.execute(
                "INSERT INTO books (id, title, file_path, date_added) VALUES (?, ?, ?, ?)",
                ("test-uuid-1", "Test Book", "/tmp/test.epub", "2024-01-01T00:00:00"),
            )
        with get_db() as conn:
            row = conn.execute("SELECT * FROM books WHERE id = ?", ("test-uuid-1",)).fetchone()
            book = row_to_dict(row)
        self.assertEqual(book["title"], "Test Book")
        self.assertEqual(book["read_status"], "unread")


if __name__ == "__main__":
    unittest.main()
