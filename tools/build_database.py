#!/usr/bin/env python3
"""Build the app's SQLite database from the files in data/sources.

    python3 tools/build_database.py [--output path]   (default: ~/.local/share/quran-app/quran.db)

Inputs (all inside data/sources):
  kfgqpc/hafsData_v18.json   Uthmani text, modern-spelling text, page, line, juz'
  quran_meta.json            rub' start verses and place of revelation
  qul/*.zip                  tafsir and translation databases from QUL

The script checks its own work and stops with an error instead of producing a
database that looks right but is not.
"""

import argparse
import json
import re
import sqlite3
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from quran_app.arabic_text import has_letters, normalize_for_search  # noqa: E402
from quran_app.paths import DATABASE_PATH, write_stamp  # noqa: E402
from quran_app.page_layout import word_spans  # noqa: E402
from quran_app.word_alignment import align_words  # noqa: E402

SOURCES = ROOT / "data" / "sources"

EXPECTED = {
    "chapters": 114,
    "verses": 6236,
    "pages": 604,
    "juz": 30,
    "rubs": 240,
    "words": 77430,
    "glyphs": 83668,  # every word once more, plus a verse-end marker per verse
}

# (key, tab title, kind, language, QUL zip file, file inside the zip)
# The tab order is the order of `sort_order`. Slot 4 is kept free for the
# Clear Qur'an translation.
TEXT_SOURCES = [
    ("mukhtasar", "المختصر", "tafsir", "ar", 1,
     "arabic-al-mukhtasar-in-interpreting-the-noble-quran"),
    ("muyassar", "الميسر", "tafsir", "ar", 2, "ar-tafsir-muyassar"),
    ("sahih", "Sahih International", "translation", "en", 3,
     "en-sahih-international-inline-footnotes"),
    ("irab", "إعراب القرآن", "tafsir", "ar", 5, "i-rab-al-quran-li-al-darwish"),
    ("tahrir", "التحرير والتنوير", "tafsir", "ar", 6, "ar-tafseer-tahrir-al-tanwir"),
]

