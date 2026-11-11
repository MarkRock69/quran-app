"""Saved audio presets: a passage, a reciter and style, a speed and repetition counts, under a name.

Stored in one JSON file (paths.AUDIO_PRESETS). Every setting is optional: a preset only holds the ones its
author chose to include, and applying it changes only those. Pure logic, no Qt.

    {"version": 1, "presets": [
        {"name": "...", "from": [2, 255], "to": [2, 260], "reciter": "minshawi", "style": "murattal",
         "speed": 1.25, "verse_repeats": 3, "passage_repeats": 2}
    ]}
"""

import json
import os
from pathlib import Path

from .audio_catalog import RECITERS, SPEED_MAX, SPEED_MIN, STYLE_NAMES, range_text, speed_text

MAX_REPEATS = 99
SETTINGS = ("from", "to", "reciter", "style", "speed", "verse_repeats", "passage_repeats")


def _verse(value, verse_count):
    """[chapter, verse] if it names a real verse, else None."""
    try:
        chapter, verse = value
        if isinstance(chapter, bool) or isinstance(verse, bool):
            return None
        chapter, verse = int(chapter), int(verse)
        if 1 <= chapter <= 114 and 1 <= verse <= verse_count(chapter):
            return [chapter, verse]
    except (TypeError, ValueError):
        pass
    return None


def clean(raw, verse_count):
    """A valid preset from whatever was in the file: unusable settings are dropped. None if it has no name."""
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    preset = {"name": name.strip()}
    for key in ("from", "to"):
        if key in raw and (value := _verse(raw[key], verse_count)):
            preset[key] = value
    if raw.get("reciter") in {item.key for item in RECITERS}:
        preset["reciter"] = raw["reciter"]
    if raw.get("style") in STYLE_NAMES:
        preset["style"] = raw["style"]
    speed = raw.get("speed")
    if isinstance(speed, (int, float)) and not isinstance(speed, bool) and SPEED_MIN <= speed <= SPEED_MAX:
        preset["speed"] = round(float(speed), 2)
    for key in ("verse_repeats", "passage_repeats"):
        count = raw.get(key)
        if isinstance(count, int) and not isinstance(count, bool) and 1 <= count <= MAX_REPEATS:
            preset[key] = count
    return preset


def load(path, verse_count):
    """The saved presets (a list of dicts). A missing file is an empty list; a file that cannot be read is set
    aside as `<name>.bad` so that saving afterwards does not destroy it."""
    path = Path(path)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data["presets"]
        if not isinstance(raw, list):
            raise ValueError("presets is not a list")
    except (OSError, ValueError, KeyError, TypeError):
        try:
            path.replace(path.with_name(path.name + ".bad"))
        except OSError:
            pass
        return []
    seen, presets = set(), []
    for item in raw:
        preset = clean(item, verse_count)
        if preset and preset["name"] not in seen:
            seen.add(preset["name"])
            presets.append(preset)
    return presets


def save(path, presets):
    """Write the presets, all at once (a half-written file is never left behind)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({"version": 1, "presets": presets}, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    os.replace(temporary, path)


def upsert(presets, preset):
    """A new list with `preset` added, or replacing the one of the same name (keeping its place)."""
    result = list(presets)
    for index, existing in enumerate(result):
        if existing["name"] == preset["name"]:
            result[index] = preset
            return result
    return result + [preset]


def remove(presets, name):
    return [preset for preset in presets if preset["name"] != name]


def find(presets, name):
    return next((preset for preset in presets if preset["name"] == name), None)


def summary(preset, chapter_name, digits="indic"):
    """One line saying what a preset holds, for a tooltip."""
    from .numbers import format_number
    n = lambda value: format_number(value, digits)  # noqa: E731
    parts = []
    first, last = preset.get("from"), preset.get("to")
    if first and last:
        parts.append(range_text(tuple(first), tuple(last), chapter_name, digits))
    elif first:
        parts.append(f"من {chapter_name(first[0])} {n(first[1])}")
    elif last:
        parts.append(f"إلى {chapter_name(last[0])} {n(last[1])}")
    names = {item.key: item.name_ar for item in RECITERS}
    if "reciter" in preset:
        parts.append(names[preset["reciter"]])
    if "style" in preset:
        parts.append(STYLE_NAMES[preset["style"]])
    if "speed" in preset:
        parts.append(f"السرعة {speed_text(preset['speed'])}")
    if "verse_repeats" in preset:
        parts.append(f"تكرار الآية {n(preset['verse_repeats'])}")
    if "passage_repeats" in preset:
        parts.append(f"تكرار المقطع {n(preset['passage_repeats'])}")
    return " · ".join(parts) or "بلا إعدادات"
