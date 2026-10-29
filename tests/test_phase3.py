"""Phase 3: pages, formatting, images, links, scene numbers, reports, PDF."""
import os
import re
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import Qt                                       # noqa: E402
from PySide6.QtGui import QImage, QColor, QTextCursor                # noqa: E402
from PySide6.QtTest import QTest                                    # noqa: E402

from app.core import T, Run, Element, Script                        # noqa: E402
from app.core import reports                                        # noqa: E402
from app.core.smart import SmartMemory                              # noqa: E402
from app.formats import fdx, fountain, load, save, loses_content    # noqa: E402
from app.ui.editor import ScreenplayEditor                          # noqa: E402
from app.ui.pages import export_pdf, page_size_px                   # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def ed(app, tmp_path):
    e = ScreenplayEditor(SmartMemory(tmp_path / "m.json"))
    e.resize(1100, 900)
    e.show()
    e.setFocus()
    return e


def long_script(scenes=25) -> Script:
    els = []
    for i in range(scenes):
        els += [Element.plain(T.SCENE_HEADING, f"INT. ROOM {i % 5} - DAY"),
                Element.plain(T.ACTION, "Rain hammers the window while the radio hisses. " * 3),
                Element.plain(T.CHARACTER, "MEERA" if i % 2 else "ARJUN"),
                Element.plain(T.DIALOGUE, "We have to listen to it again, all of it, from the start.")]
    return Script(elements=els)


def select(ed, start, end):
    c = ed.textCursor()
    c.setPosition(start)
    c.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(c)


# ------------------------------------------------------------------ model and formats
def test_rich_runs_survive_json_and_fdx():
    s = Script(elements=[Element(T.ACTION, [Run("plain "), Run("gone", strike=True),
                                            Run(" red", color="#C0392B"),
                                            Run(" marked", highlight="#F3E3A3"),
                                            Run(" site", link="https://example.com")])])
    back = Script.from_json(s.to_json())
    assert back.elements[0].runs == s.elements[0].runs
    f = fdx.parse(fdx.write(s)).elements[0].runs
    assert [(r.text, r.strike, r.color, r.highlight) for r in f] == [
        ("plain ", False, None, None), ("gone", True, None, None), (" red", False, "#C0392B", None),
        (" marked", False, None, "#F3E3A3"), (" site", False, None, None)]
    assert '<Text Color="#C0C039392B2B">' in fdx.write(s)


def test_images_survive_fdx_and_become_notes_in_fountain(tmp_path):
    s = Script(elements=[Element.image("pic.png", "iVBOR", 2.0, 1.0)])
    back = fdx.parse(fdx.write(s)).elements[0]                 # kept in <CutToData>
    assert back.type == T.IMAGE and back.extra["image"]["png"] == "iVBOR"
    assert fountain.parse(fountain.write(s)).elements[0].type == T.NOTE
    assert loses_content(s, tmp_path / "a.fountain") and not loses_content(s, tmp_path / "a.fdx")
    assert not loses_content(s, tmp_path / "a.cut")
    save(s, tmp_path / "a.cut")
    assert load(tmp_path / "a.cut").elements[0].extra["image"]["png"] == "iVBOR"


def test_reports():
    pairs = [(T.SCENE_HEADING, "INT. LAB - NIGHT"), (T.ACTION, "Dark."),
             (T.CHARACTER, "MEERA"), (T.DIALOGUE, "Look at this."),
             (T.SCENE_HEADING, "EXT. ROOF - DAY"), (T.CHARACTER, "ARJUN"), (T.DIALOGUE, "Cold."),
             (T.CHARACTER, "MEERA"), (T.DIALOGUE, "Come."),
             (T.SCENE_HEADING, "INT. LAB - DAY")]
    r = reports.build(pairs, ["1", "2", "2A"])
    assert [s.number for s in r.scenes] == ["1", "2", "2A"]
    assert r.characters[0].name == "MEERA" and r.characters[0].speeches == 2
    assert r.characters[0].scenes == ["1", "2"]
    lab = [l for l in r.locations if l.location == "LAB"][0]
    assert lab.times == ["NIGHT", "DAY"] and lab.scenes == ["1", "2A"]
    assert r.dialogue_words == 5 and r.dialogue_share > 0
    assert reports.characters_csv(r).splitlines()[0].startswith("Character,Speeches")
    assert reports.eighths(1.375) == "1 3/8" and reports.eighths(0.1) == "1/8"