SCHEMA = """
CREATE TABLE chapters (
    id            INTEGER PRIMARY KEY,
    name_ar       TEXT NOT NULL,
    revelation    TEXT NOT NULL CHECK (revelation IN ('meccan', 'medinan')),
    verse_count   INTEGER NOT NULL,
    first_verse_id INTEGER NOT NULL,
    start_page    INTEGER NOT NULL
);

CREATE TABLE juz (
    id             INTEGER PRIMARY KEY,
    first_verse_id INTEGER NOT NULL,
    start_page     INTEGER NOT NULL
);

-- One row per quarter of a hizb. hizb = (id - 1) / 4 + 1.
-- position_in_hizb is 1 (the hizb itself begins here) to 4.
CREATE TABLE rubs (
    id               INTEGER PRIMARY KEY,
    hizb             INTEGER NOT NULL,
    position_in_hizb INTEGER NOT NULL,
    first_verse_id   INTEGER NOT NULL,
    start_page       INTEGER NOT NULL
);

CREATE TABLE verses (
    id              INTEGER PRIMARY KEY,
    chapter           INTEGER NOT NULL REFERENCES chapters(id),
    number          INTEGER NOT NULL,
    page            INTEGER NOT NULL,  -- page where the verse starts
    last_page       INTEGER NOT NULL,  -- page where it ends
    line_start      INTEGER NOT NULL,
    line_end        INTEGER NOT NULL,
    juz             INTEGER NOT NULL REFERENCES juz(id),
    rub             INTEGER NOT NULL REFERENCES rubs(id),
    has_sajdah      INTEGER NOT NULL,
    word_count      INTEGER NOT NULL,
    text_uthmani    TEXT NOT NULL,
    text_imlaei     TEXT NOT NULL,
    search_uthmani  TEXT NOT NULL,
    search_imlaei   TEXT NOT NULL,
    UNIQUE (chapter, number)
);
CREATE INDEX verses_page ON verses(page);

CREATE TABLE words (
    id             INTEGER PRIMARY KEY,
    verse_id       INTEGER NOT NULL REFERENCES verses(id),
    position       INTEGER NOT NULL,
    text_uthmani   TEXT NOT NULL,
    text_imlaei    TEXT NOT NULL,
    search_uthmani TEXT NOT NULL,
    search_imlaei  TEXT NOT NULL,
    UNIQUE (verse_id, position)
);

-- What is drawn on the Mushaf pages. A glyph is one word as the page font
-- draws it (with its stop sign, if any) or a verse-end marker.
CREATE TABLE glyphs (
    id         INTEGER PRIMARY KEY,   -- reading order over the whole Mushaf
    page       INTEGER NOT NULL,
    line       INTEGER NOT NULL,
    slot       INTEGER NOT NULL,      -- order within the line, 1 = first read
    verse_id   INTEGER NOT NULL REFERENCES verses(id),
    first_word INTEGER,               -- our word numbers it stands for;
    last_word  INTEGER,               -- both NULL for a verse-end marker
    text       TEXT NOT NULL,         -- the characters to draw in the page font
    UNIQUE (page, line, slot)
);
CREATE INDEX glyphs_verse ON glyphs(verse_id);

CREATE TABLE page_lines (
    page     INTEGER NOT NULL,
    line     INTEGER NOT NULL,
    kind     TEXT NOT NULL CHECK (kind IN ('chapter_name', 'basmala', 'text')),
    centered INTEGER NOT NULL,
    chapter  INTEGER,                 -- for chapter_name lines
    PRIMARY KEY (page, line)
) WITHOUT ROWID;

CREATE TABLE text_sources (
    id         INTEGER PRIMARY KEY,
    key        TEXT NOT NULL UNIQUE,
    title      TEXT NOT NULL,
    kind       TEXT NOT NULL CHECK (kind IN ('tafsir', 'translation')),
    language   TEXT NOT NULL,
    sort_order INTEGER NOT NULL
);

-- A tafsir often covers several verses at once; its text is stored once.
CREATE TABLE text_groups (
    id             INTEGER PRIMARY KEY,
    source_id      INTEGER NOT NULL REFERENCES text_sources(id),
    first_verse_id INTEGER NOT NULL,
    last_verse_id  INTEGER NOT NULL,
    body           TEXT NOT NULL
);

CREATE TABLE text_group_of_verse (
    source_id INTEGER NOT NULL REFERENCES text_sources(id),
    verse_id  INTEGER NOT NULL REFERENCES verses(id),
    group_id  INTEGER NOT NULL REFERENCES text_groups(id),
    PRIMARY KEY (source_id, verse_id)
) WITHOUT ROWID;
"""

TRAILING_NUMBER = re.compile(chr(0x00A0) + "[" + chr(0x0660) + "-" + chr(0x0669) + "]+$")
SAJDAH_SIGN = "۩"


def fail(message):
    sys.exit(f"BUILD FAILED: {message}")


def check_equal(label, actual, expected):
    if actual != expected:
        fail(f"{label}: expected {expected}, found {actual}")


def load_verses():
    path = SOURCES / "kfgqpc" / "hafsData_v18.json"
    rows = json.loads(path.read_text(encoding="utf-8"))
    rows.sort(key=lambda row: row["id"])
    check_equal("verse count in the text source", len(rows), EXPECTED["verses"])
    for expected_id, row in enumerate(rows, 1):
        check_equal("verse id sequence", row["id"], expected_id)
    return rows


