#ifndef AppVersion
  #error AppVersion must be supplied by build.ps1
#endif

[Setup]
AppId={{31455545-6B6C-4785-8C06-3A436507234F}
AppName=StitchVert
AppVersion={#AppVersion}
AppPublisher=StitchVert contributors
AppPublisherURL=https://github.com/RoguePixelLabs/StitchVert
AppUpdatesURL=https://github.com/RoguePixelLabs/StitchVert/releases
DefaultDirName={localappdata}\Programs\StitchVert
DefaultGroupName=StitchVert
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
Compression=lzma2
SolidCompression=yes
OutputDir=..\dist
OutputBaseFilename=StitchVert-{#AppVersion}-Windows-x64-Setup
UninstallDisplayIcon={app}\runtime\pythonw.exe
CloseApplications=yes
RestartApplications=no
WizardStyle=modern

[Files]
Source: "..\build\installer-stage\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"

[Icons]
Name: "{autoprograms}\StitchVert"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\app.pyw"""; WorkingDir: "{app}"
Name: "{autodesktop}\StitchVert"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\app.pyw"""; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\app.pyw"""; WorkingDir: "{app}"; Description: "Launch StitchVert"; Flags: nowait postinstall skipifsilent
