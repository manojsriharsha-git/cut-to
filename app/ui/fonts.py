"""
Fonts: the free, open-licence fonts that come with Cut To:, fonts you add yourself,
and the fonts already installed on this computer.

  resources/fonts/fonts.json   the bundled families (name, group, files, licence)
  %APPDATA%/Cut To/fonts/      fonts added with Format > Add Font File…

Screenplays are traditionally typed in Courier 12 pt; the page count (one page ≈ one
minute) only holds for a Courier-style typewriter font. Other fonts are for title
pages, notes and documents.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from PySide6.QtGui import QFontDatabase

from ..resources import resource_path

GET_MORE_URL = "https://fonts.google.com/"
DEFAULT_FONT = "Courier Prime"
GROUPS = {"Screenplay": "Screenplay (typewriter)", "Document": "Documents", "Title": "Titles"}
FONT_EXT = (".ttf", ".otf")


def bundled() -> list[dict]:
    try:
        return json.loads(Path(resource_path("fonts", "fonts.json")).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def user_dir(data: Path) -> Path:
    return Path(data) / "fonts"


def load_all(data: Path | None = None) -> list[str]:
    """Register the bundled fonts and the user's added fonts. Returns families that failed."""
    failed = []
    for fam in bundled():
        ok = False
        for f in fam["files"]:
            ok |= QFontDatabase.addApplicationFont(resource_path("fonts", fam["folder"], f)) >= 0
        if not ok:
            failed.append(fam["name"])
    if data is not None and user_dir(data).is_dir():
        for f in sorted(user_dir(data).iterdir()):
            if f.suffix.lower() in FONT_EXT:
                QFontDatabase.addApplicationFont(str(f))
    return failed


def add_font_file(path: str, data: Path) -> list[str]:
    """Copy a downloaded .ttf/.otf into the app's font folder and use it. Returns its families."""
    src = Path(path)
    if src.suffix.lower() not in FONT_EXT:
        return []
    dest_dir = user_dir(data)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    if src.resolve() != dest.resolve():
        shutil.copy2(src, dest)
    fid = QFontDatabase.addApplicationFont(str(dest))
    return list(QFontDatabase.applicationFontFamilies(fid)) if fid >= 0 else []


def font_groups() -> list[tuple[str, list[str]]]:
    """[(group title, [family, ...]), ...]: bundled groups first, then the computer's own."""
    out: dict[str, list[str]] = {}
    seen = set()
    for fam in bundled():
        out.setdefault(GROUPS.get(fam["group"], fam["group"]), []).append(fam["name"])
        seen.add(fam["name"])
    system = []
    for f in QFontDatabase.families():
        plain = re.sub(r"\s*\[[^\]]*\]$", "", f)          # "Roboto Mono [GOOG]" -> "Roboto Mono"
        if plain in seen or f.startswith("@") or QFontDatabase.isPrivateFamily(f) \
                or any(plain.startswith(s + " ") for s in seen):
            continue
        system.append(f)
    groups = list(out.items())
    if system:
        groups.append(("On this computer", sorted(set(system), key=str.lower)))
    return groups


def is_typewriter(family: str) -> bool:
    return family in next((names for title, names in font_groups() if title == GROUPS["Screenplay"]), []) \
        or QFontDatabase.isFixedPitch(family)
