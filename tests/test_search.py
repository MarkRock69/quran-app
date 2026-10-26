import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import database_path  # noqa: E402
from quran_app.arabic_text import normalize_for_search  # noqa: E402
from quran_app.search import ALL_WORDS, ANY_WORD, SearchIndex, SearchOptions  # noqa: E402

index = None


def setUpModule():
    global index
    index = SearchIndex.from_database(database_path())


def coordinates(result):
    return [(index.verses[hit.verse_index].chapter, index.verses[hit.verse_index].number) for hit in result.hits]


def find(query, **options):
    return index.search(query, SearchOptions(**options))


def matched_text(snippet):
    return "".join(text for text, matched in snippet.segments if matched)


def whole_text(snippet):
    return "".join(text for text, _ in snippet.segments)


def snippet_for(coordinate, query, before=3, after=3, **options):
    result = find(query, **options)
    for hit, found_at in zip(result.hits, coordinates(result)):
        if found_at == coordinate:
            return index.render(hit, before, after)
    raise AssertionError(f"{query!r} not found at {coordinate}")


class DiacriticsTest(unittest.TestCase):
    def test_typing_without_diacritics_finds_the_marked_text(self):
        self.assertIn((2, 120), coordinates(find("ولئن")))

    def test_marks_typed_must_match_but_untyped_marks_are_ignored(self):
        everything = coordinates(find("ولئن"))
        with_marks = coordinates(find("وَلَئِن"))
        self.assertEqual(with_marks, everything)

    def test_a_typed_mark_narrows_the_results(self):
        # 2:120 has a kasra on the final noon, 2:145 starts with a sukun there
        # (and has a kasra form later), 3:157 has no mark on it at all
        kasra = coordinates(find("وَلَئِنِ"))
        sukun = coordinates(find("وَلَئِنْ"))
        self.assertIn((2, 120), kasra)
        self.assertNotIn((2, 120), sukun)
        self.assertIn((2, 145), sukun)
        self.assertNotIn((3, 157), kasra)
        self.assertNotIn((3, 157), sukun)

    def test_keyboard_sukun_matches_the_uthmani_sukun_sign(self):
        self.assertIn((2, 145), coordinates(find("وَلَئِنْ")))

    def test_tanween_typed_on_the_keyboard_matches_the_uthmani_form(self):
        # 2:75 has فَرِيقٞ written with the open dammatan sign
        self.assertIn((2, 75), coordinates(find("فَرِيقٌ")))

    def test_strict_marks_requires_exactly_the_typed_marks(self):
        loose = find("وَلَئِن")
        strict = find("وَلَئِن", strict_marks=True)
        self.assertLess(strict.occurrence_count, loose.occurrence_count)
        self.assertGreater(strict.occurrence_count, 0)


class SpellingTest(unittest.TestCase):
    def test_modern_spelling_finds_the_uthmani_spelling(self):
        result = find("الصلاة")
        self.assertGreater(result.verse_count, 50)
        snippet = snippet_for((2, 3), "الصلاة")
        self.assertEqual(normalize_for_search(matched_text(snippet)), "الصلوه")

    def test_letter_variants_are_interchangeable(self):
        self.assertEqual(coordinates(find("آمنوا")), coordinates(find("امنوا")))
        self.assertEqual(find("آمنوا").occurrence_count, find("امنوا").occurrence_count)
        self.assertEqual(find("على").verse_count, find("علي").verse_count)
        self.assertEqual(find("رحمة").verse_count, find("رحمه").verse_count)

    def test_a_typed_hamza_must_be_present_but_a_missing_one_matches_both(self):
        with_hamza = set(coordinates(find("ولئن")))
        without = set(coordinates(find("ولين")))
        self.assertTrue(with_hamza < without)
        self.assertNotIn((2, 144), with_hamza)  # فَلَنُوَلِّيَنَّكَ has no hamza
        self.assertIn((2, 144), without)

    def test_hamza_below_and_above_are_not_confused_with_plain_alef(self):
        self.assertLess(find("إن").occurrence_count, find("ان").occurrence_count)


class PhraseTest(unittest.TestCase):
    def test_default_is_the_exact_phrase_anywhere_in_a_word(self):
        self.assertEqual(coordinates(find("قيو")), [(2, 255), (3, 2), (20, 111)][: len(find("قيو").hits)])
        self.assertIn((2, 255), coordinates(find("قيو")))

    def test_words_must_be_in_order(self):
        self.assertIn((2, 255), coordinates(find("الحي القيوم")))
        self.assertEqual(find("القيوم الحي").hits, [])

    def test_spaces_around_a_word_mean_the_whole_word(self):
        loose = find("الله")
        whole = find(" الله ")
        self.assertLess(whole.occurrence_count, loose.occurrence_count)
        for hit, found_at in list(zip(whole.hits, coordinates(whole)))[:200]:
            snippet = index.render(hit, 0, 0)
            self.assertEqual(normalize_for_search(matched_text(snippet)), "الله", found_at)

    def test_a_space_at_one_end_only_anchors_that_end(self):
        starts = find(" ولئن")
        self.assertGreater(starts.occurrence_count, 0)
        for hit in starts.hits:
            shown = normalize_for_search(matched_text(index.render(hit, 0, 0)))
            self.assertTrue(shown.startswith(normalize_for_search("ولئن")), shown)

    def test_a_phrase_never_spans_two_verses(self):
        # last word of 1:1 followed by the first word of 1:2
        self.assertEqual(find("الرحيم الحمد").hits, [])

    def test_empty_and_mark_only_queries_find_nothing(self):
        for query in ("", "   ", "َ", "۞"):
            self.assertEqual(find(query).hits, [], repr(query))

    def test_results_come_in_mushaf_order(self):
        found = coordinates(find("الله"))
        self.assertEqual(found, sorted(found))

    def test_counts(self):
        result = find("الله")
        self.assertGreaterEqual(result.occurrence_count, result.verse_count)
        self.assertEqual(result.verse_count, len(set(coordinates(result))))


