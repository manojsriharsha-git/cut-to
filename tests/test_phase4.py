"""Phase 4: Final Draft page rules (keep-with-next, speech splits, (MORE)/(CONT'D))."""
import os
import random
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
from PySide6.QtCore import Qt                                   # noqa: E402
from PySide6.QtGui import QTextCursor                           # noqa: E402
from PySide6.QtTest import QTest                                # noqa: E402

from app.core import T, Element, Script                         # noqa: E402
from app.core.pagination import Geom, Page, plan, place         # noqa: E402
from app.core.smart import SmartMemory                          # noqa: E402
from app.ui.editor import ScreenplayEditor                      # noqa: E402
from app.ui.pages import measure, actual_lines, page_model   # noqa: E402

PAGE = Page(1056, 96, 96)
L = 16


def g(t, n, margin=L, keep=False):
    return Geom(t, margin, [L] * n, keep)


# ------------------------------------------------------------------ rules (pure Python)
def fill(lines):
    """Action that fills `lines` lines of page 1 (first paragraph has no space before)."""
    return [g(T.ACTION, lines, 0)]


def test_heading_never_last_on_page():
    geoms = fill(50) + [g(T.SCENE_HEADING, 1, 2 * L, True), g(T.ACTION, 3)]
    p = plan(geoms, PAGE)
    assert 1 in p.breaks
    assert PAGE.page(p.lines[1][0]) == 1


def test_character_keeps_two_lines_of_speech():
    geoms = fill(51) + [g(T.CHARACTER, 1, L, True), g(T.DIALOGUE, 4, 0)]
    p = plan(geoms, PAGE)
    assert 1 in p.breaks
    assert PAGE.page(p.lines[1][0]) == PAGE.page(p.lines[2][0]) == 1


def test_long_speech_splits_with_two_lines_each_side():
    geoms = fill(40) + [g(T.CHARACTER, 1, L, True), g(T.DIALOGUE, 20, 0)]
    p = plan(geoms, PAGE)
    assert not p.breaks                                   # 12 lines fit, 8 carry over: allowed
    pages = [PAGE.page(y) for y in p.lines[2]]
    assert pages.count(0) >= 2 and pages.count(1) >= 2


def test_speech_that_would_leave_one_line_moves_whole():
    geoms = fill(51) + [g(T.CHARACTER, 1, L, True), g(T.DIALOGUE, 6, 0)]
    p = plan(geoms, PAGE)                                  # only 1 dialogue line would fit
    assert 1 in p.breaks


def test_page_never_ends_on_parenthetical():
    geoms = fill(48) + [g(T.CHARACTER, 1, L, True), g(T.DIALOGUE, 3, 0),
                        g(T.PARENTHETICAL, 1, 0, True), g(T.DIALOGUE, 5, 0)]
    p = plan(geoms, PAGE)
    assert 3 in p.breaks and PAGE.page(p.lines[3][0]) == 1


def test_action_orphan_line_moves():
    geoms = fill(52) + [g(T.ACTION, 4)]                    # only 1 line would fit
    p = plan(geoms, PAGE)
    assert 1 in p.breaks and PAGE.page(p.lines[1][0]) == 1


def test_heading_goes_with_a_character_that_moves():
    geoms = fill(48) + [g(T.SCENE_HEADING, 1, 2 * L, True), g(T.CHARACTER, 1, L, True),
                        g(T.DIALOGUE, 4, 0)]
    p = plan(geoms, PAGE)
    assert 1 in p.breaks and 2 not in p.breaks
    assert PAGE.page(p.lines[1][0]) == PAGE.page(p.lines[2][0]) == 1


# ------------------------------------------------------------------ editor and Qt
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


def random_script(seed, n=160):
    rnd = random.Random(seed)
    els = []
    for i in range(n):
        r = rnd.random()
        if r < 0.12:
            els.append(Element.plain(T.SCENE_HEADING, f"INT. ROOM {i} - DAY"))
        elif r < 0.45:
            els.append(Element.plain(T.ACTION, " ".join(["rain"] * rnd.randint(3, 60))))
        else:
            els.append(Element.plain(T.CHARACTER, rnd.choice(["MEERA", "ARJUN"])))
            if rnd.random() < 0.3:
                els.append(Element.plain(T.PARENTHETICAL, "(quietly)"))
            els.append(Element.plain(T.DIALOGUE, " ".join(["listen"] * rnd.randint(2, 90))))
    return Script(elements=els)


