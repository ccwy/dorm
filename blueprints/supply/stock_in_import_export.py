import os
from flask import Blueprint, request, flash, redirect, url_for, send_file
import logging
from utils.db import db
from models.supply.stock_in import StockIn
from models.supply.stock_in_detail import StockInDetail
from models.supply.supplier import Supplier
from models.supply.supply_item import SupplyItem
from models.supply.storage_location import StorageLocation
from models.system_config.system_config import SystemConfig
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.log import log_operation
from utils.lazy_imports import pd  # 延迟导入pandas，避免启动时加载重型库
import io
from datetime import datetime
import traceback
from io import BytesIO

# 创建导入导出专用蓝图
stock_in_import_export_bp = Blueprint(
    'stock_in_import_export',
    __name__,
    url_prefix='/stock-in/import-export',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/stock-in/import-export/static'
)


# 下载入库单导入模板
@stock_in_import_export_bp.route('/template', methods=['GET'])
@login_required
@require_permission('supply.import')
def download_template():
    """生成并下载入库单数据导入模板"""
    try:
        logging.debug('开始生成入库单数据导入模板')

        # 从系统配置获取入库类型选项
        stock_in_types = SystemConfig.get_config_value('stock_in_types', '采购入库,其它入库')
        if isinstance(stock_in_types, str):
            stock_in_types = [t.strip() for t in stock_in_types.split(',') if t.strip()]
        stock_in_type_hint = '/'.join(stock_in_types) if stock_in_types else '采购入库/其它入库'

        # 模板数据生成
        template_data = {
            "入库类型": ["采购入库", "采购入库", "其它入库"],
            "入库日期": ["2026-01-15", "2026-01-15", "2026-01-16"],
            "供应商名称": ["示例供应商A", "示例供应商A", ""],
            "物品编号": ["YP2026010001", "YP2026010002", "YP2026010003"],
            "物品名称": ["打印纸A4", "签字笔(黑)", "文件夹"],
            "规格型号": ["70g/500张", "0.5mm", ""],
            "单位": ["包", "支", "个"],
            "存放位置": ["1号仓库-办公用品区", "1号仓库-办公用品区", "2号仓库"],
            "数量": [10, 50, 20],
            "单价": [25.00, 3.50, 5.00],
            "备注": ["", "", "捐赠物资"],
        }

        df = pd.DataFrame(template_data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='入库单导入')

            # 添加说明工作表
            desc_data = {
                "字段名称": ["入库类型", "入库日期", "供应商名称", "物品编号", "物品名称",
                            "规格型号", "单位", "存放位置", "数量", "单价", "备注"],
                "是否必填": ["是", "是", "否", "是", "否", "否", "否", "是", "是", "否", "否"],
                "说明": [
                    f"可选值：{stock_in_type_hint}",
                    "格式：YYYY-MM-DD",
                    "供应商名称，必须在系统中已存在",
                    "物品编号，必须在系统中已存在",
                    "物品名称，可留空（按物品编号匹配）",
                    "规格型号，可留空",
                    "计量单位（个/盒/箱/包等），可留空",
                    "存放位置名称，必须在系统中已存在",
                    "正整数",
                    "单价，可留空默认0",
                    "备注信息，可留空",
                ]
            }
            df_desc = pd.DataFrame(desc_data)
            df_desc.to_excel(writer, index=False, sheet_name='填写说明')

        output.seek(0)
        filename = "入库单数据导入模板.xlsx"

        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='batch_import_export',
            action="下载入库单导入模板",
            result="成功"
        )
        logging.info(f'用户{current_user.id}下载入库单导入模板')

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'生成入库单导入模板失败: {str(e)}', exc_info=True)
        flash('生成模板失败，请联系管理员', 'danger')
        return redirect(url_for('stock_in.list_stock_ins'))


