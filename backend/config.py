"""
Application configuration loaded from the .env file at project root.
All paths are resolved as pathlib.Path objects — never raw strings.
"""

import sys
from pathlib import Path
import os

from dotenv import load_dotenv

# In a frozen exe (PyInstaller), user data must live next to the .exe, not in
# the temp extraction dir (sys._MEIPASS). In dev mode, use the source root.
if getattr(sys, 'frozen', False):
    PROJECT_ROOT = Path(sys.executable).parent
else:
    PROJECT_ROOT = Path(__file__).parent.parent

load_dotenv(PROJECT_ROOT / ".env")


def _resolve_path(raw: str, default: Path) -> Path:
    """Expand env vars and make relative paths absolute against PROJECT_ROOT."""
    p = Path(os.path.expandvars(raw))
    return p if p.is_absolute() else PROJECT_ROOT / p


LIBRARY_PATH: Path = _resolve_path(
    os.getenv("LIBRARY_PATH", str(PROJECT_ROOT / "sample_library")),
    PROJECT_ROOT / "sample_library",
)

DATA_PATH: Path = _resolve_path(
    os.getenv("DATA_PATH", "./data"),
    PROJECT_ROOT / "data",
)

KOBO_BOOKS_FOLDER: str = os.getenv("KOBO_BOOKS_FOLDER", "")

PORT: int = int(os.getenv("PORT", "5000"))
DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

# Derived paths — always computed from DATA_PATH so one env var controls both
DB_PATH: Path = DATA_PATH / "library.db"
COVERS_PATH: Path = DATA_PATH / "covers"
