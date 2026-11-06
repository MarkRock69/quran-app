import unittest
from pathlib import Path

from quran_app.banner import (
    BANNER_FRAME, BASMALA, CHAPTER_NAME_CODES, SURAH_WORD, chapter_name_glyph, plan_frame, stretch_x,
)

FONT = Path(__file__).resolve().parent.parent / "data" / "fonts" / "QCF2BSML.ttf"


class BannerTest(unittest.TestCase):
    def test_114_distinct_codes_in_order(self):
        self.assertEqual(len(CHAPTER_NAME_CODES), 114)
        self.assertEqual(list(CHAPTER_NAME_CODES), sorted(set(CHAPTER_NAME_CODES)))
        self.assertEqual((CHAPTER_NAME_CODES[0], CHAPTER_NAME_CODES[-1]), (0x5D, 0xF1))

    def test_no_such_chapter(self):
        for chapter in (0, 115):
            with self.assertRaises(ValueError):
                chapter_name_glyph(chapter)

    @unittest.skipUnless(FONT.exists(), "run tools/fetch_fonts.py first")
    def test_every_glyph_is_in_the_font(self):
        from fontTools.ttLib import TTFont

        cmap = TTFont(FONT).getBestCmap()
        for chapter in range(1, 115):
            self.assertIn(ord(chapter_name_glyph(chapter)), cmap)
        for glyph in (BANNER_FRAME, BASMALA, SURAH_WORD):
            self.assertIn(ord(glyph), cmap)


class StretchTest(unittest.TestCase):
    def test_wide_box_adds_width_in_the_middle_and_keeps_the_height(self):
        scale, extra = plan_frame(800, 100, 1280, 50)
        self.assertEqual(scale, 0.5)
        self.assertAlmostEqual((800 + extra) * scale, 1280)

    def test_narrow_box_shrinks_without_stretching(self):
        scale, extra = plan_frame(800, 100, 400, 50)
        self.assertEqual((scale, extra), (0.5, 0.0))

    def test_only_points_right_of_the_cut_move(self):
        self.assertEqual(stretch_x(10, 400, 250), 10)
        self.assertEqual(stretch_x(400, 400, 250), 400)
        self.assertEqual(stretch_x(401, 400, 250), 651)


if __name__ == "__main__":
    unittest.main()
