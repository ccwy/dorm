from flask import Blueprint, request, send_file, flash, redirect, url_for
from models.utility.utility_room_bill_record import RoomUtilityRecord
from models.utility.utility_room_bill_occupant import RoomUtilityOccupant
from models.dorm.dorm import Dorm
from models.user.user import User
from models.room.room import Room
from utils.db import db
from utils.log import log_operation
from datetime import datetime, timedelta
from collections import defaultdict
from decimal import Decimal
import io
import logging
from flask_login import login_required, current_user
from utils.auth import require_permission

# 创建导出蓝图
utility_room_bill_occupants_export_bp = Blueprint('utility_room_bill_occupants_export', __name__, url_prefix='/utility_room_bill_occupants_export')


def get_billing_period_dates(billing_period):
    """将账期字符串转换为具体日期时间范围（YYYY-MM -> 月初和月末，精确到秒）"""
    try:
        year, month = map(int, billing_period.split('-'))
        # 修正：返回datetime类型，包含时间信息
        start_date = datetime(year, month, 1, 0, 0, 0)  # 月初00:00:00
        # 计算月末日期时间
        if month == 12:
            next_month = 1
            next_year = year + 1
        else:
            next_month = month + 1
            next_year = year
        # 月末最后一秒
        end_date = datetime(next_year, next_month, 1, 0, 0, 0) - timedelta(seconds=1)
        return start_date, end_date
    except Exception as e:
        # 修复日志记录方式 - 使用logging并包含详细信息
        logging.error(f"解析账期失败: {billing_period}, 错误: {str(e)}")
        raise ValueError(f"无效的账期格式: {billing_period}，应为YYYY-MM")

