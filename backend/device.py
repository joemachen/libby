"""
E-reader device detection and EPUB file transfer.

Supports any USB mass-storage device that natively reads EPUB files.
Detection tries each registered device profile in order; the first whose
marker directory exists on a mounted partition wins.

Supported devices
-----------------
  kobo       – Kobo e-readers      (.kobo/ marker)
  pocketbook – PocketBook readers  (.adds/ marker)
  tolino     – Tolino readers      (.tolino/ marker)
  boox       – ONYX Boox readers   (Android/ marker)

Explicitly excluded (no native EPUB / non-mass-storage):
  Kindle    – requires format conversion (MOBI/AZW)
  reMarkable – uses USB network / MTP, not mass storage
"""

import shutil
import sys
from pathlib import Path

import psutil

import config
from models import Device


# ---------------------------------------------------------------------------
# Device profile registry
# ---------------------------------------------------------------------------

# Profiles are checked in insertion order — put the most-specific markers first
# to avoid false positives (e.g. Boox "Android/" is the broadest marker).
DEVICE_PROFILES: dict[str, dict] = {
    "kobo": {
        "display_name": "Kobo",
        "markers":      [".kobo"],
        "label_hints":  ["KOBOeReader", "KOBO"],
        "system_dirs":  {".kobo"},
    },
    "pocketbook": {
        "display_name": "PocketBook",
        "markers":      [".adds"],
        "label_hints":  ["PocketBook", "PB"],
        "system_dirs":  {".adds", "System", "thumbnails"},
    },
    "tolino": {
        "display_name": "Tolino",
        "markers":      [".tolino"],
        "label_hints":  ["tolino"],
        "system_dirs":  {".tolino"},
    },
    "boox": {
        "display_name": "ONYX Boox",
        "markers":      ["Android"],
        "label_hints":  ["BOOX", "Onyx"],
        "system_dirs":  {"Android", ".android_secure", "DCIM", "Movies", "Music", "Pictures"},
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def find_device() -> Device | None:
    """
    Scan all mounted partitions for a supported e-reader device.

    Tries each profile in DEVICE_PROFILES order; the first mount that
    contains one of the profile's marker directories wins.
    Returns a populated Device or None if no device is found.
    """
    for part in psutil.disk_partitions(all=False):
        mount = Path(part.mountpoint)
        if not mount.exists():
            continue

        for device_type, profile in DEVICE_PROFILES.items():
            if any((mount / m).exists() for m in profile["markers"]):
                return _build_device(mount, part, device_type, profile)

    return None


def get_status() -> dict:
    """
    Return current device connection status.
    Result: {"connected": bool, "device": Device.to_dict() | None}
    """
    device = find_device()
    return {"connected": device is not None, "device": device.to_dict() if device else None}


def eject_device() -> None:
    """
    Safely eject the connected device from the operating system.

    On Windows uses the Shell COM 'Eject' verb — equivalent to right-click
    → Eject in File Explorer. Works for any USB device, not just Kobo.

    Raises:
      RuntimeError – no device connected
      OSError      – not Windows, or eject command failed
    """
    device = find_device()
    if device is None:
        raise RuntimeError("No e-reader device is currently connected")

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
    Scan the connected device for EPUB files and cross-reference with the library DB.

    System directories specific to the detected device type are skipped
    (e.g. .kobo/ for Kobo, .adds/ for PocketBook, Android/ for Boox).

    Returns a list of dicts with keys:
      filename   – bare filename (e.g. "Dune.epub")
      path       – full path on the device
      in_library – True if the filename matches a book in the local DB
      book_id    – local DB id, or None
      title      – local DB title, or None
      author     – local DB author, or None
      cover_path – local cover URL, or None
    """
    device = find_device()
    if device is None:
        raise RuntimeError("No e-reader device is currently connected")

    from database import get_db

    mount = Path(device.mount_point)

    # Get the system dirs to skip for this device type
    profile = DEVICE_PROFILES.get(device.device_type, {})
    system_dirs: set[str] = profile.get("system_dirs", set())

    # Collect all EPUBs, skipping device system directories
    epub_paths = [
        p for p in mount.rglob("*.epub")
        if not system_dirs.intersection(p.parts)
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
    Copy an EPUB file to the connected device.

    The destination folder on the device is controlled by the
    DEVICE_BOOKS_FOLDER config value (env var). If empty, files are
    copied to the device root.

    Returns {"bytes_transferred": int, "destination": str}.
    Raises:
      FileNotFoundError – source file missing
      RuntimeError     – no device connected
      OSError          – insufficient space or copy failure
    """
    if not book_path.exists():
        raise FileNotFoundError(f"Source file not found: {book_path}")

    device = find_device()
    if device is None:
        raise RuntimeError("No e-reader device is currently connected")

    file_size = book_path.stat().st_size
    if file_size > device.free_space:
        raise OSError(
            f"Insufficient space on device "
            f"({fmt_bytes(file_size)} needed, {fmt_bytes(device.free_space)} free)"
        )

    mount = Path(device.mount_point)
    folder = config.DEVICE_BOOKS_FOLDER.strip()
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


def _build_device(mount: Path, partition, device_type: str, profile: dict) -> Device:
    """Construct a Device from a psutil partition object and a profile dict."""
    try:
        usage = psutil.disk_usage(str(mount))
        free, total = usage.free, usage.total
    except OSError:
        free = total = 0

    # Use the Windows volume label when available; fall back to the
    # profile's display name so we always show something meaningful.
    label = profile["display_name"]
    if sys.platform == "win32":
        label = _win_label(partition.mountpoint) or label

    return Device(
        name=label,
        mount_point=partition.mountpoint,
        free_space=free,
        total_space=total,
        device_type=device_type,
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
