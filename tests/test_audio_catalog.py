import tempfile
import unittest
from pathlib import Path

from quran_app.audio_catalog import (
    RECITERS, available, build_queue, file_name, flat_name, next_index, parse_md5, playlist, previous_index, reciter,
    verse_path,
)


class NamesTest(unittest.TestCase):
    def test_file_names(self):
        self.assertEqual(file_name(1, 1), "001001.mp3")
        self.assertEqual(file_name(114, 6), "114006.mp3")
        self.assertEqual(file_name(2, 0), "002000.mp3")  # the basmala of chapter 2
        self.assertEqual(verse_path("/a", "minshawi", "murattal", 2, 255), Path("/a/minshawi/murattal/002255.mp3"))

    def test_zip_members_are_flattened_and_others_ignored(self):
        self.assertEqual(flat_name("Minshawy_Murattal_128kbps/001001.mp3"), "001001.mp3")
        self.assertEqual(flat_name("001001.mp3"), "001001.mp3")
        for other in ("000_checksum.md5", "000_test_008006.mp3", "x/zips/", "12345.mp3", "folder/"):
            self.assertIsNone(flat_name(other))

    def test_md5_list(self):
        text = "d41d8cd98f00b204e9800998ecf8427e  001001.mp3\nD41D8CD98F00B204E9800998ECF8427F *dir/001002.mp3\nbad line\n"
        self.assertEqual(parse_md5(text), {"001001.mp3": "d41d8cd98f00b204e9800998ecf8427e",
                                          "001002.mp3": "d41d8cd98f00b204e9800998ecf8427f"})

    def test_the_three_reciters(self):
        self.assertEqual([r.key for r in RECITERS], ["minshawi", "jabir", "abdulbasit"])
        self.assertEqual(sorted(reciter("minshawi").recordings), ["mujawwad", "murattal"])
        self.assertEqual(list(reciter("jabir").recordings), ["murattal"])


class PlaylistTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        base = self.root / "minshawi" / "murattal"
        base.mkdir(parents=True)
        for name in ("001000", "001001", "002000", "002001", "002002", "009001", "114001"):
            (base / f"{name}.mp3").touch()

    def play(self, verses, **kw):
        paths, missing = playlist(self.root, "minshawi", "murattal", verses, **kw)
        return [p.name for p in paths], missing

    def test_basmala_comes_before_the_first_verse_of_a_chapter(self):
        self.assertEqual(self.play([(2, 1), (2, 2)])[0], ["002000.mp3", "002001.mp3", "002002.mp3"])

    def test_not_for_chapters_1_and_9_or_mid_chapter_starts(self):
        self.assertEqual(self.play([(1, 1)])[0], ["001001.mp3"])
        self.assertEqual(self.play([(9, 1)])[0], ["009001.mp3"])
        self.assertEqual(self.play([(2, 2)])[0], ["002002.mp3"])

    def test_a_passage_across_chapters(self):
        self.assertEqual(self.play([(1, 1), (2, 1)])[0], ["001001.mp3", "002000.mp3", "002001.mp3"])

    def test_basmala_can_be_turned_off(self):
        self.assertEqual(self.play([(2, 1)], basmala=False)[0], ["002001.mp3"])

    def test_queue_items_know_their_verse(self):
        items, _ = build_queue(self.root, "minshawi", "murattal", [(2, 1), (2, 2)])
        self.assertEqual([(i.chapter, i.number) for i in items], [(2, 0), (2, 1), (2, 2)])

    def test_repeats(self):
        items, _ = build_queue(self.root, "minshawi", "murattal", [(2, 1), (2, 2)], verse_repeats=2, passage_repeats=2)
        self.assertEqual([(i.number) for i in items], [0, 1, 1, 2, 2, 0, 1, 1, 2, 2])  # basmala once per pass and verse

    def test_next_and_previous_move_by_verse_not_by_repetition(self):
        items, _ = build_queue(self.root, "minshawi", "murattal", [(2, 1), (2, 2)], verse_repeats=2)
        # items: basmala, 1, 1, 2, 2  (groups 0, 1, 1, 2, 2)
        self.assertEqual(next_index(items, 0), 1)
        self.assertEqual(next_index(items, 1), 3)
        self.assertEqual(next_index(items, 2), 3)
        self.assertIsNone(next_index(items, 4))
        self.assertEqual(previous_index(items, 4), 1)
        self.assertEqual(previous_index(items, 3), 1)
        self.assertEqual(previous_index(items, 2), 0)
        self.assertEqual(previous_index(items, 0), 0)

    def test_available_lists_only_what_is_on_disk(self):
        self.assertEqual(available(self.root), {"minshawi": ["murattal"]})
        self.assertEqual(available(self.root / "nothing"), {})

    def test_missing_verses_are_reported_but_missing_basmalas_are_not(self):
        names, missing = self.play([(114, 1), (114, 2)])
        self.assertEqual(names, ["114001.mp3"])
        self.assertEqual(missing, [(114, 2)])


if __name__ == "__main__":
    unittest.main()


class SpeedTests(unittest.TestCase):
    def test_parse(self):
        from quran_app.audio_catalog import parse_speed, speed_text
        self.assertEqual(parse_speed("1.25"), 1.25)
        self.assertEqual(parse_speed("١٫٥"), 1.5)
        self.assertEqual(parse_speed("0.333"), 0.33)
        self.assertEqual(parse_speed("3"), 3.0)
        self.assertEqual(speed_text(1.0), "1")
        self.assertEqual(speed_text(1.33), "1.33")
        for bad in ("0.24", "3.01", "abc", ""):
            with self.assertRaises(ValueError):
                parse_speed(bad)
