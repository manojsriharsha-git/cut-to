"""Rebuild the app icons from the logo artwork.

Source:  resources/icons/cutto-1024.png  (the Cut To: logo, 1024 x 1024)
Makes:   resources/icons/cutto.png (256 px, used by the app window)
         resources/icons/cutto.ico (16-256 px, used by the exe, installer and file icons)

Run:  python tools/make_icon.py
"""
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "resources" / "icons"
SIZES = [16, 24, 32, 48, 64, 128, 256]


def main():
    QGuiApplication([])
    src = QImage(str(ICONS / "cutto-1024.png"))
    if src.isNull():
        raise SystemExit("resources/icons/cutto-1024.png is missing")
    smooth = Qt.TransformationMode.SmoothTransformation
    src.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, smooth).save(str(ICONS / "cutto.png"))
    try:
        from PIL import Image                     # best .ico (all sizes in one file)
        Image.open(ICONS / "cutto-1024.png").save(ICONS / "cutto.ico", sizes=[(s, s) for s in SIZES])
    except ImportError:                           # Qt can write a single-size .ico
        src.scaled(256, 256, Qt.AspectRatioMode.KeepAspectRatio, smooth).save(str(ICONS / "cutto.ico"))
        print("Tip: pip install pillow for an .ico with every size from 16 to 256 px")
    print("Icons written to", ICONS)


if __name__ == "__main__":
    main()
