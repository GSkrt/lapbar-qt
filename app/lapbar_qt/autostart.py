"""Start lapbar-qt when you log in: the "Start at login" item in the tray menu.

No installer is involved; the app registers itself, per user, the native way on each system:
- Windows: a value under HKEY_CURRENT_USER\\...\\CurrentVersion\\Run (no admin rights; listed under Task
  Manager > Startup apps, where it can also be switched off);
- macOS: a LaunchAgent, ~/Library/LaunchAgents/io.github.gskrt.lapbar-qt.plist, with RunAtLoad;
- Linux: an XDG autostart entry, ~/.config/autostart/lapbar-qt.desktop, which KDE, GNOME, XFCE, Cinnamon,
  MATE and LXQt run at login. Tiling compositors such as Hyprland and Sway don't read that folder: there, the
  command has to go in the compositor's own config (manual_hint() says so, with the line to add).

The entry points at wherever the app runs from right now: the packaged .exe/.app, or Python plus
app/bin/lapbar-qt from source. refresh() rewrites it on every start, so moving the app doesn't leave a
stale entry behind.
"""
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from lapbar import platforms

NAME = "LapBar"
MAC_LABEL = "io.github.gskrt.lapbar-qt"
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
SOURCE_ENTRY = Path(__file__).resolve().parents[1] / "bin" / "lapbar-qt"
ICON = Path(__file__).resolve().parent / "assets" / "icon.png"
# Desktops that don't run ~/.config/autostart by themselves (XDG_CURRENT_DESKTOP, lowercased).
NO_XDG_AUTOSTART = {"hyprland", "sway", "river", "niri", "wayfire", "labwc", "dwl", "i3"}


def command() -> list[str]:
    if platforms.FROZEN:
        return [sys.executable]
    return [platforms.background_python(), str(SOURCE_ENTRY)]


# ---------------------------------------------------------------- Linux (XDG autostart)

def _desktop_file() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "autostart" / "lapbar-qt.desktop"


def _desktop_quote(arg: str) -> str:
    """Quoting for a .desktop Exec= line (Desktop Entry spec): double quotes, with \\ " ` $ escaped."""
    if arg and not any(c in arg for c in ' \t\n"\'\\><~|&;$*?#()`'):
        return arg
    escaped = "".join("\\" + c if c in '"`$\\' else c for c in arg)
    return f'"{escaped}"'


def _desktop_entry() -> str:
    exec_line = " ".join(_desktop_quote(a) for a in command()).replace("%", "%%")
    return ("[Desktop Entry]\nType=Application\nName=LapBar\nComment=Strava activity in the system tray\n"
            f"Exec={exec_line}\nIcon={ICON}\nTerminal=false\nX-GNOME-Autostart-enabled=true\n")


# ---------------------------------------------------------------- macOS (LaunchAgent)

def _launch_agent() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"


def _launch_agent_plist() -> bytes:
    return plistlib.dumps({"Label": MAC_LABEL, "ProgramArguments": command(), "RunAtLoad": True,
                           "ProcessType": "Interactive"})


# ---------------------------------------------------------------- Windows (Run key)

def _run_key(write: bool = False):
    import winreg
    access = winreg.KEY_READ | (winreg.KEY_SET_VALUE if write else 0)
    return winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, access)


def _windows_value() -> str | None:
    import winreg
    try:
        with _run_key() as key:
            return winreg.QueryValueEx(key, NAME)[0]
    except FileNotFoundError:
        return None


# ---------------------------------------------------------------- the switch

def is_enabled() -> bool:
    if platforms.IS_WINDOWS:
        return _windows_value() is not None
    if platforms.IS_MAC:
        return _launch_agent().exists()
    return _desktop_file().exists()


def set_enabled(enabled: bool) -> None:
    if platforms.IS_WINDOWS:
        import winreg
        with _run_key(write=True) as key:
            if enabled:
                winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(command()))
            else:
                try:
                    winreg.DeleteValue(key, NAME)
                except FileNotFoundError:
                    pass
        return
    path = _launch_agent() if platforms.IS_MAC else _desktop_file()
    if not enabled:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if platforms.IS_MAC:
        path.write_bytes(_launch_agent_plist())
    else:
        path.write_text(_desktop_entry(), encoding="utf-8")


def refresh() -> None:
    """On every start: if starting at login is on, point it at where the app runs from now."""
    try:
        if is_enabled():
            set_enabled(True)
    except OSError:
        pass                       # a read-only home or a locked registry must never stop the app starting


def manual_hint() -> str | None:
    """On a desktop that ignores ~/.config/autostart, what to add to its config instead; otherwise None."""
    if platforms.IS_WINDOWS or platforms.IS_MAC:
        return None
    desktop = (os.environ.get("XDG_CURRENT_DESKTOP") or "").lower()
    names = {part for part in desktop.split(":") if part}
    if not names & NO_XDG_AUTOSTART:
        return None
    line = " ".join(_desktop_quote(a) for a in command())
    if "hyprland" in names:
        return ("Hyprland doesn't run ~/.config/autostart. Add this to your Hyprland config instead:\n\n"
                f'exec-once = {line}\n\n(or, in a Lua config: hl.exec_cmd("{line}") inside hl.on("hyprland.start", ...))')
    return f"Your desktop doesn't run ~/.config/autostart. Start this from its config instead:\n\n{line}"
