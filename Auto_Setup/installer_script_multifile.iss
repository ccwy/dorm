; 使用Inno Setup创建Windows安装程序 - 多文件版本

[Setup]
AppName=行政后勤管理系统
AppVersion=1.0
AppPublisher=愿你三冬暖
;AppPublisherURL=https://your-website.com
DefaultDirName={code:GetDefaultInstallationDir}
DefaultGroupName=行政后勤管理系统
OutputBaseFilename=行政后勤管理系统_Setup_v1.0
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
; KB4474419/KB4490628补丁检测工具（Win7 SHA-2代码签名支持）
Source: "kb4474419_check.bat"; DestDir: "{tmp}"; Flags: deleteafterinstall

; 主程序文件 - PyInstaller多文件模式
; 复制整个多文件版本目录下的所有文件和子目录
Source: "..\dist\行政后勤管理系统\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

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
Name: "{group}\行政后勤管理系统"; Filename: "{app}\行政后勤管理系统.exe"
Name: "{userdesktop}\行政后勤管理系统"; Filename: "{app}\行政后勤管理系统.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标"
Name: "checkkb4474419"; Description: "检测SHA-2代码签名支持(Win7必需)"; GroupDescription: "安装选项"; Flags: checkedonce
Name: "checkwebview2"; Description: "检测WebView2运行时"; GroupDescription: "安装选项"; Flags: checkedonce

[Code]
// 获取默认安装目录
function GetDefaultInstallationDir(Param: String): String;
var
  S: String;
begin
  // 不根据权限强制设置路径，让用户自行选择
  // 提供合理的默认值（用户AppData目录），但用户可以在安装向导中修改
  Result := ExpandConstant('{userappdata}\行政后勤管理系统');
end;

function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
  PreInstallCheckPath: String;
