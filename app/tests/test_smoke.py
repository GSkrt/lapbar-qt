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
