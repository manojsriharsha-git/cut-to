"""FDX (.fdx) reader & writer.

.fdx is plain XML, so this is format *interoperability*, not decompiling
any other program. Structure handled:

<FinalDraft DocumentType="Script" Template="No" Version="5">
  <Content>
    <Paragraph Type="Scene Heading" Number="1">
      <SceneProperties .../>
      <Text Style="Bold+Underline">INT. HOUSE - DAY</Text>
    </Paragraph>
    <Paragraph>                      <- dual dialogue wrapper
      <DualDialogue> ...Character/Parenthetical/Dialogue paragraphs... </DualDialogue>
    </Paragraph>
  </Content>
  <TitlePage><Content><Paragraph Alignment="Center"><Text>..</Text></Paragraph></Content></TitlePage>
  <ElementSettings Type="...">...</ElementSettings>
  <CutToData>{json}</CutToData>   <- Cut To:'s own extras (cards, beats, notes...)
</FinalDraft>

Scene colours and summaries also go in the standard place
(<SceneProperties Color=".."><Summary>..</Summary>), so other apps show them too.
Other apps ignore <CutToData>; Cut To: reads it back so nothing is lost.
(Files from before the rename used <ScreenplayData>; those still open.)
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from ..core.ir import T, Run, Element, Script, merge_runs, PLANNING_KEYS
from ..core.layout import ELEMENT_SPECS

FDX_FONT = "Courier Final Draft"
_KNOWN_ATTRS = {"Type", "Number", "StartsNewPage", "Alignment"}


# ------------------------------------------------------------------ colours
def _color_in(value: str | None) -> str | None:
    """FDX stores colours as #RRRRGGGGBBBB (16 bits each); we use #RRGGBB."""
    if not value or not value.startswith("#"):
        return None
    h = value[1:]
    if len(h) == 12:
        h = h[0:2] + h[4:6] + h[8:10]
    if len(h) != 6:
        return None
    h = "#" + h.upper()
    return None if h in ("#000000", "#FFFFFF") else h


def _color_out(value: str) -> str:
    h = value.lstrip("#").upper()
    return "#" + "".join(h[i:i + 2] * 2 for i in (0, 2, 4))


# ------------------------------------------------------------------ reading
def _runs(p: ET.Element) -> list[Run]:
    runs = []
    for t in p.findall("Text"):
        style = t.get("Style", "")
        font = t.get("Font")
        if font and font.lower().startswith("courier"):
            font = None                              # the format's default typewriter face
        runs.append(Run(t.text or "", "Bold" in style, "Italic" in style, "Underline" in style,
                        "Strikeout" in style, _color_in(t.get("Color")),
                        _color_in(t.get("Background")), font=font))
    return merge_runs(runs)


def _para_to_el(p: ET.Element, dual: int = 0) -> Element:
    type_ = p.get("Type") or T.ACTION
    extra = {}
    attrs = {k: v for k, v in p.attrib.items() if k not in _KNOWN_ATTRS}
    if attrs:
        extra["attrs"] = attrs
    sp = p.find("SceneProperties")
    if sp is not None:
        extra["scene_properties"] = dict(sp.attrib)
        color = _color_in(sp.get("Color"))
        if color:
            extra["color"] = color
        summary = sp.find("Summary")
        if summary is not None:
            text = "\n".join("".join(t.text or "" for t in sp_p.findall("Text"))
                             for sp_p in summary.findall("Paragraph")).strip()
            if text:
                extra["synopsis"] = text
    return Element(
        type=type_,
        runs=_runs(p),
        scene_number=p.get("Number") or None,
        dual=dual,
        page_break_before=p.get("StartsNewPage") == "Yes",
        centered=p.get("Alignment") == "Center" and type_ in (T.ACTION, T.GENERAL),
        extra=extra,
    )


def _parse_title_page(root: ET.Element) -> list[tuple[str, str]]:
    content = root.find("TitlePage/Content")
    if content is None:
        return []
    lines = []
    for p in content.findall("Paragraph"):
        txt = "".join(r.text for r in _runs(p)).strip()
        if txt:
            lines.append(txt)
    if not lines:
        return []
    tp = [("Title", lines[0])]
    rest = lines[1:]
    for idx, ln in enumerate(rest):
        low = ln.lower()
        if low in ("by", "written by") or low.endswith(" by"):
            tp.append(("Credit", ln))
            if idx + 1 < len(rest):
                tp.append(("Author", rest[idx + 1]))
            rest = rest[:idx] + rest[idx + 2:]
            break
    if rest:
        tp.append(("Contact", "\n".join(rest)))
    return tp


def parse(data: bytes | str) -> Script:
    if isinstance(data, str):
        data = data.encode("utf-8")
    root = ET.fromstring(data)
    if root.tag != "FinalDraft":
        raise ValueError("Not an FDX document (root is <%s>)" % root.tag)
    els: list[Element] = []
    content = root.find("Content")
    if content is not None:
        for p in content.findall("Paragraph"):
            dd = p.find("DualDialogue")
            if dd is not None:
                speaker = 0
                for sub in dd.findall("Paragraph"):
                    if sub.get("Type") == T.CHARACTER:
                        speaker += 1
                    els.append(_para_to_el(sub, dual=min(max(speaker, 1), 2)))
            else:
                el = _para_to_el(p)
                txt = el.text.strip()
                if el.type == T.GENERAL and txt.startswith("[[") and txt.endswith("]]"):
                    el = Element.plain(T.NOTE, txt[2:-2].strip())   # our own note mapping
                els.append(el)
    script = Script(title_page=_parse_title_page(root), elements=els)
    _read_extras(root, script)
    return script


