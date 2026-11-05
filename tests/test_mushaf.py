import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import database_path  # noqa: E402
from quran_app.mushaf import Mushaf, format_number, hit_test, layout_page, spread_of  # noqa: E402

mushaf = None


def setUpModule():
    global mushaf
    mushaf = Mushaf(database_path())


def tearDownModule():
    mushaf.close()


def verse_text(chapter, number):
    import sqlite3

    return sqlite3.connect(database_path()).execute(
        "SELECT text_uthmani FROM verses WHERE chapter=? AND number=?", (chapter, number)
    ).fetchone()[0]


class SpreadTest(unittest.TestCase):
    def test_first_spread_has_page_one_on_the_right(self):
        self.assertEqual(spread_of(1), (2, 1))
        self.assertEqual(spread_of(2), (2, 1))

    def test_right_is_odd_and_comes_first(self):
        for page in (3, 4, 42, 43):
            left, right = spread_of(page)
            self.assertEqual(right % 2, 1)
            self.assertEqual(left, right + 1)
        self.assertEqual(spread_of(42), (42, 41))
        self.assertEqual(spread_of(43), (44, 43))

    def test_last_spread_is_603_and_604(self):
        self.assertEqual(spread_of(603), (604, 603))
        self.assertEqual(spread_of(604), (604, 603))

    def test_every_page_belongs_to_exactly_one_spread(self):
        seen = {}
        for page in range(1, 605):
            seen.setdefault(spread_of(page), []).append(page)
        shown = sorted(p for left, right in seen for p in (left, right))
        self.assertEqual(shown, list(range(1, 605)))
        self.assertEqual(len(seen), 302)

    def test_no_such_page(self):
        for page in (0, 605):
            with self.assertRaises(ValueError):
                spread_of(page)


class PageTest(unittest.TestCase):
    def test_every_page_has_its_lines_and_cells(self):
        for number in (1, 2, 3, 42, 300, 604):
            page = mushaf.page(number)
            self.assertEqual(len(page.lines), 8 if number <= 2 else 15, number)
            self.assertTrue(all(line.cells for line in page.lines if line.kind == "text"))
            self.assertTrue(all(not line.cells for line in page.lines if line.kind != "text"))

    def test_chapter_start_pages_have_a_name_line_then_a_basmala(self):
        page = mushaf.page(2)  # Al-Baqara begins here
        kinds = [line.kind for line in page.lines]
        self.assertEqual(kinds[:2], ["chapter_name", "basmala"])
        self.assertEqual(page.lines[0].chapter, 2)

    def test_the_first_chapter_has_a_name_line_but_its_basmala_is_verse_one(self):
        page = mushaf.page(1)
        self.assertEqual([line.kind for line in page.lines][:2], ["chapter_name", "text"])

    def test_cells_are_in_reading_order_across_the_whole_mushaf(self):
        previous = 0
        for number in (41, 42, 43):
            for cell in mushaf.page(number).cells:
                self.assertGreater(cell.glyph_id, previous)
                previous = cell.glyph_id

    def test_a_page_ends_with_a_verse_end_marker(self):
        for number in (3, 100, 500):
            self.assertTrue(mushaf.page(number).cells[-1].is_verse_end)

    def test_page_of_verse(self):
        self.assertEqual(mushaf.page_of_verse(2, 255), 42)
        self.assertEqual(mushaf.page_of_verse(114, 6), 604)

    def test_ayat_al_kursi_is_on_its_page(self):
        verses = {(cell.chapter, cell.number) for cell in mushaf.page(42).cells}
        self.assertIn((2, 255), verses)


