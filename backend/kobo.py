"""
Kobo device detection and EPUB file transfer.

Detection strategy (in priority order):
  1. Mount point contains a .kobo/ subdirectory  (definitive cross-platform check)
  2. Volume label equals "KOBOeReader"            (Windows: checked via ctypes)

Sending copies the source EPUB to the device root or to KOBO_BOOKS_FOLDER if set.
"""

import shutil
import sys
from pathlib import Path

import psutil

import config
from models import Device


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_kobo() -> Device | None:
    """
    Scan all mounted partitions for a Kobo device.
    Returns a populated Device or None if none is found.
    """
    for part in psutil.disk_partitions(all=False):
        mount = Path(part.mountpoint)
        if not mount.exists():
            continue

        # .kobo/ directory is the definitive indicator on all platforms
        if (mount / ".kobo").is_dir():
            return _build_device(mount, part)

        # Windows volume-label fallback
        if sys.platform == "win32" and _win_label(part.mountpoint) == "KOBOeReader":
            return _build_device(mount, part)

    return None


def get_status() -> dict:
    """
    Return current Kobo connection status.
    Result: {"connected": bool, "device": Device.to_dict() | None}
    """
    device = find_kobo()
    return {"connected": device is not None, "device": device.to_dict() if device else None}


def send_book(book_path: Path) -> dict:
    """
    Copy an EPUB file to the connected Kobo.

    Returns {"bytes_transferred": int, "destination": str}.
    Raises:
      FileNotFoundError – source file missing
      RuntimeError     – no Kobo connected
      OSError          – insufficient space or copy failure
    """
    if not book_path.exists():
        raise FileNotFoundError(f"Source file not found: {book_path}")

    device = find_kobo()
    if device is None:
        raise RuntimeError("No Kobo device is currently connected")

    file_size = book_path.stat().st_size
    if file_size > device.free_space:
        raise OSError(
            f"Insufficient space on Kobo "
            f"({fmt_bytes(file_size)} needed, {fmt_bytes(device.free_space)} free)"
        )

    mount = Path(device.mount_point)
    folder = config.KOBO_BOOKS_FOLDER.strip()
    dest_dir = (mount / folder) if folder else mount
    dest_dir.mkdir(parents=True, exist_ok=True)

    dest = dest_dir / book_path.name
    shutil.copy2(str(book_path), str(dest))

    return {
        "bytes_transferred": dest.stat().st_size,
        "destination": str(dest),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_device(mount: Path, partition) -> Device:
    """Construct a Device from a psutil partition object."""
    try:
        usage = psutil.disk_usage(str(mount))
        free, total = usage.free, usage.total
    except OSError:
        free = total = 0

    label = "KOBOeReader"
    if sys.platform == "win32":
        label = _win_label(partition.mountpoint) or label

    return Device(
        name=label,
        mount_point=partition.mountpoint,
        free_space=free,
        total_space=total,
        is_kobo=True,
    )


def _win_label(drive: str) -> str:
    """Return the Windows volume label for a drive path like 'E:\\'."""
    import ctypes
    buf = ctypes.create_unicode_buffer(256)
    try:
        ctypes.windll.kernel32.GetVolumeInformationW(
            drive, buf, len(buf), None, None, None, None, 0
        )
    except Exception:
        pass
    return buf.value


def fmt_bytes(n: int) -> str:
    """Human-readable byte count (e.g. '1.4 GB')."""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
