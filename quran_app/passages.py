"""A passage to play: from one unit to another, where a unit is a verse, chapter, juz', hizb, rub' or page.

    verse     2:255 to 3:10          (a passage can cross chapters)
    chapter   2 to 4                  juz'  30        hizb  1 to 2        rub'  5        page  50 to 52

"To" left empty means the same unit as "from". No Qt.
"""

from typing import NamedTuple

from .navigation import KINDS, parse_jump

PASSAGE_KINDS = {"verse": "آية", "chapter": "سورة", "juz": "جزء", "hizb": "حزب", "rub": "ربع", "page": "صفحة"}
LAST_VERSE_ID = 6236


class Passage(NamedTuple):
    first: int  # verse ids, in reading order, both included
    last: int
    verses: tuple  # ((chapter, number), ...)


def _unit(connection, kind, text):
    """(first verse id, last verse id) of the unit that `text` names."""
    if kind == "verse":
        parsed = parse_jump(text, "chapter")
        if parsed[0] != "verse":
            raise ValueError("اكتب السورة:الآية، مثل ٢:٢٥٥")
        _, chapter, number = parsed
        row = connection.execute("SELECT id FROM verses WHERE chapter = ? AND number = ?", (chapter, number)).fetchone()
        if row is None:
            raise ValueError(f"لا توجد الآية {chapter}:{number}")
        return row[0], row[0]
    parsed = parse_jump(text, kind)
    if parsed[0] != kind:
        raise ValueError(f"اكتب رقم {KINDS[kind][2]} فقط")
    n = parsed[1]
    if kind == "chapter":
        return (connection.execute("SELECT id FROM verses WHERE chapter = ? AND number = 1", (n,)).fetchone()[0],
                connection.execute("SELECT MAX(id) FROM verses WHERE chapter = ?", (n,)).fetchone()[0])
    if kind == "page":
        return connection.execute("SELECT MIN(id), MAX(id) FROM verses WHERE page = ?", (n,)).fetchone()
    table, units = ("juz", 30) if kind == "juz" else ("rubs", 240)
    first_row, last_row = ((n - 1) * 4 + 1, n * 4) if kind == "hizb" else (n, n)  # a hizb is four rub's
    first = connection.execute(f"SELECT first_verse_id FROM {table} WHERE id = ?", (first_row,)).fetchone()[0]
    if last_row == units:
        return first, LAST_VERSE_ID
    following = connection.execute(f"SELECT first_verse_id FROM {table} WHERE id = ?", (last_row + 1,)).fetchone()[0]
    return first, following - 1


def resolve(connection, kind, first_text, last_text=""):
    """The Passage from `first_text` to `last_text` (or to the end of the same unit). Raises ValueError in Arabic."""
    if kind not in PASSAGE_KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    first = _unit(connection, kind, first_text)[0]
    end = first_text if not last_text.strip() else last_text
    last = _unit(connection, kind, end)[1]
    if last < first:
        raise ValueError("النهاية قبل البداية")
    verses = tuple(connection.execute(
        "SELECT chapter, number FROM verses WHERE id BETWEEN ? AND ? ORDER BY id", (first, last)))
    return Passage(first, last, verses)
