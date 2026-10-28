"""Fountain (.fountain) reader & writer  —  https://fountain.io/syntax

Lossy mappings (documented): Fountain has no Shot/General element, so those are
written as forced Action. Everything else round-trips.
"""
from __future__ import annotations

import re

from ..core.ir import T, Element, Script
from ..core.emphasis import parse_emphasis, runs_to_fountain

SCENE_RE = re.compile(r"^(INT|EXT|EST|INT\.?/EXT|I/E)[\. ]", re.I)
SCENE_NUM_RE = re.compile(r"\s*#([\w\-.]+)#\s*$")
TITLE_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z ]*):\s*(.*)$")
PAGE_BREAK_RE = re.compile(r"^={3,}$")
BONEYARD_RE = re.compile(r"/\*.*?\*/", re.S)


def is_character_line(s: str) -> bool:
    name = s.rstrip().rstrip("^").strip()
    name = name.split("(")[0].strip()
    return bool(name) and any(c.isalpha() for c in name) and name == name.upper()


def _el(type_: str, text: str, **kw) -> Element:
    return Element(type_, parse_emphasis(text), **kw)


# ------------------------------------------------------------------ reading
def _parse_title_page(lines: list[str]) -> tuple[list[tuple[str, str]], int]:
    if not lines or not TITLE_KEY_RE.match(lines[0]):
        return [], 0
    tp: list[tuple[str, str]] = []
    i = 0
    while i < len(lines) and lines[i].strip():
        m = TITLE_KEY_RE.match(lines[i])
        if m and not lines[i][0].isspace():
            key, val = m.group(1).strip(), m.group(2).strip()
            parts = [val] if val else []
            i += 1
            while i < len(lines) and lines[i].strip() and lines[i][0] in " \t":
                parts.append(lines[i].strip())
                i += 1
            tp.append((key, "\n".join(parts)))
        else:
            i += 1
    return tp, i


def parse(text: str) -> Script:
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip(chr(0xFEFF))
    text = BONEYARD_RE.sub("", text)
    lines = text.split("\n")
    title_page, i = _parse_title_page(lines)
    els: list[Element] = []
    pending_break = False
    n = len(lines)

    def add(el: Element):
        nonlocal pending_break
        if pending_break:
            el.page_break_before = True
            pending_break = False
        els.append(el)

    def block_from(start: int) -> tuple[list[str], int]:
        out, j = [], start
        while j < n and lines[j].strip():
            out.append(lines[j].rstrip())
            j += 1
        return out, j

    while i < n:
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue
        prev_blank = i == 0 or not lines[i - 1].strip()
        next_blank = i + 1 >= n or not lines[i + 1].strip()

        if PAGE_BREAK_RE.match(s):
            pending_break = True
            i += 1
            continue

        if s.startswith("[[") and prev_blank:                       # standalone note
            buf, j = [s], i
            while "]]" not in buf[-1] and j + 1 < n:
                j += 1
                buf.append(lines[j].strip())
            note = "\n".join(buf)
            if note.endswith("]]"):
                add(Element.plain(T.NOTE, note[2:-2].strip()))
                i = j + 1
                continue

        if s.startswith("#"):
            level = len(s) - len(s.lstrip("#"))
            add(Element.plain(T.SECTION, s[level:].strip(), extra={"level": level}))
            i += 1
            continue

        if s.startswith("=") and not s.startswith("=="):
            add(Element.plain(T.SYNOPSIS, s[1:].strip()))
            i += 1
            continue

        if s.startswith("~"):
            add(_el(T.LYRICS, s[1:].strip()))
            i += 1
            continue

        if s.startswith(">") and s.endswith("<"):
            add(_el(T.ACTION, s[1:-1].strip(), centered=True))
            i += 1
            continue

        if s.startswith(">"):
            add(_el(T.TRANSITION, s[1:].strip()))
            i += 1
            continue

        if prev_blank and ((s.startswith(".") and not s.startswith("..")) or SCENE_RE.match(s)):
            heading = s[1:].strip() if s.startswith(".") else s
            num = None
            m = SCENE_NUM_RE.search(heading)
            if m:
                num = m.group(1)
                heading = heading[:m.start()].rstrip()
            add(_el(T.SCENE_HEADING, heading, scene_number=num))
            i += 1
            continue

        if prev_blank and next_blank and s.isupper() and s.endswith("TO:"):
            add(_el(T.TRANSITION, s))
            i += 1
            continue

        if not s.startswith("!") and (s.startswith("@") or
                                      (prev_blank and not next_blank and is_character_line(s))):
            name = s[1:].strip() if s.startswith("@") else s
            dual = 0
            if name.endswith("^"):
                name = name[:-1].rstrip()
                dual = 2
                j = len(els) - 1
                while j >= 0 and els[j].type in (T.DIALOGUE, T.PARENTHETICAL):
                    j -= 1
                if j >= 0 and els[j].type == T.CHARACTER:
                    for k in range(j, len(els)):
                        els[k].dual = 1
                else:
                    dual = 0
            add(_el(T.CHARACTER, name, dual=dual))
            i += 1
            dialogue_buf: list[str] = []

            def flush_dialogue():
                if dialogue_buf:
                    add(_el(T.DIALOGUE, "\n".join(dialogue_buf), dual=dual))
                    dialogue_buf.clear()

            while i < n and (lines[i].strip() or lines[i] == "  "):
                ln = lines[i].strip()
                if ln.startswith("(") and ln.endswith(")"):
                    flush_dialogue()
                    add(_el(T.PARENTHETICAL, ln, dual=dual))
                else:
                    dialogue_buf.append(ln)
                i += 1
            flush_dialogue()
            continue

        # default: action block (first line may be forced with "!")
        block, i = block_from(i)
        if block[0].lstrip().startswith("!"):
            block[0] = block[0].lstrip()[1:]
        add(_el(T.ACTION, "\n".join(block)))

    return Script(title_page=title_page, elements=els)


