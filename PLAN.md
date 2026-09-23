# UI plan: tray icon + standard windows

Not started. This is the agreed shape before any of it gets built.

## The tray icon

A `QSystemTrayIcon`, the whole always-visible presence (no bar text frame — that part of LapBar doesn't carry
over, per the README).

- **Left-click:** opens (or raises, if already open) the **main window** — see below. Clicking again while it's
  open toggles it closed, matching how the Omarchy popup behaves today.
- **Right-click:** shows a `QMenu` with what is in Panel.qml's **⋮ menu** today: Refresh now, Mute/Unmute kudos
  and comment alerts, Refresh every … (opens the interval picker), FTP … (opens the FTP dialog), Manage data …
  (opens the data window), How to use … (opens the how-to window or just links the README — undecided, see
  below), Update credentials or sign in …, Open Strava API settings, About, Reset account.
- **Middle-click:** refresh now — carried over from the bar widget's middle-click, `QSystemTrayIcon` reports this
  as a distinct click type so it's a direct match.
- **Tooltip:** the same text the bar widget's hover tooltip builds today (last updated, kudos/PRs, load vs last
  week, form, request budget, mute state, last-refresh error) — this is where that information lives now that
  there's no cycling bar text.

## The main window (left-click target)

Panel.qml's popup content, minus the ⋮ menu (moved to the tray's right-click) and minus the bar-frame concept
entirely — everything else carries over as a standard, always-a-window `QMainWindow`:

- the ride: name, date, route trace, stats, and the one-line records/kudos/comments summary that opens the
  details window
- fitness, fatigue and form (including tomorrow's form), with **Open chart** opening the fitness chart window
- training load vs last week
- the calendar
- the skip-today chips and the Motivational quotes radio
- totals (today/week/month/year)
- the Powered by Strava logo

## Child windows opened from the main window — all standard `QWidget`/`QDialog` windows, not floating panels

| Today (Omarchy/Quickshell) | Here |
|---|---|
| `activity/shell.qml` (details) | a details window: comments, records, kudos |
| `charts/shell.qml` (ride charts) | a charts window, built on **PyQtGraph** — see Decided below |
| `charts/shell.qml` (fitness chart, same window/different doc) | same charts window, fed the fitness doc |
| `manage/shell.qml` (data window) | a data window, built on `manage.status()`, already carried over |
| `help/shell.qml` (how-to) | undecided: port the guide-rendering window, or just link the README |
| the FTP / interval / reset submenus in Panel.qml's menu | small dialogs, opened from the tray's right-click menu |

## Decided

- **Charts: PyQtGraph** (`python-pyqtgraph`, available via pacman/`extra`, MIT-licensed, 0.14.0 confirmed
  installable and working on this machine). Its built-in downsampling (`setDownsampling(method='peak')`, the
  library's own default) is the same min/max-per-pixel-column technique `charts/logic.js` was hand-built around
  this session for the Quickshell version — verified, not assumed: fed it a synthetic 2,000,000-sample series
  with a single-sample spike, and a fully-zoomed-out render took 14 ms and still showed the spike (6,370 points
  on screen for the real-ride-scale 19,113-sample case, 2.2 ms). Multiple linked, shared-cursor plots (the
  elevation/speed/heart-rate/power stack) are a native PyQtGraph pattern (`setXLink()`, `InfiniteLine` for the
  crosshair), not something to build from scratch the way the Quickshell canvas version was. Replaces the
  hand-rolled `QPainter`-vs-`QtCharts` dilemma this plan started with.
- **Notifications: a direct `org.freedesktop.Notifications` D-Bus call via `QtDBus`**, not
  `QSystemTrayIcon.showMessage()` (which has no action-button support at all). Verified end to end, not assumed:
  a real `Notify` call shaped exactly like `coach.py`'s excuse buttons (multiple `key`/`label` actions) round-
  tripped through the session bus, and a simulated click correctly delivered `ActionInvoked` with the clicked
  key back to a PyQt6 listener. `python-pyqt6` bundles `QtDBus` already — no extra package. Getting there needed
  working around two PyQt6 marshaling defaults that don't match libnotify's real `Notify` signature
  (`susssasa{sv}i`, confirmed via `busctl --user introspect`): a plain Python `int` is sent as `int32`, but
  `replaces_id` needs `uint32`, and a plain Python list of strings is sent as an array of variants (`av`), but
  `actions` needs a plain string array (`as`) — both need building through `QDBusArgument` with an explicit
  `QMetaType` id rather than passed as bare Python values. This is a marshaling detail to get right when this
  gets built, not a reason to avoid the approach — the interaction itself, replacing `notify-send -A`, works.
- **How-to window: `QTextBrowser` rendering `docs/help.md` as-is**, no porting and no separate renderer needed.
  Verified, not assumed: loaded the real file into a real `QTextBrowser` and confirmed Qt's built-in Markdown
  importer (`setMarkdown()`) renders all of it correctly, including the three GFM tables (`| Frame | Looks like
  |...`) as real HTML tables and the bold/heading/list formatting throughout. The screenshots resolve too —
  `QTextBrowser.setSearchPaths(["docs"])` finds `screenshots/popup-guide.png` etc. from the file's own relative
  `![...](screenshots/...)` paths with no path-rewriting. Two calls (`setSearchPaths`, `setMarkdown`) and the
  guide is done; nothing here needs building from scratch.
- **Background refresh: a `QObject` worker moved to a persistent `QThread`.** Verified, not assumed: a worker
  with a `fetch()` slot doing a simulated 2-second blocking call (standing in for the real HTTP fetch) was moved
  to its own `QThread`, while the main thread ticked a counter every 100 ms — it ticked 20 times during the
  2-second "fetch," proving the UI thread never froze. The result signal landed back on the main thread
  automatically (Qt queues a cross-thread signal to the receiver's own thread with no extra plumbing), so the
  UI just connects to it normally. Shape: one worker `QObject` holding the fetch logic, started once and kept
  alive (not spun up per refresh), driven by a `QTimer` living on that same worker thread for the interval,
  emitting a signal with the result. Not built into the app yet, just the pattern confirmed to work.

## Real open questions this plan doesn't answer yet

None left — everything above was either decided up front or resolved by verifying it directly.

## Suggested build order, for whenever this starts

1. A tray icon that appears and quits — proves the packaging and entry point work, nothing else.
2. Wire the tray tooltip to real backend data on a timer (background thread).
3. Right-click menu: refresh now, mute toggle — real actions, no dialogs yet.
4. Left-click opens the main window, read-only, with real fetched data.
5. The details window, opened from the main window's summary line.
6. The FTP / interval / reset dialogs.
7. The data window.
8. Charts, on PyQtGraph.
9. Notifications (kudos, comments, the coach).
10. Packaging: AUR/pacman, then Flatpak.
