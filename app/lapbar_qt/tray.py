"""Build-order step 2: the tray tooltip now carries real backend data, refreshed on a timer via a
background thread (see worker.py) so the fetch never blocks the tray icon or its menu. Also wires up the
first-run credentials wizard (setup_wizard.py): offered from the menu always, and popped automatically the
first time a fetch reports there is nothing set up yet, so a non-technical user isn't left staring at a
tooltip with no idea what to do.
"""
import sys
from pathlib import Path

from PyQt6.QtCore import QMetaObject, Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import setup_wizard, worker

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

    def open_setup():
        # fetch() is a @pyqtSlot on a worker living on the background thread; invokeMethod queues this call
        # onto that thread instead of running it here, the same cross-thread pattern QThread signals use.
        if setup_wizard.run_setup_wizard():
            QMetaObject.invokeMethod(fetch_worker, "fetch", Qt.ConnectionType.QueuedConnection)

    setup_action = QAction("Set up credentials…", menu)
    setup_action.triggered.connect(open_setup)
    menu.addAction(setup_action)

    menu.addSeparator()

    quit_action = QAction("Quit", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)

    thread, fetch_worker = worker.start_background_refresh(tray.setToolTip, open_setup)

    def shutdown():
        thread.quit()
        thread.wait()

    app.aboutToQuit.connect(shutdown)

    tray.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
