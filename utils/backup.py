from flask import current_app
import os
import time
import logging
import threading  # 新增：导入线程模块用于锁机制
from datetime import datetime, date
import re
import traceback
from utils.db import db
from utils.db_config import DatabaseConfig  # 新增：导入DatabaseConfig类

# 全局备份锁（确保进程内唯一）
backup_lock = threading.Lock()
# 线程标识（确保只启动一个备份线程）
backup_thread_ident = None

# 添加新类：DatabaseBackupManager（整合从system_config.py移动过来的功能）
class DatabaseBackupManager:
    """数据库备份管理器，提供备份、恢复和删除功能"""
    
    @classmethod
    def _auto_detect_db_type(cls):
        """
        从数据库连接URI自动检测数据库类型
        返回 'MYSQL' 或 'SQLITE'
        """
        # 从Flask配置获取实际使用的数据库连接URI
        db_uri = DatabaseConfig.get_db_uri()
        
        if 'mysql' in db_uri:
            return 'MYSQL'
        elif 'sqlite' in db_uri:
            return 'SQLITE'
        else:
            # 未知类型，抛出异常让调用者处理
            raise ValueError(f"无法识别的数据库类型，连接字符串: {db_uri}")

    @classmethod
    def _get_mysql_config(cls):
        """从配置或连接字符串解析MySQL参数"""
        db_uri = DatabaseConfig.get_db_uri()
        
        # 优先从连接字符串解析
        if 'mysql' in db_uri:
            # 格式: mysql+pymysql://user:pass@host:port/dbname
            parts = db_uri.split('://')[1].split('/')
            auth_part = parts[0].split('@')
            user_pass = auth_part[0].split(':')
            host_port = auth_part[1].split(':') if len(auth_part) > 1 else ['localhost', 3306]
            
            return {
                'host': host_port[0] if len(host_port) > 0 else 'localhost',
                'port': int(host_port[1]) if len(host_port) > 1 else 3306,
                'user': user_pass[0] if len(user_pass) > 0 else '',
                'password': user_pass[1] if len(user_pass) > 1 else '',
                'dbname': parts[1].split('?')[0] if len(parts) > 1 else ''
            }
        
        # 从配置获取备选 - 修改为从JSON文件获取
        config_data = DatabaseConfig.load_config()
        return {
            'host': config_data.get('MYSQL_HOST', 'localhost'),
            'port': int(config_data.get('MYSQL_PORT', 3306)),
            'user': config_data.get('MYSQL_USER', ''),
            'password': config_data.get('MYSQL_PASSWORD', ''),
            'dbname': config_data.get('MYSQL_DB', '')
        }

    @classmethod
    def _get_sqlite_path(cls):
        """获取SQLite数据库实际路径"""
        db_uri = DatabaseConfig.get_db_uri()
        
        if 'sqlite' in db_uri:
            # 处理sqlite:/// 或 sqlite://// 格式
            if db_uri.startswith('sqlite:///'):
                db_path = db_uri[10:]
                # 相对路径转为绝对路径
                if not os.path.isabs(db_path) and current_app:
                    db_path = os.path.join(current_app.root_path, db_path)
                return db_path
        
        # 从配置获取备选 - 修改为从JSON文件获取
        config_data = DatabaseConfig.load_config()
        config_path = config_data.get('SQLITE_DB_PATH', '')
        if config_path and not os.path.isabs(config_path) and current_app:
            return os.path.join(current_app.root_path, config_path)
        return config_path

    @classmethod
    def create_database_backup(cls):
        """
        创建数据库备份（自动检测类型，纯Python实现）
        :return: 备份成功返回备份内容，失败返回None
        """
        try:
            # 自动检测数据库类型
            try:
                db_type = cls._auto_detect_db_type()
            except ValueError as e:
                logging.error(f"数据库类型检测失败: {str(e)}")
                return None
                
            logging.info(f"自动检测到数据库类型: {db_type}")
            
            if db_type == 'SQLITE':
                # SQLite备份逻辑
                db_path = cls._get_sqlite_path()
                
                if not db_path or not os.path.exists(db_path):
                    logging.error(f"SQLite数据库文件不存在: {db_path}")
                    return None
                    
                # 关闭数据库连接再备份（避免文件锁定）
                db.session.remove()
                db.engine.dispose()
                
                # 读取数据库文件内容
                with open(db_path, 'rb') as f:
                    backup_content = f.read()
                    
                if backup_content:
                    logging.info(f"SQLite数据库备份成功，内容大小: {len(backup_content)} bytes")
                    return backup_content
                else:
                    logging.error("SQLite备份内容为空")
                    return None
                    
            elif db_type == 'MYSQL':
                # MySQL备份逻辑
                import pymysql  # 延迟导入，SQLite模式下不需要加载pymysql
                mysql_config = cls._get_mysql_config()
                
                try:
                    # 连接数据库
                    conn = pymysql.connect(
                        host=mysql_config['host'],
                        port=mysql_config['port'],
                        user=mysql_config['user'],
                        password=mysql_config['password'],
                        charset='utf8mb4',
                        cursorclass=pymysql.cursors.DictCursor
                    )
                    logging.info(f"成功连接到MySQL服务器: {mysql_config['host']}:{mysql_config['port']}")

                    backup_content = []
                    # 写入备份头部信息
                    backup_content.append(f"-- MySQL自动备份文件\n")
                    backup_content.append(f"-- 备份时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    backup_content.append(f"-- 数据库: {mysql_config['dbname']}\n\n")
                    
                    with conn.cursor() as cursor:
                        # 切换到目标数据库
                        cursor.execute(f"USE `{mysql_config['dbname']}`")
                        
                        # 备份表结构和数据
                        cursor.execute("SHOW TABLES")
                        tables = [item[f'Tables_in_{mysql_config["dbname"]}'] for item in cursor.fetchall()]
                        logging.info(f"发现{len(tables)}个表需要备份")

                        for table in tables:
                            # 备份表结构
                            cursor.execute(f"SHOW CREATE TABLE `{table}`")
                            create_result = cursor.fetchone()
                            create_sql = create_result['Create Table']
                            
                            backup_content.append(f"-- 表结构: {table}\n")
                            backup_content.append(f"DROP TABLE IF EXISTS `{table}`;\n")
                            backup_content.append(f"{create_sql};\n\n")
                            
                            # 备份表数据（分批处理）
                            cursor.execute(f"SELECT COUNT(*) AS cnt FROM `{table}`")
                            total_rows = cursor.fetchone()['cnt']
                            logging.info(f"备份表 {table}，共 {total_rows} 行数据")

                            if total_rows > 0:
                                batch_size = 1000
                                offset = 0
                                backup_content.append(f"-- 表数据: {table}\n")
                                
                                while offset < total_rows:
                                    cursor.execute(f"SELECT * FROM `{table}` LIMIT {batch_size} OFFSET {offset}")
                                    rows = cursor.fetchall()
                                    if not rows:
                                        break
                                        
                                    # 获取列名
                                    columns = [desc[0] for desc in cursor.description]
                                    column_str = ', '.join([f'`{col}`' for col in columns])
                                    
                                    # 生成INSERT语句
                                    values_list = []
                                    for row in rows:
                                        values = []
                                        for col in columns:
                                            value = row[col]
                                            if value is None:
                                                values.append('NULL')
                                            # 处理日期时间类型
                                            elif isinstance(value, (datetime, date)):
                                                values.append(f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'")
                                            elif isinstance(value, (int, float)):
                                                values.append(str(value))
                                            else:
                                                # 字符串转义
                                                escaped = str(value).replace("'", "''").replace('"', '""')
                                                values.append(f"'{escaped}'")
                                        values_str = ', '.join(values)
                                        values_list.append(f"({values_str})")
                                        
                                    # 添加数据
                                    backup_content.append(f"INSERT INTO `{table}` ({column_str}) VALUES\n")
                                    backup_content.append(',\n'.join(values_list) + ";\n\n")
                                    offset += batch_size

                    # 合并备份内容
                    backup_content_str = ''.join(backup_content)
                    logging.info(f"MySQL数据库备份成功，内容大小: {len(backup_content_str)} bytes")
                    return backup_content_str

                except pymysql.MySQLError as e:
                    logging.error(f"MySQL操作错误: {e.args[0]} - {e.args[1]}")
                    return None
                except Exception as e:
                    logging.error(f"MySQL备份过程出错: {str(e)}")
                    return None
                finally:
                    if 'conn' in locals() and conn.open:
                        conn.close()
                    
            else:
                logging.error(f"不支持的数据库类型: {db_type}")
                return None
                
        except Exception as e:
            logging.error(f"创建数据库备份失败: {str(e)}", exc_info=True)
            return None
    
    
    @classmethod
    def restore_database_backup(cls, backup_content, db_type=None):
        """恢复数据库备份（增加外键约束临时禁用）
        :param backup_content: 备份内容（二进制或字符串）
        :param db_type: 数据库类型（可选，自动检测）
        :return: 恢复成功返回True，失败返回False
        """
        try:
            # 自动检测数据库类型
            if not db_type:
                try:
                    db_type = cls._auto_detect_db_type()
                except ValueError as e:
                    logging.error(f"数据库类型检测失败: {str(e)}")
                    return False
       
            logging.info(f"数据库类型: {db_type}, 开始恢复备份")
            
            # 关闭当前数据库连接
            db.session.remove()
            db.engine.dispose()
            
            if db_type == 'SQLITE':
                # SQLite恢复逻辑
                db_path = cls._get_sqlite_path()
                if not db_path:
                    logging.error("无法解析SQLite数据库路径")
                    return False
                    
                os.makedirs(os.path.dirname(db_path), exist_ok=True)
                
                # 写入数据库文件
                try:
                    if isinstance(backup_content, bytes):
                        with open(db_path, 'wb') as f:
                            f.write(backup_content)
                    else:
                        # 处理字符串类型的备份内容
                        with open(db_path, 'wb') as f:
                            f.write(backup_content.encode('utf-8'))
                except Exception as e:
                    logging.error(f"写入SQLite数据库文件失败: {str(e)}")
                    return False
                    
                if os.path.exists(db_path) and os.path.getsize(db_path) > 0:
                    logging.info(f"SQLite数据库恢复成功")
                    db.engine.dispose()
                    return True
                else:
                    logging.error("SQLite恢复失败")
                    return False
                    
            elif db_type == 'MYSQL':
                # MySQL恢复逻辑（增加外键约束处理）
                import pymysql  # 延迟导入，SQLite模式下不需要加载pymysql
                mysql_config = cls._get_mysql_config()
                if not mysql_config:
                    logging.error("无法解析MySQL配置参数")
                    return False

                db_name = mysql_config['dbname']
                conn = None
                try:
                    conn = pymysql.connect(
                        host=mysql_config['host'],
                        port=mysql_config['port'],
                        user=mysql_config['user'],
                        password=mysql_config['password'],
                        charset='utf8mb4',
                        autocommit=True,
                        connect_timeout=30
                    )
                    logging.info(f"成功连接到MySQL服务器")

                    with conn.cursor() as cursor:
                        # 重建数据库
                        cursor.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
                        cursor.execute(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                        cursor.execute(f"USE `{db_name}`")
                        
                        # 临时禁用多种约束检查
                        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                        cursor.execute("SET UNIQUE_CHECKS = 0")
                        cursor.execute("SET SQL_MODE = 'NO_ENGINE_SUBSTITUTION'")
                        logging.info("已临时禁用外键约束和唯一约束检查")

                        # 解析SQL命令
                        def sql_command_generator():
                            buffer = []
                            in_comment = False
                            in_string = None
                              
                            # 确保内容是字符串
                            if isinstance(backup_content, bytes):
                                content = backup_content.decode('utf-8')
                            else:
                                content = backup_content
                                  
                            for line_num, line in enumerate(content.split('\n'), 1):
                                line = line.rstrip('\n')
                                if '/*' in line:
                                    in_comment = True
                                if '*/' in line:
                                    in_comment = False
                                    line = line.split('*/', 1)[1]
                                if in_comment or line.strip().startswith('--'):
                                    continue
                                      
                                for char in line:
                                    if char in ["'", '"']:
                                        if in_string == char:
                                            in_string = None
                                        elif in_string is None:
                                            in_string = char
                                          
                                buffer.append(line)
                                if ';' in line and in_string is None:
                                    cmd = ' '.join(buffer).strip()
                                    cmd = re.sub(r'\s+', ' ', cmd)
                                    if cmd:
                                        yield cmd, line_num
                                    buffer = []
                            # 只在处理完所有行后检查剩余的buffer
                            if buffer:
                                cmd = ' '.join(buffer).strip()
                                if cmd:
                                    yield cmd, line_num

                        # 执行SQL命令
                        total_commands = sum(1 for _ in sql_command_generator())
                        logging.info(f"检测到 {total_commands} 条SQL命令")

                        conn.autocommit(False)
                        successful_commands = 0
                        failed_commands = 0
                        max_failures = 10  # 允许的最大失败命令数
                        constraint_check_interval = 50  # 重新禁用约束的间隔命令数

                        for cmd, line_num in sql_command_generator():
                            try:
                                # 在每次执行命令前都禁用约束
                                cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                                cursor.execute("SET UNIQUE_CHECKS = 0")
                                logging.debug(f"执行命令前已禁用约束，当前已执行 {successful_commands} 条命令")
                                cursor.execute(cmd)
                                successful_commands += 1
                                # 每执行100条命令提交一次
                                if successful_commands % 100 == 0:
                                    conn.commit()
                                    logging.info(f"已成功执行 {successful_commands} 条命令")
                                    # 提交后重新禁用约束
                                    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
                                    cursor.execute("SET UNIQUE_CHECKS = 0")
                                    logging.debug(f"提交后已重新禁用约束")
                            except pymysql.MySQLError as e:
                                # 记录错误但继续执行
                                failed_commands += 1
                                logging.error(f"SQL执行失败（行号{line_num}）: {e.args[0]} - {e.args[1]}")
                                logging.error(f"出错命令: {cmd[:200]}...")
                                 
                                # 如果失败次数过多，则终止恢复
                                if failed_commands > max_failures:
                                    conn.rollback()
                                    logging.error(f"超过最大失败命令数({max_failures})，恢复终止")
                                    return False
                            except Exception as e:
                                failed_commands += 1
                                logging.error(f"执行SQL命令时发生未知错误（行号{line_num}）: {str(e)}")
                                if failed_commands > max_failures:
                                    conn.rollback()
                                    logging.error(f"超过最大失败命令数({max_failures})，恢复终止")
                                    return False

                        # 恢复所有约束检查
                        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
                        cursor.execute("SET UNIQUE_CHECKS = 1")
                        cursor.execute("SET SQL_MODE = 'STRICT_TRANS_TABLES,NO_ENGINE_SUBSTITUTION'")
                        conn.commit()
                        logging.info(f"MySQL恢复完成，已恢复所有约束检查")
                        return True

                except Exception as e:
                    logging.error(f"MySQL恢复失败: {str(e)}")
                    logging.error(traceback.format_exc())
                    return False
                finally:
                    if conn and conn.open:
                        conn.close()
                    db.engine.dispose()
                    
            else:
                logging.error(f"不支持的数据库类型: {db_type}")
                return False
                
        except Exception as e:
            logging.error(f"恢复数据库备份失败: {str(e)}", exc_info=True)
            return False

    @classmethod
    def delete_backup_file(cls, filename):
        """
        删除指定的备份文件
        :param filename: 备份文件名
        :return: 删除成功返回True，否则返回False
        """
        try:
            # 获取备份目录
            backup_dir = current_app.config.get('BACKUP_DIR')
            
            if not backup_dir:
                logging.error("未配置备份目录，无法删除备份文件")
                return False
            
            file_path = os.path.join(backup_dir, filename)
            
            # 验证文件名是否为备份文件，统一检查逻辑
            if not os.path.exists(file_path) or not (filename.startswith('BACKUP_') or filename.startswith('backup_')):
                logging.error(f"备份文件不存在或不合法: {filename}")
                return False
            
            os.remove(file_path)
            logging.info(f"备份文件 {filename} 已成功删除")
            return True
        except Exception as e:
            logging.error(f"删除备份文件 {filename} 失败: {str(e)}")
            return False

def backup_database(trigger_source="auto"):  # 新增：触发源参数，用于日志区分
    """备份数据库，支持多种数据库类型"""
    # 新增：使用锁机制确保同一时间只有一个备份进程
    global backup_lock
    if not backup_lock.acquire(blocking=False):
        logging.warning(f"检测到正在进行的备份进程，{trigger_source}触发的备份将跳过")
        return

    try:
        # 获取备份目录
        backup_dir = current_app.config.get('BACKUP_DIR')
        logging.info(f"[{trigger_source}] 备份目录: {backup_dir}")
        
        # 确保备份目录存在
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
            logging.info(f"[{trigger_source}] 已创建备份目录: {backup_dir}")
            
        # 使用DatabaseBackupManager的create_database_backup方法创建备份
        logging.info(f"[{trigger_source}] 开始执行数据库备份")
        backup_content = DatabaseBackupManager.create_database_backup()
        
        if backup_content:
            # 生成备份文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            # 自动检测数据库类型以命名备份文件
            try:
                db_type = DatabaseBackupManager._auto_detect_db_type()
                backup_filename = f"BACKUP_{db_type}_AUTO_{timestamp}.sql"
            except:
                backup_filename = f"BACKUP_{timestamp}.sql"
            
            backup_path = os.path.join(backup_dir, backup_filename)
            
            # 在蓝图层处理文件保存逻辑
            try:
                if isinstance(backup_content, bytes):
                    # SQLite备份内容为二进制
                    logging.info(f"SQLite备份内容长度: {len(backup_content)}")
                    with open(backup_path, 'wb') as f:
                        f.write(backup_content)
                else:
                    # MySQL备份内容为字符串
                    logging.info(f"MySQL备份内容长度: {len(backup_content)}")
                    with open(backup_path, 'w', encoding='utf-8') as f:
                        f.write(backup_content)
            except Exception as e:
                logging.error(f"保存备份文件失败: {str(e)}")
                raise Exception(f"保存备份文件失败: {str(e)}")
            
            logging.info(f"[{trigger_source}] 数据库备份成功: {backup_path}")
            
            # 清理旧备份
            clean_old_backups()
        else:
            logging.error(f"[{trigger_source}] 备份内容为空，备份失败")
    except Exception as e:
        logging.error(f"[{trigger_source}] 备份失败: {str(e)}")
        print(f"[{trigger_source}] 备份失败: {str(e)}")
    finally:
        # 新增：释放锁
        backup_lock.release()

def clean_old_backups():
    """清理旧备份，根据配置保留指定数量的备份"""
    try:
        # 获取备份目录 - 使用current_app获取配置，与现有代码风格保持一致
        backup_dir = current_app.config.get('BACKUP_DIR')  
        logging.info(f"开始清理旧备份，目录: {backup_dir}")
        
        if not os.path.exists(backup_dir):
            logging.warning(f"备份目录不存在: {backup_dir}")
            return
            
        backup_files = []
        for f in os.listdir(backup_dir):
            db_type = DatabaseBackupManager._auto_detect_db_type()
            if f.startswith('BACKUP_') and db_type in f and f.endswith('.sql'):
                backup_files.append(f)
        
        backup_files.sort()
        logging.info(f"找到 {len(backup_files)} 个备份文件")

        config_data = DatabaseConfig.load_config()
        max_backups = config_data.get('BACKUP_RETENTION_COUNT', 100)
        logging.info(f"配置的最大保留备份数: {max_backups}")
        
        files_to_delete = len(backup_files) - max_backups
        if files_to_delete > 0:
            logging.info(f"需要删除 {files_to_delete} 个旧备份文件")
            for i in range(files_to_delete):
                file_path = os.path.join(backup_dir, backup_files[i])
                try:
                    os.remove(file_path)
                    logging.info(f"已删除过期备份: {file_path}")
                except OSError as e:
                    logging.error(f"处理备份文件时出错 {file_path}: {str(e)}")
        else:
            logging.info(f"当前备份数量({len(backup_files)})未超过最大保留数({max_backups})，无需删除")
    except Exception as e:
        logging.error(f"清理旧备份失败: {str(e)}")

def auto_backup(app):
    """自动备份线程，确保全局唯一且按间隔执行"""
    global backup_thread_ident
    # 检查是否已有备份线程在运行，确保唯一性
    if backup_thread_ident is not None:
        logging.warning(f"检测到已有备份线程（ID: {backup_thread_ident}），当前线程退出")
        return

    with app.app_context():
        # 记录当前线程ID，标记为活跃
        backup_thread_ident = threading.get_ident()
        logging.info(f"自动备份线程启动，唯一标识ID: {backup_thread_ident}")
        
        last_enable_state = None
        # 记录上次备份时间，避免状态变更时立即执行
        last_backup_time = 0
        
        while True:
            try:
                # 读取最新配置
                config_data = DatabaseConfig.load_config()
                enable_auto_backup = config_data.get('ENABLE_AUTO_BACKUP', False)  #从本地配置文件获取是否开启自动备份
                interval = config_data.get('BACKUP_INTERVAL', 1200) * 60 #从本地配置文件获取更新间隔，最小时间间隔1分钟，单位：分钟
                interval = int(interval) if str(interval).isdigit() else 86400
                interval = max(interval, 60)  # 最小间隔60秒，防止频繁执行
                
                # 状态变更处理：从禁用→启用时，不立即备份，等待一个间隔后再执行
                if enable_auto_backup != last_enable_state:
                    logging.info(f"自动备份状态变更: {last_enable_state} -> {enable_auto_backup}")
                    last_enable_state = enable_auto_backup
                    # 状态变为启用时，重置上次备份时间，确保按间隔执行
                    if enable_auto_backup:
                        last_backup_time = time.time()
                        logging.info(f"自动备份已启用，将在{interval}秒后执行首次备份")
                
                # 仅当启用且距离上次备份超过间隔时间时，才执行备份
                if enable_auto_backup:
                    current_time = time.time()
                    if current_time - last_backup_time >= interval:
                        logging.info(f"达到备份间隔（{interval}秒），准备执行自动备份")
                        backup_database(trigger_source="auto")
                        last_backup_time = current_time  # 更新上次备份时间
                    #else:
                        #remaining = int((interval - (current_time - last_backup_time)))
                       # logging.info(f"未达到备份间隔，剩余{remaining}秒")
                #else:
                    #logging.info("自动备份已禁用，跳过本次检查")
                
                # 休眠60秒后再次检查（而非直接休眠interval，确保配置变更能及时响应）
                time.sleep(60)
                
            except Exception as e:
                logging.error(f"自动备份循环错误: {str(e)}", exc_info=True)
                time.sleep(300)
            finally:
                # 线程退出时清除标识
                if not threading.main_thread().is_alive():
                    backup_thread_ident = None
                    logging.info("主程序退出，自动备份线程终止")
                    break
