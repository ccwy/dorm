from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from utils.db import db
from models.supply.supply_item import SupplyItem
from models.supply.supplier import Supplier
from models.supply.storage_location import StorageLocation
from utils.log import log_operation
from utils.auth import require_permission
import logging
import traceback
from datetime import datetime
from .supply_item import supply_item_bp


# ========== 路由：新增物品 ==========
@supply_item_bp.route('/operations/add', methods=['POST'])
@login_required
@require_permission('supply_item.create')
def add_supply_item():
    """新增物品"""
    try:
        name = request.form.get('name', '').strip()
        category = request.form.get('category', '').strip() or None
        specification = request.form.get('specification', '').strip() or None
        brand = request.form.get('brand', '').strip() or None
        unit = request.form.get('unit', '').strip() or None
        supplier_id = request.form.get('supplier_id', type=int)
        unit_price = request.form.get('unit_price', 0, type=float)
        reference_price = request.form.get('reference_price', type=float)
        min_stock = request.form.get('min_stock', 0, type=int)
        # 如果未提供min_stock，使用系统配置的默认值
        if min_stock == 0 and not request.form.get('min_stock'):
            from models.system_config.system_config import SystemConfig
            min_stock = SystemConfig.get_config_value('supply_default_min_stock', 0)
        max_stock = request.form.get('max_stock', type=int)
        status = request.form.get('status', '启用').strip() or '启用'
        remark = request.form.get('remark', '').strip() or None
        item_number = request.form.get('item_number', '').strip() or None  # 手动编号（可选）

        # 必填字段校验
        if not name:
            flash('物品名称不能为空', 'danger')
            return redirect(url_for('supply_item.add_page'))

        # 状态值校验
        if status not in ['启用', '停用']:
            status = '启用'

        # 检查手动编号是否重复
        if item_number and SupplyItem.query.filter_by(item_number=item_number).first():
            flash(f'物品编号"{item_number}"已存在', 'danger')
            return redirect(url_for('supply_item.add_page'))

        try:
            item = SupplyItem.create(
                name=name, category=category, specification=specification,
                brand=brand, unit=unit, supplier_id=supplier_id, unit_price=unit_price,
                reference_price=reference_price, min_stock=min_stock,
                max_stock=max_stock, status=status,
                remark=remark, operator_user_id=current_user.id,
                item_number=item_number
            )
        except ValueError as e:
            flash(str(e), 'danger')
            return redirect(url_for('supply_item.add_page'))

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='supply_item_add',
            action=f"新增物品: {name}（{item.item_number}）",
            result="成功"
        )

        flash(f'新增物品成功: {name}（{item.item_number}）', 'success')
        logging.info(f"新增物品成功，物品ID: {item.id}, 名称: {name}, 编号: {item.item_number}")

        if request.form.get('save_and_continue'):
            return redirect(url_for('supply_item.add_page'))
        return redirect(url_for('supply_item.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='supply_item_add',
            action=f"新增物品失败: {str(e)}",
            result="失败"
        )
        flash(f'新增物品失败: {str(e)}', 'danger')
        logging.error(f"新增物品失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('supply_item.add_page'))


# ========== 路由：编辑物品 ==========
@supply_item_bp.route('/operations/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('supply_item.edit')
def edit_supply_item(id):
    """编辑物品"""
    try:
        item = SupplyItem.query.get_or_404(id)
        old_name = item.name

        # 获取表单数据
        new_name = request.form.get('name', '').strip()
        new_category = request.form.get('category', '').strip() or None
        new_specification = request.form.get('specification', '').strip() or None
        new_brand = request.form.get('brand', '').strip() or None
        new_unit = request.form.get('unit', '').strip() or None
        new_supplier_id = request.form.get('supplier_id', type=int)
        new_unit_price = request.form.get('unit_price', 0, type=float)
        new_reference_price = request.form.get('reference_price', type=float)
        new_min_stock = request.form.get('min_stock', 0, type=int)
        new_max_stock = request.form.get('max_stock', type=int)
        new_status = request.form.get('status', '启用').strip() or '启用'
        new_remark = request.form.get('remark', '').strip() or None

        # 状态值校验
        if new_status not in ['启用', '停用']:
            new_status = '启用'

        # 必填字段校验
        if not new_name:
            flash('物品名称不能为空', 'danger')
            return redirect(url_for('supply_item.edit_page', id=id))

        # 记录变更
        changes = []
        if old_name != new_name:
            changes.append(f"名称: {old_name} → {new_name}")
        if item.category != new_category:
            changes.append(f"分类: {item.category or '无'} → {new_category or '无'}")
        if item.specification != new_specification:
            changes.append(f"规格型号: {item.specification or '无'} → {new_specification or '无'}")
        if item.brand != new_brand:
            changes.append(f"品牌: {item.brand or '无'} → {new_brand or '无'}")
        if item.unit != new_unit:
            changes.append(f"计量单位: {item.unit or '无'} → {new_unit or '无'}")
        if item.supplier_id != new_supplier_id:
            changes.append("默认供应商已更新")
        if item.unit_price != new_unit_price:
            changes.append(f"单价: {item.unit_price} → {new_unit_price}")
        if item.min_stock != new_min_stock:
            changes.append(f"最低库存: {item.min_stock} → {new_min_stock}")
        if item.max_stock != new_max_stock:
            changes.append(f"最高库存: {item.max_stock or '无'} → {new_max_stock or '无'}")
        if item.status != new_status:
            changes.append(f"状态: {item.status} → {new_status}")
        if item.remark != new_remark:
            changes.append("备注已更新")

        # 更新物品信息
        item.name = new_name
        item.category = new_category
        item.specification = new_specification
        item.brand = new_brand
        item.unit = new_unit
        item.supplier_id = new_supplier_id
        item.unit_price = new_unit_price
        item.reference_price = new_reference_price
        item.min_stock = new_min_stock
        item.max_stock = new_max_stock
        item.status = new_status
        item.remark = new_remark
        item.operator_user_id = current_user.id
        db.session.commit()

        # 记录操作日志
        change_summary = '，'.join(changes) if changes else '无变更'
        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='supply_item_edit',
            action=f"编辑物品: {old_name} → {new_name}，{change_summary}",
            result="成功"
        )

        flash(f'编辑物品成功: {new_name}', 'success')
        logging.info(f"编辑物品成功，物品ID: {id}, 变更: {change_summary}")
        return redirect(url_for('supply_item.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='supply_item_edit',
            action=f"编辑物品失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'编辑物品失败: {str(e)}', 'danger')
        logging.error(f"编辑物品失败，物品ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('supply_item.index'))


# ========== 路由：删除物品 ==========
@supply_item_bp.route('/operations/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('supply_item.delete')
def delete_supply_item(id):
    """删除物品 - 检查使用情况，被引用时拒绝删除"""
    try:
        item = SupplyItem.query.get_or_404(id)
        item_name = item.name
        item_number = item.item_number

        # 检查使用情况
        usage = SupplyItem.check_usage(id)
        if usage['used']:
            details = usage['details']
            parts = []
            if details.get('stock_detail_count', 0) > 0:
                parts.append(f"{details['stock_detail_count']}条库存明细")
            if details.get('stock_in_count', 0) > 0:
                parts.append(f"{details['stock_in_count']}条入库明细")
            if details.get('stock_out_count', 0) > 0:
                parts.append(f"{details['stock_out_count']}条出库明细")
            usage_detail = '、'.join(parts)
            flash(f'物品"{item_name}"正在被使用（{usage_detail}），无法删除', 'danger')
            return redirect(url_for('supply_item.detail', id=id))

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='supply_item_delete',
            action=f"删除物品: {item_name}（{item_number}）",
            result="成功"
        )

        # 删除物品（级联删除库存明细）
        db.session.delete(item)
        db.session.commit()

        flash(f'删除物品成功: {item_name}（{item_number}）', 'success')
        logging.info(f"删除物品成功，物品ID: {id}, 名称: {item_name}, 编号: {item_number}")
        return redirect(url_for('supply_item.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='supply_item_delete',
            action=f"删除物品失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'删除物品失败: {str(e)}', 'danger')
        logging.error(f"删除物品失败，物品ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('supply_item.index'))


# ========== 路由：重新计算物品总库存 ==========
@supply_item_bp.route('/operations/recalculate-stock/<int:id>', methods=['POST'])
@login_required
@require_permission('supply_item.edit')
def recalculate_item_stock(id):
    """重新计算物品总库存"""
    try:
        item = SupplyItem.query.get_or_404(id)
        old_stock = item.current_stock
        item = SupplyItem.recalculate_stock(id)

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='supply_item_recalculate_stock',
            action=f"重新计算物品库存: {item.name}，{old_stock} → {item.current_stock}",
            result="成功"
        )

        flash(f'物品"{item.name}"总库存已重新计算: {old_stock} → {item.current_stock}', 'success')
        logging.info(f"重新计算物品库存，物品ID: {id}, {old_stock} → {item.current_stock}")
        return redirect(url_for('supply_item.detail', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='supply_item_recalculate_stock',
            action=f"重新计算物品库存失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'重新计算库存失败: {str(e)}', 'danger')
        logging.error(f"重新计算物品库存失败，物品ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('supply_item.detail', id=id))


# ========== 路由：批量删除物品 ==========
@supply_item_bp.route('/operations/batch-delete', methods=['POST'])
@login_required
@require_permission('supply_item.delete')
def batch_delete_supply_items():
    """批量删除物品"""
    try:
        ids = request.form.getlist('item_ids[]')
        if not ids:
            flash('未选择要删除的物品', 'warning')
            return redirect(url_for('supply_item.index'))

        success_count = 0
        fail_count = 0

        for id in ids:
            item = SupplyItem.query.get(int(id))
            if item:
                db.session.delete(item)
                success_count += 1
            else:
                fail_count += 1

        db.session.commit()

        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='supply_item_batch_delete',
            action=f"批量删除物品: 成功{success_count}条, 失败{fail_count}条",
            result="成功"
        )

        flash(f'批量删除完成: 成功{success_count}条, 失败{fail_count}条', 'success')
        logging.info(f"批量删除物品，成功{success_count}条, 失败{fail_count}条")
        return redirect(url_for('supply_item.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='supply_item_batch_delete',
            action=f"批量删除物品失败: {str(e)}",
            result="失败"
        )
        flash(f'批量删除失败: {str(e)}', 'danger')
        logging.error(f"批量删除物品失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('supply_item.index'))