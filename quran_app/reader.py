"""A window that shows the Mushaf, one page or two pages side by side.

    python3 -m quran_app.reader [--page 42] [--spread]

Keys:  Ctrl+G = go to (page, chapter, juz', hizb, rub' or verse 2:255),  Ctrl+F = search,  Ctrl+I = the chapter and rub' lists,  Ctrl+T = tafsir of the clicked verse,
       The ☰ button (top corner) opens the side panel, which has all of these as tabs.
       Ctrl+B = bookmark this page (the list is the second tab of the side panel),
       Left / PageDown / scroll down = next page,  Right / PageUp / scroll up = previous,
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
    QPolygonF, QShortcut,
    QAction, QColor, QFont, QFontDatabase, QFontMetricsF, QGuiApplication, QKeySequence,
    QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import QApplication, QDockWidget, QMainWindow, QMenu, QToolButton, QWidget

from .banner import (
    BANNER_FRAME, BASMALA, OVAL_HEIGHT, OVAL_LEFT, OVAL_RIGHT, SURAH_WORD, chapter_name_glyph, plan_frame,
    stretch_x,
)
from .bookmarks import DEFAULT_PATH, Bookmarks
from .mushaf import PAGE_COUNT, Mushaf, hit_test, layout_page, spread_of
from .numbers import format_number, next_style
from .page_header import header_for
from .panels import BookmarksPanel, IndexPanel, JumpPanel, SearchPanel, SidePanel, TafsirPanel, ViewPanel

ROOT = Path(__file__).resolve().parent.parent
PAGE_ASPECT = 0.70  # width / height of one page
PAGE_BACKGROUND = QColor("#fbf8ee")
TEXT_COLOR = QColor("#111111")
SELECTION_COLOR = QColor(70, 130, 220, 90)
FRAME_COLOR = QColor("#2f6b57")
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
        self.banner_family = self._load(self.folder / "QCF2BSML.ttf")

    def banner_font(self):
        font = QFont(self.banner_family or "serif")
        font.setPixelSize(100)  # the painter scales it
        font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
        return font

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
    menu_clicked = Signal()
    verse_clicked = Signal(int)  # the glyph id of a cell that was clicked

    def __init__(self, mushaf, fonts):
        super().__init__()
        self._wheel = 0
        self.number_style = "indic"  # 'indic', 'western' or 'words'
        self.bookmarks = None
        self._menu_button = None
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
    def digits(self):
        return "western" if self.number_style == "western" else "indic"

    def add_menu_button(self):
        """A hamburger button in the top corner; it announces `menu_clicked`."""
        button = QToolButton(self)
        button.setText("\u2630")
        button.setAutoRaise(True)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # the arrow keys keep turning pages
        button.setFixedSize(40, 36)
        button.setStyleSheet("QToolButton { font-size: 24px; color: #444; border: none; }")
        button.clicked.connect(self.menu_clicked)
        self._menu_button = button
        self._place_menu_button()

    def _place_menu_button(self):
        if self._menu_button is not None:
            self._menu_button.move(self.width() - self._menu_button.width() - 8, 6)
            self._menu_button.raise_()

    def resizeEvent(self, event):
        self._place_menu_button()
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
            if self.bookmarks is not None and self.bookmarks.has(page):
                self._paint_ribbon(painter, rect)
            painter.setFont(QFont("sans-serif", 9))
            painter.setPen(QColor("#666666"))
            painter.drawText(
                QRectF(rect.x(), rect.bottom() - rect.height() * 0.05, rect.width(), rect.height() * 0.05),
                Qt.AlignmentFlag.AlignCenter, format_number(page, self.digits),
            )

    @staticmethod
    def _paint_ribbon(painter, rect):
        """A small red ribbon at the top corner of a bookmarked page."""
        x, y, w, h = rect.x() + rect.width() * 0.006, rect.y(), rect.width() * 0.028, rect.height() * 0.055
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#b3261e"))
        painter.drawPolygon(QPolygonF([QPointF(x, y), QPointF(x + w, y), QPointF(x + w, y + h),
                                       QPointF(x + w / 2, y + h * 0.78), QPointF(x, y + h)]))

    def _paint_page_header(self, painter, page, rect):
        header = header_for(self.mushaf.page_info(page), self.mushaf.chapter_name(
            self.mushaf.page_info(page).chapter), self.number_style)
        font = QFont(self.fonts.text_family or "serif")
        font.setPixelSize(max(8, round(rect.height() * 0.026)))
        painter.setFont(font)
        painter.setPen(TEXT_COLOR)
        strip = QRectF(rect.x() + rect.width() * 0.04, rect.y() + rect.height() * 0.012,
                       rect.width() * 0.92, rect.height() * 0.042)
        painter.drawText(strip, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter,
                         header.right)
        # name first, so the number lands to its left in a right-to-left line
        painter.drawText(strip, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter,
                         f"{header.chapter_name} {header.chapter_number}")
        painter.setPen(QPen(FRAME_COLOR, 1))
        painter.drawLine(QPointF(strip.left(), strip.bottom() + 2), QPointF(strip.right(), strip.bottom() + 2))

    def _paint_header(self, painter, item, x, y, size):
        """The chapter banner (frame and calligraphic name) or the basmala, from the King Fahd font."""
        box = QRectF(x, y, item.width, item.height)
        font = self.fonts.banner_font()
        if item.line.kind == "basmala":
            self._draw_fitted(painter, font, BASMALA, box.adjusted(box.width() * 0.2, box.height() * 0.05,
                                                                    -box.width() * 0.2, -box.height() * 0.05))
            return
        oval = self._draw_frame(painter, font, box.adjusted(0, box.height() * 0.04, 0, -box.height() * 0.04))
        # the oval in the middle of the frame holds "سورة" and the name
        self._draw_name(painter, font, chapter_name_glyph(item.line.chapter), oval)

    def _draw_frame(self, painter, font, box):
        """Draw the banner frame across the whole box, stretched in the middle. Returns the oval's rectangle."""
        path = QPainterPath()
        path.addText(0, 0, font, BANNER_FRAME)
        ink = path.boundingRect()
        scale, extra = plan_frame(ink.width(), ink.height(), box.width(), box.height())
        cut = ink.center().x()
        stretched = QPainterPath()
        stretched.setFillRule(Qt.FillRule.WindingFill)
        count, i = path.elementCount(), 0

        def point(element):
            return stretch_x(element.x, cut, extra), element.y

        while i < count:
            element = path.elementAt(i)
            if element.isMoveTo():
                stretched.moveTo(*point(element))
                i += 1
            elif element.isLineTo():
                stretched.lineTo(*point(element))
                i += 1
            else:  # a curve: this element and the next two
                stretched.cubicTo(*point(element), *point(path.elementAt(i + 1)), *point(path.elementAt(i + 2)))
                i += 3
        width, height = (ink.width() + extra) * scale, ink.height() * scale
        left, top = box.center().x() - width / 2, box.center().y() - height / 2
        painter.save()
        painter.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        painter.translate(left - ink.x() * scale, top - ink.y() * scale)
        painter.scale(scale, scale)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(FRAME_COLOR)
        painter.drawPath(stretched)
        painter.restore()
        oval_left = left + ink.width() * OVAL_LEFT * scale
        oval_right = left + (ink.width() * OVAL_RIGHT + extra) * scale
        oval = QRectF(0, 0, (oval_right - oval_left) * 0.89, height * OVAL_HEIGHT)
        oval.moveCenter(QPointF((oval_left + oval_right) / 2, top + height / 2))
        return oval

    @staticmethod
    def _ink(font, text):
        return QFontMetricsF(font).tightBoundingRect(text)

    def _draw_ink(self, painter, font, text, ink_x, baseline, scale, color):
        """Draw `text` so that its ink starts at ink_x, scaled, on the given baseline."""
        painter.save()
        # Left to right, so that the bidi algorithm does not mirror a bracket-like code of the banner
        # font: Al-Fatiha is "]" in it, and would be drawn as "[" (an ornament) in a right-to-left window.
        painter.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        painter.translate(ink_x - self._ink(font, text).x() * scale, baseline)
        painter.scale(scale, scale)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(QPointF(0, 0), text)
        painter.restore()

    def _draw_fitted(self, painter, font, text, box, color=TEXT_COLOR):
        """Draw `text` as large as fits in `box` (same proportions), centered. Returns where its ink went."""
        ink = self._ink(font, text)
        scale = min(box.width() / ink.width(), box.height() / ink.height())
        target = QRectF(0, 0, ink.width() * scale, ink.height() * scale)
        target.moveCenter(box.center())
        self._draw_ink(painter, font, text, target.x(), target.y() - ink.y() * scale, scale, color)
        return target

    def _draw_name(self, painter, font, name, box):
        word = self._ink(font, SURAH_WORD)
        title = self._ink(font, name)
        gap = 18  # at 100 px
        top, bottom = min(word.top(), title.top()), max(word.bottom(), title.bottom())
        total = word.width() + gap + title.width()
        scale = min(box.width() / total, box.height() / (bottom - top))
        right = box.center().x() + total * scale / 2
        baseline = box.center().y() - (bottom - top) * scale / 2 - top * scale
        self._draw_ink(painter, font, SURAH_WORD, right - word.width() * scale, baseline, scale, TEXT_COLOR)
        self._draw_ink(painter, font, name, right - (word.width() + gap + title.width()) * scale, baseline,
                       scale, TEXT_COLOR)

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
            if self._anchor:
                self.verse_clicked.emit(self._anchor)

    def mouseMoveEvent(self, event):
        if self._anchor is not None and event.buttons() & Qt.MouseButton.LeftButton:
            focus = self._cell_at(event.position())
            if focus is not None:
                self.selection = tuple(sorted((self._anchor, focus)))
                self.update()

    def selected_text(self):
        return self.mushaf.text_between(*self.selection, digits=self.digits) if self.selection else ""

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
    def __init__(self, mushaf, fonts, page, spread, database_path, bookmarks):
        super().__init__()
        self.setWindowTitle("القرآن الكريم")  # القرآن الكريم
        self.mushaf, self.bookmarks = mushaf, bookmarks
        self.canvas = PageCanvas(mushaf, fonts)
        self.canvas.bookmarks = bookmarks
        self.setCentralWidget(self.canvas)
        self.canvas.page_step.connect(self.step)
        self.page = page
        self.spread = spread
        digits = lambda: self.canvas.digits  # noqa: E731
        self.search = SearchPanel(database_path, fonts.text_family, digits)
        self.jump = JumpPanel(mushaf)
        self.tafsir = TafsirPanel(mushaf, fonts.text_family, digits)
        self.index = IndexPanel(mushaf, fonts.text_family, digits)
        self.marks = BookmarksPanel(bookmarks, mushaf, digits)
        self.view = ViewPanel(spread, self.canvas.number_style)
        self.search.chosen.connect(self.show_verse)
        self.jump.jumped.connect(self.on_jump)
        self.index.chosen.connect(self.go_to)
        self.marks.chosen.connect(self.go_to)
        self.marks.toggle_here.connect(self.toggle_bookmark)
        self.marks.removed_page.connect(lambda _: self.canvas.update())
        self.view.spread_changed.connect(self.set_spread)
        self.view.style_changed.connect(self.set_number_style)
        self.canvas.menu_clicked.connect(self.toggle_side)
        self.canvas.verse_clicked.connect(self.pick_verse)
        self.side = QDockWidget("القائمة", self)
        self.side.setWidget(SidePanel(self.search, self.jump, self.index, self.tafsir, self.marks, self.view))
        self.side.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.side)
        self.side.setMinimumWidth(500)
        self.side.hide()
        for keys, action in (("Ctrl+G", self.open_jump), ("Ctrl+F", self.open_search), ("Ctrl+B", self.toggle_bookmark), ("Ctrl+I", self.open_index),
                              ("Ctrl+T", self.open_tafsir),
                              ("Escape", self.close_side)):
            QShortcut(QKeySequence(keys), self, activated=action)
        self.canvas.add_menu_button()
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

    def toggle_side(self):
        if self.side.isVisible():
            self.close_side()
        else:
            self.side.show()

    def toggle_spread(self):
        self.set_spread(not self.spread)

    def set_spread(self, spread):
        self.spread = spread
        self.view.show_state(self.spread, self.canvas.number_style)
        self.refresh()

    def cycle_numbers(self):
        self.set_number_style(next_style(self.canvas.number_style))

    def set_number_style(self, style):
        self.canvas.set_number_style(style)
        self.view.show_state(self.spread, style)
        self.search.refresh_numbers()
        self.index.refresh()
        self.tafsir.refresh()
        self.marks.refresh()

    def on_jump(self, target):
        if target.verse:
            self.show_verse(*target.verse)
        else:
            self.go_to(target.page)

    def show_verse(self, chapter, number):
        """Open the page of a verse and select it."""
        self.go_to(self.mushaf.page_of_verse(chapter, number))
        self.canvas.selection = self.mushaf.verse_cells(chapter, number)
        self.tafsir.set_verse(chapter, number)
        self.canvas.update()
        self.canvas.setFocus()

    def open_jump(self):
        self.side.show()
        self.side.widget().setCurrentWidget(self.jump)
        self.jump.focus()

    def pick_verse(self, glyph_id):
        """A click on the page: the tafsir shows this verse (if the panel is open or was used)."""
        chapter, number = self.mushaf.verse_of_glyph(glyph_id)
        self.tafsir.set_verse(chapter, number)

    def open_tafsir(self):
        self.side.show()
        self.side.widget().setCurrentWidget(self.tafsir)
        if not self.tafsir.has_verse():
            self.tafsir.set_verse(*self.mushaf.first_verse_of_page(self.page))

    def open_index(self):
        self.side.show()
        self.side.widget().setCurrentWidget(self.index)

    def open_search(self):
        self.side.show()
        self.side.widget().setCurrentWidget(self.search)
        self.search.focus()

    def close_side(self):
        self.side.hide()
        self.canvas.setFocus()

    def toggle_bookmark(self):
        self.bookmarks.toggle(self.page)  # in two-page mode, the right-hand page
        self.marks.refresh()
        self.canvas.update()

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
            self.toggle_spread()
        elif ctrl and key == Qt.Key.Key_D:
            self.cycle_numbers()
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
    parser.add_argument("--user-db", type=Path, default=DEFAULT_PATH, help="where bookmarks are kept")
    parser.add_argument("--spread", action="store_true", help="show two pages side by side")
    arguments = parser.parse_args()
    if not arguments.db.exists():
        sys.exit(f"{arguments.db} not found. Run: python3 tools/build_database.py")
    if not all((arguments.fonts / name).exists() for name in ("QCF2001.ttf", "QCF2BSML.ttf")):
        sys.exit("Fonts not found or incomplete. Run: python3 tools/fetch_fonts.py")
    application = QApplication(sys.argv[:1])
    application.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    window = ReaderWindow(Mushaf(arguments.db), Fonts(arguments.fonts), arguments.page, arguments.spread,
                          arguments.db, Bookmarks(arguments.user_db))
    window.show()
    sys.exit(application.exec())


if __name__ == "__main__":
    main()
