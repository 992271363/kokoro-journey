; ============================================================
; Kokoro Journey — Inno Setup 安装脚本
; 用法: ISCC.exe KokoroJourney.iss
;       正式构建请用 build_release.ps1 结尾打印的命令注入版本号:
;       ISCC.exe /DMyAppVersion="v2026.9.13-1.0.0" KokoroJourney.iss
; 前提: 先运行 build_release.ps1（会同步生成 client\dist）
; ============================================================

#define MyAppName "Kokoro Journey"
#ifndef MyAppVersion
#define MyAppVersion "v2026.9.9-1.0.0"
#endif
#define MyAppPublisher "Kokoro Journey"
#define MyAppExeName "kokoro-journey.exe"
#define MyAppLogExeName "log-console.exe"
#define SourceDir "..\client\dist"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppId={{B7F3A2C1-8D4E-4F6A-9C2B-1E5D7A8F3E90}
DefaultDirName={localappdata}\Programs\Kokoro Journey
DefaultGroupName={#MyAppName}
OutputDir=..\installer_output
OutputBaseFilename=KokoroJourneySetup-{#MyAppVersion}
SetupIconFile=..\client\icons\icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "额外任务:"
Name: "autostart"; Description: "开机自动启动"; GroupDescription: "额外任务:"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "uninstall_data_handler.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: {app}
Name: "{group}\日志控制台"; Filename: "{app}\{#MyAppLogExeName}"; WorkingDir: {app}
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: {app}; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "KokoroJourney"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
var
  ShouldDeleteData: Boolean;
  UninstallConfigForm: TForm;
  DataCheckbox: TCheckBox;
  UninstallResult: Integer;

function GetDataDirFromStateFile: String;
begin
  Result := ExpandConstant('{localappdata}\Kokoro Journey');
end;

procedure NextBtnClick(Sender: TObject);
begin
  ShouldDeleteData := not DataCheckbox.Checked;
  UninstallResult := mrOK;
  UninstallConfigForm.Close;
end;

procedure CancelBtnClick(Sender: TObject);
begin
  UninstallResult := mrCancel;
  UninstallConfigForm.Close;
end;

function InitializeUninstall: Boolean;
var
  TitleLabel, DescLabel, DataLabel, WarnLabel: TLabel;
  NextBtn, CancelBtn: TButton;
  DataDir: String;
begin
  ShouldDeleteData := False;

  DataDir := GetDataDirFromStateFile;
  if DataDir = '' then
    DataDir := ExpandConstant('{localappdata}\Kokoro Journey');

  UninstallConfigForm := TForm.Create(nil);
  UninstallConfigForm.BorderStyle := bsDialog;
  UninstallConfigForm.Caption := '卸载设置';
  UninstallConfigForm.Width := 480;
  UninstallConfigForm.Height := 310;
  UninstallConfigForm.Position := poScreenCenter;

  TitleLabel := TLabel.Create(UninstallConfigForm);
  TitleLabel.Parent := UninstallConfigForm;
  TitleLabel.Caption := '卸载 Kokoro Journey';
  TitleLabel.Font.Size := 16;
  TitleLabel.Font.Style := [fsBold];
  TitleLabel.Left := 30;
  TitleLabel.Top := 25;

  DescLabel := TLabel.Create(UninstallConfigForm);
  DescLabel.Parent := UninstallConfigForm;
  DescLabel.Caption := '请选择数据处理方式：';
  DescLabel.Left := 30;
  DescLabel.Top := 65;

  DataLabel := TLabel.Create(UninstallConfigForm);
  DataLabel.Parent := UninstallConfigForm;
  DataLabel.Caption := '用户数据位置：' + DataDir;
  DataLabel.Left := 30;
  DataLabel.Top := 95;

  DataCheckbox := TCheckBox.Create(UninstallConfigForm);
  DataCheckbox.Parent := UninstallConfigForm;
  DataCheckbox.Caption := '保留用户数据（数据库、设置、历史记录等）';
  DataCheckbox.Checked := True;
  DataCheckbox.Left := 40;
  DataCheckbox.Top := 125;
  DataCheckbox.Width := 400;

  WarnLabel := TLabel.Create(UninstallConfigForm);
  WarnLabel.Parent := UninstallConfigForm;
  WarnLabel.Caption := '取消勾选后，用户数据将被永久删除，无法恢复。';
  WarnLabel.Font.Style := [fsItalic];
  WarnLabel.Font.Color := clMaroon;
  WarnLabel.Left := 60;
  WarnLabel.Top := 155;

  NextBtn := TButton.Create(UninstallConfigForm);
  NextBtn.Parent := UninstallConfigForm;
  NextBtn.Caption := '下一步';
  NextBtn.Default := True;
  NextBtn.Left := 180;
  NextBtn.Top := 210;
  NextBtn.Width := 85;
  NextBtn.OnClick := @NextBtnClick;

  CancelBtn := TButton.Create(UninstallConfigForm);
  CancelBtn.Parent := UninstallConfigForm;
  CancelBtn.Caption := '取消';
  CancelBtn.Left := 275;
  CancelBtn.Top := 210;
  CancelBtn.Width := 85;
  CancelBtn.OnClick := @CancelBtnClick;

  UninstallResult := mrCancel;
  UninstallConfigForm.ShowModal;
  Result := UninstallResult = mrOK;
  UninstallConfigForm.Free;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  UninstallForm: TUninstallProgressForm;
  ResultCode: Integer;
  ScriptPath, StateFilePath, PowerShellPath, Params: String;
  ExecSuccess: Boolean;
begin
  if CurUninstallStep <> usUninstall then
    Exit;

  UninstallForm := GetUninstallProgressForm;

  if not ShouldDeleteData then
  begin
    // 保留用户数据
    UninstallForm.PageNameLabel.Caption := '用户数据已保留。';
    UninstallForm.Update;
    Exit;
  end
  else
  begin
    // 删除用户数据
    StateFilePath := ExpandConstant('{localappdata}\Kokoro Journey\uninstall_state.json');
    ScriptPath := ExpandConstant('{app}\uninstall_data_handler.ps1');

    if not (FileExists(StateFilePath) and FileExists(ScriptPath)) then
    begin
      UninstallForm.PageNameLabel.Caption := '未找到用户数据配置，无需清理。';
      UninstallForm.Update;
      Exit;
    end;

    UninstallForm.PageNameLabel.Caption := '正在处理用户数据...';
    UninstallForm.Update;

    PowerShellPath := ExpandConstant('{sys}\powershell.exe');
    Params := '-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' +
              ScriptPath + '" "' + StateFilePath + '" -DeleteData';
    ResultCode := -1;
    ExecSuccess := Exec(PowerShellPath, Params, '', SW_SHOWNORMAL,
                        ewWaitUntilTerminated, ResultCode);

    if ExecSuccess and (ResultCode = 0) then
      UninstallForm.PageNameLabel.Caption := '用户数据处理完成。'
    else
      UninstallForm.PageNameLabel.Caption := '部分用户数据未能删除，请手动处理。';
    UninstallForm.Update;
  end;
end;
