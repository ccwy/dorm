# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# 获取当前目录（不使用__file__）
current_dir = os.path.dirname(os.path.abspath(sys.argv[0])) if len(sys.argv) > 0 else os.getcwd()

# 定义项目根目录（脚本位于Auto_Setup文件夹中，需要向上一级目录）
project_root = os.path.abspath(os.path.join(current_dir, '..'))

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
    'flask_wtf',
    'jinja2',
    'werkzeug',
    'schedule',
    'xlsxwriter',
    'requests',
    'psutil'
]

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
        additional_hidden_imports
    ),
    # 排除不需要的数据库驱动模块以消除警告
    excludes=['pysqlite2', 'MySQLdb', 'psycopg2'],
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
# 设置应用程序唯一后缀，与其他临时目录命名保持一致
app_unique_suffix = "dorm_mgmt_v1.0"

# 创建运行时临时目录前先确保基础目录存在
# 不使用自定义路径，让PyInstaller使用默认的临时目录处理机制
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='宿舍管理系统',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    print("\nPyInstaller打包完成后，请使用Inno Setup打开installer_script.iss文件创建完整的安装程序。")
    