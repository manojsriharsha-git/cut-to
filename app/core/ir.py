"""
Intermediate Representation (IR) for screenplays.

Every format (Fountain, FDX, JSON, later DOCX/PDF/RTF) converts TO this model
and FROM this model. Converters never talk to each other directly, so adding a
new format only means writing one reader and one writer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict, replace
from typing import Iterable


class T:
    """Element type names. Values match Final Draft's Paragraph Type strings."""
    SCENE_HEADING = "Scene Heading"
    ACTION = "Action"
    CHARACTER = "Character"
    PARENTHETICAL = "Parenthetical"
    DIALOGUE = "Dialogue"
    TRANSITION = "Transition"
    SHOT = "Shot"
    GENERAL = "General"
    # Not native Final Draft paragraph types (Fountain-only concepts)
    NOTE = "Note"
    SECTION = "Section"
    SYNOPSIS = "Synopsis"
    LYRICS = "Lyrics"
    IMAGE = "Image"          # Screenplay's own: a picture on its own line

    CORE = (SCENE_HEADING, ACTION, CHARACTER, PARENTHETICAL,
            DIALOGUE, TRANSITION, SHOT, GENERAL)
    DIALOGUE_BLOCK = (CHARACTER, PARENTHETICAL, DIALOGUE)


@dataclass
class Run:
    """A span of text sharing one style (Final Draft <Text Style="..."> run)."""
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    color: str | None = None        # text colour "#RRGGBB", None = normal ink
    highlight: str | None = None    # background colour "#RRGGBB"
    link: str | None = None         # hyperlink address
    font: str | None = None         # font family, None = the script's font

    def style(self) -> tuple:
        return (self.bold, self.italic, self.underline, self.strike,
                self.color, self.highlight, self.link, self.font)

    def same_style(self, other: "Run") -> bool:
        return self.style() == other.style()


def merge_runs(runs: Iterable[Run]) -> list[Run]:
    """Join neighbouring runs with identical style; drop empty runs."""
    out: list[Run] = []
    for r in runs:
        if not r.text:
            continue
        if out and out[-1].same_style(r):
            out[-1].text += r.text
        else:
            out.append(replace(r))
    return out


@dataclass
class Element:
    """One screenplay paragraph."""
    type: str
    runs: list[Run] = field(default_factory=list)
    scene_number: str | None = None
    dual: int = 0                    # 0 = normal, 1 = left speaker, 2 = right speaker
    page_break_before: bool = False
    centered: bool = False
    extra: dict = field(default_factory=dict)   # format-specific attrs kept for fidelity

    @property
    def text(self) -> str:
        return "".join(r.text for r in self.runs)

    @classmethod
    def plain(cls, type_: str, text: str, **kw) -> "Element":
        return cls(type_, [Run(text)] if text else [], **kw)

    @classmethod
    def image(cls, name: str, png_base64: str, width_in: float, height_in: float) -> "Element":
        """A picture line. Its text is a placeholder that Fountain/FDX keep as a note."""
        return cls(T.IMAGE, [Run(f"[[Image: {name}]]")],
                   extra={"image": {"name": name, "png": png_base64,
                                    "width_in": round(width_in, 3),
                                    "height_in": round(height_in, 3)}})

    def has_rich_content(self) -> bool:
        """True if this paragraph holds things only .screenplay files keep."""
        return self.type == T.IMAGE or any(r.color or r.highlight or r.link or r.font for r in self.runs)


# Element.extra keys Screenplay uses for its own features (all optional):
#   synopsis, color, storylines   - scene planning (on scene headings)
#   notes                         - ScriptNotes attached to the paragraph
#   revision                      - revision set the paragraph was changed in
#   breakdown, shots              - production breakdown tags and shot list (scene headings)
#   image                         - picture data (Image paragraphs)
# Script.extra holds project-wide data: beats, storylines, character profiles,
# revision sets, locked scene numbers, template, goals.
PLANNING_KEYS = ("synopsis", "color", "storylines", "notes", "revision", "breakdown", "shots")


@dataclass
class Script:
    title_page: list[tuple[str, str]] = field(default_factory=list)  # ordered (key, value)
    elements: list[Element] = field(default_factory=list)
    extra: dict = field(default_factory=dict)                        # project-wide data

    # ---------- queries (used later by navigator / SmartType / reports) ----------
    def scenes(self) -> list[Element]:
        return [e for e in self.elements if e.type == T.SCENE_HEADING]

    def characters(self) -> list[str]:
        """Unique character names in order of first appearance, extensions stripped."""
        seen: dict[str, None] = {}
        for e in self.elements:
            if e.type == T.CHARACTER:
                name = e.text.split("(")[0].strip().rstrip("^").strip()
                if name:
                    seen.setdefault(name, None)
        return list(seen)

    def has_rich_content(self) -> bool:
        return any(e.has_rich_content() for e in self.elements)

    def has_planning_data(self) -> bool:
        """Cards, beats, notes, revisions, breakdown... (kept by .screenplay and .fdx)."""
        return bool(self.extra) or any(k in e.extra for e in self.elements for k in PLANNING_KEYS)

    def title(self) -> str:
        for k, v in self.title_page:
            if k.lower() == "title":
                return v
        return ""

    # ---------- JSON (the IR on disk) ----------
    def to_dict(self) -> dict:
        d = {
            "format": "screenplay-ir",
            "version": 1,
            "title_page": [list(kv) for kv in self.title_page],
            "elements": [asdict(e) for e in self.elements],
        }
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Script":
        els = []
        for e in d.get("elements", []):
            runs = [Run(**r) for r in e.get("runs", [])]
            els.append(Element(
                type=e["type"], runs=runs,
                scene_number=e.get("scene_number"),
                dual=e.get("dual", 0),
                page_break_before=e.get("page_break_before", False),
                centered=e.get("centered", False),
                extra=e.get("extra", {}),
            ))
        tp = [(k, v) for k, v in d.get("title_page", [])]
        return cls(title_page=tp, elements=els, extra=d.get("extra", {}))

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, s: str) -> "Script":
        return cls.from_dict(json.loads(s))
