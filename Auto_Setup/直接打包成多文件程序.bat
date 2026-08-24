@echo off
setlocal enabledelayedexpansion

:: 项目根目录
cd /d "%~dp0.."
set "PROJECT_DIR=%cd%"
set "DEST_DIR=%PROJECT_DIR%\Auto_Setup\Output"

:: 显示开始信息及时间
echo ==============================================
echo 开始执行Python程序一键封装流程（单窗口模式）
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

:: 检测pyinstaller是否已安装
echo [%date% %time:~0,8%] 检测pyinstaller是否已安装...
python -m pip show pyinstaller >nul 2>&1
if %errorlevel% equ 0 (
    echo [%date% %time:~0,8%] pyinstaller 已安装，自动执行下一步...
) else (
	echo [%date% %time:~0,8%] pyinstaller 未安装，开始安装...
	pip install pyinstaller
	if %errorlevel% equ 0 (
		echo [%date% %time:~0,8%] pyinstaller 安装成功！自动执行下一步...
	) else (
		echo [%date% %time:~0,8%] 错误：pyinstaller 安装失败，请检查网络连接或权限问题。
		pause
		exit /b 1
	)
)

:: 检测并安装所需依赖
echo.
echo [%date% %time:~0,8%] 开始检测项目依赖...

:: 定义需要检测和安装的依赖列表（使用编号避免解析问题）
set "dep1=Flask>=2.3.3"
set "dep2=Flask-SQLAlchemy>=3.1.1"
set "dep3=Flask-WTF>=1.2.1"
set "dep4=Flask-Login>=0.6.3"
set "dep5=Flask-Migrate>=4.0.5"
set "dep6=openpyxl>=3.1.2"
set "dep7=pandas>=2.1.4"
set "dep8=numpy>=1.26.3"
set "dep9=python-dotenv>=1.0.0"
set "dep10=PyMySQL>=1.1.0"
set "dep11=cryptography>=41.0.7"
set "dep12=Werkzeug>=2.3.7"
set "dep13=Jinja2>=3.1.2"
set "dep14=schedule>=1.2.0"
set "dep15=xlsxwriter>=3.2.5"
set "dep16=waitress>=2.1.2"
set "dep17=pywebview==3.7"
set "dep18=requests>=2.31.0"
set "dep19=psutil>=7.0.0"
set "dep20=Pillow>=9.5.0"
set "dep21=pystray>=0.19"

:: 循环检测并安装依赖（使用编号循环避免特殊字符问题）
for /l %%i in (1,1,19) do (
    :: 获取当前依赖项
    set "current_dep=!dep%%i!"
    
    :: 提取包名（去掉版本信息）
    for /f "delims==<>" %%p in ("!current_dep!") do set "package=%%p"
    
    echo.
    echo [%date% %time:~0,8%] 检测 !package! 是否安装...
    python -m pip show "!package!" >nul 2>&1
    if !errorlevel! equ 0 (
        echo [%date% %time:~0,8%] !package! 已安装，跳过...
    ) else (
        echo [%date% %time:~0,8%] !package! 未安装，开始安装 !current_dep!...
        pip install "!current_dep!"
        if !errorlevel! equ 0 (
            echo [%date% %time:~0,8%] !package! 安装成功！
        ) else (
            echo [%date% %time:~0,8%] 错误：!package! 安装失败
            pause
            exit /b 1
        )
    )
)
echo.
echo [%date% %time:~0,8%] 所有依赖检测和安装完成...

:: 直接调用pyinstaller（同一窗口执行，自动等待完成）
echo.
echo [%date% %time:~0,8%] 开始使用pyinstaller打包程序...
pyinstaller "%PROJECT_DIR%\Auto_Setup\dorm_management_multifile.spec"
if %errorlevel% neq 0 (
    echo [%date% %time:~0,8%] 错误：pyinstaller打包失败
    pause
    exit /b 1
)

:: 打包完成提示
echo.
echo [%date% %time:~0,8%] ==============================================
echo [%date% %time:~0,8%] Python程序打包已完成...
echo [%date% %time:~0,8%] 等待完成保存...
timeout /t 2 /nobreak >nul
echo [%date% %time:~0,8%] ==============================================

:: 创建目标目录（如果不存在）
echo.
echo [%date% %time:~0,8%] 准备移动文件...
if not exist "%DEST_DIR%" (
    mkdir "%DEST_DIR%"
    echo [%date% %time:~0,8%] 创建目标目录: %DEST_DIR%
)

:: 移动dist文件夹内容到Auto_Setup/Output
echo [%date% %time:~0,8%] 正在移动dist文件夹内容到%DEST_DIR%...
xcopy /E /H /C /R /Y "%PROJECT_DIR%\dist\*" "%DEST_DIR%\*"
if %errorlevel% gtr 1 (
    echo [%date% %time:~0,8%] 错误：文件移动失败
    pause
    exit /b 1
)

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
if exist "%PROJECT_DIR%\blueprints\__pycache__" (
    rmdir /s /q "%PROJECT_DIR%\blueprints\__pycache__"
    echo [%date% %time:~0,8%] 已删除blueprints\__pycache__文件夹
)
if exist "%PROJECT_DIR%\models\__pycache__" (
    rmdir /s /q "%PROJECT_DIR%\models\__pycache__"
    echo [%date% %time:~0,8%] 已删除models\__pycache__文件夹
)
if exist "%PROJECT_DIR%\utils\__pycache__" (
    rmdir /s /q "%PROJECT_DIR%\utils\__pycache__"
    echo [%date% %time:~0,8%] 已删除utils\__pycache__文件夹
)

:: 完成提示
echo.
echo [%date% %time:~0,8%] ==============================================
echo [%date% %time:~0,8%] 所有操作已成功完成！
echo [%date% %time:~0,8%] 程序打包已自动完成！
echo [%date% %time:~0,8%] 本次为多文件绿色版本！
echo [%date% %time:~0,8%] 输出文件已保存至: %DEST_DIR%
echo 完成时间: %date% %time:~0,8%
echo [%date% %time:~0,8%] ==============================================

pause
exit /b 0
