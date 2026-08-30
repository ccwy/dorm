from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from utils.db import db
from models.maintenance import MaintenanceOrder, MaintenanceReply
from models.user import User
from models.role import Role
from models.system_config import SystemConfig
from utils.maintenance_photo import MaintenancePhotoManager
from flask_login import login_required, current_user
from sqlalchemy import or_
from sqlalchemy.orm import joinedload
from datetime import datetime
from utils.auth import require_permission
from utils.log import log_operation
import logging


# 创建管理端维修蓝图
maintenance_admin_bp = Blueprint('maintenance_admin', __name__, url_prefix='/admin/maintenance')


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


def get_maintenance_staff_list():
    """获取维修员列表（含当前活跃工单数）"""
    from sqlalchemy import func
    
    # 子查询：统计每个维修员的活跃工单数（待处理+处理中）
    active_orders_subquery = (
        db.session.query(
            MaintenanceOrder.assigned_to,
            func.count(MaintenanceOrder.id).label('active_count')
        )
        .filter(
            MaintenanceOrder.status.in_(['待处理', '处理中']),
            MaintenanceOrder.assigned_to.isnot(None)
        )
        .group_by(MaintenanceOrder.assigned_to)
        .subquery()
    )
    
    # 查询维修员列表并关联活跃工单数
    staff_list = (
        User.query
        .join(Role, User.role_id == Role.id)
        .outerjoin(active_orders_subquery, User.id == active_orders_subquery.c.assigned_to)
        .filter(Role.code == 'maintenance_staff', User.is_active == True)
        .add_columns(func.coalesce(active_orders_subquery.c.active_count, 0).label('active_orders'))
        .all()
    )
    
    # 将active_orders属性设置到User对象上，供模板直接访问
    result = []
    for staff, active_orders in staff_list:
        staff.active_orders = int(active_orders)
        result.append(staff)
    
    return result


# 管理端维修工单列表
@maintenance_admin_bp.route('/list')
@login_required
@require_permission('maintenance.manage')
def admin_order_list():
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
        maintenance_type = request.args.get('maintenance_type', '').strip()
        priority = request.args.get('priority', '').strip()
        assigned_to = request.args.get('assigned_to', '').strip()
        
        # 分页参数处理
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # 使用search方法进行多条件查询，预加载关联数据
        query = MaintenanceOrder.query.options(
            joinedload(MaintenanceOrder.assigned_user),
            joinedload(MaintenanceOrder.user)
        )
        
        # 处理关键字搜索
        if search and search.strip():
            query = query.filter(
                MaintenanceOrder.title.like(f'%{search}%') |
                MaintenanceOrder.description.like(f'%{search}%') |
                MaintenanceOrder.order_no.like(f'%{search}%') |
                MaintenanceOrder.room_number.like(f'%{search}%')
            )
        
        # 处理状态筛选
        if status and status.strip():
            query = query.filter_by(status=status)
        
        # 处理维修类型筛选
        if maintenance_type and maintenance_type.strip():
            query = query.filter_by(maintenance_type=maintenance_type)
        
        # 处理优先级筛选
        if priority and priority.strip():
            query = query.filter_by(priority=priority)
        
        # 处理维修员筛选
        if assigned_to and assigned_to.strip():
            try:
                assigned_to_int = int(assigned_to)
                query = query.filter_by(assigned_to=assigned_to_int)
            except ValueError:
                pass
        
        # 执行分页查询
        pagination = query.order_by(MaintenanceOrder.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        orders = pagination.items
        
        # 获取筛选选项列表
        status_list = ['待处理', '处理中', '已解决', '已关闭']
        priority_list = ['低', '一般', '高', '紧急']
        
        # 获取维修类型配置
        maintenance_types = SystemConfig.get_config_value(
            'MAINTENANCE_TYPES', '水电维修,门窗维修,家具维修,空调维修,网络维修,其他'
        )
        if isinstance(maintenance_types, str):
            maintenance_types = [t.strip() for t in maintenance_types.split(',')]
        
        # 获取维修员列表
        staff_list = get_maintenance_staff_list()
        
        # 分页范围
        page_range = generate_page_range(page, pagination.pages)
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员 [{user_id}] 访问维修工单管理列表",
            result="成功",
            module="maintenance",
            operation_type="records"
        )
        logging.info(f"管理员 [{user_id}] 成功访问维修工单管理列表")
        return render_template('maintenance/admin_order_list.html',
                              title="维修工单管理",
                              orders=orders, pagination=pagination, page=page, per_page=per_page,
                              page_range=page_range,
                              search_query=search, status_filter=status,
                              maintenance_type_filter=maintenance_type,
                              priority_filter=priority, assigned_to_filter=assigned_to,
                              status_list=status_list, priority_list=priority_list,
                              maintenance_types=maintenance_types,
                              staff_list=staff_list,
                              stats=type('Stats', (), {
                                  'pending': MaintenanceOrder.query.filter_by(status='待处理').count(),
                                  'in_progress': MaintenanceOrder.query.filter_by(status='处理中').count(),
                                  'resolved': MaintenanceOrder.query.filter_by(status='已解决').count(),
                                  'closed': MaintenanceOrder.query.filter_by(status='已关闭').count()
                              })())
    except Exception as e:
        logging.error(f"获取管理端维修工单列表失败: {str(e)}")
        flash('获取维修工单列表失败，请稍后重试', 'error')
        return redirect(url_for('index'))


