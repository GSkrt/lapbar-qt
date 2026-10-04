"""Popups (coach nudges, new kudos, new comments) shown by the tray icon itself.

QSystemTrayIcon.showMessage() is Qt's own cross-platform notification: a Windows toast, a macOS notification,
and on Linux the desktop's notification service. Nothing else is needed on any of them -- no notify-send, no
D-Bus code of our own, no helper process -- and the text never appears on a command line. The backend reaches
this through lapbar.popups.presenter, from the background fetch thread; a signal carries it over to the GUI
thread, where the tray lives.
"""
from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QSystemTrayIcon

POPUP_MS = 20000


class TrayNotifier(QObject):
    _requested = pyqtSignal(str, str, str, object)

    def __init__(self, tray: QSystemTrayIcon, on_click_without_link=None):
        super().__init__()
        self._tray = tray
        self._on_click_without_link = on_click_without_link
        self._url: str | None = None
        # Emitted from the fetch thread, received on this (GUI) thread: Qt queues it across automatically.
        self._requested.connect(self._show)
        tray.messageClicked.connect(self._clicked)

    def present(self, kind: str, title: str, body: str, url: str | None) -> None:
        """lapbar.popups.presenter: safe to call from any thread."""
        self._requested.emit(kind, title, body, url)

    def _show(self, kind: str, title: str, body: str, url):
        self._url = url                    # a click opens the activity on Strava (kudos and comments)
        self._tray.showMessage(title, body, self._tray.icon(), POPUP_MS)

    def _clicked(self):
        if self._url:
            QDesktopServices.openUrl(QUrl(self._url))
        elif self._on_click_without_link:
            self._on_click_without_link()  # a coach nudge: open the main window
