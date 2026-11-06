"""The side panel and the jump box: search, bookmarks, "go to". Qt only; the logic is in search.py,
navigation.py and bookmarks.py, which are tested without a window."""

from html import escape

from PySide6.QtCore import QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QTextDocument
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QSpinBox, QStyle, QStyledItemDelegate, QTabWidget, QVBoxLayout, QHBoxLayout, QWidget,
)

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


class BookmarksPanel(QListWidget):
    """The bookmarked pages. Enter or a click goes there; Delete removes the bookmark."""

    chosen = Signal(int)  # page

    def __init__(self, bookmarks, mushaf, digits):
        super().__init__()
        self._bookmarks, self._mushaf, self._digits = bookmarks, mushaf, digits
        self.itemActivated.connect(lambda item: self.chosen.emit(item.data(TARGET_ROLE)))
        self.itemClicked.connect(lambda item: self.chosen.emit(item.data(TARGET_ROLE)))
        self.refresh()

    def refresh(self):
        digits = self._digits()
        self.clear()
        for page in self._bookmarks.pages():
            info = self._mushaf.page_info(page)
            item = QListWidgetItem(
                f"صفحة {format_number(page, digits)} — {self._mushaf.chapter_name(info.chapter)}"
                f" — {header_for(info, '', digits).right.split('،')[0]}"
            )
            item.setData(TARGET_ROLE, page)
            self.addItem(item)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.currentItem() is not None:
            self._bookmarks.remove(self.currentItem().data(TARGET_ROLE))
            self.refresh()
        else:
            super().keyPressEvent(event)


class SidePanel(QTabWidget):
    def __init__(self, search, bookmarks):
        super().__init__()
        self.search, self.bookmarks = search, bookmarks
        self.addTab(search, "بحث")
        self.addTab(bookmarks, "العلامات")


class JumpDialog(QDialog):
    """Go to a page, chapter, juz', hizb or rub' by number, or to a verse as 2:255."""

    last_kind = "page"

    def __init__(self, mushaf, parent=None):
        super().__init__(parent)
        self.setWindowTitle("اذهب إلى")
        self._mushaf = mushaf
        self.target = None
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.kind = QComboBox()
        for key, (_, _, name) in KINDS.items():
            self.kind.addItem(name, key)
        self.kind.setCurrentIndex(list(KINDS).index(JumpDialog.last_kind))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(HINT)
        row.addWidget(self.kind)
        row.addWidget(self.edit, 1)
        layout.addLayout(row)
        self.error = QLabel()
        self.error.setStyleSheet(f"color: {MATCH_COLOR}")
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("اذهب")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("إلغاء")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.resize(460, 120)

    def accept(self):
        JumpDialog.last_kind = self.kind.currentData()
        try:
            self.target = self._mushaf.jump(self.kind.currentData(), self.edit.text())
        except ValueError as error:
            self.error.setText(str(error))
            return
        super().accept()
