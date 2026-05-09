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


def eject_device() -> None:
    """
    Safely eject the connected Kobo from the operating system.

    On Windows uses the Shell COM 'Eject' verb — equivalent to right-click →
    Eject in File Explorer. The physical drive will unmount; the poller will
    then detect the disconnect automatically.

    Raises:
      RuntimeError – no Kobo connected
      OSError      – eject command failed
    """
    device = find_kobo()
    if device is None:
        raise RuntimeError("No Kobo device is currently connected")

    if sys.platform != "win32":
        raise OSError("Safe eject is only supported on Windows")

    import subprocess

    drive = device.mount_point.rstrip("\\/")
    script = (
        f"$shell = New-Object -comObject Shell.Application; "
        f"$shell.Namespace(17).ParseName('{drive}').InvokeVerb('Eject')"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise OSError(f"Eject failed: {result.stderr.strip() or 'unknown error'}")


def list_device_books() -> list[dict]:
    """
    Scan the connected Kobo for EPUB files and cross-reference with the library DB.

    Returns a list of dicts with keys:
      filename   – bare filename (e.g. "Dune.epub")
      path       – full path on the device
      in_library – True if the filename matches a book in the local DB
      book_id    – local DB id, or None
      title      – local DB title, or None
      author     – local DB author, or None
      cover_path – local cover URL, or None
    """
    device = find_kobo()
    if device is None:
        raise RuntimeError("No Kobo device is currently connected")

    from database import get_db

    mount = Path(device.mount_point)

    # Collect all EPUBs, skipping the .kobo system directory
    epub_paths = [
        p for p in mount.rglob("*.epub")
        if ".kobo" not in p.parts
    ]

    # Build a filename → book dict lookup from the local library
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, title, author, file_path, cover_path FROM books"
        ).fetchall()

    library_by_filename: dict[str, dict] = {}
    for row in rows:
        fname = Path(row["file_path"]).name
        library_by_filename[fname] = {
            "book_id":    row["id"],
            "title":      row["title"],
            "author":     row["author"],
            "cover_path": row["cover_path"],
        }

    result: list[dict] = []
    for ep in sorted(epub_paths, key=lambda p: p.name.lower()):
        fname = ep.name
        match = library_by_filename.get(fname)
        result.append({
            "filename":   fname,
            "path":       str(ep),
            "in_library": match is not None,
            "book_id":    match["book_id"]    if match else None,
            "title":      match["title"]      if match else None,
            "author":     match["author"]     if match else None,
            "cover_path": match["cover_path"] if match else None,
        })

    return result


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
