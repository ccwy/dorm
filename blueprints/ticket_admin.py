from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, abort
from utils.db import db
from models.ticket import Ticket
from models.ticket_reply import TicketReply
from models.user import User
from models.system_config import SystemConfig
from flask_login import login_required, current_user
from sqlalchemy import or_
from datetime import datetime
from utils.auth import admin_required
import logging
import os
from utils.ticket_photo import ticket_photo_manager
from utils.log import log_operation

# 创建管理端留言蓝图
ticket_admin_bp = Blueprint('ticket_admin', __name__, url_prefix='/admin/ticket')

# 管理端留言列表
@ticket_admin_bp.route('/list')
@login_required
@admin_required
def admin_ticket_list():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        # 获取查询参数
        search = request.args.get('search', '').strip()
        status = request.args.get('status', '').strip()
        category = request.args.get('category', '').strip()
        priority = request.args.get('priority', '').strip()
        
        # 分页参数处理
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)

        # 创建查询对象
        query = Ticket.query
        
        # 处理关键字搜索
        if search and search.strip():
            query = query.join(User).filter(
                Ticket.title.like(f'%{search}%') | 
                Ticket.description.like(f'%{search}%') |
                User.name.like(f'%{search}%')
            )
        
        # 处理状态搜索
        if status and status.strip():
            query = query.filter_by(status=status)
        
        # 处理分类搜索
        if category and category.strip():
            query = query.filter_by(category=category)
        
        # 处理优先级搜索
        if priority and priority.strip():
            query = query.filter_by(priority=priority)
        
        # 执行分页查询
        pagination = query.order_by(Ticket.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
        tickets = pagination.items
        
        # 获取所有状态、优先级用于筛选
        statuses = db.session.query(Ticket.status).distinct().all()
        priorities = db.session.query(Ticket.priority).distinct().all()
        
        status_list = [s[0] for s in statuses if s[0]]
        priority_list = [p[0] for p in priorities if p[0]]
        
        # 获取系统配置中的留言分类
        message_categories = SystemConfig.get_config_value('MESSAGE_CATEGORIES', ['宿舍问题', '设施维修', '水电费问题', '其他问题'])
        
        # 使用系统配置的分类覆盖数据库查询的分类
        category_list = message_categories
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员 [{user_id}] 访问留言管理列表",
            result="成功",
            module="ticket",
            operation_type="records"
        )
        logging.info(f"管理员 [{user_id}] 成功访问留言管理列表")
        return render_template('ticket_manage/admin_ticket_list.html', 
                              title="留言管理列表",
                              tickets=tickets, 
                              pagination=pagination, 
                              page=page, 
                              per_page=per_page,
                              search_query=search, 
                              status_filter=status, 
                              category_filter=category,
                              priority_filter=priority,
                              status_list=status_list, 
                              category_list=category_list, 
                              priority_list=priority_list,
                              message_categories=message_categories)
    except Exception as e:
        logging.error(f"获取管理端留言列表失败: {str(e)}")
        flash('获取留言列表失败，请稍后重试', 'error')
        return redirect(url_for('index'))

# 查看留言详情
@ticket_admin_bp.route('/detail/<int:ticket_id>')
@login_required
@admin_required
def ticket_detail(ticket_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        # 获取留言
        ticket = Ticket.get_by_id(ticket_id)
        
        # 检查权限
        if not ticket:
            flash('留言不存在', 'error')
            logging.error("留言不存在")
            return redirect(url_for('ticket_admin.admin_ticket_list'))
        
        # 获取留言回复
        replies = TicketReply.query.filter_by(ticket_id=ticket_id).order_by(TicketReply.created_at).all()
        
        # 获取系统配置中的留言分类
        message_categories = SystemConfig.get_config_value('MESSAGE_CATEGORIES', ['宿舍问题', '设施维修', '水电费问题', '其他问题'])

        # 获取留言的媒体文件列表（管理端）
        media_files = ticket_photo_manager.get_media_files(ticket_id, is_admin=True)

        logging.info(f"管理员[{user_id}]成功查看留言详情，留言ID: {ticket_id}")
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 {user_id} 查看留言详情，留言ID: {ticket_id}",
            result="成功",
            module="ticket",
            operation_type="records"
        )
        return render_template('ticket_manage/admin_ticket_detail.html', title="留言详情", ticket=ticket, replies=replies, message_categories=message_categories, media_files=media_files)
    except Exception as e:
        logging.error(f"查看留言详情失败: {str(e)}")
        flash('查看留言详情失败，请稍后重试', 'error')
        return redirect(url_for('ticket_admin.admin_ticket_list'))

