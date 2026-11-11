import json
import tempfile
import unittest
from pathlib import Path

from quran_app import audio_presets as ap

COUNTS = {1: 7, 2: 286, 112: 4}


def verse_count(chapter):
    return COUNTS.get(chapter, 10)


class CleanTest(unittest.TestCase):
    def test_keeps_valid_drops_invalid(self):
        preset = ap.clean({"name": " Dua ", "from": [2, 255], "to": [2, 999], "reciter": "nobody",
                           "style": "mujawwad", "speed": 5, "verse_repeats": 3, "passage_repeats": 0,
                           "extra": 1}, verse_count)
        self.assertEqual(preset, {"name": "Dua", "from": [2, 255], "style": "mujawwad", "verse_repeats": 3})

    def test_needs_a_name(self):
        self.assertIsNone(ap.clean({"from": [1, 1]}, verse_count))
        self.assertIsNone(ap.clean({"name": "  "}, verse_count))
        self.assertIsNone(ap.clean("text", verse_count))

    def test_a_preset_may_hold_only_a_name(self):
        self.assertEqual(ap.clean({"name": "x"}, verse_count), {"name": "x"})

    def test_speed_is_rounded_and_bools_rejected(self):
        self.assertEqual(ap.clean({"name": "x", "speed": 1.333}, verse_count)["speed"], 1.33)
        self.assertNotIn("speed", ap.clean({"name": "x", "speed": True}, verse_count))
        self.assertNotIn("verse_repeats", ap.clean({"name": "x", "verse_repeats": True}, verse_count))
        self.assertNotIn("from", ap.clean({"name": "x", "from": [True, 1]}, verse_count))


class FileTest(unittest.TestCase):
    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "sub" / "audio_presets.json"

    def test_round_trip_with_arabic(self):
        presets = [{"name": "سورة الإخلاص", "from": [112, 1], "to": [112, 4], "speed": 0.75}]
        ap.save(self.path, presets)
        self.assertIn("سورة الإخلاص", self.path.read_text(encoding="utf-8"))
        self.assertEqual(ap.load(self.path, verse_count), presets)

    def test_missing_file_is_empty(self):
        self.assertEqual(ap.load(self.path, verse_count), [])

    def test_unreadable_file_is_set_aside(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json", encoding="utf-8")
        self.assertEqual(ap.load(self.path, verse_count), [])
        self.assertFalse(self.path.exists())
        self.assertTrue(self.path.with_name("audio_presets.json.bad").exists())

    def test_bad_entries_and_duplicates_are_skipped(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"presets": [{"name": "a"}, 5, {"name": "a", "speed": 2}, {"name": "b"}]}),
                             encoding="utf-8")
        self.assertEqual([p["name"] for p in ap.load(self.path, verse_count)], ["a", "b"])

    def test_upsert_remove_find(self):
        a, b = {"name": "a"}, {"name": "b"}
        presets = ap.upsert(ap.upsert([], a), b)
        replaced = ap.upsert(presets, {"name": "a", "speed": 2})
        self.assertEqual([p["name"] for p in replaced], ["a", "b"])
        self.assertEqual(replaced[0]["speed"], 2)
        self.assertEqual(ap.remove(replaced, "a"), [b])
        self.assertEqual(ap.find(replaced, "b"), b)
        self.assertIsNone(ap.find(replaced, "zzz"))


class SummaryTest(unittest.TestCase):
    def test_summary(self):
        name = {2: "البقرة"}.get
        text = ap.summary({"name": "x", "from": [2, 1], "to": [2, 5], "reciter": "minshawi", "style": "murattal",
                           "speed": 1.5, "verse_repeats": 2, "passage_repeats": 3}, name, "western")
        self.assertEqual(text, "البقرة: الآيات 1 – 5 · محمد صديق المنشاوي · مرتل · السرعة 1.5 · تكرار الآية 2 · تكرار المقطع 3")
        self.assertEqual(ap.summary({"name": "x"}, name), "بلا إعدادات")
