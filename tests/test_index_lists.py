import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import database_path  # noqa: E402
from quran_app.index_lists import Band, ChapterRow, RubRow, opening_words, verse_count_text  # noqa: E402
from quran_app.mushaf import Mushaf  # noqa: E402

mushaf = None


def setUpModule():
    global mushaf
    mushaf = Mushaf(database_path())


def tearDownModule():
    mushaf.close()


class ChapterListTest(unittest.TestCase):
    def setUp(self):
        self.rows = mushaf.chapter_index()

    def test_counts(self):
        self.assertEqual(sum(isinstance(r, Band) for r in self.rows), 30)
        self.assertEqual(sum(isinstance(r, ChapterRow) for r in self.rows), 114)

    def test_like_the_quran_android_screenshot(self):
        names = [(type(r).__name__, getattr(r, "juz", None) or r.chapter, r.page) for r in self.rows[:6]]
        self.assertEqual(
            names,
            [("Band", 1, 1), ("ChapterRow", 1, 1), ("ChapterRow", 2, 2),
             ("Band", 2, 22), ("Band", 3, 42), ("ChapterRow", 3, 50)],
        )

    def test_row_details(self):
        fatiha, baqara = self.rows[1], self.rows[2]
        self.assertEqual((fatiha.meccan, fatiha.verse_count), (True, 7))
        self.assertEqual((baqara.meccan, baqara.verse_count), (False, 286))
        self.assertEqual(self.rows[5].verse_count, 200)

    def test_chapters_stay_in_order(self):
        chapters = [r.chapter for r in self.rows if isinstance(r, ChapterRow)]
        self.assertEqual(chapters, list(range(1, 115)))


class RubListTest(unittest.TestCase):
    def setUp(self):
        self.rows = mushaf.rub_index()

    def test_counts(self):
        self.assertEqual(sum(isinstance(r, RubRow) for r in self.rows), 240)
        self.assertEqual(sum(isinstance(r, Band) for r in self.rows), 30)

    def test_juz_1_like_the_screenshot(self):
        rows = self.rows[:7]
        self.assertEqual(rows[0], Band(1, 1))
        got = [(r.hizb, r.position, r.chapter, r.verse, r.page) for r in rows[1:]]
        self.assertEqual(got, [(1, 1, 1, 1, 1), (1, 2, 2, 26, 5), (1, 3, 2, 44, 7),
                               (1, 4, 2, 60, 9), (2, 1, 2, 75, 11), (2, 2, 2, 92, 14)])

    def test_opening_words_like_the_screenshot(self):
        words = [r.text.replace("...", "").split() for r in self.rows[1:7]]
        self.assertEqual([len(w) for w in words], [4, 5, 3, 4, 4, 3])
        self.assertTrue(all(r.text.endswith("...") for r in self.rows if isinstance(r, RubRow)))
        self.assertNotIn(chr(0x06DE), "".join(r.text for r in self.rows if isinstance(r, RubRow)))


class TextTest(unittest.TestCase):
    def test_opening_words_cut(self):
        text = "أَتَأْمُرُونَ ٱلنَّاسَ بِٱلْبِرِّ وَتَنسَوْنَ أَنفُسَكُمْ"
        self.assertEqual(opening_words(text), "أَتَأْمُرُونَ ٱلنَّاسَ بِٱلْبِرِّ...")
        self.assertEqual(opening_words("كَلِمَةٌ"), "كَلِمَةٌ...")
        self.assertEqual(opening_words(chr(0x06DE) + " سَيَقُولُ"), "سَيَقُولُ...")

    def test_verse_count_text(self):
        self.assertEqual(verse_count_text(7), "٧ آيات")
        self.assertEqual(verse_count_text(286), "٢٨٦ آية")
        self.assertEqual(verse_count_text(200, "western"), "200 آية")
        self.assertEqual(verse_count_text(3), "٣ آيات")
        self.assertEqual(verse_count_text(11), "١١ آية")


if __name__ == "__main__":
    unittest.main()
