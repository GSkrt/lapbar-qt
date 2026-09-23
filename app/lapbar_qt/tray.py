"""Build-order step 4: left-click toggles the main window (mainwindow.py), read-only, with real fetched
data -- alongside the tooltip (step 2), the right-click menu's real actions (step 3), and the first-run
credentials wizard (setup_wizard.py), offered from the menu always and popped automatically the first time
a fetch reports nothing is set up yet.
"""
import sys

from lapbar import mute
from PyQt6.QtCore import QMetaObject, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from . import mainwindow, setup_wizard, worker


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # a tray-only app has no window to keep it alive

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("No system tray available on this desktop.", file=sys.stderr)
        return 1

    # Placeholder only -- a real tray-sized icon is still to be designed. Qt's own built-in standard icon
    # needs no asset file and no icon theme to be installed, so it renders the same everywhere until then.
    tray = QSystemTrayIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
    tray.setToolTip("lapbar-qt · Loading…")

    main_window = mainwindow.MainWindow()

    def toggle_main_window(reason=None):
        if reason is not None and reason != QSystemTrayIcon.ActivationReason.Trigger:
            return  # only a left-click (Trigger) should open/close the window; ignore other reasons
        if main_window.isVisible():
            main_window.hide()
        else:
            main_window.show()
            main_window.raise_()
            main_window.activateWindow()

    tray.activated.connect(toggle_main_window)

    menu = QMenu()

    def open_setup():
        # fetch() is a @pyqtSlot on a worker living on the background thread; invokeMethod queues this call
        # onto that thread instead of running it here, the same cross-thread pattern QThread signals use.
        if setup_wizard.run_setup_wizard():
            QMetaObject.invokeMethod(fetch_worker, "fetch", Qt.ConnectionType.QueuedConnection)

    def refresh_now():
        QMetaObject.invokeMethod(fetch_worker, "fetch", Qt.ConnectionType.QueuedConnection)

    refresh_action = QAction("Refresh now", menu)
    refresh_action.triggered.connect(refresh_now)
    menu.addAction(refresh_action)

    # mute.is_muted()/set_muted() are just a flag-file check, safe to call straight from the GUI thread --
    # unlike the fetch, there is no network call here that would need a background thread.
    mute_action = QAction("Mute kudos and comment alerts", menu)
    mute_action.setCheckable(True)
    menu.aboutToShow.connect(lambda: mute_action.setChecked(mute.is_muted()))
    mute_action.triggered.connect(lambda checked: mute.set_muted(checked))
    menu.addAction(mute_action)

    menu.addSeparator()

    setup_action = QAction("Set up credentials…", menu)
    setup_action.triggered.connect(open_setup)
    menu.addAction(setup_action)

    menu.addSeparator()

    quit_action = QAction("Quit", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)

    thread, fetch_worker = worker.start_background_refresh(tray.setToolTip, open_setup, main_window.update_summary)

    def shutdown():
        thread.quit()
        thread.wait()

    app.aboutToQuit.connect(shutdown)

    tray.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
