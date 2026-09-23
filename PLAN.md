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
| `charts/shell.qml` (ride charts) | a charts window — **needs real design work**, see below |
| `charts/shell.qml` (fitness chart, same window/different doc) | same charts window, fed the fitness doc |
| `manage/shell.qml` (data window) | a data window, built on `manage.status()`, already carried over |
| `help/shell.qml` (how-to) | undecided: port the guide-rendering window, or just link the README |
| the FTP / interval / reset submenus in Panel.qml's menu | small dialogs, opened from the tray's right-click menu |

## Real open questions this plan doesn't answer yet

- **Charts.** Quickshell's chart window has real logic behind it (`charts/logic.js`'s level-of-detail
  reduction, the shared-cursor crosshair, the table view) that was never ported — none of that exists here yet.
  Worth deciding: hand-rolled `QPainter` drawing (closest to what exists today, most control) vs `QtCharts` (less
  code, less control over the exact zoomed-out real-sample-reduction behaviour LapBar relies on for long rides).
- **Notifications.** `QSystemTrayIcon.showMessage()` is the native, cross-desktop way to show a popup, and could
  replace shelling out to `notify-send`. It does **not** support the excuse buttons the coach's notifications
  carry today (`-A key=label`) — that needs either a direct `org.freedesktop.Notifications` D-Bus call (what
  `notify-send` does under the hood, doable from PyQt6 via `QtDBus`) to keep that exact interaction, or accepting
  that clicking a coach notification just opens the app to where you'd pick an excuse instead. Not decided.
- **Background refresh.** With the backend now in-process (no more subprocess-and-parse-JSON boundary to
  `bin/lapbar`), a periodic refresh must not block the Qt event loop — needs a worker thread (`QThread`, or a
  plain background thread posting results back via a Qt signal) rather than calling the network-blocking fetch
  logic directly on the UI thread. Not built yet.
- **How-to window.** Porting `help/shell.qml`'s markdown-and-pictures rendering is real work for arguably little
  gain when a `QTextBrowser` pointed at the README, or just opening the README link, might be enough. Undecided.

## Suggested build order, for whenever this starts

1. A tray icon that appears and quits — proves the packaging and entry point work, nothing else.
2. Wire the tray tooltip to real backend data on a timer (background thread).
3. Right-click menu: refresh now, mute toggle — real actions, no dialogs yet.
4. Left-click opens the main window, read-only, with real fetched data.
5. The details window, opened from the main window's summary line.
6. The FTP / interval / reset dialogs.
7. The data window.
8. Charts (once the design question above is settled).
9. Notifications (kudos, comments, the coach).
10. Packaging: AUR/pacman, then Flatpak.
