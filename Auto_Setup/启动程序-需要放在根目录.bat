@echo off
setlocal enabledelayedexpansion

:: ��Ŀ��Ŀ¼
cd /d "%~dp0"
set "PROJECT_DIR=%cd%"

:: �л�����ĿĿ¼
echo [%date% %time:~0,8%] �л�����ĿĿ¼...
cd /d "%PROJECT_DIR%"
if %errorlevel% neq 0 (
    echo [%date% %time:~0,8%] �����޷��л�����ĿĿ¼ %PROJECT_DIR%
    pause
    exit /b 1
)

:: ��ʾ������Ϣ��ʱ��
cls
echo ==============================================
echo �������ϵͳ - һ�������ű�
echo ����ʱ��: %date% %time:~0,8%
echo ��Ŀ·��: %PROJECT_DIR%
echo ==============================================
echo.

:: ������ʱ�ļ���
echo.
echo [%date% %time:~0,8%] ��ʼ������ʱ�ļ�...
if exist "%PROJECT_DIR%\build" (
    rmdir /s /q "%PROJECT_DIR%\build"
    echo [%date% %time:~0,8%] ��ɾ��build�ļ���
)
if exist "%PROJECT_DIR%\__pycache__" (
    rmdir /s /q "%PROJECT_DIR%\__pycache__"
    echo [%date% %time:~0,8%] ��ɾ��__pycache__�ļ���
)
if exist "%PROJECT_DIR%\dist" (
    rmdir /s /q "%PROJECT_DIR%\dist"
    echo [%date% %time:~0,8%] ��ɾ��dist�ļ���
)
for /d /r "%PROJECT_DIR%" %%d in (__pycache__) do (
    if exist "%%d" (
        rmdir /s /q "%%d"
        echo [%date% %time:~0,8%] ��ɾ��%%d
    )
)
if exist "%PROJECT_DIR%\data" (
    rmdir /s /q "%PROJECT_DIR%\data"
    echo [%date% %time:~0,8%] ��ɾ��data�ļ���
)

:: ���Python�Ƿ�װ
echo [%date% %time:~0,8%] ���Python�Ƿ�װ...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [%date% %time:~0,8%] ����δ�ҵ�Python����ȷ��Python����ȷ��װ�����ӵ�ϵͳPATH��
    pause
    exit /b 1
) else (
    echo [%date% %time:~0,8%] Python�Ѱ�װ�����Զ�ִ����һ��...
)

:: ���requirements.txt�Ƿ����
echo.
echo [%date% %time:~0,8%] �����Ŀ����...
if not exist "%PROJECT_DIR%\requirements.txt" (
    echo [%date% %time:~0,8%] ���棺δ�ҵ�requirements.txt�ļ�������������顣
) else (
    :: ��װ�����������Ҫ��
    echo [%date% %time:~0,8%] ���ڰ�װ��Ŀ����...
    pip install -r "%PROJECT_DIR%\requirements.txt"
    if %errorlevel% neq 0 (
        echo [%date% %time:~0,8%] ���棺������װ�����г��ִ��󣬵�����������Ӧ�á�
    ) else (
        echo [%date% %time:~0,8%] ������װ��ɡ�
    )

    :: 生成PWA图标（幂等操作，重复运行无副作用）
    echo [%date% %time:~0,8%] 正在检查PWA图标...
    python "%PROJECT_DIR%\static\images\pwa\generate_pwa_icons.py"
    if %errorlevel% equ 0 (
        echo [%date% %time:~0,8%] PWA图标检查完成
    ) else (
        echo [%date% %time:~0,8%] PWA图标生成失败（非致命错误，应用仍可正常运行）
    )

    :: 检查VAPID密钥（如未配置则自动生成并持久化到data目录）
    echo [%date% %time:~0,8%] 正在检查VAPID推送密钥...
    python -c "from utils.generate_vapid_keys import ensure_vapid_keys; ensure_vapid_keys()"
    if %errorlevel% equ 0 (
        echo [%date% %time:~0,8%] VAPID密钥检查完成
    ) else (
        echo [%date% %time:~0,8%] VAPID密钥检查失败（推送通知功能可能不可用）
    )
)


:: 启动应用程序 ����Ӧ�ó���ָ������ģʽ����
echo.
echo [%date% %time:~0,8%] ==============================================
echo [%date% %time:~0,8%] ��������Ӧ�ó���...
echo [%date% %time:~0,8%] ��Ctrl+C��ֹͣӦ�ó���
echo [%date% %time:~0,8%] ==============================================
echo.

python "%PROJECT_DIR%\main.py"

echo ��������˳�...
pause >nul
exit /b %errorlevel%

