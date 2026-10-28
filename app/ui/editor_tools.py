"""
Formatting, Insert and Production commands for the page.

Part of the editor: ScreenplayEditor inherits these methods, so `self` is the editor.
"""
from __future__ import annotations

import re
import uuid

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFont, QColor, QTextCursor, QImage, QTextCharFormat, QTextDocument

from ..core.ir import T, Run
from ..core.smart import ENTER_NEXT
from .pages import block_type, block_meta, scene_marks

MAX_IMAGE_IN = (6.0, 7.0)   # an image fits inside the action margins


class FormattingTools:
    # ================================================================ text formatting
    def char_state(self) -> dict:
        cf = self.currentCharFormat()
        return {"bold": cf.fontWeight() >= QFont.Weight.DemiBold.value, "italic": cf.fontItalic(),
                "underline": cf.fontUnderline() and not cf.isAnchor(),
                "strike": cf.fontStrikeOut()}

    def _edit_selection(self, change):
        """Apply `change(format) -> format` to every styled piece of the selection
        (or to what you type next, when nothing is selected)."""
        cur = self.textCursor()
        if not cur.hasSelection():
            self.setCurrentCharFormat(change(QTextCharFormat(self.currentCharFormat())))
            self.formatChanged.emit()
            return
        start, end = cur.selectionStart(), cur.selectionEnd()
        doc = self.document()
        pieces = []
        block = doc.findBlock(start)
        while block.isValid() and block.position() <= end:
            for it in block:
                frag = it.fragment()
                if frag.isValid():
                    s, t = max(frag.position(), start), min(frag.position() + frag.length(), end)
                    if s < t:
                        pieces.append((s, t, QTextCharFormat(frag.charFormat())))
            block = block.next()
        edit = QTextCursor(doc)
        edit.beginEditBlock()
        for s, t, fmt in pieces:
            edit.setPosition(s)
            edit.setPosition(t, QTextCursor.MoveMode.KeepAnchor)
            edit.setCharFormat(change(fmt))
        edit.endEditBlock()
        self.formatChanged.emit()

    def toggle_style(self, which: str):
        on = not self.char_state()[which]

        def change(f: QTextCharFormat) -> QTextCharFormat:
            if which == "bold":
                f.setFontWeight(QFont.Weight.Bold if on else QFont.Weight.Normal)
            elif which == "italic":
                f.setFontItalic(on)
            elif which == "underline":
                f.setFontUnderline(on)
            else:
                f.setFontStrikeOut(on)
            return f
        self._edit_selection(change)

    def set_text_color(self, color: str | None):
        def change(f):
            if color:
                f.setForeground(QColor(color))
            else:
                f.clearForeground()
            return f
        self._edit_selection(change)

    def set_highlight(self, color: str | None):
        def change(f):
            if color:
                f.setBackground(QColor(color))
            else:
                f.clearBackground()
            return f
        self._edit_selection(change)

    def clear_formatting(self):
        etype = self.current_type()
        self._edit_selection(lambda f: f if f.isImageFormat() else self._type_char_format(etype))

    def change_case(self, mode: str):
        """mode: 'upper', 'lower' or 'title'. Works on the selection, or the current word."""
        cur = self.textCursor()
        if not cur.hasSelection():
            cur.select(QTextCursor.SelectionType.WordUnderCursor)
        text = cur.selectedText()
        if not text:
            return
        new = {"upper": text.upper(), "lower": text.lower(), "title": text.title()}[mode]
        fmt = cur.charFormat()
        start = cur.selectionStart()
        cur.insertText(new, fmt)
        cur.setPosition(start)
        cur.setPosition(start + len(new), QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cur)

    # ================================================================ insert
    def insert_link(self, text: str, url: str):
        """Turns the selection into a link, or inserts `text` as a link."""
        url = url.strip()
        if not url:
            return
        cur = self.textCursor()
        if cur.hasSelection():
            self._edit_selection(lambda f: self._run_format(f, Run("", link=url)))
            cur.setPosition(cur.selectionEnd())
            self.setTextCursor(cur)
        else:
            cur.insertText(text or url, self._run_format(cur.charFormat(), Run("", link=url)))
            self.setTextCursor(cur)
        self.setCurrentCharFormat(self._type_char_format(self.current_type()))

    def insert_image(self, path: str) -> bool:
        img = QImage(path)
        if img.isNull():
            return False
        if img.width() > 1600:                        # keep files small
            img = img.scaledToWidth(1600, Qt.TransformationMode.SmoothTransformation)
        w_in, h_in = img.width() / 96, img.height() / 96
        scale = min(1.0, MAX_IMAGE_IN[0] / w_in, MAX_IMAGE_IN[1] / h_in)
        w_in, h_in = w_in * scale, h_in * scale
        name = f"image-{uuid.uuid4().hex[:8]}.png"
        self.document().addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), img)
        cur = self.textCursor()
        cur.beginEditBlock()
        if cur.block().text().strip():
            self._new_block_after(T.IMAGE)
        else:
            self.set_block_type(cur.block(), T.IMAGE)
        block = self.textCursor().block()
        meta = block_meta(block)
        meta["image"] = {"name": name, "width_in": round(w_in, 3), "height_in": round(h_in, 3)}
        self._set_meta(block, meta)
        self.textCursor().insertImage(self._image_format(name, w_in, h_in))
        self._new_block_after(T.ACTION)
        cur.endEditBlock()
        self._after_change()
        return True

    def insert_page_break(self):
        """Ctrl+Enter: the next paragraph starts on a new page."""
        cur = self.textCursor()
        cur.beginEditBlock()
        etype = self.current_type()
        if not cur.atBlockEnd():
            cur.insertBlock()
            self.setTextCursor(cur)
        else:
            self._new_block_after(ENTER_NEXT.get(etype, T.ACTION) if cur.block().text().strip()
                                  else etype)
        block = self.textCursor().block()
        meta = block_meta(block)
        meta["page_break_before"] = True
        self._set_meta(block, meta)
        cur.endEditBlock()
        self._after_change()

    def remove_page_break(self):
        block = self.textCursor().block()
        meta = block_meta(block)
        if meta.pop("page_break_before", None):
            self._set_meta(block, meta)

    # ================================================================ production
    def number_scenes(self, locked: bool = False):
        """Gives every scene heading a number, 1, 2, 3 ... (one Undo step).

        With locked scene numbers (production drafts), existing numbers never change:
        a new scene after 12 becomes 12A, then 12B; a new scene before 1 becomes A1."""
        cur = self.textCursor()
        cur.beginEditBlock()
        headings = []
        block = self.document().firstBlock()
        while block.isValid():
            if block_type(block) == T.SCENE_HEADING and block.text().strip():
                headings.append(block)
            block = block.next()
        if locked:
            numbers = [block_meta(b).get("scene_number") for b in headings]
            new = locked_numbers(numbers)
        else:
            new = [str(i) for i in range(1, len(headings) + 1)]
        for b, num in zip(headings, new):
            meta = block_meta(b)
            if meta.get("scene_number") != num:
                meta["scene_number"] = num
                self._set_meta(b, meta)
        cur.endEditBlock()
        self.structureChanged.emit()
        self.viewport().update()

    def clear_scene_numbers(self):
        cur = self.textCursor()
        cur.beginEditBlock()
        block = self.document().firstBlock()
        while block.isValid():
            meta = block_meta(block)
            if meta.pop("scene_number", None):
                self._set_meta(block, meta)
            block = block.next()
        cur.endEditBlock()
        self.structureChanged.emit()
        self.viewport().update()

    def has_scene_numbers(self) -> bool:
        return bool(scene_marks(self.document()))


def _bump(label: str) -> str:
    """12 -> 12A, 12A -> 12B, A1 -> B1."""
    m = re.fullmatch(r"(\d+)([A-Z]*)", label)
    if m:
        num, suf = m.groups()
        return num + ("A" if not suf else suf[:-1] + chr(ord(suf[-1]) + 1) if suf[-1] != "Z" else suf + "A")
    m = re.fullmatch(r"([A-Z]+)(\d+)", label)
    if m:
        pre, num = m.groups()
        return chr(ord(pre[0]) + 1) + pre[1:] + num
    return label + "A"


def locked_numbers(numbers: list) -> list[str]:
    """Fill in numbers for new scenes without touching the ones already given."""
    taken = {n for n in numbers if n}
    out = []
    prev = None
    for n in numbers:
        if n:
            out.append(n)
            prev = n
            continue
        if prev is None:
            first_num = next((x for x in numbers if x), "1")
            m = re.match(r"\d+", first_num)
            cand = "A" + (m.group(0) if m else "1")
        else:
            cand = _bump(prev)
        while cand in taken:
            cand = _bump(cand)
        taken.add(cand)
        out.append(cand)
        prev = cand
    return out
