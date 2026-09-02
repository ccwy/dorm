from flask import Blueprint, render_template, abort, flash, request, redirect, url_for
from utils.db import db
from models.user import User
from models.dorm import Dorm
from models.room import Room
from models.system_config import SystemConfig  # 导入系统配置模型
from models.department import Department
from config import Config
from flask_login import login_required, current_user
from utils.log import log_operation
from sqlalchemy import or_
from datetime import datetime, date

from utils.auth import require_permission
import logging

# 创建蓝图
user_bp = Blueprint('user', __name__, url_prefix='/user')
import blueprints.user_info  # 导入用户信息查看页面蓝图
# 用户管理列表（带搜索功能）
@user_bp.route('/manage')
@login_required
@require_permission('user.view')
def manage():
    try:
        search_query = request.args.get('search', '').strip()
        company = request.args.get('company', '').strip()
        department = request.args.get('department', '').strip()
        status = request.args.get('status', '').strip()
        gender = request.args.get('gender', '').strip()
        
        # 只有当请求中没有status参数时，才使用默认值
        if 'status' not in request.args:
            # 获取所有状态
            statuses = db.session.query(User.status).distinct().all()
            status_list = [s[0] for s in statuses if s[0]]
            # 查找第一个在职状态
            for stat in status_list:
                if '在职' in stat:
                    status = stat
                    break
        
        # 分页参数处理
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        # 确保per_page在合理范围内
        per_page = max(10, min(100, per_page))
        logging.info(f"分页参数: 页码={page}, 每页显示={per_page}")
        
        # 基础查询 - 关联Department表以确保公司和部门数据源统一
        query = User.query.outerjoin(Department, User.department_id == Department.id).order_by(User.id.desc())
        
        # 搜索筛选
        if search_query:
            query = query.filter(
                or_(
                    User.name.ilike(f'%{search_query}%'),
                    User.student_id.ilike(f'%{search_query}%'),
                    Department.company.ilike(f'%{search_query}%'),
                    Department.name.ilike(f'%{search_query}%'),
                    User.position.ilike(f'%{search_query}%'),
                    User.phone.ilike(f'%{search_query}%')
                )
            )
        
        # 公司筛选（通过Department表关联查询，确保数据源统一）
        if company:
            query = query.filter(Department.company == company)
        
        # 部门筛选
        if department:
            query = query.filter(Department.name == department)
            
        # 状态筛选
        logging.info(f"状态筛选值: {status}")
        if status:
            query = query.filter(User.status == status)

        # 性别筛选
        if gender:
            query = query.filter(User.gender == gender)
        
        # 执行分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        users = pagination.items
        
        # 获取所有公司用于筛选
        company_list = Department.get_all_companies()
        
        # 获取所有部门用于筛选（从Department表获取正常状态的部门）
        department_list = [d.name for d in Department.query.filter_by(status='正常').order_by(Department.name).all()]
        
        # 获取所有状态用于筛选
        statuses = db.session.query(User.status).distinct().all()
        status_list = [s[0] for s in statuses if s[0]]
        
        # 获取所有性别用于筛选
        genders = db.session.query(User.gender).distinct().all()
        gender_list = [g[0] for g in genders if g[0]]
        
        logging.info(f"加载用户管理数据成功，用户总数: {pagination.total}")
        
        # 为每个用户获取最新的住宿记录
        from models.dorm import Dorm
        user_dorm_map = {}
        for user in users:
            latest_dorm = Dorm.get_user_latest_dorm(user.id)
            user_dorm_map[user.id] = latest_dorm
            
        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='records',
            action="访问用户管理页面",
            result="成功"
        )
        return render_template(
            'user_manage/user_manage.html',
            title=f"用户管理",
            users=users,
            pagination=pagination,  # 传递分页对象
            total=pagination.total,
            page=page,
            per_page=per_page,
            search_query=search_query,
            company_filter=company,
            department_filter=department,
            status_filter=status,
            companies=company_list,
            departments=department_list,
            statuses=status_list,
            genders=gender_list,
            gender_filter=gender,
            user_dorm_map=user_dorm_map
        )
    except Exception as e:
        flash(f'加载数据失败: {str(e)}', 'danger')
        logging.error(f"加载用户管理数据失败: {str(e)}")
        return render_template(
            'user_manage/user_manage.html',
            title=f"用户管理",
            users=[],
            pagination=None,
            total=0,
            companies=[],
            departments=[],
            statuses=[],
            user_dorm_map={}
        )

