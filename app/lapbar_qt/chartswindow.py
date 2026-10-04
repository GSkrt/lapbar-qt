"""Build-order step 8 (ride charts): PyQtGraph, one plot per stream (elevation, speed, heart rate, power,
cadence, temperature, grade), X-linked with a shared crosshair. The choice and its verification --
PyQtGraph's own downsampling matching the hand-built reduction in charts/logic.js -- are in PLAN.md.
Fetching can hit the network (streams.get()/detail() may need to download), so it runs on a background
QThread like everything else here.

Panel.qml's chart window also has keyboard stepping (arrows, +/- to zoom, R to reset, T for a table, Esc to
close); PyQtGraph's own mouse interactions (drag to pan, scroll to zoom, double-click to reset) cover the
core of that for free and are what this first pass relies on -- the keyboard/table layer is a later pass.
"""
import bisect

import pyqtgraph as pg
from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import branding, chartlegend, fetcher, plotstyle

pg.setConfigOptions(antialias=True)


def _fmt_value(value, series: dict) -> str:
    if value is None:
        return "—"
    if series["format"] == "pace":
        total = int(round(value))
        return f"{total // 60}:{total % 60:02d} {series['unit']}"
    decimals = series.get("decimals", 0)
    return f"{value:.{decimals}f} {series['unit']}" if decimals else f"{round(value)} {series['unit']}"


def _min_max_text(values: list, series: dict) -> str:
    present = [v for v in values if v is not None]
    if not present:
        return ""
    return f"min {_fmt_value(min(present), series)}  ·  max {_fmt_value(max(present), series)}"


class _ChartWorker(QObject):
    finished = pyqtSignal(dict)

    def __init__(self, activity_id: int):
        super().__init__()
        self.activity_id = activity_id

    @pyqtSlot()
    def run(self):
        try:
            result = fetcher.chart_data_for(self.activity_id)
        except Exception as e:  # noqa: BLE001 - reported back to the window, never raised into the thread
            result = {"error": "unexpected", "message": str(e)}
        self.finished.emit(result)


class ChartsWindow(QDialog):
    def __init__(self, activity_id: int, title: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title or "Ride charts")
        self.resize(880, 640)

        outer = QVBoxLayout(self)
        outer.addWidget(branding.logo_label())
        self.status = QLabel("Loading…")
        outer.addWidget(self.status)

        self._toggles_row = QHBoxLayout()
        outer.addLayout(self._toggles_row)

        body = QHBoxLayout()
        outer.addLayout(body)

        self._plot_widget = pg.GraphicsLayoutWidget()
        self._plot_widget.hide()
        body.addWidget(self._plot_widget, stretch=1)

        # "Right: the values for the day under the cursor" (docs/help.md), its own panel, each line colored
        # to match its plot -- updated on every crosshair move.
        self._values_panel = QWidget()
        self._values_panel.setFixedWidth(200)
        self._values_layout = QVBoxLayout(self._values_panel)
        self._values_layout.setSpacing(0)
        body.addWidget(self._values_panel)
        self.value_rows: dict[str, chartlegend.ValueRow] = {}

        self._plots: list = []
        self._vlines: list = []
        self._x: list = []
        self._series: list = []

        self._thread = QThread()
        self._worker = _ChartWorker(activity_id)
        self._worker.moveToThread(self._thread)
        self._worker.finished.connect(self._on_finished)
        # DirectConnection: see detailswindow.py -- quit() is thread-safe, and this must not wait for the
        # main thread's event loop or the thread could still be "running" when this window is destroyed.
        self._worker.finished.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def closeEvent(self, event):
        self._thread.quit()
        self._thread.wait()
        super().closeEvent(event)

    def _on_finished(self, data: dict):
        self._thread.quit()
        self._thread.wait()
        if "error" in data:
            self.status.setText(f"Could not load charts: {data.get('message', data.get('error'))}")
            return
        self.status.hide()
        self._build_plots(data)
        self._plot_widget.show()

    def _build_plots(self, data: dict):
        x = data["x"]["values"]
        x_label = f"{data['x']['label']} ({data['x']['unit']})"
        series = data["series"]
        self._x = x
        self._series = series

        # Divide the values panel's height by the number of measures, same as the plots divide their own
        # column (charts/shell.qml's panelH), and scale the fonts to that -- a lone measure gets a big
        # number, seven of them get smaller ones that still comfortably out-size the plot axis text.
        row_height = self.height() / max(len(series), 1)
        value_pt, name_pt, minmax_pt = chartlegend.font_sizes_for(row_height)

        first_plot = None
        for i, s in enumerate(series):
            color = pg.intColor(i, hues=max(len(series), 1))
            plot = self._plot_widget.addPlot(row=i, col=0)
            plotstyle.style(plot, left=plotstyle.label(s["label"], s["unit"]),
                            bottom=x_label if i == len(series) - 1 else None)

            y = [v if v is not None else float("nan") for v in s["values"]]
            curve = plot.plot(x, y, pen=color)
            curve.setDownsampling(auto=True, method="peak")
            curve.setClipToView(True)

            if first_plot is None:
                first_plot = plot
            else:
                plot.setXLink(first_plot)

            vline = pg.InfiniteLine(angle=90, movable=False)
            plot.addItem(vline, ignoreBounds=True)
            self._plots.append(plot)
            self._vlines.append(vline)

            # "Click a name to hide that measure" (docs/help.md) -- each row's own checkbox toggles it.
            checkbox = QCheckBox(s["label"])
            checkbox.setChecked(True)
            checkbox.toggled.connect(lambda checked, p=plot: p.setVisible(checked))
            self._toggles_row.addWidget(checkbox)

            row = chartlegend.ValueRow(s["label"], color.name())
            row.set_scale(value_pt, name_pt, minmax_pt)
            row.minmax_label.setText(_min_max_text(s["values"], s))
            self._values_layout.addWidget(row, stretch=1)
            self.value_rows[s["key"]] = row

        if self._plots:
            self._plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

    def _on_mouse_moved(self, pos):
        for plot in self._plots:
            if plot.sceneBoundingRect().contains(pos):
                x_val = plot.vb.mapSceneToView(pos).x()
                for vline in self._vlines:
                    vline.setPos(x_val)
                self._update_readout(x_val)
                return

    def _nearest_index(self, x_val: float) -> int:
        idx = bisect.bisect_left(self._x, x_val)
        idx = max(0, min(idx, len(self._x) - 1))
        if idx > 0 and abs(self._x[idx - 1] - x_val) < abs(self._x[idx] - x_val):
            idx -= 1
        return idx

    def _update_readout(self, x_val: float):
        if not self._x:
            return
        idx = self._nearest_index(x_val)
        for s in self._series:
            self.value_rows[s["key"]].value_label.setText(_fmt_value(s["values"][idx], s))
