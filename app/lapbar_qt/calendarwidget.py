"""Calendar to browse past rides, matching Panel.qml's own: days shaded by how active you were (blue, or
green for days whose full data is stored locally), an orange ring for days you skipped, click a day to show
that ride. Built on QCalendarWidget (paintCell overridden) rather than a hand-rolled grid of cells -- the
same "use the right built-in Qt class for the job" approach as QSystemTrayIcon/QThread/QTextBrowser/
PyQtGraph elsewhere in this app.

Older years' activities are read from disk on demand (history.year_activities(), a single JSON file per
year) when the calendar is paged to a year that isn't the current one -- this year's activities are already
part of the regular fetch (summary["activities"]), so no separate call is needed for it.
"""
from datetime import date

from PyQt6.QtCore import QDate, QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QCalendarWidget, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from lapbar import excuses, history

ACCENT = QColor("#7aa2f7")
RING_COLOR = QColor("#ffca28")
STORED_COLOR = QColor("#4caf50")
MONTH_NAMES = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
              "October", "November", "December")


def _day_key(qdate: QDate) -> str:
    return f"{qdate.year():04d}-{qdate.month():02d}-{qdate.day():02d}"


def _alpha_for(moving_time_s: float) -> float:
    """Darker fill for longer days: under 30 min, under 1 h, under 2 h, 2 h or more -- same buckets as
    Panel.qml's dayAlpha()."""
    if moving_time_s < 1800:
        return 0.3
    if moving_time_s < 3600:
        return 0.5
    if moving_time_s < 7200:
        return 0.72
    return 0.92