# 管理端维修工单详情
@maintenance_admin_bp.route('/detail/<int:order_id>')
@login_required
@require_permission('maintenance.manage')
def admin_order_detail(order_id):
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
        
        if not order:
            flash('维修工单不存在', 'error')
            logging.error(f"维修工单 {order_id} 不存在")
            return redirect(url_for('maintenance_admin.admin_order_list'))
        
        # 获取回复列表
        replies = MaintenanceReply.get_by_order_id(order_id)
        
        # 获取媒体文件列表
        media_files = MaintenancePhotoManager.get_media_files(order_id)
        
        # 获取维修员列表
        staff_list = get_maintenance_staff_list()
        
        # 获取维修类型配置
        maintenance_types = SystemConfig.get_config_value(
            'MAINTENANCE_TYPES', '水电维修,门窗维修,家具维修,空调维修,网络维修,其他'
        )
        if isinstance(maintenance_types, str):
            maintenance_types = [t.strip() for t in maintenance_types.split(',')]
        
        logging.info(f"管理员[{user_id}]成功查看维修工单详情，工单ID: {order_id}")
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员 {user_id} 查看维修工单详情，工单ID: {order_id}",
            result="成功",
            module="maintenance",
            operation_type="records"
        )
        return render_template('maintenance/admin_order_detail.html',
                              title="维修工单详情",
                              order=order, replies=replies, media_files=media_files,
                              staff_list=staff_list, maintenance_types=maintenance_types,
                              timeline=order.get_timeline())
    except Exception as e:
        logging.error(f"查看维修工单详情失败: {str(e)}")
        flash('查看维修工单详情失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_admin.admin_order_list'))


# 分配维修员
@maintenance_admin_bp.route('/assign/<int:order_id>', methods=['POST'])
@login_required
@require_permission('maintenance.manage')
def assign_order(order_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        logging.debug(f"管理员[{user_id}]尝试分配维修工单，工单ID: {order_id}")
        
        # 获取工单
        order = MaintenanceOrder.get_by_id(order_id)
        
        if not order:
            logging.warning(f"管理员[{user_id}]尝试分配不存在的维修工单，工单ID: {order_id}")
            flash('维修工单不存在', 'error')
            return redirect(url_for('maintenance_admin.admin_order_list'))
        
        # 获取分配的维修员ID
        assigned_to = request.form.get('assigned_to', '').strip()
        assignment_type = request.form.get('assignment_type', 'manual').strip()
        
        if not assigned_to:
            logging.warning(f"管理员[{user_id}]分配维修工单时未选择维修员，工单ID: {order_id}")
            flash('请选择维修员', 'error')
            return redirect(url_for('maintenance_admin.admin_order_detail', order_id=order_id))
        
        try:
            assigned_to_int = int(assigned_to)
        except ValueError:
            flash('无效的维修员ID', 'error')
            return redirect(url_for('maintenance_admin.admin_order_detail', order_id=order_id))
        
        # 获取维修员信息
        staff_user = User.query.get(assigned_to_int)
        if not staff_user:
            flash('维修员不存在', 'error')
            return redirect(url_for('maintenance_admin.admin_order_detail', order_id=order_id))
        
        # 更新分配信息
        old_status = order.status
        order.update(assigned_to=assigned_to_int, assignment_type=assignment_type)
        
        # 如果工单状态为待处理，自动更新为处理中
        if old_status == '待处理':
            order.update(status='处理中')
        
        # 创建分配通知回复
        MaintenanceReply.create_assignment_reply(
            order_id=order_id,
            assigned_to_user=staff_user,
            assigned_by_user=current_user,
            assignment_type=assignment_type
        )
        
        logging.info(f"管理员[{user_id}]成功分配维修工单 {order_id} 给维修员 {staff_user.name}")
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员[{user_id}]分配维修工单 {order_id} 给维修员 {staff_user.name}",
            result="成功",
            module="maintenance",
            operation_type="assign"
        )
        
        flash(f'维修工单已分配给维修员【{staff_user.name}】', 'success')
        return redirect(url_for('maintenance_admin.admin_order_detail', order_id=order_id))
    except Exception as e:
        logging.error(f"分配维修工单失败: {str(e)}")
        flash('分配维修工单失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_admin.admin_order_detail', order_id=order_id))


