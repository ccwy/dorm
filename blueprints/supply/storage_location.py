from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from utils.db import db
from models.supply.storage_location import StorageLocation
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
import logging

# 定义蓝图
storage_location_bp = Blueprint(
    'storage_location',
    __name__,
    url_prefix='/storage-location',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/storage-location/static'
)


def get_usage_types():
    """从系统配置获取存放位置使用类型选项，返回中文列表"""
    try:
        from models.system_config.system_config import SystemConfig
        usage_types = SystemConfig.get_config_value('storage_location_usage_types', '低值易耗品,固定资产,合同管理')
        if isinstance(usage_types, str):
            usage_types = [v.strip() for v in usage_types.split(',') if v.strip()]
        if not usage_types:
            usage_types = ['低值易耗品', '固定资产', '合同管理']
    except Exception:
        usage_types = ['低值易耗品', '固定资产', '合同管理']
    return usage_types

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
from . import storage_location_operations


# 存放位置列表页（含筛选+分页）
@storage_location_bp.route('/', methods=['GET'])
@login_required
@require_permission('supply.view')
def index():
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        status = request.args.get('status', '').strip()
        usage_type = request.args.get('usage_type', '').strip()

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # 参数校验
        if page < 1:
            page = 1
        per_page = max(10, min(100, per_page))

        # 获取筛选选项
        statuses = ['启用', '停用']
        usage_types = get_usage_types()

        # 构建查询
        query = StorageLocation.query.order_by(StorageLocation.id.desc())

        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    StorageLocation.name.ilike(search_filter),
                    StorageLocation.code.ilike(search_filter),
                    StorageLocation.building.ilike(search_filter),
                    StorageLocation.room.ilike(search_filter)
                )
            )
        if status:
            query = query.filter(StorageLocation.status == status)
        if usage_type:
            query = query.filter(StorageLocation.usage_type == usage_type)

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        locations = pagination.items
        total_count = pagination.total
        total_pages = pagination.pages
        current_page = pagination.page
        page_range = generate_page_range(current_page, total_pages)

        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='records',
            action="访问存放位置管理页面",
            result="成功"
        )
        logging.info(f"加载存放位置管理页面，当前用户ID: {current_user.id}")

        return render_template(
            'supply_manage/location_list.html',
            title="存放位置管理",
            # 存放位置数据
            locations=locations,
            total_count=total_count,
            # 分页参数
            current_page=current_page,
            per_page=per_page,
            total_pages=total_pages,
            page_range=page_range,
            # 筛选配置
            statuses=statuses,
            usage_types=usage_types,
            # 当前筛选条件（回显）
            current_status=status,
            current_usage_type=usage_type,
            keyword=keyword
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='records',
            action=f"加载存放位置管理页面失败: {str(e)}",
            result="失败"
        )
        flash('加载存放位置数据失败，请联系管理员', 'danger')
        logging.error(f"加载存放位置管理页面失败: {str(e)}")
        return render_template(
            'supply_manage/location_list.html',
            title="存放位置管理",
            locations=[],
            total_count=0,
            current_page=1,
            per_page=20,
            total_pages=0,
            page_range=[],
            companies=[],
            statuses=['启用', '停用'],
            usage_types=get_usage_types(),
            current_status='',
            current_usage_type='',
            keyword=''
        )


# 新增存放位置页面
@storage_location_bp.route('/add', methods=['GET'])
@login_required
@require_permission('supply.create')
def add_page():
    try:
        usage_types = get_usage_types()
        return render_template(
            'supply_manage/location_form.html',
            title="新增存放位置",
            location=None,
            usage_types=usage_types
        )
    except Exception as e:
        logging.error(f"加载新增存放位置页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('storage_location.index'))


# 编辑存放位置页面
@storage_location_bp.route('/edit/<int:id>', methods=['GET'])
@login_required
@require_permission('supply.edit')
def edit_page(id):
    try:
        location = StorageLocation.query.get_or_404(id)
        usage_types = get_usage_types()
        return render_template(
            'supply_manage/location_form.html',
            title=f"编辑存放位置 - {location.name}",
            location=location,
            usage_types=usage_types
        )
    except Exception as e:
        logging.error(f"加载编辑存放位置页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('storage_location.index'))


# 存放位置详情页（含库存明细）
@storage_location_bp.route('/detail/<int:id>', methods=['GET'])
@login_required
@require_permission('supply.view')
def detail(id):
    try:
        location = StorageLocation.query.get_or_404(id)

        # 根据usage_type查询不同的库存明细
        stock_details = []
        fixed_assets = []
        contracts = []

        if location.usage_type == '低值易耗品':
            # 低值易耗品：查询SupplyStockDetail
            from models.supply.supply_stock_detail import SupplyStockDetail
            stock_details = SupplyStockDetail.get_stock_by_location(id)
        elif location.usage_type == '固定资产':
            # 固定资产：通过storage_location(String)与location.name匹配
            from models.fixed_asset.fixed_asset import FixedAsset
            fixed_assets = FixedAsset.query.filter(
                FixedAsset.storage_location == location.name
            ).order_by(FixedAsset.id).all()
        elif location.usage_type == '合同管理':
            # 合同管理：通过storage_location_id(FK)与location.id匹配
            from models.contract.contract import Contract
            contracts = Contract.query.filter(
                Contract.storage_location_id == location.id
            ).order_by(Contract.id).all()

        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='records',
            action=f"查看存放位置详情 [ID: {id}, {location.name}]",
            result="成功"
        )
        logging.info(f"查看存放位置详情，位置ID: {id}")

        usage_types = get_usage_types()
        return render_template(
            'supply_manage/location_detail.html',
            title=f"存放位置详情 - {location.name}",
            location=location,
            stock_details=stock_details,
            fixed_assets=fixed_assets,
            contracts=contracts,
            usage_types=usage_types
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='records',
            action=f"查看存放位置详情失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash('查看存放位置详情失败，请重试', 'danger')
        logging.error(f"查看存放位置详情失败，位置ID: {id}, 错误: {str(e)}")
        return redirect(url_for('storage_location.index'))