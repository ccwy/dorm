from flask import Blueprint, request, jsonify
import logging
from utils.db import db
from flask_login import login_required, current_user
from utils.log import log_operation
import traceback
from utils.auth import require_permission
from models.supply.supply_stock_detail import SupplyStockDetail
from models.supply.supply_item import SupplyItem
from models.supply.storage_location import StorageLocation

supply_stock_detail_api_bp = Blueprint(
    'supply_stock_detail_api',
    __name__,
    url_prefix='/api/supply-stock-details'
)


# ========== 获取库存明细列表JSON（分页+筛选） ==========
@supply_stock_detail_api_bp.route('/list', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_stock_detail_list():
    """获取库存明细列表JSON，支持分页和多条件筛选"""
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        item_id = request.args.get('item_id', type=int)
        location_id = request.args.get('location_id', type=int)
        low_stock = request.args.get('low_stock', '').strip()

        # 分页参数
        page = max(request.args.get('page', 1, type=int), 1)
        per_page = min(max(request.args.get('per_page', 20, type=int), 1), 100)

        # 构建查询
        query = SupplyStockDetail.query.order_by(SupplyStockDetail.id.desc())

        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    SupplyStockDetail.item_name.ilike(search_filter),
                    SupplyStockDetail.location_name.ilike(search_filter)
                )
            )
        if item_id:
            query = query.filter(SupplyStockDetail.item_id == item_id)
        if location_id:
            query = query.filter(SupplyStockDetail.location_id == location_id)
        if low_stock == '1':
            query = query.join(
                SupplyItem, SupplyStockDetail.item_id == SupplyItem.id
            ).filter(SupplyStockDetail.quantity <= SupplyItem.min_stock)

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # 格式化库存明细数据
        detail_list = []
        for detail in pagination.items:
            detail_data = {
                "id": detail.id,
                "item_id": detail.item_id,
                "item_name": detail.item_name or '',
                "item_number": detail.item_number if hasattr(detail, 'item_number') and detail.item_number else '',
                "location_id": detail.location_id,
                "location_name": detail.location_name or '',
                "current_stock": detail.quantity,
                "min_stock": detail.min_stock if hasattr(detail, 'min_stock') else None,
                "updated_at": detail.updated_at.strftime('%Y-%m-%d %H:%M') if detail.updated_at else None
            }
            detail_list.append(detail_data)

        response = {
            "success": True,
            "data": detail_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages
            }
        }

        log_operation(
            user_id=current_user.id,
            module='supply_stock_detail',
            operation_type='api_query',
            action=f"API查询库存明细列表，页码:{page}，每页:{per_page}",
            result="成功"
        )

        return jsonify(response)

    except Exception as e:
        logging.error(f"API获取库存明细列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 按物品查询库存JSON ==========
@supply_stock_detail_api_bp.route('/by-item/<int:item_id>', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_stock_by_item(item_id):
    """按物品查询各位置库存JSON"""
    try:
        item = SupplyItem.query.get_or_404(item_id)
        stock_details = SupplyStockDetail.get_stock_by_item(item_id)

        detail_list = []
        for detail in stock_details:
            detail_data = {
                "id": detail.id,
                "item_id": detail.item_id,
                "item_name": detail.item_name or '',
                "location_id": detail.location_id,
                "location_name": detail.location_name or '',
                "current_stock": detail.quantity,
                "min_stock": detail.min_stock if hasattr(detail, 'min_stock') else None,
                "updated_at": detail.updated_at.strftime('%Y-%m-%d %H:%M') if detail.updated_at else None
            }
            detail_list.append(detail_data)

        return jsonify({
            "success": True,
            "data": {
                "item": {
                    "id": item.id,
                    "name": item.name,
                    "item_number": item.item_number or '',
                    "current_stock": item.current_stock,
                    "min_stock": item.min_stock,
                    "unit": item.unit or ''
                },
                "stock_details": detail_list
            }
        })

    except Exception as e:
        logging.error(f"API按物品查询库存失败 [物品ID: {item_id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 按位置查询库存JSON ==========
@supply_stock_detail_api_bp.route('/by-location/<int:location_id>', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_stock_by_location(location_id):
    """按位置查询各物品库存JSON"""
    try:
        location = StorageLocation.query.get_or_404(location_id)
        stock_details = SupplyStockDetail.get_stock_by_location(location_id)

        detail_list = []
        for detail in stock_details:
            detail_data = {
                "id": detail.id,
                "item_id": detail.item_id,
                "item_name": detail.item_name or '',
                "item_number": detail.item_number if hasattr(detail, 'item_number') and detail.item_number else '',
                "location_id": detail.location_id,
                "location_name": detail.location_name or '',
                "current_stock": detail.quantity,
                "min_stock": detail.min_stock if hasattr(detail, 'min_stock') else None,
                "updated_at": detail.updated_at.strftime('%Y-%m-%d %H:%M') if detail.updated_at else None
            }
            detail_list.append(detail_data)

        return jsonify({
            "success": True,
            "data": {
                "location": {
                    "id": location.id,
                    "name": location.name,
                    "code": location.code if hasattr(location, 'code') and location.code else '',
                    "display_name": location.display_name if hasattr(location, 'display_name') else location.name
                },
                "stock_details": detail_list
            }
        })

    except Exception as e:
        logging.error(f"API按位置查询库存失败 [位置ID: {location_id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取低库存预警JSON ==========
@supply_stock_detail_api_bp.route('/low-stock', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_low_stock():
    """获取低库存预警物品列表JSON"""
    try:
        items = SupplyItem.get_low_stock_items()

        item_list = [{
            "id": item.id,
            "name": item.name,
            "item_number": item.item_number or '',
            "category": item.category or '',
            "unit": item.unit or '',
            "current_stock": item.current_stock,
            "min_stock": item.min_stock,
            "supplier_name": item.supplier_name if hasattr(item, 'supplier_name') else ''
        } for item in items]

        return jsonify({
            "success": True,
            "data": item_list
        })

    except Exception as e:
        logging.error(f"API获取低库存预警失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取库存汇总JSON ==========
@supply_stock_detail_api_bp.route('/summary', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_stock_summary():
    """获取库存汇总统计JSON"""
    try:
        # 基础统计
        total_items = SupplyItem.query.filter_by(status='启用')
        total_items_count = total_items.count()

        # 低库存统计
        low_stock_items = SupplyItem.get_low_stock_items()
        low_stock_count = len(low_stock_items)

        # 总库存明细数
        stock_detail_query = SupplyStockDetail.query
        total_detail_count = stock_detail_query.count()

        # 按位置统计
        location_count = StorageLocation.query.filter_by(status='启用').count()

        summary = {
            "total_items": total_items_count,
            "low_stock_count": low_stock_count,
            "total_stock_details": total_detail_count,
            "active_locations": location_count
        }

        log_operation(
            user_id=current_user.id,
            module='supply_stock_detail',
            operation_type='api_query',
            action="API查询库存汇总",
            result="成功"
        )

        return jsonify({
            "success": True,
            "data": summary
        })

    except Exception as e:
        logging.error(f"API获取库存汇总失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500