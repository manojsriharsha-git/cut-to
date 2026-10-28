"""
Moving a script between the model (Script / Element / Run) and the page.

Part of the editor: ScreenplayEditor inherits these methods, so `self` is the editor.
"""
from __future__ import annotations

import base64
import copy

from PySide6.QtCore import Qt, QUrl, QBuffer, QByteArray, QIODevice
from PySide6.QtGui import (QFont, QColor, QTextCursor, QImage, QTextCharFormat, QTextFormat,
                           QTextImageFormat, QTextDocument)

from ..core.ir import T, Run, Element, Script, merge_runs
from .pages import block_type, block_meta, page_size_px, first_line_y
from .theme import C

LINE_SEP = chr(0x2028)      # Shift+Enter soft line break inside one paragraph
OBJECT = chr(0xFFFC)        # the character Qt uses to hold an inline image
LINK_COLOR = "#2F6FA8"
NOTE_TYPES = (T.NOTE, T.SECTION, T.SYNOPSIS)


class DocumentIO:
    """load_script / to_script and the questions the navigator asks about the page."""

    def _image_format(self, name: str, w_in: float, h_in: float) -> QTextImageFormat:
        f = QTextImageFormat()
        f.setName(name)
        f.setWidth(w_in * self.dpi)
        f.setHeight(h_in * self.dpi)
        return f

    def load_script(self, script: Script, doc_key: str | None = None):
        self._busy = True
        self._loading = True
        self._pasted = True                        # opening a script isn't writing (word goal)
        self._dirty = []
        self.popup.hide()
        self.doc_key = doc_key
        self.title_page = list(script.title_page)
        self.project = copy.deepcopy(script.extra)
        doc = self.document()
        doc.clear()
        self._apply_page_setup()                       # clear() resets the page margins
        cur = QTextCursor(doc)
        elements = script.elements or [Element(T.SCENE_HEADING)]
        for i, el in enumerate(elements):
            if i:
                cur.insertBlock()
            meta = {}
            if el.scene_number:
                meta["scene_number"] = el.scene_number
            if el.dual:
                meta["dual"] = el.dual
            if el.page_break_before:
                meta["page_break_before"] = True
            if el.centered:
                meta["centered"] = True
            extra = {k: v for k, v in el.extra.items() if k != "image"}
            if extra:
                meta["extra"] = extra
            img = el.extra.get("image") if el.type == T.IMAGE else None
            if img:
                meta["image"] = {k: v for k, v in img.items() if k != "png"}
            cur.setBlockFormat(self._block_format(el.type, meta or None))
            tcf = self._type_char_format(el.type)
            cur.setBlockCharFormat(tcf)
            if img:
                qimg = QImage.fromData(base64.b64decode(img["png"]), "PNG")
                doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(img["name"]), qimg)
                cur.insertImage(self._image_format(img["name"], img["width_in"], img["height_in"]))
                continue
            for r in el.runs:
                cur.insertText(r.text.replace("\n", LINE_SEP), self._run_format(tcf, r))
        self._paginate(join=False)                     # Final Draft page rules
        doc.clearUndoRedoStacks()
        doc.setModified(False)
        self.setTextCursor(QTextCursor(doc.firstBlock()))
        self._busy = False
        self._loading = False
        self.memory.set_document(self.element_pairs(), doc_key)
        self._after_change()
        self.structureChanged.emit()
        self.projectChanged.emit("")

    @staticmethod
    def _run_format(base: QTextCharFormat, r: Run) -> QTextCharFormat:
        cf = QTextCharFormat(base)
        if r.bold:
            cf.setFontWeight(QFont.Weight.Bold)
        if r.italic:
            cf.setFontItalic(True)
        if r.underline:
            cf.setFontUnderline(True)
        if r.strike:
            cf.setFontStrikeOut(True)
        if r.color:
            cf.setForeground(QColor(r.color))
        if r.highlight:
            cf.setBackground(QColor(r.highlight))
        if r.font:
            cf.setFontFamilies([r.font])
        if r.link:
            cf.setAnchor(True)
            cf.setAnchorHref(r.link)
            cf.setFontUnderline(True)
            cf.setForeground(QColor(LINK_COLOR))
            cf.setToolTip(f"{r.link}  (Ctrl+click to open)")
        return cf

    def _format_to_run(self, text: str, cf: QTextCharFormat, etype: str) -> Run:
        link = cf.anchorHref() if cf.isAnchor() and cf.anchorHref() else None
        font = None
        if cf.hasProperty(QTextFormat.Property.FontFamilies):
            fams = cf.fontFamilies() or []
            if fams and fams[0] != self.script_font():
                font = fams[0]
        color = None
        if cf.hasProperty(QTextFormat.Property.ForegroundBrush) and \
                cf.foreground().style() != Qt.BrushStyle.NoBrush:
            color = cf.foreground().color().name().upper()
            if color in (C.INK, LINK_COLOR.upper()) or (etype in NOTE_TYPES and color == C.CARAMEL):
                color = None
        highlight = None
        if cf.hasProperty(QTextFormat.Property.BackgroundBrush) and \
                cf.background().style() != Qt.BrushStyle.NoBrush:
            highlight = cf.background().color().name().upper()
        return Run(text, cf.fontWeight() >= QFont.Weight.DemiBold.value, cf.fontItalic(),
                   cf.fontUnderline() and not link, cf.fontStrikeOut(), color, highlight, link, font)

    def _image_element(self, block) -> Element | None:
        for it in block:
            frag = it.fragment()
            if frag.isValid() and frag.charFormat().isImageFormat():
                f = frag.charFormat().toImageFormat()
                res = self.document().resource(QTextDocument.ResourceType.ImageResource,
                                               QUrl(f.name()))
                img = res if isinstance(res, QImage) else QImage(res) if res is not None else QImage()
                if img.isNull():
                    return None
                ba = QByteArray()
                buf = QBuffer(ba)
                buf.open(QIODevice.OpenModeFlag.WriteOnly)
                img.save(buf, "PNG")
                return Element.image(f.name(), bytes(ba.toBase64()).decode("ascii"),
                                     f.width() / self.dpi, f.height() / self.dpi)
        return None

    def to_script(self, keep_empty: bool = False) -> Script:
        els = []
        block = self.document().firstBlock()
        while block.isValid():
            etype = block_type(block)
            meta = block_meta(block)
            el = self._image_element(block) if etype == T.IMAGE else None
            if el is None:
                runs = []
                for it in block:
                    frag = it.fragment()
                    if not frag.isValid():
                        continue
                    text = frag.text().replace(LINE_SEP, "\n").replace(OBJECT, "")
                    if self.caps(etype):
                        text = text.upper()
                    runs.append(self._format_to_run(text, frag.charFormat(), etype))
                runs = merge_runs(runs)
                if keep_empty or "".join(r.text for r in runs).strip():
                    el = Element(T.ACTION if etype == T.IMAGE else etype, runs)
            if el is not None:
                el.scene_number = meta.get("scene_number")
                el.dual = meta.get("dual", 0)
                el.page_break_before = meta.get("page_break_before", False)
                el.centered = meta.get("centered", False)
                el.extra.update(meta.get("extra", {}))
                els.append(el)
            block = block.next()
        return Script(title_page=list(self.title_page), elements=els,
                      extra=copy.deepcopy(self.project))

    def element_pairs(self, until_block=None) -> list[tuple[str, str]]:
        """(type, text) of every paragraph, or only those before `until_block`."""
        out = []
        block = self.document().firstBlock()
        while block.isValid() and block != until_block:
            out.append((block_type(block),
                        block.text().replace(LINE_SEP, "\n").replace(OBJECT, "")))
            block = block.next()
        return out

    def scenes(self) -> list[tuple[int, str, str | None, int]]:
        """(block number, heading, scene number, page) for every scene heading."""
        out = []
        block = self.document().firstBlock()
        while block.isValid():
            if block_type(block) == T.SCENE_HEADING and block.text().strip():
                y = first_line_y(self.document(), block)
                out.append((block.blockNumber(), block.text().strip().upper(),
                            block_meta(block).get("scene_number"),
                            int(y // page_size_px(self.dpi)[1]) + 1))
            block = block.next()
        return out

    def scene_lengths(self) -> list[float]:
        """Length of each scene in pages (text area only), for eighths reporting."""
        _, h = page_size_px(self.dpi)
        body = h - 2 * self.dpi

        def body_y(y):
            page = int(y // h)
            return page * body + min(max(y - page * h - self.dpi, 0), body)

        starts = [first_line_y(self.document(), self.document().findBlockByNumber(n))
                  for n, *_ in self.scenes()]
        last = self.document().lastBlock()
        end = self.document().documentLayout().blockBoundingRect(last).bottom()
        bounds = starts + [end]
        return [max(0.0, (body_y(bounds[i + 1]) - body_y(bounds[i])) / body)
                for i in range(len(starts))]