# 编辑留言
@ticket_admin_bp.route('/update/<int:ticket_id>', methods=['POST'])
@login_required
@admin_required
def update_ticket(ticket_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        logging.debug(f"管理员[{user_id}]尝试更新留言，留言ID: {ticket_id}")
        
        # 获取留言
        ticket = Ticket.get_by_id(ticket_id)
        
        # 检查权限
        if not ticket:
            logging.warning(f"管理员[{user_id}]尝试更新不存在的留言，留言ID: {ticket_id}")
            flash('留言不存在', 'error')
            return redirect(url_for('ticket_admin.admin_ticket_list'))
        
        # 获取表单数据
        title = request.form.get('title').strip()
        description = request.form.get('description').strip()
        category = request.form.get('category').strip()
        priority = request.form.get('priority').strip()
        status = request.form.get('status').strip()
        
        # 验证必填字段
        if not title or not description or not category or not priority or not status:
            logging.warning(f"管理员[{user_id}]更新留言时必填字段为空，留言ID: {ticket_id}")
            flash('请填写所有必填字段', 'error')
            return redirect(url_for('ticket_admin.admin_ticket_list', ticket_id=ticket_id))
        
        # 更新留言
        ticket.update(
            title=title,
            description=description,
            category=category,
            priority=priority,
            status=status
        )
        
        logging.info(f"管理员[{user_id}]成功更新留言，留言ID: {ticket_id}")
        flash('留言更新成功', 'success')
        return redirect(url_for('ticket_admin.admin_ticket_list', ticket_id=ticket_id))
    except Exception as e:
        error_message = str(e)
        logging.error(f"管理员[{current_user.id}]更新留言失败，留言ID: {ticket_id}，错误: {error_message}")
        flash('更新留言失败，请稍后重试', 'error')
        return redirect(url_for('ticket_admin.admin_ticket_list', ticket_id=ticket_id))

# 添加留言回复
@ticket_admin_bp.route('/add_reply/<int:ticket_id>', methods=['POST'])
@login_required
@admin_required
def add_ticket_reply(ticket_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        logging.debug(f"管理员[{user_id}]尝试回复留言，留言ID: {ticket_id}")
        
        # 获取留言
        ticket = Ticket.get_by_id(ticket_id)
        
        # 检查权限
        if not ticket:
            logging.warning(f"管理员[{user_id}]尝试回复不存在的留言，留言ID: {ticket_id}")
            flash('留言不存在', 'error')
            return redirect(url_for('ticket_admin.admin_ticket_list'))
        
        # 获取回复内容
        content = request.form.get('content').strip()
        
        if not content:
            logging.warning(f"管理员[{user_id}]回复留言内容为空，留言ID: {ticket_id}")
            flash('请输入回复内容', 'error')
            return redirect(url_for('ticket_admin.ticket_detail', ticket_id=ticket_id))
        
        # 添加回复
        TicketReply.create(ticket_id, user_id, content)
        
        # 如果是管理员回复，可以将留言状态改为处理中
        if ticket.status == '待处理':
            ticket.update(status='处理中')
        
        # 自动将已关闭的留言状态改为处理中
        if ticket.status == '已关闭':
            ticket.update(status='处理中')
            ticket.closed_at = None
        
        # 检查是否需要回复并关闭
        if request.form.get('reply_and_close') == '1':
            ticket.update(status='已关闭')
            logging.info(f"管理员[{user_id}]回复留言并关闭成功，留言ID: {ticket_id}")
            flash('回复添加成功，留言已关闭', 'success')
        else:
            logging.info(f"管理员[{user_id}]回复留言成功，留言ID: {ticket_id}")
            flash('回复添加成功', 'success')
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员[{user_id}]回复留言 {ticket_id} 成功",
            result="成功",
            module="ticket",
            operation_type="reply"
        )
        return redirect(url_for('ticket_admin.ticket_detail', ticket_id=ticket_id))
    except Exception as e:
        logging.error(f"管理员[{current_user.id}]添加留言回复失败，留言ID: {ticket_id}，错误: {str(e)}")
        flash('添加回复失败，请稍后重试', 'error')
        return redirect(url_for('ticket_admin.ticket_detail', ticket_id=ticket_id))

# 关闭留言
@ticket_admin_bp.route('/close/<int:ticket_id>', methods=['POST'])
@login_required
@admin_required
def close_ticket(ticket_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        logging.debug(f"管理员[{user_id}]尝试关闭留言，留言ID: {ticket_id}")
        
        # 获取留言
        ticket = Ticket.get_by_id(ticket_id)
        
        # 检查权限
        if not ticket:
            logging.warning(f"管理员[{user_id}]尝试关闭不存在的留言，留言ID: {ticket_id}")
            flash('留言不存在', 'error')
            return redirect(url_for('ticket_admin.admin_ticket_list'))
        
        # 关闭留言
        ticket.update(status='已关闭')
        logging.info(f"管理员[{user_id}]关闭留言成功，留言ID: {ticket_id}")
        flash('留言已关闭', 'success')
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 {user_id} 关闭留言 {ticket_id} 成功",
            result="成功",
            module="ticket",
            operation_type="close"
        )
        return redirect(url_for('ticket_admin.admin_ticket_list'))
    except Exception as e:
        logging.error(f"管理员[{current_user.id}]关闭留言失败，留言ID: {ticket_id}，错误: {str(e)}")
        flash('关闭留言失败，请稍后重试', 'error')
        return redirect(url_for('ticket_admin.admin_ticket_list'))


# 删除留言
@ticket_admin_bp.route('/delete/<int:ticket_id>', methods=['POST'])
@login_required
@admin_required
def delete_ticket(ticket_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        logging.debug(f"管理员[{user_id}]尝试删除留言，留言ID: {ticket_id}")
        
        # 获取留言
        ticket = Ticket.get_by_id(ticket_id)
        
        # 检查权限
        if not ticket:
            logging.warning(f"管理员[{user_id}]尝试删除不存在的留言，留言ID: {ticket_id}")
            flash('留言不存在', 'error')
            return redirect(url_for('ticket_admin.admin_ticket_list'))
        
        # 删除留言照片
        ticket_photo_manager.delete_ticket_directory(ticket_id)
        logging.info(f"管理员[{user_id}]成功删除留言关联媒体文件，留言ID: {ticket_id}")
        
        # 删除留言
        ticket.delete()
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 {user_id} 删除留言 {ticket_id} 成功",
            result="成功",
            module="ticket",
            operation_type="delete"
        )
        logging.info(f"管理员[{user_id}]成功删除留言，留言ID: {ticket_id}")
        flash(f'留言删除成功，留言ID: {ticket_id}', 'success')
        return redirect(url_for('ticket_admin.admin_ticket_list'))
    except Exception as e:
        error_message = str(e)
        logging.error(f"管理员[{current_user.id}]删除留言失败，留言ID: {ticket_id}，错误: {error_message}")
        flash('删除留言失败，请稍后重试', 'error')
        return redirect(url_for('ticket_admin.admin_ticket_list'))

# 批量删除留言
@ticket_admin_bp.route('/batch_delete', methods=['POST'])
@login_required
@admin_required
def batch_delete_tickets():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
       
        # 获取留言ID列表
        ticket_ids = request.form.getlist('ticket_ids[]')
        
        if not ticket_ids:
            logging.warning("请选择要删除的留言")
            flash('请选择要删除的留言', 'error')
            return redirect(url_for('ticket_admin.admin_ticket_list'))
        
        # 转换为整数列表，添加错误处理
        valid_ticket_ids = []
        for id_str in ticket_ids:
            try:
                if id_str and id_str.strip() != '':  # 确保不为空
                    valid_ticket_ids.append(int(id_str))
            except (ValueError, TypeError):
                # 忽略无效的ID，继续处理其他有效ID
                continue
        
        # 如果没有有效ID，显示提示信息
        if not valid_ticket_ids:
            logging.warning("请选择有效的留言进行删除")
            flash('请选择有效的留言进行删除', 'error')
            return redirect(url_for('ticket_admin.admin_ticket_list'))
        
        # 使用有效的ID列表
        ticket_ids = valid_ticket_ids
        
        logging.info(f"用户[{user_id}] - 开始删除{len(ticket_ids)}条留言")
        
        # 删除每个留言的照片
        for ticket_id in ticket_ids:
            ticket_photo_manager.delete_ticket_directory(ticket_id)
        
        # 批量删除留言记录
        Ticket.batch_delete(ticket_ids)
        
        logging.info(f"管理员[{user_id}]成功删除{len(ticket_ids)}条留言")
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员[{user_id}]成功删除{len(ticket_ids)}条留言",
            result="成功",
            module="ticket",
            operation_type="delete"
        )
        flash(f'已成功删除{len(ticket_ids)}条留言', 'success')
        return redirect(url_for('ticket_admin.admin_ticket_list'))
    except Exception as e:
        logging.error(f"批量删除留言失败: {str(e)}")
        flash('批量删除留言失败，请稍后重试', 'error')
        return redirect(url_for('ticket_admin.admin_ticket_list'))
        
