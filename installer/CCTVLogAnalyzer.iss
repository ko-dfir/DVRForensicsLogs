#ifndef MyAppVersion
  #define MyAppVersion "1.01"
#endif
#ifndef MyWindowsVersion
  #define MyWindowsVersion "1.1.0.0"
#endif

#define MyAppName "CCTV Log Analyzer"
#define MyAppPublisher "CCTV Log Analyzer"
#define MyAppExeName "CCTVLogAnalyzer.exe"

[Setup]
AppId={{361E090C-0736-4C9B-9913-DF6E5C32A557}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
; {autopf} is %LOCALAPPDATA%\Programs for "me only" and Program Files for "all users".
DefaultDirName={autopf}\CCTV Log Analyzer
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\installer-output
OutputBaseFilename=CCTVLogAnalyzer-{#MyAppVersion}-Setup
SetupIconFile=..\assets\cctv-log-analyzer.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Default is a per-user install without elevation; the dialog offers an
; elevated all-users install into Program Files instead.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
VersionInfoVersion={#MyWindowsVersion}
VersionInfoProductVersion={#MyWindowsVersion}
VersionInfoDescription=CCTV Log Analyzer Installer
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\cctv_log_analyzer.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; Per-user data folder. In an all-users install {localappdata} would be the
; elevating admin's profile, so leave it to the app, which creates it on first run.
Name: "{localappdata}\CCTVLogAnalyzer"; Flags: uninsneveruninstall; Check: not IsAdminInstallMode

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent runasoriginaluser
