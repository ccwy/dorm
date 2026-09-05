"""
Android 平台适配层

提供 Android 环境下的路径映射、环境配置和桌面依赖的空模块替换。
此文件仅在 Android 环境下被使用，不影响 Windows/Docker 端的任何逻辑。
"""

import os
import sys
import logging
import types

logger = logging.getLogger(__name__)

# ==================== 路径映射 ====================

_android_context = None


def set_android_context(context):
    """设置 Android Context（由 Chaquopy 调用）"""
    global _android_context
    _android_context = context


def get_android_context():
    """获取 Android Context"""
    return _android_context


def get_files_dir():
    """
    获取 Android 内部存储路径（等同于 Context.getFilesDir()）
    Chaquopy 环境下通过 sys.path 推断，或通过 Context 获取
    """
    if _android_context is not None:
        try:
            return str(_android_context.getFilesDir().getAbsolutePath())
        except Exception:
            pass

    # 备用方案：从 sys.path 推断
    for path in sys.path:
        if 'files' in path and 'chaquopy' in path.lower():
            return os.path.dirname(path)

    # 最终回退
    return os.getcwd()


def get_cache_dir():
    """获取 Android 缓存路径"""
    if _android_context is not None:
        try:
            return str(_android_context.getCacheDir().getAbsolutePath())
        except Exception:
            pass
    return os.path.join(get_files_dir(), 'cache')


def get_database_path(db_name='data.db'):
    """获取数据库文件路径"""
    data_dir = os.environ.get('APP_DATA_DIR', os.path.join(get_files_dir(), 'data'))
    return os.path.join(data_dir, db_name)


# ==================== 环境配置 ====================

def setup_android_env():
    """
    设置 Android 环境变量

    在 Flask 启动前调用，确保所有环境检测正确识别 Android 平台。
    APP_DATA_DIR 统一指向 {files_dir}/data，与 Docker(/data) 和 Windows({app}/data) 结构一致。
    所有数据（数据库、配置、照片、文件共享、备份）均存储在 APP_DATA_DIR 下。
    """
    # 设置 Android 环境标识（与 DOCKER_ENV 机制一致）
    os.environ['ANDROID_ENV'] = 'true'

    # 强制客户端模式
    os.environ['SERVER_MODE'] = '客户端'

    # 禁用桌面视图
    os.environ['USE_DESKTOP_VIEW'] = 'false'

    # 设置数据目录：统一使用 {files_dir}/data 作为数据根目录
    # 目录结构：data/{data.db, db_config.json, photo/, file_sharing/, backups/}
    files_dir = get_files_dir()
    data_dir = os.path.join(files_dir, 'data')
    os.environ['APP_DATA_DIR'] = data_dir

    # 配置 Python 路径
    if files_dir not in sys.path:
        sys.path.insert(0, files_dir)

    # 确保数据目录结构存在
    ensure_data_dirs(data_dir)

    logger.info(f"Android 环境配置完成: files_dir={files_dir}, data_dir={data_dir}")


def ensure_data_dirs(data_dir):
    """
    创建 Android 数据目录结构

    统一目录结构：
    data/
    ├── data.db              ← SQLite 数据库
    ├── db_config.json       ← 数据库配置
    ├── photo/               ← 照片存储
    │   ├── asset_photo/     ← 资产照片
    │   ├── room_photo/      ← 房间照片
    │   ├── maintenance_photo/ ← 维修照片
    │   ├── contract_attachments/ ← 合同附件
    │   ├── room_meter_photo/ ← 水电表照片
    │   ├── todo_photo/      ← 待办照片
    │   └── ticket_photo/    ← 工单照片
    ├── file_sharing/        ← 文件共享
    └── backups/             ← 数据库备份
    """
    subdirs = [
        '',  # data 根目录本身
        'photo',
        'photo/asset_photo',
        'photo/room_photo',
        'photo/maintenance_photo',
        'photo/maintenance_temp',
        'photo/contract_attachments',
        'photo/room_meter_photo',
        'photo/todo_photo',
        'photo/ticket_photo',
        'file_sharing',
        'backups',
        'logs',
    ]

    for subdir in subdirs:
        dir_path = os.path.join(data_dir, subdir) if subdir else data_dir
        if not os.path.exists(dir_path):
            try:
                os.makedirs(dir_path, exist_ok=True)
                logger.debug(f"创建数据目录: {dir_path}")
            except Exception as e:
                logger.warning(f"创建数据目录失败: {dir_path}, 错误: {e}")


