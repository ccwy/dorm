from flask import Blueprint, request, jsonify
import logging
from utils.db import db
from flask_login import login_required, current_user
from utils.log import log_operation
import traceback
from utils.auth import require_permission
from models.supply.supply_item import SupplyItem

supply_item_api_bp = Blueprint('supply_item_api', __name__, url_prefix='/api/supply-items')


# ========== 获取物品列表JSON（分页+筛选） ==========
@supply_item_api_bp.route('/list', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_supply_item_list():
    """获取物品列表JSON，支持分页和多条件筛选"""
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        category = request.args.get('category', '').strip()
        status = request.args.get('status', '').strip()
        supplier_id = request.args.get('supplier_id', type=int)
        low_stock = request.args.get('low_stock', '').strip()

        # 分页参数
        page = max(request.args.get('page', 1, type=int), 1)
        per_page = min(max(request.args.get('per_page', 20, type=int), 1), 100)

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
            query = query.filter(SupplyItem.current_stock <= SupplyItem.min_stock)

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # 格式化物品数据
        item_list = []
        for item in pagination.items:
            item_data = {
                "id": item.id,
                "item_number": item.item_number or '',
                "name": item.name,
                "category": item.category or '',
                "specification": item.specification or '',
                "unit": item.unit or '',
                "supplier_id": item.supplier_id,
                "supplier_name": item.supplier_name,
                "unit_price": float(item.unit_price) if item.unit_price else 0,
                "reference_price": float(item.reference_price) if item.reference_price else None,
                "current_stock": item.current_stock,
                "min_stock": item.min_stock,
                "max_stock": item.max_stock,
                "is_low_stock": item.is_low_stock,
                "status": item.status or '启用',
                "remark": item.remark or '',
                "created_at": item.created_at.strftime('%Y-%m-%d %H:%M') if item.created_at else None,
                "updated_at": item.updated_at.strftime('%Y-%m-%d %H:%M') if item.updated_at else None
            }
            item_list.append(item_data)

        response = {
            "success": True,
            "data": item_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages
            }
        }

        log_operation(
            user_id=current_user.id,
            module='supply_item',
            operation_type='api_query',
            action=f"API查询物品列表，页码:{page}，每页:{per_page}",
            result="成功"
        )

        return jsonify(response)

    except Exception as e:
        logging.error(f"API获取物品列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取物品详情JSON ==========
@supply_item_api_bp.route('/<int:id>', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_supply_item_detail(id):
    """获取物品详情JSON"""
    try:
        item = SupplyItem.query.get_or_404(id)

        item_data = {
            "id": item.id,
            "item_number": item.item_number or '',
            "name": item.name,
            "category": item.category or '',
            "specification": item.specification or '',
            "unit": item.unit or '',
            "supplier_id": item.supplier_id,
            "supplier_name": item.supplier_name,
            "unit_price": float(item.unit_price) if item.unit_price else 0,
            "reference_price": float(item.reference_price) if item.reference_price else None,
            "current_stock": item.current_stock,
            "min_stock": item.min_stock,
            "max_stock": item.max_stock,
            "is_low_stock": item.is_low_stock,
            "status": item.status or '启用',
            "remark": item.remark or '',
            "operator_user_id": item.operator_user_id,
            "created_at": item.created_at.strftime('%Y-%m-%d %H:%M') if item.created_at else None,
            "updated_at": item.updated_at.strftime('%Y-%m-%d %H:%M') if item.updated_at else None
        }

        return jsonify({
            "success": True,
            "data": item_data
        })

    except Exception as e:
        logging.error(f"API获取物品详情失败 [ID: {id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取启用中的物品列表JSON（用于下拉选择） ==========
@supply_item_api_bp.route('/active', methods=['GET'])
@login_required
def get_active_supply_items():
    """获取启用中的物品列表，用于下拉选择"""
    try:
        items = SupplyItem.get_active_items()

        item_list = [{
            "id": item.id,
            "name": item.name,
            "item_number": item.item_number or '',
            "category": item.category or '',
            "unit": item.unit or '',
            "current_stock": item.current_stock,
            "unit_price": float(item.unit_price) if item.unit_price else 0
        } for item in items]

        return jsonify({
            "success": True,
            "data": item_list
        })
    except Exception as e:
        logging.error(f"API获取启用物品列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取低库存物品列表JSON ==========
@supply_item_api_bp.route('/low-stock', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_low_stock_items():
    """获取低于最低库存的物品列表"""
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
            "supplier_name": item.supplier_name
        } for item in items]

        return jsonify({
            "success": True,
            "data": item_list
        })
    except Exception as e:
        logging.error(f"API获取低库存物品列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取物品名称列表JSON ==========
@supply_item_api_bp.route('/names', methods=['GET'])
@login_required
def get_supply_item_names():
    """获取所有物品名称列表，供下拉选择使用"""
    try:
        names = SupplyItem.get_all_names()
        return jsonify({
            "success": True,
            "data": names
        })
    except Exception as e:
        logging.error(f"API获取物品名称列表失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500