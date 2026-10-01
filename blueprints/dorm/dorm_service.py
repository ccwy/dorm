# --------------------------
# 宿舍业务服务函数（供申请审核approve()调用）
# 从dorm_operations蓝图端点提取的完整业务逻辑，去除Web层依赖
# --------------------------
from utils.db import db
from models.dorm.dorm import Dorm
from models.user.user import User
from models.room.room import Room
from models.room.room_bed import Bed
from models.fee_subsidy.fee_subsidy import FeeSubsidy
from models.utility.utility_room_meter import UtilityMeterReading
from models.utility.utility_room_bill_checkout import CheckoutUtilityRecord
from flask_login import current_user
import logging


def do_allocation(user_id, room_id, bed_id, check_in_date, operator_id=None, remarks=''):
    """完整分配业务逻辑：模型层分配 + 禁用外宿/住宿补贴 + 清零补贴金额

    Args:
        user_id: 用户ID
        room_id: 房间ID
        bed_id: 床位ID
        check_in_date: 入住日期
        operator_id: 操作人ID（可选，默认取current_user）
        remarks: 备注

    Returns:
        dict: {'new_dorm': Dorm对象, 'subsidies_disabled': bool, 'subsidies_count': int}
    """
    # 1. 执行模型层分配操作
    new_dorm = Dorm.create_allocation(
        user_id=user_id, room_id=room_id, bed_id=bed_id,
        check_in_date=check_in_date, remarks=remarks
    )

    # 2. 禁用用户的外宿补贴和住宿补贴
    subsidies_disabled = False
    subsidies_count = 0
    try:
        active_lodging_subsidies = FeeSubsidy.query.filter(
            FeeSubsidy.user_id == user_id,
            FeeSubsidy.fee_type.in_(['外宿补贴', '住宿补贴']),
            FeeSubsidy.is_enabled == True
        ).all()
        if active_lodging_subsidies:
            subsidies_disabled = True
            subsidies_count = len(active_lodging_subsidies)
            op_id = operator_id if operator_id is not None else (current_user.id if hasattr(current_user, 'id') and current_user.is_authenticated else 0)
            for subsidy in active_lodging_subsidies:
                subsidy.is_enabled = False
                subsidy.change_reason = f"分配宿舍自动禁用: {remarks}"
                subsidy.operator_id = op_id
                db.session.add(subsidy)
            user = User.query.get(user_id)
            if user:
                user.lodging_allowance = 0
                db.session.add(user)
            logging.info(f"用户ID {user_id}的外宿/住宿补贴已自动禁用，共{subsidies_count}条记录")
    except Exception as e:
        logging.error(f"禁用用户外宿/住宿补贴时发生错误：{str(e)}")

    return {'new_dorm': new_dorm, 'subsidies_disabled': subsidies_disabled, 'subsidies_count': subsidies_count}


def do_change(user_id, target_room_id, reason="自愿换宿", change_date=None, operator_id=None):
    """完整换宿业务逻辑：用户/房间验证 + 模型层换宿

    Args:
        user_id: 用户ID
        target_room_id: 目标房间ID
        reason: 换宿原因
        change_date: 换宿日期
        operator_id: 操作人ID（可选）

    Returns:
        dict: {'new_dorm': Dorm对象, 'old_dorm': Dorm对象, 'user': User对象, 'target_room': Room对象}
    """
    user = User.query.get(user_id)
    if not user:
        raise ValueError(f"用户不存在（ID: {user_id}）")
    target_room = Room.query.get(target_room_id)
    if not target_room:
        raise ValueError(f"目标宿舍不存在（ID: {target_room_id}）")

    new_dorm = Dorm.change_dorm(
        user_id=user_id, target_room_id=target_room_id,
        reason=reason, change_date=change_date
    )
    old_dorm = new_dorm.prev_dorm
    return {'new_dorm': new_dorm, 'old_dorm': old_dorm, 'user': user, 'target_room': target_room}


