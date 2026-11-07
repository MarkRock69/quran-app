"""The little icons of the playback bar, drawn here so they look the same on every system theme."""

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

SIZE = 28


def make_icon(name, color):
    """name: 'left', 'right' (arrows), 'play', 'pause' or 'stop'."""
    pixmap = QPixmap(SIZE, SIZE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(color)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    if name == "play":
        painter.drawPolygon(QPolygonF([QPointF(8, 5), QPointF(23, 14), QPointF(8, 23)]))
    elif name == "pause":
        painter.drawRect(QRectF(7, 5, 5, 18))
        painter.drawRect(QRectF(16, 5, 5, 18))
    elif name == "stop":
        painter.drawRect(QRectF(6, 6, 16, 16))
    else:  # an arrow: a shaft with a head
        pen = QPen(color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        tip, tail, sign = (4, 24, 1) if name == "left" else (24, 4, -1)
        painter.drawLine(QPointF(tail, 14), QPointF(tip, 14))
        painter.drawLine(QPointF(tip, 14), QPointF(tip + 8 * sign, 6))
        painter.drawLine(QPointF(tip, 14), QPointF(tip + 8 * sign, 22))
    painter.end()
    return QIcon(pixmap)
