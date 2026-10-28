"""
Production: breakdown tagging and sheets, shot lists, a stripboard, locked scene
numbers with A-numbers, omitted scenes and page templates (TV, multi-cam, stage play).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QMarginsF
from PySide6.QtGui import (QAction, QActionGroup, QColor, QTextCursor, QTextDocument, QPageLayout,
                           QPageSize, QPdfWriter)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                               QTabWidget, QComboBox, QLineEdit, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QTableWidget, QTableWidgetItem, QHeaderView, QLabel,
                               QSplitter, QFileDialog, QAbstractItemView)

from ..core import breakdown as bd
from ..core.layout import TEMPLATES
from ..core.smart import split_heading
from .planning import scene_infos
from .theme import C

STRIP_COLORS = {("INT", "DAY"): "#FFFFFF", ("EXT", "DAY"): "#FFF3B0", ("INT", "NIGHT"): "#BFD7F5",
                ("EXT", "NIGHT"): "#BFE3C6"}


def scene_breakdowns(editor) -> list[bd.SceneBreakdown]:
    from ..core import reports
    out = []
    for info in scene_infos(editor):
        intro, loc, time = split_heading(info.heading)
        extra = editor.block_extra(info.block)
        out.append(bd.SceneBreakdown(info.number, info.heading, intro.rstrip("."), loc, time,
                                     reports.eighths(info.length), info.page, info.synopsis,
                                     info.characters, dict(extra.get("breakdown", {})),
                                     list(extra.get("shots", []))))
    return out


class ProductionView(QWidget):
    def __init__(self, feature):
        super().__init__()
        self.f = feature
        self.window = feature.window
        self.editor = feature.editor
        self.infos = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 10)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Production", objectName="viewTitle"))
        bar.addStretch(1)
        for text, slot in (("Breakdown Sheets (PDF)…", self.export_sheets),
                           ("Breakdown (CSV)…", lambda: self.export_csv("breakdown")),
                           ("Shot List (CSV)…", lambda: self.export_csv("shots"))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            bar.addWidget(b)
        lay.addLayout(bar)
        split = QSplitter()
        lay.addWidget(split, 1)
        self.scenes = QListWidget(objectName="navList")
        self.scenes.currentRowChanged.connect(self.show_scene)
        split.addWidget(self.scenes)
        self.tabs = QTabWidget()
        split.addWidget(self.tabs)
        split.setSizes([280, 760])

        # breakdown tab
        page = QWidget()
        v = QVBoxLayout(page)
        self.title = QLabel(objectName="profileName")
        self.cast = QLabel(wordWrap=True)
        v.addWidget(self.title)
        v.addWidget(self.cast)
        row = QHBoxLayout()
        self.cat = QComboBox()
        for name, color in bd.CATEGORIES:
            if name != "Cast":
                from .planning import _dot
                self.cat.addItem(_dot(color), name)
        self.item = QLineEdit(placeholderText="Add an element, e.g. Telescope")
        self.item.returnPressed.connect(self.add_item)
        add = QPushButton("Add")
        add.clicked.connect(self.add_item)
        row.addWidget(self.cat)
        row.addWidget(self.item, 1)
        row.addWidget(add)
        v.addLayout(row)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        v.addWidget(self.tree, 1)
        rm = QPushButton("Remove Selected")
        rm.clicked.connect(self.remove_item)
        hint = QLabel("Tip: in the script, select words and right-click → Tag as… to add them here.",
                      objectName="hint")
        r2 = QHBoxLayout()
        r2.addWidget(hint, 1)
        r2.addWidget(rm)
        v.addLayout(r2)
        self.tabs.addTab(page, "Breakdown")

        # shot list tab
        page = QWidget()
        v = QVBoxLayout(page)
        self.shots = QTableWidget(0, len(bd.SHOT_FIELDS))
        self.shots.setHorizontalHeaderLabels([lbl for _k, lbl in bd.SHOT_FIELDS])
        self.shots.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.shots.verticalHeader().hide()
        self.shots.itemChanged.connect(lambda _it: self._save_shots())
        v.addWidget(self.shots, 1)
        row = QHBoxLayout()
        for text, slot in (("Add Shot", self.add_shot), ("Remove", self.remove_shot),
                           ("Move Up", lambda: self.move_shot(-1)), ("Move Down", lambda: self.move_shot(1))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        self.tabs.addTab(page, "Shot List")

        # stripboard tab
        self.strips = QTableWidget(0, 6)
        self.strips.setHorizontalHeaderLabels(["Scene", "I/E", "Location", "Time", "Pages", "Cast"])
        self.strips.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.strips.verticalHeader().hide()
        self.strips.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabs.addTab(self.strips, "Stripboard")
        self._filling = False

    def enter_view(self):
        self.refresh()

    def refresh(self):
        row = max(0, self.scenes.currentRow())
        self.data = scene_breakdowns(self.editor)
        self.infos = scene_infos(self.editor)
        self.scenes.blockSignals(True)
        self.scenes.clear()
        for s in self.data:
            n = sum(len(v) for v in s.items.values())
            it = QListWidgetItem(f"{s.number}  {s.heading}\n{s.length} pg · {n} tagged · {len(s.shots)} shots")
            self.scenes.addItem(it)
        self.scenes.blockSignals(False)
        if self.data:
            self.scenes.setCurrentRow(min(row, len(self.data) - 1))
            self.show_scene(self.scenes.currentRow())
        self._fill_strips()

    def current(self):
        r = self.scenes.currentRow()
        return (self.data[r], self.infos[r]) if 0 <= r < len(self.data) else (None, None)

    def show_scene(self, row: int):
        s, _info = self.current()
        if s is None:
            return
        self.title.setText(f"Scene {s.number} — {s.heading}")
        self.cast.setText("Cast (who speaks): " + (", ".join(s.cast) or "—"))
        self.tree.clear()
        for name, color in bd.CATEGORIES:
            vals = s.items.get(name, [])
            if vals:
                top = QTreeWidgetItem([f"{name} ({len(vals)})"])
                top.setForeground(0, QColor(C.INK))
                top.setBackground(0, QColor(color))
                for v in vals:
                    ch = QTreeWidgetItem([v])
                    ch.setData(0, Qt.ItemDataRole.UserRole, (name, v))
                    top.addChild(ch)
                self.tree.addTopLevelItem(top)
                top.setExpanded(True)
        self._filling = True
        self.shots.setRowCount(0)
        for shot in s.shots:
            self._shot_row(shot)
        self._filling = False

    def add_item(self):
        s, info = self.current()
        if s is None or not self.item.text().strip():
            return
        items = bd.tag(s.items, self.cat.currentText(), self.item.text())
        self.editor.set_block_extra(info.block, "breakdown", items)
        self.item.clear()
        self.refresh()

    def remove_item(self):
        s, info = self.current()
        it = self.tree.currentItem()
        if s is None or it is None or not it.data(0, Qt.ItemDataRole.UserRole):
            return
        cat, text = it.data(0, Qt.ItemDataRole.UserRole)
        self.editor.set_block_extra(info.block, "breakdown", bd.untag(s.items, cat, text))
        self.refresh()

    def _shot_row(self, shot: dict):
        r = self.shots.rowCount()
        self.shots.insertRow(r)
        for c, (key, _l) in enumerate(bd.SHOT_FIELDS):
            choices = {"size": bd.SHOT_SIZES, "angle": bd.SHOT_ANGLES, "move": bd.SHOT_MOVES}.get(key)
            if choices:
                box = QComboBox()
                box.setEditable(True)
                box.addItems([""] + choices)
                box.setCurrentText(shot.get(key, ""))
                box.currentTextChanged.connect(lambda _t: self._save_shots())
                self.shots.setCellWidget(r, c, box)
            else:
                self.shots.setItem(r, c, QTableWidgetItem(str(shot.get(key, ""))))

    def _read_shots(self) -> list[dict]:
        out = []
        for r in range(self.shots.rowCount()):
            shot = {}
            for c, (key, _l) in enumerate(bd.SHOT_FIELDS):
                w = self.shots.cellWidget(r, c)
                v = w.currentText() if w is not None else (self.shots.item(r, c).text()
                                                           if self.shots.item(r, c) else "")
                if v:
                    shot[key] = v
            out.append(shot)
        return out

    def _save_shots(self):
        if self._filling:
            return
        s, info = self.current()
        if s is None:
            return
        shots = self._read_shots()
        s.shots = shots
        self.editor.set_block_extra(info.block, "shots", shots)

    def add_shot(self):
        s, _ = self.current()
        if s is None:
            return
        self._filling = True
        self._shot_row({"shot": str(self.shots.rowCount() + 1), "size": "WS", "angle": "Eye level",
                        "move": "Static"})
        self._filling = False
        self._save_shots()

    def remove_shot(self):
        r = self.shots.currentRow()
        if r >= 0:
            self.shots.removeRow(r)
            self._save_shots()

    def move_shot(self, d: int):
        r = self.shots.currentRow()
        shots = self._read_shots()
        if 0 <= r < len(shots) and 0 <= r + d < len(shots):
            shots[r], shots[r + d] = shots[r + d], shots[r]
            s, info = self.current()
            self.editor.set_block_extra(info.block, "shots", shots)
            s.shots = shots
            self.show_scene(self.scenes.currentRow())
            self.shots.selectRow(r + d)

    def _fill_strips(self):
        self.strips.setRowCount(0)
        for row in bd.stripboard(self.data):
            r = self.strips.rowCount()
            self.strips.insertRow(r)
            color = STRIP_COLORS.get((row[1].replace(".", "")[:3].upper(),
                                      "NIGHT" if "NIGHT" in row[3].upper() else "DAY"), "#FFFFFF")
            for c, text in enumerate(row):
                it = QTableWidgetItem(text)
                it.setBackground(QColor(color))
                it.setForeground(QColor("#3A322B"))
                self.strips.setItem(r, c, it)

    def export_csv(self, kind: str):
        folder = Path(self.window.settings.value("lastDir", "") or Path.home())
        name = f"{self.window._script_title()} - {'Breakdown' if kind == 'breakdown' else 'Shot List'}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", str(folder / name), "CSV (*.csv)")
        if path:
            data = scene_breakdowns(self.editor)
            text = bd.breakdown_csv(data) if kind == "breakdown" else bd.shots_csv(data)
            Path(path).write_text(text, encoding="utf-8-sig")
            self.window.statusBar().showMessage(f"Exported {Path(path).name}", 4000)

    def export_sheets(self):
        folder = Path(self.window.settings.value("lastDir", "") or Path.home())
        path, _ = QFileDialog.getSaveFileName(self, "Breakdown Sheets",
                                              str(folder / f"{self.window._script_title()} - Breakdown.pdf"),
                                              "PDF (*.pdf)")
        if path:
            write_html_pdf(bd.sheets_html(scene_breakdowns(self.editor), self.window._script_title()), path)
            self.window.statusBar().showMessage(f"Exported {Path(path).name}", 4000)


def write_html_pdf(html_text: str, path: str):
    doc = QTextDocument()
    doc.setHtml(html_text)
    writer = QPdfWriter(path)
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.PageSizeId.Letter), QPageLayout.Orientation.Portrait,
                                     QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter))
    writer.setCreator("Cut To:")
    doc.print_(writer)


class Production:
    def __init__(self, window):
        self.window = window
        self.editor = window.editor
        self.view = ProductionView(self)
        window.add_view("production", "Production", "production", self.view)
        self.editor.context_hooks.append(self._menu)
        self.show_tags = False
        self._timer = QTimer(window, singleShot=True, interval=500)
        self._timer.timeout.connect(self.apply_tags)
        self.editor.structureChanged.connect(lambda: self.show_tags and self._timer.start())
        self.editor.projectChanged.connect(lambda _p: self.show_tags and self._timer.start())

        a = window._a
        self.act_lock = a("Lock Scene Numbers", self.toggle_lock, None, "lock", checkable=True)
        self.act_omit = a("Omit Scene", self.omit_scene, None)
        self.act_tags = a("Show Breakdown Tags", self.toggle_tags, None, "tag", checkable=True)
        pr = window.menus["production"]
        first = pr.actions()[2] if len(pr.actions()) > 2 else None
        pr.insertAction(first, self.act_lock)
        pr.insertAction(first, self.act_omit)
        pr.addSeparator()
        pr.addAction(self.act_tags)
        pr.addAction("Breakdown & Shot List", lambda: window.show_view("production"))
        # templates
        self.tgroup = QActionGroup(window)
        tm = window.menus["format"].addMenu("Page Template")
        self.template_actions = {}
        for name in TEMPLATES:
            act = QAction(name, window, checkable=True)
            act.triggered.connect(lambda _=False, n=name: self.editor.set_template(n))
            self.tgroup.addAction(act)
            tm.addAction(act)
            self.template_actions[name] = act
        nm = QAction("New From Template…", window)
        f = window.menus["file"]
        sub = f.addMenu("New From Template")
        f.insertMenu(f.actions()[1], sub)
        for name in TEMPLATES:
            sub.addAction(name, lambda n=name: window.new_file(n))
        del nm
        self.script_loaded()

    def script_loaded(self):
        p = self.editor.project
        self.act_lock.setChecked(bool(p.get("locked")))
        self.template_actions.get(p.get("template", "Screenplay"), self.template_actions["Screenplay"]).setChecked(True)
        if self.show_tags:
            self.apply_tags()

    def toggle_lock(self, on: bool):
        ed = self.editor
        if on:
            ed.number_scenes(locked=bool(ed.project.get("locked")))
            ed.project["locked"] = True
            self.window.statusBar().showMessage("Scene numbers locked: new scenes get A-numbers (12A, 12B…)", 5000)
        else:
            ed.project.pop("locked", None)
        ed.touch_project("locked")

    def omit_scene(self):
        """Production drafts keep a numbered scene's slot: its heading becomes OMITTED."""
        ed = self.editor
        n = ed.textCursor().blockNumber()
        rng = next(((a, b) for a, b in ed.scene_ranges() if a <= n <= b), None)
        if rng is None:
            return
        first, last = rng
        cur = QTextCursor(ed.document())
        cur.beginEditBlock()
        ed._busy = True
        try:
            if last > first:
                ed._delete_blocks(cur, first + 1, last)
            block = ed.document().findBlockByNumber(first)
            cur.setPosition(block.position())
            cur.setPosition(block.position() + block.length() - 1, QTextCursor.MoveMode.KeepAnchor)
            cur.insertText("OMITTED")
        finally:
            ed._busy = False
            cur.endEditBlock()
        ed._struct_timer.start()
        ed.structureChanged.emit()

    def toggle_tags(self, on: bool):
        self.show_tags = on
        self.apply_tags() if on else self.editor.set_layer("breakdown", [])

    def apply_tags(self):
        """Colour every tagged element where it appears in its scene."""
        import re
        ed = self.editor
        sels = []
        doc = ed.document()
        for first, last in ed.scene_ranges():
            items = ed.block_extra(first).get("breakdown", {})
            if not items:
                continue
            for cat, words in items.items():
                color = QColor(bd.CATEGORY_COLOR.get(cat, C.HONEY))
                color.setAlpha(150)
                for w in words:
                    rx = re.compile(rf"(?<![\w']){re.escape(w)}(?![\w'])", re.I)
                    for n in range(first, last + 1):
                        b = doc.findBlockByNumber(n)
                        for m in rx.finditer(b.text()):
                            c = QTextCursor(doc)
                            c.setPosition(b.position() + m.start())
                            c.setPosition(b.position() + m.end(), QTextCursor.MoveMode.KeepAnchor)
                            sels.append(ed.make_selection(c, background=color.name(QColor.NameFormat.HexArgb)))
        ed.set_layer("breakdown", sels)

    def _menu(self, cur: QTextCursor):
        sel = self.editor.textCursor()
        text = sel.selectedText().strip() if sel.hasSelection() else ""
        if not text or len(text) > 60 or chr(0x2029) in text:
            return []
        ed = self.editor
        n = sel.block().blockNumber()
        rng = next(((a, b) for a, b in ed.scene_ranges() if a <= n <= b), None)
        if rng is None:
            return []
        acts = []
        parent = QAction(f"Tag “{text[:24]}” as")
        from PySide6.QtWidgets import QMenu
        menu = QMenu()
        from .planning import _dot
        for name, color in bd.CATEGORIES:
            if name == "Cast":
                continue
            a = menu.addAction(_dot(color), name)
            a.triggered.connect(lambda _=False, c=name: self._tag(rng[0], c, text))
        parent.setMenu(menu)
        parent._menu = menu                       # keep the submenu alive
        acts.append(parent)
        return acts

    def _tag(self, heading_block: int, cat: str, text: str):
        items = bd.tag(self.editor.block_extra(heading_block).get("breakdown", {}), cat, text)
        self.editor.set_block_extra(heading_block, "breakdown", items)
        if not self.show_tags:
            self.act_tags.setChecked(True)
            self.toggle_tags(True)
        else:
            self.apply_tags()
        self.window.statusBar().showMessage(f"Tagged “{text}” as {cat}", 3000)

