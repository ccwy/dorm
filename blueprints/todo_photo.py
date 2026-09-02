from flask import Blueprint, request, jsonify, send_from_directory
from flask_login import login_required, current_user
from utils.log import log_operation
import logging
from utils.todo_photo import TodoMediaManager
import os
from models.todo import Todo
from utils.auth import require_permission
from .todo import todo_bp  # 导入todo蓝图

@todo_bp.route('/upload', methods=['POST'])
@login_required
@require_permission('todo.edit')
def upload_media():
    """上传待办事项照片或视频"""
    try:
        # 获取表单数据
        todo_id = request.form.get('todo_id')
        
        # 验证必要参数
        if not todo_id:
            logging.warning(f"用户 {current_user.id} 尝试上传待办事项媒体文件，但缺少待办事项ID参数")
            return jsonify({'success': False, 'message': '缺少待办事项ID参数'})
        
        # 检查是否有文件上传
        if 'media_file' not in request.files:
            logging.warning(f"用户 {current_user.id} 尝试上传待办事项媒体文件，但没有文件被上传")
            return jsonify({'success': False, 'message': '没有文件被上传'})
        
        file = request.files['media_file']
        
        # 检查文件名是否为空
        if file.filename == '':
            logging.warning(f"用户 {current_user.id} 尝试上传待办事项媒体文件，但没有选择文件")
            return jsonify({'success': False, 'message': '没有选择文件'})
        
        # 验证待办事项是否存在，并且用户有访问权限
        todo = Todo.get_by_id(todo_id)
        if not todo:
            logging.warning(f"用户 {current_user.id} 尝试上传媒体文件到不存在的待办事项，ID: {todo_id}")
            return jsonify({'success': False, 'message': '待办事项不存在'})
        
        # 检查用户权限：超级管理员或待办事项创建者或负责人
        if not ((current_user.user_role and current_user.user_role.code == 'super_admin') or todo.created_by == current_user.id or todo.assignee == current_user.id):
            logging.warning(f"用户 {current_user.id} 尝试上传媒体文件到无权限的待办事项，ID: {todo_id}")
            return jsonify({'success': False, 'message': '您没有权限上传此待办事项的媒体文件'})
        
        # 上传文件
        filename = TodoMediaManager.upload_file(file, todo_id)
        
        if filename:
            # 生成文件URL
            file_url = TodoMediaManager.get_media_url(filename, todo_id)
            logging.info(f"用户 {current_user.id} 上传待办事项媒体文件成功: {filename}")
            # 记录操作日志
            log_operation(
                user_id=current_user.id,
                module='todo',
                operation_type='upload_media',
                action=f"上传待办事项ID {todo_id} 的媒体文件: {filename}",
                result="成功"
            )
            
            return jsonify({
                'success': True,
                'message': '文件上传成功',
                'filename': filename,
                'url': file_url
            })
        else:
            logging.warning(f"用户 {current_user.id} 尝试上传待办事项媒体文件，但文件格式不支持")
            return jsonify({'success': False, 'message': '文件格式不支持'})
    except Exception as e:
        logging.error(f"上传待办事项媒体文件时发生错误: {str(e)}")
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='todo',
            operation_type='upload_media',
            action=f"上传待办事项媒体文件失败: {str(e)}",
            result="失败"
        )
        return jsonify({'success': False, 'message': f'上传失败: {str(e)}'})

@todo_bp.route('/delete_file', methods=['POST'])
@login_required
@require_permission('todo.edit')
def delete_file():
    """删除待办事项照片或视频"""
    try:
        # 获取请求数据
        data = request.get_json()
        todo_id = data.get('todo_id')
        filename = data.get('filename')
        
        # 验证必要参数
        if not todo_id or not filename:
            logging.warning(f"用户 {current_user.id} 尝试删除待办事项媒体文件，但缺少必要参数")
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        # 验证todo_id是否为整数
        try:
            todo_id = int(todo_id)
        except ValueError:
            logging.warning(f"用户 {current_user.id} 提供的待办事项ID格式无效: {todo_id}")
            return jsonify({'success': False, 'message': '待办事项ID格式无效'})
        
        # 验证待办事项是否存在，并且用户有访问权限
        todo = Todo.get_by_id(todo_id)
        if not todo:
            logging.warning(f"用户 {current_user.id} 尝试删除媒体文件到不存在的待办事项，ID: {todo_id}")
            return jsonify({'success': False, 'message': '待办事项不存在'})
        
        # 检查用户权限：超级管理员或待办事项创建者或负责人
        if not ((current_user.user_role and current_user.user_role.code == 'super_admin') or todo.created_by == current_user.id or todo.assignee == current_user.id):
            logging.warning(f"用户 {current_user.id} 尝试删除媒体文件到无权限的待办事项，ID: {todo_id}")
            return jsonify({'success': False, 'message': '您没有权限删除此待办事项的媒体文件'})
        
        # 删除文件
        success = TodoMediaManager.delete_file(filename, todo_id)
        logging.info(f"用户 {current_user.id} 尝试删除待办事项ID为 {todo_id} 的媒体文件: {filename}")
        if success:
            # 记录操作日志
            log_operation(
                user_id=current_user.id,
                module='todo',
                operation_type='delete_media',
                action=f"删除待办事项ID为 {todo_id} 的媒体文件: {filename}",
                result="成功"
            )
            logging.info(f"用户 {current_user.id} 删除待办事项媒体文件成功: {filename}")
            return jsonify({'success': True, 'message': '文件删除成功'})
        else:
            logging.warning(f"用户 {current_user.id} 尝试删除待办事项媒体文件，但文件删除失败或文件不存在")
            return jsonify({'success': False, 'message': '文件删除失败或文件不存在'})
    except Exception as e:
        logging.error(f"删除待办事项媒体文件时发生错误: {str(e)}")
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='todo',
            operation_type='delete_media',
            action=f"删除待办事项媒体文件失败: {str(e)}",
            result="失败"
        )
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})

@todo_bp.route('/<int:todo_id>/<path:filename>')
@login_required
@require_permission('todo.view')
def serve_media_file(todo_id, filename):
    """提供待办事项媒体文件的访问"""
    try:
        # 验证待办事项是否存在，并且用户有访问权限
        todo = Todo.get_by_id(todo_id)
        if not todo:
            logging.warning(f"用户 {current_user.id} 尝试访问不存在的待办事项媒体文件，待办事项ID: {todo_id}")
            return jsonify({'success': False, 'message': '待办事项不存在'}), 404
        
        # 检查用户权限：超级管理员或待办事项创建者或负责人
        if not ((current_user.user_role and current_user.user_role.code == 'super_admin') or todo.created_by == current_user.id or todo.assignee == current_user.id):
            logging.warning(f"用户 {current_user.id} 尝试访问无权限的待办事项媒体文件，待办事项ID: {todo_id}")
            return jsonify({'success': False, 'message': '您没有权限访问此待办事项的媒体文件'}), 403
        
        # 获取文件路径
        todo_dir = TodoMediaManager.ensure_todo_directory_exists(todo_id)
        file_path = os.path.join(todo_dir, filename)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logging.warning(f"用户 {current_user.id} 尝试访问不存在的媒体文件: {filename}，待办事项ID: {todo_id}")
            return jsonify({'success': False, 'message': '文件不存在'}), 404
        
        # 提供文件下载
        return send_from_directory(todo_dir, filename)
    except Exception as e:
        logging.error(f"提供待办事项媒体文件时发生错误: {str(e)}")
        return jsonify({'success': False, 'message': f'访问文件失败: {str(e)}'}), 500