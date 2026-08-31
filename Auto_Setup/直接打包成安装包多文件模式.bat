@echo off
setlocal enabledelayedexpansion

:: ��Ŀ��Ŀ¼
cd /d "%~dp0.."
set "PROJECT_DIR=%cd%"
set "DEST_DIR=%PROJECT_DIR%\Auto_Setup\Output"

:: ��ʾ��ʼ��Ϣ��ʱ��
echo ==============================================
echo ��ʼִ��Python����һ����װ���̣�������ģʽ��
echo ��ʼʱ��: %date% %time:~0,8%
echo ��Ŀ·��: %PROJECT_DIR%
echo ==============================================
echo.

:: �л�����ĿĿ¼
echo [%date% %time:~0,8%] �л�����ĿĿ¼...
cd /d "%PROJECT_DIR%"
if %errorlevel% neq 0 (
    echo [%date% %time:~0,8%] �����޷��л�����ĿĿ¼ %PROJECT_DIR%
    pause
    exit /b 1
)

:: ��ʼ������ʱ�ļ���
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

:: ���pyinstaller�Ƿ��Ѱ�װ
echo [%date% %time:~0,8%] ���pyinstaller�Ƿ��Ѱ�װ...
python -m pip show pyinstaller >nul 2>&1
if %errorlevel% equ 0 (
    echo [%date% %time:~0,8%] pyinstaller �Ѱ�װ���Զ�ִ����һ��...
) else (
	echo [%date% %time:~0,8%] pyinstaller δ��װ����ʼ��װ...
	pip install pyinstaller==6.16
	if %errorlevel% equ 0 (
		echo [%date% %time:~0,8%] pyinstaller ��װ�ɹ����Զ�ִ����һ��...
	) else (
		echo [%date% %time:~0,8%] ����pyinstaller ��װʧ�ܣ������������ӻ�Ȩ�����⡣
		pause
		exit /b 1
	)
)

:: ��Ⲣ��װ��������
echo.
echo [%date% %time:~0,8%] ��ʼ�����Ŀ����...

:: ������Ҫ���Ͱ�װ�������б���ʹ�ñ�ű���������⣩
set "dep1=Flask>=2.3.3"
set "dep2=Flask-SQLAlchemy>=3.1.1"
set "dep3=Flask-WTF>=1.2.1"
set "dep4=Flask-Login>=0.6.3"
set "dep5=Flask-Migrate>=4.0.5"
set "dep6=openpyxl>=3.1.2"
set "dep7=pandas>=2.0.3,<2.1"
set "dep8=numpy>=1.24.4,<1.25"
set "dep9=python-dotenv>=1.0.0"
set "dep10=PyMySQL>=1.1.0"
set "dep11=cryptography>=41.0.7,<43.0"
set "dep12=Werkzeug>=2.3.7"
set "dep13=Jinja2>=3.1.2"
set "dep14=schedule>=1.2.0"
set "dep15=xlsxwriter>=3.2.5"
set "dep16=waitress>=2.1.2"
set "dep17=pywebview==3.7"
set "dep18=requests>=2.31.0"
set "dep19=psutil>=5.9.8,<6.0"
set "dep20=Pillow>=10.4.0,<11.0"
set "dep21=pystray>=0.19.5"

:: ѭ����Ⲣ��װ������ʹ�ñ��ѭ�����������ַ����⣩
for /l %%i in (1,1,21) do (
    :: ��ȡ��ǰ������
    set "current_dep=!dep%%i!"
    
    :: ��ȡ������ȥ���汾��Ϣ��
    for /f "delims==<>" %%p in ("!current_dep!") do set "package=%%p"
    
    echo.
    echo [%date% %time:~0,8%] ��� !package! �Ƿ�װ...
    python -m pip show "!package!" >nul 2>&1
    if !errorlevel! equ 0 (
        echo [%date% %time:~0,8%] !package! �Ѱ�װ������...
    ) else (
        echo [%date% %time:~0,8%] !package! δ��װ����ʼ��װ !current_dep!...
        pip install "!current_dep!"
        if !errorlevel! equ 0 (
            echo [%date% %time:~0,8%] !package! ��װ�ɹ���
        ) else (
            echo [%date% %time:~0,8%] ����!package! ��װʧ��
            pause
            exit /b 1
        )
    )
)
echo.
echo [%date% %time:~0,8%] �����������Ͱ�װ���...

:: ֱ�ӵ���pyinstaller��ͬһ����ִ�У��Զ��ȴ���ɣ�
echo.
echo [%date% %time:~0,8%] ��ʼʹ��pyinstaller�������...
echo y | pyinstaller "%PROJECT_DIR%\Auto_Setup\dorm_management_multifile.spec"
if %errorlevel% neq 0 (
    echo [%date% %time:~0,8%] ����pyinstaller���ʧ��
    pause
    exit /b 1
)

:: ��������ʾ
echo.
echo [%date% %time:~0,8%] ==============================================
echo [%date% %time:~0,8%] Python�����������...
echo [%date% %time:~0,8%] �ȴ���ɱ�����Զ����밲װ�����ɲ���...
timeout /t 2 /nobreak >nul
echo [%date% %time:~0,8%] ==============================================

:: ֱ�ӵ���Inno Setup��ͬһ����ִ�У��Զ��ȴ���ɣ�
echo.
echo [%date% %time:~0,8%] ��ʼʹ��Inno Setup���ɰ�װ��...
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "%PROJECT_DIR%\Auto_Setup\installer_script_multifile.iss"
if %errorlevel% neq 0 (
    echo [%date% %time:~0,8%] ����Inno Setup���ɰ�װ��ʧ��
    pause
    exit /b 1
)


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

:: �����ʾ
echo.
echo [%date% %time:~0,8%] ==============================================
echo [%date% %time:~0,8%] ���в����ѳɹ���ɣ�
echo [%date% %time:~0,8%] �������Ͱ�װ�����ɾ����Զ���ɣ�
echo [%date% %time:~0,8%] ����Ϊ���ļ���ɫ�汾��
echo [%date% %time:~0,8%] ����ļ��ѱ�����: %DEST_DIR%
echo ���ʱ��: %date% %time:~0,8%
echo [%date% %time:~0,8%] ==============================================

pause
exit /b 0
