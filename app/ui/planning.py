"""
Story planning: Index Cards, Beat Board, Characters, storylines, structure points
and the scene ribbon above the page.

Scene data (synopsis, colour, storylines) lives on each scene heading, so it moves,
copies and undoes with the scene. Board data (beats, flow lines), storylines,
structure points and character profiles live in the script's project data.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, QTimer, Signal, QLineF
from PySide6.QtGui import (QColor, QPainter, QPen, QFont, QFontMetricsF, QPainterPath, QBrush,
                           QPolygonF, QAction)
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                               QStyledItemDelegate, QAbstractItemView, QLabel, QPushButton,
                               QComboBox, QDialog, QFormLayout, QLineEdit, QPlainTextEdit,
                               QDialogButtonBox, QGraphicsView, QGraphicsScene, QGraphicsObject,
                               QGraphicsPathItem, QMenu, QToolButton, QSplitter, QFrame,
                               QTableWidget, QTableWidgetItem, QHeaderView, QCheckBox, QSlider,
                               QColorDialog, QScrollArea, QGridLayout, QSpinBox, QListView, QStyle)

from ..core import reports
from ..core.ir import T
from .theme import C

CARD_COLORS = [("None", None), ("Honey", "#E4C85D"), ("Salmon", "#EAB5A3"), ("Sky", "#9DC3E6"),
               ("Mint", "#A8D5BA"), ("Lavender", "#C3B1E1"), ("Caramel", "#C88E5C"),
               ("Rose", "#E88EA0"), ("Slate", "#9AA5B1")]
STRUCTURE_DEFAULTS = [("Inciting Incident", 0.10), ("Act One Break", 0.25), ("Midpoint", 0.50),
                      ("All Is Lost", 0.75), ("Act Two Break", 0.80), ("Climax", 0.90)]
PROFILE_FIELDS = [("description", "Description"), ("age", "Age"), ("want", "Wants (goal)"),
                  ("need", "Needs"), ("flaw", "Flaw"), ("arc", "Arc"), ("backstory", "Backstory"),
                  ("voice", "Voice / how they speak"), ("actor", "Cast / actor"), ("notes", "Notes")]


# ======================================================================== scene model
@dataclass
class SceneInfo:
    index: int
    block: int
    heading: str
    number: str
    page: int
    length: float
    synopsis: str = ""
    color: str | None = None
    storylines: list = field(default_factory=list)
    characters: list = field(default_factory=list)
    preview: str = ""
    words: int = 0
    dialogue_words: int = 0


def scene_infos(editor) -> list[SceneInfo]:
    scenes = editor.scenes()
    lengths = editor.scene_lengths()
    pairs = editor.element_pairs()
    rep = reports.build(pairs, [s[2] for s in scenes])
    ranges = editor.scene_ranges()
    out = []
    for i, ((block, heading, number, page), length, row, (first, last)) in \
            enumerate(zip(scenes, lengths, rep.scenes, ranges)):
        extra = editor.block_extra(block)
        body = pairs[first + 1:last + 1]
        preview = " ".join(t for ty, t in body if ty == T.ACTION)[:260]
        words = sum(len(t.split()) for _ty, t in body)
        dwords = sum(len(t.split()) for ty, t in body if ty == T.DIALOGUE)
        out.append(SceneInfo(i, block, heading, number or str(i + 1), page, length,
                             extra.get("synopsis", ""), extra.get("color"),
                             list(extra.get("storylines", [])), list(row.characters), preview,
                             words, dwords))
    return out


def storylines(editor) -> list[dict]:
    return editor.project.setdefault("storylines", [])


# ======================================================================== card dialog
class CardDialog(QDialog):
    """Edit a scene card: synopsis, colour and storylines."""

    def __init__(self, info: SceneInfo, lines: list[dict], parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Scene {info.number}")
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        form.setContentsMargins(22, 22, 22, 18)
        form.setSpacing(10)
        head = QLabel(info.heading)
        head.setStyleSheet("font-weight:600")
        form.addRow("Scene", head)
        self.synopsis = QPlainTextEdit(info.synopsis)
        self.synopsis.setPlaceholderText("What happens in this scene, in a line or two")
        self.synopsis.setFixedHeight(96)
        form.addRow("Synopsis", self.synopsis)
        self.color = QComboBox()
        for name, value in CARD_COLORS:
            self.color.addItem(_dot(value), name, value)
        self.color.setCurrentIndex(max(0, self.color.findData(info.color)))
        form.addRow("Colour", self.color)
        self.checks = []
        if lines:
            box = QWidget()
            v = QVBoxLayout(box)
            v.setContentsMargins(0, 0, 0, 0)
            for sl in lines:
                cb = QCheckBox(sl["name"])
                cb.setIcon(_dot(sl.get("color")))
                cb.setChecked(sl["id"] in info.storylines)
                v.addWidget(cb)
                self.checks.append((sl["id"], cb))
            form.addRow("Storylines", box)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self) -> tuple[str, str | None, list]:
        return (self.synopsis.toPlainText().strip(), self.color.currentData(),
                [sid for sid, cb in self.checks if cb.isChecked()])


def _dot(color):
    from PySide6.QtGui import QPixmap, QIcon
    px = QPixmap(28, 28)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor(C.LINE))
    p.setBrush(QColor(color) if color else Qt.BrushStyle.NoBrush)
    p.drawEllipse(5, 5, 18, 18)
    p.end()
    return QIcon(px)


# ======================================================================== index cards
INFO = Qt.ItemDataRole.UserRole + 1


class CardDelegate(QStyledItemDelegate):
    def __init__(self, view):
        super().__init__(view)
        self.view = view

    def sizeHint(self, opt, index):                # noqa: N802
        return self.view.card_size

    def paint(self, p: QPainter, opt, index):
        info: SceneInfo = index.data(INFO)
        if info is None:
            return
        r = QRectF(opt.rect).adjusted(8, 8, -8, -8)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        shadow = QColor(0, 0, 0, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(shadow)
        p.drawRoundedRect(r.translated(0, 2), 8, 8)
        p.setBrush(QColor(C.PAPER))
        p.setPen(QPen(QColor(C.MUSTARD if selected else C.LINE), 2 if selected else 1))
        p.drawRoundedRect(r, 8, 8)
        stripe = info.color or (self.view.storyline_color(info) or None)
        if stripe:
            card = QPainterPath()
            card.addRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)
            p.save()
            p.setClipPath(card)
            p.fillRect(QRectF(r.left(), r.top(), r.width(), 6), QColor(stripe))
            p.restore()
        x, y, w = r.left() + 12, r.top() + 18, r.width() - 24
        f = QFont(self.view.font())
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 0.95)
        p.setFont(f)
        p.setPen(QColor(C.CARAMEL))
        p.drawText(QRectF(x, y, w, 18), Qt.AlignmentFlag.AlignLeft, info.number)
        p.setPen(QColor(C.INK_SOFT))
        fs = QFont(self.view.font())
        fs.setPointSizeF(fs.pointSizeF() * 0.85)
        p.setFont(fs)
        p.drawText(QRectF(x, y, w, 18), Qt.AlignmentFlag.AlignRight,
                   f"p.{info.page} · {reports.eighths(info.length)}")
        p.setFont(f)
        p.setPen(QColor(C.INK))
        fm = QFontMetricsF(f)
        heading = fm.elidedText(info.heading, Qt.TextElideMode.ElideRight, w)
        p.drawText(QRectF(x, y + 20, w, 20), Qt.AlignmentFlag.AlignLeft, heading)
        body = info.synopsis or info.preview
        fb = QFont(self.view.font())
        fb.setItalic(not info.synopsis)
        p.setFont(fb)
        p.setPen(QColor(C.INK if info.synopsis else C.INK_SOFT))
        body_rect = QRectF(x, y + 44, w, r.bottom() - (y + 44) - 28)
        line_h = QFontMetricsF(fb).lineSpacing()
        body_rect.setHeight(max(line_h, int(body_rect.height() / line_h) * line_h))
        p.save()
        p.setClipRect(body_rect)
        p.drawText(body_rect, int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
                   body or "Double-click to write a synopsis")
        p.restore()
        p.setFont(fs)
        p.setPen(QColor(C.INK_SOFT))
        who = ", ".join(info.characters[:3]) + (" …" if len(info.characters) > 3 else "")
        p.drawText(QRectF(x, r.bottom() - 24, w, 18), Qt.AlignmentFlag.AlignLeft,
                   QFontMetricsF(fs).elidedText(who, Qt.TextElideMode.ElideRight, w * 0.75))
        dots = [self.view.line_color(s) for s in info.storylines]
        dx = r.right() - 14
        for c in dots[:5]:
            if c:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(c))
                p.drawEllipse(QPointF(dx, r.bottom() - 15), 5, 5)
                dx -= 13
        p.restore()


class CardList(QListWidget):
    moved = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Snap)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSpacing(4)
        self.setUniformItemSizes(True)
        self.setObjectName("cards")

    def dropEvent(self, e):                       # noqa: N802
        src = self.currentRow()
        target = self.indexAt(e.position().toPoint())
        if target.isValid():
            dst = target.row()
            rect = self.visualRect(target)
            if e.position().x() > rect.center().x():
                dst += 1
        else:
            dst = self.count()
        e.ignore()
        if src >= 0 and dst not in (src, src + 1):
            self.moved.emit(src, dst)


class CardsView(QWidget):
    """Index cards for every scene. Drag to reorder scenes in the script."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.editor = window.editor
        self.card_size = QSize(250, 175)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 10)
        bar = QHBoxLayout()
        title = QLabel("Index Cards", objectName="viewTitle")
        bar.addWidget(title)
        bar.addStretch(1)
        self.filter = QComboBox()
        self.filter.currentIndexChanged.connect(lambda _: self.refresh())
        bar.addWidget(QLabel("Storyline"))
        bar.addWidget(self.filter)
        self.size = QSlider(Qt.Orientation.Horizontal)
        self.size.setRange(180, 360)
        self.size.setValue(250)
        self.size.setFixedWidth(110)
        self.size.valueChanged.connect(self._resize)
        bar.addWidget(QLabel("Size"))
        bar.addWidget(self.size)
        lines_btn = QPushButton("Storylines…")
        lines_btn.clicked.connect(self.edit_storylines)
        add = QPushButton("New Card", objectName="primary")
        add.clicked.connect(self.new_card)
        bar.addWidget(lines_btn)
        bar.addWidget(add)
        lay.addLayout(bar)
        hint = QLabel("Drag cards to reorder scenes in the script · double-click to edit · "
                      "right-click for more", objectName="hint")
        lay.addWidget(hint)
        self.list = CardList()
        self.list.setItemDelegate(CardDelegate(self))
        self.list.moved.connect(self._moved)
        self.list.itemDoubleClicked.connect(lambda it: self.edit_card(it.data(INFO)))
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list, 1)
        self._dirty = True
        self.editor.structureChanged.connect(self._mark)
        self.editor.projectChanged.connect(lambda _p: self._mark())

    def _mark(self):
        self._dirty = True
        if self.isVisible():
            QTimer.singleShot(0, self.refresh)

    def enter_view(self):
        self.refresh()

    def _resize(self, w):
        self.card_size = QSize(w, int(w * 0.7))
        self.list.setGridSize(QSize(w + 8, int(w * 0.7) + 8))
        self.list.doItemsLayout()

    def line_color(self, sid):
        return next((s.get("color") for s in storylines(self.editor) if s["id"] == sid), None)

    def storyline_color(self, info: SceneInfo):
        return self.line_color(info.storylines[0]) if info.storylines else None

    def refresh(self):
        self._dirty = False
        cur_filter = self.filter.currentData()
        self.filter.blockSignals(True)
        self.filter.clear()
        self.filter.addItem("All scenes", None)
        for sl in storylines(self.editor):
            self.filter.addItem(_dot(sl.get("color")), sl["name"], sl["id"])
        self.filter.setCurrentIndex(max(0, self.filter.findData(cur_filter)))
        self.filter.blockSignals(False)
        want = self.filter.currentData()
        row = self.list.currentRow()
        self.list.clear()
        self.list.setGridSize(QSize(self.card_size.width() + 8, self.card_size.height() + 8))
        for info in scene_infos(self.editor):
            it = QListWidgetItem()
            it.setData(INFO, info)
            it.setSizeHint(self.card_size)
            it.setToolTip(info.heading)
            if want and want not in info.storylines:
                it.setHidden(True)
            self.list.addItem(it)
        if 0 <= row < self.list.count():
            self.list.setCurrentRow(row)

    def _moved(self, src: int, dst: int):
        self.editor.move_scene(src, dst)
        self.refresh()
        self.list.setCurrentRow(dst if dst < src else dst - 1)

    def edit_card(self, info: SceneInfo):
        dlg = CardDialog(info, storylines(self.editor), self)
        if dlg.exec():
            syn, color, lines = dlg.values()
            ed = self.editor
            cur = ed.textCursor()
            cur.beginEditBlock()
            ed.set_block_extra(info.block, "synopsis", syn)
            ed.set_block_extra(info.block, "color", color)
            ed.set_block_extra(info.block, "storylines", lines)
            cur.endEditBlock()
            self.refresh()

    def new_card(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("New Scene Card")
        form = QFormLayout(dlg)
        form.setContentsMargins(22, 22, 22, 18)
        heading = QLineEdit(placeholderText="INT. LOCATION - DAY")
        syn = QPlainTextEdit()
        syn.setFixedHeight(90)
        form.addRow("Scene heading", heading)
        form.addRow("Synopsis", syn)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        form.addRow(bb)
        if dlg.exec() and heading.text().strip():
            row = self.list.currentRow()
            self.editor.add_scene(heading.text().strip(), syn.toPlainText().strip(),
                                  after=row if row >= 0 else None)
            self.refresh()

    def _menu(self, pos):
        it = self.list.itemAt(pos)
        if it is None:
            return
        info: SceneInfo = it.data(INFO)
        m = QMenu(self)
        m.addAction("Edit Card…", lambda: self.edit_card(info))
        m.addAction("Go to Scene", lambda: (self.window.show_view("script"),
                                            self.editor.goto_block(info.block)))
        cm = m.addMenu("Colour")
        for name, value in CARD_COLORS:
            cm.addAction(_dot(value), name, lambda v=value: (
                self.editor.set_block_extra(info.block, "color", v), self.refresh()))
        m.addSeparator()
        m.addAction("Move to Start", lambda: self._moved(info.index, 0))
        m.addAction("Move to End", lambda: self._moved(info.index, self.list.count()))
        m.exec(self.list.mapToGlobal(pos))

    def edit_storylines(self):
        if StorylinesDialog(self.editor, self).exec():
            self.editor.touch_project("storylines")
            self.refresh()


# ======================================================================== storylines
class StorylinesDialog(QDialog):
    """Name the threads of your story (A-story, B-story, a character's arc...)."""

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle("Storylines")
        self.setMinimumSize(420, 340)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 14)
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Storyline", "Colour"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        lay.addWidget(self.table)
        row = QHBoxLayout()
        add, remove = QPushButton("Add"), QPushButton("Remove")
        add.clicked.connect(lambda: self._add({"id": uuid.uuid4().hex[:8], "name": "New storyline",
                                               "color": CARD_COLORS[1 + self.table.rowCount() % 8][1]}))
        remove.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()))
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for sl in storylines(editor):
            self._add(dict(sl))

    def _add(self, sl: dict):
        r = self.table.rowCount()
        self.table.insertRow(r)
        name = QTableWidgetItem(sl["name"])
        name.setData(Qt.ItemDataRole.UserRole, sl["id"])
        self.table.setItem(r, 0, name)
        btn = QToolButton()
        btn.setIcon(_dot(sl.get("color")))
        btn.setProperty("color", sl.get("color"))
        btn.clicked.connect(lambda _=False, b=btn: self._pick(b))
        self.table.setCellWidget(r, 1, btn)

    def _pick(self, btn):
        c = QColorDialog.getColor(QColor(btn.property("color") or C.HONEY), self)
        if c.isValid():
            btn.setProperty("color", c.name().upper())
            btn.setIcon(_dot(c.name()))

    def _save(self):
        out = []
        for r in range(self.table.rowCount()):
            it = self.table.item(r, 0)
            out.append({"id": it.data(Qt.ItemDataRole.UserRole), "name": it.text().strip() or "Storyline",
                        "color": self.table.cellWidget(r, 1).property("color")})
        self.editor.project["storylines"] = out
        self.accept()


