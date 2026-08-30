from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from utils.db import db
from models.supply.stock_out import StockOut
from models.supply.stock_out_detail import StockOutDetail
from models.supply.supply_item import SupplyItem
from models.supply.storage_location import StorageLocation
from models.supply.supply_stock_detail import SupplyStockDetail
from models.department import Department
from models.user import User
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
import logging

# 定义蓝图
stock_out_bp = Blueprint(
    'stock_out',
    __name__,
    url_prefix='/stock-out',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/stock-out/static'
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
from . import stock_out_operations


# 出库单列表页（含筛选+分页）
@stock_out_bp.route('/', methods=['GET'])
@login_required
@require_permission('supply.view')
def list_stock_outs():
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        stock_out_type = request.args.get('stock_out_type', '').strip()
        status = request.args.get('status', '').strip()
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

        # 从系统配置获取出库类型选项
        from models.system_config import SystemConfig
        stock_out_types = SystemConfig.get_config_value('stock_out_types', '正常领用,其他出库')
        if isinstance(stock_out_types, str):
            stock_out_types = [t.strip() for t in stock_out_types.split(',') if t.strip()]

        # 构建查询
        query = StockOut.query.order_by(StockOut.id.desc())

        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    StockOut.stock_out_number.ilike(search_filter),
                    StockOut.remark.ilike(search_filter)
                )
            )
        if stock_out_type:
            query = query.filter(StockOut.stock_out_type == stock_out_type)
        if status:
            query = query.filter(StockOut.status == status)
        if date_from:
            try:
                from datetime import datetime as dt
                date_from_val = dt.strptime(date_from, '%Y-%m-%d').date()
                query = query.filter(StockOut.stock_out_date >= date_from_val)
            except ValueError:
                pass
        if date_to:
            try:
                from datetime import datetime as dt
                date_to_val = dt.strptime(date_to, '%Y-%m-%d').date()
                query = query.filter(StockOut.stock_out_date <= date_to_val)
            except ValueError:
                pass

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        stock_outs = pagination.items
        total_count = pagination.total
        total_pages = pagination.pages
        current_page = pagination.page
        page_range = generate_page_range(current_page, total_pages)

        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='records',
            action="访问出库管理页面",
            result="成功"
        )
        logging.info(f"加载出库管理页面，当前用户ID: {current_user.id}")

        # 获取出库单审核开关状态
        from models.system_config import SystemConfig
        approval_enabled = SystemConfig.get_config_value('STOCK_OUT_APPROVAL_ENABLED', True)

        return render_template(
            'supply_manage/stock_out_list.html',
            title="出库管理",
            # 出库单数据
            stock_outs=stock_outs,
            total_count=total_count,
            # 分页参数
            current_page=current_page,
            per_page=per_page,
            total_pages=total_pages,
            page_range=page_range,
            # 筛选配置
            statuses=statuses,
            stock_out_types=stock_out_types,
            # 当前筛选条件（回显）
            current_status=status,
            current_stock_out_type=stock_out_type,
            keyword=keyword,
            date_from=date_from,
            date_to=date_to,
            approval_enabled=approval_enabled
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='records',
            action=f"加载出库管理页面失败: {str(e)}",
            result="失败"
        )
        flash('加载出库单数据失败，请联系管理员', 'danger')
        logging.error(f"加载出库管理页面失败: {str(e)}")
        return render_template(
            'supply_manage/stock_out_list.html',
            title="出库管理",
            stock_outs=[],
            total_count=0,
            current_page=1,
            per_page=20,
            total_pages=0,
            page_range=[],
            statuses=['待审核', '已审核', '已取消'],
            stock_out_types=[],
            current_status='',
            current_stock_out_type='',
            keyword='',
            date_from='',
            date_to='',
            approval_enabled=True
        )


