import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import database_path  # noqa: E402
from quran_app.bookmarks import Bookmarks  # noqa: E402
from quran_app.mushaf import Mushaf  # noqa: E402
from quran_app.navigation import parse_jump  # noqa: E402

mushaf = None


def setUpModule():
    global mushaf
    mushaf = Mushaf(database_path())


def tearDownModule():
    mushaf.close()


class ParseTest(unittest.TestCase):
    def test_numbers_in_either_digits(self):
        self.assertEqual(parse_jump("٤٢", "page"), ("page", 42, None))
        self.assertEqual(parse_jump(" 12 ", "juz"), ("juz", 12, None))
        self.assertEqual(parse_jump("۴۲", "page"), ("page", 42, None))

    def test_verse_forms(self):
        for text in ("2:255", "٢:٢٥٥", "2 255", "2/255", "2.255"):
            self.assertEqual(parse_jump(text, "page"), ("verse", 2, 255), text)

    def test_errors_are_in_arabic(self):
        for text, kind in (("", "page"), ("abc", "page"), ("605", "page"), ("0", "chapter"), ("31", "juz"),
                           ("115:1", "page")):
            with self.assertRaises(ValueError):
                parse_jump(text, kind)


class JumpTest(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(mushaf.jump("page", "42").page, 42)
        self.assertEqual(mushaf.jump("chapter", "2").page, 2)
        self.assertEqual(mushaf.jump("chapter", "114").page, 604)
        self.assertEqual(mushaf.jump("juz", "30").page, mushaf.page_of_verse(78, 1))
        self.assertEqual(mushaf.jump("hizb", "2").page, 11)
        self.assertEqual(mushaf.jump("rub", "2").page, 5)
        self.assertGreater(mushaf.jump("rub", "240").page, mushaf.jump("hizb", "60").page - 1)

    def test_hizb_is_its_first_rub(self):
        for hizb in (1, 2, 30, 60):
            self.assertEqual(mushaf.jump("hizb", str(hizb)).page, mushaf.jump("rub", str((hizb - 1) * 4 + 1)).page)

    def test_verse(self):
        jump = mushaf.jump("page", "2:255")
        self.assertEqual((jump.page, jump.verse), (42, (2, 255)))

    def test_verse_out_of_range(self):
        for text in ("2:287", "1:8", "1:0"):
            with self.assertRaises(ValueError):
                mushaf.jump("page", text)


class BookmarksTest(unittest.TestCase):
    def test_toggle_and_list(self):
        marks = Bookmarks(":memory:")
        self.assertTrue(marks.toggle(42))
        self.assertTrue(marks.toggle(7))
        self.assertEqual(marks.pages(), [7, 42])
        self.assertFalse(marks.toggle(42))
        self.assertFalse(marks.has(42))
        self.assertTrue(marks.has(7))
        marks.close()


if __name__ == "__main__":
    unittest.main()
