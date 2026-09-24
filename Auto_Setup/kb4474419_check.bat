@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM SHA-2代码签名支持检测脚本（Windows 7专用）
REM KB4474419 为原始 SHA-2 补丁，KB4490628 为后续更新（已包含前者功能）
REM 仅推荐安装 KB4474419，确保准确且避免安装指引混乱
REM 参数 --iss: 为 Inno Setup 安装程序用，跳过 pause 避免安装暂停
REM
REM 根因说明：Python 运行时的编译扩展（如 _socket.pyd）使用 SHA-256 签名，
REM Win7 缺少 SHA-2 支持会导致 DLL 加载失败：
REM   ImportError: DLL load failed while importing _socket: 参数错误。

set "ISS_MODE=0"
if "%~1"=="--iss" set "ISS_MODE=1"
set "SHA2_FOUND=0"

:check_win_version
REM 检测是否为 Windows 7 系统（版本号 6.1）
ver | findstr /i "6.1" >nul 2>&1
if %errorLevel% neq 0 (
    echo 当前系统不是 Windows 7，无需检测 SHA-2 补丁
    goto end
)

echo 检测到 Windows 7 系统，正在检测 SHA-2 代码签名支持...

REM ============================================================
REM 检测1: 通过 wmic 查询 KB4474419（原始 SHA-2 补丁）
REM ============================================================
:check_kb4474419_wmic
wmic qfe get HotFixID 2>nul | findstr /i "KB4474419" >nul 2>&1
if %errorLevel% equ 0 (
    echo SHA-2 支持: 检测到 KB4474419 已安装
    set "SHA2_FOUND=1"
    goto kb_installed
)

REM ============================================================
REM 检测2: 通过 wmic 查询 KB4490628（后续更新已包含 KB4474419）
REM ============================================================
:check_kb4490628_wmic
wmic qfe get HotFixID 2>nul | findstr /i "KB4490628" >nul 2>&1
if %errorLevel% equ 0 (
    echo SHA-2 支持: 检测到 KB4490628 已安装（包含 KB4474419 功能）
    set "SHA2_FOUND=1"
    goto kb_installed
)

REM ============================================================
REM 检测3: 通过注册表查询 KB4474419
REM ============================================================
:check_kb4474419_reg
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\HotFix\KB4474419" >nul 2>&1
if %errorLevel% equ 0 (
    echo SHA-2 支持: 注册表检测到 KB4474419
    set "SHA2_FOUND=1"
    goto kb_installed
)

REM ============================================================
REM 检测4: 通过注册表查询 KB4490628
REM ============================================================
:check_kb4490628_reg
reg query "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\HotFix\KB4490628" >nul 2>&1
if %errorLevel% equ 0 (
    echo SHA-2 支持: 注册表检测到 KB4490628
    set "SHA2_FOUND=1"
    goto kb_installed
)

REM ============================================================
REM 检测5: 检查 crypt32.dll 文件版本（最可靠的检测方式）
REM Win7 SP1 安装 SHA-2 支持后 crypt32.dll 版本 >= 6.1.7601.23473
REM 即使某些 KB 脚本检测不到，此文件版本仍能准确反映 SHA-2 支持
REM ============================================================
:check_crypt32_version
set "CRYPTVER="
for /f "tokens=2 delims==" %%v in ('wmic datafile where "name='C:\\Windows\\System32\\crypt32.dll'" get Version /value 2^>nul ^| findstr "Version="') do set "CRYPTVER=%%v"

if defined CRYPTVER (
    echo 检测到 crypt32.dll 版本: !CRYPTVER!
    set "CRYPTBUILD="
    for /f "tokens=4 delims=." %%p in ("!CRYPTVER!") do set "CRYPTBUILD=%%p"
    if defined CRYPTBUILD (
        set /a CRYPTBUILD_NUM=!CRYPTBUILD!
        if !CRYPTBUILD_NUM! GEQ 23473 (
            echo SHA-2 支持: crypt32.dll 版本 !CRYPTVER! 已支持 SHA-2 签名
            set "SHA2_FOUND=1"
            goto kb_installed
        )
    )
)

REM ============================================================
REM 所有检测方法均未发现 SHA-2 支持
REM ============================================================
:kb_not_installed
cls
echo ===============================================================================
echo                             重要提示
echo ===============================================================================
echo 当前系统为 Windows 7，但未检测到 SHA-2 代码签名支持！
echo.
echo 缺少此支持会导致程序启动时报错：
echo   ImportError: DLL load failed while importing _socket: 参数错误
echo 这是因为 Python 运行时的编译扩展（_socket.pyd 等）使用 SHA-256 签名，
echo Windows 7 无法验证该签名从而导致 DLL 加载失败。
echo.
echo 请安装 KB4474419 补丁以获取 SHA-2 支持：
echo.
echo 官方下载: https://catalog.update.microsoft.com/v7/site/Search.aspx?q=KB4474419
echo 备用x64下载: https://mnl.lanzouc.com/i2ULP49qiqla
echo 备用x86下载: https://mnl.lanzouc.com/iWzXt49qiptc
echo.
echo 注意：
echo   - 64 位系统选择 x64 版本，32 位系统选择 x86 版本
echo   - 安装完成后需要重启电脑
echo   - 安装前请确保系统已安装 SP1（服务包1）
echo   - 如果已安装 KB4490628 或 2019年9月之后的月度汇总更新，则已包含 SHA-2 支持
echo ===============================================================================
if "%ISS_MODE%"=="0" pause
endlocal
exit /b 1

:kb_installed
echo SHA-2 代码签名支持检测通过，系统满足运行要求
endlocal
exit /b 0

:end
endlocal
exit /b 0