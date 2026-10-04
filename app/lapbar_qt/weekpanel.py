"""This week against last week, at a glance: a headline saying how far ahead or behind you are at this point of
the week, and two small charts.

- Running total through the week: last week's whole week in grey, this week so far in blue, a dashed line at
  "now", and the gap between the two at that moment drawn in green (ahead) or orange (behind) -- the
  headline's number, as a picture.
- The last 12 weeks' totals as bars (this week so far in blue) with their average as a dashed line, for the
  weekly load over time rather than just against one other week.

The metric (time, distance, climb, Relative Effort) is picked here and remembered. The numbers come from
weekcompare.py.
"""
from datetime import datetime, timedelta

import pyqtgraph as pg
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QComboBox, QGroupBox, QHBoxLayout, QLabel, QTabWidget, QVBoxLayout

from lapbar import history

from . import icons, plotstyle, weekcompare

THIS_BLUE = "#3987e5"
LAST_GREY = "#9e9e9e"
AHEAD_GREEN = "#4caf50"
BEHIND_ORANGE = "#ff8a4c"
WEEKS = 12
DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def _steps(points: list[tuple[float, float]]) -> tuple[list[float], list[float]]:
    """Running-total points as a staircase: the total jumps at each activity and stays flat in between."""
    xs, ys = [], []
    for i, (x, y) in enumerate(points):
        if i:
            xs.append(x)
            ys.append(points[i - 1][1])
        xs.append(x)
        ys.append(y)
    return xs, ys


def _small_font() -> QFont:
    font = QFont()
    font.setPointSize(8)
    return font


