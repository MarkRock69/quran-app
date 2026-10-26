"""Line up the Uthmani words of a verse with its modern-spelling words.

The Uthmani script sometimes writes as one word what modern spelling writes
as two (هَٰٓأَنتُمۡ is "ها أنتم"), so the two word lists of a verse can differ in
length. The Mushaf page, the glyphs and the displayed text all follow the
Uthmani words, so every Uthmani word gets the modern-spelling text that
belongs to it.
"""

from functools import lru_cache

from .arabic_text import normalize_for_search

# Largest group of words on one side that may collapse into a single word on
# the other side.
_MAX_GROUP = 3

# How far from the straight diagonal the alignment may wander, on top of the
# difference in word counts. Real verses never come close to this.
_BAND = 4


@lru_cache(maxsize=None)
def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (char_a != char_b),
                )
            )
        previous = current
    return previous[-1]


def align_words(uthmani_words, imlaei_words):
    """Pair each Uthmani word with its modern-spelling text.

    Returns `(pairs, cost)`. `pairs` has one string per Uthmani word: the
    matching modern word, several modern words joined by a space when the
    Uthmani word covers more than one, or an empty string for the later words
    of a group when several Uthmani words share one modern word. `cost` is
    the total number of letters that differ, which is 0 for a perfect match
    and is meant for reporting suspicious verses.
    """
    uthmani_keys = [normalize_for_search(word).replace(" ", "") for word in uthmani_words]
    imlaei_keys = [normalize_for_search(word).replace(" ", "") for word in imlaei_words]
    count_u, count_i = len(uthmani_words), len(imlaei_words)

    infinity = float("inf")
    best = [[infinity] * (count_i + 1) for _ in range(count_u + 1)]
    step = [[None] * (count_i + 1) for _ in range(count_u + 1)]
    best[0][0] = 0

    band = abs(count_u - count_i) + _BAND
    for i in range(count_u + 1):
        for j in range(max(0, i - band), min(count_i, i + band) + 1):
            if best[i][j] == infinity:
                continue
            for take_u in range(1, _MAX_GROUP + 1):
                for take_i in range(1, _MAX_GROUP + 1):
                    if take_u > 1 and take_i > 1:
                        continue
                    if i + take_u > count_u or j + take_i > count_i:
                        continue
                    left = "".join(uthmani_keys[i : i + take_u])
                    right = "".join(imlaei_keys[j : j + take_i])
                    cost = best[i][j] + _edit_distance(left, right)
                    # A tiny penalty for grouping keeps one-to-one the
                    # preferred reading when costs tie.
                    cost += 0.001 * (take_u + take_i - 2)
                    if cost < best[i + take_u][j + take_i]:
                        best[i + take_u][j + take_i] = cost
                        step[i + take_u][j + take_i] = (take_u, take_i)

    if best[count_u][count_i] == infinity:
        raise ValueError("the two word lists cannot be lined up")

    pairs = [""] * count_u
    i, j = count_u, count_i
    while i > 0 or j > 0:
        take_u, take_i = step[i][j]
        i -= take_u
        j -= take_i
        pairs[i] = " ".join(imlaei_words[j : j + take_i])
    return pairs, round(best[count_u][count_i])
