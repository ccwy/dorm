from flask import  request, jsonify, current_app
from flask_login import login_required, current_user
from utils.auth import require_permission
import os
import logging
from datetime import datetime 
from models.system_config import SystemConfig  # 系统配置模型
from utils.log import log_operation
from .system_settings import system_config_bp  # 系统配置蓝图
from utils.backup import DatabaseBackupManager  # 已经导入，但需要修改使用方式
from utils.db_config import DatabaseConfig  # 新增：导入DatabaseConfig类


def get_db_type_identifier():
    """获取数据库类型标识（mysql/sqlite）"""
    db_uri = current_app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if 'mysql' in db_uri:
        return 'MYSQL'
    elif 'sqlite' in db_uri:
        return 'SQLITE'
    return 'unknown'


@system_config_bp.route('/api/backup/create', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def create_backup():
    try:
        # 获取数据库类型标识
        db_type = get_db_type_identifier()
        # 从config获取备份目录配置
        backup_dir = current_app.config.get('BACKUP_DIR')
        
        # 确保备份目录存在
        if not backup_dir:
            default_dir = current_app.config.get('BACKUP_DIR')
            backup_dir = default_dir
        
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir, exist_ok=True)
        
        # 创建备份文件（使用SQL脚本格式）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"BACKUP_{db_type}_{timestamp}.sql"  # 关键修改：加入数据库类型
        backup_path = os.path.join(backup_dir, backup_filename)
        
        # 直接调用工具类中的方法
        backup_content = DatabaseBackupManager.create_database_backup()
        logging.info(f"数据库备份内容类型: {type(backup_content)}")
        
        if backup_content is None:
            logging.error("数据库备份操作失败，返回None")
            raise Exception("数据库备份操作失败")
        
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
        

        
        log_operation(
            user_id=current_user.id,
            action=f"创建{db_type}数据库备份，备份文件: {backup_filename}",
            module="system",
            operation_type="create_backup",
            result=f"成功"
        )
        logging.info(f"创建{db_type}数据库备份成功，备份文件: {backup_filename}")
        return jsonify({
            "success": True,
            "message": f"{db_type}数据库备份创建成功",
            "backup_file": backup_filename,
            "backup_time": timestamp
        })
    except Exception as e:
        logging.error(f"创建备份失败: {str(e)}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else 0,
            action=f"创建系统备份失败, {str(e)}",
            module="system.backup",
            operation_type="create_backup",
            result="失败"
        )
        return jsonify({
            "success": False,
            "message": f"创建备份失败: {str(e)}"
        }), 500

