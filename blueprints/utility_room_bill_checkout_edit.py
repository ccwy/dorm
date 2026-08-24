from flask import request, jsonify
from utils.db import db
from models.dorm import Dorm
from models.user import User
from models.room import Room
from models.utility_room_bill_record import RoomUtilityRecord
from models.utility_room_bill_checkout import CheckoutUtilityRecord
from models.utility_room_meter import UtilityMeterReading
from flask_login import login_required, current_user
from utils.log import log_operation
from datetime import datetime
import logging
from .utility_room_bill_checkout import utility_room_bill_checkout_bp  # 导入退宿费用子表主蓝图
# 导入admin_required装饰器
from utils.auth import admin_required

@utility_room_bill_checkout_bp.route('/edit/<int:checkout_id>', methods=['GET'])
@login_required
@admin_required
def get_checkout_edit_data(checkout_id):
    """获取退宿费用修改页面所需的初始数据（住宿天数直接从子表读取）"""
    try:
        # 1. 获取子表记录
        checkout_record = CheckoutUtilityRecord.query.get(checkout_id)
        if not checkout_record:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='utility_api',
                action=f"查询退宿修改数据 [退宿记录ID: {checkout_id}]，退宿记录不存在",
                result="失败"
            )
            return jsonify({"status": "error", "message": f"退宿记录ID={checkout_id}不存在"}), 404
        
        # 2. 获取关联的主表和房间信息
        main_record = RoomUtilityRecord.query.get(checkout_record.record_id)
        if not main_record:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='utility_api',
                action=f"查询退宿修改数据 [退宿记录ID: {checkout_id}]，关联的主账单记录不存在",
                result="失败"
            )
            return jsonify({"status": "error", "message": f"关联的主账单记录不存在"}), 404
        
        room = Room.query.get(main_record.room_id)
        if not room:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='utility_api',
                action=f"查询退宿修改数据 [退宿记录ID: {checkout_id}]，关联的房间不存在",
                result="失败"
            )
            return jsonify({"status": "error", "message": f"关联的房间不存在"}), 404
        
        # 3. 获取用户和住宿记录信息
        dorm_record = Dorm.query.filter_by(
            user_id=checkout_record.user_id,
            room_id=room.id,
            status='checked_out'
        ).first()
        
        if not dorm_record:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='utility_api',
                action=f"查询退宿修改数据 [退宿记录ID: {checkout_id}]，未找到用户的住宿记录",
                result="失败"
            )
            return jsonify({"status": "error", "message": f"未找到用户的住宿记录"}), 404
        
        user = User.query.get(checkout_record.user_id)
        if not user:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='utility_api',
                action=f"查询退宿修改数据 [退宿记录ID: {checkout_id}]，用户信息不存在",
                result="失败"
            )
            return jsonify({"status": "error", "message": f"用户信息不存在"}), 404
        
        # 4. 获取室友信息（仅显示当前账单周期内始终在本房间的人员）
        roommates = []
        
        # 确定当前账单周期的时间范围
        # 从费用主表(main_record)获取正确的账期开始时间
        # 注意：main_record是主账单记录，包含正确的账期信息
        current_checkin = main_record.start_date
        current_checkout = dorm_record.check_out_date or datetime.now()
        
        # 获取当前房间的所有住宿记录（包括在住和已退宿）
        all_dorm_records = Dorm.query.filter(
            Dorm.room_id == room.id,
            Dorm.user_id != checkout_record.user_id  # 排除当前用户
        ).all()

        # 去重用户ID，确保每个室友只显示一次
        unique_user_ids = set()
        for dorm in all_dorm_records:
            if dorm.user_id not in unique_user_ids:
                unique_user_ids.add(dorm.user_id)
                
                # 获取用户完整住宿链（考虑换宿情况）
                dorm_chain = dorm.dorm_chain
                
                # 检查该用户是否在当前账期内有住宿记录且未换宿离开
                has_valid_stay = False
                relevant_dorm = None
                
                for chain_dorm in dorm_chain:
                    # 确定该段住宿的时间范围
                    chain_checkin = chain_dorm.check_in_date
                    chain_checkout = chain_dorm.check_out_date or datetime.now()
                    
                    # 检查是否在当前房间且时间范围与账单周期重叠
                    if (chain_dorm.room_id == room.id and 
                        chain_checkin <= current_checkout and 
                        chain_checkout >= current_checkin):
                        
                        # 检查该用户在账单周期内是否有换宿记录
                        transfer_details = chain_dorm.get_transfer_details()
                        has_early_transfer = False
                        
                        # 如果有后续换宿记录，且换宿时间在账单周期内，则视为提前离开
                        if transfer_details['next']:
                            next_checkin = transfer_details['next']['check_in']
                            if isinstance(next_checkin, datetime) and current_checkin < next_checkin < current_checkout:
                                has_early_transfer = True
                        
                        # 只有没有提前换宿的才算有效室友
                        if not has_early_transfer:
                            has_valid_stay = True
                            relevant_dorm = chain_dorm
                            break
                
                if has_valid_stay and relevant_dorm:
                    rm_user = User.query.get(dorm.user_id)
                    if rm_user:
                        # 确定该用户在账单周期内的实际住宿时间
                        # 关键修改：显示室友的实际入住日期，而不是当期账单起点
                        actual_checkin = relevant_dorm.check_in_date
                        actual_checkout = relevant_dorm.check_out_date  # 只有退宿了才有退宿日期，否则为None
                        
                        # 检查是否有换宿记录
                        transfer_details = relevant_dorm.get_transfer_details()
                        has_transfer = bool(transfer_details['prev'] or transfer_details['next'])
                        
                        # 关键修改：只显示在当前账期内有有效住宿记录的室友
                        # 跳过以下情况：
                        # 1. 在用户实际入住前已经退宿的室友
                        # 2. 在账期开始前已经退宿的室友（确保按账期截断）
                        if (actual_checkout is not None and 
                            (actual_checkout < actual_checkin or actual_checkout < current_checkin)):
                            continue  # 跳过不符合账期要求的室友
                        
                        # 获取换宿记录的详细信息（根据换宿时间点确定显示内容）
                        transfer_prev_room = None
                        transfer_next_room = None
                        
                        # 1. 室友在用户退宿前换宿进宿舍，在用户退宿后换宿走的情况
                        #    显示室友从哪里换宿进来的
                        if transfer_details['prev'] and not (transfer_details['next'] and transfer_details['next']['check_in'] <= current_checkout):
                            transfer_prev_room = transfer_details['prev']['room_number']
                        
                        # 2. 室友在用户退宿前换宿走的情况
                        #    显示室友从当前宿舍换宿到其它宿舍
                        if transfer_details['next'] and transfer_details['next']['check_in'] <= current_checkout:
                            transfer_next_room = transfer_details['next']['room_number']
                        
                        # 2. 根据室友的退宿日期与用户退宿日期的关系确定状态
                        # 首先检查是否有退宿日期
                        if relevant_dorm.check_out_date:
                            # 如果有退宿日期，且退宿日期在用户退宿日期之前或当天，则显示为已退宿
                            if relevant_dorm.check_out_date <= current_checkout:
                                status_text = "已退宿"
                                status_type = "neutral"
                            else:
                                # 退宿日期晚于用户退宿日期，显示为在住，不显示退宿日期
                                status_text = "在住"
                                status_type = "success"
                                actual_checkout = None
                        else:
                            # 没有退宿日期，显示为在住，不显示退宿日期
                            status_text = "在住"
                            status_type = "success"
                            actual_checkout = None
                        
                        roommates.append({
                            "user_id": rm_user.id,
                            "name": rm_user.name,
                            "check_in_date": actual_checkin.isoformat() if actual_checkin else None,
                            "check_out_date": actual_checkout.isoformat() if actual_checkout else None,
                            "status": relevant_dorm.status,
                            "status_text": status_text,
                            "status_type": status_type,
                            "has_transfer": has_transfer,
                            "transfer_prev_room": transfer_prev_room,
                            "transfer_next_room": transfer_next_room,
                            # 新增：明确标记是否在账单周期内换宿
                            "transferred_during_period": False
                        })

        # 按入住时间排序
        roommates.sort(key=lambda x: x["check_in_date"] if x["check_in_date"] else "")
        
        # 5. 准备抄表记录和费用信息
        meter_data = {
            "electric": {
                "previous_reading": float(checkout_record.electric_previous) if checkout_record.electric_previous else 0,
                "current_reading": float(checkout_record.electric_reading) if checkout_record.electric_reading else 0,
                "meter_electric_usage": float(checkout_record.meter_electric_usage) if checkout_record.meter_electric_usage else 0,
                "user_original_electric_usage": float(checkout_record.user_original_electric_usage) if checkout_record.user_original_electric_usage else 0,
                "electric_reduction": float(checkout_record.user_reduction_electric) if checkout_record.user_reduction_electric else 0,
                "electric_billing_usage": float(checkout_record.user_billing_electric_usage) if checkout_record.user_billing_electric_usage else 0,
                "electric_price": float(checkout_record.electric_price) if checkout_record.electric_price else 0,
                
                "user_original_electric_fee": float(checkout_record.user_original_electric_fee) if checkout_record.user_original_electric_fee else 0,
                "user_billing_electric_fee": float(checkout_record.user_billing_electric_fee) if checkout_record.user_billing_electric_fee else 0
            },
            "water": {
                "previous_reading": float(checkout_record.water_previous) if checkout_record.water_previous else 0,
                "current_reading": float(checkout_record.water_reading) if checkout_record.water_reading else 0,
                "meter_water_usage": float(checkout_record.meter_water_usage) if checkout_record.meter_water_usage else 0,
                "user_original_water_usage": float(checkout_record.user_original_water_usage) if checkout_record.user_original_water_usage else 0,
                "user_reduction_water": float(checkout_record.user_reduction_water) if checkout_record.user_reduction_water else 0,
                "user_billing_water_usage": float(checkout_record.user_billing_water_usage) if checkout_record.user_billing_water_usage else 0,
                
                "water_price": float(checkout_record.water_price) if checkout_record.water_price else 0,
                
                "user_original_water_fee": float(checkout_record.user_original_water_fee) if checkout_record.user_original_water_fee else 0,
                "user_billing_water_fee": float(checkout_record.user_billing_water_fee) if checkout_record.user_billing_water_fee else 0
            }
        }
        
        # 6. 总费用信息（展示用）
        total_fee = {
            "meter_electric_fee": float(checkout_record.meter_electric_fee) if checkout_record.meter_electric_fee else 0,
            "meter_water_fee": float(checkout_record.meter_water_fee) if checkout_record.meter_water_fee else 0,
            "meter_total_fee": float(checkout_record.meter_total_fee) if checkout_record.meter_total_fee else 0,
            "user_original_total_fee": float(checkout_record.user_original_total_fee) if checkout_record.user_original_total_fee else 0,
            "user_billing_total_fee": float(checkout_record.user_billing_total_fee) if checkout_record.user_billing_total_fee else 0,
            "user_proportional_reduction": float(checkout_record.user_proportional_reduction) if checkout_record.user_proportional_reduction else 0,
            "user_independent_reduction": float(checkout_record.user_independent_reduction) if checkout_record.user_independent_reduction else 0,
            "payable_fee": float(checkout_record.payable_fee) if checkout_record.payable_fee else 0,
            "user_ratio": float(checkout_record.user_period_days / checkout_record.total_period_days) if (checkout_record.user_period_days and checkout_record.total_period_days) else 0
        }
        
        # 7. 组装返回数据
        result = {
            "status": "success",
            "data": {
                "id": checkout_record.id,
                "user_info": {
                    "user_id": user.id,
                    "name": user.name,
                    "gender": user.gender,
                    "department": user.department if hasattr(user, 'department') else "",
                    "position": user.position if hasattr(user, 'position') else ""
                },
                "room_info": {
                    "room_id": room.id,
                    "room_number": f"{room.building}{room.room_number}",
                    "check_in_date": dorm_record.check_in_date.isoformat() if dorm_record.check_in_date else None,
                    "check_out_date": dorm_record.check_out_date.isoformat() if dorm_record.check_out_date else None,
                    # 直接从子表读取的天数信息
                    "stay_days": checkout_record.stay_days,
                    "user_period_days": checkout_record.user_period_days,
                    "total_period_days": checkout_record.total_period_days,
                    "natural_days": checkout_record.natural_days,
                    "is_modifiable": False
                },
                "roommates": roommates,
                "meter_data": {
                    "electric": {** meter_data["electric"],
                        "is_modifiable": True
                    },
                    "water": {
                        **meter_data["water"],
                        "is_modifiable": True
                    }
                },
                "fee_info": total_fee
            }
        }
        # 记录成功日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='utility_api',
            action=f"查询退宿修改数据 [退宿记录ID: {checkout_id}]",
            result=f"成功"
        )
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"获取退宿修改数据失败: {str(e)}", exc_info=True)
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else 0,
            module='utility',
            operation_type='utility_api',
            action=f"查询退宿修改数据失败 [退宿记录ID: {checkout_id}]: {str(e)}",
            result="失败"
        )
        return jsonify({"status": "error", "message": f"获取数据失败: {str(e)}"}), 500
    

