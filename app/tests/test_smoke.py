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


def _summary():
    """A refresh result shaped like the real one (strava.fetch() plus the CLI's additions), with made-up values."""
    from datetime import date, timedelta
    today = date.today()
    days = []
    for i in range(60, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        days.append({"date": d, "load": float(i % 7 * 10), "fitness": 20 + i % 5, "fatigue": 25 - i % 9,
                     "form": float((i % 11) - 5), "warmup": False})
    ride = {"id": 42, "start": f"{today.isoformat()}T17:00:00Z", "sport": "Ride", "family": "ride",
            "name": "Evening Ride", "distance_km": 17.1, "elevation_m": 286, "moving_time_s": 2460,
            "elapsed_time_s": 2600, "avg_speed_kmh": 24.9, "max_speed_kmh": 51.0, "pace_s": None,
            "avg_watts": 200, "avg_heartrate": 130, "avg_cadence": 74, "url": "https://www.strava.com/activities/42"}
    period = {"distance_km": 17.1, "elevation_m": 286, "moving_time_s": 2460, "count": 1}
    week = {"moving_time_s": 2460, "distance_km": 17.1, "effort": 40}
    return {"provider": "strava", "updated": f"{today.isoformat()}T18:00:00Z", "latest": ride,
            "today": period, "week": period, "month": period, "year": period,
            "days": {today.isoformat(): {**period, "families": ["ride"]}},
            "history": {"years": [], "from": "2026-01-01", "complete": True}, "archived_ids": [42],
            "load": {"this_week": week, "last_week": week, "last_week_same_point": week, "days_left": 3,
                     "has_effort": True},
            "fitness": {"current": {**days[-1], "status": "balanced"},
                        "tomorrow": {"date": (today + timedelta(days=1)).isoformat(), "form": -2.0,
                                     "status": "balanced"},
                        "days": days, "sources": {"effort": 10, "time": 2}, "ftp": None, "ftp_estimate": None},
            "activities": [ride], "coach": None, "muted": False}


def test_a_real_refresh_fills_the_main_window_and_draws_the_fitness_plot(qapp):
    from lapbar_qt import mainwindow
    main = mainwindow.MainWindow()
    main.show()
    main.update_summary(_summary())            # raised NameError once, leaving the plot empty -- never again
    _drain(qapp)
    assert len(main.fitness_plot._plots) == 2  # fitness/fatigue lines on top, form bars below
    assert main.fitness_plot.height() > 0
    assert main.stats_layout.count() > 0       # the ride's stats rows were drawn
    assert main.calendar_panel.calendar.archived_keys == {main.calendar_panel._today.isoformat()}
    main.close()


def test_the_week_panel_shows_where_you_stand_and_switches_metric(qapp):
    from lapbar_qt import mainwindow
    main = mainwindow.MainWindow()
    main.update_summary(_summary())
    panel = main.week_panel
    assert "last week" in panel.headline.text()
    keys = [panel.metric_box.itemData(i) for i in range(panel.metric_box.count())]
    assert keys == ["time", "distance", "climb"]                # no Relative Effort in this summary
    panel.metric_box.setCurrentIndex(1)
    assert panel.current_metric() == "distance" and "km" in panel.detail.text()
    main.close()


def test_the_data_window_has_the_export_controls_and_describes_the_database(qapp):
    import time

    from PyQt6.QtWidgets import QGroupBox, QPushButton
    from lapbar import manage
    from lapbar_qt import datawindow
    window = datawindow.DataWindow()
    window.show()
    deadline = time.monotonic() + 10
    while window._status is None and time.monotonic() < deadline:   # manage.status() runs on a thread
        qapp.processEvents()
    assert window._status is not None
    buttons = {b.text() for b in window.findChildren(QPushButton)}
    assert {"Export now", "Rebuild", "Choose folder…", "Default"} <= buttons
    boxes = {b.title() for b in window.findChildren(QGroupBox)}
    assert {"Export to DuckDB", "History", "Fetching, day by day"} <= boxes
    assert {t["table"] for t in manage.status()["schema"]} <= boxes                # every table is described
    assert window.windowTitle() == "LapBar · Data"
    window.close()


def test_text_from_strava_is_never_read_as_markup(qapp, monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel
    from lapbar import platforms
    from lapbar_qt import branding, mainwindow, notifications
    sneaky = "<b>Ride</b> <a href='https://evil.example'>x</a>"
    main = mainwindow.MainWindow()
    summary = _summary()
    summary["latest"]["name"] = sneaky
    main.update_summary(summary)
    assert main.ride_title.textFormat() == Qt.TextFormat.PlainText and sneaky in main.ride_title.text()
    header = branding.header("Activity metrics", sneaky)
    assert all(label.textFormat() == Qt.TextFormat.PlainText for label in header.findChildren(QLabel)
               if sneaky in label.text())
    monkeypatch.setattr(platforms, "IS_WINDOWS", False)
    monkeypatch.setattr(platforms, "IS_MAC", False)            # Linux: notifications render markup
    assert notifications.body_text(sneaky) == "&lt;b&gt;Ride&lt;/b&gt; &lt;a href='https://evil.example'&gt;x&lt;/a&gt;"
    assert "<" not in notifications.plain_line(sneaky) and ">" not in notifications.plain_line(sneaky)
    monkeypatch.setattr(platforms, "IS_WINDOWS", True)         # Windows: plain text, shown as it is
    assert notifications.body_text(sneaky) == sneaky and notifications.plain_line(sneaky) == sneaky
    main.close()


def test_the_tray_escapes_what_it_shows_on_linux(qapp, monkeypatch):
    from lapbar import platforms
    from lapbar_qt import notifications
    monkeypatch.setattr(platforms, "IS_WINDOWS", False)
    monkeypatch.setattr(platforms, "IS_MAC", False)
    tray = QSystemTrayIcon()
    shown = []
    monkeypatch.setattr(tray, "showMessage", lambda title, body, icon, ms: shown.append((title, body)))
    notifications.TrayNotifier(tray).present("comments", "Eve <i>X</i>", "<b>hi</b> & bye", None)
    _drain(qapp)
    assert shown == [("Eve ‹i›X‹/i›", "&lt;b&gt;hi&lt;/b&gt; &amp; bye")]


def test_it_starts_without_a_console(monkeypatch):
    """A windowed Windows .exe (and pythonw) has sys.stdout = None: nothing may assume a console at import."""
    import importlib
    import sys

    from lapbar import cli, setup
    monkeypatch.setattr(sys, "stdout", None)
    importlib.reload(setup)        # it decided on terminal colours with sys.stdout.isatty() when loaded
    importlib.reload(cli)
