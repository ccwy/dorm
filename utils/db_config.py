
import json
import os
import sqlite3
from flask import current_app
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError
import sys
import base64  # 添加base64模块导入
from utils.system_detector import is_win7

# 检查是否在Docker环境中
is_docker = os.environ.get('DOCKER_ENV') == 'true'

# 确定配置文件路径
if is_docker:
    # Docker环境 - 使用简化的外部数据卷路径
    DB_CONFIG_PATH = '/data/db_config.json'
else:
    # 非Docker环境
    if getattr(sys, 'frozen', False):
        # 打包环境
        app_dir = os.path.dirname(sys.executable)
        DB_CONFIG_PATH = os.path.join(app_dir, 'data', 'db_config.json')
    else:
        # 开发环境
        current_file_dir = os.path.abspath(os.path.dirname(__file__))
        app_dir = os.path.abspath(os.path.join(current_file_dir, os.pardir))
        DB_CONFIG_PATH = os.path.join(app_dir, 'data', 'db_config.json')

class DatabaseConfig:
    # 配置缓存，避免启动期间重复读取文件和解码
    _config_cache = None
    _config_cache_mtime = None  # 文件修改时间，用于检测配置变更
    
    @staticmethod
    def initialize():
        """初始化配置文件（如果不存在）"""
        if not os.path.exists(DB_CONFIG_PATH):
            # 检查是否在Docker环境中
            is_docker = os.environ.get('DOCKER_ENV') == 'true'
            
            if is_docker:
                # Docker环境 - 使用简化的外部数据卷路径
                sqlite_db_path = '/data/data.db'
            else:
                # 获取应用程序目录
                if getattr(sys, 'frozen', False):
                    # 打包环境
                    app_dir = os.path.dirname(sys.executable)
                else:
                    # 开发环境
                    current_file_dir = os.path.abspath(os.path.dirname(__file__))
                    app_dir = os.path.abspath(os.path.join(current_file_dir, os.pardir))
                
                # sqlite数据库文件始终存储在应用目录下的data文件夹
                data_dir = os.path.join(app_dir, 'data')
                
                # 确定数据库文件路径
                sqlite_db_path = os.path.join(data_dir, 'data.db')
            
            # 默认配置
            default_config = {
                "SQL_TYPE": "SQLITE",                       # 数据库类型，支持MySQL和sqlite
                "SQLITE_DB_PATH": sqlite_db_path,           # sqlite 路径
                "MYSQL_HOST": "192.168.5.100",              # MySQL 主机地址
                "MYSQL_PORT": 3306,                         # MySQL 主机端口
                "MYSQL_DB": "test",                         # MySQL 数据库名称
                "MYSQL_USER": "test",                       # MySQL 数据库账号
                "MYSQL_PASSWORD": "123456",                 # MySQL 数据库密码
                "LAST_FAILED_MYSQL_ATTEMPT": None,          # 记录最后一次MySQL连接失败时间
                "AUTO_SWITCHED_TO_SQLITE": False,           # 标记是否是自动切换到SQLite
                "SERVER_PORT": 35168,                       # 服务器端口
                "BACKUP_RETENTION_COUNT": 100,              # 备份数量
                "BACKUP_INTERVAL": 1440,                    # 自动备份间隔（分钟）
                "ENABLE_AUTO_BACKUP": True,                 # 是否开启自动备份
                'ENABLE_CUSTOM_METER_READING_DAY': False,   # 水自定义抄表日期配置（新增默认值）
                'CUSTOM_METER_READING_DAY': 1,              # 自定义抄表日期
                "SERVER_MODE": "服务端" if is_win7() else "客户端",  # 启动模式（Win7默认服务端，否则默认客户端）
                "SYSTEM_TITLE": "行政后勤管理系统"                # 系统标题   
            }
            
            # SQLite目录初始化 - 先检查再创建
            if default_config["SQL_TYPE"] == "SQLITE":
                db_dir = os.path.dirname(default_config["SQLITE_DB_PATH"])
                if not os.path.exists(db_dir):
                    try:
                        os.makedirs(db_dir, exist_ok=True)
                        logging.info(f"初始化创建SQLite目录: {db_dir}")
                    except OSError as e:
                        logging.error(f"创建SQLite目录失败: {str(e)}")
            DatabaseConfig.save_config(default_config)
            return default_config
        return DatabaseConfig.load_config()
    
    @staticmethod
    def load_config():
        """加载配置文件（带缓存，避免重复读取文件和解码）"""
        try:
            # 检查缓存是否有效（文件未修改时使用缓存）
            if DatabaseConfig._config_cache is not None and os.path.exists(DB_CONFIG_PATH):
                current_mtime = os.path.getmtime(DB_CONFIG_PATH)
                if DatabaseConfig._config_cache_mtime == current_mtime:
                    return DatabaseConfig._config_cache.copy()
            
            if not os.path.exists(DB_CONFIG_PATH):
                config = DatabaseConfig.initialize()
                DatabaseConfig._update_cache(config)
                return config
                
            with open(DB_CONFIG_PATH, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                
            # 直接使用base64解码
            decoded_content = base64.b64decode(content).decode('utf-8')
            config = json.loads(decoded_content)
            DatabaseConfig._update_cache(config)
            return config
        except Exception as e:
            if current_app:
                logging.error(f"加载数据库配置文件失败: {str(e)}")
            config = DatabaseConfig.initialize()
            DatabaseConfig._update_cache(config)
            return config
    
    @staticmethod
    def _update_cache(config):
        """更新配置缓存"""
        DatabaseConfig._config_cache = config.copy()
        if os.path.exists(DB_CONFIG_PATH):
            DatabaseConfig._config_cache_mtime = os.path.getmtime(DB_CONFIG_PATH)
    
    @staticmethod
    def invalidate_cache():
        """使缓存失效（配置变更时调用）"""
        DatabaseConfig._config_cache = None
        DatabaseConfig._config_cache_mtime = None
    
    @staticmethod
    def save_config(config_data):
        """保存配置到文件"""
        try:
            # 确保配置文件目录存在
            dir_path = os.path.dirname(DB_CONFIG_PATH)
            if not os.path.exists(dir_path):
                os.makedirs(dir_path)
                
            # 将配置转换为JSON字符串并使用base64编码
            json_str = json.dumps(config_data, ensure_ascii=False, indent=4)
            encoded_str = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
            
            with open(DB_CONFIG_PATH, 'w', encoding='utf-8') as f:
                f.write(encoded_str)
            # 保存后使缓存失效，下次读取时重新加载
            DatabaseConfig.invalidate_cache()
            return True
        except Exception as e:
            if current_app:
                logging.error(f"保存数据库配置文件失败: {str(e)}")
            return False
    
    @staticmethod
    def update_config(config_updates):
        """更新部分配置"""
        current_config = DatabaseConfig.load_config()
        current_config.update(config_updates)
        return DatabaseConfig.save_config(current_config)
    
    @staticmethod
    def test_mysql_connection(config=None):
        """
        精确判定MySQL连接状态：
        - 致命错误（无法修复）：返回False（触发切换）
        - 可修复错误（如数据库不存在）：返回True（继续执行）
        """
        if not config:
            config = DatabaseConfig.load_config()
            
        try:
            # 尝试建立基础连接并执行验证查询（设置3秒连接超时，避免长时间阻塞）
            connect_timeout = config.get('MYSQL_CONNECT_TIMEOUT', 3)
            engine = create_engine(
                DatabaseConfig._get_mysql_uri(config),
                connect_args={"connect_timeout": connect_timeout}
            )
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))  # 仅验证连接有效性，不依赖任何表
                conn.commit()
                return True, "MySQL连接成功"
                
        except OperationalError as e:
            error_str = str(e)
            # 定义致命错误类型（这些错误无法通过后续流程修复，必须切换）
            fatal_errors = [
                "Access denied",          # 权限错误（用户名/密码错误）
                "Can't connect to MySQL server",  # 主机不可达/端口错误
                "Unknown MySQL server host",      # 主机名错误
                "Connection refused",     # 连接被拒绝（端口占用或服务未启动）
                "Timeout",                # 连接超时（网络问题）
                "Host 'xxx' is not allowed to connect"  # 主机访问权限受限
            ]
            
            # 检查是否为致命错误
            if any(error in error_str for error in fatal_errors):
                # 提取具体错误信息
                for error in fatal_errors:
                    if error in error_str:
                        error_msg = f"MySQL致命错误 [{error}]: {config['MYSQL_HOST']}:{config['MYSQL_PORT']}"
                        return False, error_msg
                # 未匹配到具体致命错误类型但确定是致命错误
                return False, f"MySQL连接失败: {error_str}"
            elif "Unknown database" in error_str:
                # 数据库不存在（可修复，由后续流程创建）
                return True, f"数据库不存在，将尝试创建: {config['MYSQL_DB']}"
            else:
                # 其他非致命错误（如临时网络波动）
                logging.warning(f"MySQL非致命错误: {error_str}")
                return True, "连接存在临时问题，将继续尝试"
        except SQLAlchemyError as e:
            # SQLAlchemy层面的非连接错误（不影响基础连接）
            logging.warning(f"MySQL非连接性错误: {str(e)}")
            return True, "连接成功但存在其他SQL错误"
        except Exception as e:
            # 其他未知错误（保守处理为非致命错误）
            logging.error(f"MySQL连接检测未知错误: {str(e)}")
            return True, "检测到未知错误，将继续尝试"
    
    @staticmethod
    def test_sqlite_connection(config=None):
        """测试SQLite连接（强化检查逻辑）"""
        if not config:
            config = DatabaseConfig.load_config()
            
        try:
            db_path = config.get("SQLITE_DB_PATH", "")
            if not db_path:
                return False, "SQLite路径未配置"
                
            # 目录检查 - 先判断再创建
            db_dir = os.path.dirname(db_path)
            if not os.path.exists(db_dir):
                try:
                    os.makedirs(db_dir, exist_ok=True)
                    logging.info(f"创建SQLite目录: {db_dir}")
                except OSError as e:
                    return False, f"创建SQLite目录失败: {str(e)}"
            # 检查目录可写性
            if not os.access(db_dir, os.W_OK):
                return False, f"SQLite目录不可写: {db_dir}（权限不足）"
            
            # 文件检查 - 存在性验证后再操作
            file_exists = os.path.exists(db_path)
            
            # 仅当文件存在时检查可写性
            if file_exists and not os.access(db_path, os.W_OK):
                return False, f"SQLite文件不可写: {db_path}（权限不足）"
            
            # 仅当文件不存在时尝试创建
            if not file_exists:
                try:
                    with open(db_path, 'a'):  # 'a'模式不截断已有内容，仅创建空文件
                        pass
                    logging.info(f"SQLite文件不存在，已创建: {db_path}")
                except IOError as e:
                    return False, f"创建SQLite文件失败: {str(e)}"
            
            # 验证数据库完整性
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA integrity_check")
            conn.close()
            return True, f"SQLite连接成功（文件: {db_path}）"
        except Exception as e:
            error_msg = f"SQLite连接失败: {str(e)}"
            logging.error(error_msg)
            return False, error_msg
    
    @staticmethod
    def _get_mysql_uri(config):
        """生成MySQL连接字符串（含连接超时设置，避免不可用时长时间阻塞）"""
        connect_timeout = config.get('MYSQL_CONNECT_TIMEOUT', 3)
        return f"mysql+pymysql://{config['MYSQL_USER']}:{config['MYSQL_PASSWORD']}@{config['MYSQL_HOST']}:{config['MYSQL_PORT']}/{config['MYSQL_DB']}?charset=utf8mb4&connect_timeout={connect_timeout}"
    
    @staticmethod
    def _get_sqlite_uri(config):
        """生成SQLite连接字符串"""
        return f"sqlite:///{config['SQLITE_DB_PATH']}"
    
    @staticmethod
    def get_db_uri(force_check=False):
        """
        获取数据库连接字符串，带自动故障转移
        force_check: 是否强制检查连接状态
        """
        config = DatabaseConfig.load_config()
        current_db_type = config.get("SQL_TYPE", "").upper()
        
        if current_db_type == "MYSQL" and (force_check or config.get("AUTO_SWITCHED_TO_SQLITE", False)):
            mysql_available, error_msg = DatabaseConfig.test_mysql_connection(config)
            
            # 仅当确认MySQL完全不可用（致命错误）时才切换到SQLite
            if not mysql_available:
                from datetime import datetime
                try:
                    if current_app:
                        logging.error(f"MySQL致命错误，必须切换到SQLite: {error_msg}")
                    else:
                        logging.error(f"MySQL致命错误，必须切换到SQLite: {error_msg}")
                except RuntimeError:
                    logging.error(f"MySQL致命错误，必须切换到SQLite: {error_msg}")
                
                # 更新配置并切换
                config["SQL_TYPE"] = "SQLITE"
                config["LAST_FAILED_MYSQL_ATTEMPT"] = datetime.now().isoformat()
                config["AUTO_SWITCHED_TO_SQLITE"] = True
                DatabaseConfig.save_config(config)
                return DatabaseConfig._get_sqlite_uri(config)
            else:
                # MySQL可用（包括可修复的错误），重置切换标记
                if config.get("AUTO_SWITCHED_TO_SQLITE", False):
                    config["AUTO_SWITCHED_TO_SQLITE"] = False
                    DatabaseConfig.save_config(config)
                    try:
                        if current_app:
                            logging.info("MySQL已恢复可用，切换回MySQL模式")
                        else:
                            logging.info("MySQL已恢复可用，切换回MySQL模式")
                    except RuntimeError:
                        logging.info("MySQL已恢复可用，切换回MySQL模式")
                
                # 日志提示可修复的问题
                if "数据库不存在" in error_msg or "临时问题" in error_msg:
                    try:
                        if current_app:
                            logging.warning(f"MySQL需要修复: {error_msg}")
                        else:
                            logging.warning(f"MySQL需要修复: {error_msg}")
                    except RuntimeError:
                        logging.warning(f"MySQL需要修复: {error_msg}")
        
        # 确保SQLite资源可用（切换时使用）
        if current_db_type == "SQLITE":
            db_path = config.get("SQLITE_DB_PATH", "")
            db_dir = os.path.dirname(db_path)
            
            # 目录存在性检查（不重复创建）
            if not os.path.exists(db_dir):
                try:
                    os.makedirs(db_dir, exist_ok=True)
                    logging.info(f"创建SQLite目录: {db_dir}")
                except OSError as e:
                    logging.error(f"创建SQLite目录失败: {str(e)}")
            # 目录可写性检查（提前暴露问题）
            elif not os.access(db_dir, os.W_OK):
                logging.warning(f"SQLite目录不可写: {db_dir}（可能导致写入失败）")
            
            # 仅在首次启动（数据库文件不存在）或强制检查时执行连接预验证
            # 非首次启动跳过integrity_check，避免大数据库的延迟
            db_file_exists = os.path.exists(db_path)
            if force_check or not db_file_exists:
                sqlite_available, sqlite_msg = DatabaseConfig.test_sqlite_connection(config)
                if not sqlite_available:
                    logging.error(f"SQLite初始化失败: {sqlite_msg}")
            else:
                logging.debug(f"SQLite数据库文件已存在，跳过连接预验证: {db_path}")
        
        # 返回当前配置的连接字符串（MySQL可用时继续使用）
        if current_db_type == "MYSQL":
            return DatabaseConfig._get_mysql_uri(config)
        else:
            return DatabaseConfig._get_sqlite_uri(config)
    
    @staticmethod
    def reset_auto_switch():
        """重置自动切换标记（当用户手动切换回MySQL时）"""
        config = DatabaseConfig.load_config()
        if config.get("AUTO_SWITCHED_TO_SQLITE", False):
            config["AUTO_SWITCHED_TO_SQLITE"] = False
            DatabaseConfig.save_config(config)
