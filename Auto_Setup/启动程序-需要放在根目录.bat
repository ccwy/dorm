@echo off
setlocal enabledelayedexpansion

:: 项目根目录
cd /d "%~dp0"
set "PROJECT_DIR=%cd%"

:: 切换到项目目录
echo [%date% %time:~0,8%] 切换到项目目录...
cd /d "%PROJECT_DIR%"
if %errorlevel% neq 0 (
    echo [%date% %time:~0,8%] 错误：无法切换到项目目录 %PROJECT_DIR%
    pause
    exit /b 1
)

:: 显示启动信息和时间
cls
echo ==============================================
echo 宿舍管理系统 - 一键启动脚本
echo 启动时间: %date% %time:~0,8%
echo 项目路径: %PROJECT_DIR%
echo ==============================================
echo.

:: 清理临时文件夹
echo.
echo [%date% %time:~0,8%] 开始清理临时文件...
if exist "%PROJECT_DIR%\build" (
    rmdir /s /q "%PROJECT_DIR%\build"
    echo [%date% %time:~0,8%] 已删除build文件夹
)
if exist "%PROJECT_DIR%\__pycache__" (
    rmdir /s /q "%PROJECT_DIR%\__pycache__"
    echo [%date% %time:~0,8%] 已删除__pycache__文件夹
)
if exist "%PROJECT_DIR%\dist" (
    rmdir /s /q "%PROJECT_DIR%\dist"
    echo [%date% %time:~0,8%] 已删除dist文件夹
)
for /d /r "%PROJECT_DIR%" %%d in (__pycache__) do (
    if exist "%%d" (
        rmdir /s /q "%%d"
        echo [%date% %time:~0,8%] 已删除%%d
    )
)
if exist "%PROJECT_DIR%\data" (
    rmdir /s /q "%PROJECT_DIR%\data"
    echo [%date% %time:~0,8%] 已删除data文件夹
)

:: 检查Python是否安装
echo [%date% %time:~0,8%] 检查Python是否安装...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [%date% %time:~0,8%] 错误：未找到Python，请确保Python已正确安装并添加到系统PATH。
    pause
    exit /b 1
) else (
    echo [%date% %time:~0,8%] Python已安装，将自动执行下一步...
)

:: 检查requirements.txt是否存在
echo.
echo [%date% %time:~0,8%] 检查项目依赖...
if not exist "%PROJECT_DIR%\requirements.txt" (
    echo [%date% %time:~0,8%] 警告：未找到requirements.txt文件，跳过依赖检查。
) else (
    :: 安装依赖（如果需要）
    echo [%date% %time:~0,8%] 正在安装项目依赖...
    pip install -r "%PROJECT_DIR%\requirements.txt"
    if %errorlevel% neq 0 (
        echo [%date% %time:~0,8%] 警告：依赖安装过程中出现错误，但将继续启动应用。
    ) else (
        echo [%date% %time:~0,8%] 依赖安装完成。
    )
)


:: 启动应用程序，指定开发模式配置
echo.
echo [%date% %time:~0,8%] ==============================================
echo [%date% %time:~0,8%] 正在启动应用程序...
echo [%date% %time:~0,8%] 按Ctrl+C可停止应用程序
echo [%date% %time:~0,8%] ==============================================
echo.

python "%PROJECT_DIR%\main.py"

echo 按任意键退出...
pause >nul
exit /b %errorlevel%

