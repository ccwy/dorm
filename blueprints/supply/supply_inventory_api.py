from flask import Blueprint, request, jsonify
import logging
from utils.db import db
from flask_login import login_required, current_user
from utils.log import log_operation
import traceback
from utils.auth import require_permission
from models.supply.supply_inventory import SupplyInventory
from models.supply.supply_inventory_detail import SupplyInventoryDetail

supply_inventory_api_bp = Blueprint('supply_inventory_api', __name__, url_prefix='/api/supply-inventories')


# ========== 获取盘点单列表JSON（分页+筛选） ==========
@supply_inventory_api_bp.route('/', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_supply_inventory_list():
    """获取盘点单列表JSON，支持分页和多条件筛选"""
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        status = request.args.get('status', '').strip()
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()

        # 分页参数
        page = max(request.args.get('page', 1, type=int), 1)
        per_page = min(max(request.args.get('per_page', 20, type=int), 1), 100)

        # 构建查询
        query = SupplyInventory.query.order_by(SupplyInventory.id.desc())

        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    SupplyInventory.inventory_number.ilike(search_filter),
                    SupplyInventory.title.ilike(search_filter),
                    SupplyInventory.remark.ilike(search_filter)
                )
            )
        if status:
            query = query.filter(SupplyInventory.status == status)
        if date_from:
            try:
                from datetime import datetime as dt
                date_from_val = dt.strptime(date_from, '%Y-%m-%d').date()
                query = query.filter(SupplyInventory.inventory_date >= date_from_val)
            except ValueError:
                pass
        if date_to:
            try:
                from datetime import datetime as dt
                date_to_val = dt.strptime(date_to, '%Y-%m-%d').date()
                query = query.filter(SupplyInventory.inventory_date <= date_to_val)
            except ValueError:
                pass

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # 格式化盘点单数据
        inventory_list = []
        for inv in pagination.items:
            inv_data = {
                "id": inv.id,
                "inventory_number": inv.inventory_number,
                "title": inv.title or '',
                "inventory_date": inv.inventory_date.strftime('%Y-%m-%d') if inv.inventory_date else None,
                "status": inv.status,
                "total_count": inv.total_count or 0,
                "checked_count": inv.checked_count or 0,
                "normal_count": inv.normal_count or 0,
                "abnormal_count": inv.abnormal_count or 0,
                "remark": inv.remark or '',
                "created_at": inv.created_at.strftime('%Y-%m-%d %H:%M') if inv.created_at else None,
                "updated_at": inv.updated_at.strftime('%Y-%m-%d %H:%M') if inv.updated_at else None
            }
            inventory_list.append(inv_data)

        response = {
            "success": True,
            "data": inventory_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages
            }
        }

        log_operation(
            user_id=current_user.id,
            module='supply_inventory',
            operation_type='api_query',
            action=f"API查询盘点单列表，页码:{page}，每页:{per_page}",
            result="成功"
        )

        return jsonify(response)

    except Exception as e:
        logging.error(f"API获取盘点单列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取盘点单详情JSON ==========
@supply_inventory_api_bp.route('/<int:id>', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_supply_inventory_detail(id):
    """获取盘点单详情JSON（含明细列表）"""
    try:
        inventory = SupplyInventory.query.get_or_404(id)

        # 获取明细列表
        details = SupplyInventoryDetail.query.filter_by(inventory_id=id).order_by(SupplyInventoryDetail.id).all()
        detail_list = []
        for d in details:
            detail_data = {
                "id": d.id,
                "item_id": d.item_id,
                "item_name": d.item_name or '',
                "specification": d.specification or '',
                "unit": d.unit or '',
                "location_id": d.location_id,
                "location_name": d.location_name or '',
                "system_quantity": d.system_quantity,
                "actual_quantity": d.actual_quantity,
                "difference_quantity": d.difference_quantity,
                "unit_price": float(d.unit_price) if d.unit_price else 0,
                "inventory_result": d.inventory_result or '未盘点',
                "inventory_remark": d.inventory_remark or '',
                "checked_by": d.checked_by or '',
                "checked_at": d.checked_at.strftime('%Y-%m-%d %H:%M') if d.checked_at else None
            }
            detail_list.append(detail_data)

        inventory_data = {
            "id": inventory.id,
            "inventory_number": inventory.inventory_number,
            "title": inventory.title or '',
            "inventory_date": inventory.inventory_date.strftime('%Y-%m-%d') if inventory.inventory_date else None,
            "status": inventory.status,
            "total_count": inventory.total_count or 0,
            "checked_count": inventory.checked_count or 0,
            "normal_count": inventory.normal_count or 0,
            "abnormal_count": inventory.abnormal_count or 0,
            "remark": inventory.remark or '',
            "details": detail_list,
            "created_at": inventory.created_at.strftime('%Y-%m-%d %H:%M') if inventory.created_at else None,
            "updated_at": inventory.updated_at.strftime('%Y-%m-%d %H:%M') if inventory.updated_at else None
        }

        return jsonify({
            "success": True,
            "data": inventory_data
        })

    except Exception as e:
        logging.error(f"API获取盘点单详情失败 [ID: {id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取进行中盘点单列表JSON ==========
@supply_inventory_api_bp.route('/active', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_active_supply_inventories():
    """获取进行中的盘点单列表JSON"""
    try:
        query = SupplyInventory.query.filter_by(status='进行中').order_by(SupplyInventory.id.desc())

        inventories = query.all()

        inventory_list = [{
            "id": inv.id,
            "inventory_number": inv.inventory_number,
            "title": inv.title or '',
            "inventory_date": inv.inventory_date.strftime('%Y-%m-%d') if inv.inventory_date else None,
            "total_count": inv.total_count or 0,
            "checked_count": inv.checked_count or 0,
            "normal_count": inv.normal_count or 0,
            "abnormal_count": inv.abnormal_count or 0,
            "created_at": inv.created_at.strftime('%Y-%m-%d %H:%M') if inv.created_at else None
        } for inv in inventories]

        return jsonify({
            "success": True,
            "data": inventory_list
        })

    except Exception as e:
        logging.error(f"API获取进行中盘点单列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取盘点统计JSON ==========
@supply_inventory_api_bp.route('/statistics', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_supply_inventory_statistics():
    """获取盘点统计JSON（按状态统计盘点次数、异常率等）"""
    try:
        from sqlalchemy import func, extract
        from datetime import datetime as dt

        year = request.args.get('year', dt.now().year, type=int)

        # 基础过滤条件 - 已完成的盘点
        base_filter = [SupplyInventory.status == '已完成']

        # 按月份统计盘点次数
        month_stats = db.session.query(
            extract('month', SupplyInventory.inventory_date).label('month'),
            func.count(SupplyInventory.id).label('count')
        ).filter(
            *base_filter,
            extract('year', SupplyInventory.inventory_date) == year
        ).group_by(
            extract('month', SupplyInventory.inventory_date)
        ).order_by(
            extract('month', SupplyInventory.inventory_date)
        ).all()

        month_statistics = [{
            "month": int(ms.month),
            "count": ms.count
        } for ms in month_stats]

        # 异常率统计：异常明细数 / 已盘点明细数
        total_checked_count = db.session.query(
            func.sum(SupplyInventory.checked_count)
        ).filter(
            *base_filter
        ).scalar() or 0

        total_abnormal_count = db.session.query(
            func.sum(SupplyInventory.abnormal_count)
        ).filter(
            *base_filter
        ).scalar() or 0

        abnormal_rate = round(total_abnormal_count / total_checked_count * 100, 2) if total_checked_count > 0 else 0

        # 按状态统计
        status_stats = db.session.query(
            SupplyInventory.status,
            func.count(SupplyInventory.id).label('count')
        ).group_by(
            SupplyInventory.status
        ).all()

        status_statistics = [{
            "status": ss.status,
            "count": ss.count
        } for ss in status_stats]

        return jsonify({
            "success": True,
            "data": {
                "year": year,
                "by_month": month_statistics,
                "by_status": status_statistics,
                "abnormal_statistics": {
                    "total_checked": total_checked_count,
                    "total_abnormal": total_abnormal_count,
                    "abnormal_rate": abnormal_rate
                }
            }
        })

    except Exception as e:
        logging.error(f"API获取盘点统计失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500