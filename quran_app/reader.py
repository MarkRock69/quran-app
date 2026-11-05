"""A window that shows the Mushaf, one page or two pages side by side.

    python3 -m quran_app.reader [--page 42] [--spread]

Keys:  Left / PageDown / scroll down = next page,  Right / PageUp / scroll up = previous,
       Ctrl+2 = switch between one page and two,
       Ctrl+D = numbers as Arabic-Indic digits, Western digits, or ordinal words,  Ctrl+C = copy the selection,
       Home / End = first / last page,  Ctrl+Q = quit.
Select text with the mouse; Ctrl+C (or the right-click menu) copies the real
Uthmani text, not the font's glyph codes.

All geometry and text logic is in mushaf.py (tested without Qt); this file only
measures, paints and handles input.
"""

import argparse
import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QAction, QColor, QFont, QFontDatabase, QFontMetricsF, QGuiApplication, QKeySequence,
    QPainter, QPen,
)
from PySide6.QtWidgets import QApplication, QMainWindow, QMenu, QWidget

from .mushaf import PAGE_COUNT, Mushaf, hit_test, layout_page, spread_of
from .numbers import format_number, next_style
from .page_header import header_for

ROOT = Path(__file__).resolve().parent.parent
PAGE_ASPECT = 0.70  # width / height of one page
PAGE_BACKGROUND = QColor("#fbf8ee")
TEXT_COLOR = QColor("#111111")
SELECTION_COLOR = QColor(70, 130, 220, 90)
FRAME_COLOR = QColor("#8a6d2b")
NAME_BACKGROUND = QColor("#efe6c8")
BASMALA = "بِسْمِ ٱللَّهِ ٱلرَّحْمَـٰنِ ٱلرَّحِيمِ"
MEASURE_SIZE = 1000  # measure glyphs at a large size, then divide


class Fonts:
    """Loads the page fonts on demand."""

    def __init__(self, folder):
        self.folder = Path(folder)
        self._families = {}
        self.text_family = None
        name_font = self.folder / "UthmanTN1.otf"
        if name_font.exists():
            self.text_family = self._load(name_font)

    @staticmethod
    def _load(path):
        font_id = QFontDatabase.addApplicationFont(str(path))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        return families[0] if families else None

    def page_family(self, page):
        if page not in self._families:
            path = self.folder / f"QCF2{page:03d}.ttf"
            self._families[page] = self._load(path) if path.exists() else None
        return self._families[page]

    def page_font(self, page, pixel_size):
        font = QFont(self.page_family(page) or "serif")
        font.setPixelSize(max(1, round(pixel_size)))
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        return font

    def measurer(self, page):
        """A function giving the width of a text in ems, in this page's font."""
        metrics = QFontMetricsF(self.page_font(page, MEASURE_SIZE))
        return lambda text: metrics.horizontalAdvance(text) / MEASURE_SIZE


WHEEL_STEP = 120  # one notch of a mouse wheel; touchpads send smaller amounts that add up