def create_fee_export_data(billing_period):
    """创建导出数据，仅按账期筛选，按用户汇总导出"""
    # 构建查询条件 - 仅按账期筛选
    query = RoomUtilityRecord.query.filter(RoomUtilityRecord.billing_period == billing_period)
    
    # 预计算账期日期范围用于后续天数计算（datetime类型）
    start_date, end_date = get_billing_period_dates(billing_period)
    
    # 获取符合条件的主表记录
    main_records = query.all()
    export_data = []
    export_warnings = []
    
    for main in main_records:
        # 获取该记录的所有人员分摊记录
        occupant_records = RoomUtilityOccupant.get_by_record(main.record_id)
        
        # 获取房间信息
        room = Room.query.get(main.room_id)
        if not room:
            logging.error(f"找不到房间信息: room_id={main.room_id}")
            continue
        
        # 验证房间信息完整性
        if not room.building or not room.room_number:
            logging.error(f"房间信息不完整: room_id={main.room_id}, building={room.building}, room_number={room.room_number}")
            continue
        
        # 批量获取住宿记录 - 通过dorm_id精确匹配
        user_ids = [rec.user_id for rec in occupant_records]
        dorm_ids = [rec.dorm_id for rec in occupant_records if rec.dorm_id]
        dorm_by_id = {}
        if dorm_ids:
            dorm_records = Dorm.query.filter(Dorm.id.in_(dorm_ids)).all()
            dorm_by_id = {d.id: d for d in dorm_records}
        
        # 批量获取用户信息
        users = User.query.filter(User.id.in_(user_ids)).all()
        user_map = {user.id: user for user in users}
        
        # 过滤有效记录并按 (user_id) 分组
        user_groups = defaultdict(list)
        for occupant in occupant_records:
            # 通过dorm_id精确获取对应的dorm记录
            dorm = dorm_by_id.get(occupant.dorm_id) if occupant.dorm_id else None
            if not dorm:
                logging.error(
                    f"导出-分摊记录缺少dorm_id关联: occupant_id={occupant.id}, "
                    f"user_id={occupant.user_id}, room_id={occupant.room_id}, "
                    f"record_id={occupant.record_id}"
                )
                export_warnings.append(
                    f"分摊记录ID={occupant.id}（用户ID={occupant.user_id}，"
                    f"房间ID={occupant.room_id}）缺少dorm_id关联，请重新核算账单"
                )
                continue
            user_groups[occupant.user_id].append((occupant, dorm))
        
        # 按用户分组汇总输出
        for user_id, group_items in user_groups.items():
            user = user_map.get(user_id)
            user_name = user.name if user else f"未知用户（ID:{user_id}）"
            user_company = user.company or "" if user else ""
            user_department = user.department or "" if user else ""
            user_position = user.position or "" if user else ""
            
            if len(group_items) == 1:
                # 单条记录，直接输出
                occupant, dorm = group_items[0]
                check_in_date = dorm.check_in_date
                check_in_str = check_in_date.strftime('%Y-%m-%d') if check_in_date else ""
                
                export_data.append({
                    '账期': main.billing_period,
                    '房间ID': main.room_id,
                    '楼栋': room.building,
                    '房间号': room.room_number,
                    '本期电表当前读数': main.electric_current,
                    '本期电表上期读数': main.electric_previous,
                    '本期电表用量': main.electric_usage,
                    '减免电用量': main.electric_reduction,
                    '计费电用量': main.electric_billing_usage,
                    '电费单价': main.electric_price,
                    '本期电费': main.total_electric_fee,
                    '计费电费': main.billing_electric_fee,
                    '本期水表当前读数': main.water_current,
                    '本期水表上期读数': main.water_previous,
                    '本期水表用量': main.water_usage,
                    '减免水用量': main.water_reduction,
                    '计费水用量': main.water_billing_usage,
                    '水费单价': main.water_price,
                    '本期水费': main.total_water_fee,
                    '计费水费': main.billing_water_fee,
                    '本期总费用': main.total_fee,
                    '计费总费用': main.billing_total_fee,
                    '退宿人员费用': main.checked_out_total_fee,
                    '减免房间级费用': main.room_reduction_fee,
                    '房间应付费用': main.actual_total_fee,
                    '分摊人员ID': user_id,
                    '分摊人员姓名': user_name,
                    '公司': user_company,
                    '部门': user_department,
                    '职位': user_position,
                    '入住时间': check_in_str,
                    '账期内住宿天数': occupant.stay_days,
                    '分摊电费': occupant.electric_fee,
                    '分摊水费': occupant.water_fee,
                    '分摊总金额': occupant.total_fee,
                    '减免金额': occupant.user_reduction_fee,
                    '分摊应付金额': occupant.payable_fee,
                    '备注': ""
                })
            else:
                # 多条记录，汇总输出
                # 入住时间取最早
                check_in_dates = []
                for occupant, dorm in group_items:
                    if dorm.check_in_date:
                        check_in_dates.append(dorm.check_in_date)
                min_check_in = min(check_in_dates) if check_in_dates else None
                check_in_str = min_check_in.strftime('%Y-%m-%d') if min_check_in else ""
                
                # 汇总求和（使用Decimal避免浮点精度问题）
                stay_days_sum = sum(o.stay_days or 0 for o, d in group_items)
                electric_fee_sum = sum(Decimal(str(o.electric_fee or 0)) for o, d in group_items)
                water_fee_sum = sum(Decimal(str(o.water_fee or 0)) for o, d in group_items)
                total_fee_sum = sum(Decimal(str(o.total_fee or 0)) for o, d in group_items)
                user_reduction_fee_sum = sum(Decimal(str(o.user_reduction_fee or 0)) for o, d in group_items)
                payable_fee_sum = sum(Decimal(str(o.payable_fee or 0)) for o, d in group_items)
                
                # 构建备注：列出应付金额明细和合计
                payable_details = "+".join(str(Decimal(str(o.payable_fee or 0))) for o, d in group_items)
                
                remark = f"换宿合并: 应付[{payable_details}={payable_fee_sum}]"
                
                export_data.append({
                    '账期': main.billing_period,
                    '房间ID': main.room_id,
                    '楼栋': room.building,
                    '房间号': room.room_number,
                    '本期电表当前读数': main.electric_current,
                    '本期电表上期读数': main.electric_previous,
                    '本期电表用量': main.electric_usage,
                    '减免电用量': main.electric_reduction,
                    '计费电用量': main.electric_billing_usage,
                    '电费单价': main.electric_price,
                    '本期电费': main.total_electric_fee,
                    '计费电费': main.billing_electric_fee,
                    '本期水表当前读数': main.water_current,
                    '本期水表上期读数': main.water_previous,
                    '本期水表用量': main.water_usage,
                    '减免水用量': main.water_reduction,
                    '计费水用量': main.water_billing_usage,
                    '水费单价': main.water_price,
                    '本期水费': main.total_water_fee,
                    '计费水费': main.billing_water_fee,
                    '本期总费用': main.total_fee,
                    '计费总费用': main.billing_total_fee,
                    '退宿人员费用': main.checked_out_total_fee,
                    '减免房间级费用': main.room_reduction_fee,
                    '房间应付费用': main.actual_total_fee,
                    '分摊人员ID': user_id,
                    '分摊人员姓名': user_name,
                    '公司': user_company,
                    '部门': user_department,
                    '职位': user_position,
                    '入住时间': check_in_str,
                    '账期内住宿天数': stay_days_sum,
                    '分摊电费': float(electric_fee_sum),
                    '分摊水费': float(water_fee_sum),
                    '分摊总金额': float(total_fee_sum),
                    '减免金额': float(user_reduction_fee_sum),
                    '分摊应付金额': float(payable_fee_sum),
                    '备注': remark
                })
    
    return export_data, export_warnings


