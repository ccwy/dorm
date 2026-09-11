from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from utils.db import db
from models.maintenance import MaintenanceOrder, MaintenanceReply
from models.user.user import User
from models.system_config.system_config import SystemConfig
from utils.maintenance_photo import MaintenancePhotoManager
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.log import log_operation
from sqlalchemy.orm import joinedload
from datetime import datetime
import logging


# 创建维修员端维修蓝图
maintenance_staff_bp = Blueprint('maintenance_staff', __name__, url_prefix='/staff/maintenance')


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


# 维修员工单列表
@maintenance_staff_bp.route('/list')
@login_required
@require_permission('maintenance.handle')
def staff_order_list():
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
        per_page = request.args.get('per_page', 20, type=int)
        
        # 获取筛选参数
        status = request.args.get('status', '').strip()
        search = request.args.get('search', '').strip()
        
        # 只显示分配给当前维修员的工单，预加载关联数据
        query = MaintenanceOrder.query.filter_by(assigned_to=user_id).options(
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
        
        # 状态列表
        status_list = ['待处理', '处理中', '已解决', '已关闭']
        
        # 获取维修类型配置
        maintenance_types = SystemConfig.get_config_value(
            'MAINTENANCE_TYPES', '水电维修,门窗维修,家具维修,空调维修,网络维修,其他'
        )
        if isinstance(maintenance_types, str):
            maintenance_types = [t.strip() for t in maintenance_types.split(',')]
        
        # 分页范围
        page_range = generate_page_range(page, pagination.pages)
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"维修员 [{user_id}] 访问维修工单列表",
            result="成功",
            module="maintenance",
            operation_type="records"
        )
        logging.info(f"维修员 [{user_id}] 成功访问维修工单列表")
        return render_template('maintenance/staff_order_list.html',
                              title="我的维修任务",
                              orders=orders, pagination=pagination, page=page, per_page=per_page,
                              page_range=page_range,
                              status_filter=status, search_query=search,
                              status_list=status_list, maintenance_types=maintenance_types,
                              stats=type('Stats', (), {
                                  'in_progress': MaintenanceOrder.query.filter_by(assigned_to=user_id, status='处理中').count(),
                                  'resolved': MaintenanceOrder.query.filter_by(assigned_to=user_id, status='已解决').count(),
                                  'urgent': MaintenanceOrder.query.filter_by(assigned_to=user_id, priority='紧急').filter(MaintenanceOrder.status.in_(['待处理', '处理中'])).count()
                              })())
    except Exception as e:
        logging.error(f"获取维修员工单列表失败: {str(e)}")
        flash('获取维修工单列表失败，请稍后重试', 'error')
        return redirect(url_for('index'))


# 维修员工单详情
@maintenance_staff_bp.route('/detail/<int:order_id>')
@login_required
@require_permission('maintenance.handle')
def staff_order_detail(order_id):
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
        
        # 检查权限 - 只能查看分配给自己的工单
        if not order or order.assigned_to != user_id:
            logging.warning(f"维修员 {user_id} 尝试查看不属于自己的维修工单 {order_id}")
            flash('无权查看此维修工单', 'error')
            return redirect(url_for('maintenance_staff.staff_order_list'))
        
        # 获取回复列表
        replies = MaintenanceReply.get_by_order_id(order_id)
        
        # 获取媒体文件列表
        media_files = MaintenancePhotoManager.get_media_files(order_id)
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"维修员 [{user_id}] 查看维修工单详情，工单ID: {order_id}",
            result="成功",
            module="maintenance",
            operation_type="records"
        )
        logging.info(f"维修员 [{user_id}] 成功查看维修工单详情，工单ID: {order_id}")
        
        return render_template('maintenance/staff_order_detail.html',
                              title="维修工单详情",
                              order=order, replies=replies, media_files=media_files,
                              timeline=order.get_timeline())
    except Exception as e:
        logging.error(f"查看维修工单详情失败: {str(e)}")
        flash('查看维修工单详情失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_staff.staff_order_list'))


