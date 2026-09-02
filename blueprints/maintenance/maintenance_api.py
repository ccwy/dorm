from flask import Blueprint, request, jsonify, send_file, current_app
from models.maintenance import MaintenanceOrder
from models.user import User
from models.role import Role
from models.room import Room
from utils.maintenance_photo import MaintenancePhotoManager
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.log import log_operation
from utils.db import db
import logging
import os


# 创建维修API蓝图
maintenance_api_bp = Blueprint('maintenance_api', __name__, url_prefix='/api/maintenance')


def _check_maintenance_upload_permission():
    """检查维修模块上传权限（maintenance.create、maintenance.handle 或 maintenance.manage）"""
    if not current_user.is_authenticated:
        return False
    return (current_user.has_permission('maintenance.create') or 
            current_user.has_permission('maintenance.handle') or 
            current_user.has_permission('maintenance.manage'))


# 临时文件上传
@maintenance_api_bp.route('/upload-temp', methods=['POST'])
@login_required
def temp_upload():
    """上传临时文件（创建工单前使用）"""
    if not _check_maintenance_upload_permission():
        return jsonify({'success': False, 'message': '无权限访问'}), 403
    try:
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            return jsonify({'success': False, 'message': '用户信息无效'}), 400
        
        user_id = int(str(user_id))
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未找到上传文件'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'}), 400
        
        # 上传临时文件
        filename = MaintenancePhotoManager.upload_temp_file(file, user_id)
        
        if filename:
            # 获取临时文件列表
            temp_files = MaintenancePhotoManager.get_temp_files(user_id)
            # 生成临时文件访问URL
            file_url = MaintenancePhotoManager.get_temp_url(user_id, filename)
            
            # 记录操作日志
            log_operation(
                user_id=user_id,
                action=f"用户 [{user_id}] 上传临时文件: {filename}",
                result="成功",
                module="maintenance",
                operation_type="upload"
            )
            logging.info(f"用户 [{user_id}] 成功上传临时文件: {filename}")
            
            return jsonify({
                'success': True,
                'message': '文件上传成功',
                'filename': filename,
                'url': file_url,
                'files': temp_files
            })
        else:
            return jsonify({'success': False, 'message': '文件上传失败'}), 500
    except Exception as e:
        logging.error(f"上传临时文件失败: {str(e)}")
        return jsonify({'success': False, 'message': f'文件上传失败: {str(e)}'}), 500


# 获取临时文件列表
@maintenance_api_bp.route('/temp-files')
@login_required
def get_temp_files():
    """获取当前用户的临时文件列表"""
    if not _check_maintenance_upload_permission():
        return jsonify({'success': False, 'message': '无权限访问'}), 403
    try:
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            return jsonify({'success': False, 'message': '用户信息无效'}), 400
        
        user_id = int(str(user_id))
        
        temp_files = MaintenancePhotoManager.get_temp_files(user_id)
        
        return jsonify({
            'success': True,
            'files': temp_files
        })
    except Exception as e:
        logging.error(f"获取临时文件列表失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取临时文件列表失败: {str(e)}'}), 500


# 删除临时文件
@maintenance_api_bp.route('/delete-temp/<path:filename>', methods=['POST'])
@login_required
@require_permission('maintenance.manage')
def delete_temp_file(filename):
    """删除临时文件"""
    if not _check_maintenance_upload_permission():
        return jsonify({'success': False, 'message': '无权限访问'}), 403
    try:
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            return jsonify({'success': False, 'message': '用户信息无效'}), 400
        
        user_id = int(str(user_id))
        
        result = MaintenancePhotoManager.delete_temp_file(filename, user_id)
        
        if result:
            # 获取更新后的临时文件列表
            temp_files = MaintenancePhotoManager.get_temp_files(user_id)
            
            # 记录操作日志
            log_operation(
                user_id=user_id,
                action=f"用户 [{user_id}] 删除临时文件: {filename}",
                result="成功",
                module="maintenance",
                operation_type="delete"
            )
            logging.info(f"用户 [{user_id}] 成功删除临时文件: {filename}")
            
            return jsonify({
                'success': True,
                'message': '文件删除成功',
                'files': temp_files
            })
        else:
            return jsonify({'success': False, 'message': '文件删除失败'}), 500
    except Exception as e:
        logging.error(f"删除临时文件失败: {str(e)}")
        return jsonify({'success': False, 'message': f'删除临时文件失败: {str(e)}'}), 500


# 工单照片上传
@maintenance_api_bp.route('/upload-photo/<int:order_id>', methods=['POST'])
@login_required
def upload_order_photo(order_id):
    """上传工单照片"""
    if not _check_maintenance_upload_permission():
        return jsonify({'success': False, 'message': '无权限访问'}), 403
    try:
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            return jsonify({'success': False, 'message': '用户信息无效'}), 400
        
        user_id = int(str(user_id))
        
        # 检查工单是否存在
        order = MaintenanceOrder.get_by_id(order_id)
        if not order:
            return jsonify({'success': False, 'message': '维修工单不存在'}), 404
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '未找到上传文件'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '未选择文件'}), 400
        
        # 上传文件
        filename = MaintenancePhotoManager.upload_file(file, order_id)
        
        if filename:
            # 获取更新后的媒体文件列表
            media_files = MaintenancePhotoManager.get_media_files(order_id)
            
            # 记录操作日志
            log_operation(
                user_id=user_id,
                action=f"用户 [{user_id}] 上传维修工单 {order_id} 照片: {filename}",
                result="成功",
                module="maintenance",
                operation_type="upload"
            )
            logging.info(f"用户 [{user_id}] 成功上传维修工单 {order_id} 照片: {filename}")
            
            return jsonify({
                'success': True,
                'message': '照片上传成功',
                'filename': filename,
                'files': media_files
            })
        else:
            return jsonify({'success': False, 'message': '照片上传失败'}), 500
    except Exception as e:
        logging.error(f"上传工单照片失败: {str(e)}")
        return jsonify({'success': False, 'message': f'照片上传失败: {str(e)}'}), 500


