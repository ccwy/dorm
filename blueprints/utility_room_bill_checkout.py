from flask import Blueprint, request, jsonify, make_response
import logging
from utils.db import db
from models.dorm import Dorm
from models.user import User
from models.room import Room
from models.utility_room_bill_record import RoomUtilityRecord
from models.utility_room_bill_checkout import CheckoutUtilityRecord
from models.utility_room_meter import UtilityMeterReading
from flask_login import login_required, current_user
from utils.log import log_operation
import traceback
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from sqlalchemy import func
# 新增：导入系统配置模型
from models.system_config import SystemConfig
from io import BytesIO
from urllib.parse import quote
# 导入权限装饰器
from utils.auth import require_permission

utility_room_bill_checkout_bp = Blueprint('utility_room_bill_checkout', __name__, url_prefix='/utility_room_bill_checkout')

from . import utility_room_bill_checkout_operations  # 增加删除蓝图
from . import utility_room_bill_checkout_edit  # 编辑蓝图
from . import utility_room_bill_checkout_export  # 导出蓝图

@utility_room_bill_checkout_bp.route('/checkout_query', methods=['POST'])
@login_required
@require_permission('utility.view')
def query_checkout_records():
    """
    退宿人员费用查询接口（POST方式）
    支持账期(yyyy-mm)、用户ID、房间ID的组合查询
    返回包含水电费抄表记录、费用信息的JSON格式数据
    """
    try:
        # 从POST请求的JSON数据中获取查询参数
        data = request.get_json() or {}
        
        # 提取核心查询参数
        user_id_str = data.get('user_id')
        try:
            user_id = int(user_id_str) if user_id_str is not None else 0
        except ValueError:
            # 处理无法转换为整数的情况
            user_id = 0  # 或根据业务逻辑抛出异常

        room_id_str = data.get('room_id')
        try:
            room_id = int(room_id_str) if room_id_str is not None else 0
        except ValueError:
            # 处理无法转换为整数的情况
            room_id = 0  # 或根据业务逻辑抛出异常

        billing_period = str(data.get('billing_period', '')).strip()
        
        # 验证账期格式（如果提供）
        if billing_period:
            try:
                # 仅验证格式是否为yyyy-mm
                datetime.strptime(billing_period, '%Y-%m')
            except ValueError:
                log_operation(
                    user_id=current_user.id,
                    module='utility',
                    operation_type='utility_api',
                    action=f"查询退宿记录 [用户ID: {user_id}, 房间ID: {room_id}, 账期: {billing_period}]失败，账期格式错误",
                    result="失败"
                )
                return jsonify({
                    'success': False, 
                    'message': '账期格式错误，应为YYYY-MM'
                }), 400
        
        # 构建查询
        query = CheckoutUtilityRecord.query.join(
            RoomUtilityRecord, 
            CheckoutUtilityRecord.record_id == RoomUtilityRecord.record_id
        )
        
        # 应用组合查询条件
        if user_id:
            query = query.filter(CheckoutUtilityRecord.user_id == user_id)
        
        if room_id:
            query = query.filter(RoomUtilityRecord.room_id == room_id)
        
        if billing_period:
            query = query.filter(RoomUtilityRecord.billing_period == billing_period)
        
        # 处理分页参数
        page = data.get('page', 1)
        per_page = data.get('per_page', 20)
        
        # 确保分页参数为整数且合理
        try:
            page = int(page)
            per_page = int(per_page)
            per_page = min(per_page, 100)  # 限制最大每页数量
            page = max(page, 1)  # 确保页码至少为1
        except (ValueError, TypeError):
            page = 1
            per_page = 20
        
        # 执行分页查询
        paginated_records = query.order_by(CheckoutUtilityRecord.checkout_date.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        # 处理查询结果
        records = []
        for record in paginated_records.items:
            main_record = RoomUtilityRecord.query.get(record.record_id)
            room = Room.query.get(main_record.room_id) if main_record else None
            user = User.query.get(record.user_id) if record.user_id else None
            
            records.append({
                'id': record.id,
                'record_id': record.record_id,
                'billing_period': main_record.billing_period if main_record else None,
                'user': {
                    'id': user.id if user else None,
                    'name': user.name if user else None,
                    'department': user.department if user else None
                } if user else None,
                'room': {
                    'id': room.id if room else None,
                    'full_room': f"{room.building}{room.room_number}" if (room and room.building and room.room_number) else None
                } if room else None,
                'time_info': {
                    'checkout_date': record.checkout_date.isoformat() if record.checkout_date else None,
                    'user_period_days': record.user_period_days,
                },
                'electric_meter': {
                    'electric_reading': float(record.electric_reading) if record.electric_reading else None,
                    'electric_previous': float(record.electric_previous) if record.electric_previous else None,
                    'meter_electric_usage': float(record.meter_electric_usage) if record.meter_electric_usage else None,
                    'user_original_electric_usage': float(record.user_original_electric_usage) if record.user_original_electric_usage else None,
                    'user_reduction_electric': float(record.user_reduction_electric) if record.user_reduction_electric else None,
                    'user_billing_electric_usage': float(record.user_billing_electric_usage) if record.user_billing_electric_usage else None,
                    'user_original_electric_fee': float(record.user_original_electric_fee) if record.user_original_electric_fee else None,
                    'user_billing_electric_fee': float(record.user_billing_electric_fee) if record.user_billing_electric_fee else None,
                },
                'water_meter': {
                    'water_reading': float(record.water_reading) if record.water_reading else None,
                    'water_previous': float(record.water_previous) if record.water_previous else None,
                    'meter_water_usage': float(record.meter_water_usage) if record.meter_water_usage else None,
                    'user_original_water_usage': float(record.user_original_water_usage) if record.user_original_water_usage else None,
                    'user_reduction_water': float(record.user_reduction_water) if record.user_reduction_water else None,
                    'user_billing_water_usage': float(record.user_billing_water_usage) if record.user_billing_water_usage else None,
                    'user_original_water_fee': float(record.user_original_water_fee) if record.user_original_water_fee else None,
                    'user_billing_water_fee': float(record.user_billing_water_fee) if record.user_billing_water_fee else None,
                },
                'total': {
                    'user_original_total_fee': float(record.user_original_total_fee) if record.user_original_total_fee else None,
                    'user_billing_total_fee': float(record.user_billing_total_fee) if record.user_billing_total_fee else None,
                    'user_proportional_reduction': float(record.user_proportional_reduction) if record.user_proportional_reduction else None,
                    'user_independent_reduction': float(record.user_independent_reduction) if record.user_independent_reduction else None,
                    'payable_fee': float(record.payable_fee) if record.payable_fee else None
                }
            })
        
        # 构建分页信息
        pagination = {
            'total': paginated_records.total,
            'pages': paginated_records.pages,
            'page': page,
            'per_page': per_page,
            'has_next': paginated_records.has_next,
            'has_prev': paginated_records.has_prev
        }
        # 记录查询成功日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='utility_api',
            action=f"查询退宿记录 [用户ID: {user_id}, 房间ID: {room_id}, 账期: {billing_period}]，查询到{len(records)}条记录",
            result=f"成功"
        )
        # 返回JSON格式响应
        return jsonify({
            'success': True,
            'message': f'查询到{len(records)}条退宿费用记录',
            'data': {
                'records': records,
                'pagination': pagination
            }
        })
        
    except Exception as e:
        logging.error(f"查询退宿费用记录失败: {str(e)}\n{traceback.format_exc()}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else None,
            module='utility',
            operation_type='utility_api',
            action=f"查询退宿记录失败 [用户ID: {user_id if 'user_id' in locals() else ''}, 房间ID: {room_id if 'room_id' in locals() else ''}, 账期: {billing_period if 'billing_period' in locals() else ''}]: {str(e)}",
            result="失败"
        )
        return jsonify({
            'success': False,
            'message': '查询退宿费用记录失败',
            'error': str(e)
        }), 500
