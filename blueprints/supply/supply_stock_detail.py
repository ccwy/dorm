from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify, send_file
from utils.db import db
from models.supply.supply_stock_detail import SupplyStockDetail
from models.supply.supply_item import SupplyItem
from models.supply.storage_location import StorageLocation
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
import logging
import io
import traceback
from datetime import datetime
from utils.lazy_imports import pd

# 定义蓝图
supply_stock_detail_bp = Blueprint(
    'supply_stock_detail',
    __name__,
    url_prefix='/supply-stock-detail',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/supply-stock-detail/static'
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


# 库存明细列表页（支持按物品/位置/低库存筛选）
@supply_stock_detail_bp.route('/', methods=['GET'])
@login_required
@require_permission('supply.view')
def list_stock_details():
    """库存明细列表页，按物品分组汇总，支持筛选和展开查看位置明细"""
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        item_id = request.args.get('item_id', type=int)
        location_id = request.args.get('location_id', type=int)
        low_stock = request.args.get('low_stock', '').strip()
        item_keyword = request.args.get('item_keyword', '').strip()

        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)

        # 参数校验
        if page < 1:
            page = 1
        per_page = max(10, min(100, per_page))

        # 获取筛选选项
        items = SupplyItem.get_active_items()
        locations = StorageLocation.get_active_locations(usage_type='低值易耗品')

        # 获取是否显示无库存物品
        show_zero = request.args.get('show_zero', '').strip()

        # 按物品分组查询：先查物品列表，再查每个物品的位置明细
        # 构建物品查询
        item_query = SupplyItem.query.filter(SupplyItem.status == '启用')

        # 默认只显示有库存的物品
        if show_zero != '1':
            item_query = item_query.filter(SupplyItem.current_stock > 0)

        # 关键字筛选（兼容keyword和item_keyword参数）
        search_keyword = item_keyword or keyword
        if search_keyword:
            search_filter = f'%{search_keyword}%'
            item_query = item_query.filter(
                db.or_(
                    SupplyItem.name.ilike(search_filter),
                    SupplyItem.item_number.ilike(search_filter)
                )
            )

        # 指定物品筛选
        if item_id:
            item_query = item_query.filter(SupplyItem.id == item_id)

        # 按位置筛选时，只显示在该位置有库存的物品
        if location_id:
            item_query = item_query.join(
                SupplyStockDetail, SupplyItem.id == SupplyStockDetail.item_id
            ).filter(SupplyStockDetail.location_id == location_id)

        # 低库存筛选（受supply_low_stock_alert配置控制）
        if low_stock == '1':
            from models.system_config.system_config import SystemConfig
            if SystemConfig.get_config_value('supply_low_stock_alert', True):
                item_query = item_query.filter(SupplyItem.current_stock <= SupplyItem.min_stock)

        # 按物品编号排序
        item_query = item_query.order_by(SupplyItem.item_number)

        # 分页查询物品
        pagination = item_query.paginate(page=page, per_page=per_page, error_out=False)
        paginated_items = pagination.items
        total_count = pagination.total
        total_pages = pagination.pages
        current_page = pagination.page
        page_range = generate_page_range(current_page, total_pages)

        # 为每个物品获取位置明细
        item_stock_list = []
        for item in paginated_items:
            # 查询该物品在各位置的库存明细
            detail_query = SupplyStockDetail.query.options(
                db.joinedload(SupplyStockDetail.location)
            ).filter(SupplyStockDetail.item_id == item.id)

            # 如果按位置筛选，只显示该位置的明细
            if location_id:
                detail_query = detail_query.filter(SupplyStockDetail.location_id == location_id)

            location_details = detail_query.order_by(SupplyStockDetail.location_id).all()

            item_stock_list.append({
                'item': item,
                'total_quantity': item.current_stock or 0,
                'location_count': len(location_details),
                'location_details': location_details
            })

        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='supply_stock_detail',
            operation_type='records',
            action="访问库存明细页面",
            result="成功"
        )
        logging.info(f"加载库存明细页面，当前用户ID: {current_user.id}")

        return render_template(
            'supply_manage/stock_detail_list.html',
            title="库存明细",
            # 物品分组汇总数据
            item_stock_list=item_stock_list,
            total_count=total_count,
            # 分页参数
            current_page=current_page,
            per_page=per_page,
            total_pages=total_pages,
            page_range=page_range,
            # 筛选配置
            items=items,
            locations=locations,
            # 当前筛选条件（回显）
            current_item_id=item_id,
            current_location_id=location_id,
            low_stock=low_stock,
            item_keyword=search_keyword,
            show_zero=show_zero
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='supply_stock_detail',
            operation_type='records',
            action=f"加载库存明细页面失败: {str(e)}",
            result="失败"
        )
        flash('加载库存明细数据失败，请联系管理员', 'danger')
        logging.error(f"加载库存明细页面失败: {str(e)}")
        return render_template(
            'supply_manage/stock_detail_list.html',
            title="库存明细",
            item_stock_list=[],
            total_count=0,
            current_page=1,
            per_page=20,
            total_pages=0,
            page_range=[],
            items=[],
            locations=[],
            current_item_id=None,
            current_location_id=None,
            low_stock='',
            item_keyword='',
            show_zero=''
        )


