from flask import request, flash, redirect, url_for
from flask_login import login_required, current_user
from utils.db import db
from models.payment.payment_record import PaymentRecord
from models.contract.contract import Contract
from utils.log import log_operation
from utils.auth import require_permission
import logging
import traceback
from decimal import Decimal, InvalidOperation
from datetime import datetime
from .payment import payment_bp


# ========== 路由：创建付款记录 ==========
@payment_bp.route('/operations/create', methods=['POST'])
@login_required
@require_permission('payment.create')
def create_payment():
    """创建付款记录"""
    try:
        # 读取表单字段
        contract_id = request.form.get('contract_id', type=int)
        payment_method = request.form.get('payment_method', '').strip() or None
        fixed_amount = request.form.get('fixed_amount', '').strip() or None
        payment_rounds = request.form.get('payment_rounds', '').strip() or None
        plan_start_date = request.form.get('plan_start_date', '').strip() or None
        plan_end_date = request.form.get('plan_end_date', '').strip() or None
        payment_period = request.form.get('payment_period', '').strip() or None
        planned_payment_date = request.form.get('planned_payment_date', '').strip() or None
        deadline_date = request.form.get('deadline_date', '').strip() or None
        planned_amount = request.form.get('planned_amount', '').strip() or None
        actual_amount = request.form.get('actual_amount', '').strip() or None
        payment_date = request.form.get('payment_date', '').strip() or None
        status = request.form.get('status', '待付款').strip() or '待付款'
        remark = request.form.get('remark', '').strip() or None

        # 必填字段校验
        if not contract_id:
            flash('请选择关联合同', 'danger')
            return redirect(url_for('payment.add_page'))

        # 验证合同是否存在
        contract = Contract.query.get(contract_id)
        if not contract:
            flash('所选合同不存在', 'danger')
            return redirect(url_for('payment.add_page'))

        # 自动生成付款编号
        payment_number = PaymentRecord.generate_payment_number()

        # 计算当前轮次（关联合同已付款轮次+1）
        current_round = (contract.current_payment_round or 0) + 1

        # 校验：月度固定金额或月度实际金额方式，付款轮次不能超过合同总轮次
        if payment_method in ('月度固定金额', '月度实际金额') and contract.payment_rounds:
            if current_round > contract.payment_rounds:
                flash('该合同已达到付款轮次上限', 'danger')
                return redirect(url_for('payment.add_page'))

        # 数值转换：fixed_amount/planned_amount/actual_amount转Decimal
        if fixed_amount:
            try:
                fixed_amount = Decimal(fixed_amount)
            except (InvalidOperation, ValueError):
                fixed_amount = None
        if planned_amount:
            try:
                planned_amount = Decimal(planned_amount)
            except (InvalidOperation, ValueError):
                planned_amount = None
        if actual_amount:
            try:
                actual_amount = Decimal(actual_amount)
            except (InvalidOperation, ValueError):
                actual_amount = None

        # 数值转换：payment_rounds/plan_start_date/plan_end_date转int
        if payment_rounds:
            try:
                payment_rounds = int(payment_rounds)
            except (ValueError, TypeError):
                payment_rounds = None
        if plan_start_date:
            try:
                plan_start_date = int(plan_start_date)
            except (ValueError, TypeError):
                plan_start_date = None
        if plan_end_date:
            try:
                plan_end_date = int(plan_end_date)
            except (ValueError, TypeError):
                plan_end_date = None

        # 日期转换
        if planned_payment_date:
            try:
                planned_payment_date = datetime.strptime(planned_payment_date, '%Y-%m-%d').date()
            except ValueError:
                planned_payment_date = None
        if deadline_date:
            try:
                deadline_date = datetime.strptime(deadline_date, '%Y-%m-%d').date()
            except ValueError:
                deadline_date = None
        if payment_date:
            try:
                payment_date = datetime.strptime(payment_date, '%Y-%m-%d').date()
            except ValueError:
                payment_date = None

        # 非固定金额类：清空固定金额专属字段
        if payment_method not in ('月度固定金额', '月度实际金额'):
            payment_rounds = None
            plan_start_date = None
            plan_end_date = None
            payment_period = None
        elif payment_method == '月度实际金额':
            # 月度实际金额：保留轮次，清空其他固定金额专属字段
            plan_start_date = None
            plan_end_date = None
            payment_period = None

        # 创建付款记录
        payment = PaymentRecord.create(
            contract_id=contract_id,
            payment_number=payment_number,
            payment_method=payment_method,
            fixed_amount=fixed_amount,
            payment_rounds=payment_rounds,
            current_round=current_round,
            plan_start_date=plan_start_date,
            plan_end_date=plan_end_date,
            payment_period=payment_period,
            planned_payment_date=planned_payment_date,
            deadline_date=deadline_date,
            planned_amount=planned_amount,
            actual_amount=actual_amount,
            payment_date=payment_date,
            status=status,
            remark=remark,
            operator_id=current_user.id,
            operator_name=current_user.name
        )

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='payment_create',
            action=f"创建付款记录: {payment_number}（合同ID: {contract_id}）",
            result="成功"
        )

        flash(f'创建付款记录成功: {payment_number}', 'success')
        logging.info(f"创建付款记录成功，付款ID: {payment.id}, 编号: {payment_number}")
        return redirect(url_for('payment.detail', id=payment.id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='payment_create',
            action=f"创建付款记录失败: {str(e)}",
            result="失败"
        )
        flash(f'创建付款记录失败: {str(e)}', 'danger')
        logging.error(f"创建付款记录失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('payment.add_page'))


# ========== 路由：更新付款记录 ==========
@payment_bp.route('/operations/update/<int:id>', methods=['POST'])
@login_required
@require_permission('payment.edit')
def update_payment(id):
    """更新付款记录"""
    try:
        payment = PaymentRecord.query.get_or_404(id)

        # 读取表单字段
        new_contract_id = request.form.get('contract_id', type=int)
        if new_contract_id:
            contract = Contract.query.get(new_contract_id)
            if not contract:
                flash('关联合同不存在', 'danger')
                return redirect(url_for('payment.edit_page', id=id))
        new_payment_method = request.form.get('payment_method', '').strip() or None
        new_fixed_amount = request.form.get('fixed_amount', '').strip() or None
        new_payment_rounds = request.form.get('payment_rounds', '').strip() or None
        new_plan_start_date = request.form.get('plan_start_date', '').strip() or None
        new_plan_end_date = request.form.get('plan_end_date', '').strip() or None
        new_payment_period = request.form.get('payment_period', '').strip() or None
        new_planned_payment_date = request.form.get('planned_payment_date', '').strip() or None
        new_deadline_date = request.form.get('deadline_date', '').strip() or None
        new_planned_amount = request.form.get('planned_amount', '').strip() or None
        new_actual_amount = request.form.get('actual_amount', '').strip() or None
        new_payment_date = request.form.get('payment_date', '').strip() or None
        new_status = request.form.get('status', '待付款').strip() or '待付款'
        new_remark = request.form.get('remark', '').strip() or None

        # 必填字段校验
        if not new_contract_id:
            flash('请选择关联合同', 'danger')
            return redirect(url_for('payment.edit_page', id=id))

        # 数值转换：fixed_amount/planned_amount/actual_amount转Decimal
        if new_fixed_amount:
            try:
                new_fixed_amount = Decimal(new_fixed_amount)
            except (InvalidOperation, ValueError):
                new_fixed_amount = None
        if new_planned_amount:
            try:
                new_planned_amount = Decimal(new_planned_amount)
            except (InvalidOperation, ValueError):
                new_planned_amount = None
        if new_actual_amount:
            try:
                new_actual_amount = Decimal(new_actual_amount)
            except (InvalidOperation, ValueError):
                new_actual_amount = None

        # 数值转换：payment_rounds/plan_start_date/plan_end_date转int
        if new_payment_rounds:
            try:
                new_payment_rounds = int(new_payment_rounds)
            except (ValueError, TypeError):
                new_payment_rounds = None
        if new_plan_start_date:
            try:
                new_plan_start_date = int(new_plan_start_date)
            except (ValueError, TypeError):
                new_plan_start_date = None
        if new_plan_end_date:
            try:
                new_plan_end_date = int(new_plan_end_date)
            except (ValueError, TypeError):
                new_plan_end_date = None

        # 日期转换
        if new_planned_payment_date:
            try:
                new_planned_payment_date = datetime.strptime(new_planned_payment_date, '%Y-%m-%d').date()
            except ValueError:
                new_planned_payment_date = None
        if new_deadline_date:
            try:
                new_deadline_date = datetime.strptime(new_deadline_date, '%Y-%m-%d').date()
            except ValueError:
                new_deadline_date = None
        if new_payment_date:
            try:
                new_payment_date = datetime.strptime(new_payment_date, '%Y-%m-%d').date()
            except ValueError:
                new_payment_date = None

        # 非固定金额类：清空固定金额专属字段
        if new_payment_method not in ('月度固定金额', '月度实际金额'):
            new_payment_rounds = None
            new_plan_start_date = None
            new_plan_end_date = None
            new_payment_period = None
        elif new_payment_method == '月度实际金额':
            # 月度实际金额：保留轮次，清空其他固定金额专属字段
            new_plan_start_date = None
            new_plan_end_date = None
            new_payment_period = None

        # 状态变更时更新合同的当前已付款轮次
        old_status = payment.status
        if old_status != new_status:
            contract = Contract.query.get(payment.contract_id)
            if contract:
                if old_status != '已付款' and new_status == '已付款':
                    # 从非"已付款"变为"已付款"：+1
                    contract.current_payment_round = (contract.current_payment_round or 0) + 1
                elif old_status == '已付款' and new_status != '已付款':
                    # 从"已付款"变为其他状态：-1（最低0）
                    contract.current_payment_round = max((contract.current_payment_round or 0) - 1, 0)

        # 对比新旧值，记录变更详情
        changes = []
        if payment.contract_id != new_contract_id:
            changes.append(f"关联合同ID: {payment.contract_id} → {new_contract_id}")
        if payment.payment_method != new_payment_method:
            changes.append(f"付款方式: {payment.payment_method or '无'} → {new_payment_method or '无'}")
        if str(payment.fixed_amount or '') != str(new_fixed_amount or ''):
            changes.append(f"固定金额: {payment.fixed_amount or '无'} → {new_fixed_amount or '无'}")
        if payment.payment_rounds != new_payment_rounds:
            changes.append(f"付款轮次: {payment.payment_rounds or '无'} → {new_payment_rounds or '无'}")
        if payment.plan_start_date != new_plan_start_date:
            changes.append(f"每月准备日: {payment.plan_start_date or '无'} → {new_plan_start_date or '无'}")
        if payment.plan_end_date != new_plan_end_date:
            changes.append(f"每月截止日: {payment.plan_end_date or '无'} → {new_plan_end_date or '无'}")
        if payment.payment_period != new_payment_period:
            changes.append(f"付款周期: {payment.payment_period or '无'} → {new_payment_period or '无'}")
        if payment.planned_payment_date != new_planned_payment_date:
            changes.append(f"计划付款日期: {payment.planned_payment_date or '无'} → {new_planned_payment_date or '无'}")
        if payment.deadline_date != new_deadline_date:
            changes.append(f"截止付款日期: {payment.deadline_date or '无'} → {new_deadline_date or '无'}")
        if str(payment.planned_amount or '') != str(new_planned_amount or ''):
            changes.append(f"计划付款金额: {payment.planned_amount or '无'} → {new_planned_amount or '无'}")
        if str(payment.actual_amount or '') != str(new_actual_amount or ''):
            changes.append(f"实际付款金额: {payment.actual_amount or '无'} → {new_actual_amount or '无'}")
        if payment.payment_date != new_payment_date:
            changes.append(f"实际付款日期: {payment.payment_date or '无'} → {new_payment_date or '无'}")
        if payment.status != new_status:
            changes.append(f"状态: {payment.status or '无'} → {new_status or '无'}")
        if payment.remark != new_remark:
            changes.append(f"备注: {payment.remark or '无'} → {new_remark or '无'}")

        # 更新字段
        payment.contract_id = new_contract_id
        payment.payment_method = new_payment_method
        payment.fixed_amount = new_fixed_amount
        payment.payment_rounds = new_payment_rounds
        payment.plan_start_date = new_plan_start_date
        payment.plan_end_date = new_plan_end_date
        payment.payment_period = new_payment_period
        payment.planned_payment_date = new_planned_payment_date
        payment.deadline_date = new_deadline_date
        payment.planned_amount = new_planned_amount
        payment.actual_amount = new_actual_amount
        payment.payment_date = new_payment_date
        payment.status = new_status
        payment.remark = new_remark

        db.session.commit()

        # 记录操作日志
        change_detail = '；'.join(changes) if changes else '无变更'
        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='payment_update',
            action=f"更新付款记录: {payment.payment_number}，变更: {change_detail}",
            result="成功"
        )

        flash(f'更新付款记录成功: {payment.payment_number}', 'success')
        logging.info(f"更新付款记录成功，付款ID: {id}, 编号: {payment.payment_number}")
        return redirect(url_for('payment.detail', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='payment_update',
            action=f"更新付款记录失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'更新付款记录失败: {str(e)}', 'danger')
        logging.error(f"更新付款记录失败，付款ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('payment.edit_page', id=id))


# ========== 路由：删除付款记录 ==========
@payment_bp.route('/operations/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('payment.delete')
def delete_payment(id):
    """删除付款记录"""
    try:
        payment = PaymentRecord.query.get_or_404(id)
        payment_number = payment.payment_number

        # 如果被删除的付款记录状态为"已付款"，需回退合同当前已付款轮次
        if payment.status == '已付款':
            contract = Contract.query.get(payment.contract_id)
            if contract:
                contract.current_payment_round = max((contract.current_payment_round or 0) - 1, 0)

        db.session.delete(payment)
        db.session.commit()

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='payment_delete',
            action=f"删除付款记录: {payment_number}",
            result="成功"
        )

        flash(f'删除付款记录成功: {payment_number}', 'success')
        logging.info(f"删除付款记录成功，付款ID: {id}, 编号: {payment_number}")
        return redirect(url_for('payment.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='payment_delete',
            action=f"删除付款记录失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'删除付款记录失败: {str(e)}', 'danger')
        logging.error(f"删除付款记录失败，付款ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('payment.index'))