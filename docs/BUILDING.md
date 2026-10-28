# Building Cut To: from source

## What you need

- **Windows 10 or 11 (64-bit).** The app's code also runs on Linux and macOS for development, but the installer is Windows-only.
- **Python 3.12 or newer** from [python.org](https://www.python.org/downloads/). Tick *"Add python.exe to PATH"* when installing.
- **Git** from [git-scm.com](https://git-scm.com/download/win).
- **Inno Setup 6** from [jrsoftware.org](https://jrsoftware.org/isdl.php). You only need it to make the installer.

## Get the code and run it

```
git clone https://github.com/manojsriharsha-git/cut-to.git
cd cut-to
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### With PyCharm instead

1. **Open the project.** Choose **File → Open**, select the `cut-to` folder, then click **Trust Project**.
2. **Set the interpreter.** In **Settings → Project → Python Interpreter → Add Interpreter → Virtualenv**, create `.venv` with Python 3.12 or newer.
3. **Install the packages.** In the **Terminal** tab, run `pip install -r requirements.txt`.
4. **Use the run menu.** The run menu (top right) already lists three entries:
   - **Cut To** runs the app.
   - **All tests** runs the self-checks.
   - **Build installer** runs `build.bat`.

## Run the tests

```
python -m pytest
```

All 100 should pass. They run without opening any window, using Qt's offscreen mode. The test files are in `tests/`, one per area of the app.

## Build Cut To.exe and the installer

```
build.bat
```

It runs in five steps:

1. installs `requirements.txt`;
2. runs the tests, and stops if any fail;
3. builds `dist\Cut To\Cut To.exe` with PyInstaller (recipe: `packaging\cutto.spec`);
4. zips that folder into `dist\CutTo-<version>-Windows-Portable.zip`, which people unzip and run with no installing;
5. builds `dist\CutTo-Setup-<version>.exe` with Inno Setup (script: `packaging\installer.iss`).

Both are self-contained: people who use them install nothing else.

## Releases on GitHub (automatic)

You don't have to build releases on your own PC. `.github/workflows/release.yml` builds the installer on GitHub's Windows machines whenever you push a version tag. To publish a new version:

1. **Raise the version number** in three places:
   - `__version__` in `app/__init__.py`;
   - `AppVersion` in `packaging/installer.iss`;
   - the version numbers in `packaging/version_info.txt`.
2. **Add the release notes** to the top of `CHANGELOG.md`.
3. **Commit, then tag and push:**
   ```
   git tag v1.0.1
   git push origin v1.0.1
   ```
4. **Wait about 10 minutes.** GitHub runs the tests, builds both downloads and creates a release with `CutTo-1.0.1-Windows-Portable.zip` and `CutTo-Setup-1.0.1.exe` attached. Check progress in the repository's **Actions** tab.

Every push and pull request also runs the tests (`.github/workflows/ci.yml`).

## The website (GitHub Pages)

The download page at **https://manojsriharsha-git.github.io/cut-to/** is `website/index.html`.
`.github/workflows/pages.yml` publishes it, together with the screenshots from `docs/images` and the icon and fonts from `resources`. It runs whenever any of those change and whenever a release is published.

- **Turn it on once:** in the repository, open **Settings → Pages → Build and deployment → Source** and choose **GitHub Actions**.
- **Download buttons:** they always point at the files of the latest release. The page asks GitHub for them, so you never edit links when you release.

## Code signing (optional)

Windows SmartScreen warns about unsigned installers. To remove the warning you need a code-signing certificate, from a commercial authority or a free open-source programme such as SignPath Foundation. Once you have one, sign `Cut To.exe` and the setup file with `signtool` before publishing. Inno Setup can do this through its `SignTool` setting.

## Changing the icon

The logo artwork is `resources/icons/cutto-1024.png`. After editing it, run:

```
python tools/make_icon.py
```

This regenerates `cutto.png` (256 px) and `cutto.ico` (16–256 px), which the app, the exe and the installer use.