# 按物品查看各位置库存
@supply_stock_detail_bp.route('/by-item/<int:item_id>', methods=['GET'])
@login_required
@require_permission('supply.view')
def by_item(item_id):
    """按物品查看各位置库存明细"""
    try:
        item = SupplyItem.query.get_or_404(item_id)

        # 获取该物品在各位置的库存
        stock_details = SupplyStockDetail.get_stock_by_item(item_id)

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        if page < 1:
            page = 1
        per_page = max(10, min(100, per_page))

        # 手动分页（get_stock_by_item返回列表）
        total_count = len(stock_details)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_details = stock_details[start:end]
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 0
        page_range = generate_page_range(page, total_pages)

        log_operation(
            user_id=current_user.id,
            module='supply_stock_detail',
            operation_type='records',
            action=f"按物品查看库存 [物品: {item.name}]",
            result="成功"
        )
        logging.info(f"按物品查看库存，物品ID: {item_id}")

        return render_template(
            'supply_manage/stock_detail_by_item.html',
            title=f"物品库存 - {item.name}",
            item=item,
            stock_details=paginated_details,
            total_count=total_count,
            current_page=page,
            per_page=per_page,
            total_pages=total_pages,
            page_range=page_range
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='supply_stock_detail',
            operation_type='records',
            action=f"按物品查看库存失败 [物品ID: {item_id}]: {str(e)}",
            result="失败"
        )
        flash('查看物品库存失败，请重试', 'danger')
        logging.error(f"按物品查看库存失败，物品ID: {item_id}, 错误: {str(e)}")
        return redirect(url_for('supply_stock_detail.list_stock_details'))


# 按位置查看各物品库存
@supply_stock_detail_bp.route('/by-location/<int:location_id>', methods=['GET'])
@login_required
@require_permission('supply.view')
def by_location(location_id):
    """按位置查看各物品库存明细"""
    try:
        location = StorageLocation.query.get_or_404(location_id)

        # 获取该位置下各物品的库存
        stock_details = SupplyStockDetail.get_stock_by_location(location_id)

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        if page < 1:
            page = 1
        per_page = max(10, min(100, per_page))

        # 手动分页
        total_count = len(stock_details)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_details = stock_details[start:end]
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 0
        page_range = generate_page_range(page, total_pages)

        log_operation(
            user_id=current_user.id,
            module='supply_stock_detail',
            operation_type='records',
            action=f"按位置查看库存 [位置: {location.name}]",
            result="成功"
        )
        logging.info(f"按位置查看库存，位置ID: {location_id}")

        return render_template(
            'supply_manage/stock_detail_by_location.html',
            title=f"位置库存 - {location.display_name if hasattr(location, 'display_name') else location.name}",
            location=location,
            stock_details=paginated_details,
            total_count=total_count,
            current_page=page,
            per_page=per_page,
            total_pages=total_pages,
            page_range=page_range
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='supply_stock_detail',
            operation_type='records',
            action=f"按位置查看库存失败 [位置ID: {location_id}]: {str(e)}",
            result="失败"
        )
        flash('查看位置库存失败，请重试', 'danger')
        logging.error(f"按位置查看库存失败，位置ID: {location_id}, 错误: {str(e)}")
        return redirect(url_for('supply_stock_detail.list_stock_details'))