class ModesTest(unittest.TestCase):
    def test_all_words_in_any_order(self):
        self.assertIn((1, 2), coordinates(find("رب الحمد", mode=ALL_WORDS)))
        self.assertEqual(find("رب الحمد").hits, [])  # as a phrase, wrong order

    def test_all_words_needs_every_word(self):
        self.assertEqual(find("الحمد القيوم", mode=ALL_WORDS).hits, [])

    def test_any_word_is_the_union(self):
        either = set(coordinates(find("الحمد القيوم", mode=ANY_WORD)))
        self.assertTrue(set(coordinates(find("الحمد"))) <= either)
        self.assertTrue(set(coordinates(find("القيوم"))) <= either)

    def test_modes_highlight_every_found_word(self):
        result = find("رب الحمد", mode=ALL_WORDS)
        position = coordinates(result).index((1, 2))
        snippet = index.render(result.hits[position], 3, 3)
        pieces = [normalize_for_search(text) for text, matched in snippet.segments if matched]
        self.assertEqual(pieces, ["الحمد", "رب"])
        self.assertEqual(normalize_for_search(whole_text(snippet)), "الحمد لله رب العلمين")  # Uthmani spelling: dagger alef

    def test_unknown_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            SearchOptions(mode="nonsense")


class SnippetTest(unittest.TestCase):
    def test_three_words_of_context_on_each_side(self):
        snippet = snippet_for((2, 255), "الحي القيوم")
        self.assertEqual(normalize_for_search(whole_text(snippet)), "اله الا هو الحي القيوم لا تاخذه سنه")
        self.assertEqual(normalize_for_search(matched_text(snippet)), "الحي القيوم")
        self.assertFalse(snippet.starts_at_verse_start)
        self.assertFalse(snippet.ends_at_verse_end)

    def test_context_is_cut_at_the_edges_of_the_verse(self):
        snippet = snippet_for((1, 1), "الله")
        self.assertEqual(normalize_for_search(whole_text(snippet)), "بسم الله الرحمن الرحيم")
        self.assertTrue(snippet.starts_at_verse_start)
        self.assertTrue(snippet.ends_at_verse_end)

    def test_the_end_of_a_verse_stops_the_context(self):
        snippet = snippet_for((3, 2), "القيوم")
        self.assertTrue(snippet.ends_at_verse_end)
        self.assertEqual(normalize_for_search(whole_text(snippet)).split()[-1], "القيوم")

    def test_the_number_of_context_words_can_be_changed(self):
        for before, after in [(0, 0), (1, 0), (0, 2), (5, 5), (10, 10)]:
            snippet = snippet_for((2, 255), "الحي القيوم", before, after)
            words = normalize_for_search(whole_text(snippet)).split()
            # five words come before the match in this verse (الله لا إله إلا هو)
            self.assertEqual(len(words), min(before, 5) + 2 + after, (before, after))

    def test_no_context_shows_only_the_match(self):
        snippet = snippet_for((2, 255), "الحي القيوم", 0, 0)
        self.assertEqual(snippet.segments, ((matched_text(snippet), True),))

    def test_the_text_shown_is_the_uthmani_text_with_all_marks(self):
        snippet = snippet_for((1, 1), "الله", 3, 3)
        stored = sqlite3.connect(database_path()).execute(
            "SELECT text_uthmani FROM verses WHERE chapter=1 AND number=1"
        ).fetchone()[0]
        self.assertEqual(whole_text(snippet), stored)
        self.assertNotEqual(whole_text(snippet), normalize_for_search(stored))

    def test_part_of_a_word_is_highlighted_alone(self):
        snippet = snippet_for((2, 255), "قيو", 0, 0)
        self.assertEqual(normalize_for_search(matched_text(snippet)), "قيو")
        snippet = snippet_for((2, 255), "قيو", 3, 3)
        self.assertEqual(normalize_for_search(whole_text(snippet)).split()[3], "القيوم")

    def test_chapter_name_verse_number_and_page(self):
        snippet = snippet_for((2, 255), "الحي القيوم")
        self.assertEqual((snippet.chapter, snippet.number, snippet.coordinate), (2, 255, "2:255"))
        self.assertEqual(snippet.page, 42)
        self.assertIn("بَقَرَة", snippet.chapter_name)

    def test_a_match_over_two_uthmani_words_written_as_one(self):
        # هَٰٓأَنتُمۡ is one Uthmani word for two modern words ("ها أنتم")
        result = find("ها انتم")
        self.assertIn((3, 66), coordinates(result))
        snippet = snippet_for((3, 66), "ها انتم", 0, 0)
        self.assertIn("هَٰٓأَنتُمۡ", matched_text(snippet))

    def test_every_hit_of_a_broad_query_can_be_rendered(self):
        result = find("ا")
        self.assertGreater(result.occurrence_count, 40000)
        for hit in result.hits[::97]:
            snippet = index.render(hit)
            self.assertTrue(matched_text(snippet))
            self.assertTrue(normalize_for_search(matched_text(snippet)))


class SpeedTest(unittest.TestCase):
    def test_a_search_is_fast_enough_for_typing(self):
        import time

        for query in ("ا", "ال", "الله", "ولئن"):
            started = time.perf_counter()
            find(query)
            self.assertLess(time.perf_counter() - started, 1.0, query)


if __name__ == "__main__":
    unittest.main()
