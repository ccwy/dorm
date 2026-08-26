import os
import sys
import subprocess
import threading
import time
import logging
import ctypes
from ctypes import wintypes

# 【重要】本模块绝不导入 webview，即使在函数内部也不行。
# 原因：import webview 会触发 edgechromium.py 的模块级代码，
# 通过 pythonnet/clr 加载 WebView2 .NET 程序集，
# 而 WebView2 Core DLL 内部的安全验证机制会检查父进程可执行文件路径，
# 在 PyInstaller 打包环境中导致：
#   "Security validation failure: failed to obtain executable path for parent process!"
# 因此，关闭 WebView 窗口必须使用 Windows API (ctypes) 而非 webview.windows.destroy()

# 批处理脚本内容模板 - 打包环境使用，包含自动删除功能
batch_script_template = '''@echo off
setlocal enabledelayedexpansion

:: 配置程序名称（自动从当前可执行文件名获取）
set "APP_NAME={APP_NAME}"

:: 强制关闭所有现有的程序实例
taskkill /F /IM %APP_NAME% >nul 2>&1
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *{APP_TITLE}*" >nul 2>&1
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq *{APP_TITLE}*" >nul 2>&1

:: 检查是否还有残留进程
tasklist | findstr /i "%APP_NAME% python.exe pythonw.exe" >nul
if %errorlevel% equ 0 (
    taskkill /F /IM %APP_NAME% /T >nul 2>&1
)

:: 切换到data目录的上一层目录
cd /d "%~dp0.."

:: 启动新的程序实例（仅打包环境）
:: 设置PYINSTALLER_RESET_ENVIRONMENT=1，确保新进程作为独立实例启动
:: PyInstaller 6.10.0+ 要求重启时设置此变量，否则新进程会被误判为子进程
set PYINSTALLER_RESET_ENVIRONMENT=1

if exist "%CD%\%APP_NAME%" (
    start "" /b "%CD%\%APP_NAME%"
)

:: 执行完毕后自动删除当前批处理脚本
start /b cmd /c "del "%0" >nul 2>&1"

exit /b 0'''

def get_environment():
    """获取当前运行环境"""
    return "windows"

def _close_all_webview_windows():
    """使用 Windows API 关闭所有属于当前进程的可见窗口
    
    通过 ctypes 调用 user32.dll 的 EnumWindows/PostMessageW 实现，
    避免 import webview 触发 WebView2 安全验证失败。
    """
    try:
        # Windows 消息常量
        WM_CLOSE = 0x0010
        
        # 获取当前进程ID
        current_pid = os.getpid()
        
        # 定义回调函数类型
        WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        
        # 加载 user32.dll
        user32 = ctypes.windll.user32
        
        # 记录关闭的窗口数
        closed_count = [0]  # 使用列表以便在闭包中修改
        
        def enum_callback(hwnd, lparam):
            """枚举窗口回调：找到属于当前进程的可见窗口并发送 WM_CLOSE"""
            # 获取窗口所属进程ID
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            
            if pid.value == current_pid:
                # 只关闭可见窗口（跳过隐藏的消息窗口等）
                if user32.IsWindowVisible(hwnd):
                    window_title = ctypes.create_unicode_buffer(256)
                    user32.GetWindowTextW(hwnd, window_title, 256)
                    title = window_title.value.strip()
                    
                    # 发送 WM_CLOSE 消息优雅关闭窗口
                    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
                    closed_count[0] += 1
                    logging.info(f"已发送关闭消息到窗口: hwnd={hwnd}, title='{title}'")
            return True  # 继续枚举
        
        callback = WNDENUMPROC(enum_callback)
        user32.EnumWindows(callback, 0)
        
        if closed_count[0] > 0:
            logging.info(f"已向 {closed_count[0]} 个窗口发送关闭消息，等待窗口关闭...")
            time.sleep(1)  # 给窗口关闭足够的时间
        else:
            logging.info("未找到需要关闭的窗口（可能已关闭或无可见窗口）")
            
    except Exception as e:
        logging.warning(f"通过 Windows API 关闭窗口失败: {str(e)}，将依赖进程终止自动关闭窗口")

def _ensure_batch_script_exists():
    """确保批处理脚本存在于data目录（仅处理打包环境）
    
    动态从当前可执行文件名获取APP_NAME，避免硬编码导致重命名后重启失效。
    每次调用都会更新脚本内容，确保APP_NAME与当前exe文件名一致。
    """
    try:
        # 确定打包环境下的应用目录
        app_dir = os.path.dirname(sys.executable)
        
        # data文件夹路径
        data_dir = os.path.join(app_dir, 'data')
        
        # 确保data目录存在
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            logging.info(f"创建data目录: {data_dir}")
        
        # 批处理脚本路径
        batch_script_path = os.path.join(data_dir, 'auto_restart_app.bat')
        
        # 从当前可执行文件路径动态获取程序名称
        app_name = os.path.basename(sys.executable)
        # 获取程序标题（去掉.exe后缀，用于窗口标题匹配）
        app_title = os.path.splitext(app_name)[0]
        
        # 替换模板中的占位符为实际值
        script_content = batch_script_template.replace('{APP_NAME}', app_name)
        script_content = script_content.replace('{APP_TITLE}', app_title)
        
        # 每次都更新脚本内容，确保APP_NAME与当前exe文件名一致
        # 这样即使exe被重命名，重启时也能使用正确的新名称
        with open(batch_script_path, 'w', encoding='mbcs') as f:
            f.write(script_content)
        logging.info(f"已更新批处理脚本: {batch_script_path} | APP_NAME={app_name}")
        
        return batch_script_path
    except Exception as e:
        logging.error(f"确保脚本存在失败: {str(e)}")
        return None

