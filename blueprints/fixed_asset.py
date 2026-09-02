from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from utils.db import db
from models.fixed_asset import FixedAsset
from models.asset_operation_record import AssetOperationRecord
from models.asset_inventory import AssetInventory
from models.asset_inventory_detail import AssetInventoryDetail
from models.system_config import SystemConfig
from models.department import Department
from utils.asset_photo import AssetPhotoManager
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
import logging
from models.room import Room
from models.user import User
from models.supply.supplier import Supplier
from models.supply.storage_location import StorageLocation

# 定义蓝图
fixed_asset_bp = Blueprint(
    'fixed_asset',
    __name__,
    url_prefix='/fixed_asset',
    template_folder='../templates',
    static_folder='../static',
    static_url_path='/fixed_asset/static'
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
from . import fixed_asset_operations


# 固定资产列表页（含筛选+分页）
@fixed_asset_bp.route('/', methods=['GET'])
@login_required
@require_permission('fixed_asset.view')
def index():
    try:
        # 获取筛选参数
        category = request.args.get('category', '').strip()
        status = request.args.get('status', '').strip()
        dept_using = request.args.get('dept_using', '').strip()
        dept_owning = request.args.get('dept_owning', '').strip()
        company = request.args.get('company', '').strip()
        keyword = request.args.get('keyword', '').strip()
        room_id = request.args.get('room_id', '').strip()

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # 参数校验
        if page < 1:
            page = 1
        per_page = max(10, min(100, per_page))

        # 从SystemConfig读取配置列表
        categories = SystemConfig.get_config_value('ASSET_CATEGORIES', ['办公设备', '家具', '交通工具', '电子设备', '机械设备', '其他'])
        statuses = SystemConfig.get_config_value('ASSET_STATUSES', ['在用', '闲置', '维修中', '已报废', '已转移', '已出售'])
        departments = Department.get_all_names()  # 用于筛选下拉选项
        locations = StorageLocation.get_all_names(usage_type='固定资产')
        companies = Department.get_all_companies()

        # 构建查询
        query = FixedAsset.query.order_by(FixedAsset.id.desc())

        if category:
            query = query.filter(FixedAsset.asset_category == category)
        if status:
            query = query.filter(FixedAsset.status == status)
        if dept_using:
            # 按部门名称查找ID再筛选
            dept = Department.query.filter_by(name=dept_using).first()
            if dept:
                query = query.filter(FixedAsset.department_using_id == dept.id)
            else:
                query = query.filter(FixedAsset.department_using_id == -1)  # 无匹配
        if dept_owning:
            dept = Department.query.filter_by(name=dept_owning).first()
            if dept:
                query = query.filter(FixedAsset.department_owning_id == dept.id)
            else:
                query = query.filter(FixedAsset.department_owning_id == -1)  # 无匹配
        if company:
            query = query.filter(FixedAsset.company == company)
        if room_id:
            query = query.filter(FixedAsset.room_id == int(room_id))
        if keyword:
            search_filter = f'%{keyword}%'
            # 支持按房间号搜索（需join Room表）
            query = query.outerjoin(Room, FixedAsset.room_id == Room.id)
            query = query.filter(
                db.or_(
                    FixedAsset.asset_number.ilike(search_filter),
                    FixedAsset.asset_name.ilike(search_filter),
                    FixedAsset.specification.ilike(search_filter),
                    Room.room_number.ilike(search_filter),
                    Room.building.ilike(search_filter)
                )
            )

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        assets = pagination.items
        total_count = pagination.total
        total_pages = pagination.pages
        current_page = pagination.page
        page_range = generate_page_range(current_page, total_pages)

        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action="访问固定资产管理页面",
            result="成功"
        )
        logging.info(f"加载固定资产管理页面，当前用户ID: {current_user.id}")

        return render_template(
            'fixed_asset_manage/fixed_asset_manage.html',
            title="固定资产管理",
            # 资产数据
            assets=assets,
            total_count=total_count,
            # 分页参数
            current_page=current_page,
            per_page=per_page,
            total_pages=total_pages,
            page_range=page_range,
            # 筛选配置
            categories=categories,
            statuses=statuses,
            departments=departments,
            locations=locations,
            companies=companies,
            # 当前筛选条件（回显）
            category=category,
            status=status,
            dept_using=dept_using,
            dept_owning=dept_owning,
            company=company,
            keyword=keyword,
            room_id=room_id
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action=f"加载固定资产管理页面失败: {str(e)}",
            result="失败"
        )
        flash('加载固定资产数据失败，请联系管理员', 'danger')
        logging.error(f"加载固定资产管理页面失败: {str(e)}")
        return render_template(
            'fixed_asset_manage/fixed_asset_manage.html',
            title="固定资产管理",
            assets=[],
            total_count=0,
            current_page=1,
            per_page=20,
            total_pages=0,
            page_range=[],
            categories=[],
            statuses=[],
            departments=[],
            locations=[],
            category='',
            status='',
            dept_using='',
            dept_owning='',
            keyword='',
            room_id=''
        )