# 低库存预警列表
@supply_stock_detail_bp.route('/low-stock', methods=['GET'])
@login_required
@require_permission('supply.view')
def low_stock():
    """低库存预警列表页"""
    try:
        # 检查低库存预警是否启用
        from models.system_config.system_config import SystemConfig
        low_stock_alert_enabled = SystemConfig.get_config_value('supply_low_stock_alert', True)
        
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        if page < 1:
            page = 1
        per_page = max(10, min(100, per_page))

        # 获取低库存物品
        low_stock_items = SupplyItem.get_low_stock_items()

        # 手动分页
        total_count = len(low_stock_items)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_items = low_stock_items[start:end]
        total_pages = (total_count + per_page - 1) // per_page if total_count > 0 else 0
        page_range = generate_page_range(page, total_pages)

        log_operation(
            user_id=current_user.id,
            module='supply_stock_detail',
            operation_type='records',
            action="访问低库存预警页面",
            result="成功"
        )
        logging.info(f"加载低库存预警页面，当前用户ID: {current_user.id}")

        return render_template(
            'supply_manage/stock_detail_low_stock.html',
            title="低库存预警",
            low_stock_items=paginated_items,
            total_count=total_count,
            current_page=page,
            per_page=per_page,
            total_pages=total_pages,
            page_range=page_range,
            low_stock_alert_enabled=low_stock_alert_enabled
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='supply_stock_detail',
            operation_type='records',
            action=f"加载低库存预警页面失败: {str(e)}",
            result="失败"
        )
        flash('加载低库存预警数据失败，请联系管理员', 'danger')
        logging.error(f"加载低库存预警页面失败: {str(e)}")
        return render_template(
            'supply_manage/stock_detail_low_stock.html',
            title="低库存预警",
            low_stock_items=[],
            total_count=0,
            current_page=1,
            per_page=20,
            total_pages=0,
            page_range=[]
        )


# 重新计算物品总库存
@supply_stock_detail_bp.route('/operations/recalculate/<int:item_id>', methods=['POST'])
@login_required
@require_permission('supply.edit')
def recalculate_stock(item_id):
    """重新计算指定物品的总库存"""
    try:
        item = SupplyItem.query.get_or_404(item_id)
        item = SupplyItem.recalculate_stock(item_id)

        log_operation(
            user_id=current_user.id,
            module='supply_stock_detail',
            operation_type='update',
            action=f"重新计算物品库存 [物品: {item.name}，总库存: {item.current_stock}]",
            result="成功"
        )
        flash(f'物品 "{item.name}" 总库存已重新计算为 {item.current_stock}', 'success')
        logging.info(f"重新计算物品库存，物品ID: {item_id}，总库存: {item.current_stock}")
    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='supply_stock_detail',
            operation_type='update',
            action=f"重新计算物品库存失败 [物品ID: {item_id}]: {str(e)}",
            result="失败"
        )
        flash(f'重新计算库存失败: {str(e)}', 'danger')
        logging.error(f"重新计算物品库存失败，物品ID: {item_id}, 错误: {str(e)}")

    # 返回来源页面
    return redirect(request.referrer or url_for('supply_stock_detail.list_stock_details'))


