from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from utils.db import db
from models.supply.stock_in import StockIn
from models.supply.stock_in_detail import StockInDetail
from models.supply.supplier import Supplier
from models.supply.supply_item import SupplyItem
from models.supply.storage_location import StorageLocation
from models.system_config import SystemConfig
from utils.log import log_operation
from utils.auth import require_permission
import logging
import traceback
from datetime import datetime
from .stock_in import stock_in_bp


# ========== 路由：新增入库单 ==========
@stock_in_bp.route('/operations/add', methods=['POST'])
@login_required
@require_permission('supply.create')
def create_stock_in():
    """新增入库单"""
    try:
        # 收集主表数据
        stock_in_type = request.form.get('stock_in_type', '').strip()
        stock_in_date_str = request.form.get('stock_in_date', '').strip()
        supplier_id = request.form.get('supplier_id', type=int) or None
        supplier_name = request.form.get('supplier_name', '').strip()
        handler_user_id = current_user.id
        remark = request.form.get('remark', '').strip() or None
        stock_in_number = request.form.get('stock_in_number', '').strip() or None  # 手动编号（可选）

        # 如果没有supplier_id但有supplier_name，尝试查找或创建供应商
        if not supplier_id and supplier_name:
            existing = Supplier.query.filter_by(name=supplier_name).first()
            if existing:
                supplier_id = existing.id
            else:
                new_supplier = Supplier.create(
                    name=supplier_name,
                    status='启用',
                    handler_user_id=current_user.id,
                    operator_user_id=current_user.id
                )
                supplier_id = new_supplier.id

        # 必填字段校验
        if not stock_in_type:
            flash('入库类型不能为空', 'danger')
            return redirect(url_for('stock_in.add_stock_in'))
        if not stock_in_date_str:
            flash('入库日期不能为空', 'danger')
            return redirect(url_for('stock_in.add_stock_in'))

        # 解析入库日期
        try:
            stock_in_date = datetime.strptime(stock_in_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('入库日期格式不正确', 'danger')
            return redirect(url_for('stock_in.add_stock_in'))

        # 收集明细数据（从前端JS动态添加的明细行）
        items = request.form.getlist('items[]')
        if not items:
            # 尝试从JSON格式获取
            import json
            items_json = request.form.get('items_json', '')
            if items_json:
                try:
                    items = json.loads(items_json)
                except json.JSONDecodeError:
                    items = []
            else:
                items = []

        if not items:
            flash('请至少添加一条入库明细', 'danger')
            return redirect(url_for('stock_in.add_stock_in'))

        # 创建入库主表
        try:
            stock_in = StockIn.create(
                stock_in_type=stock_in_type,
                stock_in_date=stock_in_date,
                supplier_id=supplier_id,
                handler_user_id=handler_user_id,
                remark=remark,
                operator_user_id=current_user.id,
                stock_in_number=stock_in_number
            )
        except ValueError as e:
            flash(str(e), 'danger')
            return redirect(url_for('stock_in.add_stock_in'))

        # 创建明细
        for item_data in items:
            if isinstance(item_data, str):
                import json
                try:
                    item_data = json.loads(item_data)
                except json.JSONDecodeError:
                    continue

            item_id = item_data.get('item_id', type=int) if not isinstance(item_data, dict) else int(item_data.get('item_id', 0))
            location_id = int(item_data.get('location_id', 0)) if isinstance(item_data, dict) else request.form.get('location_id', type=int)
            quantity = int(item_data.get('quantity', 0)) if isinstance(item_data, dict) else int(item_data.get('quantity', 0))
            unit_price = float(item_data.get('unit_price', 0)) if isinstance(item_data, dict) else float(item_data.get('unit_price', 0))
            item_name = item_data.get('item_name', '') if isinstance(item_data, dict) else ''
            item_number = item_data.get('item_number', '') if isinstance(item_data, dict) else ''
            specification = item_data.get('specification', '') if isinstance(item_data, dict) else ''
            location_name = item_data.get('location_name', '') if isinstance(item_data, dict) else ''
            unit = item_data.get('unit', '') if isinstance(item_data, dict) else ''
            detail_remark = item_data.get('remark', '') if isinstance(item_data, dict) else ''

            # 验证：物品和位置至少有id或name之一
            if (not item_id and not item_name) or (not location_id and not location_name) or quantity <= 0:
                continue

            # 延迟创建：如果item_id为空但item_name有值，查找或创建物品
            if not item_id and item_name:
                existing_item = SupplyItem.query.filter_by(name=item_name).first()
                if existing_item:
                    item_id = existing_item.id
                    # 使用已有物品的规格/单位（如果表单未提供）
                    if not specification:
                        specification = existing_item.specification or ''
                    if not unit:
                        unit = existing_item.unit or ''
                else:
                    new_item = SupplyItem.create(
                        name=item_name,
                        item_number=item_number.strip() if item_number and item_number.strip() else None,
                        category='低值易耗品',
                        specification=specification if specification else None,
                        unit=unit if unit else None,
                        supplier_id=supplier_id,
                        unit_price=unit_price,
                        min_stock=SystemConfig.get_config_value('supply_default_min_stock', 0),
                        status='启用',
                        operator_user_id=current_user.id
                    )
                    item_id = new_item.id

            # 延迟创建：如果location_id为空但location_name有值，查找或创建位置
            if not location_id and location_name:
                existing_location = StorageLocation.query.filter_by(name=location_name, usage_type='低值易耗品').first()
                if existing_location:
                    location_id = existing_location.id
                else:
                    new_location = StorageLocation.create(
                        name=location_name,
                        status='启用',
                        usage_type='低值易耗品',
                        handler_user_id=current_user.id,
                        operator_user_id=current_user.id
                    )
                    location_id = new_location.id

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

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='stock_in_add',
            action=f"新增入库单: {stock_in.stock_in_number}",
            result="成功"
        )

        # 检查入库单审核开关：未启用审核时保存即自动审核
        approval_enabled = SystemConfig.get_config_value('STOCK_IN_APPROVAL_ENABLED', True)
        if not approval_enabled:
            try:
                StockIn.approve(stock_in.id, current_user.id)
                flash(f'新增入库单成功: {stock_in.stock_in_number}（已自动审核）', 'success')
                logging.info(f"入库单自动审核，入库单ID: {stock_in.id}, 单号: {stock_in.stock_in_number}")
            except Exception as auto_approve_err:
                flash(f'新增入库单成功: {stock_in.stock_in_number}（自动审核失败: {str(auto_approve_err)}）', 'warning')
                logging.warning(f"入库单自动审核失败，入库单ID: {stock_in.id}, 错误: {str(auto_approve_err)}")
        else:
            flash(f'新增入库单成功: {stock_in.stock_in_number}', 'success')

        logging.info(f"新增入库单成功，入库单ID: {stock_in.id}, 单号: {stock_in.stock_in_number}")

        if request.form.get('save_and_continue'):
            return redirect(url_for('stock_in.add_stock_in'))
        return redirect(url_for('stock_in.list_stock_ins'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='stock_in_add',
            action=f"新增入库单失败: {str(e)}",
            result="失败"
        )
        flash(f'新增入库单失败: {str(e)}', 'danger')
        logging.error(f"新增入库单失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('stock_in.add_stock_in'))


# ========== 路由：编辑入库单 ==========
@stock_in_bp.route('/operations/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('supply.edit')
def update_stock_in(id):
    """编辑入库单（仅待审核状态可编辑）"""
    try:
        stock_in = StockIn.query.get_or_404(id)

        # 仅待审核状态可编辑
        if stock_in.status != '待审核':
            flash('仅待审核状态的入库单可以编辑', 'warning')
            return redirect(url_for('stock_in.detail_stock_in', id=id))

        # 收集主表数据
        stock_in_type = request.form.get('stock_in_type', '').strip()
        stock_in_date_str = request.form.get('stock_in_date', '').strip()
        supplier_id = request.form.get('supplier_id', type=int) or None
        supplier_name = request.form.get('supplier_name', '').strip()
        handler_user_id = current_user.id
        remark = request.form.get('remark', '').strip() or None
        stock_in_number = request.form.get('stock_in_number', '').strip() or None  # 手动编号（可选）

        # 如果没有supplier_id但有supplier_name，尝试查找或创建供应商
        if not supplier_id and supplier_name:
            existing = Supplier.query.filter_by(name=supplier_name).first()
            if existing:
                supplier_id = existing.id
            else:
                new_supplier = Supplier.create(
                    name=supplier_name,
                    status='启用',
                    handler_user_id=current_user.id,
                    operator_user_id=current_user.id
                )
                supplier_id = new_supplier.id

        # 必填字段校验
        if not stock_in_type:
            flash('入库类型不能为空', 'danger')
            return redirect(url_for('stock_in.edit_stock_in', id=id))
        if not stock_in_date_str:
            flash('入库日期不能为空', 'danger')
            return redirect(url_for('stock_in.edit_stock_in', id=id))

        # 解析入库日期
        try:
            stock_in_date = datetime.strptime(stock_in_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('入库日期格式不正确', 'danger')
            return redirect(url_for('stock_in.edit_stock_in', id=id))

        # 更新主表
        stock_in.stock_in_type = stock_in_type
        stock_in.stock_in_date = stock_in_date
        stock_in.supplier_id = supplier_id
        stock_in.handler_user_id = handler_user_id
        stock_in.remark = remark
        stock_in.operator_user_id = current_user.id

        # 删除旧明细
        StockInDetail.query.filter_by(stock_in_id=id).delete()

        # 创建新明细
        items = request.form.getlist('items[]')
        if not items:
            import json
            items_json = request.form.get('items_json', '')
            if items_json:
                try:
                    items = json.loads(items_json)
                except json.JSONDecodeError:
                    items = []
            else:
                items = []

        for item_data in items:
            if isinstance(item_data, str):
                try:
                    item_data = json.loads(item_data)
                except (json.JSONDecodeError, TypeError):
                    continue

            if not isinstance(item_data, dict):
                continue

            item_id = int(item_data.get('item_id', 0))
            location_id = int(item_data.get('location_id', 0))
            quantity = int(item_data.get('quantity', 0))
            unit_price = float(item_data.get('unit_price', 0))
            item_name = item_data.get('item_name', '')
            item_number = item_data.get('item_number', '')
            specification = item_data.get('specification', '')
            location_name = item_data.get('location_name', '')
            unit = item_data.get('unit', '')
            detail_remark = item_data.get('remark', '')

            # 验证：物品和位置至少有id或name之一
            if (not item_id and not item_name) or (not location_id and not location_name) or quantity <= 0:
                continue

            # 延迟创建：如果item_id为空但item_name有值，查找或创建物品
            if not item_id and item_name:
                existing_item = SupplyItem.query.filter_by(name=item_name).first()
                if existing_item:
                    item_id = existing_item.id
                    # 使用已有物品的规格/单位（如果表单未提供）
                    if not specification:
                        specification = existing_item.specification or ''
                    if not unit:
                        unit = existing_item.unit or ''
                else:
                    new_item = SupplyItem.create(
                        name=item_name,
                        item_number=item_number.strip() if item_number and item_number.strip() else None,
                        category='低值易耗品',
                        specification=specification if specification else None,
                        unit=unit if unit else None,
                        supplier_id=supplier_id,
                        unit_price=unit_price,
                        min_stock=SystemConfig.get_config_value('supply_default_min_stock', 0),
                        status='启用',
                        operator_user_id=current_user.id
                    )
                    item_id = new_item.id

            # 延迟创建：如果location_id为空但location_name有值，查找或创建位置
            if not location_id and location_name:
                existing_location = StorageLocation.query.filter_by(name=location_name, usage_type='低值易耗品').first()
                if existing_location:
                    location_id = existing_location.id
                else:
                    new_location = StorageLocation.create(
                        name=location_name,
                        status='启用',
                        usage_type='低值易耗品',
                        handler_user_id=current_user.id,
                        operator_user_id=current_user.id
                    )
                    location_id = new_location.id

            StockInDetail.create(
                stock_in_id=id,
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
        StockIn.recalculate_total_amount(id)

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='stock_in_edit',
            action=f"编辑入库单: {stock_in.stock_in_number}",
            result="成功"
        )

        # 检查入库单审核开关：未启用审核时保存即自动审核
        approval_enabled = SystemConfig.get_config_value('STOCK_IN_APPROVAL_ENABLED', True)
        if not approval_enabled:
            try:
                StockIn.approve(id, current_user.id)
                flash(f'编辑入库单成功: {stock_in.stock_in_number}（已自动审核）', 'success')
                logging.info(f"入库单自动审核，入库单ID: {id}, 单号: {stock_in.stock_in_number}")
            except Exception as auto_approve_err:
                flash(f'编辑入库单成功: {stock_in.stock_in_number}（自动审核失败: {str(auto_approve_err)}）', 'warning')
                logging.warning(f"入库单自动审核失败，入库单ID: {id}, 错误: {str(auto_approve_err)}")
        else:
            flash(f'编辑入库单成功: {stock_in.stock_in_number}', 'success')

        logging.info(f"编辑入库单成功，入库单ID: {id}, 单号: {stock_in.stock_in_number}")
        return redirect(url_for('stock_in.list_stock_ins'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='stock_in_edit',
            action=f"编辑入库单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'编辑入库单失败: {str(e)}', 'danger')
        logging.error(f"编辑入库单失败，入库单ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('stock_in.list_stock_ins'))


# ========== 路由：删除入库单 ==========
@stock_in_bp.route('/operations/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('supply.delete')
def delete_stock_in(id):
    """删除入库单（仅待审核状态可删除）"""
    try:
        stock_in = StockIn.query.get_or_404(id)
        stock_in_number = stock_in.stock_in_number

        # 仅待审核状态可删除
        if stock_in.status != '待审核':
            flash('仅待审核状态的入库单可以删除', 'danger')
            return redirect(url_for('stock_in.detail_stock_in', id=id))

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='stock_in_delete',
            action=f"删除入库单: {stock_in_number}",
            result="成功"
        )

        # 删除入库单（级联删除明细）
        db.session.delete(stock_in)
        db.session.commit()

        flash(f'删除入库单成功: {stock_in_number}', 'success')
        logging.info(f"删除入库单成功，入库单ID: {id}, 单号: {stock_in_number}")
        return redirect(url_for('stock_in.list_stock_ins'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='stock_in_delete',
            action=f"删除入库单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'删除入库单失败: {str(e)}', 'danger')
        logging.error(f"删除入库单失败，入库单ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('stock_in.list_stock_ins'))


# ========== 路由：审核入库单 ==========
@stock_in_bp.route('/operations/approve/<int:id>', methods=['POST'])
@login_required
@require_permission('supply.approve')
def approve_stock_in(id):
    """审核入库单"""
    try:
        stock_in = StockIn.query.get_or_404(id)
        review_remark = request.form.get('review_remark', '').strip() or None

        # 调用审核方法（内部会自动更新库存和写入进出库记录）
        result = StockIn.approve(id, current_user.id, review_remark)

        if result is None:
            flash('审核失败，入库单不存在或状态不是待审核', 'danger')
            return redirect(url_for('stock_in.detail_stock_in', id=id))

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='stock_in_approve',
            action=f"审核入库单: {stock_in.stock_in_number}",
            result="成功"
        )

        flash(f'审核入库单成功: {stock_in.stock_in_number}，库存已更新', 'success')
        logging.info(f"审核入库单成功，入库单ID: {id}, 单号: {stock_in.stock_in_number}")
        return redirect(url_for('stock_in.detail_stock_in', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='stock_in_approve',
            action=f"审核入库单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'审核入库单失败: {str(e)}', 'danger')
        logging.error(f"审核入库单失败，入库单ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('stock_in.detail_stock_in', id=id))


# ========== 路由：反审核入库单 ==========
@stock_in_bp.route('/operations/unapprove/<int:id>', methods=['POST'])
@login_required
@require_permission('supply.unapprove')
def unapprove_stock_in(id):
    """反审核入库单（仅已审核状态可反审核，反审核后状态变为待审核，库存回滚）"""
    try:
        # 检查系统配置是否允许反审核
        from models.system_config import SystemConfig
        unapprove_enabled = SystemConfig.get_config_value('STOCK_IN_UNAPPROVE_ENABLED', True)
        if not unapprove_enabled:
            flash('入库单反审核功能已关闭，请联系管理员开启', 'warning')
            return redirect(url_for('stock_in.detail_stock_in', id=id))

        stock_in = StockIn.query.get_or_404(id)

        # 调用反审核方法（内部会自动回滚库存和删除进出库记录）
        result = StockIn.unapprove(id, current_user.id)

        if result is None:
            flash('反审核失败，入库单不存在或状态不是已审核', 'danger')
            return redirect(url_for('stock_in.detail_stock_in', id=id))

        # 检查是否库存不足
        if isinstance(result, dict) and 'error' in result:
            insufficient_items = result.get('details', [])
            error_msg = result.get('error', '库存不足，无法反审核')
            detail_msgs = []
            for item in insufficient_items:
                detail_msgs.append(
                    f"{item.get('item_name', '未知')}（{item.get('location_name', '未知位置')}）"
                    f"：当前库存{item.get('available', 0)}，需扣减{item.get('required', 0)}"
                )
            flash(f'{error_msg}：' + '；'.join(detail_msgs), 'danger')
            logging.warning(f"反审核入库单库存不足，入库单ID: {id}, 单号: {stock_in.stock_in_number}")
            return redirect(url_for('stock_in.detail_stock_in', id=id))

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='stock_in_unapprove',
            action=f"反审核入库单: {stock_in.stock_in_number}",
            result="成功"
        )

        flash(f'反审核入库单成功: {stock_in.stock_in_number}，库存已回滚，可重新编辑', 'success')
        logging.info(f"反审核入库单成功，入库单ID: {id}, 单号: {stock_in.stock_in_number}")
        return redirect(url_for('stock_in.detail_stock_in', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='stock_in_unapprove',
            action=f"反审核入库单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'反审核入库单失败: {str(e)}', 'danger')
        logging.error(f"反审核入库单失败，入库单ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('stock_in.detail_stock_in', id=id))


# ========== 路由：取消入库单 ==========
@stock_in_bp.route('/operations/cancel/<int:id>', methods=['POST'])
@login_required
@require_permission('supply.edit')
def cancel_stock_in(id):
    """取消入库单（仅待审核状态可取消）"""
    try:
        stock_in = StockIn.query.get_or_404(id)

        # 调用取消方法
        result = StockIn.cancel(id, current_user.id)

        if result is None:
            flash('取消失败，入库单不存在或状态不是待审核', 'danger')
            return redirect(url_for('stock_in.detail_stock_in', id=id))

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='stock_in_cancel',
            action=f"取消入库单: {stock_in.stock_in_number}",
            result="成功"
        )

        flash(f'取消入库单成功: {stock_in.stock_in_number}', 'success')
        logging.info(f"取消入库单成功，入库单ID: {id}, 单号: {stock_in.stock_in_number}")
        return redirect(url_for('stock_in.detail_stock_in', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='stock_in_cancel',
            action=f"取消入库单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'取消入库单失败: {str(e)}', 'danger')
        logging.error(f"取消入库单失败，入库单ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('stock_in.detail_stock_in', id=id))


# ========== 路由：批量删除入库单 ==========
@stock_in_bp.route('/operations/batch-delete', methods=['POST'])
@login_required
@require_permission('supply.delete')
def batch_delete_stock_ins():
    """批量删除入库单（仅待审核状态可删除）"""
    try:
        ids = request.form.getlist('stock_in_ids[]')
        if not ids:
            flash('未选择要删除的入库单', 'warning')
            return redirect(url_for('stock_in.list_stock_ins'))

        success_count = 0
        fail_count = 0

        for id in ids:
            stock_in = StockIn.query.get(int(id))
            if stock_in and stock_in.status == '待审核':
                db.session.delete(stock_in)
                success_count += 1
            else:
                fail_count += 1

        db.session.commit()

        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='stock_in_batch_delete',
            action=f"批量删除入库单: 成功{success_count}条, 失败{fail_count}条",
            result="成功"
        )

        flash(f'批量删除完成: 成功{success_count}条, 失败{fail_count}条', 'success')
        logging.info(f"批量删除入库单，成功{success_count}条, 失败{fail_count}条")
        return redirect(url_for('stock_in.list_stock_ins'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='stock_in_batch_delete',
            action=f"批量删除入库单失败: {str(e)}",
            result="失败"
        )
        flash(f'批量删除失败: {str(e)}', 'danger')
        logging.error(f"批量删除入库单失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('stock_in.list_stock_ins'))