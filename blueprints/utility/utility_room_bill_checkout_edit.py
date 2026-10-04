from flask import request, flash, redirect, url_for
from utils.db import db
from models.utility.utility_room_bill_checkout import CheckoutUtilityRecord
from models.utility.utility_room_meter import UtilityMeterReading
from flask_login import login_required, current_user
from utils.log import log_operation
from decimal import Decimal, InvalidOperation
import logging
from .utility_room_bill_checkout import utility_room_bill_checkout_bp  # 导入退宿费用子表主蓝图
# 导入权限装饰器
from utils.auth import require_permission

@utility_room_bill_checkout_bp.route('/update/<int:checkout_id>', methods=['POST'])
@login_required
@require_permission('utility.edit')
def update_checkout_data(checkout_id):
    """仅接收修改后的抄表记录，更新并重新计算费用"""
    try:
        # 1. 获取表单数据
        new_electric_reading = request.form.get('new_electric_reading')
        new_water_reading = request.form.get('new_water_reading')
        electric_price = request.form.get('electric_price')
        water_price = request.form.get('water_price')
        user_proportional_reduction = request.form.get('user_proportional_reduction')
        user_independent_reduction = request.form.get('user_independent_reduction')
        user_reduction_electric = request.form.get('user_reduction_electric')
        user_reduction_water = request.form.get('user_reduction_water')
        remarks = request.form.get('remarks')
        
        if new_electric_reading is None and new_water_reading is None:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='checkout_fee',
                action=f"更新退宿记录 [退宿记录ID: {checkout_id}]，未提供更新数据",
                result="失败"
            )
            flash('未提供更新数据', 'danger')
            return redirect(url_for('utility_index.utility_room_checkout_edit', id=checkout_id))
        
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
            flash(f'退宿记录ID={checkout_id}不存在', 'danger')
            return redirect(url_for('utility_index.utility_room_checkout_edit', id=checkout_id))
        
        # 3. 仅提取需要更新的抄表参数（已从表单获取）
        
        # 4. 调用模型方法更新退宿记录（传递抄表参数和可选的单价/减免参数）
        update_kwargs = {
            'new_electric_reading': new_electric_reading,
            'new_water_reading': new_water_reading
        }
        # 如果用户提供了单价或减免值，传递到模型层
        if electric_price is not None and electric_price != '':
            update_kwargs['electric_price'] = electric_price
        if water_price is not None and water_price != '':
            update_kwargs['water_price'] = water_price
        if user_proportional_reduction is not None and user_proportional_reduction != '':
            update_kwargs['user_proportional_reduction'] = user_proportional_reduction
        if user_independent_reduction is not None and user_independent_reduction != '':
            update_kwargs['user_independent_reduction'] = user_independent_reduction
        if user_reduction_electric is not None and user_reduction_electric != '':
            update_kwargs['user_reduction_electric'] = user_reduction_electric
        if user_reduction_water is not None and user_reduction_water != '':
            update_kwargs['user_reduction_water'] = user_reduction_water
        if remarks is not None:
            update_kwargs['remarks'] = remarks
        
        updated_record = checkout_record.update_checkout_record(**update_kwargs)
        
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
                try:
                    update_params['electric_current'] = Decimal(new_electric_reading)
                except InvalidOperation:
                    update_params['electric_current'] = new_electric_reading
            if new_water_reading is not None:
                try:
                    update_params['water_current'] = Decimal(new_water_reading)
                except InvalidOperation:
                    update_params['water_current'] = new_water_reading
                
            if update_params:
                meter_reading.update(**update_params)
        
        db.session.commit()
        
        # 6. 返回更新成功
         # 记录成功日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='checkout_fee',
            action=f"更新退宿记录 [退宿记录ID: {checkout_id}, 新电表读数: {new_electric_reading}, 新水表读数: {new_water_reading}, 电费单价: {electric_price}, 水费单价: {water_price}, 房间级减免: {user_proportional_reduction}, 个人级减免: {user_independent_reduction}, 电减免用量: {user_reduction_electric}, 水减免用量: {user_reduction_water}, 备注: {remarks}]，退宿费用已更新，抄表记录已同步",
            result="成功"
        )
        flash('退宿费用已成功更新，抄表记录已同步更新', 'success')
        return redirect(url_for('utility_index.utility_room_checkout_edit', id=checkout_id))
        
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
        flash(str(e), 'danger')
        return redirect(url_for('utility_index.utility_room_checkout_edit', id=checkout_id))
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
        flash(f'更新失败: {str(e)}', 'danger')
        return redirect(url_for('utility_index.utility_room_checkout_edit', id=checkout_id))
