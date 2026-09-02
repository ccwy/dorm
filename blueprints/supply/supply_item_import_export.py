import os
from flask import Blueprint, request, flash, redirect, url_for, send_file
import logging
from utils.db import db
from models.supply.supply_item import SupplyItem
from models.supply.supplier import Supplier
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.lazy_imports import pd  # 延迟导入pandas，避免启动时加载重型库
import io
from datetime import datetime
import traceback
from utils.auth import require_permission
from io import BytesIO

# 创建导入导出专用蓝图
supply_item_import_export_bp = Blueprint(
    'supply_item_import_export',
    __name__,
    url_prefix='/supply-item/import-export',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/supply-item/import-export/static'
)


# 导出物品数据
@supply_item_import_export_bp.route('/export', methods=['GET'])
@login_required
@require_permission('supply.export')
def export():
    """导出物品数据为Excel"""
    try:
        logging.debug('开始执行物品数据导出')

        # 获取物品数据
        items = SupplyItem.query.order_by(SupplyItem.id).all()
        logging.debug(f'查询到{len(items)}条物品数据')

        if not items:
            logging.info('没有可导出的物品数据')
            flash('没有可导出的物品数据', 'info')
            return redirect(url_for('supply_item.index'))

        # 准备导出数据
        data = []
        for item in items:
            try:
                # 获取供应商名称
                supplier_name = ''
                if item.supplier_id:
                    supplier = Supplier.query.get(item.supplier_id)
                    supplier_name = supplier.name if supplier else ''

                data.append({
                    '物品编号': item.item_number or '',
                    '物品名称': item.name or '',
                    '分类': item.category or '',
                    '规格型号': item.specification or '',
                    '单位': item.unit or '',
                    '供应商': supplier_name,
                    '单价': float(item.unit_price) if item.unit_price else 0,
                    '参考价格': float(item.reference_price) if item.reference_price else '',
                    '最低库存': item.min_stock if item.min_stock is not None else 0,
                    '最高库存': item.max_stock if item.max_stock is not None else '',
                    '状态': item.status or '启用',
                    '备注': item.remark or '',
                    '创建时间': item.created_at.strftime('%Y-%m-%d %H:%M') if item.created_at else '',
                    '更新时间': item.updated_at.strftime('%Y-%m-%d %H:%M') if item.updated_at else '',
                })
            except Exception as e:
                logging.error(f'处理物品ID={item.id}时出错: {str(e)}', exc_info=True)
                raise

        logging.debug(f'数据准备完成，共{len(data)}条记录')

        # 生成Excel
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='物品数据')

        output.seek(0)
        filename = f"物品数据导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        logging.debug(f'Excel文件生成成功，文件名: {filename}')

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='batch_import_export',
            action=f"导出物品数据，共 {len(items)} 条记录",
            result="成功"
        )
        logging.info(f'用户{current_user.id}成功导出物品数据')

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'导出物品数据失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='batch_import_export',
            action=f"尝试导出物品数据失败: {str(e)}",
            result="失败"
        )
        flash('导出失败，请联系管理员', 'danger')
        return redirect(url_for('supply_item.index'))


