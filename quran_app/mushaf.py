"""The Mushaf pages: what is drawn where, and how a selection becomes text.

Nothing here depends on Qt, so all of it can be tested without a window. The
window (`reader.py`) only measures glyphs and paints what this module places.

A page is a list of lines. A text line is a row of cells; a cell is one word as
the page font draws it (with its stop sign, if any) or a verse-end marker. Cells
carry the verse and the word numbers they stand for, which is what makes
selecting and copying produce the real Uthmani text instead of font glyphs.
"""

import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from typing import Optional

from .index_lists import chapter_index, rub_index
from . import tafsir
from .passages import resolve
from .navigation import KINDS, Jump, parse_jump
from .numbers import format_number
from .page_header import PageInfo, rub_progress

PAGE_COUNT = 604

# Ornate parentheses written around a verse number when copying.
_PAREN_OPEN = chr(0xFD3F)
_PAREN_CLOSE = chr(0xFD3E)


@dataclass(frozen=True)
class Cell:
    glyph_id: int  # position in reading order over the whole Mushaf
    verse_id: int
    chapter: int
    number: int  # verse number in its chapter
    first_word: Optional[int]  # None for a verse-end marker
    last_word: Optional[int]
    text: str  # what to draw in the page font

    @property
    def is_verse_end(self):
        return self.first_word is None


@dataclass(frozen=True)
class Line:
    number: int
    kind: str  # 'text', 'chapter_name' or 'basmala'
    centered: bool
    chapter: Optional[int]
    cells: tuple


@dataclass(frozen=True)
class Page:
    number: int
    lines: tuple

    @property
    def cells(self):
        return tuple(cell for line in self.lines for cell in line.cells)


def spread_of(page):
    """The pages shown together when the book is open at `page`.

    The book is read right to left, as in the printed Mushaf: the first spread
    is page 1 on the right and page 2 on the left, then 3 on the right and 4
    on the left, and so on up to 603 and 604. The right page is always odd and
    comes first. Returns (left, right).
    """
    if not 1 <= page <= PAGE_COUNT:
        raise ValueError(f"no page {page}")
    right = page if page % 2 == 1 else page - 1
    return (right + 1, right)


class Mushaf:
    """Pages and verse text, read from the database built by tools/build_database.py."""

    def __init__(self, database_path):
        self._connection = sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
        self._verses = {
            row[0]: row[1:]
            for row in self._connection.execute("SELECT id, chapter, number FROM verses")
        }
        self._chapter_names = dict(self._connection.execute("SELECT id, name_ar FROM chapters"))
        self._verse_counts = dict(self._connection.execute("SELECT id, verse_count FROM chapters"))
        self._words = lru_cache(maxsize=512)(self._load_words)

    def close(self):
        self._connection.close()

    def chapter_name(self, chapter):
        return self._chapter_names[chapter]

    def verse_count(self, chapter):
        return self._verse_counts[chapter]

    @lru_cache(maxsize=64)
    def page(self, number):
        if not 1 <= number <= PAGE_COUNT:
            raise ValueError(f"no page {number}")
        by_line = {}
        for glyph_id, line, verse_id, first, last, text in self._connection.execute(
            "SELECT id, line, verse_id, first_word, last_word, text FROM glyphs"
            " WHERE page = ? ORDER BY line, slot",
            (number,),
        ):
            chapter, verse_number = self._verses[verse_id]
            by_line.setdefault(line, []).append(
                Cell(glyph_id, verse_id, chapter, verse_number, first, last, text)
            )
        lines = tuple(
            Line(line, kind, bool(centered), chapter, tuple(by_line.get(line, ())))
            for line, kind, centered, chapter in self._connection.execute(
                "SELECT line, kind, centered, chapter FROM page_lines WHERE page = ? ORDER BY line",
                (number,),
            )
        )
        return Page(number, lines)

    @lru_cache(maxsize=64)
    def page_info(self, number):
        """Juz', chapter and rub' mark for the heading of a page."""
        first = self.page(number).cells[0]
        (juz,) = self._connection.execute("SELECT juz FROM verses WHERE id = ?", (first.verse_id,)).fetchone()
        rub = self._connection.execute(
            "SELECT hizb, position_in_hizb FROM rubs WHERE start_page = ?", (number,)
        ).fetchone()
        progress = rub_progress(*rub) if rub else None
        return PageInfo(juz, first.chapter, *(progress or (None, None)))

    def chapter_index(self):
        """Bands and rows of the chapter list (see index_lists.py)."""
        return chapter_index(self._connection)

    def rub_index(self):
        """Bands and rows of the rub' list (see index_lists.py)."""
        return rub_index(self._connection)

    def passage(self, kind, first_text, last_text=""):
        """The verses of a passage to play (see passages.py). Raises ValueError, message in Arabic."""
        return resolve(self._connection, kind, first_text, last_text)

    def tafsir_sources(self):
        return tafsir.sources(self._connection)

    def tafsir_entry(self, source, chapter, number):
        return tafsir.entry(self._connection, source, chapter, number)

    def verse_of_glyph(self, glyph_id):
        """(chapter, verse number) of the verse a page glyph belongs to."""
        return self._connection.execute(
            "SELECT v.chapter, v.number FROM glyphs g JOIN verses v ON v.id = g.verse_id WHERE g.id = ?",
            (glyph_id,),
        ).fetchone()

    def first_verse_of_page(self, page):
        cell = self.page(page).cells[0]
        return cell.chapter, cell.number

    def jump(self, kind, text):
        """Where typed text leads: a `Jump` (page, and the verse if one was asked for).
        `kind` is 'page', 'chapter', 'juz', 'hizb' or 'rub'. Raises ValueError, message in Arabic."""
        kind, first, second = parse_jump(text, kind)
        if kind == "verse":
            (count,) = self._connection.execute("SELECT verse_count FROM chapters WHERE id = ?", (first,)).fetchone()
            if not 1 <= second <= count:
                raise ValueError(f"{self.chapter_name(first)}: الآيات من {format_number(1)} إلى {format_number(count)}")
            return Jump(self.page_of_verse(first, second), (first, second))
        if kind == "page":
            return Jump(first, None)
        table, key = {
            "chapter": ("chapters", first),
            "juz": ("juz", first),
            "hizb": ("rubs", (first - 1) * 4 + 1),
            "rub": ("rubs", first),
        }[kind]
        (page,) = self._connection.execute(f"SELECT start_page FROM {table} WHERE id = ?", (key,)).fetchone()
        return Jump(page, None)

    def page_of_verse(self, chapter, number):
        row = self._connection.execute(
            "SELECT page FROM verses WHERE chapter = ? AND number = ?", (chapter, number)
        ).fetchone()
        if row is None:
            raise ValueError(f"no verse {chapter}:{number}")
        return row[0]

    def verse_cells(self, chapter, number):
        """The cells of one verse, wherever they are on its pages."""
        rows = self._connection.execute(
            "SELECT g.id FROM glyphs g JOIN verses v ON v.id = g.verse_id"
            " WHERE v.chapter = ? AND v.number = ? ORDER BY g.id",
            (chapter, number),
        ).fetchall()
        return (rows[0][0], rows[-1][0]) if rows else None

    # ---------------------------------------------------------------- copying

    def _load_words(self, verse_id):
        return dict(
            self._connection.execute(
                "SELECT position, text_uthmani FROM words WHERE verse_id = ?", (verse_id,)
            )
        )

    def text_between(self, first_glyph_id, last_glyph_id, digits="indic"):
        """The Uthmani text of every cell from one glyph to another, inclusive.

        Words keep their stop signs; a verse-end marker becomes the verse number
        in ornate parentheses. A word the page draws as two glyphs is written once.
        """
        low, high = sorted((first_glyph_id, last_glyph_id))
        rows = self._connection.execute(
            "SELECT verse_id, first_word, last_word FROM glyphs WHERE id BETWEEN ? AND ?"
            " ORDER BY id",
            (low, high),
        ).fetchall()
        pieces = []
        written = set()
        for verse_id, first, last in rows:
            if first is None:
                number = self._verses[verse_id][1]
                pieces.append(f"{_PAREN_OPEN}{format_number(number, digits)}{_PAREN_CLOSE}")
                continue
            words = self._words(verse_id)
            for position in range(first, last + 1):
                if (verse_id, position) not in written:
                    written.add((verse_id, position))
                    pieces.append(words[position])
        return " ".join(pieces)


