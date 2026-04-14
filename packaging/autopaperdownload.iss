#define MyAppName "AutoPaperdownload"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#ifndef SourceDir
  #define SourceDir "dist\\AutoPaperdownload"
#endif

[Setup]
AppId={{3F57A6EF-89F2-4A36-B97A-664CBA0BA3E1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppName}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=release\win
OutputBaseFilename=AutoPaperdownload-Setup-{#MyAppVersion}-win64
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
DisableDirPage=no
DisableProgramGroupPage=no

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\AutoPaperdownload.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\AutoPaperdownload.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AutoPaperdownload.exe"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
