"""Where the app keeps its files.

The big files (page fonts, audio, the database built from the sources) live in one folder outside
the project, so a new copy of the project finds them and nothing is downloaded or built twice:

    ~/.local/share/quran-app/      (or the folder named by the QURAN_APP_DATA environment variable)
        fonts/  audio/  quran.db  user.db (bookmarks, settings)

The database is rebuilt, in about 30 seconds, only when what it is built from has changed.
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = ROOT / "data" / "sources"
DATA_DIR = Path(os.environ.get("QURAN_APP_DATA") or Path.home() / ".local" / "share" / "quran-app")
FONTS_DIR = DATA_DIR / "fonts"
AUDIO_DIR = DATA_DIR / "audio"
DATABASE_PATH = DATA_DIR / "quran.db"
USER_DB = DATA_DIR / "user.db"
_STAMP = DATA_DIR / "quran.db.stamp"

# The code the database is built by (tools/build_database.py and the modules it uses).
_BUILD_CODE = (
    ROOT / "tools" / "build_database.py",
    ROOT / "quran_app" / "arabic_text.py",
    ROOT / "quran_app" / "word_alignment.py",
    ROOT / "quran_app" / "page_layout.py",
)


def database_stamp():
    """A fingerprint of everything the database is built from."""
    digest = hashlib.sha256()
    for path in _BUILD_CODE:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    for path in sorted(SOURCES.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(SOURCES)).encode())
            digest.update(str(path.stat().st_size).encode())
    return digest.hexdigest()


def database_is_current():
    return DATABASE_PATH.exists() and _STAMP.exists() and _STAMP.read_text() == database_stamp()


def write_stamp():
    _STAMP.write_text(database_stamp())


def ensure_database():
    """Build the database if it is missing or out of date. Returns its path."""
    if not database_is_current():
        print("Building the database (about 30 seconds, only needed when it changes)...", file=sys.stderr, flush=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        _STAMP.unlink(missing_ok=True)
        subprocess.run([sys.executable, str(ROOT / "tools" / "build_database.py")], check=True)
    return DATABASE_PATH
