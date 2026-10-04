"""Headless Qt, and every file and secret kept in a temporary folder, on Linux, Windows and macOS alike."""
import os
import sys
import urllib.request
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "backend")]


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    for var in ("HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "XDG_CONFIG_HOME", "XDG_STATE_HOME",
                "XDG_CACHE_HOME", "XDG_DATA_HOME"):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))
    monkeypatch.setenv("LAPBAR_KEYRING", "none")
    for name in ("STRAVA_CLIENT_ID", "STRAVA_CLIENT_SECRET", "STRAVA_REFRESH_TOKEN", "LAPBAR_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)

    def blocked(*a, **k):
        raise AssertionError("test tried to use the real network")
    monkeypatch.setattr(urllib.request, "urlopen", blocked)


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    return app