# ==================== 空模块替换（Stub） ====================

def _create_stub_module(name, attrs=None):
    """
    创建空模块替换

    在 Android 上替换 tkinter、pywebview、pystray、psutil 等不可用的桌面依赖。
    模块提供空函数/类，确保 import 不报错，但调用时抛出明确异常。
    """
    module = types.ModuleType(name)
    module.__file__ = f'<android_stub:{name}>'
    module.__package__ = name

    if attrs:
        for attr_name, attr_value in attrs.items():
            setattr(module, attr_name, attr_value)

    return module


def _stub_function(name):
    """创建一个调用时抛出异常的空函数"""
    def _func(*args, **kwargs):
        raise RuntimeError(
            f"{name}() 不可用：当前运行在 Android 平台，"
            f"此功能需要桌面环境支持。"
        )
    _func.__name__ = name
    return _func


def install_stub_modules():
    """
    安装空模块替换

    在 Android 上替换以下不可用的桌面依赖：
    - tkinter: GUI 工具包
    - pywebview: 桌面 WebView
    - pystray: 系统托盘
    - psutil: 进程管理（Android 使用 Activity 生命周期替代）

    注意：仅在 Android 环境下调用，Windows/Docker 端不受影响。
    """
    if not os.environ.get('ANDROID_ENV', 'false').lower() == 'true':
        logger.debug("非 Android 环境，跳过 stub 模块安装")
        return

    # tkinter stub
    if 'tkinter' not in sys.modules:
        tkinter_stub = _create_stub_module('tkinter', {
            'Tk': type('Tk', (), {'__init__': _stub_function('tkinter.Tk')}),
            'Frame': type('Frame', (), {}),
            'Label': type('Label', (), {}),
            'Button': type('Button', (), {}),
            'messagebox': _create_stub_module('tkinter.messagebox', {
                'showinfo': _stub_function('messagebox.showinfo'),
                'showwarning': _stub_function('messagebox.showwarning'),
                'showerror': _stub_function('messagebox.showerror'),
            }),
        })
        sys.modules['tkinter'] = tkinter_stub
        sys.modules['tkinter.messagebox'] = tkinter_stub.messagebox

    # pywebview stub
    if 'webview' not in sys.modules:
        webview_stub = _create_stub_module('webview', {
            'create_window': _stub_function('webview.create_window'),
            'start': _stub_function('webview.start'),
        })
        sys.modules['webview'] = webview_stub

    # pystray stub
    if 'pystray' not in sys.modules:
        pystray_stub = _create_stub_module('pystray', {
            'Icon': type('Icon', (), {'__init__': _stub_function('pystray.Icon')}),
        })
        sys.modules['pystray'] = pystray_stub

    # psutil stub（Android 使用 Activity 生命周期替代进程管理）
    if 'psutil' not in sys.modules:
        psutil_stub = _create_stub_module('psutil', {
            'Process': type('Process', (), {'__init__': _stub_function('psutil.Process')}),
            'process_iter': _stub_function('psutil.process_iter'),
            'pid_exists': _stub_function('psutil.pid_exists'),
        })
        sys.modules['psutil'] = psutil_stub

    logger.info("Android stub 模块安装完成")


# ==================== Flask 启动适配 ====================

def start_flask_server():
    """
    Android 端 Flask 服务器启动入口

    由 Chaquopy 从 Android 端调用，完成以下步骤：
    1. 设置 Android 环境标识（此函数仅从 Android/Chaquopy 调用）
    2. 安装 stub 模块
    3. 设置 Android 环境变量
    4. 启动 Flask+waitress 服务器
    """
    # 此函数仅从 Android/Chaquopy 调用，立即设置 ANDROID_ENV 标识
    # 必须在检查之前设置，否则 setup_android_env() 尚未执行会导致检查失败
    os.environ['ANDROID_ENV'] = 'true'

    if not os.environ.get('ANDROID_ENV', 'false').lower() == 'true':
        logger.warning("start_flask_server() 仅应在 Android 环境下调用")
        return None

    # 1. 安装 stub 模块（必须在所有 import 之前）
    install_stub_modules()

    # 2. 设置环境变量
    setup_android_env()

    # 3. 导入并启动 Flask
    from main import init_flask_app
    app, process_cleaner, run_server = init_flask_app()

    logger.info("Android 端 Flask 应用初始化完成")

    # 4. 启动 waitress 服务器
    run_server()

    return app