def check_rules(ed):
    doc = ed.document()
    blocks, geoms = measure(doc)
    lines = actual_lines(doc, blocks)
    h = page_model(ed.dpi).height
    pg = lambda y: int(y // h)                              # noqa: E731
    for i, (b, gm) in enumerate(zip(blocks, geoms)):
        if gm.type == T.SCENE_HEADING and i + 1 < len(blocks):
            assert pg(lines[i][-1]) == pg(lines[i + 1][0]), f"heading alone at page end: {b.text()}"
        if gm.type == T.CHARACTER:
            j = i + 1
            body = []
            while j < len(blocks) and geoms[j].type in (T.DIALOGUE, T.PARENTHETICAL):
                body += lines[j]
                j += 1
            pages = [pg(y) for y in body]
            assert pages[: min(2, len(pages))].count(pg(lines[i][0])) == min(2, len(pages))
            if len(set(pages)) > 1:
                assert pages.count(pages[0]) >= 2 and len(pages) - pages.count(pages[0]) >= 2


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_rules_hold_on_random_scripts(ed, seed):
    ed.load_script(random_script(seed))
    check_rules(ed)
    assert ed.page_count() >= 4


@pytest.mark.parametrize("font", [None, "Courier Prime", "Courier New", "Playfair Display", "Bebas Neue"])
def test_model_matches_qt(ed, font):
    """The pure-Python page model must place every line exactly where Qt does, whatever the
    font's own line height is (it differs between fonts and between Windows and Linux)."""
    from app.ui.fonts import load_all
    load_all()
    for seed in (7, 8, 9):
        s = random_script(seed)
        if font:
            s.extra["font"] = font
        ed.load_script(s)
        doc = ed.document()
        blocks, geoms = measure(doc)
        breaks = {i for i, b in enumerate(blocks) if b.blockFormat().pageBreakPolicy().value & 1}
        model, _ = place(geoms, page_model(ed.dpi), breaks)
        real = actual_lines(doc, blocks)
        for m, r in zip(model, real):
            assert [round(y) for y in m] == [round(y) for y in r]


def test_more_and_contd_where_a_speech_splits(ed):
    els = [Element.plain(T.ACTION, " ".join(["rain"] * 400)),
           Element.plain(T.CHARACTER, "MEERA"),
           Element.plain(T.DIALOGUE, " ".join(["listen to this"] * 120))]
    ed.load_script(Script(elements=els))
    assert ed._splits and ed._splits[0].name == "MEERA"
    s = ed._splits[0]
    h = page_model(ed.dpi).height
    assert int(s.contd_y // h) == int(s.more_y // h) + 1


def test_undo_takes_page_breaks_with_it(ed, app):
    ed.load_script(random_script(11))
    before = ed.to_script()
    breaks_before = [b.blockFormat().pageBreakPolicy() for b in measure(ed.document())[0]]
    c = ed.textCursor()
    c.movePosition(QTextCursor.MoveOperation.Start)
    ed.setTextCursor(c)
    QTest.keyClick(ed, Qt.Key.Key_Escape)
    QTest.keyClick(ed, Qt.Key.Key_End)
    QTest.keyClick(ed, Qt.Key.Key_Return)
    QTest.keyClicks(ed, "A brand new line of action pushes everything down the page.")
    ed._paginate()                                  # what the timer does after typing
    check_rules(ed)
    while ed.document().isUndoAvailable():
        ed.document().undo()
    assert ed.to_script().elements == before.elements
    after = [b.blockFormat().pageBreakPolicy() for b in measure(ed.document())[0]]
    assert after == breaks_before
    ed.document().redo()
    assert ed.document().isUndoAvailable()


def test_plan_is_fast_on_a_long_script():
    """A 300-page script re-paginates well under a second (it runs after every pause in typing)."""
    import time
    rnd = random.Random(5)
    geoms = []
    for _ in range(3000):
        geoms += [g(T.CHARACTER, 1, L, True), g(T.DIALOGUE, rnd.randint(1, 12), 0),
                  g(T.ACTION, rnd.randint(1, 6))]
    t = time.time()
    p = plan(geoms, PAGE)
    assert p.pages > 250 and time.time() - t < 1.0