# 维修员回复工单
@maintenance_staff_bp.route('/reply/<int:order_id>', methods=['POST'])
@login_required
@require_permission('maintenance.handle')
def staff_add_reply(order_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        logging.debug(f"维修员 {user_id} 开始回复维修工单 {order_id}")
        
        # 获取工单
        order = MaintenanceOrder.get_by_id(order_id)
        
        # 检查权限
        if not order:
            logging.warning(f"维修员 {user_id} 尝试回复不存在的维修工单 {order_id}")
            flash('维修工单不存在', 'error')
            return redirect(url_for('maintenance_staff.staff_order_list'))
        if order.assigned_to != user_id:
            logging.warning(f"维修员 {user_id} 尝试回复不属于自己的维修工单 {order_id}")
            flash('无权回复此维修工单', 'error')
            return redirect(url_for('maintenance_staff.staff_order_list'))
        
        # 获取回复内容
        content = request.form.get('content', '').strip()
        
        if not content:
            logging.warning(f"维修员 {user_id} 回复维修工单 {order_id} 时内容为空")
            flash('请输入回复内容', 'error')
            return redirect(url_for('maintenance_staff.staff_order_detail', order_id=order_id))
        
        # 处理上传的附件文件（AJAX上传到临时目录的文件）
        uploaded_files_str = request.form.get('uploaded_files', '').strip()
        if uploaded_files_str:
            filenames = [f.strip() for f in uploaded_files_str.split(',') if f.strip()]
            if filenames:
                moved = MaintenancePhotoManager.move_temp_to_formal(user_id, order_id, filenames)
                logging.debug(f"维修员 {user_id} 回复时移动 {len(moved)} 个临时文件到工单 {order_id}")
                # 清理临时文件及目录
                MaintenancePhotoManager.cleanup_temp_files(user_id)
        
        # 处理直接上传的文件
        files = request.files.getlist('files')
        for file in files:
            if file and file.filename:
                filename = MaintenancePhotoManager.upload_file(file, order_id)
                if filename:
                    logging.debug(f"维修员 {user_id} 回复时上传文件 {filename} 到工单 {order_id}")
        
        # 创建回复
        reply = MaintenanceReply.create(
            order_id=order_id,
            user_id=user_id,
            content=content
        )
        
        # 维修员回复自动将工单状态改为处理中（如果还是待处理）
        if order.status == '待处理':
            order.update(status='处理中')
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"维修员 {user_id} 回复维修工单 {order_id} 成功，回复ID: {reply.id}",
            result="成功",
            module="maintenance",
            operation_type="reply"
        )
        
        flash('回复添加成功', 'success')
        return redirect(url_for('maintenance_staff.staff_order_detail', order_id=order_id))
    except Exception as e:
        logging.error(f"维修员回复维修工单失败: {str(e)}")
        logging.debug(f"维修员回复维修工单异常详情 - 用户ID: {user_id}, 工单ID: {order_id}, 错误类型: {type(e).__name__}, 错误信息: {str(e)}")
        flash('回复维修工单失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_staff.staff_order_detail', order_id=order_id))


