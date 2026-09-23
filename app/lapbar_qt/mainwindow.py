"""Build-order step 4: left-click opens the main window, read-only, with real fetched data -- Panel.qml's
popup content, minus the ⋮ menu (moved to the tray's right-click already) and minus the bar-frame
concept entirely (PLAN.md's "The main window" section). Route trace, the calendar, and any interactive
controls (Open chart, skip-today, the quotes radio) are later steps; this is the read-only text content.
"""
from PyQt6.QtCore import pyqtSlot
from PyQt6.QtWidgets import QGridLayout, QGroupBox, QLabel, QMainWindow, QVBoxLayout, QWidget

from . import tooltip


def _stat_cells(latest: dict) -> list[tuple[str, str]]:
    """Which numbers matter depends on the sport, same as Panel.qml's statCells: pace where people think in
    pace, speed and power for cycling, time only for sessions without distance (gym, yoga...)."""
    cells = []
    if latest.get("distance_km", 0) > 0:
        km = latest["distance_km"]
        cells.append(("Distance", f"{km:.1f} km" if km >= 10 else f"{km:.2f} km"))
    cells.append(("Time", tooltip.fmt_duration(latest.get("moving_time_s", 0))))
    if latest.get("elevation_m", 0) > 0:
        cells.append(("Climb", f"{latest['elevation_m']} m"))
    if latest.get("pace_s"):
        m, s = divmod(int(latest["pace_s"]), 60)
        cells.append(("Pace", f"{m}:{s:02d} /{latest['pace_unit']}"))
    elif latest.get("avg_speed_kmh"):
        cells.append(("Speed", f"{latest['avg_speed_kmh']} km/h"))
    if latest.get("avg_watts"):
        cells.append(("Power", f"{round(latest['avg_watts'])} W"))
    if latest.get("avg_heartrate"):
        cells.append(("Heart rate", f"{latest['avg_heartrate']} bpm"))
    if latest.get("avg_cadence"):
        cells.append(("Cadence", f"{latest['avg_cadence']} {latest.get('cadence_unit', '')}"))
    return cells


def _totals_line(period: dict | None) -> str:
    if not period or not period.get("count"):
        return "—"
    return (f"{period['count']} · {tooltip.fmt_duration(period['moving_time_s'])} · "
            f"{period['distance_km']:.1f} km · {period['elevation_m']} m climb")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("lapbar-qt")
        self.resize(420, 560)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.ride_title = QLabel("Loading…")
        self.ride_title.setWordWrap(True)
        title_font = self.ride_title.font()
        title_font.setPointSize(title_font.pointSize() + 3)
        title_font.setBold(True)
        self.ride_title.setFont(title_font)
        layout.addWidget(self.ride_title)

        self.kudos_line = QLabel("")
        layout.addWidget(self.kudos_line)

        self.stats_box = QGroupBox("This ride")
        self.stats_layout = QGridLayout(self.stats_box)
        layout.addWidget(self.stats_box)

        self.load_line = QLabel("")
        self.load_line.setWordWrap(True)
        layout.addWidget(self.load_line)

        self.fitness_box = QGroupBox("Fitness, fatigue and form")
        fitness_layout = QVBoxLayout(self.fitness_box)
        self.fitness_line = QLabel("")
        self.fitness_line.setWordWrap(True)
        fitness_layout.addWidget(self.fitness_line)
        layout.addWidget(self.fitness_box)

        self.totals_box = QGroupBox("Totals")
        totals_layout = QGridLayout(self.totals_box)
        self.totals_labels: dict[str, QLabel] = {}
        for row, period in enumerate(("today", "week", "month", "year")):
            totals_layout.addWidget(QLabel(period.capitalize() + ":"), row, 0)
            value_label = QLabel("—")
            totals_layout.addWidget(value_label, row, 1)
            self.totals_labels[period] = value_label
        layout.addWidget(self.totals_box)

        layout.addStretch(1)

        footer = QLabel("Powered by Strava")
        footer.setStyleSheet("color: gray;")
        layout.addWidget(footer)

    @pyqtSlot(dict)
    def update_summary(self, summary: dict):
        latest = summary.get("latest") or {}
        if latest.get("name"):
            self.ride_title.setText(f"{latest['name']}  ·  {tooltip.sport_name(latest.get('sport'))}")
        else:
            self.ride_title.setText("No recent activity")

        if latest:
            kudos, prs, comments = latest.get("kudos", 0), latest.get("prs", 0), latest.get("comments", 0)
            self.kudos_line.setText(
                f"{kudos} {'kudo' if kudos == 1 else 'kudos'}  ·  {prs} {'PR' if prs == 1 else 'PRs'}  ·  "
                f"{comments} {'comment' if comments == 1 else 'comments'}")
        else:
            self.kudos_line.setText("")

        while self.stats_layout.count():
            item = self.stats_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for row, (label, value) in enumerate(_stat_cells(latest)):
            self.stats_layout.addWidget(QLabel(label + ":"), row, 0)
            self.stats_layout.addWidget(QLabel(value), row, 1)

        self.load_line.setText(tooltip.load_headline(summary.get("load")) or "No training last week to compare")

        fitness = summary.get("fitness") or {}
        now, tomorrow = fitness.get("current"), fitness.get("tomorrow")
        if now and now.get("status") != "starting":
            status = tooltip.FITNESS_STATUS_NAME.get(now.get("status"), "").lower()
            text = (f"Form {tooltip.signed(now['form'])} ({status}) · fitness {round(now['fitness'])} "
                    f"· fatigue {round(now['fatigue'])}")
            if tomorrow:
                tstatus = tooltip.FITNESS_STATUS_NAME.get(tomorrow.get("status"), "").lower()
                text += f"\nTomorrow {tooltip.signed(tomorrow['form'])} ({tstatus}) with today's work counted"
            self.fitness_line.setText(text)
        else:
            self.fitness_line.setText("Just getting started: a few weeks of activity are needed before this means much")

        for period in ("today", "week", "month", "year"):
            self.totals_labels[period].setText(_totals_line(summary.get(period)))