def _read_extras(root: ET.Element, script: Script):
    node = root.find("CutToData")
    if node is None:
        node = root.find("ScreenplayData")
    if node is None or not (node.text or "").strip():
        return
    try:
        data = json.loads(node.text)
    except ValueError:
        return
    script.extra = data.get("project", {})
    for key, extra in data.get("elements", {}).items():
        i = int(key)
        if 0 <= i < len(script.elements):
            el = script.elements[i]
            el.extra.update(extra)
            if "image" in extra and "png" in extra["image"]:
                el.type = T.IMAGE
                el.runs = [Run(f"[[Image: {extra['image']['name']}]]")]


# ------------------------------------------------------------------ writing
def _add_text(p: ET.Element, runs: list[Run]):
    if not runs:
        ET.SubElement(p, "Text").text = ""
        return
    for r in runs:
        t = ET.SubElement(p, "Text")
        style = "+".join(n for n, on in (("Bold", r.bold), ("Italic", r.italic),
                                         ("Underline", r.underline), ("Strikeout", r.strike)) if on)
        if style:
            t.set("Style", style)
        if r.color:
            t.set("Color", _color_out(r.color))
        if r.highlight:
            t.set("Background", _color_out(r.highlight))
        if r.font:
            t.set("Font", r.font)
        t.text = r.text


def _fdx_type(el: Element) -> tuple[str, list[Run]]:
    """Map IR types that FDX lacks onto General, keeping their text."""
    if el.type == T.NOTE:
        return T.GENERAL, [Run(f"[[{el.text}]]")]
    if el.type == T.SECTION:
        return T.GENERAL, [Run("#" * int(el.extra.get("level", 1)) + " " + el.text)]
    if el.type == T.SYNOPSIS:
        return T.GENERAL, [Run("= " + el.text)]
    if el.type == T.IMAGE:                      # FDX gets a placeholder note
        return T.GENERAL, [Run(el.text)]
    return el.type, [Run(r.text, r.bold, r.italic, r.underline, r.strike, r.color, r.highlight,
                         font=r.font) for r in el.runs]          # links are kept as plain text


def _add_para(parent: ET.Element, el: Element):
    type_, runs = _fdx_type(el)
    p = ET.SubElement(parent, "Paragraph", Type=type_)
    for k, v in el.extra.get("attrs", {}).items():
        p.set(k, v)
    if el.scene_number:
        p.set("Number", el.scene_number)
    if el.page_break_before:
        p.set("StartsNewPage", "Yes")
    if el.centered:
        p.set("Alignment", "Center")
    if type_ == T.SCENE_HEADING:
        sp_attrs = dict(el.extra.get("scene_properties", {}))
        if el.extra.get("color"):
            sp_attrs["Color"] = _color_out(el.extra["color"])
        sp = ET.SubElement(p, "SceneProperties", sp_attrs)
        if el.extra.get("synopsis"):
            summary = ET.SubElement(sp, "Summary")
            for line in el.extra["synopsis"].split("\n"):
                ET.SubElement(ET.SubElement(summary, "Paragraph"), "Text").text = line
    _add_text(p, runs)


def _title_page(root: ET.Element, tp: list[tuple[str, str]]):
    if not tp:
        return
    d = {k.lower(): v for k, v in tp}
    content = ET.SubElement(ET.SubElement(root, "TitlePage"), "Content")

    def para(text: str, align: str = "Center"):
        p = ET.SubElement(content, "Paragraph", Alignment=align)
        ET.SubElement(p, "Text").text = text

    for _ in range(12):
        para("")
    for key in ("title", "credit", "author", "source"):
        if key in d:
            for ln in d[key].split("\n"):
                para(ln)
            para("")
    for _ in range(14):
        para("")
    used = {"title", "credit", "author", "source"}
    for k, v in tp:
        if k.lower() not in used:
            for ln in v.split("\n"):
                para(ln, "Left")


def _element_settings(root: ET.Element):
    for type_, (left, right, before, align, caps, nxt) in ELEMENT_SPECS.items():
        es = ET.SubElement(root, "ElementSettings", Type=type_)
        ET.SubElement(es, "FontSpec", Font=FDX_FONT, Size="12",
                      Style="AllCaps" if caps else "")
        ET.SubElement(es, "ParagraphSpec", Alignment=align, FirstIndent="0.00",
                      Leading="Regular", LeftIndent=f"{left:.2f}",
                      RightIndent=f"{right:.2f}", SpaceBefore=str(before),
                      Spacing="1", StartsNewPage="No")
        ET.SubElement(es, "Behavior", PaginateAs=type_, ReturnKey=nxt, Shortcut="")


def write(script: Script) -> str:
    root = ET.Element("FinalDraft", DocumentType="Script", Template="No", Version="5")
    content = ET.SubElement(root, "Content")
    els = script.elements
    i = 0
    while i < len(els):
        if els[i].dual:
            dd = ET.SubElement(ET.SubElement(content, "Paragraph"), "DualDialogue")
            while i < len(els) and els[i].dual:
                _add_para(dd, els[i])
                i += 1
            continue
        _add_para(content, els[i])
        i += 1
    _title_page(root, script.title_page)
    _element_settings(root)
    extras = {str(i): {k: v for k, v in e.extra.items() if k in PLANNING_KEYS or k == "image"}
              for i, e in enumerate(els)}
    extras = {k: v for k, v in extras.items() if v}
    if extras or script.extra:
        ET.SubElement(root, "CutToData").text = json.dumps(
            {"project": script.extra, "elements": extras}, ensure_ascii=False)
    ET.indent(root, space="  ")
    return ('<?xml version="1.0" encoding="UTF-8" standalone="no" ?>\n'
            + ET.tostring(root, encoding="unicode") + "\n")
