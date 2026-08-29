from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from utils.db import db
from models.supply.supply_inventory import SupplyInventory
from models.supply.supply_inventory_detail import SupplyInventoryDetail
from models.supply.supply_item import SupplyItem
from models.supply.supply_stock_detail import SupplyStockDetail
from models.supply.storage_location import StorageLocation
from utils.log import log_operation
from utils.auth import require_permission
import logging
import traceback
from datetime import datetime, date
from .supply_inventory import supply_inventory_bp


# ========== 路由：创建盘点单 ==========
@supply_inventory_bp.route('/operations/create', methods=['POST'])
@login_required
@require_permission('supply.create')
def create_inventory():
    """创建盘点单 - 生成盘点单号，获取所有有库存的物品创建盘点明细"""
    try:
        title = request.form.get('title', '').strip()
        inventory_date_str = request.form.get('inventory_date', '').strip()
        remark = request.form.get('remark', '').strip()

        # 必填字段校验
        if not title:
            flash('盘点标题不能为空', 'danger')
            return redirect(url_for('supply_inventory.list_inventories'))

        inventory_date = _parse_date(inventory_date_str)
        if not inventory_date:
            inventory_date = date.today()

        # 生成盘点单号（支持手动指定或自动生成）
        from models.system_config import SystemConfig
        auto_number = SystemConfig.get_config_value('supply_auto_number', True)
        manual_number = request.form.get('inventory_number', '').strip() or None
        if manual_number:
            inventory_number = manual_number
        elif auto_number:
            inventory_number = SupplyInventory.generate_inventory_number()
        else:
            flash('自动编号已关闭，请手动输入盘点单号', 'danger')
            return redirect(url_for('supply_inventory.list_inventories'))

        # 获取所有有库存的库存明细（按位置分组）
        stock_details = SupplyStockDetail.query.filter(
            SupplyStockDetail.quantity > 0
        ).order_by(SupplyStockDetail.item_id, SupplyStockDetail.location_id).all()

        # 创建盘点主表
        inventory = SupplyInventory(
            inventory_number=inventory_number,
            title=title,
            inventory_date=inventory_date,
            status='进行中',
            total_count=len(stock_details),
            checked_count=0,
            normal_count=0,
            abnormal_count=0,
            remark=remark or None,
            operator_user_id=current_user.id
        )
        db.session.add(inventory)
        db.session.flush()  # 获取inventory.id

        # 创建盘点明细（每个物品+位置组合一条明细）
        for sd in stock_details:
            detail = SupplyInventoryDetail(
                inventory_id=inventory.id,
                item_id=sd.item_id,
                location_id=sd.location_id,
                inventory_result='未盘点',
                inventory_remark=None,
                actual_quantity=None,
                system_quantity=sd.quantity,
                unit_price=sd.item.unit_price if sd.item and sd.item.unit_price else 0,
                checked_by=None,
                checked_at=None
            )
            db.session.add(detail)

        db.session.commit()

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='supply_inventory',
            operation_type='inventory_create',
            action=f"创建盘点单: {inventory_number}，标题: {title}，应盘{len(stock_details)}项",
            result="成功"
        )

        flash(f'创建盘点单成功: {inventory_number}，应盘{len(stock_details)}项', 'success')
        logging.info(f"创建盘点单成功，盘点单号: {inventory_number}, 应盘: {len(stock_details)}项")
        return redirect(url_for('supply_inventory.list_inventories'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='supply_inventory',
            operation_type='inventory_create',
            action=f"创建盘点单失败: {str(e)}",
            result="失败"
        )
        flash(f'创建盘点单失败: {str(e)}', 'danger')
        logging.error(f"创建盘点单失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('supply_inventory.list_inventories'))


# ========== 路由：执行盘点 ==========
@supply_inventory_bp.route('/operations/check', methods=['POST'])
@login_required
@require_permission('supply.edit')
def check_inventory():
    """执行盘点 - 逐条确认，更新盘点明细和主表统计"""
    try:
        inventory_id = request.form.get('inventory_id', type=int)
        detail_id = request.form.get('detail_id', type=int)
        inventory_result = request.form.get('inventory_result', '').strip()
        inventory_remark = request.form.get('inventory_remark', '').strip()
        actual_quantity_str = request.form.get('actual_quantity', '').strip()

        # 参数校验
        if not inventory_id or not detail_id:
            return jsonify({'success': False, 'message': '缺少必要参数'}), 400

        if inventory_result not in ('正常', '异常'):
            return jsonify({'success': False, 'message': '盘点结果必须为"正常"或"异常"'}), 400

        # 获取盘点明细记录
        detail = SupplyInventoryDetail.query.get(detail_id)
        if not detail or detail.inventory_id != inventory_id:
            return jsonify({'success': False, 'message': '未找到对应的盘点明细记录'}), 404

        # 获取盘点主表
        inventory = SupplyInventory.query.get(inventory_id)
        if not inventory:
            return jsonify({'success': False, 'message': '未找到对应的盘点单'}), 404

        # 检查盘点状态
        if inventory.status != '进行中':
            return jsonify({'success': False, 'message': '该盘点单已结束，无法继续盘点'}), 400

        # 记录原状态
        old_result = detail.inventory_result

        # 更新盘点明细
        detail.inventory_result = inventory_result
        detail.inventory_remark = inventory_remark or None
        # 更新实盘数量
        if actual_quantity_str:
            try:
                detail.actual_quantity = int(actual_quantity_str)
            except ValueError:
                detail.actual_quantity = None
        else:
            detail.actual_quantity = None
        detail.checked_by = current_user.username if hasattr(current_user, 'username') else str(current_user.id)
        detail.checked_at = datetime.now()

        # 更新盘点主表统计
        # 如果之前未盘点，增加已盘数
        if old_result == '未盘点':
            inventory.checked_count = (inventory.checked_count or 0) + 1

        # 更新正常/异常计数
        if inventory_result == '正常':
            inventory.normal_count = (inventory.normal_count or 0) + 1
            # 如果之前是异常，减少异常计数
            if old_result == '异常':
                inventory.abnormal_count = max(0, (inventory.abnormal_count or 0) - 1)
        elif inventory_result == '异常':
            inventory.abnormal_count = (inventory.abnormal_count or 0) + 1
            # 如果之前是正常，减少正常计数
            if old_result == '正常':
                inventory.normal_count = max(0, (inventory.normal_count or 0) - 1)

        db.session.commit()

        result_text = '正常' if inventory_result == '正常' else '异常'
        logging.info(f"易耗品盘点成功，盘点单: {inventory.inventory_number}, 明细ID: {detail_id}, 结果: {inventory_result}")

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='supply_inventory',
            operation_type='inventory_check',
            action=f"执行盘点确认: 盘点单 {inventory.inventory_number}，物品 {detail.item_name}，结果 {result_text}",
            result="成功"
        )

        return jsonify({
            'success': True,
            'message': f'盘点确认成功: {detail.item_name} - {result_text}',
            'checked_count': inventory.checked_count,
            'normal_count': inventory.normal_count,
            'abnormal_count': inventory.abnormal_count
        })

    except Exception as e:
        db.session.rollback()
        logging.error(f"执行盘点失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'盘点确认失败: {str(e)}'}), 500


# ========== 路由：完成盘点 ==========
@supply_inventory_bp.route('/operations/complete/<int:id>', methods=['POST'])
@login_required
@require_permission('supply.edit')
def complete_inventory(id):
    """完成盘点 - 更新盘点状态为已完成，调整库存"""
    try:
        inventory = SupplyInventory.query.get_or_404(id)

        # 检查盘点状态
        if inventory.status != '进行中':
            flash('该盘点单不在进行中状态，无法完成', 'warning')
            return redirect(url_for('supply_inventory.list_inventories'))

        # 调用完成盘点方法（内部会调整库存和写入记录）
        result = SupplyInventory.complete(id, current_user.id)

        if result is None:
            flash('完成盘点失败', 'danger')
            return redirect(url_for('supply_inventory.list_inventories'))

        # 统计盘盈盘亏
        surplus_count = 0
        shortage_count = 0
        for detail in result.details:
            if detail.inventory_result != '未盘点' and detail.difference_quantity != 0:
                if detail.difference_quantity > 0:
                    surplus_count += 1
                else:
                    shortage_count += 1

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='supply_inventory',
            operation_type='inventory_complete',
            action=f"完成盘点单: {inventory.inventory_number}，已盘{inventory.checked_count}/{inventory.total_count}项，盘盈{surplus_count}项，盘亏{shortage_count}项",
            result="成功"
        )

        flash(f'盘点单 {inventory.inventory_number} 已完成，盘盈{surplus_count}项，盘亏{shortage_count}项', 'success')
        logging.info(f"完成盘点单，盘点单号: {inventory.inventory_number}")
        return redirect(url_for('supply_inventory.list_inventories'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='supply_inventory',
            operation_type='inventory_complete',
            action=f"完成盘点单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'完成盘点失败: {str(e)}', 'danger')
        logging.error(f"完成盘点失败，盘点ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('supply_inventory.list_inventories'))


# ========== 路由：删除盘点单 ==========
@supply_inventory_bp.route('/operations/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('supply.delete')
def delete_inventory(id):
    """删除盘点单 - 仅允许删除进行中状态的盘点单"""
    try:
        inventory = SupplyInventory.query.get_or_404(id)

        # 检查盘点状态，仅允许删除进行中的盘点单
        if inventory.status != '进行中':
            flash('仅允许删除进行中状态的盘点单', 'warning')
            return redirect(url_for('supply_inventory.list_inventories'))

        inventory_number = inventory.inventory_number
        title = inventory.title

        # 删除盘点单（级联删除明细）
        db.session.delete(inventory)
        db.session.commit()

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='supply_inventory',
            operation_type='inventory_delete',
            action=f"删除盘点单: {inventory_number}，标题: {title}",
            result="成功"
        )

        flash(f'删除盘点单成功: {inventory_number}', 'success')
        logging.info(f"删除盘点单成功，盘点单号: {inventory_number}")
        return redirect(url_for('supply_inventory.list_inventories'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='supply_inventory',
            operation_type='inventory_delete',
            action=f"删除盘点单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'删除盘点单失败: {str(e)}', 'danger')
        logging.error(f"删除盘点单失败，盘点ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('supply_inventory.list_inventories'))


# ========== 工具函数 ==========
def _parse_date(date_str):
    """将日期字符串转换为date对象，空字符串返回None"""
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
    except ValueError:
        logging.warning(f"日期格式无效: {date_str}")
        return None