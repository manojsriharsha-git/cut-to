"""
SmartType: flow rules + learning memory.  Pure Python (no Qt) so it is unit-tested.

Two jobs:
1. FLOW  - what element comes next on Enter / Tab, and when typed text means the
           paragraph is really another element ("int." -> Scene Heading, an
           ALL-CAPS name -> Character, "CUT TO:" -> Transition).
2. MEMORY - learns scene headings (intro / location / time), the order locations
           follow each other, characters and who answers whom, and transitions.
           It predicts the next scene heading, the next speaker, and completes
           what you are typing. The current document weighs 3x; every script you
           have saved before is the long-term memory.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .ir import T

# ----------------------------------------------------------------------- constants
INTROS = ["INT.", "EXT.", "INT./EXT.", "EST."]
DEFAULT_TIMES = ["DAY", "NIGHT", "CONTINUOUS", "LATER", "MOMENTS LATER", "MORNING",
                 "EVENING", "SAME", "DAWN", "DUSK"]
DEFAULT_TRANSITIONS = ["CUT TO:", "DISSOLVE TO:", "SMASH CUT TO:", "MATCH CUT TO:",
                       "JUMP CUT TO:", "FADE OUT.", "FADE TO BLACK.", "FADE IN:"]
EXTENSIONS = ["V.O.", "O.S.", "O.C.", "CONT'D"]

INTRO_RE = re.compile(r"^(INT\.?\s*/\s*EXT\.?|I\s*/\s*E\.?|INT\.|EXT\.|EST\.)\s*", re.I)
CAPS_TYPES = {T.SCENE_HEADING, T.CHARACTER, T.TRANSITION, T.SHOT}

# Enter at the end of a non-empty paragraph
ENTER_NEXT = {
    T.SCENE_HEADING: T.ACTION, T.ACTION: T.ACTION, T.CHARACTER: T.DIALOGUE,
    T.PARENTHETICAL: T.DIALOGUE, T.DIALOGUE: T.ACTION, T.TRANSITION: T.SCENE_HEADING,
    T.SHOT: T.ACTION, T.GENERAL: T.GENERAL,
}
# Enter on an EMPTY paragraph changes it in place:  Action -> Transition -> Scene Heading
EMPTY_ENTER = {
    T.ACTION: T.TRANSITION, T.TRANSITION: T.SCENE_HEADING, T.SCENE_HEADING: T.ACTION,
    T.CHARACTER: T.ACTION, T.DIALOGUE: T.ACTION, T.PARENTHETICAL: T.DIALOGUE,
    T.SHOT: T.ACTION, T.GENERAL: T.ACTION,
}
# Tab / Shift+Tab cycle the current paragraph (the usual screenwriting convention)
TAB_NEXT = {
    T.ACTION: T.CHARACTER, T.CHARACTER: T.TRANSITION, T.TRANSITION: T.SCENE_HEADING,
    T.SCENE_HEADING: T.ACTION, T.DIALOGUE: T.PARENTHETICAL, T.PARENTHETICAL: T.DIALOGUE,
    T.SHOT: T.ACTION, T.GENERAL: T.ACTION,
}
SHIFT_TAB_NEXT = {
    T.CHARACTER: T.ACTION, T.TRANSITION: T.CHARACTER, T.SCENE_HEADING: T.TRANSITION,
    T.ACTION: T.SCENE_HEADING, T.PARENTHETICAL: T.DIALOGUE, T.DIALOGUE: T.CHARACTER,
    T.SHOT: T.ACTION, T.GENERAL: T.ACTION,
}


# ----------------------------------------------------------------------- parsing helpers
def normalize_intro(raw: str) -> str:
    r = re.sub(r"\s", "", raw.upper())
    if r.startswith("I/E") or "/" in r:
        return "INT./EXT."
    return r if r.endswith(".") else r + "."


def split_heading(heading: str) -> tuple[str, str, str]:
    """'INT. HOUSE - KITCHEN - NIGHT' -> ('INT.', 'HOUSE - KITCHEN', 'NIGHT')."""
    h = " ".join(heading.strip().upper().split())
    m = INTRO_RE.match(h)
    intro = normalize_intro(m.group(1)) if m else ""
    rest = h[m.end():] if m else h
    parts = rest.split(" - ")
    if len(parts) > 1:
        return intro, " - ".join(parts[:-1]).strip(), parts[-1].strip()
    return intro, rest.strip(), ""


def join_heading(intro: str, loc: str, time: str = "") -> str:
    s = f"{intro} {loc}".strip()
    return f"{s} - {time}" if time else s


# an extension typed without brackets: "MANOJ V.O.", "MANOJ O.S", "MANOJ CONT'D"
_BARE_EXT = re.compile(r"\s+(V\.?\s?O\.?|O\.?\s?S\.?|O\.?\s?C\.?|CONT[’']?D\.?)$")


def base_name(character_line: str) -> str:
    """The character's name alone: no (V.O.), (O.S.), (CONT'D) or dual-dialogue ^."""
    name = character_line.upper().split("(")[0].strip().rstrip("^").strip()
    return _BARE_EXT.sub("", name).strip()


# --------------------------------------------------------------- auto-capitalise
_ABBREVIATIONS = {"mr.", "mrs.", "ms.", "dr.", "st.", "vs.", "e.g.", "i.e.", "etc.", "jr.", "sr.",
                  "no.", "approx.", "prof.", "lt.", "sgt.", "capt.", "col.", "gen.", "mt."}


def capital_to_make(text: str, pos: int) -> int | None:
    """A space was just typed at text[pos - 1]. If the word before it starts a paragraph or a
    sentence and begins with a small letter, return that letter's index (else None)."""
    if pos < 2 or text[pos - 1] != " " or text[pos - 2].isspace():
        return None
    start = pos - 2
    while start > 0 and not text[start - 1].isspace():
        start -= 1
    i = start
    while i < pos - 1 and text[i] in "\"'“‘([":   # skip an opening quote or bracket
        i += 1
    if i >= pos - 1 or not text[i].islower():
        return None
    before = text[:start].rstrip()
    if before:
        prev = before.split()[-1].rstrip("\"'”’)]")
        if not prev.endswith((".", "!", "?")) or prev.endswith(("..", "…")):
            return None
        if prev.lower().lstrip("\"'“‘([") in _ABBREVIATIONS:
            return None
    return i


