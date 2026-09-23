"""Build-order step 8 (fitness chart): the same PyQtGraph approach as chartswindow.py -- linked plots, a
shared crosshair, downsampling on the line series -- fed summary["fitness"] instead of a ride's streams,
PLAN.md's "same charts window, fed the fitness doc". No separate fetch: the fitness series is already part
of the regular refresh (fetcher.fetch_summary()), so this window is built directly from the already-fetched
summary, no background thread needed.
"""
from datetime import datetime, timezone

import pyqtgraph as pg
from PyQt6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QVBoxLayout

pg.setConfigOptions(antialias=True)

FRESH_GREEN = (76, 175, 80)
TIRED_ORANGE = (255, 138, 76)


def _epoch(iso_date: str) -> float:
    y, m, d = (int(p) for p in iso_date.split("-"))
    return datetime(y, m, d, tzinfo=timezone.utc).timestamp()


class FitnessChartWindow(QDialog):
    def __init__(self, fitness: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fitness, fatigue and form")
        self.resize(760, 640)

        layout = QVBoxLayout(self)
        days = fitness.get("days") or []
        if not days:
            layout.addWidget(QLabel("Not enough history yet: a few weeks of activity are needed."))
            self._plots: list = []
            return

        x = [_epoch(d["date"]) for d in days]
        width = (x[1] - x[0]) * 0.8 if len(x) > 1 else 86400 * 0.8

        toggles_row = QHBoxLayout()
        layout.addLayout(toggles_row)

        plot_widget = pg.GraphicsLayoutWidget()
        layout.addWidget(plot_widget)

        top = plot_widget.addPlot(row=0, col=0, axisItems={"bottom": pg.DateAxisItem()})
        top.setLabel("left", "Fitness / Fatigue")
        top.showGrid(x=True, y=True, alpha=0.2)
        top.addLegend()
        fitness_curve = top.plot(x, [d["fitness"] for d in days], pen=pg.mkPen("#3987e5", width=2), name="Fitness")
        fatigue_curve = top.plot(x, [d["fatigue"] for d in days], pen=pg.mkPen("#d95926", width=2), name="Fatigue")
        for curve in (fitness_curve, fatigue_curve):
            curve.setDownsampling(auto=True, method="peak")
            curve.setClipToView(True)

        middle = plot_widget.addPlot(row=1, col=0, axisItems={"bottom": pg.DateAxisItem()})
        middle.setLabel("left", "Form")
        middle.showGrid(x=True, y=True, alpha=0.2)
        middle.setXLink(top)
        forms = [d["form"] for d in days]
        pos = [(bx, by) for bx, by in zip(x, forms) if by >= 0]
        neg = [(bx, by) for bx, by in zip(x, forms) if by < 0]
        if pos:
            px, py = zip(*pos)
            middle.addItem(pg.BarGraphItem(x=list(px), height=list(py), width=width, brush=FRESH_GREEN, pen=None))
        if neg:
            nx, ny = zip(*neg)
            middle.addItem(pg.BarGraphItem(x=list(nx), height=list(ny), width=width, brush=TIRED_ORANGE, pen=None))
        tomorrow = fitness.get("tomorrow")
        if tomorrow:
            tx, ty = _epoch(tomorrow["date"]), tomorrow["form"]
            color = FRESH_GREEN if ty >= 0 else TIRED_ORANGE
            middle.addItem(pg.BarGraphItem(x=[tx], height=[ty], width=width, brush=None, pen=pg.mkPen(color, width=2)))

        bottom = plot_widget.addPlot(row=2, col=0, axisItems={"bottom": pg.DateAxisItem()})
        bottom.setLabel("left", "Load")
        bottom.showGrid(x=True, y=True, alpha=0.2)
        bottom.setXLink(top)
        bottom.addItem(pg.BarGraphItem(x=x, height=[d["load"] for d in days], width=width, brush=(140, 140, 140)))

        # "Click a name to hide that measure" (docs/help.md): fitness/fatigue toggle their own curve since
        # both share the top plot; form/load toggle their whole row since each has one of its own.
        for label, target in (("Fitness", fitness_curve), ("Fatigue", fatigue_curve), ("Form", middle), ("Load", bottom)):
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            checkbox.toggled.connect(lambda checked, t=target: t.setVisible(checked))
            toggles_row.addWidget(checkbox)

        self._plots = [top, middle, bottom]
        self._vlines = []
        for plot in self._plots:
            vline = pg.InfiniteLine(angle=90, movable=False)
            plot.addItem(vline, ignoreBounds=True)
            self._vlines.append(vline)
        plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

    def _on_mouse_moved(self, pos):
        for plot in self._plots:
            if plot.sceneBoundingRect().contains(pos):
                x_val = plot.vb.mapSceneToView(pos).x()
                for vline in self._vlines:
                    vline.setPos(x_val)
                return
