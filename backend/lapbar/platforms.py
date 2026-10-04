"""The few things that differ between Linux, Windows and macOS, kept in one place.

Everything else in the backend is plain, portable Python. What is not:
- where an app keeps its files (XDG folders on Linux, AppData on Windows, ~/Library on macOS);
- starting a background process that outlives the refresh (a new session on POSIX, a detached process without
  a console window on Windows);
- asking whether a process is still running (`os.kill(pid, 0)` is a harmless probe on POSIX, but on Windows
  signal 0 is CTRL_C_EVENT and would interrupt a whole console process group).
"""
import os
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
FROZEN = bool(getattr(sys, "frozen", False))   # running from a packaged app (PyInstaller), not from source
APP = "lapbar-qt"


def _xdg(var: str, default: str) -> Path:
    return Path(os.environ.get(var) or Path.home() / default)


def base_dirs() -> dict[str, Path]:
    """{"state", "cache", "data", "config"}: lapbar-qt's own folder for each kind of file on this system."""
    if IS_WINDOWS:
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / APP
        roaming = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP
        return {"state": local / "state", "cache": local / "cache", "data": local / "data", "config": roaming}
    if IS_MAC:
        support = Path.home() / "Library" / "Application Support" / APP
        return {"state": support / "state", "cache": Path.home() / "Library" / "Caches" / APP, "data": support / "data",
                "config": Path.home() / "Library" / "Preferences" / APP}
    return {"state": _xdg("XDG_STATE_HOME", ".local/state") / APP, "cache": _xdg("XDG_CACHE_HOME", ".cache") / APP,
            "data": _xdg("XDG_DATA_HOME", ".local/share") / APP, "config": _xdg("XDG_CONFIG_HOME", ".config") / APP}


def detached() -> dict:
    """Popen keyword arguments for a background process that keeps running after its parent is gone."""
    if IS_WINDOWS:
        return {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.CREATE_NO_WINDOW}
    return {"start_new_session": True}


def background_python() -> str:
    """The interpreter for a background process: on Windows the console-less pythonw.exe when it is there."""
    if IS_WINDOWS:
        windowless = Path(sys.executable).with_name("pythonw.exe")
        if windowless.is_file():
            return str(windowless)
    return sys.executable


def cli_command() -> list[str]:
    """How to start `bin/lapbar <args>` as a background process.

    From source: the interpreter (console-less on Windows) running bin/lapbar in isolated mode. In a packaged
    app there is neither a Python nor a bin/lapbar on disk -- sys.executable is the app itself -- so the app's
    own executable runs the command-line tool when its first argument is --cli (packaging/lapbar-qt.py)."""
    if FROZEN:
        return [sys.executable, "--cli"]
    return [background_python(), "-I", str(Path(__file__).resolve().parent.parent / "bin" / "lapbar")]


def pid_alive(pid) -> bool:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if IS_WINDOWS:
        import ctypes
        from ctypes import wintypes
        PROCESS_QUERY_LIMITED_INFORMATION, STILL_ACTIVE = 0x1000, 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5          # ERROR_ACCESS_DENIED: it exists, it just isn't ours
        try:
            code = wintypes.DWORD()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
