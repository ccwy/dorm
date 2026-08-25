import os
import sys
import subprocess
import threading
import time
import logging

# 延迟导入webview，避免在服务端模式下也加载WebView2运行时
# 仅在客户端模式实际需要关闭WebView窗口时才导入
_webview = None

def _get_webview():
    """延迟获取webview模块，仅在需要时才导入"""
    global _webview
    if _webview is None:
        try:
            import webview as _w
            _webview = _w
            # 确保webview模块正确导入
            if not hasattr(_webview, 'windows'):
                _webview.windows = []
        except ImportError:
            logging.warning("webview模块导入失败，WebView窗口关闭功能将不可用")
    return _webview

# 批处理脚本内容模板 - 打包环境使用，包含自动删除功能
# 关键：必须确保旧进程完全退出后再启动新进程，避免WebView2安全验证失败
batch_script_template = r'''@echo off
setlocal enabledelayedexpansion

:: 配置程序名称
set "APP_NAME=宿舍管理系统.exe"

:: 第一步：强制关闭所有现有的程序实例（包括整个进程树）
taskkill /F /T /IM %APP_NAME% >nul 2>&1
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *宿舍管理系统*" >nul 2>&1
taskkill /F /IM pythonw.exe /FI "WINDOWTITLE eq *宿舍管理系统*" >nul 2>&1

:: 第二步：循环等待，确保旧进程完全退出
:: 最多等待10秒（100次 x 100毫秒），避免无限等待
set "WAIT_COUNT=0"
:wait_loop
tasklist /FI "IMAGENAME eq %APP_NAME%" 2>nul | findstr /i "%APP_NAME%" >nul
if %errorlevel% equ 0 (
    set /a WAIT_COUNT+=1
    if !WAIT_COUNT! geq 100 (
        echo 警告：旧进程未能在10秒内退出，强制终止
        taskkill /F /T /IM %APP_NAME% >nul 2>&1
        goto :wait_done
    )
    :: 进程仍存在，短暂等待后重试
    ping -n 1 127.0.0.1 >nul
    goto :wait_loop
)
:wait_done

:: 第三步：额外等待500毫秒，让操作系统完成资源清理
:: 这是关键步骤——WebView2需要父进程完全释放资源后才能正确初始化
ping -n 1 127.0.0.1 >nul

:: 计算程序所在目录（批处理脚本在data子目录下，程序在上一级目录）
:: %~dp0 是批处理脚本所在目录，带尾部反斜杠，需要去掉反斜杠再拼接
set "SCRIPT_DIR=%~dp0"
set "APP_DIR=%SCRIPT_DIR:~0,-1%\.."
:: 进入程序目录
cd /d "%APP_DIR%"

:: 第四步：启动全新的程序实例
:: 不使用/b参数，让新进程作为独立进程运行，拥有自己的进程上下文
:: 这样WebView2能正确获取自身的进程信息，避免Security validation failure错误
if exist "%CD%\%APP_NAME%" (
    start "" "%CD%\%APP_NAME%"
    :: 等待新进程启动完成（给start命令足够时间创建进程）
    ping -n 3 127.0.0.1 >nul
)

:: 执行完毕后自动删除当前批处理脚本
:: 使用独立的cmd进程删除，避免删除正在运行的脚本
start /b cmd /c "del "%0" >nul 2>&1"

exit /b 0'''

def get_environment():
    """获取当前运行环境"""
    return "windows"

def _close_all_webview_windows():
    """专门关闭所有WebView窗口的函数"""
    try:
        webview = _get_webview()
        if webview is None:
            logging.info("webview模块未加载，跳过WebView窗口关闭")
            return
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
        
        # 始终重新创建批处理脚本，确保使用最新版本
        # 使用ANSI编码保存批处理文件
        with open(batch_script_path, 'w', encoding='mbcs') as f:
            f.write(batch_script_template)
        logging.info(f"已创建/更新批处理脚本: {batch_script_path}")
        
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

            # 确保批处理脚本存在（始终重新创建，确保使用最新版本）
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
                    
                    # 使用 /c start 命令启动批处理脚本
                    # start 会让批处理脚本在新窗口中独立运行，
                    # 避免当前Python进程退出时影响批处理脚本的执行
                    subprocess.Popen(
                        'start "" /min cmd /c "' + script_path + '"',
                        shell=True,
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