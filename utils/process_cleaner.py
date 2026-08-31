import os
import sys
import signal
import atexit
import psutil
import logging
import threading
import time
import os


class ProcessCleaner:
    def __init__(self, app=None, server_thread=None):
        """初始化进程清理器，平衡清理彻底性和无报错"""
        self.main_pid = os.getpid()
        self.app = app
        self.server_thread = server_thread
        self.registered = False
        self.cleanup_count = 0  # 记录清理次数
        self.max_cleanup_attempts = 2  # 最多允许2次清理尝试，避免重复执行
        self.cleanup_lock = threading.Lock()
        self.processed_pids = set()
        self.exit_called = False  # 跟踪是否已调用过sys.exit

    def set_resources(self, app=None, server_thread=None):
        """更新资源引用"""
        if app:
            self.app = app
        if server_thread:
            self.server_thread = server_thread

    def cleanup_database_connections(self):
        """清理数据库连接"""
        if not self.app:
            logging.warning("未提供Flask应用实例，跳过数据库连接清理")
            return

        try:
            with self.app.app_context():
                from utils.db import db
                db.session.remove()
                db.engine.dispose()
                if hasattr(db.engine, 'pool'):
                    db.engine.pool.dispose()
            logging.info("数据库连接已清理")
        except Exception as e:
            logging.error(f"数据库连接清理失败: {str(e)}")

    def terminate_child_processes(self):
        """终止所有子进程（终极增强版：更可靠、更彻底的进程终止策略）"""
        try:
            # 检查主进程是否存在
            try:
                current_process = psutil.Process(self.main_pid)
                # 确保主进程确实是当前进程的父进程或自身
                if current_process.pid != os.getpid() and current_process.pid not in [p.pid for p in psutil.Process().parents()]:
                    logging.warning(f"警告：进程{self.main_pid}不是当前进程的父进程")
            except psutil.NoSuchProcess:
                logging.warning(f"进程{self.main_pid}不存在，无法获取子进程")
                return
            
            # 获取所有子进程
            children = current_process.children(recursive=True)
            
            if not children:
                logging.info("没有检测到子进程需要终止")
                return
                
            logging.info(f"发现{len(children)}个子进程，开始终止流程")
            
            # 记录需要终止的进程，避免在迭代过程中修改列表
            processes_to_terminate = []
            for child in children:
                try:
                    # 只处理正在运行的进程，且不是当前进程自身
                    if child.is_running() and child.pid != os.getpid():
                        # 记录进程信息以便日志记录
                        process_name = child.name()
                        processes_to_terminate.append((child, process_name))
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    logging.warning(f"无法访问进程{child.pid}: {str(e)}")
            
            if not processes_to_terminate:
                logging.info("没有活跃的子进程需要终止")
                return
            
            logging.info(f"准备终止{len(processes_to_terminate)}个活跃子进程")
            
            # 第一轮：尝试优雅终止（SIGTERM）
            logging.info("尝试优雅终止子进程")
            for child, process_name in processes_to_terminate:
                try:
                    if child.pid not in self.processed_pids:
                        # 再次检查进程是否仍在运行
                        if child.is_running():
                            logging.info(f"尝试优雅终止子进程: {child.pid} - {process_name}")
                            child.terminate()
                            logging.info("强制终止子进程")
                            os._exit(0)
                        else:
                            self.processed_pids.add(child.pid)
                            logging.info(f"子进程{child.pid}({process_name})已经不再运行")
                except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                    self.processed_pids.add(child.pid)
                    logging.info(f"无法访问子进程{child.pid}({process_name}): {str(e)}")
                except Exception as e:
                    logging.warning(f"尝试终止子进程{child.pid}({process_name})失败: {str(e)}")
            
            # 最终检查 - 确保所有已知的子进程都被处理
            final_check_children = current_process.children(recursive=True)
            if final_check_children:
                logging.info(f"最终检查发现{len(final_check_children)}个子进程")
                # 清空已处理PID集合，准备最后一轮清理
                os._exit(0)
            
            logging.info("子进程终止流程完成")
        except ImportError:
            logging.error("无法导入psutil模块，无法终止子进程")
        except Exception as e:
            logging.error(f"终止子进程过程中发生错误: {str(e)}")

    def auto_logout_users(self):
        """自动退出所有登录用户的会话 - 使用多层次清理策略"""
        try:
            logging.info("开始执行自动退出登录")
            
            # 方法0: 直接调用我们增强的自动退出登录功能
            if self.app:
                try:
                    from utils.auto_logout import auto_logout_on_startup
                    # 虽然函数名是_on_startup，但它的功能已经增强为多层次清理
                    with self.app.app_context():
                        auto_logout_on_startup()
                    logging.info("已调用增强的自动退出登录功能")
                except ImportError:
                    logging.warning("无法导入增强的自动退出登录模块")
                except Exception as e:
                    logging.warning(f"调用增强的自动退出登录功能失败: {str(e)}")
            
            # 方法1: 首先尝试使用HTTP请求直接调用退出登录接口
            try:
                import requests
                import json
                
                # 获取服务器地址（从应用配置或默认值）
                server_host = 'localhost'
                server_port = 35168
                
                # 优先从应用配置获取
                if self.app:
                    server_host = self.app.config.get('SERVER_HOST', 'localhost')
                    server_port = self.app.config.get('SERVER_PORT', 35168)
                    # 如果是'0.0.0.0'，在本地环境中使用'localhost'替代
                    if server_host == '0.0.0.0':
                        server_host = 'localhost'
                
                server_url = f"http://{server_host}:{server_port}"
                
                logout_url = f"{server_url}/login/logout"
                logging.info(f"尝试通过HTTP请求调用退出登录接口: {logout_url}")
                
                # 创建一个session对象来管理cookie
                session = requests.Session()
                
                # 发送GET请求到退出登录接口，使用session对象自动管理cookie
                response = session.get(logout_url, timeout=5)
                response.raise_for_status()  # 如果状态码不是200，抛出异常
                
                logging.info(f"自动退出登录成功，HTTP状态码: {response.status_code}")
            except requests.exceptions.RequestException as e:
                logging.warning(f"HTTP请求方式退出登录失败: {str(e)}")
            except ImportError:
                logging.warning("未安装requests库，无法使用HTTP请求方式退出登录")
            
            # 方法2: 如果HTTP请求失败，回退到在应用上下文中设置强制重新登录标志
            if self.app:
                try:
                    with self.app.app_context():
                        # 设置强制重新登录标志
                        self.app.config['FORCE_RELOGIN'] = True
                        logging.info("已设置强制重新登录标志")
                        
                        # 记录应用级别的cookie名称以便前端清理
                        if hasattr(self.app, 'session_cookie_name'):
                            session_cookie = self.app.session_cookie_name
                            if session_cookie:
                                logging.info(f"记录会话cookie名称: {session_cookie}")
                        
                        if hasattr(self.app, 'remember_cookie_name'):
                            remember_cookie = self.app.remember_cookie_name
                            if remember_cookie:
                                logging.info(f"记录remember cookie名称: {remember_cookie}")
                        
                        logging.info("已在应用上下文中设置强制重新登录标志")
                except Exception as e:
                    logging.error(f"在应用上下文中设置强制重新登录标志失败: {str(e)}")
            else:
                logging.warning("未提供Flask应用实例，无法执行应用上下文内的操作")
        except Exception as e:
            logging.error(f"自动退出登录过程中发生错误: {str(e)}")

    def cleanup_all_resources(self, signal_received=None, frame=None):
        """终极增强版：确保彻底终止所有进程，解决窗口关闭后进程残留问题"""
        with self.cleanup_lock:
            # 限制最大清理次数，避免无限循环
            if self.cleanup_count >= self.max_cleanup_attempts:
                logging.warning("已达到最大清理尝试次数，停止清理")
                # 最后强制退出
                if not self.exit_called:
                    self.exit_called = True
                    logging.warning("多次清理失败，最后强制退出程序")
                    os._exit(0)  # 使用os._exit而不是sys.exit，确保立即退出
                return False

            self.cleanup_count += 1
            logging.info(f"第 {self.cleanup_count} 次收到退出信号 {signal_received}，开始清理...")

            # 1. 尝试自动退出所有用户登录会话
            try:
                self.auto_logout_users()
            except Exception as e:
                logging.error(f"自动退出登录失败: {str(e)}")

            # 2. 清理数据库连接
            try:
                self.cleanup_database_connections()
            except Exception as e:
                logging.error(f"数据库连接清理失败: {str(e)}")

            # 3. 终止服务器线程（终极增强版：分阶段强制终止）
            if self.server_thread and self.server_thread.is_alive():
                logging.info("尝试终止服务器线程...")
                try:
                    # 尝试优雅终止
                    self.terminate_child_processes()
                    self.server_thread.join(timeout=2)

                    if self.server_thread.is_alive():
                        logging.error("服务器线程未能正常终止")
                        logging.info("已使用os._exit强制退出")
                        os._exit(0)
                        
                except Exception as e:
                    logging.error(f"终止服务器线程时出错: {str(e)}")

            # 确保程序能够完全退出，对于信号触发的清理，使用os._exit确保立即退出
            if not self.exit_called:
                self.exit_called = True
                # 检查1: 服务器线程状态
                if self.server_thread and self.server_thread.is_alive():
                    logging.warning("服务器线程仍然存活，强制使用os._exit退出")
                    os._exit(0)
                
                # 检查2: 子进程状态
                try:
                    current_process = psutil.Process(self.main_pid)
                    remaining_children_after_exit_attempt = current_process.children(recursive=True)
                    if remaining_children_after_exit_attempt:
                        logging.warning(f"sys.exit后仍有{len(remaining_children_after_exit_attempt)}个子进程，强制退出")
                        os._exit(0)
                except:
                    # 即使检查过程中出现异常，也强制退出
                    os._exit(0)
                
                # 检查3: 清理次数限制
                if self.cleanup_count >= self.max_cleanup_attempts - 1:
                    logging.warning("达到最大清理次数，强制使用os._exit退出")
                    os._exit(0)
                
                # 最后的安全网 - 确保即使上述所有条件都不满足，也会在短暂延迟后强制退出
                try:
                    time.sleep(0.1)  # 给其他线程最后一点时间
                    logging.warning("执行最后的强制退出")
                    os._exit(0)
                except:
                    os._exit(0)
        return True

    def register_signal_handlers(self):
        """注册信号处理器"""
        if self.registered:
            return

        # 处理标准信号
        signal.signal(signal.SIGINT, self.cleanup_all_resources)
        signal.signal(signal.SIGTERM, self.cleanup_all_resources)

        # Windows系统处理
        if sys.platform == 'win32':
            try:
                import win32api
                def console_ctrl_handler(event):
                    self.cleanup_all_resources(event)
                    return True  # 告知系统信号已处理
                win32api.SetConsoleCtrlHandler(console_ctrl_handler, True)
                logging.info("已注册Windows控制台信号处理器")
            except ImportError:
                logging.warning("未安装pywin32，Windows平台特殊信号处理可能受限")
            except Exception as e:
                logging.error(f"注册Windows控制台信号处理器失败: {str(e)}")

        # 注册退出清理
        atexit.register(lambda: self.cleanup_all_resources(None))
        
        self.registered = True
        logging.info("信号处理器注册完成")
    