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
        reconciliation_day = request.form.get('reconciliation_day', '').strip() or None
        payment_deadline_day = request.form.get('payment_deadline_day', '').strip() or None
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

        # 验证合同付款进度是否已完成
        if contract.is_payment_completed:
            flash('该合同付款进度已完成，无法新增付款记录', 'danger')
            return redirect(url_for('payment.add_page'))

        # 自动生成付款编号
        payment_number = PaymentRecord.generate_payment_number()

        # 计算当前轮次（基于该合同已有付款记录数+1）
        existing_count = PaymentRecord.query.filter_by(contract_id=contract_id).count()
        current_round = existing_count + 1

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

        # 数值转换：payment_rounds/reconciliation_day/payment_deadline_day转int
        if payment_rounds:
            try:
                payment_rounds = int(payment_rounds)
            except (ValueError, TypeError):
                payment_rounds = None
        if reconciliation_day:
            try:
                reconciliation_day = int(reconciliation_day)
            except (ValueError, TypeError):
                reconciliation_day = None
        if payment_deadline_day:
            try:
                payment_deadline_day = int(payment_deadline_day)
            except (ValueError, TypeError):
                payment_deadline_day = None

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
            reconciliation_day = None
            payment_deadline_day = None
            payment_period = None
        elif payment_method == '月度实际金额':
            # 月度实际金额：保留轮次和月度周期字段，仅清空固定金额
            fixed_amount = None

        # 创建付款记录
        payment = PaymentRecord.create(
            contract_id=contract_id,
            payment_number=payment_number,
            payment_method=payment_method,
            fixed_amount=fixed_amount,
            payment_rounds=payment_rounds,
            current_round=current_round,
            reconciliation_day=reconciliation_day,
            payment_deadline_day=payment_deadline_day,
            payment_period=payment_period,
            planned_payment_date=planned_payment_date,
            deadline_date=deadline_date,
            planned_amount=planned_amount,
            actual_amount=actual_amount,
            payment_date=payment_date,
            status=status,
            remark=remark,
            operator_id=current_user.id,
            operator_name=current_user.name,
            party_b_payment_method=contract.party_b_payment_method,
            party_b_bank_account=contract.party_b_bank_account,
            party_b_bank_name=contract.party_b_bank_name,
            party_b_receiving_bank=contract.party_b_receiving_bank,
            party_b_account_name=contract.party_b_account_name,
            party_b_payment_account=contract.party_b_payment_account,
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
        new_reconciliation_day = request.form.get('reconciliation_day', '').strip() or None
        new_payment_deadline_day = request.form.get('payment_deadline_day', '').strip() or None
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

        # 数值转换：payment_rounds/reconciliation_day/payment_deadline_day转int
        if new_payment_rounds:
            try:
                new_payment_rounds = int(new_payment_rounds)
            except (ValueError, TypeError):
                new_payment_rounds = None
        if new_reconciliation_day:
            try:
                new_reconciliation_day = int(new_reconciliation_day)
            except (ValueError, TypeError):
                new_reconciliation_day = None
        if new_payment_deadline_day:
            try:
                new_payment_deadline_day = int(new_payment_deadline_day)
            except (ValueError, TypeError):
                new_payment_deadline_day = None

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
            new_reconciliation_day = None
            new_payment_deadline_day = None
            new_payment_period = None
        elif new_payment_method == '月度实际金额':
            # 月度实际金额：保留轮次和月度周期字段，仅清空固定金额
            new_fixed_amount = None

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
        if payment.reconciliation_day != new_reconciliation_day:
            changes.append(f"对账日: {payment.reconciliation_day or '无'} → {new_reconciliation_day or '无'}")
        if payment.payment_deadline_day != new_payment_deadline_day:
            changes.append(f"付款截止日: {payment.payment_deadline_day or '无'} → {new_payment_deadline_day or '无'}")
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
        payment.reconciliation_day = new_reconciliation_day
        payment.payment_deadline_day = new_payment_deadline_day
        payment.payment_period = new_payment_period
        payment.planned_payment_date = new_planned_payment_date
        payment.deadline_date = new_deadline_date
        payment.planned_amount = new_planned_amount
        payment.actual_amount = new_actual_amount
        payment.payment_date = new_payment_date
        payment.status = new_status
        payment.remark = new_remark

        # 从合同同步收款资料快照
        if payment.contract:
            payment.party_b_payment_method = payment.contract.party_b_payment_method
            payment.party_b_bank_account = payment.contract.party_b_bank_account
            payment.party_b_bank_name = payment.contract.party_b_bank_name
            payment.party_b_receiving_bank = payment.contract.party_b_receiving_bank
            payment.party_b_account_name = payment.contract.party_b_account_name
            payment.party_b_payment_account = payment.contract.party_b_payment_account

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

        # 已付款状态的记录不允许删除
        if payment.status == '已付款':
            flash('已付款的记录不允许删除', 'danger')
            logging.warning(f"尝试删除已付款记录，付款ID: {id}, 编号: {payment_number}")
            return redirect(url_for('payment.index'))

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


# ========== 路由：变更付款状态 ==========
@payment_bp.route('/operations/status_change/<int:id>', methods=['POST'])
@login_required
@require_permission('payment.edit')
def status_change_payment(id):
    """变更付款状态"""
    try:
        payment = PaymentRecord.query.get_or_404(id)
        old_status = payment.status
        new_status = request.form.get('status', '').strip()

        # 校验状态流转合法性
        valid_transitions = {
            '待付款': ['已付款', '已逾期', '已取消'],
            '已付款': ['待付款', '已取消'],
            '已逾期': ['已付款', '待付款', '已取消'],
            '已取消': ['待付款'],
        }

        if old_status not in valid_transitions:
            flash(f'当前状态"{old_status}"不支持状态变更', 'danger')
            return redirect(url_for('payment.detail', id=id))

        if new_status not in valid_transitions.get(old_status, []):
            flash(f'状态不允许从"{old_status}"变更为"{new_status}"', 'danger')
            return redirect(url_for('payment.detail', id=id))

        # 更新状态
        payment.status = new_status

        # 如果变更为"已付款"，自动填入实际付款日期和金额
        if new_status == '已付款':
            payment_date_str = request.form.get('payment_date', '').strip()
            actual_amount_str = request.form.get('actual_amount', '').strip()
            if payment_date_str:
                try:
                    payment.payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
                except ValueError:
                    pass
            else:
                payment.payment_date = datetime.now().date()
            if actual_amount_str:
                try:
                    payment.actual_amount = Decimal(actual_amount_str)
                except (InvalidOperation, ValueError):
                    pass
            elif payment.planned_amount is not None:
                payment.actual_amount = payment.planned_amount

        # 状态变更时同步更新合同的当前已付款轮次
        contract = Contract.query.get(payment.contract_id)
        if contract:
            if old_status != '已付款' and new_status == '已付款':
                contract.current_payment_round = (contract.current_payment_round or 0) + 1
            elif old_status == '已付款' and new_status != '已付款':
                contract.current_payment_round = max((contract.current_payment_round or 0) - 1, 0)

        db.session.commit()

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='payment_status_change',
            action=f"付款记录状态变更：{old_status} → {new_status}",
            result="成功"
        )

        flash(f'付款状态已变更为：{new_status}', 'success')
        logging.info(f"付款状态变更，付款ID: {id}, {old_status} → {new_status}")
        return redirect(url_for('payment.detail', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='payment_status_change',
            action=f"变更付款状态失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'变更付款状态失败: {str(e)}', 'danger')
        logging.error(f"变更付款状态失败，付款ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('payment.detail', id=id))


# ========== 路由：标记已付款 ==========
@payment_bp.route('/operations/mark_as_paid/<int:id>', methods=['POST'])
@login_required
@require_permission('payment.edit')
def mark_as_paid(id):
    """标记付款记录为已付款"""
    try:
        payment = PaymentRecord.query.get_or_404(id)

        # 如果已经是已付款状态，提示并返回
        if payment.status == '已付款':
            flash('该付款记录已经是"已付款"状态', 'warning')
            return redirect(url_for('payment.detail', id=id))

        old_status = payment.status

        # 设置状态为已付款
        payment.status = '已付款'

        # 如果payment_date为空，自动填入当天日期
        if not payment.payment_date:
            payment.payment_date = datetime.now().date()

        # 如果actual_amount为空，自动填入planned_amount
        if payment.actual_amount is None and payment.planned_amount is not None:
            payment.actual_amount = payment.planned_amount

        # 更新合同当前已付款轮次（+1）
        contract = Contract.query.get(payment.contract_id)
        if contract:
            contract.current_payment_round = (contract.current_payment_round or 0) + 1

        db.session.commit()

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='payment_mark_paid',
            action=f"标记付款记录为已付款：{old_status} → 已付款",
            result="成功"
        )

        flash('已标记为已付款', 'success')
        logging.info(f"标记付款记录为已付款，付款ID: {id}, {old_status} → 已付款")
        return redirect(url_for('payment.detail', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='payment_mark_paid',
            action=f"标记已付款失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'标记已付款失败: {str(e)}', 'danger')
        logging.error(f"标记已付款失败，付款ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('payment.detail', id=id))