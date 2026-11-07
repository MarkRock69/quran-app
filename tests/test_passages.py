import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import database_path  # noqa: E402
from quran_app.mushaf import Mushaf  # noqa: E402

mushaf = None


def setUpModule():
    global mushaf
    mushaf = Mushaf(database_path())


def tearDownModule():
    mushaf.close()


def p(kind, a, b=""):
    return mushaf.passage(kind, a, b)


class PassageTest(unittest.TestCase):
    def test_a_single_verse_and_a_range(self):
        self.assertEqual(p("verse", "2:255").verses, ((2, 255),))
        self.assertEqual(p("verse", "1:6", "1:7").verses, ((1, 6), (1, 7)))

    def test_across_chapters(self):
        verses = p("verse", "1:6", "2:2").verses
        self.assertEqual(verses, ((1, 6), (1, 7), (2, 1), (2, 2)))

    def test_chapters(self):
        self.assertEqual(len(p("chapter", "1").verses), 7)
        self.assertEqual(len(p("chapter", "112", "114").verses), 4 + 5 + 6)
        self.assertEqual(p("chapter", "114").verses[-1], (114, 6))

    def test_juz_and_hizb_and_rub_cover_the_book_without_gaps(self):
        for kind, count in (("juz", 30), ("hizb", 60), ("rub", 240)):
            self.assertEqual(p(kind, "1").first, 1)
            self.assertEqual(p(kind, str(count)).last, 6236)
            for n in range(1, count):
                self.assertEqual(p(kind, str(n)).last + 1, p(kind, str(n + 1)).first, (kind, n))

    def test_known_sizes(self):
        self.assertEqual(p("juz", "1").verses[-1], (2, 141))  # juz' 2 starts at 2:142
        self.assertEqual(p("juz", "30").verses[0], (78, 1))
        self.assertEqual(p("hizb", "1").first, p("rub", "1").first)
        self.assertEqual(p("hizb", "1").last, p("rub", "4").last)
        self.assertEqual(p("hizb", "2", "3").first, p("rub", "5").first)
        self.assertEqual(p("hizb", "2", "3").last, p("rub", "12").last)

    def test_pages(self):
        self.assertEqual(p("page", "1").verses, tuple((1, n) for n in range(1, 8)))
        first = p("page", "50", "51")
        self.assertEqual(first.first, p("page", "50").first)
        self.assertEqual(first.last, p("page", "51").last)

    def test_digits_and_errors(self):
        self.assertEqual(p("verse", "٢:٢٥٥").verses, ((2, 255),))
        for kind, a, b in (("verse", "255", ""), ("verse", "2:300", ""), ("chapter", "2:1", ""),
                           ("chapter", "5", "2"), ("juz", "31", ""), ("page", "0", ""), ("verse", "3:10", "2:5")):
            with self.assertRaises(ValueError, msg=(kind, a, b)):
                p(kind, a, b)


if __name__ == "__main__":
    unittest.main()
