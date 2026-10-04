"""This week against last week: same moment of the week, every metric, and the weekly totals."""
from datetime import datetime

from lapbar_qt import tooltip, weekcompare

# Thursday 1 October 2026, 18:00. This week started Monday 28 September; last week Monday 21 September.
NOW = datetime(2026, 10, 1, 18, 0)


def ride(start: str, minutes: int, km: float = 0.0, climb: int = 0, effort: int | None = None) -> dict:
    return {"start": start + "Z", "moving_time_s": minutes * 60, "distance_km": km, "elevation_m": climb,
            "suffer_score": effort}


ACTIVITIES = [
    ride("2026-09-22T07:00:00", 60, 30, 300, 50),     # last week Tuesday
    ride("2026-09-24T17:00:00", 120, 60, 800, 120),   # last week Thursday, before 18:00: counts "by now"
    ride("2026-09-24T19:00:00", 30, 10, 50, 20),      # last week Thursday, after 18:00: only in last week's total
    ride("2026-09-27T10:00:00", 90, 45, 600, 80),     # last week Sunday
    ride("2026-09-30T06:00:00", 45, 20, 150, 30),     # this week Wednesday
    ride("2026-10-01T19:00:00", 60, 25, 200, 40),     # this week, but later today: not done yet
    ride("2026-08-01T10:00:00", 600, 300, 3000, 500), # long ago: in no week here
]


def test_it_compares_with_last_week_up_to_the_same_moment():
    result = weekcompare.compare(ACTIVITIES, "time", NOW)
    assert result["this"] == 0.75                             # 45 min, the 19:00 ride hasn't happened yet
    assert result["last_same_point"] == 3.0                   # Tuesday 60 + Thursday-before-18:00 120 min
    assert result["last_total"] == 5.0                        # the whole of last week
    assert result["state"] == "behind" and result["days_left"] == 4
    assert weekcompare.headline(result, "time") == "2h 15m behind last week at this point"


def test_every_metric_is_compared():
    assert weekcompare.compare(ACTIVITIES, "distance", NOW)["delta"] == 20 - 90
    assert weekcompare.compare(ACTIVITIES, "climb", NOW)["delta"] == 150 - 1100
    assert weekcompare.compare(ACTIVITIES, "effort", NOW)["delta"] == 30 - 170


def test_ahead_even_and_idle():
    ahead = weekcompare.compare([ride("2026-09-29T08:00:00", 90)], "time", NOW)
    assert ahead["state"] == "ahead" and weekcompare.headline(ahead, "time").startswith("1h 30m ahead")
    even = weekcompare.compare([ride("2026-09-29T08:00:00", 62), ride("2026-09-22T08:00:00", 60)], "time", NOW)
    assert even["state"] == "even"
    assert weekcompare.compare([], "time", NOW)["state"] == "idle"


def test_effort_is_offered_only_when_strava_gave_it():
    assert "effort" in weekcompare.available(ACTIVITIES)
    assert weekcompare.available([ride("2026-09-29T08:00:00", 60)]) == ["time", "distance", "climb"]


def test_the_running_totals_end_where_the_comparison_says():
    series = weekcompare.cumulative(ACTIVITIES, "time", NOW)
    assert series["last"][-1] == (7.0, 5.0)
    assert series["this"][-1][1] == 0.75 and abs(series["this"][-1][0] - 3.75) < 1e-9   # Thursday 18:00


def test_weekly_totals_end_with_this_week_so_far():
    weeks = weekcompare.weekly_totals(ACTIVITIES, "time", NOW, weeks=3)
    assert [monday.day for monday, _ in weeks] == [14, 21, 28]
    assert [total for _, total in weeks] == [0.0, 5.0, 0.75]


def test_the_tray_tooltip_no_longer_says_zero_behind():
    assert tooltip.load_headline({"activities": ACTIVITIES}, NOW) == "2h 15m behind last week at this point"
    assert tooltip.load_headline({"activities": []}, NOW) == ""