# 查看用户详情
@user_bp.route('/view/<int:id>')
@login_required
@require_permission('user.view')
def view(id):
    user = User.query.get_or_404(id)
    
    # 直接获取最新的住宿记录（不通过中间方法）
    from models.dorm import Dorm
    latest_dorm = Dorm.get_user_latest_dorm(id)  # 保留模型中的获取最新记录方法
    historical_dorms = latest_dorm.dorm_chain if latest_dorm else []
    
    # 住宿状态文本转换（直接基于原始字段判断）
    boarding_status = "住宿中" if (latest_dorm and latest_dorm.status == 'active') else "未住宿"
    
    # 增加一个明确的布尔变量表示用户当前是否活跃住宿
    is_user_boarding = True if (latest_dorm and latest_dorm.status == 'active') else False
    
    # 其他状态转换保持不变...
    login_status = "允许登录" if user.is_banned else "禁止登录"
    active_status = "已激活" if user.is_active else "未激活"
    
    

    # 确保birth_date是date类型而不是datetime类型
    birth_date = user.birth_date.date() if isinstance(user.birth_date, datetime) else user.birth_date

    # 新增：获取用户的水电费记录
    from models.utility_room_bill_occupant import RoomUtilityOccupant
    from models.utility_room_bill_checkout import CheckoutUtilityRecord
    
    # 获取在住人员费用记录（按账期倒序）
    active_utility_records = RoomUtilityOccupant.query.filter_by(user_id=id)
    active_utility_records = active_utility_records.join(RoomUtilityOccupant.main_record)
    active_utility_records = active_utility_records.order_by('billing_period').all()
    
    # 获取退宿人员费用记录（按账期倒序）
    checkout_utility_records = CheckoutUtilityRecord.query.filter_by(user_id=id)
    checkout_utility_records = checkout_utility_records.order_by(CheckoutUtilityRecord.created_at.desc()).all()
    
    # 合并并按账期排序所有费用记录
    utility_records = []
    
    # 处理在住人员费用记录
    for record in active_utility_records:
        utility_records.append({
            'record_id': record.record_id,
            'billing_period': record.main_record.billing_period,
            'type': 'active',
            'electric_fee': record.electric_fee,
            'water_fee': record.water_fee,
            'total_fee': record.total_fee,
            'payable_fee': record.payable_fee,
            'stay_days': record.stay_days,
            'room_id': record.room_id,
            'room_building': record.room.building if record.room else '未知',
            'room_number': record.room.room_number if record.room else '未知',
            'created_at': record.created_at,
            'reduction_fee': record.user_reduction_fee  # 新增：在住人员减免费用
        })
    
    # 处理退宿人员费用记录
    for record in checkout_utility_records:
        # 提取账期信息（格式为YYYY-MM）
        billing_period = record.checkout_date.strftime('%Y-%m')
        utility_records.append({
            'record_id': record.record_id,
            'billing_period': billing_period,
            'type': 'checkout',
            'electric_fee': record.user_billing_electric_fee,
            'water_fee': record.user_billing_water_fee,
            'total_fee': record.user_billing_total_fee,
            'payable_fee': record.payable_fee,
            'stay_days': record.user_period_days,
            'room_id': record.room_id,
            'room_building': record.room.building if record.room else '未知',
            'room_number': record.room.room_number if record.room else '未知',
            'created_at': record.created_at,
            'reduction_fee': record.user_independent_reduction + record.user_proportional_reduction,  # 新增：退宿人员减免费用（独立减免+按比例分摊减免）
            'checkout_id': record.id  # 新增：退宿记录ID，用于跳转到编辑页面
        })
    
    # 按账期倒序排序
    utility_records.sort(key=lambda x: (x['billing_period'], x['created_at']), reverse=True)
    
    # 获取室友信息（如果用户在住）
    roommates = []
    if latest_dorm and latest_dorm.status == 'active' and latest_dorm.room_id:
        # 查询同一个房间中状态为active的其他住宿记录
        roommates_query = Dorm.query.filter(
            Dorm.room_id == latest_dorm.room_id,
            Dorm.status == 'active',
            Dorm.user_id != id  # 排除当前用户
        ).all()
        
        # 为每个室友准备信息
        for roommate_dorm in roommates_query:
            roommate = User.query.get(roommate_dorm.user_id)
            if roommate:
                roommates.append({
                    'id': roommate.id,
                    'name': roommate.name,
                    'gender': roommate.gender,
                    'check_in_date': roommate_dorm.check_in_date,
                    'stay_days': roommate_dorm.stay_days,
                    'department': roommate.department,
                    'position': roommate.position,
                    'age': roommate.get_age()
                })
    
    # 新增：获取用户的留言记录
    from models.ticket import Ticket
    user_tickets = Ticket.get_by_user_id(id)
    
    # 获取用户操作记录
    from models.user_operation_record import UserOperationRecord
    operation_records = UserOperationRecord.query.filter_by(target_user_id=id)\
        .order_by(UserOperationRecord.operation_time.desc())\
        .limit(50)\
        .all()
    
    # 准备留言数据传递给前端
    ticket_records = []
    for ticket in user_tickets:
        # 计算留言的回复数量
        reply_count = len(ticket.replies)
        
        ticket_records.append({
            'id': ticket.id,
            'title': ticket.title,
            'category': ticket.category,
            'status': ticket.status,
            'priority': ticket.priority,
            'created_at': ticket.created_at,
            'updated_at': ticket.updated_at,
            'closed_at': ticket.closed_at,
            'reply_count': reply_count
        })
    
    # 记录操作日志
    log_operation(
        user_id=current_user.id,
        action=f"查看用户信息，用户ID: {id}, [姓名: {user.name}, 工号: {user.student_id}, 类别: {user.category}, 角色: {user.role_name}]",
        module='user',
        operation_type='user_view',
        result='成功'
    )
    
    # 日期格式化辅助
    def format_datetime(dt):
        if isinstance(dt, (datetime, date)):
            return dt.strftime('%Y-%m-%d %H:%M') if isinstance(dt, datetime) else dt.strftime('%Y-%m-%d')
        return '未设置'
    current_time = datetime.now()
    current_time_formatted = format_datetime(current_time)
    logging.info(f"加载用户详情数据成功，用户ID: {id}")
    return render_template(
        'user_manage/user_view.html',
        title=f"查看用户 - {user.name}",
        user=user,
        login_status=login_status,
        active_status=active_status,
        boarding_status=boarding_status,  # 仅传递状态文本
        latest_dorm=latest_dorm,  # 直接传递最新住宿记录对象
        historical_dorms=historical_dorms,
        birth_date=birth_date,
        is_user_boarding=is_user_boarding,  # 新增：传递用户是否活跃住宿的布尔值
        format_datetime=format_datetime,
        category_options=user.category,
        current_time_formatted=current_time_formatted,
        utility_records=utility_records,  # 新增：传递水电费记录
        roommates=roommates,  # 新增：传递室友信息
        ticket_records=ticket_records,  # 新增：传递留言记录
        operation_records=operation_records  # 新增：传递操作记录
    )

