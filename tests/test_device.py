"""
Unit tests for device.py — device detection and file transfer.
Tests run without a physical device by simulating marker directories.
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
        from device import fmt_bytes
        self.assertEqual(fmt_bytes(512), "512.0 B")

    def test_kilobytes(self):
        from device import fmt_bytes
        self.assertEqual(fmt_bytes(2048), "2.0 KB")

    def test_megabytes(self):
        from device import fmt_bytes
        self.assertEqual(fmt_bytes(5 * 1024 * 1024), "5.0 MB")

    def test_gigabytes(self):
        from device import fmt_bytes
        self.assertEqual(fmt_bytes(2 * 1024 ** 3), "2.0 GB")

    def test_terabytes(self):
        from device import fmt_bytes
        self.assertEqual(fmt_bytes(2 * 1024 ** 4), "2.0 TB")


# ---------------------------------------------------------------------------
# find_device — Kobo detection
# ---------------------------------------------------------------------------

class TestFindDevice(unittest.TestCase):
    """Tests for find_device() — uses temp directories to simulate devices."""

    def test_returns_none_when_no_device_connected(self):
        """No marker directory → returns None."""
        from device import find_device
        with tempfile.TemporaryDirectory() as tmp:
            part = _fake_partition(tmp)
            with patch("device.psutil.disk_partitions", return_value=[part]):
                result = find_device()
        self.assertIsNone(result)

    def test_detects_kobo_via_dot_kobo_directory(self):
        """A .kobo/ subdirectory is detected as a Kobo device."""
        from device import find_device
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".kobo").mkdir()
            part = _fake_partition(tmp)
            with patch("device.psutil.disk_partitions", return_value=[part]), \
                 patch("device.psutil.disk_usage", return_value=MagicMock(free=1_000_000, total=32_000_000)):
                result = find_device()
        self.assertIsNotNone(result)
        self.assertEqual(result.device_type, "kobo")

    def test_returned_device_has_mount_point(self):
        """Device.mount_point matches the simulated drive path."""
        from device import find_device
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".kobo").mkdir()
            part = _fake_partition(tmp)
            with patch("device.psutil.disk_partitions", return_value=[part]), \
                 patch("device.psutil.disk_usage", return_value=MagicMock(free=1_000_000, total=32_000_000)):
                result = find_device()
        self.assertEqual(result.mount_point, tmp)

    def test_returned_device_has_free_space(self):
        """Device.free_space is populated from psutil.disk_usage."""
        from device import find_device
        expected_free = 8 * 1024 ** 3  # 8 GB
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".kobo").mkdir()
            part = _fake_partition(tmp)
            with patch("device.psutil.disk_partitions", return_value=[part]), \
                 patch("device.psutil.disk_usage", return_value=MagicMock(free=expected_free, total=32 * 1024 ** 3)):
                result = find_device()
        self.assertEqual(result.free_space, expected_free)

    def test_skips_partitions_that_do_not_exist(self):
        """Partitions whose mount points don't exist are silently skipped."""
        from device import find_device
        part = _fake_partition("/nonexistent/mount/xyz")
        with patch("device.psutil.disk_partitions", return_value=[part]):
            result = find_device()
        self.assertIsNone(result)

    # ── New profile-detection tests ───────────────────────────────────────

    def test_pocketbook_detected_by_adds_dir(self):
        """A .adds/ directory is detected as a PocketBook device."""
        from device import find_device
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".adds").mkdir()
            part = _fake_partition(tmp)
            with patch("device.psutil.disk_partitions", return_value=[part]), \
                 patch("device.psutil.disk_usage", return_value=MagicMock(free=1_000_000, total=32_000_000)):
                result = find_device()
        self.assertIsNotNone(result)
        self.assertEqual(result.device_type, "pocketbook")

    def test_tolino_detected_by_tolino_dir(self):
        """A .tolino/ directory is detected as a Tolino device."""
        from device import find_device
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".tolino").mkdir()
            part = _fake_partition(tmp)
            with patch("device.psutil.disk_partitions", return_value=[part]), \
                 patch("device.psutil.disk_usage", return_value=MagicMock(free=1_000_000, total=32_000_000)):
                result = find_device()
        self.assertIsNotNone(result)
        self.assertEqual(result.device_type, "tolino")

    def test_boox_detected_by_android_dir(self):
        """An Android/ directory is detected as an ONYX Boox device."""
        from device import find_device
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Android").mkdir()
            part = _fake_partition(tmp)
            with patch("device.psutil.disk_partitions", return_value=[part]), \
                 patch("device.psutil.disk_usage", return_value=MagicMock(free=1_000_000, total=32_000_000)):
                result = find_device()
        self.assertIsNotNone(result)
        self.assertEqual(result.device_type, "boox")

    def test_unknown_device_returns_none(self):
        """A drive with no recognised marker directory returns None."""
        from device import find_device
        with tempfile.TemporaryDirectory() as tmp:
            # Put a random directory there — not a device marker
            (Path(tmp) / "random_folder").mkdir()
            part = _fake_partition(tmp)
            with patch("device.psutil.disk_partitions", return_value=[part]):
                result = find_device()
        self.assertIsNone(result)

    def test_kobo_takes_priority_over_boox(self):
        """Kobo marker (.kobo/) wins when multiple markers exist (detection order)."""
        from device import find_device
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".kobo").mkdir()
            (Path(tmp) / "Android").mkdir()  # Also has Boox marker
            part = _fake_partition(tmp)
            with patch("device.psutil.disk_partitions", return_value=[part]), \
                 patch("device.psutil.disk_usage", return_value=MagicMock(free=1_000_000, total=32_000_000)):
                result = find_device()
        self.assertIsNotNone(result)
        self.assertEqual(result.device_type, "kobo")


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------

