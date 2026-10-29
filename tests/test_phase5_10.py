"""Phases 5-10: writing comfort, planning, rewrites, production, formats, insights."""
import json

import pytest
from PySide6.QtCore import QMimeData, Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest

from app.core import T, Element, Script
from app.core.analysis import analyse
from app.core import breakdown as bd
from app.core.history import History, Recovery, compare, summary
from app.formats import load, save, loses_content, fdx, fountain
from app.formats.exports import rtf, plain_text
from app.formats.imports import trelby
from app.ui.editor_tools import locked_numbers
from app.ui.writing import _score
from app.ui.editor_extras import smart_paste_elements
from tests.conftest import sample_script


def headings(ed):
    return [e.text for e in ed.to_script().elements if e.type == T.SCENE_HEADING]


# ============================================================ Phase 5: writing comfort
def test_find_and_replace_all_is_one_undo(window):
    ed = window.editor
    ed.load_script(sample_script())
    bar = window.findbar
    bar.open(with_replace=True)
    bar.find.setText("noise")
    bar.refresh()
    assert len(bar.matches) == 2
    bar.replace.setText("static")
    assert bar.replace_all() == 2
    assert "static" in ed.toPlainText() and "noise" not in ed.toPlainText()
    ed.document().undo()
    assert ed.toPlainText().count("noise") == 2


def test_find_in_one_element_and_whole_words(window):
    ed = window.editor
    ed.load_script(sample_script())
    assert len(ed.find_all("MEERA", etype=T.CHARACTER)) == 2
    assert len(ed.find_all("MEERA")) > 2
    assert len(ed.find_all("in", whole=True)) < len(ed.find_all("in"))


def test_goto_scene_and_page(window):
    from app.ui.writing import goto
    ed = window.editor
    ed.load_script(sample_script(3))
    assert goto(ed, "scene", "2")
    assert ed.textCursor().block().text().startswith("EXT. OBSERVATORY ROOF")
    assert goto(ed, "page", "2")
    assert ed.current_page() == 2
    assert not goto(ed, "scene", "99")


def test_rename_character_everywhere(window):
    ed = window.editor
    ed.load_script(sample_script())
    n = ed.rename_character("ARJUN", "Dev", everywhere=True)
    assert n == 3                                     # two cues and one mention in action
    s = ed.to_script()
    cues = [e.text for e in s.elements if e.type == T.CHARACTER]
    assert "DEV (O.S.)" in cues and not any("ARJUN" in c for c in cues)
    assert any("DEV, 20s" in e.text for e in s.elements if e.type == T.ACTION)
    ed.document().undo()
    assert "ARJUN (O.S.)" in [e.text for e in ed.to_script().elements]


def test_copy_paste_keeps_element_types(window, qapp):
    ed = window.editor
    ed.load_script(sample_script())
    doc = ed.document()
    start = doc.findBlockByNumber(4).position()          # MEERA / (whispering) / That's not noise.
    end = doc.findBlockByNumber(6).position() + doc.findBlockByNumber(6).length() - 1
    c = ed.textCursor()
    c.setPosition(start)
    c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(c)
    md = ed.createMimeDataFromSelection()
    c.movePosition(QTextCursor.MoveOperation.End)
    ed.setTextCursor(c)
    QTest.keyClick(ed, Qt.Key.Key_Return)
    ed.insertFromMimeData(md)
    tail = ed.to_script().elements[-3:]
    assert [e.type for e in tail] == [T.CHARACTER, T.PARENTHETICAL, T.DIALOGUE]
    assert tail[2].text == "That's not noise."


def test_smart_paste_of_plain_screenplay_text(window):
    els = smart_paste_elements("INT. KITCHEN - DAY\n\nSteam rises.\n\nMEERA\nTea?")
    assert [e.type for e in els] == [T.SCENE_HEADING, T.ACTION, T.CHARACTER, T.DIALOGUE]
    assert smart_paste_elements("just one line") is None
    ed = window.editor
    ed.load_script(Script())
    md = QMimeData()
    md.setText("INT. KITCHEN - DAY\n\nSteam rises.\n\nMEERA\nTea?")
    ed.insertFromMimeData(md)
    assert [e.type for e in ed.to_script().elements] == [T.SCENE_HEADING, T.ACTION, T.CHARACTER,
                                                          T.DIALOGUE]