# 导入物品数据
@supply_item_import_export_bp.route('/import', methods=['POST'])
@login_required
@require_permission('supply.import')
def import_items():
    """批量导入物品数据"""
    try:
        logging.debug('开始批量导入物品数据')
        # 验证文件是否存在
        if 'file' not in request.files:
            flash('请选择要导入的文件', 'danger')
            logging.error('导入物品数据失败：未选择文件')
            return redirect(url_for('supply_item.index'))

        file = request.files['file']
        if file.filename == '':
            flash('请选择要导入的文件', 'danger')
            logging.error('导入物品数据失败：未选择文件')
            return redirect(url_for('supply_item.index'))

        # 文件类型验证
        allowed_extensions = {'xlsx', 'xls'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            flash(f'请上传Excel格式的文件（.xlsx 或 .xls），当前文件类型：.{file_ext}', 'danger')
            logging.error(f'导入物品数据失败：文件类型无效，当前文件类型：.{file_ext}')
            return redirect(url_for('supply_item.index'))

        # 限制文件大小（10MB）
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > 10 * 1024 * 1024:
            flash('文件大小超过限制（最大10MB）', 'danger')
            logging.error('导入物品数据失败：文件大小超过限制（最大10MB）')
            return redirect(url_for('supply_item.index'))

        try:
            file_content = file.read()
            file_bytes = BytesIO(file_content)
            file_bytes.seek(0)
            df = pd.read_excel(file_bytes)
        except Exception as e:
            detailed_error = f"文件解析失败：{str(e)}"
            flash(detailed_error, 'danger')
            logging.error(f'导入物品数据失败：文件解析失败 - {detailed_error}')
            return redirect(url_for('supply_item.index'))

        # 验证必要列
        required_columns = ['物品名称']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            flash(f'导入失败：文件缺少必要的列 - {", ".join(missing_columns)}', 'danger')
            logging.error(f'导入物品数据失败：文件缺少必要的列 - {", ".join(missing_columns)}')
            return redirect(url_for('supply_item.index'))

        # 是否覆盖已有数据（兼容overwrite和override两种参数名）
        overwrite = request.form.get('overwrite', '') == '1' or request.form.get('override', '') == '1'

        # 预加载供应商名称→ID映射
        supplier_map = {}
        suppliers = Supplier.query.all()
        for s in suppliers:
            supplier_map[s.name.strip()] = s.id

        # 获取系统配置默认值
        from models.system_config import SystemConfig
        default_min_stock = SystemConfig.get_config_value('supply_default_min_stock', 0)

        # 准备导入数据列表
        success_count = 0
        fail_count = 0
        error_records = []
        warning_records = []

        for index, row in df.iterrows():
            try:
                row_num = index + 2

                # 物品名称（必填）
                name_val = row.get('物品名称')
                if pd.isna(name_val) or str(name_val).strip() == '':
                    error_records.append(f"第{row_num}行：物品名称不能为空")
                    fail_count += 1
                    continue
                name = str(name_val).strip()

                # 物品编号（可选，留空自动生成）
                item_number = None
                item_number_val = row.get('物品编号')
                if pd.notna(item_number_val) and str(item_number_val).strip():
                    item_number = str(item_number_val).strip()
                    # 检查编号是否已存在
                    existing_by_number = SupplyItem.query.filter_by(item_number=item_number).first()
                    if existing_by_number:
                        if overwrite:
                            # 编号重复时覆盖更新
                            _update_item_from_row(existing_by_number, row, row_num, supplier_map, default_min_stock, warning_records, current_user.id)
                            success_count += 1
                            continue
                        else:
                            error_records.append(f'第{row_num}行：物品编号"{item_number}"已存在')
                            fail_count += 1
                            continue

                # 分类（可选）
                category = None
                category_val = row.get('分类')
                if pd.notna(category_val) and str(category_val).strip():
                    category = str(category_val).strip()

                # 规格型号（可选）
                specification = None
                specification_val = row.get('规格型号')
                if pd.notna(specification_val) and str(specification_val).strip():
                    specification = str(specification_val).strip()

                # 单位（可选）
                unit = None
                unit_val = row.get('单位')
                if pd.notna(unit_val) and str(unit_val).strip():
                    unit = str(unit_val).strip()

                # 供应商（可选，按名称匹配）
                supplier_id = None
                supplier_val = row.get('供应商')
                if pd.notna(supplier_val) and str(supplier_val).strip():
                    supplier_name = str(supplier_val).strip()
                    if supplier_name in supplier_map:
                        supplier_id = supplier_map[supplier_name]
                    else:
                        warning_records.append(f'第{row_num}行：供应商"{supplier_name}"未找到，已忽略')

                # 单价（可选，默认0）
                unit_price = 0
                unit_price_val = row.get('单价')
                if pd.notna(unit_price_val):
                    try:
                        unit_price = float(unit_price_val)
                    except (ValueError, TypeError):
                        warning_records.append(f'第{row_num}行：单价格式无效，使用默认值0')

                # 参考价格（可选）
                reference_price = None
                reference_price_val = row.get('参考价格')
                if pd.notna(reference_price_val):
                    try:
                        reference_price = float(reference_price_val)
                    except (ValueError, TypeError):
                        warning_records.append(f'第{row_num}行：参考价格格式无效，已忽略')

                # 最低库存（可选，使用系统配置默认值）
                min_stock = default_min_stock
                min_stock_val = row.get('最低库存')
                if pd.notna(min_stock_val):
                    try:
                        min_stock = int(float(min_stock_val))
                    except (ValueError, TypeError):
                        warning_records.append(f'第{row_num}行：最低库存格式无效，使用默认值{default_min_stock}')

                # 最高库存（可选）
                max_stock = None
                max_stock_val = row.get('最高库存')
                if pd.notna(max_stock_val):
                    try:
                        max_stock = int(float(max_stock_val))
                    except (ValueError, TypeError):
                        warning_records.append(f'第{row_num}行：最高库存格式无效，已忽略')

                # 状态（可选，默认"启用"）
                status = '启用'
                status_val = row.get('状态')
                if pd.notna(status_val) and str(status_val).strip():
                    status = str(status_val).strip()
                if status not in ['启用', '停用']:
                    status = '启用'

                # 备注（可选）
                remark = None
                remark_val = row.get('备注')
                if pd.notna(remark_val) and str(remark_val).strip():
                    remark = str(remark_val).strip()

                # 检查名称是否重复（非编号覆盖场景）
                existing = SupplyItem.query.filter_by(name=name).first()
                if existing:
                    if overwrite:
                        # 覆盖更新
                        existing.category = category or existing.category
                        existing.specification = specification or existing.specification
                        existing.unit = unit or existing.unit
                        existing.supplier_id = supplier_id if supplier_id is not None else existing.supplier_id
                        existing.unit_price = unit_price if unit_price > 0 else existing.unit_price
                        existing.reference_price = reference_price if reference_price is not None else existing.reference_price
                        existing.min_stock = min_stock if min_stock != default_min_stock else existing.min_stock
                        existing.max_stock = max_stock if max_stock is not None else existing.max_stock
                        existing.status = status
                        existing.remark = remark or existing.remark
                        existing.operator_user_id = current_user.id
                        success_count += 1
                        continue
                    else:
                        error_records.append(f'第{row_num}行：物品名称"{name}"已存在')
                        fail_count += 1
                        continue

                # 创建物品
                SupplyItem.create(
                    name=name,
                    category=category,
                    specification=specification,
                    unit=unit,
                    supplier_id=supplier_id,
                    unit_price=unit_price,
                    reference_price=reference_price,
                    min_stock=min_stock,
                    max_stock=max_stock,
                    status=status,
                    remark=remark,
                    operator_user_id=current_user.id,
                    item_number=item_number
                )
                success_count += 1

            except ValueError as e:
                error_records.append(f"第{row_num}行：{str(e)}")
                fail_count += 1
                logging.error(f'导入物品数据失败：第{row_num}行 - {str(e)}')
                continue
            except Exception as e:
                error_records.append(f"第{row_num}行：创建物品失败 - {str(e)}")
                fail_count += 1
                logging.error(f'导入物品数据失败：第{row_num}行创建物品失败 - {str(e)}')
                continue

        db.session.commit()

        # 记录操作日志
        total_count = success_count + fail_count
        if success_count > 0:
            result_status = "部分成功" if fail_count > 0 else "成功"
        else:
            result_status = "失败"

        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='batch_import_export',
            action=f"导入物品数据，成功{success_count}条，失败{fail_count}条",
            result=result_status
        )

        # 生成提示信息
        if result_status == "部分成功":
            message = f"导入部分成功：成功导入 {success_count} 条，失败 {fail_count} 条"
            message += f"<br>失败详情：<br>" + "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"
        elif result_status == "成功":
            message = f"导入全部成功：共导入 {success_count} 条物品数据"
        else:
            message = f"导入全部失败：共{len(error_records)}条记录处理失败：<br>" + "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"

        # 添加警告信息
        if warning_records:
            message += f"<br><br>警告信息：<br>" + "<br>".join(warning_records[:5])
            if len(warning_records) > 5:
                message += f"<br>... 还有 {len(warning_records)-5} 条警告"

        logging.info(message)
        flash(message, 'success' if result_status == "成功" else 'warning' if result_status == "部分成功" else 'danger')
        return redirect(url_for('supply_item.index'))

    except Exception as e:
        db.session.rollback()
        detailed_error = f"导入过程出错：{str(e)}"
        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='batch_import_export',
            action=f"物品数据导入失败: {detailed_error}\n{traceback.format_exc()}",
            result="失败"
        )
        flash(detailed_error, 'danger')
        logging.error(f'导入物品数据失败：{detailed_error}')
        return redirect(url_for('supply_item.index'))


