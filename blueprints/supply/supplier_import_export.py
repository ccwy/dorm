import os
from flask import Blueprint, request, flash, redirect, url_for, send_file
import logging
from utils.db import db
from models.supply.supplier import Supplier
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
from utils.excel_utils import is_empty, export_to_excel, read_excel_rows
import io
from datetime import datetime
import traceback
from io import BytesIO


def normalize_numeric_str(val):
    """规范化数字字符串：处理Excel读取的浮点数、科学计数法、.0后缀等问题。
    纯整数字符串直接返回，避免大数float转换丢失精度（如18位统一社会信用代码）。
    """
    s = str(val).strip()
    if not s:
        return s
    if s.isdigit():
        return s
    if s.startswith('-') and s[1:].isdigit():
        return s
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except (ValueError, OverflowError):
        pass
    return s


# 创建导入导出专用蓝图
supplier_import_export_bp = Blueprint(
    'supplier_import_export',
    __name__,
    url_prefix='/supplier/import-export',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/supplier/import-export/static'
)


# 导出供应商数据
@supplier_import_export_bp.route('/export', methods=['GET'])
@login_required
@require_permission('supplier.export')
def export():
    """导出供应商数据为Excel"""
    try:
        logging.debug('开始执行供应商数据导出')

        # 获取供应商数据
        suppliers = Supplier.query.order_by(Supplier.id).all()
        logging.debug(f'查询到{len(suppliers)}条供应商数据')

        if not suppliers:
            logging.info('没有可导出的供应商数据')
            flash('没有可导出的供应商数据', 'info')
            return redirect(url_for('supplier.index'))

        # 准备导出数据
        data = []
        for s in suppliers:
            try:
                data.append({
                    '供应商ID': s.id or '',
                    '供应商名称': s.name or '',
                    '统一社会信用代码': s.unified_social_credit_code or '',
                    '法定代表人': s.legal_representative or '',
                    '联系人': s.contact_person or '',
                    '联系电话': s.contact_phone or '',
                    '邮箱': s.email or '',
                    '地址': s.address or '',
                    '状态': s.status or '启用',
                    '税率': float(s.tax_rate) if s.tax_rate else '',
                    '收款方式': s.payment_method or '',
                    '银行账号': s.bank_account or '',
                    '开户行': s.bank_name or '',
                    '收款银行': s.receiving_bank or '',
                    '开户名称': s.account_name or '',
                    '收款账号': s.payment_account or '',
                    '发票类型': s.invoice_type or '',
                    '备注': s.remark or '',
                    '创建时间': s.created_at.strftime('%Y-%m-%d %H:%M') if s.created_at else '',
                    '更新时间': s.updated_at.strftime('%Y-%m-%d %H:%M') if s.updated_at else '',
                })
            except Exception as e:
                logging.error(f'处理供应商ID={s.id}时出错: {str(e)}', exc_info=True)
                raise

        logging.debug(f'数据准备完成，共{len(data)}条记录')

        # 生成Excel
        export_headers = ['供应商ID', '供应商名称', '统一社会信用代码', '法定代表人', '联系人', '联系电话',
                          '邮箱', '地址', '状态', '税率', '收款方式', '银行账号', '开户行', '收款银行',
                          '开户名称', '收款账号', '发票类型', '备注', '创建时间', '更新时间']
        export_rows = [[item.get(h, '') for h in export_headers] for item in data]
        output = io.BytesIO()
        export_to_excel([{'name': '供应商数据', 'headers': export_headers, 'rows': export_rows}], output)

        output.seek(0)
        filename = f"供应商数据导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        logging.debug(f'Excel文件生成成功，文件名: {filename}')

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='batch_import_export',
            action=f"导出供应商数据，共 {len(suppliers)} 条记录",
            result="成功"
        )
        logging.info(f'用户{current_user.id}成功导出供应商数据')

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'导出供应商数据失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='batch_import_export',
            action=f"尝试导出供应商数据失败: {str(e)}",
            result="失败"
        )
        flash('导出失败，请联系管理员', 'danger')
        return redirect(url_for('supplier.index'))