# ========== 导出库存明细数据 ==========
@supply_stock_detail_bp.route('/export', methods=['GET'])
@login_required
@require_permission('supply.export')
def export_stock_details():
    """导出库存明细数据为Excel"""
    try:
        logging.debug('开始执行库存明细数据导出')

        # 获取筛选参数（与列表页一致）
        keyword = request.args.get('keyword', '').strip()
        item_id = request.args.get('item_id', type=int)
        location_id = request.args.get('location_id', type=int)
        low_stock = request.args.get('low_stock', '').strip()
        item_keyword = request.args.get('item_keyword', '').strip()
        show_zero = request.args.get('show_zero', '').strip()

        # 构建物品查询（与列表页逻辑一致）
        item_query = SupplyItem.query.filter(SupplyItem.status == '启用')

        if show_zero != '1':
            item_query = item_query.filter(SupplyItem.current_stock > 0)

        search_keyword = item_keyword or keyword
        if search_keyword:
            search_filter = f'%{search_keyword}%'
            item_query = item_query.filter(
                db.or_(
                    SupplyItem.name.ilike(search_filter),
                    SupplyItem.item_number.ilike(search_filter)
                )
            )

        if item_id:
            item_query = item_query.filter(SupplyItem.id == item_id)

        if location_id:
            item_query = item_query.join(
                SupplyStockDetail, SupplyItem.id == SupplyStockDetail.item_id
            ).filter(SupplyStockDetail.location_id == location_id)

        if low_stock == '1':
            from models.system_config.system_config import SystemConfig
            if SystemConfig.get_config_value('supply_low_stock_alert', True):
                item_query = item_query.filter(SupplyItem.current_stock <= SupplyItem.min_stock)

        items = item_query.order_by(SupplyItem.item_number).all()

        if not items:
            flash('没有可导出的库存明细数据', 'info')
            return redirect(url_for('supply_stock_detail.list_stock_details'))

        # 准备导出数据
        data = []
        for item in items:
            # 获取该物品在各位置的库存明细
            detail_query = SupplyStockDetail.query.filter(SupplyStockDetail.item_id == item.id)
            if location_id:
                detail_query = detail_query.filter(SupplyStockDetail.location_id == location_id)
            location_details = detail_query.order_by(SupplyStockDetail.location_id).all()

            if location_details:
                for detail in location_details:
                    data.append({
                        '物品编号': item.item_number or '',
                        '物品名称': item.name or '',
                        '分类': item.category or '',
                        '规格型号': item.specification or '',
                        '单位': item.unit or '',
                        '单价': float(item.unit_price) if item.unit_price else 0,
                        '存放位置': detail.location.name if detail.location else '未知',
                        '位置库存数量': detail.quantity,
                        '总库存数量': item.current_stock or 0,
                        '最低库存': item.min_stock or 0,
                        '状态': item.status or '',
                    })
            else:
                data.append({
                    '物品编号': item.item_number or '',
                    '物品名称': item.name or '',
                    '分类': item.category or '',
                    '规格型号': item.specification or '',
                    '单位': item.unit or '',
                    '单价': float(item.unit_price) if item.unit_price else 0,
                    '存放位置': '无',
                    '位置库存数量': 0,
                    '总库存数量': item.current_stock or 0,
                    '最低库存': item.min_stock or 0,
                    '状态': item.status or '',
                })

        # 生成Excel
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='库存明细')

        output.seek(0)
        filename = f"库存明细导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        log_operation(
            user_id=current_user.id,
            module='supply_stock_detail',
            operation_type='batch_import_export',
            action=f"导出库存明细数据，共 {len(data)} 条记录",
            result="成功"
        )
        logging.info(f'用户{current_user.id}成功导出库存明细数据')

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'导出库存明细数据失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='supply_stock_detail',
            operation_type='batch_import_export',
            action=f"尝试导出库存明细数据失败: {str(e)}",
            result="失败"
        )
        flash('导出失败，请联系管理员', 'danger')
        return redirect(url_for('supply_stock_detail.list_stock_details'))