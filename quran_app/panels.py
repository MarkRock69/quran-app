"""The side panel: search, go to, bookmarks, and how the book is shown. Qt only; the logic is in search.py,
navigation.py and bookmarks.py, which are tested without a window."""

from html import escape

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QTextDocument
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QRadioButton, QSpinBox, QStyle, QStyledItemDelegate, QTabWidget, QTextBrowser, QVBoxLayout, QHBoxLayout,
    QWidget,
)

from .index_lists import Band, ChapterRow, RubRow, revelation_text, verse_count_text
from .navigation import HINT, KINDS
from .numbers import format_number
from .page_header import header_for
from .search import ALL_WORDS, ANY_WORD, PHRASE, SearchIndex, SearchOptions

MATCH_COLOR = "#b3261e"
MUTED_COLOR = "#6b6b6b"
MAX_RESULTS = 300
HTML_ROLE = Qt.ItemDataRole.UserRole
TARGET_ROLE = Qt.ItemDataRole.UserRole + 1


class RichDelegate(QStyledItemDelegate):
    """Draws each list row from the HTML stored in it, wrapped to the width of the list."""

    def __init__(self, view, family):
        super().__init__(view)
        self._view = view
        self._family = family

    def _document(self, index):
        document = QTextDocument()
        font = QFont(self._family or "serif")
        font.setPixelSize(20)
        document.setDefaultFont(font)
        document.setHtml(f'<div dir="rtl">{index.data(HTML_ROLE)}</div>')
        document.setTextWidth(max(100, self._view.viewport().width() - 16))
        return document

    def sizeHint(self, option, index):
        document = self._document(index)
        return QSize(int(document.textWidth()), int(document.size().height()) + 10)

    def paint(self, painter, option, index):
        painter.save()
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(70, 130, 220, 60))
        painter.translate(option.rect.x() + 8, option.rect.y() + 5)
        self._document(index).drawContents(painter, QRectF(0, 0, option.rect.width() - 16, option.rect.height()))
        painter.restore()
        painter.setPen(QColor(0, 0, 0, 30))
        painter.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())


def snippet_html(snippet, digits):
    number = lambda n: format_number(n, digits)  # noqa: E731
    head = (
        f'<span style="color:{MUTED_COLOR};font-size:14px">{escape(snippet.chapter_name)} {number(snippet.number)}'
        f"  ·  {number(snippet.chapter)}:{number(snippet.number)}</span><br>"
    )
    body = "".join(
        f'<b style="color:{MATCH_COLOR}">{escape(text)}</b>' if matched else escape(text)
        for text, matched in snippet.segments
    )
    return head + ("… " if not snippet.starts_at_verse_start else "") + body + (" …" if not snippet.ends_at_verse_end else "")


