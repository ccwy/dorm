"""
iOS 平台适配层

提供 iOS 环境下的路径映射、环境配置和桌面依赖的空模块替换。
此文件仅在 iOS 环境下被使用，不影响 Windows/Docker/Android 端的任何逻辑。

iOS 端架构：Swift 壳 + WKWebView + 嵌入式 Python（kivy-ios 编译的 Python.framework），
由 Swift 通过 Python C API 调用本模块的 start_flask_server() 启动本地 Flask 服务器。
"""

import os
import sys
import types
import logging

logger = logging.getLogger(__name__)

# ==================== 路径映射 ====================


def get_documents_dir():
    """
    获取 iOS 沙盒 Documents 目录路径

    iOS 上 Python 无法直接调用 NSDocumentDirectory，
    由 Swift 端在启动 Python 前通过环境变量 IOS_DOCUMENT_DIR 注入。
    若未注入则回退到 os.path.expanduser('~/Documents')。
    """
    documents_dir = os.environ.get('IOS_DOCUMENT_DIR')
    if documents_dir:
        return documents_dir
    # 回退方案
    return os.path.expanduser('~/Documents')


def get_cache_dir():
    """获取 iOS 缓存路径（Documents 目录下的 cache 子目录）"""
    return os.path.join(get_documents_dir(), 'cache')


def get_database_path(db_name='data.db'):
    """获取数据库文件路径"""
    data_dir = os.environ.get('APP_DATA_DIR', os.path.join(get_documents_dir(), 'data'))
    return os.path.join(data_dir, db_name)


# ==================== 环境配置 ====================


