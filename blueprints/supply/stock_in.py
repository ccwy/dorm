from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from utils.db import db
from models.supply.stock_in import StockIn
from models.supply.stock_in_detail import StockInDetail
from models.supply.supplier import Supplier
from models.supply.supply_item import SupplyItem
from models.supply.storage_location import StorageLocation
from models.department import Department
from models.user import User
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
import logging

# 定义蓝图
stock_in_bp = Blueprint(
    'stock_in',
    __name__,
    url_prefix='/stock-in',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/stock-in/static'
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
from . import stock_in_operations


# 入库单列表页（含筛选+分页）
@stock_in_bp.route('/', methods=['GET'])
@login_required
@require_permission('supply.view')
def list_stock_ins():
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        stock_in_type = request.args.get('stock_in_type', '').strip()
        status = request.args.get('status', '').strip()
        supplier_id = request.args.get('supplier_id', '').strip()
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # 参数校验
        if page < 1:
            page = 1
        per_page = max(10, min(100, per_page))

        # 获取筛选选项
        statuses = ['待审核', '已审核', '已取消']
        suppliers = Supplier.get_active_suppliers()

        # 从系统配置获取入库类型选项
        from models.system_config import SystemConfig
        stock_in_types = SystemConfig.get_config_value('stock_in_types', '采购入库,其它入库')
        if isinstance(stock_in_types, str):
            stock_in_types = [t.strip() for t in stock_in_types.split(',') if t.strip()]

        # 构建查询
        query = StockIn.query.order_by(StockIn.id.desc())

        if keyword:
            search_filter = f'%{keyword}%'
            from models.supply.stock_in_detail import StockInDetail
            from models.supply.supply_item import SupplyItem
            query = query.outerjoin(StockInDetail, StockIn.id == StockInDetail.stock_in_id)\
                         .outerjoin(SupplyItem, StockInDetail.item_id == SupplyItem.id)
            query = query.filter(
                db.or_(
                    StockIn.stock_in_number.ilike(search_filter),
                    StockIn.remark.ilike(search_filter),
                    SupplyItem.item_number.ilike(search_filter),
                    SupplyItem.name.ilike(search_filter)
                )
            ).distinct()
        if stock_in_type:
            query = query.filter(StockIn.stock_in_type == stock_in_type)
        if status:
            query = query.filter(StockIn.status == status)
        if supplier_id:
            query = query.filter(StockIn.supplier_id == supplier_id)
        if date_from:
            try:
                from datetime import datetime as dt
                date_from_val = dt.strptime(date_from, '%Y-%m-%d').date()
                query = query.filter(StockIn.stock_in_date >= date_from_val)
            except ValueError:
                pass
        if date_to:
            try:
                from datetime import datetime as dt
                date_to_val = dt.strptime(date_to, '%Y-%m-%d').date()
                query = query.filter(StockIn.stock_in_date <= date_to_val)
            except ValueError:
                pass

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        stock_ins = pagination.items
        total_count = pagination.total
        total_pages = pagination.pages
        current_page = pagination.page
        page_range = generate_page_range(current_page, total_pages)

        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='records',
            action="访问入库管理页面",
            result="成功"
        )
        logging.info(f"加载入库管理页面，当前用户ID: {current_user.id}")

        # 获取入库单审核开关状态
        from models.system_config import SystemConfig
        approval_enabled = SystemConfig.get_config_value('STOCK_IN_APPROVAL_ENABLED', True)
        unapprove_enabled = SystemConfig.get_config_value('STOCK_IN_UNAPPROVE_ENABLED', True)

        return render_template(
            'supply_manage/stock_in_list.html',
            title="入库管理",
            # 入库单数据
            stock_ins=stock_ins,
            total_count=total_count,
            # 分页参数
            current_page=current_page,
            per_page=per_page,
            total_pages=total_pages,
            page_range=page_range,
            # 筛选配置
            statuses=statuses,
            stock_in_types=stock_in_types,
            suppliers=suppliers,
            # 当前筛选条件（回显）
            current_status=status,
            current_stock_in_type=stock_in_type,
            current_supplier_id=supplier_id,
            keyword=keyword,
            date_from=date_from,
            date_to=date_to,
            approval_enabled=approval_enabled,
            unapprove_enabled=unapprove_enabled
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='records',
            action=f"加载入库管理页面失败: {str(e)}",
            result="失败"
        )
        flash('加载入库单数据失败，请联系管理员', 'danger')
        logging.error(f"加载入库管理页面失败: {str(e)}")
        return render_template(
            'supply_manage/stock_in_list.html',
            title="入库管理",
            stock_ins=[],
            total_count=0,
            current_page=1,
            per_page=20,
            total_pages=0,
            page_range=[],
            statuses=['待审核', '已审核', '已取消'],
            stock_in_types=[],
            suppliers=[],
            current_status='',
            current_stock_in_type='',
            current_supplier_id='',
            keyword='',
            date_from='',
            date_to='',
            approval_enabled=True,
            unapprove_enabled=True
        )


