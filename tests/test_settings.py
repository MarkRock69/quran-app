import unittest

from quran_app.settings import Settings
from quran_app.themes import THEMES


class SettingsTest(unittest.TestCase):
    def test_remembers_values_and_defaults(self):
        settings = Settings(":memory:")
        self.assertEqual(settings.get("theme", "light"), "light")
        settings.set("theme", "dark")
        settings.set("tafsir_order", ["irab", "sahih"])
        settings.set("theme", "light")
        self.assertEqual(settings.get("theme"), "light")
        self.assertEqual(settings.get("tafsir_order"), ["irab", "sahih"])
        settings.close()


class ThemeTest(unittest.TestCase):
    def test_both_themes_define_the_same_colours(self):
        self.assertEqual(set(THEMES["light"]), set(THEMES["dark"]))


if __name__ == "__main__":
    unittest.main()
