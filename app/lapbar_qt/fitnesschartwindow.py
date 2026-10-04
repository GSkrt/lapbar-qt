"""Build-order step 8 (fitness chart): the same PyQtGraph approach as chartswindow.py -- linked plots, a
shared crosshair, downsampling on the line series -- fed summary["fitness"] instead of a ride's streams,
PLAN.md's "same charts window, fed the fitness doc". No separate fetch: the fitness series is already part
of the regular refresh (fetcher.fetch_summary()), so this window is built directly from the already-fetched
summary, no background thread needed.
"""
import bisect
from datetime import datetime, timezone

import pyqtgraph as pg
from PyQt6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import branding, chartlegend

pg.setConfigOptions(antialias=True)

FRESH_GREEN = (76, 175, 80)
TIRED_ORANGE = (255, 138, 76)
FITNESS_BLUE = "#3987e5"
FATIGUE_ORANGE = "#d95926"
LOAD_GRAY = "#8c8c8c"
FRESH_GREEN_HEX = "#4caf50"
TIRED_ORANGE_HEX = "#ff8a4c"


def _epoch(iso_date: str) -> float:
    y, m, d = (int(p) for p in iso_date.split("-"))
    return datetime(y, m, d, tzinfo=timezone.utc).timestamp()


class FitnessChartWindow(QDialog):
    def __init__(self, fitness: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fitness, fatigue and form")
        self.resize(760, 640)

        outer = QVBoxLayout(self)
        outer.addWidget(branding.logo_label())
        days = fitness.get("days") or []
        if not days:
            outer.addWidget(QLabel("Not enough history yet: a few weeks of activity are needed."))
            self._plots: list = []
            return

        x = [_epoch(d["date"]) for d in days]
        width = (x[1] - x[0]) * 0.8 if len(x) > 1 else 86400 * 0.8

        toggles_row = QHBoxLayout()
        outer.addLayout(toggles_row)

        body = QHBoxLayout()
        outer.addLayout(body)

        self._x = x
        self._days = days

        plot_widget = pg.GraphicsLayoutWidget()
        body.addWidget(plot_widget, stretch=1)

        # "Right: the values for the day under the cursor" (docs/help.md), its own panel, each line colored
        # to match its plot -- updated on every crosshair move. Form's color flips with its sign. Rows get
        # equal stretch (four measures here, always) and fonts scaled the same way as chartswindow.py.
        values_panel = QWidget()
        values_panel.setFixedWidth(200)
        values_layout = QVBoxLayout(values_panel)
        values_layout.setSpacing(0)
        row_height = self.height() / 4
        value_pt, name_pt, minmax_pt = chartlegend.font_sizes_for(row_height)

        fitness_vals = [d["fitness"] for d in days]
        fatigue_vals = [d["fatigue"] for d in days]
        form_vals = [d["form"] for d in days]
        load_vals = [d["load"] for d in days]

        self.value_rows = {
            "Fitness": chartlegend.ValueRow("Fitness", FITNESS_BLUE),
            "Fatigue": chartlegend.ValueRow("Fatigue", FATIGUE_ORANGE),
            "Form": chartlegend.ValueRow("Form", FRESH_GREEN_HEX),
            "Load": chartlegend.ValueRow("Load", LOAD_GRAY),
        }
        self.value_rows["Fitness"].minmax_label.setText(f"min {min(fitness_vals):.0f}  ·  max {max(fitness_vals):.0f}")
        self.value_rows["Fatigue"].minmax_label.setText(f"min {min(fatigue_vals):.0f}  ·  max {max(fatigue_vals):.0f}")
        self.value_rows["Form"].minmax_label.setText(f"min {min(form_vals):.0f}  ·  max {max(form_vals):.0f}")
        self.value_rows["Load"].minmax_label.setText(f"min {min(load_vals):.0f}  ·  max {max(load_vals):.0f}")
        for name in ("Fitness", "Fatigue", "Form", "Load"):
            row = self.value_rows[name]
            row.set_scale(value_pt, name_pt, minmax_pt)
            values_layout.addWidget(row, stretch=1)
        body.addWidget(values_panel)

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
                self._update_readout(x_val)
                return

    def _update_readout(self, x_val: float):
        idx = bisect.bisect_left(self._x, x_val)
        idx = max(0, min(idx, len(self._x) - 1))
        if idx > 0 and abs(self._x[idx - 1] - x_val) < abs(self._x[idx] - x_val):
            idx -= 1
        day = self._days[idx]
        self.value_rows["Fitness"].value_label.setText(str(round(day["fitness"])))
        self.value_rows["Fatigue"].value_label.setText(str(round(day["fatigue"])))
        self.value_rows["Load"].value_label.setText(str(round(day["load"])))
        form_row = self.value_rows["Form"]
        form_row.name_label.setText(f"Form · {day['date']}")
        form_row.value_label.setText(str(round(day["form"])))
        form_row.set_color(FRESH_GREEN_HEX if day["form"] >= 0 else TIRED_ORANGE_HEX)
