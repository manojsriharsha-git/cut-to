"""
Writing-comfort features of the page: highlight layers, copy/paste that keeps element
types, smart paste, find, rename a character, focus and typewriter modes, revision marks.

Part of the editor: ScreenplayEditor inherits these methods, so `self` is the editor.
"""
from __future__ import annotations

import base64
import re
from contextlib import contextmanager

from PySide6.QtCore import QMimeData, QRectF, QUrl
from PySide6.QtGui import (QColor, QTextCursor, QTextCharFormat, QTextFormat, QImage, QPainter,
                           QTextDocument)
from PySide6.QtWidgets import QTextEdit, QMenu

from ..core.ir import T, Element, merge_runs, Script
from ..core.smart import base_name
from ..formats import fountain
from .pages import block_type, block_meta
from .theme import C

MIME = "application/x-screenplay+json"
LINE_SEP = chr(0x2028)
OBJECT = chr(0xFFFC)
REVISION_COLORS = [("White", "#FFFFFF"), ("Blue", "#7EA6E0"), ("Pink", "#F2A7C3"),
                   ("Yellow", "#F2DA6B"), ("Green", "#8FCB8F"), ("Goldenrod", "#DDB24A"),
                   ("Buff", "#E8D3A9"), ("Salmon", "#F0A58C"), ("Cherry", "#D9576B"),
                   ("Tan", "#C9A57E")]
# the industry's standard order of revision colours


def _words(text: str) -> int:
    return len(re.findall(r"[\w'’-]+", text))


