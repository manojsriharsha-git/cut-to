"""
Screenplay page rules, as pure Python so they can be tested without a window.

The editor measures each paragraph (its space-before, the height of each of its
lines, whether it must stay in one piece, whether the writer forced a page break)
and asks `plan()` which paragraphs need an automatic page break so that:

  * a scene heading (or shot) is never the last thing on a page,
  * a character name always has at least 2 lines of its speech under it,
  * a speech that splits across pages leaves at least 2 lines on each page,
    and never ends a page on a parenthetical (the page gets (MORE) / CONT'D),
  * an action paragraph that splits leaves at least 2 lines on each page.

The placement model copies how Qt lays out a paginated document (checked against
Qt on random scripts in the tests): the first paragraph ignores its space-before,
a forced break starts a new page and then adds the space-before, a paragraph that
must stay in one piece moves to the next page without its space-before, and a line
that would cross the bottom margin moves to the next page.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .ir import T

HEADINGS = (T.SCENE_HEADING, T.SHOT)
SPEECH_BODY = (T.PARENTHETICAL, T.DIALOGUE)
MIN_LINES = 2


@dataclass
class Geom:
    type: str
    margin: float                 # space before, in px
    lines: list[float]            # height of each line, in px
    keep_together: bool = False   # must not split across pages
    forced: bool = False          # the writer forced a page break before it


@dataclass
class Page:
    height: float                 # whole sheet, px
    top: float                    # top margin, px
    bottom: float                 # bottom margin, px

    def bottom_of(self, y: float) -> float:
        return int(y // self.height) * self.height + self.height - self.bottom

    def next_top(self, y: float) -> float:
        return (int(y // self.height) + 1) * self.height + self.top

    def page(self, y: float) -> int:
        return int(y // self.height)


@dataclass
class Plan:
    breaks: set[int] = field(default_factory=set)        # paragraphs needing an automatic break
    lines: list[list[float]] = field(default_factory=list)  # y of every line, per paragraph
    pages: int = 1


def place(geoms: list[Geom], page: Page, breaks: set[int], start: int = 0,
          lines: list | None = None, before: list | None = None,
          stop: int | None = None) -> tuple[list, list]:
    """Lay paragraphs out like Qt does, from paragraph `start` on.

    Returns (y of every line per paragraph, y before each paragraph); pass the lists
    back in to re-lay only the part after a change.
    """
    lines = lines if lines is not None else [[] for _ in geoms]
    before = before if before is not None else [0.0] * len(geoms)
    y = before[start] if start else page.top
    for i in range(start, len(geoms) if stop is None else min(stop, len(geoms))):
        g = geoms[i]
        before[i] = y
        if (g.forced or i in breaks) and i > 0:
            y = page.next_top(y) + g.margin
        elif i > 0:
            y += g.margin
        if g.keep_together and g.lines and y + sum(g.lines) > page.bottom_of(y):
            y = page.next_top(y)
        ys = []
        for h in g.lines:
            if y + h > page.bottom_of(y) + 0.01:
                y = page.next_top(y)
            ys.append(y)
            y += h
        lines[i] = ys
    if stop is not None and stop < len(geoms):
        before[stop] = y                       # where the next paragraph will start
    return lines, before


def _speech_end(geoms: list[Geom], i: int) -> int:
    """Index after the last parenthetical/dialogue that follows character i."""
    j = i + 1
    while j < len(geoms) and geoms[j].type in SPEECH_BODY:
        j += 1
    return j


def _first_on_page(lines: list[list[float]], i: int, page: Page) -> bool:
    """True when paragraph i starts its page (nothing earlier sits on the same page)."""
    k = i - 1
    while k >= 0 and not lines[k]:
        k -= 1
    return k < 0 or page.page(lines[k][-1]) < page.page(lines[i][0])


def _keep_with_previous(geoms: list[Geom], lines: list[list[float]], i: int, page: Page) -> int:
    """Move a break up to the scene heading that sits right above paragraph i."""
    while i > 0 and geoms[i - 1].type in HEADINGS and lines[i - 1] and \
            page.page(lines[i - 1][-1]) == page.page(lines[i][0]) and \
            not _first_on_page(lines, i - 1, page):
        i -= 1
    return i


def _violation(geoms: list[Geom], lines: list[list[float]], page: Page, start: int = 0,
               stop: int | None = None) -> int | None:
    """First paragraph (from `start`) that needs an automatic page break, or None."""
    n = len(geoms)
    for i in range(start, n if stop is None else min(stop, n)):
        g = geoms[i]
        if not lines[i]:
            continue
        first_page = page.page(lines[i][0])
        last_page = page.page(lines[i][-1])

        if g.type in HEADINGS:
            j = i + 1
            while j < n and not lines[j]:
                j += 1
            if j < n:
                need = lines[j][:MIN_LINES]
                if any(page.page(y) != last_page for y in need) and not _first_on_page(lines, i, page):
                    return _keep_with_previous(geoms, lines, i, page)

        elif g.type == T.CHARACTER:
            end = _speech_end(geoms, i)
            body = [y for k in range(i + 1, end) for y in lines[k]]
            if not body:
                continue
            head = body[:MIN_LINES]
            starts_here = not _first_on_page(lines, i, page)
            if any(page.page(y) != last_page for y in head) and starts_here:
                return _keep_with_previous(geoms, lines, i, page)   # name cut off from its speech
            pages = [page.page(y) for y in body]
            if len(set(pages)) > 1:
                a = pages.count(pages[0])
                b = len(pages) - a
                if (a < MIN_LINES or b < MIN_LINES) and starts_here:
                    return _keep_with_previous(geoms, lines, i, page)   # too little speech on a page
                # never end a page on a parenthetical: move it to the next page
                k_last = None
                for k in range(i + 1, end):
                    if lines[k] and page.page(lines[k][-1]) == pages[0]:
                        k_last = k
                if k_last is not None and geoms[k_last].type == T.PARENTHETICAL \
                        and k_last > i + 1 and not _first_on_page(lines, k_last, page):
                    return k_last

        elif g.type in (T.ACTION, T.GENERAL) and first_page != last_page and not g.keep_together:
            a = sum(1 for y in lines[i] if page.page(y) == first_page)
            b = len(lines[i]) - a
            if (a < MIN_LINES or b < MIN_LINES) and not _first_on_page(lines, i, page):
                return _keep_with_previous(geoms, lines, i, page)
    return None


def plan(geoms: list[Geom], page: Page, max_rounds: int = 20000) -> Plan:
    """Work out every automatic page break, first page to last.

    One pass down the script: lay out a little ahead of the paragraph being checked,
    and when a paragraph needs a break, re-lay from there and look again a few
    paragraphs back. Each paragraph is laid out only a handful of times, so a
    300-page script takes a moment, not seconds."""
    n = len(geoms)
    breaks: set[int] = set()
    if not n:
        return Plan(breaks, [], 1)
    lines: list[list[float]] = [[] for _ in geoms]
    before = [0.0] * n
    placed = 0                                   # paragraphs [0, placed) are laid out

    def ensure(k: int):
        nonlocal placed
        k = min(n, k)
        if k > placed:
            place(geoms, page, breaks, placed, lines, before, stop=k)
            placed = k

    i = rounds = 0
    while i < n:
        end = _speech_end(geoms, i) if geoms[i].type == T.CHARACTER else i + 1
        j = end                                   # the next paragraph with lines (headings look at it)
        while j < n and not geoms[j].lines:
            j += 1
        ensure(max(end, j) + 2)
        bad = _violation(geoms, lines, page, i, i + 1)
        if bad is None or bad in breaks or rounds >= max_rounds:
            i += 1
            continue
        breaks.add(bad)
        rounds += 1
        placed = min(placed, bad)                 # everything from the break moves
        i = max(0, bad - 12)                       # rules look a few paragraphs ahead
    ensure(n)
    last = max((ys[-1] for ys in lines if ys), default=page.top)
    return Plan(breaks, lines, page.page(last) + 1)


@dataclass
class Split:
    """A speech continuing onto the next page: draw (MORE) and NAME (CONT'D)."""
    name: str
    more_y: float        # y just below the last line of the speech on the first page
    contd_y: float       # y of the first line of the speech on the next page


def speech_splits(types: list[str], texts: list[str], lines: list[list[float]],
                  page: Page) -> list[Split]:
    out = []
    name = None
    prev_y = None
    for t, text, ys in zip(types, texts, lines):
        if t == T.CHARACTER:
            name = text.split("(")[0].strip().upper()
            prev_y = None
            continue
        if t not in SPEECH_BODY:
            name = None
            continue
        for y in ys:
            if name and prev_y is not None and page.page(y) != page.page(prev_y):
                out.append(Split(name, prev_y, y))
            prev_y = y
    return out
