#!/usr/bin/env python3
"""Build the app's SQLite database from the files in data/sources.

    python3 tools/build_database.py [--output build/quran.db]

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
from quran_app.word_alignment import align_words  # noqa: E402

SOURCES = ROOT / "data" / "sources"

EXPECTED = {
    "surahs": 114,
    "verses": 6236,
    "pages": 604,
    "juz": 30,
    "rubs": 240,
    "words": 77430,
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
CREATE TABLE surahs (
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
    surah           INTEGER NOT NULL REFERENCES surahs(id),
    number          INTEGER NOT NULL,
    page            INTEGER NOT NULL,
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
    UNIQUE (surah, number)
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

TRAILING_NUMBER = re.compile(r" [٠-٩]+$")
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
                "surah": row["sora"],
                "number": row["aya_no"],
                "page": row["page"],
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
                surah, number = ayah_key.split(":")
                return verse_id_of[(int(surah), int(number))]

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


def build(output):
    meta = json.loads((SOURCES / "quran_meta.json").read_text(encoding="utf-8"))
    rows = load_verses()
    verses, words, rub_first_verse, alignment_costs = prepare_verses(rows, meta)
    verse_id_of = {(v["surah"], v["number"]): v["id"] for v in verses}
    page_of = {v["id"]: v["page"] for v in verses}

    if output.exists():
        output.unlink()
    output.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(output)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)

    # Surahs
    surah_names = {row["sora"]: row["sora_name_ar"] for row in rows}
    for surah, name in sorted(surah_names.items()):
        own = [v for v in verses if v["surah"] == surah]
        connection.execute(
            "INSERT INTO surahs VALUES (?,?,?,?,?,?)",
            (surah, name, meta["revelation"][str(surah)], len(own), own[0]["id"], own[0]["page"]),
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
        "id", "surah", "number", "page", "line_start", "line_end", "juz", "rub",
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
    connection.commit()

    # Final checks on what was written
    def count(table):
        return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    check_equal("surahs", count("surahs"), EXPECTED["surahs"])
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
        "verses in surah table",
        connection.execute("SELECT SUM(verse_count) FROM surahs").fetchone()[0],
        EXPECTED["verses"],
    )
    connection.close()

    costs = Counter(alignment_costs.values())
    worst = sorted(alignment_costs.items(), key=lambda item: -item[1])[:5]
    print(f"Wrote {output} ({output.stat().st_size / 1_000_000:.1f} MB)")
    print(f"  {EXPECTED['surahs']} surahs, {EXPECTED['verses']} verses, {EXPECTED['words']} words, "
          f"{EXPECTED['pages']} pages, {EXPECTED['juz']} juz', {EXPECTED['rubs']} rub'")
    print(f"  word alignment cost per verse (letters that differ): {dict(sorted(costs.items()))}")
    print(f"  least certain verses: {worst}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "quran.db")
    build(parser.parse_args().output)


if __name__ == "__main__":
    main()
