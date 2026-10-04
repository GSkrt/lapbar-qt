"""The LapBar wordmark (assets/logo/, the same SVGs the Omarchy plugin uses), shown top-left in every window
the way LapBar's own Quickshell windows show it in their header: white on dark themes, black on light ones.
"""
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication, QHBoxLayout, QLabel, QWidget

LOGO_DIR = Path(__file__).parent / "assets" / "logo"
HEADER_HEIGHT = 30


def logo_pixmap(height: int = HEADER_HEIGHT) -> QPixmap:
    app = QApplication.instance()
    dark = app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    renderer = QSvgRenderer(str(LOGO_DIR / f"lapbar_horiz_{'white' if dark else 'black'}.svg"))
    size = renderer.defaultSize()
    if not renderer.isValid() or size.height() == 0:
        return QPixmap()
    # Rendered at the screen's device pixel ratio so the wordmark stays sharp on scaled (HiDPI) outputs.
    ratio = app.devicePixelRatio()
    width = round(size.width() * height / size.height())
    pixmap = QPixmap(round(width * ratio), round(height * ratio))
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def logo_label() -> QLabel:
    label = QLabel()
    pixmap = logo_pixmap()
    if pixmap.isNull():
        label.setText("LapBar")  # the SVG asset is missing; the name alone still says what this window is
        font = label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 4)
        label.setFont(font)
    else:
        label.setPixmap(pixmap)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return label


def header(title: str, subtitle: str | None = None, closes_on_esc: bool = True) -> QWidget:
    """A window's top row, like LapBar's own windows: the logo, what this window is (and for which activity),
    and on the right "Esc to close" for the windows that do."""
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 4)
    layout.addWidget(logo_label())
    name = QLabel(title)
    font = name.font()
    font.setBold(True)
    font.setPointSize(font.pointSize() + 3)
    name.setFont(font)
    layout.addSpacing(10)
    layout.addWidget(name, alignment=Qt.AlignmentFlag.AlignVCenter)
    if subtitle:
        detail = QLabel("·  " + subtitle)
        detail.setStyleSheet("color: gray;")
        detail.setFont(QFont(font.family(), font.pointSize() - 2))
        layout.addWidget(detail, alignment=Qt.AlignmentFlag.AlignVCenter)
    layout.addStretch(1)
    if closes_on_esc:
        hint = QLabel("Esc to close")
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint, alignment=Qt.AlignmentFlag.AlignVCenter)
    return row


def window_title(title: str) -> str:
    return f"LapBar · {title}"
