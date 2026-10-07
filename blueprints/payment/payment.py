from flask import Blueprint, render_template, request, flash, redirect, url_for
from datetime import date, datetime
from utils.db import db
from models.payment.payment_record import PaymentRecord
from models.contract.contract import Contract
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
from models.system_config.system_config import SystemConfig
import logging

# 定义蓝图
payment_bp = Blueprint(
    'payment',
    __name__,
    url_prefix='/payment',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/payment/static'
)

# 分页工具函数
def generate_page_range(current_page, total_pages, show_pages=5):
    if total_pages <= show_pages:
        return list(range(1, total_pages + 1))
    half = show_pages // 2
    start = max(1, current_page - half)
    end = min(total_pages, start + show_pages - 1)
    if end - start < show_pages - 1:
        start = max(1, end - show_pages + 1)
    page_range = []
    if start > 1:
        page_range.append(1)
        if start > 2:
            page_range.append('...')
    page_range.extend(range(start, end + 1))
    if end < total_pages:
        if end < total_pages - 1:
            page_range.append('...')
        page_range.append(total_pages)
    return page_range

# 导入操作模块
from . import payment_operations


# 付款记录列表页（含筛选+分页）
@payment_bp.route('/', methods=['GET'])
@login_required
@require_permission('payment.view')
def index():
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        status = request.args.get('status', '').strip()
        payment_method = request.args.get('payment_method', '').strip()

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # 参数校验
        if page < 1:
            page = 1
        per_page = max(10, min(100, per_page))

        # 获取筛选选项
        statuses = ['待付款', '已付款', '已逾期', '已取消']
        payment_methods = SystemConfig.get_config_value('PAYMENT_METHODS', ['月度固定金额', '月度实际金额', '一次性付清', '按实际金额付款'])

        # 构建查询（使用joinedload预加载contract关系，避免N+1查询）
        query = PaymentRecord.query.options(db.joinedload(PaymentRecord.contract)).order_by(PaymentRecord.id.desc())

        # keyword搜索：ilike匹配payment_number, remark, 合同编号, 合同名称
        if keyword:
            search_filter = f'%{keyword}%'
            query = query.join(PaymentRecord.contract)
            query = query.filter(
                db.or_(
                    PaymentRecord.payment_number.ilike(search_filter),
                    PaymentRecord.remark.ilike(search_filter),
                    Contract.contract_number.ilike(search_filter),
                    Contract.contract_name.ilike(search_filter)
                )
            )

        # status筛选
        if status:
            query = query.filter(PaymentRecord.status == status)

        # payment_method筛选
        if payment_method:
            query = query.filter(PaymentRecord.payment_method == payment_method)

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        payments = pagination.items
        total_count = pagination.total
        total_pages = pagination.pages
        current_page = pagination.page
        page_range = generate_page_range(current_page, total_pages)

        # 更新逾期状态
        PaymentRecord.update_overdue_status()

        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='records',
            action="访问付款管理页面",
            result="成功"
        )
        logging.info(f"加载付款管理页面，当前用户ID: {current_user.id}")

        return render_template(
            'payment/payment_list.html',
            title="付款管理",
            payments=payments,
            total_count=total_count,
            current_page=current_page,
            per_page=per_page,
            total_pages=total_pages,
            page_range=page_range,
            statuses=statuses,
            payment_methods=payment_methods,
            current_status=status,
            current_payment_method=payment_method,
            keyword=keyword
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='records',
            action=f"加载付款管理页面失败: {str(e)}",
            result="失败"
        )
        flash('加载付款数据失败，请联系管理员', 'danger')
        logging.error(f"加载付款管理页面失败: {str(e)}")
        return render_template(
            'payment/payment_list.html',
            title="付款管理",
            payments=[],
            total_count=0,
            current_page=1,
            per_page=20,
            total_pages=0,
            page_range=[],
            statuses=['待付款', '已付款', '已逾期', '已取消'],
            payment_methods=SystemConfig.get_config_value('PAYMENT_METHODS', ['月度固定金额', '月度实际金额', '一次性付清', '按实际金额付款']),
            current_status='',
            current_payment_method='',
            keyword=''
        )


