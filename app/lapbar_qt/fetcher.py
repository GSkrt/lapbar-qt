"""Calls the real backend fetch (lapbar.cli.cmd_fetch) in-process and returns its --print summary.

Reuses the actual, already-tested CLI logic rather than re-implementing ratelimit/backfill/ftp/history
handling here: cmd_fetch does the real work (rate-limit check, Strava fetch, cache write, coach tick,
kudos/comment alerts, DuckDB export) and, with --print, writes the same JSON Panel.qml already parses
from its subprocess today. We just capture that stdout instead of spawning a process for it.
"""
import argparse
import contextlib
import io
import json

from lapbar import auth, cli, prefs, ratelimit, streams, vault
from lapbar.http import HttpError


def fetch_summary(*, manual: bool = False) -> dict:
    args = argparse.Namespace(manual=manual, backfill=3, ftp=prefs.load()["ftp"], history_years=0, print=True)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.cmd_fetch(args)
    output = buf.getvalue().strip()
    if not output:
        return {"error": "unexpected", "message": "No output from fetch"}
    return json.loads(output)


def details_for(activity_id: int) -> dict:
    """Records (PRs, KOMs), who gave kudos, and comments for one activity -- reuses cli.cmd_details the
    same way fetch_summary() reuses cmd_fetch."""
    args = argparse.Namespace(activity=activity_id)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.cmd_details(args)
    output = buf.getvalue().strip()
    if not output:
        return {"error": "unexpected", "message": "No output from details"}
    return json.loads(output)


def chart_data_for(activity_id: int) -> dict:
    """Chart data for one activity, full resolution when it's archived on disk (streams.detail()) so the
    window can zoom all the way in, else the averaged overview (streams.get(), downloading if needed) --
    the same fallback streams.detail()'s own docstring describes. Reuses the CLI's rate-limit check, auth
    and activity lookup (cli._activity_for, the same helper cmd_streams/cmd_details use) rather than
    duplicating them; cmd_streams itself only prints a summary to stdout (its JSON goes to a file for the
    Quickshell window to read), which is not useful here since this runs in-process.
    """
    try:
        if streams.cached(activity_id) is None:
            ratelimit.check("action")          # stored data costs nothing, so only a download is checked
        token = auth.default_token_source().access_token()
        activity = cli._activity_for(activity_id, token)
        path = streams.detail(activity)
        if path is not None:
            return json.loads(path.read_text())
        data = streams.get(token, activity, refresh=False)
    except (auth.NotConfigured, auth.NotAuthorized, vault.VaultUnavailable, ratelimit.BudgetExhausted,
            HttpError, OSError) as e:
        code, message = cli._classify(e)
        return {"error": code, "message": message}
    if data is None:
        return {"error": "no_streams", "message": "Strava has no time series for this activity (for example a manual entry)."}
    return data