# 获取工单照片列表
@maintenance_api_bp.route('/photos/<int:order_id>')
@login_required
def get_order_photos(order_id):
    """获取工单照片列表"""
    if not _check_maintenance_upload_permission():
        return jsonify({'success': False, 'message': '无权限访问'}), 403
    try:
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            return jsonify({'success': False, 'message': '用户信息无效'}), 400
        
        user_id = int(str(user_id))
        
        # 检查工单是否存在
        order = MaintenanceOrder.get_by_id(order_id)
        if not order:
            return jsonify({'success': False, 'message': '维修工单不存在'}), 404
        
        media_files = MaintenancePhotoManager.get_media_files(order_id)
        
        return jsonify({
            'success': True,
            'files': media_files
        })
    except Exception as e:
        logging.error(f"获取工单照片列表失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取工单照片列表失败: {str(e)}'}), 500


# 删除工单照片
@maintenance_api_bp.route('/delete-photo/<int:order_id>/<path:filename>', methods=['POST'])
@login_required
@require_permission('maintenance.manage')
def delete_order_photo(order_id, filename):
    """删除工单照片"""
    if not _check_maintenance_upload_permission():
        return jsonify({'success': False, 'message': '无权限访问'}), 403
    try:
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            return jsonify({'success': False, 'message': '用户信息无效'}), 400
        
        user_id = int(str(user_id))
        
        # 检查工单是否存在
        order = MaintenanceOrder.get_by_id(order_id)
        if not order:
            return jsonify({'success': False, 'message': '维修工单不存在'}), 404
        
        result = MaintenancePhotoManager.delete_file(filename, order_id)
        
        if result:
            # 获取更新后的媒体文件列表
            media_files = MaintenancePhotoManager.get_media_files(order_id)
            
            # 记录操作日志
            log_operation(
                user_id=user_id,
                action=f"用户 [{user_id}] 删除维修工单 {order_id} 照片: {filename}",
                result="成功",
                module="maintenance",
                operation_type="delete"
            )
            logging.info(f"用户 [{user_id}] 成功删除维修工单 {order_id} 照片: {filename}")
            
            return jsonify({
                'success': True,
                'message': '照片删除成功',
                'files': media_files
            })
        else:
            return jsonify({'success': False, 'message': '照片删除失败'}), 500
    except Exception as e:
        logging.error(f"删除工单照片失败: {str(e)}")
        return jsonify({'success': False, 'message': f'删除工单照片失败: {str(e)}'}), 500


# 临时文件访问
@maintenance_api_bp.route('/temp/<int:user_id>/<path:filename>')
@login_required
def serve_temp_file(user_id, filename):
    """提供临时文件访问"""
    try:
        # 只允许访问自己的临时文件
        if current_user.id != user_id:
            return jsonify({'success': False, 'message': '无权访问此文件'}), 403
        
        file_path = MaintenancePhotoManager.get_temp_file_path(filename, user_id)
        
        if file_path and os.path.exists(file_path):
            return send_file(file_path)
        else:
            return jsonify({'success': False, 'message': '文件不存在'}), 404
    except Exception as e:
        logging.error(f"访问临时文件失败: {str(e)}")
        return jsonify({'success': False, 'message': '文件访问失败'}), 500


# 媒体文件访问
@maintenance_api_bp.route('/media/<int:order_id>/<path:filename>')
@login_required
@require_permission('maintenance.view')
def serve_media_file(order_id, filename):
    """提供工单媒体文件访问"""
    try:
        # 检查工单是否存在
        order = MaintenanceOrder.get_by_id(order_id)
        if not order:
            return jsonify({'success': False, 'message': '维修工单不存在'}), 404
        
        file_path = MaintenancePhotoManager.get_file_path(filename, order_id)
        
        if file_path and os.path.exists(file_path):
            return send_file(file_path)
        else:
            return jsonify({'success': False, 'message': '文件不存在'}), 404
    except Exception as e:
        logging.error(f"访问媒体文件失败: {str(e)}")
        return jsonify({'success': False, 'message': '文件访问失败'}), 500


# 维修员列表API
@maintenance_api_bp.route('/staff-list')
@login_required
@require_permission('maintenance.manage')
def get_staff_list():
    """获取维修员列表（用于分配选择）"""
    try:
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            return jsonify({'success': False, 'message': '用户信息无效'}), 400
        
        user_id = int(str(user_id))
        
        # 查询所有维修员角色的活跃用户
        staff_list = User.query.join(Role, User.role_id == Role.id).filter(
            Role.code == 'maintenance_staff',
            User.is_active == True
        ).all()
        
        staff_data = []
        for staff in staff_list:
            # 统计每个维修员当前处理中的工单数
            processing_count = MaintenanceOrder.query.filter_by(
                assigned_to=staff.id,
                status='处理中'
            ).count()
            
            staff_data.append({
                'id': staff.id,
                'name': staff.name,
                'processing_count': processing_count
            })
        
        return jsonify({
            'success': True,
            'staff': staff_data
        })
    except Exception as e:
        logging.error(f"获取维修员列表失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取维修员列表失败: {str(e)}'}), 500


# 清理所有临时文件API
@maintenance_api_bp.route('/clear-all-temp', methods=['POST'])
@login_required
@require_permission('maintenance.manage')
def clear_all_temp():
    """清理所有用户临时目录中的媒体文件（管理员操作）"""
    try:
        result = MaintenancePhotoManager.clear_all_temp_files()
        
        log_operation(
            user_id=current_user.id,
            module='maintenance',
            operation_type='delete',
            action=f"清理所有维修临时文件 [删除: {result['deleted']}, 用户: {result['users_cleared']}, 失败: {len(result['errors'])}]",
            result="成功" if not result['errors'] else "部分成功"
        )
        
        return jsonify({
            'success': True,
            'deleted': result['deleted'],
            'users_cleared': result['users_cleared'],
            'errors': result['errors'],
            'message': f"成功清理 {result['deleted']} 个文件" + (f"，{len(result['errors'])} 个失败" if result['errors'] else "")
        })
    
    except Exception as e:
        logging.error(f"清理所有维修临时文件失败: {str(e)}")
        return jsonify({'success': False, 'message': f'清理失败: {str(e)}'}), 500


# ========== 搜索房间（报修申请用） ==========
@maintenance_api_bp.route('/rooms/search', methods=['GET'])
@login_required
@require_permission('maintenance.create')
def search_rooms():
    """搜索房间（报修申请选择房间用）"""
    try:
        query = request.args.get('query', '').strip()
        rooms = Room.query
        if query:
            rooms = rooms.filter(
                db.or_(
                    Room.building.ilike(f'%{query}%'),
                    Room.room_number.ilike(f'%{query}%')
                )
            )
        rooms = rooms.order_by(Room.building, Room.room_number).limit(30).all()
        return jsonify([{
            'id': r.id,
            'building': r.building,
            'room_number': r.room_number,
            'display': r.room_full_identifier if hasattr(r, 'room_full_identifier') and r.room_full_identifier else f"{r.building}{r.room_number}",
            'status': r.status
        } for r in rooms])
    except Exception as e:
        logging.error(f"搜索房间失败: {str(e)}")
        return jsonify([]), 500