# 导入供应商数据
@supplier_import_export_bp.route('/import', methods=['POST'])
@login_required
@require_permission('supplier.import')
def import_suppliers():
    """批量导入供应商数据"""
    try:
        logging.debug('开始批量导入供应商数据')
        # 验证文件是否存在
        if 'file' not in request.files:
            flash('请选择要导入的文件', 'danger')
            logging.error('导入供应商数据失败：未选择文件')
            return redirect(url_for('supplier.index'))

        file = request.files['file']
        if file.filename == '':
            flash('请选择要导入的文件', 'danger')
            logging.error('导入供应商数据失败：未选择文件')
            return redirect(url_for('supplier.index'))

        # 文件类型验证
        allowed_extensions = {'xlsx', 'xls'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            flash(f'请上传Excel格式的文件（.xlsx 或 .xls），当前文件类型：.{file_ext}', 'danger')
            logging.error(f'导入供应商数据失败：文件类型无效，当前文件类型：.{file_ext}')
            return redirect(url_for('supplier.index'))

        # 限制文件大小（10MB）
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > 10 * 1024 * 1024:
            flash('文件大小超过限制（最大10MB）', 'danger')
            logging.error('导入供应商数据失败：文件大小超过限制（最大10MB）')
            return redirect(url_for('supplier.index'))

        try:
            file_content = file.read()
            file_bytes = BytesIO(file_content)
            file_bytes.seek(0)
            rows = read_excel_rows(file_bytes, sheet_name=0, header_row=1)
        except Exception as e:
            detailed_error = f"文件解析失败：{str(e)}"
            flash(detailed_error, 'danger')
            logging.error(f'导入供应商数据失败：文件解析失败 - {detailed_error}')
            return redirect(url_for('supplier.index'))

        # 白名单模式：只识别必填列和可选列，其余列全部自动忽略
        # 必填列（缺失时报错）
        required_columns = ['供应商名称']
        # 可选列（缺失时不报错）
        optional_columns = [
            '统一社会信用代码', '法定代表人', '联系人', '联系电话',
            '邮箱', '地址', '状态', '税率',
            '收款方式', '银行账号', '开户行', '收款银行', '开户名称', '收款账号', '发票类型',
            '备注'
        ]
        # 列名别名映射：将Excel中可能出现的列名映射到标准列名
        column_alias_map = {}
        # 所有可能需要识别的标准列名
        all_known_columns = set(required_columns) | set(optional_columns)

        # 获取实际列名
        excel_columns = list(rows[0].keys()) if rows else []

        # 别名列重命名为标准名（仅保留白名单列）
        rename_map = {}
        for col in excel_columns:
            if col in all_known_columns:
                rename_map[col] = col
                continue
            for standard_name, aliases in column_alias_map.items():
                if col in aliases:
                    rename_map[col] = standard_name
                    break

        # 识别未匹配的列
        ignored_columns = [col for col in excel_columns if col not in rename_map]
        if ignored_columns:
            logging.info(f'导入供应商数据：自动忽略未识别列 {ignored_columns}')

        # 仅保留白名单列
        rows = [{rename_map[k]: v for k, v in row.items() if k in rename_map} for row in rows]

        # 检查必填列缺失
        missing_columns = [col for col in required_columns if col not in rename_map.values()]
        if missing_columns:
            flash(f'导入失败：文件缺少必要的列 - {", ".join(missing_columns)}', 'danger')
            logging.error(f'导入供应商数据失败：文件缺少必要的列 - {", ".join(missing_columns)}')
            return redirect(url_for('supplier.index'))

        # 是否覆盖已有数据
        override = request.form.get('override', '') == '1'

        # 准备导入数据列表
        success_count = 0
        fail_count = 0
        error_records = []

        for index, row in enumerate(rows):
            try:
                row_num = index + 2

                # 供应商名称（必填）
                name_val = row.get('供应商名称')
                if is_empty(name_val):
                    error_records.append(f"第{row_num}行：供应商名称不能为空")
                    fail_count += 1
                    continue
                name = str(name_val).strip()

                # 统一社会信用代码（可选）
                unified_social_credit_code_val = row.get('统一社会信用代码')
                unified_social_credit_code = normalize_numeric_str(unified_social_credit_code_val) if not is_empty(unified_social_credit_code_val) else None

                # 法定代表人（可选）
                legal_representative_val = row.get('法定代表人')
                legal_representative = str(legal_representative_val).strip() if not is_empty(legal_representative_val) else None

                # 联系人（可选）
                contact_person_val = row.get('联系人')
                contact_person = str(contact_person_val).strip() if not is_empty(contact_person_val) else None

                # 联系电话（可选）
                contact_phone_val = row.get('联系电话')
                contact_phone = normalize_numeric_str(contact_phone_val) if not is_empty(contact_phone_val) else None

                # 邮箱（可选）
                email_val = row.get('邮箱')
                email = str(email_val).strip() if not is_empty(email_val) else None

                # 地址（可选）
                address_val = row.get('地址')
                address = str(address_val).strip() if not is_empty(address_val) else None

                # 状态（可选，默认"启用"）
                status_val = row.get('状态')
                status = str(status_val).strip() if not is_empty(status_val) else '启用'
                if status not in ['启用', '停用']:
                    status = '启用'

                # 税率（可选，数值）
                tax_rate_val = row.get('税率')
                tax_rate = None
                if not is_empty(tax_rate_val):
                    try:
                        tax_rate = float(str(tax_rate_val).strip())
                    except (ValueError, TypeError):
                        error_records.append(f'第{row_num}行：税率格式无效，已忽略')
                        tax_rate = None

                # 备注（可选）
                remark_val = row.get('备注')
                remark = str(remark_val).strip() if not is_empty(remark_val) else None

                # 收款方式（可选）
                payment_method_val = row.get('收款方式')
                payment_method = str(payment_method_val).strip() if not is_empty(payment_method_val) else None

                # 银行账号（可选）
                bank_account_val = row.get('银行账号')
                bank_account = normalize_numeric_str(bank_account_val) if not is_empty(bank_account_val) else None

                # 开户行（可选）
                bank_name_val = row.get('开户行')
                bank_name = str(bank_name_val).strip() if not is_empty(bank_name_val) else None

                # 收款银行（可选）
                receiving_bank_val = row.get('收款银行')
                receiving_bank = str(receiving_bank_val).strip() if not is_empty(receiving_bank_val) else None

                # 开户名称（可选）
                account_name_val = row.get('开户名称')
                account_name = str(account_name_val).strip() if not is_empty(account_name_val) else None

                # 收款账号（可选）
                payment_account_val = row.get('收款账号')
                payment_account = normalize_numeric_str(payment_account_val) if not is_empty(payment_account_val) else None

                # 发票类型（可选）
                invoice_type_val = row.get('发票类型')
                invoice_type = str(invoice_type_val).strip() if not is_empty(invoice_type_val) else None

                # 检查名称是否重复
                existing = Supplier.query.filter_by(name=name).first()
                if existing:
                    if override:
                        # 覆盖更新
                        existing.unified_social_credit_code = unified_social_credit_code or existing.unified_social_credit_code
                        existing.legal_representative = legal_representative or existing.legal_representative
                        existing.contact_person = contact_person or existing.contact_person
                        existing.contact_phone = contact_phone or existing.contact_phone
                        existing.email = email or existing.email
                        existing.address = address or existing.address
                        existing.status = status
                        existing.tax_rate = tax_rate if tax_rate is not None else existing.tax_rate
                        existing.remark = remark or existing.remark
                        existing.payment_method = payment_method or existing.payment_method
                        existing.bank_account = bank_account or existing.bank_account
                        existing.bank_name = bank_name or existing.bank_name
                        existing.receiving_bank = receiving_bank or existing.receiving_bank
                        existing.account_name = account_name or existing.account_name
                        existing.payment_account = payment_account or existing.payment_account
                        existing.invoice_type = invoice_type or existing.invoice_type
                        existing.handler_user_id = current_user.id
                        success_count += 1
                        continue
                    else:
                        error_records.append(f'第{row_num}行：供应商名称"{name}"已存在')
                        fail_count += 1
                        continue

                # 创建供应商
                Supplier.create(
                    name=name,
                    unified_social_credit_code=unified_social_credit_code,
                    legal_representative=legal_representative,
                    contact_person=contact_person,
                    contact_phone=contact_phone,
                    email=email,
                    address=address,
                    status=status,
                    handler_user_id=current_user.id,
                    tax_rate=tax_rate,
                    remark=remark,
                    payment_method=payment_method,
                    bank_account=bank_account,
                    bank_name=bank_name,
                    receiving_bank=receiving_bank,
                    account_name=account_name,
                    payment_account=payment_account,
                    invoice_type=invoice_type,
                    operator_user_id=current_user.id
                )
                success_count += 1

            except Exception as e:
                error_records.append(f"第{row_num}行：创建供应商失败 - {str(e)}")
                fail_count += 1
                logging.error(f'导入供应商数据失败：第{row_num}行创建供应商失败 - {str(e)}')
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
            module='supplier',
            operation_type='batch_import_export',
            action=f"导入供应商数据，成功{success_count}条，失败{fail_count}条",
            result=result_status
        )

        # 生成提示信息
        if result_status == "部分成功":
            message = f"导入部分成功：成功导入 {success_count} 条，失败 {fail_count} 条"
            message += f"<br>失败详情：<br>" + "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"
        elif result_status == "成功":
            message = f"导入全部成功：共导入 {success_count} 条供应商数据"
        else:
            message = f"导入全部失败：共{len(error_records)}条记录处理失败：<br>" + "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"

        logging.info(message)
        flash(message, 'success' if result_status == "成功" else 'warning' if result_status == "部分成功" else 'danger')
        return redirect(url_for('supplier.index'))

    except Exception as e:
        db.session.rollback()
        detailed_error = f"导入过程出错：{str(e)}"
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='batch_import_export',
            action=f"供应商数据导入失败: {detailed_error}\n{traceback.format_exc()}",
            result="失败"
        )
        flash(detailed_error, 'danger')
        logging.error(f'导入供应商数据失败：{detailed_error}')
        return redirect(url_for('supplier.index'))


