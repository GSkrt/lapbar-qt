"""The data window, the Qt counterpart of LapBar's manage/shell.qml: everything about what is stored and the DuckDB
export, built on manage.status().

Left: History (how much is stored, the limit on how far back it goes), Fetching day by day (downloads and
Strava requests), and Export to DuckDB (where the file goes, Export now / Rebuild, keep it up to date, real
geometry, progress and the last result). Right: what is in the database -- how the tables join, every table
and column with its type and meaning, example queries to copy, and notes.

manage.status() walks the whole archive on disk to size it, so it runs on a background thread. An export runs
the way the original runs it, as a separate `lapbar export` process (platforms.cli_command(), so it also works
in a packaged app): the export tightens the process umask while it writes, which must not touch this GUI
process, and its progress is read back from the export's own state file while it runs. The continuous export
started after a refresh shows up here the same way.
"""
import json
from pathlib import Path

from PyQt6.QtCore import QDate, QObject, QProcess, Qt, QThread, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QFont, QGuiApplication
from PyQt6.QtWidgets import (QCalendarWidget, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFrame, QGridLayout,
                             QGroupBox, QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea, QVBoxLayout,
                             QWidget)

from lapbar import export, manage, platforms, prefs

from . import branding

WARN = "#ff8a4c"


def _fmt_bytes(n) -> str:
    if n is None:
        return "—"
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def _fmt_int(n) -> str:
    return f"{int(n or 0):,}"


def _caption(text: str, color: str = "gray") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet(f"color: {color};")
    return label


