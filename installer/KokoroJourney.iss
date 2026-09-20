; ============================================================
; Kokoro Journey — Inno Setup 安装脚本
; 用法: ISCC.exe KokoroJourney.iss
;       正式构建请用 build_release.ps1 结尾打印的命令注入版本号:
;       ISCC.exe /DMyAppVersion="v2026.9.20-1.2.1" KokoroJourney.iss
; 前提: 先运行 build_release.ps1（会同步生成 client\dist）
; ============================================================

#define MyAppName "Kokoro Journey"
#ifndef MyAppVersion
#define MyAppVersion "v2026.9.20-1.2.1"
#endif
#ifndef MyFileVersion
#define MyFileVersion "1.2.1.0"
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
  // ---- 已安装检测（升级安装） ----
  GUpgradeDir: String;        // 注册表检测到的安装目录
  GUpgradeVer: String;        // 注册表检测到的旧版本号
  GFoundFromRegistry: Boolean;
  GTier2Confirmed: Boolean;   // 目录扫描命中后用户已确认
  GNewDirConfirmed: Boolean;  // 注册表命中但改到新目录，用户已确认

// ============================================================
// 已安装检测
//   Tier1：注册表 HKCU / HKLM（含 WOW6432Node）的卸载信息 InstallLocation
//   Tier2：Tier1 未命中时，在用户所选目录下最多递归 3 层寻找特征文件
//  特征文件：kokoro-journey.exe 或 unins000.exe 任一命中即视为已安装
// ============================================================

function ReadInstallFromKey(const RootKey: Integer; const SubKey: String;
                            var Dir, Ver: String): Boolean;
begin
  Dir := '';
  Ver := '';
  Result := RegQueryStringValue(RootKey, SubKey, 'InstallLocation', Dir)
            and (Dir <> '') and DirExists(Dir);
  if Result then
  begin
    if not RegQueryStringValue(RootKey, SubKey, 'DisplayVersion', Ver) then
      Ver := '';
  end;
end;

function DetectInstalledFromRegistry(): Boolean;
var
  Base, Base32: String;
begin
  Base := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1';
  Base32 := 'Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1';

  Result := True;
  if ReadInstallFromKey(HKCU, Base, GUpgradeDir, GUpgradeVer) then Exit;
  if ReadInstallFromKey(HKCU, Base32, GUpgradeDir, GUpgradeVer) then Exit;
  if ReadInstallFromKey(HKLM, Base, GUpgradeDir, GUpgradeVer) then Exit;
  if ReadInstallFromKey(HKLM, Base32, GUpgradeDir, GUpgradeVer) then Exit;
  Result := False;
end;

function IsKokoroInstallDir(const Dir: String): Boolean;
begin
  Result := FileExists(AddBackslash(Dir) + 'kokoro-journey.exe')
         or FileExists(AddBackslash(Dir) + 'unins000.exe');
end;

function FindInstallMarker(const Dir: String; Depth: Integer; var Found: String): Boolean;
var
  FindRec: TFindRec;
  Sub: String;
begin
  Result := False;
  if Depth > 3 then Exit;
  if IsKokoroInstallDir(Dir) then
  begin
    Found := Dir;
    Result := True;
    Exit;
  end;
  if not DirExists(Dir) then Exit;
  if FindFirst(AddBackslash(Dir) + '*', FindRec) then
  begin
    try
      repeat
        if (FindRec.Name <> '.') and (FindRec.Name <> '..') then
        begin
          Sub := AddBackslash(Dir) + FindRec.Name;
          if DirExists(Sub) then
          begin
            if FindInstallMarker(Sub, Depth + 1, Found) then
            begin
              Result := True;
              Exit;
            end;
          end;
        end;
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

function InitializeSetup(): Boolean;
begin
  GUpgradeDir := '';
  GUpgradeVer := '';
  GTier2Confirmed := False;
  GNewDirConfirmed := False;

  GFoundFromRegistry := DetectInstalledFromRegistry();
  if GFoundFromRegistry then
  begin
    if GUpgradeVer = '' then
      GUpgradeVer := '（版本未知）';
    Log('已安装检测：注册表命中 -> ' + GUpgradeDir + ' (' + GUpgradeVer + ')');
  end
  else
    Log('已安装检测：注册表未命中，将在目录选择后做目录扫描。');

  Result := True;
end;

procedure InitializeWizard();
begin
  if GFoundFromRegistry then
  begin
    // 预填旧目录，但保留目录选择页
    WizardForm.DirEdit.Text := GUpgradeDir;
    // 欢迎页显示旧版本
    WizardForm.WelcomeLabel2.Caption :=
      WizardForm.WelcomeLabel2.Caption + #13#10#13#10 +
      '检测到已安装版本 ' + GUpgradeVer + '，将进行升级安装。';
  end;
end;

// 统一的检测确认：返回 False 表示用户选择不继续。
// 正常 UI 下由 NextButtonClick 调用；静默安装下 NextButtonClick 不触发，
// 由 PrepareToInstall 调用（SuppressibleMsgBox 在静默时取默认 Yes，不阻塞）。
function ConfirmInstallTarget(): Boolean;
var
  ChosenDir, Found: String;
begin
  Result := True;
  ChosenDir := WizardDirValue();

  if GFoundFromRegistry then
  begin
    // 注册表命中但用户改到别处：明确提示旧安装会保留
    if (not GNewDirConfirmed)
       and (CompareText(RemoveBackslashUnlessRoot(ChosenDir),
                        RemoveBackslashUnlessRoot(GUpgradeDir)) <> 0) then
    begin
      Log('已安装检测：注册表命中(' + GUpgradeDir + ')，但目标改为 ' + ChosenDir);
      if SuppressibleMsgBox(
           '检测到旧安装：' + GUpgradeDir + #13#10#13#10 +
           '但你选择了新目录：' + ChosenDir + #13#10#13#10 +
           '继续将把程序安装到新目录，旧安装会保留（可能同时存在两份）。是否继续？',
           mbConfirmation, MB_YESNO, IDYES) = IDYES then
        GNewDirConfirmed := True
      else
      begin
        Result := False;
        Exit;
      end;
    end;
  end
  else if not GTier2Confirmed then
  begin
    // 无注册表信息：在所选目录下最多递归 3 层扫描特征文件
    Found := '';
    if FindInstallMarker(ChosenDir, 0, Found) then
    begin
      Log('已安装检测：目录扫描命中 -> ' + Found);
      if SuppressibleMsgBox(
           '在所选目录下检测到已安装的 Kokoro Journey：' + #13#10 + Found + #13#10#13#10 +
           '是否按覆盖升级继续安装？',
           mbConfirmation, MB_YESNO, IDYES) = IDYES then
        GTier2Confirmed := True
      else
      begin
        Result := False;
        Exit;
      end;
    end;
  end;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID <> wpSelectDir then Exit;
  Result := ConfirmInstallTarget();
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  NeedsRestart := False;
  Result := '';
  if not ConfirmInstallTarget() then
    Result := '安装已取消：目标目录下检测到已有安装。';
end;

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
