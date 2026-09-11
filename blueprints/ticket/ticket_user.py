from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, abort
from utils.db import db
from models.ticket.ticket import Ticket
from models.ticket.ticket_reply import TicketReply
from models.user.user import User
from models.system_config.system_config import SystemConfig
from flask_login import login_required, current_user
from utils.auth import require_permission
from datetime import datetime
import logging
import os
from utils.log import log_operation


# 创建用户端留言蓝图
ticket_user_bp = Blueprint('ticket_user', __name__, url_prefix='/user/ticket')

# 用户端留言列表
@ticket_user_bp.route('/list')
@login_required
@require_permission('ticket.view')
def user_ticket_list():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        # 分页参数处理
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)

        # 获取当前用户的留言并分页
        query = Ticket.query.filter_by(user_id=user_id).order_by(Ticket.created_at.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        tickets = pagination.items
        
        # 获取留言分类配置，使用与其他页面相同的get_config_value方法
        message_categories = SystemConfig.get_config_value('MESSAGE_CATEGORIES', ['宿舍问题', '设施维修', '水电费问题', '其他问题'])

        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 [{user_id}] 访问留言管理列表",
            result="成功",
            module="ticket",
            operation_type="records"
        )
        logging.info(f"用户 [{user_id}] 成功访问留言列表")
        return render_template('ticket_manage/user_ticket_list.html', title="留言列表", 
                              tickets=tickets, pagination=pagination, page=page, per_page=per_page,
                              message_categories=message_categories)
    except Exception as e:
        logging.error(f"获取用户留言列表失败: {str(e)}")
        flash('获取留言列表失败，请稍后重试', 'error')
        return redirect(url_for('index'))

# 创建留言
@ticket_user_bp.route('/create', methods=['POST'])
@login_required
@require_permission('ticket.create')
def create_ticket():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        logging.debug(f"用户 {user_id} 开始创建留言")
        
        title = request.form.get('title').strip()
        description = request.form.get('description').strip()
        category = request.form.get('category').strip()
        priority = request.form.get('priority', '一般').strip()
        
        logging.debug(f"留言创建参数 - 标题: {title}, 分类: {category}, 优先级: {priority}")
        
        # 验证参数
        if not title or not description or not category:
            logging.warning(f"用户 {user_id} 创建留言参数不完整: 标题={'有' if title else '无'}, 描述={'有' if description else '无'}, 分类={'有' if category else '无'}")
            flash('请填写所有必填字段', 'error')
            return redirect(url_for('ticket_user.user_ticket_list'))
        
        # 创建留言
        ticket = Ticket.create(user_id, title, description, category, priority)
        logging.debug(f"用户 {user_id} 创建留言成功，标题：{title}，留言ID: {ticket.id}")
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 {user_id} 创建留言成功，标题：{title}，留言ID: {ticket.id}",
            result="成功",
            module="ticket",
            operation_type="create"
        )
        
        flash('留言创建成功', 'success')
        return redirect(url_for('ticket_user.user_ticket_list'))
    except Exception as e:
        logging.error(f"创建留言失败: {str(e)}")
        logging.debug(f"创建留言异常详情 - 用户ID: {current_user.id if hasattr(current_user, 'id') else '未知'}, 错误类型: {type(e).__name__}, 错误信息: {str(e)}")
        flash('创建留言失败，请稍后重试', 'error')
        return redirect(url_for('ticket_user.user_ticket_list'))

# 查看留言详情
@ticket_user_bp.route('/detail/<int:ticket_id>')
@login_required
@require_permission('ticket.view')
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
        if not ticket or ticket.user_id != user_id:
            logging.warning(f"用户 {user_id} 尝试查看不属于自己的留言 {ticket_id}")
            flash('无权查看此留言', 'error')
            return redirect(url_for('ticket_user.user_ticket_list'))
        
        # 获取留言回复
        replies = TicketReply.query.filter_by(ticket_id=ticket_id).order_by(TicketReply.created_at).all()
        
        # 获取留言媒体文件
        from utils.ticket_photo import TicketPhotoManager
        media_files = TicketPhotoManager.get_media_files(ticket_id)
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 [{user_id}] 查看留言详情，标题：{ticket.title}，留言ID: {ticket_id}",
            result="成功",
            module="ticket",
            operation_type="records"
        )
        logging.info(f"用户 [{user_id}] 成功查看留言详情，留言ID: {ticket_id}")
        
        return render_template('ticket_manage/user_ticket_detail.html', title="留言详情", 
                              ticket=ticket, replies=replies, media_files=media_files)
    except Exception as e:
        logging.error(f"查看留言详情失败: {str(e)}")
        flash('查看留言详情失败，请稍后重试', 'error')
        return redirect(url_for('ticket_user.user_ticket_list'))

