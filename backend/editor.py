"""
EPUB editor — edits title, author, cover image, and strips OceanofPDF watermark
blocks.

All writes operate on the EPUB *as a ZIP archive*: only the entries that need
changing are transformed, every other entry is copied byte-for-byte, the result
is written to a temp file in the same directory, and the original is replaced
atomically only on success. This avoids the data-destruction failure mode of
ebooklib's whole-book `write_epub` (which truncates the target before a fragile
re-serialization that can fail on real-world EPUBs).
"""

import io
import os
import re
import shutil
import zipfile
from pathlib import Path
from typing import Callable

from lxml import etree
from PIL import Image

_SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}

# Namespaces used in the OPF package document.
_DC_NS = "http://purl.org/dc/elements/1.1/"
_OPF_NS = "http://www.idpf.org/2007/opf"
_CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"

# Match a <div>/<p> block that contains an oceanofpdf.com reference WITHOUT
# crossing into any nested block of the same type (the negative lookahead keeps
# the match isolated to the single watermark block, so surrounding content is
# left byte-for-byte untouched). DOTALL lets the block span multiple lines.
_OCEAN_DIV_RE = re.compile(
    r"<div\b(?:(?!</?div\b).)*?oceanofpdf\.com(?:(?!</?div\b).)*?</div\s*>",
    re.IGNORECASE | re.DOTALL,
)
_OCEAN_P_RE = re.compile(
    r"<p\b(?:(?!</?p\b).)*?oceanofpdf\.com(?:(?!</?p\b).)*?</p\s*>",
    re.IGNORECASE | re.DOTALL,
)

# transform(name, data) -> (new_data, changed)
Transform = Callable[[str, bytes], "tuple[bytes, bool]"]


# ---------------------------------------------------------------------------
# Safe ZIP-level rewrite core
# ---------------------------------------------------------------------------


def _rewrite_epub(book_path: Path, transform: Transform) -> int:
    """Rewrite an EPUB zip entry-by-entry, atomically and with a backup.

    `transform(name, data)` is called for every entry and must return
    `(possibly_modified_bytes, changed_flag)`. The new archive is written to a
    sibling temp file; only if it completes is a `.bak` copy made and the temp
    `os.replace`d over the original (atomic on the same volume). On any error the
    temp file is removed and the original is left untouched.

    Returns the number of entries reported as changed. If nothing changed, the
    original file is left exactly as-is (no rewrite, no backup).

    Raises FileNotFoundError if the EPUB does not exist.
    """
    if not book_path.exists():
        raise FileNotFoundError(f"EPUB not found: {book_path}")

    tmp_path = book_path.with_name(book_path.name + ".tmp")
    changed_count = 0

    try:
        with zipfile.ZipFile(book_path, "r") as zin:
            infos = zin.infolist()
            # Read everything first so a failure mid-stream can't touch the live
            # file (we only open the temp for writing after this succeeds).
            entries = [(info, zin.read(info.filename)) for info in infos]

        # Apply the transform, recording the new bytes per entry.
        new_entries: list[tuple[zipfile.ZipInfo, bytes]] = []
        for info, data in entries:
            new_data, changed = transform(info.filename, data)
            if changed:
                changed_count += 1
            else:
                new_data = data
            new_entries.append((info, new_data))

        if changed_count == 0:
            return 0

        # Write the new archive. `mimetype` must be the first entry and stored
        # uncompressed for the EPUB to be valid.
        with zipfile.ZipFile(tmp_path, "w") as zout:
            ordered = sorted(
                new_entries,
                key=lambda pair: 0 if pair[0].filename == "mimetype" else 1,
            )
            for info, data in ordered:
                if info.filename == "mimetype":
                    zout.writestr("mimetype", data, compress_type=zipfile.ZIP_STORED)
                else:
                    zout.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED)

        # Success: back up the original, then atomically swap in the new file.
        shutil.copy2(book_path, book_path.with_name(book_path.name + ".bak"))
        os.replace(tmp_path, book_path)
    except Exception:
        # Never leave a partial temp file behind, and never touch the original.
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    return changed_count


def _opf_path(book_path: Path) -> str:
    """Return the archive-internal path of the OPF package document."""
    with zipfile.ZipFile(book_path, "r") as z:
        container = z.read("META-INF/container.xml")
    root = etree.fromstring(container)
    rootfile = root.find(f".//{{{_CONTAINER_NS}}}rootfile")
    if rootfile is None or not rootfile.get("full-path"):
        raise ValueError("EPUB container.xml has no rootfile full-path")
    return rootfile.get("full-path")


# ---------------------------------------------------------------------------
# Public editors
# ---------------------------------------------------------------------------


