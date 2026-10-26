"""Shared test setup: build the database once and reuse it across test files."""

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_folder = None
_path = None


def database_path():
    """Path of a freshly built database, built on first use."""
    global _folder, _path
    if _path is None:
        _folder = tempfile.TemporaryDirectory()
        _path = Path(_folder.name) / "quran.db"
        subprocess.run(
            [sys.executable, "-I", str(ROOT / "tools" / "build_database.py"), "--output", str(_path)],
            check=True,
            capture_output=True,
        )
    return _path
