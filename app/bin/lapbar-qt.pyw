"""Windows launcher: a .pyw file runs under pythonw.exe, so double-clicking it starts the tray app without a
console window. Same entry point as lapbar-qt next to it."""
import os
import runpy
import sys
from pathlib import Path

# pythonw has no console: sys.stdout/stderr/stdin are None, and anything writing to them would crash.
for _name, _mode in (("stdout", "w"), ("stderr", "w"), ("stdin", "r")):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, _mode, encoding="utf-8"))

runpy.run_path(str(Path(__file__).with_name("lapbar-qt")), run_name="__main__")
