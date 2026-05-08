"""
Unit tests for kobo.py — device detection and file transfer.
Tests run without a physical Kobo device by simulating the .kobo/ directory.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_partition(mountpoint: str, opts: str = "rw") -> MagicMock:
    """Return a mock psutil partition."""
    p = MagicMock()
    p.mountpoint = mountpoint
    p.device     = mountpoint
    p.opts       = opts
    return p


# ---------------------------------------------------------------------------
# fmt_bytes
# ---------------------------------------------------------------------------

class TestFmtBytes(unittest.TestCase):
    """Tests for the fmt_bytes() helper."""

    def test_bytes(self):
        from kobo import fmt_bytes
        self.assertEqual(fmt_bytes(512), "512.0 B")

    def test_kilobytes(self):
        from kobo import fmt_bytes
        self.assertEqual(fmt_bytes(2048), "2.0 KB")

    def test_megabytes(self):
        from kobo import fmt_bytes
        self.assertEqual(fmt_bytes(5 * 1024 * 1024), "5.0 MB")

    def test_gigabytes(self):
        from kobo import fmt_bytes
        self.assertEqual(fmt_bytes(2 * 1024 ** 3), "2.0 GB")

    def test_terabytes(self):
        from kobo import fmt_bytes
        self.assertEqual(fmt_bytes(2 * 1024 ** 4), "2.0 TB")


# ---------------------------------------------------------------------------
# find_kobo
# ---------------------------------------------------------------------------

class TestFindKobo(unittest.TestCase):
    """Tests for find_kobo() — uses a temp directory to simulate the device."""

    def test_returns_none_when_no_kobo_connected(self):
        """No .kobo/ directory → returns None."""
        from kobo import find_kobo
        with tempfile.TemporaryDirectory() as tmp:
            part = _fake_partition(tmp)
            with patch("kobo.psutil.disk_partitions", return_value=[part]):
                result = find_kobo()
        self.assertIsNone(result)

    def test_detects_kobo_via_dot_kobo_directory(self):
        """A directory with a .kobo/ subdirectory is detected as a Kobo."""
        from kobo import find_kobo
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".kobo").mkdir()
            part = _fake_partition(tmp)
            with patch("kobo.psutil.disk_partitions", return_value=[part]), \
                 patch("kobo.psutil.disk_usage", return_value=MagicMock(free=1_000_000, total=32_000_000)):
                result = find_kobo()
        self.assertIsNotNone(result)
        self.assertTrue(result.is_kobo)

    def test_returned_device_has_mount_point(self):
        """Device.mount_point matches the simulated drive path."""
        from kobo import find_kobo
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".kobo").mkdir()
            part = _fake_partition(tmp)
            with patch("kobo.psutil.disk_partitions", return_value=[part]), \
                 patch("kobo.psutil.disk_usage", return_value=MagicMock(free=1_000_000, total=32_000_000)):
                result = find_kobo()
        self.assertEqual(result.mount_point, tmp)

    def test_returned_device_has_free_space(self):
        """Device.free_space is populated from psutil.disk_usage."""
        from kobo import find_kobo
        expected_free = 8 * 1024 ** 3  # 8 GB
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".kobo").mkdir()
            part = _fake_partition(tmp)
            with patch("kobo.psutil.disk_partitions", return_value=[part]), \
                 patch("kobo.psutil.disk_usage", return_value=MagicMock(free=expected_free, total=32 * 1024 ** 3)):
                result = find_kobo()
        self.assertEqual(result.free_space, expected_free)

    def test_skips_partitions_that_do_not_exist(self):
        """Partitions whose mount points don't exist are silently skipped."""
        from kobo import find_kobo
        part = _fake_partition("/nonexistent/mount/xyz")
        with patch("kobo.psutil.disk_partitions", return_value=[part]):
            result = find_kobo()
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------

class TestGetStatus(unittest.TestCase):

    def test_not_connected(self):
        from kobo import get_status
        with patch("kobo.find_kobo", return_value=None):
            result = get_status()
        self.assertFalse(result["connected"])
        self.assertIsNone(result["device"])

    def test_connected(self):
        from kobo import get_status
        from models import Device
        fake = Device("KOBOeReader", "/mnt/kobo", 1_000_000, 32_000_000, is_kobo=True)
        with patch("kobo.find_kobo", return_value=fake):
            result = get_status()
        self.assertTrue(result["connected"])
        self.assertEqual(result["device"]["name"], "KOBOeReader")


