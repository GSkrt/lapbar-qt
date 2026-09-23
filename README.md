# lapbar-qt (working name)

A standalone, Qt-based sibling of [LapBar](https://github.com/GSkrt/lapbar), aimed at KDE and packaged for pacman
(and, if it's worth it once this exists, other distros too) — not tied to Omarchy or Quickshell.

**The name is a placeholder.** LapBar itself went through three names before settling; this one hasn't been
decided at all yet.

## Where this stands

Nothing runs yet. What exists so far is the **shared backend**, copied from LapBar and trimmed of everything that
was Quickshell-specific, as a working starting point — not a finished product.

- `backend/lapbar/` — the Strava/fitness/coach backend: auth (with keyring storage), the hardened HTTP layer,
  fitness/fatigue/form, kudos and comments tracking, the DuckDB export, the whole request-budget and caching
  logic. This is the same code LapBar uses, unmodified apart from removing the four modules below.
- `backend/bin/lapbar` — the same CLI entry point LapBar has (`lapbar fetch --print`, `lapbar api`, etc.), useful
  for exploring the backend and as a reference for what a native UI here will eventually call directly instead of
  going through a subprocess.
- `backend/tests/` — LapBar's test suite, with anything that read a `.qml` file removed. 412 passed, 1 skipped
  (a check for this project's own README listing every Strava call, skipped until there is one written).

**Removed, not adapted:** `charts.py`, `helpwin.py`, `activitywin.py` (100% "spawn a Quickshell process and float
it" — nothing to reuse) and `manage.py`'s `open_window()` (its `status()` data-aggregation half is kept). A native
UI here will need its own equivalent of all four windows LapBar has — the popup, the ride charts, the fitness
chart, the data window, the details window — built against whatever toolkit gets chosen, not this code.

## Open decisions

Nothing below is decided. Whatever gets picked changes what "the UI" even means here, so it's worth deciding
before building much more:

- **Shape:** a system tray icon (works across KDE/GNOME/XFCE, closest cross-desktop equivalent to the bar
  widget, but loses the rotating text label), a KDE Plasma widget/plasmoid (matches the bar-widget feel exactly,
  but KDE-only), or a plain standalone window (simplest, but no longer an always-visible ambient presence — arguably
  a different product).
- **Toolkit:** PySide6 (Qt's own official Python bindings — keeps the backend and UI in one process, no more
  subprocess/JSON boundary) vs. QML + QtQuick.Controls calling the existing `bin/lapbar` CLI the way LapBar's
  Quickshell widget does today (keeps the current battle-tested IPC pattern, less to rewrite).
- **Packaging:** AUR/pacman first (fastest path to something real, matches "pacman" and this machine's distro
  family) with a Flatpak later, or Flatpak from the start for genuine day-one portability to every distro.

## License

GPL-3.0-or-later, same as LapBar (see `LICENSE`).
