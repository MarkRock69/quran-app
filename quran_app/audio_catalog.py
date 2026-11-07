"""Where the recitations come from and where their files live. No Qt.

Source: everyayah.com, which keeps one mp3 per verse named SSSVVV.mp3 (chapter, verse, three
digits each) for each reciter and style, plus SSS000.mp3 for the basmala of a chapter, and a zip
of all of them (000_versebyverse.zip) that tools/fetch_audio.py downloads once.

On disk:  <audio folder, see paths.py>/<reciter>/<style>/SSSVVV.mp3
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

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
    Reciter("husary", "محمود خليل الحصري", {
        "murattal": Recording("Husary_128kbps", 2.0),
        "mujawwad": Recording("Husary_128kbps_Mujawwad", 3.0),
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


SPEED_MIN, SPEED_MAX = 0.25, 3.0
SPEED_PRESETS = (0.25, 0.33, 0.5, 0.67, 0.75, 1, 1.25, 1.33, 1.5, 1.67, 1.75, 2)


def speed_text(speed):
    """1.0 -> '1', 1.330 -> '1.33'."""
    return f"{speed:.2f}".rstrip("0").rstrip(".")


def parse_speed(text):
    """The playback speed typed in `text`, rounded to two decimals. Raises ValueError (message in Arabic)."""
    from .navigation import normalize_digits
    cleaned = normalize_digits(text.strip()).replace("\u066b", ".").replace(",", ".").replace("\u060c", ".")
    try:
        value = float(cleaned)
    except ValueError:
        raise ValueError("اكتب رقماً، مثل 1.25") from None
    value = round(value, 2)
    if not SPEED_MIN <= value <= SPEED_MAX:
        raise ValueError(f"السرعة من {speed_text(SPEED_MIN)} إلى {speed_text(SPEED_MAX)}")
    return value


class QueueItem(NamedTuple):
    chapter: int
    number: int  # 0 for the basmala of the chapter
    path: Path
    group: int  # the steps of "next" and "previous": a basmala, or one verse with all its repetitions
    pass_no: int = 0  # which playing of the whole passage (from 0)
    repeat: int = 0  # which repetition of the verse (from 0)


def build_queue(root, reciter_key, style, verses, basmala=True, verse_repeats=1, passage_repeats=1):
    """What to play for `verses`, a list of (chapter, verse number) in order: ([QueueItem, ...], missing).

    The whole passage is played `passage_repeats` times and each verse `verse_repeats` times in a row.
    A chapter's basmala file is put (once) before its first verse when the passage reaches that verse
    (not for chapters 1 and 9). Verses with no file on disk are left out and listed once in `missing`;
    a missing basmala is not reported.
    """
    items, missing, reported, group = [], [], set(), 0
    for pass_no in range(passage_repeats):
        for chapter, number in verses:
            if basmala and number == 1 and chapter not in NO_BASMALA:
                path = verse_path(root, reciter_key, style, chapter, 0)
                if path.exists():
                    items.append(QueueItem(chapter, 0, path, group, pass_no))
                    group += 1
            path = verse_path(root, reciter_key, style, chapter, number)
            if path.exists():
                items.extend(QueueItem(chapter, number, path, group, pass_no, repeat) for repeat in range(verse_repeats))
                group += 1
            elif (chapter, number) not in reported:
                reported.add((chapter, number))
                missing.append((chapter, number))
    return items, missing


def reposition(items, current):
    """Where in a rebuilt queue `items` the item `current` (from the old queue) belongs, so playback can carry on
    without a break after the repetition counts change. The same pass and repetition when they still exist,
    otherwise the nearest ones. None if the verse is no longer in the queue."""
    same = [(i, item) for i, item in enumerate(items) if (item.chapter, item.number) == (current.chapter, current.number)]
    if not same:
        return None
    last_pass = max(item.pass_no for _, item in same)
    pass_no = min(current.pass_no, last_pass)
    in_pass = [(i, item) for i, item in same if item.pass_no == pass_no]
    repeat = min(current.repeat, max(item.repeat for _, item in in_pass))
    return next(i for i, item in in_pass if item.repeat == repeat)


def queue_range(items):
    """((chapter, verse), (chapter, verse)): the first and last verse of a queue, basmalas ignored; None if empty."""
    verses = [(item.chapter, item.number) for item in items if item.number]
    return (verses[0], verses[-1]) if verses else None


def range_text(first, last, chapter_name, digits="indic"):
    """'البقرة: الآيات ٢٥٥ – ٢٦٠' within one chapter, 'من البقرة ٢٥٥ إلى آل عمران ١٠' across chapters."""
    from .numbers import format_number
    n = lambda value: format_number(value, digits)  # noqa: E731
    (c1, v1), (c2, v2) = first, last
    if c1 == c2:
        what = f"الآية {n(v1)}" if v1 == v2 else f"الآيات {n(v1)} – {n(v2)}"
        return f"{chapter_name(c1)}: {what}"
    return f"من {chapter_name(c1)} {n(v1)} إلى {chapter_name(c2)} {n(v2)}"


def parse_repeat(text, highest=99):
    """A repetition count typed in `text` (1 to `highest`, any digit style). Raises ValueError (message in Arabic)."""
    from .navigation import normalize_digits
    try:
        value = int(normalize_digits(text.strip()))
    except ValueError:
        value = 0
    if not 1 <= value <= highest:
        raise ValueError(f"أدخل عدداً من 1 إلى {highest}")
    return value


def next_index(items, index):
    """Where "next" goes from item `index`: the first item of the next group, or None at the end."""
    group = items[index].group
    for position in range(index + 1, len(items)):
        if items[position].group != group:
            return position
    return None


def previous_index(items, index):
    """Where "previous" goes: the start of the group before the current one (the start of the queue at the first)."""
    start = index
    while start > 0 and items[start - 1].group == items[index].group:
        start -= 1
    if start == 0:
        return 0
    before = start - 1
    while before > 0 and items[before - 1].group == items[start - 1].group:
        before -= 1
    return before


def playlist(root, reciter_key, style, verses, basmala=True):
    """Like build_queue, but just the paths."""
    items, missing = build_queue(root, reciter_key, style, verses, basmala)
    return [item.path for item in items], missing


def available(root):
    """{reciter key: [styles with downloaded files]}, only for what is on disk."""
    found = {}
    for item in RECITERS:
        styles = [
            style for style in item.recordings
            if next(folder(root, item.key, style).glob("[0-9][0-9][0-9][0-9][0-9][0-9].mp3"), None) is not None
        ]
        if styles:
            found[item.key] = styles
    return found
