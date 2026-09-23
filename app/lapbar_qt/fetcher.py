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

from lapbar import cli


def fetch_summary(*, manual: bool = False) -> dict:
    args = argparse.Namespace(manual=manual, backfill=3, ftp=0, history_years=0, print=True)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cli.cmd_fetch(args)
    output = buf.getvalue().strip()
    if not output:
        return {"error": "unexpected", "message": "No output from fetch"}
    return json.loads(output)
