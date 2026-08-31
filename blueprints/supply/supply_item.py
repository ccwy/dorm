from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from utils.db import db
from models.supply.supply_item import SupplyItem
from models.supply.supplier import Supplier
from models.supply.storage_location import StorageLocation
from models.system_config import SystemConfig
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
import logging

# 定义蓝图
supply_item_bp = Blueprint(
    'supply_item',
    __name__,
    url_prefix='/supply-item',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/supply-item/static'
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
from . import supply_item_operations


# 物品列表页（含筛选+分页）
@supply_item_bp.route('/', methods=['GET'])
@login_required
@require_permission('supply.view')
def index():
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        category = request.args.get('category', '').strip()
        status = request.args.get('status', '').strip()
        supplier_id = request.args.get('supplier_id', type=int)
        location_id = request.args.get('location_id', type=int)
        low_stock = request.args.get('low_stock', '').strip()

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # 参数校验
        if page < 1:
            page = 1
        per_page = max(10, min(100, per_page))

        # 获取筛选选项
        statuses = ['启用', '停用']
        suppliers = Supplier.get_active_suppliers()
        locations = StorageLocation.get_active_locations(usage_type='低值易耗品')

        # 构建查询
        query = SupplyItem.query.order_by(SupplyItem.id.desc())

        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    SupplyItem.name.ilike(search_filter),
                    SupplyItem.item_number.ilike(search_filter),
                    SupplyItem.specification.ilike(search_filter)
                )
            )
        if category:
            query = query.filter(SupplyItem.category == category)
        if status:
            query = query.filter(SupplyItem.status == status)
        if supplier_id:
            query = query.filter(SupplyItem.supplier_id == supplier_id)
        if low_stock == '1':
            from models.system_config import SystemConfig
            if SystemConfig.get_config_value('supply_low_stock_alert', True):
                query = query.filter(SupplyItem.current_stock <= SupplyItem.min_stock)

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        items = pagination.items
        total_count = pagination.total
        total_pages = pagination.pages
        current_page = pagination.page
        page_range = generate_page_range(current_page, total_pages)

        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='records',
            action="访问基础物料资料页面",
            result="成功"
        )
        logging.info(f"加载基础物料资料页面，当前用户ID: {current_user.id}")

        return render_template(
            'supply_manage/item_list.html',
            title="基础物料资料",
            # 物品数据
            items=items,
            total_count=total_count,
            # 分页参数
            current_page=current_page,
            per_page=per_page,
            total_pages=total_pages,
            page_range=page_range,
            # 筛选配置
            statuses=statuses,
            suppliers=suppliers,
            locations=locations,
            # 当前筛选条件（回显）
            current_category=category,
            current_status=status,
            current_supplier_id=supplier_id,
            current_location_id=location_id,
            low_stock=low_stock,
            keyword=keyword
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='records',
            action=f"加载基础物料资料页面失败: {str(e)}",
            result="失败"
        )
        flash('加载物品数据失败，请联系管理员', 'danger')
        logging.error(f"加载基础物料资料页面失败: {str(e)}")
        return render_template(
            'supply_manage/item_list.html',
            title="基础物料资料",
            items=[],
            total_count=0,
            current_page=1,
            per_page=20,
            total_pages=0,
            page_range=[],
            companies=[],
            statuses=['启用', '停用'],
            suppliers=[],
            locations=[],
            current_category='',
            current_status='',
            current_supplier_id=None,
            current_location_id=None,
            low_stock='',
            keyword=''
        )


# 新增物品页面
@supply_item_bp.route('/add', methods=['GET'])
@login_required
@require_permission('supply.create')
def add_page():
    try:
        suppliers = Supplier.get_active_suppliers()
        locations = StorageLocation.get_active_locations(usage_type='低值易耗品')
        # 读取预设单位配置（get_config_value对list类型返回列表，对不存在的配置返回字符串）
        supply_units_value = SystemConfig.get_config_value('supply_units', '个,件,箱,包,盒,瓶,支,本,张,套,台,把,条,块,卷,桶,袋,罐')
        supply_units = supply_units_value if isinstance(supply_units_value, list) else [u.strip() for u in supply_units_value.split(',') if u.strip()]
        # 读取预设分类配置
        supply_categories_value = SystemConfig.get_config_value('supply_categories', '文具,办公设备,耗材,清洁用品,其他')
        supply_categories = supply_categories_value if isinstance(supply_categories_value, list) else [c.strip() for c in supply_categories_value.split(',') if c.strip()]
        return render_template(
            'supply_manage/item_form.html',
            title="新增物品",
            item=None,
            suppliers=suppliers,
            locations=locations,
            supply_units=supply_units,
            supply_categories=supply_categories
        )
    except Exception as e:
        logging.error(f"加载新增物品页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('supply_item.index'))


# 编辑物品页面
@supply_item_bp.route('/edit/<int:id>', methods=['GET'])
@login_required
@require_permission('supply.edit')
def edit_page(id):
    try:
        item = SupplyItem.query.get_or_404(id)
        suppliers = Supplier.get_active_suppliers()
        locations = StorageLocation.get_active_locations(usage_type='低值易耗品')
        # 读取预设单位配置（get_config_value对list类型返回列表，对不存在的配置返回字符串）
        supply_units_value = SystemConfig.get_config_value('supply_units', '个,件,箱,包,盒,瓶,支,本,张,套,台,把,条,块,卷,桶,袋,罐')
        supply_units = supply_units_value if isinstance(supply_units_value, list) else [u.strip() for u in supply_units_value.split(',') if u.strip()]
        # 读取预设分类配置
        supply_categories_value = SystemConfig.get_config_value('supply_categories', '文具,办公设备,耗材,清洁用品,其他')
        supply_categories = supply_categories_value if isinstance(supply_categories_value, list) else [c.strip() for c in supply_categories_value.split(',') if c.strip()]
        return render_template(
            'supply_manage/item_form.html',
            title=f"编辑物品 - {item.name}",
            item=item,
            suppliers=suppliers,
            locations=locations,
            supply_units=supply_units,
            supply_categories=supply_categories
        )
    except Exception as e:
        logging.error(f"加载编辑物品页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('supply_item.index'))


# 物品详情页（含库存明细和进出库记录）
@supply_item_bp.route('/detail/<int:id>', methods=['GET'])
@login_required
@require_permission('supply.view')
def detail(id):
    try:
        item = SupplyItem.query.get_or_404(id)

        # 获取各位置库存明细
        from models.supply.supply_stock_detail import SupplyStockDetail
        stock_details = SupplyStockDetail.get_stock_by_item(id)

        # 获取最近进出库记录
        from models.supply.supply_stock_record import SupplyStockRecord
        recent_records = SupplyStockRecord.query.filter_by(
            item_id=id
        ).order_by(SupplyStockRecord.record_date.desc()).limit(20).all()

        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='records',
            action=f"查看物品详情 [ID: {id}, {item.name}]",
            result="成功"
        )
        logging.info(f"查看物品详情，物品ID: {id}")

        return render_template(
            'supply_manage/item_detail.html',
            title=f"物品详情 - {item.name}",
            item=item,
            stock_details=stock_details,
            recent_records=recent_records
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='records',
            action=f"查看物品详情失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash('查看物品详情失败，请重试', 'danger')
        logging.error(f"查看物品详情失败，物品ID: {id}, 错误: {str(e)}")
        return redirect(url_for('supply_item.index'))