import os
from flask import Blueprint, request, flash, redirect, url_for, send_file
import logging
from utils.db import db
from models.supply.stock_out import StockOut
from models.supply.stock_out_detail import StockOutDetail
from models.supply.supply_item import SupplyItem
from models.supply.storage_location import StorageLocation
from models.system_config.system_config import SystemConfig
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.log import log_operation
from utils.excel_utils import is_empty, export_to_excel, read_excel_rows
from utils.excel_date_utils import excel_date_utils
import io
from datetime import datetime
import traceback
from io import BytesIO

# 创建导入导出专用蓝图
stock_out_import_export_bp = Blueprint(
    'stock_out_import_export',
    __name__,
    url_prefix='/stock-out/import-export',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/stock-out/import-export/static'
)


# 下载出库单导入模板
@stock_out_import_export_bp.route('/template', methods=['GET'])
@login_required
@require_permission('supply.import')
def download_template():
    """生成并下载出库单数据导入模板"""
    try:
        logging.debug('开始生成出库单数据导入模板')

        # 从系统配置获取出库类型选项
        stock_out_types = SystemConfig.get_config_value('stock_out_types', '正常领用,其他出库')
        if isinstance(stock_out_types, str):
            stock_out_types = [t.strip() for t in stock_out_types.split(',') if t.strip()]
        stock_out_type_hint = '/'.join(stock_out_types) if stock_out_types else '正常领用/其他出库'

        # 模板数据生成
        headers = ["出库类型", "物品编号", "物品名称", "规格型号", "单位", "存放位置",
                   "数量", "单价", "出库日期", "领用人", "领用部门", "备注"]
        template_rows = [
            {"出库类型": "正常领用", "物品编号": "YP2026010001", "物品名称": "打印纸A4",
             "规格型号": "70g/500张", "单位": "包", "存放位置": "1号仓库-办公用品区",
             "数量": 5, "单价": 25.00, "出库日期": "2026-01-15", "领用人": "张三",
             "领用部门": "行政部", "备注": ""},
            {"出库类型": "正常领用", "物品编号": "YP2026010002", "物品名称": "签字笔(黑)",
             "规格型号": "0.5mm", "单位": "支", "存放位置": "1号仓库-办公用品区",
             "数量": 20, "单价": 3.50, "出库日期": "2026-01-15", "领用人": "张三",
             "领用部门": "行政部", "备注": ""},
            {"出库类型": "其他出库", "物品编号": "YP2026010003", "物品名称": "文件夹",
             "规格型号": "", "单位": "个", "存放位置": "2号仓库",
             "数量": 10, "单价": 5.00, "出库日期": "2026-01-16", "领用人": "李四",
             "领用部门": "技术部", "备注": "报废处理"},
        ]

        # 说明工作表
        desc_headers = ["字段名称", "是否必填", "说明"]
        desc_rows = [
            {"字段名称": "出库类型", "是否必填": "是", "说明": f"可选值：{stock_out_type_hint}"},
            {"字段名称": "物品编号", "是否必填": "是", "说明": "物品编号，必须在系统中已存在"},
            {"字段名称": "物品名称", "是否必填": "否", "说明": "物品名称，可留空（按物品编号匹配）"},
            {"字段名称": "规格型号", "是否必填": "否", "说明": "规格型号，可留空"},
            {"字段名称": "单位", "是否必填": "否", "说明": "计量单位（个/盒/箱/包等），可留空"},
            {"字段名称": "存放位置", "是否必填": "是", "说明": "存放位置名称，必须在系统中已存在"},
            {"字段名称": "数量", "是否必填": "是", "说明": "正整数"},
            {"字段名称": "单价", "是否必填": "否", "说明": "单价，可留空默认0"},
            {"字段名称": "出库日期", "是否必填": "是", "说明": "格式：YYYY-MM-DD"},
            {"字段名称": "领用人", "是否必填": "否", "说明": "领用人姓名，必须是系统中在职用户"},
            {"字段名称": "领用部门", "是否必填": "否", "说明": "领用部门名称，必须是系统中存在的部门"},
            {"字段名称": "备注", "是否必填": "否", "说明": "备注信息，可留空"},
        ]

        output = io.BytesIO()
        export_to_excel([
            {'name': '出库单导入', 'headers': headers, 'rows': template_rows},
            {'name': '填写说明', 'headers': desc_headers, 'rows': desc_rows},
        ], output)

        output.seek(0)
        filename = "出库单数据导入模板.xlsx"

        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='batch_import_export',
            action="下载出库单导入模板",
            result="成功"
        )
        logging.info(f'用户{current_user.id}下载出库单导入模板')

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'生成出库单导入模板失败: {str(e)}', exc_info=True)
        flash('生成模板失败，请联系管理员', 'danger')
        return redirect(url_for('stock_out.list_stock_outs'))


