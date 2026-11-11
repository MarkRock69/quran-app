# quran-app

A personal Qur'an reading app. Arabic-only interface, Madani Mushaf pages, search
that ignores diacritics, tafsir side panel, audio. Not for publication.

Stack: Python + Qt (PySide6) with SQLite. Code uses the word
**verse** (never "ayah"), and `verses` for the plural.

## Which systems it runs on

**Tested:** Ubuntu 24.04 on Xorg, and nothing else. That is the only place the app has ever been run.

**Hypothetically:** any desktop operating system that PySide6 (Qt 6) supports (other Linux distributions,
Ubuntu on Wayland, Windows 10/11, macOS), because the app is plain Python, SQLite and files, and all drawing,
fonts, text direction and audio go through Qt. Nobody has tried it there, so treat it as unproven. What may go
wrong or differ:

- **Python and PySide6.** `pip install PySide6` needs a Python version PySide6 supports (roughly 3.9 to 3.13)
  and a platform it publishes wheels for. Newer Debian and Ubuntu releases refuse system-wide `pip install`
  and want a virtual environment (`python3 -m venv`). Very old distributions may have a C library that is too
  old for the wheels.
- **The menu entry.** `tools/install_launcher.py` writes a freedesktop `.desktop` file, which only exists on
  Linux. Windows and macOS need their own shortcut or app bundle, and the dock or taskbar icon is arranged
  differently there.
- **Window name and icon.** The app names its window `quran-app` so the Ubuntu dock matches it to the menu
  entry. That was fixed and checked on Xorg only. On Wayland it relies on `setDesktopFileName`, which should do
  the same job but has not been seen working. Other desktops (KDE, XFCE, Windows, macOS) may show a generic icon.
- **Where the data goes.** Everything lives in `~/.local/share/quran-app/` (set `QURAN_APP_DATA` to change it)
  on every system, which is not where Windows or macOS programs usually keep data. It works, but expect the
  folder in an unusual place.
- **Audio.** Playback uses Qt Multimedia. Which codecs and backend it uses differs by system, so mp3 playback,
  seeking and how well the playback speed keeps the voice's pitch may differ. Only Ubuntu's behaviour has been heard.
- **Fonts and text.** The Mushaf pages use the King Fahd per-page fonts loaded from files, which should look the
  same everywhere. The side panel, buttons and tables use your system's fonts and Qt theme, so spacing and the
  dark/light look follow the theme. The layout was only seen in a dark Qt theme with right-to-left layout on Ubuntu.
- **Right-to-left details.** A few right-to-left fixes (the keys in the shortcuts table, the order of the playback
  icons, the position of the header text) were made by watching how Qt behaved on Ubuntu. Other platforms or
  Qt versions might order things differently.
- **Keyboard shortcuts.** They are written with Ctrl. On macOS Qt maps Ctrl to the Command key, so the physical
  key differs. Ctrl+/ and Ctrl+K may depend on the keyboard layout.
- **Downloading and building.** The download scripts and the database build are plain Python and should behave
  the same anywhere, but the first database build takes around 30 seconds and the audio is about 16 GB. Paths with
  spaces or non-Latin characters in them have not been tried.

If you try another system, the first run is the test. Report what breaks and it can be fixed.

## Build order

