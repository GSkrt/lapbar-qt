# lapbar-qt

A standalone, PyQt6 sibling of [LapBar](https://github.com/GSkrt/lapbar): a system tray icon instead of an Omarchy
bar widget, aimed at every mainstream distro (not only Arch/pacman, not tied to Omarchy or Quickshell at all).

> **Status: mostly untested.** Developed and run day-to-day on Arch Linux only. The packaged Windows `.exe` and
> macOS `.app` builds pass CI's own self-test (the app starts up and exits cleanly) but have not been tried by
> hand on real Windows or macOS machines — there isn't one available to test macOS on at all. Linux distros other
> than Arch haven't been tried either. Expect rough edges; please open an issue with what you hit.

## Installing

### Arch Linux

Not yet on the AUR (account registration there is currently closed). Until then, build the same `PKGBUILD` it
would use, straight from this repo:

```sh
git clone https://github.com/GSkrt/lapbar-qt && cd lapbar-qt/packaging
makepkg -si
```

It's a VCS package (`lapbar-qt-git`), so it always builds whatever is currently on `main`; rerun `makepkg -si` to
update. Running it from source without installing works too, the same way as "Other Linux distros" below.

### Other Linux distros

No native package yet, run from source with pip:

```sh
python -m pip install -r requirements.txt   # PyQt6, pyqtgraph
git clone https://github.com/GSkrt/lapbar-qt && cd lapbar-qt
python app/bin/lapbar-qt
```

Or with your distro's own Qt6 bindings package instead of pip, if it has one: `python3-pyqt6` on Debian/Ubuntu,
`python3-qt6` on Fedora, `python3-pyqt6` on openSUSE. `pyqtgraph` is usually pip-only.

### Windows / macOS

Download the latest build from [Releases](https://github.com/GSkrt/lapbar-qt/releases) — a single `lapbar-qt.exe`
for Windows, or `lapbar-qt.app` in a `.dmg` for macOS (Apple silicon). See
[Packaged apps](#packaged-apps-windows-exe-macos-app-linux-binary) below for the first-launch security prompt.
Alternatively, run from source the same way as "Other Linux distros" above (`python -m pip install -r
requirements.txt`, then `python app/bin/lapbar-qt`, or double-click `app\bin\lapbar-qt.pyw` on Windows to skip the
console window).

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

### Packaged apps (Windows .exe, macOS .app, Linux binary)

`.github/workflows/build.yml` builds all three with PyInstaller (`packaging/lapbar-qt.spec`): a single
`lapbar-qt.exe` for Windows, `lapbar-qt.app` in a `.dmg` for macOS (Apple silicon), and a single `lapbar-qt`
binary in a `.tar.gz` for generic Linux (Arch users should prefer `packaging/PKGBUILD` instead, see
[Arch Linux](#arch-linux) above) — each self-tested after the build. Pushing a version tag
(`git tag v0.2.0 && git push --tags`) builds and publishes all three as a GitHub release; running the workflow by
hand only keeps them as downloadable artifacts for 14 days, unless published as a release separately. The first
build was made and published this way, as a rolling `main` pre-release rather than a version tag — the app is
still mostly untested (see the disclaimer above), so it gets replaced wholesale by later `main` builds rather than
accumulating version numbers, until there's a real `v*` release.

They are not code-signed, so the first launch shows a warning: on Windows, SmartScreen's "More info" then "Run
anyway"; on macOS 15 and later, try to open it once, then System Settings > Privacy & Security > "Open Anyway"
(or `xattr -dr com.apple.quarantine lapbar-qt.app`).
Signing needs a Windows code-signing certificate and an Apple Developer account. DuckDB is not bundled, so
Manage data's export is unavailable in these builds.

## Where this stands

Runs day to day on Arch. The tray app has its own native windows for everything LapBar shows through Quickshell —
the popup/tooltip, ride charts, fitness chart, data window, details window, plus week-vs-week comparison, a setup
wizard, and start-at-login — built as PyQt6 `QWidget`/`QDialog` views, not spawned Quickshell processes.

- `backend/lapbar/` — the Strava/fitness/coach backend: auth (with keyring storage), the hardened HTTP layer,
  fitness/fatigue/form, kudos and comments tracking, the DuckDB export, the whole request-budget and caching
  logic. A copy of LapBar's own backend (see [Relationship to LapBar](#relationship-to-lapbar)), trimmed of
  everything Quickshell-specific.
- `backend/bin/lapbar` — the same CLI entry point LapBar has (`lapbar fetch --print`, `lapbar api`, etc.), useful
  for exploring the backend directly instead of through the tray app.
- `app/lapbar_qt/` — the PyQt6 tray app: `tray.py` is the entry point, the rest are its windows and widgets.
- `backend/tests/` and `app/tests/` — run both with CI (`.github/workflows/tests.yml`), or locally with
  `cd backend && uv run --extra dev pytest`.

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

- **AUR:** `packaging/PKGBUILD` is ready but not submitted — new-account registration on the AUR is currently
  closed. Until it reopens, Arch users build it locally (see [Installing](#arch-linux)).
- **Flatpak or AppImage:** neither built yet. An AppImage is the lower-effort next step — PyInstaller already
  produces the single-file Linux binary it would wrap, no sandboxing/portals work needed. Flatpak reaches
  Flathub's audience but needs a manifest and portal permissions for the keyring (`secret-tool`) and
  notifications it uses, and Flathub has its own review queue.

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
