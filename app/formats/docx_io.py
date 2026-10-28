"""Microsoft Word (.docx) import and export, using python-docx.

Export: one Word paragraph per element, Courier Prime 12pt, industry-standard indents,
and a named paragraph style per element ("Screenplay Scene Heading", ...), so a
file exported here comes back exactly.

Import: paragraphs with those style names map straight back. Any other Word file
(a script typed in Word) is read by its indents and capitals, the same way a
reader's eye would: CAPS at the left = scene heading, CAPS in the middle =
character, indented text under a character = dialogue, (text) = parenthetical,
CAPS ending in TO: = transition.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..core.ir import T, Run, Element, Script, merge_runs
from ..core.layout import ELEMENT_SPECS

STYLE_PREFIX = "Screenplay "
SCENE_START = re.compile(r"^(INT|EXT|EST|INT\./EXT|INT/EXT|I/E)[\. ]", re.I)


def _require():
    import importlib.util
    if importlib.util.find_spec("docx") is None:      # pragma: no cover
        raise RuntimeError("Word files need the python-docx package (pip install python-docx)")


# ------------------------------------------------------------------ export
def write(script: Script, path: str | Path):
    _require()
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.style import WD_STYLE_TYPE

    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Inches(8.5), Inches(11)
    sec.left_margin = sec.right_margin = Inches(1.0)   # indents are measured from these
    sec.top_margin = sec.bottom_margin = Inches(1.0)
    base = doc.styles["Normal"]
    base.font.name = "Courier Prime"
    base.font.size = Pt(12)
    base.paragraph_format.space_after = Pt(0)
    base.paragraph_format.space_before = Pt(0)

    styles = {}
    for etype, (left, right, before, align, caps, _next) in ELEMENT_SPECS.items():
        st = doc.styles.add_style(STYLE_PREFIX + etype, WD_STYLE_TYPE.PARAGRAPH)
        st.base_style = base
        pf = st.paragraph_format
        pf.left_indent = Inches(left - 1.0)
        pf.right_indent = Inches(8.5 - 1.0 - right)
        pf.space_before = Pt(before)
        pf.line_spacing = 1.0
        if align == "Right":
            pf.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        st.font.all_caps = caps
        if etype in (T.SCENE_HEADING, T.CHARACTER):
            pf.keep_with_next = True
        styles[etype] = st
    for extra in (T.NOTE, T.SECTION, T.SYNOPSIS, T.LYRICS, T.IMAGE):
        st = doc.styles.add_style(STYLE_PREFIX + extra, WD_STYLE_TYPE.PARAGRAPH)
        st.base_style = styles[T.ACTION]
        if extra in (T.NOTE, T.SYNOPSIS):
            st.font.italic = True
            st.font.color.rgb = RGBColor(0xC8, 0x8E, 0x5C)
        styles[extra] = st

    # title page
    tp = {k.lower(): v for k, v in script.title_page}
    if tp:
        for _ in range(14):
            doc.add_paragraph()
        for key in ("title", "credit", "author", "source"):
            for line in tp.get(key, "").split("\n"):
                if line.strip():
                    p = doc.add_paragraph(line.strip())
                    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            if tp.get(key):
                doc.add_paragraph()
        for key in ("draft date", "contact"):
            for line in tp.get(key, "").split("\n"):
                if line.strip():
                    doc.add_paragraph(line.strip())
        doc.add_page_break()

    first = True
    for el in script.elements:
        style = styles.get(el.type, styles[T.ACTION])
        p = doc.add_paragraph(style=style)
        if first:
            p.paragraph_format.space_before = Pt(0)
            first = False
        if el.page_break_before:
            p.paragraph_format.page_break_before = True
        if el.centered:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if el.type == T.IMAGE:
            p.add_run(el.text)
            continue
        if el.scene_number and el.type == T.SCENE_HEADING:
            p.add_run(f"{el.scene_number}  ")
        for r in el.runs:
            run = p.add_run(r.text)
            run.bold = r.bold or None
            run.italic = r.italic or None
            run.underline = r.underline or None
            run.font.strike = r.strike or None
            if r.color:
                run.font.color.rgb = RGBColor.from_string(r.color.lstrip("#"))
            if r.font:
                run.font.name = r.font
    doc.core_properties.title = script.title() or ""
    doc.core_properties.comments = "Written with Cut To:"
    doc.save(str(path))


# ------------------------------------------------------------------ import
def _runs(par) -> list[Run]:
    out = []
    for r in par.runs:
        color = None
        try:
            if r.font.color is not None and r.font.color.type is not None and r.font.color.rgb:
                c = str(r.font.color.rgb).upper()
                color = None if c in ("000000", "C88E5C") else "#" + c
        except (AttributeError, ValueError):
            color = None
        font = r.font.name if r.font.name and not r.font.name.lower().startswith("courier") else None
        out.append(Run(r.text, bool(r.bold), bool(r.italic), bool(r.underline),
                       bool(r.font.strike), color, font=font))
    return merge_runs(out)


def _indent_in(par, attr: str) -> float:
    v = getattr(par.paragraph_format, attr)
    if v is None and par.style is not None:
        st = par.style
        while st is not None and v is None:
            v = getattr(st.paragraph_format, attr)
            st = st.base_style
    return (v.inches if v is not None else 0.0)


def guess_type(text: str, left: float, prev: str | None, centered: bool = False,
               right_aligned: bool = False) -> str:
    """Element type of an unstyled paragraph from its look. `left` is inches from the page edge."""
    s = text.strip()
    caps = s == s.upper() and any(c.isalpha() for c in s)
    if SCENE_START.match(s):
        return T.SCENE_HEADING
    if caps and (s.endswith("TO:") or s in ("FADE OUT.", "FADE TO BLACK.", "CUT TO BLACK.")) \
            or (right_aligned and caps):
        return T.TRANSITION
    if s.startswith("(") and s.endswith(")") and prev in (T.CHARACTER, T.DIALOGUE, T.PARENTHETICAL):
        return T.PARENTHETICAL
    if caps and (left >= 3.2 or centered) and len(s) < 40:
        return T.CHARACTER
    if prev in (T.CHARACTER, T.PARENTHETICAL) or (prev == T.DIALOGUE and 2.2 <= left < 3.2):
        return T.DIALOGUE
    return T.ACTION


def read(path: str | Path) -> Script:
    _require()
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    doc = Document(str(path))
    els: list[Element] = []
    prev = None
    styled = any((p.style is not None and p.style.name.startswith(STYLE_PREFIX)) for p in doc.paragraphs)
    for par in doc.paragraphs:
        text = par.text
        if not text.strip():
            if prev == T.DIALOGUE or prev == T.CHARACTER:
                prev = T.ACTION if prev == T.DIALOGUE else prev
            continue
        runs = _runs(par)
        name = par.style.name if par.style is not None else ""
        if styled and name.startswith(STYLE_PREFIX):
            etype = name[len(STYLE_PREFIX):]
        elif styled:
            continue                                    # title page lines
        else:
            left = 1.0 + _indent_in(par, "left_indent")
            etype = guess_type(text, left, prev, par.alignment == WD_ALIGN_PARAGRAPH.CENTER,
                               par.alignment == WD_ALIGN_PARAGRAPH.RIGHT)
        el = Element(etype, runs)
        if etype == T.SCENE_HEADING:
            m = re.match(r"^\s*(\d+[A-Z]?)\s{2,}(.*)$", el.text)
            if m:
                el.scene_number = m.group(1)
                el.runs = [Run(m.group(2))]
        if par.paragraph_format.page_break_before:
            el.page_break_before = True
        els.append(el)
        prev = etype
    title_page = []
    cp = doc.core_properties
    if cp.title:
        title_page.append(("Title", cp.title))
    return Script(title_page=title_page, elements=els)
