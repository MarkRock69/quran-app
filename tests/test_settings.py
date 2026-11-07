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


class TabOrderTests(unittest.TestCase):
    def test_order_tabs(self):
        from quran_app.settings import order_tabs
        tabs = {"a": 1, "b": 2, "c": 3}
        self.assertEqual(order_tabs(["c", "a"], tabs), ["c", "a", "b"])
        self.assertEqual(order_tabs(["x", "b", "b"], tabs), ["b", "a", "c"])
        self.assertEqual(order_tabs(None, tabs), ["a", "b", "c"])
