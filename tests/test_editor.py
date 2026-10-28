"""Drives the real editor with simulated keystrokes (runs headless)."""
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import Qt                         # noqa: E402
from PySide6.QtTest import QTest                      # noqa: E402

from app.core import T                                # noqa: E402
from app.core.smart import SmartMemory                # noqa: E402
from app.ui.editor import ScreenplayEditor            # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def ed(app, tmp_path):
    e = ScreenplayEditor(SmartMemory(tmp_path / "m.json"))
    e.resize(1000, 800)
    e.show()
    e.setFocus()
    return e


def typ(ed, text):
    QTest.keyClicks(ed, text)


def key(ed, k, mod=Qt.KeyboardModifier.NoModifier):
    QTest.keyClick(ed, k, mod)


def types(ed):
    return [(t, x) for t, x in ed.element_pairs()]


def test_enter_flow_writes_a_scene(ed):
    typ(ed, "int. kitchen - night");  key(ed, Qt.Key.Key_Escape); key(ed, Qt.Key.Key_Return)
    typ(ed, "Rain hammers the window.");                          key(ed, Qt.Key.Key_Return)
    typ(ed, "MEERA");                 key(ed, Qt.Key.Key_Escape); key(ed, Qt.Key.Key_Return)
    typ(ed, "Who's there?");                                      key(ed, Qt.Key.Key_Return)
    key(ed, Qt.Key.Key_Return)                     # empty Action -> Transition
    typ(ed, "cut");                                key(ed, Qt.Key.Key_Return)   # ghost CUT TO:
    assert types(ed) == [
        (T.SCENE_HEADING, "int. kitchen - night"),
        (T.ACTION, "Rain hammers the window."),
        (T.CHARACTER, "MEERA"),                    # reclassified from Action on Enter
        (T.DIALOGUE, "Who's there?"),
        (T.TRANSITION, "CUT TO:"),
        (T.SCENE_HEADING, ""),                     # Transition -> Scene Heading
    ]


def test_empty_enter_cycles_to_scene(ed):
    key(ed, Qt.Key.Key_Escape); key(ed, Qt.Key.Key_Return)    # empty Scene -> Action
    assert ed.current_type() == T.ACTION
    key(ed, Qt.Key.Key_Return)
    assert ed.current_type() == T.TRANSITION
    key(ed, Qt.Key.Key_Return)
    assert ed.current_type() == T.SCENE_HEADING


def test_tab_and_parenthetical(ed):
    key(ed, Qt.Key.Key_Escape); key(ed, Qt.Key.Key_Return)    # -> Action
    key(ed, Qt.Key.Key_Tab)                                   # -> Character
    typ(ed, "ARJUN"); key(ed, Qt.Key.Key_Escape); key(ed, Qt.Key.Key_Return)
    typ(ed, "(")                                              # Dialogue -> Paren, auto ")"
    assert ed.current_type() == T.PARENTHETICAL
    typ(ed, "quietly"); key(ed, Qt.Key.Key_Return)
    assert ed.current_type() == T.DIALOGUE
    typ(ed, "Hi."); key(ed, Qt.Key.Key_Tab)                   # Dialogue+Tab -> new paren
    assert ed.current_type() == T.PARENTHETICAL
    assert types(ed)[-3:] == [(T.PARENTHETICAL, "(quietly)"), (T.DIALOGUE, "Hi."),
                              (T.PARENTHETICAL, "()")]


def test_smarttype_predicts_heading_and_speaker(ed):
    for line in ("int. observatory - night", "Dust.", "MEERA", "One.", "ARJUN", "Two."):
        typ(ed, line); key(ed, Qt.Key.Key_Escape); key(ed, Qt.Key.Key_Return)
    key(ed, Qt.Key.Key_Tab)                                   # Action -> Character
    ed._after_change()
    assert ed._completion.ghost.text == "MEERA"               # alternates speakers
    key(ed, Qt.Key.Key_Return)                                # accept -> Dialogue
    assert types(ed)[-2:] == [(T.CHARACTER, "MEERA"), (T.DIALOGUE, "")]
    typ(ed, "Three."); key(ed, Qt.Key.Key_Return); key(ed, Qt.Key.Key_Return)
    key(ed, Qt.Key.Key_Return)                                # -> Scene Heading
    ed._on_structure_timer()
    typ(ed, "int. obs")
    assert ed._ghost_rest == "ERVATORY - NIGHT"
    key(ed, Qt.Key.Key_Return)
    assert types(ed)[-2:] == [(T.SCENE_HEADING, "INT. OBSERVATORY - NIGHT"), (T.ACTION, "")]


def test_to_script_uppercases_and_keeps_styles(ed):
    typ(ed, "int. roof - day"); key(ed, Qt.Key.Key_Escape); key(ed, Qt.Key.Key_Return)
    typ(ed, "It ")
    key(ed, Qt.Key.Key_B, Qt.KeyboardModifier.ControlModifier)
    typ(ed, "explodes")
    s = ed.to_script()
    assert s.elements[0].text == "INT. ROOF - DAY"
    assert [(r.text, r.bold) for r in s.elements[1].runs] == [("It ", False), ("explodes", True)]


def test_load_roundtrip(ed):
    from pathlib import Path
    from app.formats import load
    src = load(Path(__file__).parent.parent / "samples" / "sample.fountain")
    ed.load_script(src)
    out = ed.to_script()
    assert [(e.type, e.text, e.dual, e.scene_number) for e in out.elements] == \
           [(e.type, e.text, e.dual, e.scene_number) for e in src.elements]