# 资产详情页（含操作记录时间线）
@fixed_asset_bp.route('/detail/<int:id>', methods=['GET'])
@login_required
@require_permission('fixed_asset.view')
def detail(id):
    try:
        asset = FixedAsset.query.get_or_404(id)

        # 获取操作记录时间线（按时间倒序）
        operation_records = AssetOperationRecord.query.filter_by(
            asset_id=id
        ).order_by(AssetOperationRecord.operation_time.desc()).all()

        # 获取资产照片列表
        media_files = AssetPhotoManager.get_media_files(asset.id)

        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action=f"查看固定资产详情 [ID: {id}, {asset.display_number}]",
            result="成功"
        )
        logging.info(f"查看固定资产详情，资产ID: {id}")

        return render_template(
            'fixed_asset_manage/fixed_asset_detail.html',
            title=f"资产详情 - {asset.display_number}",
            asset=asset,
            operation_records=operation_records,
            media_files=media_files,
            companies=Department.get_all_companies()
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action=f"查看固定资产详情失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash('查看资产详情失败，请重试', 'danger')
        logging.error(f"查看固定资产详情失败，资产ID: {id}, 错误: {str(e)}")
        return redirect(url_for('fixed_asset.index'))


# 盘点管理列表页
@fixed_asset_bp.route('/inventory', methods=['GET'])
@login_required
@require_permission('fixed_asset.view')
def inventory():
    try:
        # 获取筛选参数
        inventory_status = request.args.get('status', '').strip()
        search = request.args.get('search', '').strip()

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # 参数校验
        if page < 1:
            page = 1
        per_page = max(10, min(100, per_page))

        # 构建查询
        query = AssetInventory.query.order_by(AssetInventory.created_at.desc())

        if inventory_status:
            query = query.filter(AssetInventory.status == inventory_status)

        if search:
            search_filter = f'%{search}%'
            query = query.filter(
                db.or_(
                    AssetInventory.inventory_number.ilike(search_filter),
                    AssetInventory.title.ilike(search_filter)
                )
            )

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        inventories = pagination.items
        total_count = pagination.total
        total_pages = pagination.pages
        current_page = pagination.page
        page_range = generate_page_range(current_page, total_pages)

        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action="访问资产盘点管理页面",
            result="成功"
        )
        logging.info(f"加载资产盘点管理页面，当前用户ID: {current_user.id}")

        return render_template(
            'fixed_asset_manage/fixed_asset_inventory.html',
            title="资产盘点管理",
            inventories=inventories,
            total_count=total_count,
            current_page=current_page,
            per_page=per_page,
            total_pages=total_pages,
            page_range=page_range,
            # 筛选条件回显
            inventory_status=inventory_status,
            search=search
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action=f"加载资产盘点管理页面失败: {str(e)}",
            result="失败"
        )
        flash('加载盘点数据失败，请联系管理员', 'danger')
        logging.error(f"加载资产盘点管理页面失败: {str(e)}")
        return render_template(
            'fixed_asset_manage/fixed_asset_inventory.html',
            title="资产盘点管理",
            inventories=[],
            total_count=0,
            current_page=1,
            per_page=20,
            total_pages=0,
            page_range=[],
            inventory_status='',
            search=''
        )


