"""
跨平台进程池工具模块
根据运行环境自动选择最优的并发策略：
- Windows/Docker/Linux: 使用进程池（绕过GIL，利用多核CPU）
- Android: 降级为线程池（Chaquopy不支持多进程）
- 打包环境: 使用spawn方式启动子进程（兼容PyInstaller）
"""
import os
import logging
import platform
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, Executor
from typing import Optional


# 全局进程池/线程池实例（懒初始化）
_executor: Optional[Executor] = None
_executor_lock = __import__('threading').Lock()


def _is_android() -> bool:
    """检测是否为Android环境"""
    return os.environ.get('ANDROID_ENV', 'false').lower() == 'true'


def _is_docker() -> bool:
    """检测是否为Docker环境"""
    if _is_android():
        return False
    if os.getenv('DOCKER_ENV', 'false').lower() == 'true':
        return True
    return False


def get_optimal_workers() -> int:
    """
    根据环境获取最优worker数量
    - 默认使用CPU核心数，但至少2个，最多8个
    - Android环境限制为2（资源受限）
    """
    try:
        cpu_count = os.cpu_count() or 2
    except NotImplementedError:
        cpu_count = 2
    
    if _is_android():
        # Android资源受限，最多2个worker
        return min(2, cpu_count)
    
    # 其他环境：使用CPU核心数，但限制在2-8之间
    return max(2, min(cpu_count, 8))


def get_executor() -> Executor:
    """
    获取全局执行器实例（懒初始化）
    - Windows/Docker/Linux: 返回ProcessPoolExecutor
    - Android: 返回ThreadPoolExecutor
    """
    global _executor
    if _executor is not None:
        return _executor
    
    with _executor_lock:
        if _executor is not None:
            return _executor
        
        workers = get_optimal_workers()
        
        if _is_android():
            # Android环境降级为线程池
            logging.info(f"Android环境，使用线程池（workers={workers}）")
            _executor = ThreadPoolExecutor(
                max_workers=workers,
                thread_name_prefix='cpu_worker'
            )
        else:
            # Windows/Docker/Linux使用进程池
            # Windows必须使用spawn方式（兼容PyInstaller打包）
            # Linux默认使用fork，但在打包环境下也需要spawn
            is_frozen = getattr(__import__('sys'), 'frozen', False)
            mp_context = None
            
            if platform.system() == 'Windows' or is_frozen:
                from multiprocessing import get_context
                mp_context = get_context('spawn')
                logging.info(f"使用spawn方式启动子进程（workers={workers}）")
            
            try:
                _executor = ProcessPoolExecutor(
                    max_workers=workers,
                    mp_context=mp_context
                )
                logging.info(f"进程池已创建（workers={workers}，类型=ProcessPoolExecutor）")
            except Exception as e:
                # 进程池创建失败时降级为线程池
                logging.warning(f"进程池创建失败，降级为线程池: {e}")
                _executor = ThreadPoolExecutor(
                    max_workers=workers,
                    thread_name_prefix='cpu_worker'
                )
                logging.info(f"线程池已创建（workers={workers}，类型=ThreadPoolExecutor）")
        
        return _executor


def submit_task(func, *args, **kwargs):
    """
    提交CPU密集型任务到进程池/线程池
    返回 concurrent.futures.Future 对象
    
    注意：
    - 提交到ProcessPoolExecutor的函数和参数必须可pickle序列化
    - 不能是lambda、局部函数、或Flask请求上下文相关的对象
    - 数据库查询等I/O操作不适合放在进程池中（应在主进程完成查询后传递数据）
    
    使用示例：
        # 正确：数据处理任务
        future = submit_task(process_excel_data, raw_data)
        result = future.result(timeout=30)
        
        # 错误：涉及数据库查询的任务
        future = submit_task(export_from_db)  # 子进程无法访问Flask上下文
    """
    executor = get_executor()
    try:
        return executor.submit(func, *args, **kwargs)
    except Exception as e:
        logging.error(f"提交任务失败: {e}")
        # 降级为同步执行
        return _SyncFuture(func(*args, **kwargs))


class _SyncFuture:
    """同步Future包装器，当进程池不可用时降级为同步执行"""
    def __init__(self, result):
        self._result = result
    
    def result(self, timeout=None):
        return self._result
    
    def done(self):
        return True
    
    def cancel(self):
        return False
    
    def cancelled(self):
        return False


def shutdown_executor(wait=True):
    """关闭执行器，在应用退出时调用"""
    global _executor
    if _executor is not None:
        with _executor_lock:
            if _executor is not None:
                try:
                    _executor.shutdown(wait=wait)
                    logging.info("进程池/线程池已关闭")
                except Exception as e:
                    logging.warning(f"关闭执行器失败: {e}")
                finally:
                    _executor = None


def is_process_pool() -> bool:
    """判断当前使用的是否为进程池"""
    return isinstance(get_executor(), ProcessPoolExecutor)