@echo off
:: 显示开始时间
echo ==============================================
echo 开始执行批处理操作... %date% %time%
echo ==============================================

:: 获取当前脚本所在目录
set "current_dir=%~dp0"
echo 当前工作目录: %current_dir%
echo.

:: 执行第一个批处理文件（自动跳过pause）
echo 开始执行第一个批处理: %date% %time%
echo 正在执行：直接打包成单文件.bat
echo. | call "%current_dir%直接打包成单文件.bat"

:: 检查第一个批处理是否成功执行
if %errorlevel% equ 0 (
    echo 直接打包成单文件.bat 执行完成 %date% %time%
) else (
    echo 直接打包成单文件.bat 执行失败 %date% %time%
    pause
    exit /b 1
)

:: 执行第二个批处理文件（自动跳过pause）
echo.
echo 开始执行第二个批处理: %date% %time%
echo 正在执行：直接打包成安装包多文件模式.bat
echo. | call "%current_dir%直接打包成安装包多文件模式.bat"

:: 检查第二个批处理是否成功执行
if %errorlevel% equ 0 (
    echo 直接打包成安装包多文件模式.bat 执行完成 %date% %time%
) else (
    echo 直接打包成安装包多文件模式.bat 执行失败 %date% %time%
    pause
    exit /b 1
)

echo.
echo ==============================================
echo 所有批处理操作执行完毕 %date% %time%
echo ==============================================
pause
    