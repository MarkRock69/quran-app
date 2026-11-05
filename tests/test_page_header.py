import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import database_path  # noqa: E402
from quran_app.mushaf import Mushaf, layout_page  # noqa: E402
from quran_app.numbers import next_style, number_text, ordinal  # noqa: E402
from quran_app.page_header import header_for, rub_progress  # noqa: E402

mushaf = None


def setUpModule():
    global mushaf
    mushaf = Mushaf(database_path())


def tearDownModule():
    mushaf.close()


def header(page, style="indic"):
    info = mushaf.page_info(page)
    return header_for(info, mushaf.chapter_name(info.chapter), style)


class OrdinalTest(unittest.TestCase):
    def test_words(self):
        expected = {1: "الأول", 8: "الثامن", 11: "الحادي عشر", 12: "الثاني عشر", 19: "التاسع عشر",
                    20: "العشرون", 21: "الحادي والعشرون", 60: "الستون", 100: "المائة",
                    101: "الحادي بعد المائة"}
        for number, word in expected.items():
            self.assertEqual(ordinal(number), word, number)
        self.assertEqual(ordinal(2, feminine=True), "الثانية")
        self.assertEqual(ordinal(114, feminine=True), "الرابعة عشرة بعد المائة")

    def test_styles(self):
        self.assertEqual(number_text(8), "٨")
        self.assertEqual(number_text(8, "western"), "8")
        self.assertEqual(number_text(8, "words"), "الثامن")
        self.assertEqual([next_style(s) for s in ("indic", "western", "words")], ["western", "words", "indic"])


class HeaderTest(unittest.TestCase):
    def test_rub_progress(self):
        self.assertEqual(rub_progress(1, 4), (1, 3))
        self.assertEqual(rub_progress(8, 2), (8, 1))
        self.assertEqual(rub_progress(8, 1), (7, 4))
        self.assertIsNone(rub_progress(1, 1))

    def test_page_9_three_quarters_of_hizb_1(self):
        self.assertEqual(header(9, "western").right, "الجزء 1، ثلاثة أرباع الحزب 1")

    def test_page_74_a_quarter_of_hizb_8(self):
        self.assertEqual(header(74, "western").right, "الجزء 4، ربع الحزب 8")
        self.assertEqual(header(74).right, "الجزء ٤، ربع الحزب ٨")

    def test_page_without_a_rub_mark_shows_only_the_juz(self):
        self.assertEqual(header(10, "words").right, "الجزء الأول")

    def test_chapter_name_and_number(self):
        h = header(42)
        self.assertEqual((h.chapter_number, h.chapter_name), ("٢", mushaf.chapter_name(2)))
        self.assertEqual(header(604, "western").chapter_number, "112")
        self.assertEqual(header(42, "words").chapter_number, "الثانية")

    def test_every_page_has_a_header(self):
        for page in range(1, 605):
            self.assertTrue(header(page).right.startswith("الجزء"))

    def test_juz_matches_start_pages(self):
        self.assertEqual(mushaf.page_info(62).juz, 4)
        self.assertEqual(mushaf.page_info(61).juz, 3)


class FitTest(unittest.TestCase):
    def test_no_line_is_wider_than_the_page_on_the_short_pages(self):
        measure = lambda text: 1.0 * len(text)  # noqa: E731
        for number in (1, 2, 3, 42):
            placed, size = layout_page(mushaf.page(number), measure, 540, 750, default_size=40)
            for item in placed:
                if item.cell:
                    self.assertGreaterEqual(item.x, -1e-6, number)
                    self.assertLessEqual(item.x + item.width, 540 + 1e-6, number)


if __name__ == "__main__":
    unittest.main()