# 添加留言回复
@ticket_user_bp.route('/add_reply/<int:ticket_id>', methods=['POST'])
@login_required
@require_permission('ticket.create')
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
        logging.debug(f"用户 {user_id} 开始回复留言 {ticket_id}")
        
        # 获取留言
        ticket = Ticket.get_by_id(ticket_id)
        
        # 检查权限
        if not ticket:
            logging.warning(f"用户 {user_id} 尝试回复不存在的留言 {ticket_id}")
            flash('无权回复此留言', 'error')
            return redirect(url_for('ticket_user.ticket_detail', ticket_id=ticket_id))
        if ticket.user_id != user_id:
            logging.warning(f"用户 {user_id} 尝试回复不属于自己的留言 {ticket_id}")
            flash('无权回复此留言', 'error')
            return redirect(url_for('ticket_user.ticket_detail', ticket_id=ticket_id))
        
        # 获取回复内容
        content = request.form.get('content').strip()
        
        if not content:
            logging.warning(f"用户 {user_id} 回复留言 {ticket_id} 时内容为空")
            flash('请输入回复内容', 'error')
            return redirect(url_for('ticket_user.ticket_detail', ticket_id=ticket_id))
        
        # 记录回复内容长度，但不记录具体内容以保护隐私
        logging.debug(f"用户 {user_id} 回复留言 {ticket_id}，内容长度: {len(content)} 字符")
        
        # 添加回复
        reply = TicketReply.create(ticket_id, user_id, content)
        logging.debug(f"用户 {user_id} 回复留言 {ticket_id} 成功，回复ID: {reply.id}")
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 {user_id} 回复留言 {ticket_id} 成功，回复ID: {reply.id}",
            result="成功",
            module="ticket",
            operation_type="reply"
        )
        
        # 用户回复自动重开留言
        if ticket.status == '已关闭':
            logging.debug(f"用户 {user_id} 回复已关闭留言 {ticket_id}，自动重开留言状态")
            ticket.update(status='处理中')
            ticket.closed_at = None
        
        flash(f'回复添加成功，标题：{ticket.title}', 'success')
        return redirect(url_for('ticket_user.ticket_detail', ticket_id=ticket_id))
    except Exception as e:
        logging.error(f"添加留言回复失败: {str(e)}")
        logging.debug(f"添加回复异常详情 - 用户ID: {user_id}, 留言ID: {ticket_id}, 错误类型: {type(e).__name__}, 错误信息: {str(e)}")
        flash('添加回复失败，请稍后重试', 'error')
        return redirect(url_for('ticket_user.ticket_detail', ticket_id=ticket_id))

# 关闭留言
@ticket_user_bp.route('/close/<int:ticket_id>', methods=['POST'])
@login_required
@require_permission('ticket.edit')
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
        logging.debug(f"用户 {user_id} 开始关闭留言 {ticket_id}")
        
        # 获取留言
        ticket = Ticket.get_by_id(ticket_id)
        
        # 检查权限
        if not ticket:
            logging.warning(f"用户 {user_id} 尝试关闭不存在的留言 {ticket_id}")
            flash('无权操作此留言', 'error')
            return redirect(url_for('ticket_user.user_ticket_list'))
        if ticket.user_id != user_id:
            logging.warning(f"用户 {user_id} 尝试关闭不属于自己的留言 {ticket_id}")
            flash('无权操作此留言', 'error')
            return redirect(url_for('ticket_user.user_ticket_list'))
        
        # 记录当前留言状态
        current_status = ticket.status
        logging.debug(f"留言 {ticket_id} 当前状态: {current_status}")
        
        # 如果留言已经关闭，则不重复操作
        if current_status == '已关闭':
            logging.warning(f"用户 {user_id} 尝试关闭已经关闭的留言 {ticket_id}")
            flash('留言已经处于关闭状态', 'info')
            return redirect(url_for('ticket_user.user_ticket_list'))
        
        # 关闭留言
        ticket.update(status='已关闭')
        logging.debug(f"用户 {user_id} 关闭留言 {ticket_id} 成功，留言标题: {ticket.title}")
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 {user_id} 关闭留言 {ticket_id} 成功，留言标题: {ticket.title}",
            result="成功",
            module="ticket",
            operation_type="close"
        )
        
        flash('留言已关闭', 'success')
        return redirect(url_for('ticket_user.user_ticket_list'))
    except Exception as e:
        logging.error(f"关闭留言失败: {str(e)}")
        logging.debug(f"关闭留言异常详情 - 用户ID: {user_id}, 留言ID: {ticket_id}, 错误类型: {type(e).__name__}, 错误信息: {str(e)}")
        flash('关闭留言失败，请稍后重试', 'error')
        return redirect(url_for('ticket_user.user_ticket_list'))

