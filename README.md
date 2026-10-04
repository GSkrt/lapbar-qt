# lapbar-qt

A standalone, PyQt6 sibling of [LapBar](https://github.com/GSkrt/lapbar): a system tray icon instead of an Omarchy
bar widget, aimed at every mainstream distro (not only Arch/pacman, not tied to Omarchy or Quickshell at all).

## Running it

Linux, Windows and macOS. Python 3.11+, plus PyQt6 and pyqtgraph:

- **Arch:** `sudo pacman -S python-pyqt6 python-pyqtgraph`, then `app/bin/lapbar-qt`.
- **Windows / macOS / other distros:** `python -m pip install -r requirements.txt`, then
  `python app/bin/lapbar-qt`. On Windows, double-clicking `app\bin\lapbar-qt.pyw` starts it without a console window.

What differs per system, all handled in `backend/lapbar/platforms.py` and `vault.py`:

| | Linux | Windows | macOS |
|---|---|---|---|
| Files | XDG folders (`~/.local/share/lapbar-qt`, …) | `%LOCALAPPDATA%\lapbar-qt`, config in `%APPDATA%` | `~/Library/Application Support/lapbar-qt`, `~/Library/Caches` |
| Strava secret and tokens | keyring via `secret-tool`, else a private 0600 file | Windows Credential Manager | private 0600 file |
| Popups (coach, kudos, comments) | the tray icon's own notifications | same (Windows toasts) | same (Notification Center) |

macOS has no keyring option here on purpose: its built-in `security` tool takes the secret as a command-line
argument, readable by every local account in `ps`. `LAPBAR_KEYRING=secret-tool|windows|none` overrides the choice.
Popups shown by the tray carry no buttons, so the coach's "excuse" buttons from the Omarchy version are not offered;
clicking a kudos or comment popup opens the activity on Strava, clicking a coach nudge opens the main window.

CI (`.github/workflows/tests.yml`) runs the backend tests and a headless smoke test of the app: on Linux for every
push, and on Windows and macOS too when started by hand from the Actions tab.

### Starting at login

There is no installer: tick **Start at login** in the tray icon's menu (it is also offered once, right after
the first successful setup). The app then registers itself for the current user only, without admin rights:
a `HKCU\...\CurrentVersion\Run` value on Windows (it shows under Task Manager > Startup apps), a LaunchAgent in
`~/Library/LaunchAgents` on macOS, and `~/.config/autostart/lapbar-qt.desktop` on Linux. Every start re-points
the entry at where the app runs from, so moving the `.exe` or `.app` doesn't break it. Hyprland, Sway and
similar compositors don't read `~/.config/autostart`; the app says so and shows the line for their config.

### Packaged apps (Windows .exe, macOS .app)

`.github/workflows/build.yml` builds them with PyInstaller (`packaging/lapbar-qt.spec`): a single
`lapbar-qt.exe` for Windows, and `lapbar-qt.app` in a `.dmg` for macOS (Apple silicon), each self-tested
after the build. Pushing a version tag (`git tag v0.2.0 && git push --tags`) builds both and publishes them as a
GitHub release; running the workflow by hand only keeps them as downloadable artifacts for 14 days.

They are not code-signed, so the first launch shows a warning: on Windows, SmartScreen's "More info" then "Run
anyway"; on macOS 15 and later, try to open it once, then System Settings > Privacy & Security > "Open Anyway"
(or `xattr -dr com.apple.quarantine lapbar-qt.app`).
Signing needs a Windows code-signing certificate and an Apple Developer account. DuckDB is not bundled, so
Manage data's export is unavailable in these builds.

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

## Decided

- **Shape:** a system tray icon (`QSystemTrayIcon`), not a KDE Plasma widget and not a standalone window. Works
  across KDE, GNOME (with the AppIndicator extension), XFCE and most others — the actual cross-distro goal,
  which a Plasma-only plasmoid wouldn't have met. Trades away LapBar's rotating bar-text frame for an icon plus a
  tooltip; the click-to-open popup carries over.
- **Toolkit:** PyQt6, imported and confirmed working on this machine (`python-pyqt6` 6.11.0 from Arch's own
  `extra` repo, GPL-licensed — compatible with this project's GPL-3.0-or-later without any extra consideration).
  Since the backend is already Python, PyQt6 can host both in one process: no more subprocess-and-parse-JSON
  boundary between the UI and `lapbar/` the way Quickshell talks to `bin/lapbar` today. The four windows LapBar
  spawns separately (charts, data, details, how-to) become native `QWidget`/`QDialog` views instead.

## Still open

- **Packaging:** AUR/pacman first (fastest path to something real, matches this machine's distro family) with a
  Flatpak later, or Flatpak from the start for genuine day-one portability to every distro. Not urgent until
  there's an app to package.

## Relationship to LapBar

Both keep going, as two independent projects, not one replacing the other — the Omarchy plugin stays exactly
what it is for Omarchy users, this becomes the option for everyone else. They are two separate repositories,
deliberately: LapBar is already partway through the Omarchy marketplace's security review, and folding unrelated
Qt/tray code into that repository now would put an unrelated codebase in front of the same reviewer and risk
resetting a review already in progress, for no benefit — a plugin marketplace expects one plugin at the root of
its repo, not a plugin plus an unrelated standalone app.

`backend/lapbar/` is a copy, not a shared package, so the two won't drift automatically back into sync. When a
real bug or security fix lands in one (this copy is current as of the HTTP/OAuth/permissions/PATH hardening
already in LapBar), it needs to be deliberately ported to the other — there's no tooling for that yet, and it's
not worth building until keeping them in sync by hand actually becomes painful. If it does, the next step would
be extracting `lapbar/` into its own installable package both projects depend on, rather than two copies.

## License

GPL-3.0-or-later, same as LapBar (see `LICENSE`).