class CopyTest(unittest.TestCase):
    def test_a_whole_verse_copies_as_its_text_and_number(self):
        first, last = mushaf.verse_cells(1, 1)
        text = mushaf.text_between(first, last)
        stored = verse_text(1, 1)
        self.assertEqual(text, stored + " " + chr(0xFD3F) + "١" + chr(0xFD3E))

    def test_western_digits(self):
        first, last = mushaf.verse_cells(2, 255)
        self.assertTrue(mushaf.text_between(first, last, digits="western").endswith("255" + chr(0xFD3E)))

    def test_selection_direction_does_not_matter(self):
        first, last = mushaf.verse_cells(1, 2)
        self.assertEqual(mushaf.text_between(first, last), mushaf.text_between(last, first))

    def test_a_partial_selection_is_whole_words(self):
        first, _ = mushaf.verse_cells(1, 1)
        self.assertEqual(mushaf.text_between(first + 1, first + 2), " ".join(verse_text(1, 1).split()[1:3]))

    def test_stop_signs_stay_with_their_words(self):
        first, last = mushaf.verse_cells(2, 26)
        self.assertIn("ۚ", mushaf.text_between(first, last))

    def test_a_word_drawn_as_two_glyphs_is_written_once(self):
        # 36:22: the page draws "ما لي" as two glyphs, the text has one word
        first, last = mushaf.verse_cells(36, 22)
        cells = [c for p in range(mushaf.page_of_verse(36, 22), mushaf.page_of_verse(36, 22) + 1)
                 for c in mushaf.page(p).cells if (c.chapter, c.number) == (36, 22)]
        self.assertEqual(cells[0].first_word, cells[1].first_word)
        text = mushaf.text_between(first, last)
        self.assertEqual(len(text.split()), 7 + 1)  # seven words and the number

    def test_the_text_of_a_page_matches_the_database_verses(self):
        import sqlite3

        db = sqlite3.connect(database_path())
        for number in (3, 250, 604):
            cells = mushaf.page(number).cells
            copied = mushaf.text_between(cells[0].glyph_id, cells[-1].glyph_id)
            expected = []
            for verse_id in dict.fromkeys(c.verse_id for c in cells):
                text = db.execute("SELECT text_uthmani FROM verses WHERE id=?", (verse_id,)).fetchone()[0]
                expected.append(text.replace(chr(0x06DE), "").split())
            flat = [word for words in expected for word in words]
            copied_words = [w for w in copied.split() if not w.startswith(chr(0xFD3F))]
            self.assertEqual(copied_words, flat, number)

    def test_digits(self):
        self.assertEqual(format_number(255), "٢٥٥")
        self.assertEqual(format_number(255, "western"), "255")


class GeometryTest(unittest.TestCase):
    @staticmethod
    def measure(text):
        return 1.0 * len(text)  # every character one em wide

    def setUp(self):
        self.page = mushaf.page(42)
        self.placed, self.size = layout_page(self.page, self.measure, 540, 750, default_size=20)

    def test_every_cell_is_placed_once(self):
        cells = [p.cell for p in self.placed if p.cell]
        self.assertEqual(len(cells), len(self.page.cells))

    def test_justified_lines_fill_the_width_exactly(self):
        by_line = {}
        for item in self.placed:
            if item.cell:
                by_line.setdefault(item.line.number, []).append(item)
        for items in by_line.values():
            if not items[0].line.centered and len(items) > 1:
                self.assertAlmostEqual(max(i.x + i.width for i in items), 540, places=6)
                self.assertAlmostEqual(min(i.x for i in items), 0, delta=0.5 * self.size + 540)
        widest = max(
            sum(i.width for i in items) for items in by_line.values() if not items[0].line.centered
        )
        self.assertAlmostEqual(widest, 540, places=6)  # the widest line has no extra gap

    def test_first_cell_of_a_line_is_at_the_right(self):
        for line in self.page.lines:
            if line.kind != "text":
                continue
            items = [p for p in self.placed if p.cell in line.cells]
            xs = [p.x for p in items]
            self.assertEqual(xs, sorted(xs, reverse=True))

    def test_lines_are_evenly_spaced_and_inside_the_box(self):
        tops = sorted({round(p.y, 6) for p in self.placed})
        self.assertEqual(len(tops), 15)
        self.assertAlmostEqual(tops[1] - tops[0], 50)
        self.assertTrue(all(-1e-6 <= p.x and p.x + p.width <= 540 + 1e-6 for p in self.placed if p.cell))

    def test_centered_lines_are_centered(self):
        placed, _ = layout_page(mushaf.page(1), self.measure, 540, 750, default_size=20)
        line = next(l for l in mushaf.page(1).lines if l.kind == "text" and l.centered)
        items = [p for p in placed if p.cell in line.cells]
        left, right = min(p.x for p in items), max(p.x + p.width for p in items)
        self.assertAlmostEqual(left + right, 540, places=6)

    def test_pages_without_justified_lines_use_the_default_size(self):
        _, size = layout_page(mushaf.page(1), self.measure, 540, 750, default_size=20)
        self.assertEqual(size, 20)

    def test_hit_test_finds_cells_and_nearest_cell(self):
        item = next(p for p in self.placed if p.cell)
        self.assertEqual(hit_test(self.placed, item.x + 1, item.y + 1), item.cell)
        self.assertEqual(hit_test(self.placed, -50, item.y + 1) is not None, True)  # beyond the left edge
        self.assertIsNone(hit_test(self.placed, 10, 10_000))


if __name__ == "__main__":
    unittest.main()
