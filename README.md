# quran-app

A personal Qur'an reading app for one laptop (Ubuntu 24.04, Xorg). Arabic-only
interface, Madani Mushaf pages, search that ignores diacritics, tafsir side
panel, audio. Not for publication.

Planned stack: Python + Qt (PySide6, Qt Quick) with SQLite. Code uses the word
**verse** (never "ayah"), and `verses` for the plural.

## Build order

1. **Data** (done): text, search copy, chapter/juz'/rub'/page tables, tafsir
2. **Search engine** (done): `quran_app/search.py`
3. Mushaf page view (per-page fonts, selectable text)
4. Navigation: lists, jump box, bookmarks, shortcuts
5. Tafsir side panel with vertical tabs
6. Audio, with a selectable passage
7. Themes (light, dark) and the Arabic-Indic / Western digit toggle

## Build the database

Needs only Python 3.12 (already on Ubuntu 24.04), no installs.

    python3 tools/build_database.py        # writes build/quran.db, about 30 seconds
    python3 -m unittest discover -s tests  # 63 checks, about 30 seconds

The build stops with an error if any count or check fails. `build/` is not
committed; it is rebuilt from `data/sources`.

## What is in the database

| Table | Contents |
|---|---|
| `chapters` | name, Meccan/Medinan, verse count, first verse, start page |
| `juz` | first verse and start page of each of the 30 juz' |
| `rubs` | 240 quarters of a hizb: hizb number, position in the hizb (1 to 4), first verse, start page |
| `verses` | 6236 verses: page, lines, juz', rub', full Uthmani text, modern-spelling text, and a search copy of each |
| `words` | 77,430 Uthmani words, each with its modern spelling and search forms |
| `text_sources`, `text_groups`, `text_group_of_verse` | the five tafsir and translation sources; a tafsir covering several verses is stored once |

Search forms remove every diacritic and Qur'anic sign, unify أ إ آ ٱ → ا,
ى → ي, ة → ه, ؤ → و, ئ → ي, and drop ء. See `quran_app/arabic_text.py`.

## How search works

`SearchIndex` (in `quran_app/search.py`) keeps the whole text in memory
(loads in about 1 second) and answers a query in well under 100 ms, so it can
run on every keystroke.

- **Exact phrase, anywhere in the text, is the default.** `قيو` finds it inside
  القيوم. A space at the start or end of the query anchors that end to a word
  boundary, so ` الله ` finds only the whole word.
- **Diacritics are ignored unless typed.** `ولئن` and `وَلَئِن` both work. Marks
  you do type must be present at the same letters; marks you leave out are
  ignored. The `strict_marks` option demands exactly the typed marks.
  Your keyboard's sukun, tanween and the Uthmani script's own signs for them
  are treated as the same mark.
- **Spelling:** modern spelling finds the Uthmani one (الصلاة finds
  ٱلصَّلَوٰةَ); أ إ آ ٱ ا, ى ي, ة ه are interchangeable. Hamza works one way:
  typing `ئ` requires a hamza in the text, typing `ي` matches either.
- **A phrase never spans two verses.** Hits come in Mushaf order.
- **Modes:** the exact phrase (default), all the words in any order, or any
  one of the words.
- **Results:** `render(hit, before=3, after=3)` returns the Uthmani text of the
  match with the matched characters flagged, plus the chosen number of words on
  each side, cut off at the edges of the verse.

## Where the data comes from

| File in `data/sources` | Source | Used for |
|---|---|---|
| `kfgqpc/hafsData_v18.json` | King Fahd Glorious Qur'an Printing Complex, via [ibnhazm/KFGQPC](https://github.com/ibnhazm/KFGQPC) | Uthmani text, modern-spelling text, page, line, juz' |
| `quran_meta.json` | rub' start verses and place of revelation, taken from [malekverse/quran-dataset](https://github.com/malekverse/quran-dataset) | rub' and Meccan/Medinan |
| `qul/*.zip` | [QUL](https://qul.tarteel.ai) (Tarteel) | Al-Mukhtasar, Al-Muyassar, Al-Tahrir wa al-Tanwir, I'rab al-Qur'an (Darwish), Sahih International |

Cross-checks done while building:

- The 240 rub' start verses agree with the rub' sign (۞) printed in the King
  Fahd text: all 199 signs sit on a rub' start, and the other 41 starts are
  verse 1 of a chapter, which carries no sign.
- Juz' boundaries come from the print, not from the rub' list. In the print,
  juz' 4 starts at 3:92 and juz' 11 at 9:94, at the top of pages 62 and 202.
  The rub' sign sits one verse earlier or later in those two places (3:93,
  9:93), so a rub' can start in a different juz' than the one its verse is in.
- Chapter, juz' and rub' start pages match the Quran Android screenshots
  (tests/test_database.py).

The per-page Mushaf fonts (King Fahd Complex) are not in this repository yet;
they are added in step 3. The Clear Qur'an translation is not included (no
download available); its tab is reserved in the tab order.

The King Fahd data, QUL data and fonts have their own terms. This repository is
for personal use; do not make it public with these files in it.