1. **Data** (done): text, search copy, chapter/juz'/rub'/page tables, tafsir
2. **Search engine** (done): `quran_app/search.py`
3. **Mushaf page view** (page model done and tested; the Qt window is written but not yet run, see below)
4. Navigation: jump box, search panel, bookmarks, chapter list and rub' list (written, first run pending)
5. Tafsir side panel with the six sources in a column (written, first run pending; The Clear Qur'an is reserved, no download exists)
6. Audio with a selectable passage (done: downloader, passage selector, player; first run pending)
7. Themes (light, dark) and the Arabic-Indic / Western digit toggle

## Build the database

Needs only Python 3.12 (already on Ubuntu 24.04), no installs.

    python3 tools/build_database.py        # writes ~/.local/share/quran-app/quran.db, about 30 seconds
    python3 -m unittest discover -s tests  # about 95 checks, about 40 seconds

The build stops with an error if any count or check fails. The reader does this by itself on its first run and again only when the sources or the build code change.

## What is in the database

| Table | Contents |
|---|---|
| `chapters` | name, Meccan/Medinan, verse count, first verse, start page |
| `juz` | first verse and start page of each of the 30 juz' |
| `rubs` | 240 quarters of a hizb: hizb number, position in the hizb (1 to 4), first verse, start page |
| `verses` | 6236 verses: page, lines, juz', rub', full Uthmani text, modern-spelling text, and a search copy of each |
| `words` | 77,430 Uthmani words, each with its modern spelling and search forms |
| `glyphs` | 83,668 page glyphs: one per word (with its stop sign) plus a verse-end marker per verse, each with its page, line and position, and the words of the verse it stands for |
| `page_lines` | the 15 lines of each of the 604 pages (8 for pages 1 and 2): chapter name, basmala or text, centered or justified |
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
| `qul/qpc-v4.db.zip`, `qul/qpc-v4-tajweed-15-lines.db.zip` | QUL, KFGQPC V4 (1441H print) | the glyph of every word, and which words are on which line of which page |

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

The page layout (1441H print) agrees with the text source on the page of every
verse, so no chapter, juz' or rub' start page changed. No verse crosses a page.
Four verses are written with one word more or fewer than our text
(15:7, 27:20, 36:22, 37:130); `quran_app/page_layout.py` lines them up.

## The Mushaf window

    python3 tools/fetch_fonts.py                      # once: the 604 page fonts, about 200 MB
    pip install PySide6                               # once
    python3 -m quran_app.reader --page 42 --spread    # two pages; leave out --spread for one

Left, PageDown or scrolling down = next page; Right, PageUp or scrolling up =
previous page; Ctrl+2 = one or two pages. In two-page mode the book is read right
to left like the printed Mushaf: 1 on the right and 2 on the left, then 3|4, and
so on. Ctrl+D = cycle numbers: Arabic-Indic digits, Western digits, ordinal
words (الأول). Each page has a heading: juz' (and, when a rub' starts on the page,
how much of the hizb is done, e.g. `الجزء ١، ثلاثة أرباع الحزب ١`) on the right,
chapter name and number on the left. Chapter banners, the calligraphic chapter
names and the basmala are glyphs of the King Fahd font QCF2BSML.ttf (rerun
`tools/fetch_fonts.py` once to get it; it skips what you already have). The ☰ button in the top corner opens the side panel, which has everything below
as tabs (search, go to, bookmarks, view: one or two pages and the number style),
so the keyboard is never required. Ctrl+K = go to a page, chapter, juz', hizb or rub' by number, or a verse as `2:255`
(either digit style). The display tab (or Ctrl+G) switches the pages between light and dark; the side panel follows your Qt theme. The الاختصارات tab (Ctrl+/) lists every keyboard shortcut. The tafsir sources and the side panel's tabs can be dragged into any order; the orders, the page colours, one or two pages (`--spread` / `--no-spread` override it), the number style (with separate choices for the chapter, juz'/hizb and page numbers) are remembered (the playback speed is not: it starts at 1) in `~/.local/share/quran-app/user.db`. The الصوت tab (Ctrl+U) plays any passage: pick the reciter (and style, where there is more than one), then the passage with the from/to chapter and verse dropdowns, how many times to repeat each verse and the whole passage, or use the buttons for the selected verse, from it to the end of the chapter, the current page, chapter or juz'. While something plays, a bar at the bottom shows the range being played, what is playing now, the playback speed (an editable dropdown, 0.25 to 3) and the repetition counts, which can be changed on the fly (the playback carries on without a break); it also has icons for next verse (left arrow), pause/play (Space), stop and previous verse (right arrow); the page follows the recitation. Click a verse on the page and its tafsir shows in the التفسير tab (Ctrl+T), with the six
sources as a column beside the text; a text that covers several verses says so. Ctrl+I opens the chapter list (juz' bands, page, Meccan or Medinan, verse count)
and the rub' list (circle showing how much of the hizb has passed, opening words,
chapter and verse, page), laid out like the Quran Android app; choosing a row goes
to its page. Ctrl+F opens the side panel with search as you type: choose a
result to open its page with the verse selected; Esc closes the panel. Ctrl+B
bookmarks the page (a red ribbon shows; the list is the panel's second tab, Delete
removes one); bookmarks are kept in `~/.local/share/quran-app/user.db`.
Ctrl+C = copy the selection (real Uthmani text, with verse numbers in
ornate brackets). The page fonts are drawn with the glyph codes in `glyphs`
(QCF V2 fonts, plain, no tajweed colours). Stretching of word gaps to fill each
line is done by the window, because these fonts leave it to the app.
`quran_app/mushaf.py` holds everything that does not need Qt and is tested; the
Qt window `quran_app/reader.py` was written without being able to run Qt, so
expect to fix small things on the first run.