def strip_oceanofpdf(book_path: Path) -> int:
    """Remove OceanofPDF watermark blocks from every (X)HTML content document.

    Targets <div>/<p> blocks containing an 'oceanofpdf.com' reference (the
    advertisement OceanofPDF injects into each chapter). All other entries —
    images, CSS, OPF, fonts — are preserved byte-for-byte. Writes a `.bak`
    backup and replaces the file atomically. Returns the total blocks removed.
    """
    total = 0

    def _transform(name: str, data: bytes) -> "tuple[bytes, bool]":
        nonlocal total
        if not name.lower().endswith((".xhtml", ".html", ".htm")):
            return data, False
        text = data.decode("utf-8", errors="surrogateescape")
        text, n_div = _OCEAN_DIV_RE.subn("", text)
        text, n_p = _OCEAN_P_RE.subn("", text)
        removed = n_div + n_p
        if not removed:
            return data, False
        total += removed
        return text.encode("utf-8", errors="surrogateescape"), True

    _rewrite_epub(book_path, _transform)
    return total


def write_metadata(book_path: Path, title: str | None, author: str | None) -> None:
    """Overwrite dc:title and/or dc:creator in the EPUB's OPF metadata.

    Edits only the OPF entry via lxml; all other entries are untouched.
    Writes a `.bak` backup and replaces the file atomically.
    """
    if title is None and author is None:
        return

    opf_name = _opf_path(book_path)

    def _transform(name: str, data: bytes) -> "tuple[bytes, bool]":
        if name != opf_name:
            return data, False

        root = etree.fromstring(data)
        metadata = root.find(f"{{{_OPF_NS}}}metadata")
        if metadata is None:
            # Some OPFs use an unprefixed/default-namespace metadata element.
            metadata = root.find("metadata")
        if metadata is None:
            raise ValueError("OPF has no <metadata> element")

        def _set(tag: str, value: str) -> None:
            el = metadata.find(f"{{{_DC_NS}}}{tag}")
            if el is None:
                el = etree.SubElement(metadata, f"{{{_DC_NS}}}{tag}")
            el.text = value

        if title is not None:
            _set("title", title)
        if author is not None:
            _set("creator", author)

        new_data = etree.tostring(
            root, xml_declaration=True, encoding="utf-8", standalone=True
        )
        return new_data, True

    _rewrite_epub(book_path, _transform)


def replace_cover(book_path: Path, image_path: Path) -> None:
    """Replace the cover image with a resized (max 600×900) JPEG of image_path.

    Resolves the existing cover entry from the OPF manifest and replaces its
    bytes in place. Writes a `.bak` backup and replaces the file atomically.

    Raises:
      FileNotFoundError – EPUB or source image missing
      ValueError        – unsupported image format, or no cover entry found
    """
    if not book_path.exists():
        raise FileNotFoundError(f"EPUB not found: {book_path}")

    img = Image.open(image_path)
    if img.format not in _SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported image format: {img.format!r}. Accepted: JPEG, PNG, WEBP."
        )

    img.thumbnail((600, 900))
    img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    jpeg_bytes = buf.getvalue()

    opf_name = _opf_path(book_path)
    cover_entry = _resolve_cover_entry(book_path, opf_name)
    if cover_entry is None:
        raise ValueError("No cover image found in EPUB to replace")

    def _transform(name: str, data: bytes) -> "tuple[bytes, bool]":
        if name != cover_entry:
            return data, False
        return jpeg_bytes, True

    _rewrite_epub(book_path, _transform)


def _resolve_cover_entry(book_path: Path, opf_name: str) -> str | None:
    """Return the archive-internal path of the cover image entry, or None.

    Priority: manifest item with properties="cover-image" → <meta name="cover">
    idref → manifest id/href containing 'cover' → first image item. Hrefs are
    resolved relative to the OPF document's directory.
    """
    with zipfile.ZipFile(book_path, "r") as z:
        opf_data = z.read(opf_name)
    root = etree.fromstring(opf_data)

    manifest = root.find(f"{{{_OPF_NS}}}manifest")
    if manifest is None:
        manifest = root.find("manifest")
    if manifest is None:
        return None

    items = manifest.findall(f"{{{_OPF_NS}}}item")
    if not items:
        items = manifest.findall("item")

    opf_dir = os.path.dirname(opf_name)

    def _resolve(href: str) -> str:
        joined = os.path.join(opf_dir, href) if opf_dir else href
        return os.path.normpath(joined).replace("\\", "/")

    # 1. properties="cover-image"
    for it in items:
        if "cover-image" in (it.get("properties") or ""):
            return _resolve(it.get("href", ""))

    # 2. <meta name="cover" content="<id>">
    metadata = root.find(f"{{{_OPF_NS}}}metadata") or root.find("metadata")
    cover_id = None
    if metadata is not None:
        for meta in metadata.findall(f"{{{_OPF_NS}}}meta") + metadata.findall("meta"):
            if meta.get("name") == "cover":
                cover_id = meta.get("content")
                break
    if cover_id:
        for it in items:
            if it.get("id") == cover_id:
                return _resolve(it.get("href", ""))

    # 3. id/href containing 'cover' among image items
    image_items = [
        it for it in items if (it.get("media-type") or "").startswith("image/")
    ]
    for it in image_items:
        hay = f"{it.get('id', '')} {it.get('href', '')}".lower()
        if "cover" in hay:
            return _resolve(it.get("href", ""))

    # 4. first image item
    if image_items:
        return _resolve(image_items[0].get("href", ""))

    return None
