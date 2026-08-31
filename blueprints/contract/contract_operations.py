from flask import render_template, request, flash, redirect, url_for, jsonify, send_file
from flask_login import login_required, current_user
from utils.db import db
from models.contract.contract import Contract
from models.contract.contract_operation_record import ContractOperationRecord
from models.supply.supplier import Supplier
from models.supply.storage_location import StorageLocation
from utils.log import log_operation
from utils.auth import require_permission
from utils.contract_attachment import ContractAttachmentManager
import logging
import traceback
from datetime import datetime, date
from .contract import contract_bp


# ========== 路由：新增合同 ==========
@contract_bp.route('/operations/add', methods=['POST'])
@login_required
@require_permission('contract.create')
def add_contract():
    """新增合同"""
    try:
        contract_number = request.form.get('contract_number', '').strip() or None
        contract_name = request.form.get('contract_name', '').strip()
        party_a_id = request.form.get('party_a_id', type=int) or None
        party_b_id = request.form.get('party_b_id', type=int) or None
        party_a_name = request.form.get('party_a_name', '').strip()
        party_b_name = request.form.get('party_b_name', '').strip()

        # 获取甲乙方快照字段
        party_a_contact_person = request.form.get('party_a_contact_person', '').strip() or None
        party_a_contact_phone = request.form.get('party_a_contact_phone', '').strip() or None
        party_a_address = request.form.get('party_a_address', '').strip() or None
        party_a_credit_code = request.form.get('party_a_credit_code', '').strip() or None
        party_a_legal_representative = request.form.get('party_a_legal_representative', '').strip() or None

        party_b_contact_person = request.form.get('party_b_contact_person', '').strip() or None
        party_b_contact_phone = request.form.get('party_b_contact_phone', '').strip() or None
        party_b_address = request.form.get('party_b_address', '').strip() or None
        party_b_credit_code = request.form.get('party_b_credit_code', '').strip() or None
        party_b_legal_representative = request.form.get('party_b_legal_representative', '').strip() or None

        # 处理自定义甲方
        if not party_a_id and party_a_name:
            existing = Supplier.query.filter_by(name=party_a_name).first()
            if existing:
                party_a_id = existing.id
                # 用现有供应商信息补充快照（如果前端未填）
                if not party_a_contact_person:
                    party_a_contact_person = existing.contact_person
                if not party_a_contact_phone:
                    party_a_contact_phone = existing.contact_phone
                if not party_a_address:
                    party_a_address = existing.address
                if not party_a_credit_code:
                    party_a_credit_code = existing.unified_social_credit_code
                if not party_a_legal_representative:
                    party_a_legal_representative = existing.legal_representative
            else:
                new_supplier = Supplier.create(
                    name=party_a_name,
                    contact_person=party_a_contact_person,
                    contact_phone=party_a_contact_phone,
                    address=party_a_address,
                    unified_social_credit_code=party_a_credit_code,
                    legal_representative=party_a_legal_representative,
                    status='启用',
                    handler_user_id=current_user.id,
                    operator_user_id=current_user.id
                )
                party_a_id = new_supplier.id

        # 处理自定义乙方
        if not party_b_id and party_b_name:
            existing = Supplier.query.filter_by(name=party_b_name).first()
            if existing:
                party_b_id = existing.id
                # 用现有供应商信息补充快照（如果前端未填）
                if not party_b_contact_person:
                    party_b_contact_person = existing.contact_person
                if not party_b_contact_phone:
                    party_b_contact_phone = existing.contact_phone
                if not party_b_address:
                    party_b_address = existing.address
                if not party_b_credit_code:
                    party_b_credit_code = existing.unified_social_credit_code
                if not party_b_legal_representative:
                    party_b_legal_representative = existing.legal_representative
            else:
                new_supplier = Supplier.create(
                    name=party_b_name,
                    contact_person=party_b_contact_person,
                    contact_phone=party_b_contact_phone,
                    address=party_b_address,
                    unified_social_credit_code=party_b_credit_code,
                    legal_representative=party_b_legal_representative,
                    status='启用',
                    handler_user_id=current_user.id,
                    operator_user_id=current_user.id
                )
                party_b_id = new_supplier.id

        # 如果从供应商选择（party_a_id有值），从Supplier获取信息填充快照
        if party_a_id and not party_a_contact_person:
            supplier_a = Supplier.query.get(party_a_id)
            if supplier_a:
                party_a_contact_person = supplier_a.contact_person
                party_a_contact_phone = supplier_a.contact_phone
                party_a_address = supplier_a.address
                party_a_credit_code = supplier_a.unified_social_credit_code
                party_a_legal_representative = supplier_a.legal_representative

        # 如果从供应商选择（party_b_id有值），从Supplier获取信息填充快照
        if party_b_id and not party_b_contact_person:
            supplier_b = Supplier.query.get(party_b_id)
            if supplier_b:
                party_b_contact_person = supplier_b.contact_person
                party_b_contact_phone = supplier_b.contact_phone
                party_b_address = supplier_b.address
                party_b_credit_code = supplier_b.unified_social_credit_code
                party_b_legal_representative = supplier_b.legal_representative
        contract_type = request.form.get('contract_type', '').strip() or None
        contract_category = request.form.get('contract_category', '').strip() or None
        contract_amount = request.form.get('contract_amount', '').strip() or None
        currency = request.form.get('currency', 'CNY').strip() or 'CNY'
        tax_rate = request.form.get('tax_rate', '').strip() or None
        tax_amount = request.form.get('tax_amount', '').strip() or None
        signing_date = request.form.get('signing_date', '').strip() or None
        start_date = request.form.get('start_date', '').strip() or None
        end_date = request.form.get('end_date', '').strip() or None
        handler_user_id = request.form.get('handler_user_id', type=int) or None
        department_id = request.form.get('department_id', type=int) or None
        remark = request.form.get('remark', '').strip() or None
        previous_contract_id = request.form.get('previous_contract_id', type=int) or None
        status = request.form.get('status', '草稿').strip() or '草稿'
        storage_location_id = request.form.get('storage_location_id', type=int) or None
        storage_location_name = request.form.get('storage_location_name', '').strip()

        # 处理自定义存放位置
        if not storage_location_id and storage_location_name:
            existing_location = StorageLocation.query.filter_by(name=storage_location_name, usage_type='合同管理').first()
            if existing_location:
                storage_location_id = existing_location.id
            else:
                new_location = StorageLocation.create(
                    name=storage_location_name,
                    usage_type='合同管理',
                    status='启用',
                    handler_user_id=current_user.id,
                    operator_user_id=current_user.id
                )
                storage_location_id = new_location.id

        # 必填字段校验
        if not contract_name:
            flash('合同名称不能为空', 'danger')
            return redirect(url_for('contract.add_page'))

        # 自动生成合同编号（用户留空时）
        if not contract_number:
            today_str = date.today().strftime('%Y%m')
            prefix = f'HT{today_str}'
            existing = Contract.query.filter(Contract.contract_number.like(f'{prefix}%')).order_by(Contract.contract_number.desc()).first()
            if existing:
                last_num = int(existing.contract_number[-4:])
                contract_number = f'{prefix}{last_num + 1:04d}'
            else:
                contract_number = f'{prefix}0001'

        # 合同编号唯一性校验
        if Contract.is_number_exists(contract_number):
            flash(f'合同编号"{contract_number}"已存在', 'danger')
            return redirect(url_for('contract.add_page'))

        # 税率自动填充：若用户未手动输入税率且选择了供应商，从供应商获取税率
        if not tax_rate and party_b_id:
            supplier = Supplier.query.get(party_b_id)
            if supplier and supplier.tax_rate:
                tax_rate = supplier.tax_rate

        # 金额转换
        if contract_amount:
            try:
                contract_amount = float(contract_amount)
            except (ValueError, TypeError):
                contract_amount = None

        # 税率转换
        if tax_rate:
            try:
                tax_rate = float(tax_rate)
            except (ValueError, TypeError):
                tax_rate = None

        # 税额转换
        if tax_amount:
            try:
                tax_amount = float(tax_amount)
            except (ValueError, TypeError):
                tax_amount = None

        # 日期转换
        if signing_date:
            try:
                signing_date = datetime.strptime(signing_date, '%Y-%m-%d').date()
            except ValueError:
                signing_date = None
        if start_date:
            try:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            except ValueError:
                start_date = None
        if end_date:
            try:
                end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
            except ValueError:
                end_date = None

        # 创建合同记录
        contract = Contract.create(
            contract_name=contract_name,
            contract_number=contract_number,
            party_a_id=party_a_id,
            party_b_id=party_b_id,
            contract_type=contract_type,
            contract_category=contract_category,
            contract_amount=contract_amount,
            currency=currency,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            signing_date=signing_date,
            start_date=start_date,
            end_date=end_date,
            handler_user_id=handler_user_id,
            department_id=department_id,
            previous_contract_id=previous_contract_id,
            storage_location_id=storage_location_id,
            remark=remark,
            operator_user_id=current_user.id,
            party_a_contact_person=party_a_contact_person,
            party_a_contact_phone=party_a_contact_phone,
            party_a_address=party_a_address,
            party_a_credit_code=party_a_credit_code,
            party_a_legal_representative=party_a_legal_representative,
            party_b_contact_person=party_b_contact_person,
            party_b_contact_phone=party_b_contact_phone,
            party_b_address=party_b_address,
            party_b_credit_code=party_b_credit_code,
            party_b_legal_representative=party_b_legal_representative,
            status=status
        )

        # 记录操作记录
        renewal_info = ''
        if previous_contract_id:
            prev_contract = Contract.query.get(previous_contract_id)
            if prev_contract:
                renewal_info = f'，续签自合同：{prev_contract.contract_number} - {prev_contract.contract_name}'
        storage_location_info = ''
        if storage_location_id:
            location = StorageLocation.query.get(storage_location_id)
            if location:
                storage_location_info = f'，存放位置：{location.display_name}'
        ContractOperationRecord.create_record(
            contract_id=contract.id,
            operation_type='add',
            operator_id=current_user.id,
            operator_name=current_user.name,
            summary=f'新增合同：{contract_name}（编号：{contract_number}）{renewal_info}{storage_location_info}'
        )

        # 给旧合同添加操作记录
        if previous_contract_id:
            prev_contract = Contract.query.get(previous_contract_id)
            if prev_contract:
                ContractOperationRecord.create_record(
                    contract_id=prev_contract.id,
                    operation_type='contract_renew',
                    operator_id=current_user.id,
                    operator_name=current_user.name,
                    summary=f'已续签新合同：{contract.contract_number or "未编号"} - {contract.contract_name}'
                )

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='contract_add',
            action=f"新增合同: {contract_name}（编号：{contract_number}）{renewal_info}",
            result="成功"
        )

        flash(f'新增合同成功: {contract_name}', 'success')
        logging.info(f"新增合同成功，合同ID: {contract.id}, 名称: {contract_name}, 编号: {contract_number}")
        if request.form.get('save_and_continue'):
            return redirect(url_for('contract.add_page'))
        return redirect(url_for('contract.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='contract_add',
            action=f"新增合同失败: {str(e)}",
            result="失败"
        )
        flash(f'新增合同失败: {str(e)}', 'danger')
        logging.error(f"新增合同失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('contract.add_page'))


# ========== 路由：编辑合同 ==========
@contract_bp.route('/operations/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('contract.edit')
def edit_contract(id):
    """编辑合同"""
    try:
        contract = Contract.query.get_or_404(id)
        old_name = contract.contract_name

        # 获取表单数据
        new_contract_number = request.form.get('contract_number', '').strip() or None
        new_contract_name = request.form.get('contract_name', '').strip()
        new_party_a_id = request.form.get('party_a_id', type=int) or None
        new_party_b_id = request.form.get('party_b_id', type=int) or None
        new_party_a_name = request.form.get('party_a_name', '').strip()
        new_party_b_name = request.form.get('party_b_name', '').strip()

        # 获取甲乙方快照字段
        new_party_a_contact_person = request.form.get('party_a_contact_person', '').strip() or None
        new_party_a_contact_phone = request.form.get('party_a_contact_phone', '').strip() or None
        new_party_a_address = request.form.get('party_a_address', '').strip() or None
        new_party_a_credit_code = request.form.get('party_a_credit_code', '').strip() or None
        new_party_a_legal_representative = request.form.get('party_a_legal_representative', '').strip() or None

        new_party_b_contact_person = request.form.get('party_b_contact_person', '').strip() or None
        new_party_b_contact_phone = request.form.get('party_b_contact_phone', '').strip() or None
        new_party_b_address = request.form.get('party_b_address', '').strip() or None
        new_party_b_credit_code = request.form.get('party_b_credit_code', '').strip() or None
        new_party_b_legal_representative = request.form.get('party_b_legal_representative', '').strip() or None

        # 处理自定义甲方
        if not new_party_a_id and new_party_a_name:
            existing = Supplier.query.filter_by(name=new_party_a_name).first()
            if existing:
                new_party_a_id = existing.id
                # 用现有供应商信息补充快照（如果前端未填）
                if not new_party_a_contact_person:
                    new_party_a_contact_person = existing.contact_person
                if not new_party_a_contact_phone:
                    new_party_a_contact_phone = existing.contact_phone
                if not new_party_a_address:
                    new_party_a_address = existing.address
                if not new_party_a_credit_code:
                    new_party_a_credit_code = existing.unified_social_credit_code
                if not new_party_a_legal_representative:
                    new_party_a_legal_representative = existing.legal_representative
            else:
                new_supplier = Supplier.create(
                    name=new_party_a_name,
                    contact_person=new_party_a_contact_person,
                    contact_phone=new_party_a_contact_phone,
                    address=new_party_a_address,
                    unified_social_credit_code=new_party_a_credit_code,
                    legal_representative=new_party_a_legal_representative,
                    status='启用',
                    handler_user_id=current_user.id,
                    operator_user_id=current_user.id
                )
                new_party_a_id = new_supplier.id

        # 处理自定义乙方
        if not new_party_b_id and new_party_b_name:
            existing = Supplier.query.filter_by(name=new_party_b_name).first()
            if existing:
                new_party_b_id = existing.id
                # 用现有供应商信息补充快照（如果前端未填）
                if not new_party_b_contact_person:
                    new_party_b_contact_person = existing.contact_person
                if not new_party_b_contact_phone:
                    new_party_b_contact_phone = existing.contact_phone
                if not new_party_b_address:
                    new_party_b_address = existing.address
                if not new_party_b_credit_code:
                    new_party_b_credit_code = existing.unified_social_credit_code
                if not new_party_b_legal_representative:
                    new_party_b_legal_representative = existing.legal_representative
            else:
                new_supplier = Supplier.create(
                    name=new_party_b_name,
                    contact_person=new_party_b_contact_person,
                    contact_phone=new_party_b_contact_phone,
                    address=new_party_b_address,
                    unified_social_credit_code=new_party_b_credit_code,
                    legal_representative=new_party_b_legal_representative,
                    status='启用',
                    handler_user_id=current_user.id,
                    operator_user_id=current_user.id
                )
                new_party_b_id = new_supplier.id

        # 如果从供应商选择（new_party_a_id有值），从Supplier获取信息填充快照
        if new_party_a_id and not new_party_a_contact_person:
            supplier_a = Supplier.query.get(new_party_a_id)
            if supplier_a:
                new_party_a_contact_person = supplier_a.contact_person
                new_party_a_contact_phone = supplier_a.contact_phone
                new_party_a_address = supplier_a.address
                new_party_a_credit_code = supplier_a.unified_social_credit_code
                new_party_a_legal_representative = supplier_a.legal_representative

        # 如果从供应商选择（new_party_b_id有值），从Supplier获取信息填充快照
        if new_party_b_id and not new_party_b_contact_person:
            supplier_b = Supplier.query.get(new_party_b_id)
            if supplier_b:
                new_party_b_contact_person = supplier_b.contact_person
                new_party_b_contact_phone = supplier_b.contact_phone
                new_party_b_address = supplier_b.address
                new_party_b_credit_code = supplier_b.unified_social_credit_code
                new_party_b_legal_representative = supplier_b.legal_representative
        new_contract_type = request.form.get('contract_type', '').strip() or None
        new_contract_category = request.form.get('contract_category', '').strip() or None
        new_contract_amount = request.form.get('contract_amount', '').strip() or None
        new_currency = request.form.get('currency', 'CNY').strip() or 'CNY'
        new_tax_rate = request.form.get('tax_rate', '').strip() or None
        new_tax_amount = request.form.get('tax_amount', '').strip() or None
        new_signing_date = request.form.get('signing_date', '').strip() or None
        new_start_date = request.form.get('start_date', '').strip() or None
        new_end_date = request.form.get('end_date', '').strip() or None
        new_handler_user_id = request.form.get('handler_user_id', type=int) or None
        new_department_id = request.form.get('department_id', type=int) or None
        new_remark = request.form.get('remark', '').strip() or None
        new_storage_location_id = request.form.get('storage_location_id', type=int) or None
        new_storage_location_name = request.form.get('storage_location_name', '').strip()
        new_status = request.form.get('status', '').strip() or None

        # 处理自定义存放位置
        if not new_storage_location_id and new_storage_location_name:
            existing_location = StorageLocation.query.filter_by(name=new_storage_location_name, usage_type='合同管理').first()
            if existing_location:
                new_storage_location_id = existing_location.id
            else:
                new_location = StorageLocation.create(
                    name=new_storage_location_name,
                    usage_type='合同管理',
                    status='启用',
                    handler_user_id=current_user.id,
                    operator_user_id=current_user.id
                )
                new_storage_location_id = new_location.id

        # 必填字段校验
        if not new_contract_name:
            flash('合同名称不能为空', 'danger')
            return redirect(url_for('contract.edit_page', id=id))

        # 合同编号唯一性校验（排除自身）
        if new_contract_number and Contract.is_number_exists(new_contract_number, exclude_id=id):
            flash(f'合同编号"{new_contract_number}"已存在', 'danger')
            return redirect(url_for('contract.edit_page', id=id))

        # 金额转换
        if new_contract_amount:
            try:
                new_contract_amount = float(new_contract_amount)
            except (ValueError, TypeError):
                new_contract_amount = None

        # 税率转换
        if new_tax_rate:
            try:
                new_tax_rate = float(new_tax_rate)
            except (ValueError, TypeError):
                new_tax_rate = None

        # 税额转换
        if new_tax_amount:
            try:
                new_tax_amount = float(new_tax_amount)
            except (ValueError, TypeError):
                new_tax_amount = None

        # 日期转换
        if new_signing_date:
            try:
                new_signing_date = datetime.strptime(new_signing_date, '%Y-%m-%d').date()
            except ValueError:
                new_signing_date = None
        if new_start_date:
            try:
                new_start_date = datetime.strptime(new_start_date, '%Y-%m-%d').date()
            except ValueError:
                new_start_date = None
        if new_end_date:
            try:
                new_end_date = datetime.strptime(new_end_date, '%Y-%m-%d').date()
            except ValueError:
                new_end_date = None

        # 获取乙方名称用于变更记录
        new_party_b_name = '未指定'
        if new_party_b_id:
            supplier = Supplier.query.get(new_party_b_id)
            if supplier:
                new_party_b_name = supplier.name

        # 对比新旧值，记录变更详情
        changes = []
        if contract.contract_name != new_contract_name:
            changes.append(f"合同名称: {contract.contract_name} → {new_contract_name}")
        if contract.contract_number != new_contract_number:
            changes.append(f"合同编号: {contract.contract_number or '无'} → {new_contract_number or '无'}")
        if contract.party_a_id != new_party_a_id:
            changes.append(f"甲方ID: {contract.party_a_id or '无'} → {new_party_a_id or '无'}")
        if contract.party_b_id != new_party_b_id:
            old_b_name = contract.party_b_name if contract.party_b_id else '未指定'
            changes.append(f"乙方: {old_b_name} → {new_party_b_name}")
        if contract.contract_type != new_contract_type:
            changes.append(f"合同类型: {contract.contract_type or '无'} → {new_contract_type or '无'}")
        if contract.contract_category != new_contract_category:
            changes.append(f"合同分类: {contract.contract_category or '无'} → {new_contract_category or '无'}")
        if str(contract.contract_amount or '') != str(new_contract_amount or ''):
            changes.append(f"合同金额: {contract.contract_amount or '无'} → {new_contract_amount or '无'}")
        if contract.currency != new_currency:
            changes.append(f"币种: {contract.currency or '无'} → {new_currency or '无'}")
        if str(contract.tax_rate or '') != str(new_tax_rate or ''):
            changes.append(f"税率: {contract.tax_rate or '无'} → {new_tax_rate or '无'}")
        if str(contract.tax_amount or '') != str(new_tax_amount or ''):
            changes.append(f"税额: {contract.tax_amount or '无'} → {new_tax_amount or '无'}")
        if contract.signing_date != new_signing_date:
            changes.append(f"签订日期: {contract.signing_date or '无'} → {new_signing_date or '无'}")
        if contract.start_date != new_start_date:
            changes.append(f"开始日期: {contract.start_date or '无'} → {new_start_date or '无'}")
        if contract.end_date != new_end_date:
            changes.append(f"结束日期: {contract.end_date or '无'} → {new_end_date or '无'}")
        if contract.handler_user_id != new_handler_user_id:
            changes.append(f"经手人ID: {contract.handler_user_id or '无'} → {new_handler_user_id or '无'}")
        if contract.department_id != new_department_id:
            changes.append(f"归属部门ID: {contract.department_id or '无'} → {new_department_id or '无'}")
        if contract.remark != new_remark:
            changes.append("备注已更新")
        if contract.storage_location_id != new_storage_location_id:
            old_location_name = contract.storage_location.display_name if contract.storage_location else '未指定'
            new_location = StorageLocation.query.get(new_storage_location_id) if new_storage_location_id else None
            new_location_name = new_location.display_name if new_location else '未指定'
            changes.append(f"存放位置: {old_location_name} → {new_location_name}")
        if new_status and new_status != contract.status:
            changes.append(f"状态: {contract.status or '无'} → {new_status}")

        # 更新合同字段
        contract.contract_name = new_contract_name
        contract.contract_number = new_contract_number
        contract.party_a_id = new_party_a_id
        contract.party_b_id = new_party_b_id
        contract.contract_type = new_contract_type
        contract.contract_category = new_contract_category
        contract.contract_amount = new_contract_amount
        contract.currency = new_currency
        contract.tax_rate = new_tax_rate
        contract.tax_amount = new_tax_amount
        contract.signing_date = new_signing_date
        contract.start_date = new_start_date
        contract.end_date = new_end_date
        contract.handler_user_id = new_handler_user_id
        contract.department_id = new_department_id
        contract.remark = new_remark
        contract.storage_location_id = new_storage_location_id
        if new_status:
            contract.status = new_status
        contract.operator_user_id = current_user.id
        # 更新甲乙方快照字段
        contract.party_a_contact_person = new_party_a_contact_person
        contract.party_a_contact_phone = new_party_a_contact_phone
        contract.party_a_address = new_party_a_address
        contract.party_a_credit_code = new_party_a_credit_code
        contract.party_a_legal_representative = new_party_a_legal_representative
        contract.party_b_contact_person = new_party_b_contact_person
        contract.party_b_contact_phone = new_party_b_contact_phone
        contract.party_b_address = new_party_b_address
        contract.party_b_credit_code = new_party_b_credit_code
        contract.party_b_legal_representative = new_party_b_legal_representative

        db.session.commit()

        # 记录操作记录
        change_detail = [{'field': c.split(':')[0].strip(), 'change': c} for c in changes] if changes else None
        ContractOperationRecord.create_record(
            contract_id=id,
            operation_type='edit',
            operator_id=current_user.id,
            operator_name=current_user.name,
            change_detail=change_detail,
            summary=f'编辑合同: {old_name} → {new_contract_name}，{", ".join(changes) if changes else "无变更"}'
        )

        # 记录操作日志
        change_summary = '，'.join(changes) if changes else '无变更'
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='contract_edit',
            action=f"编辑合同: {old_name} → {new_contract_name}，{change_summary}",
            result="成功"
        )

        flash(f'编辑合同成功: {new_contract_name}', 'success')
        logging.info(f"编辑合同成功，合同ID: {id}, 变更: {change_summary}")
        return redirect(url_for('contract.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='contract_edit',
            action=f"编辑合同失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'编辑合同失败: {str(e)}', 'danger')
        logging.error(f"编辑合同失败，合同ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('contract.index'))


# ========== 路由：删除合同 ==========
@contract_bp.route('/operations/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('contract.delete')
def delete_contract(id):
    """删除合同"""
    try:
        contract = Contract.query.get_or_404(id)
        contract_name = contract.contract_name
        contract_number = contract.contract_number

        # 检查使用情况：是否有续签合同引用此合同作为previous_contract_id
        renewed_contracts = Contract.query.filter_by(previous_contract_id=id).count()
        if renewed_contracts > 0:
            flash(f'合同"{contract_name}"已被{renewed_contracts}份续签合同引用，无法删除', 'danger')
            return redirect(url_for('contract.detail', id=id))

        # 记录操作记录（删除前记录）
        ContractOperationRecord.create_record(
            contract_id=id,
            operation_type='delete',
            operator_id=current_user.id,
            operator_name=current_user.name,
            summary=f'删除合同：{contract_name}（编号：{contract_number or "无"}）'
        )

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='contract_delete',
            action=f"删除合同: {contract_name}（编号：{contract_number or '无'}）",
            result="成功"
        )

        # 删除合同附件目录
        ContractAttachmentManager.delete_all_files(id)

        # 删除合同（级联删除附件记录和操作记录）
        db.session.delete(contract)
        db.session.commit()

        flash(f'删除合同成功: {contract_name}', 'success')
        logging.info(f"删除合同成功，合同ID: {id}, 名称: {contract_name}")
        return redirect(url_for('contract.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='contract_delete',
            action=f"删除合同失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'删除合同失败: {str(e)}', 'danger')
        logging.error(f"删除合同失败，合同ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('contract.index'))


# ========== 路由：变更合同状态 ==========
@contract_bp.route('/operations/status_change/<int:id>', methods=['POST'])
@login_required
@require_permission('contract.edit')
def status_change_contract(id):
    """变更合同状态"""
    try:
        contract = Contract.query.get_or_404(id)
        old_status = contract.status
        new_status = request.form.get('status', '').strip()

        # 校验状态流转合法性
        valid_transitions = {
            '草稿': ['生效中', '已终止'],
            '生效中': ['即将到期', '已到期', '已终止', '已归档'],
            '即将到期': ['生效中', '已到期', '已终止', '已归档'],
            '已到期': ['生效中', '已终止', '已归档'],
            '已终止': [],
            '已归档': []
        }

        if old_status not in valid_transitions:
            flash(f'当前状态"{old_status}"不支持状态变更', 'danger')
            return redirect(url_for('contract.detail', id=id))

        if new_status not in valid_transitions.get(old_status, []):
            flash(f'状态不允许从"{old_status}"变更为"{new_status}"', 'danger')
            return redirect(url_for('contract.detail', id=id))

        # 更新状态
        contract.status = new_status
        contract.operator_user_id = current_user.id
        db.session.commit()

        # 记录操作记录
        ContractOperationRecord.create_record(
            contract_id=id,
            operation_type='status_change',
            operator_id=current_user.id,
            operator_name=current_user.name,
            change_detail={'old_status': old_status, 'new_status': new_status},
            summary=f'合同状态变更：{old_status} → {new_status}'
        )

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='contract_status_change',
            action=f"合同{contract.contract_name}状态变更：{old_status} → {new_status}",
            result="成功"
        )

        flash(f'合同状态已变更为：{new_status}', 'success')
        logging.info(f"合同状态变更，合同ID: {id}, {old_status} → {new_status}")
        return redirect(url_for('contract.detail', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='contract_status_change',
            action=f"变更合同状态失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'变更合同状态失败: {str(e)}', 'danger')
        logging.error(f"变更合同状态失败，合同ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('contract.detail', id=id))


# ========== 路由：上传合同附件 ==========
@contract_bp.route('/operations/upload_attachment/<int:id>', methods=['POST'])
@login_required
@require_permission('contract.edit')
def upload_contract_attachment(id):
    """上传合同附件（支持批量上传）"""
    try:
        contract = Contract.query.get_or_404(id)

        # 检查request.files中是否有files
        if 'files' not in request.files:
            flash('未选择要上传的文件', 'danger')
            return redirect(url_for('contract.detail', id=id))

        files = request.files.getlist('files')
        if not files or files[0].filename == '' or files[0].filename is None:
            flash('未选择要上传的文件', 'danger')
            return redirect(url_for('contract.detail', id=id))

        # 批量上传文件
        success_count = 0
        fail_count = 0
        success_filenames = []

        for file in files:
            if file and file.filename and file.filename != '':
                saved_filename = ContractAttachmentManager.upload_file(id, file)
                if saved_filename:
                    success_count += 1
                    success_filenames.append(file.filename)

                    # 记录操作记录
                    ContractOperationRecord.create_record(
                        contract_id=id,
                        operation_type='upload_attachment',
                        operator_id=current_user.id,
                        operator_name=current_user.name,
                        summary=f'上传附件：{file.filename}'
                    )

                    # 记录操作日志
                    log_operation(
                        user_id=current_user.id,
                        module='contract',
                        operation_type='contract_upload_attachment',
                        action=f"上传合同附件: {file.filename} [合同ID: {id}]",
                        result="成功"
                    )
                    logging.info(f"上传合同附件成功，合同ID: {id}, 文件: {file.filename}")
                else:
                    fail_count += 1
                    logging.warning(f"上传合同附件失败（不支持的文件类型），合同ID: {id}, 文件: {file.filename}")

        # 根据上传结果显示flash消息
        if success_count > 0:
            flash(f'成功上传 {success_count} 个附件', 'success')
        if fail_count > 0:
            flash(f'{fail_count} 个文件上传失败（不支持的文件类型）', 'danger')

        return redirect(url_for('contract.detail', id=id))

    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='contract_upload_attachment',
            action=f"上传合同附件失败 [合同ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'附件上传失败: {str(e)}', 'danger')
        logging.error(f"上传合同附件失败，合同ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('contract.detail', id=id))


# ========== 路由：删除合同附件 ==========
@contract_bp.route('/operations/delete_attachment/<int:contract_id>', methods=['POST'])
@login_required
@require_permission('contract.edit')
def delete_contract_attachment(contract_id):
    """删除合同附件（按contract_id和filename）"""
    try:
        filename = request.form.get('filename', '').strip()
        if not filename:
            flash('缺少文件名参数', 'danger')
            return redirect(url_for('contract.detail', id=contract_id))

        # 删除文件
        success = ContractAttachmentManager.delete_file(contract_id, filename)

        if not success:
            flash('附件删除失败，文件不存在', 'danger')
            return redirect(url_for('contract.detail', id=contract_id))

        # 记录操作记录
        ContractOperationRecord.create_record(
            contract_id=contract_id,
            operation_type='delete_attachment',
            operator_id=current_user.id,
            operator_name=current_user.name,
            summary=f'删除附件：{filename}'
        )

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='contract_delete_attachment',
            action=f"删除合同附件: {filename} [合同ID: {contract_id}]",
            result="成功"
        )

        flash(f'附件删除成功: {filename}', 'success')
        logging.info(f"删除合同附件成功，合同ID: {contract_id}, 文件: {filename}")
        return redirect(url_for('contract.detail', id=contract_id))

    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='contract_delete_attachment',
            action=f"删除合同附件失败 [合同ID: {contract_id}]: {str(e)}",
            result="失败"
        )
        flash(f'附件删除失败: {str(e)}', 'danger')
        logging.error(f"删除合同附件失败，合同ID: {contract_id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('contract.detail', id=contract_id))


# ========== 路由：续签合同 ==========
@contract_bp.route('/operations/renew/<int:id>', methods=['GET'])
@login_required
@require_permission('contract.create')
def renew_contract(id):
    """续签合同 - 跳转到新增页面，自动填充原合同信息"""
    try:
        contract = Contract.query.get_or_404(id)

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='contract_renew',
            action=f"续签合同: {contract.contract_name}（编号：{contract.contract_number or '无'}）",
            result="成功"
        )

        logging.info(f"续签合同，原合同ID: {id}, 名称: {contract.contract_name}")
        return redirect(url_for('contract.add_page', previous_contract_id=id))

    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='contract_renew',
            action=f"续签合同失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'续签合同失败: {str(e)}', 'danger')
        logging.error(f"续签合同失败，合同ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('contract.detail', id=id))


# ========== 路由：批量删除 ==========
@contract_bp.route('/operations/batch-delete', methods=['POST'])
@login_required
@require_permission('contract.delete')
def batch_delete_contracts():
    """批量删除合同"""
    try:
        id_strings = request.form.getlist('contract_ids[]')
        if not id_strings:
            flash('请选择要删除的合同', 'danger')
            return redirect(url_for('contract.index'))

        # 转换并验证ID
        contract_ids = []
        invalid_ids = []
        for id_str in id_strings:
            try:
                contract_id = int(id_str.strip())
                contract_ids.append(contract_id)
            except ValueError:
                invalid_ids.append(id_str)

        if invalid_ids:
            logging.warning(f"批量删除包含无效ID: {', '.join(invalid_ids)}")

        if not contract_ids:
            flash('未提供有效的合同ID', 'danger')
            return redirect(url_for('contract.index'))

        # 批量处理删除
        deleted_count = 0
        errors = []

        for contract_id in contract_ids:
            try:
                contract = Contract.query.get(contract_id)
                if not contract:
                    errors.append(f"合同ID {contract_id} 不存在")
                    continue

                contract_name = contract.contract_name
                contract_number = contract.contract_number

                # 检查是否有续签合同引用
                renewed_count = Contract.query.filter_by(previous_contract_id=contract_id).count()
                if renewed_count > 0:
                    errors.append(f"合同「{contract_name}」被{renewed_count}份续签合同引用，无法删除")
                    continue

                # 删除合同附件目录
                ContractAttachmentManager.delete_all_files(contract_id)

                # 删除合同（级联删除附件记录和操作记录）
                db.session.delete(contract)
                deleted_count += 1
                logging.info(f"批量删除合同: {contract_name}({contract_number or '无编号'})")

            except Exception as e:
                errors.append(f"合同ID {contract_id} 删除失败: {str(e)}")
                logging.error(f"批量删除合同ID {contract_id} 异常: {str(e)}")

        # 统一提交事务
        db.session.commit()

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='contract_delete',
            action=f"批量删除合同，共{len(contract_ids)}个，成功删除{deleted_count}个，失败{len(errors)}个",
            result="成功"
        )

        if errors:
            for error in errors:
                flash(error, 'warning')

        flash(f'批量删除完成，成功删除{deleted_count}个合同', 'success')
        logging.info(f"批量删除完成，总数: {len(contract_ids)}, 成功: {deleted_count}, 失败: {len(errors)}")
        return redirect(url_for('contract.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='contract_delete',
            action=f"批量删除合同失败: {str(e)}",
            result="失败"
        )
        flash(f'批量删除失败: {str(e)}', 'danger')
        logging.error(f"批量删除合同失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('contract.index'))