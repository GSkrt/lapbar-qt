"""Build-order step 6: the FTP, refresh-interval and reset-account dialogs, alongside everything the menu
already had (step 3), the main window (step 4), the details window (step 5), the tooltip (step 2), and the
first-run credentials wizard (setup_wizard.py), offered from the menu always and popped automatically the
first time a fetch reports nothing is set up yet.
"""
import sys

from lapbar import mute, prefs, setup
from PyQt6.QtCore import QMetaObject, Q_ARG, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QStyle, QSystemTrayIcon

from . import mainwindow, settings_dialogs, setup_wizard, worker


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

    last_summary: dict = {}

    def track_summary(summary: dict):
        last_summary.clear()
        last_summary.update(summary)

    def open_setup():
        # fetch() is a @pyqtSlot on a worker living on the background thread; invokeMethod queues this call
        # onto that thread instead of running it here, the same cross-thread pattern QThread signals use.
        if setup_wizard.run_setup_wizard():
            QMetaObject.invokeMethod(fetch_worker, "fetch", Qt.ConnectionType.QueuedConnection)

    def refresh_now():
        QMetaObject.invokeMethod(fetch_worker, "fetch", Qt.ConnectionType.QueuedConnection)

    def open_ftp_dialog():
        estimate = (last_summary.get("fitness") or {}).get("ftp_estimate")
        dialog = settings_dialogs.FtpDialog(prefs.load()["ftp"], estimate)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            prefs.update(ftp=dialog.spin.value())
            refresh_now()  # recalculates load/fitness at once with the new value, same as Panel.qml's setFtp()

    def open_interval_dialog():
        dialog = settings_dialogs.IntervalDialog(prefs.load()["refresh_interval_sec"])
        if dialog.exec() == QDialog.DialogCode.Accepted:
            prefs.update(refresh_interval_sec=dialog.chosen)
            QMetaObject.invokeMethod(fetch_worker, "set_interval", Qt.ConnectionType.QueuedConnection,
                                     Q_ARG(int, dialog.chosen))

    def open_reset_dialog():
        confirmed = QMessageBox.question(
            None, "Reset account",
            "This removes your saved credentials and sign-in. Your downloaded activities stay. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        removed = setup.forget(out=lambda *_: None)
        QMessageBox.information(None, "Reset account", "Removed: " + (", ".join(removed) or "nothing"))
        refresh_now()

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

    interval_action = QAction("Refresh every…", menu)
    interval_action.triggered.connect(open_interval_dialog)
    menu.addAction(interval_action)

    ftp_action = QAction("FTP…", menu)
    ftp_action.triggered.connect(open_ftp_dialog)
    menu.addAction(ftp_action)

    menu.addSeparator()

    setup_action = QAction("Set up credentials…", menu)
    setup_action.triggered.connect(open_setup)
    menu.addAction(setup_action)

    reset_action = QAction("Reset account…", menu)
    reset_action.triggered.connect(open_reset_dialog)
    menu.addAction(reset_action)

    menu.addSeparator()

    quit_action = QAction("Quit", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)

    thread, fetch_worker = worker.start_background_refresh(tray.setToolTip, open_setup, main_window.update_summary)
    fetch_worker.summaryReady.connect(track_summary)

    def shutdown():
        thread.quit()
        thread.wait()

    app.aboutToQuit.connect(shutdown)

    tray.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
