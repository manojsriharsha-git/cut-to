"""
Industry page-layout constants (US Letter, Courier 12pt, 6 lines per inch).

Indents are measured in inches from the LEFT EDGE OF THE PAGE, the same way
Final Draft stores them in <ParagraphSpec LeftIndent/RightIndent>.
Phase 1 uses these to write valid FDX ElementSettings; Phase 2 (editor) and
Phase 4 (pagination / PDF) reuse the exact same numbers.
"""
from .ir import T

PAGE_WIDTH_IN = 8.5
PAGE_HEIGHT_IN = 11.0
TOP_MARGIN_IN = 1.0
BOTTOM_MARGIN_IN = 1.0
LINES_PER_INCH = 6
CHARS_PER_INCH = 10            # Courier 12pt
FONT_SIZE_PT = 12

# type: (left_indent, right_indent, space_before_pts, alignment, all_caps, next_on_enter)
ELEMENT_SPECS = {
    T.SCENE_HEADING: (1.50, 7.50, 24, "Left",  True,  T.ACTION),
    T.ACTION:        (1.50, 7.50, 12, "Left",  False, T.ACTION),
    T.CHARACTER:     (3.50, 7.25, 12, "Left",  True,  T.DIALOGUE),
    T.PARENTHETICAL: (3.00, 5.50, 0,  "Left",  False, T.DIALOGUE),
    T.DIALOGUE:      (2.50, 6.00, 0,  "Left",  False, T.ACTION),
    T.TRANSITION:    (5.50, 7.10, 12, "Right", True,  T.SCENE_HEADING),
    T.SHOT:          (1.50, 7.50, 24, "Left",  True,  T.ACTION),
    T.GENERAL:       (1.50, 7.50, 0,  "Left",  False, T.GENERAL),
}


# ---------------------------------------------------------------- templates
# Same element types, different page layout. Values as in ELEMENT_SPECS.
TEMPLATES = {
    "Screenplay": ELEMENT_SPECS,
    "TV Drama": ELEMENT_SPECS,
    "Multi-Camera Sitcom": {
        **ELEMENT_SPECS,
        T.SCENE_HEADING: (1.50, 7.50, 24, "Left", True, T.ACTION),
        T.ACTION:        (1.50, 7.50, 12, "Left", True, T.ACTION),       # action in CAPS
        T.CHARACTER:     (3.50, 7.25, 12, "Left", True, T.DIALOGUE),
        T.PARENTHETICAL: (2.75, 6.00, 0,  "Left", False, T.DIALOGUE),
        T.DIALOGUE:      (2.50, 6.50, 0,  "Left", False, T.ACTION),
    },
    "Stage Play": {
        **ELEMENT_SPECS,
        T.SCENE_HEADING: (1.50, 7.50, 24, "Center", True, T.ACTION),     # ACT ONE, SCENE 1
        T.ACTION:        (3.50, 7.50, 12, "Left", False, T.CHARACTER),   # stage directions
        T.CHARACTER:     (1.50, 7.50, 12, "Center", True, T.DIALOGUE),
        T.PARENTHETICAL: (3.00, 6.00, 0,  "Left", False, T.DIALOGUE),
        T.DIALOGUE:      (1.50, 7.50, 0,  "Left", False, T.CHARACTER),
    },
}
# lines per line of text (multi-camera dialogue is double spaced)
LINE_SPACING = {"Multi-Camera Sitcom": {T.DIALOGUE: 2, T.PARENTHETICAL: 2}}


def specs_for(template: str | None) -> dict:
    return TEMPLATES.get(template or "Screenplay", ELEMENT_SPECS)


def spacing_for(template: str | None, element_type: str) -> int:
    return LINE_SPACING.get(template or "", {}).get(element_type, 1)


def chars_per_line(element_type: str) -> int:
    left, right, *_ = ELEMENT_SPECS.get(element_type, ELEMENT_SPECS[T.ACTION])
    return int(round((right - left) * CHARS_PER_INCH))


def lines_per_page() -> int:
    return int((PAGE_HEIGHT_IN - TOP_MARGIN_IN - BOTTOM_MARGIN_IN) * LINES_PER_INCH)


def estimate_pages(elements) -> int:
    """Rough page count from (type, text) pairs. Exact pagination arrives in Phase 4."""
    import textwrap
    lines = 0
    for etype, text in elements:
        if not text.strip():
            continue
        spec = ELEMENT_SPECS.get(etype, ELEMENT_SPECS[T.ACTION])
        lines += spec[2] // 12                      # blank lines before
        width = chars_per_line(etype)
        for para in text.split("\n"):
            lines += max(1, len(textwrap.wrap(para, width)))
    return max(1, -(-lines // (lines_per_page() - 1)))
