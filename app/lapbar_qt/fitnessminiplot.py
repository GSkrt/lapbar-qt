"""Compact fitness/fatigue/form preview for the main window, matching Panel.qml's FitnessPlot.qml: fitness
and fatigue as lines on top, form as green/orange bars underneath (tomorrow's as an outline), a small fixed
height, no zoom/pan (it's a static preview -- docs/help.md describes it as part of the popup itself: "a
plain-words status and the plot"). The full, interactive, linked-crosshair version with min/max and a
Load row lives in fitnesschartwindow.py, behind the "Open chart" button next to this.
"""
from datetime import datetime, timezone

import pyqtgraph as pg
from PyQt6.QtWidgets import QVBoxLayout, QWidget

pg.setConfigOptions(antialias=True)

FITNESS_BLUE = "#3987e5"
FATIGUE_ORANGE = "#d95926"
FRESH_GREEN = (76, 175, 80)
TIRED_ORANGE = (255, 138, 76)


def _epoch(iso_date: str) -> float:
    y, m, d = (int(p) for p in iso_date.split("-"))
    return datetime(y, m, d, tzinfo=timezone.utc).timestamp()


class FitnessMiniPlot(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(160)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._plot_widget = pg.GraphicsLayoutWidget()
        layout.addWidget(self._plot_widget)

    def update_fitness(self, fitness: dict):
        self._plot_widget.clear()
        days = (fitness or {}).get("days") or []
        if len(days) < 2:
            return
        x = [_epoch(d["date"]) for d in days]
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
