"""Bookmarks: pages the reader wants to come back to. Kept in a small file of their own, not in the Qur'an database."""

import sqlite3
from pathlib import Path

from .paths import USER_DB

DEFAULT_PATH = USER_DB


class Bookmarks:
    def __init__(self, path=DEFAULT_PATH):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(path))
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS bookmarks (page INTEGER PRIMARY KEY, added TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        self._connection.commit()

    def close(self):
        self._connection.close()

    def has(self, page):
        return self._connection.execute("SELECT 1 FROM bookmarks WHERE page = ?", (page,)).fetchone() is not None

    def pages(self):
        return [row[0] for row in self._connection.execute("SELECT page FROM bookmarks ORDER BY page")]

    def toggle(self, page):
        """Add the bookmark, or remove it if there. Returns True if the page is bookmarked now."""
        if self.has(page):
            self.remove(page)
            return False
        self._connection.execute("INSERT INTO bookmarks (page) VALUES (?)", (page,))
        self._connection.commit()
        return True

    def remove(self, page):
        self._connection.execute("DELETE FROM bookmarks WHERE page = ?", (page,))
        self._connection.commit()