# 导出入库单列表
@stock_in_import_export_bp.route('/export', methods=['GET'])
@login_required
@require_permission('supply.export')
def export():
    """导出入库单数据为Excel（包含入库单汇总和入库明细两个工作表）"""
    try:
        logging.debug('开始执行入库单数据导出')

        # 查询所有入库单（含明细）
        stock_ins = StockIn.query.order_by(StockIn.stock_in_date.desc(), StockIn.id.desc()).all()
        logging.debug(f'查询到{len(stock_ins)}条入库单数据')

        if not stock_ins:
            logging.info('没有可导出的入库单数据')
            flash('没有可导出的入库单数据', 'info')
            return redirect(url_for('stock_in.list_stock_ins'))

        # 准备入库单汇总数据
        summary_data = []
        for si in stock_ins:
            try:
                summary_data.append({
                    '入库单号': si.stock_in_number or '',
                    '入库类型': si.stock_in_type or '',
                    '入库日期': si.stock_in_date.strftime('%Y-%m-%d') if si.stock_in_date else '',
                    '供应商': si.supplier_name or '',
                    '经手人': si.handler_name or '',
                    '总金额': float(si.total_amount) if si.total_amount else 0,
                    '状态': si.status or '',
                    '备注': si.remark or '',
                    '创建时间': si.created_at.strftime('%Y-%m-%d %H:%M') if si.created_at else '',
                    '更新时间': si.updated_at.strftime('%Y-%m-%d %H:%M') if si.updated_at else '',
                })
            except Exception as e:
                logging.error(f'处理入库单ID={si.id}时出错: {str(e)}', exc_info=True)
                raise

        # 准备入库明细数据
        detail_data = []
        for si in stock_ins:
            for d in si.details:
                try:
                    detail_data.append({
                        '入库单号': si.stock_in_number or '',
                        '入库类型': si.stock_in_type or '',
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
                    logging.error(f'处理入库明细ID={d.id}时出错: {str(e)}', exc_info=True)
                    raise

        logging.debug(f'数据准备完成，汇总{len(summary_data)}条，明细{len(detail_data)}条')

        # 生成Excel（两个工作表）
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, index=False, sheet_name='入库单汇总')

            df_detail = pd.DataFrame(detail_data)
            df_detail.to_excel(writer, index=False, sheet_name='入库明细')

        output.seek(0)
        filename = f"入库单数据导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        logging.debug(f'Excel文件生成成功，文件名: {filename}')

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='batch_import_export',
            action=f"导出入库单数据，共 {len(stock_ins)} 条记录",
            result="成功"
        )
        logging.info(f'用户{current_user.id}成功导出入库单数据')

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'导出入库单数据失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='batch_import_export',
            action=f"尝试导出入库单数据失败: {str(e)}",
            result="失败"
        )
        flash('导出失败，请联系管理员', 'danger')
        return redirect(url_for('stock_in.list_stock_ins'))


