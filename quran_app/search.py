"""Search over the whole Qur'an text, fast enough to run on every keystroke.

How a query is matched
----------------------
Every verse is kept in memory in two searchable forms ("views"): the Uthmani
script reduced to its letters, and the modern spelling reduced to its letters.
A query is reduced the same way and looked for as plain text in both views, so
a modern spelling (الصلاة) finds the Uthmani one (الصلوة) and diacritics are
ignored.

* The query is searched exactly as typed: no word boundaries are applied
  unless the query starts or ends with a space. A space at the start means
  "a word starts here", a space at the end means "a word ends here".
* A phrase never spans two verses: each verse is searched on its own.
* If the query contains vowel marks, those marks must be present in the
  Uthmani text at the same letters; marks that were not typed are ignored.
  With `strict_marks` the text must carry exactly the typed marks.
* Hamza works one way: typing أ إ آ ؤ ئ requires a hamza-bearing letter in
  the text, while typing plain ا و ي matches the letter with or without one.

Showing a result
----------------
`SearchIndex.render` builds the text to display: the found words, with the
matched characters flagged, and some words of context on each side, cut off
at the edges of the verse. Only the Uthmani text is ever displayed.
"""

import sqlite3
from dataclasses import dataclass
from itertools import groupby
from typing import NamedTuple

from .arabic_text import ALL_VOWEL_MARKS, HAMZA, analyse

PHRASE = "phrase"  # the whole query, exactly, in order
ALL_WORDS = "all_words"  # every word of the query, in any order
ANY_WORD = "any_word"  # at least one word of the query
MODES = (PHRASE, ALL_WORDS, ANY_WORD)

_UTHMANI, _IMLAEI = 0, 1


@dataclass(frozen=True)
class SearchOptions:
    mode: str = PHRASE
    strict_marks: bool = False

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"unknown search mode {self.mode!r}")


class _Query(NamedTuple):
    needle: str  # the letters to look for, spaces at the edges kept
    vowels: object  # vowel marks typed at each letter, or None if none typed
    hamza_at: list  # positions of letters typed with a hamza


class Hit(NamedTuple):
    """One place a query was found.

    `pieces` are the matched stretches, as (view, start, end) positions in
    that view's text. `first_word` and `last_word` are the (0-based) words of
    the verse that the match touches.
    """

    verse_index: int
    pieces: tuple
    first_word: int
    last_word: int


class SearchResult(NamedTuple):
    hits: list
    verse_count: int

    @property
    def occurrence_count(self):
        return len(self.hits)


class Snippet(NamedTuple):
    """What to show for one result."""

    chapter: int
    chapter_name: str
    number: int
    page: int
    segments: tuple  # ((text, matched), ...), in reading order
    starts_at_verse_start: bool
    ends_at_verse_end: bool

    @property
    def coordinate(self):
        return f"{self.chapter}:{self.number}"


class _View:
    """A verse reduced to letters, padded with a space on both sides."""

    __slots__ = ("text", "word_of", "starts", "parts")

    def __init__(self, parts):
        self.parts = tuple(parts)
        self.text = " " + " ".join(parts) + " "
        self.word_of = [-1]
        self.starts = []
        for index, part in enumerate(parts):
            self.starts.append(len(self.word_of))
            self.word_of.extend([index] * len(part))
            self.word_of.append(-1)

    def word_span(self, start, end):
        """First and last word touched by text[start:end], ignoring spaces."""
        first = start
        while first < end and self.text[first] == " ":
            first += 1
        last = end - 1
        while last >= first and self.text[last] == " ":
            last -= 1
        if last < first:
            return None
        return self.word_of[first], self.word_of[last]


class _IndexedVerse:
    __slots__ = ("id", "chapter", "number", "page", "words", "views", "flags")

    def __init__(self, verse_id, chapter, number, page, words, uthmani_parts, imlaei_words):
        self.id = verse_id
        self.chapter = chapter
        self.number = number
        self.page = page
        self.words = tuple(words)
        imlaei_letters = [analyse(word) for word in imlaei_words]
        imlaei_parts = ["".join(letter.char for letter in letters) for letters in imlaei_letters]
        self.views = (_View(uthmani_parts), _View(imlaei_parts))
        # For every character of each view: the marks (Uthmani) or just the
        # hamza flag (modern spelling), lined up with the view's text.
        uthmani_flags = [0]
        for word in self.words:
            uthmani_flags.extend(letter.marks for letter in analyse(word))
            uthmani_flags.append(0)
        imlaei_flags = [0]
        for letters in imlaei_letters:
            imlaei_flags.extend(letter.marks & HAMZA for letter in letters)
            imlaei_flags.append(0)
        self.flags = (uthmani_flags, imlaei_flags)


