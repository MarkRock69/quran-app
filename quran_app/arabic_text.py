"""Arabic text helpers shared by the database builder and the search engine.

The Qur'an is stored with every mark exactly as printed. Searching runs on a
*normalized* copy, produced by `normalize_for_search`, so that a query typed
without diacritics (or with a different but equivalent spelling of a letter)
still finds the verse.

`analyse` is the same normalization, but it also remembers, for every
surviving letter, which vowel marks it carries and where it sits in the
original text. Search uses it to compare typed marks and to highlight the
exact characters that matched.

Characters are written as code points (U+XXXX) in this file because most of
them are invisible combining marks.
"""

import re
from typing import NamedTuple

# Everything that is a mark rather than a letter:
#   U+0640        tatweel (the stretching character)
#   U+064B-065F   fathatan ... wavy hamza below (harakat, shadda, sukun, maddah ...)
#   U+0670        dagger (superscript) alef
#   U+06D6-06ED   Qur'anic annotation signs, small high/low letters, the
#                 rub' el hizb sign and the sajdah sign
MARKS = re.compile(
    "[" + chr(0x0640) + chr(0x064B) + "-" + chr(0x065F) + chr(0x0670)
    + chr(0x06D6) + "-" + chr(0x06ED) + "]"
)

# Letter variants that the reader treats as the same letter when searching.
_LETTER_MAP = {
    0x0623: chr(0x0627),  # alef with hamza above -> alef
    0x0625: chr(0x0627),  # alef with hamza below -> alef
    0x0622: chr(0x0627),  # alef with maddah      -> alef
    0x0671: chr(0x0627),  # alef wasla            -> alef
    0x0649: chr(0x064A),  # alef maksura          -> yeh
    0x0629: chr(0x0647),  # teh marbuta           -> heh
    0x0624: chr(0x0648),  # waw with hamza        -> waw
    0x0626: chr(0x064A),  # yeh with hamza        -> yeh
    0x0621: "",  # hamza on the line is dropped
}

# The vowel marks a reader can type, as bits. The Uthmani script writes some
# of them with other code points than a keyboard produces, so each mark lists
# every code point that means it:
#   sukun      U+0652 (keyboard) and U+06E1 (Uthmani, nearly everywhere)
#   fathatan   U+064B (stacked) and U+0657 (open form)
#   dammatan   U+064C (stacked) and U+065E (open form)
#   kasratan   U+064D (stacked) and U+0656 (open form)
FATHA = 1
DAMMA = 2
KASRA = 4
SHADDA = 8
SUKUN = 16
FATHATAN = 32
DAMMATAN = 64
KASRATAN = 128
DAGGER_ALEF = 256
ALL_VOWEL_MARKS = 511
# Not a vowel mark: the letter carries a hamza (written with a hamza letter,
# or with a hamza/maddah mark). Search uses it one way only: a hamza that is
# typed must be present in the text, but a letter typed without a hamza
# matches the letter with or without one.
HAMZA = 512

_MARK_BITS = {
    0x064E: FATHA,
    0x064F: DAMMA,
    0x0650: KASRA,
    0x0651: SHADDA,
    0x0652: SUKUN,
    0x06E1: SUKUN,
    0x064B: FATHATAN,
    0x0657: FATHATAN,
    0x064C: DAMMATAN,
    0x065E: DAMMATAN,
    0x064D: KASRATAN,
    0x0656: KASRATAN,
    0x0670: DAGGER_ALEF,
    0x0653: HAMZA,  # maddah above (alef + maddah is alef with maddah)
    0x0654: HAMZA,  # hamza above
    0x0655: HAMZA,  # hamza below
}

# Letters that already contain a hamza: alef with maddah / hamza above /
# hamza below, waw with hamza, yeh with hamza.
_HAMZA_LETTERS = {0x0622, 0x0623, 0x0624, 0x0625, 0x0626}

# Every Arabic letter that can carry a word (used for sanity checks).
_BASE_LETTER = re.compile("[" + chr(0x0621) + "-" + chr(0x064A) + chr(0x0671) + "]")


class Letter(NamedTuple):
    """One letter of the normalized text.

    `char` is the normalized letter (or a single space). `marks` is a bitmask
    of the vowel marks on it, plus HAMZA if it carries a hamza. `start` and
    `end` delimit the letter and all of its marks in the original text, so
    `text[start:end]` is what to highlight.
    """

    char: str
    marks: int
    start: int
    end: int


def strip_marks(text: str) -> str:
    """Remove every diacritic and Qur'anic sign, keeping the letters."""
    return MARKS.sub("", text)


def has_letters(text: str) -> bool:
    """True if `text` contains at least one Arabic base letter."""
    return _BASE_LETTER.search(text) is not None


def analyse(text: str) -> tuple:
    """Break `text` into normalized letters, with their marks and positions.

    The letters, joined, are exactly `normalize_for_search(text)` apart from
    leading and trailing spaces, which are kept (a space at the edge of a
    search query means "a word starts/ends here"). Runs of whitespace
    become one space.

    A hamza written on the line is dropped like in normalization, and the
    marks it carries move to the next letter of the same word.
    """
    letters = []  # each entry is [char, marks, start, end]
    carry = 0
    after_dropped_hamza = False
    for index, char in enumerate(text):
        if char.isspace():
            if letters and letters[-1][0] == " ":
                letters[-1][3] = index + 1
            else:
                letters.append([" ", 0, index, index + 1])
            carry = 0
            after_dropped_hamza = False
        elif MARKS.match(char):
            bit = _MARK_BITS.get(ord(char), 0)
            if after_dropped_hamza:
                carry |= bit
                if letters:
                    letters[-1][3] = index + 1
            elif letters and letters[-1][0] != " ":
                letters[-1][1] |= bit
                letters[-1][3] = index + 1
        else:
            mapped = _LETTER_MAP.get(ord(char), char)
            if mapped == "":
                after_dropped_hamza = True
                if letters and letters[-1][0] != " ":
                    letters[-1][3] = index + 1
            else:
                if ord(char) in _HAMZA_LETTERS:
                    carry |= HAMZA
                letters.append([mapped, carry, index, index + 1])
                carry = 0
                after_dropped_hamza = False
    return tuple(Letter(*entry) for entry in letters)


def normalize_for_search(text: str) -> str:
    """Return the search form of `text`.

    Marks are removed, letter variants are unified, and runs of whitespace
    (including the no-break space used in the mushaf text) become one space.
    """
    return "".join(letter.char for letter in analyse(text)).strip()
