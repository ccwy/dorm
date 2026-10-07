from flask import Blueprint, request, jsonify
import logging
import traceback
from utils.db import db
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
from models.payment.payment_record import PaymentRecord
from models.contract.contract import Contract
from datetime import datetime

payment_api_bp = Blueprint('payment_api', __name__, url_prefix='/payment/api')


# ========== 付款记录列表JSON（分页+筛选） ==========
@payment_api_bp.route('/', methods=['GET'])
@login_required
@require_permission('payment.view')
def get_payment_list():
    """获取付款记录列表JSON，支持分页和多条件筛选"""
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        status = request.args.get('status', '').strip()
        contract_id = request.args.get('contract_id', '').strip()
        payment_period = request.args.get('payment_period', '').strip()

        # 分页参数
        page = max(request.args.get('page', 1, type=int), 1)
        per_page = min(max(request.args.get('per_page', 20, type=int), 1), 100)

        # 构建查询
        query = PaymentRecord.query.order_by(PaymentRecord.id.desc())

        # keyword搜索
        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    PaymentRecord.payment_number.ilike(search_filter),
                    PaymentRecord.remark.ilike(search_filter)
                )
            )

        # status筛选
        if status:
            query = query.filter(PaymentRecord.status == status)

        # contract_id筛选
        if contract_id:
            try:
                query = query.filter(PaymentRecord.contract_id == int(contract_id))
            except (ValueError, TypeError):
                pass

        # payment_period筛选
        if payment_period:
            query = query.filter(PaymentRecord.payment_period == payment_period)

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # 格式化付款记录数据
        payment_list = []
        for p in pagination.items:
            payment_data = {
                "id": p.id,
                "contract_id": p.contract_id,
                "payment_number": p.payment_number or '',
                "payment_method": p.payment_method or '',
                "fixed_amount": float(p.fixed_amount) if p.fixed_amount else None,
                "payment_rounds": p.payment_rounds,
                "current_round": p.current_round,
                "plan_start_date": p.plan_start_date,
                "plan_end_date": p.plan_end_date,
                "payment_period": p.payment_period or '',
                "planned_payment_date": p.planned_payment_date.strftime('%Y-%m-%d') if p.planned_payment_date else None,
                "deadline_date": p.deadline_date.strftime('%Y-%m-%d') if p.deadline_date else None,
                "party_b_payment_method": p.party_b_payment_method or '',
                "party_b_bank_account": p.party_b_bank_account or '',
                "party_b_bank_name": p.party_b_bank_name or '',
                "party_b_receiving_bank": p.party_b_receiving_bank or '',
                "party_b_account_name": p.party_b_account_name or '',
                "party_b_payment_account": p.party_b_payment_account or '',
                "planned_amount": float(p.planned_amount) if p.planned_amount else 0.00,
                "actual_amount": float(p.actual_amount) if p.actual_amount else None,
                "payment_date": p.payment_date.strftime('%Y-%m-%d') if p.payment_date else None,
                "status": p.status or '待付款',
                "remark": p.remark or '',
                "operator_name": p.operator_name or '',
                "create_time": p.create_time.strftime('%Y-%m-%d %H:%M') if p.create_time else None,
                "update_time": p.update_time.strftime('%Y-%m-%d %H:%M') if p.update_time else None
            }
            payment_list.append(payment_data)

        response = {
            "success": True,
            "data": payment_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages
            }
        }

        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='api_query',
            action=f"API查询付款列表，页码:{page}，每页:{per_page}",
            result="成功"
        )

        return jsonify(response)

    except Exception as e:
        logging.error(f"API获取付款列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
        }), 500


