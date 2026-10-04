"""This week so far against last week, for any of the weekly metrics, and the last weeks' totals.

Worked out from the activity list every refresh already carries (summary["activities"]: start, moving time,
distance, climb and Strava's Relative Effort per activity), not from the backend's pre-summed `load` block --
that only has time, distance and effort, and no day-by-day breakdown, which the cumulative chart needs.

"At this point" means the same moment of last week: on Wednesday at 18:00, last week's Monday to Wednesday
18:00. Weeks start on Monday, like Strava's own weekly totals. Activity start times are Strava's local
start times (start_date_local), compared with the local clock.
"""
from datetime import datetime, timedelta

# key: (label, activity field, scale to the unit shown, unit)
METRICS = {
    "time": ("Time", "moving_time_s", 1 / 3600, "h"),
    "distance": ("Distance", "distance_km", 1.0, "km"),
    "climb": ("Climb", "elevation_m", 1.0, "m"),
    "effort": ("Effort", "suffer_score", 1.0, "pts"),
}
# Below this difference the two weeks count as level: a few minutes, a kilometre, a small climb.
EVEN_WITHIN = {"time": 5 / 60, "distance": 1.0, "climb": 20.0, "effort": 3.0}


def week_start(moment: datetime) -> datetime:
    day = datetime(moment.year, moment.month, moment.day)
    return day - timedelta(days=day.weekday())


def _start(activity: dict) -> datetime | None:
    try:
        return datetime.fromisoformat((activity.get("start") or "")[:19])
    except ValueError:
        return None


def value_of(activity: dict, metric: str) -> float:
    _, field, scale, _ = METRICS[metric]
    return float(activity.get(field) or 0) * scale


def available(activities: list[dict]) -> list[str]:
    """The metrics worth offering: effort only when Strava gave Relative Effort for something."""
    return [m for m in METRICS if m != "effort" or any(a.get("suffer_score") for a in activities)]


def _dated(activities: list[dict]):
    for activity in activities:
        start = _start(activity)
        if start is not None:
            yield start, activity


def compare(activities: list[dict], metric: str, now: datetime) -> dict:
    """{"this", "last_same_point", "last_total", "delta", "state"}: values in the metric's unit; state is
    "ahead", "behind", "even", or "idle" when neither week has anything yet."""
    this_start = week_start(now)
    last_start = this_start - timedelta(days=7)
    same_point = last_start + (now - this_start)
    this = last_same = last_total = 0.0
    for start, activity in _dated(activities):
        value = value_of(activity, metric)
        if this_start <= start <= now:
            this += value
        elif last_start <= start < this_start:
            last_total += value
            if start < same_point:
                last_same += value
    delta = this - last_same
    if this == 0 and last_total == 0:
        state = "idle"
    elif abs(delta) < EVEN_WITHIN[metric]:
        state = "even"
    else:
        state = "ahead" if delta > 0 else "behind"
    return {"this": this, "last_same_point": last_same, "last_total": last_total, "delta": delta, "state": state,
            "days_left": 7 - now.weekday()}


def cumulative(activities: list[dict], metric: str, now: datetime) -> dict:
    """Running totals through the week, as step points (x in days since Monday, 0..7):
    {"last": [(x, total), ...] over the whole of last week, "this": [...] up to now}."""
    this_start = week_start(now)
    last_start = this_start - timedelta(days=7)

    def steps(begin: datetime, end: datetime) -> list[tuple[float, float]]:
        points, total = [(0.0, 0.0)], 0.0
        for start, activity in sorted(((s, a) for s, a in _dated(activities) if begin <= s < end),
                                      key=lambda pair: pair[0]):
            total += value_of(activity, metric)
            points.append(((start - begin).total_seconds() / 86400, total))
        points.append(((end - begin).total_seconds() / 86400, total))
        return points

    return {"last": steps(last_start, this_start), "this": steps(this_start, now)}


def weekly_totals(activities: list[dict], metric: str, now: datetime, weeks: int = 12) -> list[tuple[datetime, float]]:
    """[(Monday, total), ...] for the last `weeks` weeks, oldest first; the last one is this week so far."""
    first = week_start(now) - timedelta(days=7 * (weeks - 1))
    totals = {first + timedelta(days=7 * i): 0.0 for i in range(weeks)}
    for start, activity in _dated(activities):
        if first <= start <= now:
            totals[week_start(start)] += value_of(activity, metric)
    return sorted(totals.items())


def fmt(value: float, metric: str) -> str:
    if metric == "time":
        minutes = round(value * 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours}h {minutes:02d}m" if hours else f"{minutes} min"
    if metric == "distance":
        return f"{value:.1f} km"
    if metric == "climb":
        return f"{round(value)} m"
    return f"{round(value)} effort"


def headline(result: dict, metric: str) -> str:
    state = result["state"]
    if state == "idle":
        return "No training this week or last week yet"
    if state == "even":
        return "On par with last week at this point"
    return f"{fmt(abs(result['delta']), metric)} {'ahead of' if state == 'ahead' else 'behind'} last week at this point"


def detail(result: dict, metric: str) -> str:
    left = result["days_left"]
    return (f"{fmt(result['this'], metric)} so far · last week {fmt(result['last_same_point'], metric)} by now, "
            f"{fmt(result['last_total'], metric)} in all · {left} day{'' if left == 1 else 's'} left")
