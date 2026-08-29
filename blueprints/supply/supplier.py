from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from utils.db import db
from models.supply.supplier import Supplier
from models.supply.supplier_operation_record import SupplierOperationRecord
from models.user import User
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
import logging

# 定义蓝图
supplier_bp = Blueprint(
    'supplier',
    __name__,
    url_prefix='/supplier',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/supplier/static'
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
from . import supplier_operations


# 供应商列表页（含筛选+分页）
@supplier_bp.route('/', methods=['GET'])
@login_required
@require_permission('supply.view')
def index():
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        status = request.args.get('status', '').strip()

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # 参数校验
        if page < 1:
            page = 1
        per_page = max(10, min(100, per_page))

        # 获取筛选选项
        statuses = ['启用', '停用']

        # 构建查询
        query = Supplier.query.order_by(Supplier.id.desc())

        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    Supplier.name.ilike(search_filter),
                    Supplier.contact_person.ilike(search_filter),
                    Supplier.contact_phone.ilike(search_filter)
                )
            )
        if status:
            query = query.filter(Supplier.status == status)

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        suppliers = pagination.items
        total_count = pagination.total
        total_pages = pagination.pages
        current_page = pagination.page
        page_range = generate_page_range(current_page, total_pages)

        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='records',
            action="访问供应商管理页面",
            result="成功"
        )
        logging.info(f"加载供应商管理页面，当前用户ID: {current_user.id}")

        return render_template(
            'supply_manage/supplier_list.html',
            title="供应商管理",
            # 供应商数据
            suppliers=suppliers,
            total_count=total_count,
            # 分页参数
            current_page=current_page,
            per_page=per_page,
            total_pages=total_pages,
            page_range=page_range,
            # 筛选配置
            statuses=statuses,
            # 当前筛选条件（回显）
            current_status=status,
            keyword=keyword
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='records',
            action=f"加载供应商管理页面失败: {str(e)}",
            result="失败"
        )
        flash('加载供应商数据失败，请联系管理员', 'danger')
        logging.error(f"加载供应商管理页面失败: {str(e)}")
        return render_template(
            'supply_manage/supplier_list.html',
            title="供应商管理",
            suppliers=[],
            total_count=0,
            current_page=1,
            per_page=20,
            total_pages=0,
            page_range=[],
            statuses=['启用', '停用'],
            current_status='',
            keyword=''
        )


# 新增供应商页面
@supplier_bp.route('/add', methods=['GET'])
@login_required
@require_permission('supply.create')
def add_page():
    try:
        from datetime import date
        today = date.today().strftime('%Y-%m-%d')
        return render_template(
            'supply_manage/supplier_form.html',
            title="新增供应商",
            supplier=None,
            today=today
        )
    except Exception as e:
        logging.error(f"加载新增供应商页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('supplier.index'))


# 编辑供应商页面
@supplier_bp.route('/edit/<int:id>', methods=['GET'])
@login_required
@require_permission('supply.edit')
def edit_page(id):
    try:
        supplier = Supplier.query.get_or_404(id)
        return render_template(
            'supply_manage/supplier_form.html',
            title=f"编辑供应商 - {supplier.name}",
            supplier=supplier
        )
    except Exception as e:
        logging.error(f"加载编辑供应商页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('supplier.index'))


# 供应商详情页（含操作记录时间线）
@supplier_bp.route('/detail/<int:id>', methods=['GET'])
@login_required
@require_permission('supply.view')
def detail(id):
    try:
        supplier = Supplier.query.get_or_404(id)

        # 获取操作记录时间线（按时间倒序）
        operation_records = SupplierOperationRecord.query.filter_by(
            supplier_id=id
        ).order_by(SupplierOperationRecord.operation_time.desc()).all()

        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='records',
            action=f"查看供应商详情 [ID: {id}, {supplier.name}]",
            result="成功"
        )
        logging.info(f"查看供应商详情，供应商ID: {id}")

        return render_template(
            'supply_manage/supplier_detail.html',
            title=f"供应商详情 - {supplier.name}",
            supplier=supplier,
            operation_records=operation_records
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='records',
            action=f"查看供应商详情失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash('查看供应商详情失败，请重试', 'danger')
        logging.error(f"查看供应商详情失败，供应商ID: {id}, 错误: {str(e)}")
        return redirect(url_for('supplier.index'))