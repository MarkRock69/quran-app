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


# --- a frame of any width -------------------------------------------------------
#
# The frame is stretched without distorting its ornaments: everything to the right
# of the frame's middle line moves right by the extra width. Only straight lines
# cross that line (the borders and the top and bottom of the oval), so they just
# get longer, and the ornaments and circles at the ends keep their shape.

# Where the oval in the middle of the frame is, as fractions of the frame's own width and height.
OVAL_LEFT = 0.262
OVAL_RIGHT = 0.711
OVAL_HEIGHT = 0.58


def plan_frame(ink_width, ink_height, box_width, box_height):
    """How to fit the frame in a box: (scale, extra), extra being the width to add in the middle,
    in the frame's own units. The frame is as tall as the box allows; if that leaves it narrower than the box
    it is stretched in the middle, and if it would be wider (a narrow page) it is shrunk instead."""
    scale = min(box_height / ink_height, box_width / ink_width)
    extra = max(0.0, box_width / scale - ink_width)
    return scale, extra


def stretch_x(x, cut, extra):
    """Where a point at x goes when `extra` is inserted at x = cut."""
    return x + extra if x > cut else x
