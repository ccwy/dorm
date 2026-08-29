from flask import Blueprint, request, jsonify
import logging
from utils.db import db
from flask_login import login_required, current_user
from utils.log import log_operation
import traceback
from utils.auth import admin_required
from models.supply.supply_stock_record import SupplyStockRecord

supply_stock_record_api_bp = Blueprint('supply_stock_record_api', __name__, url_prefix='/api/supply-stock-records')


# ========== 获取进出库记录列表JSON（分页+筛选） ==========
@supply_stock_record_api_bp.route('/', methods=['GET'])
@login_required
@admin_required
def get_supply_stock_record_list():
    """获取进出库记录列表JSON，支持分页和多条件筛选"""
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
        page = max(request.args.get('page', 1, type=int), 1)
        per_page = min(max(request.args.get('per_page', 20, type=int), 1), 100)

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

        # 格式化记录数据
        record_list = []
        for record in pagination.items:
            record_data = {
                "id": record.id,
                "record_type": record.record_type,
                "record_date": record.record_date.strftime('%Y-%m-%d %H:%M') if record.record_date else None,
                "item_id": record.item_id,
                "item_name": record.item_name or '',
                "location_id": record.location_id,
                "location_name": record.location_name or '',
                "quantity": record.quantity,
                "unit_price": float(record.unit_price) if record.unit_price else 0,
                "total_price": float(record.total_price) if record.total_price else 0,
                "source_number": record.source_number or '',
                "source_type": record.source_type or '',
                "recipient_user_id": record.recipient_user_id,
                "recipient_name": record.recipient_name,
                "department_id": record.department_id,
                "department_name": record.department_name,
                "remark": record.remark or '',
                "created_at": record.created_at.strftime('%Y-%m-%d %H:%M') if record.created_at else None
            }
            record_list.append(record_data)

        response = {
            "success": True,
            "data": record_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages
            }
        }

        log_operation(
            user_id=current_user.id,
            module='supply_stock_record',
            operation_type='api_query',
            action=f"API查询进出库记录列表，页码:{page}，每页:{per_page}",
            result="成功"
        )

        return jsonify(response)

    except Exception as e:
        logging.error(f"API获取进出库记录列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取进出库记录详情JSON ==========
@supply_stock_record_api_bp.route('/<int:id>', methods=['GET'])
@login_required
@admin_required
def get_supply_stock_record_detail(id):
    """获取进出库记录详情JSON"""
    try:
        record = SupplyStockRecord.query.get_or_404(id)

        record_data = {
            "id": record.id,
            "record_type": record.record_type,
            "record_date": record.record_date.strftime('%Y-%m-%d %H:%M') if record.record_date else None,
            "item_id": record.item_id,
            "item_name": record.item_name or '',
            "location_id": record.location_id,
            "location_name": record.location_name or '',
            "quantity": record.quantity,
            "unit_price": float(record.unit_price) if record.unit_price else 0,
            "total_price": float(record.total_price) if record.total_price else 0,
            "source_number": record.source_number or '',
            "source_type": record.source_type or '',
            "recipient_user_id": record.recipient_user_id,
            "recipient_name": record.recipient_name,
            "department_id": record.department_id,
            "department_name": record.department_name,
            "operator_user_id": record.operator_user_id,
            "remark": record.remark or '',
            "created_at": record.created_at.strftime('%Y-%m-%d %H:%M') if record.created_at else None
        }

        return jsonify({
            "success": True,
            "data": record_data
        })

    except Exception as e:
        logging.error(f"API获取进出库记录详情失败 [ID: {id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 按物品查询记录JSON ==========
@supply_stock_record_api_bp.route('/by-item/<int:item_id>', methods=['GET'])
@login_required
@admin_required
def get_records_by_item(item_id):
    """按物品查询进出库记录JSON"""
    try:
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()
        record_type = request.args.get('record_type', '').strip()

        start_date_val = None
        end_date_val = None
        if start_date:
            try:
                from datetime import datetime as dt
                start_date_val = dt.strptime(start_date, '%Y-%m-%d')
            except ValueError:
                pass
        if end_date:
            try:
                from datetime import datetime as dt
                end_date_val = dt.strptime(end_date, '%Y-%m-%d')
            except ValueError:
                pass

        records = SupplyStockRecord.get_by_item(
            item_id=item_id,
            start_date=start_date_val,
            end_date=end_date_val,
            record_type=record_type if record_type else None
        )

        record_list = [{
            "id": r.id,
            "record_type": r.record_type,
            "record_date": r.record_date.strftime('%Y-%m-%d %H:%M') if r.record_date else None,
            "item_name": r.item_name or '',
            "location_name": r.location_name or '',
            "quantity": r.quantity,
            "unit_price": float(r.unit_price) if r.unit_price else 0,
            "total_price": float(r.total_price) if r.total_price else 0,
            "source_number": r.source_number or '',
            "source_type": r.source_type or '',
            "remark": r.remark or ''
        } for r in records]

        return jsonify({
            "success": True,
            "data": record_list
        })

    except Exception as e:
        logging.error(f"API按物品查询进出库记录失败 [物品ID: {item_id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 按位置查询记录JSON ==========
@supply_stock_record_api_bp.route('/by-location/<int:location_id>', methods=['GET'])
@login_required
@admin_required
def get_records_by_location(location_id):
    """按位置查询进出库记录JSON"""
    try:
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()

        start_date_val = None
        end_date_val = None
        if start_date:
            try:
                from datetime import datetime as dt
                start_date_val = dt.strptime(start_date, '%Y-%m-%d')
            except ValueError:
                pass
        if end_date:
            try:
                from datetime import datetime as dt
                end_date_val = dt.strptime(end_date, '%Y-%m-%d')
            except ValueError:
                pass

        records = SupplyStockRecord.get_by_location(
            location_id=location_id,
            start_date=start_date_val,
            end_date=end_date_val
        )

        record_list = [{
            "id": r.id,
            "record_type": r.record_type,
            "record_date": r.record_date.strftime('%Y-%m-%d %H:%M') if r.record_date else None,
            "item_name": r.item_name or '',
            "location_name": r.location_name or '',
            "quantity": r.quantity,
            "unit_price": float(r.unit_price) if r.unit_price else 0,
            "total_price": float(r.total_price) if r.total_price else 0,
            "source_number": r.source_number or '',
            "source_type": r.source_type or '',
            "remark": r.remark or ''
        } for r in records]

        return jsonify({
            "success": True,
            "data": record_list
        })

    except Exception as e:
        logging.error(f"API按位置查询进出库记录失败 [位置ID: {location_id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 按部门查询记录JSON ==========
@supply_stock_record_api_bp.route('/by-department/<int:department_id>', methods=['GET'])
@login_required
@admin_required
def get_records_by_department(department_id):
    """按部门查询领用记录JSON"""
    try:
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()

        start_date_val = None
        end_date_val = None
        if start_date:
            try:
                from datetime import datetime as dt
                start_date_val = dt.strptime(start_date, '%Y-%m-%d')
            except ValueError:
                pass
        if end_date:
            try:
                from datetime import datetime as dt
                end_date_val = dt.strptime(end_date, '%Y-%m-%d')
            except ValueError:
                pass

        records = SupplyStockRecord.get_by_department(
            department_id=department_id,
            start_date=start_date_val,
            end_date=end_date_val
        )

        record_list = [{
            "id": r.id,
            "record_type": r.record_type,
            "record_date": r.record_date.strftime('%Y-%m-%d %H:%M') if r.record_date else None,
            "item_name": r.item_name or '',
            "location_name": r.location_name or '',
            "quantity": r.quantity,
            "unit_price": float(r.unit_price) if r.unit_price else 0,
            "total_price": float(r.total_price) if r.total_price else 0,
            "source_number": r.source_number or '',
            "source_type": r.source_type or '',
            "recipient_name": r.recipient_name,
            "department_name": r.department_name,
            "remark": r.remark or ''
        } for r in records]

        return jsonify({
            "success": True,
            "data": record_list
        })

    except Exception as e:
        logging.error(f"API按部门查询领用记录失败 [部门ID: {department_id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取进出库统计JSON ==========
@supply_stock_record_api_bp.route('/statistics', methods=['GET'])
@login_required
@admin_required
def get_supply_stock_record_statistics():
    """获取进出库统计JSON（调用 SupplyStockRecord.get_statistics()）"""
    try:
        start_date = request.args.get('start_date', '').strip()
        end_date = request.args.get('end_date', '').strip()

        start_date_val = None
        end_date_val = None
        if start_date:
            try:
                from datetime import datetime as dt
                start_date_val = dt.strptime(start_date, '%Y-%m-%d')
            except ValueError:
                pass
        if end_date:
            try:
                from datetime import datetime as dt
                end_date_val = dt.strptime(end_date, '%Y-%m-%d')
            except ValueError:
                pass

        stats = SupplyStockRecord.get_statistics(
            start_date=start_date_val,
            end_date=end_date_val
        )

        statistics = [{
            "record_type": s.record_type,
            "count": s.count,
            "total_quantity": int(s.total_quantity) if s.total_quantity else 0,
            "total_amount": float(s.total_amount) if s.total_amount else 0
        } for s in stats]

        return jsonify({
            "success": True,
            "data": statistics
        })

    except Exception as e:
        logging.error(f"API获取进出库统计失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 导出进出库记录为Excel ==========
@supply_stock_record_api_bp.route('/export', methods=['GET'])
@login_required
@admin_required
def export():
    """导出进出库记录数据为Excel"""
    # 参照其他模块的 import_export 实现导出逻辑
    pass