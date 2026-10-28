# Third-party notices

Cut To: is licensed under the GNU General Public License v3.0 or later (see [LICENSE](LICENSE)).
It includes or uses the following third-party software and fonts, each under its own licence.

## Software

| Component | Used for | Licence |
|---|---|---|
| [Qt for Python (PySide6)](https://doc.qt.io/qtforpython/) and Qt 6 | the whole user interface | LGPL-3.0 |
| [pyspellchecker](https://github.com/barrust/pyspellchecker) | spelling | MIT |
| [python-docx](https://github.com/python-openxml/python-docx) | Word import and export | MIT |
| [pdfplumber](https://github.com/jsvine/pdfplumber) and pdfminer.six | PDF import | MIT |
| [Python](https://www.python.org/) | the runtime bundled in the installer | PSF License |
| [PyInstaller](https://pyinstaller.org/) | building the exe (not part of the app's own code) | GPL-2.0 with a bootloader exception |
| [Inno Setup](https://jrsoftware.org/isinfo.php) | building the installer (not shipped as a library) | Inno Setup License |

Qt is used as an unmodified, dynamically linked library, as the LGPL allows. Its source is available from [qt.io](https://www.qt.io/download-open-source).

## Fonts

Every bundled font is in `resources/fonts/<family>/`, next to its licence file (`OFL.txt` or `LICENSE.txt`). They come from the [Google Fonts](https://github.com/google/fonts) repository.

- **SIL Open Font License 1.1:**
  - Courier Prime, Cousine, IBM Plex Mono, Space Mono, Anonymous Pro, Roboto Mono, Inconsolata, Cutive, Cutive Mono, PT Mono;
  - Inter, Lato, Open Sans, Roboto, Work Sans, Montserrat, Poppins, Nunito, PT Sans, PT Serif, Lora, Libre Baskerville, EB Garamond, Crimson Pro, Source Serif 4;
  - Playfair Display, DM Serif Display, Bebas Neue, Oswald, Archivo Black, Space Grotesk.
- **Apache License 2.0:** Special Elite.
- **Converted to separate Regular and Bold files:** Montserrat, Nunito and Space Grotesk. Their variable font files open at their thinnest weight in Qt, so they were split into static Regular and Bold styles. Their licences allow this, because these fonts have no Reserved Font Name.

The Cut To: logo uses Archivo Black (SIL OFL 1.1).
