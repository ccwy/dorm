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
echo 宿舍管理系统 - 清理缓存脚本
echo 启动时间: %date% %time:~0,8%
echo 项目路径: %PROJECT_DIR%
echo ==============================================
echo.

:: 开始前清理临时文件夹
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

:: 启动应用程序，指定开发模式配置
echo.
echo [%date% %time:~0,8%] ==============================================
echo [%date% %time:~0,8%] 清晰缓存文件完成...
echo [%date% %time:~0,8%] 按Ctrl+C可停止应用程序
echo [%date% %time:~0,8%] ==============================================
echo.

 
pause
exit /b 0
