import os
from flask import Blueprint, request, flash, redirect, url_for, send_file
import logging
from utils.db import db
from models.contract.contract import Contract
from models.contract.contract_operation_record import ContractOperationRecord
from models.supply.supplier import Supplier
from models.supply.storage_location import StorageLocation
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.log import log_operation
from utils.lazy_imports import pd  # 延迟导入pandas，避免启动时加载重型库
import io
from datetime import datetime
import traceback
from io import BytesIO

# 创建导入导出专用蓝图
contract_import_export_bp = Blueprint(
    'contract_import_export',
    __name__,
    url_prefix='/contract/import-export',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/contract/import-export/static'
)


# 导出合同数据
@contract_import_export_bp.route('/export', methods=['POST'])
@login_required
@require_permission('contract.export')
def export():
    """导出合同数据为Excel"""
    try:
        logging.debug('开始执行合同数据导出')

        # 获取合同数据
        contracts = Contract.query.order_by(Contract.id).all()
        logging.debug(f'查询到{len(contracts)}条合同数据')

        if not contracts:
            logging.info('没有可导出的合同数据')
            flash('没有可导出的合同数据', 'info')
            return redirect(url_for('contract.index'))

        # 准备导出数据
        data = []
        for c in contracts:
            try:
                data.append({
                    'ID': c.id,
                    '合同编号': c.contract_number or '',
                    '合同名称': c.contract_name or '',
                    '甲方名称': c.party_a_name if c.party_a else '',
                    '甲方联系人': c.party_a_contact_person or '',
                    '甲方联系电话': c.party_a_contact_phone or '',
                    '甲方地址': c.party_a_address or '',
                    '甲方统一社会信用代码': c.party_a_credit_code or '',
                    '甲方法定代表人': c.party_a_legal_representative or '',
                    '乙方名称': c.party_b_name if c.party_b else '',
                    '乙方联系人': c.party_b_contact_person or '',
                    '乙方联系电话': c.party_b_contact_phone or '',
                    '乙方地址': c.party_b_address or '',
                    '乙方统一社会信用代码': c.party_b_credit_code or '',
                    '乙方法定代表人': c.party_b_legal_representative or '',
                    '乙方收款方式': c.party_b_payment_method or '',
                    '乙方银行账号': c.party_b_bank_account or '',
                    '乙方开户行': c.party_b_bank_name or '',
                    '乙方收款银行': c.party_b_receiving_bank or '',
                    '乙方开户名称': c.party_b_account_name or '',
                    '乙方收款账号': c.party_b_payment_account or '',
                    '乙方发票类型': c.party_b_invoice_type or '',
                    '合同类型': c.contract_type or '',
                    '合同分类': c.contract_category or '',
                    '合同金额': float(c.contract_amount) if c.contract_amount is not None else '',
                    '币种': c.currency or 'CNY',
                    '税率(%)': float(c.tax_rate) if c.tax_rate is not None else '',
                    '税额': float(c.tax_amount) if c.tax_amount is not None else '',
                    '付款方式': c.payment_method or '',
                    '付款要求': c.payment_requirements or '',
                    '固定金额': float(c.fixed_amount) if c.fixed_amount else '',
                    '付款轮次': c.payment_rounds or '',
                    '对账日': c.reconciliation_day or '',
                    '付款截止日': c.payment_deadline_day or '',
                    '签订日期': c.signing_date.strftime('%Y-%m-%d') if c.signing_date else '',
                    '开始日期': c.start_date.strftime('%Y-%m-%d') if c.start_date else '',
                    '结束日期': c.end_date.strftime('%Y-%m-%d') if c.end_date else '',
                    '合同状态': c.status or '待生效',
                    '经手人': c.handler_name if c.handler_user_id else '',
                    '归属部门': c.department_name if c.department_id else '',
                    '存放位置': c.storage_location_name if c.storage_location else '',
                    '备注': c.remark or '',
                    '创建时间': c.created_at.strftime('%Y-%m-%d %H:%M') if c.created_at else '',
                    '更新时间': c.updated_at.strftime('%Y-%m-%d %H:%M') if c.updated_at else '',
                })
            except Exception as e:
                logging.error(f'处理合同ID={c.id}时出错: {str(e)}', exc_info=True)
                raise

        logging.debug(f'数据准备完成，共{len(data)}条记录')

        # 生成Excel
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='合同数据')

        output.seek(0)
        filename = f"合同数据导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        logging.debug(f'Excel文件生成成功，文件名: {filename}')

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='batch_import_export',
            action=f"导出合同数据，共 {len(contracts)} 条记录",
            result="成功"
        )
        logging.info(f'用户{current_user.id}成功导出合同数据')

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'导出合同数据失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='batch_import_export',
            action=f"尝试导出合同数据失败: {str(e)}",
            result="失败"
        )
        flash('导出失败，请联系管理员', 'danger')
        return redirect(url_for('contract.index'))


