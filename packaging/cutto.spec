# PyInstaller recipe for "Cut To.exe"   —   run:  pyinstaller packaging/cutto.spec
# Builds a folder app in "dist/Cut To" (fast to start); the installer wraps that folder.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files

ROOT = Path(SPECPATH).parent
datas = [(str(ROOT / "resources"), "resources")]
datas += collect_data_files("spellchecker")      # the English word list
datas += collect_data_files("docx")              # Word's blank template

# Big Qt parts Cut To: never uses: leaving them out makes the app much smaller.
EXCLUDES = ["PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
            "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.QtQuick", "PySide6.QtQml",
            "PySide6.QtQuick3D", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtDataVisualization",
            "PySide6.QtGraphs", "PySide6.QtBluetooth", "PySide6.QtPositioning", "PySide6.QtLocation",
            "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtNfc", "PySide6.QtWebSockets",
            "PySide6.QtDesigner", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
            "tkinter", "matplotlib", "numpy", "pandas", "pytest"]

a = Analysis([str(ROOT / "main.py")], pathex=[str(ROOT)], datas=datas,
             hiddenimports=["PySide6.QtTextToSpeech", "PySide6.QtSvg", "PySide6.QtPrintSupport"],
             excludes=EXCLUDES, noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Cut To",
          icon=str(ROOT / "resources" / "icons" / "cutto.ico"),
          console=False, version=str(ROOT / "packaging" / "version_info.txt"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Cut To")