# 盘点详情页
@fixed_asset_bp.route('/inventory/detail/<int:id>', methods=['GET'])
@login_required
@require_permission('fixed_asset.view')
def inventory_detail(id):
    try:
        inventory_record = AssetInventory.query.get_or_404(id)

        # 获取筛选参数
        result_filter = request.args.get('result_filter', '').strip()
        category_filter = request.args.get('category_filter', '').strip()
        company_filter = request.args.get('company_filter', '').strip()
        department_filter = request.args.get('department_filter', '').strip()
        responsible_filter = request.args.get('responsible_filter', '').strip()
        search = request.args.get('search', '').strip()

        # 获取盘点明细列表
        query = AssetInventoryDetail.query.filter_by(
            inventory_id=id
        ).order_by(AssetInventoryDetail.id.asc())

        # 盘点结果筛选
        if result_filter:
            query = query.filter(AssetInventoryDetail.inventory_result == result_filter)

        # 判断是否需要join FixedAsset（避免重复join）
        need_join_asset = bool(search or category_filter or company_filter or responsible_filter or department_filter)

        if need_join_asset:
            query = query.join(FixedAsset, AssetInventoryDetail.asset_id == FixedAsset.id)

        # 分类筛选
        if category_filter:
            query = query.filter(FixedAsset.asset_category == category_filter)

        # 公司筛选
        if company_filter:
            query = query.filter(FixedAsset.company == company_filter)

        # 部门筛选（需join Department）
        if department_filter:
            query = query.join(Department, FixedAsset.department_using_id == Department.id).filter(
                Department.name == department_filter
            )

        # 责任人筛选
        if responsible_filter:
            query = query.filter(FixedAsset.responsible_person == responsible_filter)

        # 搜索（按资产编号/名称/规格/存放位置/责任人搜索）
        if search:
            search_filter = f'%{search}%'
            query = query.filter(
                db.or_(
                    FixedAsset.asset_number.ilike(search_filter),
                    FixedAsset.asset_name.ilike(search_filter),
                    FixedAsset.specification.ilike(search_filter),
                    FixedAsset.storage_location.ilike(search_filter),
                    FixedAsset.responsible_person.ilike(search_filter)
                )
            )

        details = query.all()

        # 获取下拉选项数据
        categories = [c[0] for c in db.session.query(FixedAsset.asset_category).distinct().order_by(FixedAsset.asset_category).all()]
        companies = Department.get_all_companies()
        departments = [d[0] for d in db.session.query(Department.name).filter(Department.status == '正常').distinct().order_by(Department.name).all()]
        responsible_persons = [r[0] for r in db.session.query(FixedAsset.responsible_person).filter(
            FixedAsset.responsible_person.isnot(None), FixedAsset.responsible_person != ''
        ).distinct().order_by(FixedAsset.responsible_person).all()]

        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action=f"查看盘点详情 [ID: {id}, {inventory_record.inventory_number}]",
            result="成功"
        )
        logging.info(f"查看盘点详情，盘点ID: {id}")

        return render_template(
            'fixed_asset_manage/fixed_asset_inventory_detail.html',
            title=f"盘点详情 - {inventory_record.title}",
            inventory_record=inventory_record,
            details=details,
            result_filter=result_filter,
            category_filter=category_filter,
            company_filter=company_filter,
            department_filter=department_filter,
            responsible_filter=responsible_filter,
            search=search,
            categories=categories,
            companies=companies,
            departments=departments,
            responsible_persons=responsible_persons,
            inventory_unapprove_enabled=SystemConfig.get_config_value('asset_inventory_unapprove_enabled', True)
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action=f"查看盘点详情失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash('查看盘点详情失败，请重试', 'danger')
        logging.error(f"查看盘点详情失败，盘点ID: {id}, 错误: {str(e)}")
        return redirect(url_for('fixed_asset.inventory'))


# 报废表单页
@fixed_asset_bp.route('/scrap/<int:id>', methods=['GET'])
@login_required
@require_permission('fixed_asset.scrap')
def scrap(id):
    try:
        asset = FixedAsset.query.get_or_404(id)

        # 仅对非报废/非出售状态资产显示
        if asset.status in ('已报废', '已出售'):
            flash('该资产已报废或已出售，无法再次操作', 'warning')
            return redirect(url_for('fixed_asset.detail', id=id))

        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action=f"访问资产报废表单 [ID: {id}, {asset.display_number}]",
            result="成功"
        )
        logging.info(f"访问资产报废表单，资产ID: {id}")

        return render_template(
            'fixed_asset_manage/fixed_asset_scrap.html',
            title=f"资产报废 - {asset.display_number}",
            asset=asset
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action=f"访问资产报废表单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash('加载报废表单失败，请重试', 'danger')
        logging.error(f"访问资产报废表单失败，资产ID: {id}, 错误: {str(e)}")
        return redirect(url_for('fixed_asset.detail', id=id))


# 出售表单页
@fixed_asset_bp.route('/sell/<int:id>', methods=['GET'])
@login_required
@require_permission('fixed_asset.sell')
def sell(id):
    try:
        asset = FixedAsset.query.get_or_404(id)

        # 仅对非报废/非出售状态资产显示
        if asset.status in ('已报废', '已出售'):
            flash('该资产已报废或已出售，无法再次操作', 'warning')
            return redirect(url_for('fixed_asset.detail', id=id))

        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action=f"访问资产出售表单 [ID: {id}, {asset.display_number}]",
            result="成功"
        )
        logging.info(f"访问资产出售表单，资产ID: {id}")

        return render_template(
            'fixed_asset_manage/fixed_asset_sell.html',
            title=f"资产出售 - {asset.display_number}",
            asset=asset
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action=f"访问资产出售表单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash('加载出售表单失败，请重试', 'danger')
        logging.error(f"访问资产出售表单失败，资产ID: {id}, 错误: {str(e)}")
        return redirect(url_for('fixed_asset.detail', id=id))


# 新增资产表单页
@fixed_asset_bp.route('/add', methods=['GET'])
@login_required
@require_permission('fixed_asset.create')
def add_page():
    # 从系统配置读取下拉选项（各项独立异常处理，避免单项失败导致整个页面无法加载）
    try:
        categories = SystemConfig.get_config_value('ASSET_CATEGORIES', ['办公设备', '家具', '交通工具', '电子设备', '机械设备', '其他'])
    except Exception as e:
        logging.warning(f"获取资产分类配置失败: {str(e)}")
        categories = ['办公设备', '家具', '交通工具', '电子设备', '机械设备', '其他']

    try:
        statuses = SystemConfig.get_config_value('ASSET_STATUSES', ['在用', '闲置', '维修中', '已报废', '已转移', '已出售'])
    except Exception as e:
        logging.warning(f"获取资产状态配置失败: {str(e)}")
        statuses = ['在用', '闲置', '维修中', '已报废', '已转移', '已出售']

    try:
        departments = Department.get_all_names()  # 用于筛选下拉选项
    except Exception as e:
        logging.warning(f"获取部门列表失败: {str(e)}")
        departments = []

    try:
        companies = Department.get_all_companies()
    except Exception as e:
        logging.warning(f"获取公司列表失败: {str(e)}")
        companies = []

    try:
        active_departments = Department.get_active_by_company(None)
    except Exception as e:
        logging.warning(f"获取活跃部门列表失败: {str(e)}")
        active_departments = []

    try:
        locations = StorageLocation.get_all_names(usage_type='固定资产')
    except Exception as e:
        logging.warning(f"获取存放位置列表失败: {str(e)}")
        locations = []

    try:
        suppliers = Supplier.get_all_names()
    except Exception as e:
        logging.warning(f"获取供应商列表失败: {str(e)}")
        suppliers = []

    try:
        units = SystemConfig.get_config_value('supply_units', ['个', '件', '箱', '包', '盒', '瓶', '支', '本', '张', '套', '台', '把'])
    except Exception as e:
        logging.warning(f"获取单位配置失败: {str(e)}")
        units = ['个', '件', '箱', '包', '盒', '瓶', '支', '本', '张', '套', '台', '把']

    try:
        sources = SystemConfig.get_config_value('ASSET_SOURCES', ['采购', '捐赠', '调入', '自建', '其他'])
    except Exception as e:
        logging.warning(f"获取资产来源配置失败: {str(e)}")
        sources = ['采购', '捐赠', '调入', '自建', '其他']

    # 获取用户列表（责任人下拉用）
    try:
        users = User.query.filter(User.status == '在职').order_by(User.name).all()
    except Exception as e:
        logging.warning(f"获取用户列表失败: {str(e)}")
        users = []

    # 获取房间列表（关联房间下拉用）
    try:
        rooms = Room.query.order_by(Room.building, Room.room_number).all()
    except Exception as e:
        logging.warning(f"获取房间列表失败: {str(e)}")
        rooms = []

    logging.info(f"访问新增资产页面，当前用户ID: {current_user.id}")

    try:
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action="访问新增资产页面",
            result="成功"
        )
    except Exception as log_err:
        logging.warning(f"记录操作日志失败: {str(log_err)}")

    return render_template(
        'fixed_asset_manage/fixed_asset_add.html',
        title="新增资产",
        categories=categories,
        statuses=statuses,
        departments=departments,
        companies=companies,
        active_departments=active_departments,
        locations=locations,
        suppliers=suppliers,
        units=units,
        sources=sources,
        users=users,
        rooms=rooms
    )


