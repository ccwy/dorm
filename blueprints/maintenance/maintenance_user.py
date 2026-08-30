from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from utils.db import db
from models.maintenance import MaintenanceOrder, MaintenanceReply
from models.user import User
from models.role import Role
from models.dorm import Dorm
from models.room import Room
from models.system_config import SystemConfig
from utils.maintenance_photo import MaintenancePhotoManager
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.log import log_operation
from sqlalchemy.orm import joinedload
from datetime import datetime
import logging


# 创建用户端维修蓝图
maintenance_user_bp = Blueprint('maintenance_user', __name__, url_prefix='/user/maintenance')


def generate_page_range(current_page, total_pages, show_pages=5):
    """生成分页页码范围"""
    if total_pages <= show_pages:
        return list(range(1, total_pages + 1))
    half = show_pages // 2
    start = max(1, current_page - half)
    end = min(total_pages, start + show_pages - 1)
    if end - start + 1 < show_pages:
        start = max(1, end - show_pages + 1)
    return list(range(start, end + 1))


def auto_assign_order(order):
    """自动分配维修工单"""
    auto_assign_enabled = SystemConfig.get_config_value('MAINTENANCE_AUTO_ASSIGN_ENABLED', True)
    if not auto_assign_enabled:
        return
    
    # 查询所有活跃维修员
    staff_users = User.query.join(Role, User.role_id == Role.id).filter(
        Role.code == 'maintenance_staff',
        User.is_active == True
    ).all()
    
    if not staff_users:
        return
    
    # 统计每个维修员处理中的工单数，选择最少的
    min_count = float('inf')
    selected_staff = None
    for staff in staff_users:
        count = MaintenanceOrder.query.filter_by(
            assigned_to=staff.id,
            status='处理中'
        ).count()
        if count < min_count:
            min_count = count
            selected_staff = staff
    
    if selected_staff:
        order.update(assigned_to=selected_staff.id, assignment_type='auto')
        MaintenanceReply.create_assignment_reply(
            order_id=order.id,
            assigned_to_user=selected_staff,
            assigned_by_user=current_user,
            assignment_type='auto'
        )


# 用户维修工单列表
@maintenance_user_bp.route('/list')
@login_required
@require_permission('maintenance.view')
def user_order_list():
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
        
        # 获取筛选参数
        status = request.args.get('status', '').strip()
        search = request.args.get('search', '').strip()
        
        # 获取当前用户的工单，预加载关联数据
        query = MaintenanceOrder.query.filter_by(user_id=user_id).options(
            joinedload(MaintenanceOrder.assigned_user),
            joinedload(MaintenanceOrder.user)
        )
        
        # 处理状态筛选
        if status and status.strip():
            query = query.filter_by(status=status)
        
        # 处理关键词搜索
        if search and search.strip():
            query = query.filter(
                MaintenanceOrder.title.like(f'%{search}%') |
                MaintenanceOrder.description.like(f'%{search}%') |
                MaintenanceOrder.order_no.like(f'%{search}%') |
                MaintenanceOrder.room_number.like(f'%{search}%')
            )
        
        # 排序和分页
        pagination = query.order_by(MaintenanceOrder.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        orders = pagination.items
        
        # 获取维修类型配置
        maintenance_types = SystemConfig.get_config_value(
            'MAINTENANCE_TYPES', '水电维修,门窗维修,家具维修,空调维修,网络维修,其他'
        )
        if isinstance(maintenance_types, str):
            maintenance_types = [t.strip() for t in maintenance_types.split(',')]
        
        # 状态列表
        status_list = ['待处理', '处理中', '已解决', '已关闭']
        
        # 分页范围
        page_range = generate_page_range(page, pagination.pages)
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 [{user_id}] 访问维修工单列表",
            result="成功",
            module="maintenance",
            operation_type="records"
        )
        logging.info(f"用户 [{user_id}] 成功访问维修工单列表")
        return render_template('maintenance/user_order_list.html',
                              title="我的维修工单",
                              orders=orders, pagination=pagination, page=page, per_page=per_page,
                              page_range=page_range,
                              status_filter=status, search_query=search,
                              status_list=status_list, maintenance_types=maintenance_types)
    except Exception as e:
        logging.error(f"获取用户维修工单列表失败: {str(e)}")
        flash('获取维修工单列表失败，请稍后重试', 'error')
        return redirect(url_for('index'))


