import unittest

from quran_app.shortcuts import SHORTCUTS


class ShortcutsTest(unittest.TestCase):
    def test_listed_once_with_a_meaning(self):
        keys = [k for k, _ in SHORTCUTS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(meaning for _, meaning in SHORTCUTS))
        self.assertIn("Ctrl+/", keys)
