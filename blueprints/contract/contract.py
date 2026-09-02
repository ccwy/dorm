from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from utils.db import db
from models.contract.contract import Contract
from models.contract.contract_operation_record import ContractOperationRecord
from models.supply.supplier import Supplier
from models.supply.storage_location import StorageLocation
from models.department import Department
from models.system_config import SystemConfig
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
from utils.contract_attachment import ContractAttachmentManager
import logging
import re
from datetime import date, timedelta

# 定义蓝图
contract_bp = Blueprint(
    'contract',
    __name__,
    url_prefix='/contract',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/contract/static'
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
import blueprints.contract.contract_operations


# 合同列表页（含筛选+分页）
@contract_bp.route('/', methods=['GET'])
@login_required
@require_permission('contract.view')
def index():
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        status = request.args.get('status', '').strip()
        contract_type = request.args.get('contract_type', '').strip()
        is_renewal = request.args.get('is_renewal', '').strip()

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # 参数校验
        if page < 1:
            page = 1
        per_page = max(10, min(100, per_page))

        # 获取筛选选项
        statuses = ['草稿', '生效中', '即将到期', '已到期', '已终止', '已归档']

        # 从SystemConfig获取合同类型和分类配置
        contract_types_value = SystemConfig.get_config_value('CONTRACT_TYPES', '采购合同,服务合同,租赁合同,其他')
        contract_types = contract_types_value if isinstance(contract_types_value, list) else [t.strip() for t in contract_types_value.split(',') if t.strip()]

        contract_categories_value = SystemConfig.get_config_value('CONTRACT_CATEGORIES', '一般合同,重要合同,框架协议')
        contract_categories = contract_categories_value if isinstance(contract_categories_value, list) else [c.strip() for c in contract_categories_value.split(',') if c.strip()]

        # 构建查询
        query = Contract.query.order_by(Contract.id.desc())

        # keyword搜索：ilike匹配contract_number, contract_name, party_a_name(通过join Supplier), party_b_name(通过join Supplier)
        if keyword:
            search_filter = f'%{keyword}%'
            from sqlalchemy.orm import aliased
            SupplierA = aliased(Supplier)
            SupplierB = aliased(Supplier)
            query = query.outerjoin(SupplierA, Contract.party_a_id == SupplierA.id).outerjoin(SupplierB, Contract.party_b_id == SupplierB.id).filter(
                db.or_(
                    Contract.contract_number.ilike(search_filter),
                    Contract.contract_name.ilike(search_filter),
                    SupplierA.name.ilike(search_filter),
                    SupplierB.name.ilike(search_filter)
                )
            )

        # status筛选
        if status:
            query = query.filter(Contract.status == status)

        # contract_type筛选
        if contract_type:
            query = query.filter(Contract.contract_type == contract_type)

        # is_renewal筛选
        if is_renewal == '1':
            query = query.filter(Contract.previous_contract_id != None)
        elif is_renewal == '0':
            query = query.filter(Contract.previous_contract_id == None)

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        contracts = pagination.items
        total_count = pagination.total
        total_pages = pagination.pages
        current_page = pagination.page
        page_range = generate_page_range(current_page, total_pages)

        # 获取到期提醒数据
        expiring_count = len(Contract.get_expiring_contracts())
        expired_count = len(Contract.get_expired_contracts())

        # 更新到期状态
        Contract.update_expiry_status()

        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='records',
            action="访问合同管理页面",
            result="成功"
        )
        logging.info(f"加载合同管理页面，当前用户ID: {current_user.id}")

        return render_template(
            'contract_manage/contract_list.html',
            title="合同管理",
            # 合同数据
            contracts=contracts,
            total_count=total_count,
            # 分页参数
            current_page=current_page,
            per_page=per_page,
            total_pages=total_pages,
            page_range=page_range,
            # 筛选配置
            statuses=statuses,
            contract_types=contract_types,
            contract_categories=contract_categories,
            # 当前筛选条件（回显）
            current_status=status,
            current_contract_type=contract_type,
            current_is_renewal=is_renewal,
            keyword=keyword,
            # 到期提醒
            expiring_count=expiring_count,
            expired_count=expired_count
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='records',
            action=f"加载合同管理页面失败: {str(e)}",
            result="失败"
        )
        flash('加载合同数据失败，请联系管理员', 'danger')
        logging.error(f"加载合同管理页面失败: {str(e)}")
        return render_template(
            'contract_manage/contract_list.html',
            title="合同管理",
            contracts=[],
            total_count=0,
            current_page=1,
            per_page=20,
            total_pages=0,
            page_range=[],
            statuses=['草稿', '生效中', '即将到期', '已到期', '已终止', '已归档'],
            contract_types=['采购合同', '服务合同', '租赁合同', '其他'],
            contract_categories=['一般合同', '重要合同', '框架协议'],
            current_status='',
            current_contract_type='',
            current_is_renewal='',
            keyword='',
            expiring_count=0,
            expired_count=0
        )