# 导入合同数据
@contract_import_export_bp.route('/import', methods=['POST'])
@login_required
@require_permission('contract.import')
def import_contracts():
    """批量导入合同数据"""
    try:
        logging.debug('开始批量导入合同数据')
        # 验证文件是否存在
        if 'file' not in request.files:
            flash('请选择要导入的文件', 'danger')
            logging.error('导入合同数据失败：未选择文件')
            return redirect(url_for('contract.index'))

        file = request.files['file']
        if file.filename == '':
            flash('请选择要导入的文件', 'danger')
            logging.error('导入合同数据失败：未选择文件')
            return redirect(url_for('contract.index'))

        # 文件类型验证
        allowed_extensions = {'xlsx', 'xls'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            flash(f'请上传Excel格式的文件（.xlsx 或 .xls），当前文件类型：.{file_ext}', 'danger')
            logging.error(f'导入合同数据失败：文件类型无效，当前文件类型：.{file_ext}')
            return redirect(url_for('contract.index'))

        # 限制文件大小（10MB）
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > 10 * 1024 * 1024:
            flash('文件大小超过限制（最大10MB）', 'danger')
            logging.error('导入合同数据失败：文件大小超过限制（最大10MB）')
            return redirect(url_for('contract.index'))

        try:
            file_content = file.read()
            file_bytes = BytesIO(file_content)
            file_bytes.seek(0)
            df = pd.read_excel(file_bytes)
        except Exception as e:
            detailed_error = f"文件解析失败：{str(e)}"
            flash(detailed_error, 'danger')
            logging.error(f'导入合同数据失败：文件解析失败 - {detailed_error}')
            return redirect(url_for('contract.index'))

        # 白名单模式：只识别必填列和可选列，其余列全部自动忽略
        # 必填列（缺失时报错）
        required_columns = ['合同名称']
        # 可选列（缺失时不报错）
        optional_columns = [
            'ID', '合同编号', '甲方名称', '甲方联系人', '甲方联系电话', '甲方地址',
            '甲方统一社会信用代码', '甲方法定代表人', '乙方名称', '乙方联系人',
            '乙方联系电话', '乙方地址', '乙方统一社会信用代码', '乙方法定代表人',
            '乙方收款方式', '乙方银行账号', '乙方开户行', '乙方收款银行',
            '乙方开户名称', '乙方收款账号', '乙方发票类型',
            '合同类型', '合同分类', '合同金额', '币种', '税率(%)', '税率',
            '税额', '付款方式', '付款要求', '固定金额', '付款轮次',
            '对账日', '付款截止日', '签订日期', '开始日期', '结束日期', '合同状态', '经手人',
            '归属部门', '备注', '存放位置'
        ]
        # 列名别名映射：将Excel中可能出现的列名映射到标准列名
        column_alias_map = {}
        # 所有可能需要识别的标准列名
        all_known_columns = set(required_columns) | set(optional_columns)

        # 别名列重命名为标准名
        rename_map = {}
        for col in df.columns:
            if col in all_known_columns:
                continue  # 已经是标准名
            for standard_name, aliases in column_alias_map.items():
                if col in aliases:
                    rename_map[col] = standard_name
                    break

        if rename_map:
            df = df.rename(columns=rename_map)

        # 识别未匹配的列
        ignored_columns = [col for col in df.columns if col not in all_known_columns]
        if ignored_columns:
            logging.info(f'导入合同数据：自动忽略未识别列 {ignored_columns}')

        # 仅保留白名单列
        whitelist_columns = [col for col in df.columns if col in all_known_columns]
        df = df[whitelist_columns]

        # 检查必填列缺失
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            flash(f'导入失败：文件缺少必要的列 - {", ".join(missing_columns)}', 'danger')
            logging.error(f'导入合同数据失败：文件缺少必要的列 - {", ".join(missing_columns)}')
            return redirect(url_for('contract.index'))

        # 是否覆盖已有数据
        override = request.form.get('override', '') == '1'

        # 准备导入数据列表
        success_count = 0
        fail_count = 0
        error_records = []

        for index, row in df.iterrows():
            try:
                row_num = index + 2

                # 合同名称（必填）
                contract_name_val = row.get('合同名称')
                if pd.isna(contract_name_val) or str(contract_name_val).strip() == '':
                    error_records.append(f"第{row_num}行：合同名称不能为空")
                    fail_count += 1
                    continue
                contract_name = str(contract_name_val).strip()

                # ID（可选，用于通过ID匹配覆盖已有合同）
                contract_id_val = row.get('ID')
                contract_id = None
                if pd.notna(contract_id_val) and str(contract_id_val).strip():
                    try:
                        contract_id = int(float(str(contract_id_val).strip()))
                    except (ValueError, TypeError):
                        contract_id = None

                # 合同编号（可选）
                contract_number_val = row.get('合同编号')
                contract_number = str(contract_number_val).strip() if pd.notna(contract_number_val) and str(contract_number_val).strip() else None

                # 甲方名称（可选，通过名称匹配Supplier）
                party_a_id = None
                party_a_name_val = row.get('甲方名称')
                if pd.notna(party_a_name_val) and str(party_a_name_val).strip():
                    party_a_name = str(party_a_name_val).strip()
                    party_a_supplier = Supplier.query.filter_by(name=party_a_name).first()
                    if party_a_supplier:
                        party_a_id = party_a_supplier.id
                    else:
                        party_a_id = None

                # 甲方详情字段（可选，直接从Excel读取赋值到Contract模型）
                party_a_contact_person_val = row.get('甲方联系人')
                party_a_contact_person = str(party_a_contact_person_val).strip() if pd.notna(party_a_contact_person_val) and str(party_a_contact_person_val).strip() else None

                party_a_contact_phone_val = row.get('甲方联系电话')
                party_a_contact_phone = str(party_a_contact_phone_val).strip() if pd.notna(party_a_contact_phone_val) and str(party_a_contact_phone_val).strip() else None

                party_a_address_val = row.get('甲方地址')
                party_a_address = str(party_a_address_val).strip() if pd.notna(party_a_address_val) and str(party_a_address_val).strip() else None

                party_a_credit_code_val = row.get('甲方统一社会信用代码')
                party_a_credit_code = str(party_a_credit_code_val).strip() if pd.notna(party_a_credit_code_val) and str(party_a_credit_code_val).strip() else None

                party_a_legal_representative_val = row.get('甲方法定代表人')
                party_a_legal_representative = str(party_a_legal_representative_val).strip() if pd.notna(party_a_legal_representative_val) and str(party_a_legal_representative_val).strip() else None

                # 乙方名称（可选，通过名称匹配Supplier）
                party_b_id = None
                party_b_name_val = row.get('乙方名称')
                if pd.notna(party_b_name_val) and str(party_b_name_val).strip():
                    party_b_name = str(party_b_name_val).strip()
                    party_b_supplier = Supplier.query.filter_by(name=party_b_name).first()
                    if party_b_supplier:
                        party_b_id = party_b_supplier.id
                    else:
                        party_b_id = None

                # 乙方详情字段（可选，直接从Excel读取赋值到Contract模型）
                party_b_contact_person_val = row.get('乙方联系人')
                party_b_contact_person = str(party_b_contact_person_val).strip() if pd.notna(party_b_contact_person_val) and str(party_b_contact_person_val).strip() else None

                party_b_contact_phone_val = row.get('乙方联系电话')
                party_b_contact_phone = str(party_b_contact_phone_val).strip() if pd.notna(party_b_contact_phone_val) and str(party_b_contact_phone_val).strip() else None

                party_b_address_val = row.get('乙方地址')
                party_b_address = str(party_b_address_val).strip() if pd.notna(party_b_address_val) and str(party_b_address_val).strip() else None

                party_b_credit_code_val = row.get('乙方统一社会信用代码')
                party_b_credit_code = str(party_b_credit_code_val).strip() if pd.notna(party_b_credit_code_val) and str(party_b_credit_code_val).strip() else None

                party_b_legal_representative_val = row.get('乙方法定代表人')
                party_b_legal_representative = str(party_b_legal_representative_val).strip() if pd.notna(party_b_legal_representative_val) and str(party_b_legal_representative_val).strip() else None

                # 乙方扩展字段（可选）
                party_b_payment_method_val = row.get('乙方收款方式')
                party_b_payment_method = str(party_b_payment_method_val).strip() if pd.notna(party_b_payment_method_val) and str(party_b_payment_method_val).strip() else None

                party_b_bank_account_val = row.get('乙方银行账号')
                party_b_bank_account = str(party_b_bank_account_val).strip() if pd.notna(party_b_bank_account_val) and str(party_b_bank_account_val).strip() else None

                party_b_bank_name_val = row.get('乙方开户行')
                party_b_bank_name = str(party_b_bank_name_val).strip() if pd.notna(party_b_bank_name_val) and str(party_b_bank_name_val).strip() else None

                party_b_receiving_bank_val = row.get('乙方收款银行')
                party_b_receiving_bank = str(party_b_receiving_bank_val).strip() if pd.notna(party_b_receiving_bank_val) and str(party_b_receiving_bank_val).strip() else None

                party_b_account_name_val = row.get('乙方开户名称')
                party_b_account_name = str(party_b_account_name_val).strip() if pd.notna(party_b_account_name_val) and str(party_b_account_name_val).strip() else None

                party_b_payment_account_val = row.get('乙方收款账号')
                party_b_payment_account = str(party_b_payment_account_val).strip() if pd.notna(party_b_payment_account_val) and str(party_b_payment_account_val).strip() else None

                party_b_invoice_type_val = row.get('乙方发票类型')
                party_b_invoice_type = str(party_b_invoice_type_val).strip() if pd.notna(party_b_invoice_type_val) and str(party_b_invoice_type_val).strip() else None

                # 合同类型（可选）
                contract_type_val = row.get('合同类型')
                contract_type = str(contract_type_val).strip() if pd.notna(contract_type_val) and str(contract_type_val).strip() else None

                # 合同分类（可选）
                contract_category_val = row.get('合同分类')
                contract_category = str(contract_category_val).strip() if pd.notna(contract_category_val) and str(contract_category_val).strip() else None

                # 合同金额（可选）
                contract_amount = None
                contract_amount_val = row.get('合同金额')
                if pd.notna(contract_amount_val) and str(contract_amount_val).strip():
                    try:
                        contract_amount = float(str(contract_amount_val).strip())
                    except (ValueError, TypeError):
                        error_records.append(f"第{row_num}行：合同金额格式无效 - {contract_amount_val}")
                        fail_count += 1
                        continue

                # 币种（可选，默认CNY）
                currency_val = row.get('币种')
                currency = str(currency_val).strip() if pd.notna(currency_val) and str(currency_val).strip() else 'CNY'

                # 税率（可选，百分比转小数，如13表示13%）
                tax_rate = None
                tax_rate_val = row.get('税率(%)') if '税率(%)' in df.columns else row.get('税率')
                if pd.notna(tax_rate_val) and str(tax_rate_val).strip():
                    try:
                        tax_rate = float(str(tax_rate_val).strip())
                    except (ValueError, TypeError):
                        error_records.append(f"第{row_num}行：税率格式无效 - {tax_rate_val}")
                        fail_count += 1
                        continue

                # 税额（可选，如果Excel中有则赋值，没有则由模型自动计算）
                tax_amount = None
                tax_amount_val = row.get('税额')
                if pd.notna(tax_amount_val) and str(tax_amount_val).strip():
                    try:
                        tax_amount = float(str(tax_amount_val).strip())
                    except (ValueError, TypeError):
                        # 税额格式无效不阻断导入，仅跳过该字段
                        tax_amount = None

                # 付款方式（可选）
                payment_method_val = row.get('付款方式')
                payment_method = str(payment_method_val).strip() if pd.notna(payment_method_val) and str(payment_method_val).strip() else None

                # 付款要求（可选）
                payment_requirements_val = row.get('付款要求')
                payment_requirements = str(payment_requirements_val).strip() if pd.notna(payment_requirements_val) and str(payment_requirements_val).strip() else None

                # 固定金额（可选）
                fixed_amount = None
                fixed_amount_val = row.get('固定金额')
                if pd.notna(fixed_amount_val) and str(fixed_amount_val).strip():
                    try:
                        fixed_amount = float(str(fixed_amount_val).strip())
                    except (ValueError, TypeError):
                        fixed_amount = None

                # 付款轮次（可选）
                payment_rounds_val = row.get('付款轮次')
                payment_rounds = None
                if pd.notna(payment_rounds_val) and str(payment_rounds_val).strip():
                    try:
                        payment_rounds = int(float(str(payment_rounds_val).strip()))
                    except (ValueError, TypeError):
                        payment_rounds = None

                # 对账日（可选）
                reconciliation_day_val = row.get('对账日')
                reconciliation_day = None
                if pd.notna(reconciliation_day_val) and str(reconciliation_day_val).strip():
                    try:
                        reconciliation_day = int(float(str(reconciliation_day_val).strip()))
                    except (ValueError, TypeError):
                        reconciliation_day = None

                # 付款截止日（可选）
                payment_deadline_day_val = row.get('付款截止日')
                payment_deadline_day = None
                if pd.notna(payment_deadline_day_val) and str(payment_deadline_day_val).strip():
                    try:
                        payment_deadline_day = int(float(str(payment_deadline_day_val).strip()))
                    except (ValueError, TypeError):
                        payment_deadline_day = None

                # 签订日期（可选）
                signing_date = None
                signing_date_val = row.get('签订日期')
                if pd.notna(signing_date_val) and str(signing_date_val).strip():
                    try:
                        if isinstance(signing_date_val, datetime):
                            signing_date = signing_date_val.date()
                        elif hasattr(signing_date_val, 'date'):
                            signing_date = signing_date_val.date()
                        else:
                            date_str = str(signing_date_val).strip()
                            signing_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        error_records.append(f"第{row_num}行：签订日期格式无效 - {signing_date_val}，请使用YYYY-MM-DD格式")
                        fail_count += 1
                        continue

                # 开始日期（可选）
                start_date = None
                start_date_val = row.get('开始日期')
                if pd.notna(start_date_val) and str(start_date_val).strip():
                    try:
                        if isinstance(start_date_val, datetime):
                            start_date = start_date_val.date()
                        elif hasattr(start_date_val, 'date'):
                            start_date = start_date_val.date()
                        else:
                            date_str = str(start_date_val).strip()
                            start_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        error_records.append(f"第{row_num}行：开始日期格式无效 - {start_date_val}，请使用YYYY-MM-DD格式")
                        fail_count += 1
                        continue

                # 结束日期（可选）
                end_date = None
                end_date_val = row.get('结束日期')
                if pd.notna(end_date_val) and str(end_date_val).strip():
                    try:
                        if isinstance(end_date_val, datetime):
                            end_date = end_date_val.date()
                        elif hasattr(end_date_val, 'date'):
                            end_date = end_date_val.date()
                        else:
                            date_str = str(end_date_val).strip()
                            end_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        error_records.append(f"第{row_num}行：结束日期格式无效 - {end_date_val}，请使用YYYY-MM-DD格式")
                        fail_count += 1
                        continue

                # 合同状态（可选，默认"待生效"）
                status_val = row.get('合同状态')
                status = str(status_val).strip() if pd.notna(status_val) and str(status_val).strip() else '待生效'
                valid_statuses = ['待生效', '生效中', '即将到期', '已到期', '已终止', '已归档']
                if status not in valid_statuses:
                    status = '待生效'

                # 经手人（可选）
                handler_user_id = None
                handler_val = row.get('经手人')
                if pd.notna(handler_val) and str(handler_val).strip():
                    try:
                        from models.user.user import User
                        handler_name = str(handler_val).strip()
                        handler_user = User.query.filter_by(name=handler_name).first()
                        if handler_user:
                            handler_user_id = handler_user.id
                    except Exception:
                        handler_user_id = None

                # 归属部门（可选）
                department_id = None
                department_val = row.get('归属部门')
                if pd.notna(department_val) and str(department_val).strip():
                    try:
                        from models.department.department import Department
                        dept_name = str(department_val).strip()
                        dept = Department.query.filter_by(name=dept_name).first()
                        if dept:
                            department_id = dept.id
                    except Exception:
                        department_id = None

                # 备注（可选）
                remark_val = row.get('备注')
                remark = str(remark_val).strip() if pd.notna(remark_val) and str(remark_val).strip() else None

                # 存放位置（可选，通过名称匹配StorageLocation，usage_type='合同管理'）
                storage_location_id = None
                storage_location_name_val = row.get('存放位置')
                if pd.notna(storage_location_name_val) and str(storage_location_name_val).strip():
                    storage_location_name = str(storage_location_name_val).strip()
                    storage_location = StorageLocation.query.filter_by(name=storage_location_name, usage_type='合同管理').first()
                    if storage_location:
                        storage_location_id = storage_location.id

                # ID匹配优先：如果提供了ID列，优先通过ID查找已有合同进行覆盖更新
                if contract_id and override:
                    existing = Contract.query.filter_by(id=contract_id).first()
                    if existing:
                        existing.contract_name = contract_name
                        if contract_number is not None:
                            existing.contract_number = contract_number
                        if party_a_id is not None:
                            existing.party_a_id = party_a_id
                        if party_b_id is not None:
                            existing.party_b_id = party_b_id
                        # 甲方详情字段
                        if party_a_contact_person is not None:
                            existing.party_a_contact_person = party_a_contact_person
                        if party_a_contact_phone is not None:
                            existing.party_a_contact_phone = party_a_contact_phone
                        if party_a_address is not None:
                            existing.party_a_address = party_a_address
                        if party_a_credit_code is not None:
                            existing.party_a_credit_code = party_a_credit_code
                        if party_a_legal_representative is not None:
                            existing.party_a_legal_representative = party_a_legal_representative
                        # 乙方详情字段
                        if party_b_contact_person is not None:
                            existing.party_b_contact_person = party_b_contact_person
                        if party_b_contact_phone is not None:
                            existing.party_b_contact_phone = party_b_contact_phone
                        if party_b_address is not None:
                            existing.party_b_address = party_b_address
                        if party_b_credit_code is not None:
                            existing.party_b_credit_code = party_b_credit_code
                        if party_b_legal_representative is not None:
                            existing.party_b_legal_representative = party_b_legal_representative
                        # 乙方扩展字段
                        if party_b_payment_method is not None:
                            existing.party_b_payment_method = party_b_payment_method
                        if party_b_bank_account is not None:
                            existing.party_b_bank_account = party_b_bank_account
                        if party_b_bank_name is not None:
                            existing.party_b_bank_name = party_b_bank_name
                        if party_b_receiving_bank is not None:
                            existing.party_b_receiving_bank = party_b_receiving_bank
                        if party_b_account_name is not None:
                            existing.party_b_account_name = party_b_account_name
                        if party_b_payment_account is not None:
                            existing.party_b_payment_account = party_b_payment_account
                        if party_b_invoice_type is not None:
                            existing.party_b_invoice_type = party_b_invoice_type
                        existing.contract_type = contract_type or existing.contract_type
                        existing.contract_category = contract_category or existing.contract_category
                        if contract_amount is not None:
                            existing.contract_amount = contract_amount
                        existing.currency = currency or existing.currency
                        if tax_rate is not None:
                            existing.tax_rate = tax_rate
                        if tax_amount is not None:
                            existing.tax_amount = tax_amount
                        # 付款相关字段
                        if payment_method is not None:
                            existing.payment_method = payment_method
                        if payment_requirements is not None:
                            existing.payment_requirements = payment_requirements
                        if fixed_amount is not None:
                            existing.fixed_amount = fixed_amount
                        if payment_rounds is not None:
                            existing.payment_rounds = payment_rounds
                        if reconciliation_day is not None:
                            existing.reconciliation_day = reconciliation_day
                        if payment_deadline_day is not None:
                            existing.payment_deadline_day = payment_deadline_day
                        if signing_date is not None:
                            existing.signing_date = signing_date
                        if start_date is not None:
                            existing.start_date = start_date
                        if end_date is not None:
                            existing.end_date = end_date
                        existing.status = status
                        if handler_user_id is not None:
                            existing.handler_user_id = handler_user_id
                        if department_id is not None:
                            existing.department_id = department_id
                        existing.remark = remark or existing.remark
                        if storage_location_id is not None:
                            existing.storage_location_id = storage_location_id
                        existing.operator_user_id = current_user.id
                        # 记录操作
                        ContractOperationRecord.create_record(
                            contract_id=existing.id,
                            operation_type='edit',
                            operator_id=current_user.id,
                            operator_name=current_user.name if hasattr(current_user, 'name') else str(current_user.id),
                            summary=f'导入覆盖更新合同(ID:{contract_id})：{existing.contract_number or contract_name}'
                        )
                        success_count += 1
                        continue
                    else:
                        error_records.append(f'第{row_num}行：未找到ID为{contract_id}的合同')
                        fail_count += 1
                        continue

                # 合同编号唯一性校验
                if contract_number:
                    if Contract.is_number_exists(contract_number):
                        if override:
                            # 查找已有合同进行覆盖更新
                            existing = Contract.query.filter_by(contract_number=contract_number).first()
                            if existing:
                                existing.contract_name = contract_name
                                if party_a_id is not None:
                                    existing.party_a_id = party_a_id
                                if party_b_id is not None:
                                    existing.party_b_id = party_b_id
                                # 甲方详情字段
                                if party_a_contact_person is not None:
                                    existing.party_a_contact_person = party_a_contact_person
                                if party_a_contact_phone is not None:
                                    existing.party_a_contact_phone = party_a_contact_phone
                                if party_a_address is not None:
                                    existing.party_a_address = party_a_address
                                if party_a_credit_code is not None:
                                    existing.party_a_credit_code = party_a_credit_code
                                if party_a_legal_representative is not None:
                                    existing.party_a_legal_representative = party_a_legal_representative
                                # 乙方详情字段
                                if party_b_contact_person is not None:
                                    existing.party_b_contact_person = party_b_contact_person
                                if party_b_contact_phone is not None:
                                    existing.party_b_contact_phone = party_b_contact_phone
                                if party_b_address is not None:
                                    existing.party_b_address = party_b_address
                                if party_b_credit_code is not None:
                                    existing.party_b_credit_code = party_b_credit_code
                                if party_b_legal_representative is not None:
                                    existing.party_b_legal_representative = party_b_legal_representative
                                # 乙方扩展字段
                                if party_b_payment_method is not None:
                                    existing.party_b_payment_method = party_b_payment_method
                                if party_b_bank_account is not None:
                                    existing.party_b_bank_account = party_b_bank_account
                                if party_b_bank_name is not None:
                                    existing.party_b_bank_name = party_b_bank_name
                                if party_b_receiving_bank is not None:
                                    existing.party_b_receiving_bank = party_b_receiving_bank
                                if party_b_account_name is not None:
                                    existing.party_b_account_name = party_b_account_name
                                if party_b_payment_account is not None:
                                    existing.party_b_payment_account = party_b_payment_account
                                if party_b_invoice_type is not None:
                                    existing.party_b_invoice_type = party_b_invoice_type
                                existing.contract_type = contract_type or existing.contract_type
                                existing.contract_category = contract_category or existing.contract_category
                                if contract_amount is not None:
                                    existing.contract_amount = contract_amount
                                existing.currency = currency or existing.currency
                                if tax_rate is not None:
                                    existing.tax_rate = tax_rate
                                if tax_amount is not None:
                                    existing.tax_amount = tax_amount
                                # 付款相关字段
                                if payment_method is not None:
                                    existing.payment_method = payment_method
                                if payment_requirements is not None:
                                    existing.payment_requirements = payment_requirements
                                if fixed_amount is not None:
                                    existing.fixed_amount = fixed_amount
                                if payment_rounds is not None:
                                    existing.payment_rounds = payment_rounds
                                if reconciliation_day is not None:
                                    existing.reconciliation_day = reconciliation_day
                                if payment_deadline_day is not None:
                                    existing.payment_deadline_day = payment_deadline_day
                                if signing_date is not None:
                                    existing.signing_date = signing_date
                                if start_date is not None:
                                    existing.start_date = start_date
                                if end_date is not None:
                                    existing.end_date = end_date
                                existing.status = status
                                if handler_user_id is not None:
                                    existing.handler_user_id = handler_user_id
                                if department_id is not None:
                                    existing.department_id = department_id
                                existing.remark = remark or existing.remark
                                if storage_location_id is not None:
                                    existing.storage_location_id = storage_location_id
                                existing.operator_user_id = current_user.id
                                # 记录操作
                                ContractOperationRecord.create_record(
                                    contract_id=existing.id,
                                    operation_type='edit',
                                    operator_id=current_user.id,
                                    operator_name=current_user.name if hasattr(current_user, 'name') else str(current_user.id),
                                    summary=f'导入覆盖更新合同：{contract_number}'
                                )
                                success_count += 1
                                continue
                        else:
                            error_records.append(f'第{row_num}行：合同编号"{contract_number}"已存在')
                            fail_count += 1
                            continue

                # 创建合同
                contract = Contract.create(
                    contract_number=contract_number,
                    contract_name=contract_name,
                    party_a_id=party_a_id,
                    party_a_contact_person=party_a_contact_person,
                    party_a_contact_phone=party_a_contact_phone,
                    party_a_address=party_a_address,
                    party_a_credit_code=party_a_credit_code,
                    party_a_legal_representative=party_a_legal_representative,
                    party_b_id=party_b_id,
                    party_b_contact_person=party_b_contact_person,
                    party_b_contact_phone=party_b_contact_phone,
                    party_b_address=party_b_address,
                    party_b_credit_code=party_b_credit_code,
                    party_b_legal_representative=party_b_legal_representative,
                    party_b_payment_method=party_b_payment_method,
                    party_b_bank_account=party_b_bank_account,
                    party_b_bank_name=party_b_bank_name,
                    party_b_receiving_bank=party_b_receiving_bank,
                    party_b_account_name=party_b_account_name,
                    party_b_payment_account=party_b_payment_account,
                    party_b_invoice_type=party_b_invoice_type,
                    contract_type=contract_type,
                    contract_category=contract_category,
                    contract_amount=contract_amount,
                    currency=currency,
                    tax_rate=tax_rate,
                    tax_amount=tax_amount,
                    payment_method=payment_method,
                    payment_requirements=payment_requirements,
                    fixed_amount=fixed_amount,
                    payment_rounds=payment_rounds,
                    reconciliation_day=reconciliation_day,
                    payment_deadline_day=payment_deadline_day,
                    signing_date=signing_date,
                    start_date=start_date,
                    end_date=end_date,
                    status=status,
                    handler_user_id=handler_user_id,
                    department_id=department_id,
                    remark=remark,
                    previous_contract_id=None,
                    storage_location_id=storage_location_id,
                    operator_user_id=current_user.id
                )
                # 记录操作
                ContractOperationRecord.create_record(
                    contract_id=contract.id,
                    operation_type='add',
                    operator_id=current_user.id,
                    operator_name=current_user.name if hasattr(current_user, 'name') else str(current_user.id),
                    summary=f'导入创建合同：{contract.contract_number or contract.contract_name}'
                )
                success_count += 1

            except Exception as e:
                error_records.append(f"第{row_num}行：创建合同失败 - {str(e)}")
                fail_count += 1
                logging.error(f'导入合同数据失败：第{row_num}行创建合同失败 - {str(e)}')
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
            module='contract',
            operation_type='batch_import_export',
            action=f"导入合同数据，成功{success_count}条，失败{fail_count}条",
            result=result_status
        )

        # 生成提示信息
        if result_status == "部分成功":
            message = f"导入部分成功：成功导入 {success_count} 条，失败 {fail_count} 条"
            message += f"<br>失败详情：<br>" + "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"
        elif result_status == "成功":
            message = f"导入全部成功：共导入 {success_count} 条合同数据"
        else:
            message = f"导入全部失败：共{len(error_records)}条记录处理失败：<br>" + "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"

        logging.info(message)
        flash(message, 'success' if result_status == "成功" else 'warning' if result_status == "部分成功" else 'danger')
        return redirect(url_for('contract.index'))

    except Exception as e:
        db.session.rollback()
        detailed_error = f"导入过程出错：{str(e)}"
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='batch_import_export',
            action=f"合同数据导入失败: {detailed_error}\n{traceback.format_exc()}",
            result="失败"
        )
        flash(detailed_error, 'danger')
        logging.error(f'导入合同数据失败：{detailed_error}')
        return redirect(url_for('contract.index'))


