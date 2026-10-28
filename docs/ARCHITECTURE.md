# How Cut To: is built

This is a map of the code for contributors. Cut To: is a Python 3.12 desktop app using Qt for Python (PySide6).

```
main.py                    starts the app (app.ui.main_window.run)
app/
  core/                    pure Python, no Qt: everything here is unit-tested without a window
    ir.py                  the script model: Script → Element → Run (the "IR")
    layout.py              page sizes, element indents, templates (screenplay, TV, multi-cam, stage)
    pagination.py          page rules: where automatic page breaks go, (MORE)/(CONT'D)
    smart.py               Enter/Tab flow tables and SmartType (learning predictions)
    reports.py             scenes / characters / locations reports
    analysis.py            Insights numbers (screen time, who talks to whom…)
    breakdown.py           production breakdown, shot list, stripboard, breakdown sheets
    history.py             crash recovery and version history (files under %APPDATA%)
    emphasis.py            Fountain *italic* / **bold** / _underline_
  formats/                 every file format converts to and from the IR, never to each other
    __init__.py            registry: load(path) / save(script, path), what each format keeps
    fdx.py fountain.py     FDX and Fountain (read + write)
    docx_io.py             Word (read + write)
    pdf_import.py          screenplay PDFs (read)
    imports.py             Celtx, Trelby, Highland, Fade In (read)
    exports.py             RTF and plain text (write)
  ui/
    main_window.py         menus, toolbar, the view rail, status bar, files, PDF/print
    editor.py              the page: element types, keys, SmartType popup, painting
    editor_io.py           IR ⇄ page
    editor_tools.py        formatting, insert, scene numbers
    editor_extras.py       highlight layers, copy/paste, find, rename, focus mode, moving scenes
    pages.py               page geometry, page furniture, PDF and print rendering
    writing.py             find bar, go to, command palette, goals, spelling
    planning.py            index cards, beat board, characters, storylines, scene ribbon
    rewrites.py            ScriptNotes, revisions, version history dialog
    production.py          breakdown, shot list, stripboard, templates, locked numbers
    insights.py            charts and table read
    fonts.py               bundled / added / system fonts
    theme.py icons.py      colours (Day / Night / Midnight) and line icons
resources/                 fonts (with their licences) and the app icon
packaging/                 PyInstaller spec, Inno Setup script, Windows version info
tests/                     pytest: about 100 checks, run headless (QT_QPA_PLATFORM=offscreen)
```

## The IR

Every script is a `Script`. It holds:
- `title_page`: a list of (key, value) pairs.
- `elements`: one per paragraph. Each element has a type ("Scene Heading", "Action"…) and styled `Run`s of text.
- `extra`: project data such as beats, storylines, character profiles and revision settings.

Per-paragraph data lives in `Element.extra`. It covers synopsis, colour, storylines, notes, revision level, breakdown, shots and image data. Because it is stored on the paragraph, it moves, copies and undoes together with the paragraph.

The `.cut` file is simply this model as JSON (`Script.to_json`). `.fdx` writes standard FDX XML and puts the extras in a `<CutToData>` section, which other apps ignore.

## The page

The editor is a `QTextEdit` whose document is paginated as US Letter. Each paragraph stores its element type and its metadata as block-format properties (`PROP_TYPE`, `PROP_META`). That way they survive undo, copy and paste, and splitting a paragraph.

The page rules work like this:
1. After each pause in typing, `pages.measure()` reads the height of every line.
2. `pagination.plan()`, which is pure Python, decides which paragraphs need an automatic page break.
3. The editor applies those breaks inside the user's last undo step, so one Ctrl+Z takes back both the typing and the breaks it caused.

`tests/test_phase4.py` checks that the Python model places every line exactly where Qt does, across several fonts.

## Adding a feature

- **Logic first:** put the logic in `app/core` as plain functions and test it there.
- **UI hooks:** a feature area plugs into the main window from its own module. It creates its views with `window.add_view(...)`, its menu items through `window.menus[...]`, and its right-click items through `editor.context_hooks`. See `rewrites.py` for a small example.
- **New file format:**
  1. Add a module in `app/formats/`.
  2. Register it in `app/formats/__init__.py`.
  3. Add a round-trip test.
