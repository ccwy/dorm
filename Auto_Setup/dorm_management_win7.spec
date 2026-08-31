# -*- mode: python ; coding: utf-8 -*-
# Win7专用独立版本 PyInstaller打包配置
# 移除pywebview依赖，硬编码服务端模式

import sys
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 获取当前目录（不使用__file__）
current_dir = os.path.dirname(os.path.abspath(sys.argv[0])) if len(sys.argv) > 0 else os.getcwd()

# 定义项目根目录（脚本位于Auto_Setup文件夹中，需要向上一级目录）
project_root = os.path.abspath(os.path.join(current_dir, '..'))

# 定义资源文件路径 - 指向项目根目录下的资源
data_dir = os.path.join(project_root, 'data')

# 确保data目录存在
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

# Win7专用：移除webview，添加win32api支持
additional_hidden_imports = [
    'pymysql',
    'cryptography',
    'openpyxl',
    'pandas',
    'numpy',
    'waitress',
    # 注意：Win7版本不包含webview
    'flask',
    'flask_sqlalchemy',
    'flask_login',
    'flask_wtf',
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
    'psutil',
    # Win7专用：添加pywin32支持
    'win32api',
    'win32con',
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
    binaries=[],
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
    # 排除不需要的模块以减小包体积
    excludes=[
        'pysqlite2', 'MySQLdb', 'psycopg2',  # 不需要的数据库驱动
        'unittest', 'test', 'tests',  # 测试框架
        'setuptools', 'pip', 'wheel',  # 包管理工具
        'pydoc', 'doctest',  # 文档工具
        'xmlrpc',  # XML-RPC（不需要）
        'py_compile', 'compileall',  # 编译工具
        'cProfile', 'profile', 'pstats',  # 性能分析工具
        'zipimport',  # ZIP导入
        # Win7专用：明确排除pywebview相关模块
        'webview', 'pywebview',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

# 创建可执行文件
app_unique_suffix = "dorm_mgmt_win7_v1.0"

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='行政后勤管理系统_Win7',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # 禁用UPX压缩——UPX解压开销会拖慢启动速度
    upx_exclude=[],
    runtime_tmpdir=None,
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
    print("\nPyInstaller打包完成（Win7专用版本）。")
    print("请使用Inno Setup打开installer_script_win7.iss文件创建Win7安装程序。")