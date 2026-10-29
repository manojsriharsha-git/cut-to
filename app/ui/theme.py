"""Bumble palette + one stylesheet. Change colours here only.

Three looks share the same accents (honey, mustard, salmon, caramel):
Day (warm paper), Night (warm charcoal) and Midnight (ink blue). `apply_theme()`
swaps the neutrals in `C`; `build_qss()` turns the palette into the stylesheet.
"""


class C:
    # sampled from the Bumble palette
    HONEY = "#E4C85D"      # yellow
    BLUSH = "#EED9D4"      # pale pink
    CREAM = "#F1F0EB"      # off-white
    SALMON = "#EAB5A3"     # pink
    CARAMEL = "#C88E5C"    # brown
    MUSTARD = "#DFAF40"    # gold
    GREIGE = "#E6DFD7"     # background
    # derived neutrals
    SAND = "#ECE6DF"       # sidebar
    PAPER = "#FBFAF6"      # the page
    LINE = "#DCD2C7"       # hairlines
    INK = "#3A322B"        # text
    INK_SOFT = "#8C7D70"   # secondary text
    SELECT = "#F3E3A3"     # text selection (light honey)
    THUMB = "#D5C7B8"      # scrollbar
    NAME = "Day"


_NEUTRALS = ("BLUSH", "CREAM", "GREIGE", "SAND", "PAPER", "LINE", "INK", "INK_SOFT", "SELECT", "THUMB")
THEMES = {
    "Day": dict(BLUSH="#EED9D4", CREAM="#F1F0EB", GREIGE="#E6DFD7", SAND="#ECE6DF",
                PAPER="#FBFAF6", LINE="#DCD2C7", INK="#3A322B", INK_SOFT="#8C7D70",
                SELECT="#F3E3A3", THUMB="#D5C7B8"),
    "Night": dict(BLUSH="#4A3D37", CREAM="#332C28", GREIGE="#221E1B", SAND="#2A2522",
                  PAPER="#2F2925", LINE="#463C35", INK="#EDE4D8", INK_SOFT="#A89888",
                  SELECT="#6B5A2E", THUMB="#54483F"),
    "Midnight": dict(BLUSH="#2C3550", CREAM="#1E2538", GREIGE="#121726", SAND="#171D2E",
                     PAPER="#1B2133", LINE="#2D3650", INK="#E3E6EE", INK_SOFT="#8D96AE",
                     SELECT="#5A4C22", THUMB="#36405C"),
}


def apply_theme(name: str) -> str:
    """Switch the neutral colours in C. Returns the theme name actually used."""
    name = name if name in THEMES else "Day"
    for k, v in THEMES[name].items():
        setattr(C, k, v)
    C.NAME = name
    return name


def is_dark() -> bool:
    return C.NAME != "Day"


def build_qss() -> str:
    return _QSS_TEMPLATE()


