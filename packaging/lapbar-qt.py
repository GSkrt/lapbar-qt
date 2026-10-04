"""Entry point of the packaged app (PyInstaller, see lapbar-qt.spec): one executable, three jobs.

  lapbar-qt                 the tray app
  lapbar-qt --cli <args>    the backend's command-line tool (bin/lapbar), which the app starts in the
                            background for the continuous DuckDB export (platforms.cli_command())
  lapbar-qt --self-test     opens the app's windows off-screen with the bundled files and exits 0, or 1 with
                            the error in lapbar-qt-selftest.log; CI runs it on every build

Also runs from source (python packaging/lapbar-qt.py), which is how the spec is checked locally.
"""
import os
import sys
import traceback
from pathlib import Path

if not getattr(sys, "frozen", False):
    ROOT = Path(__file__).resolve().parent.parent
    sys.path[:0] = [str(ROOT / "app"), str(ROOT / "backend")]


def self_test() -> int:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    try:
        import importlib
        import pkgutil

        from PyQt6.QtGui import QIcon
        from PyQt6.QtWidgets import QApplication

        import lapbar_qt
        from lapbar import coach
        app = QApplication([])
        for module in pkgutil.iter_modules(lapbar_qt.__path__):
            importlib.import_module(f"lapbar_qt.{module.name}")
        from lapbar_qt import branding, mainwindow, tray
        assert not QIcon(str(tray.ICON_PATH)).isNull(), f"tray icon missing: {tray.ICON_PATH}"
        assert not branding.logo_pixmap().isNull(), "LapBar logo missing"
        assert coach.messages()["titles"], "coach messages missing"
        window = mainwindow.MainWindow()
        window.show()
        app.processEvents()
        window.close()
        return 0
    except Exception:  # noqa: BLE001 - the whole point is to report any failure
        Path("lapbar-qt-selftest.log").write_text(traceback.format_exc(), encoding="utf-8")
        traceback.print_exc()
        return 1


def main() -> int:
    args = sys.argv[1:]
    if args[:1] == ["--cli"]:
        from lapbar import cli
        sys.argv = ["lapbar", *args[1:]]
        cli.main(args[1:])
        return 0
    if args[:1] == ["--self-test"]:
        return self_test()
    from lapbar_qt.tray import main as tray_main
    return tray_main()


if __name__ == "__main__":
    sys.exit(main())