# 编辑资产表单页
@fixed_asset_bp.route('/edit/<int:id>', methods=['GET'])
@login_required
@require_permission('fixed_asset.edit')
def edit_page(id):
    asset = FixedAsset.query.get_or_404(id)

    # 从系统配置读取下拉选项（各项独立异常处理，避免单项失败导致整个页面无法加载）
    try:
        categories = SystemConfig.get_config_value('ASSET_CATEGORIES', ['办公设备', '家具', '交通工具', '电子设备', '机械设备', '其他'])
    except Exception as e:
        logging.warning(f"获取资产分类配置失败: {str(e)}")
        categories = ['办公设备', '家具', '交通工具', '电子设备', '机械设备', '其他']

    try:
        statuses = SystemConfig.get_config_value('ASSET_STATUSES', ['在用', '闲置', '维修中', '已报废', '已转移', '已出售'])
    except Exception as e:
        logging.warning(f"获取资产状态配置失败: {str(e)}")
        statuses = ['在用', '闲置', '维修中', '已报废', '已转移', '已出售']

    try:
        departments = Department.get_all_names()  # 用于筛选下拉选项
    except Exception as e:
        logging.warning(f"获取部门列表失败: {str(e)}")
        departments = []

    try:
        companies = Department.get_all_companies()
    except Exception as e:
        logging.warning(f"获取公司列表失败: {str(e)}")
        companies = []

    try:
        # 根据资产的公司获取对应部门列表
        asset_company = asset.company if asset else None
        active_departments = Department.get_active_by_company(asset_company)
    except Exception as e:
        logging.warning(f"获取活跃部门列表失败: {str(e)}")
        active_departments = []

    try:
        locations = StorageLocation.get_all_names(usage_type='固定资产')
    except Exception as e:
        logging.warning(f"获取存放位置列表失败: {str(e)}")
        locations = []

    try:
        suppliers = Supplier.get_all_names()
    except Exception as e:
        logging.warning(f"获取供应商列表失败: {str(e)}")
        suppliers = []

    try:
        units = SystemConfig.get_config_value('supply_units', ['个', '件', '箱', '包', '盒', '瓶', '支', '本', '张', '套', '台', '把'])
    except Exception as e:
        logging.warning(f"获取单位配置失败: {str(e)}")
        units = ['个', '件', '箱', '包', '盒', '瓶', '支', '本', '张', '套', '台', '把']

    try:
        sources = SystemConfig.get_config_value('ASSET_SOURCES', ['采购', '捐赠', '调入', '自建', '其他'])
    except Exception as e:
        logging.warning(f"获取资产来源配置失败: {str(e)}")
        sources = ['采购', '捐赠', '调入', '自建', '其他']

    # 获取资产照片列表（独立异常处理）
    try:
        media_files = AssetPhotoManager.get_media_files(asset.id)
    except Exception as photo_err:
        logging.warning(f"获取资产照片列表失败，资产ID: {id}, 错误: {str(photo_err)}")
        media_files = []

    # 获取用户列表（责任人下拉用）
    try:
        users = User.query.filter(User.status == '在职').order_by(User.name).all()
    except Exception as e:
        logging.warning(f"获取用户列表失败: {str(e)}")
        users = []

    # 获取房间列表（关联房间下拉用）
    try:
        rooms = Room.query.order_by(Room.building, Room.room_number).all()
    except Exception as e:
        logging.warning(f"获取房间列表失败: {str(e)}")
        rooms = []

    logging.info(f"访问编辑资产页面，资产ID: {id}, 部门数量: {len(departments) if departments else 0}")

    try:
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action=f"访问编辑资产页面 [ID: {id}, {asset.display_number}]",
            result="成功"
        )
    except Exception as log_err:
        logging.warning(f"记录操作日志失败: {str(log_err)}")

    return render_template(
        'fixed_asset_manage/fixed_asset_edit.html',
        title=f"编辑资产 - {asset.display_number}",
        asset=asset,
        categories=categories,
        statuses=statuses,
        departments=departments,
        companies=companies,
        active_departments=active_departments,
        locations=locations,
        suppliers=suppliers,
        units=units,
        sources=sources,
        media_files=media_files,
        users=users,
        rooms=rooms
    )


