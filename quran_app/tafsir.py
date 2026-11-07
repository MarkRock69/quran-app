"""Tafsir and translation texts for a verse. No Qt.

The six sources, in the tab order: المختصر, الميسر, Sahih International, The Clear Qur'an
(reserved, no download exists, so it is listed as unavailable), إعراب القرآن, التحرير والتنوير.
A text often covers several verses; it is shown for each of them, with its range.
"""

import re
from dataclasses import dataclass
from html import escape
from typing import Optional

_PAGE_NUMBER = re.compile(r'<p class="page-num">.*?</p>', re.S)
_EMPTY_PARAGRAPH = re.compile(r"<p>\s*</p>")
_FOOTNOTE = re.compile(r"\[\[(.*?)\]\]", re.S)

CLEAR_QURAN_ORDER = 4


@dataclass(frozen=True)
class Source:
    id: int  # 0 for a source that is not available
    key: str
    title: str
    rtl: bool
    available: bool


@dataclass(frozen=True)
class Entry:
    source: Source
    first: tuple  # (chapter, verse) the text begins at
    last: tuple
    html: str


def body_to_html(key, body):
    """The stored text as simple HTML for a text browser."""
    if key == "sahih":
        parts = _FOOTNOTE.split(body)  # text, note, text, note, ..., text
        notes = [note.strip() for note in parts[1::2]]
        text = "".join(
            escape(piece) + (f"<sup>{i}</sup>" if i <= len(notes) else "")
            for i, piece in enumerate(parts[0::2], 1)
        )
        out = f"<p>{text}</p>"
        if notes:
            out += "<hr>" + "".join(f"<p><sup>{i}</sup> {escape(note)}</p>" for i, note in enumerate(notes, 1))
        return out
    if "<p" in body or "<div" in body:
        return _EMPTY_PARAGRAPH.sub("", _PAGE_NUMBER.sub("", body))
    return "".join(f"<p>{escape(line)}</p>" for line in body.split("\n") if line.strip())


def sources(connection):
    rows = list(
        connection.execute("SELECT id, key, title, language, sort_order FROM text_sources ORDER BY sort_order")
    )
    result = [Source(i, key, title, language == "ar", True) for i, key, title, language, _ in rows]
    clear = Source(0, "clear", "The Clear Qur'an", False, False)
    position = sum(1 for *_, order in rows if order < CLEAR_QURAN_ORDER)
    result.insert(position, clear)
    return result


def entry(connection, source, chapter, number) -> Optional[Entry]:
    """The text of `source` for a verse, or None if it has nothing on it."""
    if not source.available:
        return None
    row = connection.execute(
        "SELECT v1.chapter, v1.number, v2.chapter, v2.number, g.body"
        " FROM text_group_of_verse m"
        " JOIN text_groups g ON g.id = m.group_id"
        " JOIN verses v1 ON v1.id = g.first_verse_id JOIN verses v2 ON v2.id = g.last_verse_id"
        " WHERE m.source_id = ? AND m.verse_id = (SELECT id FROM verses WHERE chapter = ? AND number = ?)",
        (source.id, chapter, number),
    ).fetchone()
    if row is None:
        return None
    return Entry(source, (row[0], row[1]), (row[2], row[3]), body_to_html(source.key, row[4]))