# ---------------------------------------------------------------------------
# send_book
# ---------------------------------------------------------------------------

class TestSendBook(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        tmp_path = Path(self.tmp.name)
        import config as cfg
        self._orig_folder = cfg.KOBO_BOOKS_FOLDER
        cfg.KOBO_BOOKS_FOLDER = ""

    def tearDown(self):
        import config as cfg
        cfg.KOBO_BOOKS_FOLDER = self._orig_folder
        self.tmp.cleanup()

    def test_raises_when_no_device(self):
        """send_book() raises RuntimeError when no Kobo is connected."""
        from kobo import send_book
        dummy = Path(self.tmp.name) / "book.epub"
        dummy.write_bytes(b"epub content")
        with patch("kobo.find_kobo", return_value=None):
            with self.assertRaises(RuntimeError):
                send_book(dummy)

    def test_raises_when_source_missing(self):
        """send_book() raises FileNotFoundError for a missing source file."""
        from kobo import send_book
        with patch("kobo.find_kobo", return_value=None):
            with self.assertRaises(FileNotFoundError):
                send_book(Path("/nonexistent/book.epub"))

    def test_raises_when_insufficient_space(self):
        """send_book() raises OSError when the file won't fit on the device."""
        from kobo import send_book
        from models import Device
        src = Path(self.tmp.name) / "large.epub"
        src.write_bytes(b"x" * 1000)
        fake_device = Device("KOBOeReader", self.tmp.name, free_space=100,
                             total_space=32_000_000, is_kobo=True)
        with patch("kobo.find_kobo", return_value=fake_device):
            with self.assertRaises(OSError):
                send_book(src)

    def test_copies_file_to_device_root(self):
        """send_book() copies the EPUB to the device root when KOBO_BOOKS_FOLDER is empty."""
        from kobo import send_book
        from models import Device
        # Simulate a Kobo mount point inside the temp dir
        mount = Path(self.tmp.name) / "kobo_mount"
        mount.mkdir()
        src = Path(self.tmp.name) / "dune.epub"
        src.write_bytes(b"epub data here")
        fake_device = Device("KOBOeReader", str(mount), free_space=1_000_000,
                             total_space=32_000_000, is_kobo=True)
        with patch("kobo.find_kobo", return_value=fake_device):
            result = send_book(src)
        dest = mount / "dune.epub"
        self.assertTrue(dest.exists())
        self.assertEqual(result["bytes_transferred"], dest.stat().st_size)

    def test_copies_file_to_subfolder(self):
        """send_book() uses KOBO_BOOKS_FOLDER when configured."""
        import config as cfg
        from kobo import send_book
        from models import Device
        cfg.KOBO_BOOKS_FOLDER = "books"
        mount = Path(self.tmp.name) / "kobo_mount"
        mount.mkdir()
        src = Path(self.tmp.name) / "foundation.epub"
        src.write_bytes(b"epub content")
        fake_device = Device("KOBOeReader", str(mount), free_space=1_000_000,
                             total_space=32_000_000, is_kobo=True)
        with patch("kobo.find_kobo", return_value=fake_device):
            result = send_book(src)
        dest = mount / "books" / "foundation.epub"
        self.assertTrue(dest.exists())

    def test_returns_destination_path(self):
        """send_book() result dict includes the destination path string."""
        from kobo import send_book
        from models import Device
        mount = Path(self.tmp.name) / "kobo_mount"
        mount.mkdir()
        src = Path(self.tmp.name) / "test.epub"
        src.write_bytes(b"data")
        fake_device = Device("KOBOeReader", str(mount), free_space=1_000_000,
                             total_space=32_000_000, is_kobo=True)
        with patch("kobo.find_kobo", return_value=fake_device):
            result = send_book(src)
        self.assertIn("destination", result)
        self.assertTrue(result["destination"].endswith("test.epub"))


if __name__ == "__main__":
    unittest.main()