# 更新工单状态
@maintenance_admin_bp.route('/update-status/<int:order_id>', methods=['POST'])
@login_required
@require_permission('maintenance.manage')
def update_status(order_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        logging.debug(f"管理员[{user_id}]尝试更新维修工单状态，工单ID: {order_id}")
        
        # 获取工单
        order = MaintenanceOrder.get_by_id(order_id)
        
        if not order:
            logging.warning(f"管理员[{user_id}]尝试更新不存在的维修工单状态，工单ID: {order_id}")
            flash('维修工单不存在', 'error')
            return redirect(url_for('maintenance_admin.admin_order_list'))
        
        # 获取新状态
        new_status = request.form.get('status', '').strip()
        
        if not new_status:
            flash('请选择状态', 'error')
            return redirect(url_for('maintenance_admin.admin_order_detail', order_id=order_id))
        
        # 记录旧状态
        old_status = order.status
        
        # 更新状态
        order.update(status=new_status)
        
        # 如果状态为已关闭，设置closed_at
        if new_status == '已关闭':
            order.closed_at = datetime.now()
            db.session.commit()
        
        # 如果从已关闭重新开启，清除closed_at
        if old_status == '已关闭' and new_status != '已关闭':
            order.closed_at = None
            db.session.commit()
        
        # 创建状态变更通知回复
        MaintenanceReply.create_status_change_reply(
            order_id=order_id,
            old_status=old_status,
            new_status=new_status,
            user=current_user
        )
        
        logging.info(f"管理员[{user_id}]成功更新维修工单 {order_id} 状态: {old_status} -> {new_status}")
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员[{user_id}]更新维修工单 {order_id} 状态: {old_status} -> {new_status}",
            result="成功",
            module="maintenance",
            operation_type="update_status"
        )
        
        flash(f'工单状态已更新为【{new_status}】', 'success')
        return redirect(url_for('maintenance_admin.admin_order_detail', order_id=order_id))
    except Exception as e:
        logging.error(f"更新维修工单状态失败: {str(e)}")
        flash('更新维修工单状态失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_admin.admin_order_detail', order_id=order_id))


# 删除维修工单
@maintenance_admin_bp.route('/delete/<int:order_id>', methods=['POST'])
@login_required
@require_permission('maintenance.delete')
def delete_order(order_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        logging.debug(f"管理员[{user_id}]尝试删除维修工单，工单ID: {order_id}")
        
        # 获取工单
        order = MaintenanceOrder.get_by_id(order_id)
        
        if not order:
            logging.warning(f"管理员[{user_id}]尝试删除不存在的维修工单，工单ID: {order_id}")
            flash('维修工单不存在', 'error')
            return redirect(url_for('maintenance_admin.admin_order_list'))
        
        # 删除工单关联的媒体文件
        MaintenancePhotoManager.delete_all_files(order_id)
        logging.info(f"管理员[{user_id}]成功删除维修工单关联媒体文件，工单ID: {order_id}")
        
        # 删除工单
        order.delete()
        
        logging.info(f"管理员[{user_id}]成功删除维修工单，工单ID: {order_id}")
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员[{user_id}]删除维修工单 {order_id} 成功",
            result="成功",
            module="maintenance",
            operation_type="delete"
        )
        
        flash(f'维修工单删除成功，工单ID: {order_id}', 'success')
        return redirect(url_for('maintenance_admin.admin_order_list'))
    except Exception as e:
        logging.error(f"删除维修工单失败: {str(e)}")
        flash('删除维修工单失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_admin.admin_order_list'))