# 资产转移表单页
@fixed_asset_bp.route('/transfer/<int:id>', methods=['GET'])
@login_required
@require_permission('fixed_asset.transfer')
def transfer_page(id):
    asset = FixedAsset.query.get_or_404(id)

    # 仅对在用/闲置/维修中状态资产显示
    if asset.status not in ('在用', '闲置', '维修中'):
        flash('该资产当前状态不允许转移', 'warning')
        return redirect(url_for('fixed_asset.detail', id=id))

    # 从系统配置读取下拉选项（各项独立异常处理）
    try:
        departments = Department.get_all_names()  # 用于筛选下拉选项
    except Exception as e:
        logging.warning(f"获取部门列表失败: {str(e)}")
        departments = []

    try:
        companies = Department.get_all_companies()
    except Exception as e:
        logging.warning(f"获取公司列表失败: {str(e)}")
        companies = []

    try:
        # 根据资产的公司获取对应部门列表
        asset_company = asset.company if asset else None
        active_departments = Department.get_active_by_company(asset_company)
    except Exception as e:
        logging.warning(f"获取活跃部门列表失败: {str(e)}")
        active_departments = []

    try:
        locations = StorageLocation.get_all_names(usage_type='固定资产')
    except Exception as e:
        logging.warning(f"获取存放位置列表失败: {str(e)}")
        locations = []

    # 获取用户列表（责任人下拉用）
    try:
        users = User.query.filter(User.status == '在职').order_by(User.name).all()
    except Exception as e:
        logging.warning(f"获取用户列表失败: {str(e)}")
        users = []

    # 获取房间列表（关联房间下拉用）
    try:
        rooms = Room.query.order_by(Room.building, Room.room_number).all()
    except Exception as e:
        logging.warning(f"获取房间列表失败: {str(e)}")
        rooms = []

    logging.info(f"访问资产转移页面，资产ID: {id}")

    try:
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action=f"访问资产转移页面 [ID: {id}, {asset.display_number}]",
            result="成功"
        )
    except Exception as log_err:
        logging.warning(f"记录操作日志失败: {str(log_err)}")

    return render_template(
        'fixed_asset_manage/fixed_asset_transfer.html',
        title=f"资产转移 - {asset.display_number}",
        asset=asset,
        departments=departments,
        companies=companies,
        active_departments=active_departments,
        locations=locations,
        users=users,
        rooms=rooms
    )


