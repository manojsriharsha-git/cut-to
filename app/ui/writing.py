"""
Writing comfort: find & replace bar, Go To, command palette, rename character,
writing goals and spelling. Each piece is a small widget the main window plugs in.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import (QAction, QColor, QKeySequence, QSyntaxHighlighter, QTextCharFormat,
                           QTextCursor, QShortcut)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLineEdit, QPushButton, QToolButton, QLabel,
                               QComboBox, QCheckBox, QDialog, QVBoxLayout, QListWidget,
                               QListWidgetItem, QFormLayout, QDialogButtonBox, QSpinBox,
                               QProgressBar, QWidget)

from ..core.ir import T
from ..core.smart import CAPS_TYPES
from .editor import SHORTCUT_TYPES
from .icons import icon
from .pages import block_type
from .theme import C

WORD_RE = re.compile(r"[A-Za-z][A-Za-z'’]*")
# Screenwriting words a general dictionary doesn't know
SCREEN_WORDS = {"int", "ext", "est", "contd", "cont'd", "cont’d", "os", "vo", "pov", "ecu", "mcu", "cu",
                "ws", "ms", "ots", "insert", "intercut", "smash", "mos", "sfx", "vfx", "fx", "superimpose",
                "super", "flashback", "montage", "beat", "o.s", "v.o", "ok", "okay", "uh", "um", "hmm"}


# ======================================================================== find & replace
class FindBar(QFrame):
    """Ctrl+F / Ctrl+H. Highlights every match; Enter = next, Shift+Enter = previous."""
    closed = Signal()

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setObjectName("findBar")
        self.matches: list[QTextCursor] = []
        self.index = -1
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 8, 14, 8)
        lay.setSpacing(6)
        row1, row2 = QHBoxLayout(), QHBoxLayout()
        lay.addLayout(row1)
        lay.addLayout(row2)
        self.find = QLineEdit(placeholderText="Find")
        self.find.setClearButtonEnabled(True)
        self.replace = QLineEdit(placeholderText="Replace with")
        self.case = QCheckBox("Match case")
        self.whole = QCheckBox("Whole word")
        self.scope = QComboBox()
        self.scope.addItem("All elements", None)
        for t in SHORTCUT_TYPES:
            self.scope.addItem(t, t)
        self.count = QLabel("")
        self.count.setMinimumWidth(80)
        prev, nxt = QToolButton(text="↑"), QToolButton(text="↓")
        prev.setToolTip("Previous (Shift+Enter)")
        nxt.setToolTip("Next (Enter)")
        close = QToolButton(text="✕")
        close.setToolTip("Close (Esc)")
        self.btn_one = QPushButton("Replace")
        self.btn_all = QPushButton("Replace All")
        for w in (self.find, prev, nxt, self.count, self.case, self.whole, self.scope):
            row1.addWidget(w)
        row1.addStretch(1)
        row1.addWidget(close)
        for w in (self.replace, self.btn_one, self.btn_all):
            row2.addWidget(w)
        row2.addStretch(1)
        self.find.setMinimumWidth(260)
        self.replace.setMinimumWidth(260)
        self._row2 = [self.replace, self.btn_one, self.btn_all]

        self._timer = QTimer(self, singleShot=True, interval=150)
        self._timer.timeout.connect(self.refresh)
        self.find.textChanged.connect(lambda _: self._timer.start())
        for cb in (self.case, self.whole):
            cb.toggled.connect(lambda _: self.refresh())
        self.scope.currentIndexChanged.connect(lambda _: self.refresh())
        self.find.returnPressed.connect(self.next)
        prev.clicked.connect(self.prev)
        nxt.clicked.connect(self.next)
        close.clicked.connect(self.close_bar)
        self.btn_one.clicked.connect(self.replace_one)
        self.btn_all.clicked.connect(self.replace_all)
        QShortcut(QKeySequence("Shift+Return"), self.find, self.prev)
        QShortcut(QKeySequence("Escape"), self, self.close_bar)
        editor.document().contentsChanged.connect(lambda: self.isVisible() and self._timer.start())
        self.hide()

    def open(self, with_replace: bool = False):
        sel = self.editor.textCursor().selectedText()
        if sel and " " not in sel:
            self.find.setText(sel)
        for w in self._row2:
            w.setVisible(with_replace)
        self.show()
        self.find.setFocus()
        self.find.selectAll()
        self.refresh()

    def close_bar(self):
        self.hide()
        self.editor.set_layer("find", [])
        self.editor.setFocus()
        self.closed.emit()

    def refresh(self):
        if not self.isVisible():
            return
        ed = self.editor
        self.matches = ed.find_all(self.find.text(), self.case.isChecked(), self.whole.isChecked(),
                                   self.scope.currentData())
        pos = ed.textCursor().selectionStart()
        self.index = next((i for i, c in enumerate(self.matches) if c.selectionStart() >= pos), 0) \
            if self.matches else -1
        self._show()

    def _show(self, move: bool = False):
        ed = self.editor
        sels = [ed.make_selection(c, background=C.SELECT) for c in self.matches]
        if 0 <= self.index < len(self.matches):
            cur = self.matches[self.index]
            sels.append(ed.make_selection(cur, background=C.MUSTARD))
            if move:
                ed.setTextCursor(cur)
                ed.ensureCursorVisible()
        ed.set_layer("find", sels)
        n = len(self.matches)
        self.count.setText(f"{self.index + 1} of {n}" if n else ("No results" if self.find.text() else ""))

    def next(self):
        if self.matches:
            self.index = (self.index + 1) % len(self.matches) if self._on_match() else max(self.index, 0)
            self._show(move=True)

    def prev(self):
        if self.matches:
            self.index = (self.index - 1) % len(self.matches)
            self._show(move=True)

    def _on_match(self) -> bool:
        cur = self.editor.textCursor()
        return 0 <= self.index < len(self.matches) and \
            self.matches[self.index].selectionStart() == cur.selectionStart() and cur.hasSelection()

    def replace_one(self):
        if not self.matches:
            return
        if not self._on_match():
            self._show(move=True)
            return
        self.editor.replace_cursors([self.matches[self.index]], self.replace.text())
        self.refresh()
        self._show(move=True)

    def replace_all(self) -> int:
        n = self.editor.replace_cursors(self.matches, self.replace.text())
        self.refresh()
        self.count.setText(f"Replaced {n}")
        return n


# ======================================================================== go to
class GotoDialog(QDialog):
    """Ctrl+G: jump to a scene number or a page."""

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle("Go To")
        form = QFormLayout(self)
        form.setContentsMargins(22, 22, 22, 18)
        self.kind = QComboBox()
        self.kind.addItems(["Scene", "Page"])
        self.value = QLineEdit(placeholderText="e.g. 12 or 12A")
        form.addRow("Go to", self.kind)
        form.addRow("Number", self.value)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.go)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def go(self):
        if goto(self.editor, self.kind.currentText().lower(), self.value.text().strip()):
            self.accept()
        else:
            self.value.selectAll()
            self.value.setFocus()


def goto(editor, kind: str, value: str) -> bool:
    """Jump to scene `value` (its number, or its position if unnumbered) or page `value`."""
    if not value:
        return False
    if kind == "scene":
        scenes = editor.scenes()
        for i, (block, _heading, number, _page) in enumerate(scenes, 1):
            if (number or "").upper() == value.upper() or (not number and str(i) == value):
                editor.goto_block(block)
                return True
        return False
    if not value.isdigit():
        return False
    page = int(value)
    block = editor.document().firstBlock()
    from .pages import page_of
    while block.isValid():
        if page_of(editor.document(), block, editor.dpi) + 1 >= page:
            editor.goto_block(block.blockNumber())
            return True
        block = block.next()
    return False


# ======================================================================== command palette
def _score(query: str, text: str) -> int | None:
    """Fuzzy match: every typed letter must appear in order. Lower is better."""
    q, t = query.lower(), text.lower()
    if not q:
        return 0
    if q in t:
        return t.index(q)
    pos, gaps = -1, 0
    for ch in q:
        nxt = t.find(ch, pos + 1)
        if nxt < 0:
            return None
        gaps += nxt - pos - 1
        pos = nxt
    return 100 + gaps


class CommandPalette(QDialog):
    """Ctrl+Shift+P: type a few letters of any command or scene and press Enter."""

    def __init__(self, entries: list[tuple[str, str, object]], parent=None):
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("palette")
        self.entries = entries                    # (label, detail, callable)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        self.search = QLineEdit(placeholderText="Type a command or a scene…")
        self.list = QListWidget(objectName="paletteList")
        lay.addWidget(self.search)
        lay.addWidget(self.list)
        self.resize(560, 420)
        self.search.textChanged.connect(self._fill)
        self.search.returnPressed.connect(self._run)
        self.list.itemActivated.connect(lambda _: self._run())
        self.search.installEventFilter(self)
        self._fill("")

    def eventFilter(self, obj, e):            # noqa: N802
        if e.type() == e.Type.KeyPress and e.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            r = self.list.currentRow() + (1 if e.key() == Qt.Key.Key_Down else -1)
            self.list.setCurrentRow(max(0, min(self.list.count() - 1, r)))
            return True
        return super().eventFilter(obj, e)

    def _fill(self, q: str):
        self.list.clear()
        scored = []
        for i, (label, detail, fn) in enumerate(self.entries):
            s = _score(q, label)
            if s is not None:
                scored.append((s, i, label, detail, fn))
        for s, _i, label, detail, fn in sorted(scored)[:60]:
            it = QListWidgetItem(f"{label}" + (f"      {detail}" if detail else ""))
            it.setData(Qt.ItemDataRole.UserRole, fn)
            self.list.addItem(it)
        self.list.setCurrentRow(0)

    def _run(self):
        it = self.list.currentItem()
        if it:
            fn = it.data(Qt.ItemDataRole.UserRole)
            self.accept()
            QTimer.singleShot(0, fn)

    def showEvent(self, e):                   # noqa: N802
        super().showEvent(e)
        if self.parent():
            g = self.parent().geometry()
            self.move(g.center().x() - self.width() // 2, g.top() + 110)
        self.search.setFocus()


def palette_entries(window) -> list[tuple[str, str, object]]:
    """Every menu command plus every scene, for the command palette."""
    out = []

    def walk(menu, path):
        for a in menu.actions():
            if a.menu():
                walk(a.menu(), path + [a.menu().title().replace("&", "")])
            elif not a.isSeparator() and a.text() and a.isEnabled():
                keys = a.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
                out.append((a.text().replace("&", "").rstrip("…"), "  ".join([" › ".join(path), keys]).strip(),
                            a.trigger))
    for a in window.menuBar().actions():
        if a.menu():
            walk(a.menu(), [a.menu().title().replace("&", "")])
    ed = window.editor
    for i, (block, heading, number, page) in enumerate(ed.scenes(), 1):
        out.append((f"{number or i}  {heading}", f"Scene · p.{page}",
                    lambda b=block: (window.show_view("script"), ed.goto_block(b))))
    return out


# ======================================================================== rename character
class RenameDialog(QDialog):
    def __init__(self, names: list[str], current: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Rename Character")
        self.setMinimumWidth(400)
        form = QFormLayout(self)
        form.setContentsMargins(22, 22, 22, 18)
        form.setSpacing(10)
        self.old = QComboBox()
        self.old.addItems(names)
        if current in names:
            self.old.setCurrentText(current)
        self.new = QLineEdit()
        self.everywhere = QCheckBox("Also change it in action and dialogue")
        self.everywhere.setChecked(True)
        form.addRow("Character", self.old)
        form.addRow("New name", self.new)
        form.addRow("", self.everywhere)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        self.new.setFocus()


# ======================================================================== goals
class Goals:
    """A daily word goal. Only words you type count: opening or pasting a script doesn't."""

    TYPING = 2000        # a bigger jump between two checks can't be typing

    def __init__(self, settings, editor):
        self.settings = settings
        self.editor = editor
        self.day = dt.date.today().isoformat()
        self.today = self.history().get(self.day, 0)
        self.last: int | None = None

    @property
    def target(self) -> int:
        return int(self.settings.value("goalWords", 0) or 0)

    def history(self) -> dict:
        try:
            return json.loads(self.settings.value("goalHistory", "{}") or "{}")
        except ValueError:
            return {}

    def reset_baseline(self):
        """Called after a script is opened."""
        self.last = self.editor.word_count()

    def tick(self):
        words = self.editor.word_count()
        if dt.date.today().isoformat() != self.day:
            self.record()
            self.day, self.today = dt.date.today().isoformat(), 0
        pasted = getattr(self.editor, "_pasted", False)
        self.editor._pasted = False
        if self.last is not None and not pasted and 0 < words - self.last <= self.TYPING:
            self.today += words - self.last
        self.last = words

    def written_today(self) -> int:
        return self.today

    def record(self):
        """Remember today's progress (called on save and on close)."""
        hist = self.history()
        hist[self.day] = self.today
        self.settings.setValue("goalHistory", json.dumps(dict(sorted(hist.items())[-120:])))

    def streak(self) -> int:
        hist, target, n = self.history(), self.target, 0
        if not target:
            return 0
        hist[self.day] = self.today
        day = dt.date.today()
        if hist.get(day.isoformat(), 0) < target:
            day -= dt.timedelta(days=1)
        while hist.get(day.isoformat(), 0) >= target:
            n += 1
            day -= dt.timedelta(days=1)
        return n


