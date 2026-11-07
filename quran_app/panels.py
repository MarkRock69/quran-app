"""The side panel: search, go to, bookmarks, and how the book is shown. Qt only; the logic is in search.py,
navigation.py and bookmarks.py, which are tested without a window."""

from html import escape

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPalette, QTextDocument
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
    QRadioButton, QSpinBox, QStyle, QStyledItemDelegate, QTabWidget, QTextBrowser, QVBoxLayout, QHBoxLayout,
    QWidget,
)

from .audio_catalog import (
    RECITERS, SPEED_PRESETS, STYLE_NAMES, available, build_queue, parse_speed, speed_text,
)
from .index_lists import Band, ChapterRow, RubRow, revelation_text, verse_count_text
from .navigation import HINT, KINDS, normalize_digits
from .passages import PASSAGE_KINDS
from .numbers import AUTO, format_number
from .page_header import header_for
from .settings import order_tabs
from .tafsir import order_sources
from .search import ALL_WORDS, ANY_WORD, PHRASE, SearchIndex, SearchOptions

MATCH_COLOR = "#e0483f"  # readable on light and dark
MUTED_COLOR = "#8a8a8a"
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


ACCENT = QColor("#3f8f74")  # the circles of the rub' list, readable on light and dark


def mix(first, second, amount):
    """`first` with `amount` (0 to 1) of `second` blended in."""
    return QColor(*(round(a * (1 - amount) + b * amount) for a, b in (
        (first.red(), second.red()), (first.green(), second.green()), (first.blue(), second.blue()))))


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
        base, text = option.palette.color(QPalette.ColorRole.Base), option.palette.color(QPalette.ColorRole.Text)
        self._ink, self._muted = text, mix(base, text, 0.62)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.fillRect(rect, mix(base, text, 0.12) if isinstance(row, Band) else base)
        if selected:
            painter.fillRect(rect, QColor(70, 130, 220, 50))
        right, left = rect.right() - 16, rect.left() + 16
        number = lambda n: format_number(n, digits)  # noqa: E731
        page = row.page
        painter.setPen(self._muted)
        painter.setFont(self._font(16, text=False))
        painter.drawText(QRectF(left, rect.top(), 70, rect.height()),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter,
                         number(page))
        if isinstance(row, Band):
            painter.setPen(self._ink)
            painter.setFont(self._font(20, bold=True))
            self._text(painter, QRectF(left + 80, rect.top(), right - left - 80, rect.height()),
                       f"الجزء {number(row.juz)}")
        elif isinstance(row, ChapterRow):
            painter.setPen(self._muted)
            painter.setFont(self._font(34, text=False))
            self._text(painter, QRectF(right - 56, rect.top(), 56, rect.height()), number(row.chapter))
            body = QRectF(left + 80, rect.top(), right - 70 - left - 80, rect.height())
            self._two_lines(painter, body, f"سُورَةُ {row.name}",
                            f"{revelation_text(row.meccan)} - {verse_count_text(row.verse_count, digits)}")
        else:
            self._pie(painter, QRectF(right - 54, rect.center().y() - 27, 54, 54), row, digits, base)
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
        painter.setPen(self._ink)
        painter.setFont(self._font(21, bold=True))
        self._text(painter, QRectF(body.left(), body.top() + 6, body.width(), half - 2), first)
        painter.setPen(self._muted)
        painter.setFont(self._font(17))
        self._text(painter, QRectF(body.left(), body.center().y() - 2, body.width(), half - 2), second)

    def _pie(self, painter, rect, row, digits, base):
        """A full circle with the hizb number at the start of a hizb; otherwise the quarters gone by."""
        painter.setPen(Qt.PenStyle.NoPen)
        if row.position == 1:
            painter.setBrush(ACCENT)
            painter.drawEllipse(rect)
            painter.setPen(QColor("white"))
            painter.setFont(self._font(20, text=False))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, format_number(row.hizb, digits))
            return
        painter.setBrush(mix(base, ACCENT, 0.3))
        painter.drawEllipse(rect)
        painter.setBrush(ACCENT)
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

    order_changed = Signal(list)  # the source keys, in the order the reader chose

    def __init__(self, mushaf, family, digits, order=None):
        super().__init__()
        self._mushaf, self._family, self._digits = mushaf, family, digits
        self._verse = None
        self._sources = order_sources(mushaf.tafsir_sources(), order)
        self._by_key = {source.key: source for source in self._sources}
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
            item = QListWidgetItem(source.title)
            item.setData(TARGET_ROLE, source.key)
            self.names.addItem(item)
        self.names.setCurrentRow(0)
        self.names.setDragDropMode(QListWidget.DragDropMode.InternalMove)  # drag to rearrange
        self.names.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.names.currentRowChanged.connect(lambda _: self._show())
        self.names.model().rowsMoved.connect(self._moved)
        hint = QLabel("اسحب المصادر لإعادة ترتيبها")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {MUTED_COLOR}")
        side = QVBoxLayout()
        side.addWidget(self.names, 1)
        side.addWidget(hint)
        layout.addLayout(column, 1)
        layout.addLayout(side)  # in the right-to-left window this is the right-hand column

    def _keys(self):
        return [self.names.item(row).data(TARGET_ROLE) for row in range(self.names.count())]

    def _moved(self, *_):
        keys = self._keys()
        self._sources = [self._by_key[key] for key in keys]
        self.order_changed.emit(keys)

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
        item = self.names.currentItem() or self.names.item(0)
        source = self._by_key[item.data(TARGET_ROLE)]
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


