from pathlib import Path
import xml.etree.ElementTree as ET

from app.core import T, Script
from app.core.emphasis import parse_emphasis, runs_to_fountain
from app.formats import fountain, fdx, load

SAMPLE = Path(__file__).parent.parent / "samples" / "sample.fountain"


def sig(script: Script):
    """Comparable fingerprint: type, text, styles, scene no., dual, page break."""
    return [(e.type, e.text, [(r.bold, r.italic, r.underline) for r in e.runs],
             e.scene_number, e.dual, e.page_break_before, e.centered)
            for e in script.elements]


def test_fountain_parse_types():
    s = load(SAMPLE)
    types = [e.type for e in s.elements]
    assert types.count(T.SCENE_HEADING) == 3
    assert T.PARENTHETICAL in types and T.TRANSITION in types and T.NOTE in types
    assert s.scenes()[0].scene_number == "1"
    assert s.scenes()[2].text == "FLASHBACK - MEERA'S CHILDHOOD HOME"
    assert s.characters() == ["MEERA", "ARJUN"]
    assert s.title() == "The Last Signal"
    assert dict(s.title_page)["Contact"] == "Spirit Trainings\nHyderabad"


def test_dual_dialogue_marked():
    s = load(SAMPLE)
    duals = [(e.type, e.dual) for e in s.elements if e.dual]
    assert duals == [(T.CHARACTER, 1), (T.DIALOGUE, 1), (T.CHARACTER, 2), (T.DIALOGUE, 2)]


def test_page_break_and_centered():
    s = load(SAMPLE)
    roof = s.scenes()[1]
    assert roof.page_break_before
    assert any(e.centered and e.text == "THE SIGNAL REPEATS" for e in s.elements)


def test_fountain_roundtrip():
    s1 = load(SAMPLE)
    s2 = fountain.parse(fountain.write(s1))
    assert sig(s1) == sig(s2)
    assert s1.title_page == s2.title_page


def test_fdx_roundtrip_core_elements():
    s1 = load(SAMPLE)
    xml = fdx.write(s1)
    ET.fromstring(xml.encode())              # well-formed
    s2 = fdx.parse(xml)
    core = [t for t in T.CORE if t != T.GENERAL]   # Notes/Sections land in General
    core1 = [x for x, e in zip(sig(s1), s1.elements) if e.type in core]
    core2 = [x for x, e in zip(sig(s2), s2.elements) if e.type in core]
    assert core1 == core2
    assert len(s1.elements) == len(s2.elements)       # nothing dropped
    assert s2.title() == "The Last Signal"


def test_fdx_note_survives_roundtrip():
    xml = fdx.write(load(SAMPLE))
    assert "[[Keep this under one page.]]" in xml          # stored as General in FDX
    s2 = fdx.parse(xml)
    assert any(e.type == T.NOTE and e.text == "Keep this under one page."
               for e in s2.elements)


def test_json_roundtrip():
    s1 = load(SAMPLE)
    s2 = Script.from_json(s1.to_json())
    assert sig(s1) == sig(s2) and s1.title_page == s2.title_page


def test_fountain_to_fdx_to_fountain_text_identical():
    s1 = load(SAMPLE)
    s3 = fountain.parse(fountain.write(fdx.parse(fdx.write(s1))))
    assert [e.text for e in s1.elements][:5] == [e.text for e in s3.elements][:5]
    assert len(s1.elements) == len(s3.elements)


def test_emphasis():
    for src in ["plain", "**bold** and *it*", "_under_ ***both***", r"5 \* 3 = 15"]:
        assert runs_to_fountain(parse_emphasis(src)).replace("\\", "") == src.replace("\\", "")
    runs = parse_emphasis("a **b** c")
    assert [(r.text, r.bold) for r in runs] == [("a ", False), ("b", True), (" c", False)]
    assert parse_emphasis("odd *marker")[0].text == "odd *marker"