def _update_item_from_row(item, row, row_num, supplier_map, default_min_stock, warning_records, operator_user_id):
    """根据导入行数据更新已有物品（按编号匹配覆盖时使用）"""
    # 分类
    category_val = row.get('分类')
    if pd.notna(category_val) and str(category_val).strip():
        item.category = str(category_val).strip()

    # 规格型号
    specification_val = row.get('规格型号')
    if pd.notna(specification_val) and str(specification_val).strip():
        item.specification = str(specification_val).strip()

    # 单位
    unit_val = row.get('单位')
    if pd.notna(unit_val) and str(unit_val).strip():
        item.unit = str(unit_val).strip()

    # 供应商
    supplier_val = row.get('供应商')
    if pd.notna(supplier_val) and str(supplier_val).strip():
        supplier_name = str(supplier_val).strip()
        if supplier_name in supplier_map:
            item.supplier_id = supplier_map[supplier_name]
        else:
            warning_records.append(f'第{row_num}行：供应商"{supplier_name}"未找到，已忽略')

    # 单价
    unit_price_val = row.get('单价')
    if pd.notna(unit_price_val):
        try:
            item.unit_price = float(unit_price_val)
        except (ValueError, TypeError):
            warning_records.append(f'第{row_num}行：单价格式无效，已忽略')

    # 参考价格
    reference_price_val = row.get('参考价格')
    if pd.notna(reference_price_val):
        try:
            item.reference_price = float(reference_price_val)
        except (ValueError, TypeError):
            warning_records.append(f'第{row_num}行：参考价格格式无效，已忽略')

    # 最低库存
    min_stock_val = row.get('最低库存')
    if pd.notna(min_stock_val):
        try:
            item.min_stock = int(float(min_stock_val))
        except (ValueError, TypeError):
            warning_records.append(f'第{row_num}行：最低库存格式无效，已忽略')

    # 最高库存
    max_stock_val = row.get('最高库存')
    if pd.notna(max_stock_val):
        try:
            item.max_stock = int(float(max_stock_val))
        except (ValueError, TypeError):
            warning_records.append(f'第{row_num}行：最高库存格式无效，已忽略')

    # 状态
    status_val = row.get('状态')
    if pd.notna(status_val) and str(status_val).strip():
        status = str(status_val).strip()
        if status in ['启用', '停用']:
            item.status = status

    # 备注
    remark_val = row.get('备注')
    if pd.notna(remark_val) and str(remark_val).strip():
        item.remark = str(remark_val).strip()

    # 名称
    name_val = row.get('物品名称')
    if pd.notna(name_val) and str(name_val).strip():
        item.name = str(name_val).strip()

    item.operator_user_id = operator_user_id