# ======================================================================== structure points
class StructureDialog(QDialog):
    """Where the big turns should land, in pages (shown on the scene ribbon)."""

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle("Structure Points")
        self.setMinimumSize(420, 360)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 14)
        lay.addWidget(QLabel("Pages where each turn should happen. They appear as marks on the "
                             "scene ribbon above the page.", wordWrap=True))
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Turn", "Page"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        lay.addWidget(self.table)
        row = QHBoxLayout()
        add, remove, defaults = QPushButton("Add"), QPushButton("Remove"), QPushButton("Use Classic Beats")
        add.clicked.connect(lambda: self._add("New point", 1))
        remove.clicked.connect(lambda: self.table.removeRow(self.table.currentRow()))
        defaults.clicked.connect(self._defaults)
        for b in (add, remove, defaults):
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        for pt in editor.project.get("structure", []):
            self._add(pt["name"], pt["page"])

    def _add(self, name, page):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(name))
        spin = QSpinBox()
        spin.setRange(1, 999)
        spin.setValue(int(page))
        self.table.setCellWidget(r, 1, spin)

    def _defaults(self):
        total = max(90, self.editor.page_count())
        self.table.setRowCount(0)
        for name, frac in STRUCTURE_DEFAULTS:
            self._add(name, max(1, round(total * frac)))

    def _save(self):
        self.editor.project["structure"] = [
            {"name": self.table.item(r, 0).text(), "page": self.table.cellWidget(r, 1).value()}
            for r in range(self.table.rowCount())]
        self.accept()