# 批量更新供应商数据
@supplier_import_export_bp.route('/batch_update', methods=['POST'])
@login_required
@require_permission('supplier.edit')
def batch_update():
    """批量更新供应商数据（基于供应商ID）"""
    try:
        logging.debug('开始批量更新供应商数据')
        if 'file' not in request.files:
            flash('请选择要导入的文件', 'danger')
            logging.error('批量更新供应商数据失败：未选择文件')
            return redirect(url_for('supplier.index'))

        file = request.files['file']
        if file.filename == '':
            flash('请选择要导入的文件', 'danger')
            logging.error('批量更新供应商数据失败：未选择文件')
            return redirect(url_for('supplier.index'))

        # 文件类型验证
        allowed_extensions = {'xlsx', 'xls'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            flash(f'请上传Excel格式的文件（.xlsx 或 .xls），当前文件类型：.{file_ext}', 'danger')
            logging.error(f'批量更新供应商数据失败：文件类型无效，当前文件类型：.{file_ext}')
            return redirect(url_for('supplier.index'))

        try:
            file_content = file.read()
            file_bytes = BytesIO(file_content)
            file_bytes.seek(0)
            rows = read_excel_rows(file_bytes, sheet_name=0, header_row=1)
        except Exception as e:
            detailed_error = f"文件解析失败：{str(e)}"
            flash(detailed_error, 'danger')
            logging.error(f'批量更新供应商数据失败：文件解析失败 - {detailed_error}')
            return redirect(url_for('supplier.index'))

        # 白名单模式：只识别必填列和可选列，其余列全部自动忽略
        # 必填列（缺失时报错）
        required_columns = ['供应商ID']
        # 可选列（缺失时不报错）
        optional_columns = [
            '供应商名称', '统一社会信用代码', '法定代表人', '联系人', '联系电话',
            '邮箱', '地址', '状态', '税率',
            '收款方式', '银行账号', '开户行', '收款银行', '开户名称', '收款账号', '发票类型',
            '备注'
        ]
        # 列名别名映射：将Excel中可能出现的列名映射到标准列名
        column_alias_map = {
            '供应商ID': ['供应商ID（批量更新必填）', '供应商ID(批量更新必填)', '供应商ID', '供应商id', 'ID', 'id'],
        }
        # 所有可能需要识别的标准列名
        all_known_columns = set(required_columns) | set(optional_columns)

        # 获取实际列名
        excel_columns = list(rows[0].keys()) if rows else []

        # 构建列名映射：只保留白名单中的列，其余自动忽略
        column_mapping = {}
        ignored_columns = []
        for col in excel_columns:
            # 先检查是否直接匹配标准列名
            if col in all_known_columns:
                column_mapping[col] = col  # 标准列名保持不变
                continue
            # 再检查是否匹配某个标准列名的别名
            matched = False
            for standard_name, aliases in column_alias_map.items():
                if col in aliases:
                    column_mapping[col] = standard_name
                    matched = True
                    break
            if not matched:
                ignored_columns.append(col)

        if ignored_columns:
            logging.info(f'批量更新供应商数据：自动忽略未识别列 {ignored_columns}')

        # 重命名列以统一标准，并只保留白名单中的列
        rows = [{column_mapping[k]: v for k, v in row.items() if k in column_mapping} for row in rows]

        missing_columns = [col for col in required_columns if col not in column_mapping.values()]
        if missing_columns:
            flash(f'导入失败：文件缺少必要的列 - {", ".join(missing_columns)}', 'danger')
            logging.error(f'批量更新供应商数据失败：文件缺少必要的列 - {", ".join(missing_columns)}')
            return redirect(url_for('supplier.index'))

        # 预处理数据
        success_count = 0
        error_list = []
        processed_ids = {}  # 缓存已处理的ID，提高效率

        for index, row in enumerate(rows):
            row_num = index + 2
            try:
                # 提取供应商ID（处理Excel可能将数字读取为float的问题）
                raw_id = row.get('供应商ID')
                if is_empty(raw_id):
                    record_id_str = ''
                elif isinstance(raw_id, float):
                    record_id_str = str(int(raw_id))
                else:
                    record_id_str = str(raw_id).strip()
                if not record_id_str:
                    error_list.append(f"第{row_num}行：供应商ID不能为空（批量更新必须提供）")
                    continue

                # 验证ID格式
                try:
                    record_id = int(record_id_str)
                except ValueError:
                    error_list.append(f"第{row_num}行：供应商ID必须是数字，当前值：{record_id_str}")
                    continue

                # 通过ID查询供应商（使用缓存）
                cache_key = f"id_{record_id}"
                if cache_key not in processed_ids:
                    supplier = Supplier.query.get(record_id)
                    processed_ids[cache_key] = supplier
                supplier = processed_ids[cache_key]

                # 验证供应商存在性
                if not supplier:
                    error_list.append(f"第{row_num}行：供应商ID {record_id} 不存在")
                    continue

                # 处理供应商名称（非空时才更新）
                name_val = row.get('供应商名称')
                if not is_empty(name_val):
                    supplier.name = str(name_val).strip()

                # 处理统一社会信用代码
                credit_code_val = row.get('统一社会信用代码')
                if not is_empty(credit_code_val):
                    supplier.unified_social_credit_code = normalize_numeric_str(credit_code_val)

                # 处理法定代表人
                legal_rep_val = row.get('法定代表人')
                if not is_empty(legal_rep_val):
                    supplier.legal_representative = str(legal_rep_val).strip()

                # 处理联系人
                contact_person_val = row.get('联系人')
                if not is_empty(contact_person_val):
                    supplier.contact_person = str(contact_person_val).strip()

                # 处理联系电话
                contact_phone_val = row.get('联系电话')
                if not is_empty(contact_phone_val):
                    supplier.contact_phone = normalize_numeric_str(contact_phone_val)

                # 处理邮箱
                email_val = row.get('邮箱')
                if not is_empty(email_val):
                    supplier.email = str(email_val).strip()

                # 处理地址
                address_val = row.get('地址')
                if not is_empty(address_val):
                    supplier.address = str(address_val).strip()

                # 处理状态（枚举校验：仅启用/停用）
                status_val = row.get('状态')
                if not is_empty(status_val):
                    status_text = str(status_val).strip()
                    if status_text in ['启用', '停用']:
                        supplier.status = status_text
                    else:
                        logging.warning(f'批量更新供应商ID {record_id} 状态值无效：{status_text}，默认设为启用')
                        supplier.status = '启用'

                # 处理税率（数值校验）
                tax_rate_val = row.get('税率')
                if not is_empty(tax_rate_val):
                    try:
                        supplier.tax_rate = float(str(tax_rate_val).strip())
                    except (ValueError, TypeError):
                        logging.warning(f'批量更新供应商ID {record_id} 税率格式无效：{tax_rate_val}，已忽略')

                # 处理收款方式
                payment_method_val = row.get('收款方式')
                if not is_empty(payment_method_val):
                    supplier.payment_method = str(payment_method_val).strip()

                # 处理银行账号
                bank_account_val = row.get('银行账号')
                if not is_empty(bank_account_val):
                    supplier.bank_account = normalize_numeric_str(bank_account_val)

                # 处理开户行
                bank_name_val = row.get('开户行')
                if not is_empty(bank_name_val):
                    supplier.bank_name = str(bank_name_val).strip()

                # 处理收款银行
                receiving_bank_val = row.get('收款银行')
                if not is_empty(receiving_bank_val):
                    supplier.receiving_bank = str(receiving_bank_val).strip()

                # 处理开户名称
                account_name_val = row.get('开户名称')
                if not is_empty(account_name_val):
                    supplier.account_name = str(account_name_val).strip()

                # 处理收款账号
                payment_account_val = row.get('收款账号')
                if not is_empty(payment_account_val):
                    supplier.payment_account = normalize_numeric_str(payment_account_val)

                # 处理发票类型
                invoice_type_val = row.get('发票类型')
                if not is_empty(invoice_type_val):
                    supplier.invoice_type = str(invoice_type_val).strip()

                # 处理备注
                remark_val = row.get('备注')
                if not is_empty(remark_val):
                    supplier.remark = str(remark_val).strip()

                supplier.handler_user_id = current_user.id
                success_count += 1

            except Exception as e:
                error_list.append(f"第{row_num}行：数据处理失败 - {str(e)}")
                logging.error(f'批量更新供应商数据失败：第{row_num}行数据处理失败 - {str(e)}')
                continue

        # 如果有错误，回滚并返回
        if error_list:
            db.session.rollback()
            message = f"数据验证失败：共{len(error_list)}条错误<br>" + "<br>".join(error_list[:5])
            if len(error_list) > 5:
                message += f"<br>... 还有 {len(error_list)-5} 条错误"
            flash(message, 'danger')
            logging.error(f'批量更新供应商数据失败：数据验证失败，共{len(error_list)}条错误')
            return redirect(url_for('supplier.index'))

        # 提交事务
        db.session.commit()

        logging.info(f'批量更新供应商数据成功，共更新{success_count}条记录，操作人：{current_user.id}')
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='batch_update',
            action=f"批量更新供应商数据，共更新{success_count}条记录",
            result="成功"
        )
        flash(f"批量更新完成，成功更新{success_count}条记录", 'success')
        return redirect(url_for('supplier.index'))

    except Exception as e:
        db.session.rollback()
        detailed_error = f"批量更新过程出错：{str(e)}"
        logging.error(f'批量更新供应商数据失败：{detailed_error}，操作人：{current_user.id}\n{traceback.format_exc()}')
        flash(detailed_error, 'danger')
        return redirect(url_for('supplier.index'))