# 新增合同页面
@contract_bp.route('/add', methods=['GET'])
@login_required
@require_permission('contract.create')
def add_page():
    try:
        # 获取供应商列表（用于甲乙方选择）
        suppliers = Supplier.query.filter_by(status='启用').order_by(Supplier.name).all()

        # 从SystemConfig获取合同类型和分类配置
        contract_types_value = SystemConfig.get_config_value('CONTRACT_TYPES', '采购合同,服务合同,租赁合同,其他')
        contract_types = contract_types_value if isinstance(contract_types_value, list) else [t.strip() for t in contract_types_value.split(',') if t.strip()]

        contract_categories_value = SystemConfig.get_config_value('CONTRACT_CATEGORIES', '一般合同,重要合同,框架协议')
        contract_categories = contract_categories_value if isinstance(contract_categories_value, list) else [c.strip() for c in contract_categories_value.split(',') if c.strip()]

        # 获取默认日期
        today = date.today().strftime('%Y-%m-%d')
        one_year_later = (date.today() + timedelta(days=365)).strftime('%Y-%m-%d')

        # 如果URL参数有previous_contract_id（续签），获取原合同信息
        previous_contract = None
        renewal_count = 0
        renewal_contract_name = ''  # 续签时预填充的合同名称
        previous_contract_id = request.args.get('previous_contract_id', type=int)
        if previous_contract_id:
            previous_contract = Contract.query.get(previous_contract_id)
            if previous_contract:
                renewal_count = len(previous_contract.renewal_chain) + 1
                # 去除原合同名中已有的"（第N次续签）"后缀，避免重叠
                base_name = re.sub(r'（第\d+次续签）$', '', previous_contract.contract_name)
                renewal_contract_name = f'{base_name}（第{renewal_count}次续签）'

        # 获取部门列表
        departments = Department.query.order_by(Department.name).all()

        # 获取合同存放位置列表
        storage_locations = StorageLocation.get_active_locations(usage_type='合同管理')

        return render_template(
            'contract_manage/contract_form.html',
            title="新增合同",
            contract=None,
            suppliers=suppliers,
            contract_types=contract_types,
            contract_categories=contract_categories,
            today=today,
            one_year_later=one_year_later,
            previous_contract=previous_contract,
            renewal_count=renewal_count,
            renewal_contract_name=renewal_contract_name,
            departments=departments,
            storage_locations=storage_locations
        )
    except Exception as e:
        logging.error(f"加载新增合同页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('contract.index'))


# 编辑合同页面
@contract_bp.route('/edit/<int:id>', methods=['GET'])
@login_required
@require_permission('contract.edit')
def edit_page(id):
    try:
        contract = Contract.query.get_or_404(id)

        # 获取供应商列表
        suppliers = Supplier.query.filter_by(status='启用').order_by(Supplier.name).all()

        # 从SystemConfig获取合同类型和分类配置
        contract_types_value = SystemConfig.get_config_value('CONTRACT_TYPES', '采购合同,服务合同,租赁合同,其他')
        contract_types = contract_types_value if isinstance(contract_types_value, list) else [t.strip() for t in contract_types_value.split(',') if t.strip()]

        contract_categories_value = SystemConfig.get_config_value('CONTRACT_CATEGORIES', '一般合同,重要合同,框架协议')
        contract_categories = contract_categories_value if isinstance(contract_categories_value, list) else [c.strip() for c in contract_categories_value.split(',') if c.strip()]

        # 获取部门列表
        departments = Department.query.order_by(Department.name).all()

        # 获取合同存放位置列表
        storage_locations = StorageLocation.get_active_locations(usage_type='合同管理')

        return render_template(
            'contract_manage/contract_form.html',
            title=f"编辑合同 - {contract.contract_name}",
            contract=contract,
            suppliers=suppliers,
            contract_types=contract_types,
            contract_categories=contract_categories,
            departments=departments,
            storage_locations=storage_locations
        )
    except Exception as e:
        logging.error(f"加载编辑合同页面失败: {str(e)}")
        flash('加载页面失败', 'danger')
        return redirect(url_for('contract.index'))


# 合同详情页（含操作记录时间线）
@contract_bp.route('/detail/<int:id>', methods=['GET'])
@login_required
@require_permission('contract.view')
def detail(id):
    try:
        contract = Contract.query.get_or_404(id)

        # 获取操作记录时间线（按时间倒序）
        operation_records = ContractOperationRecord.query.filter_by(
            contract_id=id
        ).order_by(ContractOperationRecord.operation_time.desc()).all()

        # 获取附件列表（纯文件系统模式）
        attachments = ContractAttachmentManager.get_media_files(id)

        # 获取续签关系链
        renewal_chain = contract.renewal_chain

        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='records',
            action=f"查看合同详情 [ID: {id}, {contract.contract_name}]",
            result="成功"
        )
        logging.info(f"查看合同详情，合同ID: {id}")

        return render_template(
            'contract_manage/contract_detail.html',
            title=f"合同详情 - {contract.contract_name}",
            contract=contract,
            operation_records=operation_records,
            attachments=attachments,
            renewal_chain=renewal_chain
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='records',
            action=f"查看合同详情失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash('查看合同详情失败，请重试', 'danger')
        logging.error(f"查看合同详情失败，合同ID: {id}, 错误: {str(e)}")
        return redirect(url_for('contract.index'))