# 维修员开始处理工单
@maintenance_staff_bp.route('/start-work/<int:order_id>', methods=['POST'])
@login_required
@require_permission('maintenance.handle')
def staff_start_work(order_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        logging.debug(f"维修员 {user_id} 开始处理维修工单 {order_id}")
        
        # 获取工单
        order = MaintenanceOrder.get_by_id(order_id)
        
        # 检查权限
        if not order:
            logging.warning(f"维修员 {user_id} 尝试开始处理不存在的维修工单 {order_id}")
            flash('维修工单不存在', 'error')
            return redirect(url_for('maintenance_staff.staff_order_list'))
        if order.assigned_to != user_id:
            logging.warning(f"维修员 {user_id} 尝试开始处理不属于自己的维修工单 {order_id}")
            flash('无权操作此维修工单', 'error')
            return redirect(url_for('maintenance_staff.staff_order_list'))
        
        # 检查当前状态
        if order.status != '待处理':
            flash('只有待处理状态的工单才能开始处理', 'error')
            return redirect(url_for('maintenance_staff.staff_order_detail', order_id=order_id))
        
        # 记录旧状态
        old_status = order.status
        
        # 更新状态为处理中
        order.update(status='处理中')
        
        # 创建状态变更通知回复
        MaintenanceReply.create_status_change_reply(
            order_id=order_id,
            old_status=old_status,
            new_status='处理中',
            user=current_user
        )
        
        logging.info(f"维修员 {user_id} 开始处理维修工单 {order_id}")
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"维修员 {user_id} 开始处理维修工单 {order_id}",
            result="成功",
            module="maintenance",
            operation_type="start_work"
        )
        
        flash('已开始处理维修工单', 'success')
        return redirect(url_for('maintenance_staff.staff_order_detail', order_id=order_id))
    except Exception as e:
        logging.error(f"开始处理维修工单失败: {str(e)}")
        flash('开始处理维修工单失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_staff.staff_order_detail', order_id=order_id))


# 维修员标记工单完成
@maintenance_staff_bp.route('/complete/<int:order_id>', methods=['POST'])
@login_required
@require_permission('maintenance.handle')
def staff_complete_order(order_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        logging.debug(f"维修员 {user_id} 开始标记维修工单 {order_id} 为已完成")
        
        # 获取工单
        order = MaintenanceOrder.get_by_id(order_id)
        
        # 检查权限
        if not order:
            logging.warning(f"维修员 {user_id} 尝试完成不存在的维修工单 {order_id}")
            flash('维修工单不存在', 'error')
            return redirect(url_for('maintenance_staff.staff_order_list'))
        if order.assigned_to != user_id:
            logging.warning(f"维修员 {user_id} 尝试完成不属于自己的维修工单 {order_id}")
            flash('无权操作此维修工单', 'error')
            return redirect(url_for('maintenance_staff.staff_order_list'))
        
        # 检查当前状态
        if order.status == '已解决':
            flash('工单已经处于已解决状态', 'info')
            return redirect(url_for('maintenance_staff.staff_order_detail', order_id=order_id))
        
        if order.status == '已关闭':
            flash('工单已经关闭，无法标记完成', 'error')
            return redirect(url_for('maintenance_staff.staff_order_detail', order_id=order_id))
        
        # 记录旧状态
        old_status = order.status
        
        # 更新状态为已解决
        order.update(status='已解决')
        
        # 创建状态变更通知回复（已解决）
        MaintenanceReply.create_status_change_reply(
            order_id=order_id,
            old_status=old_status,
            new_status='已解决',
            user=current_user
        )
        
        # 自动关闭工单
        order.update(status='已关闭')
        order.closed_at = datetime.now()
        db.session.commit()
        
        # 创建状态变更通知回复（已关闭）
        MaintenanceReply.create_status_change_reply(
            order_id=order_id,
            old_status='已解决',
            new_status='已关闭',
            user=current_user
        )
        
        logging.info(f"维修员 {user_id} 成功完成并关闭维修工单 {order_id}")
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"维修员 {user_id} 完成并关闭维修工单 {order_id}",
            result="成功",
            module="maintenance",
            operation_type="complete"
        )
        
        flash('维修工单已完成并自动关闭', 'success')
        return redirect(url_for('maintenance_staff.staff_order_detail', order_id=order_id))
    except Exception as e:
        logging.error(f"标记维修工单完成失败: {str(e)}")
        logging.debug(f"标记维修工单完成异常详情 - 用户ID: {user_id}, 工单ID: {order_id}, 错误类型: {type(e).__name__}, 错误信息: {str(e)}")
        flash('标记维修工单完成失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_staff.staff_order_detail', order_id=order_id))