def setup_ios_env():
    """
    设置 iOS 环境变量

    在 Flask 启动前调用，确保所有环境检测正确识别 iOS 平台。
    APP_DATA_DIR 统一指向 {Documents}/data，与 Android(/sdcard/.../data)、
    Docker(/data) 和 Windows({app}/data) 结构一致。
    所有数据（数据库、配置、照片、文件共享、备份）均存储在 APP_DATA_DIR 下。
    """
    # 修复 iOS 上 stdout/stderr 默认 ASCII 编码，print 中文时 UnicodeEncodeError 崩溃
    # kivy-ios 编译的 Python.framework 不继承终端 UTF-8 locale，需显式重新配置
    try:
        if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        if sys.stderr and sys.stderr.encoding and sys.stderr.encoding.lower() not in ('utf-8', 'utf8'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    # 设置 iOS 环境标识（与 ANDROID_ENV / DOCKER_ENV 机制一致）
    os.environ['IOS_ENV'] = 'true'

    # 强制客户端模式
    os.environ['SERVER_MODE'] = '客户端'

    # 禁用桌面视图
    os.environ['USE_DESKTOP_VIEW'] = 'false'

    # 设置数据目录：统一使用 {Documents}/data 作为数据根目录
    # 目录结构：data/{data.db, db_config.json, photo/, file_sharing/, backups/}
    documents_dir = get_documents_dir()
    data_dir = os.path.join(documents_dir, 'data')
    os.environ['APP_DATA_DIR'] = data_dir

    # 确保项目根目录在 sys.path 中（Swift 端调用时 Python 可能不在项目目录启动）
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # 确保数据目录结构存在
    ensure_data_dirs(data_dir)

    logger.info(f"iOS 环境配置完成: documents_dir={documents_dir}, data_dir={data_dir}")


def ensure_data_dirs(data_dir):
    """
    创建 iOS 数据目录结构

    统一目录结构（与 Android 端完全一致）：
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
    │   ├── ticket_photo/    ← 工单照片
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

    在 iOS 上替换 tkinter、pywebview、pystray、psutil 等不可用的桌面依赖。
    模块提供空函数/类，确保 import 不报错，但调用时抛出明确异常。
    """
    module = types.ModuleType(name)
    module.__file__ = f'<ios_stub:{name}>'
    module.__package__ = name

    if attrs:
        for attr_name, attr_value in attrs.items():
            setattr(module, attr_name, attr_value)

    return module


def _stub_function(name):
    """创建一个调用时抛出异常的空函数"""
    def _func(*args, **kwargs):
        raise RuntimeError(
            f"{name}() 不可用：当前运行在 iOS 平台，"
            f"此功能需要桌面环境支持。"
        )
    _func.__name__ = name
    return _func


def install_stub_modules():
    """
    安装空模块替换

    在 iOS 上替换以下不可用的桌面依赖：
    - tkinter: GUI 工具包
    - pywebview: 桌面 WebView
    - pystray: 系统托盘
    - psutil: 进程管理（iOS 使用应用生命周期替代）
    - subprocess: 进程创建（kivy-ios 缺少 _posixsubprocess C 扩展）
    - concurrent.futures.process: 多进程执行器（iOS 缺少 _multiprocessing，回退线程池）
    - _multiprocessing: 多进程 C 扩展（kivy-ios 未编译）
    - pandas: 数据处理库（C 扩展无法编译，由 utils/pandas_compat.py 兼容层替代，
      基于 openpyxl/xlsxwriter 实现项目使用的 API 子集）

    注意：仅在 iOS 环境下调用，Windows/Docker/Android 端不受影响。
    """
    if not os.environ.get('IOS_ENV', 'false').lower() == 'true':
        logger.debug("非 iOS 环境，跳过 stub 模块安装")
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

    # psutil stub（iOS 使用应用生命周期替代进程管理）
    if 'psutil' not in sys.modules:
        psutil_stub = _create_stub_module('psutil', {
            'Process': type('Process', (), {'__init__': _stub_function('psutil.Process')}),
            'process_iter': _stub_function('psutil.process_iter'),
            'pid_exists': _stub_function('psutil.pid_exists'),
        })
        sys.modules['psutil'] = psutil_stub

    # subprocess stub（kivy-ios 编译的 Python.framework 缺少 _posixsubprocess C 扩展，
    # 标准库 subprocess.py 顶部 import _posixsubprocess 会失败，需替换防止间接导入崩溃）
    if 'subprocess' not in sys.modules:
        subprocess_stub = _create_stub_module('subprocess', {
            'Popen': type('Popen', (), {'__init__': _stub_function('subprocess.Popen')}),
            'run': _stub_function('subprocess.run'),
            'call': _stub_function('subprocess.call'),
            'check_call': _stub_function('subprocess.check_call'),
            'check_output': _stub_function('subprocess.check_output'),
            'DEVNULL': -1,
            'PIPE': -1,
            'STDOUT': -1,
            'CalledProcessError': type('CalledProcessError', (Exception,), {}),
            'TimeoutExpired': type('TimeoutExpired', (Exception,), {}),
        })
        sys.modules['subprocess'] = subprocess_stub

    # concurrent.futures.process stub（iOS 缺少 _multiprocessing C 扩展，无法多进程）
    # ProcessPoolExecutor 回退为 ThreadPoolExecutor，与 process_pool._is_android() 运行时逻辑一致
    if 'concurrent.futures.process' not in sys.modules:
        try:
            import concurrent.futures as _cf
            from concurrent.futures import ThreadPoolExecutor as _tpe
            _process_stub = _create_stub_module('concurrent.futures.process', {
                'ProcessPoolExecutor': _tpe,
            })
            sys.modules['concurrent.futures.process'] = _process_stub
            _cf.ProcessPoolExecutor = _tpe
        except Exception as e:
            logger.warning(f"concurrent.futures.process stub 安装失败: {e}")

    # _multiprocessing stub（kivy-ios Python.framework 缺少此 C 扩展）
    if '_multiprocessing' not in sys.modules:
        try:
            _mp_stub = _create_stub_module('_multiprocessing', {})
            sys.modules['_multiprocessing'] = _mp_stub
        except Exception as e:
            logger.warning(f"_multiprocessing stub 安装失败: {e}")

    # pandas 兼容层 stub（iOS 无 pandas C 扩展，用 openpyxl/xlsxwriter 实现兼容层）
    if 'pandas' not in sys.modules:
        try:
            from utils import pandas_compat
            sys.modules['pandas'] = pandas_compat
        except Exception as e:
            logger.warning(f"pandas 兼容层加载失败: {e}")

    logger.info("iOS stub 模块安装完成")


# ==================== Flask 启动进度（供 Swift 端轮询读取） ====================

_progress_pct = 0
_progress_msg = "正在初始化..."


def _ios_progress_callback(pct, msg):
    """iOS 端启动进度回调，更新全局进度状态"""
    global _progress_pct, _progress_msg
    _progress_pct = pct
    _progress_msg = msg


def get_progress():
    """
    返回当前启动进度字符串（pct|msg 格式），供 Swift 端通过 Python C API 轮询调用。

    使用方式（Swift 端）：
        let result = try pyObject.callMethod("get_progress")
        let parts = result.split(separator: "|")
        let pct = Int(parts[0])
        let msg = String(parts[1])
    """
    return f"{_progress_pct}|{_progress_msg}"


def get_system_title():
    """
    返回系统标题，供 Swift 端通过 Python C API 调用，动态设置 iOS 端界面标题。

    从 db_config.json 读取 SYSTEM_TITLE 配置项。
    在 setup_ios_env() 执行后调用（此时 APP_DATA_DIR 和配置文件路径已就绪）。

    使用方式（Swift 端）：
        let title = try pyObject.callMethod("get_system_title") ?? "行政后勤管理系统"
    """
    try:
        from utils.db_config import DatabaseConfig
        config = DatabaseConfig.load_config()
        return config.get("SYSTEM_TITLE", "行政后勤管理系统")
    except Exception as e:
        logger.warning(f"获取系统标题失败: {e}")
        return "行政后勤管理系统"


# ==================== Flask 启动适配 ====================


def start_flask_server():
    """
    iOS 端 Flask 服务器启动入口

    由 Swift 端通过 Python C API 调用，完成以下步骤：
    1. 设置 iOS 环境标识（此函数仅从 iOS 端调用）
    2. 安装 stub 模块
    3. 设置 iOS 环境变量
    4. 启动 Flask+waitress 服务器（带进度回调）
    """
    # 此函数仅从 iOS 端调用，立即设置 IOS_ENV 标识
    # 必须在检查之前设置，否则 setup_ios_env() 尚未执行会导致检查失败
    os.environ['IOS_ENV'] = 'true'

    if not os.environ.get('IOS_ENV', 'false').lower() == 'true':
        logger.warning("start_flask_server() 仅应在 iOS 环境下调用")
        return None

    try:
        # 1. 安装 stub 模块（必须在所有 import 之前）
        install_stub_modules()

        # 2. 设置环境变量
        setup_ios_env()

        # 3. 导入并启动 Flask（传递进度回调，Python 端更新全局变量，Swift 端轮询读取）
        from main import init_flask_app
        app, run_server = init_flask_app(progress_callback=_ios_progress_callback)

        logger.info("iOS 端 Flask 应用初始化完成")

        # 4. 启动 waitress 服务器
        run_server()
    except Exception:
        # 诊断：Swift 端 PyObject_CallObject 不检查返回值 NULL 对应的 Python 异常，
        # 异常会被静默吞掉，界面永远停留在"正在初始化 0%"。
        # 此处记录完整 traceback 到日志文件，并把错误摘要写入进度消息供 Swift 端显示。
        import traceback
        err = traceback.format_exc()
        global _progress_pct, _progress_msg
        _progress_msg = "启动失败: " + err.strip().splitlines()[-1][:200]
        try:
            log_dir = os.path.join(os.environ.get('APP_DATA_DIR', get_documents_dir()), 'logs')
            os.makedirs(log_dir, exist_ok=True)
            with open(os.path.join(log_dir, 'startup_error.log'), 'w', encoding='utf-8') as f:
                f.write(err)
        except Exception:
            pass
        raise

    return app