# AJAX: 根据公司获取部门列表
@fixed_asset_bp.route('/api/departments-by-company', methods=['GET'])
@login_required
def api_departments_by_company():
    """根据公司名称获取状态为正常的部门列表（AJAX级联查询）"""
    try:
        company = request.args.get('company', '').strip()
        # company为空字符串时传None，查询未指定公司的部门
        departments = Department.get_active_by_company(company if company else None)
        dept_list = [{'id': d.id, 'name': d.name} for d in departments]
        return jsonify({'success': True, 'departments': dept_list}), 200
    except Exception as e:
        logging.error(f"获取部门列表失败: {str(e)}")
        return jsonify({'success': False, 'message': '获取部门列表失败'}), 500


# 创建盘点单表单页
@fixed_asset_bp.route('/inventory/create', methods=['GET'])
@login_required
@require_permission('fixed_asset.inventory')
def inventory_create_page():
    try:
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action="访问创建盘点单页面",
            result="成功"
        )
        logging.info(f"访问创建盘点单页面，当前用户ID: {current_user.id}")

        return render_template(
            'fixed_asset_manage/fixed_asset_inventory_create.html',
            title="创建盘点单"
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='records',
            action=f"访问创建盘点单页面失败: {str(e)}",
            result="失败"
        )
        flash('加载创建盘点单页面失败，请重试', 'danger')
        logging.error(f"访问创建盘点单页面失败: {str(e)}")
        return redirect(url_for('fixed_asset.inventory'))