class PageCanvas(QWidget):
    page_step = Signal(int)  # +1 = next page (or spread), -1 = previous

    def __init__(self, mushaf, fonts):
        super().__init__()
        self._wheel = 0
        self.number_style = "indic"  # 'indic', 'western' or 'words'
        self.mushaf = mushaf
        self.fonts = fonts
        self.pages = []  # pages shown, right to left
        self.selection = None  # (first glyph id, last glyph id), as dragged
        self._anchor = None
        self._layouts = {}  # page -> (rect, placed, size)
        self.setMouseTracking(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def show_pages(self, pages):
        self.pages = [p for p in pages if p]
        self.selection = None
        self._layouts.clear()
        self.update()

    def set_number_style(self, style):
        self.number_style = style
        self.update()

    @property
    def _digits(self):
        return "western" if self.number_style == "western" else "indic"

    def resizeEvent(self, event):
        self._layouts.clear()
        super().resizeEvent(event)

    def wheelEvent(self, event):
        """Scroll down for the next page, up for the previous one."""
        self._wheel += event.angleDelta().y()
        while abs(self._wheel) >= WHEEL_STEP:
            self.page_step.emit(1 if self._wheel < 0 else -1)
            self._wheel += WHEEL_STEP if self._wheel < 0 else -WHEEL_STEP
        event.accept()

    # ------------------------------------------------------------ layout

    def _page_rects(self):
        count = max(1, len(self.pages))
        margin = 12
        available_width = (self.width() - margin * (count + 1)) / count
        available_height = self.height() - margin * 2
        width = min(available_width, available_height * PAGE_ASPECT)
        height = width / PAGE_ASPECT
        total = width * count + margin * (count - 1)
        left = (self.width() - total) / 2
        top = (self.height() - height) / 2
        # pages are listed right to left, so the first is the rightmost
        return [
            QRectF(left + (count - 1 - index) * (width + margin), top, width, height)
            for index in range(len(self.pages))
        ]

    def _layout(self, page, rect):
        if page not in self._layouts:
            inner = QRectF(rect.x() + rect.width() * 0.04, rect.y() + rect.height() * 0.065,
                           rect.width() * 0.92, rect.height() * 0.865)
            reference = layout_page(
                self.mushaf.page(3), self.fonts.measurer(3), inner.width(), inner.height(), 20
            )[1]
            placed, size = layout_page(
                self.mushaf.page(page), self.fonts.measurer(page), inner.width(), inner.height(),
                reference,
            )
            self._layouts[page] = (inner, placed, size)
        return self._layouts[page]

    # ------------------------------------------------------------ painting

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.fillRect(self.rect(), QColor("#e9e2d0"))
        low, high = self.selection if self.selection else (None, None)
        for page, rect in zip(self.pages, self._page_rects()):
            painter.fillRect(rect, PAGE_BACKGROUND)
            inner, placed, size = self._layout(page, rect)
            font = self.fonts.page_font(page, size)
            metrics = QFontMetricsF(font)
            shift = (metrics.ascent() - metrics.descent()) / 2
            for item in placed:
                x, y = inner.x() + item.x, inner.y() + item.y
                if item.cell is None:
                    self._paint_header(painter, item, x, y, size)
                    continue
                if low is not None and low <= item.cell.glyph_id <= high:
                    painter.fillRect(QRectF(x, y, item.width, item.height), SELECTION_COLOR)
                painter.setFont(font)
                painter.setPen(TEXT_COLOR)
                painter.drawText(QPointF(x, y + item.height / 2 + shift), item.cell.text)
            self._paint_page_header(painter, page, rect)
            painter.setFont(QFont("sans-serif", 9))
            painter.setPen(QColor("#666666"))
            painter.drawText(
                QRectF(rect.x(), rect.bottom() - rect.height() * 0.05, rect.width(), rect.height() * 0.05),
                Qt.AlignmentFlag.AlignCenter, format_number(page, self._digits),
            )

    def _paint_page_header(self, painter, page, rect):
        header = header_for(self.mushaf.page_info(page), self.mushaf.chapter_name(
            self.mushaf.page_info(page).chapter), self.number_style)
        font = QFont(self.fonts.text_family or "serif")
        font.setPixelSize(max(8, round(rect.height() * 0.026)))
        painter.setFont(font)
        painter.setPen(TEXT_COLOR)
        strip = QRectF(rect.x() + rect.width() * 0.04, rect.y() + rect.height() * 0.012,
                       rect.width() * 0.92, rect.height() * 0.042)
        painter.drawText(strip, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, header.right)
        # name first, so the number lands to its left in a right-to-left line
        painter.drawText(strip, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         f"{header.chapter_name} {header.chapter_number}")
        painter.setPen(QPen(FRAME_COLOR, 1))
        painter.drawLine(QPointF(strip.left(), strip.bottom() + 2), QPointF(strip.right(), strip.bottom() + 2))

    def _paint_header(self, painter, item, x, y, size):
        font = QFont(self.fonts.text_family or "serif")
        font.setPixelSize(max(1, round(size * 0.8)))
        painter.setFont(font)
        painter.setPen(TEXT_COLOR)
        area = QRectF(x, y, item.width, item.height)
        if item.line.kind == "basmala":
            painter.drawText(area, Qt.AlignmentFlag.AlignCenter, BASMALA)
            return
        text = "سُورَةُ " + self.mushaf.chapter_name(item.line.chapter)
        box = QRectF(x + item.width * 0.12, y + item.height * 0.1, item.width * 0.76, item.height * 0.8)
        painter.setPen(QPen(FRAME_COLOR, 2))
        painter.setBrush(NAME_BACKGROUND)
        painter.drawRoundedRect(box, 6, 6)
        painter.setPen(TEXT_COLOR)
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    # ------------------------------------------------------------ selection

    def _cell_at(self, point):
        for page, rect in zip(self.pages, self._page_rects()):
            if rect.contains(point):
                inner, placed, _ = self._layout(page, rect)
                cell = hit_test(placed, point.x() - inner.x(), point.y() - inner.y())
                return cell.glyph_id if cell else None
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._anchor = self._cell_at(event.position())
            self.selection = (self._anchor, self._anchor) if self._anchor else None
            self.update()

    def mouseMoveEvent(self, event):
        if self._anchor is not None and event.buttons() & Qt.MouseButton.LeftButton:
            focus = self._cell_at(event.position())
            if focus is not None:
                self.selection = tuple(sorted((self._anchor, focus)))
                self.update()

    def selected_text(self):
        return self.mushaf.text_between(*self.selection, digits=self._digits) if self.selection else ""

    def copy(self):
        text = self.selected_text()
        if text:
            QGuiApplication.clipboard().setText(text)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        action = QAction("نسخ", menu)  # نسخ
        action.setEnabled(bool(self.selection))
        action.triggered.connect(self.copy)
        menu.addAction(action)
        menu.exec(event.globalPos())


class ReaderWindow(QMainWindow):
    def __init__(self, mushaf, fonts, page, spread):
        super().__init__()
        self.setWindowTitle("القرآن الكريم")  # القرآن الكريم
        self.canvas = PageCanvas(mushaf, fonts)
        self.setCentralWidget(self.canvas)
        self.canvas.page_step.connect(self.step)
        self.page = page
        self.spread = spread
        self.resize(1100, 800)
        self.refresh()

    def refresh(self):
        if self.spread:
            left, right = spread_of(self.page)
            self.page = right
            self.canvas.show_pages([right, left])  # read right to left: the right page first
        else:
            self.canvas.show_pages([self.page])

    def go_to(self, page):
        self.page = min(PAGE_COUNT, max(1, page))
        self.refresh()

    def step(self, direction):
        if self.spread:
            left, right = spread_of(self.page)
            self.go_to(left + 1 if direction > 0 else right - 1)
        else:
            self.go_to(self.page + direction)

    def keyPressEvent(self, event):
        key, ctrl = event.key(), event.modifiers() & Qt.KeyboardModifier.ControlModifier
        if key in (Qt.Key.Key_Left, Qt.Key.Key_PageDown):
            self.step(+1)
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_PageUp):
            self.step(-1)
        elif key == Qt.Key.Key_Home:
            self.go_to(1)
        elif key == Qt.Key.Key_End:
            self.go_to(PAGE_COUNT)
        elif ctrl and key == Qt.Key.Key_2:
            self.spread = not self.spread
            self.refresh()
        elif ctrl and key == Qt.Key.Key_D:
            self.canvas.set_number_style(next_style(self.canvas.number_style))
        elif event.matches(QKeySequence.StandardKey.Copy):
            self.canvas.copy()
        elif ctrl and key == Qt.Key.Key_Q:
            self.close()
        else:
            super().keyPressEvent(event)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db", type=Path, default=ROOT / "build" / "quran.db")
    parser.add_argument("--fonts", type=Path, default=ROOT / "data" / "fonts")
    parser.add_argument("--page", type=int, default=1)
    parser.add_argument("--spread", action="store_true", help="show two pages side by side")
    arguments = parser.parse_args()
    if not arguments.db.exists():
        sys.exit(f"{arguments.db} not found. Run: python3 tools/build_database.py")
    if not (arguments.fonts / "QCF2001.ttf").exists():
        sys.exit("Page fonts not found. Run: python3 tools/fetch_fonts.py")
    application = QApplication(sys.argv[:1])
    application.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    window = ReaderWindow(Mushaf(arguments.db), Fonts(arguments.fonts), arguments.page, arguments.spread)
    window.show()
    sys.exit(application.exec())


if __name__ == "__main__":
    main()
