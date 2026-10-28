"""Export-only formats: Rich Text (.rtf) and formatted plain text (.txt).

Both use the same indents as the page (core/layout.py). RTF measures in twips
(1440 per inch, from the 1-inch page margin); plain text uses 10 characters per
inch of Courier, so it lines up in any fixed-width font.
"""
from __future__ import annotations

import textwrap

from ..core.ir import T, Script
from ..core.layout import ELEMENT_SPECS, CHARS_PER_INCH

TWIP = 1440


def _rtf_escape(s: str) -> str:
    out = []
    for ch in s:
        o = ord(ch)
        if ch in "\\{}":
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\line ")
        elif o > 127:
            out.append(f"\\u{o if o < 32768 else o - 65536}?")
        else:
            out.append(ch)
    return "".join(out)


def rtf(script: Script) -> str:
    out = [r"{\rtf1\ansi\deff0{\fonttbl{\f0\fmodern Courier Prime;}}",
           r"{\colortbl;\red0\green0\blue0;\red200\green142\blue92;}",
           r"\paperw12240\paperh15840\margl1440\margr1440\margt1440\margb1440\f0\fs24"]
    tp = {k.lower(): v for k, v in script.title_page}
    if tp:
        out.append(r"\pard\qc" + r"\par" * 18)
        for key in ("title", "credit", "author", "source"):
            for line in tp.get(key, "").split("\n"):
                if line.strip():
                    out.append(r"\pard\qc " + _rtf_escape(line.strip()) + r"\par")
            if tp.get(key):
                out.append(r"\pard\par")
        out.append(r"\page")
    first = True
    for el in script.elements:
        left, right, before, align, caps, _ = ELEMENT_SPECS.get(el.type, ELEMENT_SPECS[T.ACTION])
        li = int((left - 1.0) * TWIP)
        ri = int((8.5 - 1.0 - right) * TWIP)
        sb = 0 if first else before * 20
        first = False
        para = [r"\pard"]
        if el.page_break_before:
            para.append(r"\pagebb")
        para.append(r"\qr" if align == "Right" else r"\qc" if el.centered else r"\ql")
        para.append(rf"\li{li}\ri{ri}\sb{sb}")
        if el.type in (T.SCENE_HEADING, T.CHARACTER):
            para.append(r"\keepn")
        if caps:
            para.append(r"\caps")
        if el.type in (T.NOTE, T.SYNOPSIS):
            para.append(r"\cf2\i")
        text = []
        if el.type == T.SCENE_HEADING and el.scene_number:
            text.append(_rtf_escape(el.scene_number + "  "))
        for r in el.runs:
            on = "".join(c for c, f in ((r"\b", r.bold), (r"\i", r.italic), (r"\ul", r.underline),
                                        (r"\strike", r.strike)) if f)
            body = _rtf_escape(r.text)
            text.append("{" + on + " " + body + "}" if on else body)
        out.append("".join(para) + " " + "".join(text) + r"\par")
    out.append("}")
    return "\n".join(out)


def plain_text(script: Script) -> str:
    """The script as fixed-width text: indents, CAPS and blank lines like the printed page."""
    lines: list[str] = []
    tp = {k.lower(): v for k, v in script.title_page}
    if tp:
        for key in ("title", "credit", "author"):
            for ln in tp.get(key, "").split("\n"):
                if ln.strip():
                    lines.append(ln.strip().center(65))
            lines.append("")
        lines += ["", ""]
    for el in script.elements:
        left, right, before, align, caps, _ = ELEMENT_SPECS.get(el.type, ELEMENT_SPECS[T.ACTION])
        if lines and before:
            lines += [""] * (before // 12)
        pad = int(round((left - 1.5) * CHARS_PER_INCH))
        width = int(round((right - left) * CHARS_PER_INCH))
        text = el.text.upper() if caps else el.text
        if el.type == T.SCENE_HEADING and el.scene_number:
            text = f"{el.scene_number}  {text}"
        for para in text.split("\n"):
            wrapped = textwrap.wrap(para, width) or [""]
            for w in wrapped:
                if align == "Right":
                    lines.append(w.rjust(int(round((right - 1.5) * CHARS_PER_INCH))))
                elif el.centered:
                    lines.append(w.center(60))
                else:
                    lines.append(" " * pad + w)
    return "\n".join(lines).rstrip() + "\n"
