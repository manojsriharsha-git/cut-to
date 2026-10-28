"""Toolbar icons drawn from tiny inline SVG shapes, so no image files are needed.

Every icon is a 24x24 line drawing; `icon(name)` returns a QIcon in the ink colour.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QByteArray, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtSvg import QSvgRenderer

from .theme import C

PATHS = {
    "new": "M6 3h8l4 4v14H6z M14 3v4h4 M12 11v6 M9 14h6",
    "open": "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z",
    "save": "M5 4h11l3 3v13H5z M8 4v5h7V4 M8 20v-6h8v6",
    "undo": "M9 6l-5 5 5 5 M4 11h10a5 5 0 0 1 0 10h-3",
    "redo": "M15 6l5 5-5 5 M20 11H10a5 5 0 0 0 0 10h3",
    "bold": "M7 5h6a3.5 3.5 0 0 1 0 7H7z M7 12h7.5a3.5 3.5 0 0 1 0 7H7z",
    "italic": "M10 5h8 M6 19h8 M14 5l-4 14",
    "underline": "M7 4v7a5 5 0 0 0 10 0V4 M5 20h14",
    "strike": "M16.5 7.5A4.5 4.5 0 0 0 12 5c-2.6 0-4.3 1.4-4.3 3.3 0 1.3.8 2.2 2.3 2.7"
              " M4 12h16 M7.5 16.5C8.2 18 9.9 19 12 19c2.7 0 4.5-1.4 4.5-3.4 0-.6-.2-1.1-.5-1.6",
    "color": "M7 16l5-12 5 12 M8.7 12h6.6",
    "highlight": "M14.5 4.5l5 5L11 18H6v-5z M12 7l5 5",
    "case": "M3 17l4-10 4 10 M4.4 13.5h5.2 M15.5 11.2a2.8 2.8 0 1 0 0 5.6 2.8 2.8 0 0 0 0-5.6z M18.3 9.5v7.5",
    "clear": "M6 5h12 M12 5l-3 14 M14 14l6 6 M20 14l-6 6",
    "image": "M4 5h16v14H4z M9.5 8.5a1.5 1.5 0 1 0 0 3 1.5 1.5 0 0 0 0-3z M4 16l4.5-4.5 4 4 2.5-2.5 5 5",
    "link": "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"
            " M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
    "pagebreak": "M6 3v5h12V3 M6 21v-5h12v5 M3 12h2 M8 12h3 M13 12h3 M19 12h2",
    "scenes_num": "M5 9h14 M5 15h14 M10.5 4L8.5 20 M15.5 4l-2 16",
    "title": "M6 3h12v18H6z M9 8h6 M10 11h4 M9.5 17h5",
    "reports": "M5 20V11 M12 20V4 M19 20v-7 M3 20h18",
    "sidebar": "M4 5h16v14H4z M9.5 5v14",
    "zoom_in": "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z M16 16l4 4 M8 11h6 M11 8v6",
    "zoom_out": "M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14z M16 16l4 4 M8 11h6",
    "print": "M7 8V3h10v5 M7 17H5a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"
             " M7 13h10v8H7z",
    "pdf": "M6 3h8l4 4v14H6z M14 3v4h4 M12 10v7 M9 14l3 3 3-3",
    "check": "M5 12.5l4.5 4.5L19 7.5",
    "search": "M10.5 4a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13z M15.5 15.5L20 20",
    "script": "M7 3h7l4 4v14H7z M14 3v4h4 M10 12h5 M10 16h5",
    "cards": "M3 5h8v6H3z M13 5h8v6h-8z M3 13h8v6H3z M13 13h8v6h-8z",
    "board": "M4 5h6v5H4z M14 14h6v5h-6z M14 5h6v5h-6z M10 7.5h4 M17 10v4",
    "people": "M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6 M16 4.5a3.5 3.5 0 0 1 0 6.5 M18 14c2 .7 3 2.8 3 6",
    "chart": "M4 20h16 M7 20v-6 M11 20V8 M15 20v-9 M19 20V5",
    "note": "M5 4h14v11l-5 5H5z M14 20v-5h5",
    "revision": "M4 20l4-1 11-11-3-3L5 16z M14 7l3 3",
    "history": "M4 12a8 8 0 1 0 2.3-5.7 M4 4v4h4 M12 8v4l3 2",
    "tag": "M3 12V4h8l10 10-8 8z M7.5 8.5h.01",
    "shot": "M3 7h12v10H3z M15 10l6-3v10l-6-3z",
    "play": "M7 5l12 7-12 7z",
    "stop": "M7 7h10v10H7z",
    "pause": "M8 5v14 M16 5v14",
    "moon": "M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z",
    "focus": "M4 9V4h5 M15 4h5v5 M20 15v5h-5 M9 20H4v-5",
    "command": "M5 7l5 5-5 5 M12 17h7",
    "plus": "M12 5v14 M5 12h14",
    "trash": "M5 7h14 M10 7V4h4v3 M7 7l1 13h8l1-13",
    "lock": "M6 11h12v9H6z M8.5 11V8a3.5 3.5 0 0 1 7 0v3",
    "speak": "M4 9h4l5-4v14l-5-4H4z M16.5 9a4 4 0 0 1 0 6 M19 6.5a7.5 7.5 0 0 1 0 11",
    "export": "M12 4v11 M7.5 10.5L12 15l4.5-4.5 M5 20h14",
    "import": "M12 15V4 M7.5 8.5L12 4l4.5 4.5 M5 20h14",
    "production": "M4 8h16v12H4z M4 8l3-4h10l3 4 M9 13h6",
}


def svg(name: str, color: str | None = None, width: float = 1.8) -> str:
    color = color or C.INK
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
            f'stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
            f'stroke-linejoin="round"><path d="{PATHS[name]}"/></svg>')


def pixmap(name: str, size: int = 20, color: str | None = None, swatch: str | None = None,
           ratio: float = 2.0) -> QPixmap:
    """Render one icon. `swatch` adds a colour bar under it (text colour / highlight)."""
    px = QPixmap(int(size * ratio), int(size * ratio))
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg(name, color).encode())).render(p, QRectF(0, 0, px.width(), px.height()))
    if swatch:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(swatch))
        s = px.width() / 24
        p.drawRoundedRect(QRectF(4 * s, 19.5 * s, 16 * s, 3 * s), 1.2 * s, 1.2 * s)
    p.end()
    px.setDevicePixelRatio(ratio)
    return px


def icon(name: str, swatch: str | None = None) -> QIcon:
    ic = QIcon()
    ic.addPixmap(pixmap(name, swatch=swatch), QIcon.Mode.Normal)
    ic.addPixmap(pixmap(name, color=C.THUMB, swatch=swatch), QIcon.Mode.Disabled)
    return ic