# 新增入库单页面
@stock_in_bp.route('/add', methods=['GET'])
@login_required
@require_permission('supply.create')
def add_stock_in():
    try:
        departments = Department.query.order_by(Department.id).all()
        suppliers = Supplier.get_active_suppliers()
        locations = StorageLocation.query.filter_by(status='启用', usage_type='低值易耗品').order_by(StorageLocation.id).all()
        items = SupplyItem.query.filter_by(status='启用').order_by(SupplyItem.id).all()

        # 从系统配置获取入库类型选项
        from models.system_config import SystemConfig
        stock_in_types = SystemConfig.get_config_value('stock_in_types', '采购入库,其它入库')
        if isinstance(stock_in_types, str):
            stock_in_types = [t.strip() for t in stock_in_types.split(',') if t.strip()]

        # 从系统配置获取预设单位选项
        supply_units_value = SystemConfig.get_config_value('supply_units', '个,件,箱,包,盒,瓶,支,本,张,套,台,把,条,块,卷,桶,袋,罐')
        supply_units = supply_units_value if isinstance(supply_units_value, list) else [u.strip() for u in supply_units_value.split(',') if u.strip()]

        return render_template(
            'supply_manage/stock_in_form.html',
            title="新增入库单",
            stock_in=None,
            departments=departments,
            suppliers=suppliers,
            locations=locations,
            items=items,
            stock_in_types=stock_in_types,
            supply_units=supply_units
        )
    except Exception as e:
        logging.error(f"加载新增入库单页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('stock_in.list_stock_ins'))


# 编辑入库单页面（仅待审核状态可编辑）
@stock_in_bp.route('/edit/<int:id>', methods=['GET'])
@login_required
@require_permission('supply.edit')
def edit_stock_in(id):
    try:
        stock_in = StockIn.query.get_or_404(id)

        # 仅待审核状态可编辑
        if stock_in.status != '待审核':
            flash('仅待审核状态的入库单可以编辑', 'warning')
            return redirect(url_for('stock_in.detail_stock_in', id=id))

        departments = Department.query.order_by(Department.id).all()
        suppliers = Supplier.get_active_suppliers()
        locations = StorageLocation.query.filter_by(status='启用', usage_type='低值易耗品').order_by(StorageLocation.id).all()
        items = SupplyItem.query.filter_by(status='启用').order_by(SupplyItem.id).all()

        # 从系统配置获取入库类型选项
        from models.system_config import SystemConfig
        stock_in_types = SystemConfig.get_config_value('stock_in_types', '采购入库,其它入库')
        if isinstance(stock_in_types, str):
            stock_in_types = [t.strip() for t in stock_in_types.split(',') if t.strip()]

        # 从系统配置获取预设单位选项
        supply_units_value = SystemConfig.get_config_value('supply_units', '个,件,箱,包,盒,瓶,支,本,张,套,台,把,条,块,卷,桶,袋,罐')
        supply_units = supply_units_value if isinstance(supply_units_value, list) else [u.strip() for u in supply_units_value.split(',') if u.strip()]

        return render_template(
            'supply_manage/stock_in_form.html',
            title=f"编辑入库单 - {stock_in.stock_in_number}",
            stock_in=stock_in,
            departments=departments,
            suppliers=suppliers,
            locations=locations,
            items=items,
            stock_in_types=stock_in_types,
            supply_units=supply_units
        )
    except Exception as e:
        logging.error(f"加载编辑入库单页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('stock_in.list_stock_ins'))


# 入库单详情页面（含明细列表）
@stock_in_bp.route('/detail/<int:id>', methods=['GET'])
@login_required
@require_permission('supply.view')
def detail_stock_in(id):
    try:
        stock_in = StockIn.query.get_or_404(id)
        details = StockInDetail.query.filter_by(stock_in_id=id).order_by(StockInDetail.id).all()

        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='records',
            action=f"查看出库单详情 [ID: {id}, {stock_in.stock_in_number}]",
            result="成功"
        )
        logging.info(f"查看出库单详情，入库单ID: {id}")

        # 获取入库单审核开关状态
        from models.system_config import SystemConfig
        approval_enabled = SystemConfig.get_config_value('STOCK_IN_APPROVAL_ENABLED', True)
        unapprove_enabled = SystemConfig.get_config_value('STOCK_IN_UNAPPROVE_ENABLED', True)

        return render_template(
            'supply_manage/stock_in_detail.html',
            title=f"入库单详情 - {stock_in.stock_in_number}",
            stock_in=stock_in,
            details=details,
            approval_enabled=approval_enabled,
            unapprove_enabled=unapprove_enabled
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='records',
            action=f"查看出库单详情失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash('查看出库单详情失败，请重试', 'danger')
        logging.error(f"查看出库单详情失败，入库单ID: {id}, 错误: {str(e)}")
        return redirect(url_for('stock_in.list_stock_ins'))