class WeekComparePanel(QGroupBox):
    def __init__(self):
        super().__init__("This week vs last week")
        self._settings = QSettings("lapbar-qt", "lapbar-qt")
        self._activities: list[dict] = []
        self._now = datetime.now()
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.headline = QLabel("")
        self.headline.setWordWrap(True)
        font = self.headline.font()
        font.setBold(True)
        self.headline.setFont(font)
        top.addWidget(self.headline, stretch=1)
        self.metric_box = QComboBox()
        top.addWidget(self.metric_box)
        layout.addLayout(top)

        self.detail = QLabel("")
        self.detail.setWordWrap(True)
        self.detail.setStyleSheet("color: gray;")
        layout.addWidget(self.detail)

        # Two charts, one at a time, so the panel stays as compact as the fitness one below it.
        self.tabs = QTabWidget()
        self.week_plot = pg.PlotWidget()
        self.history_plot = pg.PlotWidget()
        self.tabs.addTab(self.week_plot, icons.chart("week"), "This week")
        self.tabs.addTab(self.history_plot, icons.chart("weeks"), f"Last {WEEKS} weeks")
        self.tabs.setFixedHeight(175)
        self.tabs.setCurrentIndex(int(self._settings.value("week_tab", 0)))
        self.tabs.currentChanged.connect(lambda i: self._settings.setValue("week_tab", i))
        layout.addWidget(self.tabs)

        self.metric_box.currentIndexChanged.connect(self._on_metric_changed)

    # ---------------------------------------------------------------- data in

    def set_summary(self, summary: dict, now: datetime | None = None):
        self._now = now or datetime.now()
        activities = list(summary.get("activities") or [])
        first_week = weekcompare.week_start(self._now) - timedelta(days=7 * (WEEKS - 1))
        if first_week.year < self._now.year:       # the charts reach back into last year: add its stored list
            activities += history.year_activities(self._now.year - 1)
        self._activities = activities
        self._fill_metrics()
        self._redraw()

    def current_metric(self) -> str:
        return self.metric_box.currentData() or "time"

    def _fill_metrics(self):
        wanted = self.metric_box.currentData() or self._settings.value("week_metric", "time")
        offered = weekcompare.available(self._activities)
        self.metric_box.blockSignals(True)
        self.metric_box.clear()
        for key in offered:
            self.metric_box.addItem(weekcompare.METRICS[key][0], key)
        self.metric_box.setCurrentIndex(offered.index(wanted) if wanted in offered else 0)
        self.metric_box.blockSignals(False)

    def _on_metric_changed(self):
        self._settings.setValue("week_metric", self.current_metric())
        self._redraw()

    # ---------------------------------------------------------------- drawing

    def _redraw(self):
        metric = self.current_metric()
        unit = weekcompare.METRICS[metric][3]
        result = weekcompare.compare(self._activities, metric, self._now)
        self.headline.setText(weekcompare.headline(result, metric))
        color = {"ahead": AHEAD_GREEN, "behind": BEHIND_ORANGE}.get(result["state"])
        self.headline.setStyleSheet(f"color: {color};" if color else "")
        self.detail.setText("" if result["state"] == "idle" else weekcompare.detail(result, metric))

        self._draw_week(metric, unit, result, color)
        self._draw_history(metric, unit)

    def _axis_style(self, plot, left: str, bottom: str | None = None):
        for side in ("left", "bottom"):
            plot.getAxis(side).setStyle(tickFont=_small_font())
        plotstyle.style(plot, left=left, bottom=bottom)
        plot.getViewBox().setMouseEnabled(x=False, y=False)
        plot.hideButtons()

    def _draw_week(self, metric: str, unit: str, result: dict, gap_color: str | None):
        self.week_plot.clear()
        plot = self.week_plot.getPlotItem()
        self._axis_style(plot, plotstyle.label(weekcompare.METRICS[metric][0], unit) + ", running total")
        plot.getAxis("bottom").setTicks([[(i + 0.5, name) for i, name in enumerate(DAY_NAMES)]])
        plot.setXRange(0, 7, padding=0.01)
        series = weekcompare.cumulative(self._activities, metric, self._now)

        lx, ly = _steps(series["last"])
        plot.plot(lx, ly, pen=pg.mkPen(LAST_GREY, width=2), fillLevel=0, brush=pg.mkBrush(158, 158, 158, 40),
                  name="Last week")
        tx, ty = _steps(series["this"])
        plot.plot(tx, ty, pen=pg.mkPen(THIS_BLUE, width=3), name="This week")

        now_x = series["this"][-1][0]
        plot.addItem(pg.InfiniteLine(pos=now_x, angle=90, pen=pg.mkPen("#bbbbbb", width=1, style=Qt.PenStyle.DashLine)))
        if gap_color:
            # The headline's number, drawn: from where you are to where last week was at this moment.
            plot.plot([now_x, now_x], [result["this"], result["last_same_point"]], pen=pg.mkPen(gap_color, width=5))
            label = pg.TextItem(("+" if result["delta"] > 0 else "−") + weekcompare.fmt(abs(result["delta"]), metric),
                                color=gap_color, anchor=(1.05 if now_x > 3.5 else -0.05, 0.5))
            label.setFont(_small_font())
            label.setPos(now_x, (result["this"] + result["last_same_point"]) / 2)
            plot.addItem(label)
        top = max(ly[-1], ty[-1], 0.001)
        plot.setYRange(0, top, padding=0.08)

    def _draw_history(self, metric: str, unit: str):
        weeks = weekcompare.weekly_totals(self._activities, metric, self._now, WEEKS)
        self.history_plot.clear()
        plot = self.history_plot.getPlotItem()
        self._axis_style(plot, plotstyle.label(weekcompare.METRICS[metric][0], unit) + " per week", "week starting")
        xs = list(range(len(weeks)))
        values = [v for _, v in weeks]
        plot.addItem(pg.BarGraphItem(x=xs[:-1], height=values[:-1], width=0.7, brush=LAST_GREY, pen=None))
        plot.addItem(pg.BarGraphItem(x=[xs[-1]], height=[values[-1]], width=0.7, brush=THIS_BLUE, pen=None))
        finished = values[:-1]
        if any(finished):
            average = sum(finished) / len(finished)
            plot.addItem(pg.InfiniteLine(pos=average, angle=0, pen=pg.mkPen("#e0e0e0", width=1,
                                                                            style=Qt.PenStyle.DashLine)))
            label = pg.TextItem(f"avg {weekcompare.fmt(average, metric)}", color="#e0e0e0", anchor=(0, 1))
            label.setFont(_small_font())
            label.setPos(-0.4, average)
            plot.addItem(label)
        # Every other Monday's date, counting back from this week so this week always gets one.
        plot.getAxis("bottom").setTicks([[(x, f"{monday.day}.{monday.month}") for x, (monday, _) in
                                          zip(xs, weeks) if (len(weeks) - 1 - x) % 2 == 0]])
        plot.setXRange(-0.6, len(weeks) - 0.4, padding=0)
        plot.setYRange(0, max(values + [0.001]), padding=0.1)
