"""Small remembered choices (theme, number style, tafsir order), kept in the same user file as the bookmarks."""

import json
import sqlite3
from pathlib import Path

from .bookmarks import DEFAULT_PATH


class Settings:
    def __init__(self, path=DEFAULT_PATH):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(str(path))
        self._connection.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        self._connection.commit()

    def get(self, key, default=None):
        row = self._connection.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row[0])
        except ValueError:
            return default

    def set(self, key, value):
        self._connection.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, json.dumps(value)),
        )
        self._connection.commit()

    def close(self):
        self._connection.close()
