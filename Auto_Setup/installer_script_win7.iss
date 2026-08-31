; 行政后勤管理系统 Win7专用独立版本 安装程序脚本
; 使用Inno Setup创建Windows安装程序
; 注意：此版本不需要WebView2运行时，使用浏览器模式

[Setup]
AppName=行政后勤管理系统(Win7版)
AppVersion=1.0
AppPublisher=愿你三冬暖
DefaultDirName={code:GetDefaultInstallationDir}
DefaultGroupName=行政后勤管理系统(Win7版)
OutputBaseFilename=行政后勤管理系统_Win7_Setup_v1.0
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
ShowLanguageDialog=no

;语言 - 默认使用中文
[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

; 定义安装类型
[Types]
Name: "full"; Description: "完整安装"; Flags: iscustom

[Components]
Name: "program"; Description: "主程序"; Types: full; Flags: fixed
Name: "data"; Description: "数据文件"; Types: full; Flags: fixed
; Win7版本不需要WebView2组件

[Files]
; 安装前清理工具
Source: "pre_install_check.bat"; DestDir: "{tmp}"; Flags: deleteafterinstall
; Win7版本不需要WebView2检测工具

; 主程序文件 - PyInstaller单文件模式（Win7专用）
Source: "..\dist\行政后勤管理系统_Win7.exe"; DestDir: "{app}"; Flags: ignoreversion

[Dirs]
; 确保创建必要的目录结构
Name: "{app}\data"
Name: "{app}\data\backups"
Name: "{app}\data\photo"
Name: "{app}\data\file_sharing"
Name: "{app}\data\logs"

[Icons]
Name: "{group}\行政后勤管理系统(Win7版)"; Filename: "{app}\行政后勤管理系统_Win7.exe"
Name: "{userdesktop}\行政后勤管理系统(Win7版)"; Filename: "{app}\行政后勤管理系统_Win7.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标"

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  PreInstallCheckPath: String;
  BrowserFound: Boolean;
begin
  // 运行安装前清理工具
  PreInstallCheckPath := ExpandConstant('{tmp}\pre_install_check.bat');
  ShellExec('', PreInstallCheckPath, '', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  
  // 等待1秒以确保清理完成
  Sleep(1000);
  
  // 检测是否有可用的浏览器（Win7版本使用浏览器模式）
  BrowserFound := False;
  
  // 检查Chrome
  if RegKeyExists(HKEY_LOCAL_MACHINE, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe') then
    BrowserFound := True
  // 检查Firefox
  else if RegKeyExists(HKEY_LOCAL_MACHINE, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe') then
    BrowserFound := True
  // 检查IE（Win7自带）
  else if RegKeyExists(HKEY_LOCAL_MACHINE, 'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\iexplore.exe') then
    BrowserFound := True
  // 检查默认浏览器
  else if RegKeyExists(HKEY_CLASSES_ROOT, 'http\shell\open\command') then
    BrowserFound := True;
  
  if not BrowserFound then
  begin
    if MsgBox('未检测到已安装的浏览器。' + #13#10 + #13#10 +
      '行政后勤管理系统(Win7版)使用浏览器模式运行，需要系统安装有浏览器。' + #13#10 + #13#10 +
      '是否继续安装？', mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      Exit;
    end;
  end;
  
  // 提示Win7系统要求
  if MsgBox('行政后勤管理系统(Win7版)系统要求：' + #13#10 + #13#10 +
    '• Windows 7 SP1（32位或64位）' + #13#10 +
    '• 需要安装VC++ 2015-2019运行时（x86）' + #13#10 +
    '• 建议安装KB2999226通用C运行时更新' + #13#10 +
    '• 需要安装现代浏览器（Chrome/Firefox推荐）' + #13#10 + #13#10 +
    '是否继续安装？', mbConfirmation, MB_YESNO) = IDNO then
  begin
    Result := False;
    Exit;
  end;
  
  Result := True;
end;

// 控制是否显示特定页面
function ShouldSkipPage(PageID: Integer): Boolean;
begin
  // 禁用组件选择页面
  if PageID = wpSelectComponents then
    Result := True
  else
    Result := False;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  // Win7版本不需要WebView2检测
  // 安装后提示用户安装运行时依赖
  if CurStep = ssPostInstall then
  begin
    MsgBox('安装完成！' + #13#10 + #13#10 +
      '温馨提示：' + #13#10 +
      '1. 如程序无法启动，请安装VC++ 2015-2019运行时（x86）' + #13#10 +
      '2. 建议安装Windows更新KB2999226' + #13#10 +
      '3. 建议使用Chrome或Firefox浏览器以获得最佳体验', mbInformation, MB_OK);
  end;
end;

[Run]
Filename: "{app}\行政后勤管理系统_Win7.exe"; Description: "{cm:LaunchProgram,行政后勤管理系统(Win7版)}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 删除应用程序目录下的所有文件和子目录
Type: filesandordirs; Name: "{app}"; 
; 删除开始菜单中的程序组
Type: filesandordirs; Name: "{group}"
; 删除桌面快捷方式
Type: files; Name: "{commondesktop}\行政后勤管理系统(Win7版).lnk"
; 清除可能的临时文件和日志文件
Type: files; Name: "{localappdata}\dorm_mgmt_win7_v1.0\*.log"
; 清理应用程序数据目录
Type: filesandordirs; Name: "{localappdata}\dorm_mgmt_win7_v1.0"
Type: filesandordirs; Name: "{localappdata}\行政后勤管理系统(Win7版)"
Type: filesandordirs; Name: "{userdocs}\dorm_mgmt_win7_v1.0"

[Tasks]
; 添加可选的清理任务
Name: "cleanup"; Description: "完全清理所有程序数据，包括用户数据和设置"; GroupDescription: "卸载选项"

[Registry]
; 注册表项
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\行政后勤管理系统_Win7"; ValueType: string; ValueName: "DisplayName"; ValueData: "行政后勤管理系统(Win7版)"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\行政后勤管理系统_Win7"; ValueType: string; ValueName: "Publisher"; ValueData: "{#SetupSetting('AppPublisher')}"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\行政后勤管理系统_Win7"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#SetupSetting('AppVersion')}"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\行政后勤管理系统_Win7"; ValueType: string; ValueName: "UninstallString"; ValueData: "{uninstallexe}"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\行政后勤管理系统_Win7"; ValueType: string; ValueName: "QuietUninstallString"; ValueData: "{uninstallexe} /SILENT"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\行政后勤管理系统_Win7"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\行政后勤管理系统_Win7"; ValueType: string; ValueName: "NoModify"; ValueData: "1"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\行政后勤管理系统_Win7"; ValueType: string; ValueName: "NoRepair"; ValueData: "1"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\行政后勤管理系统_Win7"; ValueType: none; Flags: uninsdeletekey

[UninstallRun]
; 运行程序的卸载参数
Filename: "{app}\行政后勤管理系统_Win7.exe"; Parameters: "--uninstall"; RunOnceId: "UninstallApp";
; 清理临时文件
Filename: "{sys}\cmd.exe"; Parameters: "/C if exist ""%TEMP%\dorm_mgmt_win7_v1.0"" rd /s /q ""%TEMP%\dorm_mgmt_win7_v1.0"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupDormTemp1"
Filename: "{sys}\cmd.exe"; Parameters: "/C if exist ""%TMP%\dorm_mgmt_win7_v1.0"" rd /s /q ""%TMP%\dorm_mgmt_win7_v1.0"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupDormTemp2"
Filename: "{sys}\cmd.exe"; Parameters: "/C if exist ""%LOCALAPPDATA%\Temp\dorm_mgmt_win7_v1.0"" rd /s /q ""%LOCALAPPDATA%\Temp\dorm_mgmt_win7_v1.0"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupDormTemp3"
; 在卸载过程结束后删除应用程序目录
Filename: "{sys}\cmd.exe"; Parameters: "/C timeout /t 2 >nul && rd /s /q ""{app}"" >nul 2>&1"; Flags: runhidden; RunOnceId: "DeleteTempFiles"

[Messages]
cm:CreateDesktopIcon=创建桌面快捷方式
cm:AdditionalIcons=附加图标
cm:LaunchProgram=启动 行政后勤管理系统(Win7版)

[Code]
// 获取默认安装目录
function GetDefaultInstallationDir(Param: String): String;
begin
  Result := ExpandConstant('{userappdata}\行政后勤管理系统(Win7版)');
end;