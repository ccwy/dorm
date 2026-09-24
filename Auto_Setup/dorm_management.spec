# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 获取当前目录（不使用__file__）
current_dir = os.path.dirname(os.path.abspath(sys.argv[0])) if len(sys.argv) > 0 else os.getcwd()

# 定义项目根目录（脚本位于Auto_Setup文件夹中，需要向上一级目录）
project_root = os.path.abspath(os.path.join(current_dir, '..'))

# ===== Windows 7 兼容性：收集 UCRT DLL =====
# Python 3.5+ 依赖 Universal C Runtime (UCRT)，Win7 未内置
# 从 Python 安装目录收集 UCRT DLL 打包进应用，确保 Win7 可运行
ucrt_binaries = []
if sys.platform == 'win32':
    # UCRT DLL 通常位于 Python 安装目录或 Windows System32
    # 从 Python 目录收集（这些 DLL 与 Python 版本匹配，兼容性最好）
    python_dir = os.path.dirname(sys.executable)
    ucrt_dll_names = [
        'ucrtbase.dll',
        'api-ms-win-crt-runtime-l1-1-0.dll',
        'api-ms-win-crt-stdio-l1-1-0.dll',
        'api-ms-win-crt-heap-l1-1-0.dll',
        'api-ms-win-crt-string-l1-1-0.dll',
        'api-ms-win-crt-convert-l1-1-0.dll',
        'api-ms-win-crt-environment-l1-1-0.dll',
        'api-ms-win-crt-filesystem-l1-1-0.dll',
        'api-ms-win-crt-math-l1-1-0.dll',
        'api-ms-win-crt-time-l1-1-0.dll',
        'api-ms-win-crt-utility-l1-1-0.dll',
        'api-ms-win-crt-locale-l1-1-0.dll',
        'api-ms-win-crt-process-l1-1-0.dll',
        'api-ms-win-crt-multibyte-l1-1-0.dll',
        'api-ms-win-crt-signals-l1-1-0.dll',
    ]
    for dll_name in ucrt_dll_names:
        # 优先从 Python 目录查找
        dll_path = os.path.join(python_dir, dll_name)
        if os.path.isfile(dll_path):
            ucrt_binaries.append((dll_path, '.'))
            continue
        # 备用：从 System32 查找
        system32 = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'System32')
        dll_path = os.path.join(system32, dll_name)
        if os.path.isfile(dll_path):
            ucrt_binaries.append((dll_path, '.'))
    if ucrt_binaries:
        print(f"[Win7兼容] 收集到 {len(ucrt_binaries)} 个 UCRT DLL")

# 定义资源文件路径 - 指向项目根目录下的资源
data_dir = os.path.join(project_root, 'data')

# 确保data目录存在（添加这两行）
if not os.path.exists(data_dir):
    os.makedirs(data_dir)
    print(f"Created data directory: {data_dir}")

base = None
if sys.platform == 'win32':
    base = 'Win32GUI'  # 无控制台窗口

# 收集Flask模板和静态文件
templates_path = os.path.join(project_root, 'templates')
static_path = os.path.join(project_root, 'static')

# 数据库和配置文件
db_config_path = os.path.join(data_dir, 'db_config.json')
data_db_path = os.path.join(data_dir, 'data.db')

# 添加更多的隐藏导入
# 注意：pandas/openpyxl/pymysql 使用延迟导入（lazy_imports.py），
# PyInstaller静态分析无法检测到这些依赖，必须显式收集所有子模块
additional_hidden_imports = [
    'pymysql',
    'cryptography',
    'openpyxl',
    'pandas',
    'numpy',
    'waitress',
    'webview',
    'flask',
    'flask_sqlalchemy',
    'flask_login',
    'jinja2',
    'werkzeug',
    'schedule',
    'xlsxwriter',
    'requests',
    'tkinter',
    'tkinter.ttk',
    'tkinter.messagebox',
    'pystray',
    'PIL',
    'psutil'
]

# 收集延迟导入库的所有子模块，确保打包完整
lazy_import_submodules = (
    collect_submodules('pymysql') +
    collect_submodules('pandas') +
    collect_submodules('openpyxl') +
    collect_submodules('numpy') +
    collect_submodules('pystray') +
    collect_submodules('PIL')
)

a = Analysis(
    [os.path.join(project_root, 'main.py')],
    pathex=[project_root],
    binaries=ucrt_binaries,
    datas=[
        # 核心应用资源
        (templates_path, 'templates'),
        (static_path, 'static'),
        
        # 数据相关资源 - 只添加目录结构，不依赖具体文件
        (data_dir, 'data'),
    ],
    hiddenimports=(
        collect_submodules('blueprints') +
        collect_submodules('models') +
        collect_submodules('utils') +
        additional_hidden_imports +
        lazy_import_submodules
    ),
    # 排除不需要的模块以减小包体积和加速启动
    # 注意：仅排除确定不被任何依赖项使用的模块，避免运行时 ImportError
    excludes=[
        'pysqlite2', 'MySQLdb', 'psycopg2',  # 不需要的数据库驱动
        'unittest', 'test', 'tests',  # 测试框架
        'setuptools', 'pip', 'wheel',  # 包管理工具
        'pydoc', 'doctest',  # 文档工具
        'xmlrpc',  # XML-RPC（不需要）
        'py_compile', 'compileall',  # 编译工具
        'cProfile', 'profile', 'pstats',  # 性能分析工具
        'zipimport',  # ZIP导入
        'flask_wtf',  # 未使用的Flask扩展
        'flask_migrate',  # 未使用的Flask迁移工具
        'dotenv',  # python-dotenv模块，项目未使用
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[os.path.join(current_dir, 'runtime_hook_win7.py')],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# 创建可执行文件
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='行政后勤管理系统',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 禁用UPX压缩——UPX解压开销会拖慢启动速度
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_root, 'static', 'favicon.ico'),
    base=base,
)

# 如果是Windows平台，创建安装程序说明
if sys.platform == 'win32':
    print("\nPyInstaller打包完成后，请使用Inno Setup打开installer_script.iss文件创建完整的安装程序。")
    