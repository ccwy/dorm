from flask import Blueprint, request, jsonify, send_file
import logging
import os
import traceback
from datetime import datetime
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.log import log_operation
from utils.media.room_meter_checkout_photo import room_meter_checkout_photo_manager

utility_room_meter_checkout_photo_bp = Blueprint('utility_room_meter_checkout_photo', __name__, url_prefix='/utility-checkout')


@utility_room_meter_checkout_photo_bp.route('/upload_media', methods=['POST'])
@login_required
@require_permission('utility.edit')
def upload_checkout_media():
    """上传退宿照片或视频"""
    try:
        # 获取请求参数
        billing_period = request.form.get('billing_period')
        room_id = request.form.get('room_id')
        user_id = request.form.get('user_id')
        
        # 验证参数
        if not billing_period or not room_id or not user_id:
            logging.warning(f"用户 {current_user.id} 尝试上传退宿媒体文件，但缺少必要参数")
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        if 'file' not in request.files:
            logging.warning(f"用户 {current_user.id} 尝试上传退宿媒体文件，但没有文件被上传")
            return jsonify({'success': False, 'message': '没有文件被上传'})
        
        file = request.files['file']
        if file.filename == '':
            logging.warning(f"用户 {current_user.id} 尝试上传退宿媒体文件，但没有选择文件")
            return jsonify({'success': False, 'message': '没有选择文件'})
        
        # 上传文件
        filename = room_meter_checkout_photo_manager.upload_file(file, billing_period, room_id, user_id)
        if not filename:
            logging.warning(f"用户 {current_user.id} 尝试上传退宿媒体文件，但文件格式不支持")
            return jsonify({'success': False, 'message': '不支持的文件格式'})
        
        # 生成文件URL
        file_url = room_meter_checkout_photo_manager.get_media_url(filename, billing_period, room_id, user_id)
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='checkout_photo',
            action=f"上传退宿媒体文件: {filename} 到 {billing_period}/room_{room_id}/checkout_{user_id}",
            result="成功"
        )
        
        return jsonify({
            'success': True,
            'message': '上传成功',
            'filename': filename,
            'file_url': file_url
        })
        
    except Exception as e:
        logging.error(f"上传退宿媒体文件失败: {str(e)}")
        traceback.print_exc()
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='checkout_photo',
            action=f"上传退宿媒体文件失败",
            result="失败",
            error=str(e)
        )
        
        return jsonify({'success': False, 'message': f'上传失败: {str(e)}'})


@utility_room_meter_checkout_photo_bp.route('/media/<billing_period>/<room_id>/checkout/<user_id>/<filename>')
@login_required
@require_permission('utility.view')
def serve_checkout_media(billing_period, room_id, user_id, filename):
    """提供退宿媒体文件的访问"""
    try:
        # 获取文件路径
        file_path = room_meter_checkout_photo_manager.get_file_path(filename, billing_period, room_id, user_id)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logging.warning(f"尝试访问不存在的退宿媒体文件: {file_path}")
            return jsonify({'success': False, 'message': '文件不存在'}), 404
        
        # 获取文件的MIME类型
        mimetype = None
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp')):
            if filename.lower().endswith('.png'):
                mimetype = 'image/png'
            elif filename.lower().endswith(('.jpg', '.jpeg')):
                mimetype = 'image/jpeg'
            elif filename.lower().endswith('.gif'):
                mimetype = 'image/gif'
            elif filename.lower().endswith('.bmp'):
                mimetype = 'image/bmp'
            elif filename.lower().endswith('.webp'):
                mimetype = 'image/webp'
        elif filename.lower().endswith(('.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv')):
            if filename.lower().endswith('.mp4'):
                mimetype = 'video/mp4'
            elif filename.lower().endswith('.avi'):
                mimetype = 'video/x-msvideo'
            elif filename.lower().endswith('.mov'):
                mimetype = 'video/quicktime'
            elif filename.lower().endswith('.wmv'):
                mimetype = 'video/x-ms-wmv'
            elif filename.lower().endswith('.flv'):
                mimetype = 'video/x-flv'
            elif filename.lower().endswith('.mkv'):
                mimetype = 'video/x-matroska'
        
        # 使用send_file提供文件
        return send_file(file_path, mimetype=mimetype, conditional=True)
        
    except Exception as e:
        logging.error(f"提供退宿媒体文件访问失败: {str(e)}")
        return jsonify({'success': False, 'message': f'访问失败: {str(e)}'}), 500


