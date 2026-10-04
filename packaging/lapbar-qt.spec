# PyInstaller build of lapbar-qt: `pyinstaller --noconfirm --clean packaging/lapbar-qt.spec` from the repo root.
#   Windows: dist/lapbar-qt.exe, a single file, no console window.
#   macOS:   dist/lapbar-qt.app, a tray-only app (no Dock icon, LSUIElement).
#   Linux:   dist/lapbar-qt, a single file (handy for checking the spec; Linux users run it from source).
# The version comes from LAPBAR_VERSION (CI sets it from the git tag).
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
sys.path[:0] = [str(ROOT / "app"), str(ROOT / "backend")]
VERSION = os.environ.get("LAPBAR_VERSION", "0.1.0").lstrip("v")
ICON = str(ROOT / "app" / "lapbar_qt" / "assets" / "icon.png")   # PyInstaller converts it (needs Pillow)

a = Analysis(
    [str(ROOT / "packaging" / "lapbar-qt.py")],
    pathex=[str(ROOT / "app"), str(ROOT / "backend")],
    datas=[
        (str(ROOT / "app" / "lapbar_qt" / "assets"), "lapbar_qt/assets"),
        (str(ROOT / "backend" / "lapbar" / "messages"), "lapbar/messages"),
    ],
    # Every module of both packages: some are imported lazily, inside functions, where analysis can't see them.
    hiddenimports=collect_submodules("lapbar") + collect_submodules("lapbar_qt"),
    excludes=["tkinter", "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtQml", "PyQt6.QtQuick",
              "PyQt6.QtMultimedia", "PyQt6.QtBluetooth", "PyQt6.QtNetwork", "PyQt6.QtPdf"],
)
pyz = PYZ(a.pure)

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="lapbar-qt", console=False, icon=ICON)
    coll = COLLECT(exe, a.binaries, a.datas, name="lapbar-qt")
    app = BUNDLE(
        coll,
        name="lapbar-qt.app",
        icon=ICON,
        bundle_identifier="io.github.gskrt.lapbar-qt",
        version=VERSION,
        info_plist={
            "CFBundleName": "LapBar",
            "CFBundleDisplayName": "LapBar",
            "CFBundleShortVersionString": VERSION,
            "LSUIElement": True,              # a menu-bar (tray) app: no Dock icon, no app menu
            "NSHighResolutionCapable": True,
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="lapbar-qt", console=False, icon=ICON,
              upx=False)
