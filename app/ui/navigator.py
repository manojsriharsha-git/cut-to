"""Left panel (Scenes / Characters / Locations) and the Reports window."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize, QRectF
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QButtonGroup, QStackedWidget,
                               QStyledItemDelegate, QStyle, QDialog, QTabWidget, QTableWidget,
                               QTableWidgetItem, QDialogButtonBox, QFileDialog, QAbstractItemView,
                               QGridLayout)

from ..core import reports
from .theme import C

SUBTITLE = Qt.ItemDataRole.UserRole + 1
TARGET = Qt.ItemDataRole.UserRole          # block number to jump to


class TwoLineDelegate(QStyledItemDelegate):
    """A title line and a quieter detail line, with the Bumble selection style."""

    def paint(self, p: QPainter, opt, index):
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(opt.rect).adjusted(6, 2, -6, -2)
        if opt.state & QStyle.StateFlag.State_Selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C.BLUSH))
            p.drawRoundedRect(box, 6, 6)
            p.setBrush(QColor(C.MUSTARD))
            p.drawRoundedRect(QRectF(box.left(), box.top() + 8, 3, box.height() - 16), 1.5, 1.5)
        elif opt.state & QStyle.StateFlag.State_MouseOver:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C.CREAM))
            p.drawRoundedRect(box, 6, 6)
        x, w = int(box.left()) + 12, int(box.width()) - 18
        title = QFont(opt.font)
        title.setWeight(QFont.Weight.DemiBold)
        fm = QFontMetrics(title)
        p.setFont(title)
        p.setPen(QColor(C.INK))
        y = int(box.top()) + 6 + fm.ascent()
        p.drawText(x, y, fm.elidedText(index.data() or "", Qt.TextElideMode.ElideRight, w))
        sub = QFont(opt.font)
        sub.setPointSizeF(max(7.5, opt.font.pointSizeF() - 1.5))
        fs = QFontMetrics(sub)
        p.setFont(sub)
        p.setPen(QColor(C.INK_SOFT))
        p.drawText(x, y + fm.descent() + 4 + fs.ascent(),
                   fs.elidedText(index.data(SUBTITLE) or "", Qt.TextElideMode.ElideRight, w))
        p.restore()

    def sizeHint(self, opt, index):
        return QSize(opt.rect.width(), 50)


class Navigator(QFrame):
    """Scenes, Characters and Locations of the open script. Click a row to jump there."""
    jump = Signal(int)

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setObjectName("sidebar")
        self.setMinimumWidth(220)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 12, 6, 8)
        lay.setSpacing(8)

        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.group = QButtonGroup(self)
        self.stack = QStackedWidget()
        self.lists = []
        for i, name in enumerate(("Scenes", "Characters", "Locations")):
            b = QPushButton(name, objectName="seg")
            b.setCheckable(True)
            b.setProperty("pos", "first" if i == 0 else "last" if i == 2 else "mid")
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.group.addButton(b, i)
            seg.addWidget(b)
            lst = QListWidget(objectName="navList")
            lst.setItemDelegate(TwoLineDelegate(lst))
            lst.setMouseTracking(True)
            lst.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            lst.itemClicked.connect(self._clicked)
            self.stack.addWidget(lst)
            self.lists.append(lst)
        self.group.button(0).setChecked(True)
        self.group.idClicked.connect(self.stack.setCurrentIndex)
        self.seg = seg
        lay.addLayout(seg)
        lay.addWidget(self.stack, 1)

    def add_tab(self, name: str, widget) -> int:
        """Another tab beside Scenes / Characters / Locations (e.g. Notes)."""
        i = len(self.group.buttons())
        last = self.group.button(i - 1)
        last.setProperty("pos", "mid")
        last.style().unpolish(last)
        last.style().polish(last)
        b = QPushButton(name, objectName="seg")
        b.setCheckable(True)
        b.setProperty("pos", "last")
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.group.addButton(b, i)
        self.seg.addWidget(b)
        self.stack.addWidget(widget)
        return i

    def _clicked(self, item: QListWidgetItem):
        target = item.data(TARGET)
        if target is not None:
            self.jump.emit(int(target))

    def refresh(self):
        scenes = self.editor.scenes()
        lengths = self.editor.scene_lengths()
        rep = reports.build(self.editor.element_pairs(), [s[2] for s in scenes])
        block_of = {}
        lst = self.lists[0]
        lst.clear()
        for (block_no, heading, _num, page), row, length in zip(scenes, rep.scenes, lengths):
            block_of.setdefault(row.number, block_no)
            who = ", ".join(row.characters[:4]) + (" …" if len(row.characters) > 4 else "")
            sub = f"p. {page}  ·  {reports.eighths(length)} pg" + (f"  ·  {who}" if who else "")
            self._add(lst, f"{row.number}   {heading}", sub, block_no)

        lst = self.lists[1]
        lst.clear()
        for c in rep.characters:
            sub = (f"{c.speeches} speeches  ·  {c.words} words  ·  "
                   f"{len(c.scenes)} scene{'s' if len(c.scenes) != 1 else ''}")
            self._add(lst, c.name, sub, block_of.get(c.scenes[0]) if c.scenes else None)

        lst = self.lists[2]
        lst.clear()
        for loc in rep.locations:
            sub = " / ".join(loc.intros) + ("  ·  " + " / ".join(loc.times) if loc.times else "") + \
                  f"  ·  {len(loc.scenes)} scene{'s' if len(loc.scenes) != 1 else ''}"
            self._add(lst, loc.location, sub, block_of.get(loc.scenes[0]) if loc.scenes else None)
        self.sync(self.editor.textCursor().blockNumber())

    @staticmethod
    def _add(lst: QListWidget, title: str, sub: str, target):
        it = QListWidgetItem(title)
        it.setData(SUBTITLE, sub)
        it.setData(TARGET, target)
        it.setToolTip(title)
        lst.addItem(it)

    def sync(self, block_number: int):
        """Highlight the scene the cursor is in."""
        lst = self.lists[0]
        row = -1
        for i in range(lst.count()):
            if lst.item(i).data(TARGET) <= block_number:
                row = i
        lst.blockSignals(True)
        lst.setCurrentRow(row)
        lst.blockSignals(False)


class ReportsDialog(QDialog):
    """Totals and three sortable tables, each exportable as CSV for production."""

    def __init__(self, editor, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reports")
        self.resize(860, 560)
        self.title = title or "Untitled"
        scenes = editor.scenes()
        lengths = editor.scene_lengths()
        self.rep = reports.build(editor.element_pairs(), [s[2] for s in scenes])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(14)

        stats = QGridLayout()
        stats.setHorizontalSpacing(28)
        figures = [("Pages", editor.page_count()), ("Scenes", len(self.rep.scenes)),
                   ("Characters", len(self.rep.characters)), ("Locations", len(self.rep.locations)),
                   ("Words", self.rep.total_words), ("Dialogue", f"{self.rep.dialogue_share}%")]
        for i, (name, value) in enumerate(figures):
            v = QLabel(str(value), objectName="statValue")
            n = QLabel(name.upper(), objectName="statName")
            stats.addWidget(v, 0, i)
            stats.addWidget(n, 1, i)
        lay.addLayout(stats)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._table(
            ["Scene", "Heading", "Page", "Length", "Characters", "Words"],
            [[s.number, s.heading, page, reports.eighths(length), ", ".join(s.characters), s.words]
             for s, (_, _, _, page), length in zip(self.rep.scenes, scenes, lengths)]), "Scenes")
        self.tabs.addTab(self._table(
            ["Character", "Speeches", "Words", "Scenes", "Scene numbers"],
            [[c.name, c.speeches, c.words, len(c.scenes), ", ".join(c.scenes)]
             for c in self.rep.characters]), "Characters")
        self.tabs.addTab(self._table(
            ["Location", "INT/EXT", "Times of day", "Scenes", "Scene numbers"],
            [[l.location, " / ".join(l.intros), " / ".join(l.times), len(l.scenes), ", ".join(l.scenes)]
             for l in self.rep.locations]), "Locations")
        lay.addWidget(self.tabs, 1)

        bb = QDialogButtonBox()
        export = bb.addButton("Export CSV…", QDialogButtonBox.ButtonRole.ActionRole)
        export.setObjectName("primary")
        export.setAutoDefault(False)
        export.setMinimumWidth(130)
        export.clicked.connect(self.export_csv)
        close = bb.addButton(QDialogButtonBox.StandardButton.Close)
        close.setAutoDefault(False)
        close.clicked.connect(self.accept)
        lay.addWidget(bb)

    @staticmethod
    def _table(header: list[str], rows: list[list]) -> QTableWidget:
        t = QTableWidget(len(rows), len(header))
        t.setHorizontalHeaderLabels(header)
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setAlternatingRowColors(True)
        t.setShowGrid(False)
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem()
                if isinstance(value, str) and value.isdigit():
                    value = int(value)                     # so 10 sorts after 9
                item.setData(Qt.ItemDataRole.DisplayRole, value)
                t.setItem(r, c, item)
        t.resizeColumnsToContents()
        for c in range(len(header) - 1):
            t.setColumnWidth(c, t.columnWidth(c) + 24)
        t.horizontalHeader().setStretchLastSection(True)
        t.setSortingEnabled(True)
        t.sortByColumn(-1, Qt.SortOrder.AscendingOrder)    # keep script order until clicked
        return t

    def export_csv(self):
        kind = ("scenes", "characters", "locations")[self.tabs.currentIndex()]
        default = str(Path.home() / f"{self.title} - {kind}.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", default, "CSV (*.csv)")
        if path:
            text = {"scenes": reports.scenes_csv, "characters": reports.characters_csv,
                    "locations": reports.locations_csv}[kind](self.rep)
            Path(path).write_text(text, encoding="utf-8-sig")   # opens cleanly in Excel