@utility_room_meter_checkout_photo_bp.route('/delete_media', methods=['POST'])
@login_required
@require_permission('utility.edit')
def delete_checkout_media():
    """删除退宿媒体文件"""
    try:
        # 获取请求参数
        data = request.json
        billing_period = data.get('billing_period')
        room_id = data.get('room_id')
        user_id = data.get('user_id')
        filename = data.get('filename')
        
        # 验证参数
        if not billing_period or not room_id or not user_id or not filename:
            logging.warning(f"用户 {current_user.id} 尝试删除退宿媒体文件，但缺少必要参数")
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        # 删除文件
        success = room_meter_checkout_photo_manager.delete_file(filename, billing_period, room_id, user_id)
        
        if success:
            # 记录操作日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"删除退宿媒体文件: {filename} 从 {billing_period}/room_{room_id}/checkout_{user_id}",
                result="成功"
            )
            
            return jsonify({'success': True, 'message': '文件删除成功'})
        else:
            logging.warning(f"用户 {current_user.id} 尝试删除退宿媒体文件，但文件删除失败或文件不存在")
            return jsonify({'success': False, 'message': '文件删除失败或文件不存在'})
            
    except Exception as e:
        logging.error(f"删除退宿媒体文件失败: {str(e)}")
        traceback.print_exc()
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"删除退宿媒体文件失败",
            result="失败",
            error=str(e)
        )
        
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})


@utility_room_meter_checkout_photo_bp.route('/get_media_files', methods=['GET'])
@login_required
@require_permission('utility.view')
def get_checkout_media_files():
    """获取指定账期、房间和退宿费用子表的所有媒体文件"""
    try:
        # 获取请求参数
        billing_period = request.args.get('billing_period')
        room_id = request.args.get('room_id')
        user_id = request.args.get('user_id')
        
        # 诊断日志：打印接收到的参数
        logging.info(f"[退宿照片诊断] get_checkout_media_files 参数: billing_period={billing_period}, room_id={room_id}, user_id={user_id}")
        
        # 验证参数
        if not billing_period or not room_id or not user_id:
            logging.warning(f"用户 {current_user.id} 尝试获取退宿媒体文件，但缺少必要参数: billing_period={billing_period}, room_id={room_id}, user_id={user_id}")
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        # 获取媒体文件列表
        media_files = room_meter_checkout_photo_manager.get_media_files(billing_period, room_id, user_id)
        logging.info(f"[退宿照片诊断] get_media_files 返回文件数: {len(media_files)}, billing_period={billing_period}, room_id={room_id}, user_id={user_id}")
        
        # 转换为前端可用的格式
        result_files = []
        for file in media_files:
            file_url = room_meter_checkout_photo_manager.get_media_url(file['filename'], billing_period, room_id, user_id)
            result_files.append({
                'filename': file['filename'],
                'type': file['type'],
                'url': file_url,
                'upload_time': file.get('upload_time')
            })
        
        # 确保upload_time是JSON可序列化的
        for file in result_files:
            if file['upload_time'] and isinstance(file['upload_time'], datetime):
                file['upload_time'] = file['upload_time'].isoformat()
        
        return jsonify({
            'success': True,
            'files': result_files
        })
        
    except Exception as e:
        logging.error(f"获取退宿媒体文件列表失败: {str(e)}")
        traceback.print_exc()
        
        return jsonify({'success': False, 'message': f'获取失败: {str(e)}'})


# ========== 临时上传相关路由（退宿申请/审核页面使用，账期尚未确定时） ==========

