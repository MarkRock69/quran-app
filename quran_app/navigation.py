"""Jumping: what a typed number means, and which page it leads to. No Qt.

    42        a page, a chapter, a juz', a hizb or a rub' (the box says which)
    2:255     chapter 2, verse 255 (understood in any box)

Digits can be Arabic-Indic (٤٢) or Western (42).
"""

import re
from typing import NamedTuple, Optional

from .numbers import format_number

# kind -> (first, last, name in Arabic)
KINDS = {
    "page": (1, 604, "صفحة"),
    "chapter": (1, 114, "سورة"),
    "juz": (1, 30, "جزء"),
    "hizb": (1, 60, "حزب"),
    "rub": (1, 240, "ربع"),
}

_DIGITS = {**{0x0660 + i: ord("0") + i for i in range(10)}, **{0x06F0 + i: ord("0") + i for i in range(10)}}
_VERSE = re.compile(r"(\d+)\s*[:/.\-]\s*(\d+)|(\d+)\s+(\d+)")
_NUMBER = re.compile(r"\d+")

HINT = "اكتب رقماً، أو سورة:آية مثل ٢:٢٥٥"


class Jump(NamedTuple):
    page: int
    verse: Optional[tuple]  # (chapter, number) when a verse was asked for


def normalize_digits(text):
    return text.translate(_DIGITS)


def parse_jump(text, kind):
    """(kind, number, None) or ("verse", chapter, number). Raises ValueError with a message in Arabic."""
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    text = normalize_digits(text).strip()
    match = _VERSE.fullmatch(text)
    if match:
        chapter, verse = (int(g) for g in match.groups() if g is not None)
        _check("chapter", chapter)
        return "verse", chapter, verse
    if not _NUMBER.fullmatch(text):
        raise ValueError(HINT)
    number = int(text)
    _check(kind, number)
    return kind, number, None


def _check(kind, number):
    first, last, name = KINDS[kind]
    if not first <= number <= last:
        raise ValueError(f"{name}: من {format_number(first)} إلى {format_number(last)}")
