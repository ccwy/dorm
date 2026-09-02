from flask import request, jsonify, make_response
from utils.db import db
from models.user import User
from models.department import Department
from models.room import Room
from models.utility_room_bill_record import RoomUtilityRecord
from models.utility_room_bill_checkout import CheckoutUtilityRecord
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
import traceback
from datetime import datetime
import logging
from .utility_room_bill_checkout import utility_room_bill_checkout_bp  # 导入退宿费用子表主蓝图
from io import BytesIO
from urllib.parse import quote
    
@utility_room_bill_checkout_bp.route('/export', methods=['POST'])
@login_required
@require_permission('utility.export')
def export_checkout_records():
    """
    导出退宿人员费用记录为Excel文件
    支持按账期、部门等条件筛选后导出
    """
    import pandas as pd
    try:
        # 获取查询参数
        data = request.get_json() or {}
        
        # 提取查询条件
        billing_period = str(data.get('billing_period', '')).strip()
        department = str(data.get('department', '')).strip()
        search_text = str(data.get('search_text', '')).strip().lower()
        
        # 构建查询
        query = CheckoutUtilityRecord.query.join(
            RoomUtilityRecord, 
            CheckoutUtilityRecord.record_id == RoomUtilityRecord.record_id
        ).join(
            User, 
            CheckoutUtilityRecord.user_id == User.id
        ).outerjoin(
            Department, User.department_id == Department.id
        ).join(
            Room, 
            RoomUtilityRecord.room_id == Room.id
        )
        
        # 应用查询条件
        if billing_period:
            query = query.filter(RoomUtilityRecord.billing_period == billing_period)
        
        if department:
            query = query.filter(Department.name == department)
        
        if search_text:
            # 按姓名或房间号搜索
            query = query.filter(
                db.or_(
                    User.name.ilike(f'%{search_text}%'),
                    Room.full_room.ilike(f'%{search_text}%')
                )
            )
        
        # 获取所有符合条件的记录
        records = query.order_by(
            RoomUtilityRecord.billing_period.desc(),
            CheckoutUtilityRecord.checkout_date.desc()
        ).all()
        
        if not records:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='batch_import_export',
                action=f"导出退宿费用记录 [账期: {billing_period}, 部门: {department}]，没有找到符合条件的退宿记录",
                result="失败"
            )
            return jsonify({
                'success': False,
                'message': '没有找到符合条件的退宿记录'
            }), 404
        
        # 准备导出数据
        export_data = []
        for record in records:
            main_record = RoomUtilityRecord.query.get(record.record_id)
            room = Room.query.get(main_record.room_id) if main_record else None
            user = User.query.get(record.user_id) if record.user_id else None
            
            # 构建导出行数据
            export_data.append({
                '账期': main_record.billing_period if main_record else '',
                '房间ID': room.id if room else '',
                '楼栋': room.building if room else '',
                '房间号': room.room_number if room else '',
                '姓名': user.name if user else '',
                '公司': user.company or '' if user else '',
                '部门': user.department if user else '',
                '入住日期': record.checkin_date.strftime('%Y-%m-%d %H:%M:%S') if record.checkin_date else '',
                '退宿日期': record.checkout_date.strftime('%Y-%m-%d %H:%M:%S') if record.checkout_date else '',
                '当期已住天数': record.user_period_days if record.user_period_days else 0,
                '总住宿天数': record.total_period_days if record.total_period_days else 0,
                '电表上次读数': float(record.electric_previous) if record.electric_previous else 0,
                '电表退宿读数': float(record.electric_reading) if record.electric_reading else 0,
                '电抄表用量': float(record.meter_electric_usage) if record.meter_electric_usage else 0,
                '原始电用量(kWh)': float(record.user_original_electric_usage) if record.user_original_electric_usage else 0,
                '减免电用量(kWh)': float(record.user_reduction_electric) if record.user_reduction_electric else 0,
                '计费电用量(kWh)': float(record.user_billing_electric_usage) if record.user_billing_electric_usage else 0,
                '电费单价(元/kWh)': float(record.electric_price) if record.electric_price else 0,
                '房间总电费(元)': float(record.meter_electric_fee) if record.meter_electric_fee else 0,
                '个人原始电费(元)': float(record.user_original_electric_fee) if record.user_original_electric_fee else 0,
                '个人计费电费(元)': float(record.user_billing_electric_fee) if record.user_billing_electric_fee else 0,
                '水表上次读数': float(record.water_previous) if record.water_previous else 0,
                '水表退宿读数': float(record.water_reading) if record.water_reading else 0,
                '水抄表用量': float(record.meter_water_usage) if record.meter_water_usage else 0,
                '原始水用量(m³)': float(record.user_original_water_usage) if record.user_original_water_usage else 0,
                '减免水用量(m³)': float(record.user_reduction_water) if record.user_reduction_water else 0,
                '计费水用量(m³)': float(record.user_billing_water_usage) if record.user_billing_water_usage else 0,
                '水费单价(元/m³)': float(record.water_price) if record.water_price else 0,
                '房间总水费(元)': float(record.meter_water_fee) if record.meter_water_fee else 0,
                '个人原始水费(元)': float(record.user_original_water_fee) if record.user_original_water_fee else 0,
                '个人计费水费(元)': float(record.user_billing_water_fee) if record.user_billing_water_fee else 0,
                '房间总费用(元)': float(record.meter_total_fee) if record.meter_total_fee else 0,
                '个人原始总费用(元)': float(record.user_original_total_fee) if record.user_original_total_fee else 0,
                '个人计费总费用(元)': float(record.user_billing_total_fee) if record.user_billing_total_fee else 0,
                '按比例分摊减免(元)': float(record.user_proportional_reduction) if record.user_proportional_reduction else 0,
                '个人独立减免(元)': float(record.user_independent_reduction) if record.user_independent_reduction else 0,
                '个人应付费用(元)': float(record.payable_fee) if record.payable_fee else 0,
                '退宿状态': record.checkout_status if record.checkout_status else '',
                '支付状态': record.payment_status if record.payment_status else ''
            })
        
        # 创建DataFrame
        df = pd.DataFrame(export_data)
        
        # 设置数值格式化
        float_columns = [
            '电表上次读数', '电表退宿读数', '电抄表用量', '原始电用量(kWh)', '减免电用量(kWh)',
            '计费电用量(kWh)', '电费单价(元/kWh)', '房间总电费(元)',
            '个人原始电费(元)', '个人计费电费(元)', '水表上次读数',
            '水表退宿读数', '水抄表用量', '原始水用量(m³)', '减免水用量(m³)',
            '计费水用量(m³)', '水费单价(元/m³)', '房间总水费(元)',
            '个人原始水费(元)', '个人计费水费(元)', '房间总费用(元)',
            '个人原始总费用(元)', '个人计费总费用(元)', 
            '按比例分摊减免(元)', '个人独立减免(元)', '个人应付费用(元)'
        ]
        for col in float_columns:
            df[col] = df[col].apply(lambda x: f"{x:.2f}")
        
        # 创建Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # 设置工作表名称
            sheet_name = f"退宿费用记录_{billing_period or '全部'}"
            # 写入数据
            df.to_excel(writer, index=False, sheet_name=sheet_name)
            
            # 获取工作表对象
            worksheet = writer.sheets[sheet_name]
            
            # 调整列宽
            for column_cells in worksheet.columns:
                length = max(len(str(cell.value)) for cell in column_cells) + 2
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(length, 30)  # 最大宽度限制
        
        # 准备响应
        output.seek(0)
        response = make_response(output.getvalue())
        
        # 设置文件名和响应头
        filename = f"退宿人员费用记录_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        # 对中文文件名进行URL编码
        encoded_filename = quote(filename, encoding='utf-8')
        # 使用UTF-8编码声明文件名
        response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
        response.headers["Content-type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module="utility",
            operation_type="batch_import_export",
            action=f"导出退宿费用记录成功，[账期: {billing_period},导出{len(records)}条记录至Excel",
            result="成功"
        )
        
        return response
        
    except Exception as e:
        logging.error(f"导出退宿费用记录失败: {str(e)}\n{traceback.format_exc()}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else None,
            module="utility",
            operation_type="batch_import_export",
            action=f"导出退宿费用记录失败 [账期: {billing_period if 'billing_period' in locals() else ''}, 部门: {department if 'department' in locals() else ''}]失败: {str(e)}",
            result="失败"
        )
        return jsonify({
            'success': False,
            'message': '导出退宿费用记录失败',
            'error': str(e)
        }), 500
