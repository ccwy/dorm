from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from utils.db import db
from models.supply.supply_stock_record import SupplyStockRecord
from models.supply.supply_item import SupplyItem
from models.supply.storage_location import StorageLocation
from models.department import Department
from models.user import User
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import admin_required
import logging

# 定义蓝图
supply_stock_record_bp = Blueprint(
    'supply_stock_record',
    __name__,
    url_prefix='/supply-stock-record',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/supply-stock-record/static'
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


# 进出库记录列表页（支持筛选+分页）
@supply_stock_record_bp.route('/', methods=['GET'])
@login_required
@admin_required
def list_records():
    try:
        # 获取筛选参数
        record_type = request.args.get('record_type', '').strip()
        item_id = request.args.get('item_id', type=int)
        location_id = request.args.get('location_id', type=int)
        department_id = request.args.get('department_id', type=int)
        recipient_user_id = request.args.get('recipient_user_id', type=int)
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()
        keyword = request.args.get('keyword', '').strip()

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # 参数校验
        if page < 1:
            page = 1
        per_page = max(10, min(100, per_page))

        # 获取筛选选项
        record_types = ['入库', '出库', '盘盈', '盘亏']
        items = SupplyItem.get_active_items()
        locations = StorageLocation.query.filter_by(status='启用').order_by(StorageLocation.id).all()
        departments = Department.query.order_by(Department.id).all()
        users = User.query.order_by(User.id).all()

        # 构建查询
        query = SupplyStockRecord.query.order_by(SupplyStockRecord.id.desc())

        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    SupplyStockRecord.item_name.ilike(search_filter),
                    SupplyStockRecord.source_number.ilike(search_filter),
                    SupplyStockRecord.remark.ilike(search_filter)
                )
            )
        if record_type:
            query = query.filter(SupplyStockRecord.record_type == record_type)
        if item_id:
            query = query.filter(SupplyStockRecord.item_id == item_id)
        if location_id:
            query = query.filter(SupplyStockRecord.location_id == location_id)
        if department_id:
            query = query.filter(SupplyStockRecord.department_id == department_id)
        if recipient_user_id:
            query = query.filter(SupplyStockRecord.recipient_user_id == recipient_user_id)
        if date_from:
            try:
                from datetime import datetime as dt
                date_from_val = dt.strptime(date_from, '%Y-%m-%d')
                query = query.filter(SupplyStockRecord.record_date >= date_from_val)
            except ValueError:
                pass
        if date_to:
            try:
                from datetime import datetime as dt
                date_to_val = dt.strptime(date_to, '%Y-%m-%d')
                query = query.filter(SupplyStockRecord.record_date <= date_to_val)
            except ValueError:
                pass

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        records = pagination.items
        total_count = pagination.total
        total_pages = pagination.pages
        current_page = pagination.page
        page_range = generate_page_range(current_page, total_pages)

        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='supply_stock_record',
            operation_type='records',
            action="访问进出库记录页面",
            result="成功"
        )
        logging.info(f"加载进出库记录页面，当前用户ID: {current_user.id}")

        return render_template(
            'supply_manage/record_list.html',
            title="进出库记录",
            records=records,
            total_count=total_count,
            current_page=current_page,
            per_page=per_page,
            total_pages=total_pages,
            page_range=page_range,
            record_types=record_types,
            items=items,
            locations=locations,
            departments=departments,
            users=users,
            current_record_type=record_type,
            current_item_id=item_id,
            current_location_id=location_id,
            current_department_id=department_id,
            current_recipient_user_id=recipient_user_id,
            keyword=keyword,
            date_from=date_from,
            date_to=date_to
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='supply_stock_record',
            operation_type='records',
            action=f"加载进出库记录页面失败: {str(e)}",
            result="失败"
        )
        flash('加载进出库记录数据失败，请联系管理员', 'danger')
        logging.error(f"加载进出库记录页面失败: {str(e)}")
        return render_template(
            'supply_manage/record_list.html',
            title="进出库记录",
            records=[],
            total_count=0,
            current_page=1,
            per_page=20,
            total_pages=0,
            page_range=[],
            record_types=['入库', '出库', '盘盈', '盘亏'],
            items=[],
            locations=[],
            departments=[],
            users=[],
            current_record_type='',
            current_item_id=None,
            current_location_id=None,
            current_department_id=None,
            current_recipient_user_id=None,
            keyword='',
            date_from='',
            date_to=''
        )


# 记录详情页面
@supply_stock_record_bp.route('/detail/<int:id>', methods=['GET'])
@login_required
@admin_required
def detail_record(id):
    try:
        record = SupplyStockRecord.query.get_or_404(id)

        log_operation(
            user_id=current_user.id,
            module='supply_stock_record',
            operation_type='records',
            action=f"查看进出库记录详情 [ID: {id}]",
            result="成功"
        )
        logging.info(f"查看进出库记录详情，记录ID: {id}")

        return render_template(
            'supply_manage/record_detail.html',
            title=f"进出库记录详情 - {record.record_type}",
            record=record
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='supply_stock_record',
            operation_type='records',
            action=f"查看进出库记录详情失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash('查看出入库记录详情失败，请重试', 'danger')
        logging.error(f"查看出入库记录详情失败，记录ID: {id}, 错误: {str(e)}")
        return redirect(url_for('supply_stock_record.list_records'))