def test_command_palette_fuzzy_score():
    assert _score("expdf", "Export PDF") is not None
    assert _score("xyz", "Export PDF") is None
    assert _score("pdf", "Export PDF") < _score("ept", "Export PDF")


def test_themes_switch_and_back(window):
    from app.ui.theme import C
    window.set_theme("Night")
    assert C.NAME == "Night" and window.editor.palette().base().color().name().upper() == C.PAPER
    window.set_theme("Midnight")
    window.set_theme("Day")
    assert C.PAPER == "#FBFAF6"


def test_goals_count_only_typed_words(window):
    ed = window.editor
    ed.load_script(sample_script())
    window._after_open()
    g = window.goals
    before = g.written_today()
    QTest.keyClicks(ed, "three more words ")
    g.tick()
    assert g.written_today() - before == 3
    ed.load_script(sample_script(3))                    # opening a script is not writing
    window._after_open()
    g.tick()
    assert g.written_today() - before == 3
    md = QMimeData()
    md.setText("pasted words never count toward the goal")
    ed.insertFromMimeData(md)
    g.tick()
    assert g.written_today() - before == 3


def test_recovery_and_history(tmp_path):
    rec = Recovery(tmp_path)
    s = sample_script()
    rec.write("abc", s, "/x/a.fdx")
    pending = rec.pending()
    assert pending and pending[0][1] == "/x/a.fdx"
    assert rec.load(pending[0][0]).elements[0].text == s.elements[0].text
    rec.clear("abc")
    assert not rec.pending()
    h = History(tmp_path, keep_auto=3)
    for i in range(5):
        h.snapshot(s, "/x/a.fdx", pages=i)
    h.snapshot(s, "/x/a.fdx", label="Studio draft", auto=False)
    vs = h.versions("/x/a.fdx")
    assert len(vs) == 4 and any(v.label == "Studio draft" for v in vs)
    s2 = sample_script()
    s2.elements[3].runs[0].text = "Changed line."
    changes = compare(s, s2)
    assert summary(changes) == {"added": 1, "removed": 1}


def test_spelling_marks_and_suggests(window, qapp):
    pytest.importorskip("spellchecker")
    ed = window.editor
    ed.load_script(Script(elements=[Element.plain(T.ACTION, "The telescpoe hums. MEERA waits.")]))
    window.set_spelling(True)
    sp = window.speller
    sp.names.add("meera")                                  # character names are never wrong
    assert not sp.ok("telescpoe") and sp.ok("telescope") and sp.ok("Meera")
    assert "telescope" in sp.suggestions("telescpoe")
    c = QTextCursor(ed.document().firstBlock())
    c.setPosition(6)
    acts = ed.spell.menu_actions(c)
    assert acts and acts[0].text() == "telescope"
    acts[0].trigger()
    assert ed.toPlainText().startswith("The telescope")
    window.set_spelling(False)


def test_save_keeps_backup_and_clears_recovery(window, tmp_path):
    ed = window.editor
    ed.load_script(sample_script())
    ed.document().setModified(True)
    window.autosave()
    assert window.recovery.pending()
    assert window._write(tmp_path / "x.cut")
    assert not window.recovery.pending()
    assert window.history.versions(str(tmp_path / "x.cut"))


# ============================================================ Phase 6: planning
def test_move_scene_keeps_cards_and_undoes(window):
    ed = window.editor
    ed.load_script(sample_script())
    ed.set_block_extra(ed.scenes()[0][0], "synopsis", "They find the signal")
    before = headings(ed)
    ed.move_scene(0, 3)
    after = headings(ed)
    assert after == before[1:] + before[:1]
    moved = [e for e in ed.to_script().elements if e.type == T.SCENE_HEADING][-1]
    assert moved.extra.get("synopsis") == "They find the signal" and moved.scene_number == "1"
    ed.document().undo()
    assert headings(ed) == before