def _QSS_TEMPLATE() -> str:  # noqa: N802
    return f"""
QMainWindow, QWidget#central, QDialog {{ background: {C.GREIGE}; }}
QMenuBar {{ background: {C.GREIGE}; border: none; padding: 3px 8px; color: {C.INK}; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 6px; background: transparent; }}
QMenuBar::item:selected {{ background: {C.BLUSH}; }}
QMenu {{ background: {C.PAPER}; border: 1px solid {C.LINE}; border-radius: 8px; padding: 6px; color: {C.INK}; }}
QMenu::item {{ padding: 6px 30px 6px 14px; border-radius: 6px; }}
QMenu::item:selected {{ background: {C.BLUSH}; }}
QMenu::item:disabled {{ color: {C.INK_SOFT}; }}
QMenu::separator {{ height: 1px; background: {C.LINE}; margin: 5px 8px; }}

QToolBar {{ background: {C.GREIGE}; border: none; border-bottom: 1px solid {C.LINE}; padding: 5px 10px; spacing: 1px; }}
QComboBox {{ background: {C.PAPER}; border: 1px solid {C.LINE}; border-radius: 8px;
             padding: 5px 12px; min-width: 150px; color: {C.INK}; }}
QComboBox:hover {{ border-color: {C.SALMON}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {C.PAPER}; border: 1px solid {C.LINE}; outline: 0;
             selection-background-color: {C.BLUSH}; selection-color: {C.INK}; padding: 4px; }}

QFrame#sidebar {{ background: {C.SAND}; border: none; }}
QLabel#sideTitle {{ color: {C.CARAMEL}; font-size: 8pt; font-weight: 600; padding: 16px 18px 6px 18px; }}
QListWidget#scenes {{ background: transparent; border: none; padding: 2px 10px; outline: 0; color: {C.INK}; }}
QListWidget#scenes::item {{ padding: 7px 8px; border-radius: 6px; margin: 1px 0; }}
QListWidget#scenes::item:hover {{ background: {C.CREAM}; }}
QListWidget#scenes::item:selected {{ background: {C.BLUSH}; color: {C.INK}; }}

QListWidget#suggest {{ background: {C.PAPER}; border: 1px solid {C.SALMON}; padding: 4px;
                       outline: 0; color: {C.INK}; font-family: "Courier Prime"; font-size: 11pt; }}
QListWidget#suggest::item {{ padding: 4px 10px; border-radius: 4px; }}
QListWidget#suggest::item:selected {{ background: {C.HONEY}; color: {C.INK}; }}

QStatusBar {{ background: {C.GREIGE}; border-top: 1px solid {C.LINE}; }}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {C.INK_SOFT}; padding: 3px 8px; }}
QLabel#elemPill {{ background: {C.HONEY}; color: {C.INK}; border-radius: 9px;
                   padding: 2px 12px; font-weight: 600; }}

/* the page (QTextEdit#page) takes its colours from the palette (editor.apply_colors),
   so the paper and the desk around it can differ */
QSplitter::handle {{ background: {C.LINE}; }}

QScrollBar:vertical {{ background: transparent; width: 11px; margin: 3px; }}
QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 3px; }}
QScrollBar::handle {{ background: {C.THUMB}; border-radius: 4px; min-height: 40px; min-width: 40px; }}
QScrollBar::handle:hover {{ background: {C.CARAMEL}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QLineEdit, QPlainTextEdit {{ background: {C.PAPER}; border: 1px solid {C.LINE}; border-radius: 6px;
                             padding: 5px; color: {C.INK}; selection-background-color: {C.SELECT}; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {C.MUSTARD}; }}
QPushButton {{ background: {C.PAPER}; border: 1px solid {C.LINE}; border-radius: 8px;
               padding: 6px 18px; color: {C.INK}; }}
QPushButton:hover {{ border-color: {C.SALMON}; }}
QPushButton:default {{ background: {C.MUSTARD}; border-color: {C.MUSTARD}; font-weight: 600; }}
QLabel {{ color: {C.INK}; }}
QToolTip {{ background: {C.PAPER}; color: {C.INK}; border: 1px solid {C.LINE}; padding: 4px; }}
QMessageBox {{ background: {C.GREIGE}; }}

QToolBar#main::separator {{ background: {C.LINE}; width: 1px; margin: 6px 3px; }}

QToolButton {{ background: transparent; border: none; border-radius: 6px; padding: 3px; color: {C.INK}; }}
QToolButton:hover {{ background: {C.BLUSH}; }}
QToolButton:pressed, QToolButton:checked {{ background: {C.SELECT}; }}
QToolButton[popupMode="1"] {{ padding-right: 14px; }}
QToolButton::menu-button {{ border: none; width: 12px; }}
QLabel#zoom {{ color: {C.INK_SOFT}; min-width: 40px; qproperty-alignment: AlignCenter; }}
QToolButton#textTool {{ padding: 5px 10px; color: {C.INK_SOFT}; font-weight: 600; }}
QToolButton#focusExit {{ background: transparent; border: 1px solid transparent; border-radius: 14px;
                         color: {C.INK_SOFT}; padding: 4px 10px; font-size: 11pt; }}
QToolButton#focusExit:hover {{ background: {C.CREAM}; border-color: {C.LINE}; color: {C.INK}; }}
QPushButton#primary {{ background: {C.MUSTARD}; border: 1px solid {C.MUSTARD}; color: {C.INK};
                       font-weight: 600; padding: 6px 16px; border-radius: 8px; }}
QPushButton#primary:hover {{ background: {C.HONEY}; border-color: {C.HONEY}; }}

QPushButton#seg {{ background: {C.CREAM}; border: 1px solid {C.LINE}; border-radius: 0;
                   padding: 5px 4px; color: {C.INK_SOFT}; font-size: 9pt; }}
QPushButton#seg[pos="first"] {{ border-top-left-radius: 8px; border-bottom-left-radius: 8px; }}
QPushButton#seg[pos="last"] {{ border-top-right-radius: 8px; border-bottom-right-radius: 8px; }}
QPushButton#seg:checked {{ background: {C.PAPER}; color: {C.INK}; font-weight: 600; }}
QListWidget#navList {{ background: transparent; border: none; outline: 0; }}

QTabWidget::pane {{ border: 1px solid {C.LINE}; border-radius: 8px; background: {C.PAPER}; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 7px 16px; color: {C.INK_SOFT}; border: none; }}
QTabBar::tab:selected {{ color: {C.INK}; font-weight: 600; border-bottom: 2px solid {C.MUSTARD}; }}
QTableWidget {{ background: {C.PAPER}; alternate-background-color: {C.CREAM}; border: none;
                selection-background-color: {C.BLUSH}; selection-color: {C.INK}; color: {C.INK}; }}
QHeaderView::section {{ background: {C.PAPER}; color: {C.INK_SOFT}; border: none;
                        border-bottom: 1px solid {C.LINE}; padding: 6px 8px; font-weight: 600; }}
QLabel#statValue {{ font-size: 18pt; font-weight: 600; color: {C.INK}; }}
QLabel#statName {{ font-size: 8pt; color: {C.CARAMEL}; font-weight: 600; }}

QWidget#central, QWidget#scriptPage {{ background: {C.GREIGE}; }}
QFrame#rail {{ background: {C.SAND}; border-right: 1px solid {C.LINE}; }}
QLabel#railLogo {{ padding: 2px 0 4px 0; }}
QToolBar#main QComboBox {{ min-width: 0px; }}
QToolButton#railButton {{ padding: 8px; border-radius: 10px; margin: 1px 0; }}
QToolButton#railButton:checked {{ background: {C.HONEY}; }}
QToolButton#railButton:hover:!checked {{ background: {C.BLUSH}; }}
QFrame#findBar {{ background: {C.SAND}; border-top: 1px solid {C.LINE}; }}
QFrame#findBar QLabel {{ color: {C.INK_SOFT}; }}
QDialog#palette {{ background: {C.PAPER}; border: 1px solid {C.SALMON}; border-radius: 12px; }}
QListWidget#paletteList {{ background: transparent; border: none; outline: 0; color: {C.INK}; }}
QListWidget#paletteList::item {{ padding: 7px 10px; border-radius: 6px; }}
QListWidget#paletteList::item:selected {{ background: {C.HONEY}; color: #3A322B; }}
QProgressBar#goalBar {{ background: {C.LINE}; border: none; border-radius: 3px; }}
QProgressBar#goalBar::chunk {{ background: {C.MUSTARD}; border-radius: 3px; }}
QLabel#viewTitle {{ font-size: 15pt; font-weight: 600; color: {C.INK}; padding-right: 12px; }}
QLabel#sectionTitle {{ font-size: 11pt; font-weight: 600; color: {C.INK}; padding-top: 6px; }}
QLabel#hint {{ color: {C.INK_SOFT}; font-size: 8.5pt; }}
QLabel#profileName {{ font-size: 16pt; font-weight: 600; color: {C.INK}; }}
QFrame#tile {{ background: {C.PAPER}; border: 1px solid {C.LINE}; border-radius: 10px; min-width: 130px; }}
QListWidget#cards {{ background: {C.GREIGE}; border: none; outline: 0; }}
QGraphicsView#board {{ border: 1px solid {C.LINE}; border-radius: 8px; }}
QWidget#insights, QWidget#profile {{ background: {C.GREIGE}; }}
QTreeWidget, QListWidget {{ background: {C.PAPER}; color: {C.INK}; border: 1px solid {C.LINE};
                            border-radius: 8px; outline: 0; }}
QListWidget#navList, QListWidget#scenes, QListWidget#suggest {{ border-radius: 0; }}
QListWidget::item, QTreeWidget::item {{ padding: 5px 8px; border-radius: 6px; }}
QListWidget::item:selected, QTreeWidget::item:selected {{ background: {C.BLUSH}; color: {C.INK}; }}
QListWidget::item:hover:!selected {{ background: {C.CREAM}; }}
QTextBrowser {{ background: {C.PAPER}; color: {C.INK}; border: 1px solid {C.LINE}; border-radius: 8px; }}
QCheckBox, QRadioButton {{ color: {C.INK}; }}
QSpinBox, QDateEdit {{ background: {C.PAPER}; border: 1px solid {C.LINE}; border-radius: 6px;
                       padding: 4px; color: {C.INK}; }}
QSlider::groove:horizontal {{ height: 4px; background: {C.LINE}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {C.MUSTARD}; width: 14px; margin: -5px 0; border-radius: 7px; }}
QScrollArea {{ background: {C.GREIGE}; }}
"""


QSS = build_qss()
