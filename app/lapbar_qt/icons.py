"""Small chart icons for the buttons and tabs that open a plot (assets/icons/*.svg).

The data lines and bars use the app's own chart colours; the axes are drawn in `currentColor`, filled in here
with the palette's button text colour so they read on light and dark themes alike. Rendered at several sizes
and at the screen's pixel ratio, so they stay sharp in a 16 px tab or a scaled-up button.
"""
from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPalette, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

ICON_DIR = Path(__file__).parent / "assets" / "icons"
SIZES = (16, 20, 24, 32, 48)
BUTTON_SIZE = QSize(20, 20)


@lru_cache(maxsize=None)
def _icon(name: str, axis_color: str) -> QIcon:
    svg = (ICON_DIR / f"{name}.svg").read_text(encoding="utf-8").replace("currentColor", axis_color)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    ratio = QApplication.instance().devicePixelRatio()
    icon = QIcon()
    for size in SIZES:
        pixmap = QPixmap(round(size * ratio), round(size * ratio))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(ratio)
        icon.addPixmap(pixmap)
    return icon


def chart(name: str) -> QIcon:
    """"metrics" (a ride's measures), "fitness" (fitness/fatigue/form), "week" (running totals), "weeks" (bars)."""
    axis = QApplication.instance().palette().color(QPalette.ColorRole.ButtonText).name()
    return _icon(name, axis)


def decorate(button, name: str) -> None:
    button.setIcon(chart(name))
    button.setIconSize(BUTTON_SIZE)