class GoalWidget(QWidget):
    """Status-bar progress: a thin honey bar and '320 / 500 words'."""
    clicked = Signal()

    def __init__(self, goals: Goals, parent=None):
        super().__init__(parent)
        self.goals = goals
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 0, 6, 0)
        lay.setSpacing(6)
        self.bar = QProgressBar(objectName="goalBar")
        self.bar.setTextVisible(False)
        self.bar.setFixedSize(70, 6)
        self.label = QLabel()
        lay.addWidget(self.bar)
        lay.addWidget(self.label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Writing goal — click to change")
        self.update_view()

    def update_view(self):
        self.goals.tick()
        target = self.goals.target
        done = self.goals.written_today()
        if target:
            self.bar.setVisible(True)
            self.bar.setMaximum(target)
            self.bar.setValue(min(done, target))
            self.label.setText(f"{done} / {target} words" + ("  ✓" if done >= target else ""))
        else:
            self.bar.setVisible(False)
            self.label.setText(f"+{done} words today")

    def mousePressEvent(self, e):              # noqa: N802
        self.clicked.emit()


class GoalDialog(QDialog):
    def __init__(self, goals: Goals, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Writing Goal")
        form = QFormLayout(self)
        form.setContentsMargins(22, 22, 22, 18)
        form.setSpacing(10)
        self.words = QSpinBox()
        self.words.setRange(0, 20000)
        self.words.setSingleStep(100)
        self.words.setSpecialValueText("No goal")
        self.words.setValue(goals.target)
        form.addRow("Words per day", self.words)
        form.addRow("Written today", QLabel(str(goals.written_today())))
        form.addRow("Streak", QLabel(f"{goals.streak()} day(s) in a row"))
        last = sorted(goals.history().items())[-7:]
        if last:
            form.addRow("Last days", QLabel("   ".join(f"{d[5:]}: {n}" for d, n in last)))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)


# ======================================================================== spelling
class Speller:
    """English spelling (pyspellchecker) plus your own dictionary and character names."""

    def __init__(self, user_file: Path):
        self.user_file = user_file
        self._checker = None
        self.user: set[str] = set()
        self.ignored: set[str] = set()
        self.names: set[str] = set()
        self._cache: dict[str, bool] = {}
        try:
            self.user = {w.strip().lower() for w in user_file.read_text(encoding="utf-8").splitlines()
                         if w.strip()}
        except OSError:
            pass

    @property
    def available(self) -> bool:
        return self.checker is not None

    @property
    def checker(self):
        if self._checker is None:
            try:
                from spellchecker import SpellChecker
                self._checker = SpellChecker(distance=1)
            except Exception:                      # noqa: BLE001 - missing package: no spelling
                self._checker = False
        return self._checker or None

    def ok(self, word: str) -> bool:
        w = word.lower().strip("'’")
        if len(w) < 2 or w in SCREEN_WORDS or w in self.user or w in self.ignored or w in self.names:
            return True
        if w not in self._cache:
            chk = self.checker
            self._cache[w] = True if chk is None else (w in chk or w.replace("’", "'") in chk)
        return self._cache[w]

    def suggestions(self, word: str, n: int = 6) -> list[str]:
        chk = self.checker
        if chk is None:
            return []
        cands = chk.candidates(word.lower()) or set()
        ranked = sorted(cands, key=lambda c: -chk.word_usage_frequency(c))[:n]
        if word.isupper():
            return [c.upper() for c in ranked]
        if word[:1].isupper():
            return [c.capitalize() for c in ranked]
        return ranked

    def add(self, word: str):
        self.user.add(word.lower())
        self._cache.pop(word.lower(), None)
        self.user_file.parent.mkdir(parents=True, exist_ok=True)
        self.user_file.write_text("\n".join(sorted(self.user)) + "\n", encoding="utf-8")

    def ignore(self, word: str):
        self.ignored.add(word.lower())
        self._cache.pop(word.lower(), None)


class SpellHighlighter(QSyntaxHighlighter):
    """Red wavy underline under misspelled words, as you type."""

    def __init__(self, editor, speller: Speller):
        super().__init__(editor.document())
        self.editor = editor
        self.speller = speller
        self.fmt = QTextCharFormat()
        self.fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        self.fmt.setUnderlineColor(QColor("#D0453A"))

    def highlightBlock(self, text: str):       # noqa: N802
        etype = block_type(self.currentBlock())
        if etype in (T.IMAGE,) or not self.speller.available:
            return
        for m in WORD_RE.finditer(text):
            if not self.speller.ok(m.group(0)):
                self.setFormat(m.start(), m.end() - m.start(), self.fmt)

    def word_at(self, cur: QTextCursor) -> QTextCursor | None:
        block = cur.block()
        pos = cur.position() - block.position()
        for m in WORD_RE.finditer(block.text()):
            if m.start() <= pos <= m.end():
                if self.speller.ok(m.group(0)):
                    return None
                c = QTextCursor(block)
                c.setPosition(block.position() + m.start())
                c.setPosition(block.position() + m.end(), QTextCursor.MoveMode.KeepAnchor)
                return c
        return None

    def menu_actions(self, cur: QTextCursor) -> list:
        """Right-click: suggestions, Add to Dictionary, Ignore."""
        if self.document() is None:
            return []
        word_cur = self.word_at(cur)
        if word_cur is None:
            return []
        word = word_cur.selectedText()
        if block_type(cur.block()) in CAPS_TYPES:
            word = word.upper()
        acts = []
        for s in self.speller.suggestions(word):
            a = QAction(s)
            f = a.font()
            f.setBold(True)
            a.setFont(f)
            a.triggered.connect(lambda _=False, c=word_cur, s=s: self._replace(c, s))
            acts.append(a)
        if not acts:
            a = QAction("No suggestions")
            a.setEnabled(False)
            acts.append(a)
        acts.append(None)
        add = QAction(icon("check"), f"Add “{word}” to Dictionary")
        add.triggered.connect(lambda: (self.speller.add(word), self.rehighlight()))
        ign = QAction("Ignore All")
        ign.triggered.connect(lambda: (self.speller.ignore(word), self.rehighlight()))
        return acts + [add, ign]

    def _replace(self, cur: QTextCursor, text: str):
        fmt = QTextCursor(cur)
        fmt.setPosition(cur.selectionStart() + 1)
        cur.insertText(text, fmt.charFormat())