# 创建维修工单
@maintenance_user_bp.route('/create', methods=['GET', 'POST'])
@login_required
@require_permission('maintenance.create')
def user_order_create():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        if request.method == 'GET':
            # 获取当前用户的住宿记录
            dorm = Dorm.query.filter_by(user_id=user_id, status='active').first()
            room_info = ''
            room_id = None
            room_number = ''
            if dorm:
                room = Room.query.get(dorm.room_id)
                if room:
                    room_id = room.id
                    room_number = room.room_full_identifier
                    room_info = room_number
            
            # 获取维修类型配置
            maintenance_types = SystemConfig.get_config_value(
                'MAINTENANCE_TYPES', '水电维修,门窗维修,家具维修,空调维修,网络维修,其他'
            )
            if isinstance(maintenance_types, str):
                maintenance_types = [t.strip() for t in maintenance_types.split(',')]
            
            # 获取临时文件列表
            temp_files = MaintenancePhotoManager.get_temp_files(user_id)
            
            # 优先级列表
            priority_list = ['低', '一般', '高', '紧急']
            
            logging.info(f"用户 [{user_id}] 访问创建维修工单页面")
            return render_template('maintenance/user_order_create.html',
                                  title="创建维修工单",
                                  room_info=room_info, room_id=room_id, room_number=room_number,
                                  maintenance_types=maintenance_types,
                                  priority_list=priority_list,
                                  temp_files=temp_files)
        
        # POST请求 - 创建工单
        description = request.form.get('description', '').strip()
        maintenance_type = request.form.get('maintenance_type', '').strip()
        priority = request.form.get('priority', '一般').strip()
        room_info = request.form.get('room_info', '').strip()
        
        # 验证必填字段
        if not description or not maintenance_type:
            logging.warning(f"用户 {user_id} 创建维修工单参数不完整")
            flash('请填写所有必填字段', 'error')
            return redirect(url_for('maintenance_user.user_order_create'))
        
        # 获取房间信息 - 优先使用搜索选择的room_id
        room_id = request.form.get('room_id', '').strip()
        room_number = room_info
        if room_id:
            # 用户通过搜索选择了房间
            room = Room.query.get(int(room_id))
            if room:
                room_number = room.room_full_identifier
            else:
                room_id = None
        if not room_id and room_info:
            # 未选择房间，尝试从用户住宿信息获取
            dorm = Dorm.query.filter_by(user_id=user_id, status='active').first()
            if dorm:
                room_id = dorm.room_id
                room = Room.query.get(room_id)
                if room:
                    room_number = room.room_full_identifier
        
        # 标题自动取描述前20字
        title = description[:20] if description else '无标题'
        
        # 创建维修工单
        order = MaintenanceOrder.create(
            user_id=user_id,
            room_id=room_id,
            room_number=room_number,
            title=title,
            description=description,
            maintenance_type=maintenance_type,
            priority=priority
        )
        logging.debug(f"用户 {user_id} 创建维修工单成功，工单ID: {order.id}")
        
        # 移动临时文件到正式目录
        temp_files = MaintenancePhotoManager.get_temp_files(user_id)
        if temp_files:
            filenames = [f['filename'] for f in temp_files]
            moved_files = MaintenancePhotoManager.move_temp_to_formal(user_id, order.id, filenames)
            logging.debug(f"移动 {len(moved_files)} 个临时文件到工单 {order.id} 的正式目录")
        
        # 清理临时文件
        MaintenancePhotoManager.cleanup_temp_files(user_id)
        
        # 自动分配维修员
        auto_assign_order(order)
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 {user_id} 创建维修工单成功，工单ID: {order.id}",
            result="成功",
            module="maintenance",
            operation_type="create"
        )
        
        flash('维修工单创建成功', 'success')
        return redirect(url_for('maintenance_user.user_order_detail', order_id=order.id))
    except Exception as e:
        logging.error(f"创建维修工单失败: {str(e)}")
        logging.debug(f"创建维修工单异常详情 - 用户ID: {current_user.id if hasattr(current_user, 'id') else '未知'}, 错误类型: {type(e).__name__}, 错误信息: {str(e)}")
        flash('创建维修工单失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_user.user_order_list'))


# 查看维修工单详情
@maintenance_user_bp.route('/detail/<int:order_id>')
@login_required
@require_permission('maintenance.view')
def user_order_detail(order_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        # 获取工单
        order = MaintenanceOrder.get_by_id(order_id)
        
        # 检查权限
        if not order or order.user_id != user_id:
            logging.warning(f"用户 {user_id} 尝试查看不属于自己的维修工单 {order_id}")
            flash('无权查看此维修工单', 'error')
            return redirect(url_for('maintenance_user.user_order_list'))
        
        # 获取回复列表
        replies = MaintenanceReply.get_by_order_id(order_id)
        
        # 获取媒体文件列表
        media_files = MaintenancePhotoManager.get_media_files(order_id)
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 [{user_id}] 查看维修工单详情，工单ID: {order_id}",
            result="成功",
            module="maintenance",
            operation_type="records"
        )
        logging.info(f"用户 [{user_id}] 成功查看维修工单详情，工单ID: {order_id}")
        
        return render_template('maintenance/user_order_detail.html',
                              title="维修工单详情",
                              order=order, replies=replies, media_files=media_files,
                              timeline=order.get_timeline())
    except Exception as e:
        logging.error(f"查看维修工单详情失败: {str(e)}")
        flash('查看维修工单详情失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_user.user_order_list'))


