from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from datetime import datetime  # 修改：仅保留datetime导入，移除date
from utils.db import db
from models.dorm import Dorm
from models.user import User
from models.department import Department
from models.room import Room ,RoomStatus
from utils.log import log_operation
import logging
from sqlalchemy import func  # 新增：导入聚合函数
# 导入require_permission装饰器
from utils.auth import require_permission

# 定义dorm蓝图
dorm_bp = Blueprint(
    'dorm', 
    __name__, 
    url_prefix='/dorm', 
    template_folder='../templates',
    static_folder='../static'
)

# 导入路由（确保所有路由被注册）
from . import dorm_operations  # 包含add、edit、checkout、swap等路由
from . import dorm_resident_api  # 包含新的在住人员查询API
    
@dorm_bp.route('/manage')
@login_required
@require_permission('dorm.view')
def manage():
    """宿舍管理页面"""
    try:
        dorms = Dorm.query.join(User).join(Room).order_by(Dorm.id.desc()).all()
        log_operation(
            user_id=current_user.id,
            module='dorm',
            operation_type='records',
            action="访问宿舍管理页面",
            result="成功"
        )
        return render_template(
            'dorm_manage/dorm_index.html',
            title="宿舍管理",
            dorms=dorms
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='dorm',
            operation_type='records',
            action=f"加载宿舍管理页面失败: {str(e)}",
            result="失败"
        )
        flash(f'加载宿舍数据失败: {str(e)}', 'danger')
        return render_template('dorm_manage/dorm_index.html', title="宿舍管理", dorms=[])

