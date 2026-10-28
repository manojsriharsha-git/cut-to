"""
Insights: numbers and pictures of the script (who talks, how much, where, how long)
plus a table read that speaks the script aloud with a different voice per character.

Charts are drawn with QPainter in the app's own colours: one hue (honey) for
magnitude, quiet grid lines, values in ink, hover tooltips on every mark.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, QRectF, QPointF, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QFontMetricsF, QTextCursor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame,
                               QGridLayout, QPushButton, QTableWidget, QTableWidgetItem,
                               QHeaderView, QDialog, QComboBox, QSlider, QCheckBox, QFormLayout,
                               QAbstractItemView, QToolTip)

from ..core import reports
from ..core.analysis import analyse, Analysis
from ..core.ir import T
from ..core.smart import base_name
from .pages import block_type
from .theme import C

BAR = "#DFAF40"          # mustard: the one hue for magnitude
BAR_SOFT = "#E4C85D"


def _font(size=9, bold=False):
    f = QFont()
    f.setPointSizeF(size)
    f.setBold(bold)
    return f


class Tile(QFrame):
    def __init__(self, value: str, name: str, sub: str = ""):
        super().__init__(objectName="tile")
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 12, 16, 12)
        v.setSpacing(2)
        a = QLabel(value, objectName="statValue")
        b = QLabel(name.upper(), objectName="statName")
        v.addWidget(a)
        v.addWidget(b)
        if sub:
            v.addWidget(QLabel(sub, objectName="hint"))


class Chart(QWidget):
    """Base: title, hover tooltip from hit rectangles."""
    title = ""

    def __init__(self, height=260):
        super().__init__()
        self.setMinimumHeight(height)
        self.setMouseTracking(True)
        self.hits: list[tuple[QRectF, str]] = []
        self.a: Analysis | None = None

    def set_data(self, a: Analysis):
        self.a = a
        self.update()

    def mouseMoveEvent(self, e):                    # noqa: N802
        for r, tip in self.hits:
            if r.contains(e.position()):
                QToolTip.showText(e.globalPosition().toPoint(), tip, self)
                return
        QToolTip.hideText()

    def frame(self, p: QPainter) -> QRectF:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(C.LINE), 1))
        p.setBrush(QColor(C.PAPER))
        p.drawRoundedRect(r, 10, 10)
        p.setPen(QColor(C.INK))
        p.setFont(_font(10, True))
        p.drawText(QRectF(r.left() + 16, r.top() + 10, r.width() - 32, 20), self.title)
        self.hits = []
        return r.adjusted(16, 40, -16, -14)


class DialogueChart(Chart):
    title = "Dialogue by character (words)"

    def paintEvent(self, e):                        # noqa: N802
        p = QPainter(self)
        r = self.frame(p)
        if not self.a or not self.a.characters:
            return
        rows = self.a.characters[:12]
        top = max(1, rows[0].words)
        fm = QFontMetricsF(_font(9))
        label_w = min(160, max(fm.horizontalAdvance(c.name) for c in rows) + 12)
        h = min(22.0, r.height() / len(rows))
        p.setFont(_font(9))
        total = max(1, self.a.dialogue_words)
        for i, c in enumerate(rows):
            y = r.top() + i * h
            p.setPen(QColor(C.INK))
            p.drawText(QRectF(r.left(), y, label_w - 8, h), int(Qt.AlignmentFlag.AlignRight |
                                                                 Qt.AlignmentFlag.AlignVCenter), c.name)
            w = (r.width() - label_w - 70) * c.words / top
            bar = QRectF(r.left() + label_w, y + h * 0.2, max(w, 2), h * 0.6)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(BAR))
            p.drawRoundedRect(bar, 3, 3)
            p.setPen(QColor(C.INK_SOFT))
            p.drawText(QRectF(bar.right() + 6, y, 70, h), int(Qt.AlignmentFlag.AlignVCenter),
                       f"{c.words}  ({100 * c.words / total:.0f}%)")
            self.hits.append((QRectF(r.left(), y, r.width(), h),
                              f"{c.name}: {c.words} words in {c.speeches} speeches, {len(c.scenes)} scenes"))


class SceneLengthChart(Chart):
    title = "Scene length (pages)"

    def paintEvent(self, e):                        # noqa: N802
        p = QPainter(self)
        r = self.frame(p)
        if not self.a or not self.a.scene_lengths:
            return
        vals = self.a.scene_lengths
        top = max(max(vals), 0.125)
        top = math.ceil(top * 2) / 2
        base = r.bottom() - 18
        p.setFont(_font(8))
        for k in range(0, 5):
            v = top * k / 4
            y = base - (base - r.top()) * k / 4
            p.setPen(QPen(QColor(C.LINE), 1))
            p.drawLine(QPointF(r.left() + 30, y), QPointF(r.right(), y))
            p.setPen(QColor(C.INK_SOFT))
            p.drawText(QRectF(r.left(), y - 8, 26, 16), int(Qt.AlignmentFlag.AlignRight), f"{v:g}")
        n = len(vals)
        step = (r.width() - 34) / n
        bw = max(2.0, step - 2)
        for i, v in enumerate(vals):
            x = r.left() + 34 + i * step
            hh = (base - r.top()) * v / top
            bar = QRectF(x, base - hh, bw, hh)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(BAR))
            p.drawRoundedRect(bar, min(3, bw / 2), min(3, bw / 2))
            self.hits.append((QRectF(x, r.top(), step, base - r.top()),
                              f"Scene {self.a.scene_labels[i]}: {reports.eighths(v)} pages"))
            if n <= 40 or i % max(1, n // 20) == 0:
                p.setPen(QColor(C.INK_SOFT))
                p.drawText(QRectF(x - 10, base + 2, bw + 20, 14), int(Qt.AlignmentFlag.AlignHCenter),
                           self.a.scene_labels[i])


class PresenceChart(Chart):
    title = "Who speaks in which scene"

    def paintEvent(self, e):                        # noqa: N802
        p = QPainter(self)
        r = self.frame(p)
        if not self.a or not self.a.characters or not self.a.scenes:
            return
        rows = self.a.characters[:12]
        fm = QFontMetricsF(_font(9))
        label_w = min(160, max(fm.horizontalAdvance(c.name) for c in rows) + 12)
        h = min(20.0, r.height() / len(rows))
        cw = (r.width() - label_w) / self.a.scenes
        p.setFont(_font(9))
        for i, c in enumerate(rows):
            y = r.top() + i * h
            p.setPen(QColor(C.INK))
            p.drawText(QRectF(r.left(), y, label_w - 8, h), int(Qt.AlignmentFlag.AlignRight |
                                                                 Qt.AlignmentFlag.AlignVCenter), c.name)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C.CREAM))
            p.drawRect(QRectF(r.left() + label_w, y + 2, r.width() - label_w, h - 4))
            p.setBrush(QColor(BAR))
            for s, on in enumerate(self.a.presence[i]):
                if on:
                    cell = QRectF(r.left() + label_w + s * cw, y + 2, max(cw - 1, 1.5), h - 4)
                    p.drawRect(cell)
                    self.hits.append((cell.adjusted(-1, -2, 1, 2),
                                      f"{c.name} speaks in scene {self.a.scene_labels[s]}"))


class TalkChart(Chart):
    title = "Who talks to whom"

    def paintEvent(self, e):                        # noqa: N802
        p = QPainter(self)
        r = self.frame(p)
        if not self.a or len(self.a.characters) < 2:
            p.setPen(QColor(C.INK_SOFT))
            p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), "Needs at least two speaking characters")
            return
        people = [c.name for c in self.a.characters[:10]]
        cx, cy = r.center().x(), r.center().y()
        rad = min(r.width(), r.height()) / 2 - 40
        pos = {n: QPointF(cx + rad * math.cos(2 * math.pi * i / len(people) - math.pi / 2),
                          cy + rad * math.sin(2 * math.pi * i / len(people) - math.pi / 2))
               for i, n in enumerate(people)}
        talks = {k: v for k, v in self.a.talks.items() if k[0] in pos and k[1] in pos}
        top = max(talks.values(), default=1)
        for (a, b), v in sorted(talks.items(), key=lambda kv: kv[1]):
            col = QColor(C.CARAMEL)
            col.setAlpha(int(70 + 150 * v / top))
            p.setPen(QPen(col, 1 + 7 * v / top, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(pos[a], pos[b])
            mid = (pos[a] + pos[b]) / 2
            self.hits.append((QRectF(mid.x() - 10, mid.y() - 10, 20, 20), f"{a} ↔ {b}: {v} exchanges"))
        words = {c.name: c.words for c in self.a.characters}
        wmax = max(words.values(), default=1) or 1
        p.setFont(_font(8, True))
        for n, pt in pos.items():
            s = 8 + 14 * math.sqrt(words.get(n, 0) / wmax)
            p.setPen(QPen(QColor(C.PAPER), 2))
            p.setBrush(QColor(BAR))
            p.drawEllipse(pt, s, s)
            p.setPen(QColor(C.INK))
            out = QPointF(pt.x() - cx, pt.y() - cy)
            ln = math.hypot(out.x(), out.y()) or 1
            lp = pt + QPointF(out.x() / ln * (s + 14), out.y() / ln * (s + 10))
            p.drawText(QRectF(lp.x() - 60, lp.y() - 8, 120, 16), int(Qt.AlignmentFlag.AlignCenter), n)
            self.hits.append((QRectF(pt.x() - s, pt.y() - s, 2 * s, 2 * s), f"{n}: {words.get(n, 0)} words"))


# ======================================================================== view
class InsightsView(QWidget):
    def __init__(self, feature):
        super().__init__()
        self.f = feature
        self.editor = feature.editor
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget(objectName="insights")
        scroll.setWidget(body)
        self.lay = QVBoxLayout(body)
        self.lay.setContentsMargins(22, 16, 22, 22)
        self.lay.setSpacing(14)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Insights", objectName="viewTitle"))
        bar.addStretch(1)
        read = QPushButton("Table Read…", objectName="primary")
        read.clicked.connect(feature.table_read)
        bar.addWidget(read)
        self.lay.addLayout(bar)
        self.tiles = QHBoxLayout()
        self.tiles.setSpacing(12)
        self.lay.addLayout(self.tiles)
        grid = QGridLayout()
        grid.setSpacing(14)
        self.dialogue, self.lengths = DialogueChart(300), SceneLengthChart(300)
        self.presence, self.talk = PresenceChart(300), TalkChart(340)
        grid.addWidget(self.dialogue, 0, 0)
        grid.addWidget(self.talk, 0, 1)
        grid.addWidget(self.lengths, 1, 0, 1, 2)
        grid.addWidget(self.presence, 2, 0, 1, 2)
        self.lay.addLayout(grid)
        self.lay.addWidget(QLabel("Screen time", objectName="sectionTitle"))
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Character", "Speeches", "Words", "Scenes",
                                              "On screen (est.)", "Speaking (est.)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setMinimumHeight(260)
        self.lay.addWidget(self.table)
        self.a = None

    def enter_view(self):
        self.refresh()

    def refresh(self):
        ed = self.editor
        scenes = ed.scenes()
        a = analyse(ed.element_pairs(), ed.scene_lengths(), ed.page_count(), [s[2] for s in scenes])
        self.a = a
        while self.tiles.count():
            w = self.tiles.takeAt(0).widget()
            if w:
                w.deleteLater()
        ints = sum(v for k, v in a.int_ext.items() if k.startswith("INT") and "EXT" not in k)
        exts = sum(v for k, v in a.int_ext.items() if k.startswith(("EXT", "EST")))
        night_words = ("NIGHT", "EVENING", "DUSK", "MIDNIGHT")
        nights = sum(v for k, v in a.day_night.items() if any(n in k for n in night_words))
        days = sum(v for k, v in a.day_night.items() if any(d in k for d in ("DAY", "MORNING", "AFTERNOON",
                                                                               "DAWN", "NOON")))
        lead = a.characters[0].name if a.characters else "—"
        for value, name, sub in ((str(a.pages), "Pages", f"about {a.runtime} min on screen"),
                                 (str(a.scenes), "Scenes", f"{len(a.characters)} speaking parts"),
                                 (f"{a.dialogue_share}%", "Dialogue", f"{a.words} words in all"),
                                 (f"{ints} / {exts}", "Int / Ext", "scenes inside / outside"),
                                 (f"{days} / {nights}", "Day / Night", "scenes by light"),
                                 (lead, "Most lines", "")):
            self.tiles.addWidget(Tile(value, name, sub))
        self.tiles.addStretch(1)
        for chart in (self.dialogue, self.lengths, self.presence, self.talk):
            chart.set_data(a)
        self.presence.setMinimumHeight(60 + 20 * min(12, len(a.characters)))
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for c in a.characters:
            r = self.table.rowCount()
            self.table.insertRow(r)
            vals = [c.name, c.speeches, c.words, len(c.scenes), f"{c.pages:.1f} min",
                    f"{c.dialogue_minutes:.1f} min"]
            for col, v in enumerate(vals):
                it = QTableWidgetItem()
                it.setData(Qt.ItemDataRole.DisplayRole, v)
                self.table.setItem(r, col, it)
        self.table.setSortingEnabled(True)


# ======================================================================== table read
class TableRead(QDialog):
    """Reads the script aloud: a voice per character, a narrator for action."""

    def __init__(self, window, engine: str | None = None):
        super().__init__(window)
        self.window = window
        self.editor = window.editor
        self.setWindowTitle("Table Read")
        self.setMinimumWidth(480)
        self.tts = None
        try:
            from PySide6.QtTextToSpeech import QTextToSpeech
            self.tts = QTextToSpeech(engine, self) if engine else QTextToSpeech(self)
        except Exception:                            # noqa: BLE001 - no speech engine on this PC
            self.tts = None
        self.voices = list(self.tts.availableVoices()) if self.tts is not None else []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 14)
        if not self.voices:
            lay.addWidget(QLabel("No text-to-speech voices were found on this computer.\n"
                                 "On Windows: Settings → Time & Language → Speech → Add voices."))
            close = QPushButton("Close")
            close.clicked.connect(self.reject)
            lay.addWidget(close)
            return
        form = QFormLayout()
        self.narrator = QComboBox()
        for v in self.voices:
            self.narrator.addItem(v.name())
        form.addRow("Narrator (action)", self.narrator)
        self.cast: dict[str, QComboBox] = {}
        names = [c for c in self.editor.to_script().characters()][:14]
        for i, n in enumerate(names):
            box = QComboBox()
            for v in self.voices:
                box.addItem(v.name())
            box.setCurrentIndex((i + 1) % len(self.voices))
            form.addRow(n, box)
            self.cast[n] = box
        self.read_action = QCheckBox("Read action and scene headings")
        self.read_action.setChecked(True)
        form.addRow("", self.read_action)
        self.rate = QSlider(Qt.Orientation.Horizontal)
        self.rate.setRange(-5, 5)
        self.rate.setValue(0)
        form.addRow("Speed", self.rate)
        lay.addLayout(form)
        row = QHBoxLayout()
        self.play = QPushButton("Play from Cursor", objectName="primary")
        self.pause = QPushButton("Pause")
        stop = QPushButton("Stop")
        row.addWidget(self.play)
        row.addWidget(self.pause)
        row.addWidget(stop)
        lay.addLayout(row)
        self.status = QLabel(objectName="hint")
        lay.addWidget(self.status)
        self.play.clicked.connect(self.start)
        self.pause.clicked.connect(self.toggle_pause)
        stop.clicked.connect(self.stop)
        self.tts.stateChanged.connect(self._state)
        self.block = None
        self.running = False
        self.speaker = None

    def start(self):
        self.block = self.editor.textCursor().block()
        self.running = True
        self.speaker = None
        self._speak_current()

    def _speak_current(self):
        while self.running and self.block is not None and self.block.isValid():
            etype = block_type(self.block)
            text = self.block.text().strip()
            if etype == T.CHARACTER:
                self.speaker = base_name(text)
                self.block = self.block.next()
                continue
            if etype not in (T.DIALOGUE, T.PARENTHETICAL):
                self.speaker = None
            speak = text and etype not in (T.PARENTHETICAL, T.NOTE, T.SECTION, T.SYNOPSIS, T.IMAGE) and \
                (etype == T.DIALOGUE or self.read_action.isChecked())
            if speak:
                box = self.cast.get(self.speaker) if etype == T.DIALOGUE else None
                idx = box.currentIndex() if box else self.narrator.currentIndex()
                self.tts.setVoice(self.voices[idx])
                self.tts.setRate(self.rate.value() / 10)
                self._highlight(self.block)
                self.status.setText(f"{self.speaker or 'Narrator'}: {text[:60]}")
                self.tts.say(text)
                return
            self.block = self.block.next()
        self.stop()

    def _state(self, state):
        from PySide6.QtTextToSpeech import QTextToSpeech
        if state == QTextToSpeech.State.Ready and self.running and self.block is not None:
            self.block = self.block.next()
            QTimer.singleShot(150, self._speak_current)

    def _highlight(self, block):
        sel = self.editor.make_selection(QTextCursor(block), background=C.SELECT, full_width=True)
        self.editor.set_layer("current", [sel])
        cur = QTextCursor(block)
        self.editor.setTextCursor(cur)
        self.editor.ensureCursorVisible()

    def toggle_pause(self):
        from PySide6.QtTextToSpeech import QTextToSpeech
        if self.tts.state() == QTextToSpeech.State.Speaking:
            self.tts.pause()
            self.pause.setText("Resume")
        else:
            self.tts.resume()
            self.pause.setText("Pause")

    def stop(self):
        self.running = False
        if self.tts is not None:
            self.tts.stop()
        self.editor.set_layer("current", [])
        if hasattr(self, "status"):
            self.status.setText("Stopped")

    def done(self, r):
        self.stop()
        super().done(r)


class Insights:
    def __init__(self, window):
        self.window = window
        self.editor = window.editor
        self.view = InsightsView(self)
        window.add_view("insights", "Insights", "chart", self.view)
        act = window._a("Table Read…", self.table_read, None, "speak")
        window.menus["tools"].addAction(act)
        window.menus["tools"].addAction("Insights", lambda: window.show_view("insights"))

    def table_read(self):
        TableRead(self.window).exec()

    def theme_changed(self):
        self.view.update()