# 删除所有留言
@ticket_admin_bp.route('/delete_all', methods=['POST'])
@login_required
@admin_required
def delete_all_tickets():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        logging.debug(f"管理员[{user_id}]尝试删除所有留言")
        
        # 获取所有留言
        tickets = Ticket.get_all()
        
        if not tickets:
            logging.error("没有可删除的留言")
            flash('没有可删除的留言', 'info')
            return redirect(url_for('ticket_admin.admin_ticket_list'))
        
        # 获取所有留言ID
        ticket_ids = [ticket.id for ticket in tickets]
        
        # 删除每个留言的照片
        for ticket_id in ticket_ids:
            ticket_photo_manager.delete_ticket_directory(ticket_id)
        
        # 批量删除
        Ticket.batch_delete(ticket_ids)
        
        logging.info(f"管理员[{user_id}]成功删除所有留言，共{len(ticket_ids)}条")
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员[{user_id}]成功删除{len(ticket_ids)}条留言",
            result="成功",
            module="ticket",
            operation_type="delete"
        )
        flash('成功删除所有留言', 'success')
        return redirect(url_for('ticket_admin.admin_ticket_list'))
    except Exception as e:
        logging.error(f"删除所有留言失败: {str(e)}")
        flash('删除所有留言失败，请稍后重试', 'error')
        return redirect(url_for('ticket_admin.admin_ticket_list'))

