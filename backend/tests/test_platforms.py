"""Linux, Windows and macOS differences: folders, background processes, process checks, keyring choice, popups."""
import os
import subprocess
import sys
import uuid

import pytest

from lapbar import alerts, coach, config, platforms, popups, vault


def test_linux_keeps_the_xdg_folders(monkeypatch, tmp_path):
    monkeypatch.setattr(platforms, "IS_WINDOWS", False)
    monkeypatch.setattr(platforms, "IS_MAC", False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    assert config.data_dir() == tmp_path / "data" / "lapbar-qt"
    assert config.cache_path() == tmp_path / "cache" / "lapbar-qt" / "cache.json"


def test_windows_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr(platforms, "IS_WINDOWS", True)
    monkeypatch.setattr(platforms, "IS_MAC", False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    monkeypatch.delenv("LAPBAR_DATA_DIR", raising=False)
    assert config.data_dir() == tmp_path / "Local" / "lapbar-qt" / "data"
    assert config.state_dir() == tmp_path / "Local" / "lapbar-qt" / "state"
    assert config.cache_path() == tmp_path / "Local" / "lapbar-qt" / "cache" / "cache.json"
    assert config.user_env_path() == tmp_path / "Roaming" / "lapbar-qt" / "env"


def test_macos_uses_library(monkeypatch, tmp_path):
    monkeypatch.setattr(platforms, "IS_WINDOWS", False)
    monkeypatch.setattr(platforms, "IS_MAC", True)
    monkeypatch.setattr(platforms.Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("LAPBAR_DATA_DIR", raising=False)
    assert config.data_dir() == tmp_path / "Library" / "Application Support" / "lapbar-qt" / "data"
    assert config.cache_path() == tmp_path / "Library" / "Caches" / "lapbar-qt" / "cache.json"


def test_the_own_folders_never_overlap(monkeypatch):
    for windows, mac in ((False, False), (True, False), (False, True)):
        monkeypatch.setattr(platforms, "IS_WINDOWS", windows)
        monkeypatch.setattr(platforms, "IS_MAC", mac)
        dirs = list(platforms.base_dirs().values())
        assert all(a == b or (a not in b.parents and b not in a.parents) for a in dirs for b in dirs)


def test_a_running_process_is_alive_and_a_finished_one_is_not():
    assert platforms.pid_alive(os.getpid())
    done = subprocess.Popen([sys.executable, "-c", "pass"])
    done.wait()
    assert not platforms.pid_alive(done.pid)
    assert not platforms.pid_alive(None) and not platforms.pid_alive("x") and not platforms.pid_alive(0)


def test_a_background_process_is_detached_the_right_way_for_the_platform():
    kwargs = platforms.detached()
    if sys.platform == "win32":
        assert kwargs["creationflags"] & subprocess.CREATE_NO_WINDOW
    else:
        assert kwargs == {"start_new_session": True}


def test_the_keyring_is_chosen_per_platform(monkeypatch):
    monkeypatch.delenv("LAPBAR_KEYRING", raising=False)
    monkeypatch.setattr(platforms, "IS_WINDOWS", False)
    monkeypatch.setattr(platforms, "IS_MAC", True)
    assert isinstance(vault._keyring(), vault.NoKeyring) and not vault.keyring_available()
    monkeypatch.setattr(platforms, "IS_MAC", False)
    assert isinstance(vault._keyring(), vault.Keyring)
    monkeypatch.setenv("LAPBAR_KEYRING", "none")
    assert isinstance(vault._keyring(), vault.NoKeyring)


def test_without_a_keyring_secrets_go_to_the_private_file(monkeypatch):
    monkeypatch.setenv("LAPBAR_KEYRING", "none")
    assert vault.get("tokens") is None                         # nothing yet is simply nothing, not an error
    assert vault.set("tokens", '{"a": 1}') == "file"
    assert vault.get("tokens") == '{"a": 1}'
    assert vault.migrate_legacy() == []                         # never "migrates" into a keyring that isn't there
    vault.delete("tokens")
    assert vault.get("tokens") is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Credential Manager exists only on Windows")
def test_windows_credential_manager_round_trip():
    ring = vault.WindowsCredentials()
    name = f"test-{uuid.uuid4().hex}"
    try:
        assert ring.get(name) is None
        ring.set(name, "sécret ✓")
        assert ring.get(name) == "sécret ✓"
    finally:
        ring.delete(name)
    assert ring.get(name) is None
    ring.delete(name)                                           # deleting what is not there is not an error


def test_with_a_presenter_installed_popups_start_no_process(monkeypatch):
    shown = []
    monkeypatch.setattr(popups, "presenter", lambda *a: shown.append(a))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("no process should be started"))
    kudos_event = {"count": 1, "total": 3, "from": ["Ana Č. <b>"], "name": "Morning & ride",
                   "url": "https://www.strava.com/activities/123"}
    alerts.deliver("kudos", kudos_event)
    coach.deliver(coach.notification("idle", "drill", "Up."), "2026-09-20")
    (kind, title, body, url), (coach_kind, *_rest, coach_url) = shown
    assert kind == "kudos" and url == "https://www.strava.com/activities/123"
    assert "Ana Č. <b>" in body and "Morning & ride" in body       # plain text: unescaped, nothing to render
    assert coach_kind == "coach" and coach_url is None


def test_a_presenter_never_gets_a_link_that_is_not_strava(monkeypatch):
    shown = []
    monkeypatch.setattr(popups, "presenter", lambda *a: shown.append(a))
    alerts.deliver("kudos", {"count": 1, "total": 1, "from": [], "name": "x", "url": "https://evil.example/activities/1"})
    assert shown[0][3] is None
