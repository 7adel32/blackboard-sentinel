#ifndef MyAppVersion
  #define MyAppVersion "1.1.12"
#endif

#define MyAppName "Blackboard Sentinel"
#define MyAppExeName "BlackboardSentinel.exe"
#define MyAppCliName "BlackboardSentinelCLI.exe"
#define MyAppPublisher "Blackboard Sentinel"
#define MyAppURL "https://github.com/7adel32/blackboard-sentinel"

[Setup]
AppId={{8D6E7C31-9B14-4C93-9C4A-72A4D3E1C809}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={localappdata}\Programs\BlackboardSentinel
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
OutputDir=dist
OutputBaseFilename=BlackboardSentinelSetup
SetupIconFile=assets\icon_app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
CloseApplicationsFilter=*.exe,*.dll
RestartApplications=no
AllowNoIcons=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a Desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked
Name: "startup"; Description: "Start Blackboard Sentinel automatically when Windows starts"; GroupDescription: "Startup:"

[InstallDelete]
; Remove legacy PyInstaller onefile uninstaller and legacy shortcuts from prior versions
Type: files; Name: "{app}\uninstall.exe"
Type: files; Name: "{userstartup}\BlackboardSentinel.lnk"
Type: files; Name: "{userprograms}\Blackboard Sentinel.lnk"
Type: files; Name: "{userprograms}\Uninstall Blackboard Sentinel.lnk"

[Files]
Source: "dist\BlackboardSentinel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "dist\{#MyAppCliName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "BlackboardSentinel"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: startup

[Run]
; No skipifsilent so silent auto-updates relaunch the tray app cleanly
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Blackboard Sentinel"; Flags: nowait postinstall

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure TerminateRunningProcesses();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#MyAppExeName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#MyAppCliName}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Sleep(400);
end;

procedure CleanupLegacyUninstallKey();
begin
  RegDeleteKeyIncludingSubkeys(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Uninstall\BlackboardSentinel');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  TerminateRunningProcesses();
  CleanupLegacyUninstallKey();
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
  begin
    TerminateRunningProcesses();
  end;
end;