def reload_service():
    """后端服务重载函数，自动判断环境并执行相应的重启逻辑"""
    def _reload_development():
        """开发环境重启逻辑"""
        try:
            current_pid = os.getpid()
            env_type = get_environment()
            
            # 获取DEBUG状态
            is_debug = False
            config_name = "development"

            logging.info(
                f"准备开发环境重载 | "
                f"进程ID: {current_pid} | "
                f"环境类型: {env_type} | "
                f"配置环境: {config_name} | "
                f"调试模式(DEBUG): {is_debug}"
            )
            
            # 开发环境重启命令
            restart_cmd = [sys.executable] + sys.argv
            
            # 开发环境参数处理
            if '--no-reload' in restart_cmd:
                restart_cmd.remove('--no-reload')
            if 'development' not in restart_cmd and '--config=development' not in restart_cmd:
                restart_cmd.append('--config=development')
            
            # 清除Werkzeug调试器环境变量
            if 'WERKZEUG_RUN_MAIN' in os.environ:
                del os.environ['WERKZEUG_RUN_MAIN']
                
            logging.info(f"开发环境重启命令: {restart_cmd}")
            
            # 关闭所有WebView窗口
            _close_all_webview_windows()
            
            # 启动新的开发环境进程
            new_process = subprocess.Popen(restart_cmd)
            logging.info(f"新开发进程已启动 | 进程ID: {new_process.pid}")
            
            # 开发环境等待时间
            wait_time = 2
            
            # 检查新进程稳定性
            process_stable = False
            for i in range(wait_time * 10):
                if new_process.poll() is not None:
                    logging.warning(
                        f"新开发进程意外终止 | "
                        f"退出码: {new_process.returncode} | "
                        f"取消当前进程({current_pid})终止"
                    )
                    return
                
                if i == wait_time * 10 - 1:
                    process_stable = True
                    break
                    
                time.sleep(0.1)
            
            if not process_stable:
                logging.warning("新开发进程未稳定启动，取消当前进程终止")
                return
            
            # 开发环境进程终止逻辑
            logging.info(f"开发模式下终止旧进程 | 进程ID: {current_pid}")
            try:
                # 先尝试优雅终止
                os.kill(current_pid, 15)  # SIGTERM
                
                # 等待短暂时间检查是否终止
                graceful_wait = 1
                for _ in range(graceful_wait * 10):
                    try:
                        os.kill(current_pid, 0)  # 检查进程是否存在
                        time.sleep(0.1)
                    except OSError:
                        logging.info(f"开发模式进程已优雅终止 | 进程ID: {current_pid}")
                        return
                
                # 优雅终止失败，尝试强制终止
                logging.info(f"开发模式进程优雅终止失败，尝试强制终止 | 进程ID: {current_pid}")
                os.kill(current_pid, 9)  # SIGKILL
            except Exception as e:
                logging.error(f"开发模式进程终止失败: {str(e)}")
                # 备选方案：使用taskkill
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(current_pid)], shell=True, check=False)
                    logging.info(f"已尝试通过taskkill终止进程 | 进程ID: {current_pid}")
                except Exception as e:
                    logging.error(f"无法通过taskkill终止进程: {str(e)}")
                
                time.sleep(0.5)
                
        except Exception as e:
            logging.error(f"开发环境服务重载失败: {str(e)}", exc_info=True)

    def _reload_packaged():
        """打包环境重启逻辑"""
        try:
            current_pid = os.getpid()
            logging.info(f"准备触发自动重启 | 当前进程ID: {current_pid}")

            # 确保批处理脚本存在
            script_path = _ensure_batch_script_exists()
            
            if not script_path:
                logging.error("无法确保批处理脚本存在，重启失败")
                return
            
            logging.info(f"使用批处理脚本路径: {script_path}")
            
            # 尝试关闭WebView窗口
            try:
                _close_all_webview_windows()
                time.sleep(0.5)  # 给窗口关闭一点时间
            except Exception as e:
                logging.warning(f"关闭WebView窗口过程出错: {str(e)}")
            
            # 直接使用Python内置的方式隐藏窗口启动批处理（仅Windows系统）
            if os.name == 'nt':
                try:
                    # 使用subprocess.STARTUPINFO隐藏CMD窗口
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    
                    subprocess.Popen(
                        ['cmd.exe', '/c', script_path],
                        shell=False,
                        close_fds=True,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        startupinfo=startupinfo
                    )
                except Exception as e:
                    logging.error(f"启动批处理脚本失败: {str(e)}")
            
            logging.info("正在退出当前进程...")
            
            # 立即强制退出当前进程
            os._exit(0)
        except Exception as e:
            logging.error(f"调用重启脚本失败: {str(e)}", exc_info=True)
    
    def _trigger_restart():
        """根据环境类型触发相应的重启逻辑"""
        # 判断是否为打包环境
        is_frozen = getattr(sys, 'frozen', False)
        
        if is_frozen:
            logging.info("检测到打包环境，使用批处理脚本进行重启")
            _reload_packaged()
        else:
            logging.info("检测到开发环境，使用开发模式重启")
            _reload_development()
    
    # 使用非守护线程执行重启
    threading.Thread(target=_trigger_restart, daemon=False).start()
    logging.info("已触发服务重启流程")
