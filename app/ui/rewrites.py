"""
Rewrites: ScriptNotes, revision mode (colours + asterisks, the industry convention) and
version history with compare and restore.

ScriptNotes live on the paragraph they're about (extra["notes"]), so they travel
with it when you cut, paste or move scenes. Revision marks live on the paragraph too
(extra["revision"] = revision level).
"""
from __future__ import annotations

import datetime as dt
import html
import uuid

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QPainter, QAction, QTextCursor
from PySide6.QtWidgets import (QDialog, QFormLayout, QPlainTextEdit, QComboBox, QDialogButtonBox,
                               QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                               QPushButton, QLabel, QDateEdit, QCheckBox, QTableWidget, QTableWidgetItem,
                               QHeaderView, QTextBrowser, QSplitter, QMessageBox, QAbstractItemView)

from ..core.history import compare, summary
from .editor_extras import REVISION_COLORS
from .pages import block_meta
from .theme import C

NOTE_COLORS = [("Honey", "#E4C85D"), ("Salmon", "#EAB5A3"), ("Sky", "#9DC3E6"), ("Mint", "#A8D5BA"),
               ("Lavender", "#C3B1E1")]


# ======================================================================== notes
class NoteDialog(QDialog):
    def __init__(self, note: dict | None, context: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ScriptNote")
        self.setMinimumWidth(440)
        form = QFormLayout(self)
        form.setContentsMargins(22, 22, 22, 18)
        form.setSpacing(10)
        ctx = QLabel(context[:140] + ("…" if len(context) > 140 else ""))
        ctx.setWordWrap(True)
        ctx.setObjectName("hint")
        form.addRow("About", ctx)
        self.text = QPlainTextEdit((note or {}).get("text", ""))
        self.text.setFixedHeight(120)
        self.text.setPlaceholderText("A thought, a question, a fix for the next draft…")
        self.color = QComboBox()
        from .planning import _dot
        for name, value in NOTE_COLORS:
            self.color.addItem(_dot(value), name, value)
        self.color.setCurrentIndex(max(0, self.color.findData((note or {}).get("color"))))
        form.addRow("Note", self.text)
        form.addRow("Colour", self.color)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        self.text.setFocus()


class NotesPanel(QWidget):
    """Navigator tab listing every ScriptNote; click one to jump to it."""

    def __init__(self, feature):
        super().__init__()
        self.f = feature
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.list = QListWidget(objectName="navList")
        self.list.setWordWrap(True)
        self.list.itemClicked.connect(self._jump)
        self.list.itemDoubleClicked.connect(lambda it: self.f.edit_note(*it.data(Qt.ItemDataRole.UserRole)))
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        add = QPushButton("New Note")
        add.clicked.connect(self.f.new_note)
        delete = QPushButton("Delete")
        delete.clicked.connect(self._delete)
        row.addWidget(add)
        row.addWidget(delete)
        lay.addLayout(row)

    def refresh(self):
        self.list.clear()
        from .planning import _dot
        for number, note, text in self.f.all_notes():
            it = QListWidgetItem(_dot(note.get("color")), f"{note.get('text', '')}\n— {text[:60]}")
            it.setData(Qt.ItemDataRole.UserRole, (number, note["id"]))
            self.list.addItem(it)
        if not self.list.count():
            it = QListWidgetItem("No notes yet. Right-click a paragraph → Add ScriptNote (Ctrl+Shift+N).")
            it.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(it)

    def _jump(self, it):
        data = it.data(Qt.ItemDataRole.UserRole)
        if data:
            self.f.window.show_view("script")
            self.f.editor.goto_block(data[0])

    def _delete(self):
        it = self.list.currentItem()
        if it and it.data(Qt.ItemDataRole.UserRole):
            self.f.delete_note(*it.data(Qt.ItemDataRole.UserRole))


# ======================================================================== revisions
class RevisionDialog(QDialog):
    """Which revision you're writing (Blue, Pink...), its date, and how it prints."""

    def __init__(self, info: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Revisions")
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        form.setContentsMargins(22, 22, 22, 18)
        form.setSpacing(10)
        self.level = QComboBox()
        from .planning import _dot
        for i, (name, color) in enumerate(REVISION_COLORS[1:], 1):
            self.level.addItem(_dot(color), f"{name} Revision", i)
        self.level.setCurrentIndex(max(0, self.level.findData(info.get("level", 1))))
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd MMM yyyy")
        d = info.get("date")
        self.date.setDate(dt.date.fromisoformat(d) if d else dt.date.today())
        self.header = QCheckBox("Print the revision name and date at the top of every page")
        self.header.setChecked(info.get("header", True))
        self.mode = QCheckBox("Revision mode: mark every paragraph I change")
        self.mode.setChecked(info.get("mode", False))
        form.addRow("Revision", self.level)
        form.addRow("Date", self.date)
        form.addRow("", self.mode)
        form.addRow("", self.header)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self) -> dict:
        return {"level": self.level.currentData(), "date": self.date.date().toPython().isoformat(),
                "header": self.header.isChecked(), "mode": self.mode.isChecked()}


# ======================================================================== history
class HistoryDialog(QDialog):
    """Every save is kept. Compare any version with the script on screen, or bring it back."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setWindowTitle("Version History")
        self.resize(980, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        split = QSplitter()
        lay.addWidget(split, 1)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Saved", "Version", "Pages", "Words"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.show_diff)
        split.addWidget(self.table)
        self.diff = QTextBrowser()
        split.addWidget(self.diff)
        split.setSizes([400, 560])
        row = QHBoxLayout()
        self.summary = QLabel(objectName="hint")
        row.addWidget(self.summary, 1)
        save = QPushButton("Save Version…")
        save.clicked.connect(lambda: (window.save_version(), self.fill()))
        restore = QPushButton("Restore This Version", objectName="primary")
        restore.clicked.connect(self.restore)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        for b in (save, restore, close):
            row.addWidget(b)
        lay.addLayout(row)
        self.fill()

    def fill(self):
        w = self.window
        self.versions = w.history.versions(str(w.path) if w.path else None)
        self.table.setRowCount(0)
        for v in self.versions:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c, text in enumerate((v.when, v.label or ("Saved" if v.auto else "Version"),
                                      str(v.pages or ""), str(v.words))):
                it = QTableWidgetItem(text)
                if not v.auto and c == 1:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                self.table.setItem(r, c, it)
        if self.versions:
            self.table.selectRow(0)
        else:
            self.diff.setHtml("<p style='color:gray'>No saved versions yet. Every time you save, "
                              "a copy is kept here.</p>")

    def current(self):
        r = self.table.currentRow()
        return self.versions[r] if 0 <= r < len(self.versions) else None

    def show_diff(self):
        v = self.current()
        if v is None:
            return
        old = self.window.history.load(v)
        new = self.window.editor.to_script()
        changes = compare(old, new)
        s = summary(changes)
        self.summary.setText(f"Since this version: {s['added']} paragraph(s) added or changed, "
                             f"{s['removed']} removed or changed.")
        rows = []
        for ch in changes:
            if ch.kind == "same":
                if len(ch.old) > 4:
                    rows.append(f"<div style='color:{C.INK_SOFT}'>… {len(ch.old)} unchanged …</div>")
                else:
                    rows += [f"<div style='color:{C.INK_SOFT}'>{html.escape(x)}</div>" for x in ch.old]
                continue
            rows += [f"<div style='background:#F6D3C8;color:#3A322B'>− {html.escape(x)}</div>" for x in ch.old]
            rows += [f"<div style='background:#D4EBDD;color:#3A322B'>+ {html.escape(x)}</div>" for x in ch.new]
        self.diff.setHtml("<div style='font-family:Courier Prime,monospace;font-size:10pt'>"
                          + "".join(rows) + "</div>")

    def restore(self):
        v = self.current()
        if v is None:
            return
        if QMessageBox.question(self, "Restore", "Replace the script on screen with this version? "
                                "(The current script is saved as a version first, so nothing is lost.)") \
                != QMessageBox.StandardButton.Yes:
            return
        w = self.window
        w.history.snapshot(w.editor.to_script(), str(w.path) if w.path else None,
                           label="Before restoring", auto=False, pages=w.editor.page_count())
        w.editor.load_script(w.history.load(v), w.editor.doc_key)
        w.editor.document().setModified(True)
        w._after_open()
        self.accept()


# ======================================================================== feature
class Rewrites:
    def __init__(self, window):
        self.window = window
        self.editor = window.editor
        self.panel = NotesPanel(self)
        window.navigator.add_tab("Notes", self.panel)
        self.editor.context_hooks.append(self._menu)
        self.editor.paint_hooks.append(self._paint_notes)
        self.editor.structureChanged.connect(self.panel.refresh)
        self.editor.projectChanged.connect(lambda _p: self.panel.refresh())

        a = window._a
        self.act_note = a("ScriptNote…", self.new_note, "Ctrl+Shift+N", "note")
        self.act_mode = a("Revision Mode", self.toggle_mode, "Ctrl+Shift+M", "revision", checkable=True)
        self.act_set = a("Revisions…", self.edit_revisions, None)
        self.act_clear = a("Clear Revision Marks…", self.clear_marks, None)
        ins = window.menus["insert"]
        ins.addSeparator()
        ins.addAction(self.act_note)
        tools = window.menus["tools"]
        rm = tools.addMenu("Revisions")
        for act in (self.act_mode, self.act_set, self.act_clear):
            rm.addAction(act)
        tools.addSeparator()
        self.pill = QLabel(objectName="revPill")
        self.pill.hide()
        window.statusBar().insertWidget(1, self.pill)
        self.script_loaded()

    # ---------------------------------------------------------------- notes
    def all_notes(self):
        out = []
        block = self.editor.document().firstBlock()
        while block.isValid():
            for note in block_meta(block).get("extra", {}).get("notes", []):
                out.append((block.blockNumber(), note, block.text()))
            block = block.next()
        return out

    def new_note(self, block_number: int | None = None):
        ed = self.editor
        if block_number is None or block_number is False:
            block_number = ed.textCursor().blockNumber()
        block = ed.document().findBlockByNumber(block_number)
        dlg = NoteDialog(None, block.text() or "(empty paragraph)", self.window)
        if dlg.exec() and dlg.text.toPlainText().strip():
            notes = list(ed.block_extra(block_number).get("notes", []))
            notes.append({"id": uuid.uuid4().hex[:8], "text": dlg.text.toPlainText().strip(),
                          "color": dlg.color.currentData(), "date": dt.date.today().isoformat()})
            ed.set_block_extra(block_number, "notes", notes)
            self.panel.refresh()
            self.window.navigator.group.button(3).click()

    def edit_note(self, block_number: int, note_id: str):
        ed = self.editor
        notes = [dict(n) for n in ed.block_extra(block_number).get("notes", [])]
        note = next((n for n in notes if n["id"] == note_id), None)
        if note is None:
            return
        dlg = NoteDialog(note, ed.document().findBlockByNumber(block_number).text(), self.window)
        if dlg.exec():
            note.update(text=dlg.text.toPlainText().strip(), color=dlg.color.currentData())
            ed.set_block_extra(block_number, "notes", [n for n in notes if n.get("text")])
            self.panel.refresh()

    def delete_note(self, block_number: int, note_id: str):
        ed = self.editor
        notes = [n for n in ed.block_extra(block_number).get("notes", []) if n["id"] != note_id]
        ed.set_block_extra(block_number, "notes", notes)
        self.panel.refresh()

    def _paint_notes(self, p: QPainter):
        """A small coloured tab in the left margin beside every paragraph with notes."""
        ed = self.editor
        lay = ed.document().documentLayout()
        sy = ed.verticalScrollBar().value()
        sx = ed.horizontalScrollBar().value()
        vh = ed.viewport().height()
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        block = ed.document().firstBlock()
        while block.isValid():
            notes = block_meta(block).get("extra", {}).get("notes")
            if notes:
                r = lay.blockBoundingRect(block)
                bl = block.layout()
                y = r.top() + (bl.lineAt(0).y() if bl and bl.lineCount() else 0) - sy
                if -20 < y < vh + 20:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor(notes[-1].get("color") or C.HONEY))
                    x = 1.08 * ed.dpi - sx
                    p.drawRoundedRect(QRectF(x, y + 1, 0.13 * ed.dpi, ed.dpi / 6 - 2), 3, 3)
                    if len(notes) > 1:
                        p.setPen(QColor(C.INK))
                        f = p.font()
                        f.setPixelSize(max(9, int(ed.dpi / 10)))
                        p.setFont(f)
                        p.drawText(QPointF(x + 0.03 * ed.dpi, y + ed.dpi / 6 - 4), str(len(notes)))
            block = block.next()
        p.restore()

    def note_at(self, cur: QTextCursor):
        return block_meta(cur.block()).get("extra", {}).get("notes", [])

    def _menu(self, cur: QTextCursor):
        acts = []
        n = cur.blockNumber()
        add = QAction("Add ScriptNote…")
        add.triggered.connect(lambda: self.new_note(n))
        acts.append(add)
        for note in self.note_at(cur):
            a = QAction(f"Edit Note: {note['text'][:30]}…" if len(note["text"]) > 30 else
                        f"Edit Note: {note['text']}")
            a.triggered.connect(lambda _=False, nid=note["id"]: self.edit_note(n, nid))
            acts.append(a)
        return acts

    # ---------------------------------------------------------------- revisions
    def info(self) -> dict:
        return self.editor.project.get("revisions", {})

    def toggle_mode(self, on: bool):
        info = dict(self.info())
        info.setdefault("level", 1)
        info["mode"] = on
        self.editor.project["revisions"] = info
        self.editor.touch_project("revisions")
        self.apply()

    def edit_revisions(self):
        dlg = RevisionDialog(self.info(), self.window)
        if dlg.exec():
            self.editor.project["revisions"] = dlg.values()
            self.editor.touch_project("revisions")
            self.apply()

    def clear_marks(self):
        if QMessageBox.question(self.window, "Clear Revision Marks",
                                "Remove every revision asterisk from the script? "
                                "(Do this when you start a fresh set of revisions.)") \
                != QMessageBox.StandardButton.Yes:
            return
        ed = self.editor
        cur = QTextCursor(ed.document())
        cur.beginEditBlock()
        block = ed.document().firstBlock()
        while block.isValid():
            if block_meta(block).get("extra", {}).get("revision"):
                ed.set_block_extra(block.blockNumber(), "revision", None)
            block = block.next()
        cur.endEditBlock()
        ed.viewport().update()

    def apply(self):
        info = self.info()
        ed = self.editor
        ed.revision_mode = bool(info.get("mode"))
        ed.revision_level = int(info.get("level", 1))
        ed.star_colors = {i: c for i, (_n, c) in enumerate(REVISION_COLORS)}
        self.act_mode.blockSignals(True)
        self.act_mode.setChecked(ed.revision_mode)
        self.act_mode.blockSignals(False)
        name, color = REVISION_COLORS[ed.revision_level % len(REVISION_COLORS)]
        self.pill.setText(f"{name} Revision")
        self.pill.setStyleSheet(f"background:{color};color:#3A322B;border-radius:9px;padding:2px 10px;"
                                f"font-weight:600")
        self.pill.setVisible(ed.revision_mode)
        ed.viewport().update()

    def page_extras(self) -> dict:
        info = self.info()
        has_marks = any(block_meta(b).get("extra", {}).get("revision") for b in _blocks(self.editor))
        if info and info.get("header", True) and (has_marks or info.get("mode")):
            name = REVISION_COLORS[int(info.get("level", 1)) % len(REVISION_COLORS)][0]
            d = info.get("date") or dt.date.today().isoformat()
            return {"header": f"{name} Rev. ({dt.date.fromisoformat(d).strftime('%m/%d/%Y')})"}
        return {}

    def script_loaded(self):
        self.apply()
        self.panel.refresh()


def _blocks(editor):
    b = editor.document().firstBlock()
    while b.isValid():
        yield b
        b = b.next()

