import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quran_app.arabic_text import has_letters, normalize_for_search, strip_marks  # noqa: E402
from quran_app.word_alignment import align_words  # noqa: E402


class NormalizeForSearchTest(unittest.TestCase):
    def test_diacritics_are_ignored(self):
        self.assertEqual(normalize_for_search("وَلَئِن"), normalize_for_search("ولئن"))

    def test_alef_variants_are_the_same_letter(self):
        for variant in "أإآٱا":
            self.assertEqual(normalize_for_search(variant + "ب"), "اب")

    def test_yeh_and_alef_maksura(self):
        self.assertEqual(normalize_for_search("على"), normalize_for_search("علي"))

    def test_teh_marbuta_and_heh(self):
        self.assertEqual(normalize_for_search("رحمة"), normalize_for_search("رحمه"))

    def test_hamza_forms(self):
        self.assertEqual(normalize_for_search("سَأَلَ"), normalize_for_search("سال"))
        self.assertEqual(normalize_for_search("مُؤْمِن"), normalize_for_search("مومن"))
        self.assertEqual(normalize_for_search("جَزَآءً"), normalize_for_search("جزا"))

    def test_uthmani_dagger_alef_is_dropped(self):
        self.assertEqual(normalize_for_search("ٱلرَّحۡمَٰنِ"), "الرحمن")

    def test_no_break_space_and_rub_sign(self):
        self.assertEqual(normalize_for_search("۞ إِنَّ ٱللَّهَ"), "ان الله")

    def test_strip_marks_keeps_letters(self):
        self.assertEqual(strip_marks("بِسۡمِ"), "بسم")

    def test_has_letters(self):
        self.assertTrue(has_letters("بِسۡمِ"))
        self.assertFalse(has_letters("۞"))
        self.assertFalse(has_letters("ۖ"))


class AlignWordsTest(unittest.TestCase):
    def test_one_to_one(self):
        pairs, cost = align_words(["بِسۡمِ", "ٱللَّهِ"], ["بسم", "الله"])
        self.assertEqual(pairs, ["بسم", "الله"])
        self.assertEqual(cost, 0)

    def test_one_uthmani_word_for_two_modern_words(self):
        pairs, _ = align_words(["هَٰٓأَنتُمۡ", "هَٰٓؤُلَآءِ"], ["ها", "أنتم", "هؤلاء"])
        self.assertEqual(pairs, ["ها أنتم", "هؤلاء"])

    def test_the_split_can_be_anywhere_in_the_verse(self):
        pairs, _ = align_words(
            ["قَالَ", "أَوَلَوۡ", "كَانَ"], ["قال", "أو", "لو", "كان"]
        )
        self.assertEqual(pairs, ["قال", "أو لو", "كان"])

    def test_different_spelling_of_the_same_word(self):
        pairs, cost = align_words(["ٱلصَّلَوٰةَ"], ["الصلاة"])
        self.assertEqual(pairs, ["الصلاة"])
        self.assertEqual(cost, 1)


if __name__ == "__main__":
    unittest.main()