class SearchPanel(QWidget):
    """Search as you type. Choosing a result asks the window to show its verse."""

    chosen = Signal(int, int)  # chapter, verse number

    def __init__(self, database_path, family, digits):
        super().__init__()
        self._path, self._digits, self._index = database_path, digits, None
        layout = QVBoxLayout(self)
        self.box = QLineEdit()
        self.box.setPlaceholderText("ابحث في القرآن")
        self.box.textChanged.connect(self._schedule)
        self.box.returnPressed.connect(self._open_first)
        layout.addWidget(self.box)

        options = QHBoxLayout()
        self.mode = QComboBox()
        for label, mode in (("العبارة كاملة", PHRASE), ("كل الكلمات", ALL_WORDS), ("أي كلمة", ANY_WORD)):
            self.mode.addItem(label, mode)
        self.mode.currentIndexChanged.connect(self._schedule)
        self.strict = QCheckBox("مطابقة التشكيل")
        self.strict.toggled.connect(self._schedule)
        options.addWidget(self.mode)
        options.addWidget(self.strict)
        layout.addLayout(options)

        context = QHBoxLayout()
        self.before = self._spin()
        self.after = self._spin()
        context.addWidget(QLabel("كلمات قبل"))
        context.addWidget(self.before)
        context.addWidget(QLabel("وبعد"))
        context.addWidget(self.after)
        context.addStretch()
        layout.addLayout(context)

        self.summary = QLabel()
        layout.addWidget(self.summary)
        self.results = QListWidget()
        self.results.setItemDelegate(RichDelegate(self.results, family))
        self.results.setUniformItemSizes(False)
        self.results.itemActivated.connect(self._open)
        self.results.itemClicked.connect(self._open)
        layout.addWidget(self.results)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._run)

    def _spin(self):
        spin = QSpinBox()
        spin.setRange(0, 20)
        spin.setValue(3)
        spin.valueChanged.connect(self._schedule)
        return spin

    def focus(self):
        self.box.setFocus()
        self.box.selectAll()

    def refresh_numbers(self):
        self._schedule()

    def _schedule(self, *_):
        self._timer.start()

    def _ensure_index(self):
        if self._index is None:
            QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                self._index = SearchIndex.from_database(self._path)
            finally:
                QGuiApplication.restoreOverrideCursor()
        return self._index

    def _run(self):
        text = self.box.text()  # not stripped: a space at either end anchors it to a word boundary
        self.results.clear()
        if not text.strip():
            self.summary.setText("")
            return
        index = self._ensure_index()
        digits = self._digits()
        result = index.search(text, SearchOptions(self.mode.currentData(), self.strict.isChecked()))
        self.summary.setText(
            f"{format_number(result.occurrence_count, digits)} نتيجة في {format_number(result.verse_count, digits)} آية"
            + (f" (تُعرض أول {format_number(MAX_RESULTS, digits)})" if result.occurrence_count > MAX_RESULTS else "")
        )
        self.results.setUpdatesEnabled(False)
        for hit in result.hits[:MAX_RESULTS]:
            snippet = index.render(hit, self.before.value(), self.after.value())
            item = QListWidgetItem()
            item.setData(HTML_ROLE, snippet_html(snippet, digits))
            item.setData(TARGET_ROLE, (snippet.chapter, snippet.number))
            self.results.addItem(item)
        self.results.setUpdatesEnabled(True)

    def _open(self, item):
        chapter, number = item.data(TARGET_ROLE)
        self.chosen.emit(chapter, number)

    def _open_first(self):
        if self.results.count():
            self._open(self.results.item(0))


BAND_COLOR = QColor("#e3dcc7")
ROW_COLOR = QColor("#fbf8ee")
DEEP_GREEN = QColor("#2f6b57")
PALE_GREEN = QColor("#cfe3dc")
INK = QColor("#111111")
MUTED = QColor("#6b6b6b")


