"""The app's own windows and popups, headless: proves it starts and works without anything Linux-specific."""
import importlib
import pkgutil
import threading

from PyQt6.QtCore import QCoreApplication, QThread
from PyQt6.QtWidgets import QSystemTrayIcon


def _drain(app, rounds=20):
    for _ in range(rounds):
        app.processEvents()


def test_every_module_imports(qapp):
    import lapbar_qt
    for module in pkgutil.iter_modules(lapbar_qt.__path__):
        importlib.import_module(f"lapbar_qt.{module.name}")


def test_the_windows_open_without_any_data_yet(qapp):
    from lapbar_qt import branding, datawindow, mainwindow
    main = mainwindow.MainWindow()
    main.show()
    data = datawindow.DataWindow()
    data.show()
    _drain(qapp)
    assert not branding.logo_pixmap().isNull()            # the LapBar logo ships with the app and renders
    main.close()
    data.close()


def test_popups_from_the_fetch_thread_are_shown_by_the_tray_on_the_gui_thread(qapp, monkeypatch):
    from lapbar import alerts, popups
    from lapbar_qt import notifications
    tray = QSystemTrayIcon()
    shown = []
    monkeypatch.setattr(tray, "showMessage", lambda title, body, icon, ms: shown.append(
        (title, body, QThread.currentThread() is QCoreApplication.instance().thread())))
    notifier = notifications.TrayNotifier(tray)
    monkeypatch.setattr(popups, "presenter", notifier.present)

    event = {"count": 2, "total": 5, "from": ["Ana Č.", "Bo D."], "name": "Lunch ride",
             "url": "https://www.strava.com/activities/42"}
    worker = threading.Thread(target=alerts.deliver, args=("kudos", event))   # as the background fetch would
    worker.start()
    worker.join()
    _drain(qapp)
    assert len(shown) == 1
    title, body, on_gui_thread = shown[0]
    assert "2 new kudos" in title and "Ana Č." in body and on_gui_thread


def test_try_one_shows_a_sample_nudge_through_the_tray(qapp, monkeypatch):
    from lapbar import popups
    from lapbar_qt import mainwindow
    shown = []
    monkeypatch.setattr(popups, "presenter", lambda *a: shown.append(a))
    main = mainwindow.MainWindow()
    main._tone_radios["drill"].setChecked(True)
    main.try_one_button.click()
    assert shown and shown[0][0] == "coach" and shown[0][3] is None
    main.close()
