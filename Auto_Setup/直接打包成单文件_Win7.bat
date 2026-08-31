@echo off
setlocal enabledelayedexpansion

:: 项目根目录
cd /d "%~dp0.."
set "PROJECT_DIR=%cd%"
set "DEST_DIR=%PROJECT_DIR%\Auto_Setup\Output"

:: 显示开始信息
echo ==============================================
echo Win7专用独立版本 - 单文件打包
echo 开始时间: %date% %time:~0,8%
echo 项目路径: %PROJECT_DIR%
echo ==============================================
echo.

:: 切换到项目目录
echo [%date% %time:~0,8%] 切换到项目目录...
cd /d "%PROJECT_DIR%"
if %errorlevel% neq 0 (
    echo [%date% %time:~0,8%] 错误：无法切换到项目目录 %PROJECT_DIR%
    pause
    exit /b 1
)

:: 打包前清理临时文件
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
    echo [%date% %time:~0,8%] 错误：未找到Python，请确保Python 3.8已正确安装并添加到系统PATH
    pause
    exit /b 1
) else (
    echo [%date% %time:~0,8%] Python已安装，继续执行打包...
)

:: 检查pyinstaller是否已安装
echo [%date% %time:~0,8%] 检查pyinstaller是否已安装...
python -m pip show pyinstaller >nul 2>&1
if %errorlevel% equ 0 (
    echo [%date% %time:~0,8%] pyinstaller 已安装，继续执行打包...
) else (
    echo [%date% %time:~0,8%] pyinstaller 未安装，开始安装...
    pip install pyinstaller==5.13.2
    if %errorlevel% equ 0 (
        echo [%date% %time:~0,8%] pyinstaller 安装成功，继续执行打包...
    ) else (
        echo [%date% %time:~0,8%] 错误：pyinstaller 安装失败，请检查网络或权限问题。
        pause
        exit /b 1
    )
)

:: 使用requirements_win7.txt安装依赖
echo.
echo [%date% %time:~0,8%] 使用Win7专用依赖文件安装项目依赖...
pip install -r requirements_win7.txt
if %errorlevel% neq 0 (
    echo [%date% %time:~0,8%] 错误：依赖安装失败
    pause
    exit /b 1
)
echo [%date% %time:~0,8%] 所有依赖已安装完成

:: 直接调用pyinstaller（Win7专用spec文件）
echo.
echo [%date% %time:~0,8%] 开始使用pyinstaller打包（Win7专用版本）...
pyinstaller "%PROJECT_DIR%\Auto_Setup\dorm_management_win7.spec" --clean --noconfirm
if %errorlevel% neq 0 (
    echo [%date% %time:~0,8%] 错误：pyinstaller打包失败
    pause
    exit /b 1
)

:: 打包完成提示
echo.
echo [%date% %time:~0,8%] ==============================================
echo [%date% %time:~0,8%] Win7专用版本打包完成！
echo [%date% %time:~0,8%] 输出文件: dist\行政后勤管理系统_Win7.exe
echo [%date% %time:~0,8%] ==============================================
echo.
echo 注意：Win7专用版本使用浏览器模式，不需要WebView2运行时
echo.

pause