# 导出出库单列表
@stock_out_import_export_bp.route('/export', methods=['GET'])
@login_required
@require_permission('supply.export')
def export():
    """导出出库单数据为Excel（包含出库单汇总和出库明细两个工作表）"""
    try:
        logging.debug('开始执行出库单数据导出')

        # 查询所有出库单（含明细）
        stock_outs = StockOut.query.order_by(StockOut.stock_out_date.desc(), StockOut.id.desc()).all()
        logging.debug(f'查询到{len(stock_outs)}条出库单数据')

        if not stock_outs:
            logging.info('没有可导出的出库单数据')
            flash('没有可导出的出库单数据', 'info')
            return redirect(url_for('stock_out.list_stock_outs'))

        # 准备出库单汇总数据
        summary_data = []
        for so in stock_outs:
            try:
                summary_data.append({
                    '出库单号': so.stock_out_number or '',
                    '出库类型': so.stock_out_type or '',
                    '出库日期': so.stock_out_date.strftime('%Y-%m-%d') if so.stock_out_date else '',
                    '领用人': so.recipient_name or '',
                    '领用部门': so.department_name or '',
                    '经手人': so.handler_name or '',
                    '总金额': float(so.total_amount) if so.total_amount else 0,
                    '状态': so.status or '',
                    '备注': so.remark or '',
                    '创建时间': so.created_at.strftime('%Y-%m-%d %H:%M') if so.created_at else '',
                    '更新时间': so.updated_at.strftime('%Y-%m-%d %H:%M') if so.updated_at else '',
                })
            except Exception as e:
                logging.error(f'处理出库单ID={so.id}时出错: {str(e)}', exc_info=True)
                raise

        # 准备出库明细数据
        detail_data = []
        for so in stock_outs:
            for d in so.details:
                try:
                    detail_data.append({
                        '出库单号': so.stock_out_number or '',
                        '出库类型': so.stock_out_type or '',
                        '物品编号': d.display_item_number or '',
                        '物品名称': d.item_name or '',
                        '规格型号': d.specification or '',
                        '单位': d.unit or '',
                        '存放位置': d.display_location_name or '',
                        '数量': d.quantity if d.quantity else 0,
                        '单价': float(d.unit_price) if d.unit_price else 0,
                        '小计': float(d.total_price) if d.total_price else 0,
                    })
                except Exception as e:
                    logging.error(f'处理出库明细ID={d.id}时出错: {str(e)}', exc_info=True)
                    raise

        logging.debug(f'数据准备完成，汇总{len(summary_data)}条，明细{len(detail_data)}条')

        # 生成Excel（两个工作表）
        summary_headers = ['出库单号', '出库类型', '出库日期', '领用人', '领用部门', '经手人',
                           '总金额', '状态', '备注', '创建时间', '更新时间']
        detail_headers = ['出库单号', '出库类型', '物品编号', '物品名称', '规格型号', '单位',
                          '存放位置', '数量', '单价', '小计']
        output = io.BytesIO()
        export_to_excel([
            {'name': '出库单汇总', 'headers': summary_headers, 'rows': summary_data},
            {'name': '出库明细', 'headers': detail_headers, 'rows': detail_data},
        ], output)

        output.seek(0)
        filename = f"出库单数据导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        logging.debug(f'Excel文件生成成功，文件名: {filename}')

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='batch_import_export',
            action=f"导出出库单数据，共 {len(stock_outs)} 条记录",
            result="成功"
        )
        logging.info(f'用户{current_user.id}成功导出出库单数据')

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'导出出库单数据失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='batch_import_export',
            action=f"尝试导出出库单数据失败: {str(e)}",
            result="失败"
        )
        flash('导出失败，请联系管理员', 'danger')
        return redirect(url_for('stock_out.list_stock_outs'))