# 访问留言媒体文件
@ticket_admin_bp.route('/media/<int:ticket_id>/<path:filename>')
@login_required
@admin_required
def serve_ticket_media(ticket_id, filename):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            abort(403)
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        logging.debug(f"管理员 {user_id} 尝试访问留言 {ticket_id} 的媒体文件: {filename}")
        
        # 获取留言
        ticket = Ticket.get_by_id(ticket_id)
        
        # 检查权限
        if not ticket:
            logging.warning(f"管理员 {user_id} 尝试访问不存在的留言 {ticket_id} 的媒体文件")
            abort(404)
        
        # 获取文件路径
        file_path = ticket_photo_manager.get_file_path(filename, ticket_id)
        
        # 检查文件是否存在
        if not file_path or not os.path.exists(file_path):
            logging.warning(f"管理员 {user_id} 尝试访问留言 {ticket_id} 的不存在文件: {filename}")
            abort(404)
        
        # 获取文件信息
        file_size = os.path.getsize(file_path)
        logging.debug(f"文件 {filename} 大小: {file_size} 字节")
        
        # 根据文件扩展名设置MIME类型
        file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        mime_type = 'application/octet-stream'  # 默认MIME类型
        if file_ext in ['jpg', 'jpeg']:
            mime_type = 'image/jpeg'
        elif file_ext == 'png':
            mime_type = 'image/png'
        elif file_ext == 'gif':
            mime_type = 'image/gif'
        elif file_ext == 'bmp':
            mime_type = 'image/bmp'
        elif file_ext == 'webp':
            mime_type = 'image/webp'
        elif file_ext in ['mp4', 'm4v']:
            mime_type = 'video/mp4'
        elif file_ext == 'webm':
            mime_type = 'video/webm'
        elif file_ext == 'avi':
            mime_type = 'video/x-msvideo'
        elif file_ext == 'mov':
            mime_type = 'video/quicktime'
         # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员[{user_id}]访问留言媒体文件成功，留言ID: {ticket_id}，文件名: {filename}",
            result="成功",
            module="ticket",
            operation_type="records"
        )
        logging.info(f"管理员[{user_id}]成功访问留言媒体文件，留言ID: {ticket_id}，文件名: {filename}")
        # 发送文件
        return send_file(file_path, mimetype=mime_type)
    except Exception as e:
        logging.error(f"访问文件失败: {str(e)}")
        abort(404)