# ------------------------------------------------------------------ pages
def test_text_stays_inside_page_margins(ed, app):
    ed.load_script(long_script())
    app.processEvents()
    doc = ed.document()
    _, h = page_size_px(ed.dpi)
    assert ed.page_count() >= 3
    from app.ui.pages import measure, actual_lines
    blocks, geoms = measure(doc)
    for g, ys in zip(geoms, actual_lines(doc, blocks)):
        for y, lh in zip(ys, g.lines):
            off = y - (y // h) * h
            assert ed.dpi - 0.5 <= off and off + lh <= h - ed.dpi + 0.5


def test_page_break_starts_new_page(ed, app):
    QTest.keyClicks(ed, "int. lab - night")
    QTest.keyClick(ed, Qt.Key.Key_Escape)
    QTest.keyClick(ed, Qt.Key.Key_Return)
    QTest.keyClicks(ed, "Quiet.")
    QTest.keyClick(ed, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(ed, "Next page.")
    app.processEvents()
    assert ed.page_count() == 2 and ed.current_page() == 2
    assert ed.to_script().elements[-1].page_break_before


def test_zoom_keeps_text_and_pages(ed, app):
    ed.load_script(long_script(10))
    pages = ed.page_count()
    ed.set_zoom(1.5)
    app.processEvents()
    assert ed.page_count() == pages
    assert len(ed.to_script().elements) == 40 and not ed.document().isModified()


# ------------------------------------------------------------------ formatting and insert
def test_formatting_tools(ed):
    QTest.keyClicks(ed, "int. lab - night")
    QTest.keyClick(ed, Qt.Key.Key_Escape)
    QTest.keyClick(ed, Qt.Key.Key_Return)
    QTest.keyClicks(ed, "one two three four")
    base = ed.textCursor().block().position()
    select(ed, base, base + 3)
    ed.toggle_style("strike")
    select(ed, base + 4, base + 7)
    ed.set_text_color("#C0392B")
    select(ed, base + 8, base + 13)
    ed.set_highlight("#F3E3A3")
    select(ed, base + 14, base + 18)
    ed.change_case("upper")
    runs = ed.to_script().elements[1].runs
    assert [(r.text, r.strike, r.color, r.highlight) for r in runs] == [
        ("One", True, None, None), (" ", False, None, None), ("two", False, "#C0392B", None),
        (" ", False, None, None), ("three", False, None, "#F3E3A3"), (" FOUR", False, None, None)]
    select(ed, base, base + 18)
    ed.clear_formatting()
    assert len(ed.to_script().elements[1].runs) == 1


def test_link_and_image(ed, tmp_path):
    QTest.keyClick(ed, Qt.Key.Key_Escape)
    QTest.keyClick(ed, Qt.Key.Key_Return)                 # -> Action
    QTest.keyClicks(ed, "See ")
    ed.insert_link("the map", "https://example.com/map")
    QTest.keyClicks(ed, " now.")
    runs = ed.to_script().elements[0].runs
    assert [(r.text, r.link) for r in runs] == [("See ", None), ("the map", "https://example.com/map"),
                                               (" now.", None)]
    png = tmp_path / "pic.png"
    img = QImage(400, 200, QImage.Format.Format_RGB32)
    img.fill(QColor("#E4C85D"))
    img.save(str(png))
    assert ed.insert_image(str(png))
    QTest.keyClicks(ed, "After the picture.")
    s = ed.to_script()
    pic = [e for e in s.elements if e.type == T.IMAGE][0]
    assert pic.extra["image"]["width_in"] == pytest.approx(400 / 96, abs=0.01)
    save(s, tmp_path / "x.cut")
    ed.load_script(load(tmp_path / "x.cut"))
    again = ed.to_script()
    assert [e.type for e in again.elements] == [T.ACTION, T.IMAGE, T.ACTION]
    assert again.elements[0].runs[1].link == "https://example.com/map"


def test_scene_numbers_and_navigator_data(ed):
    ed.load_script(long_script(6))
    ed.number_scenes()
    assert [n for _, _, n, _ in ed.scenes()] == ["1", "2", "3", "4", "5", "6"]
    assert [e.scene_number for e in ed.to_script().scenes()] == ["1", "2", "3", "4", "5", "6"]
    lengths = ed.scene_lengths()
    assert len(lengths) == 6 and all(0 < x < 1 for x in lengths)
    ed.document().undo()
    assert all(n is None for _, _, n, _ in ed.scenes())


def test_pdf_export(ed, tmp_path, app):
    ed.load_script(long_script())
    ed.title_page = [("Title", "The Last Signal"), ("Author", "Karthik")]
    QTest.keyClicks(ed, "x")
    ed.insert_link("site", "https://example.com")
    app.processEvents()
    out = tmp_path / "s.pdf"
    export_pdf(ed.document(), str(out), ed.dpi, ed.title_page, "The Last Signal")
    data = out.read_bytes()
    assert data.startswith(b"%PDF")
    pages = len(re.findall(rb"/Type\s*/Page[^s]", data))
    assert pages == ed.page_count() + 1                    # + title page
    assert b"example.com" in data                          # clickable link
