"""Background fetch on a QThread, verified in PLAN.md: a persistent worker thread does the (blocking) Strava
call, a QTimer living on that same thread drives the periodic interval, and the result comes back to the UI
thread as an ordinary signal -- Qt queues it across threads automatically, so no manual invokeMethod needed.
"""
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal, pyqtSlot

from . import fetcher, tooltip

REFRESH_INTERVAL_MS = 15 * 60 * 1000  # matches LapBar's own documented default (docs/help.md: "default 15 minutes")


class FetchWorker(QObject):
    tooltipReady = pyqtSignal(str)
    summaryReady = pyqtSignal(dict)  # the raw fetch result, for anything that needs more than the tooltip text
    needsSetup = pyqtSignal()  # emitted once, the first time a fetch reports no (or no longer valid) credentials

    def __init__(self):
        super().__init__()
        self._last_summary: dict | None = None
        self._timer: QTimer | None = None
        self._setup_signalled = False

    def start(self):
        # Created here, not in __init__, so the QTimer is owned by whichever thread calls start() --
        # moveToThread() must happen before this, or the timer would fire on the wrong thread.
        self._timer = QTimer()
        self._timer.timeout.connect(self.fetch)
        self._timer.start(REFRESH_INTERVAL_MS)
        self.fetch()

    @pyqtSlot()
    def fetch(self):
        try:
            result = fetcher.fetch_summary()
        except Exception as e:  # noqa: BLE001 - a bad refresh must never take the tray icon down with it
            self.tooltipReady.emit(tooltip.build_tooltip(self._last_summary, {"code": "unexpected", "message": str(e)}))
            return
        if "error" in result:
            code = result["error"]
            self.tooltipReady.emit(tooltip.build_tooltip(self._last_summary, {"code": code, "message": result.get("message")}))
            if code in tooltip.NEEDS_SETUP_CODES and not self._setup_signalled:
                self._setup_signalled = True
                self.needsSetup.emit()
            return
        self._setup_signalled = False  # a later successful fetch means credentials are good again
        self._last_summary = result
        self.tooltipReady.emit(tooltip.build_tooltip(result))
        self.summaryReady.emit(result)


def start_background_refresh(on_tooltip, on_needs_setup=None, on_summary=None) -> tuple[QThread, FetchWorker]:
    """Owns the thread's lifetime; caller keeps the returned objects alive (e.g. as attributes on the tray)."""
    thread = QThread()
    worker = FetchWorker()
    worker.moveToThread(thread)
    worker.tooltipReady.connect(on_tooltip)
    if on_needs_setup:
        worker.needsSetup.connect(on_needs_setup)
    if on_summary:
        worker.summaryReady.connect(on_summary)
    thread.started.connect(worker.start)
    thread.start()
    return thread, worker
