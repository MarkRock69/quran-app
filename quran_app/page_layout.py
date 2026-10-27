"""How the words of the page layout line up with the words of the text.

The page layout (QUL's "QPC V4" words and layout) numbers the words of each
verse 1..n and then adds one more entry, the verse-end marker. Our text
splits words the same way for all but four verses, where the two prints
write one word differently:

* 15:7, 27:20 and 36:22: the layout writes two words (لَوۡ مَا, مَا لِيَ) where
  our text has one (لَّوۡمَا, مَالِيَ).
* 37:130: the layout writes one word (إِلۡيَاسِينَ) where our text has two
  (إِلۡ يَاسِينَ).
"""

# chapter:verse -> our word numbers that the layout writes as two words
SPLIT_WORDS = {(15, 7): (1,), (27, 20): (4,), (36, 22): (1,)}

# chapter:verse -> layout word numbers that cover two of our words
JOINED_WORDS = {(37, 130): (3,)}


def word_spans(chapter, number, glyph_word_count, word_count):
    """For each layout word of a verse (not counting its end marker), the
    first and last of our word numbers it stands for.

    Raises ValueError if the two do not add up, so a data change that breaks
    the alignment stops the build instead of passing silently.
    """
    splits = SPLIT_WORDS.get((chapter, number), ())
    joins = JOINED_WORDS.get((chapter, number), ())
    spans = []
    ours = 1
    position = 1
    while position <= glyph_word_count:
        if position in joins:
            spans.append((ours, ours + 1))
            ours += 2
            position += 1
        elif ours in splits:
            spans.append((ours, ours))
            spans.append((ours, ours))
            ours += 1
            position += 2
        else:
            spans.append((ours, ours))
            ours += 1
            position += 1
    if ours != word_count + 1 or len(spans) != glyph_word_count:
        raise ValueError(
            f"verse {chapter}:{number}: layout has {glyph_word_count} words "
            f"but the text has {word_count}"
        )
    return spans