# 下载导入模板
@supply_item_import_export_bp.route('/template', methods=['GET'])
@login_required
@require_permission('supply.import')
def download_template():
    """生成并下载物品数据导入模板"""
    try:
        logging.debug('开始生成物品数据导入模板')

        # 模板数据生成
        template_data = {
            "物品编号": ["YP2026080001", "", ""],
            "物品名称": ["示例物品A", "示例物品B", "示例物品C"],
            "分类": ["办公用品", "清洁用品", "维修工具"],
            "规格型号": ["A4 500张/包", "500ml/瓶", "十字 PH2"],
            "单位": ["包", "瓶", "把"],
            "供应商": ["示例供应商A", "示例供应商B", ""],
            "单价": [25.00, 15.50, 35.00],
            "参考价格": [28.00, 18.00, ""],
            "最低库存": [10, 5, 2],
            "最高库存": [100, 50, 20],
            "状态": ["启用", "启用", "停用"],
            "备注": ["常用办公用品", "", "备用工具"],
        }

        df = pd.DataFrame(template_data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='物品数据')

        output.seek(0)
        filename = "物品数据导入模板.xlsx"

        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='batch_import_export',
            action="下载物品数据导入模板",
            result="成功"
        )

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'生成物品数据导入模板失败: {str(e)}', exc_info=True)
        flash('生成模板失败，请联系管理员', 'danger')
        return redirect(url_for('supply_item.index'))