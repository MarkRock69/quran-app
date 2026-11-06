#!/usr/bin/env python3
"""Download the Mushaf page fonts into data/fonts (one time, about 220 MB).

    python3 tools/fetch_fonts.py

The fonts are the King Fahd Glorious Qur'an Printing Complex's, taken from the
public mirror github.com/nuqayah/qpc-fonts. They are not kept in this
repository (size, and their own licence); data/fonts is ignored by git.

  QCF2001.ttf ... QCF2604.ttf  one font per page, drawn with the glyph codes in the database
  QCF2BSML.ttf                 the chapter banner, the 114 chapter names and the basmala
  UthmanTN1 Ver10.otf          Uthman Taha Naskh, for the page heading
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESTINATION = ROOT / "data" / "fonts"
REPOSITORY = "https://github.com/nuqayah/qpc-fonts.git"


def run(*command, cwd=None):
    subprocess.run(command, cwd=cwd, check=True)


def main():
    if shutil.which("git") is None:
        sys.exit("git is needed: sudo apt install git")
    DESTINATION.mkdir(parents=True, exist_ok=True)
    extras = {
        "mushaf-v2/QCF2BSML.ttf": "QCF2BSML.ttf",  # chapter banner, chapter names, basmala
        "various/UthmanTN1 Ver10.otf": "UthmanTN1.otf",
    }
    pages_missing = any(not (DESTINATION / f"QCF2{n:03d}.ttf").exists() for n in range(1, 605))
    wanted = {path: name for path, name in extras.items() if not (DESTINATION / name).exists()}
    if not pages_missing and not wanted:
        print(f"Everything is already in {DESTINATION}")
        return
    with tempfile.TemporaryDirectory() as folder:
        print("Downloading" + (" (the page fonts take a few minutes)..." if pages_missing else "..."))
        run("git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", REPOSITORY, folder)
        if pages_missing:
            run("git", "sparse-checkout", "set", "mushaf-v2", "various", cwd=folder)
            wanted = extras
        else:  # only the small files that are missing
            run("git", "sparse-checkout", "set", "--no-cone", *(f"/{path}" for path in wanted), cwd=folder)
        source = Path(folder)
        if pages_missing:
            for font in sorted((source / "mushaf-v2").glob("QCF2[0-9][0-9][0-9].ttf")):
                shutil.copy2(font, DESTINATION / font.name)
        for path, name in wanted.items():
            shutil.copy2(source / path, DESTINATION / name)
    count = len(list(DESTINATION.glob("QCF2[0-9][0-9][0-9].ttf")))
    if count != 604:
        sys.exit(f"expected 604 page fonts, found {count}")
    print(f"Done: {count} page fonts in {DESTINATION}")


if __name__ == "__main__":
    main()
