from flask_login import login_required, current_user
from flask import Blueprint, render_template
from models.user.user import User
from models.dorm.dorm import Dorm
from models.room.room import Room
from models.utility.utility_room_bill_occupant import RoomUtilityOccupant
from models.utility.utility_room_bill_checkout import CheckoutUtilityRecord
from datetime import datetime
from .user import user_bp  # 导入dorm蓝图
from utils.log import log_operation

@user_bp.route('/')
@login_required
def user_info():
    # 获取当前登录用户的信息
    user = User.query.get(current_user.id)
    
    # 获取用户最新的住宿信息
    latest_dorm = Dorm.query.filter_by(user_id=user.id, status='active').first()
    
    # 获取用户的所有住宿记录（包括历史记录）
    historical_dorms = Dorm.query.filter_by(user_id=user.id).order_by(Dorm.check_in_date.desc()).all()
    
    # 获取室友信息（如果用户当前在住）
    roommates = []
    if latest_dorm and latest_dorm.status == 'active' and latest_dorm.room:
        # 获取当前房间的所有在住人员
        active_dorms_in_room = Dorm.query.filter_by(room_id=latest_dorm.room_id, status='active').all()
        
        for dorm in active_dorms_in_room:
            # 排除自己
            if dorm.user_id != user.id:
                roommate = User.query.get(dorm.user_id)
                if roommate:
                    # 添加室友的住宿信息
                    roommate_info = {
                        'id': roommate.id,
                        'name': roommate.name,
                        'age': roommate.get_age(),
                        'gender': roommate.gender,
                        'department': roommate.department,
                        'position': roommate.position,
                        'phone': roommate.phone,
                        'check_in_date': dorm.check_in_date,
                        'stay_days': dorm.stay_days
                    }
                    roommates.append(roommate_info)
    
    # 获取用户的水电费记录
    utility_records = []
    
    # 获取在住人员费用记录（按账期倒序）
    active_utility_records = RoomUtilityOccupant.query.filter_by(user_id=user.id)
    active_utility_records = active_utility_records.join(RoomUtilityOccupant.main_record)
    active_utility_records = active_utility_records.order_by('billing_period').all()
    
    # 获取退宿人员费用记录（按账期倒序）
    checkout_utility_records = CheckoutUtilityRecord.query.filter_by(user_id=user.id)
    checkout_utility_records = checkout_utility_records.order_by(CheckoutUtilityRecord.created_at.desc()).all()
    
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
            'reduction_fee': record.user_reduction_fee
        })
    
    # 处理退宿人员费用记录
    for record in checkout_utility_records:
        # 提取账期信息（格式为YYYY-MM）
        billing_period = record.main_record.billing_period if record.main_record else record.checkout_date.strftime('%Y-%m')
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
            'reduction_fee': record.user_independent_reduction + record.user_proportional_reduction,
            'checkout_id': record.id
        })
    
    # 按账期倒序排序
    utility_records.sort(key=lambda x: (x['billing_period'], x['created_at']), reverse=True)
    
    # 格式化日期函数
    def format_datetime(dt):
        if dt:
            return dt.strftime('%Y-%m-%d')
        return ''
        
    # 记录访问日志
    log_operation(
    user_id=current_user.id,
    module='user',
    operation_type='records',
    action=f"用户[ID：{current_user.id}，姓名：{user.name}]查看个人信息",
    result="成功"
    )
    
    # 渲染模板并返回
    return render_template(
        'user_manage/user_info.html',
        title="个人信息管理",
        user=user,
        latest_dorm=latest_dorm,
        historical_dorms=historical_dorms,
        roommates=roommates,
        utility_records=utility_records,
        format_datetime=format_datetime
    )