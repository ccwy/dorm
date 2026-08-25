import os
import sys
import subprocess
import threading
import time
import logging
import webview

# 确保webview模块正确导入
if not hasattr(webview, 'windows'):
    webview.windows = []

# 批处理脚本内容模板 - 打包环境使用，包含自动删除功能
batch_script_template = '''@echo off
setlocal enabledelayedexpansion

:: 动态获取exe文件名（避免硬编码，适应打包后文件名变化）
set "APP_DIR=%~dp0.."
cd /d "%APP_DIR%"
for %%I in (*.exe) do (
    set "APP_NAME=%%~nxI"
    goto :found_exe
)
echo [ERROR] 未找到exe文件
exit /b 1

:found_exe

:: 强制关闭所有现有的程序实例
taskkill /F /IM %APP_NAME% >nul 2>&1

:: 检查是否还有残留进程
tasklist | findstr /i "%APP_NAME% python.exe pythonw.exe" >nul
if %errorlevel% equ 0 (
    taskkill /F /IM %APP_NAME% /T >nul 2>&1
)

:: 等待端口释放
timeout /t 3 /nobreak >nul 2>&1

:: 切换到data目录的上一层目录
cd /d "%~dp0.."

:: 启动新的程序实例（仅打包环境）
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
    """专门关闭所有WebView窗口的函数"""
    try:
        logging.info("准备关闭所有WebView窗口")
        if hasattr(webview, 'windows') and webview.windows:
            logging.info(f"找到{len(webview.windows)}个WebView窗口，开始关闭")
            for window in webview.windows:
                try:
                    window.destroy()
                    logging.info(f"成功关闭一个WebView窗口")
                except Exception as e:
                    logging.warning(f"关闭WebView窗口失败: {str(e)}")
        else:
            logging.info("没有找到WebView窗口")
        time.sleep(1)  # 给窗口关闭足够的时间
    except Exception as e:
        logging.error(f"关闭WebView窗口过程出错: {str(e)}")

def _ensure_batch_script_exists():
    """确保批处理脚本存在于data目录（仅处理打包环境）"""
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
        
        # 检查批处理脚本是否存在，如果不存在则创建
        if not os.path.exists(batch_script_path):
            # 使用ANSI编码保存批处理文件
            with open(batch_script_path, 'w', encoding='mbcs') as f:
                f.write(batch_script_template)
            logging.info(f"已创建批处理脚本: {batch_script_path}")
        
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
