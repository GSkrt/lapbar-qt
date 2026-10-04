"""Builds the tray tooltip text from a fetch summary. A Python port of Panel.qml's `barTooltip` and its
helpers (`loadHeadline`, `signed`, `fitnessStatusName`, `budgetLine`, `fmtLoad`, `fmtDuration`, `sportName`),
so the tray's tooltip says the same things the Omarchy popup's tooltip does, just without a bar frame to
show it from. `loadMetric` has no equivalent backend preference yet (it's an Omarchy/Quickshell widget
setting today), so this always uses Panel.qml's own default, "time".
"""
from datetime import datetime, timezone

from . import weekcompare

FITNESS_STATUS_NAME = {
    "starting": "Getting started", "very_fresh": "Very fresh", "fresh": "Fresh", "balanced": "Balanced",
    "building": "Building", "overreaching": "Very tired",
}

NEEDS_SETUP_CODES = ("not_configured", "not_authorized")


def signed(v: float) -> str:
    n = round(v)
    return f"+{n}" if n > 0 else (f"−{abs(n)}" if n < 0 else "0")


def sport_name(sport: str | None) -> str:
    if not sport:
        return ""
    out = []
    for i, c in enumerate(sport):
        if i > 0 and c.isupper() and sport[i - 1].islower():
            out.append(" ")
        out.append(c)
    return "".join(out)


def fmt_duration(seconds: float) -> str:
    h, m = divmod(int(seconds) // 60, 60)
    return f"{h}h {m:02d}m" if h > 0 else f"{m} min"


def load_headline(summary: dict | None, now: datetime | None = None) -> str:
    """Time this week so far against last week at the same moment (weekcompare.py does the work).

    The backend's own `load` block has no ahead/behind state -- Panel.qml worked that out in QML -- so reading
    one from it always came out as "0 min behind"."""
    if not summary or not summary.get("activities"):
        return ""
    result = weekcompare.compare(summary["activities"], "time", now or datetime.now())
    return "" if result["state"] == "idle" else weekcompare.headline(result, "time")


def budget_line(budget: dict | None) -> str:
    if not budget:
        return ""
    line = f"Strava requests today: {budget.get('daily_used')} of {budget.get('daily_limit')}"
    if budget.get("auto_paused"):
        line += " · auto-refresh paused, manual refresh still works"
    return line


def _updated_line(iso: str | None) -> str:
    if not iso:
        return "Strava updated"
    try:
        when = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).astimezone()
    except ValueError:
        return "Strava updated"
    return "Strava updated " + when.strftime("%a %H:%M")


def build_tooltip(summary: dict | None, error: dict | None = None) -> str:
    """`summary` is the last good fetch result (or None if there has never been one); `error` is set when
    the most recent fetch failed, and is layered on top rather than replacing whatever is already shown.
    """
    if error and error.get("code") in NEEDS_SETUP_CODES:
        return "lapbar-qt · click to set up"
    if not summary:
        if error:
            return f"lapbar-qt · {error.get('message', error.get('code', 'error'))}"
        return "lapbar-qt · Loading…"

    latest = summary.get("latest") or {}
    lines = [_updated_line(summary.get("updated"))]
    if latest.get("name"):
        lines.append(f"{latest['name']} · {sport_name(latest.get('sport'))}")
    kudos, prs = latest.get("kudos", 0), latest.get("prs", 0)
    if latest:
        lines.append(f"{kudos} {'kudo' if kudos == 1 else 'kudos'}  ·  {prs} {'PR' if prs == 1 else 'PRs'}")

    headline = load_headline(summary)
    if headline:
        lines.append(headline)

    fitness = summary.get("fitness") or {}
    now, tomorrow = fitness.get("current"), fitness.get("tomorrow")
    if now and now.get("status") != "starting":
        status = FITNESS_STATUS_NAME.get(now.get("status"), "").lower()
        lines.append(f"Form {signed(now['form'])} ({status}) · fitness {round(now['fitness'])} "
                     f"· fatigue {round(now['fatigue'])}")
        if tomorrow:
            tstatus = FITNESS_STATUS_NAME.get(tomorrow.get("status"), "").lower()
            lines.append(f"Tomorrow {signed(tomorrow['form'])} ({tstatus}) with today's work counted")

    line = budget_line(summary.get("budget"))
    if line:
        lines.append(line)
    if summary.get("muted"):
        lines.append("Kudos alerts muted")
    if error and error.get("code") not in NEEDS_SETUP_CODES:
        lines.append(f"Last refresh failed: {error.get('message', error.get('code', 'error'))}")

    return "\n".join(lines)