# ------------------------------------------------------------------ writing
def _render(el: Element) -> str:
    t = runs_to_fountain(el.runs)
    plain = el.text
    first = plain.split("\n")[0].strip()

    if el.type == T.SCENE_HEADING:
        out = t if SCENE_RE.match(plain) else "." + t
        return out + (f" #{el.scene_number}#" if el.scene_number else "")
    if el.type == T.CHARACTER:
        needs_force = not is_character_line(plain) or plain[:1] in "!@#.>=~["
        return ("@" if needs_force else "") + t + (" ^" if el.dual == 2 else "")
    if el.type == T.PARENTHETICAL:
        return t if plain.startswith("(") and plain.endswith(")") else f"({t})"
    if el.type == T.DIALOGUE:
        return t
    if el.type == T.TRANSITION:
        return t if plain.isupper() and plain.endswith("TO:") else "> " + t
    if el.type == T.NOTE:
        return f"[[{plain}]]"
    if el.type == T.IMAGE:                      # Fountain keeps a placeholder note
        return plain if plain.startswith("[[") else f"[[{plain}]]"
    if el.type == T.SECTION:
        return "#" * int(el.extra.get("level", 1)) + " " + plain
    if el.type == T.SYNOPSIS:
        return "= " + plain
    if el.type == T.LYRICS:
        return "~" + t
    # Action / Shot / General / unknown
    if el.centered:
        return f"> {t} <"
    looks_special = (SCENE_RE.match(first) or is_character_line(first)
                     or first[:1] in "!@#.>=~[" or PAGE_BREAK_RE.match(first))
    return ("!" if looks_special else "") + t


def write(script: Script) -> str:
    out: list[str] = []
    for key, val in script.title_page:
        parts = val.split("\n")
        if len(parts) == 1:
            out.append(f"{key}: {val}")
        else:
            out.append(f"{key}:")
            out.extend("    " + p for p in parts)
    if script.title_page:
        out.append("")

    prev = None
    for el in script.elements:
        if el.page_break_before:
            if out and out[-1] != "":
                out.append("")
            out += ["===", ""]
        in_block = (el.type in (T.PARENTHETICAL, T.DIALOGUE)
                    and prev in T.DIALOGUE_BLOCK and not el.page_break_before)
        if not in_block and out and out[-1] != "":
            out.append("")
        out.append(_render(el))
        prev = el.type
    return "\n".join(out).rstrip() + "\n"
