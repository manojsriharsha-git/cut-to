from app.core import T
from app.core.smart import (SmartMemory, Stats, split_heading, classify_typed, live_retype,
                            looks_like_character, ENTER_NEXT, EMPTY_ENTER, TAB_NEXT)

S, A, C, P, D, TR = T.SCENE_HEADING, T.ACTION, T.CHARACTER, T.PARENTHETICAL, T.DIALOGUE, T.TRANSITION

SCRIPT = [
    (S, "INT. OBSERVATORY - NIGHT"), (A, "Dust."),
    (C, "MEERA"), (D, "That's not noise."), (C, "ARJUN (O.S.)"), (D, "Everything is."),
    (TR, "CUT TO:"),
    (S, "EXT. OBSERVATORY ROOF - CONTINUOUS"), (A, "Wind."),
    (C, "ARJUN"), (D, "Cold."),
    (TR, "CUT TO:"),
    (S, "INT. OBSERVATORY - NIGHT"), (A, "Back inside."),
]


def mem(tmp_path=None):
    m = SmartMemory(tmp_path / "mem.json" if tmp_path else None)
    m.set_document(SCRIPT, "a.fdx")
    return m


def test_split_heading():
    assert split_heading("int. house - kitchen - night") == ("INT.", "HOUSE - KITCHEN", "NIGHT")
    assert split_heading("I/E CAR - MOVING - DAY")[0] == "INT./EXT."
    assert split_heading("EXT. FIELD") == ("EXT.", "FIELD", "")


def test_flow_tables():
    assert ENTER_NEXT[C] == D and ENTER_NEXT[D] == A and ENTER_NEXT[TR] == S
    assert EMPTY_ENTER[A] == TR and EMPTY_ENTER[TR] == S      # Enter, Enter -> transition -> scene
    assert TAB_NEXT[A] == C and TAB_NEXT[D] == P


def test_smart_reclassify_on_enter():
    assert classify_typed(A, "int. kitchen - day") == S
    assert classify_typed(A, "SMASH CUT TO:") == TR
    assert classify_typed(A, "MEERA") == C
    assert classify_typed(A, "MEERA (V.O.)") == C
    assert classify_typed(A, "BOOM!") is None
    assert classify_typed(A, "She walks in.") is None
    assert classify_typed(D, "MEERA") is None
    assert looks_like_character("Meera", known=[]) is False


def test_live_retype():
    assert live_retype(A, "int. ") == S
    assert live_retype(A, "ext. r") == S
    assert live_retype(A, "interesting ") is None
    assert live_retype(D, "(quietly") == P


def test_predict_next_heading_learns_sequence():
    m = mem()
    before = SCRIPT[:3]                       # cursor is inside the OBSERVATORY scene
    assert m.predict_next_heading(before) == "EXT. OBSERVATORY ROOF - CONTINUOUS"
    assert m.predict_next_heading(SCRIPT[:9]) == "INT. OBSERVATORY - NIGHT"


def test_heading_completion_stages():
    m = mem()
    c = m.complete(S, "", SCRIPT[:3])
    assert c.ghost.text == "EXT. OBSERVATORY ROOF - CONTINUOUS"
    assert any(s.label == "INT." and not s.final for s in c.items)

    c = m.complete(S, "e")
    assert c.ghost and c.ghost.text.startswith("E")

    c = m.complete(S, "int. obs")
    assert c.ghost.text == "INT. OBSERVATORY - NIGHT"
    assert c.items[0].text == "INT. OBSERVATORY - " and not c.items[0].final

    c = m.complete(S, "int. observatory - n")
    assert c.ghost.text == "INT. OBSERVATORY - NIGHT" and c.ghost.final

    c = m.complete(S, "int. kitchen - mo")
    assert c.ghost.text == "INT. KITCHEN - MOMENTS LATER"


def test_speaker_alternation_and_contd():
    m = mem()
    before = SCRIPT[:6]   # MEERA, ARJUN spoke
    c = m.complete(C, "", before)
    assert c.ghost.text == "MEERA"
    c = m.complete(C, "a", before)
    assert c.ghost.text == "ARJUN"
    before2 = SCRIPT[7:11] + [(A, "He shivers.")]    # ARJUN spoke, then action
    assert m.complete(C, "ar", before2).items[0].text == "ARJUN (CONT'D)"
    c = m.complete(C, "MEERA (v")
    assert c.ghost.text == "MEERA (V.O.)"


def test_transition_completion():
    m = mem()
    c = m.complete(TR, "")
    assert c.ghost is None and c.items[0].text == "CUT TO:"     # empty -> Enter moves on
    assert m.complete(TR, "sm").ghost.text == "SMASH CUT TO:"


def test_memory_persists_across_documents(tmp_path):
    m = mem(tmp_path)
    m.commit()
    m2 = SmartMemory(tmp_path / "mem.json")
    m2.set_document([], "b.fdx")                 # brand-new script
    assert "MEERA" in m2.known_characters()
    assert m2.complete(S, "ext. obs").ghost.text == "EXT. OBSERVATORY ROOF - CONTINUOUS"


def test_stats_roundtrip():
    s = Stats.from_elements(SCRIPT)
    s2 = Stats.from_dict(s.to_dict())
    assert s2.loc_next == s.loc_next and s2.characters == s.characters


def test_capital_to_make():
    from app.core.smart import capital_to_make as cap
    assert cap("he ", 3) == 0
    assert cap("He sits. she ", 13) == 9
    assert cap('"wait ', 6) == 1
    assert cap("Mr. smith ", 10) is None          # abbreviation, not a new sentence
    assert cap("And then... i ", 14) is None      # an ellipsis carries on the sentence
    assert cap("He sits. She ", 13) is None       # already a capital


def test_one_suggestion_per_character():
    """'Manoj (V.O.)' and 'MANOJ' are one character, so SmartType offers one name."""
    from app.core.smart import SmartMemory, Stats, base_name
    els = [(T.SCENE_HEADING, "INT. HOUSE - DAY"), (T.CHARACTER, "Manoj (v.o.)"),
           (T.DIALOGUE, "Hi."), (T.ACTION, "He sits.")]
    m = SmartMemory(None)
    m.set_document(els, "k")
    texts = [s.text for s in m.complete(T.CHARACTER, "M", els).items]
    assert texts == ["MANOJ (CONT'D)"]
    assert base_name("manoj v.o.") == base_name("MANOJ (O.S.)") == "MANOJ"
    assert dict(Stats.from_dict({"characters": {"MANOJ (V.O.)": 3, "MANOJ": 2}}).characters) == {"MANOJ": 5}
