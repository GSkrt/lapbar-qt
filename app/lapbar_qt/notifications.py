"""Popups (coach nudges, new kudos, new comments) shown by the tray icon itself.

QSystemTrayIcon.showMessage() is Qt's own cross-platform notification: a Windows toast, a macOS notification,
and on Linux the desktop's notification service. Nothing else is needed on any of them -- no notify-send, no
D-Bus code of our own, no helper process -- and the text never appears on a command line. The backend reaches
this through lapbar.popups.presenter, from the background fetch thread; a signal carries it over to the GUI
thread, where the tray lives.
"""
import html

from PyQt6.QtCore import QObject, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QSystemTrayIcon

from lapbar import platforms

POPUP_MS = 20000


def _renders_markup() -> bool:
    """On Linux the message goes to org.freedesktop.Notifications (and the tooltip to a StatusNotifierItem host),
    which render markup -- Qt passes the text on unescaped. Windows and macOS show plain text."""
    return not (platforms.IS_WINDOWS or platforms.IS_MAC)


def plain_line(text: str) -> str:
    """For a notification title or the tray tooltip: the spec makes the title plain text, but some hosts render
    it as markup anyway, so the angle brackets of any tag are swapped for lookalikes -- harmless either way."""
    return text.replace("<", "‹").replace(">", "›") if _renders_markup() else text


def body_text(text: str) -> str:
    """For a notification body, which may be markup on Linux: escaped, so a comment or a name from someone
    else can't add formatting, links or images (verified: Qt otherwise delivers `<a href=...>` as-is)."""
    return html.escape(text, quote=False) if _renders_markup() else text


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
        self._tray.showMessage(plain_line(title), body_text(body), self._tray.icon(), POPUP_MS)

    def _clicked(self):
        if self._url:
            QDesktopServices.openUrl(QUrl(self._url))
        elif self._on_click_without_link:
            self._on_click_without_link()  # a coach nudge: open the main window
