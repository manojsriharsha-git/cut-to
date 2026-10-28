"""Import-only formats from other screenwriting apps.

  .celtx      Celtx (classic desktop): a zip with the script as HTML, one <p class="..."> per element.
  .trelby     Trelby: text after "#Start-Script", each line = break code + element code + text.
  .highland   Highland 2: a zip holding the script as Fountain (text.md / .fountain).
  .fadein     Fade In: a zip holding the script as Open Screenplay Format XML (document.xml).
"""
from __future__ import annotations

import html
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path

from ..core.ir import T, Element, Script, Run, merge_runs
from . import fountain

CELTX_CLASSES = {
    "sceneheading": T.SCENE_HEADING, "action": T.ACTION, "character": T.CHARACTER,
    "parenthetical": T.PARENTHETICAL, "dialog": T.DIALOGUE, "dialogue": T.DIALOGUE,
    "transition": T.TRANSITION, "shot": T.SHOT, "act": T.SCENE_HEADING, "text": T.GENERAL,
}


class _CeltxHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.els: list[Element] = []
        self.cls: str | None = None
        self.style = {"b": 0, "i": 0, "u": 0}
        self.runs: list[Run] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "p":
            self.cls = (a.get("class") or "action").lower()
            self.runs = []
        elif tag in ("b", "strong"):
            self.style["b"] += 1
        elif tag in ("i", "em"):
            self.style["i"] += 1
        elif tag == "u":
            self.style["u"] += 1
        elif tag == "br" and self.cls:
            self.runs.append(Run("\n"))

    def handle_endtag(self, tag):
        if tag == "p" and self.cls is not None:
            runs = merge_runs(self.runs)
            text = "".join(r.text for r in runs).strip()
            if text:
                self.els.append(Element(CELTX_CLASSES.get(self.cls, T.ACTION), runs))
            self.cls = None
        elif tag in ("b", "strong"):
            self.style["b"] = max(0, self.style["b"] - 1)
        elif tag in ("i", "em"):
            self.style["i"] = max(0, self.style["i"] - 1)
        elif tag == "u":
            self.style["u"] = max(0, self.style["u"] - 1)

    def handle_data(self, data):
        if self.cls is not None:
            text = re.sub(r"\s+", " ", data)
            if text:
                self.runs.append(Run(text, self.style["b"] > 0, self.style["i"] > 0, self.style["u"] > 0))


def celtx(path: str | Path) -> Script:
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith((".html", ".htm"))]
        script_name = next((n for n in names if "script" in n.lower()), names[0] if names else None)
        if script_name is None:
            raise ValueError("No script found inside this Celtx file")
        text = z.read(script_name).decode("utf-8", "replace")
    p = _CeltxHTML()
    p.feed(text)
    for el in p.els:                                  # Celtx keeps leading/trailing spaces
        if el.runs:
            el.runs[0].text = el.runs[0].text.lstrip()
            el.runs[-1].text = el.runs[-1].text.rstrip()
    return Script(elements=p.els)


# Trelby: every line is <linebreak><type><text>. A paragraph ends at linebreak ".".
TRELBY_TYPES = {"\\": T.SCENE_HEADING, ".": T.ACTION, "_": T.CHARACTER, ":": T.DIALOGUE,
                "(": T.PARENTHETICAL, "/": T.TRANSITION, "=": T.SHOT, "%": T.NOTE, "@": T.SCENE_HEADING}


def trelby(text: str) -> Script:
    lines = text.replace("\r\n", "\n").split("\n")
    title_page = []
    try:
        start = lines.index("#Start-Script") + 1
    except ValueError:
        raise ValueError("Not a Trelby file (no #Start-Script line)")
    for ln in lines[:start]:
        if ln.startswith("#Title-String "):
            parts = ln[len("#Title-String "):].split(",", 4)
            if len(parts) == 5 and not title_page:
                title_page.append(("Title", parts[4]))
    els: list[Element] = []
    buf: list[str] = []
    cur_type = None
    for ln in lines[start:]:
        if ln.startswith("#") or len(ln) < 2:
            continue
        lb, code, body = ln[0], ln[1], ln[2:]
        etype = TRELBY_TYPES.get(code, T.ACTION)
        if cur_type is None:
            cur_type = etype
        buf.append(body)
        joiner = {" ": " ", "+": "  ", "&": "", "|": "\n"}
        if lb == ".":
            els.append(Element.plain(cur_type, "".join(buf).strip()))
            buf, cur_type = [], None
        else:
            buf[-1] = buf[-1] + joiner.get(lb, " ")
    if buf:
        els.append(Element.plain(cur_type or T.ACTION, "".join(buf).strip()))
    return Script(title_page=title_page, elements=els)


def highland(path: str | Path) -> Script:
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.lower().endswith((".fountain", ".md", ".txt"))]
        name = next((n for n in names if n.lower().endswith("text.md")), names[0] if names else None)
        if name is None:
            raise ValueError("No script found inside this Highland file")
        return fountain.parse(z.read(name).decode("utf-8-sig", "replace"))


OSF_TYPES = {"Scene Heading": T.SCENE_HEADING, "Action": T.ACTION, "Character": T.CHARACTER,
             "Parenthetical": T.PARENTHETICAL, "Dialogue": T.DIALOGUE, "Transition": T.TRANSITION,
             "Shot": T.SHOT, "General": T.GENERAL}


def fadein(path: str | Path) -> Script:
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("document.xml"))
    els = []
    for para in root.iter("para"):
        style = para.find("style")
        base = style.get("basestyle") if style is not None else "Action"
        runs = []
        for t in para.iter("text"):
            st = t.get("style", "")
            runs.append(Run(html.unescape(t.text or ""), "Bold" in st, "Italic" in st, "Underline" in st))
        el = Element(OSF_TYPES.get(base, T.ACTION), merge_runs(runs))
        if el.text.strip():
            els.append(el)
    return Script(elements=els)