# 下载导入模板
@contract_import_export_bp.route('/template', methods=['GET'])
@login_required
@require_permission('contract.import')
def download_template():
    """生成并下载合同数据导入模板"""
    try:
        logging.debug('开始生成合同数据导入模板')

        # 模板数据生成
        template_data = {
            "ID": [1, 2, 3],
            "合同编号": ["HT2026010001", "HT2026010002", "HT2026010003"],
            "合同名称": ["办公设备采购合同", "物业服务合同", "房屋租赁合同"],
            "甲方名称": ["本公司", "本公司", "本公司"],
            "甲方联系人": ["张三", "张三", "张三"],
            "甲方联系电话": ["010-12345678", "010-12345678", "010-12345678"],
            "甲方地址": ["北京市XX区XX路XX号", "北京市XX区XX路XX号", "北京市XX区XX路XX号"],
            "甲方统一社会信用代码": ["91110000MA01XX1XXX", "91110000MA01XX1XXX", "91110000MA01XX1XXX"],
            "甲方法定代表人": ["李四", "李四", "李四"],
            "乙方名称": ["示例供应商A", "示例供应商B", "示例供应商C"],
            "乙方联系人": ["王五", "王五", "王五"],
            "乙方联系电话": ["021-87654321", "021-87654321", "021-87654321"],
            "乙方地址": ["上海市XX区XX路XX号", "上海市XX区XX路XX号", "上海市XX区XX路XX号"],
            "乙方统一社会信用代码": ["91310000MA02XX2XXX", "91310000MA02XX2XXX", "91310000MA02XX2XXX"],
            "乙方法定代表人": ["赵六", "赵六", "赵六"],
            "乙方收款方式": ["银行转账", "银行转账", "银行转账"],
            "乙方银行账号": ["6222000000001234567", "6222000000007654321", "6222000000001111222"],
            "乙方开户行": ["中国工商银行XX支行", "中国建设银行YY支行", "中国农业银行ZZ支行"],
            "乙方收款银行": ["中国工商银行", "中国建设银行", "中国农业银行"],
            "乙方开户名称": ["XX有限公司", "YY有限公司", "ZZ有限公司"],
            "乙方收款账号": ["6222000000001234567", "6222000000007654321", "6222000000001111222"],
            "乙方发票类型": ["增值税专用发票", "增值税普通发票", "增值税专用发票"],
            "合同类型": ["采购合同", "服务合同", "租赁合同"],
            "合同分类": ["一般合同", "重要合同", "一般合同"],
            "合同金额": [50000, 120000, 36000],
            "币种": ["CNY", "CNY", "CNY"],
            "税率(%)": [13, 6, 9],
            "税额": [6500, 7200, 3240],
            "付款方式": ["月度付款", "季度付款", "月度付款"],
            "付款要求": ["按月对账后付款", "按季度对账后付款", "按月对账后付款"],
            "固定金额": [50000, 80000, 30000],
            "付款轮次": [12, 24, 6],
            "对账日": [5, 10, 1],
            "付款截止日": [25, 20, 15],
            "签订日期": ["2026-01-15", "2026-02-01", "2026-03-01"],
            "开始日期": ["2026-01-15", "2026-02-01", "2026-03-01"],
            "结束日期": ["2026-12-31", "2027-01-31", "2027-02-28"],
            "合同状态": ["生效中", "待生效", "生效中"],
            "经手人": ["张三", "李四", "王五"],
            "归属部门": ["行政部", "后勤部", "行政部"],
            "存放位置": ["档案室A", "档案室B", "档案室A"],
            "备注": ["年度采购", "年度物业", "两年期租赁"],
        }

        df = pd.DataFrame(template_data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='合同数据')

        output.seek(0)
        filename = "合同数据导入模板.xlsx"

        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='batch_import_export',
            action="下载合同数据导入模板",
            result="成功"
        )

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'生成合同数据导入模板失败: {str(e)}', exc_info=True)
        flash('生成模板失败，请联系管理员', 'danger')
        return redirect(url_for('contract.index'))