class _Calendar(QCalendarWidget):
    def __init__(self):
        super().__init__()
        self.setFirstDayOfWeek(Qt.DayOfWeek.Monday)  # weeks start on Monday, like Strava's own weekly totals
        self.setGridVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setNavigationBarVisible(False)  # CalendarPanel below builds its own «/‹/›/» nav bar
        self.days: dict[str, dict] = {}
        self.archived_keys: set[str] = set()
        self.excused: dict[str, str] = {}

    def paintCell(self, painter: QPainter, rect: QRect, qdate: QDate):
        painter.save()
        key = _day_key(qdate)
        info = self.days.get(key)
        in_month = qdate.month() == self.monthShown()

        if info and in_month:
            color = QColor(STORED_COLOR if key in self.archived_keys else ACCENT)
            color.setAlphaF(_alpha_for(info.get("moving_time_s", 0)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect.adjusted(2, 2, -2, -2), 4, 4)

        if qdate == self.selectedDate() and in_month:
            painter.setPen(QPen(self.palette().color(QPalette.ColorRole.Highlight), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 4, 4)

        if key in self.excused and in_month:
            painter.setPen(QPen(RING_COLOR, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(rect.adjusted(3, 3, -3, -3))

        text_color = self.palette().color(QPalette.ColorRole.WindowText) if in_month else QColor("#666666")
        painter.setPen(QPen(text_color))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(qdate.day()))

        painter.restore()


class CalendarPanel(QWidget):
    daySelected = pyqtSignal(dict)  # the newest activity on the picked day

    def __init__(self):
        super().__init__()
        self._today = date.today()
        self._earliest_idx = self._today.year * 12
        self._activities_by_year: dict[int, list[dict]] = {}
        self._archived_ids: set[int] = set()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        toggle_row = QHBoxLayout()
        self.toggle_button = QPushButton("▾  Calendar")
        self.toggle_button.setFlat(True)
        self.toggle_button.clicked.connect(self._toggle)
        toggle_row.addWidget(self.toggle_button)
        toggle_row.addStretch(1)
        self.collapsed_hint = QLabel("")
        self.collapsed_hint.setStyleSheet("color: gray;")
        self.collapsed_hint.hide()
        toggle_row.addWidget(self.collapsed_hint)
        outer.addLayout(toggle_row)

        self._body = QWidget()
        body_layout = QVBoxLayout(self._body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._body)

        nav_row = QHBoxLayout()
        self.prev_year_btn = QPushButton("«")
        self.prev_month_btn = QPushButton("‹")
        self.page_label = QLabel("")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_font = self.page_label.font()
        page_font.setBold(True)
        self.page_label.setFont(page_font)
        self.next_month_btn = QPushButton("›")
        self.next_year_btn = QPushButton("»")
        for button in (self.prev_year_btn, self.prev_month_btn, self.next_month_btn, self.next_year_btn):
            button.setFixedWidth(28)
        nav_row.addWidget(self.prev_year_btn)
        nav_row.addWidget(self.prev_month_btn)
        nav_row.addWidget(self.page_label, stretch=1)
        nav_row.addWidget(self.next_month_btn)
        nav_row.addWidget(self.next_year_btn)
        body_layout.addLayout(nav_row)

        self.active_days_label = QLabel("")
        self.active_days_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.active_days_label.setStyleSheet("color: gray;")
        body_layout.addWidget(self.active_days_label)

        self.calendar = _Calendar()
        self.calendar.setMinimumHeight(220)
        body_layout.addWidget(self.calendar)

        legend = QLabel(f'<span style="color:{ACCENT.name()}">■</span> activity &nbsp;&nbsp;'
                        f'<span style="color:{STORED_COLOR.name()}">■</span> stored locally')
        legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        legend.setStyleSheet("color: gray;")
        body_layout.addWidget(legend)

        self.prev_year_btn.clicked.connect(lambda: self._shift(-12))
        self.prev_month_btn.clicked.connect(lambda: self._shift(-1))
        self.next_month_btn.clicked.connect(lambda: self._shift(1))
        self.next_year_btn.clicked.connect(lambda: self._shift(12))
        self.calendar.clicked.connect(self._on_clicked)
        self.calendar.currentPageChanged.connect(lambda *_: self._on_page_changed())

        self._update_page_label()

    def set_summary(self, summary: dict):
        self.calendar.days = summary.get("days") or {}
        self._archived_ids = set(summary.get("archived_ids") or [])
        self._activities_by_year[self._today.year] = summary.get("activities") or []
        history_info = summary.get("history") or {}
        earliest_from = history_info.get("from")
        if earliest_from and len(earliest_from) >= 7:
            self._earliest_idx = int(earliest_from[:4]) * 12 + int(earliest_from[5:7]) - 1
        else:
            self._earliest_idx = self._today.year * 12
        self.calendar.excused = excuses.load()
        self._recompute_archived_keys()
        self._update_active_days_label()
        self._update_nav_enabled()
        self.calendar.updateCells()

    def clear_selection(self):
        self.calendar.setSelectedDate(QDate.currentDate())
        self.calendar.updateCells()

    def _activities_for_year(self, year: int) -> list[dict]:
        if year not in self._activities_by_year:
            self._activities_by_year[year] = history.year_activities(year)
            self._recompute_archived_keys()
        return self._activities_by_year[year]

    def _recompute_archived_keys(self):
        keys = set()
        for activities in self._activities_by_year.values():
            for activity in activities:
                if activity.get("id") in self._archived_ids and activity.get("start"):
                    keys.add(activity["start"][:10])
        self.calendar.archived_keys = keys

    def _on_clicked(self, qdate: QDate):
        key = _day_key(qdate)
        activities = [a for a in self._activities_for_year(qdate.year()) if a.get("start", "")[:10] == key]
        if not activities:
            return
        activities.sort(key=lambda a: a.get("start", ""), reverse=True)
        self.calendar.updateCells()
        self.daySelected.emit(activities[0])

    def _on_page_changed(self):
        self._update_page_label()
        if self.calendar.yearShown() != self._today.year:
            self._activities_for_year(self.calendar.yearShown())
        self._update_active_days_label()
        self._update_nav_enabled()
        self.calendar.updateCells()

    def _shift(self, delta_months: int):
        idx = self.calendar.yearShown() * 12 + (self.calendar.monthShown() - 1) + delta_months
        today_idx = self._today.year * 12 + (self._today.month - 1)
        idx = max(self._earliest_idx, min(today_idx, idx))
        year, month0 = divmod(idx, 12)
        self.calendar.setCurrentPage(year, month0 + 1)

    def _update_page_label(self):
        self.page_label.setText(f"{MONTH_NAMES[self.calendar.monthShown() - 1]} {self.calendar.yearShown()}")

    def _update_active_days_label(self):
        prefix = f"{self.calendar.yearShown():04d}-{self.calendar.monthShown():02d}"
        count = sum(1 for k in self.calendar.days if k.startswith(prefix))
        self.active_days_label.setText(f"{count} {'active day' if count == 1 else 'active days'}")
        self.collapsed_hint.setText(f"{count} active this month")

    def _update_nav_enabled(self):
        idx = self.calendar.yearShown() * 12 + (self.calendar.monthShown() - 1)
        today_idx = self._today.year * 12 + (self._today.month - 1)
        can_back = idx > self._earliest_idx
        can_forward = idx < today_idx
        self.prev_year_btn.setEnabled(can_back)
        self.prev_month_btn.setEnabled(can_back)
        self.next_month_btn.setEnabled(can_forward)
        self.next_year_btn.setEnabled(can_forward)

    def _toggle(self):
        visible = not self._body.isVisible()
        self._body.setVisible(visible)
        self.toggle_button.setText(("▾" if visible else "▸") + "  Calendar")
        self.collapsed_hint.setVisible(not visible)
