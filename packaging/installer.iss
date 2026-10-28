; Inno Setup script: turns "dist\Cut To" into CutTo-Setup-1.0.0.exe
; Open this file in Inno Setup (free, jrsoftware.org) and press Build > Compile,
; or run build.bat, which does it for you.

#define AppName "Cut To:"
#define AppFolder "Cut To"
#define AppVersion "1.0.0"
#define AppExe "Cut To.exe"

[Setup]
AppId={{6A3C1E52-8F3B-4C1D-9C2E-5B7D2A9E4F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Cut To
DefaultDirName={autopf}\{#AppFolder}
DefaultGroupName={#AppFolder}
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
OutputDir=..\dist
OutputBaseFilename=CutTo-Setup-{#AppVersion}
SetupIconFile=..\resources\icons\cutto.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
ChangesAssociations=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "assoccut"; Description: "Open .cut scripts with Cut To:"; GroupDescription: "File types:"
Name: "assocfountain"; Description: "Open .fountain files with Cut To:"; GroupDescription: "File types:"
Name: "assocfdx"; Description: "Open .fdx files with Cut To:"; GroupDescription: "File types:"; Flags: unchecked

[Files]
Source: "..\dist\Cut To\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppFolder}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppFolder}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppFolder}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.cut\OpenWithProgids"; ValueType: string; ValueName: "CutTo.Script"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoccut
Root: HKA; Subkey: "Software\Classes\.fountain\OpenWithProgids"; ValueType: string; ValueName: "CutTo.Script"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocfountain
Root: HKA; Subkey: "Software\Classes\.fdx\OpenWithProgids"; ValueType: string; ValueName: "CutTo.Script"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assocfdx
Root: HKA; Subkey: "Software\Classes\CutTo.Script"; ValueType: string; ValueName: ""; ValueData: "Cut To: script"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\CutTo.Script\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\CutTo.Script\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\.cut"; ValueType: string; ValueName: ""; ValueData: "CutTo.Script"; Flags: uninsdeletevalue; Tasks: assoccut
Root: HKA; Subkey: "Software\Classes\.fountain"; ValueType: string; ValueName: ""; ValueData: "CutTo.Script"; Flags: uninsdeletevalue; Tasks: assocfountain
Root: HKA; Subkey: "Software\Classes\.fdx"; ValueType: string; ValueName: ""; ValueData: "CutTo.Script"; Flags: uninsdeletevalue; Tasks: assocfdx

[Run]
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent
