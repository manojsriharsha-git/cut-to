"""Shared test fixtures: one Qt application, a fresh editor, a fresh main window."""
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(scope="session")
def qapp():
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    app.setOrganizationName("CutToTests")
    app.setApplicationName("CutToTests")
    return app


@pytest.fixture
def window(qapp, tmp_path):
    from PySide6.QtCore import QSettings
    QSettings().clear()
    QSettings().setValue("spelling", "false")
    from app.core.smart import SmartMemory
    from app.ui.main_window import MainWindow
    w = MainWindow(SmartMemory(None), tmp_path / "data")
    w.resize(1280, 860)
    w.show()
    yield w
    w.editor.document().setModified(False)
    w.close()


def sample_script(copies: int = 1):
    from app.formats import load
    s = load(Path(__file__).resolve().parents[1] / "samples" / "sample.fountain")
    s.elements = s.elements * copies
    return s