def looks_like_character(text: str, known: Iterable[str] = ()) -> bool:
    s = text.strip()
    name = base_name(s)
    raw = s.split("(")[0].strip()
    if not name or raw != raw.upper() or not any(c.isalpha() for c in name):
        return False
    if name in set(known):
        return True
    if any(c.islower() for c in s) or len(name) > 30 or len(name.split()) > 4:
        return False
    return not name.endswith((".", "!", "?", ",", ":", ";", "-", "—"))


def classify_typed(etype: str, text: str, known: Iterable[str] = ()) -> str | None:
    """On Enter: does what was typed in this paragraph mean another element?"""
    s = text.strip()
    if etype != T.ACTION or not s:
        return None
    if INTRO_RE.match(s) and len(s) > 4:
        return T.SCENE_HEADING
    if s.isupper() and (s.endswith(" TO:") or s in ("FADE OUT.", "FADE TO BLACK.", "FADE IN:")):
        return T.TRANSITION
    if looks_like_character(s, known):
        return T.CHARACTER
    return None


def live_retype(etype: str, text: str) -> str | None:
    """While typing: switch element immediately (e.g. typing 'int.' makes a scene heading)."""
    s = text.lstrip()
    if etype == T.ACTION and re.match(r"^(int|ext|est|i/e|int\./ext)\.?\s", s, re.I) \
            and ("." in s.split()[0] or s[:3].lower() == "i/e"):
        return T.SCENE_HEADING
    if etype == T.DIALOGUE and s.startswith("("):
        return T.PARENTHETICAL
    return None


