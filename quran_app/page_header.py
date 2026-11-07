"""The line above each page: juz', hizb and quarter, chapter name and chapter number.

    right:  الجزء ١، ثلاثة أرباع الحزب ١      (the quarter part only when a rub' starts on the page)
    left:   ٢  البَقَرَة                       (chapter number, then its name)

Juz' and hizb are marked where they begin, rub's where they end: a rub' that
starts on the page means the quarter before it is finished, so the heading says
a quarter, a half or three quarters of the hizb; the first rub' of a hizb just
says "الحزب ٢" (the hizb begins). The juz' is always shown.
"""

from dataclasses import dataclass
from typing import Optional

from .numbers import number_text

_FRACTIONS = {1: "ربع", 2: "نصف", 3: "ثلاثة أرباع"}
_COMMA = "،"


@dataclass(frozen=True)
class PageInfo:
    juz: int
    chapter: int  # the chapter of the first verse on the page
    hizb: Optional[int]  # set when a rub' starts on the page
    quarters: Optional[int]  # 0 to 3: quarters of that hizb done (0 = the hizb begins here)


def rub_progress(hizb, position):
    """(hizb, quarters done) for the rub' that starts at `position` (1 to 4) of `hizb`.

    Hizbs are marked at their beginning (0 quarters: "الحزب ٢") and rub's at
    their end (the previous quarter is done: "ربع الحزب ٢"). None for the very
    first rub', which opens page 1 and gets no heading.
    """
    if (hizb, position) == (1, 1):
        return None
    return hizb, position - 1


@dataclass(frozen=True)
class Header:
    right: str
    chapter_name: str
    chapter_number: str


def header_for(info, chapter_name, style="indic"):
    n = lambda value: number_text(value, style)  # noqa: E731
    right = f"الجزء {n(info.juz)}"
    if info.hizb is not None:
        fraction = _FRACTIONS.get(info.quarters)
        hizb = f"الحزب {n(info.hizb)}"
        right += f"{_COMMA} {fraction + ' ' if fraction else ''}{hizb}"
    number = number_text(info.chapter, style, feminine=True)
    if style == "words":
        number = f"({number})"  # a word needs brackets to read as the chapter's number
    return Header(right, chapter_name, number)
