"""
The screenplay page.

Every paragraph (QTextBlock) carries its element type in a block-format property,
so it survives undo, copy/paste and splitting. Layout numbers come from
core/layout.py; flow rules and predictions come from core/smart.py; page rules
come from ui/pages.py (shared with PDF export and printing).

The page is split over three files so each stays readable:
  editor.py        - this file: page layout, element types, keys, SmartType, painting
  editor_io.py     - loading a script onto the page and reading it back
  editor_tools.py  - formatting, insert (image, link, page break) and scene numbers
"""
from __future__ import annotations

import json

from PySide6.QtCore import Qt, QTimer, Signal, QPoint, QPointF, QRectF, QSizeF, QUrl
from PySide6.QtGui import (QFont, QFontMetricsF, QPainter, QColor, QPalette, QTextCursor,
                           QTextBlockFormat, QTextCharFormat, QTextFormat, QKeyEvent,
                           QDesktopServices)
from PySide6.QtWidgets import QTextEdit, QFrame, QListWidget, QListWidgetItem

from ..core.ir import T, Script
from ..core.layout import PAGE_WIDTH_IN, specs_for, spacing_for
from ..core.smart import (SmartMemory, Completion, Suggestion, CAPS_TYPES, ENTER_NEXT,
                          EMPTY_ENTER, TAB_NEXT, SHIFT_TAB_NEXT, classify_typed, live_retype)
from .editor_io import DocumentIO, LINE_SEP, NOTE_TYPES
from .editor_tools import FormattingTools
from .editor_extras import EditorExtras
from ..core.pagination import plan
from .pages import (PROP_TYPE, PROP_META, PROP_AUTO, SCREEN_GAP, block_type, block_meta,
                    is_auto_break, page_size_px, page_model, measure, find_splits,
                    draw_page_furniture, scene_marks, revision_marks)
from .theme import C

KEEP_TOGETHER = (T.SCENE_HEADING, T.CHARACTER, T.PARENTHETICAL, T.TRANSITION, T.SHOT, T.IMAGE)

SHORT = {T.SCENE_HEADING: "Scene", T.ACTION: "Action", T.CHARACTER: "Character",
         T.PARENTHETICAL: "Paren", T.DIALOGUE: "Dialogue", T.TRANSITION: "Transition",
         T.SHOT: "Shot", T.GENERAL: "General", T.NOTE: "Note", T.SECTION: "Section",
         T.SYNOPSIS: "Synopsis", T.LYRICS: "Lyrics", T.IMAGE: "Image"}
SHORTCUT_TYPES = [T.SCENE_HEADING, T.ACTION, T.CHARACTER, T.PARENTHETICAL,
                  T.DIALOGUE, T.TRANSITION, T.SHOT, T.GENERAL]      # Ctrl+1 .. Ctrl+8


class SuggestPopup(QListWidget):
    """SmartType list. Never takes focus: the editor routes Up/Down/Enter to it."""

    def __init__(self, editor: "ScreenplayEditor"):
        super().__init__(None)
        self.editor = editor
        self.setObjectName("suggest")
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.itemClicked.connect(lambda it: editor.accept_suggestion(self.row(it)))

    def show_items(self, items: list[Suggestion], at: QPoint):
        self.clear()
        for s in items:
            QListWidgetItem(s.label, self)
        self.setCurrentRow(-1)
        fm = self.fontMetrics()
        w = max(200, max(fm.horizontalAdvance(s.label) for s in items) + 48)
        h = sum(self.sizeHintForRow(i) for i in range(self.count())) + 12
        self.setFixedSize(w, h)
        self.move(at)
        self.show()