# 处理留言媒体文件上传
@ticket_admin_bp.route('/upload_media/<int:ticket_id>', methods=['POST'])
@login_required
@admin_required
def upload_ticket_media(ticket_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            return {'success': False, 'message': '用户信息无效，请重新登录'}
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        logging.debug(f"管理员[{user_id}]尝试上传留言媒体文件，留言ID: {ticket_id}")
        
        # 获取留言
        ticket = Ticket.get_by_id(ticket_id)
        
        # 检查权限
        if not ticket:
            logging.warning(f"管理员[{user_id}]尝试上传不存在的留言媒体文件，留言ID: {ticket_id}")
            return {'success': False, 'message': '留言不存在'}
        
        # 检查是否有文件上传
        if 'file' not in request.files:
            logging.warning(f"管理员[{user_id}]上传留言媒体文件时未选择文件，留言ID: {ticket_id}")
            return {'success': False, 'message': '请选择要上传的文件'}
        
        file = request.files['file']
        
        # 检查文件是否为空
        if file.filename == '':
            logging.warning(f"管理员[{user_id}]上传留言媒体文件时文件名为空，留言ID: {ticket_id}")
            return {'success': False, 'message': '请选择要上传的文件'}
        
        # 上传文件
        try:
            filename = ticket_photo_manager.upload_file(file, ticket_id)
            logging.info(f"管理员[{user_id}]上传留言媒体文件成功，留言ID: {ticket_id}，文件名: {filename}")
            # 返回JSON响应而不是重定向
            # 记录操作日志
            log_operation(
                user_id=user_id,
                action=f"用户 {user_id} 上传留言媒体文件 {filename} 成功",
                result="成功",
                module="ticket",
                operation_type="upload_media"
            )
            return {'success': True, 'message': '文件上传成功', 'filename': filename}
        except Exception as e:
            logging.error(f"管理员[{user_id}]文件上传失败，留言ID: {ticket_id}，错误: {str(e)}")
            return {'success': False, 'message': f'文件上传失败: {str(e)}'}
    except Exception as e:
        logging.error(f"管理员[{current_user.id}]处理文件上传失败，留言ID: {ticket_id}，错误: {str(e)}")
        return {'success': False, 'message': f'处理文件上传失败: {str(e)}'}

# 批量关闭留言
@ticket_admin_bp.route('/batch_close', methods=['POST'])
@login_required
@admin_required
def batch_close_tickets():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        # 获取留言ID列表
        ticket_ids = request.form.getlist('ticket_ids[]')
        
        if not ticket_ids:
            logging.warning("请选择要关闭的留言")
            flash('请选择要关闭的留言', 'error')
            return redirect(url_for('ticket_admin.admin_ticket_list'))
        
        # 转换为整数列表，添加错误处理
        valid_ticket_ids = []
        for id_str in ticket_ids:
            try:
                if id_str and id_str.strip() != '':  # 确保不为空
                    valid_ticket_ids.append(int(id_str))
            except (ValueError, TypeError):
                # 忽略无效的ID，继续处理其他有效ID
                continue
        
        # 如果没有有效ID，显示提示信息
        if not valid_ticket_ids:
            logging.warning("请选择有效的留言进行关闭")
            flash('请选择有效的留言进行关闭', 'error')
            return redirect(url_for('ticket_admin.admin_ticket_list'))
        
        # 使用有效的ID列表
        ticket_ids = valid_ticket_ids
        
        logging.info(f"用户[{user_id}] - 开始关闭{len(ticket_ids)}条留言")
        
        # 批量关闭留言
        tickets = Ticket.query.filter(Ticket.id.in_(ticket_ids)).all()
        for ticket in tickets:
            if ticket.status != '已关闭':  # 只有未关闭的留言才需要处理
                ticket.update(status='已关闭')
        
        logging.info(f"管理员[{user_id}]成功关闭{len(ticket_ids)}条留言")
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员[{user_id}]成功关闭{len(ticket_ids)}条留言",
            result="成功",
            module="ticket",
            operation_type="close"
        )
        flash(f'已成功关闭{len(ticket_ids)}条留言', 'success')
        return redirect(url_for('ticket_admin.admin_ticket_list'))
    except Exception as e:
        logging.error(f"批量关闭留言失败: {str(e)}")
        flash('批量关闭留言失败，请稍后重试', 'error')
        return redirect(url_for('ticket_admin.admin_ticket_list'))

