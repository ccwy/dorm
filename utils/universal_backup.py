"""
通用数据库备份恢复模块
使用 JSON 作为统一备份格式，支持 SQLite ↔ MySQL 跨数据库恢复
与现有 backup.py 完全独立，不参与自动备份逻辑
"""

import json
import logging
import gzip
import io
import base64
from datetime import datetime, date
from decimal import Decimal
from flask import current_app
from utils.db import db
from utils.db_config import DatabaseConfig
from sqlalchemy import text

# ==================== 类型序列化 / 反序列化 ====================

def serialize_value(value):
    """将 Python 值序列化为 JSON 兼容格式"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return {"__type__": "datetime", "__value__": value.strftime('%Y-%m-%d %H:%M:%S')}
    if isinstance(value, date):
        return {"__type__": "date", "__value__": value.strftime('%Y-%m-%d')}
    if isinstance(value, Decimal):
        return {"__type__": "decimal", "__value__": str(value)}
    if isinstance(value, bytes):
        return {"__type__": "bytes", "__value__": base64.b64encode(value).decode('ascii')}
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value
    # 其他类型转字符串
    return str(value)


def deserialize_value(value, column_type=None):
    """从 JSON 反序列化为 Python 值"""
    if value is None:
        return None
    if isinstance(value, dict) and "__type__" in value:
        type_tag = value["__type__"]
        raw = value["__value__"]
        if type_tag == "datetime":
            return datetime.strptime(raw, '%Y-%m-%d %H:%M:%S')
        if type_tag == "date":
            return datetime.strptime(raw, '%Y-%m-%d').date()
        if type_tag == "decimal":
            return Decimal(raw)
        if type_tag == "bytes":
            return base64.b64decode(raw)
        return raw
    return value


# ==================== 模型发现与排序 ====================

def get_all_models():
    """获取所有 SQLAlchemy 模型类（继承自 db.Model）"""
    models = []
    # 遍历 db.Model 的所有子类
    for mapper in db.Model.registry.mappers:
        cls = mapper.class_
        if hasattr(cls, '__tablename__') and cls.__tablename__:
            models.append(cls)
    return models


def get_table_restore_order():
    """
    获取表的恢复顺序（按外键依赖排序，父表在前，子表在后）
    使用拓扑排序确保被依赖的表先恢复
    """
    models = get_all_models()
    
    # 构建依赖图：表名 -> 依赖的表名集合
    dependencies = {}
    table_to_model = {}
    
    for model in models:
        table_name = model.__tablename__
        table_to_model[table_name] = model
        deps = set()
        
        # 检查所有外键
        for fk in model.__table__.foreign_keys:
            referred_table = fk.column.table.name
            if referred_table != table_name:  # 排除自引用
                deps.add(referred_table)
        
        dependencies[table_name] = deps
    
    # 拓扑排序（Kahn 算法）
    in_degree = {t: 0 for t in dependencies}
    for table, deps in dependencies.items():
        for dep in deps:
            if dep in in_degree:
                in_degree[dep] = in_degree.get(dep, 0)  # 确保存在
    
    # 重新计算入度
    in_degree = {t: 0 for t in dependencies}
    for table, deps in dependencies.items():
        for dep in deps:
            if dep in in_degree:
                in_degree[table] += 1
    
    queue = [t for t in in_degree if in_degree[t] == 0]
    result = []
    
    while queue:
        queue.sort()  # 确保顺序稳定
        table = queue.pop(0)
        result.append(table)
        
        for other_table, deps in dependencies.items():
            if table in deps:
                in_degree[other_table] -= 1
                if in_degree[other_table] == 0:
                    queue.append(other_table)
    
    # 添加不在依赖图中的表（无外键的独立表）
    for table in dependencies:
        if table not in result:
            result.append(table)
    
    return result, table_to_model


# ==================== 备份管理器 ====================

class UniversalBackupManager:
    """通用备份管理器，使用 JSON 格式实现跨数据库备份恢复"""
    
    BACKUP_VERSION = "1.0"
    
    @classmethod
    def _auto_detect_db_type(cls):
        """从数据库连接URI自动检测数据库类型"""
        db_uri = DatabaseConfig.get_db_uri()
        if 'mysql' in db_uri:
            return 'MYSQL'
        elif 'sqlite' in db_uri:
            return 'SQLITE'
        else:
            raise ValueError(f"无法识别的数据库类型，连接字符串: {db_uri}")
    
    @classmethod
    def create_backup(cls):
        """
        创建通用 JSON 备份
        :return: (backup_content_str, error_message)
                 成功返回 (json_string, None)，失败返回 (None, error_msg)
        """
        try:
            db_type = cls._auto_detect_db_type()
            logging.info(f"[通用备份] 检测到数据库类型: {db_type}")
            
            models = get_all_models()
            backup = {
                "version": cls.BACKUP_VERSION,
                "export_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "source_db_type": db_type,
                "tables": {},
                "metadata": {
                    "total_tables": 0,
                    "total_rows": 0
                }
            }
            
            total_rows = 0
            
            for model in models:
                table_name = model.__tablename__
                try:
                    columns = [c.name for c in model.__table__.columns]
                    rows = []
                    
                    # 分批读取，避免内存溢出
                    batch_size = 2000
                    offset = 0
                    
                    while True:
                        results = db.session.query(model).offset(offset).limit(batch_size).all()
                        if not results:
                            break
                        
                        for row in results:
                            row_data = []
                            for col in columns:
                                value = getattr(row, col, None)
                                row_data.append(serialize_value(value))
                            rows.append(row_data)
                        
                        offset += batch_size
                    
                    backup["tables"][table_name] = {
                        "columns": columns,
                        "rows": rows,
                        "row_count": len(rows)
                    }
                    
                    total_rows += len(rows)
                    logging.info(f"[通用备份] 表 {table_name}: {len(rows)} 行")
                    
                except Exception as e:
                    logging.error(f"[通用备份] 备份表 {table_name} 失败: {str(e)}")
                    # 继续备份其他表
            
            backup["metadata"]["total_tables"] = len(backup["tables"])
            backup["metadata"]["total_rows"] = total_rows
            
            # 使用 gzip 压缩以减小文件大小
            json_str = json.dumps(backup, ensure_ascii=False, separators=(',', ':'))
            logging.info(f"[通用备份] 备份完成，共 {len(backup['tables'])} 张表，{total_rows} 行数据，JSON 大小: {len(json_str)} 字节")
            
            return json_str, None
            
        except Exception as e:
            logging.error(f"[通用备份] 创建备份失败: {str(e)}")
            return None, str(e)
    
    @classmethod
    def restore_backup(cls, backup_content):
        """
        从通用 JSON 备份恢复数据
        :param backup_content: JSON 字符串或字节
        :return: (success, error_message)
        """
        try:
            db_type = cls._auto_detect_db_type()
            logging.info(f"[通用恢复] 当前数据库类型: {db_type}")
            
            # 解析备份内容
            if isinstance(backup_content, bytes):
                # 检查 gzip 魔数 (0x1f 0x8b) 判断是否为 gzip 压缩数据
                if len(backup_content) >= 2 and backup_content[0] == 0x1f and backup_content[1] == 0x8b:
                    try:
                        backup_content = gzip.decompress(backup_content).decode('utf-8')
                        logging.info("[通用恢复] 检测到gzip压缩数据，已解压")
                    except Exception as e:
                        logging.error(f"[通用恢复] gzip解压失败: {str(e)}")
                        return False, f"gzip解压失败: {str(e)}"
                else:
                    # 非gzip数据，尝试直接UTF-8解码
                    try:
                        backup_content = backup_content.decode('utf-8')
                    except UnicodeDecodeError as e:
                        logging.error(f"[通用恢复] UTF-8解码失败: {str(e)}")
                        return False, f"文件编码无法识别: {str(e)}"
            
            backup = json.loads(backup_content)
            
            # 验证备份格式
            if "version" not in backup or "tables" not in backup:
                return False, "无效的通用备份文件格式"
            
            source_db_type = backup.get("source_db_type", "UNKNOWN")
            logging.info(f"[通用恢复] 备份来源数据库: {source_db_type}，版本: {backup.get('version')}")
            logging.info(f"[通用恢复] 备份时间: {backup.get('export_time')}")
            logging.info(f"[通用恢复] 表数量: {backup.get('metadata', {}).get('total_tables', 0)}，行数量: {backup.get('metadata', {}).get('total_rows', 0)}")
            
            # 获取恢复顺序和模型映射
            restore_order, table_to_model = get_table_restore_order()
            
            # 确保所有表结构存在（通过 SQLAlchemy create_all）
            logging.info("[通用恢复] 确保表结构存在...")
            db.create_all()
            
            # ===== 阶段1：禁用外键约束 =====
            logging.info("[通用恢复] 禁用外键约束...")
            cls._disable_foreign_keys(db_type)
            
            try:
                # ===== 阶段2：按逆序清空所有表数据（子表先删，父表后删）=====
                delete_order = list(reversed(restore_order))
                logging.info(f"[通用恢复] 清空顺序（逆序）: {delete_order[:5]}...")
                
                for table_name in delete_order:
                    if table_name not in backup["tables"]:
                        continue
                    if table_name not in table_to_model:
                        continue
                    
                    model = table_to_model[table_name]
                    try:
                        deleted = db.session.query(model).delete()
                        db.session.commit()
                        logging.info(f"[通用恢复] 已清空表 {table_name}（删除 {deleted} 行）")
                    except Exception as e:
                        db.session.rollback()
                        logging.error(f"[通用恢复] 清空表 {table_name} 失败: {str(e)}")
                        # 继续尝试其他表
                
                # ===== 阶段3：按正序恢复数据（父表先插，子表后插）=====
                restored_tables = 0
                restored_rows = 0
                failed_tables = []
                
                logging.info(f"[通用恢复] 恢复顺序（正序）: {restore_order[:5]}...")
                
                for table_name in restore_order:
                    if table_name not in backup["tables"]:
                        continue
                    
                    if table_name not in table_to_model:
                        logging.warning(f"[通用恢复] 跳过未知表 {table_name}（当前版本无对应模型）")
                        continue
                    
                    model = table_to_model[table_name]
                    table_data = backup["tables"][table_name]
                    columns = table_data["columns"]
                    rows = table_data["rows"]
                    
                    try:
                        # 批量插入
                        batch_size = 500
                        for i in range(0, len(rows), batch_size):
                            batch = rows[i:i + batch_size]
                            for row_data in batch:
                                row_dict = {}
                                for j, col in enumerate(columns):
                                    if j < len(row_data):
                                        # 获取列类型用于反序列化
                                        col_type = None
                                        try:
                                            col_obj = model.__table__.columns[col]
                                            col_type = col_obj.type
                                        except (KeyError, AttributeError):
                                            pass
                                        
                                        row_dict[col] = deserialize_value(row_data[j], col_type)
                                
                                try:
                                    instance = model(**row_dict)
                                    db.session.add(instance)
                                except Exception as row_err:
                                    logging.warning(f"[通用恢复] 表 {table_name} 插入行失败: {str(row_err)[:200]}")
                                    continue
                            
                            db.session.commit()
                        
                        restored_tables += 1
                        restored_rows += len(rows)
                        logging.info(f"[通用恢复] 表 {table_name}: 恢复 {len(rows)} 行")
                        
                    except Exception as e:
                        db.session.rollback()
                        logging.error(f"[通用恢复] 恢复表 {table_name} 失败: {str(e)}")
                        failed_tables.append(table_name)
                        continue
                
                # 处理不在恢复顺序中但存在于备份中的表
                for table_name, table_data in backup["tables"].items():
                    if table_name in failed_tables:
                        continue
                    if table_name not in restore_order and table_name in table_to_model:
                        # 已经在上面处理过了（因为 restore_order 包含了所有表）
                        pass
                    elif table_name not in table_to_model:
                        logging.warning(f"[通用恢复] 跳过备份中的表 {table_name}（当前版本无对应模型）")
                
                logging.info(f"[通用恢复] 恢复完成: {restored_tables} 张表, {restored_rows} 行数据")
                if failed_tables:
                    logging.warning(f"[通用恢复] 以下表恢复失败: {', '.join(failed_tables)}")
                
                # 恢复完成后重置自增序列（SQLite 不需要，MySQL 需要）
                if db_type == 'MYSQL':
                    try:
                        cls._reset_mysql_auto_increment(table_to_model)
                    except Exception as e:
                        logging.warning(f"[通用恢复] 重置MySQL自增序列失败（非致命）: {str(e)}")
                
            finally:
                # ===== 阶段4：重新启用外键约束 =====
                logging.info("[通用恢复] 重新启用外键约束...")
                cls._enable_foreign_keys(db_type)
            
            return True, None
            
        except json.JSONDecodeError as e:
            logging.error(f"[通用恢复] JSON 解析失败: {str(e)}")
            return False, f"JSON 解析失败: {str(e)}"
        except Exception as e:
            db.session.rollback()
            logging.error(f"[通用恢复] 恢复失败: {str(e)}")
            # 尝试重新启用外键约束
            try:
                cls._enable_foreign_keys(cls._auto_detect_db_type())
            except Exception:
                pass
            return False, str(e)
    
    @classmethod
    def _disable_foreign_keys(cls, db_type):
        """禁用外键约束（恢复时需要）"""
        try:
            if db_type == 'SQLITE':
                db.session.execute(text('PRAGMA foreign_keys=OFF'))
                db.session.commit()
                logging.info("[通用恢复] 已禁用SQLite外键约束")
            elif db_type == 'MYSQL':
                db.session.execute(text('SET FOREIGN_KEY_CHECKS=0'))
                db.session.commit()
                logging.info("[通用恢复] 已禁用MySQL外键约束")
        except Exception as e:
            logging.warning(f"[通用恢复] 禁用外键约束失败: {str(e)}")
    
    @classmethod
    def _enable_foreign_keys(cls, db_type):
        """重新启用外键约束"""
        try:
            if db_type == 'SQLITE':
                db.session.execute(text('PRAGMA foreign_keys=ON'))
                db.session.commit()
                logging.info("[通用恢复] 已重新启用SQLite外键约束")
            elif db_type == 'MYSQL':
                db.session.execute(text('SET FOREIGN_KEY_CHECKS=1'))
                db.session.commit()
                logging.info("[通用恢复] 已重新启用MySQL外键约束")
        except Exception as e:
            logging.warning(f"[通用恢复] 重新启用外键约束失败: {str(e)}")
    
    @classmethod
    def _reset_mysql_auto_increment(cls, table_to_model):
        """重置 MySQL 表的自增ID为当前最大值+1"""
        import pymysql
        mysql_config = DatabaseConfig.load_config()
        
        conn = pymysql.connect(
            host=mysql_config.get('MYSQL_HOST', 'localhost'),
            port=int(mysql_config.get('MYSQL_PORT', 3306)),
            user=mysql_config.get('MYSQL_USER', ''),
            password=mysql_config.get('MYSQL_PASSWORD', ''),
            database=mysql_config.get('MYSQL_DB', ''),
            charset='utf8mb4'
        )
        
        try:
            with conn.cursor() as cursor:
                for table_name, model in table_to_model.items():
                    # 检查表是否有自增主键
                    pk_cols = [c.name for c in model.__table__.primary_key.columns]
                    if pk_cols:
                        pk = pk_cols[0]
                        cursor.execute(
                            f"SELECT AUTO_INCREMENT FROM information_schema.TABLES "
                            f"WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
                            (table_name,)
                        )
                        result = cursor.fetchone()
                        if result and result[0] is not None:
                            cursor.execute(
                                f"SELECT MAX(`{pk}`) FROM `{table_name}`"
                            )
                            max_id_result = cursor.fetchone()
                            max_id = max_id_result[0] if max_id_result and max_id_result[0] else 0
                            new_auto_inc = max_id + 1
                            cursor.execute(
                                f"ALTER TABLE `{table_name}` AUTO_INCREMENT = %s",
                                (new_auto_inc,)
                            )
            conn.commit()
        finally:
            conn.close()
    
    @classmethod
    def get_backup_info(cls, backup_content):
        """
        获取备份文件信息（不执行恢复）
        :param backup_content: JSON 字符串或字节
        :return: (info_dict, error_message)
        """
        try:
            if isinstance(backup_content, bytes):
                # 检查 gzip 魔数 (0x1f 0x8b) 判断是否为 gzip 压缩数据
                if len(backup_content) >= 2 and backup_content[0] == 0x1f and backup_content[1] == 0x8b:
                    try:
                        backup_content = gzip.decompress(backup_content).decode('utf-8')
                        logging.info("[通用备份信息] 检测到gzip压缩数据，已解压")
                    except Exception as e:
                        logging.error(f"[通用备份信息] gzip解压失败: {str(e)}")
                        return None, f"gzip解压失败: {str(e)}"
                else:
                    # 非gzip数据，尝试直接UTF-8解码
                    try:
                        backup_content = backup_content.decode('utf-8')
                    except UnicodeDecodeError as e:
                        logging.error(f"[通用备份信息] UTF-8解码失败: {str(e)}")
                        return None, f"文件编码无法识别，请确认是有效的通用备份文件: {str(e)}"
            
            backup = json.loads(backup_content)
            
            if "version" not in backup or "tables" not in backup:
                return None, "无效的通用备份文件格式（缺少version或tables字段）"
            
            tables_info = {}
            for table_name, table_data in backup.get("tables", {}).items():
                tables_info[table_name] = {
                    "row_count": table_data.get("row_count", 0),
                    "columns": table_data.get("columns", [])
                }
            
            info = {
                "version": backup.get("version"),
                "export_time": backup.get("export_time"),
                "source_db_type": backup.get("source_db_type"),
                "total_tables": backup.get("metadata", {}).get("total_tables", 0),
                "total_rows": backup.get("metadata", {}).get("total_rows", 0),
                "tables": tables_info
            }
            
            return info, None
            
        except json.JSONDecodeError as e:
            logging.error(f"[通用备份信息] JSON解析失败: {str(e)}")
            return None, f"JSON解析失败，请确认文件是有效的通用备份格式: {str(e)}"
        except Exception as e:
            logging.error(f"[通用备份信息] 解析失败: {str(e)}")
            return None, str(e)