def create_user_summary_export_data(billing_period):
    """创建按用户汇总的导出数据，跨所有房间按user_id分组"""
    # 查询指定账期的所有 RoomUtilityRecord
    main_records = RoomUtilityRecord.query.filter(
        RoomUtilityRecord.billing_period == billing_period
    ).all()

    if not main_records:
        return []

    # 收集所有 occupant 记录，并建立 record_id -> main_record 映射
    record_map = {}
    all_occupants = []
    for main in main_records:
        record_map[main.record_id] = main
        occupants = RoomUtilityOccupant.get_by_record(main.record_id)
        all_occupants.extend(occupants)

    if not all_occupants:
        return []

    # 批量加载 User 信息
    user_ids = list(set(occ.user_id for occ in all_occupants))
    users = User.query.filter(User.id.in_(user_ids)).all()
    user_map = {user.id: user for user in users}

    # 批量加载 Dorm 信息
    dorm_ids = list(set(occ.dorm_id for occ in all_occupants if occ.dorm_id))
    dorm_by_id = {}
    if dorm_ids:
        dorm_records = Dorm.query.filter(Dorm.id.in_(dorm_ids)).all()
        dorm_by_id = {d.id: d for d in dorm_records}

    # 批量加载 Room 信息
    room_ids = list(set(main.room_id for main in main_records))
    rooms = Room.query.filter(Room.id.in_(room_ids)).all()
    room_map = {room.id: room for room in rooms}

    # 按 user_id 跨所有房间分组
    user_groups = defaultdict(list)
    for occ in all_occupants:
        user_groups[occ.user_id].append(occ)

    export_data = []

    for user_id, occupant_list in user_groups.items():
        user = user_map.get(user_id)
        user_name = user.name if user else f"未知用户（ID:{user_id}）"
        user_student_id = user.student_id if user else ""
        user_department = user.department or "" if user else ""
        user_position = user.position or "" if user else ""

        if len(occupant_list) == 1:
            # 单条记录：用户只在一个房间
            occ = occupant_list[0]
            main = record_map.get(occ.record_id)
            if not main:
                continue
            room = room_map.get(main.room_id)
            if not room:
                continue

            room_label = f"{room.building}-{room.room_number}"

            # 构建抄表记录
            meter_info = (
                f"电表: {main.electric_previous}→{main.electric_current}, "
                f"用量{main.electric_usage}; "
                f"水表: {main.water_previous}→{main.water_current}, "
                f"用量{main.water_usage}"
            )

            export_data.append({
                '账期': main.billing_period,
                '用户姓名': user_name,
                '工号': user_student_id,
                '部门': user_department,
                '职位': user_position,
                '房间号': room_label,
                '抄表记录': meter_info,
                '用户分摊水费': occ.water_fee,
                '用户分摊电费': occ.electric_fee,
                '用户分摊总金额': occ.total_fee,
                '备注': ""
            })
        else:
            # 多条记录：换宿用户，账期内在多个房间
            room_labels = []
            meter_parts = []
            total_water = Decimal('0')
            total_electric = Decimal('0')
            total_fee = Decimal('0')
            remark_details = []

            for occ in occupant_list:
                main = record_map.get(occ.record_id)
                if not main:
                    continue
                room = room_map.get(main.room_id)
                if not room:
                    continue

                room_label = f"{room.building}-{room.room_number}"
                room_labels.append(room_label)

                # 构建该房间的抄表信息
                room_meter = (
                    f"【{room_label}】电表: {main.electric_previous}→{main.electric_current}, "
                    f"用量{main.electric_usage}; "
                    f"水表: {main.water_previous}→{main.water_current}, "
                    f"用量{main.water_usage}"
                )
                meter_parts.append(room_meter)

                # 累计费用
                total_water += Decimal(str(occ.water_fee or 0))
                total_electric += Decimal(str(occ.electric_fee or 0))
                total_fee += Decimal(str(occ.total_fee or 0))

                # 备注明细
                occ_total = Decimal(str(occ.total_fee or 0))
                remark_details.append(f"{room_label}: 分摊总金额{occ_total:.2f}")

            # 房间号用逗号连接
            rooms_str = ", ".join(room_labels)
            # 抄表记录用分号连接
            meters_str = "; ".join(meter_parts)
            # 备注格式
            remark = f"换宿合并: {', '.join(remark_details)}"

            # 获取账期（所有记录的账期相同）
            billing_period_val = occupant_list[0].record_id and record_map.get(occupant_list[0].record_id)
            period_str = billing_period_val.billing_period if billing_period_val else billing_period

            export_data.append({
                '账期': period_str,
                '用户姓名': user_name,
                '工号': user_student_id,
                '部门': user_department,
                '职位': user_position,
                '房间号': rooms_str,
                '抄表记录': meters_str,
                '用户分摊水费': float(total_water),
                '用户分摊电费': float(total_electric),
                '用户分摊总金额': float(total_fee),
                '备注': remark
            })

    return export_data


