"""
Pages: one set of rules for the screen, the PDF and the printer.

The editor lets Qt split the script into US Letter pages (8.5 x 11 in, 1 in top and
bottom margins). This module draws what sits on top of every page (page numbers,
scene numbers) and renders the same pages to a PDF file or a printer, so what you
see on screen is exactly what you get on paper.
"""
from __future__ import annotations

import json

from PySide6.QtCore import QRectF, QPointF, QMarginsF
from PySide6.QtGui import (QFont, QFontMetricsF, QPainter, QColor, QPageLayout, QPageSize,
                           QPdfWriter, QTextFormat, QTextDocument, QAbstractTextDocumentLayout,
                           QPalette)

from ..core.ir import T
from ..core.layout import PAGE_WIDTH_IN, PAGE_HEIGHT_IN
from ..core.pagination import Geom, Page, Split, speech_splits

PROP_TYPE = QTextFormat.Property.UserProperty + 1      # element type of a paragraph
PROP_META = QTextFormat.Property.UserProperty + 2      # scene number, page break, image...
PROP_AUTO = QTextFormat.Property.UserProperty + 3      # automatic page break (page rules)
SCREEN_GAP = 22                                         # px of background between sheets
FIXED_HEIGHT = 2                                        # QTextBlockFormat.FixedHeight


def block_type(block) -> str:
    return block.blockFormat().property(PROP_TYPE) or T.ACTION


def block_meta(block) -> dict:
    raw = block.blockFormat().property(PROP_META)
    return json.loads(raw) if raw else {}


def is_auto_break(block) -> bool:
    return bool(block.blockFormat().property(PROP_AUTO))


def page_model(dpi: float) -> Page:
    return Page(PAGE_HEIGHT_IN * dpi, dpi, dpi)


def measure(doc: QTextDocument) -> tuple[list, list[Geom]]:
    """Every paragraph and its geometry (space before, line heights, keep-together, forced break)."""
    doc.documentLayout().blockBoundingRect(doc.lastBlock())      # make sure all is laid out
    blocks, geoms = [], []
    block = doc.firstBlock()
    while block.isValid():
        f = block.blockFormat()
        lay = block.layout()
        n = lay.lineCount() if lay is not None else 0
        if f.lineHeightType() == FIXED_HEIGHT:
            heights = [f.lineHeight()] * n
        else:
            heights = [lay.lineAt(i).height() for i in range(n)]
        geoms.append(Geom(block_type(block), f.topMargin(), heights, f.nonBreakableLines(),
                          bool(block_meta(block).get("page_break_before"))))
        blocks.append(block)
        block = block.next()
    return blocks, geoms


_SHIFT_CACHE: dict = {}


def line_shift(doc: QTextDocument) -> float:
    """How far Qt draws lines from their slots. With fixed line heights Qt nudges every
    line box by a few pixels that depend on the font (and differ between Windows and
    Linux). Pagination counts slots, so we take that nudge back out. It is the same for
    every ordinary paragraph, so the most common first-line offset is the nudge."""
    key = (id(doc), doc.revision(), doc.pageSize().width())
    if key in _SHIFT_CACHE:
        return _SHIFT_CACHE[key]
    from collections import Counter
    counts = Counter()
    block = doc.firstBlock()
    n = 0
    while block.isValid() and n < 400:
        lay = block.layout()
        if lay is not None and lay.lineCount() and block.blockFormat().lineHeightType() == FIXED_HEIGHT:
            counts[round(lay.lineAt(0).y(), 3)] += 1
            n += 1
        block = block.next()
    shift = counts.most_common(1)[0][0] if counts else 0.0
    if len(_SHIFT_CACHE) > 64:
        _SHIFT_CACHE.clear()
    _SHIFT_CACHE[key] = shift
    return shift


def actual_lines(doc: QTextDocument, blocks) -> list[list[float]]:
    """The slot (top y) of every line, per paragraph, as laid out by Qt."""
    lay = doc.documentLayout()
    shift = line_shift(doc)
    out = []
    for b in blocks:
        top = lay.blockBoundingRect(b).top()
        tl = b.layout()
        if tl is None:
            out.append([])
            continue
        s = shift if b.blockFormat().lineHeightType() == FIXED_HEIGHT else 0.0
        out.append([top + tl.lineAt(i).y() - s for i in range(tl.lineCount())])
    return out