def prepare_verses(rows, meta):
    """Turn the source rows into verse dictionaries with their words."""
    rub_starts = [tuple(pair) for pair in meta["rub_starts"]]
    check_equal("rub' starts", len(rub_starts), EXPECTED["rubs"])
    verse_id_of = {(row["sora"], row["aya_no"]): row["id"] for row in rows}
    rub_first_verse = [verse_id_of[pair] for pair in rub_starts]
    if rub_first_verse != sorted(rub_first_verse):
        fail("rub' starts are not in Qur'anic order")

    verses, words, alignment_costs = [], [], {}
    rub_index = 0
    for row in rows:
        verse_id = row["id"]
        while rub_index + 1 < len(rub_first_verse) and rub_first_verse[rub_index + 1] <= verse_id:
            rub_index += 1
        if not TRAILING_NUMBER.search(row["aya_text"]):
            fail(f"verse {row['sora']}:{row['aya_no']} has no trailing verse number")
        text_uthmani = TRAILING_NUMBER.sub("", row["aya_text"])

        uthmani_words = []
        for token in text_uthmani.split():
            if not has_letters(token):
                if token != "۞":
                    fail(f"verse {row['sora']}:{row['aya_no']}: unexpected token {token!r}")
                continue  # the rub' sign is a marker, not a word
            uthmani_words.append(token)
        imlaei_words = row["aya_text_emlaey"].split()
        pairs, cost = align_words(uthmani_words, imlaei_words)
        alignment_costs[(row["sora"], row["aya_no"])] = cost
        if " ".join(part for part in pairs if part) != " ".join(imlaei_words):
            fail(f"verse {row['sora']}:{row['aya_no']}: alignment lost modern-spelling words")

        word_rows = []
        for position, (uthmani, imlaei) in enumerate(zip(uthmani_words, pairs), 1):
            word_rows.append(
                {
                    "verse_id": verse_id,
                    "position": position,
                    "text_uthmani": uthmani,
                    "text_imlaei": imlaei,
                    "search_uthmani": normalize_for_search(uthmani),
                    "search_imlaei": normalize_for_search(imlaei),
                }
            )
        words.extend(word_rows)
        verses.append(
            {
                "id": verse_id,
                "chapter": row["sora"],
                "number": row["aya_no"],
                "page": row["page"],
                "last_page": row["page"],
                "line_start": row["line_start"],
                "line_end": row["line_end"],
                "juz": row["jozz"],
                "rub": rub_index + 1,
                "has_sajdah": int(SAJDAH_SIGN in text_uthmani),
                "word_count": len(uthmani_words),
                "text_uthmani": text_uthmani,
                "text_imlaei": " ".join(imlaei_words),
                "search_uthmani": " ".join(w["search_uthmani"] for w in word_rows),
                "search_imlaei": normalize_for_search(" ".join(imlaei_words)),
            }
        )
    return verses, words, rub_first_verse, alignment_costs


def import_text_sources(connection, verse_id_of):
    """Import the QUL tafsir and translation databases."""
    connection.executemany(
        "INSERT INTO text_sources (key, title, kind, language, sort_order) VALUES (?,?,?,?,?)",
        [(key, title, kind, language, order) for key, title, kind, language, order, _ in TEXT_SOURCES],
    )
    source_ids = dict(connection.execute("SELECT key, id FROM text_sources"))

    with tempfile.TemporaryDirectory() as folder:
        for key, title, kind, _, _, stem in TEXT_SOURCES:
            archive = SOURCES / "qul" / f"{stem}.db.zip"
            if not archive.exists():
                fail(f"missing {archive}")
            with zipfile.ZipFile(archive) as bundle:
                bundle.extract(f"{stem}.db", folder)
            source = sqlite3.connect(f"file:{Path(folder) / (stem + '.db')}?mode=ro", uri=True)
            source_id = source_ids[key]
            covered = set()

            def to_id(ayah_key):
                chapter, number = ayah_key.split(":")
                return verse_id_of[(int(chapter), int(number))]

            if kind == "translation":
                for ayah_key, text in source.execute("SELECT ayah_key, text FROM translation"):
                    verse_id = to_id(ayah_key)
                    group_id = connection.execute(
                        "INSERT INTO text_groups (source_id, first_verse_id, last_verse_id, body)"
                        " VALUES (?,?,?,?)",
                        (source_id, verse_id, verse_id, text),
                    ).lastrowid
                    connection.execute(
                        "INSERT INTO text_group_of_verse VALUES (?,?,?)",
                        (source_id, verse_id, group_id),
                    )
                    covered.add(verse_id)
            else:
                rows = source.execute(
                    "SELECT ayah_key, group_ayah_key, from_ayah, to_ayah, text FROM tafsir"
                ).fetchall()
                head_group = {}
                for ayah_key, group_key, first_key, last_key, text in rows:
                    if ayah_key != group_key:
                        continue
                    if not text or not text.strip():
                        fail(f"{key}: the first verse of group {group_key} has no text")
                    first, last = to_id(first_key or ayah_key), to_id(last_key or ayah_key)
                    head_group[group_key] = (
                        connection.execute(
                            "INSERT INTO text_groups (source_id, first_verse_id, last_verse_id, body)"
                            " VALUES (?,?,?,?)",
                            (source_id, first, last, text),
                        ).lastrowid,
                        first,
                        last,
                    )
                for ayah_key, group_key, *_ in rows:
                    group_id, first, last = head_group[group_key]
                    verse_id = to_id(ayah_key)
                    if not first <= verse_id <= last:
                        fail(f"{key}: verse {ayah_key} lies outside its group {group_key}")
                    connection.execute(
                        "INSERT INTO text_group_of_verse VALUES (?,?,?)",
                        (source_id, verse_id, group_id),
                    )
                    covered.add(verse_id)
            check_equal(f"{key}: verses covered", len(covered), EXPECTED["verses"])
            source.close()


