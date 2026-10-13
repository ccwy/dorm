import io
import logging
import traceback
from datetime import datetime
from flask import Blueprint, request, flash, redirect, url_for, send_file
from flask_login import login_required, current_user
from utils.db import db
from utils.auth import require_permission
from utils.log import log_operation
from utils.lazy_imports import pd
from utils.excel_date_utils import excel_date_utils
from models.room.room import Room
from models.room.room_item import RoomItem
from models.room.room_item_record import RoomItemRecord

# 创建房间物品导入导出专用蓝图
room_item_import_export_bp = Blueprint(
    'room_item_io',
    __name__,
    url_prefix='/room/item/io'
)


# 导出物品数据
@room_item_import_export_bp.route('/export', methods=['GET'])
@login_required
@require_permission('room_item.view')
def export_items():
    """导出房间物品数据"""
    try:
        logging.info('开始执行房间物品数据导出')

        # 查询所有物品，按房间排序
        items = RoomItem.query.order_by(RoomItem.room_id).all()
        logging.info(f'查询到{len(items)}条物品数据')

        if not items:
            flash('没有可导出的物品数据', 'info')
            return redirect(url_for('room_item.manage'))

        # 准备导出数据
        data = []
        for item in items:
            room = Room.query.get(item.room_id)
            item_type_display = RoomItem.ITEM_TYPE_MAP.get(item.item_type, item.item_type)
            data.append({
                '物品ID': item.id,
                '楼栋': room.building if room else '',
                '房间号': room.room_number if room else '',
                '物品名称': item.name,
                '物品编号': item.item_code or '',
                '物品规格': item.specification or '',
                '物品单位': item.unit or '',
                '物品类型': item_type_display,
                '总数量': item.total_quantity,
                '可用数量': item.available_quantity,
                '损坏数量': item.damaged_quantity,
                '丢失数量': item.lost_quantity,
                '报废数量': item.scrapped_quantity,
                '状态': item.status,
                '备注': item.remark or '',
                '创建时间': item.created_at.strftime('%Y-%m-%d %H:%M:%S') if item.created_at else '',
                '更新时间': item.updated_at.strftime('%Y-%m-%d %H:%M:%S') if item.updated_at else ''
            })

        # 生成Excel（单sheet）
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='物品数据')

        output.seek(0)
        filename = f"房间物品数据_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='room_item',
            operation_type='batch_import_export',
            action=f"导出房间物品数据，共 {len(items)} 条记录",
            result="成功"
        )
        logging.info(f'用户{current_user.id}成功导出房间物品数据，共{len(items)}条')

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'导出房间物品数据失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='room_item',
            operation_type='batch_import_export',
            action=f"尝试导出房间物品数据失败: {str(e)}",
            result="失败"
        )
        flash('导出失败，请联系管理员', 'danger')
        return redirect(url_for('room_item.manage'))


