"""Put the app in the applications menu (and so in the search of the GNOME overview).

    python3 tools/install_launcher.py            # add it
    python3 tools/install_launcher.py --remove   # take it out again

The menu entry runs this folder's copy of the app with the Python that ran this script, so run it again
from the new folder whenever you move to a new copy of the project.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
APPLICATIONS = Path.home() / ".local" / "share" / "applications"
ICONS = Path.home() / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps"
ENTRY = APPLICATIONS / "quran-app.desktop"
ICON = ICONS / "quran-app.svg"


def desktop_entry(project, python):
    """The text of the .desktop file. Exec values are quoted as the specification asks."""
    def quote(text):
        return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`") + '"'
    return "\n".join((
        "[Desktop Entry]",
        "Type=Application",
        "Name=Quran",
        "Comment=Mushaf reader",
        f"Exec={quote(python)} -m quran_app.reader",
        f"Path={project}",
        "Icon=quran-app",
        "StartupWMClass=quran-app",
        "Terminal=false",
        "Categories=Education;Literature;",
        "Keywords=quran;mushaf;qur'an;قرآن;مصحف;",
        "",
    ))


def refresh():
    for command in (["update-desktop-database", str(APPLICATIONS)], ["gtk-update-icon-cache", "-f", "-t", str(ICONS.parents[2])]):
        if shutil.which(command[0]):
            subprocess.run(command, check=False, capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--remove", action="store_true")
    arguments = parser.parse_args()
    if arguments.remove:
        ENTRY.unlink(missing_ok=True)
        ICON.unlink(missing_ok=True)
        refresh()
        print("Removed the menu entry.")
        return
    APPLICATIONS.mkdir(parents=True, exist_ok=True)
    ICONS.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROJECT / "assets" / "quran-app.svg", ICON)
    ENTRY.write_text(desktop_entry(PROJECT, sys.executable), encoding="utf-8")
    ENTRY.chmod(0o755)
    refresh()
    print(f"Added '{ENTRY.name}'. Search for \"Quran\" in the applications menu.")
    print(f"It starts {PROJECT} with {sys.executable}.")


if __name__ == "__main__":
    main()
