"""
Safety nets, in plain files under the app's data folder:

  recovery/   a copy of every open script with unsaved changes, rewritten every minute.
              Deleted when you save or close normally; offered back after a crash.
  history/    a snapshot every time you save (Final Draft calls these backups), plus
              any version you save on purpose with a label. Used by File > Version History.

Everything is stored as .cut JSON, so nothing (images, cards, notes) is lost.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .ir import Script, T


def doc_id(path: str | None) -> str:
    """Stable folder name for a script: its file name plus a short hash of its full path."""
    if not path:
        return "untitled"
    p = Path(path)
    h = hashlib.sha1(str(p.resolve()).lower().encode("utf-8")).hexdigest()[:8]
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in p.stem)[:40]
    return f"{safe}-{h}"


def _atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------- recovery
class Recovery:
    def __init__(self, root: str | Path):
        self.dir = Path(root) / "recovery"

    def file_for(self, session: str) -> Path:
        return self.dir / f"{session}.cut"

    def write(self, session: str, script: Script, original_path: str | None):
        d = script.to_dict()
        d["recovery"] = {"path": original_path, "time": time.time()}
        _atomic_write(self.file_for(session), json.dumps(d, ensure_ascii=False))

    def clear(self, session: str):
        try:
            self.file_for(session).unlink()
        except FileNotFoundError:
            pass

    def pending(self) -> list[tuple[Path, str | None, float]]:
        """(recovery file, original path, time) for scripts left behind by a crash."""
        out = []
        if self.dir.is_dir():
            for f in sorted(self.dir.glob("*.cut")):
                try:
                    info = json.loads(f.read_text(encoding="utf-8")).get("recovery", {})
                except (OSError, ValueError):
                    continue
                out.append((f, info.get("path"), info.get("time", f.stat().st_mtime)))
        return out

    @staticmethod
    def load(f: Path) -> Script:
        return Script.from_json(f.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- versions
@dataclass
class Version:
    file: Path
    time: float
    label: str
    pages: int
    words: int
    auto: bool

    @property
    def when(self) -> str:
        return time.strftime("%d %b %Y  %H:%M", time.localtime(self.time))


class History:
    def __init__(self, root: str | Path, keep_auto: int = 40):
        self.root = Path(root) / "history"
        self.keep_auto = keep_auto

    def folder(self, path: str | None) -> Path:
        return self.root / doc_id(path)

    def snapshot(self, script: Script, path: str | None, label: str = "", auto: bool = True,
                 pages: int = 0) -> Path:
        t = time.time()
        stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(t)) + f"-{uuid.uuid4().hex[:6]}"
        f = self.folder(path) / f"{stamp}.cut"
        d = script.to_dict()
        d["version"] = {"time": t, "label": label, "auto": auto, "pages": pages,
                        "words": sum(len(e.text.split()) for e in script.elements)}
        _atomic_write(f, json.dumps(d, ensure_ascii=False))
        self._prune(path)
        return f

    def versions(self, path: str | None) -> list[Version]:
        out = []
        folder = self.folder(path)
        if folder.is_dir():
            for f in [*folder.glob("*.cut"), *folder.glob("*.screenplay")]:
                try:
                    v = json.loads(f.read_text(encoding="utf-8")).get("version", {})
                except (OSError, ValueError):
                    continue
                out.append(Version(f, v.get("time", f.stat().st_mtime), v.get("label", ""),
                                   v.get("pages", 0), v.get("words", 0), v.get("auto", True)))
        return sorted(out, key=lambda v: v.time, reverse=True)

    def _prune(self, path: str | None):
        autos = [v for v in self.versions(path) if v.auto]
        for v in autos[self.keep_auto:]:
            try:
                v.file.unlink()
            except OSError:
                pass

    @staticmethod
    def load(v: Version) -> Script:
        return Script.from_json(v.file.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- compare
def script_lines(script: Script) -> list[str]:
    """One line per paragraph, prefixed by its element, for comparing two drafts."""
    tag = {T.SCENE_HEADING: "SCENE", T.CHARACTER: "CHAR", T.DIALOGUE: "DIAL",
           T.PARENTHETICAL: "PAREN", T.TRANSITION: "TRANS", T.ACTION: "ACTION"}
    return [f"{tag.get(e.type, e.type.upper())}: {e.text}" for e in script.elements]


@dataclass
class Change:
    kind: str          # "same", "added", "removed", "changed"
    old: list[str]
    new: list[str]


def compare(old: Script, new: Script) -> list[Change]:
    a, b = script_lines(old), script_lines(new)
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes():
        kind = {"equal": "same", "insert": "added", "delete": "removed", "replace": "changed"}[op]
        out.append(Change(kind, a[i1:i2], b[j1:j2]))
    return out


def summary(changes: list[Change]) -> dict:
    return {"added": sum(len(c.new) for c in changes if c.kind in ("added", "changed")),
            "removed": sum(len(c.old) for c in changes if c.kind in ("removed", "changed"))}
