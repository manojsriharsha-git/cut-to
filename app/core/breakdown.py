"""
Production breakdown and shot lists, as plain data (no windows), so they can be
tested and exported.

Each scene heading may carry:
  extra["breakdown"] = {"Props": ["Telescope", "Notebook"], "Vehicles": ["Jeep"], ...}
  extra["shots"]     = [{"shot": "1", "size": "WS", "angle": "Eye level", "move": "Static",
                         "lens": "35mm", "description": "...", "notes": ""}, ...]
Cast is never stored: it is read from who speaks in the scene.
"""
from __future__ import annotations

import csv
import html
import io
from dataclasses import dataclass, field

# Industry breakdown categories with their traditional highlight colours.
CATEGORIES = [
    ("Cast", "#E57373"), ("Extras", "#81C784"), ("Stunts", "#FFB74D"), ("Vehicles", "#F48FB1"),
    ("Props", "#BA68C8"), ("Special Effects", "#64B5F6"), ("Wardrobe", "#A1887F"),
    ("Makeup & Hair", "#F06292"), ("Animals", "#AED581"), ("Sound & Music", "#4DD0E1"),
    ("Set Dressing", "#DCE775"), ("Special Equipment", "#90A4AE"), ("Visual Effects", "#7986CB"),
    ("Locations", "#FFD54F"),
]
CATEGORY_COLOR = dict(CATEGORIES)
SHOT_FIELDS = [("shot", "Shot"), ("size", "Size"), ("angle", "Angle"), ("move", "Movement"),
               ("lens", "Lens"), ("description", "Description"), ("notes", "Notes")]
SHOT_SIZES = ["EWS", "WS", "FS", "MWS", "MS", "MCU", "CU", "ECU", "OTS", "POV", "Insert", "Two-shot"]
SHOT_ANGLES = ["Eye level", "High", "Low", "Overhead", "Dutch", "Ground"]
SHOT_MOVES = ["Static", "Pan", "Tilt", "Dolly", "Track", "Crane", "Handheld", "Steadicam", "Zoom", "Drone"]


@dataclass
class SceneBreakdown:
    number: str
    heading: str
    intro: str
    location: str
    time: str
    length: str                       # eighths, e.g. "1 3/8"
    page: int
    synopsis: str
    cast: list[str]
    items: dict[str, list[str]] = field(default_factory=dict)
    shots: list[dict] = field(default_factory=list)


def tag(items: dict, category: str, text: str) -> dict:
    """Add an element to a scene's breakdown (no duplicates, case-insensitive)."""
    text = " ".join(text.split())
    out = {k: list(v) for k, v in items.items()}
    lst = out.setdefault(category, [])
    if text and text.lower() not in (x.lower() for x in lst):
        lst.append(text)
    return out


def untag(items: dict, category: str, text: str) -> dict:
    out = {k: [x for x in v if not (k == category and x.lower() == text.lower())] for k, v in items.items()}
    return {k: v for k, v in out.items() if v}


def breakdown_csv(scenes: list[SceneBreakdown]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    cats = [c for c, _ in CATEGORIES if c != "Cast"]
    w.writerow(["Scene", "Heading", "Int/Ext", "Location", "Time", "Pages", "Page", "Cast"] + cats)
    for s in scenes:
        w.writerow([s.number, s.heading, s.intro, s.location, s.time, s.length, s.page,
                    "; ".join(s.cast)] + ["; ".join(s.items.get(c, [])) for c in cats])
    return buf.getvalue()


def shots_csv(scenes: list[SceneBreakdown]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Scene", "Heading"] + [label for _k, label in SHOT_FIELDS])
    for s in scenes:
        for shot in s.shots:
            w.writerow([s.number, s.heading] + [shot.get(k, "") for k, _l in SHOT_FIELDS])
    return buf.getvalue()


def sheets_html(scenes: list[SceneBreakdown], title: str) -> str:
    """Breakdown sheets, one per scene, ready to print (each starts on a new page)."""
    e = html.escape
    out = ["<html><body style='font-family:Helvetica,Arial;font-size:10pt'>"]
    for i, s in enumerate(scenes):
        brk = " style='page-break-before:always'" if i else ""
        out.append(f"<div{brk}>")
        out.append(f"<p style='font-size:8pt;color:#8C7D70'>{e(title)} · BREAKDOWN SHEET</p>")
        out.append(f"<h2 style='margin:2px 0'>Scene {e(s.number)} — {e(s.heading)}</h2>")
        out.append(f"<p><b>{e(s.intro)}</b> · {e(s.location)} · {e(s.time or '—')} · "
                   f"{e(s.length)} pages · page {s.page}</p>")
        if s.synopsis:
            out.append(f"<p><i>{e(s.synopsis)}</i></p>")
        out.append("<table width='100%' cellspacing='0' cellpadding='6' border='1' "
                   "style='border-collapse:collapse;border-color:#DCD2C7'>")
        cells = [("Cast", s.cast)] + [(c, s.items.get(c, [])) for c, _ in CATEGORIES if c != "Cast"]
        cells = [c for c in cells if c[1]] or [("Cast", ["—"])]
        for j in range(0, len(cells), 2):
            out.append("<tr>")
            for name, vals in cells[j:j + 2]:
                color = CATEGORY_COLOR.get(name, "#ccc")
                out.append(f"<td width='50%' valign='top'><span style='background:{color};padding:1px 6px'>"
                           f"<b>{e(name)}</b></span><br>{'<br>'.join(e(v) for v in vals)}</td>")
            out.append("</tr>")
        out.append("</table>")
        if s.shots:
            out.append("<h3>Shot list</h3><table width='100%' cellspacing='0' cellpadding='4' border='1' "
                       "style='border-collapse:collapse'><tr>"
                       + "".join(f"<th align='left'>{e(lbl)}</th>" for _k, lbl in SHOT_FIELDS) + "</tr>")
            for shot in s.shots:
                out.append("<tr>" + "".join(f"<td>{e(str(shot.get(k, '')))}</td>" for k, _l in SHOT_FIELDS)
                           + "</tr>")
            out.append("</table>")
        out.append("</div>")
    out.append("</body></html>")
    return "".join(out)


def stripboard(scenes: list[SceneBreakdown]) -> list[tuple[str, str, str, str, str, str]]:
    """One strip per scene, ordered for shooting: by location, then day before night."""
    order = {"DAY": 0, "MORNING": 0, "AFTERNOON": 1, "DUSK": 2, "EVENING": 2, "NIGHT": 3}
    rows = sorted(scenes, key=lambda s: (s.location, s.intro, order.get(s.time.upper(), 1)))
    return [(s.number, s.intro, s.location, s.time, s.length, ", ".join(s.cast)) for s in rows]
