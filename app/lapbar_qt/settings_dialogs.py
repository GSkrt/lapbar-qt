"""Build-order step 6: FTP and refresh-interval dialogs -- Panel.qml had these as small in-popup panels;
here they're standard QDialogs opened from the tray's right-click menu. (Reset is simple enough to be a
QMessageBox, built directly in tray.py rather than as its own dialog class.)
"""
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton, QRadioButton, QSpinBox, QVBoxLayout

INTERVAL_CHOICES = [
    (60, "Every minute"), (120, "Every 2 minutes"), (300, "Every 5 minutes"),
    (600, "Every 10 minutes"), (900, "Every 15 minutes"), (1800, "Every 30 minutes"), (3600, "Every hour"),
]


def _interval_cost(seconds: int) -> int:
    """Roughly how many of the day's 1,000 read requests the timer alone would use (about 1.2 per refresh),
    same estimate Panel.qml's intervalCost() shows next to each choice."""
    return round(86400 / seconds * 1.2)


class IntervalDialog(QDialog):
    def __init__(self, current_sec: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Refresh every…")
        self.chosen = current_sec
        layout = QVBoxLayout(self)
        for sec, label in INTERVAL_CHOICES:
            row = QHBoxLayout()
            radio = QRadioButton(label)
            radio.setChecked(sec == current_sec)
            radio.toggled.connect(lambda checked, s=sec: checked and setattr(self, "chosen", s))
            row.addWidget(radio)
            row.addStretch(1)
            row.addWidget(QLabel(f"~{_interval_cost(sec)} requests/day"))
            layout.addLayout(row)
        note = QLabel("Strava allows about 1,000 read requests a day. Automatic refreshes pause well before "
                       "that, so refreshing by hand always has room.")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class FtpDialog(QDialog):
    def __init__(self, current_ftp: int, estimate: dict | None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("FTP")
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("FTP:"))
        self.spin = QSpinBox()
        self.spin.setRange(0, 600)
        self.spin.setSingleStep(5)
        self.spin.setSuffix(" W")
        self.spin.setSpecialValueText("not set")
        self.spin.setValue(current_ftp)
        row.addWidget(self.spin)
        row.addStretch(1)
        layout.addLayout(row)

        if estimate:
            estimate_button = QPushButton(f"Estimate from my rides: {estimate['watts']} W")
            estimate_button.clicked.connect(lambda: self.spin.setValue(estimate["watts"]))
            layout.addWidget(estimate_button)
            hint = QLabel(
                f"Sets your FTP to the highest weighted power in your {estimate['rides']} power rides of 40 "
                "minutes or more. A ballpark: for an exact figure, do an FTP test. You can adjust it afterwards.")
            hint.setWordWrap(True)
            layout.addWidget(hint)

        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(lambda: self.spin.setValue(0))
        layout.addWidget(clear_button)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
