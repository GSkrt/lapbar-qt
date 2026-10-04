"""Who shows a popup (a coach nudge, new kudos, new comments).

From the command line, coach.deliver() and alerts.deliver() start a detached `bin/lapbar ... --deliver` process
that shows a desktop notification. An app hosting the backend in-process -- lapbar-qt's tray -- installs a
presenter here instead, and shows the popup itself: no extra process, no command line holding the text, and no
dependency on a Linux notification service, so it works the same on Windows and macOS.
"""
from typing import Callable

# presenter(kind, title, body, url): kind is "coach", "kudos" or "comments"; title/body are plain text.
presenter: Callable[[str, str, str, str | None], None] | None = None
