"""Glyphs of the chapter banner and the basmala, from the King Fahd font QCF2BSML.ttf.

The font keeps its glyphs at plain character codes (no ligatures), so drawing
one is drawing one character. Nothing here needs Qt.
"""

BANNER_FRAME = chr(0xF2)  # the ornate empty frame, about 8:1, with an oval in the middle
BASMALA = chr(0xF3)       # the whole basmala, one glyph
SURAH_WORD = chr(0x5C)    # the word سُورَةُ

# The 114 chapter names sit in code order from 0x5D (الفاتحة) to 0xF1 (الناس),
# except at the codes the font cannot hold (0x80 to 0xA0, 0xAD, 0xB7).
CHAPTER_NAME_CODES = tuple(
    code for code in range(0x5D, 0xF2) if not 0x80 <= code <= 0xA0 and code not in (0xAD, 0xB7)
)


def chapter_name_glyph(chapter):
    """The calligraphic name of chapter 1 to 114, as one character of the banner font."""
    if not 1 <= chapter <= 114:
        raise ValueError(f"no chapter {chapter}")
    return chr(CHAPTER_NAME_CODES[chapter - 1])