def test_cards_view_lists_scenes_and_reorders(window, qapp):
    ed = window.editor
    ed.load_script(sample_script(2))
    window.show_view("cards")
    cards = window.features[0].cards
    assert cards.list.count() == len(ed.scenes())
    first = headings(ed)[0]
    cards._moved(0, 2)
    assert headings(ed)[1] == first


def test_beat_board_persists_in_project(window, tmp_path):
    from PySide6.QtCore import QPointF
    window.show_view("board")
    board = window.features[0].board
    a = board.add_beat(QPointF(0, 0), "Meera hears it", "The signal")
    b = board.add_beat(QPointF(300, 0), "Nobody believes her")
    board.connect(a, b)
    board._save_timer.timeout.emit()
    window._write(tmp_path / "b.fdx")
    back = load(tmp_path / "b.fdx")
    assert [x["title"] for x in back.extra["beats"]] == ["Meera hears it", "Nobody believes her"]
    assert back.extra["links"] == [[a.beat["id"], b.beat["id"]]]


def test_character_profile_and_lens(window):
    ed = window.editor
    ed.load_script(sample_script())
    window.show_view("characters")
    view = window.features[0].characters
    view.refresh()
    assert view.current in ("MEERA", "ARJUN")
    view.fields["want"].setText("To be believed")
    view.fields["want"].textEdited.emit("To be believed")
    assert ed.project["characters"][view.current]["want"] == "To be believed"
    view.lens.setChecked(True)
    assert ed._layers["lens"]


def test_scene_ribbon_and_structure(window):
    ed = window.editor
    ed.load_script(sample_script(3))
    ribbon = window.features[0].ribbon
    ribbon.refresh()
    assert len(ribbon.infos) == len(ed.scenes())


# ============================================================ Phase 7: rewrites
def test_script_notes_live_on_paragraphs(window, tmp_path):
    ed = window.editor
    ed.load_script(sample_script())
    rw = window.features[1]
    ed.set_block_extra(3, "notes", [{"id": "n1", "text": "Tighten this", "color": "#E4C85D"}])
    assert rw.all_notes()[0][1]["text"] == "Tighten this"
    save(ed.to_script(), tmp_path / "n.fdx")
    back = load(tmp_path / "n.fdx")
    assert any(e.extra.get("notes") for e in back.elements)


def test_revision_mode_marks_changed_paragraphs(window, qapp):
    ed = window.editor
    ed.load_script(sample_script())
    rw = window.features[1]
    ed.project["revisions"] = {"level": 2, "mode": True}
    rw.apply()
    block = ed.document().findBlockByNumber(3)
    c = QTextCursor(block)
    c.movePosition(QTextCursor.MoveOperation.EndOfBlock)
    ed.setTextCursor(c)
    QTest.keyClicks(ed, " Quietly.")
    ed._paginate()
    s = ed.to_script()
    revised = [e for e in s.elements if e.extra.get("revision")]
    assert len(revised) == 1 and revised[0].extra["revision"] == 2
    assert rw.page_extras()["header"].startswith("Pink Rev.")
    ed.document().undo()
    assert not any(e.extra.get("revision") for e in ed.to_script().elements)


# ============================================================ Phase 8: production
def test_locked_scene_numbers():
    assert locked_numbers(["1", None, "2", None, None]) == ["1", "1A", "2", "2A", "2B"]
    assert locked_numbers([None, "1"]) == ["A1", "1"]
    assert locked_numbers(["5", "5A", None, "6"]) == ["5", "5A", "5B", "6"]


def test_lock_and_add_scene_gets_a_number(window):
    ed = window.editor
    ed.load_script(sample_script())
    ed.number_scenes()
    window.features[2].toggle_lock(True)
    ed.add_scene("INT. LAB - DAY", after=0)
    window.number_scenes()
    nums = [n for _b, _h, n, _p in ed.scenes()]
    assert nums == ["1", "1A", "2", "3"]


