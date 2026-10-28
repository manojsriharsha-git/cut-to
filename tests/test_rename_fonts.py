"""Cut To: rename, the .cut format and fonts."""
import pytest
from PySide6.QtGui import QTextCursor

from app import __app_name__, __app_id__
from app.core import T, Element, Script, Run
from app.formats import load, save, loses_content, fdx, open_filter
from app.ui.fonts import bundled, font_groups, add_font_file, is_typewriter
from app.resources import resource_path
from tests.conftest import sample_script


def test_names():
    assert __app_name__ == "Cut To:" and ":" not in __app_id__


def test_cut_files_and_old_screenplay_files(tmp_path):
    s = sample_script()
    save(s, tmp_path / "a.cut")
    assert load(tmp_path / "a.cut").elements[3].text == s.elements[3].text
    (tmp_path / "old.screenplay").write_text((tmp_path / "a.cut").read_text(encoding="utf-8"), encoding="utf-8")
    assert load(tmp_path / "old.screenplay").elements[3].text == s.elements[3].text
    assert not loses_content(s, tmp_path / "a.cut")
    assert "*.cut" in open_filter()


def test_fdx_reads_old_and_new_extra_sections():
    s = sample_script()
    s.extra = {"beats": [{"id": "b", "title": "Hook"}]}
    xml = fdx.write(s)
    assert "<CutToData>" in xml
    assert fdx.parse(xml.replace("CutToData", "ScreenplayData")).extra["beats"][0]["title"] == "Hook"


def test_bundled_fonts_load_with_licences(qapp):
    fams = bundled()
    assert len(fams) >= 30
    from app.ui.fonts import load_all
    assert load_all() == []
    from PySide6.QtGui import QFont, QFontInfo
    import os
    for f in fams:
        assert QFontInfo(QFont(f["name"])).family().startswith(f["name"]), f["name"]
        lic = "OFL.txt" if "Open Font" in f["license"] else "LICENSE.txt"
        assert os.path.exists(resource_path("fonts", f["folder"], lic)), f["name"]
    titles = [t for t, _n in font_groups()]
    assert titles[0].startswith("Screenplay") and "Courier Prime" in font_groups()[0][1]
    assert is_typewriter("Courier Prime") and not is_typewriter("Playfair Display")


def test_font_survives_save_in_cut_fdx_and_docx(tmp_path):
    s = Script(elements=[Element(T.ACTION, [Run("Title in "), Run("Playfair", font="Playfair Display")])])
    assert loses_content(s, tmp_path / "a.fountain")
    for ext in (".cut", ".fdx", ".docx"):
        if ext == ".docx":
            pytest.importorskip("docx")
        save(s, tmp_path / f"a{ext}")
        runs = [r for e in load(tmp_path / f"a{ext}").elements for r in e.runs]
        assert any(r.font == "Playfair Display" and r.text == "Playfair" for r in runs), ext


def test_selection_font_and_script_font(window):
    ed = window.editor
    ed.load_script(Script(elements=[Element.plain(T.ACTION, "Plain words here")]))
    c = QTextCursor(ed.document().firstBlock())
    c.setPosition(0)
    c.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    ed.setTextCursor(c)
    ed.set_font_family("Lora")
    runs = ed.to_script().elements[0].runs
    assert runs[0].font == "Lora" and runs[1].font is None
    ed.document().undo()
    assert ed.to_script().elements[0].runs[0].font is None
    ed.set_script_font("IBM Plex Mono")
    assert ed.document().defaultFont().family() == "IBM Plex Mono"
    assert ed.to_script().extra["font"] == "IBM Plex Mono"
    assert ed.to_script().elements[0].runs[0].font is None       # follows the script font


def test_add_font_file(window, tmp_path):
    src = resource_path("fonts", "lora", next(f for f in bundled() if f["name"] == "Lora")["files"][0])
    import shutil
    mine = tmp_path / "MyFont.ttf"
    shutil.copy(src, mine)
    assert "Lora" in add_font_file(str(mine), window.data)
    assert (window.data / "fonts" / "MyFont.ttf").exists()
    assert add_font_file(str(tmp_path / "notes.txt"), window.data) == []


def test_font_combo_lists_groups_and_actions(window):
    combo = window.font_combo
    items = [combo.itemText(i) for i in range(combo.count())]
    assert "SCREENPLAY (TYPEWRITER)" in items and "Courier Prime" in items
    assert items[-2:] == ["Add Font File…", "Get More Fonts…"]
