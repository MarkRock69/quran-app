import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import database_path  # noqa: E402
from quran_app.mushaf import Mushaf  # noqa: E402
from quran_app.tafsir import body_to_html  # noqa: E402

mushaf = None


def setUpModule():
    global mushaf
    mushaf = Mushaf(database_path())


def tearDownModule():
    mushaf.close()


class SourcesTest(unittest.TestCase):
    def test_six_in_the_agreed_order_with_the_clear_quran_reserved(self):
        titles = [(s.title, s.available, s.rtl) for s in mushaf.tafsir_sources()]
        self.assertEqual(
            titles,
            [("المختصر", True, True), ("الميسر", True, True), ("Sahih International", True, False),
             ("The Clear Qur'an", False, False), ("إعراب القرآن", True, True), ("التحرير والتنوير", True, True)],
        )

    def test_the_unavailable_source_has_no_entry(self):
        clear = mushaf.tafsir_sources()[3]
        self.assertIsNone(mushaf.tafsir_entry(clear, 2, 255))


class EntryTest(unittest.TestCase):
    def test_every_available_source_answers_for_ayat_al_kursi(self):
        for source in mushaf.tafsir_sources():
            if source.available:
                entry = mushaf.tafsir_entry(source, 2, 255)
                self.assertIsNotNone(entry, source.title)
                self.assertTrue(entry.first <= (2, 255) <= entry.last, source.title)
                self.assertGreater(len(entry.html), 100, source.title)

    def test_a_text_covering_several_verses_is_found_from_each(self):
        mukhtasar = mushaf.tafsir_sources()[0]
        first = mushaf.tafsir_entry(mukhtasar, 1, 1)
        spans = [(c, n) for c in range(1, 3) for n in range(1, 40) if mushaf.tafsir_entry(mukhtasar, c, n)
                 and mushaf.tafsir_entry(mukhtasar, c, n).first != mushaf.tafsir_entry(mukhtasar, c, n).last]
        self.assertTrue(first is not None and spans)
        c, n = spans[0]
        entry = mushaf.tafsir_entry(mukhtasar, c, n)
        self.assertEqual(mushaf.tafsir_entry(mukhtasar, *entry.last).first, entry.first)

    def test_sahih_footnotes_become_numbered_notes(self):
        sahih = mushaf.tafsir_sources()[2]
        html = mushaf.tafsir_entry(sahih, 2, 255).html
        self.assertNotIn("[[", html)
        self.assertIn("<sup>1</sup>", html)
        self.assertIn("<hr>", html)

    def test_tahrir_page_numbers_are_dropped(self):
        tahrir = mushaf.tafsir_sources()[5]
        for verse in ((2, 116), (2, 117)):
            self.assertNotIn("page-num", mushaf.tafsir_entry(tahrir, *verse).html)

    def test_plain_text_becomes_paragraphs_and_is_escaped(self):
        self.assertEqual(body_to_html("mukhtasar", "a < b\n\nc"), "<p>a &lt; b</p><p>c</p>")

    def test_footnote_order_and_escaping(self):
        html = body_to_html("sahih", "One[[first <note>]] two[[second]] three.")
        self.assertIn("One<sup>1</sup> two<sup>2</sup> three.", html)
        self.assertIn("<p><sup>1</sup> first &lt;note&gt;</p>", html)


class GlyphTest(unittest.TestCase):
    def test_verse_of_glyph(self):
        first, last = mushaf.verse_cells(2, 255)
        self.assertEqual(mushaf.verse_of_glyph(first), (2, 255))
        self.assertEqual(mushaf.verse_of_glyph(last), (2, 255))

    def test_first_verse_of_page(self):
        self.assertEqual(mushaf.first_verse_of_page(1), (1, 1))
        self.assertEqual(mushaf.first_verse_of_page(2), (2, 1))


if __name__ == "__main__":
    unittest.main()