def align_letters(a, b):
    """For each letter of `a`, the index of the letter of `b` it corresponds to.

    Used to carry a position in the modern spelling over to the Uthmani
    spelling of the same word, where a letter or two may differ.
    """
    n, m = len(a), len(b)
    if a == b:
        return list(range(n))
    cost = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        cost[i][0] = i
    for j in range(m + 1):
        cost[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost[i][j] = min(
                cost[i - 1][j] + 1,
                cost[i][j - 1] + 1,
                cost[i - 1][j - 1] + (a[i - 1] != b[j - 1]),
            )
    mapping = [0] * n
    i, j = n, m
    while i > 0 and j > 0:
        if cost[i][j] == cost[i - 1][j - 1] + (a[i - 1] != b[j - 1]):
            mapping[i - 1] = j - 1
            i -= 1
            j -= 1
        elif cost[i][j] == cost[i - 1][j] + 1:
            mapping[i - 1] = j - 1
            i -= 1
        else:
            j -= 1
    return mapping


class SearchIndex:
    """The whole text in memory, ready to search."""

    def __init__(self, verses, chapter_names):
        self.verses = verses
        self.chapter_names = chapter_names

    @classmethod
    def from_database(cls, path):
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            chapter_names = dict(connection.execute("SELECT id, name_ar FROM chapters"))
            info = {
                row[0]: row[1:]
                for row in connection.execute("SELECT id, chapter, number, page FROM verses")
            }
            word_rows = connection.execute(
                "SELECT verse_id, text_uthmani, search_uthmani, text_imlaei"
                " FROM words ORDER BY verse_id, position"
            )
            verses = []
            for verse_id, rows in groupby(word_rows, key=lambda row: row[0]):
                rows = list(rows)
                chapter, number, page = info[verse_id]
                verses.append(
                    _IndexedVerse(
                        verse_id, chapter, number, page,
                        [row[1] for row in rows],
                        [row[2] for row in rows],
                        [row[3] for row in rows],
                    )
                )
        finally:
            connection.close()
        return cls(verses, chapter_names)

    # ------------------------------------------------------------------ search

    def search(self, query, options=SearchOptions()):
        """Find `query`; the hits come in Mushaf order."""
        if options.mode == PHRASE:
            prepared = [self._prepare(query)]
        else:
            prepared = [self._prepare(term) for term in query.split()]
        prepared = [p for p in prepared if p is not None]
        if not prepared:
            return SearchResult([], 0)

        hits = []
        for verse_index, verse in enumerate(self.verses):
            if options.mode == PHRASE:
                for view_id, start, end, first, last in self._occurrences(
                    verse, prepared[0], options.strict_marks
                ):
                    hits.append(Hit(verse_index, ((view_id, start, end),), first, last))
                continue

            pieces = []
            for query_part in prepared:
                found = self._occurrences(verse, query_part, options.strict_marks, first_only=True)
                if found:
                    pieces.append(found[0])
                elif options.mode == ALL_WORDS:
                    pieces = None
                    break
            if pieces:
                pieces.sort(key=lambda piece: (piece[3], piece[4]))
                hits.append(
                    Hit(
                        verse_index,
                        tuple((view, start, end) for view, start, end, _, _ in pieces),
                        min(piece[3] for piece in pieces),
                        max(piece[4] for piece in pieces),
                    )
                )
        return SearchResult(hits, len({hit.verse_index for hit in hits}))

    @staticmethod
    def _prepare(query):
        """Reduce a query to what matching needs; None if there is nothing to find."""
        letters = analyse(query)
        needle = "".join(letter.char for letter in letters)
        if not needle.strip():
            return None
        vowels = [letter.marks & ALL_VOWEL_MARKS for letter in letters]
        hamza_at = [i for i, letter in enumerate(letters) if letter.marks & HAMZA]
        return _Query(needle, vowels if any(vowels) else None, hamza_at)

    @staticmethod
    def _accepts(flags, position, query, strict, check_vowels):
        """Do the typed hamzas and vowel marks agree with the text found?"""
        for offset in query.hamza_at:
            if not flags[position + offset] & HAMZA:
                return False
        if check_vowels and query.vowels is not None:
            for offset, wanted in enumerate(query.vowels):
                present = flags[position + offset]
                if strict:
                    if present & ALL_VOWEL_MARKS != wanted:
                        return False
                elif wanted & ~present:
                    return False
        return True

    def _occurrences(self, verse, query, strict, first_only=False):
        """All non-overlapping places the query occurs in the verse.

        Returns (view, start, end, first_word, last_word) tuples. The same
        words found through both spellings are reported once, as the Uthmani
        match.
        """
        found = {}
        for view_id in (_UTHMANI, _IMLAEI):
            if query.vowels is not None and view_id == _IMLAEI:
                continue  # vowel marks can only be checked against the Uthmani text
            needle = query.needle
            text = verse.views[view_id].text
            position = text.find(needle)
            while position != -1:
                end = position + len(needle)
                if self._accepts(verse.flags[view_id], position, query, strict, view_id == _UTHMANI):
                    span = verse.views[view_id].word_span(position, end)
                    if span is not None and span not in found:
                        found[span] = (view_id, position, end, span[0], span[1])
                    position = text.find(needle, end)
                else:
                    position = text.find(needle, position + 1)
        occurrences = sorted(found.values(), key=lambda item: (item[3], item[4]))
        return occurrences[:1] if first_only else occurrences

    # ----------------------------------------------------------------- display

    def render(self, hit, before=3, after=3):
        """The text to show for one hit, with `before`/`after` words of context."""
        verse = self.verses[hit.verse_index]
        ranges = self._highlight_ranges(verse, hit)
        low = max(0, hit.first_word - before)
        high = min(len(verse.words) - 1, hit.last_word + after)

        segments = []

        def emit(text, matched):
            if not text:
                return
            if segments and segments[-1][1] == matched:
                segments[-1] = (segments[-1][0] + text, matched)
            else:
                segments.append((text, matched))

        previous_reaches_end = False
        for index in range(low, high + 1):
            word = verse.words[index]
            letters = analyse(word)
            word_ranges = ranges.get(index, [])
            starts_matched = bool(word_ranges) and word_ranges[0][0] <= letters[0].start
            if index > low:
                emit(" ", previous_reaches_end and starts_matched)
            cursor = 0
            for start, end in word_ranges:
                emit(word[cursor:start], False)
                emit(word[start:end], True)
                cursor = end
            emit(word[cursor:], False)
            previous_reaches_end = bool(word_ranges) and word_ranges[-1][1] >= letters[-1].end

        return Snippet(
            chapter=verse.chapter,
            chapter_name=self.chapter_names[verse.chapter],
            number=verse.number,
            page=verse.page,
            segments=tuple(segments),
            starts_at_verse_start=low == 0,
            ends_at_verse_end=high == len(verse.words) - 1,
        )

    def _highlight_ranges(self, verse, hit):
        """For each word touched by the hit, the character ranges to highlight."""
        ranges = {}
        for view_id, start, end in hit.pieces:
            view = verse.views[view_id]
            first = start
            while view.text[first] == " ":
                first += 1
            last = end - 1
            while view.text[last] == " ":
                last -= 1
            for word_index in range(view.word_of[first], view.word_of[last] + 1):
                part = view.parts[word_index]
                word_start = view.starts[word_index]
                local_start = max(first, word_start) - word_start
                local_end = min(last + 1, word_start + len(part)) - word_start
                letters = analyse(verse.words[word_index])
                if view_id == _UTHMANI:
                    first_letter, last_letter = local_start, local_end - 1
                else:
                    plain = part.replace(" ", "")
                    first_letter = len(part[:local_start].replace(" ", ""))
                    last_letter = len(part[:local_end].replace(" ", "")) - 1
                    if last_letter < first_letter:
                        continue
                    mapping = align_letters(plain, "".join(letter.char for letter in letters))
                    first_letter, last_letter = mapping[first_letter], mapping[last_letter]
                if last_letter < first_letter:
                    last_letter = first_letter
                ranges.setdefault(word_index, []).append(
                    (letters[first_letter].start, letters[last_letter].end)
                )
        return {index: self._merge(found) for index, found in ranges.items()}

    @staticmethod
    def _merge(found):
        merged = []
        for start, end in sorted(found):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
            else:
                merged.append((start, end))
        return merged
