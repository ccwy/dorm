import os
import sys
import subprocess
import threading
import time
import logging
import signal  # 标准库


class DockerRestarter:
    """Docker环境下的服务重启器，支持生成并调用重启脚本"""
    
    def __init__(self):
        self.is_restarting = False
        self.lock = threading.Lock()  # 标准库线程锁
        # 重启脚本路径
        self.restart_script_path = '/tmp/restart_service.sh'
    
    def _generate_restart_script(self):
        """生成Docker内的自动重启脚本"""
        try:
            # 确定Python解释器路径
            python_exe = sys.executable
            
            # 获取当前工作目录
            current_dir = os.getcwd()
            
            # 获取服务器端口
            server_port = os.getenv('SERVER_PORT', '35168')
            
            # 生成重启命令
            is_debug = False
            debug_flag = '--debug' if is_debug else ''
            
            # 脚本内容 - 使用Python替代nc命令检查端口
            script_content = f'''
#!/bin/bash
set -e

# Docker服务自动重启脚本

# 环境变量
PYTHON_EXE="{python_exe}"
CURRENT_DIR="{current_dir}"
SERVER_PORT="{server_port}"
DEBUG_FLAG="{debug_flag}"

# 日志输出
log() {{
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}}

log "开始Docker服务重启流程"

# 等待当前进程终止（给5秒时间）
log "等待当前进程终止..."
sleep 5

# 检查并释放端口 - 使用Python替代nc命令
log "检查端口$SERVER_PORT是否已释放"
wait_seconds=30
interval=1
port_free=false

for ((i=0; i<wait_seconds; i++)); do
    if ! $PYTHON_EXE -c "import socket; sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM); result=sock.connect_ex(('localhost', int('$SERVER_PORT'))); sock.close(); exit(0 if result != 0 else 1)"; then
        port_free=true
        log "端口$SERVER_PORT已释放，耗时$i秒"
        break
    fi
    sleep $interval
done

if [ "$port_free" = "false" ]; then
    log "警告：端口$SERVER_PORT未在$wait_seconds秒内释放，继续尝试启动"
    
    # 尝试强制杀死占用端口的进程
    log "尝试强制杀死占用端口的进程..."
    $PYTHON_EXE -c "import os, signal, socket; \
    try: \
        sock=socket.socket(socket.AF_INET, socket.SOCK_STREAM); \
        sock.connect(('localhost', int('$SERVER_PORT'))); \
        pid = sock.getpeername(); \
        sock.close(); \
        os.kill(pid[1], signal.SIGKILL); \
        print('已杀死占用端口的进程') \
    except: \
        pass"
    sleep 2
fi

# 启动新的服务进程
log "启动新的服务进程..."
cd "$CURRENT_DIR"

# 检查当前目录下是否有main.py文件，如果有则直接运行main.py
if [ -f "main.py" ]; then
    log "使用main.py作为启动入口"
    if [ -n "$DEBUG_FLAG" ]; then
        nohup "$PYTHON_EXE" main.py --debug > /tmp/dorm_management.log 2>&1 &
    else
        nohup "$PYTHON_EXE" main.py > /tmp/dorm_management.log 2>&1 &
    fi
else
    # 回退到flask run方式
    log "使用flask run作为启动入口"
    if [ -n "$DEBUG_FLAG" ]; then
        nohup "$PYTHON_EXE" -m flask run --host=0.0.0.0 --port="$SERVER_PORT" --debug > /tmp/dorm_management.log 2>&1 &
    else
        nohup "$PYTHON_EXE" -m flask run --host=0.0.0.0 --port="$SERVER_PORT" > /tmp/dorm_management.log 2>&1 &
    fi
fi

new_pid=$!
log "新服务进程已启动，PID: $new_pid，日志文件: /tmp/dorm_management.log"

# 清理脚本自身
sleep 2  # 确保脚本执行完成后再清理
log "重启脚本执行完毕，自动清理"
rm -f "$0"

exit 0
'''
            
            # 写入脚本文件
            with open(self.restart_script_path, 'w') as f:
                f.write(script_content)
            
            # 给脚本添加执行权限
            os.chmod(self.restart_script_path, 0o777)  # 更高的执行权限
            
            logging.info(f"已生成Docker重启脚本: {self.restart_script_path}")
            return True
        except Exception as e:
            logging.error(f"生成重启脚本失败: {str(e)}")
            return False
    
    def _check_docker_env(self):
        """检查是否在Docker环境中"""
        return os.getenv('DOCKER_ENV', 'false').lower() == 'true' or os.path.exists('/.dockerenv')
    
    def _trigger_restart_script(self):
        """触发重启脚本执行"""
        try:
            # 检查是否在Docker环境
            if not self._check_docker_env():
                logging.error("非Docker环境，不执行重启脚本")
                return False
            
            # 生成重启脚本
            if not self._generate_restart_script():
                logging.error("生成重启脚本失败，无法继续")
                return False
            
            # 执行重启脚本
            logging.info("开始执行Docker重启脚本...")
            subprocess.Popen(
                ['/bin/bash', self.restart_script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setpgrp
            )
            
            logging.info("重启脚本已触发执行")
            return True
        except Exception as e:
            logging.error(f"触发重启脚本失败: {str(e)}")
            return False
    
    def _restart_logic(self):
        """核心重启逻辑"""
        with self.lock:
            if self.is_restarting:
                logging.info("重启已在进行中，忽略重复调用")
                return
            self.is_restarting = True
    
        try:
            # 环境判断
            if not self._check_docker_env():
                logging.error("非Docker环境，不执行重启")
                self.is_restarting = False
                return
    
            current_pid = os.getpid()
            server_port = int(os.getenv('SERVER_PORT', '35168'))
            logging.info(f"重启流程：进程[{current_pid}]，端口[{server_port}]")
    
            # 触发重启脚本
            if self._trigger_restart_script():
                # 终止当前进程 - 修改为更安全的终止逻辑
                logging.info(f"给新进程启动时间，然后优雅终止当前进程[{current_pid}]")
                
                # 等待一小段时间让重启脚本有机会启动
                time.sleep(3)
                
                try:
                    # 先尝试获取父进程ID
                    ppid = os.getppid()
                    # 如果父进程不是1号进程（init进程），可能是在容器中由其他进程启动的
                    if ppid != 1:
                        logging.info(f"向父进程[{ppid}]发送终止信号")
                        os.kill(ppid, signal.SIGTERM)
                    else:
                        logging.info(f"向当前进程[{current_pid}]发送终止信号")
                        os.kill(current_pid, signal.SIGTERM)
                    
                    # 等待2秒后强制终止
                    time.sleep(2)
                    # 再次检查进程是否存在并尝试强制终止
                    try:
                        os.kill(current_pid, 0)  # 检查进程是否存在
                        os.kill(current_pid, signal.SIGKILL)
                    except OSError:
                        pass
                except OSError as e:
                    logging.warning(f"终止进程失败（可能已退出）: {e}")
    
        except Exception as e:
            logging.error(f"重启失败: {str(e)}")
        finally:
            # 确保重置状态
            self.is_restarting = False

# 全局实例
restarter = DockerRestarter()

# 蓝图层调用入口（与原始接口完全一致）
def reload_service(delay=0):
    """蓝图层调用入口，触发Docker环境下的服务重启
    
    Args:
        delay: 重启前的延迟秒数（Docker环境下忽略此参数，因为需要手动重启）
    """
    if delay > 0:
        logging.info(f"Docker环境下忽略重启延迟参数(delay={delay})，需要手动重启")
    threading.Thread(target=restarter._restart_logic, daemon=True).start()
    logging.info("Docker服务重启流程已触发")
