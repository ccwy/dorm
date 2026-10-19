"""
通用数据路径模块

统一管理各环境（Docker/Android/打包/开发）下的 data 基础路径。
所有需要访问 data 目录的代码都应使用本模块的函数，避免重复的环境判断逻辑。

路径规则：
- Docker环境:   /data（外部数据卷）
- Android环境:  APP_DATA_DIR 环境变量（由 android_adapter.setup_android_env() 设置）
- 打包环境:     sys.executable 所在目录/data
- 开发环境:     项目根目录/data
"""

import os
import sys


def get_data_dir():
    """
    获取基础 data 目录路径（延迟求值）

    每次调用时根据当前环境变量计算路径，避免模块加载时序问题。
    Android 环境下 APP_DATA_DIR 由 android_adapter.setup_android_env() 设置，
    必须在环境变量设置后才能正确解析路径。
    """
    if os.environ.get('DOCKER_ENV', 'false').lower() == 'true':
        # Docker环境 - 使用外部数据卷路径
        return '/data'
    elif os.environ.get('ANDROID_ENV', 'false').lower() == 'true':
        # Android环境 - 使用 APP_DATA_DIR（由 android_adapter.py 设置）
        return os.environ.get('APP_DATA_DIR', '/data')
    elif getattr(sys, 'frozen', False):
        # 打包环境 - data目录在可执行文件所在目录下
        app_dir = os.path.dirname(sys.executable)
        return os.path.join(app_dir, 'data')
    else:
        # 开发环境 - data目录在项目根目录下
        current_file_dir = os.path.abspath(os.path.dirname(__file__))
        app_dir = os.path.abspath(os.path.join(current_file_dir, os.pardir))
        return os.path.join(app_dir, 'data')


def get_data_path(*subdirs):
    """
    获取 data 目录下的子路径

    用法示例：
        get_data_path('data.db')                      → {data_dir}/data.db
        get_data_path('photo', 'todo_photo')          → {data_dir}/photo/todo_photo
        get_data_path('logs')                         → {data_dir}/logs

    Args:
        *subdirs: 任意数量的子目录/文件名，按顺序拼接

    Returns:
        str: 拼接后的完整路径
    """
    return os.path.join(get_data_dir(), *subdirs)


def ensure_data_path(*subdirs):
    """
    获取 data 目录下的子路径，并确保目录存在

    如果路径指向目录（无扩展名），会自动创建该目录。
    用法示例：
        ensure_data_path('photo', 'todo_photo')  → 创建并返回 {data_dir}/photo/todo_photo
        ensure_data_path('logs')                 → 创建并返回 {data_dir}/logs

    Args:
        *subdirs: 任意数量的子目录名

    Returns:
        str: 拼接后的完整路径（目录已确保存在）
    """
    path = get_data_path(*subdirs)
    os.makedirs(path, exist_ok=True)
    return path