# ======================================================================== scene ribbon
class SceneRibbon(QWidget):
    """A thin strip of every scene above the page, sized by length. Click to jump."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.editor = window.editor
        self.setFixedHeight(26)
        self.setMouseTracking(True)
        self.infos: list[SceneInfo] = []
        self._timer = QTimer(self, singleShot=True, interval=600)
        self._timer.timeout.connect(self.refresh)
        self.editor.structureChanged.connect(self._timer.start)
        self.editor.projectChanged.connect(lambda _p: self._timer.start())
        self.editor.cursorPositionChanged.connect(self.update)

    def refresh(self):
        self.infos = scene_infos(self.editor) if self.isVisible() else []
        self.update()

    def showEvent(self, e):                       # noqa: N802
        super().showEvent(e)
        self.refresh()

    def _rects(self):
        total = sum(max(i.length, 0.05) for i in self.infos) or 1
        x, w = 10.0, self.width() - 20.0
        out = []
        for info in self.infos:
            ww = w * max(info.length, 0.05) / total
            out.append((QRectF(x, 6, max(ww - 1.5, 1), 14), info))
            x += ww
        return out

    def paintEvent(self, e):                      # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(C.GREIGE))
        if not self.infos:
            return
        cur_block = self.editor.textCursor().blockNumber()
        current = None
        lines = {s["id"]: s.get("color") for s in storylines(self.editor)}
        for i, (r, info) in enumerate(self._rects()):
            color = info.color or (lines.get(info.storylines[0]) if info.storylines else None)
            base = QColor(color) if color else QColor(C.THUMB if i % 2 else C.LINE)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(base)
            p.drawRoundedRect(r, 3, 3)
            if info.block <= cur_block:
                current = r
        if current is not None:
            p.setPen(QPen(QColor(C.INK), 1.6))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(current.adjusted(-1, -2, 1, 2), 3, 3)
        pages = max(1, self.editor.page_count())
        p.setPen(QPen(QColor(C.CARAMEL), 1.4))
        for pt in self.editor.project.get("structure", []):
            x = 10 + (self.width() - 20) * min(1.0, (pt["page"] - 1) / pages)
            p.drawLine(QPointF(x, 2), QPointF(x, 24))

    def _info_at(self, pos):
        for r, info in self._rects():
            if r.left() <= pos.x() <= r.right():
                return info
        return None

    def mouseMoveEvent(self, e):                  # noqa: N802
        info = self._info_at(e.position())
        marks = [pt["name"] for pt in self.editor.project.get("structure", [])
                 if abs(10 + (self.width() - 20) * (pt["page"] - 1) / max(1, self.editor.page_count())
                        - e.position().x()) < 4]
        tip = (f"{info.number}. {info.heading}  ·  p.{info.page}" if info else "")
        if marks:
            tip = " / ".join(marks) + ("\n" + tip if tip else "")
        self.setToolTip(tip)

    def mousePressEvent(self, e):                 # noqa: N802
        info = self._info_at(e.position())
        if info:
            self.editor.goto_block(info.block)


# ======================================================================== beat board
class BeatItem(QGraphicsObject):
    changed = Signal()

    def __init__(self, beat: dict, board: "BeatBoard"):
        super().__init__()
        self.beat = beat
        self.board = board
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsObject.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setPos(beat.get("x", 0), beat.get("y", 0))
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setAcceptHoverEvents(True)

    W, H = 220, 132

    def boundingRect(self):                      # noqa: N802
        return QRectF(-3, -3, self.W + 6, self.H + 8)

    def paint(self, p: QPainter, opt, widget=None):
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0, 0, self.W, self.H)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 25))
        p.drawRoundedRect(r.translated(0, 3), 10, 10)
        color = QColor(self.beat.get("color") or C.HONEY)
        bg = QColor(color)
        bg.setAlpha(70)
        p.setBrush(QColor(C.PAPER))
        p.setPen(QPen(QColor(C.MUSTARD) if self.isSelected() else QColor(C.LINE), 2 if self.isSelected() else 1))
        p.drawRoundedRect(r, 10, 10)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, 10, 10)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(0, 0, 6, self.H), 3, 3)
        f = QFont()
        f.setBold(True)
        f.setPointSize(10)
        p.setFont(f)
        p.setPen(QColor(C.INK))
        p.drawText(QRectF(16, 10, self.W - 26, 40), int(Qt.TextFlag.TextWordWrap),
                   self.beat.get("title") or "Beat")
        f2 = QFont()
        f2.setPointSize(9)
        p.setFont(f2)
        p.setPen(QColor(C.INK_SOFT))
        p.drawText(QRectF(16, 46, self.W - 26, self.H - 54),
                   int(Qt.TextFlag.TextWordWrap), self.beat.get("text", ""))

    def itemChange(self, change, value):         # noqa: N802
        if change == QGraphicsObject.GraphicsItemChange.ItemPositionHasChanged:
            self.beat["x"], self.beat["y"] = round(self.pos().x()), round(self.pos().y())
            self.board.item_moved(self)
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, e):          # noqa: N802
        self.board.edit_beat(self)

    def mousePressEvent(self, e):                # noqa: N802
        if self.board.connecting or e.modifiers() & Qt.KeyboardModifier.AltModifier:
            self.board.start_link(self, e.scenePos())
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):                 # noqa: N802
        if self.board.drag_line is not None:
            self.board.drag_to(e.scenePos())
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):              # noqa: N802
        if self.board.drag_line is not None:
            self.board.finish_link(e.scenePos())
            return
        super().mouseReleaseEvent(e)


class LinkItem(QGraphicsPathItem):
    def __init__(self, a: BeatItem, b: BeatItem):
        super().__init__()
        self.a, self.b = a, b
        self.setZValue(-1)
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.update_path()

    def update_path(self):
        ra = self.a.sceneBoundingRect().adjusted(3, 3, -3, -5)
        rb = self.b.sceneBoundingRect().adjusted(3, 3, -3, -5)
        a, b = ra.center(), rb.center()
        line = QLineF(a, b)
        pa, pb = _edge(ra, line), _edge(rb, QLineF(b, a))
        path = QPainterPath(pa)
        mid = (pa + pb) / 2
        path.cubicTo(QPointF(mid.x(), pa.y()), QPointF(mid.x(), pb.y()), pb)
        ang = QLineF(QPointF(mid.x(), pb.y()), pb).angle()
        import math
        rad = math.radians(ang)
        tip = pb
        left = tip - QPointF(math.cos(rad - 0.45) * 11, -math.sin(rad - 0.45) * 11)
        right = tip - QPointF(math.cos(rad + 0.45) * 11, -math.sin(rad + 0.45) * 11)
        path.addPolygon(QPolygonF([tip, left, right, tip]))
        self.setPath(path)
        pen = QPen(QColor(C.CARAMEL), 2)
        if self.isSelected():
            pen.setColor(QColor(C.MUSTARD))
        self.setPen(pen)
        self.setBrush(QBrush(QColor(C.CARAMEL)))


def _edge(rect: QRectF, line: QLineF) -> QPointF:
    """Where a line from the rect's centre leaves the rect."""
    for side in (QLineF(rect.topLeft(), rect.topRight()), QLineF(rect.topRight(), rect.bottomRight()),
                 QLineF(rect.bottomRight(), rect.bottomLeft()), QLineF(rect.bottomLeft(), rect.topLeft())):
        kind, pt = line.intersects(side)
        if kind == QLineF.IntersectionType.BoundedIntersection:
            return pt
    return line.p1()


