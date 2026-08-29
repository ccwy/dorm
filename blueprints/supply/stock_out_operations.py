from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from utils.db import db
from models.supply.stock_out import StockOut
from models.supply.stock_out_detail import StockOutDetail
from models.supply.supply_item import SupplyItem
from models.supply.storage_location import StorageLocation
from utils.log import log_operation
from utils.auth import admin_required
import logging
import traceback
from datetime import datetime
from .stock_out import stock_out_bp


# ========== 路由：新增出库单 ==========
@stock_out_bp.route('/operations/add', methods=['POST'])
@login_required
@admin_required
def create_stock_out():
    """新增出库单"""
    try:
        # 收集主表数据
        stock_out_type = request.form.get('stock_out_type', '').strip()
        stock_out_date_str = request.form.get('stock_out_date', '').strip()
        recipient_user_id = request.form.get('recipient_user_id', type=int) or None
        recipient_name = request.form.get('recipient_name', '').strip()
        department_id = request.form.get('department_id', type=int) or None
        department_name = request.form.get('department_name', '').strip()
        handler_user_id = current_user.id
        remark = request.form.get('remark', '').strip() or None
        stock_out_number = request.form.get('stock_out_number', '').strip() or None  # 手动编号（可选）

        # 处理领用人：如果没选系统用户但有自定义输入，尝试按名称查找
        if not recipient_user_id and recipient_name:
            from models.user import User
            existing_user = User.query.filter(User.name == recipient_name).first()
            if existing_user:
                recipient_user_id = existing_user.id

        # 处理部门：如果没选系统部门但有自定义输入，尝试按名称查找
        if not department_id and department_name:
            from models.department import Department
            existing_dept = Department.query.filter(Department.name == department_name).first()
            if existing_dept:
                department_id = existing_dept.id

        # 必填字段校验
        if not stock_out_type:
            flash('出库类型不能为空', 'danger')
            return redirect(url_for('stock_out.add_stock_out'))
        if not stock_out_date_str:
            flash('出库日期不能为空', 'danger')
            return redirect(url_for('stock_out.add_stock_out'))

        # 解析出库日期
        try:
            stock_out_date = datetime.strptime(stock_out_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('出库日期格式不正确', 'danger')
            return redirect(url_for('stock_out.add_stock_out'))

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
            flash('请至少添加一条出库明细', 'danger')
            return redirect(url_for('stock_out.add_stock_out'))

        # 创建出库主表
        try:
            stock_out = StockOut.create(
                stock_out_type=stock_out_type,
                stock_out_date=stock_out_date,
                recipient_user_id=recipient_user_id,
                department_id=department_id,
                handler_user_id=handler_user_id,
                remark=remark,
                operator_user_id=current_user.id,
                stock_out_number=stock_out_number
            )
        except ValueError as e:
            flash(str(e), 'danger')
            return redirect(url_for('stock_out.add_stock_out'))

        # 创建明细
        for item_data in items:
            if isinstance(item_data, str):
                import json
                try:
                    item_data = json.loads(item_data)
                except json.JSONDecodeError:
                    continue

            if not isinstance(item_data, dict):
                continue

            item_id = int(item_data.get('item_id', 0))
            location_id = int(item_data.get('location_id', 0))
            quantity = int(item_data.get('quantity', 0))
            unit_price = float(item_data.get('unit_price', 0))
            item_name = item_data.get('item_name', '')
            specification = item_data.get('specification', '')
            location_name = item_data.get('location_name', '')
            unit = item_data.get('unit', '')
            detail_remark = item_data.get('remark', '')

            if not item_id or not location_id or quantity <= 0:
                continue

            StockOutDetail.create(
                stock_out_id=stock_out.id,
                item_id=item_id,
                item_name=item_name,
                specification=specification if specification else None,
                unit=unit if unit else None,
                location_id=location_id,
                location_name=location_name,
                quantity=quantity,
                unit_price=unit_price,
                remark=detail_remark if detail_remark else None,
                operator_user_id=current_user.id
            )

        # 重新计算总金额
        StockOut.recalculate_total_amount(stock_out.id)

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='stock_out_add',
            action=f"新增出库单: {stock_out.stock_out_number}",
            result="成功"
        )

        # 检查出库单审核开关：未启用审核时保存即自动审核
        from models.system_config import SystemConfig
        approval_enabled = SystemConfig.get_config_value('STOCK_OUT_APPROVAL_ENABLED', True)
        if not approval_enabled:
            try:
                StockOut.approve(stock_out.id, current_user.id)
                flash(f'新增出库单成功: {stock_out.stock_out_number}（已自动审核）', 'success')
                logging.info(f"出库单自动审核，出库单ID: {stock_out.id}, 单号: {stock_out.stock_out_number}")
            except Exception as auto_approve_err:
                flash(f'新增出库单成功: {stock_out.stock_out_number}（自动审核失败: {str(auto_approve_err)}）', 'warning')
                logging.warning(f"出库单自动审核失败，出库单ID: {stock_out.id}, 错误: {str(auto_approve_err)}")
        else:
            flash(f'新增出库单成功: {stock_out.stock_out_number}', 'success')

        logging.info(f"新增出库单成功，出库单ID: {stock_out.id}, 单号: {stock_out.stock_out_number}")

        if request.form.get('action') == 'continue':
            return redirect(url_for('stock_out.add_stock_out'))
        return redirect(url_for('stock_out.list_stock_outs'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='stock_out_add',
            action=f"新增出库单失败: {str(e)}",
            result="失败"
        )
        flash(f'新增出库单失败: {str(e)}', 'danger')
        logging.error(f"新增出库单失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('stock_out.add_stock_out'))


# ========== 路由：编辑出库单 ==========
@stock_out_bp.route('/operations/edit/<int:id>', methods=['POST'])
@login_required
@admin_required
def update_stock_out(id):
    """编辑出库单（仅待审核状态可编辑）"""
    try:
        stock_out = StockOut.query.get_or_404(id)

        # 仅待审核状态可编辑
        if stock_out.status != '待审核':
            flash('仅待审核状态的出库单可以编辑', 'warning')
            return redirect(url_for('stock_out.detail_stock_out', id=id))

        # 收集主表数据
        stock_out_type = request.form.get('stock_out_type', '').strip()
        stock_out_date_str = request.form.get('stock_out_date', '').strip()
        recipient_user_id = request.form.get('recipient_user_id', type=int) or None
        recipient_name = request.form.get('recipient_name', '').strip()
        department_id = request.form.get('department_id', type=int) or None
        department_name = request.form.get('department_name', '').strip()
        handler_user_id = current_user.id
        remark = request.form.get('remark', '').strip() or None
        stock_out_number = request.form.get('stock_out_number', '').strip() or None  # 手动编号（可选）

        # 处理领用人：如果没选系统用户但有自定义输入，尝试按名称查找
        if not recipient_user_id and recipient_name:
            from models.user import User
            existing_user = User.query.filter(User.name == recipient_name).first()
            if existing_user:
                recipient_user_id = existing_user.id

        # 处理部门：如果没选系统部门但有自定义输入，尝试按名称查找
        if not department_id and department_name:
            from models.department import Department
            existing_dept = Department.query.filter(Department.name == department_name).first()
            if existing_dept:
                department_id = existing_dept.id

        # 必填字段校验
        if not stock_out_type:
            flash('出库类型不能为空', 'danger')
            return redirect(url_for('stock_out.edit_stock_out', id=id))
        if not stock_out_date_str:
            flash('出库日期不能为空', 'danger')
            return redirect(url_for('stock_out.edit_stock_out', id=id))

        # 解析出库日期
        try:
            stock_out_date = datetime.strptime(stock_out_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('出库日期格式不正确', 'danger')
            return redirect(url_for('stock_out.edit_stock_out', id=id))

        # 更新主表
        stock_out.stock_out_type = stock_out_type
        stock_out.stock_out_date = stock_out_date
        stock_out.recipient_user_id = recipient_user_id
        stock_out.department_id = department_id
        stock_out.handler_user_id = handler_user_id
        stock_out.remark = remark
        stock_out.operator_user_id = current_user.id

        # 删除旧明细
        StockOutDetail.query.filter_by(stock_out_id=id).delete()

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
            specification = item_data.get('specification', '')
            location_name = item_data.get('location_name', '')
            unit = item_data.get('unit', '')
            detail_remark = item_data.get('remark', '')

            if not item_id or not location_id or quantity <= 0:
                continue

            StockOutDetail.create(
                stock_out_id=id,
                item_id=item_id,
                item_name=item_name,
                specification=specification if specification else None,
                unit=unit if unit else None,
                location_id=location_id,
                location_name=location_name,
                quantity=quantity,
                unit_price=unit_price,
                remark=detail_remark if detail_remark else None,
                operator_user_id=current_user.id
            )

        # 重新计算总金额
        StockOut.recalculate_total_amount(id)

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='stock_out_edit',
            action=f"编辑出库单: {stock_out.stock_out_number}",
            result="成功"
        )

        # 检查出库单审核开关：未启用审核时保存即自动审核
        from models.system_config import SystemConfig
        approval_enabled = SystemConfig.get_config_value('STOCK_OUT_APPROVAL_ENABLED', True)
        if not approval_enabled:
            try:
                StockOut.approve(id, current_user.id)
                flash(f'编辑出库单成功: {stock_out.stock_out_number}（已自动审核）', 'success')
                logging.info(f"出库单自动审核，出库单ID: {id}, 单号: {stock_out.stock_out_number}")
            except Exception as auto_approve_err:
                flash(f'编辑出库单成功: {stock_out.stock_out_number}（自动审核失败: {str(auto_approve_err)}）', 'warning')
                logging.warning(f"出库单自动审核失败，出库单ID: {id}, 错误: {str(auto_approve_err)}")
        else:
            flash(f'编辑出库单成功: {stock_out.stock_out_number}', 'success')

        logging.info(f"编辑出库单成功，出库单ID: {id}, 单号: {stock_out.stock_out_number}")
        return redirect(url_for('stock_out.list_stock_outs'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='stock_out_edit',
            action=f"编辑出库单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'编辑出库单失败: {str(e)}', 'danger')
        logging.error(f"编辑出库单失败，出库单ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('stock_out.list_stock_outs'))


# ========== 路由：删除出库单 ==========
@stock_out_bp.route('/operations/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_stock_out(id):
    """删除出库单（仅待审核状态可删除）"""
    try:
        stock_out = StockOut.query.get_or_404(id)
        stock_out_number = stock_out.stock_out_number

        # 仅待审核状态可删除
        if stock_out.status != '待审核':
            flash('仅待审核状态的出库单可以删除', 'danger')
            return redirect(url_for('stock_out.detail_stock_out', id=id))

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='stock_out_delete',
            action=f"删除出库单: {stock_out_number}",
            result="成功"
        )

        # 删除出库单（级联删除明细）
        db.session.delete(stock_out)
        db.session.commit()

        flash(f'删除出库单成功: {stock_out_number}', 'success')
        logging.info(f"删除出库单成功，出库单ID: {id}, 单号: {stock_out_number}")
        return redirect(url_for('stock_out.list_stock_outs'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='stock_out_delete',
            action=f"删除出库单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'删除出库单失败: {str(e)}', 'danger')
        logging.error(f"删除出库单失败，出库单ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('stock_out.list_stock_outs'))


# ========== 路由：审核出库单 ==========
@stock_out_bp.route('/operations/approve/<int:id>', methods=['POST'])
@login_required
@admin_required
def approve_stock_out(id):
    """审核出库单"""
    try:
        stock_out = StockOut.query.get_or_404(id)
        review_remark = request.form.get('review_remark', '').strip() or None

        # 调用审核方法（内部会自动检查库存、更新库存和写入进出库记录）
        result = StockOut.approve(id, current_user.id, review_remark)

        if result is None:
            flash('审核失败，出库单不存在或状态不是待审核', 'danger')
            return redirect(url_for('stock_out.detail_stock_out', id=id))

        # 检查是否库存不足
        if isinstance(result, dict) and 'error' in result:
            insufficient_items = result.get('details', [])
            error_msg = result.get('error', '库存不足')
            detail_msgs = []
            for item in insufficient_items:
                detail_msgs.append(
                    f"{item.get('item_name', '未知')}（{item.get('location_name', '未知位置')}）"
                    f"：库存{item.get('available', 0)}，需要{item.get('required', 0)}"
                )
            flash(f'{error_msg}：' + '；'.join(detail_msgs), 'danger')
            logging.warning(f"审核出库单库存不足，出库单ID: {id}, 单号: {stock_out.stock_out_number}")
            return redirect(url_for('stock_out.detail_stock_out', id=id))

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='stock_out_approve',
            action=f"审核出库单: {stock_out.stock_out_number}",
            result="成功"
        )

        flash(f'审核出库单成功: {stock_out.stock_out_number}，库存已更新', 'success')
        logging.info(f"审核出库单成功，出库单ID: {id}, 单号: {stock_out.stock_out_number}")
        return redirect(url_for('stock_out.detail_stock_out', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='stock_out_approve',
            action=f"审核出库单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'审核出库单失败: {str(e)}', 'danger')
        logging.error(f"审核出库单失败，出库单ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('stock_out.detail_stock_out', id=id))


# ========== 路由：反审核出库单 ==========
@stock_out_bp.route('/operations/unapprove/<int:id>', methods=['POST'])
@login_required
@admin_required
def unapprove_stock_out(id):
    """反审核出库单（仅已审核状态可反审核，反审核后状态变为待审核，库存回滚）"""
    try:
        stock_out = StockOut.query.get_or_404(id)

        # 调用反审核方法（内部会自动回滚库存和删除进出库记录）
        result = StockOut.unapprove(id, current_user.id)

        if result is None:
            flash('反审核失败，出库单不存在或状态不是已审核', 'danger')
            return redirect(url_for('stock_out.detail_stock_out', id=id))

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='stock_out_unapprove',
            action=f"反审核出库单: {stock_out.stock_out_number}",
            result="成功"
        )

        flash(f'反审核出库单成功: {stock_out.stock_out_number}，库存已回滚，可重新编辑', 'success')
        logging.info(f"反审核出库单成功，出库单ID: {id}, 单号: {stock_out.stock_out_number}")
        return redirect(url_for('stock_out.detail_stock_out', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='stock_out_unapprove',
            action=f"反审核出库单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'反审核出库单失败: {str(e)}', 'danger')
        logging.error(f"反审核出库单失败，出库单ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('stock_out.detail_stock_out', id=id))


# ========== 路由：取消出库单 ==========
@stock_out_bp.route('/operations/cancel/<int:id>', methods=['POST'])
@login_required
@admin_required
def cancel_stock_out(id):
    """取消出库单（仅待审核状态可取消）"""
    try:
        stock_out = StockOut.query.get_or_404(id)

        # 调用取消方法
        result = StockOut.cancel(id, current_user.id)

        if result is None:
            flash('取消失败，出库单不存在或状态不是待审核', 'danger')
            return redirect(url_for('stock_out.detail_stock_out', id=id))

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='stock_out_cancel',
            action=f"取消出库单: {stock_out.stock_out_number}",
            result="成功"
        )

        flash(f'取消出库单成功: {stock_out.stock_out_number}', 'success')
        logging.info(f"取消出库单成功，出库单ID: {id}, 单号: {stock_out.stock_out_number}")
        return redirect(url_for('stock_out.detail_stock_out', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='stock_out_cancel',
            action=f"取消出库单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'取消出库单失败: {str(e)}', 'danger')
        logging.error(f"取消出库单失败，出库单ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('stock_out.detail_stock_out', id=id))


# ========== 路由：批量删除出库单 ==========
@stock_out_bp.route('/operations/batch-delete', methods=['POST'])
@login_required
@admin_required
def batch_delete_stock_outs():
    """批量删除出库单（仅待审核状态可删除）"""
    try:
        selected_ids_str = request.form.get('selected_ids', '')
        if not selected_ids_str:
            flash('未选择要删除的出库单', 'warning')
            return redirect(url_for('stock_out.list_stock_outs'))

        ids = selected_ids_str.split(',')
        success_count = 0
        fail_count = 0

        for id in ids:
            stock_out = StockOut.query.get(int(id.strip()))
            if stock_out and stock_out.status == '待审核':
                db.session.delete(stock_out)
                success_count += 1
            else:
                fail_count += 1

        db.session.commit()

        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='stock_out_batch_delete',
            action=f"批量删除出库单: 成功{success_count}条, 失败{fail_count}条",
            result="成功"
        )

        flash(f'批量删除完成: 成功{success_count}条, 失败{fail_count}条', 'success')
        logging.info(f"批量删除出库单，成功{success_count}条, 失败{fail_count}条")
        return redirect(url_for('stock_out.list_stock_outs'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='stock_out_batch_delete',
            action=f"批量删除出库单失败: {str(e)}",
            result="失败"
        )
        flash(f'批量删除失败: {str(e)}', 'danger')
        logging.error(f"批量删除出库单失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('stock_out.list_stock_outs'))