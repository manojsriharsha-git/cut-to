"""Format registry: pick reader/writer by file extension.

.cut is Cut To:'s own format (the IR as JSON). It is the only format
that keeps absolutely everything; .fdx keeps everything except links.
"""
from __future__ import annotations

from pathlib import Path

from ..core.ir import Script
from . import fountain, fdx

# extension -> (description, kind)
READERS = {
    ".cut": ("Cut To:", "json"), ".screenplay": ("Cut To: (old .screenplay)", "json"),
    ".json": ("Script IR", "json"),
    ".fdx": ("FDX", "fdx"),
    ".fountain": ("Fountain", "fountain"), ".spmd": ("Fountain", "fountain"),
    ".txt": ("Plain text / Fountain", "fountain"),
    ".docx": ("Word", "docx"), ".pdf": ("PDF", "pdf"),
    ".celtx": ("Celtx", "celtx"), ".trelby": ("Trelby", "trelby"),
    ".highland": ("Highland", "highland"), ".fadein": ("Fade In", "fadein"),
}
READ_EXT = {ext: kind for ext, (_d, kind) in READERS.items()}
WRITE_EXT = {".cut": "json", ".screenplay": "json", ".json": "json", ".fdx": "fdx", ".fountain": "fountain",
             ".spmd": "fountain", ".txt": "text", ".docx": "docx", ".rtf": "rtf"}
LOSSLESS = {".cut", ".screenplay", ".json"}
NATIVE = (".cut", ".fdx", ".fountain", ".screenplay", ".json", ".spmd", ".txt")
SAVE_FILTERS = "Cut To: (*.cut);;FDX (*.fdx);;Fountain (*.fountain)"
EXPORTS = [("Word Document (.docx)", ".docx"), ("Rich Text (.rtf)", ".rtf"),
           ("Fountain", ".fountain"), ("FDX (.fdx)", ".fdx"), ("Plain Text", ".txt")]


def open_filter() -> str:
    exts = " ".join(f"*{e}" for e in READERS)
    each = ";;".join(f"{d} (*{e})" for e, (d, _k) in READERS.items() if e not in (".json", ".spmd", ".screenplay"))
    return f"All scripts ({exts});;{each};;All files (*)"


def load(path: str | Path) -> Script:
    p = Path(path)
    kind = READ_EXT.get(p.suffix.lower())
    if kind == "fdx":
        return fdx.parse(p.read_bytes())
    if kind == "fountain":
        return fountain.parse(p.read_text(encoding="utf-8-sig"))
    if kind == "json":
        return Script.from_json(p.read_text(encoding="utf-8"))
    if kind == "docx":
        from . import docx_io
        return docx_io.read(p)
    if kind == "pdf":
        from . import pdf_import
        return pdf_import.read(p)
    if kind in ("celtx", "highland", "fadein"):
        from . import imports
        return getattr(imports, kind)(p)
    if kind == "trelby":
        from . import imports
        return imports.trelby(p.read_text(encoding="utf-8", errors="replace"))
    raise ValueError(f"Unsupported input format: {p.suffix}")


def dumps(script: Script, kind: str) -> str:
    if kind == "fdx":
        return fdx.write(script)
    if kind == "fountain":
        return fountain.write(script)
    if kind == "json":
        return script.to_json()
    if kind == "rtf":
        from .exports import rtf
        return rtf(script)
    if kind == "text":
        from .exports import plain_text
        return plain_text(script)
    raise ValueError(f"Unsupported output format: {kind}")


def save(script: Script, path: str | Path) -> None:
    p = Path(path)
    kind = WRITE_EXT.get(p.suffix.lower())
    if not kind:
        raise ValueError(f"Unsupported output format: {p.suffix}")
    if kind == "docx":
        from . import docx_io
        docx_io.write(script, p)
        return
    data = dumps(script, kind)
    tmp = p.with_name(p.name + ".saving")            # never leave a half-written script
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(p)


def loses_content(script: Script, path: str | Path) -> bool:
    """True when saving to this format would drop something.

    .cut keeps everything. .fdx keeps images, colours, cards, beats and notes
    (in a section other apps ignore) but not links. Fountain keeps plain text only."""
    ext = Path(path).suffix.lower()
    if ext in LOSSLESS:
        return False
    if ext == ".fdx":
        return any(r.link for e in script.elements for r in e.runs)
    return script.has_rich_content() or script.has_planning_data()
