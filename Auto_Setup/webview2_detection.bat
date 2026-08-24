@echo off
chcp 65001 > nul

REM WebView2安装检测脚本
REM 此脚本用于在安装过程中检测WebView2是否已安装

:check_webview2
REM 检查WebView2是否已安装

REM 方法1: 检查注册表 - Evergreen Runtime
reg query "HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" >nul 2>&1
if %errorLevel% equ 0 (
    echo WebView2检测: 通过注册表检测到WebView2 Evergreen Runtime已安装
    goto webview2_installed
)

REM 方法1.1: 检查32位注册表 - Evergreen Runtime
reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" >nul 2>&1
if %errorLevel% equ 0 (
    echo WebView2检测: 通过32位注册表检测到WebView2 Evergreen Runtime已安装
    goto webview2_installed
)

REM 方法2: 检查注册表 - Fixed Version
reg query "HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F20586C8-705C-474E-BA42-7E975B87D44B}" >nul 2>&1
if %errorLevel% equ 0 (
    echo WebView2检测: 通过注册表检测到WebView2 Fixed Version已安装
    goto webview2_installed
)

REM 方法2.1: 检查32位注册表 - Fixed Version
reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F20586C8-705C-474E-BA42-7E975B87D44B}" >nul 2>&1
if %errorLevel% equ 0 (
    echo WebView2检测: 通过32位注册表检测到WebView2 Fixed Version已安装
    goto webview2_installed
)

REM 方法3: 检查常见安装路径
REM 系统级安装路径 - 64位
if exist "%SystemRoot%\System32\MicrosoftEdgeWebView2\EdgeWebView2.exe" (
    echo WebView2检测: 通过系统目录检测到WebView2已安装
    goto webview2_installed
)

REM 系统级安装路径 - 32位
if exist "%SystemRoot%\SysWOW64\MicrosoftEdgeWebView2\EdgeWebView2.exe" (
    echo WebView2检测: 通过32位系统目录检测到WebView2已安装
    goto webview2_installed
)

REM 用户级安装路径 - EdgeWebView
if exist "%LOCALAPPDATA%\Microsoft\EdgeWebView\Application\EdgeWebView2.exe" (
    echo WebView2检测: 通过用户目录检测到WebView2已安装
    goto webview2_installed
)

REM 用户级安装路径 - Edge
if exist "%LOCALAPPDATA%\Microsoft\Edge\Application\msedgewebview2.exe" (
    echo WebView2检测: 通过Edge浏览器目录检测到WebView2已安装
    goto webview2_installed
)

REM Edge浏览器安装目录的其他常见位置 - 系统级
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedgewebview2.exe" (
    echo WebView2检测: 通过系统级Edge浏览器目录检测到WebView2已安装
    goto webview2_installed
)

REM Edge浏览器安装目录的其他常见位置 - 32位系统级
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedgewebview2.exe" (
    echo WebView2检测: 通过32位系统级Edge浏览器目录检测到WebView2已安装
    goto webview2_installed
)

REM 未检测到WebView2
:webview2_not_installed
cls
echo ===============================================================================
echo                             重要提示
echo ===============================================================================
echo 宿舍管理系统需要WebView2运行时组件才能正常运行，但当前系统中未检测到该组件。
echo
echo 注意：Windows 10和Windows 11操作系统通常已预装WebView2运行时，
echo 该组件与Microsoft Edge浏览器高度集成，如果您已安装Edge浏览器，
echo 系统中很可能已包含WebView2组件。
echo
echo 如果您的系统中确实没有此组件，需要先安装它才能使用宿舍管理系统。
echo
echo 请从Microsoft官方网站下载并安装WebView2运行时：
echo https://developer.microsoft.com/zh-cn/microsoft-edge/webview2/#download-section
echo
echo 建议选择"Evergreen Bootstrapper"或"Evergreen Standalone Installer"版本，
echo 安装完成后，您可以正常使用宿舍管理系统。
echo ===============================================================================
pause
goto end

:webview2_installed
echo WebView2已成功安装，可以继续安装宿舍管理系统。
goto end

:end