# 导入入库单数据
@stock_in_import_export_bp.route('/import', methods=['POST'])
@login_required
@require_permission('supply.import')
def import_stock_ins():
    """批量导入入库单数据"""
    try:
        logging.debug('开始批量导入入库单数据')

        # 前置条件：必须开启手动审核才能批量导入
        approval_enabled = SystemConfig.get_config_value('STOCK_IN_APPROVAL_ENABLED', True)
        if not approval_enabled:
            flash('批量导入入库单需要开启手动审核功能，请在系统设置中启用入库审核后再导入', 'danger')
            logging.warning('导入入库单数据失败：未开启手动审核')
            return redirect(url_for('stock_in.list_stock_ins'))

        # 验证文件是否存在
        if 'file' not in request.files:
            flash('请选择要导入的文件', 'danger')
            logging.error('导入入库单数据失败：未选择文件')
            return redirect(url_for('stock_in.list_stock_ins'))

        file = request.files['file']
        if file.filename == '':
            flash('请选择要导入的文件', 'danger')
            logging.error('导入入库单数据失败：未选择文件')
            return redirect(url_for('stock_in.list_stock_ins'))

        # 文件类型验证
        allowed_extensions = {'xlsx', 'xls'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            flash(f'请上传Excel格式的文件（.xlsx 或 .xls），当前文件类型：.{file_ext}', 'danger')
            logging.error(f'导入入库单数据失败：文件类型无效，当前文件类型：.{file_ext}')
            return redirect(url_for('stock_in.list_stock_ins'))

        # 限制文件大小（10MB）
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > 10 * 1024 * 1024:
            flash('文件大小超过限制（最大10MB）', 'danger')
            logging.error('导入入库单数据失败：文件大小超过限制（最大10MB）')
            return redirect(url_for('stock_in.list_stock_ins'))

        try:
            file_content = file.read()
            file_bytes = BytesIO(file_content)
            file_bytes.seek(0)
            df = pd.read_excel(file_bytes, sheet_name=0)
        except Exception as e:
            detailed_error = f"文件解析失败：{str(e)}"
            flash(detailed_error, 'danger')
            logging.error(f'导入入库单数据失败：文件解析失败 - {detailed_error}')
            return redirect(url_for('stock_in.list_stock_ins'))

        # 验证必要列
        required_columns = ['入库类型', '入库日期', '物品名称', '存放位置', '数量']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            flash(f'导入失败：文件缺少必要的列 - {", ".join(missing_columns)}', 'danger')
            logging.error(f'导入入库单数据失败：文件缺少必要的列 - {", ".join(missing_columns)}')
            return redirect(url_for('stock_in.list_stock_ins'))

        # 限制导入行数
        if len(df) > 500:
            flash('单次导入数据不超过500条', 'danger')
            logging.error('导入入库单数据失败：单次导入数据超过500条')
            return redirect(url_for('stock_in.list_stock_ins'))

        # 从系统配置获取入库类型选项
        stock_in_types = SystemConfig.get_config_value('stock_in_types', '采购入库,其它入库')
        if isinstance(stock_in_types, str):
            stock_in_types = [t.strip() for t in stock_in_types.split(',') if t.strip()]

        # 准备导入数据列表
        success_count = 0
        fail_count = 0
        error_records = []

        # 按入库类型+入库日期+供应商分组，同一组的明细归入同一张入库单
        from collections import OrderedDict
        grouped = OrderedDict()

        for index, row in df.iterrows():
            row_num = index + 2

            try:
                # === 必填字段验证 ===
                # 入库类型
                stock_in_type_val = row.get('入库类型')
                if pd.isna(stock_in_type_val) or str(stock_in_type_val).strip() == '':
                    error_records.append({'row': row_num, 'message': '入库类型不能为空'})
                    fail_count += 1
                    continue
                stock_in_type = str(stock_in_type_val).strip()
                if stock_in_types and stock_in_type not in stock_in_types:
                    error_records.append({'row': row_num, 'message': f'入库类型"{stock_in_type}"不在系统配置的可选值中（{"/".join(stock_in_types)}）'})
                    fail_count += 1
                    continue

                # 入库日期
                stock_in_date_val = row.get('入库日期')
                if pd.isna(stock_in_date_val) or str(stock_in_date_val).strip() == '':
                    error_records.append({'row': row_num, 'message': '入库日期不能为空'})
                    fail_count += 1
                    continue
                stock_in_date_str = str(stock_in_date_val).strip()
                # 处理pandas可能将日期解析为datetime的情况
                if isinstance(stock_in_date_val, datetime):
                    stock_in_date = stock_in_date_val.date()
                else:
                    try:
                        stock_in_date = datetime.strptime(stock_in_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        try:
                            stock_in_date = datetime.strptime(stock_in_date_str, '%Y/%m/%d').date()
                        except ValueError:
                            error_records.append({'row': row_num, 'message': f'入库日期格式不正确：{stock_in_date_str}，请使用YYYY-MM-DD格式'})
                            fail_count += 1
                            continue

                # 物品编号（必填）
                item_number_val = row.get('物品编号')
                if pd.isna(item_number_val) or str(item_number_val).strip() == '':
                    error_records.append({'row': row_num, 'message': '物品编号不能为空'})
                    fail_count += 1
                    continue
                item_number = str(item_number_val).strip()

                # 物品名称（可选）
                item_name_val = row.get('物品名称')
                item_name = str(item_name_val).strip() if pd.notna(item_name_val) and str(item_name_val).strip() else ''

                # 存放位置
                location_name_val = row.get('存放位置')
                if pd.isna(location_name_val) or str(location_name_val).strip() == '':
                    error_records.append({'row': row_num, 'message': '存放位置不能为空'})
                    fail_count += 1
                    continue
                location_name = str(location_name_val).strip()

                # 数量
                quantity_val = row.get('数量')
                if pd.isna(quantity_val):
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
                # 供应商名称
                supplier_name_val = row.get('供应商名称')
                supplier_name = str(supplier_name_val).strip() if pd.notna(supplier_name_val) and str(supplier_name_val).strip() else ''

                # 规格型号
                specification_val = row.get('规格型号')
                specification = str(specification_val).strip() if pd.notna(specification_val) and str(specification_val).strip() else ''

                # 单位
                unit_val = row.get('单位')
                unit = str(unit_val).strip() if pd.notna(unit_val) and str(unit_val).strip() else ''

                # 单价
                unit_price_val = row.get('单价')
                if pd.isna(unit_price_val) or str(unit_price_val).strip() == '':
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
                detail_remark = str(remark_val).strip() if pd.notna(remark_val) and str(remark_val).strip() else ''

                # 分组key：入库类型+入库日期+供应商名称
                group_key = (stock_in_type, stock_in_date_str, supplier_name)
                if group_key not in grouped:
                    grouped[group_key] = {
                        'stock_in_type': stock_in_type,
                        'stock_in_date': stock_in_date,
                        'supplier_name': supplier_name,
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
                logging.error(f'导入入库单数据失败：第{row_num}行数据解析失败 - {str(e)}')
                continue

        # 按分组创建入库单
        for group_key, group_data in grouped.items():
            try:
                stock_in_type = group_data['stock_in_type']
                stock_in_date = group_data['stock_in_date']
                supplier_name = group_data['supplier_name']

                # 处理供应商（严格模式：必须存在）
                supplier_id = None
                if supplier_name:
                    existing_supplier = Supplier.query.filter_by(name=supplier_name).first()
                    if existing_supplier:
                        supplier_id = existing_supplier.id
                    else:
                        # 供应商不存在，跳过该组所有明细
                        for detail in group_data['details']:
                            error_records.append({'row': detail['row_num'], 'message': f'供应商"{supplier_name}"在系统中不存在，请先在供应商管理中添加'})
                        fail_count += len(group_data['details'])
                        logging.warning(f'导入入库单数据失败：供应商"{supplier_name}"不存在')
                        continue

                # 创建入库主表
                stock_in = StockIn.create(
                    stock_in_type=stock_in_type,
                    stock_in_date=stock_in_date,
                    supplier_id=supplier_id,
                    handler_user_id=current_user.id,
                    remark=None,
                    operator_user_id=current_user.id
                )

                # 创建明细
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
                        # 单价为空时自动使用物品基础资料的单价
                        if unit_price == 0.0 and existing_by_number.unit_price:
                            unit_price = float(existing_by_number.unit_price)
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
                        # 入库单严格模式：位置不存在则跳过该明细
                        error_records.append({
                            'row': detail['row_num'],
                            'message': f'存放位置"{location_name}"在系统中不存在，请先在位置管理中添加'
                        })
                        fail_count += 1
                        continue

                    StockInDetail.create(
                        stock_in_id=stock_in.id,
                        item_id=item_id,
                        location_id=location_id,
                        quantity=quantity,
                        unit_price=unit_price,
                        item_name=item_name,
                        specification=specification if specification else None,
                        location_name=location_name,
                        unit=unit,
                        remark=detail_remark if detail_remark else None,
                        operator_user_id=current_user.id
                    )

                # 重新计算总金额
                StockIn.recalculate_total_amount(stock_in.id)

                success_count += len(group_data['details'])
                logging.info(f"导入入库单成功，入库单ID: {stock_in.id}, 单号: {stock_in.stock_in_number}")

            except Exception as e:
                # 记录该组所有行的错误
                for detail in group_data['details']:
                    error_records.append({'row': detail['row_num'], 'message': f'创建入库单失败：{str(e)}'})
                    fail_count += 1
                logging.error(f'导入入库单数据失败：创建入库单失败 - {str(e)}')
                continue

        db.session.commit()

        # 记录操作日志
        if success_count > 0:
            result_status = "部分成功" if fail_count > 0 else "成功"
        else:
            result_status = "失败"

        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='batch_import_export',
            action=f"导入入库单数据，成功{success_count}条明细，失败{fail_count}条",
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
            message = f"导入全部成功：共导入 {success_count} 条入库明细"
        else:
            message = f"导入全部失败：共{len(error_records)}条记录处理失败：<br>" + "<br>".join(
                [f"第{err['row']}行：{err['message']}" for err in error_records[:5]]
            )
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"

        logging.info(message)
        flash(message, 'success' if result_status == "成功" else 'warning' if result_status == "部分成功" else 'danger')
        return redirect(url_for('stock_in.list_stock_ins'))

    except Exception as e:
        db.session.rollback()
        detailed_error = f"导入过程出错：{str(e)}"
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='batch_import_export',
            action=f"入库单数据导入失败: {detailed_error}\n{traceback.format_exc()}",
            result="失败"
        )
        flash(detailed_error, 'danger')
        logging.error(f'导入入库单数据失败：{detailed_error}')
        return redirect(url_for('stock_in.list_stock_ins'))