# 批量分配维修员
@maintenance_admin_bp.route('/batch-assign', methods=['POST'])
@login_required
@require_permission('maintenance.manage')
def batch_assign():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        # 获取工单ID列表
        order_ids = request.form.getlist('order_ids[]')
        assigned_to = request.form.get('assigned_to', '').strip()
        
        if not order_ids:
            logging.warning("请选择要分配的维修工单")
            flash('请选择要分配的维修工单', 'error')
            return redirect(url_for('maintenance_admin.admin_order_list'))
        
        if not assigned_to:
            flash('请选择维修员', 'error')
            return redirect(url_for('maintenance_admin.admin_order_list'))
        
        try:
            assigned_to_int = int(assigned_to)
        except ValueError:
            flash('无效的维修员ID', 'error')
            return redirect(url_for('maintenance_admin.admin_order_list'))
        
        # 获取维修员信息
        staff_user = User.query.get(assigned_to_int)
        if not staff_user:
            flash('维修员不存在', 'error')
            return redirect(url_for('maintenance_admin.admin_order_list'))
        
        # 转换为整数列表，添加错误处理
        valid_order_ids = []
        for id_str in order_ids:
            try:
                if id_str and id_str.strip() != '':
                    valid_order_ids.append(int(id_str))
            except (ValueError, TypeError):
                continue
        
        if not valid_order_ids:
            flash('请选择有效的维修工单进行分配', 'error')
            return redirect(url_for('maintenance_admin.admin_order_list'))
        
        logging.info(f"管理员[{user_id}] - 开始批量分配{len(valid_order_ids)}个维修工单给维修员 {staff_user.name}")
        
        # 批量分配
        assigned_count = 0
        for oid in valid_order_ids:
            order = MaintenanceOrder.get_by_id(oid)
            if order:
                order.update(assigned_to=assigned_to_int, assignment_type='manual')
                # 如果工单状态为待处理，自动更新为处理中
                if order.status == '待处理':
                    order.update(status='处理中')
                # 创建分配通知回复
                MaintenanceReply.create_assignment_reply(
                    order_id=oid,
                    assigned_to_user=staff_user,
                    assigned_by_user=current_user,
                    assignment_type='manual'
                )
                assigned_count += 1
        
        logging.info(f"管理员[{user_id}]成功批量分配{assigned_count}个维修工单给维修员 {staff_user.name}")
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员[{user_id}]成功批量分配{assigned_count}个维修工单给维修员 {staff_user.name}",
            result="成功",
            module="maintenance",
            operation_type="batch_assign"
        )
        
        flash(f'已成功分配{assigned_count}个维修工单给维修员【{staff_user.name}】', 'success')
        return redirect(url_for('maintenance_admin.admin_order_list'))
    except Exception as e:
        logging.error(f"批量分配维修工单失败: {str(e)}")
        flash('批量分配维修工单失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_admin.admin_order_list'))


# 管理员回复维修工单
@maintenance_admin_bp.route('/reply/<int:order_id>', methods=['POST'])
@login_required
@require_permission('maintenance.manage')
def admin_add_reply(order_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        logging.debug(f"管理员[{user_id}]尝试回复维修工单，工单ID: {order_id}")
        
        # 获取工单
        order = MaintenanceOrder.get_by_id(order_id)
        
        if not order:
            logging.warning(f"管理员[{user_id}]尝试回复不存在的维修工单，工单ID: {order_id}")
            flash('维修工单不存在', 'error')
            return redirect(url_for('maintenance_admin.admin_order_list'))
        
        # 获取回复内容
        content = request.form.get('content', '').strip()
        
        if not content:
            logging.warning(f"管理员[{user_id}]回复维修工单内容为空，工单ID: {order_id}")
            flash('请输入回复内容', 'error')
            return redirect(url_for('maintenance_admin.admin_order_detail', order_id=order_id))
        
        # 处理上传的附件文件
        uploaded_files_str = request.form.get('uploaded_files', '').strip()
        if uploaded_files_str:
            filenames = [f.strip() for f in uploaded_files_str.split(',') if f.strip()]
            if filenames:
                moved = MaintenancePhotoManager.move_temp_to_formal(user_id, order_id, filenames)
                logging.debug(f"管理员 {user_id} 回复时移动 {len(moved)} 个临时文件到工单 {order_id}")
                # 清理临时文件及目录
                MaintenancePhotoManager.cleanup_temp_files(user_id)
        
        # 处理直接上传的文件
        files = request.files.getlist('files')
        for file in files:
            if file and file.filename:
                filename = MaintenancePhotoManager.upload_file(file, order_id)
                if filename:
                    logging.debug(f"管理员 {user_id} 回复时上传文件 {filename} 到工单 {order_id}")
        
        # 添加回复
        MaintenanceReply.create(order_id=order_id, user_id=user_id, content=content)
        
        # 如果是管理员回复，可以将工单状态改为处理中
        if order.status == '待处理':
            order.update(status='处理中')
        
        # 检查是否需要回复并关闭
        if request.form.get('reply_and_close') == '1':
            old_status = order.status
            order.update(status='已关闭')
            # 创建状态变更通知回复
            MaintenanceReply.create_status_change_reply(
                order_id=order_id,
                old_status=old_status,
                new_status='已关闭',
                user=current_user
            )
            logging.info(f"管理员[{user_id}]回复维修工单并关闭成功，工单ID: {order_id}")
            flash('回复添加成功，工单已关闭', 'success')
        else:
            logging.info(f"管理员[{user_id}]回复维修工单成功，工单ID: {order_id}")
            flash('回复添加成功', 'success')
        
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员[{user_id}]回复维修工单 {order_id} 成功",
            result="成功",
            module="maintenance",
            operation_type="reply"
        )
        return redirect(url_for('maintenance_admin.admin_order_detail', order_id=order_id))
    except Exception as e:
        logging.error(f"管理员回复维修工单失败: {str(e)}")
        flash('回复维修工单失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_admin.admin_order_detail', order_id=order_id))


