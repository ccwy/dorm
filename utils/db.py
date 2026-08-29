
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.pool import StaticPool
from sqlalchemy import event
from flask import Flask
import traceback
import logging
from flask import current_app

# 全局数据库实例
db = SQLAlchemy()
_is_initialized = False

def create_admin_user():
    """创建初始超级管理员"""
    from models.user import User 
    admin = User.query.filter_by(role='超级管理员').first()
    if not admin:
        admin = User(
            student_id='SUPERADMIN001',
            name='系统超级管理员',
            gender='男',
            category='管理员',
            username='admin',
            role='超级管理员',
            status='在职',
            is_active=True,
            is_banned=True
        )
        admin.set_password('123456')
        db.session.add(admin)
        
        try:
            db.session.commit()
            logging.info("初始超级管理员账号创建成功")
        except Exception as e:
            db.session.rollback()
            logging.error(f"创建超级管理员账号失败: {str(e)}")

def init_system_configs():
    """初始化系统配置"""
    from models.system_config import SystemConfig
    SystemConfig.init_default_configs()
    logging.info("已初始化系统配置")

def set_sqlite_pragma(dbapi_connection, connection_record):
    """SQLite启用外键约束"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

def set_mysql_charset(dbapi_connection, connection_record):
    """MySQL设置字符集"""
    cursor = dbapi_connection.cursor()
    cursor.execute("SET NAMES utf8mb4")
    cursor.close()

def register_db_listeners():
    """注册数据库监听器"""
    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if 'sqlite' in db_uri:
        current_app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            'poolclass': StaticPool,  # 使用静态连接池
            'connect_args': {'check_same_thread': False}  # 允许跨线程使用连接
        }
        @event.listens_for(db.engine, 'connect')
        def handle_connect(dbapi_connection, connection_record):
            logging.debug("获取数据库连接")
            set_sqlite_pragma(dbapi_connection, connection_record)
            
    elif 'mysql' in db_uri:
        @event.listens_for(db.engine, 'connect')
        def handle_connect(dbapi_connection, connection_record):
            set_mysql_charset(dbapi_connection, connection_record)
    
def _parse_mysql_config_from_uri(db_uri):
    """从连接字符串中解析MySQL配置（避免依赖USE_MYSQL）"""
    import re
    # 匹配mysql+pymysql://user:pass@host:port/dbname
    pattern = r'mysql\+pymysql://(\w+):(.*)@([\w\.\-]+):?(\d*)/(\w+)\??.*'
    match = re.match(pattern, db_uri)
    if not match:
        return None
    
    return {
        'user': match.group(1),
        'password': match.group(2),
        'host': match.group(3),
        'port': int(match.group(4)) if match.group(4) else 3306,
        'dbname': match.group(5)
    }

def _force_create_mysql_database(app, db_uri):
    """根据连接字符串创建数据库（完全不依赖USE_MYSQL）"""
    import pymysql  # 延迟导入，SQLite模式下不需要加载pymysql
    # 从URI解析配置
    config = _parse_mysql_config_from_uri(db_uri)
    if not config:
        logging.error(f"无法解析MySQL连接字符串: {db_uri}")
        return False
    
    db_host = config['host']
    db_port = config['port']
    db_name = config['dbname']
    db_user = config['user']
    db_password = config['password']
    
    logging.info(
        f"【强制创建数据库】从连接字符串解析到参数: "
        f"host={db_host}, port={db_port}, user={db_user}, dbname={db_name}"
    )
    
    try:
        # 连接到MySQL服务器（不指定数据库）
        conn = pymysql.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            charset='utf8mb4',
            connect_timeout=10,
            autocommit=True
        )
        logging.info(f"成功连接到MySQL服务器: {db_host}:{db_port}")
        
        with conn.cursor() as cursor:
            # 检查数据库是否存在
            cursor.execute(f"SHOW DATABASES LIKE '{db_name}'")
            if cursor.fetchone():
                logging.info(f"数据库 '{db_name}' 已存在")
                conn.close()
                return True
            
            # 创建数据库
            logging.info(f"开始创建数据库 '{db_name}'...")
            cursor.execute(
                f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            
            # 验证创建结果
            cursor.execute(f"SHOW DATABASES LIKE '{db_name}'")
            if cursor.fetchone():
                logging.info(f"数据库 '{db_name}' 创建成功")
                conn.close()
                return True
            else:
                logging.error(f"创建后未找到数据库 '{db_name}'")
                conn.close()
                return False
                
    except pymysql.MySQLError as e:
        error_code, error_msg = e.args
        logging.error(f"MySQL操作失败 (代码: {error_code}): {error_msg}")
        return False
    except Exception as e:
        logging.error(f"创建数据库时发生未知错误: {str(e)}")
        logging.error(traceback.format_exc())
        return False

def init_db(app: Flask, force_recreate=False):
    """初始化数据库（完全基于连接字符串判断数据库类型）"""
    global _is_initialized
    
    if not _is_initialized or force_recreate:
        # 1. 获取连接字符串
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI')
        if not db_uri:
            logging.error("数据库连接字符串未配置")
            return None
        
        logging.info(f"使用的数据库连接: {db_uri}")
        
        # 2. 强制判断是否为MySQL，直接执行创建逻辑（不依赖USE_MYSQL）
        mysql_db_created = True
        if 'mysql' in db_uri:
            logging.info("检测到MySQL连接字符串，执行数据库创建逻辑...")
            mysql_db_created = _force_create_mysql_database(app, db_uri)
            if not mysql_db_created:
                logging.error("数据库创建失败，终止初始化")
                return None
        
        # 3. 绑定ORM到应用
        if not _is_initialized:
            db.init_app(app)
            logging.info("SQLAlchemy已绑定到应用")

        # 4. 根据数据库类型设置引擎选项
        with app.app_context():
            register_db_listeners()
            logging.info("已注册数据库监听器并设置引擎选项")
        
        # 5. 在应用上下文内创建表结构
        with app.app_context():
            
            # 导入所有模型
            import models.user
            import models.room
            import models.room_bed
            import models.dorm
            import models.log
            import models.utility_room_meter
            import models.system_config
            import models.utility_room_bill_record
            import models.utility_room_bill_occupant
            import models.utility_room_bill_checkout
            import models.fee_subsidy
            import models.fee_subsidy_usage
            import models.room_facility  # 房间设施模型
            import models.ticket  # 留言模型
            import models.ticket_reply  # 留言回复模型
            import models.todo  # 待办事项模型
            import models.todo_progress  # 待办事项进度记录模型
            import models.chat_session  # 聊天会话模型
            import models.chat_participant  # 聊天参与者模型
            import models.chat_message  # 聊天消息模型
            import models.department  # 部门管理模型
            import models.fixed_asset  # 固定资产模型
            import models.asset_inventory  # 盘点主表模型
            import models.asset_inventory_detail  # 盘点明细模型
            import models.asset_operation_record  # 资产操作记录模型

            # 低值易耗品进销存管理模型
            import models.supply.supplier
            import models.supply.supplier_operation_record
            import models.supply.supply_item
            import models.supply.storage_location
            import models.supply.supply_stock_detail
            import models.supply.stock_in
            import models.supply.stock_in_detail
            import models.supply.stock_out
            import models.supply.stock_out_detail
            import models.supply.supply_inventory
            import models.supply.supply_inventory_detail
            import models.supply.supply_stock_record

            # 创建表结构
            if force_recreate or not _is_initialized:
                logging.info("开始创建数据表结构...")
                db.create_all()
                logging.info("数据表结构创建完成")

                # 初始化管理员和配置，数据库监听器内已有初始化
                create_admin_user()               
                init_system_configs()

            if not _is_initialized:
                _is_initialized = True
                logging.info("数据库初始化完成（首次执行）")
            else:
                logging.info("数据库表结构重建完成（强制模式）")
    return db
    