"""Build-order step 1: a tray icon that appears and quits. Nothing else yet."""
import sys
from pathlib import Path

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

ICON_PATH = Path(__file__).parent / "assets" / "icon.png"


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # a tray-only app has no window to keep it alive

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("No system tray available on this desktop.", file=sys.stderr)
        return 1

    tray = QSystemTrayIcon(QIcon(str(ICON_PATH)))
    tray.setToolTip("lapbar-qt")

    menu = QMenu()
    quit_action = QAction("Quit", menu)
    quit_action.triggered.connect(app.quit)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)

    tray.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
