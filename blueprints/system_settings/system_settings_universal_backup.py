"""
通用备份恢复蓝图
使用 JSON 格式实现跨数据库（SQLite ↔ MySQL）备份恢复
与现有 backup.py 完全独立，不参与自动备份逻辑
"""

from flask import request, jsonify, current_app, session
from flask_login import login_required, current_user, logout_user
from utils.auth import require_permission
from utils.cookie_secure import invalidate_all_sessions
import os
import logging
import gzip
from datetime import datetime
from utils.log import log_operation
from .system_settings import system_config_bp  # 系统配置蓝图
from utils.universal_backup import UniversalBackupManager


@system_config_bp.route('/api/universal-backup/create', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def create_universal_backup():
    """创建通用JSON格式备份（跨数据库兼容）"""
    try:
        # 检查是否为超级管理员
        if not (current_user.user_role and current_user.user_role.code == 'super_admin'):
            logging.warning(f"非超级管理员用户{current_user.id}尝试创建通用备份")
            return jsonify({
                "success": False,
                "message": "只有超级管理员才能创建通用备份"
            }), 403

        # 创建通用备份
        backup_content, error = UniversalBackupManager.create_backup()

        if error:
            raise Exception(error)

        if backup_content is None:
            raise Exception("通用备份操作失败，返回空内容")

        # 保存到备份目录
        backup_dir = current_app.config.get('BACKUP_DIR')
        if not backup_dir:
            backup_dir = os.path.join(current_app.instance_path, 'backups')

        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir, exist_ok=True)

        # 使用 .json.gz 扩展名标识通用备份（gzip压缩存储）
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        db_type = UniversalBackupManager._auto_detect_db_type()
        backup_filename = f"UNIVERSAL_BACKUP_{db_type}_{timestamp}.json.gz"
        backup_path = os.path.join(backup_dir, backup_filename)

        # gzip 压缩保存
        compressed = gzip.compress(backup_content.encode('utf-8'))
        with open(backup_path, 'wb') as f:
            f.write(compressed)

        file_size = os.path.getsize(backup_path)
        logging.info(f"[通用备份] 备份已保存: {backup_filename}, 压缩后大小: {file_size} 字节")

        log_operation(
            user_id=current_user.id,
            action=f"创建通用备份，文件: {backup_filename}",
            module="system.backup",
            operation_type="create_universal_backup",
            result="成功"
        )

        return jsonify({
            "success": True,
            "message": "通用备份创建成功",
            "backup_file": backup_filename,
            "backup_time": timestamp,
            "file_size": file_size
        })

    except Exception as e:
        logging.error(f"创建通用备份失败: {str(e)}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else 0,
            action=f"创建通用备份失败: {str(e)}",
            module="system.backup",
            operation_type="create_universal_backup",
            result="失败"
        )
        return jsonify({
            "success": False,
            "message": f"创建通用备份失败: {str(e)}"
        }), 500