class BeatDialog(QDialog):
    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Beat")
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        form.setContentsMargins(22, 22, 22, 18)
        self.title = QLineEdit(data.get("title", ""))
        self.text = QPlainTextEdit(data.get("text", ""))
        self.text.setFixedHeight(110)
        self.color = QComboBox()
        for name, value in CARD_COLORS[1:]:
            self.color.addItem(_dot(value), name, value)
        self.color.setCurrentIndex(max(0, self.color.findData(data.get("color"))))
        form.addRow("Title", self.title)
        form.addRow("Beat", self.text)
        form.addRow("Colour", self.color)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)


class BoardView(QGraphicsView):
    def __init__(self, scene, board):
        super().__init__(scene)
        self.board = board
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setObjectName("board")

    def wheelEvent(self, e):                     # noqa: N802
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            f = 1.12 if e.angleDelta().y() > 0 else 1 / 1.12
            self.scale(f, f)
        else:
            super().wheelEvent(e)

    def mouseDoubleClickEvent(self, e):          # noqa: N802
        if self.itemAt(e.position().toPoint()) is None:
            self.board.add_beat(self.mapToScene(e.position().toPoint()))
            return
        super().mouseDoubleClickEvent(e)

    def drawBackground(self, p, rect):           # noqa: N802
        p.fillRect(rect, QColor(C.GREIGE))
        p.setPen(QPen(QColor(C.LINE), 1.2))
        step = 28
        x0 = int(rect.left()) - int(rect.left()) % step
        y0 = int(rect.top()) - int(rect.top()) % step
        for x in range(x0, int(rect.right()) + step, step):
            for y in range(y0, int(rect.bottom()) + step, step):
                p.drawPoint(x, y)

    def keyPressEvent(self, e):                  # noqa: N802
        if e.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.board.delete_selected()
            return
        super().keyPressEvent(e)