# 提供留言媒体文件访问
@ticket_user_bp.route('/media/<int:ticket_id>/<path:filename>')
@login_required
@require_permission('ticket.view')
def serve_ticket_media(ticket_id, filename):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            abort(401)
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        logging.debug(f"用户 {user_id} 尝试访问留言 {ticket_id} 的媒体文件: {filename}")
        
        # 获取留言，检查用户是否有权访问该留言的媒体文件
        ticket = Ticket.get_by_id(ticket_id)
        if not ticket:
            logging.warning(f"用户 {user_id} 尝试访问不存在的留言 {ticket_id} 的媒体文件")
            abort(403)
        if ticket.user_id != user_id:
            logging.warning(f"用户 {user_id} 无权访问留言 {ticket_id} 的媒体文件")
            abort(403)
        
        # 导入TicketPhotoManager类
        from utils.ticket_photo import TicketPhotoManager
        
        # 获取文件的完整路径
        file_path = TicketPhotoManager.get_file_path(filename, ticket_id)
        if not file_path or not os.path.exists(file_path):
            logging.warning(f"文件 {filename} 不存在于留言 {ticket_id} 的媒体目录中")
            abort(404)
        
        # 获取文件信息
        file_size = os.path.getsize(file_path)
        logging.debug(f"文件 {filename} 大小: {file_size} 字节")
        
        # 获取文件扩展名，设置正确的MIME类型
        _, ext = os.path.splitext(filename)
        ext = ext.lower()
        
        # 根据文件扩展名设置MIME类型
        mimetype = None
        if ext in ['.jpg', '.jpeg']:
            mimetype = 'image/jpeg'
        elif ext == '.png':
            mimetype = 'image/png'
        elif ext == '.gif':
            mimetype = 'image/gif'
        elif ext == '.bmp':
            mimetype = 'image/bmp'
        elif ext == '.mp4':
            mimetype = 'video/mp4'
        elif ext == '.avi':
            mimetype = 'video/x-msvideo'
        elif ext == '.mov':
            mimetype = 'video/quicktime'
        elif ext == '.wmv':
            mimetype = 'video/x-ms-wmv'
        elif ext == '.flv':
            mimetype = 'video/x-flv'
        elif ext == '.mkv':
            mimetype = 'video/x-matroska'
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 [{user_id}] 访问留言 {ticket_id} 的媒体文件: {filename}",
            result="成功",
            module="ticket",
            operation_type="records"
        )
        logging.info(f"用户 [{user_id}] 成功访问留言 {ticket_id} 的媒体文件: {filename}")

        # 发送文件
        return send_file(file_path, mimetype=mimetype)
    except Exception as e:
        logging.error(f"提供留言媒体文件失败: {str(e)}")
        abort(500)


