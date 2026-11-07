#!/usr/bin/env python3
"""Download the recitations into ~/.local/share/quran-app/audio (one time). Needs the internet; nothing else.

    python3 tools/fetch_audio.py                       # everything (about 11 GB)
    python3 tools/fetch_audio.py --only minshawi       # one reciter
    python3 tools/fetch_audio.py --only minshawi:murattal abdulbasit:mujawwad

Each reciter and style is one zip from everyayah.com (resumable: run it again if it stops).
The zip is unpacked into <that folder>/<reciter>/<style>/ as SSSVVV.mp3, checked against the
site's md5 list, and deleted. Anything already complete is skipped.
"""

import argparse
import hashlib
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from quran_app.audio_catalog import (  # noqa: E402
    BASE_URL, CHECKSUM_NAME, RECITERS, ZIP_NAME, flat_name, folder, parse_md5,
)
from quran_app.paths import AUDIO_DIR  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DESTINATION = AUDIO_DIR
EXPECTED_VERSES = 6236
CHUNK = 1 << 20


def download(url, target):
    """Download `url` to `target`, resuming a partial file."""
    partial = target.with_suffix(target.suffix + ".part")
    done = partial.stat().st_size if partial.exists() else 0
    request = urllib.request.Request(url, headers={"Range": f"bytes={done}-"} if done else {})
    with urllib.request.urlopen(request, timeout=60) as response:
        if done and response.status != 206:  # the server ignored the range: start again
            done = 0
        total = done + int(response.headers.get("Content-Length", 0))
        mode = "ab" if done else "wb"
        with open(partial, mode) as out:
            last = -1
            while True:
                block = response.read(CHUNK)
                if not block:
                    break
                out.write(block)
                done += len(block)
                percent = int(done * 100 / total) if total else 0
                if percent != last and percent % 5 == 0:
                    print(f"    {percent}%  ({done / 1e6:.0f} of {total / 1e6:.0f} MB)", flush=True)
                    last = percent
    partial.rename(target)


def fetch_text(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8", "replace")


def md5_of(path):
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def have_all(target):
    return target.exists() and len(list(target.glob("[0-9][0-9][0-9][0-9][0-9][0-9].mp3"))) >= EXPECTED_VERSES


def fetch_one(reciter, style, recording):
    target = folder(DESTINATION, reciter.key, style)
    label = f"{reciter.key}/{style}"
    if have_all(target):
        print(f"{label}: already there")
        return True
    target.mkdir(parents=True, exist_ok=True)
    archive = target / ZIP_NAME
    url = f"{BASE_URL}/{recording.folder}/{ZIP_NAME}"
    print(f"{label}: downloading about {recording.size_gb:g} GB from {url}")
    download(url, archive)
    print(f"{label}: unpacking")
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            name = flat_name(member.filename)
            if name:
                with bundle.open(member) as source, open(target / name, "wb") as out:
                    shutil.copyfileobj(source, out)
    archive.unlink()
    problems = 0
    try:
        sums = parse_md5(fetch_text(f"{BASE_URL}/{recording.folder}/{CHECKSUM_NAME}"))
    except OSError as error:
        sums = {}
        print(f"{label}: could not get the md5 list ({error}); skipping the check")
    for name, expected in sums.items():
        path = target / name
        if path.exists() and md5_of(path) != expected:
            print(f"{label}: BAD checksum {name}")
            problems += 1
    count = len(list(target.glob("[0-9][0-9][0-9][0-9][0-9][0-9].mp3")))
    print(f"{label}: {count} files, {problems} with a bad checksum")
    return problems == 0 and count >= EXPECTED_VERSES


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--only", nargs="*", help="reciter or reciter:style to fetch, e.g. minshawi abdulbasit:mujawwad")
    arguments = parser.parse_args()
    wanted = set(arguments.only or [])
    free = shutil.disk_usage(ROOT).free / 1e9
    jobs = [
        (reciter, style, recording)
        for reciter in RECITERS
        for style, recording in reciter.recordings.items()
        if not wanted or reciter.key in wanted or f"{reciter.key}:{style}" in wanted
    ]
    if not jobs:
        sys.exit("nothing matches --only")
    need = sum(r.size_gb for *_, r in jobs) * 2  # the zip and what is unpacked from it
    print(f"{len(jobs)} download(s), about {need / 2:g} GB; {free:.0f} GB free on this disk")
    if free < max(r.size_gb for *_, r in jobs) * 2 + 1:
        sys.exit("not enough free disk space")
    failed = []
    for reciter, style, recording in jobs:
        try:
            if not fetch_one(reciter, style, recording):
                failed.append(f"{reciter.key}/{style}")
        except (OSError, zipfile.BadZipFile) as error:
            print(f"{reciter.key}/{style}: stopped ({error}). Run the command again to continue.")
            failed.append(f"{reciter.key}/{style}")
    if failed:
        sys.exit("not finished: " + ", ".join(failed))
    print("Done.")


if __name__ == "__main__":
    main()