class BeatBoard(QWidget):
    """A free canvas of story beats. Double-click empty space for a new beat; Alt-drag (or
    Connect) from one beat to another to draw a flow line; send a beat to the script as a scene."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.editor = window.editor
        self.connecting = False
        self.drag_line = None
        self.drag_from = None
        self.items: dict[str, BeatItem] = {}
        self.links: list[LinkItem] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 10)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Beat Board", objectName="viewTitle"))
        bar.addStretch(1)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setCheckable(True)
        self.connect_btn.toggled.connect(lambda on: setattr(self, "connecting", on))
        fit = QPushButton("Fit")
        fit.clicked.connect(self.fit)
        structure = QPushButton("Structure Points…")
        structure.clicked.connect(self.edit_structure)
        add = QPushButton("New Beat", objectName="primary")
        add.clicked.connect(lambda: self.add_beat(self.view.mapToScene(self.view.viewport().rect().center())))
        for b in (self.connect_btn, fit, structure, add):
            bar.addWidget(b)
        lay.addLayout(bar)
        lay.addWidget(QLabel("Double-click the board for a new beat · Alt-drag between beats to "
                             "connect them · Ctrl+wheel to zoom · Delete removes", objectName="hint"))
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(-2000, -1500, 6000, 4000)
        self.view = BoardView(self.scene, self)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.view, 1)
        self._save_timer = QTimer(self, singleShot=True, interval=400)
        self._save_timer.timeout.connect(lambda: self.editor.touch_project("beats"))
        self.editor.projectChanged.connect(self._project_changed)
        self._loaded_for = None

    def _project_changed(self, part):
        if part == "":                             # a new script was opened
            self.load()

    def enter_view(self):
        if self._loaded_for is not self.editor.project:
            self.load()

    def beats(self) -> list[dict]:
        return self.editor.project.setdefault("beats", [])

    def link_data(self) -> list[list[str]]:
        return self.editor.project.setdefault("links", [])

    def load(self):
        self.scene.clear()
        self.items, self.links = {}, []
        self.drag_line = None
        self._loaded_for = self.editor.project
        for b in list(self.editor.project.get("beats", [])):
            self._item(b)
        for a, b in list(self.editor.project.get("links", [])):
            if a in self.items and b in self.items:
                lk = LinkItem(self.items[a], self.items[b])
                self.scene.addItem(lk)
                self.links.append(lk)

    def _item(self, data: dict) -> BeatItem:
        it = BeatItem(data, self)
        self.scene.addItem(it)
        self.items[data["id"]] = it
        return it

    def item_moved(self, item: BeatItem):
        for lk in self.links:
            if lk.a is item or lk.b is item:
                lk.update_path()
        self._save_timer.start()

    def add_beat(self, at: QPointF, title: str = "", text: str = ""):
        data = {"id": uuid.uuid4().hex[:8], "x": round(at.x() - BeatItem.W / 2),
                "y": round(at.y() - BeatItem.H / 2), "title": title, "text": text,
                "color": CARD_COLORS[1 + len(self.beats()) % 8][1]}
        dlg = BeatDialog(data, self)
        if not title and not dlg.exec():
            return None
        if not title:
            data.update(title=dlg.title.text().strip() or "Beat", text=dlg.text.toPlainText().strip(),
                        color=dlg.color.currentData())
        self.beats().append(data)
        it = self._item(data)
        self._save_timer.start()
        return it

    def edit_beat(self, item: BeatItem):
        dlg = BeatDialog(item.beat, self)
        if dlg.exec():
            item.beat.update(title=dlg.title.text().strip(), text=dlg.text.toPlainText().strip(),
                             color=dlg.color.currentData())
            item.update()
            self._save_timer.start()

    def start_link(self, item: BeatItem, pos: QPointF):
        self.drag_from = item
        self.drag_line = self.scene.addLine(QLineF(item.sceneBoundingRect().center(), pos),
                                            QPen(QColor(C.CARAMEL), 2, Qt.PenStyle.DashLine))

    def drag_to(self, pos: QPointF):
        self.drag_line.setLine(QLineF(self.drag_from.sceneBoundingRect().center(), pos))

    def finish_link(self, pos: QPointF):
        self.scene.removeItem(self.drag_line)
        self.drag_line = None
        target = next((it for it in self.scene.items(pos) if isinstance(it, BeatItem)), None)
        if target is not None and target is not self.drag_from:
            self.connect(self.drag_from, target)
        self.drag_from = None

    def connect(self, a: BeatItem, b: BeatItem):
        pair = [a.beat["id"], b.beat["id"]]
        if pair in self.link_data():
            return
        self.link_data().append(pair)
        lk = LinkItem(a, b)
        self.scene.addItem(lk)
        self.links.append(lk)
        self._save_timer.start()

    def delete_selected(self):
        for it in self.scene.selectedItems():
            if isinstance(it, BeatItem):
                bid = it.beat["id"]
                self.editor.project["beats"] = [b for b in self.beats() if b["id"] != bid]
                self.editor.project["links"] = [lk for lk in self.link_data() if bid not in lk]
                for lk in [lk for lk in self.links if lk.a is it or lk.b is it]:
                    self.scene.removeItem(lk)
                    self.links.remove(lk)
                self.scene.removeItem(it)
                self.items.pop(bid, None)
            elif isinstance(it, LinkItem):
                pair = [it.a.beat["id"], it.b.beat["id"]]
                self.editor.project["links"] = [lk for lk in self.link_data() if lk != pair]
                self.scene.removeItem(it)
                self.links.remove(it)
        self._save_timer.start()

    def to_script(self, item: BeatItem):
        """Make a scene card from a beat (it is added at the end of the script)."""
        heading = item.beat.get("title", "NEW SCENE")
        self.editor.add_scene(heading if heading.upper().startswith(("INT", "EXT")) else
                              f"INT. {heading.upper()} - DAY", item.beat.get("text", ""))
        item.beat["scene"] = True
        self.window.statusBar().showMessage("Beat added to the script as a new scene", 3000)

    def fit(self):
        r = self.scene.itemsBoundingRect()
        if r.isValid() and not r.isEmpty():
            self.view.fitInView(r.adjusted(-60, -60, 60, 60), Qt.AspectRatioMode.KeepAspectRatio)

    def edit_structure(self):
        if StructureDialog(self.editor, self).exec():
            self.editor.touch_project("structure")

    def _menu(self, pos):
        item = self.view.itemAt(pos)
        while item is not None and not isinstance(item, (BeatItem, LinkItem)):
            item = item.parentItem()
        m = QMenu(self)
        if isinstance(item, BeatItem):
            m.addAction("Edit Beat…", lambda: self.edit_beat(item))
            m.addAction("Add to Script as Scene", lambda: self.to_script(item))
            cm = m.addMenu("Colour")
            for name, value in CARD_COLORS[1:]:
                cm.addAction(_dot(value), name, lambda v=value: (
                    item.beat.update(color=v), item.update(), self._save_timer.start()))
            m.addSeparator()
            m.addAction("Delete", lambda: (item.setSelected(True), self.delete_selected()))
        elif isinstance(item, LinkItem):
            m.addAction("Remove Line", lambda: (item.setSelected(True), self.delete_selected()))
        else:
            at = self.view.mapToScene(pos)
            m.addAction("New Beat Here…", lambda: self.add_beat(at))
            m.addAction("Beats From Scene Cards", self.beats_from_cards)
        m.exec(self.view.mapToGlobal(pos))

    def beats_from_cards(self):
        """Lay the script's scenes out as beats (one row per 6 scenes)."""
        for i, info in enumerate(scene_infos(self.editor)):
            at = QPointF((i % 6) * 250 + BeatItem.W / 2, (i // 6) * 170 + BeatItem.H / 2)
            it = self.add_beat(at, f"{info.number}. {info.heading}", info.synopsis or info.preview[:120])
            if it and info.color:
                it.beat["color"] = info.color
        self.fit()

    def theme_changed(self):
        self.scene.update()


# ======================================================================== characters
class CharactersView(QWidget):
    """Every character: profile, numbers, and a lens that lights up their lines in the script."""

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.editor = window.editor
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 10)
        split = QSplitter()
        lay.addWidget(split)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 8, 0)
        lv.addWidget(QLabel("Characters", objectName="viewTitle"))
        self.list = QListWidget(objectName="navList")
        self.list.currentItemChanged.connect(lambda cur, _prev: self.show_character(cur))
        lv.addWidget(self.list, 1)
        split.addWidget(left)
        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setFrameShape(QFrame.Shape.NoFrame)
        panel = QWidget(objectName="profile")
        self.form = QGridLayout(panel)
        self.form.setContentsMargins(24, 10, 24, 10)
        self.form.setVerticalSpacing(8)
        self.name = QLabel("", objectName="profileName")
        self.stats = QLabel("", objectName="hint")
        self.form.addWidget(self.name, 0, 0, 1, 2)
        self.form.addWidget(self.stats, 1, 0, 1, 2)
        buttons = QHBoxLayout()
        self.lens = QCheckBox("Highlight their lines in the script")
        self.lens.toggled.connect(self._lens)
        rename = QPushButton("Rename…")
        rename.clicked.connect(lambda: self.window.rename_character(self.current or ""))
        first = QPushButton("First Appearance")
        first.clicked.connect(self._first)
        buttons.addWidget(self.lens)
        buttons.addStretch(1)
        buttons.addWidget(first)
        buttons.addWidget(rename)
        self.form.addLayout(buttons, 2, 0, 1, 2)
        self.fields = {}
        for row, (key, label) in enumerate(PROFILE_FIELDS, 3):
            w = QPlainTextEdit() if key in ("description", "backstory", "notes", "arc") else QLineEdit()
            if isinstance(w, QPlainTextEdit):
                w.setFixedHeight(70)
                w.textChanged.connect(self._save)
            else:
                w.textEdited.connect(self._save)
            self.form.addWidget(QLabel(label), row, 0, Qt.AlignmentFlag.AlignTop)
            self.form.addWidget(w, row, 1)
            self.fields[key] = w
        self.form.setRowStretch(len(PROFILE_FIELDS) + 3, 1)
        right.setWidget(panel)
        split.addWidget(right)
        split.setSizes([260, 700])
        self.current: str | None = None
        self.rep = None
        self._loading = False
        self.lens_names: set[str] = set()
        self._lens_timer = QTimer(self, singleShot=True, interval=500)
        self._lens_timer.timeout.connect(self.apply_lens)
        self.editor.structureChanged.connect(lambda: self.lens_names and self._lens_timer.start())

    def enter_view(self):
        self.refresh()

    def refresh(self):
        scenes = self.editor.scenes()
        self.rep = reports.build(self.editor.element_pairs(), [s[2] for s in scenes])
        keep = self.current
        self.list.blockSignals(True)
        self.list.clear()
        for c in self.rep.characters:
            it = QListWidgetItem(c.name)
            it.setToolTip(f"{c.speeches} speeches · {c.words} words")
            self.list.addItem(it)
        self.list.blockSignals(False)
        names = [c.name for c in self.rep.characters]
        if keep in names:
            self.list.setCurrentRow(names.index(keep))
        elif names:
            self.list.setCurrentRow(0)
        else:
            self.show_character(None)

    def show_character(self, item):
        self._loading = True
        self.current = item.text() if item else None
        prof = self.editor.project.get("characters", {}).get(self.current or "", {})
        c = next((c for c in (self.rep.characters if self.rep else []) if c.name == self.current), None)
        self.name.setText(self.current or "No characters yet")
        if c:
            share = c.words / max(1, self.rep.dialogue_words) * 100
            self.stats.setText(f"{c.speeches} speeches  ·  {c.words} words ({share:.0f}% of dialogue)  ·  "
                               f"{len(c.scenes)} scene{'s' if len(c.scenes) != 1 else ''}  ·  first in scene {c.scenes[0] if c.scenes else '–'}")
        else:
            self.stats.setText("")
        for key, w in self.fields.items():
            v = prof.get(key, "")
            w.setPlainText(v) if isinstance(w, QPlainTextEdit) else w.setText(v)
            w.setEnabled(self.current is not None)
        self.lens.blockSignals(True)
        self.lens.setChecked(self.current in self.lens_names)
        self.lens.blockSignals(False)
        self._loading = False

    def _save(self):
        if self._loading or not self.current:
            return
        prof = {}
        for key, w in self.fields.items():
            v = (w.toPlainText() if isinstance(w, QPlainTextEdit) else w.text()).strip()
            if v:
                prof[key] = v
        chars = self.editor.project.setdefault("characters", {})
        if prof:
            chars[self.current] = prof
        else:
            chars.pop(self.current, None)
        self.editor.touch_project("characters")

    def _first(self):
        if not self.current:
            return
        from ..core.smart import base_name
        block = self.editor.document().firstBlock()
        while block.isValid():
            if self.editor.block_type(block) == T.CHARACTER and base_name(block.text()).upper() == self.current:
                self.window.show_view("script")
                self.editor.goto_block(block.blockNumber())
                return
            block = block.next()

    def _lens(self, on: bool):
        if not self.current:
            return
        (self.lens_names.add if on else self.lens_names.discard)(self.current)
        self.apply_lens()

    def apply_lens(self):
        """Tint the speeches of the chosen characters (each in its own colour)."""
        from ..core.smart import base_name
        from PySide6.QtGui import QTextCursor
        palette = ["#F3E3A3", "#F6D3C8", "#D6E6F5", "#D4EBDD", "#E5DAF1", "#F5DDB8"]
        colors = {n: palette[i % len(palette)] for i, n in enumerate(sorted(self.lens_names))}
        if C.NAME != "Day":
            colors = {n: QColor(c).darker(260).name() for n, c in colors.items()}
        sels = []
        speaker = None
        block = self.editor.document().firstBlock()
        while block.isValid():
            t = self.editor.block_type(block)
            if t == T.CHARACTER:
                speaker = base_name(block.text()).upper()
            elif t not in (T.DIALOGUE, T.PARENTHETICAL):
                speaker = None
            if speaker in colors and t in (T.CHARACTER, T.DIALOGUE, T.PARENTHETICAL):
                sels.append(self.editor.make_selection(QTextCursor(block), background=colors[speaker],
                                                       full_width=True))
            block = block.next()
        self.editor.set_layer("lens", sels)


