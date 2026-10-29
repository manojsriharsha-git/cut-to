"""Re-make the screenshots in docs/images (used by the README, the user guide and the website).

Run from the project folder:   python tools/screenshots.py
It opens the app off-screen with the sample script, so nothing pops up and your own
settings and SmartType memory are left alone.
"""
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings                     # noqa: E402
from PySide6.QtGui import QFont, QTextCursor              # noqa: E402
from PySide6.QtWidgets import QApplication                # noqa: E402

OUT = ROOT / "docs" / "images"


def main():
    a = QApplication([])
    a.setOrganizationName("CutToScreenshots")
    a.setApplicationName("CutToScreenshots")
    a.setApplicationDisplayName("Cut To:")
    a.setStyle("Fusion")
    QSettings().clear()
    QSettings().setValue("spelling", "false")
    f = QFont("DejaVu Sans" if sys.platform != "win32" else "Segoe UI")
    f.setPointSize(9)
    a.setFont(f)
    import app.ui.main_window as mw
    from app.ui.theme import build_qss
    from app.core.smart import SmartMemory
    from conftest import sample_script
    a.setStyleSheet(build_qss())
    mw._load_fonts()

    w = mw.MainWindow(SmartMemory(None), Path(tempfile.mkdtemp()))
    w.resize(1280, 820)
    w.show()
    ed = w.editor
    ed.load_script(sample_script(4), "/x/The Last Signal.cut")
    w.path = Path("The Last Signal.cut")
    w._after_open()
    ed.number_scenes()
    ed.project["storylines"] = [{"id": "a", "name": "The Signal", "color": "#E4C85D"},
                                {"id": "b", "name": "Meera & Arjun", "color": "#EAB5A3"}]
    colours = ["#E4C85D", "#EAB5A3", "#9DC3E6", "#A8D5BA", "#C3B1E1"]
    synopses = ["Meera hears a pattern in the static.", "On the roof, the dish turns by itself.",
                "Young Meera and the radio that started it all."]
    for i, (block, *_rest) in enumerate(ed.scenes()):
        ed.set_block_extra(block, "color", colours[i % 5])
        ed.set_block_extra(block, "synopsis", synopses[i % 3])
        ed.set_block_extra(block, "storylines", ["a"] if i % 2 else ["a", "b"])
    ed.set_block_extra(3, "notes", [{"id": "n1", "text": "Is the chai too cute? Maybe coffee.",
                                     "color": "#9DC3E6"}])
    ed.project["structure"] = [{"name": "Inciting Incident", "page": 2},
                               {"name": "Midpoint", "page": 4}]
    w.features[2]._tag(ed.scenes()[0][0], "Props", "radio telescope console")
    ed._on_structure_timer()
    a.processEvents()
    ed.setTextCursor(QTextCursor(ed.document().findBlockByNumber(3)))
    a.processEvents()
    w.grab().save(str(OUT / "script.png"))

    board = w.features[0].board
    w.show_view("board")
    board.beats_from_cards()
    items = list(board.items.values())
    board.connect(items[0], items[1])
    board.connect(items[1], items[2])
    board.fit()
    for view in ("cards", "board", "characters", "production", "insights"):
        w.show_view(view)
        a.processEvents()
        a.processEvents()
        w.grab().save(str(OUT / f"{view}.png"))
    w.show_view("script")
    w.set_theme("Night")
    a.processEvents()
    w.grab().save(str(OUT / "night.png"))
    w.set_theme("Day")
    w.font_combo.showPopup()
    a.processEvents()
    w.font_combo.view().window().grab().save(str(OUT / "fonts.png"))
    w.font_combo.hidePopup()
    print("Saved the screenshots in", OUT)


if __name__ == "__main__":
    main()