def unzip_database(archive_name, folder):
    archive = SOURCES / "qul" / archive_name
    if not archive.exists():
        fail(f"missing {archive}")
    with zipfile.ZipFile(archive) as bundle:
        member = bundle.namelist()[0]
        bundle.extract(member, folder)
    return sqlite3.connect(f"file:{Path(folder) / member}?mode=ro", uri=True)


def import_page_layout(connection):
    """Add the glyphs and lines of every page, and set each verse's real page.

    Pages, lines and the start page of every chapter, juz' and rub' follow the
    layout (the 1441H print), not the page numbers of the text source.
    """
    words_per_verse = {
        (chapter, number): (verse_id, count)
        for verse_id, chapter, number, count in connection.execute(
            "SELECT id, chapter, number, word_count FROM verses"
        )
    }
    with tempfile.TemporaryDirectory() as folder:
        glyph_db = unzip_database("qpc-v4.db.zip", folder)
        layout_db = unzip_database("qpc-v4-tajweed-15-lines.db.zip", folder)
        rows = glyph_db.execute(
            "SELECT id, surah, ayah, word, text FROM words ORDER BY id"
        ).fetchall()
        lines = layout_db.execute(
            "SELECT page_number, line_number, line_type, is_centered, first_word_id,"
            " last_word_id, surah_number FROM pages ORDER BY page_number, line_number"
        ).fetchall()

    # What each glyph stands for
    glyph_info = {}
    by_verse = {}
    for glyph_id, chapter, number, position, text in rows:
        by_verse.setdefault((chapter, number), []).append((glyph_id, position, text))
    check_equal("verses in the layout words", len(by_verse), EXPECTED["verses"])
    for (chapter, number), entries in by_verse.items():
        verse_id, word_count = words_per_verse[(chapter, number)]
        entries.sort(key=lambda entry: entry[1])
        if [entry[1] for entry in entries] != list(range(1, len(entries) + 1)):
            fail(f"layout words of {chapter}:{number} are not numbered 1..n")
        try:
            spans = word_spans(chapter, number, len(entries) - 1, word_count)
        except ValueError as problem:
            fail(str(problem))
        for (glyph_id, _, text), span in zip(entries, spans):
            glyph_info[glyph_id] = (verse_id, span[0], span[1], text)
        glyph_id, _, text = entries[-1]  # the verse-end marker
        glyph_info[glyph_id] = (verse_id, None, None, text)
    check_equal("glyphs", len(glyph_info), EXPECTED["glyphs"])

    # Where each glyph is drawn
    placed = {}
    for page, line, kind, centered, first_id, last_id, chapter in lines:
        kind = {"surah_name": "chapter_name", "basmallah": "basmala", "ayah": "text"}[kind]
        connection.execute(
            "INSERT INTO page_lines VALUES (?,?,?,?,?)",
            (page, line, kind, int(centered or 0), chapter or None),
        )
        if kind == "text":
            for slot, glyph_id in enumerate(range(int(first_id), int(last_id) + 1), 1):
                if glyph_id in placed:
                    fail(f"glyph {glyph_id} is placed twice")
                placed[glyph_id] = (page, line, slot)
    if set(placed) != set(glyph_info):
        fail("the layout and the layout words do not describe the same glyphs")
    connection.executemany(
        "INSERT INTO glyphs VALUES (?,?,?,?,?,?,?,?)",
        [(gid, *placed[gid], *glyph_info[gid]) for gid in sorted(glyph_info)],
    )

    # Pages and lines of the verses, from where their glyphs are drawn
    connection.execute(
        """UPDATE verses SET
             page = (SELECT MIN(page) FROM glyphs WHERE verse_id = verses.id),
             last_page = (SELECT MAX(page) FROM glyphs WHERE verse_id = verses.id)"""
    )
    connection.execute(
        """UPDATE verses SET
             line_start = (SELECT MIN(line) FROM glyphs WHERE verse_id = verses.id
                           AND page = verses.page),
             line_end = (SELECT MAX(line) FROM glyphs WHERE verse_id = verses.id
                         AND page = verses.last_page)"""
    )
    for table in ("chapters", "juz", "rubs"):
        connection.execute(
            f"UPDATE {table} SET start_page = "
            "(SELECT page FROM verses WHERE id = first_verse_id)"
        )