class AudioPanel(QWidget):
    """Choose a reciter, a style and a range of verses, and play it."""

    play_requested = Signal(list)  # a list of audio_catalog.QueueItem
    speed_changed = Signal(float)
    MAX_REPEATS = 99
    MAX_QUEUE = 20000

    def __init__(self, mushaf, audio_root, context, digits=lambda: "indic"):
        """`context()` gives the reader's position: {'verse': (c, v) or None, 'page': n}."""
        super().__init__()
        self._mushaf, self._root, self._context, self._digits = mushaf, audio_root, context, digits
        layout = QVBoxLayout(self)
        self.note = QLabel()
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        row = QHBoxLayout()
        self.reciter = QComboBox()
        self.style = QComboBox()
        self.reciter.currentIndexChanged.connect(self._fill_styles)
        row.addWidget(self.reciter, 1)
        row.addWidget(self.style)
        layout.addLayout(row)

        layout.addWidget(QLabel("المقطع المراد تشغيله"))
        self.from_chapter, self.from_verse = self._boundary(layout, "من")
        self.to_chapter, self.to_verse = self._boundary(layout, "إلى")
        self.from_chapter.currentIndexChanged.connect(lambda *_: self._chapter_changed(True))
        self.to_chapter.currentIndexChanged.connect(lambda *_: self._chapter_changed(False))
        self.from_verse.currentIndexChanged.connect(self._keep_order)
        self._fill_verses(self.from_verse, 1, 1)
        self._fill_verses(self.to_verse, 1, 1)

        repeats = QHBoxLayout()
        self.verse_repeats = QLineEdit("1")
        self.passage_repeats = QLineEdit("1")
        for label, edit in (("تكرار كل آية", self.verse_repeats), ("تكرار المقطع", self.passage_repeats)):
            edit.setMaximumWidth(60)
            edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            edit.returnPressed.connect(self.play)
            repeats.addWidget(QLabel(label))
            repeats.addWidget(edit)
        repeats.addStretch()
        layout.addLayout(repeats)

        speed = QHBoxLayout()
        self.speed = QComboBox()
        self.speed.setEditable(True)
        self.speed.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.speed.setMaximumWidth(90)
        for value in SPEED_PRESETS:
            self.speed.addItem(speed_text(value), value)
        self.speed.setCurrentIndex(self.speed.findData(1))
        self._speed = 1.0
        self.speed.activated.connect(lambda *_: self._apply_speed())
        self.speed.lineEdit().editingFinished.connect(self._apply_speed)
        speed.addWidget(QLabel("سرعة التشغيل"))
        speed.addWidget(self.speed)
        speed.addStretch()
        layout.addLayout(speed)

        presets = QVBoxLayout()
        for label, preset in (
            ("الآية المحددة", self._selected_verse),
            ("من الآية المحددة إلى آخر السورة", self._selected_to_chapter_end),
            ("الصفحة الحالية", self._current_page),
            ("السورة الحالية", self._current_chapter),
            ("الجزء الحالي", self._current_juz),
        ):
            button = QPushButton(label)
            button.clicked.connect(preset)
            presets.addWidget(button)
        layout.addLayout(presets)

        self.basmala = QCheckBox("تشغيل البسملة في أول كل سورة")
        self.basmala.setChecked(True)
        self.follow = QCheckBox("متابعة الصفحة أثناء التشغيل")
        self.follow.setChecked(True)
        layout.addWidget(self.basmala)
        layout.addWidget(self.follow)
        button = QPushButton("تشغيل")
        button.clicked.connect(self.play)
        layout.addWidget(button)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color: {MATCH_COLOR}")
        layout.addWidget(self.status)
        layout.addStretch()
        self._fill_chapters()
        self.rescan()

    def _boundary(self, layout, label):
        row = QHBoxLayout()
        chapter, verse = QComboBox(), QComboBox()
        row.addWidget(QLabel(label))
        row.addWidget(chapter, 3)
        row.addWidget(verse, 1)
        layout.addLayout(row)
        return chapter, verse

    # ------------------------------------------------------------ dropdowns

    def _fill_chapters(self):
        """Fill (or relabel, after a change of digits) the chapter dropdowns as 'number - name'."""
        digits = self._digits()
        for box in (self.from_chapter, self.to_chapter):
            current = box.currentData() or 1
            box.blockSignals(True)
            box.clear()
            for chapter in range(1, 115):
                box.addItem(f"{format_number(chapter, digits)} - {self._mushaf.chapter_name(chapter)}", chapter)
            box.setCurrentIndex(current - 1)
            box.blockSignals(False)

    def _fill_verses(self, box, chapter, selected):
        digits = self._digits()
        box.blockSignals(True)
        box.clear()
        for verse in range(1, self._mushaf.verse_count(chapter) + 1):
            box.addItem(format_number(verse, digits), verse)
        box.setCurrentIndex(min(selected, box.count()) - 1)
        box.blockSignals(False)

    def refresh_numbers(self):
        for chapter_box, verse_box in ((self.from_chapter, self.from_verse), (self.to_chapter, self.to_verse)):
            verse = verse_box.currentData() or 1
            self._fill_verses(verse_box, chapter_box.currentData(), verse)
        self._fill_chapters()

    def _start(self):
        return (self.from_chapter.currentData(), self.from_verse.currentData())

    def _end(self):
        return (self.to_chapter.currentData(), self.to_verse.currentData())

    def _chapter_changed(self, is_from):
        chapter_box, verse_box = (self.from_chapter, self.from_verse) if is_from else (self.to_chapter, self.to_verse)
        self._fill_verses(verse_box, chapter_box.currentData(), 1)
        if is_from and self._end() < self._start():
            self._set_end(*self._start())
        self._keep_order()

    def _keep_order(self, *_):
        """The end of the passage is never before its start."""
        if self._end() < self._start():
            self._set_end(*self._start())

    def _set_end(self, chapter, verse):
        self.to_chapter.blockSignals(True)
        self.to_chapter.setCurrentIndex(chapter - 1)
        self.to_chapter.blockSignals(False)
        self._fill_verses(self.to_verse, chapter, verse)

    def _set_start(self, chapter, verse):
        self.from_chapter.blockSignals(True)
        self.from_chapter.setCurrentIndex(chapter - 1)
        self.from_chapter.blockSignals(False)
        self._fill_verses(self.from_verse, chapter, verse)

    # ------------------------------------------------------------ recordings

    def rescan(self):
        """Look at which recordings are on disk (the reader calls this when the tab is shown)."""
        found = available(self._root)
        current = self.reciter.currentData()
        self.reciter.blockSignals(True)
        self.reciter.clear()
        for item in RECITERS:
            if item.key in found:
                self.reciter.addItem(item.name_ar, item.key)
        index = self.reciter.findData(current)
        self.reciter.setCurrentIndex(max(0, index))
        self.reciter.blockSignals(False)
        self._found = found
        self._fill_styles()
        self.note.setText("" if found else "لم تُنزَّل التسجيلات بعد. شغّل: python3 tools/fetch_audio.py")

    def showEvent(self, event):
        self.rescan()
        super().showEvent(event)

    def _fill_styles(self, *_):
        current = self.style.currentData()
        self.style.clear()
        styles = self._found.get(self.reciter.currentData(), ())
        for style in styles:
            self.style.addItem(STYLE_NAMES[style], style)
        self.style.setCurrentIndex(max(0, self.style.findData(current)))
        self.style.setVisible(len(styles) > 1)  # a reciter with one style (Ali Jabir) needs no choice

    # ------------------------------------------------------------ presets

    def _set(self, kind, first, last=""):
        passage = self._mushaf.passage(kind, first, last)
        self._set_start(*passage.verses[0])
        self._set_end(*passage.verses[-1])
        self.status.setText("")

    def _selected_verse(self):
        verse = self._context()["verse"]
        if verse:
            self._set("verse", f"{verse[0]}:{verse[1]}")
        else:
            self.status.setText("حدّد آية في الصفحة أولاً (بالضغط عليها)")

    def _selected_to_chapter_end(self):
        verse = self._context()["verse"]
        if not verse:
            self.status.setText("حدّد آية في الصفحة أولاً (بالضغط عليها)")
            return
        chapter = verse[0]
        count = self._mushaf.passage("chapter", str(chapter)).verses[-1][1]
        self._set("verse", f"{chapter}:{verse[1]}", f"{chapter}:{count}")

    def _current_page(self):
        self._set("page", str(self._context()["page"]))

    def _current_chapter(self):
        self._set("chapter", str(self._mushaf.first_verse_of_page(self._context()["page"])[0]))

    def _current_juz(self):
        self._set("juz", str(self._mushaf.page_info(self._context()["page"]).juz))

    # ------------------------------------------------------------ playing

    def set_speed(self, value):
        """Show a remembered speed (the reader tells the player itself)."""
        self._speed = value
        self.speed.setCurrentText(speed_text(value))

    def _apply_speed(self):
        try:
            value = parse_speed(self.speed.currentText())
        except ValueError as error:
            self.status.setText(str(error))
            self.speed.setCurrentText(speed_text(self._speed))
            return
        self.speed.setCurrentText(speed_text(value))
        if value != self._speed:
            self._speed = value
            self.speed_changed.emit(value)
        self.status.setText("")

    def _repeats(self, edit, what):
        try:
            value = int(normalize_digits(edit.text().strip()))
        except ValueError:
            value = 0
        if not 1 <= value <= self.MAX_REPEATS:
            self.status.setText(f"{what}: أدخل عدداً من ١ إلى {format_number(self.MAX_REPEATS, self._digits())}")
            return None
        return value

    def play(self):
        reciter, style = self.reciter.currentData(), self.style.currentData()
        if reciter is None or style is None:
            self.status.setText("لا توجد تسجيلات. شغّل: python3 tools/fetch_audio.py")
            return
        each = self._repeats(self.verse_repeats, "تكرار كل آية")
        whole = self._repeats(self.passage_repeats, "تكرار المقطع") if each else None
        if not each or not whole:
            return
        (c1, v1), (c2, v2) = self._start(), self._end()
        try:
            passage = self._mushaf.passage("verse", f"{c1}:{v1}", f"{c2}:{v2}")
        except ValueError as error:
            self.status.setText(str(error))
            return
        if len(passage.verses) * each * whole > self.MAX_QUEUE:
            self.status.setText("المقطع مع التكرار أكبر من أن يُشغَّل دفعة واحدة، قلّل التكرار")
            return
        queue, missing = build_queue(self._root, reciter, style, passage.verses, self.basmala.isChecked(), each, whole)
        if not queue:
            self.status.setText("لا توجد ملفات صوتية لهذا المقطع")
            return
        self.status.setText(f"{len(missing)} آية بلا ملف صوتي، وقد تُخطّيت" if missing else "")
        self.play_requested.emit(queue)


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
    theme_changed = Signal(str)
    part_changed = Signal(str, str)  # which number (chapter, juz, page), its style or 'auto'

    STYLES = (("indic", "أرقام هندية (١٢٣)"), ("western", "أرقام غربية (123)"), ("words", "كلمات (الأول)"))

    THEMES = (("light", "فاتح"), ("dark", "داكن"))

    PARTS = (
        ("chapter", "رقم السورة", True),
        ("juz", "رقم الجزء والحزب", True),
        ("page", "رقم الصفحة", False),  # ordinal words stop at 199
    )

    def __init__(self, spread, style, theme, parts=None):
        super().__init__()
        parts = parts or {}
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
        layout.addSpacing(16)
        layout.addWidget(QLabel("أرقام مخصصة"))
        self.part_boxes = {}
        for part, label, words_ok in self.PARTS:
            row = QHBoxLayout()
            box = QComboBox()
            box.addItem("مثل الأرقام عامةً", AUTO)
            for value, name in self.STYLES:
                if words_ok or value != "words":
                    box.addItem(name, value)
            box.setCurrentIndex(max(0, box.findData(parts.get(part, AUTO))))
            box.currentIndexChanged.connect(lambda _, part=part, box=box: self.part_changed.emit(part, box.currentData()))
            row.addWidget(QLabel(label))
            row.addWidget(box, 1)
            layout.addLayout(row)
            self.part_boxes[part] = box
        layout.addSpacing(16)
        layout.addWidget(QLabel("لون الصفحات"))
        self.colors = QButtonGroup(self)
        self._theme_buttons = {}
        for value, label in self.THEMES:
            button = QRadioButton(label)
            self._theme_buttons[value] = button
            self.colors.addButton(button)
            button.toggled.connect(lambda checked, value=value: checked and self.theme_changed.emit(value))
            layout.addWidget(button)
        layout.addStretch()
        self.show_state(spread, style, theme)

    def show_state(self, spread, style, theme):
        """Tick the buttons for the current state without announcing a change."""
        buttons = (*self._page_buttons.values(), *self._style_buttons.values(), *self._theme_buttons.values())
        for blocked in buttons:
            blocked.blockSignals(True)
        self._page_buttons[bool(spread)].setChecked(True)
        self._style_buttons[style].setChecked(True)
        self._theme_buttons[theme].setChecked(True)
        for blocked in buttons:
            blocked.blockSignals(False)


