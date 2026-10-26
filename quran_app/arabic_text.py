"""Arabic text helpers shared by the database builder and the search engine.

The Qur'an is stored with every mark exactly as printed. Searching runs on a
*normalized* copy, produced by `normalize_for_search`, so that a query typed
without diacritics (or with a different but equivalent spelling of a letter)
still finds the verse.
"""

import re
import unicodedata

# Everything that is a mark rather than a letter:
#   U+0640        tatweel (the stretching character)
#   U+064B-065F   fathatan ... wavy hamza below (harakat, shadda, sukun, maddah ...)
#   U+0670        dagger (superscript) alef
#   U+06D6-06ED   Qur'anic annotation signs, small high/low letters, the
#                 rub' el hizb sign and the sajdah sign
MARKS = re.compile("[ـً-ٰٟۖ-ۭ]")

# Letter variants that the reader treats as the same letter when searching.
_LETTER_MAP = str.maketrans(
    {
        "أ": "ا",  # أ -> ا
        "إ": "ا",  # إ -> ا
        "آ": "ا",  # آ -> ا
        "ٱ": "ا",  # ٱ (alef wasla) -> ا
        "ى": "ي",  # ى -> ي
        "ة": "ه",  # ة -> ه
        "ؤ": "و",  # ؤ -> و
        "ئ": "ي",  # ئ -> ي
        "ء": "",  # ء (hamza on the line) is dropped
    }
)

_WHITESPACE = re.compile(r"\s+")

# Every Arabic letter that can carry a word (used for sanity checks).
_BASE_LETTER = re.compile("[ء-يٱ]")


def strip_marks(text: str) -> str:
    """Remove every diacritic and Qur'anic sign, keeping the letters."""
    return MARKS.sub("", text)


def has_letters(text: str) -> bool:
    """True if `text` contains at least one Arabic base letter."""
    return _BASE_LETTER.search(text) is not None


def normalize_for_search(text: str) -> str:
    """Return the search form of `text`.

    Marks are removed, letter variants are unified, and runs of whitespace
    (including the no-break space used in the mushaf text) become one space.
    """
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_LETTER_MAP)
    text = MARKS.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()
