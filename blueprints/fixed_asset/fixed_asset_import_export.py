import os
from flask import Blueprint, request, flash, redirect, url_for, send_file
import logging
from utils.db import db
from models.fixed_asset.fixed_asset import FixedAsset
from models.fixed_asset.asset_operation_record import AssetOperationRecord
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
from utils.lazy_imports import pd  # 延迟导入pandas，避免启动时加载重型库
import io
from datetime import datetime
import traceback
from models.system_config.system_config import SystemConfig
from models.department.department import Department
from models.room.room import Room
from models.user.user import User
from io import BytesIO
from utils.excel_date_utils import excel_date_utils
from decimal import Decimal

# 创建导入导出专用蓝图
fixed_asset_import_export_bp = Blueprint(
    'fixed_asset_import_export',
    __name__,
    url_prefix='/fixed_asset/import-export',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/fixed_asset/import-export/static'
)


def _ensure_department_exists(name, company=None):
    """确保部门存在，不存在则自动创建（按name+company联合查找）"""
    if not name:
        return
    # 按name+company查找
    query = Department.query.filter_by(name=name)
    if company:
        query = query.filter(db.or_(Department.company == company, Department.company.is_(None)))
    else:
        query = query.filter(Department.company.is_(None))
    existing = query.first()
    if not existing:
        Department.create(name=name, company=company, status='正常')


# 导出资产数据
@fixed_asset_import_export_bp.route('/export', methods=['GET'])
@login_required
@require_permission('fixed_asset.export')
def export():
    try:
        logging.debug('开始执行固定资产数据导出')

        # 获取资产数据
        assets = FixedAsset.query.all()
        logging.debug(f'查询到{len(assets)}条资产数据')

        if not assets:
            logging.info('没有可导出的资产数据')
            flash('没有可导出的资产数据', 'info')
            return redirect(url_for('fixed_asset.index'))

        # 准备导出数据
        logging.debug('开始准备导出数据')
        data = []
        for asset in assets:
            try:
                data.append({
                    '资产编号': asset.asset_number or '',
                    '资产名称': asset.asset_name or '',
                    '资产分类': asset.asset_category or '',
                    '规格型号': asset.specification or '',
                    '品牌': asset.brand or '',
                    '供应商': asset.supplier or '',
                    '数量': asset.quantity or 1,
                    '单位': asset.unit or '',
                    '原值': float(asset.original_value) if asset.original_value else 0.00,
                    '净值': float(asset.net_value) if asset.net_value else 0.00,
                    '购置日期': asset.purchase_date.strftime('%Y-%m-%d') if asset.purchase_date else '',
                    '质保到期日': asset.warranty_expiry.strftime('%Y-%m-%d') if asset.warranty_expiry else '',
                    '存放位置': asset.storage_location or '',
                    '所属公司': asset.company or '',
                    '使用部门': asset.department_using or '',
                    '归属部门': asset.department_owning or '',
                    '责任人': asset.responsible_person or '',
                    '关联房间': asset.room_display or '',
                    '责任人用户': asset.responsible_user_name or '',
                    '资产来源': asset.asset_source or '',
                    '状态': asset.status or '',
                    '备注': asset.remark or '',
                })
            except Exception as e:
                logging.error(f'处理资产ID={asset.id}时出错: {str(e)}', exc_info=True)
                raise

        logging.debug(f'数据准备完成，共{len(data)}条记录')

        # 生成Excel
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='固定资产数据')

        output.seek(0)
        filename = f"固定资产数据导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        logging.debug(f'Excel文件生成成功，文件名: {filename}')

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='batch_import_export',
            action=f"导出固定资产数据，共 {len(assets)} 条记录",
            result="成功"
        )
        logging.info(f'用户{current_user.id}成功导出固定资产数据')

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'导出固定资产数据失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='batch_import_export',
            action=f"尝试导出固定资产数据失败: {str(e)}",
            result="失败"
        )
        flash(f'导出失败，请联系管理员', 'danger')
        return redirect(url_for('fixed_asset.index'))