@system_config_bp.route('/api/universal-backup/restore', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def restore_universal_backup():
    """从上传的通用JSON备份文件恢复数据"""
    try:
        # 检查是否为超级管理员
        if not (current_user.user_role and current_user.user_role.code == 'super_admin'):
            logging.warning(f"非超级管理员用户{current_user.id}尝试恢复通用备份")
            return jsonify({
                "success": False,
                "message": "只有超级管理员才能恢复数据库"
            }), 403

        # 在恢复前保存当前用户ID，然后立即退出登录
        # 恢复是破坏性操作，先作废会话再执行，避免after_request钩子访问已detach的ORM对象
        admin_user_id = current_user.id
        logout_user()
        session.clear()
        # 更新全局会话版本号，使所有浏览器中的旧cookie自动失效
        invalidate_all_sessions()
        logging.info("[通用恢复] 已在恢复前退出登录并使所有旧session失效")

        # 从上传文件或请求体获取备份内容
        if 'file' in request.files:
            file = request.files['file']
            backup_content = file.read()
        else:
            backup_content = request.get_data()

        if not backup_content:
            return jsonify({
                "success": False,
                "message": "未提供备份文件"
            }), 400

        # 先获取备份信息用于确认
        info, info_error = UniversalBackupManager.get_backup_info(backup_content)
        if info_error:
            return jsonify({
                "success": False,
                "message": f"无法解析备份文件: {info_error}"
            }), 400

        # 创建恢复前的临时备份（安全措施）
        try:
            backup_dir = current_app.config.get('BACKUP_DIR')
            if backup_dir and os.path.exists(backup_dir):
                pre_backup_content, pre_error = UniversalBackupManager.create_backup()
                if pre_backup_content and not pre_error:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    db_type = UniversalBackupManager._auto_detect_db_type()
                    pre_backup_name = f"pre_universal_restore_{db_type}_{timestamp}.json.gz"
                    pre_backup_path = os.path.join(backup_dir, pre_backup_name)
                    compressed = gzip.compress(pre_backup_content.encode('utf-8'))
                    with open(pre_backup_path, 'wb') as f:
                        f.write(compressed)
                    logging.info(f"[通用恢复] 已创建恢复前备份: {pre_backup_name}")
        except Exception as e:
            logging.warning(f"[通用恢复] 创建恢复前备份失败（非致命）: {str(e)}")

        # 执行恢复
        success, error = UniversalBackupManager.restore_backup(backup_content)

        if not success:
            raise Exception(error or "通用恢复操作失败")

        log_operation(
            user_id=admin_user_id,
            action=f"从通用备份恢复数据，来源: {info.get('source_db_type', 'UNKNOWN')}, "
                   f"备份时间: {info.get('export_time', '未知')}, "
                   f"表数量: {info.get('total_tables', 0)}, 行数量: {info.get('total_rows', 0)}",
            module="system.backup",
            operation_type="restore_universal_backup",
            result="成功"
        )

        return jsonify({
            "success": True,
            "message": f"已成功从通用备份恢复数据（来源: {info.get('source_db_type', '未知')}，"
                       f"共 {info.get('total_tables', 0)} 张表，{info.get('total_rows', 0)} 行数据），请重新登录",
            "backup_info": info,
            "need_relogin": True
        })

    except Exception as e:
        logging.error(f"恢复通用备份失败: {str(e)}")
        log_operation(
            user_id=admin_user_id,
            action=f"从通用备份恢复数据失败: {str(e)}",
            module="system.backup",
            operation_type="restore_universal_backup",
            result="失败"
        )
        return jsonify({
            "success": False,
            "message": f"恢复通用备份失败: {str(e)}"
        }), 500


@system_config_bp.route('/api/universal-backup/info', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def get_universal_backup_info():
    """获取上传的通用备份文件信息（不执行恢复，用于预览确认）"""
    try:
        # 从上传文件或请求体获取备份内容
        if 'file' in request.files:
            file = request.files['file']
            backup_content = file.read()
        else:
            backup_content = request.get_data()

        if not backup_content:
            return jsonify({
                "success": False,
                "message": "未提供备份文件"
            }), 400

        info, error = UniversalBackupManager.get_backup_info(backup_content)

        if error:
            return jsonify({
                "success": False,
                "message": f"无法解析备份文件: {error}"
            }), 400

        return jsonify({
            "success": True,
            "info": info
        })

    except Exception as e:
        logging.error(f"获取通用备份信息失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"获取通用备份信息失败: {str(e)}"
        }), 500


@system_config_bp.route('/api/universal-backup/restore/<filename>', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def restore_universal_backup_from_file(filename):
    """从备份目录中的通用备份文件恢复数据"""
    try:
        # 检查是否为超级管理员
        if not (current_user.user_role and current_user.user_role.code == 'super_admin'):
            return jsonify({
                "success": False,
                "message": "只有超级管理员才能恢复数据库"
            }), 403

        # 在恢复前保存当前用户ID，然后立即退出登录
        # 恢复是破坏性操作，先作废会话再执行，避免after_request钩子访问已detach的ORM对象
        admin_user_id = current_user.id
        logout_user()
        session.clear()
        # 更新全局会话版本号，使所有浏览器中的旧cookie自动失效
        invalidate_all_sessions()
        logging.info("[通用恢复] 已在恢复前退出登录并使所有旧session失效")

        # 安全检查：防止路径遍历
        if not filename.startswith('UNIVERSAL_BACKUP_') or '..' in filename:
            return jsonify({
                "success": False,
                "message": "无效的通用备份文件名"
            }), 400

        backup_dir = current_app.config.get('BACKUP_DIR')
        if not backup_dir:
            return jsonify({
                "success": False,
                "message": "未配置备份目录"
            }), 400

        file_path = os.path.join(backup_dir, filename)
        if not os.path.exists(file_path):
            return jsonify({
                "success": False,
                "message": "备份文件不存在"
            }), 404

        # 读取文件内容
        with open(file_path, 'rb') as f:
            backup_content = f.read()

        # 获取备份信息
        info, info_error = UniversalBackupManager.get_backup_info(backup_content)
        if info_error:
            return jsonify({
                "success": False,
                "message": f"无法解析备份文件: {info_error}"
            }), 400

        # 创建恢复前的临时备份
        try:
            if backup_dir and os.path.exists(backup_dir):
                pre_backup_content, pre_error = UniversalBackupManager.create_backup()
                if pre_backup_content and not pre_error:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    db_type = UniversalBackupManager._auto_detect_db_type()
                    pre_backup_name = f"pre_universal_restore_{db_type}_{timestamp}.json.gz"
                    pre_backup_path = os.path.join(backup_dir, pre_backup_name)
                    compressed = gzip.compress(pre_backup_content.encode('utf-8'))
                    with open(pre_backup_path, 'wb') as f:
                        f.write(compressed)
        except Exception as e:
            logging.warning(f"[通用恢复] 创建恢复前备份失败（非致命）: {str(e)}")

        # 执行恢复
        success, error = UniversalBackupManager.restore_backup(backup_content)

        if not success:
            raise Exception(error or "通用恢复操作失败")

        log_operation(
            user_id=admin_user_id,
            action=f"从通用备份文件 {filename} 恢复数据",
            module="system.backup",
            operation_type="restore_universal_backup",
            result="成功"
        )

        return jsonify({
            "success": True,
            "message": f"已成功从通用备份 {filename} 恢复数据，请重新登录",
            "backup_info": info,
            "need_relogin": True
        })

    except Exception as e:
        logging.error(f"从文件恢复通用备份失败: {str(e)}")
        log_operation(
            user_id=admin_user_id,
            action=f"从通用备份文件 {filename} 恢复数据失败: {str(e)}",
            module="system.backup",
            operation_type="restore_universal_backup",
            result="失败"
        )
        return jsonify({
            "success": False,
            "message": f"恢复通用备份失败: {str(e)}"
        }), 500


@system_config_bp.route('/api/universal-backup/list', methods=['GET'])
@login_required
def list_universal_backups():
    """获取通用备份文件列表"""
    try:
        backup_dir = current_app.config.get('BACKUP_DIR')
        page = request.args.get('page', 1, type=int)
        page_size = request.args.get('pageSize', 10, type=int)

        if not backup_dir or not os.path.exists(backup_dir):
            return jsonify({
                "success": True,
                "data": [],
                "total": 0,
                "page": page,
                "pageSize": page_size
            })

        backup_files = []
        for filename in os.listdir(backup_dir):
            # 只列出通用备份文件（.json 或 .json.gz）
            if not filename.startswith('UNIVERSAL_BACKUP_'):
                continue
            if not (filename.endswith('.json') or filename.endswith('.json.gz')):
                continue

            file_path = os.path.join(backup_dir, filename)
            file_stats = os.stat(file_path)

            # 从文件名提取数据库类型
            file_db_type = "unknown"
            if 'MYSQL' in filename:
                file_db_type = "mysql"
            elif 'SQLITE' in filename:
                file_db_type = "sqlite"

            backup_files.append({
                "filename": filename,
                "db_type": file_db_type,
                "size": file_stats.st_size,
                "created_at": datetime.fromtimestamp(file_stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                "path": file_path,
                "is_universal": True  # 标识为通用备份
            })

        # 按创建时间排序
        backup_files.sort(key=lambda x: x['created_at'], reverse=True)

        total = len(backup_files)
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_files = backup_files[start_index:end_index]

        return jsonify({
            "success": True,
            "data": paginated_files,
            "total": total,
            "page": page,
            "pageSize": page_size,
            "totalPages": (total + page_size - 1) // page_size
        })

    except Exception as e:
        logging.error(f"获取通用备份列表失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": f"获取通用备份列表失败: {str(e)}"
        }), 500