# 回复维修工单
@maintenance_user_bp.route('/reply/<int:order_id>', methods=['POST'])
@login_required
@require_permission('maintenance.create')
def user_add_reply(order_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        logging.debug(f"用户 {user_id} 开始回复维修工单 {order_id}")
        
        # 获取工单
        order = MaintenanceOrder.get_by_id(order_id)
        
        # 检查权限
        if not order:
            logging.warning(f"用户 {user_id} 尝试回复不存在的维修工单 {order_id}")
            flash('维修工单不存在', 'error')
            return redirect(url_for('maintenance_user.user_order_list'))
        if order.user_id != user_id:
            logging.warning(f"用户 {user_id} 尝试回复不属于自己的维修工单 {order_id}")
            flash('无权回复此维修工单', 'error')
            return redirect(url_for('maintenance_user.user_order_list'))
        
        # 获取回复内容
        content = request.form.get('content', '').strip()
        
        if not content:
            logging.warning(f"用户 {user_id} 回复维修工单 {order_id} 时内容为空")
            flash('请输入回复内容', 'error')
            return redirect(url_for('maintenance_user.user_order_detail', order_id=order_id))
        
        # 处理上传的附件文件
        uploaded_files_str = request.form.get('uploaded_files', '').strip()
        if uploaded_files_str:
            filenames = [f.strip() for f in uploaded_files_str.split(',') if f.strip()]
            if filenames:
                moved = MaintenancePhotoManager.move_temp_to_formal(user_id, order_id, filenames)
                logging.debug(f"用户 {user_id} 回复时移动 {len(moved)} 个临时文件到工单 {order_id}")
                # 清理临时文件及目录
                MaintenancePhotoManager.cleanup_temp_files(user_id)
        
        # 处理直接上传的文件
        files = request.files.getlist('files')
        for file in files:
            if file and file.filename:
                filename = MaintenancePhotoManager.upload_file(file, order_id)
                if filename:
                    logging.debug(f"用户 {user_id} 回复时上传文件 {filename} 到工单 {order_id}")
        
        # 创建回复
        reply = MaintenanceReply.create(
            order_id=order_id,
            user_id=user_id,
            content=content
        )
        
        # 用户回复自动重开工单
        if order.status == '已关闭':
            logging.debug(f"用户 {user_id} 回复已关闭工单 {order_id}，自动重开工单状态")
            order.update(status='处理中')
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 {user_id} 回复维修工单 {order_id} 成功，回复ID: {reply.id}",
            result="成功",
            module="maintenance",
            operation_type="reply"
        )
        
        flash('回复添加成功', 'success')
        return redirect(url_for('maintenance_user.user_order_detail', order_id=order_id))
    except Exception as e:
        logging.error(f"回复维修工单失败: {str(e)}")
        logging.debug(f"回复维修工单异常详情 - 用户ID: {user_id}, 工单ID: {order_id}, 错误类型: {type(e).__name__}, 错误信息: {str(e)}")
        flash('回复维修工单失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_user.user_order_detail', order_id=order_id))


# 用户关闭工单
@maintenance_user_bp.route('/close/<int:order_id>', methods=['POST'])
@login_required
@require_permission('maintenance.create')
def user_close_order(order_id):
    try:
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
        
        user_id = int(str(user_id))
        logging.debug(f"用户 {user_id} 关闭维修工单 {order_id}")
        
        order = MaintenanceOrder.get_by_id(order_id)
        
        if not order:
            flash('维修工单不存在', 'error')
            return redirect(url_for('maintenance_user.user_order_list'))
        if order.user_id != user_id:
            flash('无权操作此维修工单', 'error')
            return redirect(url_for('maintenance_user.user_order_list'))
        
        # 允许用户在 待处理、处理中、已解决 状态下关闭工单
        if order.status == '已关闭':
            flash('工单已关闭', 'info')
            return redirect(url_for('maintenance_user.user_order_detail', order_id=order_id))
        
        old_status = order.status
        order.update(status='已关闭')
        order.closed_at = datetime.now()
        db.session.commit()
        
        # 创建状态变更通知回复
        MaintenanceReply.create_status_change_reply(
            order_id=order_id,
            old_status=old_status,
            new_status='已关闭',
            user=current_user
        )
        
        log_operation(
            user_id=user_id,
            action=f"用户 {user_id} 关闭维修工单 {order_id}",
            result="成功",
            module="maintenance",
            operation_type="update_status"
        )
        
        logging.info(f"用户 {user_id} 关闭维修工单 {order_id}")
        flash('工单已关闭', 'success')
        return redirect(url_for('maintenance_user.user_order_detail', order_id=order_id))
    except Exception as e:
        logging.error(f"关闭维修工单失败: {str(e)}")
        flash('关闭维修工单失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_user.user_order_detail', order_id=order_id))