@system_config_bp.route('/api/backup/list', methods=['GET'])
@login_required
@require_permission('system_settings.manage')
def list_backups():
    try:
        # 获取当前数据库类型
        current_db_type = get_db_type_identifier()
        logging.info(f"当前数据库类型: {current_db_type}, 开始筛选备份文件")
        # 从config获取备份目录
        backup_dir = current_app.config.get('BACKUP_DIR')
        
        # 获取分页参数，默认为第1页，每页10条
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('pageSize', 10, type=int)
        
        if not backup_dir or not os.path.exists(backup_dir):
            return jsonify({
                "success": True,
                "data": [],
                "message": "备份目录不存在，暂无备份文件",
                "total": 0,
                "page": page,
                "pageSize": page_size
            })
        
        backup_files = []
        for filename in os.listdir(backup_dir):
            # 基础过滤：只处理备份文件
            if not (filename.startswith('BACKUP_') and filename.endswith('.sql')):
                continue
            
            # 核心筛选逻辑：根据当前数据库类型过滤
            if current_db_type == 'SQLITE':
                # SQLite环境：排除所有MySQL备份
                if 'MYSQL' in filename:
                    logging.debug(f"过滤MySQL备份文件: {filename}")
                    continue
            elif current_db_type == 'MYSQL':
                # MySQL环境：排除所有SQLite备份
                if 'SQLITE' in filename:
                    logging.debug(f"过滤SQLite备份文件: {filename}")
                    continue
            # 未知类型：不过滤（兼容处理）
            
            # 收集符合条件的文件信息
            file_path = os.path.join(backup_dir, filename)
            file_stats = os.stat(file_path)
            
            # 提取文件中的数据库类型（用于前端显示）
            file_db_type = "unknown"
            if 'mysql' in filename:
                file_db_type = "mysql"
            elif 'sqlite' in filename:
                file_db_type = "sqlite"
            
            backup_files.append({
                "filename": filename,
                "db_type": file_db_type,  # 增加数据库类型字段
                "size": file_stats.st_size,
                # 修复这里的datetime调用方式
                "created_at": datetime.fromtimestamp(file_stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                "path": file_path
            })
        
        # 按创建时间排序，最新的在前
        backup_files.sort(key=lambda x: x['created_at'], reverse=True)
        
        # 计算总页数和当前页数据
        total = len(backup_files)
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_files = backup_files[start_index:end_index]
        
        # 修改从本地配置文件获取BACKUP_RETENTION_COUNT值
        config_data = DatabaseConfig.load_config()
        retention_count = config_data.get('BACKUP_RETENTION_COUNT', 30)
        
        log_operation(
            user_id=current_user.id,
            action=f"获取备份文件列表，当前数据库类型: {current_db_type}, 共筛选出{total}个有效备份",
            module="system",
            operation_type="list_backups",
            result="成功"
        )
        logging.info("获取备份列表成功")
        return jsonify({
            "success": True,
            "data": paginated_files,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": (total + page_size - 1) // page_size,  # 计算总页数
            "current_db_type": current_db_type,  # 返回当前数据库类型
            "retention_count": retention_count
        })
    except Exception as e:
        logging.error(f"获取备份列表失败: {str(e)}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else 0,
            action=f"获取备份文件列表失败， {str(e)}",
            module="system",
            operation_type="list_backups",
            result="失败"
        )
        return jsonify({
            "success": False,
            "message": f"获取备份列表失败: {str(e)}"
        }), 500

@system_config_bp.route('/api/backup/delete/<filename>', methods=['DELETE'])
@login_required
@require_permission('system_settings.manage')
def delete_backup(filename):
    try:
        # 使用工具目录中的备份管理器删除文件
        success = DatabaseBackupManager.delete_backup_file(filename)
        
        if not success:
            return jsonify({
                "success": False,
                "message": "备份文件删除失败或文件不合法"
            }), 400
        
        log_operation(
            user_id=current_user.id,
            action=f"删除系统备份，删除文件: {filename}",
            module="system",
            operation_type="delete_backup",
            result="成功"
        )
        
        return jsonify({
            "success": True,
            "message": f"备份文件 {filename} 已成功删除"
        })
    except Exception as e:
        logging.error(f"删除备份失败: {str(e)}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else 0,
            action=f"删除系统备份失败: {str(e)}",
            module="system",
            operation_type="delete_backup",
            result="失败"
        )
        return jsonify({
            "success": False,
            "message": f"删除备份失败: {str(e)}"
        }), 500

@system_config_bp.route('/api/backup/delete-batch', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def delete_backup_batch():
        try:
            data = request.get_json()
            filenames = data.get('filenames', [])
            
            if not isinstance(filenames, list) or len(filenames) == 0:
                return jsonify({
                    "success": False,
                    "message": "请提供要删除的备份文件列表"
                }), 400
            
            success_count = 0
            failed_files = []
            
            for filename in filenames:
                if DatabaseBackupManager.delete_backup_file(filename):
                    success_count += 1
                else:
                    failed_files.append(filename)
            
            log_operation(
                user_id=current_user.id,
                action=f"批量删除备份文件，成功删除{success_count}个，失败{len(failed_files)}个",
                module="system",
                operation_type="delete_backup",
                result="成功" if success_count > 0 else "失败"
            )
            
            return jsonify({
                "success": True,
                "message": f"成功删除{success_count}个备份文件，{len(failed_files)}个删除失败",
                "success_count": success_count,
                "failed_files": failed_files
            })
        except Exception as e:
            logging.error(f"批量删除备份失败: {str(e)}")
            log_operation(
                user_id=current_user.id if current_user.is_authenticated else 0,
                action=f"批量删除备份失败: {str(e)}",
                module="system",
                operation_type="delete_backup",
                result="失败"
            )
            return jsonify({
                "success": False,
                "message": f"批量删除备份失败: {str(e)}"
            }), 500

@system_config_bp.route('/api/backup/clear-all', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def clear_all_backups():
        try:
            # 检查是否为超级管理员
            if not (current_user.user_role and current_user.user_role.code == 'super_admin'):
                logging.warning(f"非超级管理员用户{current_user.id}尝试清空所有备份")
                return jsonify({
                    "success": False,
                    "message": "只有超级管理员才能清空所有备份"
                }), 403
        
            # 获取所有备份文件
            backup_dir = current_app.config.get('BACKUP_DIR')
            if not backup_dir or not os.path.exists(backup_dir):
                return jsonify({
                    "success": False,
                    "message": "备份目录不存在，无法清空备份"
                }), 400
            
            backup_files = [f for f in os.listdir(backup_dir) if f.startswith('BACKUP_') and f.endswith('.sql')]
            
            if not backup_files:
                return jsonify({
                    "success": True,
                    "message": "备份目录已为空，无需清空",
                    "deleted_count": 0
                })
            
            # 批量删除所有备份文件
            deleted_count = 0
            failed_files = []
            
            for filename in backup_files:
                if DatabaseBackupManager.delete_backup_file(filename):
                    deleted_count += 1
                else:
                    failed_files.append(filename)
            
            log_operation(
                user_id=current_user.id,
                action=f"清空所有备份文件，共删除{deleted_count}个，失败{len(failed_files)}个",
                module="system",
                operation_type="delete_backup",
                result="成功" if deleted_count > 0 else "失败"
            )
            
            return jsonify({
                "success": True,
                "message": f"成功清空{deleted_count}个备份文件，{len(failed_files)}个删除失败",
                "deleted_count": deleted_count,
                "failed_files": failed_files
            })
        except Exception as e:
            logging.error(f"清空所有备份失败: {str(e)}")
            log_operation(
                user_id=current_user.id if current_user.is_authenticated else 0,
                action=f"清空所有备份失败: {str(e)}",
                module="system",
                operation_type="delete_backup",
                result="失败"
            )
            return jsonify({
                "success": False,
                "message": f"清空所有备份失败: {str(e)}"
            }), 500
    
@system_config_bp.route('/api/backup/restore/<filename>', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def restore_backup(filename):
    try:
        # 检查是否为超级管理员
        if not (current_user.user_role and current_user.user_role.code == 'super_admin'):
            logging.warning(f"非超级管理员用户{current_user.id}尝试恢复数据库")
            return jsonify({
                "success": False,
                "message": "只有超级管理员才能恢复数据库"
            }), 403
        
        # 从config获取备份目录
        backup_dir = current_app.config.get('BACKUP_DIR')
        
        if not backup_dir:
            return jsonify({
                "success": False,
                "message": "未配置备份目录"
            }), 400
        
        file_path = os.path.join(backup_dir, filename)
        
        if not os.path.exists(file_path) or not filename.startswith('BACKUP_') or not filename.endswith('.sql'):
            return jsonify({
                "success": False,
                "message": "备份文件不存在或不是有效的SQL备份文件"
            }), 404
        
        # 保存当前管理员ID
        current_admin_id = current_user.id
        
        # 获取当前数据库类型
        current_db_type = get_db_type_identifier()
        
        # 创建恢复前的临时备份
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_backup_name = f'pre_restore_backup_{current_db_type}_{timestamp}.sql'
        temp_backup_path = os.path.join(backup_dir, temp_backup_name)
        
        # 执行当前数据库的备份操作
        if current_db_type == 'MYSQL':
            # 移除'MYSQL'参数
            temp_backup_content = DatabaseBackupManager.create_database_backup()
            with open(temp_backup_path, 'w', encoding='utf-8') as f:
                f.write(temp_backup_content)
        else:
            # 移除'SQLITE'参数
            temp_backup_content = DatabaseBackupManager.create_database_backup()
            with open(temp_backup_path, 'wb') as f:
                f.write(temp_backup_content)
        
        # 读取文件内容并检测数据库类型（仅基于内容，不依赖文件名）
        db_type = None
        restore_content = None
        try:
            # 先以二进制方式读取文件头
            with open(file_path, 'rb') as f:
                file_header = f.read(16)  # 读取文件头16字节
                
            # SQLite文件头特征检测
            if file_header.startswith(b'SQLite format 3\x00'):
                db_type = "SQLITE"
                # 重新以二进制方式读取整个文件
                with open(file_path, 'rb') as f:
                    restore_content = f.read()
            else:
                # 否则尝试作为MySQL的文本SQL文件处理
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        restore_content = f.read()
                        # 检查内容是否包含典型的MySQL SQL语句特征
                        if any(keyword in restore_content.upper() for keyword in ['CREATE TABLE', 'INSERT INTO', 'DROP TABLE']):
                            db_type = "MYSQL"
                        else:
                            raise Exception("无法识别的备份文件格式")
                except UnicodeDecodeError:
                    # 如果解码失败，可能是损坏的SQLite文件或其他格式
                    raise Exception("无法识别的备份文件格式")
        except Exception as e:
            raise Exception(f"读取或识别备份文件失败: {str(e)}")
        
        # 增强校验：检查检测到的数据库类型是否与当前数据库一致
        if db_type != current_db_type:
            return jsonify({
                "success": False,
                "message": f"备份文件类型不匹配，当前为{current_db_type}数据库，备份文件为{db_type}数据库"
            }), 400
        
        # 执行恢复操作
        success = DatabaseBackupManager.restore_database_backup(restore_content, db_type)
        
        if not success:
            # 恢复失败时保留临时备份以便排查问题
            raise Exception("数据库恢复操作失败，已保留恢复前的临时备份")
        
        log_operation(
            user_id=current_admin_id,
            action=f"已成功从{db_type}备份 {filename} 恢复数据",
            module="system",
            operation_type="restore_backup",
            result="成功"
        )
        
        return jsonify({
            "success": True,
            "message": f"已成功从{db_type}备份 {filename} 恢复数据，请刷新网页",
            "temp_backup": temp_backup_name
        })
    except Exception as e:
        logging.error(f"恢复备份失败: {str(e)}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else 0,
            action=f"从备份恢复数据失败: {str(e)}",
            module="system",
            operation_type="restore_backup",
            result="失败"
        )
        return jsonify({
            "success": False,
            "message": f"恢复备份失败: {str(e)}"
        }), 500

@system_config_bp.route('/api/backup/restore-from-upload', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def restore_from_upload():
    try:
        # 检查是否为超级管理员
        if not (current_user.user_role and current_user.user_role.code == 'super_admin'):
            logging.warning(f"非超级管理员用户{current_user.id}尝试从上传文件恢复数据库")
            return jsonify({
                "success": False,
                "message": "只有超级管理员才能恢复数据库"
            }), 403
        
        # 获取当前数据库类型
        current_db_type = get_db_type_identifier()
        # 检查是否有文件上传
        if 'backup_file' not in request.files:
            return jsonify({
                "success": False,
                "message": "未找到上传的文件"
            }), 400
        
        backup_file = request.files['backup_file']
        
        # 验证文件名
        if backup_file.filename == '':
            return jsonify({
                "success": False,
                "message": "未选择文件"
            }), 400
        
        # 验证文件类型（确保是SQL脚本）
        if not backup_file.filename.endswith('.sql'):
            return jsonify({
                "success": False,
                "message": "请上传SQL格式的备份文件"
            }), 400
        
        # 获取备份目录
        backup_dir = current_app.config.get('BACKUP_DIR')
        if not backup_dir:
            default_dir = current_app.config.get('BACKUP_DIR')
            backup_dir = default_dir

        
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir, exist_ok=True)
        
        # 保存上传的文件（确保是SQL文件）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"uploaded_{current_db_type}_{timestamp}_{os.path.basename(backup_file.filename)}"
        # 强制文件名以.sql结尾
        if not filename.endswith('.sql'):
            filename += '.sql'
        file_path = os.path.join(backup_dir, filename)
        backup_file.save(file_path)
        
        # 保存当前管理员ID
        current_admin_id = current_user.id
        
        # 创建恢复前的临时备份（SQL脚本格式）
        temp_backup_name = f"pre_restore_upload_{timestamp}.sql"
        temp_backup_path = os.path.join(backup_dir, temp_backup_name)
        temp_backup_success = DatabaseBackupManager.create_database_backup()
        if not temp_backup_success:
            os.remove(file_path)  # 清理上传的文件
            raise Exception("创建恢复前的临时备份失败，中止恢复操作")
        
        # 读取文件内容并检测数据库类型（仅基于内容，不依赖文件名）
        db_type = None
        restore_content = None
        try:
            # 先以二进制方式读取文件头
            with open(file_path, 'rb') as f:
                file_header = f.read(16)  # 读取文件头16字节
                
            # SQLite文件头特征检测
            if file_header.startswith(b'SQLite format 3\x00'):
                db_type = "SQLITE"
                # 重新以二进制方式读取整个文件
                with open(file_path, 'rb') as f:
                    restore_content = f.read()
            else:
                # 否则尝试作为MySQL的文本SQL文件处理
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        restore_content = f.read()
                        # 检查内容是否包含典型的MySQL SQL语句特征
                        if any(keyword in restore_content.upper() for keyword in ['CREATE TABLE', 'INSERT INTO', 'DROP TABLE']):
                            db_type = "MYSQL"
                        else:
                            raise Exception("无法识别的备份文件格式")
                except UnicodeDecodeError:
                    # 如果解码失败，可能是损坏的SQLite文件或其他格式
                    raise Exception("无法识别的备份文件格式")
        except Exception as e:
            raise Exception(f"读取或识别备份文件失败: {str(e)}")
        
        # 增强校验：检查检测到的数据库类型是否与当前数据库一致
        if db_type != current_db_type:
            return jsonify({
                "success": False,
                "message": f"备份文件类型不匹配，当前为{current_db_type}数据库，备份文件为{db_type}数据库"
            }), 400
        
        # 执行恢复操作（使用统一的SQL脚本恢复方法）
        success = DatabaseBackupManager.restore_database_backup(restore_content, db_type)
        
        if not success:
            # 恢复失败时保留相关文件以便排查
            logging.error(f"数据库恢复操作失败，已保留上传的备份文件和恢复前的临时备份")
            raise Exception("数据库恢复操作失败，已保留上传的备份文件和恢复前的临时备份")
        logging.info(f"已成功从上传的{db_type}文件 {backup_file.filename} 恢复数据")
        log_operation(
            user_id=current_admin_id,
            action=f"已成功从上传的{db_type}文件 {backup_file.filename} 恢复数据",
            module="system",
            operation_type="restore_backup",
            result="成功"
        )
        
        return jsonify({
            "success": True,
            "message": f"已成功从上传的{db_type}文件 {backup_file.filename} 恢复数据，请刷新网页",
            "temp_backup": temp_backup_name,
            "saved_file": filename
        })
    except Exception as e:
        logging.error(f"从上传文件恢复备份失败: {str(e)}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else 0,
            action=f"从上传文件恢复数据失败: {str(e)}",
            module="system",
            operation_type="restore_backup",
            result="失败"
        )
        return jsonify({
            "success": False,
            "message": f"恢复备份失败: {str(e)}"
        }), 500

@system_config_bp.route('/api/backup/download/<filename>', methods=['GET'])
@login_required
@require_permission('system_settings.manage')
def download_backup(filename):
    """下载备份列表中的指定备份文件"""
    try:
        # 获取备份目录
        backup_dir = current_app.config.get('BACKUP_DIR')
        
        if not backup_dir:
            return jsonify({
                "success": False,
                "message": "未配置备份目录"
            }), 400
        
        # 构建完整文件路径
        file_path = os.path.join(backup_dir, filename)
        
        # 验证文件合法性
        if (not os.path.exists(file_path) or 
            not os.path.isfile(file_path) or 
            not filename.startswith('BACKUP_') or 
            not filename.endswith('.sql')):
            return jsonify({
                "success": False,
                "message": "备份文件不存在或不是有效的备份文件"
            }), 404
        
        # 验证备份文件类型与当前数据库类型匹配
        current_db_type = get_db_type_identifier()
        file_db_type = "unknown"
        if "mysql" in filename:
            file_db_type = "mysql"
        elif "sqlite" in filename:
            file_db_type = "sqlite"
            
        if file_db_type != current_db_type and file_db_type != "unknown":
            return jsonify({
                "success": False,
                "message": f"备份文件类型不匹配，当前为{current_db_type}数据库，备份文件为{file_db_type}数据库"
            }), 400
        
        # 记录下载日志
        log_operation(
            user_id=current_user.id,
            action=f"下载备份文件: {filename}",
            module="system",
            operation_type="download_backup",
            result="成功"
        )
        
        # 提供文件下载
        from flask import send_file
        return send_file(
            file_path,
            as_attachment=True,
            download_name=filename,
            mimetype='application/sql'
        )
        
    except Exception as e:
        logging.error(f"下载备份文件失败: {str(e)}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else 0,
            action=f"下载备份文件失败: {str(e)}",
            module="system",
            operation_type="download_backup",
            result="失败"
        )
        return jsonify({
            "success": False,
            "message": f"下载备份文件失败: {str(e)}"
        }), 500


@system_config_bp.route('/api/backup/create-and-download', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def create_and_download_backup():
    """创建直接下载备份文件（不存储到服务器）"""
    try:
        # 获取数据库类型标识
        db_type = get_db_type_identifier()
        
        # 创建数据库备份（使用无参数方法）
        backup_content = DatabaseBackupManager.create_database_backup()
        if backup_content is None:
            raise Exception("数据库备份操作失败")
        
        # 创建时间戳用于文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = f"BACKUP_{db_type}_{timestamp}.sql"
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            action=f"创建并下载{db_type}数据库备份",
            module="system",
            operation_type="create_and_download_backup",
            result="成功"
        )
        
        # 直接从内存提供下载，不保存到服务器
        from flask import send_file, make_response
        import io
        
        # 创建内存中的文件对象，根据内容类型进行处理
        if isinstance(backup_content, str):
            # 如果是字符串，转换为字节
            backup_file = io.BytesIO(backup_content.encode('utf-8'))
            content_length = len(backup_content.encode('utf-8'))
        else:
            # 如果已经是字节，直接使用
            backup_file = io.BytesIO(backup_content)
            content_length = len(backup_content)
        
        backup_file.seek(0)
        
        # 创建响应
        response = make_response(send_file(
            backup_file,
            as_attachment=True,
            download_name=backup_filename,
            mimetype='application/sql'
        ))
        
        # 设置内容长度
        response.headers['Content-Length'] = content_length
        
        return response
        
    except Exception as e:
        logging.error(f"创建并下载备份失败: {str(e)}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else 0,
            action=f"创建并下载系统备份失败, {str(e)}",
            module="system.backup",
            operation_type="create_and_download_backup",
            result="失败"
        )
        return jsonify({
            "success": False,
            "message": f"创建并下载备份失败: {str(e)}"
        }), 500
