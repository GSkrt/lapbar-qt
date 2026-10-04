"""Windows launcher: a .pyw file runs under pythonw.exe, so double-clicking it starts the tray app without a
console window. Same entry point as lapbar-qt next to it."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name("lapbar-qt")), run_name="__main__")