class EditorExtras:
    # ================================================================ highlight layers
    def set_layer(self, name: str, selections: list):
        """Several features colour text (find results, character lens, breakdown tags).
        Each owns a named layer; the editor shows all layers together."""
        self._layers[name] = selections
        merged = []
        for key in ("lens", "breakdown", "find", "current"):
            merged += self._layers.get(key, [])
        self.setExtraSelections(merged)

    @staticmethod
    def make_selection(cur: QTextCursor, background: str | None = None, underline: str | None = None,
                       full_width: bool = False, color: str | None = None) -> QTextEdit.ExtraSelection:
        sel = QTextEdit.ExtraSelection()
        sel.cursor = cur
        fmt = QTextCharFormat()
        if background:
            fmt.setBackground(QColor(background))
        if color:
            fmt.setForeground(QColor(color))
        if underline:
            fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SingleUnderline)
            fmt.setUnderlineColor(QColor(underline))
        if full_width:
            fmt.setProperty(QTextFormat.Property.FullWidthSelection, True)
        sel.format = fmt
        return sel

    # ================================================================ elements <-> selection
    def elements_between(self, start: int, end: int) -> list[Element]:
        """The paragraphs (or parts of them) between two positions, as IR elements."""
        doc = self.document()
        out = []
        block = doc.findBlock(start)
        while block.isValid() and block.position() <= end:
            etype = block_type(block)
            meta = block_meta(block)
            b0, b1 = block.position(), block.position() + block.length() - 1
            s, e = max(start, b0), min(end, b1)
            if etype == T.IMAGE and s <= b0 and e >= b1:
                el = self._image_element(block)
                if el:
                    out.append(el)
                    block = block.next()
                    continue
            runs = []
            for it in block:
                frag = it.fragment()
                if not frag.isValid():
                    continue
                fs, fe = max(frag.position(), s), min(frag.position() + frag.length(), e)
                if fs >= fe:
                    continue
                text = frag.text()[fs - frag.position(): fe - frag.position()]
                text = text.replace(LINE_SEP, "\n").replace(OBJECT, "")
                if self.caps(etype):
                    text = text.upper()
                runs.append(self._format_to_run(text, frag.charFormat(), etype))
            el = Element(T.ACTION if etype == T.IMAGE else etype, merge_runs(runs))
            whole = s <= b0 and e >= b1
            if whole:
                el.scene_number = meta.get("scene_number")
                el.dual = meta.get("dual", 0)
                el.centered = meta.get("centered", False)
                el.extra.update(meta.get("extra", {}))
            out.append(el)
            block = block.next()
        return out

    def createMimeDataFromSelection(self):        # noqa: N802 (Qt name)
        md = super().createMimeDataFromSelection()
        cur = self.textCursor()
        els = self.elements_between(cur.selectionStart(), cur.selectionEnd())
        if els:
            md.setData(MIME, Script(elements=els).to_json(indent=0).encode("utf-8"))
            md.setText("\n\n".join(e.text for e in els) if len(els) > 1 else els[0].text)
        return md

    def canInsertFromMimeData(self, source) -> bool:   # noqa: N802
        return source.hasFormat(MIME) or source.hasText() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source: QMimeData):   # noqa: N802
        self._pasted = True                       # pasted words don't count towards the goal
        if source.hasFormat(MIME):
            try:
                els = Script.from_json(bytes(source.data(MIME)).decode("utf-8")).elements
            except ValueError:
                els = []
            if els:
                self.insert_elements(els)
                return
        if source.hasText():
            els = smart_paste_elements(source.text())
            if els:
                self.insert_elements(els)
                return
            cur = self.textCursor()
            cur.insertText(source.text().replace("\r\n", "\n").replace("\n", LINE_SEP))
            self.setTextCursor(cur)
            return
        super().insertFromMimeData(source)

    def insert_elements(self, els: list[Element]):
        """Paste paragraphs at the cursor: the first one joins the current
        paragraph, the rest follow as their own paragraphs (one Undo step)."""
        cur = self.textCursor()
        cur.beginEditBlock()
        self._busy = True
        try:
            if cur.hasSelection():
                cur.removeSelectedText()
            for i, el in enumerate(els):
                if i:
                    cur.insertBlock(self._block_format(el.type), self._type_char_format(el.type))
                    self.set_block_type(cur.block(), el.type)
                elif not cur.block().text().strip() and len(els) > 1:
                    self.set_block_type(cur.block(), el.type)
                etype = block_type(cur.block())
                if i and (el.scene_number or el.extra or el.centered):
                    meta = {}
                    if el.scene_number:
                        meta["scene_number"] = el.scene_number
                    if el.centered:
                        meta["centered"] = True
                    extra = {k: v for k, v in el.extra.items() if k != "image"}
                    if extra:
                        meta["extra"] = extra
                    self._set_meta(cur.block(), meta)
                img = el.extra.get("image") if el.type == T.IMAGE else None
                if img and img.get("png"):
                    qimg = QImage.fromData(base64.b64decode(img["png"]), "PNG")
                    self.document().addResource(QTextDocument.ResourceType.ImageResource,
                                                QUrl(img["name"]), qimg)
                    meta = block_meta(cur.block())
                    meta["image"] = {k: v for k, v in img.items() if k != "png"}
                    self.set_block_type(cur.block(), T.IMAGE)
                    self._set_meta(cur.block(), meta)
                    cur.insertImage(self._image_format(img["name"], img["width_in"], img["height_in"]))
                    continue
                base = self._type_char_format(etype)
                for r in el.runs:
                    cur.insertText(r.text.replace("\n", LINE_SEP), self._run_format(base, r))
        finally:
            self._busy = False
            cur.endEditBlock()
        self.setTextCursor(cur)
        self._struct_timer.start()
        self._after_change()

    # ================================================================ paragraphs as blocks
    def set_block_extra(self, number: int, key: str, value):
        """Store a planning value (synopsis, colour, storylines, notes...) on a paragraph.
        It is an ordinary edit, so Undo takes it back."""
        block = self.document().findBlockByNumber(number)
        if not block.isValid():
            return
        meta = block_meta(block)
        extra = meta.setdefault("extra", {})
        if value in (None, "", [], {}):
            extra.pop(key, None)
        else:
            extra[key] = value
        if not extra:
            meta.pop("extra")
        self._quiet = True
        try:
            cur = QTextCursor(block)
            cur.beginEditBlock()
            self._set_meta(block, meta)
            cur.endEditBlock()
        finally:
            self._quiet = False
        self.projectChanged.emit("scene")

    def block_extra(self, number: int) -> dict:
        return block_meta(self.document().findBlockByNumber(number)).get("extra", {})

    def scene_ranges(self) -> list[tuple[int, int]]:
        """(first block, last block) of every scene."""
        heads = [n for n, *_ in self.scenes()]
        last = self.document().blockCount() - 1
        return [(h, (heads[i + 1] - 1) if i + 1 < len(heads) else last) for i, h in enumerate(heads)]

    def _delete_blocks(self, cur: QTextCursor, first: int, last: int):
        doc = self.document()
        a, b = doc.findBlockByNumber(first), doc.findBlockByNumber(last)
        nxt = b.next()
        at_top = not a.previous().isValid()
        keep_fmt = keep_cf = None
        if not at_top:
            start = a.previous().position() + a.previous().length() - 1
            end = b.position() + b.length() - 1
        elif nxt.isValid():
            start, end = a.position(), nxt.position()
            keep_fmt, keep_cf = nxt.blockFormat(), nxt.charFormat()
        else:
            start, end = a.position(), b.position() + b.length() - 1
        cur.setPosition(start)
        cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        cur.removeSelectedText()
        if at_top and keep_fmt is not None:
            first_block = doc.firstBlock()
            QTextCursor(first_block).setBlockFormat(keep_fmt)
            QTextCursor(first_block).setBlockCharFormat(keep_cf)

    def _insert_paragraphs(self, cur: QTextCursor, before: int, els: list[Element]):
        """Insert elements as whole paragraphs in front of paragraph number `before`
        (or at the end when `before` is past the last paragraph)."""
        doc = self.document()
        n = doc.blockCount()
        if before >= n:
            cur.setPosition(doc.lastBlock().position() + doc.lastBlock().length() - 1)
            for el in els:
                cur.insertBlock()
                self._fill_block(cur, el)
            return
        if before == 0:
            cur.setPosition(0)
            cur.insertBlock()                           # empty paragraph at the very top
            cur.setPosition(0)
            self._fill_block(cur, els[0])
            rest = els[1:]
            anchor = cur.block()
        else:
            rest = els
            anchor = doc.findBlockByNumber(before - 1)
        cur.setPosition(anchor.position() + anchor.length() - 1)
        for el in rest:
            cur.insertBlock()
            self._fill_block(cur, el)

    def _fill_block(self, cur: QTextCursor, el: Element):
        meta = {}
        if el.scene_number:
            meta["scene_number"] = el.scene_number
        if el.centered:
            meta["centered"] = True
        if el.page_break_before:
            meta["page_break_before"] = True
        extra = {k: v for k, v in el.extra.items() if k != "image"}
        if extra:
            meta["extra"] = extra
        img = el.extra.get("image") if el.type == T.IMAGE else None
        if img:
            meta["image"] = {k: v for k, v in img.items() if k != "png"}
        cur.setBlockFormat(self._block_format(el.type, meta or None))
        tcf = self._type_char_format(el.type)
        cur.setBlockCharFormat(tcf)
        if img and img.get("png"):
            qimg = QImage.fromData(base64.b64decode(img["png"]), "PNG")
            self.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(img["name"]), qimg)
            cur.insertImage(self._image_format(img["name"], img["width_in"], img["height_in"]))
            return
        for r in el.runs:
            cur.insertText(r.text.replace("\n", LINE_SEP), self._run_format(tcf, r))

    def move_scene(self, src: int, dst: int):
        """Move scene number `src` (0-based) so it becomes scene `dst`. One Undo step."""
        ranges = self.scene_ranges()
        if not (0 <= src < len(ranges)) or src == dst or not (0 <= dst <= len(ranges)):
            return
        first, last = ranges[src]
        els = []
        doc = self.document()
        for n in range(first, last + 1):
            b = doc.findBlockByNumber(n)
            els += self.elements_between(b.position(), b.position() + b.length() - 1) or \
                [Element(block_type(b))]
        target = ranges[dst][0] if dst < len(ranges) else doc.blockCount()
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        self._busy = True
        self._quiet = True
        try:
            if target > last:                          # moving down: insert first, then delete
                self._insert_paragraphs(cur, target, els)
                self._delete_blocks(cur, first, last)
            else:
                self._delete_blocks(cur, first, last)
                self._insert_paragraphs(cur, target, els)
        finally:
            self._busy = False
            self._quiet = False
            cur.endEditBlock()
        self._struct_timer.start()
        self.structureChanged.emit()
        self.projectChanged.emit("scene")

    def add_scene(self, heading: str, synopsis: str = "", after: int | None = None) -> int:
        """A new scene (heading + empty action) at the end, or after scene `after`."""
        ranges = self.scene_ranges()
        doc = self.document()
        target = doc.blockCount() if after is None or after + 1 >= len(ranges) else ranges[after + 1][0]
        heading_el = Element.plain(T.SCENE_HEADING, heading.upper())
        if synopsis:
            heading_el.extra["synopsis"] = synopsis
        els = [heading_el, Element(T.ACTION)]
        last = doc.lastBlock()
        cur = QTextCursor(doc)
        cur.beginEditBlock()
        self._busy = True
        try:
            if target >= doc.blockCount() and not last.text().strip() and doc.blockCount() == 1:
                cur.setPosition(0)
                self._fill_block(cur, els[0])
                self._insert_paragraphs(cur, 1, els[1:])
                number = 0
            else:
                self._insert_paragraphs(cur, target, els)
                number = target
        finally:
            self._busy = False
            cur.endEditBlock()
        self._struct_timer.start()
        self.structureChanged.emit()
        return number

    # ================================================================ find and replace
    def find_all(self, text: str, case: bool = False, whole: bool = False,
                 etype: str | None = None, regex: bool = False) -> list[QTextCursor]:
        if not text:
            return []
        pattern = text if regex else re.escape(text)
        if whole:
            pattern = rf"(?<![\w']){pattern}(?![\w'])"
        try:
            rx = re.compile(pattern, 0 if case else re.IGNORECASE)
        except re.error:
            return []
        out = []
        block = self.document().firstBlock()
        while block.isValid():
            if etype is None or block_type(block) == etype:
                shown = block.text()
                if self.caps(block_type(block)):
                    shown = shown.upper()
                for m in rx.finditer(shown):
                    if m.end() > m.start():
                        c = QTextCursor(self.document())
                        c.setPosition(block.position() + m.start())
                        c.setPosition(block.position() + m.end(), QTextCursor.MoveMode.KeepAnchor)
                        out.append(c)
            block = block.next()
        return out

    def replace_cursors(self, cursors: list[QTextCursor], new: str) -> int:
        if not cursors:
            return 0
        edit = QTextCursor(self.document())
        edit.beginEditBlock()
        for c in sorted(cursors, key=lambda c: c.selectionStart(), reverse=True):
            fmt = QTextCursor(c)
            fmt.setPosition(c.selectionStart() + 1)
            c.insertText(new, fmt.charFormat())
        edit.endEditBlock()
        self._struct_timer.start()
        return len(cursors)

    # ================================================================ rename a character
    def rename_character(self, old: str, new: str, everywhere: bool = True) -> int:
        """Changes a character's name on every cue (keeping (V.O.), (CONT'D)...) and,
        if `everywhere`, in action and dialogue too (keeping CAPS / Title case). One Undo step."""
        old_u, new = old.strip().upper(), new.strip()
        if not old_u or not new or old_u == new.upper():
            return 0
        rx = re.compile(rf"(?<![\w']){re.escape(old_u)}(?![\w'])", re.IGNORECASE)
        changes = []
        block = self.document().firstBlock()
        while block.isValid():
            etype = block_type(block)
            text = block.text()
            if etype == T.CHARACTER:
                if base_name(text).upper() == old_u:
                    m = rx.search(text)
                    if m:
                        changes.append((block.position() + m.start(), m.end() - m.start(), new.upper()))
            elif everywhere and etype not in (T.SCENE_HEADING, T.TRANSITION):
                for m in rx.finditer(text):
                    found = m.group(0)
                    rep = new.upper() if found.isupper() else (
                        new.title() if found[:1].isupper() else new.lower())
                    if self.caps(etype):
                        rep = new.upper()
                    changes.append((block.position() + m.start(), m.end() - m.start(), rep))
            block = block.next()
        if not changes:
            return 0
        cur = QTextCursor(self.document())
        cur.beginEditBlock()
        for pos, n, rep in sorted(changes, reverse=True):
            cur.setPosition(pos + 1)
            fmt = cur.charFormat()
            cur.setPosition(pos)
            cur.setPosition(pos + n, QTextCursor.MoveMode.KeepAnchor)
            cur.insertText(rep, fmt)
        cur.endEditBlock()
        profiles = self.project.get("characters", {})
        if old_u in profiles and new.upper() not in profiles:
            profiles[new.upper()] = profiles.pop(old_u)
        self._struct_timer.start()
        return len(changes)

    # ================================================================ counts
    def word_count(self) -> int:
        n = 0
        block = self.document().firstBlock()
        while block.isValid():
            if block_type(block) not in (T.NOTE, T.SECTION, T.SYNOPSIS):
                n += _words(block.text())
            block = block.next()
        return n

    # ================================================================ focus and typewriter
    def set_focus_mode(self, on: bool):
        self.focus_mode = on
        self.viewport().update()

    def set_typewriter(self, on: bool):
        self.typewriter = on
        if on:
            self._typewriter_range()
            self._typewriter_scroll()
        else:
            self.document().adjustSize()
            self.document().documentLayout().documentSizeChanged.emit(self.document().size())

    def _typewriter_range(self, *_):
        sb = self.verticalScrollBar()
        if self._in_range or not self.typewriter:
            return
        self._in_range = True
        try:
            doc_h = self.document().size().height() + 18
            extra = self.viewport().height() // 2
            sb.setRange(0, max(0, int(doc_h - self.viewport().height() + extra)))
        finally:
            self._in_range = False

    def _typewriter_scroll(self):
        if not getattr(self, "typewriter", False):
            return
        r = self.cursorRect()
        sb = self.verticalScrollBar()
        sb.setValue(sb.value() + r.center().y() - self.viewport().height() // 2)

    def _paint_focus(self, p: QPainter):
        """Focus mode: everything except the paragraph you're writing fades back."""
        if not self.focus_mode:
            return
        doc = self.document()
        lay = doc.documentLayout()
        block = self.textCursor().block()
        # fade the whole scene except the current paragraph
        r = lay.blockBoundingRect(block)
        sy = self.verticalScrollBar().value()
        sx = self.horizontalScrollBar().value()
        top, bottom = r.top() - sy, r.bottom() - sy
        w = doc.pageSize().width()
        veil = QColor(C.PAPER)
        veil.setAlpha(185)
        vh = self.viewport().height()
        if top > 0:
            p.fillRect(QRectF(-sx, 0, w, top), veil)
        if bottom < vh:
            p.fillRect(QRectF(-sx, bottom, w, vh - bottom), veil)

    # ================================================================ printing
    @contextmanager
    def clean_for_print(self):
        """Hide spelling underlines (they live on the page layout) while printing."""
        hl = getattr(self, "spell", None)
        doc = hl.document() if hl is not None else None
        if doc is not None:
            hl.setDocument(None)
        try:
            yield
        finally:
            if doc is not None:
                hl.setDocument(doc)

    # ================================================================ context menu
    def contextMenuEvent(self, e):                  # noqa: N802
        menu = self.createStandardContextMenu(e.pos())
        cur = self.cursorForPosition(e.pos())
        first = menu.actions()[0] if menu.actions() else None
        for hook in self.context_hooks:
            extra = hook(cur)
            if extra:
                for a in extra:
                    if a is None:
                        menu.insertSeparator(first)
                    else:
                        a.setParent(menu)
                        menu.insertAction(first, a)
                menu.insertSeparator(first)
        menu.exec(e.globalPos())


def smart_paste_elements(text: str) -> list[Element] | None:
    """Plain text that looks like a screenplay (a scene heading, or a NAME followed by a
    line of speech) becomes proper elements. Anything else pastes as plain text."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    if "\n" not in text:
        return None
    script = fountain.parse(text)
    kinds = {e.type for e in script.elements}
    if T.SCENE_HEADING in kinds or T.CHARACTER in kinds or T.TRANSITION in kinds:
        return script.elements
    return None


def revision_color(level: int) -> str:
    return REVISION_COLORS[level % len(REVISION_COLORS)][1]


def menu_with(parent, actions) -> QMenu:
    m = QMenu(parent)
    for a in actions:
        m.addSeparator() if a is None else m.addAction(a)
    return m


