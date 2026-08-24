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

# Windows平台设置无控制台窗口
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
    [os.path.join(project_root, 'main.py')],  # 主入口文件
    pathex=[project_root],  # 项目路径
    binaries=[],  # 二进制文件
    datas=[
        # 核心应用资源
        (templates_path, 'templates'),  # 模板文件
        (static_path, 'static'),  # 静态文件
        
        # 数据相关资源
        (data_dir, 'data'),  # 数据目录
    ],
    hiddenimports=(
        collect_submodules('blueprints') +  # 收集所有blueprints模块
        collect_submodules('models') +  # 收集所有models模块
        collect_submodules('utils') +  # 收集所有utils模块
        additional_hidden_imports  # 额外的隐藏导入
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

# 创建可执行文件 - 多文件模式
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,  # 多文件模式关键参数：排除二进制文件
    name='宿舍管理系统',  # 可执行文件名
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 无控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_root, 'static', 'favicon.ico'),  # 图标文件
    base=base,
)

# 多文件模式需要COLLECT函数来收集所有依赖文件
coll = COLLECT(
    exe,  # 可执行文件
    a.binaries,  # 二进制文件
    a.zipfiles,  # 压缩文件
    a.datas,  # 数据文件
    strip=False,
    upx=True,
    upx_exclude=[],
    name='宿舍管理系统',  # 输出文件夹名称
)

# 如果是Windows平台，输出打包完成信息
if sys.platform == 'win32':
    print("\nPyInstaller多文件模式打包完成！")
    print(f"输出目录：{os.path.join(os.path.dirname(current_dir), 'dist', '宿舍管理系统')}")
    print("说明：这是多文件版本，包含主程序和多个支持文件")