@utility_room_bill_checkout_bp.route('/update/<int:checkout_id>', methods=['POST'])
@login_required
@admin_required
def update_checkout_data(checkout_id):
    """仅接收修改后的抄表记录，更新并重新计算费用"""
    try:
        # 1. 获取请求数据
        data = request.get_json()
        if not data:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='checkout_fee',
                action=f"更新退宿记录 [退宿记录ID: {checkout_id}]，未提供更新数据",
                result="失败"
            )
            return jsonify({"status": "error", "message": "未提供更新数据"}), 400
        
        # 2. 获取子表记录
        checkout_record = CheckoutUtilityRecord.query.get(checkout_id)
        if not checkout_record:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='checkout_fee',
                action=f"更新退宿记录 [退宿记录ID: {checkout_id}]，退宿记录不存在",
                result="失败"
            )
            return jsonify({"status": "error", "message": f"退宿记录ID={checkout_id}不存在"}), 404
        
        # 3. 仅提取需要更新的抄表参数
        new_electric_reading = data.get('new_electric_reading')
        new_water_reading = data.get('new_water_reading')
        
        # 4. 调用模型方法更新退宿记录（仅传递抄表参数）
        updated_record = checkout_record.update_checkout_record(
            new_electric_reading=new_electric_reading,
            new_water_reading=new_water_reading
        )
        
        # 5. 同步更新对应的抄表记录（reading_type=2表示退宿抄表）
        meter_reading = UtilityMeterReading.query.filter_by(
            room_id=checkout_record.room_id,
            record_id=checkout_record.record_id,
            user_id=checkout_record.user_id,
            reading_date=checkout_record.checkout_date,
            reading_type=2  # 退宿类型抄表记录
        ).first()
        
        if meter_reading:
            # 更新抄表记录中的读数
            update_params = {}
            if new_electric_reading is not None:
                update_params['electric_current'] = new_electric_reading
            if new_water_reading is not None:
                update_params['water_current'] = new_water_reading
                
            if update_params:
                meter_reading.update(**update_params)
        
        db.session.commit()
        
        # 6. 返回更新后的费用信息
        result = {
            "status": "success",
            "message": "退宿费用已成功更新，抄表记录已同步更新",
        }
         # 记录成功日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='checkout_fee',
            action=f"更新退宿记录 [退宿记录ID: {checkout_id}, 新电表读数: {new_electric_reading}, 新水表读数: {new_water_reading}]，退宿费用已更新，抄表记录已同步",
            result="成功"
        )
        return jsonify(result)
        
    except ValueError as e:
        db.session.rollback()
        logging.warning(f"更新退宿记录参数错误: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='checkout_fee',
            action=f"更新退宿费用记录参数错误 [退宿记录ID: {checkout_id}]: {str(e)}",
            result="失败"
        )
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logging.error(f"更新退宿记录失败: {str(e)}", exc_info=True)
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else 0,
            module='utility',
            operation_type='checkout_fee',
            action=f"更新退宿费用记录失败 [退宿记录ID: {checkout_id}]: {str(e)}",
            result="失败"
        )
        return jsonify({"status": "error", "message": f"更新失败: {str(e)}"}), 500