# ======================================================================== feature
class Planning:
    def __init__(self, window):
        self.window = window
        self.cards = CardsView(window)
        self.board = BeatBoard(window)
        self.characters = CharactersView(window)
        window.add_view("cards", "Index Cards", "cards", self.cards)
        window.add_view("board", "Beat Board", "board", self.board)
        window.add_view("characters", "Characters", "people", self.characters)
        self.ribbon = SceneRibbon(window)
        window.script_top.addWidget(self.ribbon)
        show = window.settings.value("ribbon", "true") == "true"
        self.ribbon.setVisible(show)
        act = QAction("Scene Ribbon", window, checkable=True)
        act.setChecked(show)
        act.toggled.connect(self._ribbon)
        window.menus["view"].insertAction(window.act["focus"], act)
        tools = window.menus["tools"]
        tools.addAction("Storylines…", lambda: self.cards.edit_storylines())
        tools.addAction("Structure Points…", lambda: self.board.edit_structure())
        tools.addSeparator()

    def _ribbon(self, on):
        self.ribbon.setVisible(on)
        self.window.settings.setValue("ribbon", "true" if on else "false")

    def script_loaded(self):
        self.characters.lens_names.clear()
        self.window.editor.set_layer("lens", [])
        self.board.load()
        self.ribbon.refresh()

    def theme_changed(self):
        self.board.theme_changed()
        self.ribbon.update()
        if self.characters.lens_names:
            self.characters.apply_lens()