# ------------------------------------------------------------------ geometry


@dataclass(frozen=True)
class Placed:
    """Where one line element is drawn. `cell` is None for headers and basmala."""

    line: Line
    cell: Optional[Cell]
    x: float
    y: float
    width: float
    height: float


def layout_page(page, measure, width, height, default_size, gap_em=0.3):
    """Place every element of a page inside a `width` x `height` box.

    `measure(text)` returns the width of `text` in the page font, in ems (a
    font size of 1). The font size is chosen so that the widest line exactly
    fills the width and no centered line is wider than the page. Justified lines then share the leftover space
    between their words; centered lines keep a fixed gap. Pages with no
    justified line (the first ones) use `default_size`.

    Returns (placed, font_size); cells are laid out right to left.
    """
    widths = {
        line.number: [measure(cell.text) for cell in line.cells]
        for line in page.lines
        if line.kind == "text"
    }
    centered_widest = [
        sum(widths[line.number]) + gap_em * (len(line.cells) - 1)
        for line in page.lines
        if line.kind == "text" and line.cells and (line.centered or len(line.cells) < 2)
    ]
    justified_widest = [
        sum(widths[line.number])
        for line in page.lines
        if line.kind == "text" and not line.centered and len(line.cells) > 1
    ]
    limits = [width / max(centered_widest)] if centered_widest else []
    if justified_widest:
        limits.append(width / max(justified_widest))
        size = min(limits)
    else:
        size = min([default_size] + limits)
    pitch = height / len(page.lines)
    placed = []
    for index, line in enumerate(page.lines):
        top = index * pitch
        if line.kind != "text":
            placed.append(Placed(line, None, 0.0, top, width, pitch))
            continue
        cell_widths = [w * size for w in widths[line.number]]
        count = len(cell_widths)
        natural = sum(cell_widths)
        if line.centered or count < 2:
            gap = gap_em * size
            start = (width + natural + gap * (count - 1)) / 2
        else:
            gap = max(0.0, (width - natural) / (count - 1))
            start = width
        x = start
        for cell, cell_width in zip(line.cells, cell_widths):
            x -= cell_width
            placed.append(Placed(line, cell, x, top, cell_width, pitch))
            x -= gap
    return placed, size


def hit_test(placed, x, y):
    """The cell nearest to the point (x, y), or None if it is not on a text line."""
    best = None
    best_distance = None
    for item in placed:
        if item.cell is None or not item.y <= y < item.y + item.height:
            continue
        if item.x <= x < item.x + item.width:
            return item.cell
        distance = min(abs(x - item.x), abs(x - (item.x + item.width)))
        if best_distance is None or distance < best_distance:
            best, best_distance = item.cell, distance
    return best
