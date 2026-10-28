@echo off
rem  Builds "Cut To.exe" and the installer.  Double-click this file (or run it in
rem  PyCharm's Terminal):  build.bat
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (set PY=.venv\Scripts\python.exe) else (set PY=python)

echo [1/5] Installing what Cut To: needs...
%PY% -m pip install -r requirements.txt || goto :error

echo [2/5] Running the self-checks...
%PY% -m pytest -q || goto :error

echo [3/5] Building "dist\Cut To\Cut To.exe" ...
%PY% -m PyInstaller --noconfirm --clean packaging\cutto.spec || goto :error

echo [4/5] Making the portable zip (unzip and run)...
for /f "tokens=2 delims==" %%v in ('findstr /r /c:"__version__ = " app\__init__.py') do set VER=%%~v
set VER=%VER: =%
set VER=%VER:"=%
powershell -NoProfile -Command "Compress-Archive -Force -Path 'dist\Cut To' -DestinationPath 'dist\CutTo-%VER%-Windows-Portable.zip'" || goto :error
echo        dist\CutTo-%VER%-Windows-Portable.zip

echo [5/5] Building the installer...
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
    %ISCC% packaging\installer.iss || goto :error
    echo.
    echo Done!  Installer: dist\CutTo-Setup-1.0.0.exe
) else (
    echo.
    echo The app is ready in "dist\Cut To\Cut To.exe"
    echo To make the installer, install Inno Setup 6 from https://jrsoftware.org/isdl.php
    echo and run build.bat again.
)
pause
exit /b 0

:error
echo.
echo Something went wrong - read the red lines above.
pause
exit /b 1
