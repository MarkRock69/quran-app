"""The line above each page: juz', hizb and quarter, chapter name and chapter number.

    right:  الجزء ١، ثلاثة أرباع الحزب ١      (the quarter part only when a rub' starts on the page)
    left:   ٢  البَقَرَة                       (chapter number, then its name)

A rub' that starts on the page means the quarters before it are finished, so the
heading says how much of the hizb is done: a quarter, a half, three quarters, or
the whole hizb when the rub' that starts is the first of the next hizb.
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
    quarters: Optional[int]  # 1 to 4: how much of that hizb is done (4 = all of it)


def rub_progress(hizb, position):
    """(hizb, quarters done) for a rub' that starts at `position` (1 to 4) of `hizb`; None at the very start."""
    if position > 1:
        return hizb, position - 1
    return (hizb - 1, 4) if hizb > 1 else None


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
    return Header(right, chapter_name, number_text(info.chapter, style, feminine=True))
