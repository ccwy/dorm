from flask import Blueprint, request, jsonify, send_file
import logging
import os
import traceback
from datetime import datetime
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.log import log_operation
from utils.media.checkout_photo import checkout_photo_manager

utility_checkout_photo_bp = Blueprint('utility_checkout_photo', __name__, url_prefix='/utility-checkout')


@utility_checkout_photo_bp.route('/upload_media', methods=['POST'])
@login_required
@require_permission('utility.edit')
def upload_checkout_media():
    """上传退宿照片或视频"""
    try:
        # 获取请求参数
        billing_period = request.form.get('billing_period')
        room_id = request.form.get('room_id')
        checkout_id = request.form.get('checkout_id')
        
        # 验证参数
        if not billing_period or not room_id or not checkout_id:
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
        filename = checkout_photo_manager.upload_file(file, billing_period, room_id, checkout_id)
        if not filename:
            logging.warning(f"用户 {current_user.id} 尝试上传退宿媒体文件，但文件格式不支持")
            return jsonify({'success': False, 'message': '不支持的文件格式'})
        
        # 生成文件URL
        file_url = checkout_photo_manager.get_media_url(filename, billing_period, room_id, checkout_id)
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='checkout_photo',
            action=f"上传退宿媒体文件: {filename} 到 {billing_period}/room_{room_id}/checkout_{checkout_id}",
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


@utility_checkout_photo_bp.route('/media/<billing_period>/<room_id>/<checkout_id>/<filename>')
@login_required
@require_permission('utility.view')
def serve_checkout_media(billing_period, room_id, checkout_id, filename):
    """提供退宿媒体文件的访问"""
    try:
        # 获取文件路径
        file_path = checkout_photo_manager.get_file_path(filename, billing_period, room_id, checkout_id)
        
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


@utility_checkout_photo_bp.route('/delete_media', methods=['POST'])
@login_required
@require_permission('utility.edit')
def delete_checkout_media():
    """删除退宿媒体文件"""
    try:
        # 获取请求参数
        data = request.json
        billing_period = data.get('billing_period')
        room_id = data.get('room_id')
        checkout_id = data.get('checkout_id')
        filename = data.get('filename')
        
        # 验证参数
        if not billing_period or not room_id or not checkout_id or not filename:
            logging.warning(f"用户 {current_user.id} 尝试删除退宿媒体文件，但缺少必要参数")
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        # 删除文件
        success = checkout_photo_manager.delete_file(filename, billing_period, room_id, checkout_id)
        
        if success:
            # 记录操作日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"删除退宿媒体文件: {filename} 从 {billing_period}/room_{room_id}/checkout_{checkout_id}",
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


@utility_checkout_photo_bp.route('/get_media_files', methods=['GET'])
@login_required
@require_permission('utility.view')
def get_checkout_media_files():
    """获取指定账期、房间和退宿费用子表的所有媒体文件"""
    try:
        # 获取请求参数
        billing_period = request.args.get('billing_period')
        room_id = request.args.get('room_id')
        checkout_id = request.args.get('checkout_id')
        
        # 验证参数
        if not billing_period or not room_id or not checkout_id:
            logging.warning(f"用户 {current_user.id} 尝试获取退宿媒体文件，但缺少必要参数")
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        # 获取媒体文件列表
        media_files = checkout_photo_manager.get_media_files(billing_period, room_id, checkout_id)
        
        # 转换为前端可用的格式
        result_files = []
        for file in media_files:
            file_url = checkout_photo_manager.get_media_url(file['filename'], billing_period, room_id, checkout_id)
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