"""Build-order step 5: the details window, opened from the main window's records/kudos/comments summary
line -- comments first, then records, then kudos, the same order docs/help.md describes. Downloading
comments/kudos/records can hit the network (details.needs_download() in the backend), so it runs on a
background QThread, the same worker pattern used everywhere else in this app.
"""
import html

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import QDialog, QLabel, QScrollArea, QVBoxLayout, QWidget

from . import branding, fetcher

RECORD_ICON = {"kom": "\U0001f3c6", "pr": "\U0001f3c5"}  # cup for a top-10 KOM place, medal for a PR


def _esc(text: str | None) -> str:
    return html.escape(text or "")


def _fmt_time(seconds) -> str:
    seconds = int(seconds or 0)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _section_title(text: str) -> QLabel:
    label = QLabel(text)
    font = label.font()
    font.setBold(True)
    font.setPointSize(font.pointSize() + 1)
    label.setFont(font)
    return label


class _DetailsWorker(QObject):
    finished = pyqtSignal(dict)

    def __init__(self, activity_id: int):
        super().__init__()
        self.activity_id = activity_id

    @pyqtSlot()
    def run(self):
        try:
            result = fetcher.details_for(self.activity_id)
        except Exception as e:  # noqa: BLE001 - reported back to the window, never raised into the thread
            result = {"error": "unexpected", "message": str(e)}
        self.finished.emit(result)


class DetailsWindow(QDialog):
    def __init__(self, activity_id: int, title: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle(branding.window_title("Activity details" + (f" · {title}" if title else "")))
        self.resize(440, 560)

        outer = QVBoxLayout(self)
        outer.addWidget(branding.header("Activity details", title or None))
        self.status = QLabel("Loading…")
        outer.addWidget(self.status)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.hide()
        outer.addWidget(self._scroll)

        self._thread = QThread()
        self._worker = _DetailsWorker(activity_id)
        self._worker.moveToThread(self._thread)
        self._worker.finished.connect(self._on_finished)
        # DirectConnection: quit() is thread-safe and this makes it run synchronously on the worker thread
        # itself, right where finished.emit() is called, instead of waiting for the main thread's event
        # loop to get around to it (which is a QueuedConnection would, since self._thread lives on the main
        # thread) -- otherwise, closing this window or quitting the app before that queued call is ever
        # processed destroys a QThread that Qt still considers "running", which aborts the whole process.
        self._worker.finished.connect(self._thread.quit, Qt.ConnectionType.DirectConnection)
        self._thread.started.connect(self._worker.run)
        self._thread.start()

    def closeEvent(self, event):
        self._thread.quit()
        self._thread.wait()
        super().closeEvent(event)

    def _on_finished(self, result: dict):
        self._thread.quit()
        self._thread.wait()
        if "error" in result:
            self.status.setText(f"Could not load details: {result.get('message', result.get('error'))}")
            return
        self.status.hide()
        self._scroll.setWidget(self._build_content(result))
        self._scroll.show()

    def _build_content(self, result: dict) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)

        comments = result.get("comments") or []
        records = result.get("records") or []
        kudoers = result.get("kudoers") or []

        layout.addWidget(_section_title(f"Comments ({len(comments)})"))
        if comments:
            for c in comments:
                label = QLabel(f"<b>{_esc(c.get('who'))}</b>: {_esc(c.get('text'))}")
                label.setWordWrap(True)
                layout.addWidget(label)
        else:
            layout.addWidget(QLabel("No comments yet."))

        layout.addWidget(_section_title(f"Records ({len(records)})"))
        if records:
            for r in records:
                icon = RECORD_ICON.get(r.get("kind"), "")
                place = "PR" if r.get("kind") == "pr" else f"#{r.get('rank')}"
                label = QLabel(f"{icon} {place} — {_esc(r.get('name'))} ({_fmt_time(r.get('seconds'))})")
                label.setWordWrap(True)
                layout.addWidget(label)
        else:
            layout.addWidget(QLabel("No records on this ride."))

        layout.addWidget(_section_title(f"Kudos ({len(kudoers)})"))
        kudos_label = QLabel(", ".join(_esc(n) for n in kudoers) if kudoers else "No kudos yet.")
        kudos_label.setWordWrap(True)
        layout.addWidget(kudos_label)

        layout.addStretch(1)
        return content
