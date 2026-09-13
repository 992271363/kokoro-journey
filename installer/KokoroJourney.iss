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
#ifndef MyFileVersion
#define MyFileVersion "1.0.0.0"
#endif
#define MyAppPublisher "Kokoro Journey"
#define MyAppExeName "kokoro-journey.exe"
#define MyAppLogExeName "log-console.exe"
#define SourceDir "..\client\dist"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion={#MyFileVersion}
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
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "额外任务:"; Flags: unchecked
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
  KeepDataCheckbox: TNewCheckBox;
  WarnLabel: TNewStaticText;

function GetDataDirFromStateFile: String;
var
  StateFile: String;
  Raw: AnsiString;
  S: String;
  P, Q: Integer;
begin
  Result := ExpandConstant('{localappdata}\Kokoro Journey');
  StateFile := ExpandConstant('{localappdata}\Kokoro Journey\uninstall_state.json');
  if not FileExists(StateFile) then
    Exit;
  if not LoadStringFromFile(StateFile, Raw) then
    Exit;
  S := String(Raw);
  P := Pos('"dataDirectory":', S);
  if P = 0 then
    Exit;
  P := P + Length('"dataDirectory":');
  S := Trim(Copy(S, P, Length(S)));
  if (Length(S) > 0) and (S[1] = '"') then
    Delete(S, 1, 1);
  Q := Pos('"', S);
  if Q > 0 then
  begin
    Result := Copy(S, 1, Q - 1);
    StringChangeEx(Result, '\\', '\', True);
  end;
end;

procedure KeepDataCheckboxClick(Sender: TObject);
begin
  WarnLabel.Visible := not KeepDataCheckbox.Checked;
end;

function InitializeUninstall: Boolean;
var
  TitleText, DescText, PathText: TNewStaticText;
  UninstallBtn, CancelBtn: TNewButton;
  DataDir: String;
begin
  ShouldDeleteData := False;

  // 静默卸载（/SILENT、/VERYSILENT 等）：不显示自定义窗口，默认保留用户数据
  if UninstallSilent then
  begin
    Result := True;
    Exit;
  end;

  DataDir := GetDataDirFromStateFile;
  if DataDir = '' then
    DataDir := ExpandConstant('{localappdata}\Kokoro Journey');

  // 使用 Inno 自带的主题控件（与安装/卸载向导风格一致）
  UninstallConfigForm := TForm.Create(nil);
  try
    UninstallConfigForm.BorderStyle := bsDialog;
    UninstallConfigForm.ClientWidth := ScaleX(432);
    UninstallConfigForm.ClientHeight := ScaleY(250);
    UninstallConfigForm.Caption := '卸载 Kokoro Journey';
    UninstallConfigForm.Position := poScreenCenter;

    TitleText := TNewStaticText.Create(UninstallConfigForm);
    TitleText.Parent := UninstallConfigForm;
    TitleText.Caption := '卸载 Kokoro Journey';
    TitleText.Font.Style := [fsBold];
    TitleText.Font.Size := 12;
    TitleText.Left := ScaleX(24);
    TitleText.Top := ScaleY(20);

    DescText := TNewStaticText.Create(UninstallConfigForm);
    DescText.Parent := UninstallConfigForm;
    DescText.Caption := '即将从本机移除 Kokoro Journey，请选择是否保留用户数据。';
    DescText.AutoSize := False;
    DescText.WordWrap := True;
    DescText.Width := ScaleX(384);
    DescText.Height := ScaleY(36);
    DescText.Left := ScaleX(26);
    DescText.Top := ScaleY(54);

    KeepDataCheckbox := TNewCheckBox.Create(UninstallConfigForm);
    KeepDataCheckbox.Parent := UninstallConfigForm;
    KeepDataCheckbox.Caption := '保留用户数据（数据库、设置、历史记录等）';
    KeepDataCheckbox.Checked := True;
    KeepDataCheckbox.Left := ScaleX(26);
    KeepDataCheckbox.Top := ScaleY(100);
    KeepDataCheckbox.Width := ScaleX(384);
    KeepDataCheckbox.OnClick := @KeepDataCheckboxClick;

    WarnLabel := TNewStaticText.Create(UninstallConfigForm);
    WarnLabel.Parent := UninstallConfigForm;
    WarnLabel.Caption := '取消勾选后，用户数据将被永久删除，无法恢复。';
    WarnLabel.Font.Color := clMaroon;
    WarnLabel.AutoSize := False;
    WarnLabel.WordWrap := True;
    WarnLabel.Width := ScaleX(364);
    WarnLabel.Height := ScaleY(34);
    WarnLabel.Left := ScaleX(46);
    WarnLabel.Top := ScaleY(124);
    WarnLabel.Visible := False;

    PathText := TNewStaticText.Create(UninstallConfigForm);
    PathText.Parent := UninstallConfigForm;
    PathText.Caption := '用户数据位置：' + DataDir;
    PathText.Font.Color := $808080;
    PathText.AutoSize := False;
    PathText.WordWrap := True;
    PathText.Width := ScaleX(384);
    PathText.Height := ScaleY(32);
    PathText.Left := ScaleX(26);
    PathText.Top := ScaleY(164);

    CancelBtn := TNewButton.Create(UninstallConfigForm);
    CancelBtn.Parent := UninstallConfigForm;
    CancelBtn.Caption := '取消';
    CancelBtn.Width := ScaleX(88);
    CancelBtn.Height := ScaleY(26);
    CancelBtn.Left := UninstallConfigForm.ClientWidth - ScaleX(24) - CancelBtn.Width;
    CancelBtn.Top := UninstallConfigForm.ClientHeight - ScaleY(24) - CancelBtn.Height;
    CancelBtn.ModalResult := mrCancel;
    CancelBtn.Cancel := True;

    UninstallBtn := TNewButton.Create(UninstallConfigForm);
    UninstallBtn.Parent := UninstallConfigForm;
    UninstallBtn.Caption := '卸载';
    UninstallBtn.Width := ScaleX(88);
    UninstallBtn.Height := ScaleY(26);
    UninstallBtn.Left := CancelBtn.Left - ScaleX(10) - UninstallBtn.Width;
    UninstallBtn.Top := CancelBtn.Top;
    UninstallBtn.ModalResult := mrOk;
    UninstallBtn.Default := True;

    UninstallConfigForm.ActiveControl := KeepDataCheckbox;
    Result := UninstallConfigForm.ShowModal = mrOk;
    ShouldDeleteData := Result and (not KeepDataCheckbox.Checked);
  finally
    UninstallConfigForm.Free;
    UninstallConfigForm := nil;
  end;
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