def do_checkout(user_id, check_out_date, checkout_type='在职退宿',
                water_current=None, electric_current=None,
                operator_id=None, remarks='', billing_period=None):
    """完整退宿业务逻辑：模型层退宿 + 补贴禁用 + 用户状态更新 + 抄表 + 费用计算

    Args:
        user_id: 用户ID
        check_out_date: 退宿日期
        checkout_type: 退宿类型（在职退宿/离职退宿/自离退宿）
        water_current: 水表读数（可选）
        electric_current: 电表读数（可选）
        operator_id: 操作人ID（可选，默认取current_user）
        remarks: 备注
        billing_period: 账期（格式YYYY-MM，必填，自离退宿时可选）

    Returns:
        dict: {'dorm': Dorm对象, 'subsidies_disabled': bool, 'subsidies_count': int,
               'checkout_record': CheckoutUtilityRecord或None, 'calculate_fee': bool}
    """
    user = User.query.get(user_id)
    if not user:
        raise ValueError(f"用户不存在（ID: {user_id}）")
    current_dorm = Dorm.query.filter(
        Dorm.user_id == user_id, Dorm.status == 'active',
        Dorm.check_out_date.is_(None)
    ).with_for_update().first()
    if not current_dorm:
        raise ValueError(f"用户{user_id}无当前有效住宿记录，无法退宿")

    # 1. 执行模型层退宿操作
    current_dorm.check_out(check_out_date=check_out_date, remarks=remarks, billing_period=billing_period)

    result = {'dorm': current_dorm, 'subsidies_disabled': False, 'subsidies_count': 0,
              'checkout_record': None, 'calculate_fee': False}

    op_id = operator_id if operator_id is not None else (current_user.id if hasattr(current_user, 'id') and current_user.is_authenticated else None)

    if checkout_type == '自离退宿':
        # 自离退宿：禁用住宿补贴 + 更新用户状态为自离，不计算费用
        try:
            user_subsidies = FeeSubsidy.query.filter(
                FeeSubsidy.user_id == user_id, FeeSubsidy.is_enabled == True,
                FeeSubsidy.fee_type == "住宿补贴"
            ).all()
            if user_subsidies:
                result['subsidies_disabled'] = True
                result['subsidies_count'] = len(user_subsidies)
                for subsidy in user_subsidies:
                    FeeSubsidy.disabled_subsidy(
                        subsidy_id=subsidy.id, operator_id=op_id,
                        reason=f"用户 {user.name} 自离退宿自动禁用（退宿日期：{check_out_date.strftime('%Y-%m-%d %H:%M:%S')}）"
                    )
                logging.info(f"成功禁用用户ID={user_id},{user.name}的所有住宿补贴，共{len(user_subsidies)}条记录")
        except Exception as e:
            logging.error(f"禁用用户住宿补贴时发生错误：{str(e)}")

        user.status = '自离'
        user.is_active = False
        user.is_banned = False
        db.session.add(user)

    else:
        # 在职退宿/离职退宿：抄表 + 费用计算 + 禁用住宿补贴 + 更新用户状态
        room_id = current_dorm.room_id

        # 创建水电表抄表记录
        if water_current is not None or electric_current is not None:
            UtilityMeterReading.create_reading(
                room_id=room_id,
                water_current=water_current if water_current is not None else None,
                electric_current=electric_current if electric_current is not None else None,
                reading_date=check_out_date,
                meter_reader_id=op_id,
                reading_type=2,  # 退宿抄表
                user_id=user_id,
                billing_period=billing_period,
                notes=f"退宿抄表：{user.name if user else '未知用户'}，{check_out_date.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            logging.info(f"添加{user.name}的退宿抄表记录：房间ID={room_id}, 用户ID={user_id}, 水表读数={water_current}, 电表读数={electric_current}")

        # 计算退宿费用
        calculate_fee = (water_current is not None) and (electric_current is not None)
        checkout_record = CheckoutUtilityRecord.create_from_checkout(
            room_id=room_id,
            user_id=user_id,
            checkout_date=check_out_date,
            electric_reading=electric_current,
            water_reading=water_current,
            billing_period=billing_period,
            remarks=f"退宿费用计算：{user.name if user else '未知用户'}，退宿日期：{check_out_date.strftime('%Y-%m-%d %H:%M:%S')}",
            calculate_fee=calculate_fee,
            dorm_id=current_dorm.id
        )
        result['checkout_record'] = checkout_record
        result['calculate_fee'] = calculate_fee
        logging.info(f"计算{user.name}的退宿费用：房间ID={room_id}, 用户ID={user_id}, 是否计算费用={calculate_fee}")
        if calculate_fee:
            logging.info(f"退宿费用计算结果：房间ID={room_id}, 用户ID={user_id}, 总费用={checkout_record.payable_fee}")

        # 禁用住宿补贴
        try:
            user_subsidies = FeeSubsidy.query.filter(
                FeeSubsidy.user_id == user_id, FeeSubsidy.is_enabled == True,
                FeeSubsidy.fee_type == "住宿补贴"
            ).all()
            if user_subsidies:
                result['subsidies_disabled'] = True
                result['subsidies_count'] = len(user_subsidies)
                for subsidy in user_subsidies:
                    FeeSubsidy.disabled_subsidy(
                        subsidy_id=subsidy.id, operator_id=op_id,
                        reason=f"用户 {user.name} 退宿自动禁用（退宿日期：{check_out_date.strftime('%Y-%m-%d %H:%M:%S')}）"
                    )
                logging.info(f"成功禁用用户ID={user_id},{user.name}的所有住宿补贴，共{len(user_subsidies)}条记录")
        except Exception as e:
            logging.error(f"禁用用户住宿补贴时发生错误：{str(e)}")

        # 更新用户状态
        if checkout_type == '离职退宿':
            user.status = '离职'
            user.is_active = False
            user.is_banned = False
        elif checkout_type == '在职退宿':
            user.status = '在职'
        db.session.add(user)

    return result