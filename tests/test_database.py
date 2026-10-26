"""Checks on the built database.

Several expected values come from screenshots of the Quran Android app
(chapter list, juz' pages, rub' rows of juz' 1 and 6), so a pass means the data
agrees with the app this one is modelled on.
"""

import json
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import ROOT, database_path  # noqa: E402
from quran_app.arabic_text import normalize_for_search  # noqa: E402

db = None


def setUpModule():
    global db
    db = sqlite3.connect(database_path())


def tearDownModule():
    db.close()


def verse(chapter, number):
    return db.execute(
        "SELECT id, page, juz, rub FROM verses WHERE chapter=? AND number=?", (chapter, number)
    ).fetchone()


class StructureTest(unittest.TestCase):
    def test_totals(self):
        one = lambda sql: db.execute(sql).fetchone()[0]
        self.assertEqual(one("SELECT COUNT(*) FROM chapters"), 114)
        self.assertEqual(one("SELECT COUNT(*) FROM verses"), 6236)
        self.assertEqual(one("SELECT COUNT(*) FROM words"), 77430)
        self.assertEqual(one("SELECT COUNT(DISTINCT page) FROM verses"), 604)
        self.assertEqual(one("SELECT COUNT(*) FROM juz"), 30)
        self.assertEqual(one("SELECT COUNT(*) FROM rubs"), 240)
        self.assertEqual(one("SELECT SUM(has_sajdah) FROM verses"), 15)

    def test_every_verse_has_words_in_order(self):
        broken = db.execute(
            "SELECT v.id FROM verses v LEFT JOIN words w ON w.verse_id=v.id"
            " GROUP BY v.id HAVING COUNT(w.id) != v.word_count"
            " OR MAX(w.position) != v.word_count"
        ).fetchall()
        self.assertEqual(broken, [])

    def test_chapter_list_like_quran_android(self):
        rows = {
            r[0]: r[1:]
            for r in db.execute("SELECT id, revelation, verse_count, start_page FROM chapters")
        }
        self.assertEqual(rows[1], ("meccan", 7, 1))
        self.assertEqual(rows[2], ("medinan", 286, 2))
        self.assertEqual(rows[3], ("medinan", 200, 50))

    def test_juz_start_pages_like_quran_android(self):
        pages = dict(db.execute("SELECT id, start_page FROM juz"))
        self.assertEqual([pages[1], pages[2], pages[3], pages[6]], [1, 22, 42, 102])
        self.assertEqual(pages[30], 582)

    def test_juz_that_start_in_the_middle_of_a_chapter(self):
        first = lambda juz: db.execute(
            "SELECT v.chapter, v.number FROM juz j JOIN verses v ON v.id=j.first_verse_id"
            " WHERE j.id=?", (juz,)
        ).fetchone()
        self.assertEqual(first(2), (2, 142))
        self.assertEqual(first(3), (2, 253))
        self.assertEqual(first(4), (3, 92))
        self.assertEqual(first(11), (9, 94))

    def test_rub_rows_of_juz_1_like_quran_android(self):
        expected = [((1, 1), 1), ((2, 26), 5), ((2, 44), 7), ((2, 60), 9), ((2, 75), 11), ((2, 92), 14)]
        actual = db.execute(
            "SELECT v.chapter, v.number, r.start_page FROM rubs r"
            " JOIN verses v ON v.id=r.first_verse_id WHERE r.id BETWEEN 1 AND 6 ORDER BY r.id"
        ).fetchall()
        self.assertEqual([((s, n), p) for s, n, p in actual], expected)

    def test_rub_rows_of_juz_6_like_quran_android(self):
        expected = [((4, 148), 102), ((4, 163), 104), ((5, 1), 106), ((5, 12), 109), ((5, 27), 112)]
        actual = db.execute(
            "SELECT v.chapter, v.number, r.start_page, r.hizb, r.position_in_hizb FROM rubs r"
            " JOIN verses v ON v.id=r.first_verse_id WHERE r.id BETWEEN 41 AND 45 ORDER BY r.id"
        ).fetchall()
        self.assertEqual([((s, n), p) for s, n, p, _, _ in actual], expected)
        # The circles in the screenshot: hizb 11 starts, then 2, 3, 4 quarters, then hizb 12
        self.assertEqual([(h, q) for *_, h, q in actual], [(11, 1), (11, 2), (11, 3), (11, 4), (12, 1)])

    def test_a_verse_knows_its_place(self):
        # Ayat al-Kursi is on page 42, in juz' 3, in the rub' that starts at 2:253
        _, page, juz, rub = verse(2, 255)
        self.assertEqual((page, juz, rub), (42, 3, 17))


