"""Build-order step 2: the tray tooltip now carries real backend data, refreshed on a timer via a
background thread (see worker.py) so the fetch never blocks the tray icon or its menu.
"""
import sys
from pathlib import Path

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import worker

ICON_PATH = Path(__file__).parent / "assets" / "icon.png"


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # a tray-only app has no window to keep it alive

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("No system tray available on this desktop.", file=sys.stderr)
        return 1

    tray = QSystemTrayIcon(QIcon(str(ICON_PATH)))
    tray.setToolTip("lapbar-qt · Loading…")

    menu = QMenu()
    quit_action = QAction("Quit", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)

    thread, fetch_worker = worker.start_background_refresh(tray.setToolTip)

    def shutdown():
        thread.quit()
        thread.wait()

    app.aboutToQuit.connect(shutdown)

    tray.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