# 新增出库单页面
@stock_out_bp.route('/add', methods=['GET'])
@login_required
@require_permission('supply.create')
def add_stock_out():
    try:
        departments = Department.query.order_by(Department.id).all()
        users = User.query.order_by(User.id).all()
        locations = StorageLocation.query.filter_by(status='启用', usage_type='supply').order_by(StorageLocation.id).all()
        items = SupplyItem.query.filter_by(status='启用').order_by(SupplyItem.id).all()

        # 从系统配置获取出库类型选项
        from models.system_config import SystemConfig
        stock_out_types = SystemConfig.get_config_value('stock_out_types', '正常领用,其他出库')
        if isinstance(stock_out_types, str):
            stock_out_types = [t.strip() for t in stock_out_types.split(',') if t.strip()]

        return render_template(
            'supply_manage/stock_out_form.html',
            title="新增出库单",
            stock_out=None,
            departments=departments,
            users=users,
            locations=locations,
            items=items,
            stock_out_types=stock_out_types
        )
    except Exception as e:
        logging.error(f"加载新增出库单页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('stock_out.list_stock_outs'))





# API：获取物品实际库存位置（用于出库明细选择物品后筛选位置）
@stock_out_bp.route('/api/item-locations/<int:item_id>', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_item_locations(item_id):
    """获取指定物品有库存的存放位置列表"""
    try:
        stock_details = SupplyStockDetail.query.filter_by(item_id=item_id)\
            .filter(SupplyStockDetail.quantity > 0)\
            .order_by(SupplyStockDetail.location_id).all()
        locations = []
        for sd in stock_details:
            locations.append({
                'id': sd.location_id,
                'name': sd.location_name,
                'quantity': sd.quantity
            })
        return jsonify({'success': True, 'locations': locations})
    except Exception as e:
        logging.error(f"获取物品库存位置失败，物品ID: {item_id}, 错误: {str(e)}")
        return jsonify({'success': False, 'locations': [], 'error': str(e)}), 500


# 编辑出库单页面（仅待审核状态可编辑）
@stock_out_bp.route('/edit/<int:id>', methods=['GET'])
@login_required
@require_permission('supply.edit')
def edit_stock_out(id):
    try:
        stock_out = StockOut.query.get_or_404(id)

        # 仅待审核状态可编辑
        if stock_out.status != '待审核':
            flash('仅待审核状态的出库单可以编辑', 'warning')
            return redirect(url_for('stock_out.detail_stock_out', id=id))

        departments = Department.query.order_by(Department.id).all()
        users = User.query.order_by(User.id).all()
        locations = StorageLocation.query.filter_by(status='启用', usage_type='supply').order_by(StorageLocation.id).all()
        items = SupplyItem.query.filter_by(status='启用').order_by(SupplyItem.id).all()

        # 从系统配置获取出库类型选项
        from models.system_config import SystemConfig
        stock_out_types = SystemConfig.get_config_value('stock_out_types', '正常领用,其他出库')
        if isinstance(stock_out_types, str):
            stock_out_types = [t.strip() for t in stock_out_types.split(',') if t.strip()]

        return render_template(
            'supply_manage/stock_out_form.html',
            title=f"编辑出库单 - {stock_out.stock_out_number}",
            stock_out=stock_out,
            departments=departments,
            users=users,
            locations=locations,
            items=items,
            stock_out_types=stock_out_types
        )
    except Exception as e:
        logging.error(f"加载编辑出库单页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('stock_out.list_stock_outs'))


# 出库单详情页面（含明细列表）
@stock_out_bp.route('/detail/<int:id>', methods=['GET'])
@login_required
@require_permission('supply.view')
def detail_stock_out(id):
    try:
        stock_out = StockOut.query.get_or_404(id)
        details = StockOutDetail.query.filter_by(stock_out_id=id).order_by(StockOutDetail.id).all()

        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='records',
            action=f"查看出库单详情 [ID: {id}, {stock_out.stock_out_number}]",
            result="成功"
        )
        logging.info(f"查看出库单详情，出库单ID: {id}")

        # 获取出库单审核开关状态
        from models.system_config import SystemConfig
        approval_enabled = SystemConfig.get_config_value('STOCK_OUT_APPROVAL_ENABLED', True)

        return render_template(
            'supply_manage/stock_out_detail.html',
            title=f"出库单详情 - {stock_out.stock_out_number}",
            stock_out=stock_out,
            details=details,
            approval_enabled=approval_enabled
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='records',
            action=f"查看出库单详情失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash('查看出库单详情失败，请重试', 'danger')
        logging.error(f"查看出库单详情失败，出库单ID: {id}, 错误: {str(e)}")
        return redirect(url_for('stock_out.list_stock_outs'))