The Clear Qur'an translation is not included (no
download available); its tab is reserved in the tab order.

The King Fahd data, QUL data and fonts have their own terms. This repository is
for personal use; do not make it public with these files in it.

## Audio

    python3 tools/fetch_audio.py                     # one time, about 16 GB: all of it
    python3 tools/fetch_audio.py --only minshawi     # or one reciter, or reciter:style

Recitations come from everyayah.com, one mp3 per verse (and one per chapter for its
basmala, `SSS000.mp3`), as one zip for each reciter and style: al-Minshawi (murattal,
mujawwad), Ali Jaber (murattal only; the site has no mujawwad for him) and Abdulbasit
(murattal, mujawwad). They are unpacked into `~/.local/share/quran-app/audio/<reciter>/<style>/`, checked
against the site's md5 list, and the zip is deleted. If it stops, run it again.
`quran_app/audio_catalog.py` knows the file names and builds a playlist for any list of
verses (basmala before the first verse of a chapter, except chapters 1 and 9).

### Saved audio presets

The الصوت tab has a "المقاطع المحفوظة" row: pick a name and press "تطبيق" to load it, "جديد…" to make one,
"حذف" to delete one. "جديد…" opens a window with a name and a tick box for each setting: the first verse, the
last verse, the reciter, the style, the speed and the two repetition counts. Only ticked settings are saved,
and loading a preset changes only those, so everything else stays as it was. (Loading fills in the settings;
press "تشغيل" to play. A reciter or style that is not downloaded is skipped, and the status line says so.)
They are kept in one file, `~/.local/share/quran-app/audio_presets.json`, next to the other data. It is plain
JSON and can be edited by hand; a setting that is invalid is ignored, and a file that cannot be read is set
aside as `audio_presets.json.bad`:

    {"version": 1, "presets": [
      {"name": "الإخلاص ×٣", "from": [112, 1], "to": [112, 4], "reciter": "minshawi",
       "style": "murattal", "speed": 0.75, "verse_repeats": 3, "passage_repeats": 2}
    ]}

## Where the files live

Everything big or personal is kept in one folder outside the project,
`~/.local/share/quran-app/` (or the folder in the `QURAN_APP_DATA` environment variable):
`fonts/`, `audio/`, `quran.db` (built from `data/sources`) and `user.db` (bookmarks and settings).
A new copy of the project finds all of it, so the fonts and audio are downloaded once and
nothing needs copying between releases. To move an old setup over:

    mkdir -p ~/.local/share/quran-app
    mv OLD_PROJECT/data/fonts ~/.local/share/quran-app/fonts
    mv OLD_PROJECT/data/audio ~/.local/share/quran-app/audio   # if you had started it

## Applications menu

    python3 tools/install_launcher.py             # adds "Quran" to the applications menu
    python3 tools/install_launcher.py --remove    # takes it out

The entry starts the copy of the project it was installed from, so run it again from the new folder
when you move to a new release. Then search "Quran" in the Activities overview; you can
right-click the result and add it to the favourites (the dock).