class TestGetStatus(unittest.TestCase):

    def test_not_connected(self):
        from device import get_status
        with patch("device.find_device", return_value=None):
            result = get_status()
        self.assertFalse(result["connected"])
        self.assertIsNone(result["device"])

    def test_connected(self):
        from device import get_status
        from models import Device
        fake = Device("KOBOeReader", "/mnt/kobo", 1_000_000, 32_000_000, device_type="kobo")
        with patch("device.find_device", return_value=fake):
            result = get_status()
        self.assertTrue(result["connected"])
        self.assertEqual(result["device"]["name"], "KOBOeReader")
        self.assertEqual(result["device"]["device_type"], "kobo")


# ---------------------------------------------------------------------------
# send_book
# ---------------------------------------------------------------------------

class TestSendBook(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        import config as cfg
        self._orig_folder = cfg.DEVICE_BOOKS_FOLDER
        cfg.DEVICE_BOOKS_FOLDER = ""

    def tearDown(self):
        import config as cfg
        cfg.DEVICE_BOOKS_FOLDER = self._orig_folder
        self.tmp.cleanup()

    def test_raises_when_no_device(self):
        """send_book() raises RuntimeError when no device is connected."""
        from device import send_book
        dummy = Path(self.tmp.name) / "book.epub"
        dummy.write_bytes(b"epub content")
        with patch("device.find_device", return_value=None):
            with self.assertRaises(RuntimeError):
                send_book(dummy)

    def test_raises_when_source_missing(self):
        """send_book() raises FileNotFoundError for a missing source file."""
        from device import send_book
        with patch("device.find_device", return_value=None):
            with self.assertRaises(FileNotFoundError):
                send_book(Path("/nonexistent/book.epub"))

    def test_raises_when_insufficient_space(self):
        """send_book() raises OSError when the file won't fit on the device."""
        from device import send_book
        from models import Device
        src = Path(self.tmp.name) / "large.epub"
        src.write_bytes(b"x" * 1000)
        fake_device = Device("KOBOeReader", self.tmp.name, free_space=100,
                             total_space=32_000_000, device_type="kobo")
        with patch("device.find_device", return_value=fake_device):
            with self.assertRaises(OSError):
                send_book(src)

    def test_copies_file_to_device_root(self):
        """send_book() copies the EPUB to the device root when DEVICE_BOOKS_FOLDER is empty."""
        from device import send_book
        from models import Device
        mount = Path(self.tmp.name) / "device_mount"
        mount.mkdir()
        src = Path(self.tmp.name) / "dune.epub"
        src.write_bytes(b"epub data here")
        fake_device = Device("KOBOeReader", str(mount), free_space=1_000_000,
                             total_space=32_000_000, device_type="kobo")
        with patch("device.find_device", return_value=fake_device):
            result = send_book(src)
        dest = mount / "dune.epub"
        self.assertTrue(dest.exists())
        self.assertEqual(result["bytes_transferred"], dest.stat().st_size)

    def test_copies_file_to_subfolder(self):
        """send_book() uses DEVICE_BOOKS_FOLDER when configured."""
        import config as cfg
        from device import send_book
        from models import Device
        cfg.DEVICE_BOOKS_FOLDER = "books"
        mount = Path(self.tmp.name) / "device_mount"
        mount.mkdir()
        src = Path(self.tmp.name) / "foundation.epub"
        src.write_bytes(b"epub content")
        fake_device = Device("KOBOeReader", str(mount), free_space=1_000_000,
                             total_space=32_000_000, device_type="kobo")
        with patch("device.find_device", return_value=fake_device):
            result = send_book(src)
        dest = mount / "books" / "foundation.epub"
        self.assertTrue(dest.exists())

    def test_returns_destination_path(self):
        """send_book() result dict includes the destination path string."""
        from device import send_book
        from models import Device
        mount = Path(self.tmp.name) / "device_mount"
        mount.mkdir()
        src = Path(self.tmp.name) / "test.epub"
        src.write_bytes(b"data")
        fake_device = Device("KOBOeReader", str(mount), free_space=1_000_000,
                             total_space=32_000_000, device_type="kobo")
        with patch("device.find_device", return_value=fake_device):
            result = send_book(src)
        self.assertIn("destination", result)
        self.assertTrue(result["destination"].endswith("test.epub"))


if __name__ == "__main__":
    unittest.main()
