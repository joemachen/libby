"""
Unit tests for editor.py — EPUB metadata writing.
Run with: python -m pytest tests/test_editor.py -v
"""

import io
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_epub(path: Path, title: str = "Test Book", author: str = "Test Author") -> Path:
    """Create a minimal valid EPUB3 at path and return path."""
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(title)
    book.add_author(author)
    book.set_language("en")

    chapter = epub.EpubHtml(title="Ch1", file_name="chap_01.xhtml", lang="en")
    chapter.set_content(f"<html><body><h1>{title}</h1></body></html>")
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]

    epub.write_epub(str(path), book)
    return path


def _make_cover_epub(path: Path, title: str = "Covered Book") -> Path:
    """Create a minimal EPUB that includes a cover image item."""
    from ebooklib import epub
    from PIL import Image

    book = epub.EpubBook()
    book.set_identifier(str(uuid.uuid4()))
    book.set_title(title)
    book.add_author("Cover Author")
    book.set_language("en")

    # Build a small JPEG cover
    img = Image.new("RGB", (200, 300), color=(80, 40, 120))
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    cover_item = epub.EpubItem(
        uid="cover-image",
        file_name="images/cover.jpg",
        media_type="image/jpeg",
        content=buf.getvalue(),
    )
    cover_item.properties = ["cover-image"]
    book.add_item(cover_item)

    chapter = epub.EpubHtml(title="Ch1", file_name="chap_01.xhtml", lang="en")
    chapter.set_content("<html><body><h1>Covered</h1></body></html>")
    book.add_item(chapter)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ["nav", chapter]

    epub.write_epub(str(path), book)
    return path


def _make_image_file(path: Path, width: int, height: int, fmt: str = "JPEG") -> Path:
    """Save a solid-colour PIL image to path in the given format."""
    from PIL import Image

    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    img.save(str(path), fmt)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWriteMetadata(unittest.TestCase):

    def test_write_metadata_updates_title(self):
        """write_metadata overwrites the dc:title in the EPUB."""
        from ebooklib import epub
        from editor import write_metadata

        with tempfile.TemporaryDirectory() as tmp:
            epub_path = _make_epub(Path(tmp) / "book.epub", title="Old Title")
            write_metadata(epub_path, title="New Title", author=None)

            book = epub.read_epub(str(epub_path), options={"ignore_ncx": True})
            titles = book.get_metadata("DC", "title")
            self.assertTrue(titles, "No DC:title found after write_metadata")
            self.assertEqual(titles[0][0], "New Title")

    def test_write_metadata_updates_author(self):
        """write_metadata overwrites the dc:creator in the EPUB."""
        from ebooklib import epub
        from editor import write_metadata

        with tempfile.TemporaryDirectory() as tmp:
            epub_path = _make_epub(Path(tmp) / "book.epub", author="Old Author")
            write_metadata(epub_path, title=None, author="New Author")

            book = epub.read_epub(str(epub_path), options={"ignore_ncx": True})
            creators = book.get_metadata("DC", "creator")
            self.assertTrue(creators, "No DC:creator found after write_metadata")
            self.assertEqual(creators[0][0], "New Author")

    def test_write_metadata_creates_no_backup(self):
        """write_metadata does NOT create a .bak file."""
        from editor import write_metadata

        with tempfile.TemporaryDirectory() as tmp:
            epub_path = _make_epub(Path(tmp) / "book.epub")
            write_metadata(epub_path, title="Changed", author=None)

            bak = Path(str(epub_path) + ".bak")
            self.assertFalse(bak.exists(), "Unexpected .bak file created by write_metadata")


class TestReplaceCover(unittest.TestCase):

    def test_replace_cover_creates_backup(self):
        """replace_cover creates a .bak copy before modifying the EPUB."""
        from editor import replace_cover

        with tempfile.TemporaryDirectory() as tmp:
            epub_path = _make_cover_epub(Path(tmp) / "book.epub")
            img_path = _make_image_file(Path(tmp) / "cover.jpg", 300, 450)

            replace_cover(epub_path, img_path)

            bak = Path(str(epub_path) + ".bak")
            self.assertTrue(bak.exists(), ".bak backup not created by replace_cover")
            self.assertGreater(bak.stat().st_size, 0)

    def test_replace_cover_resizes_large_image(self):
        """replace_cover resizes an oversized image to fit within 600×900."""
        from ebooklib import epub
        from editor import replace_cover, _find_cover_item
        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            epub_path = _make_cover_epub(Path(tmp) / "book.epub")
            # 2000×3000 is larger than 600×900 in both dimensions
            img_path = _make_image_file(Path(tmp) / "big.jpg", 2000, 3000)

            replace_cover(epub_path, img_path)

            book = epub.read_epub(str(epub_path), options={"ignore_ncx": True})
            item = _find_cover_item(book)
            self.assertIsNotNone(item, "No cover item found in EPUB after replace_cover")

            result_img = Image.open(io.BytesIO(item.get_content()))
            w, h = result_img.size
            self.assertLessEqual(w, 600, f"Cover width {w} exceeds 600px")
            self.assertLessEqual(h, 900, f"Cover height {h} exceeds 900px")

    def test_replace_cover_raises_for_unsupported_format(self):
        """replace_cover raises ValueError for unsupported image formats (e.g. BMP)."""
        from editor import replace_cover

        with tempfile.TemporaryDirectory() as tmp:
            epub_path = _make_cover_epub(Path(tmp) / "book.epub")

            from PIL import Image
            bmp_path = Path(tmp) / "cover.bmp"
            Image.new("RGB", (100, 100)).save(str(bmp_path), "BMP")

            with self.assertRaises(ValueError):
                replace_cover(epub_path, bmp_path)

    def test_replace_cover_raises_for_missing_book(self):
        """replace_cover raises FileNotFoundError when the EPUB path doesn't exist."""
        from editor import replace_cover

        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nonexistent.epub"
            img_path = _make_image_file(Path(tmp) / "cover.jpg", 200, 300)

            with self.assertRaises(FileNotFoundError):
                replace_cover(missing, img_path)


if __name__ == "__main__":
    unittest.main()
