"""The rows of the chapter list and the rub' list, as in the Quran Android app. No Qt.

Chapter list: a band for each juz' (with its start page), and under it the chapters
that begin in that juz'. A juz' in which no chapter begins (juz' 2) is a band alone.

Rub' list: a band for each juz', and a row for each of the 240 rub's: the first words
of its first verse, the chapter and verse, and the page. The circle shows how much of
the hizb has gone by when the rub' starts: a full circle (with the hizb number) at the
start of a hizb, then a quarter, a half, three quarters.
"""

from dataclasses import dataclass

from .numbers import format_number

RUB_SIGN = chr(0x06DE)  # ۞, printed before the first word of some rub's
OPENING_LENGTH = 40  # opening words are cut before the text passes this many characters


@dataclass(frozen=True)
class Band:
    juz: int
    page: int


@dataclass(frozen=True)
class ChapterRow:
    chapter: int
    name: str
    meccan: bool
    verse_count: int
    page: int


@dataclass(frozen=True)
class RubRow:
    hizb: int
    position: int  # 1 to 4 within the hizb; the circle is filled (position - 1) quarters, or full at 1
    text: str  # opening words, ending in "..."
    chapter: int
    chapter_name: str
    verse: int
    page: int


def opening_words(text, limit=OPENING_LENGTH):
    """The first words of a verse, as many as fit in `limit` characters (marks and spaces
    included, which is what the screenshots agree with), then "..."."""
    words = text.replace(RUB_SIGN, "").split()
    taken = []
    for word in words:
        if taken and len(" ".join(taken + [word])) > limit:
            break
        taken.append(word)
    return " ".join(taken) + "..."


def verse_count_text(count, digits="indic"):
    """٧ آيات, ٢٨٦ آية: from 3 to 10 the plural is آيات."""
    return f"{format_number(count, digits)} {'آيات' if 3 <= count <= 10 else 'آية'}"


def revelation_text(meccan):
    return "مكية" if meccan else "مدنية"


def chapter_index(connection):
    juz_pages = dict(connection.execute("SELECT id, start_page FROM juz"))
    by_juz = {}
    for chapter, name, revelation, count, page, juz in connection.execute(
        "SELECT c.id, c.name_ar, c.revelation, c.verse_count, c.start_page, v.juz"
        " FROM chapters c JOIN verses v ON v.id = c.first_verse_id ORDER BY c.id"
    ):
        by_juz.setdefault(juz, []).append(ChapterRow(chapter, name, revelation == "meccan", count, page))
    rows = []
    for juz in sorted(juz_pages):
        rows.append(Band(juz, juz_pages[juz]))
        rows.extend(by_juz.get(juz, ()))
    return rows


def rub_index(connection):
    juz_pages = dict(connection.execute("SELECT id, start_page FROM juz"))
    rows = []
    current = None
    for hizb, position, page, juz, chapter, verse, text, name in connection.execute(
        "SELECT r.hizb, r.position_in_hizb, r.start_page, v.juz, v.chapter, v.number, v.text_uthmani, c.name_ar"
        " FROM rubs r JOIN verses v ON v.id = r.first_verse_id JOIN chapters c ON c.id = v.chapter ORDER BY r.id"
    ):
        if juz != current:
            current = juz
            rows.append(Band(juz, juz_pages[juz]))
        rows.append(RubRow(hizb, position, opening_words(text), chapter, name, verse, page))
    return rows