def _mono(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setFont(QFont("monospace"))
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def _bar(value: float, maximum: float, height: int = 10) -> QProgressBar:
    bar = QProgressBar()
    bar.setTextVisible(False)
    bar.setFixedHeight(height)
    bar.setRange(0, max(1, int(maximum)))
    bar.setValue(int(value))
    return bar


class _StatusWorker(QObject):
    finished = pyqtSignal(dict)

    @pyqtSlot()
    def run(self):
        try:
            result = manage.status()
        except Exception as e:  # noqa: BLE001 - reported back to the window, never raised into the thread
            result = {"error": str(e)}
        self.finished.emit(result)


class DateLimitDialog(QDialog):
    def __init__(self, current: str | None, first_day: str | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(branding.window_title("Fetch history back to"))
        layout = QVBoxLayout(self)
        self.calendar = QCalendarWidget()
        self.calendar.setFirstDayOfWeek(Qt.DayOfWeek.Monday)
        self.calendar.setMaximumDate(QDate.currentDate())
        if first_day:
            self.calendar.setMinimumDate(QDate.fromString(first_day, "yyyy-MM-dd"))
        if current:
            self.calendar.setSelectedDate(QDate.fromString(current, "yyyy-MM-dd"))
        layout.addWidget(self.calendar)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen_date(self) -> str:
        return self.calendar.selectedDate().toString("yyyy-MM-dd")


class DataWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(branding.window_title("Data"))
        self.resize(1180, 820)
        self._status: dict | None = None

        outer = QVBoxLayout(self)
        outer.addWidget(branding.header("Data"))
        self.status_label = QLabel("Loading…")
        outer.addWidget(self.status_label)
        self._content = QWidget()
        outer.addWidget(self._content, stretch=1)
        self.message = QLabel("")
        self.message.setWordWrap(True)
        self.message.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        outer.addWidget(self.message)

        self._thread: QThread | None = None
        self._worker: _StatusWorker | None = None
        self._export_process: QProcess | None = None
        self._export_widgets: dict = {}
        self._poll = QTimer(self)
        self._poll.setInterval(700)
        self._poll.timeout.connect(self._poll_export)
        self.reload()

    # ---------------------------------------------------------------- loading

    def reload(self):
        if self._thread is not None and self._thread.isRunning():
            return
        if self._status is None:
            self.status_label.setText("Loading…")
            self.status_label.show()
            self._content.hide()
        self._thread = QThread()
        self._worker = _StatusWorker()
        self._worker.moveToThread(self._thread)
        self._worker.finished.connect(self._on_finished)
        # DirectConnection: see detailswindow.py -- quit() is thread-safe, and this must not wait for the
        # main thread's event loop or the thread could still be "running" when this window is destroyed.
        self._worker.finished.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def closeEvent(self, event):
        self._poll.stop()
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        super().closeEvent(event)       # a running export keeps going on its own; it is a separate process

    def _on_finished(self, result: dict):
        self._thread.quit()
        self._thread.wait()
        if "error" in result:
            self.status_label.setText(f"Could not load: {result['error']}")
            return
        self._status = result
        self.status_label.hide()
        new_content = self._build_content(result)
        self.layout().replaceWidget(self._content, new_content)
        self._content.deleteLater()
        self._content = new_content
        self._content.show()
        running = bool(result["export"]["state"].get("running"))
        if running and not self._poll.isActive():
            self._poll.start()

    def _say(self, text: str, error: bool = False):
        self.message.setText(text)
        self.message.setStyleSheet(f"color: {WARN};" if error else "")

    # ---------------------------------------------------------------- layout

    def _build_content(self, result: dict) -> QWidget:
        content = QWidget()
        columns = QHBoxLayout(content)
        columns.setContentsMargins(0, 0, 0, 0)

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self._export_box(result))     # first: it is what this window is mostly opened for
        left_layout.addWidget(self._history_box(result))
        left_layout.addWidget(self._fetch_box(result))
        left_layout.addStretch(1)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)   # wrap, never cut off
        left_scroll.setWidget(left)
        left_scroll.setMinimumWidth(500)
        columns.addWidget(left_scroll, stretch=5)

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        right_scroll.setWidget(self._schema_panel(result))
        columns.addWidget(right_scroll, stretch=6)
        return content

    def _history_box(self, result: dict) -> QGroupBox:
        h = result["history"]
        box = QGroupBox("History")
        layout = QVBoxLayout(box)
        span = f", {h['oldest_day']} to {h['newest_day']}" if h.get("oldest_day") else ""
        headline = QLabel(f"{_fmt_int(h['activities'])} activities{span}")
        font = headline.font()
        font.setPointSize(font.pointSize() + 1)
        headline.setFont(font)
        layout.addWidget(headline)
        layout.addWidget(_bar(h["stored"], h["activities"]))
        pct = round(100 * h["stored"] / h["activities"]) if h["activities"] else 0
        line = (f"Full data stored for {_fmt_int(h['stored'])} of {_fmt_int(h['activities'])} ({pct}%) · "
                f"{_fmt_bytes(h['raw_bytes'])}")
        if h.get("estimated_total_bytes"):
            line += f", about {_fmt_bytes(h['estimated_total_bytes'])} when complete"
        if h.get("no_data"):
            line += f" · {h['no_data']} have no data on Strava"
        layout.addWidget(_caption(line))
        layout.addWidget(_caption(f"{len(h['years_stored'])} earlier years listed"
                                  + (" (all of them)" if h["years_complete"] else ", more to come")))

        title = QLabel("Fetch history back to")
        bold = title.font()
        bold.setBold(True)
        title.setFont(bold)
        layout.addWidget(title)
        row = QHBoxLayout()
        choose = QPushButton(f"From {h['limit']}  ▾" if h["limit"] else "Choose a date…  ▾")
        choose.clicked.connect(self._choose_limit)
        row.addWidget(choose)
        no_limit = QPushButton("No limit")
        no_limit.setEnabled(bool(h["limit"]))
        no_limit.clicked.connect(self._clear_limit)
        row.addWidget(no_limit)
        row.addStretch(1)
        layout.addLayout(row)
        layout.addWidget(_caption(
            f"Only activities from {h['limit']} on are downloaded and shown in the calendar. What is already stored "
            "stays on disk." if h["limit"] else
            "No limit: LapBar fetches everything Strava has. Set a day to stop it going further back in the past."))
        layout.addWidget(_caption(f"Stored in {h['data_dir']}"))
        return box

    def _fetch_box(self, result: dict) -> QGroupBox:
        box = QGroupBox("Fetching, day by day")
        layout = QVBoxLayout(box)
        b = result["budget"]
        layout.addWidget(_caption(
            f"Today: {b['daily_used']} of {b['daily_limit']} Strava requests used. Days are UTC, as Strava counts "
            "them. Background downloads slow down as the day fills up and stop at 40%."))
        days = list(reversed(result["fetch_days"]))
        most = max([d["activities"] for d in days] + [1])
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(3)
        for row, day in enumerate(days):
            busy = day["activities"] > 0 or day["requests"] > 0
            date_label = QLabel(day["date"][5:] + ("  today" if row == 0 else ""))
            date_label.setStyleSheet("" if row == 0 else "color: gray;")
            grid.addWidget(date_label, row, 0)
            grid.addWidget(_bar(day["activities"], most, 8), row, 1)
            count = QLabel(f"{day['activities']} stored · {day['requests']} req")
            count.setStyleSheet("" if busy else "color: gray;")
            grid.addWidget(count, row, 2, alignment=Qt.AlignmentFlag.AlignRight)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)
        layout.addWidget(_caption('"stored" is complete activities downloaded that day; "req" is the most requests '
                                  "Strava reported that day (everything LapBar asked, not only these)."))
        return box

    def _export_box(self, result: dict) -> QGroupBox:
        e = result["export"]
        state = e.get("state") or {}
        box = QGroupBox("Export to DuckDB")
        layout = QVBoxLayout(box)
        layout.addWidget(_caption("A database file with your activities, routes and every second of data, for your "
                                  "own SQL. LapBar never reads it back.", color=""))

        if not e["available"]:
            missing = QLabel("DuckDB is not installed")
            missing.setStyleSheet(f"color: {WARN}; font-weight: bold;")
            layout.addWidget(missing)
            if e.get("install"):
                layout.addWidget(_caption("Install its Python package, then reopen this window:"))
                for command in e["install"]:
                    row = QHBoxLayout()
                    row.addWidget(_mono(command), stretch=1)
                    copy = QPushButton("Copy")
                    copy.clicked.connect(lambda _=False, c=command: self._copy(c))
                    row.addWidget(copy)
                    layout.addLayout(row)
                layout.addWidget(_caption("Also install `duckdb` itself if you want its command line to query the file."))
            else:
                layout.addWidget(_caption("This build of LapBar doesn't include DuckDB. Running LapBar from source with "
                                          "DuckDB installed enables the export."))
        else:
            layout.addWidget(_caption(f"DuckDB {e['version']} found."))

        where = QLabel("Save the database in")
        bold = where.font()
        bold.setBold(True)
        where.setFont(bold)
        layout.addWidget(where)
        layout.addWidget(_mono(e["dir"]))
        folder_row = QHBoxLayout()
        choose = QPushButton("Choose folder…")
        choose.clicked.connect(self._choose_folder)
        folder_row.addWidget(choose)
        default = QPushButton("Default")
        default.setEnabled(bool(prefs.load()["export_path"]))
        default.clicked.connect(self._default_folder)
        folder_row.addWidget(default)
        folder_row.addStretch(1)
        layout.addLayout(folder_row)
        layout.addWidget(_caption(f"The file is called {e['filename']}."))

        busy = bool(state.get("running")) or self._export_process is not None
        actions = QHBoxLayout()
        export_now = QPushButton("Export now")
        export_now.setDefault(True)
        export_now.setEnabled(e["available"] and not busy)
        export_now.clicked.connect(lambda: self._run_export(rebuild=False))
        actions.addWidget(export_now)
        rebuild = QPushButton("Rebuild")
        rebuild.setEnabled(e["available"] and not busy)
        rebuild.clicked.connect(lambda: self._run_export(rebuild=True))
        actions.addWidget(rebuild)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addWidget(_caption("Export now updates the file: only activities that are not in it yet are added. "
                                  "Rebuild writes a fresh file."))

        continuous = QCheckBox("Keep it up to date")
        continuous.setEnabled(e["available"])
        continuous.setChecked(bool(e["continuous"]))
        continuous.toggled.connect(lambda on: self._set_pref(export_continuous=on))
        layout.addWidget(continuous)
        layout.addWidget(_caption("Appends new activities to the file after every refresh."))
        spatial = QCheckBox("Add real geometry (routes.geom)")
        spatial.setEnabled(e["available"])
        spatial.setChecked(bool(e["spatial_wanted"]))
        spatial.toggled.connect(lambda on: self._set_pref(export_spatial=on))
        layout.addWidget(spatial)
        layout.addWidget(_caption("Downloads DuckDB's spatial extension once (about 80 MB) from DuckDB's servers."))
        if e["available"]:
            layout.addWidget(_caption(
                "Spatial extension: installed. routes.geom is filled on the next export." if e["spatial"] else
                "Spatial extension: not installed yet; it is downloaded during the next export." if e["spatial_wanted"]
                else "Spatial extension: not installed. Without it the routes are still stored as text (wkt) and as "
                     "map cells."))
        if state.get("spatial_problem"):
            layout.addWidget(_caption(state["spatial_problem"], color=WARN))

        progress = _bar(state.get("done", 0), state.get("total", 0) or 1)
        progress_text = _caption("")
        progress.setVisible(busy)
        progress_text.setVisible(busy)
        if busy:
            progress_text.setText(f"Exporting {state.get('done', 0)} of {state.get('total', 0)} activities…")
        layout.addWidget(progress)
        layout.addWidget(progress_text)
        if not busy and state.get("finished"):
            layout.addWidget(_caption(
                f"Last export: {state['finished'].replace('T', ' ').replace('Z', ' UTC')} · "
                f"{_fmt_int(state.get('activities'))} activities, {_fmt_int(state.get('sample_rows'))} samples · "
                f"{_fmt_bytes(e['file_bytes'])}"))
        if state.get("error"):
            layout.addWidget(_caption(state["error"], color=WARN))
        self._export_widgets = {"progress": progress, "text": progress_text, "buttons": (export_now, rebuild)}
        return box

    def _schema_panel(self, result: dict) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)

        def heading(text: str):
            label = QLabel(text)
            font = label.font()
            font.setBold(True)
            font.setPointSize(font.pointSize() + 2)
            label.setFont(font)
            layout.addSpacing(6)
            layout.addWidget(label)

        heading("What is in the database")
        for relation in result.get("relationships") or []:
            layout.addWidget(_mono(relation["link"]))
            layout.addWidget(_caption(relation["about"]))

        for table in result.get("schema") or []:
            box = QGroupBox(table["table"])
            box_layout = QVBoxLayout(box)
            box_layout.addWidget(_caption(table["about"], color=""))
            grid = QGridLayout()
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(2)
            for row, column in enumerate(table["columns"]):
                name = _mono(column["name"])
                grid.addWidget(name, row, 0, alignment=Qt.AlignmentFlag.AlignTop)
                kind = _mono(column["type"])
                kind.setStyleSheet("color: gray;")
                grid.addWidget(kind, row, 1, alignment=Qt.AlignmentFlag.AlignTop)
                about = QLabel(column["about"])
                about.setWordWrap(True)
                grid.addWidget(about, row, 2)
            grid.setColumnStretch(2, 1)
            box_layout.addLayout(grid)
            layout.addWidget(box)

        heading("Example queries")
        for example in result.get("examples") or []:
            box = QGroupBox(example["title"])
            box_layout = QVBoxLayout(box)
            sql = _mono(example["sql"])
            sql.setWordWrap(True)
            box_layout.addWidget(sql)
            copy = QPushButton("Copy")
            copy.clicked.connect(lambda _=False, text=example["sql"]: self._copy(text))
            box_layout.addWidget(copy, alignment=Qt.AlignmentFlag.AlignRight)
            layout.addWidget(box)

        heading("Notes")
        for note in result.get("notes") or []:
            title = QLabel(note["title"])
            bold = title.font()
            bold.setBold(True)
            title.setFont(bold)
            layout.addWidget(title)
            layout.addWidget(_caption(note["about"]))
        layout.addWidget(_caption("Open the file with the duckdb command, Python (import duckdb), R, or DBeaver."))
        layout.addStretch(1)
        return panel

    # ---------------------------------------------------------------- actions

    def _copy(self, text: str):
        QGuiApplication.clipboard().setText(text)
        self._say("Copied: " + text.splitlines()[0] + (" …" if "\n" in text else ""))

    def _set_pref(self, **changes):
        try:
            prefs.update(**changes)
        except (ValueError, OSError) as e:
            self._say(str(e), error=True)
            return
        self._say("Saved.")
        self.reload()

    def _choose_limit(self):
        h = (self._status or {}).get("history") or {}
        dialog = DateLimitDialog(h.get("limit"), h.get("first_day"), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._set_pref(history_from=dialog.chosen_date())

    def _clear_limit(self):
        self._set_pref(history_from=None)

    def _choose_folder(self):
        e = (self._status or {}).get("export") or {}
        folder = QFileDialog.getExistingDirectory(self, "Folder for the DuckDB file", e.get("dir") or str(Path.home()))
        if not folder:
            self._say("No folder chosen.")
            return
        self._set_pref(export_path=str(Path(folder) / (e.get("filename") or "lapbar.duckdb")))

    def _default_folder(self):
        self._set_pref(export_path=None)

    def _run_export(self, rebuild: bool):
        if self._export_process is not None:
            return
        program, *args = platforms.cli_command()
        process = QProcess(self)
        process.setProgram(program)
        process.setArguments([*args, "export", *(["--rebuild"] if rebuild else [])])
        process.finished.connect(self._on_export_finished)
        self._export_process = process
        for button in self._export_widgets.get("buttons", ()):
            button.setEnabled(False)
        self._export_widgets["progress"].show()
        self._export_widgets["text"].show()
        self._export_widgets["text"].setText("Rebuilding…" if rebuild else "Exporting…")
        self._say("Rebuilding the database…" if rebuild else "Exporting…")
        process.start()
        self._poll.start()

    def _poll_export(self):
        state = export.state()
        widgets = self._export_widgets
        if state.get("running") and widgets:
            total = state.get("total") or 0
            widgets["progress"].setRange(0, max(1, total))
            widgets["progress"].setValue(state.get("done") or 0)
            if total:
                widgets["text"].setText(f"Exporting {state.get('done', 0)} of {total} activities…")
        elif self._export_process is None:      # a background (continuous) export finished
            self._poll.stop()
            self.reload()

    def _on_export_finished(self, exit_code: int, _status):
        output = bytes(self._export_process.readAllStandardOutput()).decode("utf-8", "replace").strip()
        self._export_process.deleteLater()
        self._export_process = None
        self._poll.stop()
        try:
            data = json.loads(output.splitlines()[-1]) if output else {}
        except json.JSONDecodeError:
            data = {}
        if exit_code == 0 and "sample_rows" in data:
            self._say(f"Exported {_fmt_int(data.get('activities'))} activities and {_fmt_int(data['sample_rows'])} "
                      f"samples to {data.get('path')}")
        else:
            self._say(data.get("message") or output or "The export did not finish.", error=True)
        self.reload()
