; SPDX-License-Identifier: LicenseRef-Outthinkx-NC-1.0
; Copyright (c) 2026 Outthinkx by Luca De Simoni. Nicht-kommerziell frei, sonst Lizenz: LICENSE.
;
; Windows-Installer (Inno Setup 6, gratis): enthält Python und alle Bausteine,
; braucht keine Administratorrechte und kein Internet. Gebaut von baue.ps1.

#ifndef Version
  #define Version "0.0.0"
#endif

[Setup]
AppId={{6E2B9F3A-6C1D-4E57-9A43-5D0B6A2C7E11}
AppName=Klassenbildung & Stundenplan
AppVersion={#Version}
AppVerName=Klassenbildung & Stundenplan {#Version}
VersionInfoVersion={#Version}.0
VersionInfoProductVersion={#Version}
VersionInfoCompany=Outthinkx by Luca De Simoni
AppPublisher=Outthinkx by Luca De Simoni
AppCopyright=© 2026 Outthinkx by Luca De Simoni
DefaultDirName={localappdata}\Programs\Klassenbildung
DefaultGroupName=Klassenbildung
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\build\ausgabe
OutputBaseFilename=Klassenbildung-Setup-{#Version}
SetupIconFile=klassenbildung.ico
UninstallDisplayIcon={app}\klassenbildung.ico
UninstallDisplayName=Klassenbildung & Stundenplan
LicenseFile=..\build\LICENSE.txt
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktop"; Description: "Verknüpfung auf dem Desktop"; GroupDescription: "Verknüpfungen:"

[Files]
Source: "..\build\python\*"; DestDir: "{app}\python"; Flags: recursesubdirs ignoreversion createallsubdirs
Source: "..\build\lizenzen\*"; DestDir: "{app}\lizenzen"; Flags: recursesubdirs ignoreversion
Source: "..\build\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\build\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\build\Klassenbildung.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "klassenbildung.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Klassenbildung"; Filename: "{app}\Klassenbildung.exe"; IconFilename: "{app}\klassenbildung.ico"; Comment: "Klassenbildung & Stundenplan starten"
Name: "{group}\Klassenbildung deinstallieren"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Klassenbildung"; Filename: "{app}\Klassenbildung.exe"; IconFilename: "{app}\klassenbildung.ico"; Tasks: desktop

[Run]
Filename: "{app}\Klassenbildung.exe"; Description: "Klassenbildung jetzt starten"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\python"