def find_splits(doc: QTextDocument, dpi: float) -> list[Split]:
    """Speeches that continue onto the next page, from the real layout."""
    blocks = []
    b = doc.firstBlock()
    while b.isValid():
        blocks.append(b)
        b = b.next()
    return speech_splits([block_type(b) for b in blocks], [b.text() for b in blocks],
                         actual_lines(doc, blocks), page_model(dpi))


def page_size_px(dpi: float) -> tuple[float, float]:
    return PAGE_WIDTH_IN * dpi, PAGE_HEIGHT_IN * dpi


def first_line_y(doc: QTextDocument, block) -> float:
    """Top of a paragraph's first line slot in document coordinates (after its space-before)."""
    rect = doc.documentLayout().blockBoundingRect(block)
    lay = block.layout()
    if lay is None or not lay.lineCount():
        return rect.top()
    s = line_shift(doc) if block.blockFormat().lineHeightType() == FIXED_HEIGHT else 0.0
    return rect.top() + lay.lineAt(0).y() - s


def page_of(doc: QTextDocument, block, dpi: float) -> int:
    """0-based page a paragraph starts on."""
    return int(first_line_y(doc, block) // page_size_px(dpi)[1])


def scene_marks(doc: QTextDocument) -> list[tuple[object, str]]:
    """(block, scene number) for every numbered scene heading."""
    out = []
    block = doc.firstBlock()
    while block.isValid():
        if block_type(block) == T.SCENE_HEADING:
            num = block_meta(block).get("scene_number")
            if num:
                out.append((block, str(num)))
        block = block.next()
    return out


def revision_marks(doc: QTextDocument) -> list[tuple[object, int]]:
    """(block, revision level) for every paragraph changed in a revision."""
    out = []
    block = doc.firstBlock()
    while block.isValid():
        level = block_meta(block).get("extra", {}).get("revision")
        if level:
            out.append((block, int(level)))
        block = block.next()
    return out


def page_font(dpi: float, family: str = "Courier Prime") -> QFont:
    f = QFont(family)
    f.setStyleHint(QFont.StyleHint.TypeWriter)
    f.setPixelSize(round(dpi / 6))
    return f


def draw_page_furniture(p: QPainter, doc: QTextDocument, dpi: float, page: int,
                        page_top: float, color: str, marks=None, splits=None, ink: str | None = None,
                        extras: dict | None = None, revisions=None, star_colors=None):
    """Page number (from page 2, top right), scene numbers in both margins,
    (MORE) / NAME (CONT'D) where a speech carries on, revision asterisks and header."""
    extras = extras or {}
    font = page_font(dpi, doc.defaultFont().family())
    fm = QFontMetricsF(font)
    line = dpi / 6
    p.setFont(font)
    p.setPen(QColor(color))
    header = extras.get("header", "")
    if page >= 1 or header:
        label = f"{page + 1}." if page >= 1 else ""
        if header:
            label = f"{header}   {label}".rstrip()
        x = 7.5 * dpi - fm.horizontalAdvance(label)
        p.drawText(QPointF(x, page_top + 0.5 * dpi + fm.ascent()), label)
    h = page_size_px(dpi)[1]
    if extras.get("watermark"):
        p.save()
        wf = QFont(font)
        wf.setPixelSize(round(dpi * 0.9))
        wf.setBold(True)
        p.setFont(wf)
        c = QColor(color)
        c.setAlpha(28)
        p.setPen(c)
        p.translate(4.25 * dpi, page_top + 5.5 * dpi)
        p.rotate(-35)
        text = extras["watermark"]
        p.drawText(QPointF(-QFontMetricsF(wf).horizontalAdvance(text) / 2, 0), text)
        p.restore()
        p.setFont(font)

    shift = line_shift(doc)                            # where Qt really draws the text

    def baseline(y):
        return page_top + (y - page * h) + shift + fm.ascent()

    for block, num in (marks if marks is not None else scene_marks(doc)):
        y = first_line_y(doc, block)
        if int(y // h) != page:
            continue
        p.drawText(QPointF(1.25 * dpi - fm.horizontalAdvance(num), baseline(y)), num)
        p.drawText(QPointF(7.6 * dpi, baseline(y)), num)
    if extras.get("asterisks", True):
        for block, level in (revisions if revisions is not None else revision_marks(doc)):
            lay = block.layout()
            if lay is None:
                continue
            top = doc.documentLayout().blockBoundingRect(block).top()
            p.setPen(QColor((star_colors or {}).get(level, color)))
            for i in range(lay.lineCount()):
                y = top + lay.lineAt(i).y()
                if int(y // h) == page:
                    p.drawText(QPointF(7.85 * dpi, baseline(y)), "*")
    p.setPen(QColor(ink or color))
    for s in (splits if splits is not None else find_splits(doc, dpi)):
        if int(s.more_y // h) == page:
            p.drawText(QPointF(3.5 * dpi, baseline(s.more_y + line)), "(MORE)")
        if int(s.contd_y // h) == page:
            p.drawText(QPointF(3.5 * dpi, baseline(s.contd_y - line)), f"{s.name} (CONT'D)")


def draw_title_page(p: QPainter, dpi: float, title_page: list[tuple[str, str]], color: str,
                    family: str = "Courier Prime"):
    d = {k.lower(): v for k, v in title_page}
    font = page_font(dpi, family)
    fm = QFontMetricsF(font)
    p.setFont(font)
    p.setPen(QColor(color))
    line = dpi / 6
    w = PAGE_WIDTH_IN * dpi

    def centred(text: str, y: float):
        p.drawText(QPointF((w - fm.horizontalAdvance(text)) / 2, y), text)

    y = 3.5 * dpi
    for key in ("title", "credit", "author", "source"):
        for ln in d.get(key, "").split("\n"):
            if ln.strip():
                centred(ln.strip(), y)
                y += line
        if d.get(key):
            y += line
    contact = [ln for ln in d.get("contact", "").split("\n") if ln.strip()]
    y = 10 * dpi - line * len(contact)
    for ln in contact:
        p.drawText(QPointF(1.5 * dpi, y), ln.strip())
        y += line
    if d.get("draft date"):
        text = d["draft date"].split("\n")[0]
        p.drawText(QPointF(7.5 * dpi - fm.horizontalAdvance(text), 10 * dpi - line), text)


def render(doc: QTextDocument, device, dpi: float, title_page, color: str = "#000000",
           extras: dict | None = None):
    """Draw every page of `doc` (laid out at `dpi`) onto a PDF writer or printer."""
    w, h = page_size_px(dpi)
    p = QPainter(device)
    scale = device.logicalDpiX() / dpi
    p.scale(scale, scale)
    first = True
    if any(v.strip() for _, v in title_page):
        draw_title_page(p, dpi, title_page, color, doc.defaultFont().family())
        first = False
    marks = scene_marks(doc)
    splits = find_splits(doc, dpi)
    revisions = revision_marks(doc)
    ctx = QAbstractTextDocumentLayout.PaintContext()
    pal = ctx.palette
    pal.setColor(QPalette.ColorRole.Text, QColor(color))          # always black ink on paper
    ctx.palette = pal
    pages = (extras or {}).get("pages")                              # optional page selection
    for page in range(doc.pageCount()):
        if pages is not None and page + 1 not in pages:
            continue
        if not first:
            device.newPage()
        first = False
        p.save()
        p.translate(0, -page * h)
        ctx.clip = QRectF(0, page * h, w, h)
        p.setClipRect(ctx.clip)
        doc.documentLayout().draw(p, ctx)
        p.restore()
        draw_page_furniture(p, doc, dpi, page, 0, color, marks, splits, extras=extras,
                            revisions=revisions)
    p.end()


def letter_layout() -> QPageLayout:
    return QPageLayout(QPageSize(QPageSize.PageSizeId.Letter), QPageLayout.Orientation.Portrait,
                       QMarginsF(0, 0, 0, 0))


def export_pdf(doc: QTextDocument, path: str, dpi: float, title_page, title: str = "",
               extras: dict | None = None):
    writer = QPdfWriter(path)
    writer.setPageLayout(letter_layout())
    writer.setResolution(600)
    writer.setTitle(title)
    writer.setCreator("Cut To:")
    render(doc, writer, dpi, title_page, extras=extras)