def build(output):
    meta = json.loads((SOURCES / "quran_meta.json").read_text(encoding="utf-8"))
    rows = load_verses()
    verses, words, rub_first_verse, alignment_costs = prepare_verses(rows, meta)
    verse_id_of = {(v["chapter"], v["number"]): v["id"] for v in verses}
    page_of = {v["id"]: v["page"] for v in verses}

    if output.exists():
        output.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(output)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)

    # Chapters
    chapter_names = {row["sora"]: row["sora_name_ar"] for row in rows}
    for chapter, name in sorted(chapter_names.items()):
        own = [v for v in verses if v["chapter"] == chapter]
        connection.execute(
            "INSERT INTO chapters VALUES (?,?,?,?,?,?)",
            (chapter, name, meta["revelation"][str(chapter)], len(own), own[0]["id"], own[0]["page"]),
        )

    # Juz': the first verse of each juz' in the print
    first_of_juz = {}
    for verse in verses:
        first_of_juz.setdefault(verse["juz"], verse)
    for juz_id, verse in sorted(first_of_juz.items()):
        connection.execute("INSERT INTO juz VALUES (?,?,?)", (juz_id, verse["id"], verse["page"]))

    # Rub' (quarters of a hizb)
    for rub_id, first_verse in enumerate(rub_first_verse, 1):
        connection.execute(
            "INSERT INTO rubs VALUES (?,?,?,?,?)",
            (rub_id, (rub_id - 1) // 4 + 1, (rub_id - 1) % 4 + 1, first_verse, page_of[first_verse]),
        )

    column_names = [
        "id", "chapter", "number", "page", "last_page", "line_start", "line_end", "juz", "rub",
        "has_sajdah", "word_count", "text_uthmani", "text_imlaei",
        "search_uthmani", "search_imlaei",
    ]
    connection.executemany(
        f"INSERT INTO verses ({','.join(column_names)}) VALUES ({','.join('?' * len(column_names))})",
        [tuple(v[name] for name in column_names) for v in verses],
    )
    word_columns = ["verse_id", "position", "text_uthmani", "text_imlaei",
                    "search_uthmani", "search_imlaei"]
    connection.executemany(
        f"INSERT INTO words ({','.join(word_columns)}) VALUES ({','.join('?' * len(word_columns))})",
        [tuple(w[name] for name in word_columns) for w in words],
    )

    import_text_sources(connection, verse_id_of)
    import_page_layout(connection)
    connection.commit()

    # Final checks on what was written
    def count(table):
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    check_equal("chapters", count("chapters"), EXPECTED["chapters"])
    check_equal("verses", count("verses"), EXPECTED["verses"])
    check_equal("juz'", count("juz"), EXPECTED["juz"])
    check_equal("rub'", count("rubs"), EXPECTED["rubs"])
    check_equal("words", count("words"), EXPECTED["words"])
    check_equal(
        "pages",
        connection.execute("SELECT COUNT(DISTINCT page) FROM verses").fetchone()[0],
        EXPECTED["pages"],
    )
    check_equal(
        "verses in chapter table",
        connection.execute("SELECT SUM(verse_count) FROM chapters").fetchone()[0],
        EXPECTED["verses"],
    )
    connection.close()

    costs = Counter(alignment_costs.values())
    worst = sorted(alignment_costs.items(), key=lambda item: -item[1])[:5]
    print(f"Wrote {output} ({output.stat().st_size / 1_000_000:.1f} MB)")
    print(f"  {EXPECTED['chapters']} chapters, {EXPECTED['verses']} verses, {EXPECTED['words']} words, "
          f"{EXPECTED['pages']} pages, {EXPECTED['juz']} juz', {EXPECTED['rubs']} rub'")
    print(f"  word alignment cost per verse (letters that differ): {dict(sorted(costs.items()))}")
    print(f"  least certain verses: {worst}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", type=Path, default=DATABASE_PATH)
    output = parser.parse_args().output
    output.parent.mkdir(parents=True, exist_ok=True)
    build(output)
    if output == DATABASE_PATH:
        write_stamp()  # so the reader knows it is up to date


if __name__ == "__main__":
    main()
