"""Shared legend-row widget for the chart windows, styled after Panel.qml's original chart legend
(charts/shell.qml's right-hand panel): a colored line swatch/name, a large bold current value with its
unit, and a min/max line below -- not a flat line of small text. Rows are given equal stretch so they
divide the panel's height by however many measures are shown, the same way the plots divide their own
column by charts/shell.qml's `panelH: (height - axisH) / panels.length`, and font sizes scale with that
per-row space instead of staying fixed regardless of how many rows there are.
"""
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class ValueRow(QWidget):
    def __init__(self, label: str, color: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(1)

        self.name_label = QLabel(label)
        layout.addWidget(self.name_label)

        self.value_label = QLabel("—")
        layout.addWidget(self.value_label)

        self.minmax_label = QLabel("")
        self.minmax_label.setWordWrap(True)
        self.minmax_label.setStyleSheet("color: gray;")
        layout.addWidget(self.minmax_label)

        self.set_color(color)

    def set_color(self, color: str):
        self.name_label.setStyleSheet(f"color: {color};")
        self.value_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def set_scale(self, value_pt: int, name_pt: int, minmax_pt: int):
        for label, pt, bold in ((self.name_label, name_pt, False), (self.value_label, value_pt, True),
                                (self.minmax_label, minmax_pt, False)):
            font = label.font()
            font.setPointSize(pt)
            font.setBold(bold)
            label.setFont(font)


def font_sizes_for(row_height: float) -> tuple[int, int, int]:
    """(value_pt, name_pt, minmax_pt) scaled to how much vertical space each row actually gets -- fewer
    measures means a taller row and a larger value; a plot's own axis label text sits around 9-10pt, so the
    current-value number is deliberately well above that, the same way charts/shell.qml's legend used a
    visibly larger, bold number (20px) against its 12px axis/title text. The min/max line specifically
    stays close to the value's own size rather than fading to a footnote."""
    value_pt = max(16, min(40, round(row_height * 0.26)))
    name_pt = max(11, round(value_pt * 0.55))
    minmax_pt = max(9, min(15, round(value_pt * 0.5)))
    return value_pt, name_pt, minmax_pt
