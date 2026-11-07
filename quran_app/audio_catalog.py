"""Where the recitations come from and where their files live. No Qt.

Source: everyayah.com, which keeps one mp3 per verse named SSSVVV.mp3 (chapter, verse, three
digits each) for each reciter and style, plus SSS000.mp3 for the basmala of a chapter, and a zip
of all of them (000_versebyverse.zip) that tools/fetch_audio.py downloads once.

On disk:  data/audio/<reciter>/<style>/SSSVVV.mp3
"""

import re
from dataclasses import dataclass
from pathlib import Path

BASE_URL = "https://everyayah.com/data"
ZIP_NAME = "000_versebyverse.zip"
CHECKSUM_NAME = "000_checksum.md5"
NO_BASMALA = (1, 9)  # chapter 1 has it as its first verse; chapter 9 has none


@dataclass(frozen=True)
class Recording:
    folder: str  # on everyayah.com
    size_gb: float  # of the zip, as listed there


@dataclass(frozen=True)
class Reciter:
    key: str
    name_ar: str
    recordings: dict  # style ('murattal' or 'mujawwad') -> Recording


RECITERS = (
    Reciter("minshawi", "محمد صديق المنشاوي", {
        "murattal": Recording("Minshawy_Murattal_128kbps", 1.0),
        "mujawwad": Recording("Minshawy_Mujawwad_192kbps", 4.0),
    }),
    Reciter("jabir", "علي بن عبد الله جابر", {
        "murattal": Recording("Ali_Jaber_64kbps", 0.7),
    }),
    Reciter("abdulbasit", "عبد الباسط عبد الصمد", {
        "murattal": Recording("Abdul_Basit_Murattal_192kbps", 2.0),
        "mujawwad": Recording("Abdul_Basit_Mujawwad_128kbps", 3.0),
    }),
)
STYLE_NAMES = {"murattal": "مرتل", "mujawwad": "مجوّد"}
_FILE = re.compile(r"^(\d{3})(\d{3})\.mp3$")


def reciter(key):
    for item in RECITERS:
        if item.key == key:
            return item
    raise KeyError(key)


def file_name(chapter, number):
    """SSSVVV.mp3; verse 0 is the basmala of the chapter."""
    return f"{chapter:03d}{number:03d}.mp3"


def folder(root, reciter_key, style):
    return Path(root) / reciter_key / style


def verse_path(root, reciter_key, style, chapter, number):
    return folder(root, reciter_key, style) / file_name(chapter, number)


def flat_name(member):
    """The SSSVVV.mp3 name of a zip member wherever it sits in the zip, or None if it is not a verse file."""
    name = member.replace("\\", "/").rsplit("/", 1)[-1]
    return name if _FILE.match(name) else None


def parse_md5(text):
    """{file name: md5} from a `md5sum` style file: 'hash  name' or 'hash *name' per line."""
    result = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and re.fullmatch(r"[0-9a-fA-F]{32}", parts[0]):
            result[parts[1].lstrip("*").replace("\\", "/").rsplit("/", 1)[-1]] = parts[0].lower()
    return result


def playlist(root, reciter_key, style, verses, basmala=True):
    """The files to play for `verses`, a list of (chapter, verse number) in order.

    A chapter's basmala file is put before its first verse when that verse is reached from the
    start of the chapter (not for chapters 1 and 9). Verses with no file on disk are left out
    and returned in the second list.
    """
    paths, missing = [], []
    for chapter, number in verses:
        wanted = []
        if basmala and number == 1 and chapter not in NO_BASMALA:
            wanted.append((chapter, 0))
        wanted.append((chapter, number))
        for item in wanted:
            path = verse_path(root, reciter_key, style, *item)
            if path.exists():
                paths.append(path)
            elif item[1] != 0:  # a missing basmala is not worth reporting
                missing.append(item)
    return paths, missing