# 新增付款记录页面（无合同关联）
@payment_bp.route('/add', methods=['GET'])
@login_required
@require_permission('payment.create')
def add_page():
    try:
        # 获取合同列表供选择（仅显示生效中和即将到期状态）
        contracts = Contract.query.filter(Contract.status.in_(['生效中', '即将到期'])).order_by(Contract.id.desc()).all()
        # 过滤掉付款进度已完成的合同
        contracts = [c for c in contracts if not c.is_payment_completed]

        # 自动生成付款编号
        payment_number = PaymentRecord.generate_payment_number()

        return render_template(
            'payment/payment_form.html',
            title="新增付款记录",
            payment=None,
            contracts=contracts,
            payment_number=payment_number,
            from_contract=None,
            current_month=date.today().strftime('%Y-%m')
        )
    except Exception as e:
        logging.error(f"加载新增付款页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('payment.index'))


# 从合同详情页新增付款记录
@payment_bp.route('/add/<int:contract_id>', methods=['GET'])
@login_required
@require_permission('payment.create')
def add_page_from_contract(contract_id):
    try:
        contract = Contract.query.get_or_404(contract_id)

        # 获取合同列表供选择（仅显示生效中和即将到期状态）
        contracts = Contract.query.filter(Contract.status.in_(['生效中', '即将到期'])).order_by(Contract.id.desc()).all()
        # 过滤掉付款进度已完成的合同
        contracts = [c for c in contracts if not c.is_payment_completed]

        # 自动生成付款编号
        payment_number = PaymentRecord.generate_payment_number()

        return render_template(
            'payment/payment_form.html',
            title=f"新增付款记录 - 合同: {contract.contract_name}",
            payment=None,
            contracts=contracts,
            payment_number=payment_number,
            from_contract=contract,
            current_month=date.today().strftime('%Y-%m')
        )
    except Exception as e:
        logging.error(f"加载新增付款页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('payment.index'))


# 编辑付款记录页面
@payment_bp.route('/edit/<int:id>', methods=['GET'])
@login_required
@require_permission('payment.edit')
def edit_page(id):
    try:
        payment = PaymentRecord.query.get_or_404(id)

        # 获取合同列表供选择（仅显示生效中和即将到期状态）
        contracts = Contract.query.filter(Contract.status.in_(['生效中', '即将到期'])).order_by(Contract.id.desc()).all()
        # 过滤掉付款进度已完成的合同
        contracts = [c for c in contracts if not c.is_payment_completed]

        # 编辑时，如果当前关联合同不在过滤结果中，仍需追加到列表以便显示
        if payment.contract_id and payment.contract and payment.contract not in contracts:
            contracts = [payment.contract] + list(contracts)

        return render_template(
            'payment/payment_form.html',
            title=f"编辑付款记录 - {payment.payment_number}",
            payment=payment,
            contracts=contracts,
            payment_number=payment.payment_number,
            from_contract=None,
            current_month=date.today().strftime('%Y-%m')
        )
    except Exception as e:
        logging.error(f"加载编辑付款页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('payment.index'))


# 查看付款记录详情页面
@payment_bp.route('/detail/<int:id>', methods=['GET'])
@login_required
@require_permission('payment.view')
def detail(id):
    try:
        payment = PaymentRecord.query.get_or_404(id)

        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='records',
            action=f"查看付款详情 [ID: {id}, {payment.payment_number}]",
            result="成功"
        )
        logging.info(f"查看付款详情，付款ID: {id}")

        return render_template(
            'payment/payment_detail.html',
            title=f"付款详情 - {payment.payment_number}",
            payment=payment,
            today=datetime.now().strftime('%Y-%m-%d')
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='payment',
            operation_type='records',
            action=f"查看付款详情失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash('查看付款详情失败，请重试', 'danger')
        logging.error(f"查看付款详情失败，付款ID: {id}, 错误: {str(e)}")
        return redirect(url_for('payment.index'))