# 编辑维修工单
@maintenance_admin_bp.route('/edit/<int:order_id>', methods=['POST'])
@login_required
@require_permission('maintenance.edit')
def edit_order(order_id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        logging.debug(f"管理员[{user_id}]尝试编辑维修工单，工单ID: {order_id}")
        
        # 获取工单
        order = MaintenanceOrder.get_by_id(order_id)
        
        if not order:
            logging.warning(f"管理员[{user_id}]尝试编辑不存在的维修工单，工单ID: {order_id}")
            flash('维修工单不存在', 'error')
            return redirect(url_for('maintenance_admin.admin_order_list'))
        
        # 获取编辑字段
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        maintenance_type = request.form.get('maintenance_type', '').strip()
        priority = request.form.get('priority', '').strip()
        room_number = request.form.get('room_number', '').strip()
        
        # 构建更新数据
        update_data = {}
        if title:
            update_data['title'] = title
        if description:
            update_data['description'] = description
        if maintenance_type:
            update_data['maintenance_type'] = maintenance_type
        if priority:
            update_data['priority'] = priority
        if room_number:
            update_data['room_number'] = room_number
        
        if update_data:
            order.update(**update_data)
            logging.info(f"管理员[{user_id}]成功编辑维修工单 {order_id}")
            # 记录操作日志
            log_operation(
                user_id=user_id,
                action=f"管理员[{user_id}]编辑维修工单 {order_id} 成功",
                result="成功",
                module="maintenance",
                operation_type="edit"
            )
            flash('维修工单编辑成功', 'success')
        else:
            flash('未修改任何字段', 'info')
        
        return redirect(url_for('maintenance_admin.admin_order_detail', order_id=order_id))
    except Exception as e:
        logging.error(f"编辑维修工单失败: {str(e)}")
        flash('编辑维修工单失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_admin.admin_order_detail', order_id=order_id))


# 批量删除维修工单
@maintenance_admin_bp.route('/batch-delete', methods=['POST'])
@login_required
@require_permission('maintenance.delete')
def batch_delete():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
            
        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        
        # 获取工单ID列表
        order_ids = request.form.getlist('order_ids[]')
        
        if not order_ids:
            flash('请选择要删除的维修工单', 'error')
            return redirect(url_for('maintenance_admin.admin_order_list'))
        
        # 转换为整数列表，添加错误处理
        valid_order_ids = []
        for id_str in order_ids:
            try:
                if id_str and id_str.strip() != '':
                    valid_order_ids.append(int(id_str))
            except (ValueError, TypeError):
                continue
        
        if not valid_order_ids:
            flash('请选择有效的维修工单进行删除', 'error')
            return redirect(url_for('maintenance_admin.admin_order_list'))
        
        logging.info(f"管理员[{user_id}] - 开始批量删除{len(valid_order_ids)}个维修工单")
        
        # 批量删除
        deleted_count = 0
        for oid in valid_order_ids:
            order = MaintenanceOrder.get_by_id(oid)
            if order:
                # 删除工单关联的媒体文件
                MaintenancePhotoManager.delete_all_files(oid)
                # 删除工单
                order.delete()
                deleted_count += 1
        
        logging.info(f"管理员[{user_id}]成功批量删除{deleted_count}个维修工单")
        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员[{user_id}]成功批量删除{deleted_count}个维修工单",
            result="成功",
            module="maintenance",
            operation_type="batch_delete"
        )
        
        flash(f'已成功删除{deleted_count}个维修工单', 'success')
        return redirect(url_for('maintenance_admin.admin_order_list'))
    except Exception as e:
        logging.error(f"批量删除维修工单失败: {str(e)}")
        flash('批量删除维修工单失败，请稍后重试', 'error')
        return redirect(url_for('maintenance_admin.admin_order_list'))