@utility_room_meter_checkout_photo_bp.route('/upload_temp_media', methods=['POST'])
@login_required
@require_permission('utility.edit')
def upload_checkout_temp_media():
    """上传退宿照片到临时目录（退宿申请/审核页面，账期尚未确定）"""
    try:
        room_id = request.form.get('room_id')
        user_id = request.form.get('user_id')
        
        if not room_id or not user_id:
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有文件被上传'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '没有选择文件'})
        
        filename = room_meter_checkout_photo_manager.upload_to_temp(file, room_id, user_id)
        if not filename:
            return jsonify({'success': False, 'message': '不支持的文件格式'})
        
        file_url = room_meter_checkout_photo_manager.get_temp_media_url(filename, room_id, user_id)
        
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='checkout_photo',
            action=f"上传临时退宿媒体文件: {filename} 到 room_{room_id}/checkout_{user_id}",
            result="成功"
        )
        
        return jsonify({
            'success': True,
            'message': '上传成功',
            'filename': filename,
            'file_url': file_url
        })
        
    except Exception as e:
        logging.error(f"上传临时退宿媒体文件失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'上传失败: {str(e)}'})


@utility_room_meter_checkout_photo_bp.route('/temp_media/<room_id>/checkout/<user_id>/<filename>')
@login_required
@require_permission('utility.view')
def serve_checkout_temp_media(room_id, user_id, filename):
    """提供临时目录中退宿媒体文件的访问"""
    try:
        file_path = room_meter_checkout_photo_manager.get_temp_file_path(filename, room_id, user_id)
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': '文件不存在'}), 404
        
        mimetype = None
        if filename.lower().endswith('.png'):
            mimetype = 'image/png'
        elif filename.lower().endswith(('.jpg', '.jpeg')):
            mimetype = 'image/jpeg'
        elif filename.lower().endswith('.gif'):
            mimetype = 'image/gif'
        elif filename.lower().endswith('.bmp'):
            mimetype = 'image/bmp'
        elif filename.lower().endswith('.webp'):
            mimetype = 'image/webp'
        elif filename.lower().endswith('.mp4'):
            mimetype = 'video/mp4'
        elif filename.lower().endswith('.avi'):
            mimetype = 'video/x-msvideo'
        elif filename.lower().endswith('.mov'):
            mimetype = 'video/quicktime'
        elif filename.lower().endswith('.wmv'):
            mimetype = 'video/x-ms-wmv'
        elif filename.lower().endswith('.flv'):
            mimetype = 'video/x-flv'
        elif filename.lower().endswith('.mkv'):
            mimetype = 'video/x-matroska'
        
        return send_file(file_path, mimetype=mimetype, conditional=True)
        
    except Exception as e:
        logging.error(f"提供临时退宿媒体文件访问失败: {str(e)}")
        return jsonify({'success': False, 'message': f'访问失败: {str(e)}'}), 500


@utility_room_meter_checkout_photo_bp.route('/get_temp_media_files', methods=['GET'])
@login_required
@require_permission('utility.view')
def get_checkout_temp_media_files():
    """获取指定房间和用户临时目录中的所有退宿媒体文件"""
    try:
        room_id = request.args.get('room_id')
        user_id = request.args.get('user_id')
        
        if not room_id or not user_id:
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        media_files = room_meter_checkout_photo_manager.get_temp_files(room_id, user_id)
        
        result_files = []
        for file in media_files:
            file_url = room_meter_checkout_photo_manager.get_temp_media_url(file['filename'], room_id, user_id)
            result_files.append({
                'filename': file['filename'],
                'type': file['type'],
                'url': file_url,
                'upload_time': file.get('upload_time')
            })
        
        for file in result_files:
            if file['upload_time'] and isinstance(file['upload_time'], datetime):
                file['upload_time'] = file['upload_time'].isoformat()
        
        return jsonify({
            'success': True,
            'files': result_files
        })
        
    except Exception as e:
        logging.error(f"获取临时退宿媒体文件列表失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'获取失败: {str(e)}'})


@utility_room_meter_checkout_photo_bp.route('/delete_temp_media', methods=['POST'])
@login_required
@require_permission('utility.edit')
def delete_checkout_temp_media():
    """删除临时目录中的退宿媒体文件"""
    try:
        data = request.json
        room_id = data.get('room_id')
        user_id = data.get('user_id')
        filename = data.get('filename')
        
        if not room_id or not user_id or not filename:
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        success = room_meter_checkout_photo_manager.delete_temp_file(filename, room_id, user_id)
        
        if success:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"删除临时退宿媒体文件: {filename} 从 room_{room_id}/checkout_{user_id}",
                result="成功"
            )
            return jsonify({'success': True, 'message': '文件删除成功'})
        else:
            return jsonify({'success': False, 'message': '文件删除失败或文件不存在'})
            
    except Exception as e:
        logging.error(f"删除临时退宿媒体文件失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})


@utility_room_meter_checkout_photo_bp.route('/move_temp_to_billing', methods=['POST'])
@login_required
@require_permission('utility.edit')
def move_checkout_temp_to_billing():
    """将临时目录中的退宿文件移动到正式账期目录（退宿确认时调用）"""
    try:
        data = request.json
        room_id = data.get('room_id')
        user_id = data.get('user_id')
        billing_period = data.get('billing_period')
        
        if not room_id or not user_id or not billing_period:
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        result = room_meter_checkout_photo_manager.move_temp_to_billing_period(room_id, user_id, billing_period)
        
        if result['errors']:
            logging.warning(f"移动临时退宿文件部分失败: {result['errors']}")
        
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='checkout_photo',
            action=f"移动临时退宿照片到账期 {billing_period}/room_{room_id}/checkout_{user_id} [成功: {result['moved']}, 失败: {len(result['errors'])}]",
            result="成功" if not result['errors'] else "部分成功"
        )
        
        return jsonify({
            'success': True,
            'moved': result['moved'],
            'errors': result['errors'],
            'message': f"成功移动 {result['moved']} 个文件" + (f"，{len(result['errors'])} 个失败" if result['errors'] else "")
        })
        
    except Exception as e:
        logging.error(f"移动临时退宿文件到账期目录失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'移动失败: {str(e)}'})


@utility_room_meter_checkout_photo_bp.route('/clear_user_temp_media', methods=['POST'])
@login_required
@require_permission('utility.edit')
def clear_user_checkout_temp_media():
    """清理指定房间用户的临时退宿目录中的所有媒体文件"""
    try:
        data = request.json
        room_id = data.get('room_id')
        user_id = data.get('user_id')
        
        if not room_id or not user_id:
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        result = room_meter_checkout_photo_manager.clear_user_temp_files(room_id, user_id)
        
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"清理房间 {room_id} 用户 {user_id} 所有临时退宿照片 [删除: {result['deleted']}, 失败: {len(result['errors'])}]",
            result="成功" if not result['errors'] else "部分成功"
        )
        
        return jsonify({
            'success': True,
            'deleted': result['deleted'],
            'errors': result['errors'],
            'message': f"成功清理 {result['deleted']} 个文件" + (f"，{len(result['errors'])} 个失败" if result['errors'] else "")
        })
        
    except Exception as e:
        logging.error(f"清理用户临时退宿媒体文件失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'清理失败: {str(e)}'})


@utility_room_meter_checkout_photo_bp.route('/clear_all_temp_media', methods=['POST'])
@login_required
@require_permission('utility.edit')
def clear_all_checkout_temp_media():
    """清理所有房间用户的临时退宿目录中的媒体文件"""
    try:
        result = room_meter_checkout_photo_manager.clear_all_temp_files()
        
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"清理所有临时退宿照片 [删除: {result['deleted']}, 用户: {result['users_cleared']}, 失败: {len(result['errors'])}]",
            result="成功" if not result['errors'] else "部分成功"
        )
        
        return jsonify({
            'success': True,
            'deleted': result['deleted'],
            'users_cleared': result['users_cleared'],
            'errors': result['errors'],
            'message': f"成功清理 {result['users_cleared']} 个用户共 {result['deleted']} 个文件" + (f"，{len(result['errors'])} 个失败" if result['errors'] else "")
        })
        
    except Exception as e:
        logging.error(f"清理所有临时退宿媒体文件失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'清理失败: {str(e)}'})