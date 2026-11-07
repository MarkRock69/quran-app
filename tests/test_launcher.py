import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from install_launcher import desktop_entry  # noqa: E402


class LauncherTest(unittest.TestCase):
    def test_entry(self):
        text = desktop_entry(Path("/home/me/quran app"), "/usr/bin/python3")
        self.assertIn('Exec="/usr/bin/python3" -m quran_app.reader', text)
        self.assertIn("Path=/home/me/quran app", text)
        self.assertIn("Terminal=false", text)
        self.assertTrue(text.startswith("[Desktop Entry]"))
