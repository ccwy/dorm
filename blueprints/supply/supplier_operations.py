from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from utils.db import db
from models.supply.supplier import Supplier
from models.supply.supplier_operation_record import SupplierOperationRecord
from utils.log import log_operation
from utils.auth import require_permission
import logging
import traceback
from datetime import datetime
from .supplier import supplier_bp


# ========== 路由：新增供应商 ==========
@supplier_bp.route('/operations/add', methods=['POST'])
@login_required
@require_permission('supply.create')
def add_supplier():
    """新增供应商"""
    try:
        name = request.form.get('name', '').strip()
        unified_social_credit_code = request.form.get('unified_social_credit_code', '').strip() or None
        legal_representative = request.form.get('legal_representative', '').strip() or None
        contact_person = request.form.get('contact_person', '').strip() or None
        contact_phone = request.form.get('contact_phone', '').strip() or None
        email = request.form.get('email', '').strip() or None
        address = request.form.get('address', '').strip() or None
        status = request.form.get('status', '启用').strip() or '启用'
        handler_user_id = current_user.id
        remark = request.form.get('remark', '').strip() or None
        tax_rate = request.form.get('tax_rate', '').strip() or None
        if tax_rate:
            try:
                tax_rate = float(tax_rate)
            except (ValueError, TypeError):
                tax_rate = None

        # 必填字段校验
        if not name:
            flash('供应商名称不能为空', 'danger')
            return redirect(url_for('supplier.add_page'))

        # 状态值校验
        if status not in ['启用', '停用']:
            status = '启用'

        # 检查名称是否重复（仅按name查重）
        if Supplier.is_name_exists(name, exclude_id=None):
            flash(f'已存在供应商"{name}"', 'danger')
            return redirect(url_for('supplier.add_page'))

        supplier = Supplier.create(
            name=name, unified_social_credit_code=unified_social_credit_code,
            legal_representative=legal_representative,
            contact_person=contact_person, contact_phone=contact_phone,
            email=email, address=address, status=status,
            handler_user_id=handler_user_id, remark=remark, tax_rate=tax_rate,
            operator_user_id=current_user.id
        )

        # 记录操作记录
        SupplierOperationRecord.create_record(
            supplier_id=supplier.id, operation_type='add',
            operator_id=current_user.id, operator_name=current_user.name,
            summary=f'新增供应商：{name}'
        )

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='supplier_add',
            action=f"新增供应商: {name}",
            result="成功"
        )

        flash(f'新增供应商成功: {name}', 'success')
        logging.info(f"新增供应商成功，供应商ID: {supplier.id}, 名称: {name}")

        if request.form.get('save_and_continue'):
            return redirect(url_for('supplier.add_page'))
        return redirect(url_for('supplier.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='supplier_add',
            action=f"新增供应商失败: {str(e)}",
            result="失败"
        )
        flash(f'新增供应商失败: {str(e)}', 'danger')
        logging.error(f"新增供应商失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('supplier.add_page'))


# ========== 路由：编辑供应商 ==========
@supplier_bp.route('/operations/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('supply.edit')
def edit_supplier(id):
    """编辑供应商"""
    try:
        supplier = Supplier.query.get_or_404(id)
        old_name = supplier.name

        # 获取表单数据
        new_name = request.form.get('name', '').strip()
        new_unified_social_credit_code = request.form.get('unified_social_credit_code', '').strip() or None
        new_legal_representative = request.form.get('legal_representative', '').strip() or None
        new_contact_person = request.form.get('contact_person', '').strip() or None
        new_contact_phone = request.form.get('contact_phone', '').strip() or None
        new_email = request.form.get('email', '').strip() or None
        new_address = request.form.get('address', '').strip() or None
        new_status = request.form.get('status', '启用').strip() or '启用'
        new_handler_user_id = current_user.id
        new_remark = request.form.get('remark', '').strip() or None
        new_tax_rate = request.form.get('tax_rate', '').strip() or None
        if new_tax_rate:
            try:
                new_tax_rate = float(new_tax_rate)
            except (ValueError, TypeError):
                new_tax_rate = None

        # 状态值校验
        if new_status not in ['启用', '停用']:
            new_status = '启用'

        # 必填字段校验
        if not new_name:
            flash('供应商名称不能为空', 'danger')
            return redirect(url_for('supplier.edit_page', id=id))

        # 检查名称是否重复（排除自身，仅按name查重）
        if Supplier.is_name_exists(new_name, exclude_id=id):
            flash(f'已存在供应商"{new_name}"', 'danger')
            return redirect(url_for('supplier.edit_page', id=id))

        # 记录变更
        changes = []
        if old_name != new_name:
            changes.append(f"名称: {old_name} → {new_name}")
        if supplier.unified_social_credit_code != new_unified_social_credit_code:
            changes.append(f"统一社会信用代码: {supplier.unified_social_credit_code or '无'} → {new_unified_social_credit_code or '无'}")
        if supplier.legal_representative != new_legal_representative:
            changes.append(f"法定代表人: {supplier.legal_representative or '无'} → {new_legal_representative or '无'}")
        if supplier.contact_person != new_contact_person:
            changes.append(f"联系人: {supplier.contact_person or '无'} → {new_contact_person or '无'}")
        if supplier.contact_phone != new_contact_phone:
            changes.append(f"联系电话: {supplier.contact_phone or '无'} → {new_contact_phone or '无'}")
        if supplier.email != new_email:
            changes.append(f"邮箱: {supplier.email or '无'} → {new_email or '无'}")
        if supplier.address != new_address:
            changes.append(f"地址: {supplier.address or '无'} → {new_address or '无'}")
        if supplier.status != new_status:
            changes.append(f"状态: {supplier.status} → {new_status}")
        if supplier.remark != new_remark:
            changes.append("备注已更新")
        if (supplier.tax_rate or None) != new_tax_rate:
            changes.append(f"税率: {supplier.tax_rate or '无'} → {new_tax_rate or '无'}")

        # 更新供应商信息
        supplier.name = new_name
        supplier.unified_social_credit_code = new_unified_social_credit_code
        supplier.legal_representative = new_legal_representative
        supplier.contact_person = new_contact_person
        supplier.contact_phone = new_contact_phone
        supplier.email = new_email
        supplier.address = new_address
        supplier.status = new_status
        supplier.handler_user_id = new_handler_user_id
        supplier.remark = new_remark
        supplier.tax_rate = new_tax_rate
        supplier.operator_user_id = current_user.id
        db.session.commit()

        # 记录操作记录
        change_detail = [{'field': c.split(':')[0].strip(), 'change': c} for c in changes] if changes else None
        SupplierOperationRecord.create_record(
            supplier_id=id, operation_type='edit',
            operator_id=current_user.id, operator_name=current_user.name,
            change_detail=change_detail,
            summary=f'编辑供应商: {old_name} → {new_name}，{", ".join(changes) if changes else "无变更"}'
        )

        # 记录操作日志
        change_summary = '，'.join(changes) if changes else '无变更'
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='supplier_edit',
            action=f"编辑供应商: {old_name} → {new_name}，{change_summary}",
            result="成功"
        )

        flash(f'编辑供应商成功: {new_name}', 'success')
        logging.info(f"编辑供应商成功，供应商ID: {id}, 变更: {change_summary}")
        return redirect(url_for('supplier.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='supplier_edit',
            action=f"编辑供应商失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'编辑供应商失败: {str(e)}', 'danger')
        logging.error(f"编辑供应商失败，供应商ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('supplier.index'))


# ========== 路由：删除供应商 ==========
@supplier_bp.route('/operations/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('supply.delete')
def delete_supplier(id):
    """删除供应商 - 检查使用情况，被引用时拒绝删除"""
    try:
        supplier = Supplier.query.get_or_404(id)
        supplier_name = supplier.name

        # 检查使用情况
        usage = Supplier.check_usage(id)
        if usage['used']:
            details = usage['details']
            parts = []
            if details['item_count'] > 0:
                parts.append(f"{details['item_count']}个关联物品")
            usage_detail = '、'.join(parts)
            flash(f'供应商"{supplier_name}"正在被使用（{usage_detail}），无法删除', 'danger')
            return redirect(url_for('supplier.detail', id=id))

        # 记录操作记录（删除前记录，删除后supplier_id仍可用于追溯）
        SupplierOperationRecord.create_record(
            supplier_id=id, operation_type='delete',
            operator_id=current_user.id, operator_name=current_user.name,
            summary=f'删除供应商：{supplier_name}'
        )

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='supplier_delete',
            action=f"删除供应商: {supplier_name}",
            result="成功"
        )

        # 删除供应商（级联删除操作记录）
        db.session.delete(supplier)
        db.session.commit()

        flash(f'删除供应商成功: {supplier_name}', 'success')
        logging.info(f"删除供应商成功，供应商ID: {id}, 名称: {supplier_name}")
        return redirect(url_for('supplier.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='supplier_delete',
            action=f"删除供应商失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'删除供应商失败: {str(e)}', 'danger')
        logging.error(f"删除供应商失败，供应商ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('supplier.index'))


# ========== 路由：切换供应商状态 ==========
@supplier_bp.route('/operations/toggle-status/<int:id>', methods=['POST'])
@login_required
@require_permission('supply.edit')
def toggle_supplier_status(id):
    """切换供应商启用/停用状态"""
    try:
        supplier = Supplier.query.get_or_404(id)
        old_status = supplier.status
        supplier.status = '停用' if old_status == '启用' else '启用'

        # 记录操作记录
        SupplierOperationRecord.create_record(
            supplier_id=id,
            operation_type='enable' if supplier.status == '启用' else 'disable',
            operator_id=current_user.id,
            operator_name=current_user.name,
            change_detail={'field': 'status', 'old_value': old_status, 'new_value': supplier.status},
            summary=f'供应商状态变更：{old_status} → {supplier.status}'
        )

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='supplier_toggle_status',
            action=f"供应商{supplier.name}状态变更：{old_status} → {supplier.status}",
            result="成功"
        )

        db.session.commit()
        flash(f'供应商{supplier.name}已{supplier.status}', 'success')
        logging.info(f"供应商状态变更，供应商ID: {id}, {old_status} → {supplier.status}")
        return redirect(url_for('supplier.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='supplier_toggle_status',
            action=f"切换供应商状态失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'切换供应商状态失败: {str(e)}', 'danger')
        logging.error(f"切换供应商状态失败，供应商ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('supplier.index'))


# ========== 路由：批量删除供应商 ==========
@supplier_bp.route('/operations/batch-delete', methods=['POST'])
@login_required
@require_permission('supply.delete')
def batch_delete_suppliers():
    """批量删除供应商"""
    try:
        ids = request.form.getlist('supplier_ids[]')
        if not ids:
            flash('未选择要删除的供应商', 'warning')
            return redirect(url_for('supplier.index'))

        success_count = 0
        fail_count = 0

        for id in ids:
            supplier = Supplier.query.get(int(id))
            if supplier:
                db.session.delete(supplier)
                success_count += 1
            else:
                fail_count += 1

        db.session.commit()

        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='supplier_batch_delete',
            action=f"批量删除供应商: 成功{success_count}条, 失败{fail_count}条",
            result="成功"
        )

        flash(f'批量删除完成: 成功{success_count}条, 失败{fail_count}条', 'success')
        logging.info(f"批量删除供应商，成功{success_count}条, 失败{fail_count}条")
        return redirect(url_for('supplier.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='supplier_batch_delete',
            action=f"批量删除供应商失败: {str(e)}",
            result="失败"
        )
        flash(f'批量删除失败: {str(e)}', 'danger')
        logging.error(f"批量删除供应商失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('supplier.index'))