# 导入物品数据
@room_item_import_export_bp.route('/import', methods=['POST'])
@login_required
@require_permission('room_item.create')
def import_items():
    """批量导入房间物品数据"""
    try:
        logging.info('开始批量导入房间物品数据')

        # 验证文件
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('请选择要导入的文件', 'danger')
            logging.error('导入物品数据失败：未选择文件')
            return redirect(url_for('room_item.manage'))

        # 文件类型验证
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in ('xlsx', 'xls'):
            flash(f'请上传Excel格式的文件（.xlsx 或 .xls），当前文件类型：.{file_ext}', 'danger')
            logging.error(f'导入物品数据失败：文件类型无效，当前文件类型：.{file_ext}')
            return redirect(url_for('room_item.manage'))

        # 读取Excel（优先读取'物品数据'sheet，不存在则取第一个sheet）
        try:
            file_bytes = io.BytesIO(file.read())
            xl = pd.ExcelFile(file_bytes)
            if '物品数据' in xl.sheet_names:
                df = pd.read_excel(xl, sheet_name='物品数据')
            else:
                df = pd.read_excel(xl, sheet_name=0)
        except Exception as e:
            flash(f'文件解析失败：{str(e)}', 'danger')
            logging.error(f'导入物品数据失败：文件解析失败 - {str(e)}')
            return redirect(url_for('room_item.manage'))

        if df.empty:
            flash('导入的文件没有数据', 'danger')
            logging.error('导入物品数据失败：文件没有数据')
            return redirect(url_for('room_item.manage'))

        # 构建楼栋+房间号到房间ID的映射
        all_rooms_map = {}
        for r in Room.query.all():
            key = f"{r.building}_{r.room_number}"
            all_rooms_map[key] = r.id

        # 物品类型反向映射（中文->英文）
        item_type_reverse = {v: k for k, v in RoomItem.ITEM_TYPE_MAP.items()}
        # 有效状态列表
        valid_statuses = list(RoomItem.STATUS_MAP.keys())

        success_count = 0
        error_records = []

        # 规范化Excel单元格值：浮点整数（如1.0、101.0）转为整数字符串（"1"、"101"），否则保留原字符串（如"1栋"、"A101"）
        def normalize_cell_str(val):
            s = str(val).strip()
            try:
                f = float(s)
                if f.is_integer():
                    return str(int(f))
            except ValueError:
                pass
            return s

        for idx, row in df.iterrows():
            row_num = idx + 2
            try:
                # 读取楼栋（必填）
                building_val = row.get('楼栋')
                if pd.isna(building_val) or not str(building_val).strip():
                    error_records.append(f"第{row_num}行：楼栋不能为空")
                    continue
                building = normalize_cell_str(building_val)

                # 读取房间号（必填，统一转换为字符串）
                room_number_val = row.get('房间号')
                if pd.isna(room_number_val) or not str(room_number_val).strip():
                    error_records.append(f"第{row_num}行：房间号不能为空")
                    continue
                room_number = normalize_cell_str(room_number_val)

                # 通过楼栋+房间号定位房间
                room_key = f"{building}_{room_number}"
                room_id = all_rooms_map.get(room_key)
                if not room_id:
                    error_records.append(f"第{row_num}行：未找到房间 {building}{room_number}")
                    continue

                # 读取物品名称（必填）
                name_val = row.get('物品名称')
                if pd.isna(name_val) or not str(name_val).strip():
                    error_records.append(f"第{row_num}行：物品名称不能为空")
                    continue
                name = str(name_val).strip()

                # 读取物品规格（可选）
                spec_val = row.get('物品规格')
                specification = str(spec_val).strip() if pd.notna(spec_val) and str(spec_val).strip() else None

                # 读取物品单位（可选）
                unit_val = row.get('物品单位')
                unit = str(unit_val).strip() if pd.notna(unit_val) and str(unit_val).strip() else None

                # 读取物品类型（可选，默认room_bound）
                type_val = row.get('物品类型')
                if pd.isna(type_val) or not str(type_val).strip():
                    item_type = 'room_bound'
                else:
                    type_str = str(type_val).strip()
                    item_type = item_type_reverse.get(type_str, type_str if type_str in ('room_bound', 'transferable') else 'room_bound')

                # 读取总数量（必填正整数，默认1）
                qty_val = row.get('总数量')
                if pd.isna(qty_val) or str(qty_val).strip() == '':
                    total_quantity = 1
                else:
                    try:
                        total_quantity = int(float(str(qty_val)))
                        if total_quantity < 1:
                            error_records.append(f"第{row_num}行：总数量必须为正整数，当前值{total_quantity}")
                            continue
                    except ValueError:
                        error_records.append(f"第{row_num}行：总数量必须为整数")
                        continue

                # 读取状态（可选，默认正常）
                status_val = row.get('状态')
                if pd.isna(status_val) or not str(status_val).strip():
                    status = '正常'
                else:
                    status = str(status_val).strip()
                    if status not in valid_statuses:
                        error_records.append(f"第{row_num}行：状态 '{status}' 无效，有效值为：{', '.join(valid_statuses)}")
                        continue

                # 读取备注（可选）
                remark_val = row.get('备注')
                remark = str(remark_val).strip() if pd.notna(remark_val) and str(remark_val).strip() else None

                # 读取添加时间（可选，用excel_date_utils解析）
                created_at_val = row.get('添加时间')
                created_at = None
                if pd.notna(created_at_val) and str(created_at_val).strip():
                    try:
                        parsed_dates = excel_date_utils.parse_excel_date(
                            [created_at_val], field_name='添加时间', raise_error=False
                        )
                        created_at = parsed_dates[0] if parsed_dates else None
                    except Exception as e:
                        error_records.append(f"第{row_num}行：添加时间格式无效 - {str(e)}")
                        continue

                # 判定同一种物品：名称+规格+单位+类型均相同才合并，否则新增
                existing_item = RoomItem.query.filter_by(room_id=room_id, name=name, item_type=item_type, specification=specification, unit=unit).first()

                if existing_item:
                    # 合并：增加总数量和可用数量（增量）
                    before_avail = existing_item.available_quantity
                    existing_item.total_quantity += total_quantity
                    existing_item.available_quantity += total_quantity
                    db.session.flush()
                    if created_at and (not existing_item.created_at or created_at < existing_item.created_at):
                        existing_item.created_at = created_at
                    # 添加操作记录
                    RoomItemRecord.add_record(
                        item_id=existing_item.id,
                        operation_type='import',
                        quantity=total_quantity,
                        before_quantity=before_avail,
                        after_quantity=existing_item.available_quantity,
                        operator_id=current_user.id,
                        remarks='批量导入合并数量'
                    )
                else:
                    # 创建新物品
                    item_obj = RoomItem.create_item(
                        room_id=room_id,
                        name=name,
                        item_type=item_type,
                        total_quantity=total_quantity,
                        specification=specification,
                        unit=unit,
                        remark=remark
                    )
                    db.session.flush()
                    if created_at:
                        item_obj.created_at = created_at
                    # 设置状态（create_item默认为正常）
                    if status != '正常':
                        item_obj.status = status
                    # 添加操作记录
                    RoomItemRecord.add_record(
                        item_id=item_obj.id,
                        operation_type='import',
                        quantity=total_quantity,
                        before_quantity=0,
                        after_quantity=item_obj.available_quantity,
                        operator_id=current_user.id,
                        remarks='批量导入新增物品'
                    )

                success_count += 1

            except Exception as e:
                error_records.append(f"第{row_num}行：处理失败 - {str(e)}")
                logging.error(f'导入物品数据失败：第{row_num}行 - {str(e)}')
                continue

        # 提交事务
        db.session.commit()

        # 生成汇总信息
        if error_records:
            message = f"导入完成：成功 {success_count} 条，失败 {len(error_records)} 条<br>"
            message += "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records) - 5} 条错误"
            flash(message, 'warning' if success_count > 0 else 'danger')
        else:
            flash(f"导入成功：共导入 {success_count} 条物品数据", 'success')

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='room_item',
            operation_type='batch_import_export',
            action=f"导入房间物品数据，成功{success_count}条，失败{len(error_records)}条",
            result="成功" if not error_records else ("部分成功" if success_count > 0 else "失败")
        )
        logging.info(f'物品数据导入完成，成功{success_count}条，失败{len(error_records)}条')

        return redirect(url_for('room_item.manage'))

    except Exception as e:
        db.session.rollback()
        logging.error(f'导入房间物品数据失败: {str(e)}\n{traceback.format_exc()}')
        log_operation(
            user_id=current_user.id,
            module='room_item',
            operation_type='batch_import_export',
            action=f"导入房间物品数据失败: {str(e)}",
            result="失败"
        )
        flash(f'导入过程出错：{str(e)}', 'danger')
        return redirect(url_for('room_item.manage'))


