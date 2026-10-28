"""Fountain inline emphasis  <->  styled runs.

    ***bold italic***   **bold**   *italic*   _underline_   \\* escapes a marker
"""
import re

from .ir import Run, merge_runs

_TOKEN = re.compile(r"\\([*_\\])|(\*\*\*|\*\*|\*|_)")


def parse_emphasis(s: str) -> list[Run]:
    runs: list[Run] = []
    buf: list[str] = []
    b = i = u = False
    pos = 0

    def flush():
        text = "".join(buf)
        buf.clear()
        if text:
            runs.append(Run(text, b, i, u))

    for m in _TOKEN.finditer(s):
        buf.append(s[pos:m.start()])
        pos = m.end()
        if m.group(1):                       # escaped char -> literal
            buf.append(m.group(1))
            continue
        flush()
        tok = m.group(2)
        if tok == "***":
            b, i = not b, not i
        elif tok == "**":
            b = not b
        elif tok == "*":
            i = not i
        else:
            u = not u
    buf.append(s[pos:])
    flush()

    if b or i or u:                          # unbalanced markers -> keep literally
        return [Run(s)] if s else []
    return merge_runs(runs)


def _escape(t: str) -> str:
    return t.replace("\\", "\\\\").replace("*", "\\*").replace("_", "\\_")


def runs_to_fountain(runs: list[Run]) -> str:
    out = []
    for r in runs:
        pre = ("_" if r.underline else "") + ("**" if r.bold else "") + ("*" if r.italic else "")
        out.append(pre + _escape(r.text) + pre[::-1])
    return "".join(out)
