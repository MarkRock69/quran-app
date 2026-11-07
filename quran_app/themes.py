"""Colours of the pages. The side panel follows the system's Qt theme; the pages have their own, light or dark."""

THEMES = {
    "light": {
        "surround": "#e9e2d0", "page": "#fbf8ee", "text": "#111111", "muted": "#666666",
        "frame": "#2f6b57", "ribbon": "#b3261e", "selection": (70, 130, 220, 90),
    },
    "dark": {
        "surround": "#121212", "page": "#1c1c1c", "text": "#e6e1d3", "muted": "#9a9a9a",
        "frame": "#4fa386", "ribbon": "#e0483f", "selection": (90, 150, 240, 110),
    },
}
DEFAULT_THEME = "light"
