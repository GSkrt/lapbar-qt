"""Simple polyline preview of the latest ride's route, matching Panel.qml's own route trace: an accent-
colored line with rounded joins, a green start marker and a smaller orange finish marker. `latest["route"]`
is already privacy-normalized to a 0..1 square by providers/strava.py's normalize_route() -- centred,
aspect-ratio preserved, no real coordinates -- so this widget never sees or needs real GPS data.
"""
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget

ACCENT = QColor("#7aa2f7")
START_GREEN = QColor("#4caf50")
FINISH_ORANGE = QColor("#fc4c02")  # Strava's own brand orange, same as Panel.qml's stravaOrange
INSET = 10


class RoutePreview(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(170)
        self._route: list[list[float]] = []

    def set_route(self, route: list[list[float]] | None):
        self._route = route or []
        self.update()

    def paintEvent(self, event):  # noqa: ARG002 - Qt's own signature
        if len(self._route) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        side = min(self.width(), self.height())
        x0 = (self.width() - side) / 2
        y0 = (self.height() - side) / 2
        span = side - 2 * INSET

        def to_point(p: list[float]) -> QPointF:
            return QPointF(x0 + INSET + p[0] * span, y0 + INSET + p[1] * span)

        path = QPainterPath()
        path.moveTo(to_point(self._route[0]))
        for p in self._route[1:]:
            path.lineTo(to_point(p))
        pen = QPen(ACCENT, 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(START_GREEN))
        painter.drawEllipse(to_point(self._route[0]), 7.5, 7.5)
        painter.setBrush(QBrush(FINISH_ORANGE))
        painter.drawEllipse(to_point(self._route[-1]), 4.5, 4.5)