def test_breakdown_tags_and_exports(window, tmp_path):
    ed = window.editor
    ed.load_script(sample_script())
    pr = window.features[2]
    pr._tag(ed.scenes()[0][0], "Props", "radio telescope console")
    pr._tag(ed.scenes()[0][0], "Props", "Radio telescope console")       # no duplicates
    from app.ui.production import scene_breakdowns
    data = scene_breakdowns(ed)
    assert data[0].items == {"Props": ["radio telescope console"]}
    assert data[0].cast == ["MEERA", "ARJUN"]
    assert ed._layers["breakdown"]
    assert "radio telescope console" in bd.breakdown_csv(data)
    html = bd.sheets_html(data, "Test")
    assert "BREAKDOWN SHEET" in html and "Props" in html
    from app.ui.production import write_html_pdf
    write_html_pdf(html, str(tmp_path / "b.pdf"))
    assert (tmp_path / "b.pdf").stat().st_size > 1000


def test_shot_list_saved_on_scene(window):
    ed = window.editor
    ed.load_script(sample_script())
    window.show_view("production")
    view = window.features[2].view
    view.add_shot()
    view.add_shot()
    shots = ed.block_extra(ed.scenes()[0][0])["shots"]
    assert [s["shot"] for s in shots] == ["1", "2"]
    assert "WS" in bd.shots_csv(view.data if view.data[0].shots else
                                __import__("app.ui.production", fromlist=["x"]).scene_breakdowns(ed))


def test_omit_scene_keeps_number(window):
    ed = window.editor
    ed.load_script(sample_script())
    ed.goto_block(ed.scenes()[1][0])
    window.features[2].omit_scene()
    sc = ed.scenes()
    assert sc[1][1] == "OMITTED" and sc[1][2] == "2"


def test_templates_relay_pages(window):
    ed = window.editor
    talk = [Element.plain(T.CHARACTER, "MEERA"), Element.plain(T.DIALOGUE, "Say it again. " * 30)] * 20
    ed.load_script(Script(elements=talk))
    pages = ed.page_count()
    ed.set_template("Multi-Camera Sitcom")
    assert ed.project["template"] == "Multi-Camera Sitcom"
    assert ed.document().findBlockByNumber(1).blockFormat().lineHeight() == 2 * ed.dpi / 6
    assert ed.page_count() > pages                         # double-spaced dialogue
    ed.set_template("Stage Play")
    assert ed.document().findBlockByNumber(0).blockFormat().alignment() & Qt.AlignmentFlag.AlignHCenter


# ============================================================ Phase 9: formats
def test_word_round_trip(tmp_path):
    pytest.importorskip("docx")
    s = sample_script()
    save(s, tmp_path / "a.docx")
    back = load(tmp_path / "a.docx")
    want = [(e.type, e.text) for e in s.elements if e.type in T.CORE]
    got = [(e.type, e.text) for e in back.elements if e.type in T.CORE]
    assert got == want


def test_word_import_of_a_plain_document(tmp_path):
    docx = pytest.importorskip("docx")
    from docx.shared import Inches
    d = docx.Document()
    for text, left in (("INT. HOUSE - DAY", 0), ("Rain on glass.", 0), ("MEERA", 2.0),
                       ("(softly)", 1.5), ("It's here.", 1.0), ("CUT TO:", 4.5)):
        p = d.add_paragraph(text)
        p.paragraph_format.left_indent = Inches(left + 0.5)
    d.save(tmp_path / "plain.docx")
    got = [e.type for e in load(tmp_path / "plain.docx").elements]
    assert got == [T.SCENE_HEADING, T.ACTION, T.CHARACTER, T.PARENTHETICAL, T.DIALOGUE, T.TRANSITION]


def test_pdf_import_reads_our_own_export(window, tmp_path):
    pytest.importorskip("pdfplumber")
    ed = window.editor
    els = [Element.plain(T.SCENE_HEADING, "INT. OBSERVATORY - NIGHT"),
           Element.plain(T.ACTION, "Dust hangs in the beam. " * 60),
           Element.plain(T.CHARACTER, "MEERA"),
           Element.plain(T.PARENTHETICAL, "(whispering)"),
           Element.plain(T.DIALOGUE, "That is not noise, it repeats every eleven seconds. " * 12),
           Element.plain(T.TRANSITION, "CUT TO:")]
    ed.load_script(Script(elements=els))
    from app.ui.pages import export_pdf
    export_pdf(ed.document(), str(tmp_path / "s.pdf"), ed.dpi, [])
    back = load(tmp_path / "s.pdf")
    assert [e.type for e in back.elements] == [e.type for e in els]
    assert back.elements[4].text.split() == els[4].text.split()     # joined across (MORE)/(CONT'D)


