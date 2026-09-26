"""Build-order step 4: left-click opens the main window, with real fetched data -- Panel.qml's popup
content, minus the ⋮ menu (moved to the tray's right-click already) and minus the bar-frame concept
entirely (PLAN.md's "The main window" section). The calendar and the skip-today buttons are still
deferred; the "Motivational quotes" tone picker was added alongside notifications (see worker.py -- coach
nudges and kudos/comment alerts already fire for real through the reused cli.cmd_fetch, unconditional on
any UI here; this is just the control to opt into the coach, matching Panel.qml's own radio + Try one).
"""
import webbrowser
from datetime import date
from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QPainter, QPalette, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import (QApplication, QButtonGroup, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                             QMainWindow, QPushButton, QRadioButton, QVBoxLayout, QWidget)

from lapbar import coach, prefs

from . import calendarwidget, chartswindow, detailswindow, fitnesschartwindow, fitnessminiplot, routepreview, tooltip

TONE_LABELS = (("off", "Silent"), ("motivational", "Motivational"), ("drill", "Drill sergeant"))
STRAVA_ORANGE = "#fc4c02"
STRAVA_ASSETS = Path(__file__).parent / "assets" / "strava"


def _strava_logo_pixmap(height: int = 16) -> QPixmap:
    """Strava's own "Powered by Strava" logo (unmodified, see assets/strava/NOTICE.md), white on dark
    themes and black on light ones -- same choice Panel.qml's own credit image makes."""
    dark = QApplication.instance().styleHints().colorScheme() == Qt.ColorScheme.Dark
    svg_path = STRAVA_ASSETS / f"api_logo_pwrdBy_strava_horiz_{'white' if dark else 'black'}.svg"
    renderer = QSvgRenderer(str(svg_path))
    size = renderer.defaultSize()
    if not renderer.isValid() or size.height() == 0:
        return QPixmap()
    width = round(size.width() * height / size.height())
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


