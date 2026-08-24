; 使用Inno Setup创建Windows安装程序 - 多文件版本

[Setup]
AppName=宿舍管理系统
AppVersion=1.0
AppPublisher=愿你三冬暖
;AppPublisherURL=https://your-website.com
DefaultDirName={code:GetDefaultInstallationDir}
DefaultGroupName=宿舍管理系统
OutputBaseFilename=宿舍管理系统_Setup_v1.0
;SetupIconFile=favicon.ico ; 安装程序图标文件
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
ShowLanguageDialog=no
; 清理动作在卸载过程中执行，通过CurUninstallStepChanged事件调用清理函数

;语言 - 默认使用中文，不提供语言选择
[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

; 定义安装类型
[Types]
Name: "full"; Description: "完整安装"; Flags: iscustom

[Components]
Name: "program"; Description: "主程序"; Types: full; Flags: fixed
Name: "data"; Description: "数据文件"; Types: full; Flags: fixed
Name: "webview2"; Description: "WebView2运行时"; Types: full; Flags: fixed

[Files]
; 安装前清理工具
Source: "pre_install_check.bat"; DestDir: "{tmp}"; Flags: deleteafterinstall
; WebView2检测工具
Source: "webview2_detection.bat"; DestDir: "{tmp}"; Flags: deleteafterinstall

; 主程序文件 - PyInstaller多文件模式
; 复制整个多文件版本目录下的所有文件和子目录
Source: "..\dist\宿舍管理系统\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; 配置数据文件 (程序运行时自动创建)

; 数据库文件 (程序运行时自动创建)
;Source: "data\data.db"; DestDir: "{app}\data"; Flags: ignoreversion


[Dirs]
; 确保创建必要的目录结构，即使它们在源目录中为空
Name: "{app}\data"
Name: "{app}\data\backups"
Name: "{app}\data\photo"
Name: "{app}\data\file_sharing"
Name: "{app}\data\logs"

[Icons]
Name: "{group}\宿舍管理系统"; Filename: "{app}\宿舍管理系统.exe"
Name: "{userdesktop}\宿舍管理系统"; Filename: "{app}\宿舍管理系统.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标"
Name: "checkwebview2"; Description: "检测WebView2运行时"; GroupDescription: "安装选项"; Flags: checkedonce

[Code]
// 获取默认安装目录
function GetDefaultInstallationDir(Param: String): String;
var
  S: String;
begin
  // 不根据权限强制设置路径，让用户自行选择
  // 提供合理的默认值（用户AppData目录），但用户可以在安装向导中修改
  Result := ExpandConstant('{userappdata}\宿舍管理系统');
end;

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  PreInstallCheckPath: String;
begin
  // 运行安装前清理工具
  PreInstallCheckPath := ExpandConstant('{tmp}\pre_install_check.bat');
  ShellExec('', PreInstallCheckPath, '', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  
  // 等待1秒以确保清理完成
  Sleep(1000);
  
  // 继续安装
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

// 在用户做出任务选择后检查并运行WebView2检测
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  CheckWebView2Task: Boolean;
begin
  if CurStep = ssInstall then
  begin
    // 在安装开始前检查是否选择了WebView2检测任务
    CheckWebView2Task := WizardSilent or WizardIsTaskSelected('checkwebview2');
    
    // 如果选择了检测任务，则运行WebView2检测脚本
    if CheckWebView2Task then
    begin
      ExtractTemporaryFile('webview2_detection.bat');
      if not Exec(ExpandConstant('{tmp}\webview2_detection.bat'), '', '', SW_SHOW, ewWaitUntilTerminated, ResultCode) then
      begin
        MsgBox('无法运行WebView2检测脚本。您可能需要手动安装WebView2运行时才能使用宿舍管理系统。', mbInformation, MB_OK);
      end;
    end
    else if not WizardSilent then
    begin
      // 如果未选择检测任务且非静默安装，显示提示信息
      MsgBox('您选择跳过WebView2运行时检测。请注意，宿舍管理系统需要WebView2运行时才能正常运行。如果程序无法启动，请手动安装WebView2运行时。', mbInformation, MB_OK);
    end;
  end;
end;

[Run]
Filename: "{app}\宿舍管理系统.exe"; Description: "{cm:LaunchProgram,宿舍管理系统}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 删除应用程序目录下的所有文件和子目录
Type: filesandordirs; Name: "{app}"; 

; 删除开始菜单中的程序组
Type: filesandordirs; Name: "{group}"

; 删除桌面快捷方式
Type: files; Name: "{commondesktop}\宿舍管理系统.lnk"

; 清除可能的临时文件和日志文件
Type: files; Name: "{localappdata}\dorm_mgmt_system_dorm_mgmt_v1.0\*.log"

; 清理WebView2缓存和cookie
Type: filesandordirs; Name: "{app}\WebView2"
Type: filesandordirs; Name: "{localappdata}\Microsoft\Edge\User Data\Default\WebView2"
Type: filesandordirs; Name: "{localappdata}\Microsoft\Edge WebView2\"
Type: filesandordirs; Name: "{tmp}\WebView2"

; 清理webview相关数据
Type: filesandordirs; Name: "{localappdata}\dorm_mgmt_system_dorm_mgmt_v1.0\webview"
Type: filesandordirs; Name: "{app}\webview"

; 增强WebView2和cookie清理
Type: filesandordirs; Name: "{localappdata}\Microsoft\Edge\User Data\Default\Cookies"
Type: filesandordirs; Name: "{localappdata}\Microsoft\Edge\User Data\Default\Cache"
Type: filesandordirs; Name: "{localappdata}\Microsoft\Edge\User Data\Default\Storage"
Type: filesandordirs; Name: "{localappdata}\Microsoft\Edge\User Data\Default\IndexedDB"

; 清理应用程序数据目录
Type: filesandordirs; Name: "{localappdata}\dorm_mgmt_system_dorm_mgmt_v1.0"
Type: filesandordirs; Name: "{localappdata}\宿舍管理系统"
Type: filesandordirs; Name: "{localappdata}\宿舍管理系统"
Type: filesandordirs; Name: "{userdocs}\dorm_mgmt_system_dorm_mgmt_v1.0"

[Tasks]
; 添加可选的清理任务
Name: "cleanup"; Description: "完全清理所有程序数据，包括用户数据和设置"; GroupDescription: "卸载选项"

[Registry]
; 添加此键以启用应用程序的安装信息在Windows注册表中
; 使用HKCU（当前用户）而不是HKLM（本地机器），以避免需要管理员权限
; 添加Flags: uninsdeletevalue使Inno Setup在卸载时自动删除这些注册表值
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting('AppId')}"; ValueType: string; ValueName: "DisplayName"; ValueData: "{#SetupSetting('AppName')}"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting('AppId')}"; ValueType: string; ValueName: "Publisher"; ValueData: "{#SetupSetting('AppPublisher')}"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting('AppId')}"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "{#SetupSetting('AppVersion')}"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting('AppId')}"; ValueType: string; ValueName: "UninstallString"; ValueData: "{uninstallexe}"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting('AppId')}"; ValueType: string; ValueName: "QuietUninstallString"; ValueData: "{uninstallexe} /SILENT"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting('AppId')}"; ValueType: string; ValueName: "InstallLocation"; ValueData: "{app}"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting('AppId')}"; ValueType: string; ValueName: "NoModify"; ValueData: "1"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting('AppId')}"; ValueType: string; ValueName: "NoRepair"; ValueData: "1"; Flags: uninsdeletevalue

; 添加一个额外的注册表项来标记该子键应该在卸载时被删除
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting('AppId')}"; ValueType: none; Flags: uninsdeletekey

; 添加残留注册表项的清理配置
Root: HKCU; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.dorm\UserChoice"; ValueType: none; Flags: uninsdeletekey; Tasks: cleanup
Root: HKCU; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\UFH\SHC"; ValueType: none; Flags: uninsdeletekey; Tasks: cleanup
Root: HKCU; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\RecentDocs\{#SetupSetting('AppId')}"; ValueType: none; Flags: uninsdeletekey; Tasks: cleanup
; 清理FeatureUsage中的应用切换记录
Root: HKCU; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\FeatureUsage\AppSwitched\宿舍管理系统\宿舍管理系统.exe"; ValueType: none; Flags: uninsdeletekey; Tasks: cleanup
; 清理FeatureUsage中的应用程序父项记录
Root: HKCU; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\FeatureUsage\AppSwitched\宿舍管理系统"; ValueType: none; Flags: uninsdeletekey; Tasks: cleanup

; 清理兼容性助手记录
Root: HKCU; Subkey: "SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Compatibility Assistant\Store"; ValueType: none; Flags: uninsdeletekey; Tasks: cleanup

; 清理BAM服务记录（需要管理员权限，已注释掉以避免权限错误）
; Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Services\bam\State\UserSettings"; ValueType: none; Flags: uninsdeletekey; Tasks: cleanup

; 清理英文名称注册表残留
Root: HKCU; Subkey: "Software\Dormitory Management System"; ValueType: none; Flags: uninsdeletekey; Tasks: cleanup

[UninstallRun]
; 运行程序的卸载参数以执行自定义清理
Filename: "{app}\宿舍管理系统.exe"; Parameters: "--uninstall"; RunOnceId: "UninstallApp";
; 清理Flask-Login remember cookie和自定义会话cookie
Filename: "{sys}\cmd.exe"; Parameters: "/C for /r ""%LOCALAPPDATA%\Microsoft\Windows\INetCookies"" %f in (*) do del /f /q ""%f"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupCookies1"
Filename: "{sys}\cmd.exe"; Parameters: "/C for /r ""%APPDATA%\Microsoft\Windows\Cookies"" %f in (*) do del /f /q ""%f"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupCookies2"
Filename: "{sys}\cmd.exe"; Parameters: "/C del /f /q ""%LOCALAPPDATA%\Microsoft\Windows\WebCache\WebCacheV01.dat"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupWebCache"
; 清理应用程序独特临时目录
Filename: "{sys}\cmd.exe"; Parameters: "/C if exist ""%TEMP%\dorm_mgmt_system_dorm_mgmt_v1.0"" rd /s /q ""%TEMP%\dorm_mgmt_system_dorm_mgmt_v1.0"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupDormTemp1"
Filename: "{sys}\cmd.exe"; Parameters: "/C if exist ""%TMP%\dorm_mgmt_system_dorm_mgmt_v1.0"" rd /s /q ""%TMP%\dorm_mgmt_system_dorm_mgmt_v1.0"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupDormTemp2"
Filename: "{sys}\cmd.exe"; Parameters: "/C if exist ""%TEMP%\dorm_mgmt_system_dorm_mgmt_v1.0_runtime"" rd /s /q ""%TEMP%\dorm_mgmt_system_dorm_mgmt_v1.0_runtime"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupDormRuntimeTemp1"
Filename: "{sys}\cmd.exe"; Parameters: "/C if exist ""%TMP%\dorm_mgmt_system_dorm_mgmt_v1.0_runtime"" rd /s /q ""%TMP%\dorm_mgmt_system_dorm_mgmt_v1.0_runtime"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupDormRuntimeTemp2"
Filename: "{sys}\cmd.exe"; Parameters: "/C if exist ""%LOCALAPPDATA%\Temp\dorm_mgmt_system_dorm_mgmt_v1.0"" rd /s /q ""%LOCALAPPDATA%\Temp\dorm_mgmt_system_dorm_mgmt_v1.0"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupDormTemp3"
Filename: "{sys}\cmd.exe"; Parameters: "/C if exist ""%LOCALAPPDATA%\Cache\dorm_mgmt_system_dorm_mgmt_v1.0"" rd /s /q ""%LOCALAPPDATA%\Cache\dorm_mgmt_system_dorm_mgmt_v1.0"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupDormTemp4"
Filename: "{sys}\cmd.exe"; Parameters: "/C if exist ""%APPDATA%\dorm_mgmt_system_dorm_mgmt_v1.0"" rd /s /q ""%APPDATA%\dorm_mgmt_system_dorm_mgmt_v1.0"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupDormTemp5"
; 清理PyInstaller临时文件
Filename: "{sys}\cmd.exe"; Parameters: "/C for /d %d in (""%LOCALAPPDATA%\Temp\dorm_mgmt_system_dorm_mgmt_v1.0"") do rd /s /q ""%d"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupPyInstaller1"
Filename: "{sys}\cmd.exe"; Parameters: "/C for /d %d in (""%TEMP%\dorm_mgmt_system_dorm_mgmt_v1.0"") do rd /s /q ""%d"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupPyInstaller2"