class IndexDelegate(QStyledItemDelegate):
    """Draws the rows of the chapter list and the rub' list like the Quran Android app:
    juz' bands, then rows with the page number at the left end."""

    BAND_HEIGHT, CHAPTER_HEIGHT, RUB_HEIGHT = 44, 78, 84

    def __init__(self, view, family, digits):
        super().__init__(view)
        self._family, self._digits = family, digits

    def sizeHint(self, option, index):
        row = index.data(HTML_ROLE)
        height = {Band: self.BAND_HEIGHT, ChapterRow: self.CHAPTER_HEIGHT, RubRow: self.RUB_HEIGHT}[type(row)]
        return QSize(option.rect.width(), height)

    def _font(self, pixels, bold=False, text=True):
        font = QFont(self._family if text and self._family else "sans-serif")
        font.setPixelSize(pixels)
        font.setBold(bold)
        return font

    def paint(self, painter, option, index):
        row, rect = index.data(HTML_ROLE), QRectF(option.rect)
        digits = self._digits()
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.fillRect(rect, BAND_COLOR if isinstance(row, Band) else ROW_COLOR)
        if selected:
            painter.fillRect(rect, QColor(70, 130, 220, 50))
        right, left = rect.right() - 16, rect.left() + 16
        number = lambda n: format_number(n, digits)  # noqa: E731
        page = row.page
        painter.setPen(MUTED)
        painter.setFont(self._font(16, text=False))
        painter.drawText(QRectF(left, rect.top(), 70, rect.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter,
                         number(page))
        if isinstance(row, Band):
            painter.setPen(INK)
            painter.setFont(self._font(20, bold=True))
            self._text(painter, QRectF(left + 80, rect.top(), right - left - 80, rect.height()),
                       f"الجزء {number(row.juz)}")
        elif isinstance(row, ChapterRow):
            painter.setPen(MUTED)
            painter.setFont(self._font(34, text=False))
            self._text(painter, QRectF(right - 56, rect.top(), 56, rect.height()), number(row.chapter))
            body = QRectF(left + 80, rect.top(), right - 70 - left - 80, rect.height())
            self._two_lines(painter, body, f"سُورَةُ {row.name}",
                            f"{revelation_text(row.meccan)} - {verse_count_text(row.verse_count, digits)}")
        else:
            self._pie(painter, QRectF(right - 54, rect.center().y() - 27, 54, 54), row, digits)
            body = QRectF(left + 80, rect.top(), right - 70 - left - 80, rect.height())
            self._two_lines(painter, body, row.text,
                            f"سُورَةُ {row.chapter_name}، آية {number(row.verse)}")
        painter.restore()

    def _text(self, painter, rect, text):
        text = painter.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, int(rect.width()))
        painter.drawText(rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute
                         | Qt.AlignmentFlag.AlignVCenter, text)

    def _two_lines(self, painter, body, first, second):
        half = body.height() / 2
        painter.setPen(INK)
        painter.setFont(self._font(21, bold=True))
        self._text(painter, QRectF(body.left(), body.top() + 6, body.width(), half - 2), first)
        painter.setPen(MUTED)
        painter.setFont(self._font(17))
        self._text(painter, QRectF(body.left(), body.center().y() - 2, body.width(), half - 2), second)

    def _pie(self, painter, rect, row, digits):
        """A full circle with the hizb number at the start of a hizb; otherwise the quarters gone by."""
        painter.setPen(Qt.PenStyle.NoPen)
        if row.position == 1:
            painter.setBrush(DEEP_GREEN)
            painter.drawEllipse(rect)
            painter.setPen(QColor("white"))
            painter.setFont(self._font(20, text=False))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, format_number(row.hizb, digits))
            return
        painter.setBrush(PALE_GREEN)
        painter.drawEllipse(rect)
        painter.setBrush(DEEP_GREEN)
        painter.drawPie(rect, 90 * 16, -(row.position - 1) * 90 * 16)  # clockwise from twelve o'clock


class IndexList(QListWidget):
    """One of the two lists. Choosing a row asks for its page."""

    chosen = Signal(int)

    def __init__(self, family, digits, rows):
        super().__init__()
        self.setItemDelegate(IndexDelegate(self, family, digits))
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        for row in rows:
            item = QListWidgetItem()
            item.setData(HTML_ROLE, row)
            self.addItem(item)
        self.itemClicked.connect(lambda item: self.chosen.emit(item.data(HTML_ROLE).page))
        self.itemActivated.connect(lambda item: self.chosen.emit(item.data(HTML_ROLE).page))


class IndexPanel(QTabWidget):
    """The chapter list and the rub' list."""

    chosen = Signal(int)  # page

    def __init__(self, mushaf, family, digits):
        super().__init__()
        self.chapters = IndexList(family, digits, mushaf.chapter_index())
        self.rubs = IndexList(family, digits, mushaf.rub_index())
        for view in (self.chapters, self.rubs):
            view.chosen.connect(self.chosen)
        self.addTab(self.chapters, "السور")
        self.addTab(self.rubs, "الأرباع")

    def refresh(self):
        self.chapters.viewport().update()
        self.rubs.viewport().update()


