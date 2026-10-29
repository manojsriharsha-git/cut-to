"""
The main window: menus, toolbar, the view rail (Script, Cards, Beat Board, Characters,
Production, Insights), the status bar, files, PDF and printing.

Bigger feature areas live in their own modules and plug themselves in:
writing.py (find, goals, spelling...), planning.py, rewrites.py, production.py, insights.py.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QStandardPaths, QTimer, QSize, QUrl, QLockFile
from PySide6.QtGui import (QAction, QIcon, QKeySequence, QFont, QPixmap, QPainter,
                           QColor, QDesktopServices, QActionGroup)
from PySide6.QtPrintSupport import QPrinter, QPrintDialog, QPrintPreviewDialog
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QSplitter, QLabel, QToolBar,
                               QComboBox, QStatusBar, QFileDialog, QMessageBox, QDialog,
                               QFormLayout, QLineEdit, QPlainTextEdit, QDialogButtonBox,
                               QSizePolicy, QToolButton, QMenu, QPushButton, QColorDialog,
                               QVBoxLayout, QHBoxLayout, QFrame, QStackedWidget, QButtonGroup,
                               QInputDialog)

from .. import __app_name__, __app_id__, __version__
from ..core.history import Recovery, History
from ..core.ir import Script
from ..core.smart import SmartMemory
from ..formats import load, save, loses_content, open_filter, SAVE_FILTERS, EXPORTS, NATIVE
from ..resources import resource_path
from .editor import ScreenplayEditor, SHORTCUT_TYPES
from .icons import icon
from .navigator import Navigator, ReportsDialog
from .pages import export_pdf, render, letter_layout
from .theme import C, THEMES, apply_theme, build_qss
from .fonts import load_all, font_groups, add_font_file, GET_MORE_URL, is_typewriter
from .writing import (FindBar, GotoDialog, CommandPalette, palette_entries, RenameDialog, Goals,
                      GoalWidget, GoalDialog, Speller, SpellHighlighter)

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
TITLE_KEYS = ["Title", "Credit", "Author", "Source", "Draft date", "Contact"]
TEXT_COLORS = [("Automatic", None), ("Red", "#C0392B"), ("Blue", "#2F6FA8"),
               ("Green", "#3E8E5E"), ("Caramel", C.CARAMEL), ("Plum", "#7D5BA6")]
HIGHLIGHTS = [("Honey", "#F3E3A3"), ("Blush", "#EED9D4"), ("Salmon", C.SALMON),
              ("Mint", "#D4EBDD"), ("Sky", "#D6E6F5"), ("No highlight", None)]


def swatch(color: str | None) -> QIcon:
    px = QPixmap(28, 28)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor(C.LINE))
    p.setBrush(QColor(color) if color else QColor(C.PAPER))
    p.drawEllipse(4, 4, 20, 20)
    if not color:
        p.setPen(QColor(C.SALMON))
        p.drawLine(8, 20, 20, 8)
    p.end()
    return QIcon(px)


def data_dir() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation))


class TitlePageDialog(QDialog):
    def __init__(self, title_page: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Title Page")
        self.setMinimumWidth(440)
        self._orig = title_page
        current = {k.lower(): v for k, v in title_page}
        form = QFormLayout(self)
        form.setContentsMargins(22, 22, 22, 18)
        form.setSpacing(10)
        self.fields = {}
        for k in TITLE_KEYS:
            w = QPlainTextEdit() if k == "Contact" else QLineEdit()
            if k == "Contact":
                w.setFixedHeight(70)
                w.setPlainText(current.get(k.lower(), ""))
            else:
                w.setText(current.get(k.lower(), ""))
            if k == "Credit" and not current.get("credit"):
                w.setPlaceholderText("Written by")
            form.addRow(k, w)
            self.fields[k] = w
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Save |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def result_title_page(self) -> list[tuple[str, str]]:
        out = []
        for k, w in self.fields.items():
            v = w.toPlainText() if isinstance(w, QPlainTextEdit) else w.text()
            if v.strip():
                out.append((k, v.strip()))
        known = {k.lower() for k in TITLE_KEYS}
        out += [(k, v) for k, v in self._orig if k.lower() not in known]
        return out


class LinkDialog(QDialog):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Insert Link")
        self.setMinimumWidth(420)
        form = QFormLayout(self)
        form.setContentsMargins(22, 22, 22, 18)
        form.setSpacing(10)
        self.text = QLineEdit(text)
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://")
        form.addRow("Text", self.text)
        form.addRow("Address", self.url)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                              QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        (self.url if text else self.text).setFocus()


class FocusExitButton(QToolButton):
    """A quiet ✕ in the corner while Focus Mode is on. Hovering it spells out what it does."""

    def __init__(self, parent):
        super().__init__(parent, objectName="focusExit")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Exit Focus Mode  (Ctrl+Shift+F or Esc)")
        self.setText("✕")

    def enterEvent(self, e):                       # noqa: N802
        self.setText("✕  Exit Focus Mode")
        self._reposition()
        super().enterEvent(e)

    def leaveEvent(self, e):                       # noqa: N802
        self.setText("✕")
        self._reposition()
        super().leaveEvent(e)

    def _reposition(self):
        right = self.x() + self.width()             # keep the right edge where it was
        self.adjustSize()
        self.move(right - self.width(), self.y())


class MainWindow(QMainWindow):
    def __init__(self, memory: SmartMemory, data: Path | None = None):
        super().__init__()
        self.memory = memory
        self.path: Path | None = None
        self.settings = QSettings()
        self.data = data or data_dir()
        self.text_color = "#C0392B"
        self.highlight = "#F3E3A3"
        self.session = uuid.uuid4().hex[:12]
        self.recovery = Recovery(self.data)
        self.recovery.dir.mkdir(parents=True, exist_ok=True)
        self._lock = QLockFile(str(self.recovery.dir / f"{self.session}.lock"))
        self._lock.lock()                         # tells other Cut To: windows we're alive
        self.history = History(self.data)
        self._icons: dict[QAction, str] = {}
        self.views: dict[str, tuple[QWidget, QToolButton]] = {}
        self.menus: dict[str, QMenu] = {}

        self.editor = ScreenplayEditor(memory)
        self.navigator = Navigator(self.editor)
        self.navigator.jump.connect(self.editor.goto_block)
        self.findbar = FindBar(self.editor)

        script_page = QWidget(objectName="scriptPage")
        sp = QVBoxLayout(script_page)
        sp.setContentsMargins(0, 0, 0, 0)
        sp.setSpacing(0)
        self.script_top = QVBoxLayout()           # the scene ribbon goes here
        sp.addLayout(self.script_top)
        sp.addWidget(self.editor, 1)
        sp.addWidget(self.findbar)

        self.stack = QStackedWidget()
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.addWidget(self.navigator)
        self.splitter.addWidget(self.stack)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([270, 1000])
        self.rail = QFrame(objectName="rail")
        self.rail_lay = QVBoxLayout(self.rail)
        logo = QLabel(objectName="railLogo")
        logo.setPixmap(QIcon(resource_path("icons", "cutto.png")).pixmap(QSize(34, 34)))
        logo.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        logo.setToolTip(__app_name__)
        self.rail_lay.setContentsMargins(6, 10, 6, 10)
        self.rail_lay.setSpacing(4)
        self.rail_lay.addWidget(logo)
        self.rail_lay.addSpacing(10)
        self.rail_group = QButtonGroup(self)
        self.rail_group.setExclusive(True)
        central = QWidget(objectName="central")
        row = QHBoxLayout(central)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.rail)
        row.addWidget(self.splitter, 1)
        self.setCentralWidget(central)

        self._build_actions()
        self._build_toolbar()
        self._build_statusbar()
        self._build_menus()
        self.add_view("script", "Script", "script", script_page)

        # writing comfort
        self.goals = Goals(self.settings, self.editor)
        self.goal_widget = GoalWidget(self.goals)
        self.goal_widget.clicked.connect(self.edit_goal)
        self.statusBar().insertPermanentWidget(2, self.goal_widget)
        self.speller = Speller(self.data / "dictionary.txt")
        self.editor.spell = None
        self.editor.context_hooks.append(self._spell_menu)
        self.set_auto_capitalize(self.settings.value("autoCapitalize", "true") == "true")
        if self.settings.value("spelling", "true") == "true":
            QTimer.singleShot(400, lambda: self.set_spelling(True))

        # the bigger feature areas plug themselves in (views, menus, panels)
        from .planning import Planning
        from .rewrites import Rewrites
        from .production import Production
        from .insights import Insights
        self.features = [Planning(self), Rewrites(self), Production(self), Insights(self)]
        self.rail_lay.addStretch(1)

        self.editor.elementChanged.connect(self._on_element)
        self.editor.formatChanged.connect(self._sync_format_buttons)
        self.editor.hintChanged.connect(self.hint_label.setText)
        self.editor.pageChanged.connect(self._on_page)
        self.editor.structureChanged.connect(self._refresh_structure)
        self.editor.cursorPositionChanged.connect(
            lambda: self.navigator.sync(self.editor.textCursor().blockNumber()))
        self.editor.document().modificationChanged.connect(lambda _: self._update_title())

        self.autosave_timer = QTimer(self, interval=60_000)
        self.autosave_timer.timeout.connect(self.autosave)
        self.autosave_timer.start()

        geo = self.settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        else:
            self.resize(1320, 880)
        self.editor.set_zoom(float(self.settings.value("zoom", 1.0)))
        self._update_zoom_label()
        self._update_title()
        self._refresh_structure()
        self.show_view("script")
        self.goals.reset_baseline()

    # ================================================================ actions
    def _a(self, text, slot, shortcut=None, icon_name=None, tip=None, widget_only=False,
           checkable=False):
        a = QAction(text, self)
        if icon_name:
            a.setIcon(icon(icon_name))
            self._icons[a] = icon_name
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
            if widget_only:                       # the editor handles this key itself
                a.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        a.setCheckable(checkable)
        label = tip or text.replace("&", "").rstrip("…")
        keys = a.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
        a.setToolTip(f"{label}  ({keys})" if keys else label)
        a.triggered.connect(slot)
        if not widget_only:
            self.addAction(a)
        return a

    def _build_actions(self):
        e = self.editor
        S = QKeySequence.StandardKey
        self.act = {
            "new": self._a("New", self.new_file, S.New, "new"),
            "open": self._a("Open…", self.open_file, S.Open, "open"),
            "save": self._a("Save", self.save_file, S.Save, "save"),
            "save_as": self._a("Save As…", self.save_as, "Ctrl+Shift+S"),
            "pdf": self._a("Export PDF…", self.export_pdf, "Ctrl+Shift+E", "pdf"),
            "print": self._a("Print…", self.print_script, S.Print, "print"),
            "preview": self._a("Print Preview…", self.print_preview, "Ctrl+Alt+P"),
            "quit": self._a("Quit", self.close, "Ctrl+Q"),
            "undo": self._a("Undo", e.undo, S.Undo, "undo"),
            "redo": self._a("Redo", e.redo, S.Redo, "redo"),
            "bold": self._a("Bold", lambda: e.toggle_style("bold"), "Ctrl+B", "bold",
                            widget_only=True, checkable=True),
            "italic": self._a("Italic", lambda: e.toggle_style("italic"), "Ctrl+I", "italic",
                              widget_only=True, checkable=True),
            "underline": self._a("Underline", lambda: e.toggle_style("underline"), "Ctrl+U",
                                 "underline", widget_only=True, checkable=True),
            "strike": self._a("Strikethrough", lambda: e.toggle_style("strike"), "Ctrl+Shift+X",
                              "strike", checkable=True),
            "clear": self._a("Clear Formatting", e.clear_formatting, "Ctrl+Space", "clear"),
            "image": self._a("Image…", self.insert_image, "Ctrl+Shift+I", "image", "Insert image"),
            "link": self._a("Link…", self.insert_link, "Ctrl+K", "link", "Insert link"),
            "pagebreak": self._a("Page Break", e.insert_page_break, "Ctrl+Return", "pagebreak",
                                 "Insert page break", widget_only=True),
            "nobreak": self._a("Remove Page Break", e.remove_page_break),
            "number": self._a("Number Scenes", self.number_scenes, None, "scenes_num"),
            "unnumber": self._a("Remove Scene Numbers", e.clear_scene_numbers),
            "title": self._a("Title Page…", self.edit_title_page, None, "title"),
            "reports": self._a("Reports…", self.show_reports, "Ctrl+Shift+R", "reports"),
            "sidebar": self._a("Navigator", self._toggle_sidebar, "Ctrl+\\", "sidebar",
                               checkable=True),
            "zoom_in": self._a("Zoom In", lambda: self._zoom(1.1), S.ZoomIn, "zoom_in"),
            "zoom_out": self._a("Zoom Out", lambda: self._zoom(1 / 1.1), S.ZoomOut, "zoom_out"),
            "zoom_100": self._a("Actual Size", lambda: self._zoom(None), "Ctrl+0"),
            # writing comfort
            "find": self._a("Find…", lambda: self.open_find(False), S.Find, "search"),
            "replace": self._a("Find and Replace…", lambda: self.open_find(True), "Ctrl+H"),
            "find_next": self._a("Find Next", self.findbar.next, "F3"),
            "find_prev": self._a("Find Previous", self.findbar.prev, "Shift+F3"),
            "goto": self._a("Go To Scene or Page…", self.goto_dialog, "Ctrl+G"),
            "palette": self._a("Command Palette…", self.command_palette, "Ctrl+Shift+P", "command"),
            "rename": self._a("Rename Character…", self.rename_character, None),
            "spelling": self._a("Check Spelling as You Type", lambda on: self.set_spelling(on),
                                "F7", checkable=True),
            "autocap": self._a("Capitalize Sentences Automatically", self.set_auto_capitalize,
                               None, checkable=True,
                               tip="Action and dialogue: a capital letter at the start of each sentence"),
            "focus": self._a("Focus Mode", self.toggle_focus, "Ctrl+Shift+F", "focus", checkable=True),
            "typewriter": self._a("Typewriter Scrolling", self.toggle_typewriter, "Ctrl+Shift+T",
                                  checkable=True),
            "fullscreen": self._a("Full Screen", self.toggle_fullscreen, "F11", checkable=True),
            "goal": self._a("Writing Goal…", self.edit_goal, None),
            "history": self._a("Version History…", self.show_history, None, "history"),
            "save_version": self._a("Save Version…", self.save_version, None),
        }
        self.act["sidebar"].setChecked(True)
        self.case_menu = QMenu("Change Case", self)
        for label, mode in (("UPPERCASE", "upper"), ("lowercase", "lower"), ("Title Case", "title")):
            self.case_menu.addAction(label).triggered.connect(
                lambda _=False, m=mode: e.change_case(m))
        self.theme_group = QActionGroup(self)
        self.theme_actions = {}
        for name in THEMES:
            a = QAction(name, self, checkable=True)
            a.setChecked(name == C.NAME)
            a.triggered.connect(lambda _=False, n=name: self.set_theme(n))
            self.theme_group.addAction(a)
            self.theme_actions[name] = a

    def _color_button(self, name: str, choices, apply, current) -> QToolButton:
        btn = QToolButton()
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        btn.setIcon(icon(name, swatch=current()))
        btn.setToolTip("Text colour" if name == "color" else "Highlight")
        menu = QMenu(btn)
        for label, value in choices:
            a = menu.addAction(swatch(value), label)
            a.triggered.connect(lambda _=False, v=value: apply(v, btn, name))
        menu.addSeparator()
        menu.addAction("More colours…").triggered.connect(
            lambda: (lambda c: c.isValid() and apply(c.name().upper(), btn, name))(
                QColorDialog.getColor(QColor(current()), self)))
        btn.setMenu(menu)
        btn.clicked.connect(lambda: apply(current(), btn, name))
        return btn

    def _apply_color(self, value, btn, name):
        if name == "color":
            if value:
                self.text_color = value
            self.editor.set_text_color(value)
            btn.setIcon(icon("color", swatch=self.text_color))
        else:
            if value:
                self.highlight = value
            self.editor.set_highlight(value)
            btn.setIcon(icon("highlight", swatch=self.highlight))
        self.editor.setFocus()

    def _build_toolbar(self):
        tb = QToolBar("Main", objectName="main")
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setIconSize(QSize(20, 20))
        self.addToolBar(tb)
        self.toolbar = tb
        for k in ("new", "open", "save"):
            tb.addAction(self.act[k])
        tb.addSeparator()
        tb.addAction(self.act["undo"])
        tb.addAction(self.act["redo"])
        tb.addSeparator()
        self.type_combo = QComboBox()
        for i, t in enumerate(SHORTCUT_TYPES, 1):
            self.type_combo.addItem(t, t)
            self.type_combo.setItemData(i - 1, f"Ctrl+{i}", Qt.ItemDataRole.ToolTipRole)
        self.type_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.type_combo.activated.connect(
            lambda i: (self.editor.set_current_type(self.type_combo.itemData(i)),
                       self.editor.setFocus()))
        # always wide enough for the longest name ("Parenthetical", "Scene Heading"),
        # whatever font size the theme uses
        self.type_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        tb.addWidget(self.type_combo)
        self.font_combo = QComboBox(objectName="fontCombo")
        self.font_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.font_combo.setMaxVisibleItems(24)
        self.font_combo.setFixedWidth(max(210, self.font_combo.fontMetrics()
                                          .horizontalAdvance("Libre Baskerville Italic") + 56))
        self.font_combo.view().setMinimumWidth(240)
        self.font_combo.setToolTip("Font of the selected text (Format > Script Font changes the whole script)")
        self.font_combo.activated.connect(self._font_chosen)
        self._fill_fonts()
        tb.addWidget(self.font_combo)
        tb.addSeparator()
        for k in ("bold", "italic", "underline", "strike"):
            tb.addAction(self.act[k])
        self.color_btn = self._color_button("color", TEXT_COLORS, self._apply_color,
                                            lambda: self.text_color)
        self.highlight_btn = self._color_button("highlight", HIGHLIGHTS, self._apply_color,
                                                lambda: self.highlight)
        tb.addWidget(self.color_btn)
        tb.addWidget(self.highlight_btn)
        self.case_btn = QToolButton()
        self.case_btn.setIcon(icon("case"))
        self.case_btn.setToolTip("Change case")
        self.case_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.case_btn.setMenu(self.case_menu)
        tb.addWidget(self.case_btn)
        tb.addAction(self.act["clear"])
        tb.addSeparator()
        for k in ("image", "link", "pagebreak"):
            tb.addAction(self.act[k])
        tb.addSeparator()
        for k in ("find",):
            tb.addAction(self.act[k])
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        focus_btn = QToolButton(objectName="textTool")
        focus_btn.setDefaultAction(self.act["focus"])
        focus_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        focus_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tb.addWidget(focus_btn)
        tb.addAction(self.act["print"])
        # the way out of Focus Mode, shown only while it's on (top right, faint until hovered)
        self.focus_exit = FocusExitButton(self)
        self.focus_exit.clicked.connect(lambda: self.toggle_focus(False))
        self.focus_exit.hide()
        # never squeeze the element box on a small screen
        self.type_combo.setMinimumWidth(self.type_combo.sizeHint().width())
        pdf = QPushButton("Export PDF", objectName="primary")
        pdf.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        pdf.setToolTip(self.act["pdf"].toolTip())
        pdf.clicked.connect(self.export_pdf)
        tb.addWidget(pdf)

    def _build_statusbar(self):
        sb = QStatusBar()
        sb.setSizeGripEnabled(False)
        self.setStatusBar(sb)
        self.elem_pill = QLabel(objectName="elemPill")
        self.hint_label = QLabel()
        self.stats_label = QLabel()
        sb.addWidget(self.elem_pill)
        sb.addWidget(self.hint_label, 1)
        sb.addPermanentWidget(self.stats_label)
        self.zoom_label = QLabel(objectName="zoom")
        for item in ("sidebar", "zoom_out", self.zoom_label, "zoom_in"):
            if isinstance(item, str):
                b = QToolButton()
                b.setDefaultAction(self.act[item])
                b.setIconSize(QSize(16, 16))
                b.setAutoRaise(True)
                item = b
            sb.addPermanentWidget(item)

    def _build_menus(self):
        a = self.act
        mb = self.menuBar()
        f = self.menus["file"] = mb.addMenu("&File")
        for k in ("new", "open", None, "save", "save_as", "save_version", "history"):
            f.addSeparator() if k is None else f.addAction(a[k])
        f.addSeparator()
        exp = f.addMenu("Export")
        exp.addAction(a["pdf"])
        for label, ext in EXPORTS:
            exp.addAction(f"{label}…").triggered.connect(lambda _=False, x=ext: self.export_as(x))
        self.menus["export"] = exp
        for k in (None, "print", "preview", None, "quit"):
            f.addSeparator() if k is None else f.addAction(a[k])

        ed = self.menus["edit"] = mb.addMenu("&Edit")
        ed.addAction(a["undo"])
        ed.addAction(a["redo"])
        ed.addSeparator()
        for text, slot, key in (("Cut", self.editor.cut, QKeySequence.StandardKey.Cut),
                                ("Copy", self.editor.copy, QKeySequence.StandardKey.Copy),
                                ("Paste", self.editor.paste, QKeySequence.StandardKey.Paste),
                                ("Select All", self.editor.selectAll,
                                 QKeySequence.StandardKey.SelectAll)):
            ed.addAction(self._a(text, slot, key, widget_only=True))
        ed.addSeparator()
        for k in ("find", "replace", "find_next", "find_prev", "goto", None, "spelling", None,
                  "palette"):
            ed.addSeparator() if k is None else ed.addAction(a[k])

        fm = self.menus["format"] = mb.addMenu("F&ormat")
        group = QActionGroup(self)
        self.type_actions = {}
        for i, t in enumerate(SHORTCUT_TYPES, 1):
            act = self._a(t, lambda _=False, t=t: self.editor.set_current_type(t), f"Ctrl+{i}",
                          widget_only=True, checkable=True)
            group.addAction(act)
            fm.addAction(act)
            self.type_actions[t] = act
        fm.addSeparator()
        for k in ("bold", "italic", "underline", "strike"):
            fm.addAction(a[k])
        fm.addMenu(self.case_menu)
        fm.addAction(a["clear"])
        fm.addAction(a["autocap"])
        fm.addSeparator()
        fm.addAction(self._a("Script Font…", self.choose_script_font, None))
        fm.addAction(self._a("Add Font File…", self.add_font_files, None))
        fm.addAction(self._a("Get More Fonts…", self.get_more_fonts, None))

        ins = self.menus["insert"] = mb.addMenu("&Insert")
        for k in ("image", "link", None, "pagebreak", "nobreak"):
            ins.addSeparator() if k is None else ins.addAction(a[k])

        pr = self.menus["production"] = mb.addMenu("&Production")
        for k in ("number", "unnumber", None, "title", "reports", None, "rename"):
            pr.addSeparator() if k is None else pr.addAction(a[k])
        pr.addSeparator()
        pr.addAction(self._a("Forget SmartType Memory…", self.forget_memory))

        v = self.menus["view"] = mb.addMenu("&View")
        self.menus["views"] = v.addMenu("Go To View")
        v.addSeparator()
        for k in ("sidebar", None, "focus", "typewriter", "fullscreen", None, "zoom_in",
                  "zoom_out", "zoom_100"):
            v.addSeparator() if k is None else v.addAction(a[k])
        v.addSeparator()
        tm = v.addMenu("Theme")
        for act in self.theme_actions.values():
            tm.addAction(act)
        v.addSeparator()
        v.addAction(a["goal"])

        self.menus["tools"] = mb.addMenu("&Tools")
        h = self.menus["help"] = mb.addMenu("&Help")
        h.addAction(self._a("Keyboard Flow", self.show_keys))
        h.addAction(a["palette"])
        h.addAction(self._a(f"About {__app_name__}", self.about))

    # ================================================================ views (rail)
    def add_view(self, key: str, title: str, icon_name: str, widget: QWidget, nav: bool = False):
        """Add a page to the left rail (Script, Cards, Beat Board...)."""
        self.stack.addWidget(widget)
        b = QToolButton(objectName="railButton")
        b.setIcon(icon(icon_name))
        b.setIconSize(QSize(22, 22))
        b.setCheckable(True)
        n = len(self.views) + 1
        b.setToolTip(f"{title}  (Ctrl+Alt+{n})")
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.clicked.connect(lambda: self.show_view(key))
        self.rail_group.addButton(b)
        self.rail_lay.addWidget(b)
        self._rail_icons = getattr(self, "_rail_icons", {})
        self._rail_icons[b] = icon_name
        widget.setProperty("showsNavigator", nav or key == "script")
        self.views[key] = (widget, b)
        act = self._a(title, lambda: self.show_view(key), f"Ctrl+Alt+{n}")
        self.menus["views"].addAction(act)

    def show_view(self, key: str):
        widget, button = self.views[key]
        leaving = self.stack.currentWidget()
        if leaving is not widget and hasattr(leaving, "leave_view"):
            leaving.leave_view()
        self.stack.setCurrentWidget(widget)
        button.setChecked(True)
        self.navigator.setVisible(bool(widget.property("showsNavigator")) and
                                  self.act["sidebar"].isChecked())
        if hasattr(widget, "enter_view"):
            widget.enter_view()
        if key == "script":
            self.editor.setFocus()

    def current_view(self) -> str:
        w = self.stack.currentWidget()
        return next((k for k, (v, _b) in self.views.items() if v is w), "script")

    # ================================================================ live UI
    def _on_element(self, etype: str):
        self.elem_pill.setText(etype)
        i = self.type_combo.findData(etype)
        self.type_combo.blockSignals(True)
        self.type_combo.setCurrentIndex(i)
        self.type_combo.blockSignals(False)
        if etype in self.type_actions:
            self.type_actions[etype].setChecked(True)

    # ================================================================ fonts
    def _fill_fonts(self):
        from PySide6.QtGui import QStandardItemModel, QStandardItem
        model = QStandardItemModel(self.font_combo)
        for title, names in font_groups():
            head = QStandardItem(title.upper())
            head.setFlags(Qt.ItemFlag.NoItemFlags)
            f = QFont()
            f.setBold(True)
            f.setPointSize(8)
            head.setFont(f)
            model.appendRow(head)
            for name in names:
                it = QStandardItem(name)
                it.setData(name, Qt.ItemDataRole.UserRole)
                it.setFont(QFont(name, 10))
                model.appendRow(it)
        for label, key in (("Add Font File…", "@add"), ("Get More Fonts…", "@more")):
            it = QStandardItem(label)
            it.setData(key, Qt.ItemDataRole.UserRole)
            model.appendRow(it)
        self.font_combo.setModel(model)
        self._sync_font_combo()

    def _sync_font_combo(self):
        fam = self.editor.current_font_family()
        i = self.font_combo.findData(fam)
        self.font_combo.blockSignals(True)
        if i >= 0:
            self.font_combo.setCurrentIndex(i)
        self.font_combo.blockSignals(False)

    def _font_chosen(self, i: int):
        key = self.font_combo.itemData(i)
        if key == "@add":
            self.add_font_files()
        elif key == "@more":
            self.get_more_fonts()
        elif key:
            self.editor.set_font_family(key)
        self._sync_font_combo()
        self.editor.setFocus()

    def choose_script_font(self):
        from PySide6.QtWidgets import QInputDialog
        names = [n for _t, ns in font_groups() for n in ns]
        cur = self.editor.script_font()
        name, ok = QInputDialog.getItem(self, "Script Font", "Typeface for the whole script:", names,
                                        names.index(cur) if cur in names else 0, False)
        if not ok:
            return
        if not is_typewriter(name):
            r = QMessageBox.question(self, "Script Font",
                                     f"{name} isn't a typewriter (fixed-width) font. Screenplays are read "
                                     f"at one page a minute only in a Courier-style font, and studios expect "
                                     f"Courier 12 pt.\n\nUse {name} for the whole script anyway?")
            if r != QMessageBox.StandardButton.Yes:
                return
        self.editor.set_script_font(name)
        self._sync_font_combo()

    def add_font_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Add Font File", str(Path.home() / "Downloads"),
                                                "Fonts (*.ttf *.otf)")
        added = []
        for path in paths:
            added += add_font_file(path, self.data)
        if added:
            self._fill_fonts()
            self.statusBar().showMessage("Added: " + ", ".join(sorted(set(added))), 6000)
        elif paths:
            QMessageBox.warning(self, __app_name__, "Those files couldn't be read as fonts.")

    def get_more_fonts(self):
        QDesktopServices.openUrl(QUrl(GET_MORE_URL))
        QMessageBox.information(self, "Get More Fonts", (
            "Google Fonts is opening in your browser. Every font there is free to use.<br><br>"
            "<b>To add one:</b><ol><li>Open a font and click <b>Get font</b>, then <b>Download all</b>.</li>"
            "<li>Unzip the download.</li>"
            "<li>Here, choose <b>Format → Add Font File…</b> and pick its .ttf files.</li></ol>"
            "Fonts you install in Windows also appear in the list after you restart Cut To:."))

    def about(self):
        box = QMessageBox(self)
        box.setWindowTitle(f"About {__app_name__}")
        box.setIconPixmap(QIcon(resource_path("icons", "cutto.png")).pixmap(QSize(96, 96)))
        box.setText(f"<b style='font-size:15pt'>{__app_name__}</b>&nbsp; {__version__}<br><br>"
                    "Free, open-source screenwriting.<br><br>"
                    "Licensed under the GNU GPL v3.0 or later. Fonts: SIL Open Font License / "
                    "Apache 2.0.<br>"
                    "<a href='https://github.com/manojsriharsha-git/cut-to'>"
                    "github.com/manojsriharsha-git/cut-to</a>")
        box.exec()

    def _sync_format_buttons(self):
        self._sync_font_combo()
        state = self.editor.char_state()
        for k in ("bold", "italic", "underline", "strike"):
            self.act[k].setChecked(state[k])

    def _on_page(self, page: int, total: int):
        self._page_text = f"Page {page} of {total}"
        self._update_stats()

    def _refresh_structure(self):
        self.navigator.refresh()
        self._update_stats()
        if hasattr(self, "goal_widget"):
            self.goal_widget.update_view()          # counts words: only after a pause in typing
        if self.speller.available and self.editor.spell is not None:
            names = self._name_words()
            if names - self.speller.names:
                self.speller.names |= names
                self.editor.spell.rehighlight()

    def _update_stats(self):
        scenes = self.navigator.lists[0].count()
        chars = self.navigator.lists[1].count()
        page = getattr(self, "_page_text", "")
        self.stats_label.setText(f"{page}   ·   {scenes} scenes   ·   {chars} characters")

    def _update_title(self):
        name = self.path.name if self.path else "Untitled"
        dirty = self.editor.document().isModified()
        self.setWindowTitle(f"{name}{' •' if dirty else ''} — {__app_name__}")

    def _script_title(self) -> str:
        d = {k.lower(): v for k, v in self.editor.title_page}
        return d.get("title") or (self.path.stem if self.path else "Untitled")

    def _toggle_sidebar(self):
        on = not self.navigator.isVisible()
        self.navigator.setVisible(on and bool(self.stack.currentWidget().property("showsNavigator")))
        self.act["sidebar"].setChecked(on)

    def _zoom(self, factor):
        z = 1.0 if factor is None else self.editor.zoom * factor
        self.editor.set_zoom(z)
        self.settings.setValue("zoom", self.editor.zoom)
        self._update_zoom_label()

    def _update_zoom_label(self):
        self.zoom_label.setText(f"{round(self.editor.zoom * 100)}%")

    # ================================================================ writing comfort
    def open_find(self, with_replace: bool):
        self.show_view("script")
        self.findbar.open(with_replace)

    def goto_dialog(self):
        self.show_view("script")
        GotoDialog(self.editor, self).exec()

    def command_palette(self):
        CommandPalette(palette_entries(self), self).exec()

    def rename_character(self, current: str = ""):
        names = self.editor.to_script().characters()
        if not names:
            QMessageBox.information(self, __app_name__, "There are no characters to rename yet.")
            return
        cur_block = self.editor.textCursor().block()
        if not current and self.editor.block_type(cur_block) == "Character":
            current = cur_block.text().split("(")[0].strip().upper()
        dlg = RenameDialog(names, current, self)
        if dlg.exec() and dlg.new.text().strip():
            n = self.editor.rename_character(dlg.old.currentText(), dlg.new.text(),
                                             dlg.everywhere.isChecked())
            self.statusBar().showMessage(f"Renamed {n} place{'s' if n != 1 else ''}", 4000)

    def edit_goal(self):
        dlg = GoalDialog(self.goals, self)
        if dlg.exec():
            self.settings.setValue("goalWords", dlg.words.value())
            self.goal_widget.update_view()

    def set_auto_capitalize(self, on: bool):
        self.act["autocap"].setChecked(on)
        self.editor.auto_capitalize = on
        self.settings.setValue("autoCapitalize", "true" if on else "false")

    def set_spelling(self, on: bool):
        self.act["spelling"].setChecked(on)
        self.settings.setValue("spelling", "true" if on else "false")
        if on and self.editor.spell is None:
            if not self.speller.available:
                self.statusBar().showMessage("Spelling needs the pyspellchecker package.", 5000)
                self.act["spelling"].setChecked(False)
                return
            self.speller.names = self._name_words()
            self.editor.spell = SpellHighlighter(self.editor, self.speller)
        elif not on and self.editor.spell is not None:
            self.editor.spell.setDocument(None)
            self.editor.spell.deleteLater()
            self.editor.spell = None

    def _name_words(self) -> set[str]:
        """Words of every character name (never marked as spelling mistakes)."""
        from ..core.smart import base_name
        return {w.lower() for t, text in self.editor.element_pairs() if t == "Character"
                for w in base_name(text).split()}

    def _spell_menu(self, cur):
        return self.editor.spell.menu_actions(cur) if self.editor.spell is not None else []

    def toggle_focus(self, on: bool):
        """Focus mode: just the page. Everything around the paragraph you write fades."""
        self.show_view("script")
        self.act["focus"].setChecked(on)
        for w in (self.toolbar, self.statusBar(), self.rail, self.menuBar()):
            w.setVisible(not on)
        self.navigator.setVisible(not on and self.act["sidebar"].isChecked())
        # bars above the page (scene ribbon…) step aside too, and come back as they were
        if on and not getattr(self, "_focus_hidden", None):
            top = [self.script_top.itemAt(i).widget() for i in range(self.script_top.count())]
            self._focus_hidden = [w for w in top if w is not None and w.isVisible()]
            for w in self._focus_hidden:
                w.hide()
        elif not on:
            for w in getattr(self, "_focus_hidden", None) or []:
                w.show()
            self._focus_hidden = None
        self.editor.set_focus_mode(on)
        if on and not self.isFullScreen():
            self._was_full = False
            self.showFullScreen()
        elif not on and not getattr(self, "_was_full", True):
            self.showNormal()
        self.focus_exit.setVisible(on)
        if on:
            self._place_focus_exit()
            self.focus_exit.raise_()

    def _place_focus_exit(self):
        b = self.focus_exit
        b.adjustSize()
        b.move(self.width() - b.width() - 18, 14)

    def resizeEvent(self, e):                     # noqa: N802
        super().resizeEvent(e)
        if hasattr(self, "focus_exit") and self.focus_exit.isVisible():
            self._place_focus_exit()

    def toggle_typewriter(self, on: bool):
        self.editor.set_typewriter(on)

    def toggle_fullscreen(self, on: bool):
        self.showFullScreen() if on else self.showNormal()

    def keyPressEvent(self, e):                   # noqa: N802
        if e.key() == Qt.Key.Key_Escape and self.act["focus"].isChecked():
            self.toggle_focus(False)
            return
        super().keyPressEvent(e)

    def set_theme(self, name: str):
        name = apply_theme(name)
        self.settings.setValue("theme", name)
        QApplication.instance().setStyleSheet(build_qss())
        for a, n in self._icons.items():
            a.setIcon(icon(n))
        for b, n in getattr(self, "_rail_icons", {}).items():
            b.setIcon(icon(n))
        self.case_btn.setIcon(icon("case"))
        self.color_btn.setIcon(icon("color", swatch=self.text_color))
        self.highlight_btn.setIcon(icon("highlight", swatch=self.highlight))
        self.editor.apply_colors()
        for f in self.features:
            if hasattr(f, "theme_changed"):
                f.theme_changed()
        self.theme_actions[name].setChecked(True)

    # ================================================================ files
    def _confirm_discard(self) -> bool:
        if not self.editor.document().isModified():
            return True
        r = QMessageBox.question(self, __app_name__, "Save changes to this script?",
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                 | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Save:
            return self.save_file()
        return r == QMessageBox.StandardButton.Discard

    def new_file(self, template: str | None = None):
        if self._confirm_discard():
            self.recovery.clear(self.session)
            self.path = None
            s = Script()
            if template:
                s.extra["template"] = template
            self.editor.load_script(s)
            self._after_open()

    def open_file(self, path: str | None = None):
        if not self._confirm_discard():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Open Script",
                                                  self.settings.value("lastDir", ""), open_filter())
            if not path:
                return
        try:
            script = load(path)
        except Exception as ex:                      # noqa: BLE001 - show any parse error
            QMessageBox.warning(self, __app_name__, f"Could not open file:\n{ex}")
            return
        self.recovery.clear(self.session)
        p = Path(path)
        native = p.suffix.lower() in NATIVE
        self.path = p if native else None             # imports (Word, PDF...) save as new files
        self.settings.setValue("lastDir", str(p.parent))
        self.editor.load_script(script, str(p.resolve()))
        if not native:
            self.editor.document().setModified(True)
            self.statusBar().showMessage(f"Imported {p.name} — save it to keep it", 6000)
        self.memory.commit()                         # opening a script teaches SmartType too
        self._after_open()

    def _after_open(self):
        self.goals.reset_baseline()
        self._update_title()
        for f in self.features:
            if hasattr(f, "script_loaded"):
                f.script_loaded()

    def save_file(self) -> bool:
        if self.path is None or self.path.suffix.lower() not in (".fdx", ".fountain", ".cut", ".json"):
            return self.save_as()
        return self._write(self.path)

    def save_as(self) -> bool:
        start = str(self.path.with_suffix(".fdx")) if self.path else \
            str(Path(self.settings.value("lastDir", "")) / f"{self._script_title()}.fdx")
        path, flt = QFileDialog.getSaveFileName(self, "Save Script", start, SAVE_FILTERS)
        if not path:
            return False
        p = Path(path)
        if not p.suffix:
            p = p.with_suffix({"Fountain": ".fountain", "Cut": ".cut"}.get(
                flt.split(" ")[0], ".fdx"))
        return self._write(p)

    def _write(self, p: Path) -> bool:
        script = self.editor.to_script()
        if loses_content(script, p):
            box = QMessageBox(QMessageBox.Icon.Question, __app_name__,
                              f"{p.suffix} files can't keep everything in this script "
                              f"(pictures, colours, links, cards, notes or revisions become plain "
                              f"text or are left out).\n\nSave a .cut file instead? It keeps "
                              f"everything and can still be exported to .fdx later.",
                              parent=self)
            keep = box.addButton("Save as .cut", QMessageBox.ButtonRole.AcceptRole)
            box.addButton(f"Save {p.suffix} anyway", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton(QMessageBox.StandardButton.Cancel)
            box.exec()
            if box.clickedButton() is keep:
                p = p.with_suffix(".cut")
            elif box.buttonRole(box.clickedButton()) == QMessageBox.ButtonRole.RejectRole:
                return False
        try:
            save(script, p)
        except Exception as ex:                      # noqa: BLE001
            QMessageBox.warning(self, __app_name__, f"Could not save:\n{ex}")
            return False
        self.path = p
        self.settings.setValue("lastDir", str(p.parent))
        self.editor.doc_key = str(p.resolve())
        self.memory.set_document(self.editor.element_pairs(), self.editor.doc_key)
        self.memory.commit()
        self.editor.document().setModified(False)
        self.recovery.clear(self.session)
        try:
            self.history.snapshot(script, str(p), pages=self.editor.page_count())
        except OSError:
            pass
        self.goals.record()
        self._update_title()
        self.statusBar().showMessage(f"Saved {p.name}", 2500)
        return True

    def export_as(self, ext: str):
        folder = Path(self.settings.value("lastDir", "") or Path.home())
        path, _ = QFileDialog.getSaveFileName(self, "Export", str(folder / f"{self._script_title()}{ext}"),
                                              f"*{ext}")
        if not path:
            return
        if not path.lower().endswith(ext):
            path += ext
        try:
            save(self.editor.to_script(), path)
        except Exception as ex:                      # noqa: BLE001
            QMessageBox.warning(self, __app_name__, f"Could not export:\n{ex}")
            return
        self.statusBar().showMessage(f"Exported {Path(path).name}", 4000)

    def autosave(self):
        """Every minute: keep a recovery copy of unsaved work (deleted on save/close)."""
        if self.editor.document().isModified():
            try:
                self.recovery.write(self.session, self.editor.to_script(),
                                    str(self.path) if self.path else None)
            except OSError:
                pass

    def offer_recovery(self):
        pending = []
        for item in self.recovery.pending():
            lock = QLockFile(str(item[0].with_suffix(".lock")))
            if item[0].stem != self.session and lock.tryLock(0):    # its window is gone
                lock.unlock()
                pending.append(item)
        if not pending:
            return
        names = "\n".join(f"• {Path(o).name if o else 'Untitled'}" for _f, o, _t in pending)
        r = QMessageBox.question(self, __app_name__,
                                 f"{__app_name__} closed without saving these scripts:\n\n{names}\n\n"
                                 f"Recover them now?")
        if r != QMessageBox.StandardButton.Yes:
            for f, _o, _t in pending:
                f.unlink(missing_ok=True)
            return
        f, original, _t = pending[0]
        script = self.recovery.load(f)
        self.path = Path(original) if original else None
        self.editor.load_script(script, original)
        self.editor.document().setModified(True)
        self._after_open()
        f.unlink(missing_ok=True)
        for f2, original2, _t2 in pending[1:]:          # the others open in their own windows
            w = MainWindow(self.memory, self.data)
            w.path = Path(original2) if original2 else None
            w.editor.load_script(self.recovery.load(f2), original2)
            w.editor.document().setModified(True)
            w._after_open()
            w.show()
            f2.unlink(missing_ok=True)
            QApplication.instance()._windows = getattr(QApplication.instance(), "_windows", []) + [w]

    def save_version(self):
        label, ok = QInputDialog.getText(self, "Save Version", "Name this version (e.g. “Studio draft”):")
        if ok:
            self.history.snapshot(self.editor.to_script(), str(self.path) if self.path else None,
                                  label=label.strip() or "Saved version", auto=False,
                                  pages=self.editor.page_count())
            self.statusBar().showMessage("Version saved", 3000)

    def show_history(self):
        from .rewrites import HistoryDialog
        HistoryDialog(self, self).exec()

    # ================================================================ PDF and printing
    def export_pdf(self):
        folder = Path(self.settings.value("lastDir", "") or Path.home())
        start = str(folder / f"{self._script_title()}.pdf")
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF", start, "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        with self.editor.clean_for_print():
            export_pdf(self.editor.document(), path, self.editor.dpi, self.editor.title_page,
                       self._script_title(), self.page_extras())
        self.statusBar().showMessage(f"Exported {Path(path).name}", 4000)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def page_extras(self) -> dict:
        """Extra things printed on pages (revision header, watermark...) from features."""
        extras = {}
        for f in self.features:
            if hasattr(f, "page_extras"):
                extras.update(f.page_extras())
        return extras

    def _printer(self) -> QPrinter:
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageLayout(letter_layout())
        printer.setFullPage(True)
        printer.setDocName(self._script_title())
        return printer

    def _render_to(self, printer):
        with self.editor.clean_for_print():
            render(self.editor.document(), printer, self.editor.dpi, self.editor.title_page,
                   extras=self.page_extras())

    def print_script(self):
        printer = self._printer()
        if QPrintDialog(printer, self).exec():
            self._render_to(printer)

    def print_preview(self):
        dlg = QPrintPreviewDialog(self._printer(), self)
        dlg.paintRequested.connect(self._render_to)
        dlg.resize(1000, 800)
        dlg.exec()

    # ================================================================ insert and production
    def insert_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "Insert Image",
                                              self.settings.value("lastImageDir", ""), IMAGE_FILTER)
        if path:
            self.settings.setValue("lastImageDir", str(Path(path).parent))
            if not self.editor.insert_image(path):
                QMessageBox.warning(self, __app_name__, "That file isn't an image Cut To: can read.")

    def insert_link(self):
        dlg = LinkDialog(self.editor.textCursor().selectedText(), self)
        if dlg.exec():
            self.editor.insert_link(dlg.text.text(), dlg.url.text())
        self.editor.setFocus()

    def number_scenes(self):
        self.editor.number_scenes(locked=bool(self.editor.project.get("locked")))

    def edit_title_page(self):
        dlg = TitlePageDialog(self.editor.title_page, self)
        if dlg.exec():
            self.editor.title_page = dlg.result_title_page()
            self.editor.document().setModified(True)
            self._update_title()

    def show_reports(self):
        ReportsDialog(self.editor, self._script_title(), self).exec()

    def forget_memory(self):
        if QMessageBox.question(self, __app_name__,
                                "Forget every scene heading, character and transition "
                                "SmartType has learned from your saved scripts?") \
                == QMessageBox.StandardButton.Yes:
            self.memory.forget_all()

    def show_keys(self):
        QMessageBox.information(self, "Keyboard Flow", (
            "<table cellpadding=4>"
            "<tr><td><b>Enter</b></td><td>next element: Scene → Action, Character → Dialogue, "
            "Dialogue → Action, Transition → Scene</td></tr>"
            "<tr><td><b>Enter on empty line</b></td><td>Action → Transition → Scene Heading</td></tr>"
            "<tr><td><b>Tab</b></td><td>Action → Character → Transition → Scene; "
            "Dialogue ↔ Parenthetical</td></tr>"
            "<tr><td><b>Shift+Tab</b></td><td>cycle backwards</td></tr>"
            "<tr><td><b>Grey text</b></td><td>SmartType prediction — Enter or → accepts, "
            "Esc dismisses</td></tr>"
            "<tr><td><b>↑ ↓</b></td><td>pick from the suggestion list</td></tr>"
            "<tr><td><b>Ctrl+1…8</b></td><td>Scene, Action, Character, Paren, Dialogue, "
            "Transition, Shot, General</td></tr>"
            "<tr><td><b>Ctrl+Enter</b></td><td>page break</td></tr>"
            "<tr><td><b>Shift+Enter</b></td><td>line break inside a paragraph</td></tr>"
            "<tr><td><b>Ctrl+K</b></td><td>insert a link (Ctrl+click a link to open it)</td></tr>"
            "<tr><td><b>Ctrl+F / Ctrl+H</b></td><td>find / find and replace</td></tr>"
            "<tr><td><b>Ctrl+G</b></td><td>go to a scene or page</td></tr>"
            "<tr><td><b>Ctrl+Shift+P</b></td><td>command palette: any command or scene</td></tr>"
            "<tr><td><b>Ctrl+Alt+1…6</b></td><td>Script, Cards, Beat Board, Characters, "
            "Production, Insights</td></tr>"
            "<tr><td><b>Ctrl+Shift+F</b></td><td>Focus Mode</td></tr>"
            "</table><br>Typing <i>int.</i> makes a Scene Heading; an ALL-CAPS name on its own "
            "line becomes a Character when you press Enter."))

    def closeEvent(self, e):                       # noqa: N802
        if self._confirm_discard():
            self.settings.setValue("geometry", self.saveGeometry())
            self.goals.record()
            self.recovery.clear(self.session)
            self._lock.unlock()
            self.editor.popup.hide()
            for f in self.features:
                if hasattr(f, "closing"):
                    f.closing()
            e.accept()
        else:
            e.ignore()


def _load_fonts():
    load_all(data_dir())


def _migrate_from_screenplay():
    """Before it was renamed, the app kept its data and settings under "Screenplay"."""
    import shutil
    new = data_dir()
    old = new.parent.parent / "Screenplay" / "Screenplay"
    if old.is_dir() and not new.exists():
        try:
            shutil.copytree(old, new)
        except OSError:
            pass
    settings, old_settings = QSettings(), QSettings("Screenplay", "Screenplay")
    if not settings.allKeys() and old_settings.allKeys():
        for k in old_settings.allKeys():
            settings.setValue(k, old_settings.value(k))


def memory_path() -> Path:
    return data_dir() / "smart_memory.json"


def run(argv=None) -> int:
    argv = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(__app_id__)                 # folders can't contain ":"
    app.setOrganizationName(__app_id__)
    app.setApplicationDisplayName(__app_name__)
    _migrate_from_screenplay()
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")
    ui = QFont("Segoe UI")
    ui.setPointSize(10)
    app.setFont(ui)
    apply_theme(QSettings().value("theme", "Day"))
    app.setStyleSheet(build_qss())
    _load_fonts()
    app.setWindowIcon(QIcon(resource_path("icons", "cutto.png")))

    win = MainWindow(SmartMemory(memory_path()))
    win.show()
    args = [a for a in argv[1:] if not a.startswith("-")]
    if args and Path(args[0]).exists():
        QTimer.singleShot(0, lambda: win.open_file(args[0]))
    else:
        QTimer.singleShot(300, win.offer_recovery)
    return app.exec()
