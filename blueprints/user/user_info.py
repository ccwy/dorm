from flask_login import login_required, current_user
from flask import Blueprint, render_template
from models.user.user import User
from models.dorm.dorm import Dorm
from models.room.room import Room
from models.utility.utility_room_bill_occupant import RoomUtilityOccupant
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
    # 查询用户在水电费分摊表中的记录
    occupant_records = RoomUtilityOccupant.query.filter_by(user_id=user.id).all()
    
    for record in occupant_records:
        # 获取主记录信息
        main_record = record.main_record
        if main_record:
            # 获取房间信息
            room = Room.query.get(main_record.room_id)
            
            utility_info = {
                'record_id': main_record.record_id,
                'billing_period': main_record.billing_period,
                'room_id': main_record.room_id,
                'room_building': room.building if room else '',
                'room_number': room.room_number if room else '',
                'electric_fee': record.electric_fee,
                'water_fee': record.water_fee,
                'total_fee': record.total_fee,
                'reduction_fee': record.user_reduction_fee,
                'payable_fee': record.payable_fee,
                'stay_days': record.stay_days,
                'type': 'active' if record.is_transferred else 'active'
            }
            utility_records.append(utility_info)
    
    # 按账期倒序排列水电费记录
    utility_records.sort(key=lambda x: x['billing_period'], reverse=True)
    
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