class ScreenplayEditor(DocumentIO, FormattingTools, EditorExtras, QTextEdit):
    elementChanged = Signal(str)          # current paragraph's element type
    hintChanged = Signal(str)             # "↵ Dialogue   ⇥ Parenthetical"
    structureChanged = Signal()           # debounced: scenes / characters may have changed
    pageChanged = Signal(int, int)        # (current page, total pages)
    formatChanged = Signal()              # bold / italic / ... under the cursor changed
    projectChanged = Signal(str)          # cards, beats, notes... changed (which part)

    def __init__(self, memory: SmartMemory, parent=None):
        super().__init__(parent)
        self.memory = memory
        self.doc_key: str | None = None
        self.title_page: list[tuple[str, str]] = []
        self.zoom = 1.0
        self._busy = False
        self._completion = Completion([])
        self._ghost_rest = ""
        self._dismissed = False
        self._paginating = False
        self._splits = []
        self.project: dict = {}               # cards, beats, profiles... (Script.extra)
        self._layers: dict = {}               # highlight layers (find, character lens...)
        self.focus_mode = False
        self._loading = False
        self._quiet = False
        self.typewriter = False
        self._in_range = False
        self.context_hooks: list = []         # functions adding right-click menu items
        self.paint_hooks: list = []           # functions drawing on the page (note markers...)
        self.star_colors: dict = {}           # revision level -> colour of its asterisks
        self.revision_mode = False            # mark changed paragraphs with the revision colour
        self.revision_level = 1
        self._dirty: list[QTextCursor] = []   # paragraphs changed since the last page pass

        self.setObjectName("page")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAcceptRichText(False)
        self.setTabChangesFocus(False)
        self.setCursorWidth(2)
        self.setMouseTracking(True)
        self.setLineWrapMode(QTextEdit.LineWrapMode.FixedPixelWidth)
        self.apply_colors()
        self.setAutoFillBackground(True)

        self.popup = SuggestPopup(self)
        self._struct_timer = QTimer(self, singleShot=True, interval=500)
        self._struct_timer.timeout.connect(self._on_structure_timer)
        self.textChanged.connect(self._on_text_changed)
        self.cursorPositionChanged.connect(self._on_cursor_moved)
        self.currentCharFormatChanged.connect(lambda _: self.formatChanged.emit())
        # QTextEdit quietly switches pagination off whenever it re-lays the text out
        # (resizing, typing past the window...). Switch it straight back on.
        self.document().documentLayout().documentSizeChanged.connect(self._ensure_pages)
        # The page rules run shortly after every edit (not after Undo/Redo, which
        # already bring the right page breaks back with them).
        self._page_timer = QTimer(self, singleShot=True, interval=250)
        self._page_timer.timeout.connect(self._paginate)
        self.document().undoCommandAdded.connect(self._page_timer.start)
        self.document().contentsChange.connect(self._track_change)
        self.verticalScrollBar().rangeChanged.connect(self._typewriter_range)
        self.cursorPositionChanged.connect(self._typewriter_scroll)
        self._apply_page_setup()
        self.load_script(Script())

    # ================================================================ page layout
    def apply_colors(self):
        """Paper and ink from the current theme (Day / Night / Midnight)."""
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Base, QColor(C.PAPER))
        pal.setColor(QPalette.ColorRole.Window, QColor(C.GREIGE))
        pal.setColor(QPalette.ColorRole.Text, QColor(C.INK))
        self.setPalette(pal)
        self.viewport().update()

    @property
    def dpi(self) -> float:
        return 96.0 * self.zoom

    def script_font(self) -> str:
        """The script's typeface (Format > Script Font). Courier Prime unless changed."""
        return self.project.get("font") or "Courier Prime"

    def page_font(self) -> QFont:
        f = QFont(self.script_font())
        f.setStyleHint(QFont.StyleHint.TypeWriter)
        f.setPixelSize(round(self.dpi / 6))        # 12pt at 72pt/inch
        return f

    def _apply_page_setup(self):
        """Font, 1-inch top/bottom margins and US Letter pages. Safe to call any time."""
        doc = self.document()
        was_modified = doc.isModified()            # page setup is not an edit
        self.setFont(self.page_font())
        doc.setDefaultFont(self.page_font())
        doc.setDocumentMargin(0)
        root = doc.rootFrame()
        ff = root.frameFormat()
        if ff.topMargin() != self.dpi or ff.bottomMargin() != self.dpi:
            ff.setTopMargin(self.dpi)
            ff.setBottomMargin(self.dpi)
            root.setFrameFormat(ff)
        width = round(PAGE_WIDTH_IN * self.dpi)
        if self.lineWrapColumnOrWidth() != width:
            self.setLineWrapColumnOrWidth(width)
        self._apply_page_size()
        doc.setModified(was_modified)
        self._center_page()

    def _apply_page_size(self):
        w, h = page_size_px(self.dpi)
        size = self.document().pageSize()
        if size.width() != w or size.height() != h:
            self.document().setPageSize(QSizeF(w, h))

    def _ensure_pages(self, *_):
        if self.document().pageSize().height() <= 0:
            self._apply_page_size()

    def _center_page(self):
        page_w = round(PAGE_WIDTH_IN * self.dpi)
        sb = self.verticalScrollBar().sizeHint().width()
        side = max(12, (self.width() - sb - page_w) // 2)
        m = self.viewportMargins()
        if (m.left(), m.right()) != (side, side):
            self.setViewportMargins(side, 18, side, 0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._center_page()
        self._apply_page_size()            # Qt resets the page height on every resize

    def set_zoom(self, zoom: float):
        """Re-lays the whole script at a new size. Note: this clears the Undo history."""
        zoom = max(0.6, min(2.0, zoom))
        if abs(zoom - self.zoom) < 0.01:
            return
        cur = self.textCursor()
        where = (cur.blockNumber(), cur.positionInBlock())
        modified = self.document().isModified()
        script = self.to_script(keep_empty=True)
        self.zoom = zoom
        self._apply_page_setup()
        self.load_script(script, self.doc_key)
        block = self.document().findBlockByNumber(where[0])
        if block.isValid():
            c = QTextCursor(block)
            c.setPosition(block.position() + min(where[1], block.length() - 1))
            self.setTextCursor(c)
            self.ensureCursorVisible()
        self.document().setModified(modified)

    def _paginate(self, join: bool = True):
        """Apply the screenplay page rules: work out which paragraphs need an automatic page
        break and update only the ones that changed. The change joins the writer's last
        edit, so one Ctrl+Z undoes the edit and its page breaks together."""
        if self._paginating:
            return
        self._paginating = True
        was_busy = self._busy
        self._busy = True
        try:
            doc = self.document()
            self._apply_page_size()
            revised = self._revised_blocks()
            blocks, geoms = measure(doc)
            wanted = plan(geoms, page_model(self.dpi)).breaks
            changed = [(i, b) for i, b in enumerate(blocks) if (i in wanted) != is_auto_break(b)]
            if changed or revised:
                cur = QTextCursor(doc)
                if join and doc.availableUndoSteps() > 0:
                    cur.joinPreviousEditBlock()
                else:
                    cur.beginEditBlock()
                for b in revised:                        # revision marks join the same Undo step
                    meta = block_meta(b)
                    meta.setdefault("extra", {})["revision"] = self.revision_level
                    cur.setPosition(b.position())
                    cur.setBlockFormat(self._block_format(block_type(b), meta, is_auto_break(b)))
                if revised:
                    blocks, geoms = measure(doc)
                    wanted = plan(geoms, page_model(self.dpi)).breaks
                    changed = [(i, b) for i, b in enumerate(blocks)
                               if (i in wanted) != is_auto_break(b)]
                for i, b in changed:
                    cur.setPosition(b.position())
                    cur.setBlockFormat(self._block_format(block_type(b), block_meta(b) or None,
                                                          auto=i in wanted))
                cur.endEditBlock()
            self._splits = find_splits(doc, self.dpi)
        finally:
            self._busy = was_busy
            self._paginating = False
        self.viewport().update()
        self.pageChanged.emit(self.current_page(), self.page_count())

    def _track_change(self, pos: int, removed: int, added: int):
        """Remember which paragraphs the writer changed (for revision marks)."""
        if not self.revision_mode or self._paginating or self._loading or self._quiet:
            return
        doc = self.document()
        end = min(pos + added, doc.characterCount() - 1)
        block = doc.findBlock(pos)
        while block.isValid() and block.position() <= end:
            self._dirty.append(QTextCursor(block))
            block = block.next()

    def _revised_blocks(self) -> list:
        out, seen = [], set()
        for c in self._dirty:
            b = c.block()
            if b.isValid() and b.blockNumber() not in seen and b.text().strip():
                seen.add(b.blockNumber())
                if block_meta(b).get("extra", {}).get("revision") != self.revision_level:
                    out.append(b)
        self._dirty = []
        return out

    def set_template(self, name: str):
        """Screenplay, TV Drama, Multi-Camera Sitcom or Stage Play: re-lays every page."""
        if self.project.get("template", "Screenplay") == name:
            return
        modified = self.document().isModified()
        script = self.to_script(keep_empty=True)
        script.extra["template"] = name
        where = self.textCursor().blockNumber()
        self.load_script(script, self.doc_key)
        self.goto_block(where)
        self.document().setModified(True if not modified else modified)

    def set_script_font(self, family: str):
        """Change the typeface of the whole script (re-lays every page)."""
        if family == self.script_font():
            return
        script = self.to_script(keep_empty=True)
        if family == "Courier Prime":
            script.extra.pop("font", None)
        else:
            script.extra["font"] = family
        where = self.textCursor().blockNumber()
        self.load_script(script, self.doc_key)
        self._apply_page_setup()
        self.goto_block(where)
        self.document().setModified(True)

    def set_font_family(self, family: str):
        """Font of the selection (or of what you type next), like a word processor."""
        default = self.script_font()

        def change(f):
            if family == default:
                f.clearProperty(QTextFormat.Property.FontFamilies)
                f.clearProperty(QTextFormat.Property.FontFamily)
            else:
                f.setFontFamilies([family])
            return f
        self._edit_selection(change)

    def current_font_family(self) -> str:
        fams = self.currentCharFormat().fontFamilies() if \
            self.currentCharFormat().hasProperty(QTextFormat.Property.FontFamilies) else None
        return fams[0] if fams else self.script_font()

    def touch_project(self, part: str = ""):
        """Something in the project data changed: mark the script unsaved."""
        self.document().setModified(True)
        self.projectChanged.emit(part)

    def page_count(self) -> int:
        return max(1, self.document().pageCount())

    def current_page(self) -> int:
        cur = self.textCursor()
        y = self.document().documentLayout().blockBoundingRect(cur.block()).top()
        lay = cur.block().layout()
        if lay is not None and lay.lineCount():
            line = lay.lineForTextPosition(cur.positionInBlock())
            if line.isValid():              # mid-edit the layout can be stale: skip, don't crash
                y += line.y()
        return int(y // page_size_px(self.dpi)[1]) + 1

    # ================================================================ element types
    def _block_format(self, etype: str, meta: dict | None = None,
                      auto: bool = False) -> QTextBlockFormat:
        specs = specs_for(self.project.get("template"))
        spec = specs.get(etype, specs[T.ACTION])
        left, right, before, align, _caps, _next = spec
        if etype in NOTE_TYPES or etype == T.IMAGE:
            before = 12
        f = QTextBlockFormat()
        f.setLeftMargin(left * self.dpi)
        f.setRightMargin((PAGE_WIDTH_IN - right) * self.dpi)
        f.setTopMargin(before / 72 * self.dpi)
        f.setBottomMargin(0)
        if etype != T.IMAGE:
            spacing = spacing_for(self.project.get("template"), etype)
            f.setLineHeight(self.dpi / 6 * spacing, QTextBlockFormat.LineHeightTypes.FixedHeight.value)
        f.setNonBreakableLines(etype in KEEP_TOGETHER)
        if auto or (meta and meta.get("page_break_before")):
            f.setPageBreakPolicy(QTextFormat.PageBreakFlag.PageBreak_AlwaysBefore)
        if auto:
            f.setProperty(PROP_AUTO, True)
        if etype == T.IMAGE or (meta and meta.get("centered")):
            f.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        elif align == "Right":
            f.setAlignment(Qt.AlignmentFlag.AlignRight)
        elif align == "Center":
            f.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        else:
            f.setAlignment(Qt.AlignmentFlag.AlignLeft)
        f.setProperty(PROP_TYPE, etype)
        if meta:
            f.setProperty(PROP_META, json.dumps(meta))
        return f

    def caps(self, etype: str) -> bool:
        """Is this element shown in CAPS? (Scene headings, characters... and in the
        multi-camera template, action too.)"""
        spec = specs_for(self.project.get("template")).get(etype)
        return etype in CAPS_TYPES or bool(spec and spec[4])

    def _type_char_format(self, etype: str) -> QTextCharFormat:
        cf = QTextCharFormat()
        cf.setFontCapitalization(QFont.Capitalization.AllUppercase if self.caps(etype)
                                 else QFont.Capitalization.MixedCase)
        if etype in NOTE_TYPES:
            cf.setForeground(QColor(C.CARAMEL))
        return cf

    block_type = staticmethod(block_type)
    block_meta = staticmethod(block_meta)

    def current_type(self) -> str:
        return block_type(self.textCursor().block())

    def _set_meta(self, block, meta: dict):
        QTextCursor(block).setBlockFormat(self._block_format(block_type(block), meta or None,
                                                             is_auto_break(block)))

    def set_block_type(self, block, etype: str):
        was = self._busy
        self._busy = True
        old = block_type(block)
        cur = QTextCursor(block)
        cur.setBlockFormat(self._block_format(etype, block_meta(block), is_auto_break(block)))
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        tcf = self._type_char_format(etype)
        cur.mergeCharFormat(tcf)
        bcf = cur.blockCharFormat()
        bcf.merge(tcf)
        if old in NOTE_TYPES and etype not in NOTE_TYPES:     # back to normal ink
            self._clear_note_colour(block)
            bcf.clearForeground()
        cur.setBlockCharFormat(bcf)
        if block == self.textCursor().block():
            cf = self.currentCharFormat()
            cf.merge(tcf)
            if old in NOTE_TYPES and etype not in NOTE_TYPES:
                cf.clearForeground()
            self.setCurrentCharFormat(cf)
        self._busy = was

    def _clear_note_colour(self, block):
        pieces = []
        for it in block:
            frag = it.fragment()
            if frag.isValid() and frag.charFormat().foreground().color().name().upper() == C.CARAMEL:
                pieces.append((frag.position(), frag.length(), QTextCharFormat(frag.charFormat())))
        for pos, n, fmt in pieces:
            fmt.clearForeground()
            c = QTextCursor(self.document())
            c.setPosition(pos)
            c.setPosition(pos + n, QTextCursor.MoveMode.KeepAnchor)
            c.setCharFormat(fmt)

    def set_current_type(self, etype: str):
        """Element menu / Ctrl+1..8 / Tab."""
        cur = self.textCursor()
        cur.beginEditBlock()
        block = cur.block()
        old = block_type(block)
        self.set_block_type(block, etype)
        text = block.text().strip()
        if etype == T.PARENTHETICAL and not text:
            self._insert_parens()
        elif old == T.PARENTHETICAL and text in ("()", "("):
            self._replace_block_text("")
        cur.endEditBlock()
        self._after_change()

    def goto_block(self, number: int):
        block = self.document().findBlockByNumber(number)
        if block.isValid():
            cur = QTextCursor(block)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self.setFocus()

    # ================================================================ keyboard and mouse
    def keyPressEvent(self, e: QKeyEvent):
        key, mods = e.key(), e.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        popup_on = self.popup.isVisible() and self.popup.count()

        if popup_on and key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            row = self.popup.currentRow()
            n = self.popup.count()
            row = (row + (1 if key == Qt.Key.Key_Down else -1)) % n if row >= 0 else \
                (0 if key == Qt.Key.Key_Down else n - 1)
            self.popup.setCurrentRow(row)
            return
        if key == Qt.Key.Key_Escape:
            self._dismissed = True
            self.popup.hide()
            self._ghost_rest = ""
            self.viewport().update()
            self._emit_hint()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if ctrl:
                self.insert_page_break()
            elif shift:
                self.textCursor().insertText(LINE_SEP)
            else:
                self.handle_enter()
            return
        if key == Qt.Key.Key_Backtab or (key == Qt.Key.Key_Tab and shift):
            self.set_current_type(SHIFT_TAB_NEXT.get(self.current_type(), T.ACTION))
            return
        if key == Qt.Key.Key_Tab and not ctrl:
            if popup_on and self.popup.currentRow() >= 0:
                self.accept_suggestion(self.popup.currentRow(), advance=False)
            else:
                self.handle_tab()
            return
        if key == Qt.Key.Key_Right and self._ghost_rest and not shift:
            cur = self.textCursor()
            if cur.atBlockEnd():
                self._accept_ghost()
                return
        if ctrl and Qt.Key.Key_1 <= key <= Qt.Key.Key_8:
            self.set_current_type(SHORTCUT_TYPES[key - Qt.Key.Key_1])
            return
        if ctrl and not shift and key in (Qt.Key.Key_B, Qt.Key.Key_I, Qt.Key.Key_U):
            self.toggle_style({Qt.Key.Key_B: "bold", Qt.Key.Key_I: "italic",
                               Qt.Key.Key_U: "underline"}[key])
            return
        if self.current_type() == T.IMAGE and e.text() and e.text().isprintable() and not ctrl:
            self._new_block_after(T.ACTION)          # typing next to a picture starts a new line
        super().keyPressEvent(e)

    def link_at(self, pos) -> str:
        return self.anchorAt(pos)

    def mouseMoveEvent(self, e):
        super().mouseMoveEvent(e)
        ctrl = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if self.link_at(e.position().toPoint()) and ctrl:
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)

    def mouseReleaseEvent(self, e):
        link = self.link_at(e.position().toPoint())
        if link and e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            QDesktopServices.openUrl(QUrl.fromUserInput(link))
            return
        super().mouseReleaseEvent(e)

    # ---------------------------------------------------------------- Enter
    def handle_enter(self):
        cur = self.textCursor()
        cur.beginEditBlock()
        try:
            row = self.popup.currentRow() if self.popup.isVisible() else -1
            chosen = None
            if row >= 0:
                chosen = self._completion.items[row]
            elif self._ghost_rest and self._completion.ghost:
                chosen = self._completion.ghost
            if chosen:
                self._replace_block_text(chosen.text)
                if not chosen.final:          # e.g. "INT. " -> keep typing the location
                    return
            self._enter_after_text()
        finally:
            cur.endEditBlock()
            self._after_change()

    def _enter_after_text(self):
        cur = self.textCursor()
        block = cur.block()
        etype = block_type(block)
        if etype == T.IMAGE:
            self._new_block_after(T.ACTION)
            return
        text = block.text()
        stripped = text.strip()
        if etype == T.PARENTHETICAL and stripped in ("()", "("):
            stripped = ""

        if not stripped:                                # empty: change this paragraph in place
            self._replace_block_text("")
            self.set_block_type(block, EMPTY_ENTER.get(etype, T.ACTION))
            if block_type(block) == T.PARENTHETICAL:
                self._insert_parens()
            return

        rest = text[cur.positionInBlock():]
        at_end = rest.strip() == "" or (etype == T.PARENTHETICAL and rest.strip() == ")")
        if not at_end:                                  # split mid-paragraph, keep the type
            cur.insertBlock()
            self.setTextCursor(cur)
            return

        new_type = classify_typed(etype, text, self.memory.known_characters())
        if new_type:                                    # e.g. typed "MEERA" in Action
            self.set_block_type(block, new_type)
            etype = new_type
        self._new_block_after(ENTER_NEXT.get(etype, T.ACTION))

    def _new_block_after(self, etype: str):
        cur = self.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock)
        cur.insertBlock(self._block_format(etype), self._type_char_format(etype))
        self.setTextCursor(cur)
        self.set_block_type(cur.block(), etype)
        if etype == T.PARENTHETICAL:
            self._insert_parens()

    # ---------------------------------------------------------------- Tab
    def handle_tab(self):
        cur = self.textCursor()
        block = cur.block()
        etype = block_type(block)
        filled = block.text().strip() not in ("", "()")
        if filled and cur.atBlockEnd() and etype in (T.ACTION, T.DIALOGUE):
            cur.beginEditBlock()                        # Action+Tab -> Character below,
            self._new_block_after(TAB_NEXT[etype])      # Dialogue+Tab -> (paren) below
            cur.endEditBlock()
            self._after_change()
        else:
            self.set_current_type(TAB_NEXT.get(etype, T.ACTION))

    # ---------------------------------------------------------------- helpers
    def _replace_block_text(self, text: str):
        cur = self.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.StartOfBlock)
        cur.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
        was = self._busy
        self._busy = True
        cur.insertText(text)
        self.setTextCursor(cur)
        self._busy = was

    def _insert_parens(self):
        cur = self.textCursor()
        was = self._busy
        self._busy = True
        cur.insertText("()")
        cur.movePosition(QTextCursor.MoveOperation.Left)
        self.setTextCursor(cur)                 # while still busy: no reactions mid-edit
        self._busy = was

    def accept_suggestion(self, row: int, advance: bool = True):
        if not (0 <= row < len(self._completion.items)):
            return
        s = self._completion.items[row]
        cur = self.textCursor()
        cur.beginEditBlock()
        self._replace_block_text(s.text)
        if advance and s.final:
            self._enter_after_text()
        cur.endEditBlock()
        self._after_change()
        self.setFocus()

    def _accept_ghost(self):
        if self._completion.ghost:
            self._replace_block_text(self._completion.ghost.text)
            self._after_change()

    # ================================================================ reactions
    def _on_text_changed(self):
        if self._busy:
            return
        cur = self.textCursor()
        block = cur.block()
        etype = block_type(block)
        new = live_retype(etype, block.text())
        if new:
            self.set_block_type(block, new)
            if new == T.PARENTHETICAL and block.text().strip() == "(":
                was = self._busy
                self._busy = True
                cur.insertText(")")
                cur.movePosition(QTextCursor.MoveOperation.Left)
                self.setTextCursor(cur)
                self._busy = was
        self._dismissed = False
        self._struct_timer.start()
        self._after_change()

    def _on_cursor_moved(self):
        if not self._busy:
            self._after_change()

    def _on_structure_timer(self):
        self.memory.set_document(self.element_pairs(), self.doc_key)
        self.structureChanged.emit()
        self.pageChanged.emit(self.current_page(), self.page_count())

    def _after_change(self):
        self._refresh_completion()
        self.elementChanged.emit(self.current_type())
        self.pageChanged.emit(self.current_page(), self.page_count())
        self._emit_hint()
        self.viewport().update()

    def _refresh_completion(self):
        cur = self.textCursor()
        block = cur.block()
        etype = block_type(block)
        self._ghost_rest = ""
        if (etype not in (T.SCENE_HEADING, T.CHARACTER, T.TRANSITION) or not cur.atBlockEnd()
                or self._dismissed or cur.hasSelection() or not self.isVisible()):
            self._completion = Completion([])
            self.popup.hide()
            return
        typed = block.text()
        self._completion = self.memory.complete(etype, typed, self.element_pairs(block))
        g = self._completion.ghost
        if g and g.text.startswith(typed.upper()):
            self._ghost_rest = g.text[len(typed):]
        items = self._completion.items
        if items and not (len(items) == 1 and g and items[0].text == g.text):
            r = self.cursorRect()
            self.popup.show_items(items, self.viewport().mapToGlobal(r.bottomLeft() + QPoint(-8, 6)))
        else:
            self.popup.hide()

    def _emit_hint(self):
        etype = self.current_type()
        block = self.textCursor().block()
        empty = block.text().strip() in ("", "()")
        if self._ghost_rest and self._completion.ghost:
            enter = "accept  ·  Esc dismiss"
        elif self.popup.isVisible() and self.popup.currentRow() >= 0:
            enter = "choose"
        elif empty:
            enter = EMPTY_ENTER.get(etype, T.ACTION)
        else:
            enter = ENTER_NEXT.get(etype, T.ACTION)
        tab = TAB_NEXT.get(etype, T.ACTION)
        self.hintChanged.emit(f"↵  {enter}      ⇥  {tab}")

    def focusOutEvent(self, e):
        try:
            self.popup.hide()
        except RuntimeError:            # popup already gone while the app shuts down
            pass
        super().focusOutEvent(e)

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self._after_change()

    def hideEvent(self, e):
        try:
            self.popup.hide()
        except RuntimeError:            # popup already gone while the app shuts down
            pass
        super().hideEvent(e)

    # ================================================================ painting
    def paintEvent(self, e):
        if self.document().pageSize().height() <= 0:   # Qt dropped the page size: restore it
            self._apply_page_size()
        super().paintEvent(e)
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        self._paint_focus(p)
        sx, sy = self.horizontalScrollBar().value(), self.verticalScrollBar().value()
        vw, vh = self.viewport().width(), self.viewport().height()
        _, ph = page_size_px(self.dpi)

        # page numbers, scene numbers, and the gaps between the sheets
        first_page, last_page = int(sy // ph), int((sy + vh) // ph)
        marks = scene_marks(self.document())
        revisions = revision_marks(self.document())
        for page in range(first_page, min(last_page, self.page_count() - 1) + 1):
            p.save()
            p.translate(-sx, 0)
            draw_page_furniture(p, self.document(), self.dpi, page, page * ph - sy, C.INK_SOFT,
                                marks, self._splits, C.INK, revisions=revisions,
                                star_colors=self.star_colors)
            p.restore()
        for page in range(max(1, first_page), last_page + 1):
            y = page * ph - sy
            p.fillRect(QRectF(0, y - SCREEN_GAP / 2, vw, SCREEN_GAP), QColor(C.GREIGE))
            p.setPen(QColor(C.LINE))
            p.drawLine(QPointF(0, y - SCREEN_GAP / 2), QPointF(vw, y - SCREEN_GAP / 2))
            p.drawLine(QPointF(0, y + SCREEN_GAP / 2), QPointF(vw, y + SCREEN_GAP / 2))

        # element label in the left margin, beside the current paragraph
        cur = self.textCursor()
        block = cur.block()
        r = self.cursorRect(QTextCursor(block))
        ui = QFont(self.font())
        ui.setFamily("Segoe UI")
        ui.setStyleHint(QFont.StyleHint.SansSerif)
        ui.setPixelSize(max(10, round(11 * self.zoom)))
        p.setFont(ui)
        p.setPen(QColor(C.CARAMEL))
        p.drawText(QRectF(0.15 * self.dpi - sx, r.top(), 0.8 * self.dpi, r.height()),
                   int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                   SHORT.get(block_type(block), ""))

        # SmartType ghost text
        if self._ghost_rest:
            f = QFont(self.page_font())
            f.setCapitalization(QFont.Capitalization.AllUppercase)
            p.setFont(f)
            col = QColor(C.CARAMEL)
            col.setAlpha(150)
            p.setPen(col)
            fm = QFontMetricsF(f)
            cr = self.cursorRect()
            base = cr.top() + (cr.height() - fm.height()) / 2 + fm.ascent()
            p.drawText(QPointF(cr.left() + 1, base), self._ghost_rest)
        for hook in self.paint_hooks:
            hook(p)
        p.end()
