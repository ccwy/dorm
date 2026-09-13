"""
Windows单实例控制模块

职责：
- 命名互斥体（Named Mutex）创建/释放
- 重复实例检测：已有实例运行时激活其窗口并退出当前进程
- 后台线程监听激活事件，收到信号时将窗口带到前台
- 重启标志管理：防止WebView窗口关闭时主线程提前退出

使用方式：
    from utils.single_instance import single_instance

    # 启动时检测
    single_instance.check_and_acquire()

    # 设置窗口句柄（供激活事件使用）
    single_instance.set_window_handle(hwnd)

    # 重启流程中
    single_instance.set_restarting()
    single_instance.release_mutex()

    # 检查是否正在重启
    if single_instance.is_restarting():
        ...
"""

import sys
import time
import logging
import threading


class SingleInstanceManager:
    """Windows单实例管理器

    通过命名互斥体确保同一时刻只有一个应用实例运行。
    当检测到重复实例时，通过命名事件通知已有实例激活其窗口。
    """

    # 命名内核对象名称（Local\ 前缀表示仅当前会话可见）
    MUTEX_NAME = "Local\\DormManagement_SingleInstance"
    EVENT_NAME = "Local\\DormManagement_ActivateEvent"

    # Windows API 常量
    ERROR_ALREADY_EXISTS = 183
    EVENT_MODIFY_STATE = 0x1F0003  # EVENT_ALL_ACCESS
    INFINITE_WAIT = 0xFFFFFFFF
    SW_RESTORE = 9

    def __init__(self):
        self._mutex = None
        self._window_handle = None
        self._is_restarting = False

    def check_and_acquire(self):
        """Windows单实例检测：已有实例运行时激活其窗口并退出当前进程

        重启场景特殊处理：当检测到 --restarted 参数时，说明当前进程是
        由重启流程启动的新进程，此时旧进程的互斥体可能尚未被 Windows
        内核完全清理，需要重试等待而非立即退出。
        """
        import ctypes
        kernel32 = ctypes.windll.kernel32

        # 如果是重启操作，使用重试机制等待旧进程互斥体释放
        if '--restarted' in sys.argv:
            logging.info("检测到重启操作(--restarted)，等待旧实例互斥体释放")
            for attempt in range(10):
                mutex = kernel32.CreateMutexW(None, False, self.MUTEX_NAME)
                if kernel32.GetLastError() != self.ERROR_ALREADY_EXISTS:
                    self._mutex = mutex
                    self._start_activate_watcher()
                    logging.info(f"重启操作：成功获取单实例互斥体（第{attempt + 1}次尝试）")
                    return
                # 互斥体仍被旧进程持有，关闭本次获取的句柄后重试
                kernel32.CloseHandle(mutex)
                logging.info(f"等待旧实例互斥体释放... ({attempt + 1}/10)")
                time.sleep(1)

            # 超时后强制继续启动（互斥体可能是残留的，旧进程已退出）
            logging.warning("重启操作：互斥体等待超时，强制继续启动")
            mutex = kernel32.CreateMutexW(None, False, self.MUTEX_NAME)
            self._mutex = mutex
            self._start_activate_watcher()
            return

        # 正常启动的单实例检测逻辑
        mutex = kernel32.CreateMutexW(None, False, self.MUTEX_NAME)
        if kernel32.GetLastError() == self.ERROR_ALREADY_EXISTS:
            # 已有实例运行，发送激活信号
            event_handle = kernel32.OpenEventW(self.EVENT_MODIFY_STATE, False, self.EVENT_NAME)
            if event_handle:
                kernel32.SetEvent(event_handle)
                kernel32.CloseHandle(event_handle)
            time.sleep(0.5)
            sys.exit(0)

        # 保存互斥体句柄，防止被GC回收
        self._mutex = mutex
        self._start_activate_watcher()

    def release_mutex(self):
        """主动释放单实例互斥体，供重启流程调用

        在进程退出前释放互斥体，避免新进程启动时检测到残留互斥体
        导致误判为"已有实例运行"而退出。
        """
        if self._mutex:
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                kernel32.ReleaseMutex(self._mutex)
                kernel32.CloseHandle(self._mutex)
                logging.info("已主动释放单实例互斥体")
            except Exception as e:
                logging.warning(f"释放单实例互斥体失败: {e}")
            finally:
                self._mutex = None

    def set_restarting(self):
        """设置重启标志，防止WebView窗口关闭时触发os._exit(0)

        当重启流程关闭WebView窗口时，webview.start()会返回，
        主线程会执行os._exit(0)终止整个进程，导致重启线程
        还没来得及启动新进程就被杀死。设置此标志后，主线程
        会等待重启线程完成进程终止，而不是自行退出。
        """
        self._is_restarting = True
        logging.info("已设置重启标志，主线程将在窗口关闭后等待重启线程完成")

    def is_restarting(self):
        """检查是否正在重启"""
        return self._is_restarting

    def set_window_handle(self, hwnd):
        """设置主窗口句柄，供单实例激活使用"""
        self._window_handle = hwnd

    def _start_activate_watcher(self):
        """后台线程监听激活事件，收到信号时将已有窗口带到前台"""
        import ctypes

        def watcher():
            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32
            event_handle = kernel32.CreateEventW(None, True, False, self.EVENT_NAME)
            if not event_handle:
                return
            while True:
                # 无限等待激活信号
                kernel32.WaitForSingleObject(event_handle, self.INFINITE_WAIT)
                kernel32.ResetEvent(event_handle)
                hwnd = self._window_handle
                if hwnd:
                    # SW_RESTORE = 9，恢复最小化/隐藏的窗口
                    user32.ShowWindow(hwnd, self.SW_RESTORE)
                    user32.SetForegroundWindow(hwnd)

        threading.Thread(target=watcher, daemon=True).start()


# 模块级单例，方便跨模块导入使用
single_instance = SingleInstanceManager()