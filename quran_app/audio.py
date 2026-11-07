"""Playing a queue of verse recordings, one after the other. Qt Multimedia; the logic of what to play
is in audio_catalog.py and passages.py."""

from PySide6.QtCore import QObject, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer


class Player(QObject):
    verse_changed = Signal(int, int)  # chapter, verse number (0 = the basmala of the chapter)
    position_changed = Signal(int, int)  # item number (from 1), items in the queue
    state_changed = Signal(bool)  # True while playing
    finished = Signal()  # the queue ended, or was stopped

    def __init__(self):
        super().__init__()
        self._player = QMediaPlayer(self)
        self._output = QAudioOutput(self)
        self._player.setAudioOutput(self._output)
        self._player.mediaStatusChanged.connect(self._status)
        self._player.errorOccurred.connect(lambda *_: self.next())  # a file that will not play is skipped
        self._queue = []
        self._index = -1
        self.active = False

    def play_queue(self, queue):
        self._queue = list(queue)
        self.active = bool(self._queue)
        if self.active:
            self._go(0)

    def _go(self, index):
        if not 0 <= index < len(self._queue):
            self.stop()
            return
        self._index = index
        item = self._queue[index]
        self._player.setSource(QUrl.fromLocalFile(str(item.path)))
        self._player.play()
        self.state_changed.emit(True)
        self.verse_changed.emit(item.chapter, item.number)
        self.position_changed.emit(index + 1, len(self._queue))

    def next(self):
        if self.active:
            self._go(self._index + 1)

    def previous(self):
        if self.active:
            self._go(max(0, self._index - 1))

    def toggle(self):
        if not self.active:
            return
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
            self.state_changed.emit(False)
        else:
            self._player.play()
            self.state_changed.emit(True)

    def stop(self):
        self._player.stop()
        self.active = False
        self._queue, self._index = [], -1
        self.state_changed.emit(False)
        self.finished.emit()

    def _status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.next()
