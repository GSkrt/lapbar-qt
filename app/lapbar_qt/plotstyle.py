"""One look for every plot in the app: a light grid behind the data and axis labels that carry their unit.

Labels are plain text ("Speed (km/h)"), never pyqtgraph's `units=` mode: that one adds SI prefixes on its own
(a 2,000 m climb becomes "2 km" on one plot and stays "m" on the next) and rescales the tick numbers to match.

Units used for fitness: every activity's load is in points on the TSS scale (fitness.py: power TSS, or
Strava's Relative Effort, or time x a rate per sport). Fitness and fatigue are averages of daily load, so
they, and form (their difference), are in points per day.
"""
from PyQt6.QtGui import QFont

GRID_ALPHA = 0.35              # visible but light against the dark plot background
LABEL_COLOR = "#bbbbbb"
LABEL_PT = 8
LOAD_UNIT = "pts"
FITNESS_UNIT = "pts/day"


def tick_font(points: int = LABEL_PT) -> QFont:
    font = QFont()
    font.setPointSize(points)
    return font


def style(plot, left: str | None = None, bottom: str | None = None) -> None:
    """Grid on both axes, no automatic SI prefixes, and the given axis labels (text with its unit)."""
    plot.showGrid(x=True, y=True, alpha=GRID_ALPHA)
    for side, text in (("left", left), ("bottom", bottom)):
        axis = plot.getAxis(side)
        axis.enableAutoSIPrefix(False)
        if text:
            plot.setLabel(side, text, **{"color": LABEL_COLOR, "font-size": f"{LABEL_PT}pt"})


def label(name: str, unit: str | None) -> str:
    return f"{name} ({unit})" if unit else name
