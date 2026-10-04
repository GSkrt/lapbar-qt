"""Build-order step 7: the data window, built on manage.status() -- how much history is stored, what
fetching did each day, and the DuckDB export -- opened from the tray's right-click menu. manage.status()
walks the whole downloaded-activities archive on disk to size it, so it runs on a background QThread like
everything else here, even though there is no network call involved.
"""
from PyQt6.QtCore import QDate, QObject, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (QCalendarWidget, QDialog, QDialogButtonBox, QGroupBox, QHBoxLayout, QLabel,
                             QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from lapbar import manage, prefs

from . import branding


def _fmt_bytes(n) -> str:
    if n is None:
        return "—"
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


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
    def __init__(self, current: str | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Limit how far back it goes")
        layout = QVBoxLayout(self)
        self.calendar = QCalendarWidget()
        self.calendar.setMaximumDate(QDate.currentDate())
        if current:
            y, m, d = (int(p) for p in current.split("-"))
            self.calendar.setSelectedDate(QDate(y, m, d))
        layout.addWidget(self.calendar)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def chosen_date(self) -> str:
        d = self.calendar.selectedDate()
        return f"{d.year():04d}-{d.month():02d}-{d.day():02d}"


class DataWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage data")
        self.resize(480, 600)

        outer = QVBoxLayout(self)
        outer.addWidget(branding.logo_label())
        self.status_label = QLabel("Loading…")
        outer.addWidget(self.status_label)
        self._content = QWidget()
        outer.addWidget(self._content)

        self._thread: QThread | None = None
        self._worker: _StatusWorker | None = None
        self.reload()

    def reload(self):
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
        if self._thread:
            self._thread.quit()
            self._thread.wait()
        super().closeEvent(event)

    def _on_finished(self, result: dict):
        self._thread.quit()
        self._thread.wait()
        if "error" in result:
            self.status_label.setText(f"Could not load: {result['error']}")
            return
        self.status_label.hide()
        new_content = self._build_content(result)
        self.layout().replaceWidget(self._content, new_content)
        self._content.deleteLater()
        self._content = new_content
        self._content.show()

    def _build_content(self, result: dict) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)

        hist = result["history"]
        history_box = QGroupBox("History")
        hl = QVBoxLayout(history_box)
        hl.addWidget(QLabel(f"{hist['stored']} of {hist['activities']} activities have their full data stored here."))
        if hist["no_data"]:
            hl.addWidget(QLabel(f"{hist['no_data']} more are downloaded in the background, a few per refresh."))
        if hist["oldest_day"] and hist["newest_day"]:
            hl.addWidget(QLabel(f"From {hist['oldest_day']} to {hist['newest_day']}."))
        size_line = f"On disk: {_fmt_bytes(hist['raw_bytes'])}"
        if hist["estimated_total_bytes"]:
            size_line += f" (about {_fmt_bytes(hist['estimated_total_bytes'])} once everything is stored)"
        hl.addWidget(QLabel(size_line))

        limit_row = QHBoxLayout()
        limit_row.addWidget(QLabel(f"Limit: {hist['limit'] or 'none'}"))
        choose_button = QPushButton("Choose a date…")
        choose_button.clicked.connect(self._choose_limit)
        limit_row.addWidget(choose_button)
        if hist["limit"]:
            no_limit_button = QPushButton("No limit")
            no_limit_button.clicked.connect(self._clear_limit)
            limit_row.addWidget(no_limit_button)
        limit_row.addStretch(1)
        hl.addLayout(limit_row)
        layout.addWidget(history_box)

        fetch_box = QGroupBox("Fetching, day by day")
        fl = QVBoxLayout(fetch_box)
        days = result["fetch_days"]
        table = QTableWidget(len(days), 3)
        table.setHorizontalHeaderLabels(["Date", "Activities stored", "Requests used"])
        table.verticalHeader().setVisible(False)
        for row, day in enumerate(days):
            table.setItem(row, 0, QTableWidgetItem(day["date"]))
            table.setItem(row, 1, QTableWidgetItem(str(day["activities"])))
            table.setItem(row, 2, QTableWidgetItem(str(day["requests"])))
        table.resizeColumnsToContents()
        fl.addWidget(table)
        layout.addWidget(fetch_box)

        export = result["export"]
        export_box = QGroupBox("DuckDB export")
        el = QVBoxLayout(export_box)
        if export["available"]:
            el.addWidget(QLabel(f"{export['filename']}  ·  {_fmt_bytes(export['file_bytes'])}"))
            el.addWidget(QLabel(f"Continuous updates: {'on' if export['continuous'] else 'off'}"))
            if export["state"].get("running"):
                el.addWidget(QLabel("An export is running now."))
            elif export["state"].get("error"):
                el.addWidget(QLabel(f"Last export: {export['state']['error']}"))
        else:
            el.addWidget(QLabel("DuckDB is not installed, so the export is unavailable."))
        layout.addWidget(export_box)

        layout.addStretch(1)
        return content

    def _choose_limit(self):
        dialog = DateLimitDialog(prefs.load()["history_from"], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            prefs.update(history_from=dialog.chosen_date())
            self.reload()

    def _clear_limit(self):
        prefs.update(history_from=None)
        self.reload()
