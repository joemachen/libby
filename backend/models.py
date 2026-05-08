"""
Data model dataclasses for the application.
These are plain Python objects — no ORM, no database logic here.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Book:
    """Represents a single EPUB book in the library."""

    id: str                         # UUID from EPUB metadata or generated
    title: str
    file_path: str                  # Absolute path to the .epub file
    date_added: str                 # ISO 8601 timestamp

    author: Optional[str] = None
    publisher: Optional[str] = None
    language: Optional[str] = None
    description: Optional[str] = None
    cover_path: Optional[str] = None   # Path to extracted JPEG cover
    file_size: Optional[int] = None    # Bytes
    read_status: str = "unread"        # unread | reading | read

    def to_dict(self) -> dict:
        """Serialize to a plain dict safe for JSON responses."""
        return {
            "id": self.id,
            "title": self.title,
            "author": self.author,
            "publisher": self.publisher,
            "language": self.language,
            "description": self.description,
            "file_path": self.file_path,
            "cover_path": self.cover_path,
            "file_size": self.file_size,
            "date_added": self.date_added,
            "read_status": self.read_status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Book":
        """Construct a Book from a plain dict (e.g. a DB row converted to dict)."""
        return cls(
            id=data["id"],
            title=data["title"],
            file_path=data["file_path"],
            date_added=data["date_added"],
            author=data.get("author"),
            publisher=data.get("publisher"),
            language=data.get("language"),
            description=data.get("description"),
            cover_path=data.get("cover_path"),
            file_size=data.get("file_size"),
            read_status=data.get("read_status", "unread"),
        )


@dataclass
class Device:
    """Represents a detected removable storage device (e.g. Kobo e-reader)."""

    name: str           # Volume label
    mount_point: str    # Drive letter / mount path
    free_space: int     # Bytes available
    total_space: int    # Total bytes on device
    is_kobo: bool = False

    def to_dict(self) -> dict:
        """Serialize to a plain dict safe for JSON responses."""
        return {
            "name": self.name,
            "mount_point": self.mount_point,
            "free_space": self.free_space,
            "total_space": self.total_space,
            "is_kobo": self.is_kobo,
        }
