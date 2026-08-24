@echo off
chcp 65001 > nul

REM 注意：WebView2检测已移至安装程序主脚本中执行
REM WebView2运行时是宿舍管理系统运行所必需的组件

:check_admin
REM 检查是否有管理员权限
NET SESSION >nul 2>&1
if %errorLevel% neq 0 (
    echo 注意：当前不是以管理员权限运行，可能无法清理某些系统级残留
    echo 但仍然可以继续安装，数据将存储在您选择的安装路径中
    pause
)

echo ===================================================
echo 宿舍管理系统 - 安装前清理工具

echo 正在检查并清理旧版本残留...
echo 提示：如果您之前将程序安装在自定义路径，可能需要手动清理该路径中的旧文件


REM 停止正在运行的应用程序进程
echo 检查并停止正在运行的应用程序...
taskkill /f /im "宿舍管理系统.exe" >nul 2>&1
taskkill /f /im "宿舍管理系统.exe" >nul 2>&1
echo 应用程序进程已停止（如果存在）

REM 清理Program Files目录中的旧安装
echo 检查Program Files目录中的旧安装...
if exist "%ProgramFiles%\宿舍管理系统" (
    echo 发现旧安装在Program Files目录，正在清理...
    timeout /t 1 >nul
    rmdir /s /q "%ProgramFiles%\宿舍管理系统" >nul 2>&1
    echo Program Files目录中的旧安装已清理
) else (
    echo 没有发现Program Files目录中的旧安装
)

if exist "%ProgramFiles%\宿舍管理系统" (
    echo 发现旧安装在Program Files目录，正在清理...
    timeout /t 1 >nul
    rmdir /s /q "%ProgramFiles%\宿舍管理系统" >nul 2>&1
    echo Program Files目录中的旧安装已清理
) else (
    echo 没有发现Program Files目录中的旧安装
)

REM 清理Program Files (x86)目录中的旧安装
echo 检查Program Files (x86)目录中的旧安装...
if exist "%ProgramFiles(x86)%\宿舍管理系统" (
    echo 发现旧安装在Program Files (x86)目录，正在清理...
    timeout /t 1 >nul
    rmdir /s /q "%ProgramFiles(x86)%\宿舍管理系统" >nul 2>&1
    echo Program Files (x86)目录中的旧安装已清理
) else (
    echo 没有发现Program Files (x86)目录中的旧安装
)

if exist "%ProgramFiles(x86)%\宿舍管理系统" (
    echo 发现旧安装在Program Files (x86)目录，正在清理...
    timeout /t 1 >nul
    rmdir /s /q "%ProgramFiles(x86)%\宿舍管理系统" >nul 2>&1
    echo Program Files (x86)目录中的旧安装已清理
) else (
    echo 没有发现Program Files (x86)目录中的旧安装
)

REM 清理用户AppData目录中的旧安装
echo 检查用户AppData目录中的旧安装...
set "USER_APP_DATA=%APPDATA%\..\Local\宿舍管理系统"
if exist "%USER_APP_DATA%" (
    echo 发现旧安装在用户AppData目录，正在清理...
    timeout /t 1 >nul
    rmdir /s /q "%USER_APP_DATA%" >nul 2>&1
    echo 用户AppData目录中的旧安装已清理
) else (
    echo 没有发现用户AppData目录中的旧安装
)

set "USER_APP_DATA_CN=%APPDATA%\..\Local\宿舍管理系统"
if exist "%USER_APP_DATA_CN%" (
    echo 发现旧安装在用户AppData目录，正在清理...
    timeout /t 1 >nul
    rmdir /s /q "%USER_APP_DATA_CN%" >nul 2>&1
    echo 用户AppData目录中的旧安装已清理
) else (
    echo 没有发现用户AppData目录中的旧安装
)

REM 清理用户文档目录中的日志和数据
echo 检查用户文档目录中的数据...
set "USER_DOCS=%USERPROFILE%\Documents\宿舍管理系统"
if exist "%USER_DOCS%" (
    echo 发现文档目录中的数据，正在清理...
    timeout /t 1 >nul
    rmdir /s /q "%USER_DOCS%" >nul 2>&1
    echo 文档目录中的数据已清理
) else (
    echo 没有发现文档目录中的数据
)

REM 清理LocalAppData目录中的临时文件和缓存
echo 检查LocalAppData目录中的临时文件和缓存...
set "LOCAL_APP_DATA=%LOCALAPPDATA%\宿舍管理系统"
if exist "%LOCAL_APP_DATA%" (
    echo 发现LocalAppData目录中的临时文件和缓存，正在清理...
    timeout /t 1 >nul
    rmdir /s /q "%LOCAL_APP_DATA%" >nul 2>&1
    echo LocalAppData目录中的临时文件和缓存已清理
) else (
    echo 没有发现LocalAppData目录中的临时文件和缓存
)

set "LOCAL_APP_DATA_CN=%LOCALAPPDATA%\宿舍管理系统"
if exist "%LOCAL_APP_DATA_CN%" (
    echo 发现LocalAppData目录中的临时文件和缓存，正在清理...
    timeout /t 1 >nul
    rmdir /s /q "%LOCAL_APP_DATA_CN%" >nul 2>&1
    echo LocalAppData目录中的临时文件和缓存已清理
) else (
    echo 没有发现LocalAppData目录中的临时文件和缓存
)

REM 清理系统临时目录中的相关文件
echo 检查系统临时目录中的相关文件...
set "TEMP_DIR=%TEMP%\宿舍管理系统"
if exist "%TEMP_DIR%" (
    echo 发现系统临时目录中的相关文件，正在清理...
    timeout /t 1 >nul
    rmdir /s /q "%TEMP_DIR%" >nul 2>&1
    echo 系统临时目录中的相关文件已清理
) else (
    echo 没有发现系统临时目录中的相关文件
)

REM 清理注册表中的残留
echo 正在清理注册表中的残留...
REM 只清理HKCU（当前用户）注册表项，避免需要管理员权限
reg delete "HKCU\SOFTWARE\宿舍管理系统" /f >nul 2>&1
reg delete "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\宿舍管理系统_is1" /f >nul 2>&1

REM 仅在有管理员权限时才尝试清理HKLM注册表项
NET SESSION >nul 2>&1
if %errorLevel% equ 0 (
    echo 检测到管理员权限，正在清理HKLM注册表项...
    reg delete "HKLM\SOFTWARE\宿舍管理系统" /f >nul 2>&1
    reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\宿舍管理系统_is1" /f >nul 2>&1
)
echo 注册表清理完成

REM 清理开始菜单和桌面快捷方式
echo 正在清理开始菜单和桌面快捷方式...
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\宿舍管理系统.lnk" >nul 2>&1
del /f /q "%PUBLIC%\Desktop\宿舍管理系统.lnk" >nul 2>&1
del /f /q "%USERPROFILE%\Desktop\宿舍管理系统.lnk" >nul 2>&1
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\宿舍管理系统.lnk" >nul 2>&1
del /f /q "%PUBLIC%\Desktop\宿舍管理系统.lnk" >nul 2>&1
del /f /q "%USERPROFILE%\Desktop\宿舍管理系统.lnk" >nul 2>&1
echo 快捷方式清理完成

echo ===================================================
echo 清理完成！现在可以安全安装新版本的宿舍管理系统了。
echo ===================================================
echo 提示：在安装向导中，您可以自定义安装路径
echo 数据文件将始终存储在您选择的安装路径中
echo ===================================================
pause