# 下载导入模板
@supplier_import_export_bp.route('/template', methods=['GET'])
@login_required
@require_permission('supplier.import')
def download_template():
    """生成并下载供应商数据导入模板"""
    try:
        logging.debug('开始生成供应商数据导入模板')

        # 模板数据生成
        template_headers = ['供应商ID（批量更新必填）', '供应商名称', '统一社会信用代码', '法定代表人',
                            '联系人', '联系电话', '邮箱', '地址', '状态', '税率', '收款方式',
                            '银行账号', '开户行', '收款银行', '开户名称', '收款账号', '发票类型', '备注']
        template_rows = [
            ["", "示例供应商A", "91110000MA01ABCD1X", "张三", "张三", "13800138001", "zhangsan@example.com",
             "北京市朝阳区", "启用", 13, "银行转账", "6222000000001", "中国工商银行北京分行", "工行",
             "示例供应商A", "", "增值税专用发票", "主要供应商"],
            ["", "示例供应商B", "91310000MA02EFGH2Y", "李四", "李四", "13800138002", "lisi@example.com",
             "上海市浦东新区", "启用", 6, "银行转账", "6222000000002", "中国建设银行上海分行", "建行",
             "示例供应商B", "", "增值税普通发票", "备选供应商"],
            ["", "示例供应商C", "91440000MA03IJKL3Z", "王五", "王五", "13800138003", "wangwu@example.com",
             "广州市天河区", "停用", 9, "", "", "", "", "", "", "", ""],
        ]

        output = io.BytesIO()
        export_to_excel([{'name': '供应商数据', 'headers': template_headers, 'rows': template_rows}], output)

        output.seek(0)
        filename = "供应商数据导入模板.xlsx"

        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='batch_import_export',
            action="下载供应商数据导入模板",
            result="成功"
        )

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'生成供应商数据导入模板失败: {str(e)}', exc_info=True)
        flash('生成模板失败，请联系管理员', 'danger')
        return redirect(url_for('supplier.index'))