"""Import a screenplay from a PDF (any app's export), using pdfplumber.

A screenplay PDF has no element names, only positions. Like a reader's eye, this
reads each line's left edge relative to the action margin:

    +0.0 in  action, scene heading (INT./EXT.), shot
    +1.0 in  dialogue
    +1.5 in  parenthetical
    +2.0 in  character name
    far right / ends in TO:   transition

Page numbers, (MORE) and NAME (CONT'D) at page breaks are removed, and a speech
split across pages is joined back together. Scene numbers in the margins are kept.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ..core.ir import T, Element, Script

SCENE_START = re.compile(r"^(INT|EXT|EST|INT\./EXT|INT/EXT|I/E)[\. ]", re.I)
PAGE_NUM = re.compile(r"^\d+\.?$")
CONTD = re.compile(r"\(CONT['’]D\)|\(CONTINUED\)", re.I)


@dataclass
class Line:
    page: int
    top: float          # points from the page top
    left: float         # inches from the page's left edge
    right: float        # inches
    text: str
    number: str | None = None   # scene number found in a margin


def _lines(pdf) -> list[Line]:
    out = []
    for pno, page in enumerate(pdf.pages):
        words = page.extract_words(keep_blank_chars=False, use_text_flow=False, x_tolerance=1.5)
        rows: dict[int, list] = {}
        for w in words:
            rows.setdefault(round(w["top"] / 3), []).append(w)
        for key in sorted(rows):
            ws = sorted(rows[key], key=lambda w: w["x0"])
            body = [w for w in ws if 1.3 * 72 <= w["x0"] <= 7.3 * 72]
            margin = [w for w in ws if w not in body]
            number = None
            for w in margin:
                if re.fullmatch(r"\d+[A-Z]?\.?", w["text"]):
                    number = w["text"].rstrip(".")
            if not body:
                continue
            text, last = "", None
            for w in body:                                  # keep Courier's double spaces
                if last is not None:
                    gap = (w["x0"] - last) / 7.2
                    text += " " * max(1, round(gap))
                text += w["text"]
                last = w["x1"]
            out.append(Line(pno, body[0]["top"], body[0]["x0"] / 72, body[-1]["x1"] / 72, text, number))
    return out


def _strip_furniture(lines: list[Line]) -> list[Line]:
    out = []
    by_page: dict[int, list[Line]] = {}
    for ln in lines:
        by_page.setdefault(ln.page, []).append(ln)
    for page, ls in by_page.items():
        for i, ln in enumerate(ls):
            s = ln.text.strip()
            if i == 0 and PAGE_NUM.match(s) and ln.left > 6.0:
                continue                                    # page number, top right
            if s.upper() in ("(MORE)", "(CONTINUED)", "CONTINUED:") or \
                    (s.upper().startswith("CONTINUED") and i <= 1):
                continue
            out.append(ln)
    return out


def classify(lines: list[Line]) -> list[Element]:
    lefts = Counter(round(ln.left, 1) for ln in lines)
    action = min((x for x, n in lefts.most_common(4)), default=1.5)
    els: list[Element] = []
    prev_top = prev_page = None
    prev_off = None
    for ln in lines:
        s = ln.text.strip()
        off = ln.left - action
        gap = None if prev_top is None or ln.page != prev_page else ln.top - prev_top
        new_par = gap is None or gap > 16 or abs(off - (prev_off or 0)) > 0.3 or ln.page != prev_page
        caps = s == s.upper() and any(c.isalpha() for c in s)
        if SCENE_START.match(s) and off < 0.4:
            etype = T.SCENE_HEADING
        elif off > 3.2 or (caps and s.endswith("TO:")) or s.upper() in ("FADE OUT.", "FADE TO BLACK."):
            etype = T.TRANSITION
        elif 1.8 <= off <= 3.2 and caps:
            etype = T.CHARACTER
        elif 1.3 <= off < 1.8 and s.startswith("("):
            etype = T.PARENTHETICAL
        elif 0.7 <= off < 1.8:
            etype = T.DIALOGUE
        else:
            etype = T.ACTION
        # a speech continuing after a page break: drop "NAME (CONT'D)" and join
        if etype == T.CHARACTER and CONTD.search(s) and ln.page != prev_page and els:
            name = CONTD.sub("", s).strip()
            prev_speaker = next((e.text for e in reversed(els) if e.type == T.CHARACTER), "")
            last = els[-1]
            if last.type in (T.DIALOGUE, T.PARENTHETICAL) and CONTD.sub("", prev_speaker).strip() == name:
                prev_top, prev_page, prev_off = ln.top, ln.page, 1.0
                continue
        if not new_par and els and els[-1].type == etype and etype != T.CHARACTER:
            last = els[-1]
            sep = " " if not last.text.endswith("-") else ""
            last.runs[0].text += sep + s
        elif (gap is not None and gap <= 16 and els and etype == T.DIALOGUE
              and els[-1].type == T.DIALOGUE and ln.page != prev_page):
            els[-1].runs[0].text += " " + s
        else:
            el = Element.plain(etype, s)
            if etype == T.SCENE_HEADING and ln.number:
                el.scene_number = ln.number
                el.runs[0].text = re.sub(rf"\s*{re.escape(ln.number)}\.?$", "", s).strip()
            els.append(el)
        prev_top, prev_page, prev_off = ln.top, ln.page, off
    return els


def read(path: str | Path) -> Script:
    try:
        import pdfplumber
    except ImportError as ex:                             # pragma: no cover
        raise RuntimeError("PDF import needs the pdfplumber package (pip install pdfplumber)") from ex
    with pdfplumber.open(str(path)) as pdf:
        lines = _lines(pdf)
    title_page = []
    if lines:
        first = [ln for ln in lines if ln.page == 0]
        if first and not any(SCENE_START.match(ln.text.strip()) for ln in first) and len(first) < 30:
            centred = [ln.text.strip() for ln in first if abs((ln.left + ln.right) / 2 - 4.25) < 0.4]
            if centred:
                title_page.append(("Title", centred[0]))
                rest = [c for c in centred[1:] if c.lower() not in ("written by", "by")]
                if rest:
                    title_page.append(("Credit", "Written by"))
                    title_page.append(("Author", rest[-1]))
            lines = [ln for ln in lines if ln.page != 0]
    return Script(title_page=title_page, elements=classify(_strip_furniture(lines)))