# 用户确认工单已解决
@maintenance_user_bp.route('/confirm-resolved/<int:order_id>', methods=['POST'])
@login_required
@require_permission('maintenance.create')
def user_confirm_resolved(order_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        logging.debug(f"用户 {user_id} 确认维修工单 {order_id} 已解决")
        
        # 获取工单
        order = MaintenanceOrder.get_by_id(order_id)
        
        # 检查权限
        if not order:
            logging.warning(f"用户 {user_id} 尝试确认不存在的维修工单 {order_id}")
            flash('维修工单不存在', 'error')
            return redirect(url_for('maintenance_user.user_order_list'))
        if order.user_id != user_id:
            logging.warning(f"用户 {user_id} 尝试确认不属于自己的维修工单 {order_id}")
            flash('无权操作此维修工单', 'error')
            return redirect(url_for('maintenance_user.user_order_list'))
        
        # 检查当前状态
        if order.status != '已解决':
            flash('只有已解决状态的工单才能确认', 'error')
            return redirect(url_for('maintenance_user.user_order_detail', order_id=order_id))
        
        # 记录旧状态
        old_status = order.status
        
        # 更新状态为已关闭
        order.update(status='已关闭')
        order.closed_at = datetime.now()
        db.session.commit()
        
        # 创建状态变更通知回复
        MaintenanceReply.create_status_change_reply(
            order_id=order_id,
            old_status=old_status,
            new_status='已关闭',
            user=current_user
        )
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 {user_id} 确认维修工单 {order_id} 已解决并关闭",
            result="成功",
            module="maintenance",
            operation_type="update_status"
        )
        
        logging.info(f"用户 {user_id} 确认维修工单 {order_id} 已解决并关闭")
        flash('已确认工单解决并关闭', 'success')
        return redirect(url_for('maintenance_user.user_order_detail', order_id=order_id))
    except Exception as e:
        logging.error(f"确认维修工单解决失败: {str(e)}")
        flash('确认维修工单解决失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_user.user_order_detail', order_id=order_id))


# 用户重新开启工单
@maintenance_user_bp.route('/reopen/<int:order_id>', methods=['POST'])
@login_required
@require_permission('maintenance.create')
def user_reopen_order(order_id):
    try:
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
        
        user_id = int(str(user_id))
        logging.debug(f"用户 {user_id} 重新开启维修工单 {order_id}")
        
        order = MaintenanceOrder.get_by_id(order_id)
        
        if not order:
            flash('维修工单不存在', 'error')
            return redirect(url_for('maintenance_user.user_order_list'))
        if order.user_id != user_id:
            flash('无权操作此维修工单', 'error')
            return redirect(url_for('maintenance_user.user_order_list'))
        
        # 只有已关闭的工单可以重新开启
        if order.status != '已关闭':
            flash('只有已关闭的工单才能重新开启', 'error')
            return redirect(url_for('maintenance_user.user_order_detail', order_id=order_id))
        
        old_status = order.status
        order.closed_at = None
        order.update(status='待处理')
        
        # 创建状态变更通知回复
        MaintenanceReply.create_status_change_reply(
            order_id=order_id,
            old_status=old_status,
            new_status='待处理',
            user=current_user
        )
        
        log_operation(
            user_id=user_id,
            action=f"用户 {user_id} 重新开启维修工单 {order_id}",
            result="成功",
            module="maintenance",
            operation_type="update_status"
        )
        
        logging.info(f"用户 {user_id} 重新开启维修工单 {order_id}")
        flash('工单已重新开启', 'success')
        return redirect(url_for('maintenance_user.user_order_detail', order_id=order_id))
    except Exception as e:
        logging.error(f"重新开启维修工单失败: {str(e)}")
        flash('重新开启维修工单失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_user.user_order_detail', order_id=order_id))