class TafsirPanel(QWidget):
    """The tafsir of one verse. The sources are a column of buttons beside the text, in the agreed order."""

    def __init__(self, mushaf, family, digits):
        super().__init__()
        self._mushaf, self._family, self._digits = mushaf, family, digits
        self._verse = None
        self._sources = mushaf.tafsir_sources()
        layout = QHBoxLayout(self)
        column = QVBoxLayout()
        self.title = QLabel("اضغط على آية في الصفحة لعرض تفسيرها")
        self.title.setWordWrap(True)
        self.title.setStyleSheet("font-weight: bold;")
        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        column.addWidget(self.title)
        column.addWidget(self.browser, 1)
        self.names = QListWidget()
        self.names.setFixedWidth(150)
        for source in self._sources:
            self.names.addItem(source.title)
        self.names.setCurrentRow(0)
        self.names.currentRowChanged.connect(lambda _: self._show())
        layout.addLayout(column, 1)
        layout.addWidget(self.names)  # in the right-to-left window this is the right-hand column

    def has_verse(self):
        return self._verse is not None

    def set_verse(self, chapter, number):
        self._verse = (chapter, number)
        self._show()

    def refresh(self):
        self._show()

    def showEvent(self, event):
        self._show()  # what was picked while the tab was hidden
        super().showEvent(event)

    def _show(self):
        if self._verse is None or not self.isVisible():
            return
        chapter, number = self._verse
        source = self._sources[max(0, self.names.currentRow())]
        digits = self._digits()
        name = self._mushaf.chapter_name(chapter)
        self.title.setText(f"سُورَةُ {name}، آية {format_number(number, digits)}")
        if not source.available:
            body = "<p>هذه الترجمة غير متوفرة حالياً.</p>"
            rtl = True
        else:
            found = self._mushaf.tafsir_entry(source, chapter, number)
            if found is None:
                body, rtl = "<p>لا يوجد في هذا المصدر تعليق على هذه الآية.</p>", True
            else:
                body, rtl = self._with_range(found, digits), source.rtl
        font = QFont(self._family if rtl and self._family else "sans-serif")
        font.setPixelSize(20 if rtl else 17)
        self.browser.document().setDefaultFont(font)
        direction = "rtl" if rtl else "ltr"
        self.browser.setHtml(f'<div dir="{direction}">{body}</div>')

    def _with_range(self, found, digits):
        if found.first == found.last:
            return found.html
        (c1, v1), (c2, v2) = found.first, found.last
        names = self._mushaf.chapter_name
        number = lambda n: format_number(n, digits)  # noqa: E731
        if c1 == c2:
            label = f"الآيات {number(v1)} إلى {number(v2)}"
        else:
            label = f"من {names(c1)} {number(v1)} إلى {names(c2)} {number(v2)}"
        return f'<p style="color:{MUTED_COLOR}" dir="rtl">{label}</p>' + found.html


class _PageList(QListWidget):
    """A list of bookmarked pages; Delete removes the selected one."""

    removed = Signal(int)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.currentItem() is not None:
            self.removed.emit(self.currentItem().data(TARGET_ROLE))
        else:
            super().keyPressEvent(event)


class BookmarksPanel(QWidget):
    """A button to bookmark (or unbookmark) the page being read, and the list of bookmarked pages."""

    chosen = Signal(int)  # page
    toggle_here = Signal()
    removed_page = Signal(int)

    def __init__(self, bookmarks, mushaf, digits):
        super().__init__()
        self._bookmarks, self._mushaf, self._digits = bookmarks, mushaf, digits
        layout = QVBoxLayout(self)
        button = QPushButton("إضافة علامة أو إزالتها في هذه الصفحة")
        button.clicked.connect(self.toggle_here)
        layout.addWidget(button)
        self.list = _PageList()
        self.list.itemActivated.connect(lambda item: self.chosen.emit(item.data(TARGET_ROLE)))
        self.list.itemClicked.connect(lambda item: self.chosen.emit(item.data(TARGET_ROLE)))
        self.list.removed.connect(self._remove)
        layout.addWidget(self.list)
        layout.addWidget(QLabel("زر Delete يحذف العلامة المحددة"))
        self.refresh()

    def _remove(self, page):
        self._bookmarks.remove(page)
        self.refresh()
        self.removed_page.emit(page)

    def refresh(self):
        digits = self._digits()
        self.list.clear()
        for page in self._bookmarks.pages():
            info = self._mushaf.page_info(page)
            item = QListWidgetItem(
                f"صفحة {format_number(page, digits)} — {self._mushaf.chapter_name(info.chapter)}"
                f" — {header_for(info, '', digits).right.split('،')[0]}"
            )
            item.setData(TARGET_ROLE, page)
            self.list.addItem(item)


