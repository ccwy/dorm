@echo off
setlocal enabledelayedexpansion

:: 配置参数
set "DOCKER_PATH=C:\Program Files\Docker\Docker\Docker Desktop.exe"
cd /d "%~dp0.."
set "PROJECT_DIR=%cd%"  :: 项目根目录
set "DOCKERFILE_DIR=%PROJECT_DIR%\Auto_Setup"  :: Dockerfile所在目录
set "DOCKERDATA_DIR=%PROJECT_DIR%\data"  :: 数据目录
set "DOCKERSAVE_DIR=%DOCKERFILE_DIR%\Output"  :: 保存目录
set "OUTPUT_TAR=%DOCKERSAVE_DIR%\docker_dorm-system_v1.0.tar"  :: 完整的输出文件路径
set "IMAGE_NAME=dorm-management-system:latest"

:: 等待配置 - 最多等待5分钟(30次*5秒)
set "MAX_WAIT_SECONDS=300"
set "CHECK_INTERVAL=5"
set "ELAPSED_SECONDS=0"

:: 显示开始信息
echo ==============================================
echo 开始执行Docker镜像构建与打包流程
echo 开始时间: %date% %time:~0,8%
echo 项目路径: %PROJECT_DIR%
echo Dockerfile路径: %DOCKERFILE_DIR%
echo 输出文件: %OUTPUT_TAR%
echo ==============================================
echo.

:: 检查Docker是否已安装
if not exist "%DOCKER_PATH%" (
    echo [%date% %time:~0,8%] 错误：未找到Docker Desktop，请检查安装路径
    pause
    exit /b 1
)

:: 检查Dockerfile是否存在
if not exist "%DOCKERFILE_DIR%\dockerfile" (
    echo [%date% %time:~0,8%] 错误：在 %DOCKERFILE_DIR% 中未找到dockerfile
    pause
    exit /b 1
)


:: 启动Docker Desktop
echo [%date% %time:~0,8%] 启动Docker Desktop...
start "" "%DOCKER_PATH%"

:: 等待Docker启动（动态检测而非固定等待）
echo [%date% %time:~0,8%] 等待Docker服务启动...
:WAIT_FOR_DOCKER
:: 检查Docker服务是否可用
docker info >nul 2>&1
if %errorlevel% equ 0 (
    echo [%date% %time:~0,8%] Docker服务已成功启动
    goto DOCKER_READY
)

:: 检查是否超时
if !ELAPSED_SECONDS! geq !MAX_WAIT_SECONDS! (
    echo [%date% %time:~0,8%] 错误：等待Docker启动超时（超过!MAX_WAIT_SECONDS!秒）
    pause
    exit /b 1
)

:: 未超时则继续等待
echo [%date% %time:~0,8%] Docker尚未启动，已等待!ELAPSED_SECONDS!秒，将在!CHECK_INTERVAL!秒后再次检查...
timeout /t !CHECK_INTERVAL! /nobreak >nul
set /a ELAPSED_SECONDS+=!CHECK_INTERVAL!
goto WAIT_FOR_DOCKER

:DOCKER_READY

:: 切换到项目目录
echo.
echo [%date% %time:~0,8%] 切换到项目目录: %PROJECT_DIR%
cd /d "%PROJECT_DIR%"
if %errorlevel% neq 0 (
    echo [%date% %time:~0,8%] 错误：无法切换到项目目录
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
if exist "%PROJECT_DIR%\blueprints\supply\__pycache__" (
    rmdir /s /q "%PROJECT_DIR%\blueprints\supply\__pycache__"
    echo [%date% %time:~0,8%] 已删除blueprints\supply\__pycache__文件夹
)
if exist "%PROJECT_DIR%\blueprints\role\__pycache__" (
    rmdir /s /q "%PROJECT_DIR%\blueprints\role\__pycache__"
    echo [%date% %time:~0,8%] 已删除blueprints\role\__pycache__文件夹
)
if exist "%PROJECT_DIR%\models\__pycache__" (
    rmdir /s /q "%PROJECT_DIR%\models\__pycache__"
    echo [%date% %time:~0,8%] 已删除models\__pycache__文件夹
)
if exist "%PROJECT_DIR%\models\supply\__pycache__" (
    rmdir /s /q "%PROJECT_DIR%\models\supply\__pycache__"
    echo [%date% %time:~0,8%] 已删除models\supply\__pycache__文件夹
)
if exist "%PROJECT_DIR%\models\role\__pycache__" (
    rmdir /s /q "%PROJECT_DIR%\models\role\__pycache__"
    echo [%date% %time:~0,8%] 已删除models\role\__pycache__文件夹
)
if exist "%PROJECT_DIR%\utils\__pycache__" (
    rmdir /s /q "%PROJECT_DIR%\utils\__pycache__"
    echo [%date% %time:~0,8%] 已删除utils\__pycache__文件夹
)
if exist "%PROJECT_DIR%\data" (
    rmdir /s /q "%PROJECT_DIR%\data"
    echo [%date% %time:~0,8%] 已删除data文件夹
)

echo [%date% %time:~0,8%] 已清理临时文件...

:: 创建数据目录（如果不存在）
if not exist "%DOCKERDATA_DIR%" (
    mkdir "%DOCKERDATA_DIR%"
    echo [%date% %time:~0,8%] 已创建数据目录：%DOCKERDATA_DIR%
)

:: 创建保存目录（如果不存在）
if not exist "%DOCKERSAVE_DIR%" (
    mkdir "%DOCKERSAVE_DIR%"
    echo [%date% %time:~0,8%] 已创建输出目录：%DOCKERSAVE_DIR%
)

:: 执行Docker命令
echo.
echo [%date% %time:~0,8%] 开始删除现有容器（如果存在）...
docker rm -f dorm-system
:: 忽略容器不存在的错误，继续执行
if %errorlevel% equ 1 (
    echo [%date% %time:~0,8%] 提示：dorm-system容器不存在，跳过删除步骤
)

echo.
echo [%date% %time:~0,8%] 开始构建Docker镜像...
:: 使用-f参数指定Dockerfile的具体路径
docker build -t %IMAGE_NAME% -f "%DOCKERFILE_DIR%\dockerfile" .
if %errorlevel% neq 0 (
    echo [%date% %time:~0,8%] 错误：Docker镜像构建失败
    pause
    exit /b 1
) else (
	echo [%date% %time:~0,8%] 构建Docker镜像成功...
)

echo.
echo [%date% %time:~0,8%] 开始导出Docker镜像...
:: 修正：-o后面指定具体的tar文件名，而非目录
docker save -o "%OUTPUT_TAR%" %IMAGE_NAME%
if %errorlevel% neq 0 (
    echo [%date% %time:~0,8%] 错误：Docker镜像导出失败
    pause
    exit /b 1
)

:: 完成提示
echo.
echo ==============================================
echo [%date% %time:~0,8%] 所有操作已成功完成！
echo [%date% %time:~0,8%] Docker镜像已导出至：%OUTPUT_TAR%
echo 完成时间: %date% %time:~0,8%
echo ==============================================

pause
exit /b 0