# 导入出库单数据
@stock_out_import_export_bp.route('/import', methods=['POST'])
@login_required
@require_permission('supply.import')
def import_stock_outs():
    """批量导入出库单数据"""
    # 前置条件：必须开启手动审核才能批量导入
    approval_enabled = SystemConfig.get_config_value('STOCK_OUT_APPROVAL_ENABLED', True)
    if not approval_enabled:
        flash('批量导入出库单需要开启手动审核功能，请在系统设置中开启出库审核后再进行导入操作', 'danger')
        return redirect(url_for('stock_out.list_stock_outs'))

    try:
        logging.debug('开始批量导入出库单数据')

        # 验证文件是否存在
        if 'file' not in request.files:
            flash('请选择要导入的文件', 'danger')
            logging.error('导出出库单数据失败：未选择文件')
            return redirect(url_for('stock_out.list_stock_outs'))

        file = request.files['file']
        if file.filename == '':
            flash('请选择要导入的文件', 'danger')
            logging.error('导入出库单数据失败：未选择文件')
            return redirect(url_for('stock_out.list_stock_outs'))

        # 文件类型验证
        allowed_extensions = {'xlsx', 'xls'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            flash(f'请上传Excel格式的文件（.xlsx 或 .xls），当前文件类型：.{file_ext}', 'danger')
            logging.error(f'导入出库单数据失败：文件类型无效，当前文件类型：.{file_ext}')
            return redirect(url_for('stock_out.list_stock_outs'))

        # 限制文件大小（10MB）
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > 10 * 1024 * 1024:
            flash('文件大小超过限制（最大10MB）', 'danger')
            logging.error('导入出库单数据失败：文件大小超过限制（最大10MB）')
            return redirect(url_for('stock_out.list_stock_outs'))

        try:
            file_content = file.read()
            file_bytes = BytesIO(file_content)
            file_bytes.seek(0)
            rows = read_excel_rows(file_bytes)
        except Exception as e:
            detailed_error = f"文件解析失败：{str(e)}"
            flash(detailed_error, 'danger')
            logging.error(f'导入出库单数据失败：文件解析失败 - {detailed_error}')
            return redirect(url_for('stock_out.list_stock_outs'))

        # 验证必要列
        required_columns = ['出库类型', '出库日期', '物品名称', '存放位置', '数量']
        excel_columns = list(rows[0].keys()) if rows else []
        missing_columns = [col for col in required_columns if col not in excel_columns]
        if missing_columns:
            flash(f'导入失败：文件缺少必要的列 - {", ".join(missing_columns)}', 'danger')
            logging.error(f'导入出库单数据失败：文件缺少必要的列 - {", ".join(missing_columns)}')
            return redirect(url_for('stock_out.list_stock_outs'))

        # 限制导入行数
        if len(rows) > 500:
            flash('单次导入数据不超过500条', 'danger')
            logging.error('导入出库单数据失败：单次导入数据超过500条')
            return redirect(url_for('stock_out.list_stock_outs'))

        # 从系统配置获取出库类型选项
        stock_out_types = SystemConfig.get_config_value('stock_out_types', '正常领用,其他出库')
        if isinstance(stock_out_types, str):
            stock_out_types = [t.strip() for t in stock_out_types.split(',') if t.strip()]

        # 准备导入数据列表
        success_count = 0
        fail_count = 0
        error_records = []

        # 按出库类型+出库日期+领用人+领用部门分组，同一组的明细归入同一张出库单
        from collections import OrderedDict
        grouped = OrderedDict()

        for index, row in enumerate(rows):
            row_num = index + 2

            try:
                # === 必填字段验证 ===
                # 出库类型
                stock_out_type_val = row.get('出库类型')
                if is_empty(stock_out_type_val):
                    error_records.append({'row': row_num, 'message': '出库类型不能为空'})
                    fail_count += 1
                    continue
                stock_out_type = str(stock_out_type_val).strip()
                if stock_out_types and stock_out_type not in stock_out_types:
                    error_records.append({'row': row_num, 'message': f'出库类型"{stock_out_type}"不在系统配置的可选值中（{"/".join(stock_out_types)}）'})
                    fail_count += 1
                    continue

                # 出库日期
                stock_out_date_val = row.get('出库日期')
                if is_empty(stock_out_date_val):
                    error_records.append({'row': row_num, 'message': '出库日期不能为空'})
                    fail_count += 1
                    continue
                stock_out_date_str = str(stock_out_date_val).strip()
                # 使用统一日期解析工具
                parsed = excel_date_utils.parse_excel_date([stock_out_date_val], field_name='出库日期', raise_error=False)
                stock_out_date = parsed[0].date() if parsed[0] else None
                if stock_out_date is None:
                    error_records.append({'row': row_num, 'message': f'出库日期格式不正确：{stock_out_date_str}，请使用YYYY-MM-DD格式'})
                    fail_count += 1
                    continue

                # 物品编号（必填）
                item_number_val = row.get('物品编号')
                if is_empty(item_number_val):
                    error_records.append({'row': row_num, 'message': '物品编号不能为空'})
                    fail_count += 1
                    continue
                item_number = str(item_number_val).strip()

                # 物品名称（可选）
                item_name_val = row.get('物品名称')
                item_name = str(item_name_val).strip() if not is_empty(item_name_val) else ''

                # 存放位置
                location_name_val = row.get('存放位置')
                if is_empty(location_name_val):
                    error_records.append({'row': row_num, 'message': '存放位置不能为空'})
                    fail_count += 1
                    continue
                location_name = str(location_name_val).strip()

                # 数量
                quantity_val = row.get('数量')
                if is_empty(quantity_val):
                    error_records.append({'row': row_num, 'message': '数量不能为空'})
                    fail_count += 1
                    continue
                try:
                    quantity = int(float(quantity_val))
                except (ValueError, TypeError):
                    error_records.append({'row': row_num, 'message': f'数量格式不正确：{quantity_val}'})
                    fail_count += 1
                    continue
                if quantity <= 0:
                    error_records.append({'row': row_num, 'message': '数量必须为正整数'})
                    fail_count += 1
                    continue

                # === 可选字段 ===
                # 领用人
                recipient_name_val = row.get('领用人')
                recipient_name = str(recipient_name_val).strip() if not is_empty(recipient_name_val) else ''

                # 领用部门
                department_name_val = row.get('领用部门')
                department_name = str(department_name_val).strip() if not is_empty(department_name_val) else ''

                # 规格型号
                specification_val = row.get('规格型号')
                specification = str(specification_val).strip() if not is_empty(specification_val) else ''

                # 单位
                unit_val = row.get('单位')
                unit = str(unit_val).strip() if not is_empty(unit_val) else ''

                # 单价
                unit_price_val = row.get('单价')
                if is_empty(unit_price_val):
                    unit_price = 0.0
                else:
                    try:
                        unit_price = float(unit_price_val)
                        if unit_price < 0:
                            unit_price = 0.0
                    except (ValueError, TypeError):
                        unit_price = 0.0

                # 备注
                remark_val = row.get('备注')
                detail_remark = str(remark_val).strip() if not is_empty(remark_val) else ''

                # 分组key：出库类型+出库日期+领用人+领用部门
                group_key = (stock_out_type, stock_out_date_str, recipient_name, department_name)
                if group_key not in grouped:
                    grouped[group_key] = {
                        'stock_out_type': stock_out_type,
                        'stock_out_date': stock_out_date,
                        'recipient_name': recipient_name,
                        'department_name': department_name,
                        'details': []
                    }
                grouped[group_key]['details'].append({
                    'row_num': row_num,
                    'item_name': item_name,
                    'item_number': item_number,
                    'specification': specification,
                    'unit': unit,
                    'location_name': location_name,
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'remark': detail_remark
                })

            except Exception as e:
                error_records.append({'row': row_num, 'message': f'行数据解析失败：{str(e)}'})
                fail_count += 1
                logging.error(f'导入出库单数据失败：第{row_num}行数据解析失败 - {str(e)}')
                continue

        # 按分组创建出库单
        for group_key, group_data in grouped.items():
            try:
                stock_out_type = group_data['stock_out_type']
                stock_out_date = group_data['stock_out_date']
                recipient_name = group_data['recipient_name']
                department_name = group_data['department_name']

                # 处理领用人：必须是系统中在职用户
                recipient_user_id = None
                if recipient_name:
                    from models.user.user import User
                    existing_user = User.query.filter(User.name == recipient_name, User.status == '在职').first()
                    if existing_user:
                        recipient_user_id = existing_user.id
                    # 未找到在职用户时，recipient_user_id 保持 None（与手动创建一致）

                # 处理领用部门：按名称查找系统部门
                department_id = None
                if department_name:
                    from models.department.department import Department
                    existing_dept = Department.query.filter(Department.name == department_name, Department.status == '正常').first()
                    if existing_dept:
                        department_id = existing_dept.id

                # 创建出库主表
                stock_out = StockOut.create(
                    stock_out_type=stock_out_type,
                    stock_out_date=stock_out_date,
                    recipient_user_id=recipient_user_id,
                    department_id=department_id,
                    handler_user_id=current_user.id,
                    remark=None,
                    operator_user_id=current_user.id
                )

                # 创建明细（出库单严格模式：物品和位置必须存在）
                for detail in group_data['details']:
                    item_name = detail['item_name']
                    item_number = detail['item_number']
                    specification = detail['specification']
                    unit = detail['unit']
                    location_name = detail['location_name']
                    quantity = detail['quantity']
                    unit_price = detail['unit_price']
                    detail_remark = detail['remark']

                    # 按物品编号查找（必填，唯一标识）
                    item_id = None
                    existing_by_number = SupplyItem.query.filter_by(item_number=item_number).first()
                    if existing_by_number:
                        item_id = existing_by_number.id
                        # 补全表单未提供的字段
                        if not item_name:
                            item_name = existing_by_number.name or ''
                        if not specification:
                            specification = existing_by_number.specification or ''
                        if not unit:
                            unit = existing_by_number.unit or ''
                    else:
                        # 物品编号不存在，跳过该明细
                        error_records.append({
                            'row': detail['row_num'],
                            'message': f'物品编号"{item_number}"在系统中不存在，请先在物品管理中添加'
                        })
                        fail_count += 1
                        continue

                    # 查找存放位置（严格模式：必须存在）
                    location_id = None
                    existing_location = StorageLocation.query.filter_by(name=location_name).first()
                    if existing_location:
                        location_id = existing_location.id
                        # 使用数据库中的干净name，避免Excel中传入display_name等脏数据
                        location_name = existing_location.name
                    else:
                        # 出库单严格模式：位置不存在则跳过该明细
                        error_records.append({
                            'row': detail['row_num'],
                            'message': f'存放位置"{location_name}"在系统中不存在，出库单不支持自动创建位置'
                        })
                        fail_count += 1
                        continue

                    StockOutDetail.create(
                        stock_out_id=stock_out.id,
                        item_id=item_id,
                        item_name=item_name,
                        location_id=location_id,
                        location_name=location_name,
                        quantity=quantity,
                        unit_price=unit_price,
                        specification=specification if specification else None,
                        unit=unit,
                        remark=detail_remark if detail_remark else None,
                        operator_user_id=current_user.id
                    )

                # 重新计算总金额
                StockOut.recalculate_total_amount(stock_out.id)

                success_count += len(group_data['details'])
                logging.info(f"导出出库单成功，出库单ID: {stock_out.id}, 单号: {stock_out.stock_out_number}")

            except Exception as e:
                # 记录该组所有行的错误
                for detail in group_data['details']:
                    error_records.append({'row': detail['row_num'], 'message': f'创建出库单失败：{str(e)}'})
                    fail_count += 1
                logging.error(f'导入出库单数据失败：创建出库单失败 - {str(e)}')
                continue

        db.session.commit()

        # 记录操作日志
        if success_count > 0:
            result_status = "部分成功" if fail_count > 0 else "成功"
        else:
            result_status = "失败"

        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='batch_import_export',
            action=f"导入出库单数据，成功{success_count}条明细，失败{fail_count}条",
            result=result_status
        )

        # 生成提示信息
        if result_status == "部分成功":
            message = f"导入部分成功：成功导入 {success_count} 条明细，失败 {fail_count} 条"
            if error_records:
                message += "<br>失败详情：<br>" + "<br>".join(
                    [f"第{err['row']}行：{err['message']}" for err in error_records[:5]]
                )
                if len(error_records) > 5:
                    message += f"<br>... 还有 {len(error_records)-5} 条错误"
        elif result_status == "成功":
            message = f"导入全部成功：共导入 {success_count} 条出库明细"
        else:
            message = f"导入全部失败：共{len(error_records)}条记录处理失败：<br>" + "<br>".join(
                [f"第{err['row']}行：{err['message']}" for err in error_records[:5]]
            )
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"

        logging.info(message)
        flash(message, 'success' if result_status == "成功" else 'warning' if result_status == "部分成功" else 'danger')
        return redirect(url_for('stock_out.list_stock_outs'))

    except Exception as e:
        db.session.rollback()
        detailed_error = f"导入过程出错：{str(e)}"
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='batch_import_export',
            action=f"出库单数据导入失败: {detailed_error}\n{traceback.format_exc()}",
            result="失败"
        )
        flash(detailed_error, 'danger')
        logging.error(f'导入出库单数据失败：{detailed_error}')
        return redirect(url_for('stock_out.list_stock_outs'))