"""The window for making an audio preset: tick the settings to include and set their values. Qt only; the
presets themselves (what they hold, the file) are in audio_presets.py."""

from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QSpinBox, QVBoxLayout, QWidget,
)

from .audio_catalog import RECITERS, SPEED_PRESETS, STYLE_NAMES, parse_speed, speed_text
from .audio_presets import MAX_REPEATS
from .numbers import format_number


class _VerseBox(QWidget):
    """A chapter dropdown ('number - name') and a verse dropdown."""

    def __init__(self, mushaf, digits, chapter, verse):
        super().__init__()
        self._mushaf, self._digits = mushaf, digits
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.chapter, self.verse = QComboBox(), QComboBox()
        for number in range(1, 115):
            self.chapter.addItem(f"{format_number(number, digits)} - {mushaf.chapter_name(number)}", number)
        self.chapter.setCurrentIndex(chapter - 1)
        self._fill_verses(verse)
        self.chapter.currentIndexChanged.connect(lambda *_: self._fill_verses(1))
        row.addWidget(self.chapter, 3)
        row.addWidget(self.verse, 1)

    def _fill_verses(self, selected):
        self.verse.clear()
        for number in range(1, self._mushaf.verse_count(self.chapter.currentData()) + 1):
            self.verse.addItem(format_number(number, self._digits), number)
        self.verse.setCurrentIndex(min(selected, self.verse.count()) - 1)

    def value(self):
        return [self.chapter.currentData(), self.verse.currentData()]


class PresetDialog(QDialog):
    """`current` holds the panel's present values (from, to, reciter, style, speed, verse_repeats,
    passage_repeats), which fill the editors; `found` maps reciters on disk to their styles."""

    def __init__(self, mushaf, digits, found, current, existing_names, parent=None):
        super().__init__(parent)
        self.setWindowTitle("مقطع صوتي جديد")
        self.setMinimumWidth(460)
        self._existing = set(existing_names)
        self._boxes = {}  # setting -> its tick box
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("اسم المقطع المحفوظ"))
        self.name = QLineEdit()
        layout.addWidget(self.name)
        layout.addWidget(QLabel("اختر الإعدادات التي يحفظها، وقيمة كل منها. ما لا تختاره يبقى كما هو عند تطبيقه."))
        grid = QGridLayout()
        layout.addLayout(grid)

        first, last = current["from"], current["to"]
        self.first = _VerseBox(mushaf, digits(), *first)
        self.last = _VerseBox(mushaf, digits(), *last)
        self.reciter, self.style = QComboBox(), QComboBox()
        for item in RECITERS:
            if item.key in found:
                self.reciter.addItem(item.name_ar, item.key)
        self.reciter.setCurrentIndex(max(0, self.reciter.findData(current["reciter"])))
        self._found = found
        self.reciter.currentIndexChanged.connect(self._fill_styles)
        self._fill_styles(wanted=current["style"])
        self.speed = QComboBox()
        self.speed.setEditable(True)
        self.speed.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        for value in SPEED_PRESETS:
            self.speed.addItem(speed_text(value), value)
        self.speed.setCurrentText(speed_text(current["speed"]))
        self.verse_repeats, self.passage_repeats = QSpinBox(), QSpinBox()
        for box, value in ((self.verse_repeats, current["verse_repeats"]), (self.passage_repeats, current["passage_repeats"])):
            box.setRange(1, MAX_REPEATS)
            box.setValue(value)

        rows = (
            ("from", "من", self.first), ("to", "إلى", self.last), ("reciter", "المقرئ", self.reciter),
            ("style", "الرواية", self.style), ("speed", "السرعة", self.speed),
            ("verse_repeats", "تكرار كل آية", self.verse_repeats),
            ("passage_repeats", "تكرار المقطع", self.passage_repeats),
        )
        for row, (key, label, editor) in enumerate(rows):
            tick = QCheckBox(label)
            usable = bool(found) or key not in ("reciter", "style")
            tick.setChecked(usable)
            tick.setEnabled(usable)
            editor.setEnabled(usable)
            tick.toggled.connect(editor.setEnabled)
            grid.addWidget(tick, row, 0)
            grid.addWidget(editor, row, 1)
            self._boxes[key] = tick
        grid.setColumnStretch(1, 1)
        if not found:
            layout.addWidget(QLabel("لا توجد تسجيلات منزّلة، فلا يمكن حفظ المقرئ والرواية."))

        self.error = QLabel()
        self.error.setStyleSheet("color: #e0483f")
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("حفظ")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("إلغاء")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._result = None

    def _fill_styles(self, *_, wanted=None):
        wanted = wanted or self.style.currentData()
        self.style.clear()
        for style in self._found.get(self.reciter.currentData(), ()):
            self.style.addItem(STYLE_NAMES[style], style)
        self.style.setCurrentIndex(max(0, self.style.findData(wanted)))

    def _accept(self):
        ticked = {key for key, tick in self._boxes.items() if tick.isChecked()}
        name = self.name.text().strip()
        if not name:
            self.error.setText("اكتب اسماً للمقطع")
            return
        if not ticked:
            self.error.setText("اختر إعداداً واحداً على الأقل")
            return
        preset = {"name": name}
        if "from" in ticked:
            preset["from"] = self.first.value()
        if "to" in ticked:
            preset["to"] = self.last.value()
        if {"from", "to"} <= ticked and preset["to"] < preset["from"]:
            self.error.setText("نهاية المقطع قبل بدايته")
            return
        if "reciter" in ticked:
            preset["reciter"] = self.reciter.currentData()
        if "style" in ticked:
            preset["style"] = self.style.currentData()
        if "speed" in ticked:
            try:
                preset["speed"] = parse_speed(self.speed.currentText())
            except ValueError as error:
                self.error.setText(str(error))
                return
        if "verse_repeats" in ticked:
            preset["verse_repeats"] = self.verse_repeats.value()
        if "passage_repeats" in ticked:
            preset["passage_repeats"] = self.passage_repeats.value()
        if name in self._existing:
            answer = QMessageBox.question(self, "الاسم مستخدم", f"يوجد مقطع محفوظ باسم «{name}». هل تستبدله؟")
            if answer != QMessageBox.StandardButton.Yes:
                return
        self._result = preset
        self.accept()

    def preset(self):
        """The preset made, or None if the window was cancelled."""
        return self._result