begin
  // 运行安装前清理工具
  ExtractTemporaryFile('pre_install_check.bat');
  PreInstallCheckPath := ExpandConstant('{tmp}\pre_install_check.bat');
  ShellExec('', PreInstallCheckPath, '--iss', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  
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

// KB4474419 下载链接点击处理
var
  KBShellResultCode: Integer;

procedure OpenKBOfficialLink(Sender: TObject);
begin
  ShellExec('open', 'https://catalog.update.microsoft.com/v7/site/Search.aspx?q=KB4474419', '', '', SW_SHOWNORMAL, ewNoWait, KBShellResultCode);
end;

procedure OpenKBx64Link(Sender: TObject);
begin
  ShellExec('open', 'https://mnl.lanzouc.com/i2ULP49qiqla', '', '', SW_SHOWNORMAL, ewNoWait, KBShellResultCode);
end;

procedure OpenKBx86Link(Sender: TObject);
begin
  ShellExec('open', 'https://mnl.lanzouc.com/iWzXt49qiptc', '', '', SW_SHOWNORMAL, ewNoWait, KBShellResultCode);
end;

// 在安装过程中执行各项检测
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  CheckKBTask, CheckWebView2Task: Boolean;
  KBResultCode: Integer;
  KBForm: TSetupForm;
  InfoLabel: TNewStaticText;
  LinkOfficial, Linkx64, Linkx86: TNewStaticText;
  NoteLabel: TNewStaticText;
  AbortBtn, RetryBtn: TNewButton;
begin
  if CurStep = ssInstall then
  begin
    // ===== KB4474419 SHA-2 代码签名支持检测（Win7必需） =====
    CheckKBTask := WizardSilent or WizardIsTaskSelected('checkkb4474419');
    
    if CheckKBTask then
    begin
      ExtractTemporaryFile('kb4474419_check.bat');
      KBResultCode := 1;
    
      while KBResultCode = 1 do
      begin
        if not Exec(ExpandConstant('{tmp}\\kb4474419_check.bat'), '--iss', '', SW_HIDE, ewWaitUntilTerminated, KBResultCode) then
        begin
          // 脚本执行失败，跳过检测
          KBResultCode := 0;
          Break;
        end;

        if KBResultCode <> 1 then
          Break;

        // SHA-2 支持未检测到，显示带可点击下载链接的对话框
        KBForm := CreateCustomForm(500, 300, False, False);
        try
          KBForm.Caption := '缺少 SHA-2 代码签名支持';
          KBForm.Width := 520;
          KBForm.Height := 340;
          KBForm.BorderStyle := bsDialog;
          KBForm.Position := poScreenCenter;

          // 说明文字
          InfoLabel := TNewStaticText.Create(KBForm);
          InfoLabel.Parent := KBForm;
          InfoLabel.Caption := '当前系统为 Windows 7，但未检测到 SHA-2 代码签名支持。'#13#10 +
                               '缺少此支持会导致程序无法正常运行。'#13#10#13#10 +
                               '请点击下方链接下载并安装 KB4474419 补丁：';
          InfoLabel.Left := 20;
          InfoLabel.Top := 15;
          InfoLabel.Width := 470;
          InfoLabel.Height := 70;
          InfoLabel.AutoSize := False;
          InfoLabel.WordWrap := True;

          // 官方下载链接
          LinkOfficial := TNewStaticText.Create(KBForm);
          LinkOfficial.Parent := KBForm;
          LinkOfficial.Caption := '>> 官方下载（Microsoft 更新目录）';
          LinkOfficial.Left := 30;
          LinkOfficial.Top := 95;
          LinkOfficial.Font.Color := clBlue;
          LinkOfficial.Font.Style := [fsUnderline];
          LinkOfficial.OnClick := @OpenKBOfficialLink;

          // 备用x64下载链接
          Linkx64 := TNewStaticText.Create(KBForm);
          Linkx64.Parent := KBForm;
          Linkx64.Caption := '>> 备用下载（64位系统）';
          Linkx64.Left := 30;
          Linkx64.Top := 120;
          Linkx64.Font.Color := clBlue;
          Linkx64.Font.Style := [fsUnderline];
          Linkx64.OnClick := @OpenKBx64Link;

          // 备用x86下载链接
          Linkx86 := TNewStaticText.Create(KBForm);
          Linkx86.Parent := KBForm;
          Linkx86.Caption := '>> 备用下载（32位系统）';
          Linkx86.Left := 30;
          Linkx86.Top := 145;
          Linkx86.Font.Color := clBlue;
          Linkx86.Font.Style := [fsUnderline];
          Linkx86.OnClick := @OpenKBx86Link;

          // 注意事项
          NoteLabel := TNewStaticText.Create(KBForm);
          NoteLabel.Parent := KBForm;
          NoteLabel.Caption := '注意：64位系统选 x64，32位系统选 x86；安装补丁后需重启计算机。';
          NoteLabel.Left := 20;
          NoteLabel.Top := 180;
          NoteLabel.Width := 470;
          NoteLabel.Height := 30;
          NoteLabel.AutoSize := False;
          NoteLabel.WordWrap := True;
          NoteLabel.Font.Color := clGrayText;

          // 重新检测按钮
          RetryBtn := TNewButton.Create(KBForm);
          RetryBtn.Parent := KBForm;
          RetryBtn.Caption := '重新检测';
          RetryBtn.Left := 140;
          RetryBtn.Top := 270;
          RetryBtn.Width := 100;
          RetryBtn.Height := 30;
          RetryBtn.ModalResult := mrRetry;
          RetryBtn.Default := True;

          // 中止安装按钮
          AbortBtn := TNewButton.Create(KBForm);
          AbortBtn.Parent := KBForm;
          AbortBtn.Caption := '中止安装';
          AbortBtn.Left := 260;
          AbortBtn.Top := 270;
          AbortBtn.Width := 100;
          AbortBtn.Height := 30;
          AbortBtn.ModalResult := mrCancel;
          AbortBtn.Cancel := True;

          if KBForm.ShowModal = mrCancel then
          begin
            // 用户选择中止安装
            Abort;
          end;
          // 用户选择重新检测，循环继续
        finally
          KBForm.Free;
        end;
      end;
    end
    else if not WizardSilent then
    begin
      MsgBox('您选择跳过SHA-2代码签名支持检测。请注意，Windows 7系统缺少此支持会导致程序无法正常运行。如果程序启动报错，请安装KB4474419补丁。', mbInformation, MB_OK);
    end;
    
    // ===== WebView2 检测 =====
    CheckWebView2Task := WizardSilent or WizardIsTaskSelected('checkwebview2');
    
    if CheckWebView2Task then
    begin
      ExtractTemporaryFile('webview2_detection.bat');
      if not Exec(ExpandConstant('{tmp}\webview2_detection.bat'), '--iss', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
      begin
        MsgBox('无法运行WebView2检测脚本。您可能需要手动安装WebView2运行时才能使用行政后勤管理系统。', mbInformation, MB_OK);
      end;
    end
    else if not WizardSilent then
    begin
      MsgBox('您选择跳过WebView2运行时检测。请注意，行政后勤管理系统需要WebView2运行时才能正常运行。如果程序无法启动，请手动安装WebView2运行时。', mbInformation, MB_OK);
    end;
  end;
end;

[Run]
Filename: "{app}\行政后勤管理系统.exe"; Description: "{cm:LaunchProgram,行政后勤管理系统}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 删除应用程序目录下的所有文件和子目录
Type: filesandordirs; Name: "{app}"; 

; 删除开始菜单中的程序组
Type: filesandordirs; Name: "{group}"

; 删除桌面快捷方式
Type: files; Name: "{commondesktop}\行政后勤管理系统.lnk"

; 清理WebView2缓存和cookie
Type: filesandordirs; Name: "{app}\WebView2"
Type: filesandordirs; Name: "{localappdata}\Microsoft\Edge\User Data\Default\WebView2"
Type: filesandordirs; Name: "{localappdata}\Microsoft\Edge WebView2\"
Type: filesandordirs; Name: "{tmp}\WebView2"

; 清理webview相关数据
Type: filesandordirs; Name: "{app}\webview"

; 增强WebView2和cookie清理
Type: filesandordirs; Name: "{localappdata}\Microsoft\Edge\User Data\Default\Cookies"
Type: filesandordirs; Name: "{localappdata}\Microsoft\Edge\User Data\Default\Cache"
Type: filesandordirs; Name: "{localappdata}\Microsoft\Edge\User Data\Default\Storage"
Type: filesandordirs; Name: "{localappdata}\Microsoft\Edge\User Data\Default\IndexedDB"

; 清理应用程序数据目录
Type: filesandordirs; Name: "{localappdata}\行政后勤管理系统"

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
Root: HKCU; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\FeatureUsage\AppSwitched\行政后勤管理系统\行政后勤管理系统.exe"; ValueType: none; Flags: uninsdeletekey; Tasks: cleanup
; 清理FeatureUsage中的应用程序父项记录
Root: HKCU; Subkey: "SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\FeatureUsage\AppSwitched\行政后勤管理系统"; ValueType: none; Flags: uninsdeletekey; Tasks: cleanup

; 清理兼容性助手记录
Root: HKCU; Subkey: "SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Compatibility Assistant\Store"; ValueType: none; Flags: uninsdeletekey; Tasks: cleanup

; 清理BAM服务记录（需要管理员权限，已注释掉以避免权限错误）
; Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Services\bam\State\UserSettings"; ValueType: none; Flags: uninsdeletekey; Tasks: cleanup

; 清理英文名称注册表残留
Root: HKCU; Subkey: "Software\Dormitory Management System"; ValueType: none; Flags: uninsdeletekey; Tasks: cleanup

[UninstallRun]
; 清理Flask-Login remember cookie和自定义会话cookie
Filename: "{sys}\cmd.exe"; Parameters: "/C for /r ""%LOCALAPPDATA%\Microsoft\Windows\INetCookies"" %f in (*) do del /f /q ""%f"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupCookies1"
Filename: "{sys}\cmd.exe"; Parameters: "/C for /r ""%APPDATA%\Microsoft\Windows\Cookies"" %f in (*) do del /f /q ""%f"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupCookies2"
Filename: "{sys}\cmd.exe"; Parameters: "/C del /f /q ""%LOCALAPPDATA%\Microsoft\Windows\WebCache\WebCacheV01.dat"" >nul 2>&1"; Flags: runhidden; RunOnceId: "CleanupWebCache"