class SidePanel(QTabWidget):
    """Everything the reader can do besides turning pages, in one place."""

    order_changed = Signal(list)  # the tab keys, left to right as stored

    def __init__(self, search, jump, index, tafsir, audio, bookmarks, view, order=None):
        super().__init__()
        self.search, self.jump, self.index = search, jump, index
        self.tafsir, self.bookmarks, self.view = tafsir, bookmarks, view
        self.setElideMode(Qt.TextElideMode.ElideNone)
        self.tabBar().setStyleSheet("QTabBar::tab { padding: 6px 8px; }")  # seven tabs have to fit
        tabs = {"search": (search, "بحث"), "jump": (jump, "اذهب"), "index": (index, "الفهرس"),
                "tafsir": (tafsir, "التفسير"), "audio": (audio, "الصوت"), "bookmarks": (bookmarks, "العلامات"),
                "view": (view, "العرض")}
        for key in order_tabs(order, tabs):
            widget, title = tabs[key]
            self.addTab(widget, title)
            widget.setProperty("tab_key", key)
        self.tabBar().setMovable(True)  # drag a tab to put it elsewhere
        self.tabBar().tabMoved.connect(lambda *_: self.order_changed.emit(self.order()))

    def order(self):
        return [self.widget(i).property("tab_key") for i in range(self.count())]
