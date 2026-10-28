"""
Script analysis for the Insights view (plain data, testable without windows).

Estimates follow industry rules of thumb: one page is about one minute of screen
time; dialogue is spoken at about 150 words a minute.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .ir import T
from .smart import base_name, split_heading

WPM = 150


@dataclass
class CharacterStats:
    name: str
    speeches: int = 0
    words: int = 0
    scenes: list[int] = field(default_factory=list)     # scene indexes where they speak
    pages: float = 0.0                                   # length of those scenes

    @property
    def dialogue_minutes(self) -> float:
        return self.words / WPM


@dataclass
class Analysis:
    pages: int
    scenes: int
    words: int
    dialogue_words: int
    action_words: int
    int_ext: Counter
    day_night: Counter
    scene_lengths: list[float]
    scene_labels: list[str]
    characters: list[CharacterStats]
    presence: list[list[bool]]                           # character x scene
    talks: Counter                                       # (a, b) sorted pair -> exchanges
    dialogue_per_scene: list[float]                      # share of dialogue words per scene

    @property
    def runtime(self) -> int:
        return self.pages

    @property
    def dialogue_share(self) -> int:
        return round(100 * self.dialogue_words / max(1, self.dialogue_words + self.action_words))


def analyse(pairs: list[tuple[str, str]], scene_lengths: list[float], pages: int,
            scene_numbers: list[str] | None = None) -> Analysis:
    chars: dict[str, CharacterStats] = {}
    int_ext, day_night = Counter(), Counter()
    talks: Counter = Counter()
    labels: list[str] = []
    d_words = a_words = 0
    per_scene_d: list[int] = []
    per_scene_all: list[int] = []
    scene = -1
    speaker = last_speaker = None
    for etype, text in pairs:
        text = text.strip()
        if not text:
            continue
        n = len(text.split())
        if etype == T.SCENE_HEADING:
            scene += 1
            intro, _loc, time = split_heading(text)
            int_ext[intro.rstrip(".") or "—"] += 1
            day_night[time or "—"] += 1
            labels.append((scene_numbers[scene] if scene_numbers and scene < len(scene_numbers)
                           and scene_numbers[scene] else str(scene + 1)))
            per_scene_d.append(0)
            per_scene_all.append(0)
            speaker = last_speaker = None
            continue
        if scene >= 0:
            per_scene_all[scene] += n
        if etype == T.CHARACTER:
            speaker = base_name(text)
            st = chars.setdefault(speaker, CharacterStats(speaker))
            st.speeches += 1
            if scene >= 0 and scene not in st.scenes:
                st.scenes.append(scene)
            if last_speaker and last_speaker != speaker:
                talks[tuple(sorted((last_speaker, speaker)))] += 1
            last_speaker = speaker
        elif etype in (T.DIALOGUE, T.PARENTHETICAL):
            d_words += n
            if scene >= 0:
                per_scene_d[scene] += n
            if speaker and etype == T.DIALOGUE:
                chars[speaker].words += n
        else:
            a_words += n
            if etype == T.ACTION:
                speaker = None
    n_scenes = scene + 1
    lengths = list(scene_lengths[:n_scenes]) + [0.0] * max(0, n_scenes - len(scene_lengths))
    for st in chars.values():
        st.pages = sum(lengths[i] for i in st.scenes)
    ranked = sorted(chars.values(), key=lambda c: (-c.words, -c.speeches, c.name))
    presence = [[i in set(c.scenes) for i in range(n_scenes)] for c in ranked]
    share = [d / a if a else 0.0 for d, a in zip(per_scene_d, per_scene_all)]
    return Analysis(pages, n_scenes, d_words + a_words, d_words, a_words, int_ext, day_night,
                    lengths, labels, ranked, presence, talks, share)