# ========== 付款记录详情JSON ==========
@payment_api_bp.route('/<int:id>', methods=['GET'])
@login_required
@require_permission('payment.view')
def get_payment_detail(id):
    """获取单条付款记录详情JSON"""
    try:
        payment = PaymentRecord.query.get_or_404(id)

        payment_data = {
            "id": payment.id,
            "contract_id": payment.contract_id,
            "payment_number": payment.payment_number or '',
            "payment_method": payment.payment_method or '',
            "fixed_amount": float(payment.fixed_amount) if payment.fixed_amount else None,
            "payment_rounds": payment.payment_rounds,
            "current_round": payment.current_round,
            "plan_start_date": payment.plan_start_date,
            "plan_end_date": payment.plan_end_date,
            "payment_period": payment.payment_period or '',
            "planned_payment_date": payment.planned_payment_date.strftime('%Y-%m-%d') if payment.planned_payment_date else None,
            "deadline_date": payment.deadline_date.strftime('%Y-%m-%d') if payment.deadline_date else None,
            "party_b_payment_method": payment.party_b_payment_method or '',
            "party_b_bank_account": payment.party_b_bank_account or '',
            "party_b_bank_name": payment.party_b_bank_name or '',
            "party_b_receiving_bank": payment.party_b_receiving_bank or '',
            "party_b_account_name": payment.party_b_account_name or '',
            "party_b_payment_account": payment.party_b_payment_account or '',
            "planned_amount": float(payment.planned_amount) if payment.planned_amount else 0.00,
            "actual_amount": float(payment.actual_amount) if payment.actual_amount else None,
            "payment_date": payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else None,
            "status": payment.status or '待付款',
            "remark": payment.remark or '',
            "operator_id": payment.operator_id,
            "operator_name": payment.operator_name or '',
            "create_time": payment.create_time.strftime('%Y-%m-%d %H:%M') if payment.create_time else None,
            "update_time": payment.update_time.strftime('%Y-%m-%d %H:%M') if payment.update_time else None
        }

        return jsonify({
            "success": True,
            "data": payment_data
        })

    except Exception as e:
        logging.error(f"API获取付款详情失败 [ID: {id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
        }), 500


# ========== 获取某合同的所有付款记录 ==========
@payment_api_bp.route('/contract-payments/<int:contract_id>', methods=['GET'])
@login_required
@require_permission('payment.view')
def get_contract_payments(contract_id):
    """获取某合同的所有付款记录"""
    try:
        payments = PaymentRecord.query.filter_by(contract_id=contract_id).order_by(PaymentRecord.id.desc()).all()

        payment_list = []
        for p in payments:
            payment_data = {
                "id": p.id,
                "payment_number": p.payment_number or '',
                "payment_method": p.payment_method or '',
                "payment_period": p.payment_period or '',
                "planned_payment_date": p.planned_payment_date.strftime('%Y-%m-%d') if p.planned_payment_date else None,
                "deadline_date": p.deadline_date.strftime('%Y-%m-%d') if p.deadline_date else None,
                "party_b_payment_method": p.party_b_payment_method or '',
                "party_b_bank_account": p.party_b_bank_account or '',
                "party_b_bank_name": p.party_b_bank_name or '',
                "party_b_receiving_bank": p.party_b_receiving_bank or '',
                "party_b_account_name": p.party_b_account_name or '',
                "party_b_payment_account": p.party_b_payment_account or '',
                "planned_amount": float(p.planned_amount) if p.planned_amount else 0.00,
                "actual_amount": float(p.actual_amount) if p.actual_amount else None,
                "payment_date": p.payment_date.strftime('%Y-%m-%d') if p.payment_date else None,
                "status": p.status or '待付款',
                "remark": p.remark or ''
            }
            payment_list.append(payment_data)

        return jsonify({
            "success": True,
            "data": payment_list
        })

    except Exception as e:
        logging.error(f"API获取合同付款记录失败 [contract_id: {contract_id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
        }), 500


# ========== 获取合同列表供选择 ==========
@payment_api_bp.route('/contracts', methods=['GET'])
@login_required
@require_permission('payment.view')
def get_contracts():
    """获取合同列表供付款记录关联选择"""
    try:
        contracts = Contract.query.filter(Contract.status.in_(['生效中', '即将到期'])).order_by(Contract.id.desc()).all()

        contract_list = [{
            "id": c.id,
            "contract_number": c.contract_number or '',
            "contract_name": c.contract_name or '',
            "status": c.status or '',
            "payment_method": c.payment_method or '',
            "fixed_amount": float(c.fixed_amount) if c.fixed_amount else None,
            "contract_amount": float(c.contract_amount) if c.contract_amount else None,
            "tax_rate": float(c.tax_rate) if c.tax_rate else None,
            "tax_amount": float(c.tax_amount) if c.tax_amount else None,
            "payment_rounds": c.payment_rounds,
            "current_payment_round": c.current_payment_round or 0,
            "plan_start_date": c.plan_start_date,
            "plan_end_date": c.plan_end_date,
            "expected_payment_date": c.expected_payment_date.strftime('%Y-%m-%d') if c.expected_payment_date else None,
            "deadline_date": c.deadline_date.strftime('%Y-%m-%d') if c.deadline_date else None,
            "party_a_name": c.party_a.name if c.party_a else '',
            "party_b_name": c.party_b.name if c.party_b else ''
        } for c in contracts]

        return jsonify({
            "success": True,
            "data": contract_list
        })

    except Exception as e:
        logging.error(f"API获取合同列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
        }), 500