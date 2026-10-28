"""
Production reports: scenes, characters, locations and script totals.
Pure Python (no Qt) so it is unit-tested. Input is a list of (element type, text)
pairs, the same thing the editor and SmartType already use.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Sequence

from .ir import T
from .smart import split_heading, base_name

WORD_RE = re.compile(r"[\w']+")


def words(text: str) -> int:
    return len(WORD_RE.findall(text))


@dataclass
class SceneRow:
    number: str                 # scene number if set, else its position (1, 2, 3 ...)
    heading: str
    intro: str
    location: str
    time: str
    characters: list[str] = field(default_factory=list)
    words: int = 0
    index: int = 0              # position of the heading among all paragraphs


@dataclass
class CharacterRow:
    name: str
    speeches: int = 0           # how many times they speak
    words: int = 0              # words of dialogue
    scenes: list[str] = field(default_factory=list)


@dataclass
class LocationRow:
    location: str
    intros: list[str] = field(default_factory=list)
    times: list[str] = field(default_factory=list)
    scenes: list[str] = field(default_factory=list)


@dataclass
class Report:
    scenes: list[SceneRow]
    characters: list[CharacterRow]
    locations: list[LocationRow]
    total_words: int
    dialogue_words: int
    action_words: int

    @property
    def dialogue_share(self) -> int:
        """Percent of words that are dialogue (the rest is action and headings)."""
        return round(100 * self.dialogue_words / self.total_words) if self.total_words else 0


def build(pairs: Sequence[tuple[str, str]],
          scene_numbers: Sequence[str | None] | None = None) -> Report:
    """`scene_numbers` (optional) gives the stored number for each scene heading, in order."""
    scenes: list[SceneRow] = []
    chars: dict[str, CharacterRow] = {}
    locs: dict[str, LocationRow] = {}
    total = dialogue = action = 0
    speaker = None

    for i, (etype, text) in enumerate(pairs):
        text = text.strip()
        if not text:
            continue
        n = words(text)
        total += n
        if etype == T.SCENE_HEADING:
            intro, loc, time = split_heading(text)
            k = len(scenes)
            stored = scene_numbers[k] if scene_numbers and k < len(scene_numbers) else None
            row = SceneRow(stored or str(k + 1), text.upper(), intro, loc, time, index=i)
            scenes.append(row)
            if loc:
                lr = locs.setdefault(loc, LocationRow(loc))
                if intro and intro not in lr.intros:
                    lr.intros.append(intro)
                if time and time not in lr.times:
                    lr.times.append(time)
                lr.scenes.append(row.number)
            speaker = None
            continue
        if scenes:
            scenes[-1].words += n
        if etype == T.CHARACTER:
            speaker = base_name(text)
            cr = chars.setdefault(speaker, CharacterRow(speaker))
            cr.speeches += 1
            if scenes and scenes[-1].number not in cr.scenes:
                cr.scenes.append(scenes[-1].number)
            if scenes and speaker not in scenes[-1].characters:
                scenes[-1].characters.append(speaker)
        elif etype in (T.DIALOGUE, T.PARENTHETICAL):
            dialogue += n
            if speaker and etype == T.DIALOGUE:
                chars[speaker].words += n
        else:
            action += n

    char_rows = sorted(chars.values(), key=lambda c: (-c.speeches, c.name))
    loc_rows = sorted(locs.values(), key=lambda l: (-len(l.scenes), l.location))
    return Report(scenes, char_rows, loc_rows, total, dialogue, action)


# ------------------------------------------------------------------ CSV export
def scenes_csv(r: Report) -> str:
    return _csv(["Scene", "Heading", "INT/EXT", "Location", "Time", "Characters", "Words"],
                [[s.number, s.heading, s.intro, s.location, s.time, ", ".join(s.characters), s.words]
                 for s in r.scenes])


def characters_csv(r: Report) -> str:
    return _csv(["Character", "Speeches", "Words of dialogue", "Scenes", "Scene numbers"],
                [[c.name, c.speeches, c.words, len(c.scenes), ", ".join(c.scenes)]
                 for c in r.characters])


def locations_csv(r: Report) -> str:
    return _csv(["Location", "INT/EXT", "Times of day", "Scenes", "Scene numbers"],
                [[l.location, " / ".join(l.intros), " / ".join(l.times), len(l.scenes),
                  ", ".join(l.scenes)] for l in r.locations])


def _csv(header: list[str], rows: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def eighths(length: float) -> str:
    """Scene length the production way, in eighths of a page: 1.375 pages -> '1 3/8'."""
    n = max(1, round(length * 8))
    whole, part = divmod(n, 8)
    if not part:
        return str(whole)
    return f"{whole} {part}/8" if whole else f"{part}/8"