class TextTest(unittest.TestCase):
    def test_uthmani_text_keeps_all_marks(self):
        # The stored text must be the source text untouched, apart from the
        # trailing verse number (and the no-break space before it).
        source = json.loads(
            (ROOT / "data" / "sources" / "kfgqpc" / "hafsData_v18.json").read_text(encoding="utf-8")
        )
        by_key = {(r["sora"], r["aya_no"]): r["aya_text"].rsplit(chr(0x00A0), 1)[0] for r in source}
        stored = dict(db.execute("SELECT chapter || ':' || number, text_uthmani FROM verses"))
        for (chapter, number), expected in by_key.items():
            self.assertEqual(stored[f"{chapter}:{number}"], expected, (chapter, number))
        # and the marks really are there
        first = stored["1:1"]
        self.assertNotEqual(first, normalize_for_search(first))
        self.assertEqual(normalize_for_search(first), "بسم الله الرحمن الرحيم")

    def test_verse_number_is_not_part_of_the_text(self):
        digits = db.execute(
            "SELECT COUNT(*) FROM verses WHERE text_uthmani GLOB '*[٠-٩]*'"
        ).fetchone()[0]
        self.assertEqual(digits, 0)

    def test_search_columns_have_no_marks(self):
        for column in ("search_uthmani", "search_imlaei"):
            marked = db.execute(
                f"SELECT COUNT(*) FROM verses WHERE {column} GLOB '*[ً-ٰٟۖ-ۭ]*'"
            ).fetchone()[0]
            self.assertEqual(marked, 0, column)

    def test_walaein_found_with_and_without_diacritics(self):
        def find(query):
            needle = normalize_for_search(query)
            return {
                (s, n)
                for s, n in db.execute(
                    "SELECT chapter, number FROM verses"
                    " WHERE instr(search_imlaei, ?) > 0 OR instr(search_uthmani, ?) > 0",
                    (needle, needle),
                )
            }

        plain, marked = find("ولئن"), find("وَلَئِن")
        self.assertEqual(plain, marked)
        self.assertIn((2, 120), plain)
        self.assertGreater(len(plain), 10)

    def test_modern_spelling_finds_uthmani_spelling(self):
        # In the Uthmani script this is written الصلوة with a dagger alef
        needle = normalize_for_search("الصلاة")
        found = db.execute(
            "SELECT COUNT(*) FROM verses WHERE instr(search_imlaei, ?) > 0", (needle,)
        ).fetchone()[0]
        self.assertGreater(found, 50)


class TafsirTest(unittest.TestCase):
    def test_five_sources_registered_in_tab_order(self):
        titles = [r[0] for r in db.execute("SELECT title FROM text_sources ORDER BY sort_order")]
        self.assertEqual(
            titles,
            ["المختصر", "الميسر", "Sahih International", "إعراب القرآن", "التحرير والتنوير"],
        )

    def test_every_source_covers_every_verse(self):
        for source_id, count in db.execute(
            "SELECT source_id, COUNT(*) FROM text_group_of_verse GROUP BY source_id"
        ):
            self.assertEqual(count, 6236, source_id)

    def test_a_group_covers_several_verses(self):
        row = db.execute(
            "SELECT g.first_verse_id, g.last_verse_id, length(g.body) FROM text_group_of_verse m"
            " JOIN text_groups g ON g.id=m.group_id"
            " JOIN text_sources s ON s.id=m.source_id"
            " WHERE s.key='muyassar' AND m.verse_id=?", (verse(2, 46)[0],)
        ).fetchone()
        self.assertEqual(row[0], verse(2, 45)[0])
        self.assertEqual(row[1], verse(2, 46)[0])
        self.assertGreater(row[2], 0)


if __name__ == "__main__":
    unittest.main()
