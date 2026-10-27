import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quran_app.page_layout import word_spans  # noqa: E402


class WordSpansTest(unittest.TestCase):
    def test_normal_verse_is_one_to_one(self):
        self.assertEqual(word_spans(1, 1, 4, 4), [(1, 1), (2, 2), (3, 3), (4, 4)])

    def test_the_page_writes_one_word_as_two(self):
        spans = word_spans(36, 22, 8, 7)
        self.assertEqual(spans[:3], [(1, 1), (1, 1), (2, 2)])
        self.assertEqual(spans[-1], (7, 7))

    def test_the_page_writes_two_words_as_one(self):
        self.assertEqual(word_spans(37, 130, 3, 4), [(1, 1), (2, 2), (3, 4)])

    def test_a_count_that_does_not_add_up_is_an_error(self):
        with self.assertRaises(ValueError):
            word_spans(1, 1, 5, 4)
        with self.assertRaises(ValueError):
            word_spans(36, 22, 7, 7)  # this verse needs one extra glyph


if __name__ == "__main__":
    unittest.main()