# ----------------------------------------------------------------------- statistics
class Stats:
    """Counts learned from one document."""
    FIELDS = ("headings", "locations", "times", "intros", "characters", "transitions")
    NESTED = ("time_by_loc", "intro_by_loc", "loc_next", "speaker_next")

    def __init__(self):
        for f in self.FIELDS:
            setattr(self, f, Counter())
        for f in self.NESTED:
            setattr(self, f, {})

    @staticmethod
    def _bump(nested: dict, key: str, val: str, n: int = 1):
        nested.setdefault(key, Counter())[val] += n

    @classmethod
    def from_elements(cls, elements: Iterable[tuple[str, str]]) -> "Stats":
        s = cls()
        prev_loc = None
        prev_speaker = None
        for etype, text in elements:
            text = text.strip()
            if not text:
                continue
            if etype == T.SCENE_HEADING:
                intro, loc, time = split_heading(text)
                if not loc:
                    continue
                s.headings[join_heading(intro, loc, time)] += 1
                s.locations[loc] += 1
                if intro:
                    s.intros[intro] += 1
                    cls._bump(s.intro_by_loc, loc, intro)
                if time:
                    s.times[time] += 1
                    cls._bump(s.time_by_loc, loc, time)
                if prev_loc and prev_loc != loc:
                    cls._bump(s.loc_next, prev_loc, loc)
                prev_loc, prev_speaker = loc, None
            elif etype == T.CHARACTER:
                name = base_name(text)
                if name:
                    s.characters[name] += 1
                    if prev_speaker and prev_speaker != name:
                        cls._bump(s.speaker_next, prev_speaker, name)
                    prev_speaker = name
            elif etype == T.TRANSITION:
                s.transitions[text.upper()] += 1
        return s

    def merge(self, other: "Stats", weight: int = 1) -> "Stats":
        for f in self.FIELDS:
            c = getattr(self, f)
            for k, v in getattr(other, f).items():
                c[k] += v * weight
        for f in self.NESTED:
            mine = getattr(self, f)
            for k, sub in getattr(other, f).items():
                for v, n in sub.items():
                    self._bump(mine, k, v, n * weight)
        return self

    def to_dict(self) -> dict:
        d = {f: dict(getattr(self, f)) for f in self.FIELDS}
        d.update({f: {k: dict(v) for k, v in getattr(self, f).items()} for f in self.NESTED})
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Stats":
        s = cls()
        for f in cls.FIELDS:
            getattr(s, f).update(d.get(f, {}))
        for f in cls.NESTED:
            setattr(s, f, {k: Counter(v) for k, v in d.get(f, {}).items()})
        # older files may hold "NAME (V.O.)" as its own name: fold it into NAME
        names = Counter()
        for k, v in s.characters.items():
            names[base_name(k)] += v
        s.characters = names
        talk = {}
        for k, sub in s.speaker_next.items():
            for v, n in sub.items():
                if base_name(k) != base_name(v):
                    cls._bump(talk, base_name(k), base_name(v), n)
        s.speaker_next = talk
        return s


# ----------------------------------------------------------------------- suggestions
@dataclass
class Suggestion:
    text: str            # full paragraph text after accepting
    final: bool = True   # True -> Enter also moves on to the next element
    label: str = ""      # what the popup shows (defaults to text)

    def __post_init__(self):
        self.label = self.label or self.text


@dataclass
class Completion:
    items: list[Suggestion]
    ghost: Suggestion | None = None   # inline grey prediction (extends what is typed)


def _rank(counter: Counter, keys: Iterable[str] | None = None) -> list[str]:
    keys = counter.keys() if keys is None else keys
    return sorted(keys, key=lambda k: -counter.get(k, 0))


def _dedupe(items: list[Suggestion]) -> list[Suggestion]:
    seen, out = set(), []
    for s in items:
        if s.text not in seen:
            seen.add(s.text)
            out.append(s)
    return out