@dorm_bp.route('/api/statistics')
@login_required
@require_permission('dorm.view')
def get_statistics():
    """获取数据统计信息 - 基于活跃用户数的总人数统计"""
    try:
        # --------------------------
        # 1. 用户住宿统计（核心修改）
        # --------------------------
        # 1.1 总人数：所有活跃状态的用户总数
        total_active_users = User.query.filter_by(
            status='在职' 
        ).count()
        
        # 1.2 已住宿人数：有活跃住宿记录的去重用户数
        occupied_residents = db.session.query(
            func.count(func.distinct(Dorm.user_id))
        ).filter(
            Dorm.status == 'active'  # 只统计活跃住宿
        ).scalar() or 0
        
        # 校验数据合理性
        if occupied_residents > total_active_users:
            logging.warning(
                f"数据异常：已住宿人数({occupied_residents})超过总活跃用户数({total_active_users})"
            )
        
        # --------------------------
        # 2. 房间统计
        # --------------------------
        # 2.1 总房间数（排除已关闭的）
        total_rooms = Room.query.filter(
            Room.status != RoomStatus.CLOSED.value
        ).count()
        
        # 2.2 可用房间数
        available_rooms = Room.query.filter(
            Room.status == RoomStatus.AVAILABLE.value,
            Room.capacity > 0
        ).count()

        # 2.3 可用床位数
        # 简化计算：统计所有房间的容量总和减去当前入住人数总和
        total_capacity = db.session.query(
            func.sum(Room.capacity)
        ).filter(
            Room.status != RoomStatus.CLOSED.value
        ).scalar() or 0

        total_occupancy = db.session.query(
            func.sum(Room.current_occupancy)
        ).filter(
            Room.status != RoomStatus.CLOSED.value
        ).scalar() or 0

        # 可用床位数 = 总容量 - 总当前入住人数
        available_beds_count = total_capacity - total_occupancy
        
        # --------------------------
        # 3. 退宿人数统计
        # --------------------------
        today = datetime.now()  # 修改：使用datetime.now()替代date.today()
        first_day_of_month = datetime(today.year, today.month, 1)  # 修改：使用datetime创建
        
        checkout_this_month = Dorm.query.filter(
            Dorm.status == 'checked_out',
            Dorm.check_out_date >= first_day_of_month,
            Dorm.check_out_date <= today,
            ~Dorm.next_dorms.any()  # 排除换宿记录
        ).count()
        
        # --------------------------
        # 4. 增长率计算
        # --------------------------
        last_month = today.month - 1 if today.month > 1 else 12
        last_month_year = today.year if today.month > 1 else today.year - 1
        first_day_of_last_month = datetime(last_month_year, last_month, 1)  # 修改：使用datetime创建
        
        # 计算上月最后一天
        if last_month in [4,6,9,11]:
            last_day_of_last_month = datetime(last_month_year, last_month, 30)  # 修改：使用datetime创建
        elif last_month == 2:
            if (last_month_year % 4 == 0 and last_month_year % 100 != 0) or (last_month_year % 400 == 0):
                last_day_of_last_month = datetime(last_month_year, last_month, 29)  # 修改：使用datetime创建
            else:
                last_day_of_last_month = datetime(last_month_year, last_month, 28)  # 修改：使用datetime创建
        else:
            last_day_of_last_month = datetime(last_month_year, last_month, 31)  # 修改：使用datetime创建
        
        # 上月已住宿人数（去重）
        last_month_occupied = db.session.query(
            func.count(func.distinct(Dorm.user_id))
        ).filter(
            Dorm.status == 'active',
            Dorm.updated_at >= first_day_of_last_month,
            Dorm.updated_at <= last_day_of_last_month
        ).scalar() or 0
        
        # 住宿增长率
        residents_growth = 0
        if last_month_occupied > 0:
            residents_growth = ((occupied_residents - last_month_occupied) / last_month_occupied) * 100
        
        # 可用房间增长率
        last_month_available = Room.query.filter(
            Room.status == RoomStatus.AVAILABLE.value,
            Room.capacity > 0,
            Room.updated_at >= first_day_of_last_month,
            Room.updated_at <= last_day_of_last_month
        ).count()
        
        rooms_growth = 0
        if last_month_available > 0:
            rooms_growth = ((available_rooms - last_month_available) / last_month_available) * 100
        
        # 退宿增长率
        last_month_checkout = Dorm.query.filter(
            Dorm.status == 'checked_out',
            Dorm.check_out_date >= first_day_of_last_month,
            Dorm.check_out_date <= last_day_of_last_month,
            ~Dorm.next_dorms.any()
        ).count()
        
        checkout_growth = 0
        if last_month_checkout > 0:
            checkout_growth = ((checkout_this_month - last_month_checkout) / last_month_checkout) * 100
            
        # 计算本月入住人数
        checkin_this_month = Dorm.query.filter(
            Dorm.status == 'active',
            Dorm.check_in_date >= first_day_of_month,
            Dorm.check_in_date <= today,
            ~Dorm.prev_dorm_id.isnot(None)  # 排除换宿记录，只计算新入住
        ).count()
        
        # 计算上月入住人数
        checkin_last_month = Dorm.query.filter(
            Dorm.status == 'active',
            Dorm.check_in_date >= first_day_of_last_month,
            Dorm.check_in_date <= last_day_of_last_month,
            ~Dorm.prev_dorm_id.isnot(None)  # 排除换宿记录，只计算新入住
        ).count()
        
        # 计算入住增长率
        checkin_growth = 0
        if checkin_last_month > 0:
            checkin_growth = ((checkin_this_month - checkin_last_month) / checkin_last_month) * 100
        
        # 计算可用床位数增长率
        last_month_total_capacity = db.session.query(
            func.sum(Room.capacity)
        ).filter(
            Room.status != RoomStatus.CLOSED.value,
            Room.updated_at >= first_day_of_last_month,
            Room.updated_at <= last_day_of_last_month
        ).scalar() or 0

        last_month_total_occupancy = db.session.query(
            func.sum(Room.current_occupancy)
        ).filter(
            Room.status != RoomStatus.CLOSED.value,
            Room.updated_at >= first_day_of_last_month,
            Room.updated_at <= last_day_of_last_month
        ).scalar() or 0

        last_month_available_beds_count = last_month_total_capacity - last_month_total_occupancy

        beds_growth = 0
        if last_month_available_beds_count > 0:
            beds_growth = ((available_beds_count - last_month_available_beds_count) / last_month_available_beds_count) * 100

        # 添加上月总床位数字段
        last_month_total_beds = last_month_total_capacity
        
        # 输出详细日志便于排查
        logging.info(
            f"统计结果：\n"
            f"总活跃用户数: {total_active_users}\n"
            f"已住宿人数: {occupied_residents} (去重后)\n"
            f"总房间数: {total_rooms}, 可用房间: {available_rooms}\n"
            f"本月入住: {checkin_this_month}\n"
            f"本月退宿: {checkout_this_month}"
        )

        return jsonify({
            'success': True,
            'data': {
                # 总人数/已住宿人数（基于User模型）
                'total_active_users': total_active_users,
                'occupied_residents': occupied_residents,
                'residents_growth': round(residents_growth, 1),
                
                # 房间数：总房间/可用房间
                'total_rooms': total_rooms,
                'available_rooms': available_rooms,
                'rooms_growth': round(rooms_growth, 1),
                
                # 床位数：总床位/可用床位
                'total_beds': total_capacity,
                'available_beds_count': available_beds_count,
                'beds_growth': round(beds_growth, 1),
                'last_month_total_beds': last_month_total_beds,
                'last_month_available_beds_count': last_month_available_beds_count,
                
                # 入住数据
                'checkin_this_month': checkin_this_month,
                'checkin_growth': round(checkin_growth, 1),
                
                # 退宿数据
                'checkout_this_month': checkout_this_month,
                'checkout_growth': round(checkout_growth, 1)
            }
        })
    except Exception as e:
        logging.error(f"统计接口错误: {str(e)}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
    

@dorm_bp.route('/api/recent_operations')
@login_required
@require_permission('dorm.view')
def get_recent_operations():
    """获取最近操作记录（调用换宿链并过滤换宿过程中的退宿）"""
    try:
        # 获取所有住宿记录，按更新时间降序排序
        all_dorms = Dorm.query.order_by(Dorm.updated_at.desc()).all()
        
        operations = []
        processed_operations = set()  # 用于记录已处理的操作，避免重复
        
        for dorm in all_dorms:
            # 创建一个唯一标识来避免重复处理同一操作
            operation_key = f"{dorm.user_id}_{dorm.id}_{dorm.updated_at}"
            if operation_key in processed_operations:
                continue
            
            # 检查是否是换宿过程中产生的退宿记录
            is_transfer_checkout = False
            if dorm.status == 'checked_out' and dorm.next_dorms:
                # 如果当前记录是已退宿状态，且有后续记录，可能是换宿过程中的退宿
                # 遍历所有后续记录（而不是只看第一条）
                for next_dorm in dorm.next_dorms:
                    if next_dorm.status == 'active' and next_dorm.prev_dorm_id == dorm.id:
                        # 后续有活跃记录，且是从当前记录转换过来的，说明是换宿过程中的退宿
                        is_transfer_checkout = True
                        break
                
                # 过滤掉换宿过程中产生的退宿记录
                if is_transfer_checkout:
                    processed_operations.add(operation_key)
                    continue
            
            # 确定操作类型
            if dorm.status == 'active' and not dorm.check_out_date:
                # 检查是否有前序记录，判断是新分配还是换宿
                if dorm.prev_dorm_id:
                    operation_type = 'change'  # 更换宿舍
                else:
                    operation_type = 'allocate'  # 分配宿舍
            else:
                operation_type = 'checkout'  # 正常的退宿记录
            
            # 获取用户信息
            user = User.query.get(dorm.user_id)
            user_name = user.name if user else f"未知用户(ID:{dorm.user_id})"
            
            # 获取房间信息
            room_info = f"{dorm.room.building}{dorm.room.room_number}" if dorm.room else f"未知房间(ID:{dorm.room_id})"
            
            # 如果是换宿，获取前后房间信息
            if operation_type == 'change' and dorm.prev_dorm:
                prev_room = Room.query.get(dorm.prev_dorm.room_id)
                if prev_room:
                    prev_room_info = f"{prev_room.building}{prev_room.room_number}"
                    room_info = f"{prev_room_info} → {room_info}"
            
            # 操作人信息
            operator_name = "系统"  # 实际应用中可以从操作日志中获取
            
            # 格式化操作时间
            operation_time = dorm.updated_at.strftime('%Y-%m-%d %H:%M')
            
            operations.append({
                'time': operation_time,
                'type': operation_type,
                'user_name': user_name,
                'user_id': dorm.user_id,
                'room_info': room_info,
                'operator': operator_name,
                'type_text': {
                    'allocate': '分配宿舍',
                    'change': '更换宿舍',
                    'checkout': '办理退宿'
                }[operation_type]
            })
            
            processed_operations.add(operation_key)
            
            # 如果已经收集了10条记录，停止
            if len(operations) >= 10:
                break
        
        # 按时间排序并限制为10条
        operations.sort(key=lambda x: x['time'], reverse=True)
        operations = operations[:10]
        
        return jsonify({
            'success': True,
            'data': operations
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500



#增加在住人员查询页面 - 重构版
@dorm_bp.route('/query')
@login_required
@require_permission('dorm.view')
def dorm_query():
    """在住人员查询页面（支持分页、搜索和筛选）"""
    
    try:
        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='dorm',
            operation_type='records',
            action="访问在住人员列表查询页面",
            result="成功"
        )
        
        # 获取请求参数
        search_query = request.args.get('searchQuery', '', type=str).strip()
        department_filter = request.args.get('department', '', type=str).strip()
        gender_filter = request.args.get('gender', '', type=str).strip()
        building_filter = request.args.get('building', '', type=str).strip()
        
        # 分页参数
        try:
            page = request.args.get('page', 1, type=int)
            if page < 1:
                page = 1
        except ValueError:
            page = 1
            
        try:
            per_page = request.args.get('per_page', 20, type=int)
            if per_page < 1 or per_page > 100:
                per_page = 20
        except ValueError:
            per_page = 20
        
        # 构建查询，筛选出活跃的住宿记录
        query = db.session.query(Dorm).filter(
            Dorm.status == 'active',
            Dorm.check_out_date.is_(None)
        )
        
        # 关联用户表和房间表
        query = query.join(User).join(Room)
        
        # 应用搜索条件
        if search_query:
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    User.name.ilike(f'%{search_query}%'),
                    Room.room_number.ilike(f'%{search_query}%')
                )
            )
            
        # 应用部门筛选
        if department_filter:
            query = query.join(Department, User.department_id == Department.id).filter(Department.name == department_filter)
            
        # 应用性别筛选
        if gender_filter:
            query = query.filter(User.gender == gender_filter)
            
        # 应用楼栋筛选
        if building_filter:
            query = query.filter(Room.building == building_filter)
            
        # 执行分页查询
        pagination = query.order_by(Dorm.id.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # 处理每个住宿记录，提取换宿链信息
        residents_data = []
        today = datetime.now()
        
        for dorm in pagination.items:
            user = dorm.user
            room = dorm.room
            
            # 获取完整换宿链
            dorm_chain = dorm.dorm_chain
            
            # 计算当前住宿天数（使用与Dorm模型一致的计算方法）
            check_in_date = dorm.check_in_date
            if check_in_date:
                # 只比较日期部分，忽略时间
                check_in_date_only = check_in_date.date() if isinstance(check_in_date, datetime) else check_in_date
                today_date_only = today.date() if isinstance(today, datetime) else today
                
                # 计算日期差，加1天确保入住当天被计算在内
                if today_date_only >= check_in_date_only:
                    delta_days = (today_date_only - check_in_date_only).days
                    current_stay_days = delta_days + 1
                else:
                    current_stay_days = 0
            else:
                current_stay_days = 0
            
            # 计算累计住宿天数（使用与Dorm模型一致的计算方法）
            total_stay_days = current_stay_days
            for record in dorm_chain:
                if record != dorm and record.check_out_date and record.check_in_date:
                    # 只比较日期部分，忽略时间
                    check_in_date_only = record.check_in_date.date() if isinstance(record.check_in_date, datetime) else record.check_in_date
                    check_out_date_only = record.check_out_date.date() if isinstance(record.check_out_date, datetime) else record.check_out_date
                    
                    # 计算日期差，加1天确保入住当天被计算在内
                    if check_out_date_only >= check_in_date_only:
                        delta_days = (check_out_date_only - check_in_date_only).days
                        total_stay_days += delta_days + 1
            
            # 构建人员数据
            resident_info = {
                'id': user.id,
                'name': user.name,
                'username': user.username,
                'gender': user.gender,
                'age': user.get_age(),
                'department': user.department,
                'position': user.position,
                'current_room': f"{room.building}{room.room_number}",
                'building': room.building,
                'room_number': room.room_number,
                'room_id': room.id,  # 添加房间ID，用于跳转详情页面
                'room': room,  # 添加完整的room对象引用
                'check_in_date': check_in_date,
                'current_stay_days': current_stay_days,
                'total_stay_days': total_stay_days,
                'dorm_chain': dorm_chain  # 完整换宿链
            }
            
            residents_data.append(resident_info)
            
        # 获取所有部门用于筛选下拉框
        department_list = [d.name for d in Department.query.filter_by(status='正常').order_by(Department.name).all()]
        
        # 获取所有楼栋用于筛选下拉框
        buildings = db.session.query(Room.building).distinct().filter(
            Room.building.isnot(None),
            Room.building != ''
        ).all()
        building_list = [b[0] for b in buildings]
        
        # 生成页码范围
        from blueprints.room import generate_page_range
        page_range = generate_page_range(page, pagination.pages)
        
        # 判断是否为空状态（没有任何筛选条件且没有数据）
        is_empty_state = len(residents_data) == 0 and not any([search_query, department_filter, gender_filter, building_filter])
        
        # 返回渲染模板
        return render_template(
            'dorm_manage/dorm_query.html',
            title="在住人员查询",
            residents=residents_data,
            pagination=pagination,
            page_range=page_range,
            departments=department_list,
            buildings=building_list,
            search_query=search_query,
            department_filter=department_filter,
            gender_filter=gender_filter,
            building_filter=building_filter,
            per_page=per_page,
            today=today,
            is_empty_state=is_empty_state
        )
        
    except Exception as e:
        logging.error(f"在住人员查询页面异常: {str(e)}", exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='dorm',
            operation_type='records',
            action=f"尝试访问在住人员查询页面失败: {str(e)}",
            result="失败"
        )
        flash(f'页面加载失败: {str(e)}', 'danger')
        # 失败时返回管理页，保持流程连贯
        return render_template(
            'dorm_manage/dorm_query.html',
            title="在住人员查询",
            residents=[],
            pagination=None,
            departments=[],
            buildings=[],
            search_query='',
            department_filter='',
            gender_filter='',
            building_filter='',
            per_page=20,
            today=datetime.now()
        )


@dorm_bp.route('/dorm_query_2')
@login_required
@require_permission('dorm.view')
def dorm_query_2():
    """显示宿舍分配表页面，默认显示所有房间"""
    # 获取查询参数（只保留搜索功能）
    search_query = request.args.get('search', '').strip()
    
    # 一次性查询所有必要数据，减少数据库交互
    # 1. 查询所有非关闭状态的房间信息
    rooms = Room.query.filter(Room.status != RoomStatus.CLOSED.value).all()
    
    # 2. 查询所有活跃的住宿记录，并按房间ID分组
    all_dorm_records = Dorm.query.filter_by(status='active').all()
    dorm_records_by_room = {}
    for record in all_dorm_records:
        if record.room_id not in dorm_records_by_room:
            dorm_records_by_room[record.room_id] = []
        dorm_records_by_room[record.room_id].append(record)
    
    # 3. 查询所有用户信息，构建ID到用户的映射
    all_users = User.query.all()
    user_map = {user.id: user for user in all_users}
    
    # 处理搜索
    filtered_rooms = []
    if search_query:
        for room in rooms:
            # 检查房间号是否匹配
            room_number = f"{room.building}{room.room_number}"
            if search_query in room_number:
                filtered_rooms.append(room)
                continue
                
            # 检查居住人员是否匹配（使用内存中的数据）
            room_records = dorm_records_by_room.get(room.id, [])
            residents = [user_map.get(record.user_id) for record in room_records if record.user_id in user_map]
            if any(search_query in resident.name for resident in residents if resident):
                filtered_rooms.append(room)
        rooms = filtered_rooms
    
    # 按楼栋分组并计算各区域统计数据
    regions = {}
    region_stats = {}
    for room in rooms:
        building = room.building
        if building not in regions:
            regions[building] = []
            region_stats[building] = {
                'total_rooms': 0,
                'occupied_rooms': 0,
                'vacant_rooms': 0,
                'total_residents': 0,
                'total_beds': 0,
                'occupied_beds': 0,
                'available_beds': 0
            }
            
        # 使用内存中的住宿记录数据
        room_records = dorm_records_by_room.get(room.id, [])
        resident_count = len(room_records)
        
        # 更新区域统计数据
        region_stats[building]['total_rooms'] += 1
        region_stats[building]['total_residents'] += resident_count
        region_stats[building]['total_beds'] += room.capacity
        region_stats[building]['occupied_beds'] += room.current_occupancy
        region_stats[building]['available_beds'] += (room.capacity - room.current_occupancy)
        if resident_count > 0:
            region_stats[building]['occupied_rooms'] += 1
        
        # 获取居住人员信息（使用内存中的用户映射）
        residents = [user_map.get(record.user_id) for record in room_records if record.user_id in user_map]
        
        # 计算空置床位
        vacant_beds = room.capacity - len(residents)
        
        # 构建房间信息字典
        room_info = {
            'id': room.id,
            'room_number': f"{room.building}{room.room_number}",
            'gender': room.gender_restriction,
            'level': room.room_level,
            'room_type': room.room_type,
            'capacity': room.capacity,
            'current_occupancy': room.current_occupancy,
            'residents': residents,
            'vacant_beds': vacant_beds,
            'remark': room.remark
        }
        
        regions[building].append(room_info)

    # 计算各区域的空置房间数
    for building in region_stats:
        region_stats[building]['vacant_rooms'] = (
            region_stats[building]['total_rooms'] - 
            region_stats[building]['occupied_rooms']
        )

    # 计算总统计数据
    total_stats = {
        'total_rooms': sum(stats['total_rooms'] for stats in region_stats.values()),
        'occupied_rooms': sum(stats['occupied_rooms'] for stats in region_stats.values()),
        'vacant_rooms': sum(stats['vacant_rooms'] for stats in region_stats.values()),
        'total_residents': sum(stats['total_residents'] for stats in region_stats.values()),
        'total_beds': sum(stats['total_beds'] for stats in region_stats.values()),
        'occupied_beds': sum(stats['occupied_beds'] for stats in region_stats.values()),
        'available_beds': sum(stats['available_beds'] for stats in region_stats.values())
    }
    
    # 记录访问日志
    log_operation(
    user_id=current_user.id,
    module='dorm',
    operation_type='records',
    action="访问在住人员表单式页面",
    result="成功"
    )

    # 直接返回所有房间，不再做数量限制
    return render_template(
        'dorm_manage/dorm_query_2.html', 
        title="在住人员查询",
        regions=regions,  # 传递所有房间
        original_regions=regions,  # 保持一致，都为所有房间
        stats=total_stats,
        region_stats=region_stats,
        search_query=search_query
    )
    

# 宿舍操作记录查询页面
@dorm_bp.route('/records')
@login_required
@require_permission('dorm.view')
def dorm_records():
    """宿舍操作记录查询页面"""
    try:
        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='dorm',
            operation_type='records',
            action="访问宿舍操作记录查询页面",
            result="成功"
        )
        
        # 仅渲染页面，数据由前端通过API获取
        return render_template(
            'dorm_manage/dorm_records.html',
            title="宿舍操作记录查询"
        )
        
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='dorm',
            operation_type='records',
            action="尝试访问宿舍操作记录查询页面",
            result=f"失败: {str(e)}"
        )
        flash(f'页面加载失败: {str(e)}', 'danger')
        return render_template(
            'dorm_manage/dorm_records.html',
            title="宿舍操作记录查询"
        )
