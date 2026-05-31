"""
EPUB metadata writer — edits title, author, cover image, and strips
OceanofPDF watermark blocks, all in-place.
"""

import io
import re
import shutil
from pathlib import Path

import ebooklib
from ebooklib import epub
from PIL import Image

_SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP"}

# After epub.read_epub(), metadata is keyed by full namespace URI, not the "DC" alias.
_DC_URI = "http://purl.org/dc/elements/1.1/"

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


def strip_oceanofpdf(book_path: Path) -> int:
    """Remove OceanofPDF watermark blocks from every content document, in place.

    Targets <div>/<p> blocks containing an 'oceanofpdf.com' reference (the
    advertisement OceanofPDF injects into each chapter). Bytes outside a matched
    block are preserved exactly via surrogateescape round-tripping.

    Creates a backup at book_path + '.bak' before modifying (only when at least
    one block is found). Returns the total number of blocks removed.
    Raises FileNotFoundError if the EPUB does not exist.
    """
    if not book_path.exists():
        raise FileNotFoundError(f"EPUB not found: {book_path}")

    book = epub.read_epub(str(book_path), options={"ignore_ncx": True})
    total = 0

    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        text = item.get_content().decode("utf-8", errors="surrogateescape")
        text, n_div = _OCEAN_DIV_RE.subn("", text)
        text, n_p = _OCEAN_P_RE.subn("", text)
        removed = n_div + n_p
        if removed:
            item.set_content(text.encode("utf-8", errors="surrogateescape"))
            total += removed

    if total:
        shutil.copy2(book_path, Path(str(book_path) + ".bak"))
        epub.write_epub(str(book_path), book)

    return total


def write_metadata(book_path: Path, title: str | None, author: str | None) -> None:
    """Overwrite dc:title and dc:creator in the EPUB's OPF metadata."""
    if not book_path.exists():
        raise FileNotFoundError(f"EPUB not found: {book_path}")

    book = epub.read_epub(str(book_path), options={"ignore_ncx": True})
    dc = book.metadata.setdefault(_DC_URI, {})

    if title is not None:
        dc["title"] = [(title, {})]

    if author is not None:
        dc["creator"] = [(author, {})]

    epub.write_epub(str(book_path), book)


def replace_cover(book_path: Path, image_path: Path) -> None:
    """Replace the cover image item in the EPUB with a resized version of image_path.
    Resize to max 600×900 px (preserve aspect ratio), save as JPEG.
    Creates a backup at book_path + '.bak' before modifying."""
    if not book_path.exists():
        raise FileNotFoundError(f"EPUB not found: {book_path}")

    img = Image.open(image_path)
    if img.format not in _SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported image format: {img.format!r}. Accepted: JPEG, PNG, WEBP."
        )

    backup_path = Path(str(book_path) + ".bak")
    shutil.copy2(book_path, backup_path)

    img.thumbnail((600, 900))
    img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85)
    jpeg_bytes = buf.getvalue()

    book = epub.read_epub(str(book_path), options={"ignore_ncx": True})
    cover_item = _find_cover_item(book)

    if cover_item is not None:
        cover_item.set_content(jpeg_bytes)
        cover_item.media_type = "image/jpeg"
    else:
        new_item = epub.EpubItem(
            uid="cover-image",
            file_name="images/cover.jpg",
            media_type="image/jpeg",
            content=jpeg_bytes,
        )
        new_item.properties = ["cover-image"]
        book.add_item(new_item)

    epub.write_epub(str(book_path), book)


def _find_cover_item(epub_book: epub.EpubBook):
    """Locate the cover image item using three strategies in priority order."""
    # ITEM_COVER = items with properties=["cover-image"]; ITEM_IMAGE = plain image items
    images = (
        list(epub_book.get_items_of_type(ebooklib.ITEM_IMAGE))
        + list(epub_book.get_items_of_type(ebooklib.ITEM_COVER))
    )
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