# 导入资产数据
@fixed_asset_import_export_bp.route('/import', methods=['POST'])
@login_required
@require_permission('fixed_asset.import')
def import_assets():
    """批量导入固定资产数据"""
    try:
        logging.debug('开始批量导入固定资产数据')
        # 验证文件是否存在
        if 'file' not in request.files:
            flash('请选择要导入的文件', 'danger')
            logging.error('导入固定资产数据失败：未选择文件')
            return redirect(url_for('fixed_asset.index'))

        file = request.files['file']
        if file.filename == '':
            flash('请选择要导入的文件', 'danger')
            logging.error('导入固定资产数据失败：未选择文件')
            return redirect(url_for('fixed_asset.index'))

        # 文件类型验证
        allowed_extensions = {'xlsx', 'xls'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            flash(f'请上传Excel格式的文件（.xlsx 或 .xls），当前文件类型：.{file_ext}', 'danger')
            logging.error(f'导入固定资产数据失败：文件类型无效，当前文件类型：.{file_ext}')
            return redirect(url_for('fixed_asset.index'))

        # 限制文件大小（10MB）
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > 10 * 1024 * 1024:
            flash('文件大小超过限制（最大10MB）', 'danger')
            logging.error('导入固定资产数据失败：文件大小超过限制（最大10MB）')
            return redirect(url_for('fixed_asset.index'))

        try:
            file_content = file.read()
            file_bytes = BytesIO(file_content)
            file_bytes.seek(0)
            df = pd.read_excel(file_bytes)
        except Exception as e:
            detailed_error = f"文件解析失败：{str(e)}"
            log_operation(
                user_id=current_user.id,
                action="解析Excel文件",
                result=f"失败: {detailed_error}"
            )
            flash(detailed_error, 'danger')
            logging.error(f'导入固定资产数据失败：文件解析失败 - {detailed_error}')
            return redirect(url_for('fixed_asset.index'))

        # 验证必要列
        required_columns = ['资产名称', '资产分类']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            flash(f'导入失败：文件缺少必要的列 - {", ".join(missing_columns)}', 'danger')
            logging.error(f'导入固定资产数据失败：文件缺少必要的列 - {", ".join(missing_columns)}')
            return redirect(url_for('fixed_asset.index'))

        # 获取有效的配置数据
        valid_categories = SystemConfig.get_config_value('ASSET_CATEGORIES', '办公设备,家具,交通工具,电子设备,机械设备,其他')
        if isinstance(valid_categories, str):
            valid_categories = [c.strip() for c in valid_categories.split(',') if c.strip()]

        valid_statuses = SystemConfig.get_config_value('ASSET_STATUSES', '在用,闲置,维修中,已报废,已转移,已出售')
        if isinstance(valid_statuses, str):
            valid_statuses = [s.strip() for s in valid_statuses.split(',') if s.strip()]

        valid_sources = ['采购', '捐赠', '调入', '自建', '其他']

        # 准备导入数据列表
        assets_data = []
        error_records = []
        success_count = 0
        fail_count = 0

        # 批量解析日期字段
        purchase_date_values = df.get('购置日期', pd.Series([None] * len(df)))
        warranty_expiry_values = df.get('质保到期日', pd.Series([None] * len(df)))

        try:
            parsed_purchase_dates = excel_date_utils.parse_excel_date(purchase_date_values, field_name='购置日期', raise_error=False)
        except Exception:
            parsed_purchase_dates = {i: None for i in range(len(df))}

        try:
            parsed_warranty_dates = excel_date_utils.parse_excel_date(warranty_expiry_values, field_name='质保到期日', raise_error=False)
        except Exception:
            parsed_warranty_dates = {i: None for i in range(len(df))}

        for index, row in df.iterrows():
            try:
                row_num = index + 2

                # 资产名称（必填）
                asset_name_val = row.get('资产名称')
                if pd.isna(asset_name_val) or str(asset_name_val).strip() == '':
                    error_records.append(f"第{row_num}行：资产名称不能为空")
                    fail_count += 1
                    continue
                asset_name = str(asset_name_val).strip()

                # 资产分类（必填）
                asset_category_val = row.get('资产分类')
                if pd.isna(asset_category_val) or str(asset_category_val).strip() == '':
                    error_records.append(f"第{row_num}行：资产分类不能为空")
                    fail_count += 1
                    continue
                asset_category = str(asset_category_val).strip()
                if valid_categories and asset_category not in valid_categories:
                    error_records.append(
                        f"第{row_num}行：资产分类 '{asset_category}' 无效，有效分类为：{', '.join(valid_categories)}"
                    )
                    fail_count += 1
                    continue

                # 资产编号（可选，留空自动生成）
                asset_number_val = row.get('资产编号')
                asset_number = None
                if pd.notna(asset_number_val) and str(asset_number_val).strip():
                    asset_number = str(asset_number_val).strip()
                    # 检查编号是否已存在
                    existing = FixedAsset.query.filter_by(asset_number=asset_number).first()
                    if existing:
                        error_records.append(f"第{row_num}行：资产编号 '{asset_number}' 已存在")
                        fail_count += 1
                        continue

                # 规格型号
                specification_val = row.get('规格型号')
                specification = str(specification_val).strip() if pd.notna(specification_val) and str(specification_val).strip() else None

                # 品牌
                brand_val = row.get('品牌')
                brand = str(brand_val).strip() if pd.notna(brand_val) and str(brand_val).strip() else None

                # 供应商
                supplier_val = row.get('供应商')
                supplier = str(supplier_val).strip() if pd.notna(supplier_val) and str(supplier_val).strip() else None

                # 数量
                quantity_val = row.get('数量')
                if pd.isna(quantity_val) or str(quantity_val).strip() == '':
                    quantity = 1
                else:
                    try:
                        quantity = int(float(str(quantity_val).strip()))
                        if quantity <= 0:
                            error_records.append(f"第{row_num}行：数量必须为正整数")
                            fail_count += 1
                            continue
                    except (ValueError, TypeError):
                        error_records.append(f"第{row_num}行：数量必须为整数")
                        fail_count += 1
                        continue

                # 单位
                unit_val = row.get('单位')
                unit = str(unit_val).strip() if pd.notna(unit_val) and str(unit_val).strip() else '台'

                # 原值
                original_value_val = row.get('原值')
                try:
                    if pd.isna(original_value_val) or str(original_value_val).strip() == '':
                        original_value = Decimal('0.00')
                    else:
                        original_value = Decimal(str(float(str(original_value_val).strip()))).quantize(Decimal('0.01'))
                except (ValueError, TypeError):
                    error_records.append(f"第{row_num}行：原值必须为有效的数字")
                    fail_count += 1
                    continue

                # 净值
                net_value_val = row.get('净值')
                try:
                    if pd.isna(net_value_val) or str(net_value_val).strip() == '':
                        net_value = Decimal('0.00')
                    else:
                        net_value = Decimal(str(float(str(net_value_val).strip()))).quantize(Decimal('0.01'))
                except (ValueError, TypeError):
                    error_records.append(f"第{row_num}行：净值必须为有效的数字")
                    fail_count += 1
                    continue

                # 购置日期
                purchase_date = parsed_purchase_dates.get(index) if isinstance(parsed_purchase_dates, dict) else (parsed_purchase_dates[index] if index in parsed_purchase_dates.index else None)
                purchase_date_val = row.get('购置日期')
                if pd.notna(purchase_date_val) and purchase_date is None:
                    # 尝试直接解析
                    try:
                        if hasattr(purchase_date_val, 'date'):
                            purchase_date = purchase_date_val.date()
                        else:
                            purchase_date = datetime.strptime(str(purchase_date_val).strip(), '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        pass

                # 质保到期日
                warranty_expiry = parsed_warranty_dates.get(index) if isinstance(parsed_warranty_dates, dict) else (parsed_warranty_dates[index] if index in parsed_warranty_dates.index else None)
                warranty_expiry_val = row.get('质保到期日')
                if pd.notna(warranty_expiry_val) and warranty_expiry is None:
                    try:
                        if hasattr(warranty_expiry_val, 'date'):
                            warranty_expiry = warranty_expiry_val.date()
                        else:
                            warranty_expiry = datetime.strptime(str(warranty_expiry_val).strip(), '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        pass

                # 存放位置
                storage_location_val = row.get('存放位置')
                storage_location = str(storage_location_val).strip() if pd.notna(storage_location_val) and str(storage_location_val).strip() else None

                # 所属公司
                company_val = row.get('所属公司')
                company = str(company_val).strip() if pd.notna(company_val) and str(company_val).strip() else None

                # 使用部门
                department_using_val = row.get('使用部门')
                department_using = str(department_using_val).strip() if pd.notna(department_using_val) and str(department_using_val).strip() else None

                # 归属部门
                department_owning_val = row.get('归属部门')
                department_owning = str(department_owning_val).strip() if pd.notna(department_owning_val) and str(department_owning_val).strip() else None

                # 自动创建新部门（传入company）
                _ensure_department_exists(department_using, company)
                _ensure_department_exists(department_owning, company)

                # 按名称+公司查找部门ID
                dept_using_id = None
                dept_owning_id = None
                if department_using:
                    dept_query = Department.query.filter_by(name=department_using)
                    if company:
                        dept_query = dept_query.filter(db.or_(Department.company == company, Department.company.is_(None)))
                    else:
                        dept_query = dept_query.filter(Department.company.is_(None))
                    dept = dept_query.first()
                    if dept:
                        dept_using_id = dept.id
                        if not company and dept.company:
                            company = dept.company

                if department_owning:
                    dept_query = Department.query.filter_by(name=department_owning)
                    if company:
                        dept_query = dept_query.filter(db.or_(Department.company == company, Department.company.is_(None)))
                    else:
                        dept_query = dept_query.filter(Department.company.is_(None))
                    dept = dept_query.first()
                    if dept:
                        dept_owning_id = dept.id
                        if not company and dept.company and not company:
                            company = dept.company

                # 责任人
                responsible_person_val = row.get('责任人')
                responsible_person = str(responsible_person_val).strip() if pd.notna(responsible_person_val) and str(responsible_person_val).strip() else None

                # 关联房间（按"楼栋+房间号"格式查找）
                room_id = None
                room_display_val = row.get('关联房间')
                if pd.notna(room_display_val) and str(room_display_val).strip():
                    room_display_str = str(room_display_val).strip()
                    # 尝试按"楼栋房间号"格式匹配，如"A栋101"
                    room_obj = Room.query.filter(
                        db.func.concat(Room.building, Room.room_number) == room_display_str
                    ).first()
                    if room_obj:
                        room_id = room_obj.id
                    else:
                        # 尝试按楼栋或房间号模糊匹配
                        room_obj = Room.query.filter(
                            db.or_(Room.building.ilike(f'%{room_display_str}%'), Room.room_number.ilike(f'%{room_display_str}%'))
                        ).first()
                        if room_obj:
                            room_id = room_obj.id

                # 责任人用户（按姓名查找在职用户）
                responsible_user_id = None
                responsible_user_val = row.get('责任人用户')
                if pd.notna(responsible_user_val) and str(responsible_user_val).strip():
                    responsible_user_name = str(responsible_user_val).strip()
                    user_obj = User.query.filter(User.name == responsible_user_name, User.status == '在职').first()
                    if user_obj:
                        responsible_user_id = user_obj.id
                        # 如果匹配到用户，自动同步责任人姓名（与表单行为一致）
                        responsible_person = user_obj.name

                # 资产来源
                asset_source_val = row.get('资产来源')
                if pd.isna(asset_source_val) or str(asset_source_val).strip() == '':
                    asset_source = '采购'
                else:
                    asset_source = str(asset_source_val).strip()
                    if asset_source not in valid_sources:
                        error_records.append(
                            f"第{row_num}行：资产来源 '{asset_source}' 无效，有效值为：{', '.join(valid_sources)}"
                        )
                        fail_count += 1
                        continue

                # 状态
                status_val = row.get('状态')
                if pd.isna(status_val) or str(status_val).strip() == '':
                    status = '在用'
                else:
                    status = str(status_val).strip()
                    if valid_statuses and status not in valid_statuses:
                        error_records.append(
                            f"第{row_num}行：状态 '{status}' 无效，有效状态为：{', '.join(valid_statuses)}"
                        )
                        fail_count += 1
                        continue

                # 备注
                remark_val = row.get('备注')
                remark = str(remark_val).strip() if pd.notna(remark_val) and str(remark_val).strip() else None

                # 创建资产记录
                try:
                    asset = FixedAsset.create(
                        asset_number=asset_number,
                        asset_name=asset_name,
                        asset_category=asset_category,
                        specification=specification,
                        brand=brand,
                        supplier=supplier,
                        quantity=quantity,
                        unit=unit,
                        original_value=original_value,
                        net_value=net_value,
                        purchase_date=purchase_date,
                        warranty_expiry=warranty_expiry,
                        storage_location=storage_location,
                        company=company,
                        department_using_id=dept_using_id,
                        department_owning_id=dept_owning_id,
                        responsible_person=responsible_person,
                        room_id=room_id,
                        responsible_user_id=responsible_user_id,
                        asset_source=asset_source,
                        status=status,
                        remark=remark,
                        operator_user_id=current_user.id
                    )

                    # 记录操作日志
                    AssetOperationRecord.create_record(
                        asset_id=asset.id,
                        operation_type='add',
                        operator_id=current_user.id,
                        operator_name=current_user.username if hasattr(current_user, 'username') else str(current_user.id),
                        change_detail={
                            'asset_number': asset.asset_number or '',
                            'asset_name': asset.asset_name,
                            'asset_category': asset.asset_category,
                            'specification': asset.specification or '',
                            'brand': asset.brand or '',
                            'supplier': asset.supplier or '',
                            'quantity': asset.quantity,
                            'unit': asset.unit or '台',
                            'original_value': str(asset.original_value) if asset.original_value else '',
                            'net_value': str(asset.net_value) if asset.net_value else '',
                            'purchase_date': asset.purchase_date.isoformat() if asset.purchase_date else '',
                            'warranty_expiry': asset.warranty_expiry.isoformat() if asset.warranty_expiry else '',
                            'storage_location': asset.storage_location or '',
                            'company': asset.company or '',
                            'department_using': asset.department_using or '',
                            'department_owning': asset.department_owning or '',
                            'responsible_person': asset.responsible_person or '',
                            'room_display': asset.room_display or '',
                            'responsible_user_name': asset.responsible_user_name or '',
                            'asset_source': asset.asset_source or '采购',
                            'status': asset.status,
                            'import_source': 'Excel批量导入',
                        },
                        summary=f"批量导入新增资产: {asset.asset_name}({asset.display_number})，分类: {asset.asset_category}，数量: {asset.quantity}{asset.unit or '台'}，状态: {asset.status}"
                    )

                    success_count += 1
                except Exception as e:
                    error_records.append(f"第{row_num}行：创建资产失败 - {str(e)}")
                    fail_count += 1
                    logging.error(f'导入固定资产数据失败：第{row_num}行创建资产失败 - {str(e)}')
                    continue

            except Exception as e:
                error_records.append(f"第{row_num}行：数据处理失败 - {str(e)}")
                fail_count += 1
                logging.error(f'导入固定资产数据失败：第{row_num}行数据处理失败 - {str(e)}')
                continue

        # 记录操作日志
        total_count = success_count + fail_count
        if success_count > 0:
            result_status = "部分成功" if fail_count > 0 else "成功"
        else:
            result_status = "失败"

        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='batch_import_export',
            action=f"导入固定资产数据，成功{success_count}条，失败{fail_count}条",
            result=result_status
        )

        # 生成提示信息
        if result_status == "部分成功":
            message = f"导入部分成功：成功导入 {success_count} 条，失败 {fail_count} 条"
            message += f"<br>失败详情：<br>" + "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"
        elif result_status == "成功":
            message = f"导入全部成功：共导入 {success_count} 条资产数据"
        else:
            message = f"导入全部失败：共{len(error_records)}条记录处理失败：<br>" + "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"

        logging.info(message)
        flash(message, 'success' if result_status == "成功" else 'warning' if result_status == "部分成功" else 'danger')
        return redirect(url_for('fixed_asset.index'))

    except Exception as e:
        db.session.rollback()
        detailed_error = f"导入过程出错：{str(e)}"
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='batch_import_export',
            action=f"固定资产数据导入失败: {detailed_error}\n{traceback.format_exc()}",
            result="失败"
        )
        flash(detailed_error, 'danger')
        logging.error(f'导入固定资产数据失败：{detailed_error}')
        return redirect(url_for('fixed_asset.index'))


# 下载导入模板
@fixed_asset_import_export_bp.route('/template', methods=['GET'])
@login_required
@require_permission('fixed_asset.import')
def download_template():
    """生成并下载固定资产数据导入模板"""
    try:
        logging.debug('开始生成固定资产数据导入模板')

        # 获取有效配置数据
        valid_categories = SystemConfig.get_config_value('ASSET_CATEGORIES', '办公设备,家具,交通工具,电子设备,机械设备,其他')
        if isinstance(valid_categories, str):
            valid_categories = [c.strip() for c in valid_categories.split(',') if c.strip()]

        valid_statuses = SystemConfig.get_config_value('ASSET_STATUSES', '在用,闲置,维修中,已报废,已转移,已出售')
        if isinstance(valid_statuses, str):
            valid_statuses = [s.strip() for s in valid_statuses.split(',') if s.strip()]

        valid_sources = ['采购', '捐赠', '调入', '自建', '其他']

        # 模板数据生成
        template_data = {
            "资产编号": ["ZC2026080001", "", ""],
            "资产名称": ["联想笔记本电脑", "办公桌", "叉车"],
            "资产分类": [valid_categories[0] if valid_categories else "办公设备", "", ""],
            "规格型号": ["ThinkPad X1 Carbon", "1.4m标准桌", ""],
            "品牌": ["联想", "震旦", ""],
            "供应商": ["北京联想授权经销商", "", ""],
            "数量": [1, 10, 2],
            "单位": ["台", "张", "辆"],
            "原值": [8999.00, 500.00, 150000.00],
            "净值": [5400.00, 300.00, 90000.00],
            "购置日期": [datetime.now().strftime('%Y-%m-%d'), "", ""],
            "质保到期日": [(datetime.now().replace(year=datetime.now().year + 3)).strftime('%Y-%m-%d'), "", ""],
            "存放位置": ["A栋3楼办公室", "B栋1楼仓库", "C栋停车场"],
            "所属公司": ["", "", ""],
            "使用部门": ["技术部", "行政部", "运营部"],
            "归属部门": ["行政部", "行政部", "运营部"],
            "责任人": ["张三", "李四", "王五"],
            "关联房间": ["A栋101", "", ""],
            "责任人用户": ["张三", "", ""],
            "资产来源": ["采购", "采购", "采购"],
            "状态": ["在用", "在用", "在用"],
            "备注": ["研发用笔记本电脑", "", "仓库搬运叉车"]
        }

        # 创建模板DataFrame
        df = pd.DataFrame(template_data)

        # 添加说明行
        instructions = [
            "可留空，留空则自动生成",
            "*必填项（导入时会校验非空）",
            f"*必填项，必须是：{', '.join(valid_categories)}",
            "文本（可留空）",
            "文本（可留空）",
            "文本（可留空）",
            "*必填项，必须为正整数",
            "文本，默认为'台'（可留空）",
            "非负数（可留空，默认为0）",
            "非负数（可留空，默认为0）",
            "日期格式：YYYY-MM-DD（可留空）",
            "日期格式：YYYY-MM-DD（可留空）",
            "文本（可留空）",
            "文本，所属公司名称（可留空）",
            "文本（可留空，自动匹配公司下部门）",
            "文本（可留空，自动匹配公司下部门）",
            "文本（可留空）",
            "格式：楼栋+房间号，如A栋101（可留空，按名称自动匹配）",
            "在职用户姓名（可留空，按姓名自动匹配）",
            f"可选值: {', '.join(valid_sources)}（可留空，默认'采购'）",
            f"可选值: {', '.join(valid_statuses)}（可留空，默认'在用'）",
            "文本（可留空）"
        ]
        df.loc[-1] = instructions
        df.index = df.index + 1
        df = df.sort_index()

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='固定资产导入模板')
            worksheet = writer.sheets['固定资产导入模板']
            # 设置列宽
            column_widths = [16, 20, 12, 20, 12, 16, 8, 8, 12, 12, 14, 14, 20, 14, 12, 12, 10, 14, 14, 14, 10, 20]
            for i, width in enumerate(column_widths, 1):
                col_letter = chr(64 + i) if i <= 26 else chr(64 + (i - 1) // 26) + chr(65 + (i - 1) % 26)
                worksheet.column_dimensions[col_letter].width = width
            # 标红必填项说明
            for cell in worksheet[1]:
                if "*必填项" in str(cell.value):
                    cell.font = cell.font.copy(color="FF0000")

        output.seek(0)
        filename = f"固定资产导入模板_{datetime.now().strftime('%Y%m%d')}.xlsx"
        logging.debug(f'模板生成成功: {filename}')

        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='batch_import_export',
            action="下载固定资产导入模板",
            result="成功"
        )

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'模板生成失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='batch_import_export',
            action=f"下载模板失败: {str(e)}",
            result="失败"
        )
        flash('模板下载失败，请联系管理员', 'danger')
        return redirect(url_for('fixed_asset.index'))