# 关闭所有留言
@ticket_admin_bp.route('/close_all', methods=['POST'])
@login_required
@admin_required
def close_all_tickets():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        logging.debug(f"管理员[{user_id}]尝试关闭所有留言")
        
        # 获取所有未关闭的留言
        tickets = Ticket.query.filter(Ticket.status != '已关闭').all()
        
        if not tickets:
            logging.error("没有可关闭的留言")
            flash('没有可关闭的留言', 'info')
            return redirect(url_for('ticket_admin.admin_ticket_list'))
        
        # 批量关闭
        for ticket in tickets:
            ticket.update(status='已关闭')
        
        logging.info(f"管理员[{user_id}]成功关闭所有留言，共{len(tickets)}条")
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员[{user_id}]成功关闭{len(tickets)}条留言",
            result="成功",
            module="ticket",
            operation_type="close"
        )
        flash('成功关闭所有留言', 'success')
        return redirect(url_for('ticket_admin.admin_ticket_list'))
    except Exception as e:
        logging.error(f"关闭所有留言失败: {str(e)}")
        flash('关闭所有留言失败，请稍后重试', 'error')
        return redirect(url_for('ticket_admin.admin_ticket_list'))

# 处理留言媒体文件删除
@ticket_admin_bp.route('/delete_media/<int:ticket_id>/<path:filename>', methods=['POST'])
@login_required
@admin_required
def delete_ticket_media(ticket_id, filename):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        logging.debug(f"管理员[{user_id}]尝试删除留言媒体文件，留言ID: {ticket_id}，文件名: {filename}")
        
        # 获取留言
        ticket = Ticket.get_by_id(ticket_id)
        
        # 检查权限
        if not ticket:
            logging.warning(f"管理员[{user_id}]尝试删除不存在的留言媒体文件，留言ID: {ticket_id}，文件名: {filename}")
            flash('留言不存在', 'error')
            return redirect(url_for('ticket_admin.admin_ticket_list'))
        
        # 删除文件
        try:
            ticket_photo_manager.delete_file(filename, ticket_id)
            flash('文件删除成功', 'success')
            logging.info(f"管理员[{user_id}]删除留言媒体文件成功，留言ID: {ticket_id}，文件名: {filename}")
            # 记录操作日志
            log_operation(
                user_id=user_id,
                action=f"管理员[{user_id}]删除留言媒体文件成功，留言ID: {ticket_id}，文件名: {filename}",
                result="成功",
                module="ticket",
                operation_type="delete_media"
            )
        except Exception as e:
            logging.error(f"管理员[{user_id}]文件删除失败，留言ID: {ticket_id}，文件名: {filename}，错误: {str(e)}")
            flash(f'文件删除失败: {str(e)}', 'error')
        
        return redirect(url_for('ticket_admin.ticket_detail', ticket_id=ticket_id))
    except Exception as e:
        logging.error(f"管理员[{current_user.id}]处理文件删除失败，留言ID: {ticket_id}，文件名: {filename}，错误: {str(e)}")
        flash('处理文件删除失败，请稍后重试', 'error')
        return redirect(url_for('ticket_admin.ticket_detail', ticket_id=ticket_id))