# 下载导入模板
@room_item_import_export_bp.route('/download_template', methods=['GET'])
@login_required
@require_permission('room_item.view')
def download_template():
    """生成并下载房间物品导入模板"""
    try:
        logging.info('开始生成房间物品导入模板')

        # 模板数据（第二、三行为示例数据）
        template_data = {
            '楼栋': ['A栋', 'B栋'],
            '房间号': ['101', '202'],
            '物品名称': ['床铺', '椅子'],
            '物品类型': ['房间绑定', '可转移'],
            '总数量': [4, 2],
            '状态': ['正常', ''],
            '添加时间': [datetime.now().strftime('%Y-%m-%d %H:%M:%S'), ''],
            '备注': ['', '']
        }

        # 创建模板DataFrame
        df = pd.DataFrame(template_data)

        # 说明行（作为df第一行）
        instructions = [
            '*必填项（需与系统中楼栋名称一致）',
            '*必填项（需与系统中房间号一致）',
            '*必填项',
            '可选值: 房间绑定, 可转移（默认房间绑定）',
            '*必填项，正整数',
            '可选值: 正常, 损坏, 丢失, 报废（默认正常）',
            '日期时间（可留空，格式示例：YYYY-MM-DD HH:MM:SS）',
            '文本（可留空）'
        ]
        df.loc[-1] = instructions
        df.index = df.index + 1
        df = df.sort_index()

        # 生成Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='物品数据导入模板')
            worksheet = writer.sheets['物品数据导入模板']
            # 设置列宽
            column_widths = [14, 10, 16, 16, 10, 12, 20, 20]
            for i, width in enumerate(column_widths, 1):
                worksheet.column_dimensions[chr(64 + i)].width = width
            # 必填项说明标红（说明行位于第2行）
            for cell in worksheet[2]:
                if "*必填项" in str(cell.value):
                    cell.font = cell.font.copy(color="FF0000")

        output.seek(0)
        filename = f"房间物品导入模板_{datetime.now().strftime('%Y%m%d')}.xlsx"

        log_operation(
            user_id=current_user.id,
            module='room_item',
            operation_type='batch_import_export',
            action="下载房间物品导入模板",
            result="成功"
        )
        logging.info(f'用户{current_user.id}下载房间物品导入模板')

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'生成房间物品导入模板失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='room_item',
            operation_type='batch_import_export',
            action=f"下载房间物品导入模板失败: {str(e)}",
            result="失败"
        )
        flash('模板下载失败，请联系管理员', 'danger')
        return redirect(url_for('room_item.manage'))