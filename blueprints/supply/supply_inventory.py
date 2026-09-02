import json
from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from utils.db import db
from models.supply.supply_inventory import SupplyInventory
from models.supply.supply_inventory_detail import SupplyInventoryDetail
from models.supply.supply_item import SupplyItem
from models.supply.storage_location import StorageLocation
from models.supply.supply_stock_detail import SupplyStockDetail
from models.user import User
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
import logging

# 定义蓝图
supply_inventory_bp = Blueprint(
    'supply_inventory',
    __name__,
    url_prefix='/supply-inventory',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/supply-inventory/static'
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
import blueprints.supply.supply_inventory_operations


# 盘点单列表页（含筛选+分页）
@supply_inventory_bp.route('/', methods=['GET'])
@login_required
@require_permission('supply.view')
def list_inventories():
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

        # 构建查询
        query = SupplyInventory.query.order_by(SupplyInventory.created_at.desc())

        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    SupplyInventory.inventory_number.ilike(search_filter),
                    SupplyInventory.title.ilike(search_filter)
                )
            )
        if status:
            query = query.filter(SupplyInventory.status == status)

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        inventories = pagination.items
        total_count = pagination.total
        total_pages = pagination.pages
        current_page = pagination.page
        page_range = generate_page_range(current_page, total_pages)

        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='supply_inventory',
            operation_type='records',
            action="访问盘点管理页面",
            result="成功"
        )
        logging.info(f"加载盘点管理页面，当前用户ID: {current_user.id}")

        # 获取盘点反审核开关配置
        from models.system_config import SystemConfig
        inventory_unapprove_enabled = SystemConfig.get_config_value('supply_inventory_unapprove_enabled', True)

        return render_template(
            'supply_manage/inventory_list.html',
            title="盘点管理",
            inventories=inventories,
            total_count=total_count,
            current_page=current_page,
            per_page=per_page,
            total_pages=total_pages,
            page_range=page_range,
            current_status=status,
            keyword=keyword,
            inventory_unapprove_enabled=inventory_unapprove_enabled
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='supply_inventory',
            operation_type='records',
            action=f"加载盘点管理页面失败: {str(e)}",
            result="失败"
        )
        flash('加载盘点单数据失败，请联系管理员', 'danger')
        logging.error(f"加载盘点管理页面失败: {str(e)}")
        return render_template(
            'supply_manage/inventory_list.html',
            title="盘点管理",
            inventories=[],
            total_count=0,
            current_page=1,
            per_page=20,
            total_pages=0,
            page_range=[],
            current_status='',
            keyword='',
            inventory_unapprove_enabled=True
        )


# 创建盘点单页面
@supply_inventory_bp.route('/create', methods=['GET'])
@login_required
@require_permission('supply.create')
def create_inventory_page():
    try:
        log_operation(
            user_id=current_user.id,
            module='supply_inventory',
            operation_type='records',
            action="访问创建盘点单页面",
            result="成功"
        )
        logging.info(f"访问创建盘点单页面，当前用户ID: {current_user.id}")

        return render_template(
            'supply_manage/inventory_create.html',
            title="创建盘点单"
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='supply_inventory',
            operation_type='records',
            action=f"访问创建盘点单页面失败: {str(e)}",
            result="失败"
        )
        flash('加载创建盘点单页面失败，请重试', 'danger')
        logging.error(f"访问创建盘点单页面失败: {str(e)}")
        return redirect(url_for('supply_inventory.list_inventories'))


# 盘点单详情页面（含逐条盘点功能）
@supply_inventory_bp.route('/detail/<int:id>', methods=['GET'])
@login_required
@require_permission('supply.view')
def detail_inventory(id):
    try:
        inventory = SupplyInventory.query.get_or_404(id)

        # 获取筛选参数
        result_filter = request.args.get('result_filter', '').strip()
        search = request.args.get('search', '').strip()

        # 获取盘点明细列表
        query = SupplyInventoryDetail.query.filter_by(
            inventory_id=id
        ).order_by(SupplyInventoryDetail.id.asc())

        # 盘点结果筛选
        if result_filter:
            query = query.filter(SupplyInventoryDetail.inventory_result == result_filter)

        # 搜索（按物品名称/规格/物品编号/存放位置搜索）
        if search:
            search_filter = f'%{search}%'
            # 需要join SupplyItem和StorageLocation
            query = query.join(SupplyItem, SupplyInventoryDetail.item_id == SupplyItem.id)
            query = query.join(StorageLocation, SupplyInventoryDetail.location_id == StorageLocation.id)
            query = query.filter(
                db.or_(
                    SupplyItem.name.ilike(search_filter),
                    SupplyItem.specification.ilike(search_filter),
                    SupplyItem.item_number.ilike(search_filter),
                    StorageLocation.name.ilike(search_filter)
                )
            )

        details = query.all()

        # 构建实时库存映射（用于判断账面为0的无效明细）
        stock_map = {}
        for detail in details:
            stock_detail = SupplyStockDetail.query.filter_by(
                item_id=detail.item_id,
                location_id=detail.location_id
            ).first()
            stock_map[(detail.item_id, detail.location_id)] = stock_detail.quantity if stock_detail else 0

        log_operation(
            user_id=current_user.id,
            module='supply_inventory',
            operation_type='records',
            action=f"查看盘点单详情 [ID: {id}, {inventory.inventory_number}]",
            result="成功"
        )
        logging.info(f"查看盘点单详情，盘点ID: {id}")

        # 获取盘点反审核开关配置
        from models.system_config import SystemConfig
        inventory_unapprove_enabled = SystemConfig.get_config_value('supply_inventory_unapprove_enabled', True)

        return render_template(
            'supply_manage/inventory_detail.html',
            title=f"盘点详情 - {inventory.title}",
            inventory_record=inventory,
            details=details,
            result_filter=result_filter,
            search=search,
            inventory_unapprove_enabled=inventory_unapprove_enabled,
            stock_map=stock_map
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='supply_inventory',
            operation_type='records',
            action=f"查看盘点单详情失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash('查看盘点单详情失败，请重试', 'danger')
        logging.error(f"查看盘点单详情失败，盘点ID: {id}, 错误: {str(e)}")
        return redirect(url_for('supply_inventory.list_inventories'))