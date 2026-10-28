"""Find bundled files both when running from PyCharm and inside a PyInstaller .exe."""
import sys
from pathlib import Path

_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def resource_path(*parts: str) -> str:
    return str(_BASE.joinpath("resources", *parts))