@utility_room_bill_occupants_export_bp.route('/api/export_fee_data', methods=['GET'])
@login_required
@require_permission('utility.export')
def export_fee_data():
    """导出人员费用数据为Excel，支持按房间号合并所有相同内容字段并添加完整边框"""
    import pandas as pd  # 延迟导入，避免启动时加载重型库
    try:
        # 获取筛选参数
        billing_period = request.args.get('billing_period') or request.args.get('billingPeriod')
        
        # 验证账期参数
        if not billing_period:
            # 修复日志记录 - 使用log_operation函数记录操作结果
            log_operation(
                user_id=current_user.id,
                module="utility",
                operation_type="batch_import_export",
                action=f"导出费用数据失败 [原因: 未提供账期参数]",
                result="失败"
            )
            # 同时记录到logging
            logging.warning(f"用户 {current_user.id} 未提供账期参数尝试导出费用数据")
            flash('缺少必要参数', 'warning')
            return redirect(url_for('utility_index.utility_occupant_manage'))
        
        # 记录导出操作开始 - 与日志蓝图保持一致的记录方式
        log_operation(
            user_id=current_user.id,
            module="utility",
            operation_type="batch_import_export",
            action=f"开始导出费用数据 [账期: {billing_period}]",
            result="开始"
        )
        logging.info(f"用户 {current_user.id} 开始导出 {billing_period} 账期的费用数据")
        
        # 创建导出数据
        export_data, export_warnings = create_fee_export_data(billing_period)
        
        if not export_data:
            # 记录无数据情况
            log_operation(
                user_id=current_user.id,
                module="utility",
                operation_type="batch_import_export",
                action=f"导出费用数据失败 [账期: {billing_period}, 原因: 未找到匹配记录]",
                result="失败"
            )
            logging.info(f"用户 {current_user.id} 导出 {billing_period} 账期费用数据，未找到匹配记录")
            flash('没有可导出的数据', 'warning')
            return redirect(url_for('utility_index.utility_occupant_manage'))
        
        # 创建Excel
        df = pd.DataFrame(export_data)
        
        # 先按楼栋排序，再按房间号排序，确保不同楼栋的相同房间号不会被混淆
        df = df.sort_values(by=['楼栋', '房间号'])
        
        # 处理日期时间格式（保留时间信息）
        if '入住时间' in df.columns:
            # 转换为datetime类型保留完整信息
            df['入住时间'] = pd.to_datetime(df['入住时间'], format='%Y-%m-%d', errors='coerce').dt.date
        
        # 保存到内存
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='人员费用分摊')
            
            # 获取工作表对象
            worksheet = writer.sheets['人员费用分摊']
            
            # 定义样式
            from openpyxl.styles import Border, Side, Alignment
            thin_border = Border(
                left=Side(style='thin'),
                right=Side(style='thin'),
                top=Side(style='thin'),
                bottom=Side(style='thin')
            )
            # 所有单元格统一使用垂直居中，表头额外使用水平居中
            data_alignment = Alignment(vertical='center')
            header_alignment = Alignment(vertical='center', horizontal='center')
            
            # 需要合并的列名（房间相关的公共信息）
            columns_to_merge = [
                '账期', '房间ID', '楼栋', '房间号',
                '本期电表当前读数', '本期电表上期读数', '本期电表用量', '减免电用量', '计费电用量', '电费单价','本期电费', '计费电费',
                '本期水表当前读数', '本期水表上期读数', '本期水表用量', '减免水用量', '计费水用量', '水费单价','本期水费', '计费水费',
                '本期总费用', '计费总费用', '退宿人员费用', '减免房间级费用', '房间应付费用'
            ]
            
            # 存储列名到索引的映射（1-based）
            col_index_map = {}
            for col_idx, cell in enumerate(worksheet[1]):  # 表头行
                col_index_map[cell.value] = col_idx + 1  # openpyxl是1-based索引
                # 设置表头样式
                cell.alignment = header_alignment
                cell.border = thin_border
            
            # 获取所有数据行
            max_row = worksheet.max_row
            max_col = len(col_index_map)
            
            # 先为所有单元格应用基础样式（边框和垂直居中）
            for row in range(2, max_row + 1):
                for col in range(1, max_col + 1):
                    cell = worksheet.cell(row=row, column=col)
                    cell.alignment = data_alignment
                    cell.border = thin_border
            
            if max_row > 1:  # 确保有数据行
                # 获取楼栋和房间号列的索引
                building_col_idx = col_index_map.get('楼栋')
                room_col_idx = col_index_map.get('房间号')
                
                if building_col_idx and room_col_idx:
                    # 记录当前楼栋、房间号和起始行
                    current_building = worksheet.cell(row=2, column=building_col_idx).value
                    current_room = worksheet.cell(row=2, column=room_col_idx).value
                    start_row = 2
                    
                    # 遍历所有行，识别连续相同的楼栋和房间号组合
                    for row in range(3, max_row + 1):
                        building_value = worksheet.cell(row=row, column=building_col_idx).value
                        room_value = worksheet.cell(row=row, column=room_col_idx).value
                        
                        if building_value != current_building or room_value != current_room:
                            # 对所有需要合并的列执行合并操作
                            for col_name in columns_to_merge:
                                col_idx = col_index_map.get(col_name)
                                if col_idx and (row - start_row > 1):
                                    # 合并单元格
                                    worksheet.merge_cells(
                                        start_row=start_row, 
                                        start_column=col_idx,
                                        end_row=row - 1, 
                                        end_column=col_idx
                                    )
                                    # 合并后重新设置样式（合并会清除部分样式）
                                    merged_cell = worksheet.cell(row=start_row, column=col_idx)
                                    merged_cell.alignment = Alignment(vertical='center', horizontal='center')
                                    merged_cell.border = thin_border
                            
                            current_building = building_value
                            current_room = room_value
                            start_row = row
                    
                    # 处理最后一组相同楼栋和房间号的行
                    if max_row - start_row > 0:
                        for col_name in columns_to_merge:
                            col_idx = col_index_map.get(col_name)
                            if col_idx:
                                worksheet.merge_cells(
                                    start_row=start_row, 
                                    start_column=col_idx,
                                    end_row=max_row, 
                                    end_column=col_idx
                                )
                                # 合并后重新设置样式
                                merged_cell = worksheet.cell(row=start_row, column=col_idx)
                                merged_cell.alignment = Alignment(vertical='center', horizontal='center')
                                merged_cell.border = thin_border

            # 创建第二个sheet：按用户费用汇总
            user_summary_data = create_user_summary_export_data(billing_period)
            if user_summary_data:
                df_user = pd.DataFrame(user_summary_data)
                df_user = df_user.sort_values(by=['用户姓名'])
                df_user.to_excel(writer, index=False, sheet_name='按用户费用汇总')

                # 获取第二个工作表对象
                ws_user = writer.sheets['按用户费用汇总']

                # 设置表头样式
                for cell in ws_user[1]:
                    cell.alignment = header_alignment
                    cell.border = thin_border

                # 设置数据单元格样式
                max_row_user = ws_user.max_row
                max_col_user = ws_user.max_column
                for row in range(2, max_row_user + 1):
                    for col in range(1, max_col_user + 1):
                        cell = ws_user.cell(row=row, column=col)
                        cell.alignment = data_alignment
                        cell.border = thin_border
        
        output.seek(0)
        
        # 构建文件名
        filename = f"人员费用分摊数据_{billing_period}_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
        logging.info(f"用户 {current_user.id} 导出 {billing_period} 账期费用数据，文件名: {filename}")
        # 记录导出成功
        log_operation(
            user_id=current_user.id,
            module="utility",
            operation_type="batch_import_export",
            action=f"导出费用数据成功 [账期: {billing_period}, 记录数: {len(export_data)}]",
            result="成功"
        )
        logging.info(f"用户 {current_user.id} 成功导出 {billing_period} 账期费用数据，共 {len(export_data)} 条记录")
        
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename
        )
        
    except ValueError as ve:
        # 参数错误日志记录
        logging.warning(f"用户 {current_user.id} 导出费用数据参数错误: {str(ve)}")
        log_operation(
            user_id=current_user.id,
            module="utility",
            operation_type="batch_import_export",
            action=f"导出费用数据失败 [错误: {str(ve)}]",
            result="失败"
        )
        flash(str(ve), 'warning')
        return redirect(url_for('utility_index.utility_occupant_manage'))
    except Exception as e:
        # 异常错误日志记录
        logging.error(f"用户 {current_user.id} 导出费用数据失败: {str(e)}", exc_info=True)
        log_operation(
            user_id=current_user.id,
            module="utility",
            operation_type="batch_import_export",
            action=f"导出费用数据失败 [错误: {str(e)}]",
            result="失败"
        )
        flash(f'导出失败: {str(e)}', 'danger')
        return redirect(url_for('utility_index.utility_occupant_manage'))