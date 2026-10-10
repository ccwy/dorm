from flask_login import login_required, current_user
from flask import Blueprint, render_template, redirect, url_for, flash, request
from models.user.user import User
from models.dorm.dorm import Dorm
from models.room.room import Room
from models.utility.utility_room_bill_occupant import RoomUtilityOccupant
from models.utility.utility_room_bill_checkout import CheckoutUtilityRecord
from datetime import datetime
from .user import user_bp  # 导入user蓝图
from utils.log import log_operation
from utils.auth import require_permission
from models.system_config.system_config import SystemConfig
from utils.db import db
import logging

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
                        'stay_days': dorm.stay_days,
                        'bed_number': dorm.bed.bed_number if dorm.bed else None
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
        format_datetime=format_datetime,
        bed_management_enabled=SystemConfig.get_config_value('ROOM_BED_MANAGEMENT_ENABLED', True),
    )


@user_bp.route('/change_password', methods=['POST'])
@login_required
@require_permission('user.change_own_password')
def change_password():
    current_password = request.form.get('current_password', '')
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    # 检查系统是否允许用户修改密码
    if not SystemConfig.get_config_value('ALLOW_USER_CHANGE_PASSWORD', True):
        flash('系统未开启用户修改密码功能', 'error')
        return redirect(url_for('user.user_info'))

    # 从session获取当前用户ID（不从表单获取，防止越权攻击）
    user_id = current_user.id
    user = User.query.get(user_id)

    # 显式验证用户身份
    if not user:
        logging.warning(f'修改密码失败：用户身份验证失败，用户ID[{user_id}]在数据库中不存在')
        flash('用户身份验证失败，请重新登录', 'error')
        return redirect(url_for('user.user_info'))

    # 验证当前密码（重新认证）
    if not user.check_password(current_password):
        logging.warning(f'用户[ID：{user_id}]修改密码失败：当前密码错误')
        flash('当前密码错误', 'error')
        return redirect(url_for('user.user_info'))

    # 验证新密码长度
    if len(new_password) < 6:
        logging.warning(f'用户[ID：{current_user.id}]修改密码失败：新密码长度不足6位')
        flash('新密码长度至少6位', 'error')
        return redirect(url_for('user.user_info'))

    # 验证新密码和确认密码一致
    if new_password != confirm_password:
        logging.warning(f'用户[ID：{current_user.id}]修改密码失败：两次输入的新密码不一致')
        flash('两次输入的新密码不一致', 'error')
        return redirect(url_for('user.user_info'))

    # 修改密码
    user.set_password(new_password)
    db.session.commit()
    log_operation(
        user_id=current_user.id,
        module='user',
        operation_type='user_set_password',
        action=f'用户[ID：{current_user.id}，姓名：{user.name}]修改密码',
        result='成功'
    )
    flash('密码修改成功', 'success')
    return redirect(url_for('user.user_info'))