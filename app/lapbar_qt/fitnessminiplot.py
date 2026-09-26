"""Compact fitness/fatigue/form preview for the main window, matching Panel.qml's FitnessPlot.qml: fitness
and fatigue as lines on top, form as green/orange bars underneath (tomorrow's as an outline), no zoom/pan
(it's a static preview -- docs/help.md describes it as part of the popup itself: "a plain-words status and
the plot. Hover any day."). The full, interactive, linked-crosshair version with min/max and a Load row
lives in fitnesschartwindow.py, behind the "Open chart" button next to this.

Sized to the window, not fixed: a minimum height keeps it legible, but an Expanding size policy plus a
resizeEvent that rescales the axis tick font with the widget's actual height means it genuinely grows or
shrinks along with the main window instead of leaving dead space (or clipping) at a fixed size.
"""
import bisect
from datetime import datetime, timezone

import pyqtgraph as pg
from PyQt6.QtCore import QEvent, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

MIN_HEIGHT = 90


def _tick_font_for(row_height: float) -> QFont:
    """Scaled to one subplot's own share of the widget's height (there are two, stacked), not the whole
    widget -- using the raw widget height saturated at the font ceiling almost immediately, since even a
    fairly small widget is much taller than a legible tick label."""
    font = QFont()
    font.setPointSize(max(6, min(14, round(row_height * 0.05))))
    return font


pg.setConfigOptions(antialias=True)

FITNESS_BLUE = "#3987e5"
FATIGUE_ORANGE = "#d95926"
FRESH_GREEN = (76, 175, 80)
TIRED_ORANGE = (255, 138, 76)


def _epoch(iso_date: str) -> float:
    y, m, d = (int(p) for p in iso_date.split("-"))
    return datetime(y, m, d, tzinfo=timezone.utc).timestamp()


class FitnessMiniPlot(QWidget):
    dayHovered = pyqtSignal(object)  # the hovered day's dict, or None once the mouse leaves the plot

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(MIN_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._plot_widget = pg.GraphicsLayoutWidget()
        self._plot_widget.installEventFilter(self)  # Leave doesn't reach FitnessMiniPlot's own leaveEvent,
        # since the GraphicsLayoutWidget (a QGraphicsView) is the widget actually under the mouse
        layout.addWidget(self._plot_widget)
        self._x: list[float] = []
        self._days: list[dict] = []
        self._plots: list = []
        self._vlines: list = []

    def update_fitness(self, fitness: dict):
        self._plot_widget.clear()
        self._plots = []
        self._vlines = []
        days = (fitness or {}).get("days") or []
        self._days = days
        if len(days) < 2:
            self._x = []
            return
        x = [_epoch(d["date"]) for d in days]
        self._x = x
        width = (x[1] - x[0]) * 0.8

        top = self._plot_widget.addPlot(row=0, col=0)
        top.hideAxis("bottom")
        top.showGrid(x=True, y=True, alpha=0.15)
        top.getViewBox().setMouseEnabled(x=False, y=False)
        top.hideButtons()
        fitness_curve = top.plot(x, [d["fitness"] for d in days], pen=pg.mkPen(FITNESS_BLUE, width=2))
        fatigue_curve = top.plot(x, [d["fatigue"] for d in days], pen=pg.mkPen(FATIGUE_ORANGE, width=2))
        for curve in (fitness_curve, fatigue_curve):
            curve.setDownsampling(auto=True, method="peak")
            curve.setClipToView(True)

        middle = self._plot_widget.addPlot(row=1, col=0, axisItems={"bottom": pg.DateAxisItem()})
        middle.showGrid(x=True, y=True, alpha=0.15)
        middle.setXLink(top)
        middle.getViewBox().setMouseEnabled(x=False, y=False)
        middle.hideButtons()

        forms = [d["form"] for d in days]
        pos = [(bx, by) for bx, by in zip(x, forms) if by >= 0]
        neg = [(bx, by) for bx, by in zip(x, forms) if by < 0]
        if pos:
            px_, py_ = zip(*pos)
            middle.addItem(pg.BarGraphItem(x=list(px_), height=list(py_), width=width, brush=FRESH_GREEN, pen=None))
        if neg:
            nx, ny = zip(*neg)
            middle.addItem(pg.BarGraphItem(x=list(nx), height=list(ny), width=width, brush=TIRED_ORANGE, pen=None))
        tomorrow = fitness.get("tomorrow")
        if tomorrow:
            tx, ty = _epoch(tomorrow["date"]), tomorrow["form"]
            color = FRESH_GREEN if ty >= 0 else TIRED_ORANGE
            middle.addItem(pg.BarGraphItem(x=[tx], height=[ty], width=width, brush=None, pen=pg.mkPen(color, width=2)))

        for plot in (top, middle):
            vline = pg.InfiniteLine(angle=90, movable=False)
            vline.hide()
            plot.addItem(vline, ignoreBounds=True)
            self._plots.append(plot)
            self._vlines.append(vline)
        self._plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)
        self._apply_tick_font()

    def _apply_tick_font(self):
        if not self._plots:
            return
        font = _tick_font_for(self.height() / len(self._plots))
        for plot in self._plots:
            plot.getAxis("left").setStyle(tickFont=font)
            plot.getAxis("bottom").setStyle(tickFont=font)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_tick_font()

    def leaveEvent(self, event):
        for vline in self._vlines:
            vline.hide()
        self.dayHovered.emit(None)
        super().leaveEvent(event)

    def _on_mouse_moved(self, pos):
        for plot in self._plots:
            if plot.sceneBoundingRect().contains(pos):
                x_val = plot.vb.mapSceneToView(pos).x()
                for vline in self._vlines:
                    vline.setPos(x_val)
                    vline.show()
                self._emit_hovered(x_val)
                return
        for vline in self._vlines:
            vline.hide()
        self.dayHovered.emit(None)

    def _emit_hovered(self, x_val: float):
        if not self._x:
            return
        idx = bisect.bisect_left(self._x, x_val)
        idx = max(0, min(idx, len(self._x) - 1))
        if idx > 0 and abs(self._x[idx - 1] - x_val) < abs(self._x[idx] - x_val):
            idx -= 1
        self.dayHovered.emit(self._days[idx])