class SmartMemory:
    DOC_WEIGHT = 3
    MAX_ITEMS = 8

    def __init__(self, store_path: str | Path | None = None):
        self.store_path = Path(store_path) if store_path else None
        self.store: dict[str, dict] = {}          # doc key (file path) -> Stats dict
        self.doc_key: str | None = None
        self.doc = Stats()
        self._others = Stats()
        self.all = Stats()
        self._load()
        self._rebuild()

    # ---------------- persistence
    def _load(self):
        if self.store_path and self.store_path.exists():
            try:
                self.store = json.loads(self.store_path.read_text(encoding="utf-8")).get("docs", {})
            except (OSError, ValueError):
                self.store = {}

    def _save(self):
        if not self.store_path:
            return
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.store_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "docs": self.store}), encoding="utf-8")
        tmp.replace(self.store_path)

    def _rebuild(self):
        self._others = Stats()
        for key, d in self.store.items():
            if key != self.doc_key:
                self._others.merge(Stats.from_dict(d))
        self._combine()

    def _combine(self):
        self.all = Stats().merge(self._others).merge(self.doc, self.DOC_WEIGHT)

    # ---------------- document lifecycle
    def set_document(self, elements: Iterable[tuple[str, str]], doc_key: str | None = None):
        """Call on open and (debounced) while typing."""
        if doc_key != self.doc_key:
            self.doc_key = doc_key
            self.doc = Stats.from_elements(elements)
            self._rebuild()
        else:
            self.doc = Stats.from_elements(elements)
            self._combine()

    def commit(self):
        """Call on save: this document joins long-term memory under its path."""
        if self.doc_key:
            self.store[self.doc_key] = self.doc.to_dict()
            self._save()

    def forget_all(self):
        self.store = {}
        self._save()
        self._rebuild()

    # ---------------- predictions
    def known_characters(self) -> list[str]:
        return _rank(self.all.characters)

    def _best_time(self, loc: str) -> str:
        c = self.all.time_by_loc.get(loc)
        if c:
            return c.most_common(1)[0][0]
        return self.all.times.most_common(1)[0][0] if self.all.times else "DAY"

    def _best_intro(self, loc: str) -> str:
        c = self.all.intro_by_loc.get(loc)
        if c:
            return c.most_common(1)[0][0]
        return self.all.intros.most_common(1)[0][0] if self.all.intros else "INT."

    def _full(self, loc: str, intro: str | None = None) -> str:
        return join_heading(intro or self._best_intro(loc), loc, self._best_time(loc))

    def predict_next_heading(self, before: Sequence[tuple[str, str]]) -> str | None:
        prev_loc = None
        for etype, text in reversed(before):
            if etype == T.SCENE_HEADING and text.strip():
                prev_loc = split_heading(text)[1]
                break
        if prev_loc and self.all.loc_next.get(prev_loc):
            return self._full(self.all.loc_next[prev_loc].most_common(1)[0][0])
        ranked = [l for l in _rank(self.all.locations) if l != prev_loc]
        return self._full(ranked[0]) if ranked else None

    @staticmethod
    def _scene_tail(before: Sequence[tuple[str, str]]) -> list[tuple[str, str]]:
        out = []
        for etype, text in reversed(before):
            if etype == T.SCENE_HEADING:
                break
            out.append((etype, text))
        return out[::-1]

    def predict_speaker(self, before: Sequence[tuple[str, str]]) -> str | None:
        scene = self._scene_tail(before)
        speakers = [base_name(t) for e, t in scene if e == T.CHARACTER and t.strip()]
        if speakers:
            last = speakers[-1]
            for name in reversed(speakers[:-1]):      # alternate A, B, A, B ...
                if name != last:
                    return name
            nxt = self.all.speaker_next.get(last)
            if nxt:
                return nxt.most_common(1)[0][0]
            others = [n for n in self.known_characters() if n != last]
            return others[0] if others else None
        return None

    def _contd_for(self, before: Sequence[tuple[str, str]]) -> str | None:
        """Same speaker again after only action lines in this scene -> NAME (CONT'D)."""
        scene = self._scene_tail(before)
        saw_action = False
        for etype, text in reversed(scene):
            if not text.strip():
                continue
            if etype == T.ACTION:
                saw_action = True
            elif etype == T.CHARACTER:
                return base_name(text) if saw_action else None
            elif etype not in (T.DIALOGUE, T.PARENTHETICAL):
                return None
        return None

    # ---------------- completion entry point
    def complete(self, etype: str, text: str, before: Sequence[tuple[str, str]] = ()) -> Completion:
        typed = text.upper()
        if etype == T.SCENE_HEADING:
            c = self._complete_heading(typed, before)
        elif etype == T.CHARACTER:
            c = self._complete_character(typed, before)
        elif etype == T.TRANSITION:
            c = self._complete_transition(typed)
        else:
            return Completion([])
        c.items = _dedupe([s for s in c.items if s.text != typed.strip() or not s.final])
        c.items = [s for s in c.items if s.text != typed][: self.MAX_ITEMS]
        if c.ghost and (not c.ghost.text.startswith(typed) or c.ghost.text == typed):
            c.ghost = None
        return c

    def _complete_heading(self, typed: str, before) -> Completion:
        if not typed.strip():
            pred = self.predict_next_heading(before)
            items = [Suggestion(i + " ", False, i) for i in _rank(self.all.intros, INTROS)]
            ghost = Suggestion(pred) if pred else None
            if pred:
                items.insert(0, Suggestion(pred))
            return Completion(items, ghost)

        m = INTRO_RE.match(typed)
        if not m:   # still typing the intro
            heads = [Suggestion(h) for h in _rank(self.all.headings) if h.startswith(typed)]
            intros = [Suggestion(i + " ", False, i) for i in _rank(self.all.intros, INTROS)
                      if i.startswith(typed.strip())]
            items = intros + heads
            return Completion(items, items[0] if items else None)

        intro = normalize_intro(m.group(1))
        rest = typed[m.end():]
        prefix = typed[:m.end()]
        if not prefix.endswith(" "):
            prefix += " "

        items: list[Suggestion] = []
        ghost = None
        if " - " in rest:   # typing the time of day
            loc, tpart = rest.rsplit(" - ", 1)
            loc = loc.strip()
            times = list(_rank(self.all.time_by_loc.get(loc, Counter())))
            times += [t for t in _rank(self.all.times) if t not in times]
            times += [t for t in DEFAULT_TIMES if t not in times]
            items = [Suggestion(f"{prefix}{loc} - {t}", True, t)
                     for t in times if t.startswith(tpart.strip()) and t != tpart.strip()]
            ghost = items[0] if items else None
        # typing the location (also covers locations that contain " - ")
        lp = rest.strip()
        # locations already used with this intro (INT./EXT.) first, then by frequency
        locs = sorted(self.all.locations, key=lambda l: (
            self.all.intro_by_loc.get(l, Counter()).get(intro, 0) == 0, -self.all.locations[l]))
        starts = [l for l in locs if l.startswith(lp) and l != lp]
        contains = [l for l in locs if lp and lp in l and not l.startswith(lp)]
        loc_items = [Suggestion(f"{prefix}{l} - ", False, l) for l in starts + contains]
        if lp in self.all.locations and " - " not in rest:
            loc_items = [Suggestion(f"{prefix}{lp} - {t}", True, t)
                         for t in [self._best_time(lp)] +
                         [t for t in DEFAULT_TIMES if t != self._best_time(lp)]][:4] + loc_items
        if ghost is None:
            if starts:
                ghost = Suggestion(prefix + self._full(starts[0], intro).split(" ", 1)[1])
            elif lp in self.all.locations and " - " not in rest:
                ghost = Suggestion(f"{prefix}{lp} - {self._best_time(lp)}")
        return Completion(items + loc_items, ghost)

    def _complete_character(self, typed: str, before) -> Completion:
        if "(" in typed:
            name, ext = typed.split("(", 1)
            name = name.strip()
            items = [Suggestion(f"{name} ({e})", True, e) for e in EXTENSIONS
                     if e.startswith(ext.strip().rstrip(")"))]
            return Completion(items, items[0] if ext.strip() and items else None)

        scene = self._scene_tail(before)
        in_scene = []
        for e, t in reversed(scene):
            if e == T.CHARACTER and t.strip() and base_name(t) not in in_scene:
                in_scene.append(base_name(t))
        ranked = in_scene + [n for n in self.known_characters() if n not in in_scene]
        p = typed.strip()
        names = [n for n in ranked if n.startswith(p)]
        contd = self._contd_for(before)
        # one entry per character: the same speaker again becomes "NAME (CONT'D)"
        items = [Suggestion(f"{n} (CONT'D)" if n == contd else n) for n in names]
        if contd and contd.startswith(p) and contd not in names:
            items.insert(0, Suggestion(f"{contd} (CONT'D)"))
        items.sort(key=lambda it: not it.text.endswith("(CONT'D)"))

        if not p:
            pred = self.predict_speaker(before)
            if contd and pred is None:
                pred = f"{contd} (CONT'D)"
            if pred:
                items = [Suggestion(pred)] + [s for s in items if s.text != pred]
            return Completion(items, Suggestion(pred) if pred else None)
        return Completion(items, items[0] if items else None)

    def _complete_transition(self, typed: str) -> Completion:
        ranked = _rank(self.all.transitions)
        ranked += [t for t in DEFAULT_TRANSITIONS if t not in ranked]
        p = typed.strip()
        items = [Suggestion(t) for t in ranked if t.startswith(p)]
        # Empty transition: show the list but no ghost, so Enter can move on to a Scene Heading
        return Completion(items, items[0] if p and items else None)