class _TryOneWorker(QObject):
    finished = pyqtSignal()

    def __init__(self, tone: str):
        super().__init__()
        self.tone = tone

    @pyqtSlot()
    def run(self):
        try:
            event = coach.sample(self.tone)
            coach.show(event, date.today().isoformat(), timeout_ms=8000)
        except Exception:  # noqa: BLE001 - a preview popup failing must never take the app down with it
            pass
        self.finished.emit()


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
        self.resize(760, 600)

        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)

        # Two columns side by side, same shape as Panel.qml's leftCol/rightCol: the ride itself on the
        # left, fitness/training/quotes on the right. "Powered by Strava" sits below both, right-aligned,
        # matching Panel.qml's own credit image anchored to the popup's bottom-right corner.
        columns = QHBoxLayout()
        outer.addLayout(columns, stretch=1)
        left_col = QVBoxLayout()
        right_col = QVBoxLayout()
        columns.addLayout(left_col, stretch=1)
        columns.addLayout(right_col, stretch=1)

        # Everything about the latest ride lives in one bordered box -- title, kudos, route, buttons and
        # stats used to be loose, separately-spaced widgets (title, then a gap, then a separate "This ride"
        # box for just the stats); grouping them visually as one unit and giving the stats real emphasis is
        # what was actually missing, not just bigger numbers in isolation.
        self.ride_box = QGroupBox("Latest ride")
        ride_box_layout = QVBoxLayout(self.ride_box)
        ride_box_layout.setSpacing(10)
        left_col.addWidget(self.ride_box)

        self.ride_title = QLabel("Loading…")
        self.ride_title.setWordWrap(True)
        title_font = self.ride_title.font()
        title_font.setPointSize(title_font.pointSize() + 5)
        title_font.setBold(True)
        self.ride_title.setFont(title_font)
        ride_box_layout.addWidget(self.ride_title)

        # Shown only once a calendar day other than "today" has been picked (docs/help.md item 1: "After
        # you pick another day in the calendar, a Back to latest activity link appears here").
        self.back_to_latest_link = QLabel('<a href="back">← Back to latest activity</a>')
        self.back_to_latest_link.setTextFormat(Qt.TextFormat.RichText)
        self.back_to_latest_link.linkActivated.connect(self._on_back_to_latest)
        self.back_to_latest_link.hide()
        ride_box_layout.addWidget(self.back_to_latest_link)
        self._real_latest: dict = {}
        self._selected_activity: dict | None = None

        # A link, not plain text: clicking it opens the details window (comments, records, kudos) for the
        # ride currently shown -- linkActivated fires on click without actually opening a URL.
        self.kudos_line = QLabel("")
        self.kudos_line.setTextFormat(Qt.TextFormat.RichText)
        self.kudos_line.linkActivated.connect(self._open_details)
        kudos_font = self.kudos_line.font()
        kudos_font.setPointSize(kudos_font.pointSize() + 2)
        self.kudos_line.setFont(kudos_font)
        ride_box_layout.addWidget(self.kudos_line)
        self._latest_id: int | None = None
        self._latest_url: str | None = None
        self._details_window: detailswindow.DetailsWindow | None = None

        self.route_preview = routepreview.RoutePreview()
        ride_box_layout.addWidget(self.route_preview)

        # Both buttons right under the route/overview graphics, not one as a text link elsewhere and the
        # other buried inside the stats box.
        overview_buttons = QHBoxLayout()
        self.strava_button = QPushButton("View on Strava")
        self.strava_button.setStyleSheet(
            f"QPushButton {{ background-color: {STRAVA_ORANGE}; color: white; font-weight: bold; }}"
            f"QPushButton:disabled {{ background-color: palette(button); color: palette(disabled-text); }}")
        self.strava_button.clicked.connect(self._open_on_strava)
        overview_buttons.addWidget(self.strava_button)
        self.charts_button = QPushButton("Activity metrics")
        self.charts_button.clicked.connect(self._open_charts)
        overview_buttons.addWidget(self.charts_button)
        ride_box_layout.addLayout(overview_buttons)
        self._charts_window: chartswindow.ChartsWindow | None = None

        # Basic ride data (distance, time, climb...) matters most here, so it gets real emphasis: bigger,
        # bold values, not the same small default text as everything else.
        self.stats_layout = QGridLayout()
        self.stats_layout.setHorizontalSpacing(14)
        self.stats_layout.setVerticalSpacing(6)
        ride_box_layout.addLayout(self.stats_layout)

        self.storage_line = QLabel("")
        self.storage_line.setWordWrap(True)
        self.storage_line.setStyleSheet("color: gray;")
        ride_box_layout.addWidget(self.storage_line)

        self.calendar_panel = calendarwidget.CalendarPanel()
        self.calendar_panel.daySelected.connect(self._on_day_selected)
        left_col.addWidget(self.calendar_panel)
        left_col.addStretch(1)

        self.load_line = QLabel("")
        self.load_line.setWordWrap(True)
        right_col.addWidget(self.load_line)

        self.fitness_box = QGroupBox("Fitness, fatigue and form")
        fitness_layout = QVBoxLayout(self.fitness_box)
        self.fitness_line = QLabel("")
        self.fitness_line.setWordWrap(True)
        fitness_layout.addWidget(self.fitness_line)
        self.fitness_plot = fitnessminiplot.FitnessMiniPlot()
        self.fitness_plot.dayHovered.connect(self._on_fitness_hover)
        fitness_layout.addWidget(self.fitness_plot)
        self.fitness_hover_label = QLabel("")
        self.fitness_hover_label.setWordWrap(True)
        self.fitness_hover_label.setStyleSheet("color: gray;")
        fitness_layout.addWidget(self.fitness_hover_label)
        fitness_chart_row = QHBoxLayout()
        fitness_chart_row.addStretch(1)
        self.fitness_chart_button = QPushButton("Open chart")
        self.fitness_chart_button.clicked.connect(self._open_fitness_chart)
        fitness_chart_row.addWidget(self.fitness_chart_button)
        fitness_layout.addLayout(fitness_chart_row)
        right_col.addWidget(self.fitness_box)
        self._latest_fitness: dict | None = None
        self._fitness_chart_window: fitnesschartwindow.FitnessChartWindow | None = None

        self.quotes_box = QGroupBox("Motivational quotes")
        quotes_layout = QVBoxLayout(self.quotes_box)
        self._tone_group = QButtonGroup(self.quotes_box)
        self._tone_radios: dict[str, QRadioButton] = {}
        current_tone = prefs.load()["coach_tone"]
        for tone_id, label in TONE_LABELS:
            radio = QRadioButton(label)
            radio.setChecked(tone_id == current_tone)
            radio.toggled.connect(lambda checked, t=tone_id: checked and self._set_tone(t))
            self._tone_group.addButton(radio)
            self._tone_radios[tone_id] = radio
            quotes_layout.addWidget(radio)
        try_row = QHBoxLayout()
        try_row.addStretch(1)
        self.try_one_button = QPushButton("Try one ↗")
        self.try_one_button.setEnabled(current_tone != "off")
        self.try_one_button.clicked.connect(self._try_one)
        try_row.addWidget(self.try_one_button)
        quotes_layout.addLayout(try_row)
        right_col.addWidget(self.quotes_box)
        self._try_one_thread: QThread | None = None
        self._try_one_worker: _TryOneWorker | None = None

        self.totals_box = QGroupBox("Totals")
        totals_layout = QGridLayout(self.totals_box)
        self.totals_labels: dict[str, QLabel] = {}
        for row, period in enumerate(("today", "week", "month", "year")):
            totals_layout.addWidget(QLabel(period.capitalize() + ":"), row, 0)
            value_label = QLabel("—")
            totals_layout.addWidget(value_label, row, 1)
            self.totals_labels[period] = value_label
        right_col.addWidget(self.totals_box)
        right_col.addStretch(1)

        footer_row = QHBoxLayout()
        footer_row.addStretch(1)
        footer = QLabel()
        pixmap = _strava_logo_pixmap()
        if not pixmap.isNull():
            footer.setPixmap(pixmap)
        else:
            footer.setText("Powered by Strava")  # the SVG asset is missing; a plain label is still correct
            footer.setStyleSheet("color: gray;")
        footer_row.addWidget(footer)
        outer.addLayout(footer_row)

    @pyqtSlot(dict)
    def update_summary(self, summary: dict):
        self._real_latest = summary.get("latest") or {}
        self.calendar_panel.set_summary(summary)
        self._render_activity(self._selected_activity or self._real_latest)

        archive = summary.get("archive") or {}
        budget = summary.get("budget") or {}
        if archive or budget:
            parts = []
            if archive:
                parts.append(f"{archive.get('stored', 0)} of {archive.get('total', 0)} activities stored")
            if budget:
                parts.append(f"{budget.get('daily_used', 0)} of {budget.get('daily_limit', 0)} requests used today")
            self.storage_line.setText("  ·  ".join(parts))
        else:
            self.storage_line.setText("")

        self.load_line.setText(tooltip.load_headline(summary.get("load")) or "No training last week to compare")

        fitness = summary.get("fitness") or {}
        self._latest_fitness = fitness
        self.fitness_plot.update_fitness(fitness)
        now, tomorrow = fitness.get("current"), fitness.get("tomorrow")
        if now and now.get("status") != "starting":
            status = tooltip.FITNESS_STATUS_NAME.get(now.get("status"), "").lower()
            text = (f"Form {tooltip.signed(now['form'])} ({status}) · fitness {round(now['fitness'])} "
                    f"· fatigue {round(now['fatigue'])}")
            if fitness.get("ftp"):
                text += f" · FTP {fitness['ftp']} W"
            if tomorrow:
                tstatus = tooltip.FITNESS_STATUS_NAME.get(tomorrow.get("status"), "").lower()
                text += f"\nTomorrow {tooltip.signed(tomorrow['form'])} ({tstatus}) with today's work counted"
            self.fitness_line.setText(text)
        else:
            self.fitness_line.setText("Just getting started: a few weeks of activity are needed before this means much")

        for period in ("today", "week", "month", "year"):
            self.totals_labels[period].setText(_totals_line(summary.get(period)))

    def _render_activity(self, activity: dict):
        """Fills in everything about "the ride currently shown" -- title, kudos/records line, route,
        stats, the Strava/charts buttons. Used both for the real latest activity and for whatever the
        calendar has picked (Panel.qml's `shown = selected || latest`)."""
        self._latest_id = activity.get("id")
        self._latest_url = activity.get("url")
        self.route_preview.set_route(activity.get("route"))
        self.back_to_latest_link.setVisible(self._selected_activity is not None)
        if activity.get("name"):
            self.ride_title.setText(f"{activity['name']}  ·  {tooltip.sport_name(activity.get('sport'))}")
        else:
            self.ride_title.setText("No recent activity")

        if activity:
            kudos, prs, comments = activity.get("kudos", 0), activity.get("prs", 0), activity.get("comments", 0)
            # Same icons detailswindow.py already uses per record kind (docs/help.md's own words: "a medal
            # for a personal record, a cup for a top-10 place"); 💬 for comments is the standard icon.
            text = f"\U0001f44d {kudos}  ·  \U0001f3c5 {prs}  ·  \U0001f4ac {comments}"
            # Qt's rich-text engine does not actually honor "color: inherit" on an <a> tag -- it falls back
            # to a hardcoded, near-invisible default on a dark background (verified by rendering both to a
            # pixmap and comparing pixel colors). The real window text color has to be spelled out.
            text_color = self.palette().color(QPalette.ColorRole.WindowText).name()
            self.kudos_line.setText(
                f'<a href="details" style="color: {text_color}; text-decoration: none;">{text}</a>')
        else:
            self.kudos_line.setText("")

        self.strava_button.setEnabled(bool(self._latest_url))

        while self.stats_layout.count():
            item = self.stats_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for row, (label, value) in enumerate(_stat_cells(activity)):
            label_widget = QLabel(label + ":")
            label_font = label_widget.font()
            label_font.setPointSize(label_font.pointSize() + 1)
            label_widget.setFont(label_font)
            value_widget = QLabel(value)
            value_font = value_widget.font()
            value_font.setPointSize(value_font.pointSize() + 3)
            value_font.setBold(True)
            value_widget.setFont(value_font)
            self.stats_layout.addWidget(label_widget, row, 0)
            self.stats_layout.addWidget(value_widget, row, 1)

    def _on_day_selected(self, activity: dict):
        self._selected_activity = activity
        self._render_activity(activity)

    def _on_back_to_latest(self, _link: str = ""):
        self._selected_activity = None
        self.calendar_panel.clear_selection()
        self._render_activity(self._real_latest)

    def _open_on_strava(self):
        if self._latest_url:
            webbrowser.open(self._latest_url)

    def _open_details(self, _link: str):
        if self._latest_id is None:
            return
        self._details_window = detailswindow.DetailsWindow(self._latest_id, title=self.ride_title.text() or "", parent=self)
        self._details_window.setWindowModality(Qt.WindowModality.NonModal)
        self._details_window.show()

    def _open_charts(self):
        if self._latest_id is None:
            return
        self._charts_window = chartswindow.ChartsWindow(self._latest_id, title=self.ride_title.text() or "", parent=self)
        self._charts_window.setWindowModality(Qt.WindowModality.NonModal)
        self._charts_window.show()

    def _open_fitness_chart(self):
        if not self._latest_fitness:
            return
        self._fitness_chart_window = fitnesschartwindow.FitnessChartWindow(self._latest_fitness, parent=self)
        self._fitness_chart_window.setWindowModality(Qt.WindowModality.NonModal)
        self._fitness_chart_window.show()

    def _on_fitness_hover(self, day: dict | None):
        if day is None:
            self.fitness_hover_label.setText("")
            return
        self.fitness_hover_label.setText(
            f"{day['date']} · Form {tooltip.signed(day['form'])} · fitness {round(day['fitness'])} "
            f"· fatigue {round(day['fatigue'])}")

    def _set_tone(self, tone: str):
        prefs.update(coach_tone=tone)
        self.try_one_button.setEnabled(tone != "off")

    def _try_one(self):
        tone = next((t for t, radio in self._tone_radios.items() if radio.isChecked()), "motivational")
        if tone == "off":
            return
        self.try_one_button.setEnabled(False)
        self._try_one_thread = QThread()
        self._try_one_worker = _TryOneWorker(tone)
        self._try_one_worker.moveToThread(self._try_one_thread)
        self._try_one_worker.finished.connect(self._on_try_one_finished)
        # DirectConnection: see detailswindow.py -- quit() is thread-safe, and this must not wait for the
        # main thread's event loop or the thread could still be "running" when this window is destroyed.
        self._try_one_worker.finished.connect(self._try_one_thread.quit, Qt.ConnectionType.DirectConnection)
        self._try_one_thread.started.connect(self._try_one_worker.run)
        self._try_one_thread.start()

    def _on_try_one_finished(self):
        self._try_one_thread.quit()
        self._try_one_thread.wait()
        self.try_one_button.setEnabled(True)
