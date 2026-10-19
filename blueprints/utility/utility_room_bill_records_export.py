from flask import Blueprint, request, send_file, flash, redirect, url_for
from flask_login import login_required, current_user
from utils.auth import require_permission
from models.utility.utility_room_bill_record import RoomUtilityRecord
from datetime import datetime
import io
import logging
from utils.lazy_imports import Workbook
from utils.excel_utils import write_sheet

utility_room_bill_records_export_bp = Blueprint('utility_room_bill_records_export', __name__, url_prefix='/utility_room_bill_records_export')

STATUS_MAP = {'pending': '待核算', 'processing': '核算中', 'calculated': '已核算', 'completed': '已完成'}

COLUMN_MAP = [
    ('index', '序号'),
    ('room_number', '房间号'),
    ('billing_period', '账期'),
    ('start_date', '开始日期'),
    ('end_date', '结束日期'),
    ('electric_previous', '电表上期读数'),
    ('electric_current', '电表本期读数'),
    ('electric_usage', '电表用量'),
    ('electric_reduction', '电费减免量'),
    ('electric_billing_usage', '电费计费用量'),
    ('electric_price', '电费单价'),
    ('total_electric_fee', '电费总额'),
    ('billing_electric_fee', '电费计费金额'),
    ('checked_out_electric_fee', '退宿已结算电费'),
    ('receivable_electric_fee', '应付电费'),
    ('water_previous', '水表上期读数'),
    ('water_current', '水表本期读数'),
    ('water_usage', '水表用量'),
    ('water_reduction', '水费减免量'),
    ('water_billing_usage', '水费计费用量'),
    ('water_price', '水费单价'),
    ('total_water_fee', '水费总额'),
    ('billing_water_fee', '水费计费金额'),
    ('checked_out_water_fee', '退宿已结算水费'),
    ('receivable_water_fee', '应付水费'),
    ('room_reduction_fee', '房间减免费'),
    ('total_fee', '费用总额'),
    ('billing_total_fee', '计费总额'),
    ('checked_out_total_fee', '退宿已结算总额'),
    ('receivable_total_fee', '应付总额'),
    ('actual_total_fee', '实际应付总额'),
    ('status', '状态'),
    ('remarks', '备注'),
]

NUMERIC_FIELDS = {
    'electric_previous', 'electric_current', 'electric_usage', 'electric_reduction',
    'electric_billing_usage', 'electric_price', 'total_electric_fee', 'billing_electric_fee',
    'checked_out_electric_fee', 'receivable_electric_fee',
    'water_previous', 'water_current', 'water_usage', 'water_reduction',
    'water_billing_usage', 'water_price', 'total_water_fee', 'billing_water_fee',
    'checked_out_water_fee', 'receivable_water_fee',
    'room_reduction_fee', 'total_fee', 'billing_total_fee',
    'checked_out_total_fee', 'receivable_total_fee', 'actual_total_fee',
}

DATE_FIELDS = {'start_date', 'end_date'}


@utility_room_bill_records_export_bp.route('/api/export', methods=['GET'])
@login_required
@require_permission('utility.export')
def export():
    try:
        billing_period = request.args.get('billing_period')
        if not billing_period:
            logging.warning(f"用户 {current_user.id} 未提供账期参数尝试导出费用主表数据")
            flash('请指定账期', 'warning')
            return redirect(url_for('utility_index.utility_room_records_bill', billing_period=billing_period))

        records = RoomUtilityRecord.query.filter_by(billing_period=billing_period).order_by(RoomUtilityRecord.room_id).all()
        if not records:
            logging.info(f"用户 {current_user.id} 导出 {billing_period} 账期费用主表数据，未找到匹配记录")
            flash(f'账期 {billing_period} 没有费用记录', 'warning')
            return redirect(url_for('utility_index.utility_room_records_bill', billing_period=billing_period))

        logging.info(f"用户 {current_user.id} 开始导出 {billing_period} 账期费用主表数据，共 {len(records)} 条记录")

        rows = []
        for idx, record in enumerate(records, start=1):
            row = {}
            for field, _ in COLUMN_MAP:
                if field == 'index':
                    row[field] = idx
                elif field == 'room_number':
                    row[field] = record.room.room_number if record.room else ''
                elif field == 'status':
                    row[field] = STATUS_MAP.get(getattr(record, field), '')
                elif field in DATE_FIELDS:
                    val = getattr(record, field)
                    row[field] = val.strftime('%Y-%m-%d') if val else ''
                elif field in NUMERIC_FIELDS:
                    val = getattr(record, field)
                    row[field] = float(val) if val is not None else ''
                else:
                    row[field] = getattr(record, field, '')
            rows.append(row)

        headers = [ch for _, ch in COLUMN_MAP]
        # 按列顺序构建数据行
        data_rows = [[row.get(f) for f, _ in COLUMN_MAP] for row in rows]

        output = io.BytesIO()
        wb = Workbook()
        wb.remove(wb.active)  # 移除默认空工作表
        write_sheet(wb, '费用主表', headers, data_rows)
        wb.save(output)
        wb.close()
        output.seek(0)

        filename = f'费用主表_{billing_period}_{datetime.now()}.xlsx'
        logging.info(f"用户 {current_user.id} 成功导出 {billing_period} 账期费用主表数据，共 {len(records)} 条记录，文件名: {filename}")

        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name=filename)
    except Exception as e:
        logging.error(f"用户 {current_user.id} 导出费用主表数据失败: {str(e)}", exc_info=True)
        flash(f'导出失败: {str(e)}', 'danger')
        return redirect(url_for('utility_index.utility_room_records_bill', billing_period=billing_period))