class JumpPanel(QWidget):
    """Go to a page, chapter, juz', hizb or rub' by number, or to a verse as 2:255."""

    jumped = Signal(object)  # a navigation.Jump

    def __init__(self, mushaf):
        super().__init__()
        self._mushaf = mushaf
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.kind = QComboBox()
        for key, (_, _, name) in KINDS.items():
            self.kind.addItem(name, key)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(HINT)
        self.edit.returnPressed.connect(self.go)
        row.addWidget(self.kind)
        row.addWidget(self.edit, 1)
        layout.addLayout(row)
        button = QPushButton("اذهب")
        button.clicked.connect(self.go)
        layout.addWidget(button)
        self.error = QLabel()
        self.error.setStyleSheet(f"color: {MATCH_COLOR}")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        layout.addStretch()

    def focus(self):
        self.edit.setFocus()
        self.edit.selectAll()

    def go(self):
        try:
            target = self._mushaf.jump(self.kind.currentData(), self.edit.text())
        except ValueError as error:
            self.error.setText(str(error))
            return
        self.error.setText("")
        self.jumped.emit(target)


class ViewPanel(QWidget):
    """How the book is shown: one page or two, and how numbers are written."""

    spread_changed = Signal(bool)
    style_changed = Signal(str)

    STYLES = (("indic", "أرقام هندية (١٢٣)"), ("western", "أرقام غربية (123)"), ("words", "كلمات (الأول)"))

    def __init__(self, spread, style):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("العرض"))
        self.pages = QButtonGroup(self)
        self._page_buttons = {}
        for value, label in ((False, "صفحة واحدة"), (True, "صفحتان")):
            button = QRadioButton(label)
            self._page_buttons[value] = button
            self.pages.addButton(button)
            button.toggled.connect(lambda checked, value=value: checked and self.spread_changed.emit(value))
            layout.addWidget(button)
        layout.addSpacing(16)
        layout.addWidget(QLabel("الأرقام"))
        self.numbers = QButtonGroup(self)
        self._style_buttons = {}
        for value, label in self.STYLES:
            button = QRadioButton(label)
            self._style_buttons[value] = button
            self.numbers.addButton(button)
            button.toggled.connect(lambda checked, value=value: checked and self.style_changed.emit(value))
            layout.addWidget(button)
        layout.addStretch()
        self.show_state(spread, style)

    def show_state(self, spread, style):
        """Tick the buttons for the current state without announcing a change."""
        for blocked in (*self._page_buttons.values(), *self._style_buttons.values()):
            blocked.blockSignals(True)
        self._page_buttons[bool(spread)].setChecked(True)
        self._style_buttons[style].setChecked(True)
        for blocked in (*self._page_buttons.values(), *self._style_buttons.values()):
            blocked.blockSignals(False)


class SidePanel(QTabWidget):
    """Everything the reader can do besides turning pages, in one place."""

    def __init__(self, search, jump, index, tafsir, bookmarks, view):
        super().__init__()
        self.search, self.jump, self.index = search, jump, index
        self.tafsir, self.bookmarks, self.view = tafsir, bookmarks, view
        self.setElideMode(Qt.TextElideMode.ElideNone)
        self.addTab(search, "بحث")
        self.addTab(jump, "اذهب")
        self.addTab(index, "الفهرس")
        self.addTab(tafsir, "التفسير")
        self.addTab(bookmarks, "العلامات")
        self.addTab(view, "العرض")
