"""Start at login: the right per-user entry on each system, pointing at where the app runs from."""
import plistlib
import sys
import uuid

import pytest

from lapbar import platforms
from lapbar_qt import autostart


@pytest.fixture
def linux(monkeypatch, tmp_path):
    monkeypatch.setattr(platforms, "IS_WINDOWS", False)
    monkeypatch.setattr(platforms, "IS_MAC", False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return tmp_path / "config" / "autostart" / "lapbar-qt.desktop"


def test_linux_writes_and_removes_an_xdg_autostart_entry(linux, monkeypatch):
    monkeypatch.setattr(autostart, "command", lambda: ["/opt/My Apps/python", "/home/me/lapbar-qt/app/bin/lapbar-qt"])
    assert not autostart.is_enabled()
    autostart.set_enabled(True)
    text = linux.read_text(encoding="utf-8")
    assert autostart.is_enabled() and "Type=Application" in text
    assert 'Exec="/opt/My Apps/python" /home/me/lapbar-qt/app/bin/lapbar-qt\n' in text   # quoted: it has a space
    autostart.set_enabled(False)
    assert not linux.exists() and not autostart.is_enabled()


def test_a_moved_app_is_repointed_on_the_next_start(linux, monkeypatch):
    monkeypatch.setattr(autostart, "command", lambda: ["/old/lapbar-qt"])
    autostart.set_enabled(True)
    monkeypatch.setattr(autostart, "command", lambda: ["/new/lapbar-qt"])
    autostart.refresh()
    assert "Exec=/new/lapbar-qt\n" in linux.read_text(encoding="utf-8")


def test_refresh_does_nothing_when_it_is_off(linux):
    autostart.refresh()
    assert not linux.exists()


def test_macos_writes_a_launch_agent(monkeypatch, tmp_path):
    monkeypatch.setattr(platforms, "IS_WINDOWS", False)
    monkeypatch.setattr(platforms, "IS_MAC", True)
    monkeypatch.setattr(autostart.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(autostart, "command", lambda: ["/Applications/lapbar-qt.app/Contents/MacOS/lapbar-qt"])
    autostart.set_enabled(True)
    agent = tmp_path / "Library" / "LaunchAgents" / "io.github.gskrt.lapbar-qt.plist"
    data = plistlib.loads(agent.read_bytes())
    assert data["RunAtLoad"] is True and data["ProgramArguments"] == ["/Applications/lapbar-qt.app/Contents/MacOS/lapbar-qt"]
    autostart.set_enabled(False)
    assert not agent.exists()


def test_the_packaged_app_starts_itself_and_from_source_python_runs_the_entry_point(monkeypatch):
    monkeypatch.setattr(platforms, "FROZEN", True)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\lapbar-qt.exe")
    assert autostart.command() == [r"C:\Apps\lapbar-qt.exe"]
    monkeypatch.setattr(platforms, "FROZEN", False)
    assert autostart.command()[-1].endswith("lapbar-qt") and autostart.SOURCE_ENTRY.is_file()


def test_hyprland_gets_told_where_the_line_goes_instead(linux, monkeypatch):
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "Hyprland")
    assert "exec-once = " in autostart.manual_hint()
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    assert autostart.manual_hint() is None


@pytest.mark.skipif(sys.platform != "win32", reason="the Windows registry exists only on Windows")
def test_windows_uses_the_current_users_run_key(monkeypatch):
    monkeypatch.setattr(autostart, "NAME", f"LapBar-test-{uuid.uuid4().hex[:8]}")
    monkeypatch.setattr(autostart, "command", lambda: [r"C:\Program Files\LapBar\lapbar-qt.exe"])
    try:
        autostart.set_enabled(True)
        assert autostart._windows_value() == r'"C:\Program Files\LapBar\lapbar-qt.exe"'
        assert autostart.is_enabled()
    finally:
        autostart.set_enabled(False)
    assert not autostart.is_enabled()
