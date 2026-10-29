; Inno Setup script: builds ClipForge-Setup.exe from dist\ClipForge (run by the GitHub workflow).
#define AppVersion GetEnv("CLIPFORGE_VERSION")

[Setup]
AppName=ClipForge
AppVersion={#AppVersion}
AppPublisher=ClipForge
DefaultDirName={autopf}\ClipForge
DefaultGroupName=ClipForge
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=ClipForge-Setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\ClipForge.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\ClipForge\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\ClipForge"; Filename: "{app}\ClipForge.exe"
Name: "{autodesktop}\ClipForge"; Filename: "{app}\ClipForge.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\ClipForge.exe"; Description: "Open ClipForge"; Flags: nowait postinstall skipifsilent