def test_rtf_and_text_exports():
    s = sample_script()
    r = rtf(s)
    assert r.startswith("{\\rtf1") and "\\li2880" in r and "OBSERVATORY" in r
    t = plain_text(s)
    assert "\n                    MEERA\n" in t                    # character at 3.5 in
    assert "INT. OBSERVATORY - NIGHT" in t


def test_trelby_and_celtx_imports(tmp_path):
    text = ("#Version 3\n#Start-Script\n.\\INT. ROOM - DAY\n.._Hello there\n"
            "._MEERA\n :Two lines of\n.:dialogue here.\n")
    s = trelby(text)
    assert [(e.type, e.text) for e in s.elements] == [
        (T.SCENE_HEADING, "INT. ROOM - DAY"), (T.ACTION, "_Hello there"), (T.CHARACTER, "MEERA"),
        (T.DIALOGUE, "Two lines of dialogue here.")]
    import zipfile
    with zipfile.ZipFile(tmp_path / "a.celtx", "w") as z:
        z.writestr("script-1.html", "<html><body><p class='sceneheading'>INT. ROOM - DAY</p>"
                                    "<p class='action'>A <b>loud</b> bang.</p><p class='character'>MEERA</p>"
                                    "<p class='dialog'>What was that?</p></body></html>")
    c = load(tmp_path / "a.celtx")
    assert [e.type for e in c.elements] == [T.SCENE_HEADING, T.ACTION, T.CHARACTER, T.DIALOGUE]
    assert c.elements[1].runs[1].bold


def test_fdx_keeps_planning_data_and_scene_colour():
    s = sample_script()
    s.elements[1].extra.update(synopsis="They hear it", color="#E4C85D", storylines=["a"])
    s.extra = {"beats": [{"id": "b1", "title": "Hook"}]}
    xml = fdx.write(s)
    assert "<Summary>" in xml and 'Color="#E4E4C8C85D5D"' in xml
    back = fdx.parse(xml)
    assert back.elements[1].extra["synopsis"] == "They hear it"
    assert back.elements[1].extra["storylines"] == ["a"] and back.extra["beats"][0]["title"] == "Hook"
    assert loses_content(s, "a.fountain") and not loses_content(s, "a.fdx")
    assert fountain.parse(fountain.write(s)).elements          # still valid fountain


# ============================================================ Phase 10: insights
def test_analysis_numbers():
    s = sample_script()
    pairs = [(e.type, e.text) for e in s.elements]
    a = analyse(pairs, [1.0, 0.25, 0.25], 3)
    assert a.scenes == 3 and a.characters[0].name in ("MEERA", "ARJUN")
    assert a.talks[("ARJUN", "MEERA")] >= 3
    assert a.presence[0][0] and not a.presence[0][2]
    assert a.characters[0].pages == 1.0
    assert 0 < a.dialogue_share < 100


def test_insights_view_and_table_read_dialog(window):
    window.editor.load_script(sample_script())
    window.show_view("insights")
    view = window.features[3].view
    assert view.table.rowCount() == 2
    from app.ui.insights import TableRead
    dlg = TableRead(window)                    # works with or without speech voices installed
    dlg.stop()
    dlg.close()


def test_every_view_and_menu_action_exists(window):
    assert list(window.views) == ["script", "cards", "board", "characters", "production", "insights"]
    texts = {a.text() for m in window.menus.values() for a in m.actions()}
    for needed in ("Find…", "Go To Scene or Page…", "Command Palette…", "Version History…",
                   "Lock Scene Numbers", "ScriptNote…", "Table Read…"):
        assert needed in texts or any(needed in t for t in texts), needed


def test_json_ir_keeps_project_data():
    s = sample_script()
    s.extra = {"template": "Stage Play", "structure": [{"name": "Midpoint", "page": 50}]}
    back = Script.from_json(s.to_json())
    assert back.extra == s.extra
    assert json.loads(s.to_json())["extra"]["template"] == "Stage Play"


def test_table_read_speaks_with_voices(window, qapp):
    """Uses Qt's built-in test voice engine, so it runs on any computer."""
    import time
    from app.ui.insights import TableRead
    window.editor.load_script(sample_script())
    window.editor.setTextCursor(QTextCursor(window.editor.document().firstBlock()))
    dlg = TableRead(window, "mock")
    if not dlg.voices:
        pytest.skip("Qt test voices not available")
    dlg.start()
    said = set()
    end = time.time() + 6
    while time.time() < end and len(said) < 6:
        qapp.processEvents()
        said.add(dlg.status.text())
    dlg.stop()
    assert any(s.startswith("MEERA:") for s in said) and any(s.startswith("Narrator:") for s in said)


def test_ctrl_number_keys_in_a_row_never_crash(window, qapp):
    """Ctrl+1, Ctrl+2, Ctrl+3 then Ctrl+4 used to crash: the (parentheses) were typed while
    the page was half updated, and the page-number lookup read a stale line."""
    from PySide6.QtCore import Qt
    ed = window.editor
    ed.load_script(Script())
    ed.setFocus()
    for k in (Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3, Qt.Key.Key_4, Qt.Key.Key_5, Qt.Key.Key_4,
              Qt.Key.Key_6, Qt.Key.Key_4, Qt.Key.Key_8, Qt.Key.Key_4):
        QTest.keyClick(ed, k, Qt.KeyboardModifier.ControlModifier)
        qapp.processEvents()
    assert ed.current_type() == T.PARENTHETICAL and ed.textCursor().block().text() == "()"


def test_enter_at_the_bottom_scrolls_to_the_new_line(window, qapp):
    """Pressing Enter on the last visible line must scroll down with the cursor. It used to
    stay at the top because Enter is handled by the editor itself, not by Qt."""
    from PySide6.QtCore import Qt
    ed = window.editor
    ed.load_script(Script())
    window.resize(1200, 700)
    window.show()
    ed.setFocus()
    for i in range(45):
        QTest.keyClicks(ed, "Line %d" % i)
        QTest.keyClick(ed, Qt.Key.Key_Return)
        qapp.processEvents()
        r = ed.cursorRect()
        assert 0 <= r.top() and r.bottom() <= ed.viewport().height(), i


def test_only_the_sheet_is_paper():
    """The page stylesheet must not paint a background: that would colour the desk around
    the sheet too, and the gap between pages would look like a box on one long page."""
    import re
    from app.ui.theme import build_qss
    assert not re.search(r"QTextEdit#page\s*\{", build_qss())


def test_focus_mode_has_a_visible_way_out(window, qapp):
    """The toolbar says "Focus Mode" in words, and while it's on a ✕ button brings you back."""
    from PySide6.QtWidgets import QToolButton
    labels = [b.text() for b in window.toolbar.findChildren(QToolButton)]
    assert "Focus Mode" in labels
    window.show()
    window.toggle_focus(True)
    qapp.processEvents()
    assert window.focus_exit.isVisible() and "Exit Focus Mode" in window.focus_exit.toolTip()
    window.focus_exit.click()
    qapp.processEvents()
    assert not window.act["focus"].isChecked() and not window.focus_exit.isVisible()
    assert window.toolbar.isVisible()


def test_type_and_font_boxes_fit_their_names(window):
    fm = window.type_combo.fontMetrics()
    for i in range(window.type_combo.count()):
        need = fm.horizontalAdvance(window.type_combo.itemText(i))
        assert need + 24 <= window.type_combo.sizeHint().width(), (need, window.type_combo.width())
    from app.ui.editor import SHORT
    from app.core.ir import T
    assert SHORT[T.PARENTHETICAL] == "Parenthetical" and SHORT[T.SCENE_HEADING] == "Scene Heading"