# 上传留言媒体文件
@ticket_user_bp.route('/upload_media/<int:ticket_id>', methods=['POST'])
@login_required
@require_permission('ticket.create')
def upload_ticket_media(ticket_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            return {'success': False, 'message': '用户信息无效，请重新登录'}
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        logging.debug(f"用户 {user_id} 开始为留言 {ticket_id} 上传媒体文件")
        
        # 获取留言，检查用户是否有权操作该留言
        ticket = Ticket.get_by_id(ticket_id)
        if not ticket:
            logging.warning(f"用户 {user_id} 尝试上传到不存在的留言 {ticket_id}")
            return {'success': False, 'message': '无权操作此留言'}
        if ticket.user_id != user_id:
            logging.warning(f"用户 {user_id} 尝试操作不属于自己的留言 {ticket_id}")
            return {'success': False, 'message': '无权操作此留言'}
        
        # 检查是否有文件上传
        if 'file' not in request.files:
            logging.warning(f"用户 {user_id} 留言 {ticket_id} 上传媒体文件时未选择文件")
            return {'success': False, 'message': '请选择要上传的文件'}
        
        file = request.files['file']
        
        # 检查文件名是否为空
        if file.filename == '':
            logging.warning(f"用户 {user_id} 留言 {ticket_id} 上传媒体文件时文件名为空")
            return {'success': False, 'message': '请选择要上传的文件'}
        
        logging.debug(f"用户 {user_id} 留言 {ticket_id} 上传文件: {file.filename}, 大小: {len(file.read())} bytes")
        file.seek(0)  # 重置文件指针
        
        # 导入TicketPhotoManager类
        from utils.ticket_photo import TicketPhotoManager
        
        # 上传文件
        uploaded_filename = TicketPhotoManager.upload_file(file, ticket_id)
        
        if uploaded_filename:
            logging.debug(f"用户 {user_id} 留言 {ticket_id} 媒体文件上传成功: {uploaded_filename}")
            # 记录操作日志
            log_operation(
                user_id=user_id,
                action=f"用户 {user_id} 留言 {ticket_id} 媒体文件上传成功: {uploaded_filename}",
                result="成功",
                module="ticket",
                operation_type="upload_media"
            )
            
            # 返回JSON响应而不是重定向
            return {'success': True, 'message': '文件上传成功', 'filename': uploaded_filename}
        else:
            logging.warning(f"用户 {user_id} 留言 {ticket_id} 媒体文件格式不支持: {file.filename}")
            return {'success': False, 'message': '文件格式不支持，请上传图片或视频文件'}
            
    except Exception as e:
        logging.error(f"上传留言媒体文件失败: {str(e)}")
        logging.debug(f"上传媒体文件异常详情 - 用户ID: {user_id}, 留言ID: {ticket_id}, 错误类型: {type(e).__name__}, 错误信息: {str(e)}")
        return {'success': False, 'message': f'文件上传失败: {str(e)}'}

# 删除留言媒体文件
@ticket_user_bp.route('/delete_media/<int:ticket_id>/<path:filename>', methods=['POST'])
@login_required
@require_permission('ticket.edit')
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
        logging.debug(f"用户 {user_id} 开始删除留言 {ticket_id} 的媒体文件: {filename}")
        
        # 获取留言，检查用户是否有权操作该留言
        ticket = Ticket.get_by_id(ticket_id)
        if not ticket:
            logging.warning(f"用户 {user_id} 尝试删除不存在的留言 {ticket_id} 的媒体文件")
            flash('无权操作此留言', 'error')
            return redirect(url_for('ticket_user.ticket_detail', ticket_id=ticket_id))
        if ticket.user_id != user_id:
            logging.warning(f"用户 {user_id} 尝试删除不属于自己的留言 {ticket_id} 的媒体文件")
            flash('无权操作此留言', 'error')
            return redirect(url_for('ticket_user.ticket_detail', ticket_id=ticket_id))
        
        # 导入TicketPhotoManager类
        from utils.ticket_photo import TicketPhotoManager
        
        # 检查文件是否存在
        file_path = TicketPhotoManager.get_file_path(filename, ticket_id)
        logging.debug(f"尝试删除的文件路径: {file_path}")
        
        # 删除文件
        if TicketPhotoManager.delete_file(filename, ticket_id):
            logging.debug(f"用户 {user_id} 留言 {ticket_id} 的媒体文件删除成功: {filename}")
            # 记录操作日志
            log_operation(
                user_id=user_id,
                action=f"用户 {user_id} 留言 {ticket_id} 的媒体文件删除成功: {filename}",
                result="成功",
                module="ticket",
                operation_type="delete_media"
            )
            
            flash('文件删除成功', 'success')
        else:
            logging.warning(f"用户 {user_id} 留言 {ticket_id} 的媒体文件删除失败，文件可能不存在: {filename}")
            flash('文件删除失败，文件可能不存在', 'error')
            
        return redirect(url_for('ticket_user.ticket_detail', ticket_id=ticket_id))
    except Exception as e:
        logging.error(f"删除留言媒体文件失败: {str(e)}")
        logging.debug(f"删除媒体文件异常详情 - 用户ID: {user_id}, 留言ID: {ticket_id}, 文件名: {filename}, 错误类型: {type(e).__name__}, 错误信息: {str(e)}")
        flash('文件删除失败，请稍后重试', 'error')
        return redirect(url_for('ticket_user.ticket_detail', ticket_id=ticket_id))
