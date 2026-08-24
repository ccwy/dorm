from flask import request, jsonify, current_app
from flask_login import login_required, current_user
from utils.db import db, init_db  # 导入init_db用于数据库初始化
from sqlalchemy import text
import time
import logging
from .system_settings import system_config_bp  # 系统配置蓝图

# 用于防重复执行的标记（内存级，适用于单进程部署）
db_initializing = False
last_initialize_time = 0


@system_config_bp.route('/api/db/initialize', methods=['POST'])
@login_required
def initialize_database():
    # 检查是否为超级管理员
    if not (current_user.is_authenticated and current_user.is_super_admin()):
        logging.warning(f"非超级管理员用户 {current_user.username} 尝试初始化数据库")
        return jsonify({
            "success": False,
            "message": "无权限执行此操作，只有超级管理员可以初始化数据库"
        }), 403
        
    global db_initializing, last_initialize_time
    try:
        # 清除会话（强制重新登录）
        from flask_login import logout_user
        logout_user()
        logging.info("已清除登录信息，用户已退出登录")

        # 防重复执行：30秒内不允许重复请求
        current_time = time.time()
        if db_initializing or (current_time - last_initialize_time < 30):
            logging.warning("数据库初始化操作重复请求，30秒内不允许重复执行")
            return jsonify({
                "success": False,
                "message": "数据库初始化操作正在执行中，请稍后再试"
            }), 429

        # 标记为正在执行
        db_initializing = True
        last_initialize_time = current_time
        request_id = str(time.time()).split('.')[0]  # 生成简易请求ID用于日志追踪
        logging.info(f"[请求ID: {request_id}] 开始执行数据库重置")
        
        data = request.get_json(silent=True) or {}
        force_clear = data.get('force_clear', False)
        if not isinstance(force_clear, bool):
            logging.warning(f"[请求ID: {request_id}] force_clear参数无效，默认值false")
            return jsonify({"success": False, "message": "force_clear必须是true/false"}), 400
        
        if force_clear:
            # 获取数据库类型
            dialect = db.engine.dialect.name  # 'mysql' 或 'sqlite'
            db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
            
            if dialect == 'mysql':
                # MySQL逻辑：直接删除并重建数据库
                logging.info(f"[请求ID: {request_id}] 检测到MySQL，执行数据库删除重建流程")
                
                # 1. 解析数据库配置（从连接字符串）
                from utils.db import _parse_mysql_config_from_uri  # 复用已有的解析函数
                mysql_config = _parse_mysql_config_from_uri(db_uri)
                if not mysql_config:
                    raise Exception(f"[请求ID: {request_id}] 无法解析MySQL连接配置")
                
                # 2. 关闭当前数据库连接
                db.session.remove()
                db.engine.dispose()
                logging.info(f"[请求ID: {request_id}] 已关闭现有数据库连接")
                
                # 3. 连接到MySQL服务器（不指定数据库）并删除目标数据库
                try:
                    import pymysql  # 延迟导入，仅MySQL操作时需要
                    conn = pymysql.connect(
                        host=mysql_config['host'],
                        port=mysql_config['port'],
                        user=mysql_config['user'],
                        password=mysql_config['password'],
                        charset='utf8mb4',
                        autocommit=True,
                        connect_timeout=10
                    )
                    logging.info(f"[请求ID: {request_id}] 成功连接到MySQL服务器")

                    with conn.cursor() as cursor:
                        # 强制删除数据库
                        drop_sql = f"DROP DATABASE IF EXISTS `{mysql_config['dbname']}`"
                        logging.info(f"[请求ID: {request_id}] 执行: {drop_sql}")
                        cursor.execute(drop_sql)
                    
                    conn.close()
                    logging.info(f"[请求ID: {request_id}] 数据库 {mysql_config['dbname']} 已删除")
                except Exception as e:
                    raise Exception(f"[请求ID: {request_id}] 删除数据库失败: {str(e)}")
                
                # 4. 调用init_db重建数据库和表结构（复用已有逻辑）
                init_result = init_db(current_app, force_recreate=True)
                if not init_result:
                    raise Exception(f"[请求ID: {request_id}] 重建数据库结构失败")

            else:
                # SQLite逻辑保持不变（删除表后重建）
                logging.info(f"[请求ID: {request_id}] 检测到SQLite，执行表删除重建流程")
                
                # 获取所有表名
                tables = db.session.execute(text("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name NOT LIKE 'sqlite_%'
                """)).fetchall()
                
                unique_table_names = list(dict.fromkeys(t[0] for t in tables))
                logging.info(f"[请求ID: {request_id}] 检测到{len(unique_table_names)}张表，开始删除")

                if unique_table_names:
                    # 禁用外键约束
                    db.session.execute(text("PRAGMA foreign_keys = OFF;"))
                    db.session.commit()
                    
                    # 删除所有表
                    for table in reversed(unique_table_names):
                        db.session.execute(text(f"DROP TABLE IF EXISTS {table};"))
                        db.session.commit()
                        logging.info(f"[请求ID: {request_id}] 删除表: {table}")

                    # 恢复外键约束
                    db.session.execute(text("PRAGMA foreign_keys = ON;"))
                    db.session.commit()
                    logging.info(f"[请求ID: {request_id}] 所有旧表删除完成")

                # 重建表结构
                init_db(current_app, force_recreate=True)
                logging.info(f"[请求ID: {request_id}] SQLite表结构重建完成")

            

        # 重置执行标记
        db_initializing = False
        logging.info(f"[请求ID: {request_id}] 数据库重置流程正常结束")
        return jsonify({
            "success": True,
            "message": "数据库重置成功，请重新登录"
        })
    except Exception as e:
        db.session.rollback()
        db_initializing = False  # 异常时也要重置标记
        error_msg = str(e)
        logging.error(f"[请求ID: {request_id}] 重置失败: {error_msg}")
        return jsonify({"success": False, "message": error_msg}), 500
    