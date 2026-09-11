from flask import Blueprint, request, jsonify
import logging
from utils.db import db
from flask_login import login_required, current_user
from utils.log import log_operation
import traceback
from utils.auth import require_permission
from models.supply.stock_in import StockIn
from models.supply.stock_in_detail import StockInDetail

stock_in_api_bp = Blueprint('stock_in_api', __name__, url_prefix='/api/stock-ins')


# ========== 获取入库单列表JSON（分页+筛选） ==========
@stock_in_api_bp.route('/', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_stock_in_list():
    """获取入库单列表JSON，支持分页和多条件筛选"""
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        stock_in_type = request.args.get('stock_in_type', '').strip()
        status = request.args.get('status', '').strip()
        supplier_id = request.args.get('supplier_id', '').strip()
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()

        # 分页参数
        page = max(request.args.get('page', 1, type=int), 1)
        per_page = min(max(request.args.get('per_page', 20, type=int), 1), 100)

        # 构建查询
        query = StockIn.query.order_by(StockIn.id.desc())

        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    StockIn.stock_in_number.ilike(search_filter),
                    StockIn.remark.ilike(search_filter)
                )
            )
        if stock_in_type:
            query = query.filter(StockIn.stock_in_type == stock_in_type)
        if status:
            query = query.filter(StockIn.status == status)
        if supplier_id:
            query = query.filter(StockIn.supplier_id == supplier_id)
        if date_from:
            try:
                from datetime import datetime as dt
                date_from_val = dt.strptime(date_from, '%Y-%m-%d').date()
                query = query.filter(StockIn.stock_in_date >= date_from_val)
            except ValueError:
                pass
        if date_to:
            try:
                from datetime import datetime as dt
                date_to_val = dt.strptime(date_to, '%Y-%m-%d').date()
                query = query.filter(StockIn.stock_in_date <= date_to_val)
            except ValueError:
                pass

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # 格式化入库单数据
        stock_in_list = []
        for si in pagination.items:
            stock_in_data = {
                "id": si.id,
                "stock_in_number": si.stock_in_number,
                "stock_in_type": si.stock_in_type,
                "stock_in_date": si.stock_in_date.strftime('%Y-%m-%d') if si.stock_in_date else None,
                "supplier_id": si.supplier_id,
                "supplier_name": si.supplier_name,
                "handler_user_id": si.handler_user_id,
                "handler_name": si.handler_name,
                "status": si.status,
                "total_amount": float(si.total_amount) if si.total_amount else 0,
                "remark": si.remark or '',
                "detail_count": si.detail_count,
                "created_at": si.created_at.strftime('%Y-%m-%d %H:%M') if si.created_at else None,
                "updated_at": si.updated_at.strftime('%Y-%m-%d %H:%M') if si.updated_at else None
            }
            stock_in_list.append(stock_in_data)

        response = {
            "success": True,
            "data": stock_in_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages
            }
        }

        log_operation(
            user_id=current_user.id,
            module='stock_in',
            operation_type='api_query',
            action=f"API查询入库单列表，页码:{page}，每页:{per_page}",
            result="成功"
        )

        return jsonify(response)

    except Exception as e:
        logging.error(f"API获取入库单列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取入库单详情JSON ==========
@stock_in_api_bp.route('/<int:id>', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_stock_in_detail(id):
    """获取入库单详情JSON（含明细列表）"""
    try:
        stock_in = StockIn.query.get_or_404(id)

        # 获取明细列表
        details = StockInDetail.query.filter_by(stock_in_id=id).order_by(StockInDetail.id).all()
        detail_list = []
        for d in details:
            detail_data = {
                "id": d.id,
                "item_id": d.item_id,
                "item_name": d.item_name or d.display_item_name,
                "specification": d.specification or '',
                "location_id": d.location_id,
                "location_name": d.location_name or d.display_location_name,
                "unit": d.unit or '',
                "quantity": d.quantity,
                "unit_price": float(d.unit_price) if d.unit_price else 0,
                "total_price": float(d.total_price) if d.total_price else 0,
                "remark": d.remark or ''
            }
            detail_list.append(detail_data)

        stock_in_data = {
            "id": stock_in.id,
            "stock_in_number": stock_in.stock_in_number,
            "stock_in_type": stock_in.stock_in_type,
            "stock_in_date": stock_in.stock_in_date.strftime('%Y-%m-%d') if stock_in.stock_in_date else None,
            "supplier_id": stock_in.supplier_id,
            "supplier_name": stock_in.supplier_name,
            "handler_user_id": stock_in.handler_user_id,
            "handler_name": stock_in.handler_name,
            "status": stock_in.status,
            "total_amount": float(stock_in.total_amount) if stock_in.total_amount else 0,
            "remark": stock_in.remark or '',
            "review_user_id": stock_in.review_user_id,
            "review_time": stock_in.review_time.strftime('%Y-%m-%d %H:%M') if stock_in.review_time else None,
            "review_remark": stock_in.review_remark or '',
            "details": detail_list,
            "created_at": stock_in.created_at.strftime('%Y-%m-%d %H:%M') if stock_in.created_at else None,
            "updated_at": stock_in.updated_at.strftime('%Y-%m-%d %H:%M') if stock_in.updated_at else None
        }

        return jsonify({
            "success": True,
            "data": stock_in_data
        })

    except Exception as e:
        logging.error(f"API获取入库单详情失败 [ID: {id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取待审核入库单列表JSON ==========
@stock_in_api_bp.route('/pending', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_pending_stock_ins():
    """获取待审核入库单列表JSON"""
    try:
        query = StockIn.query.filter_by(status='待审核').order_by(StockIn.id.desc())

        stock_ins = query.all()

        stock_in_list = [{
            "id": si.id,
            "stock_in_number": si.stock_in_number,
            "stock_in_type": si.stock_in_type,
            "stock_in_date": si.stock_in_date.strftime('%Y-%m-%d') if si.stock_in_date else None,
            "supplier_name": si.supplier_name,
            "handler_name": si.handler_name,
            "total_amount": float(si.total_amount) if si.total_amount else 0,
            "detail_count": si.detail_count,
            "created_at": si.created_at.strftime('%Y-%m-%d %H:%M') if si.created_at else None
        } for si in stock_ins]

        return jsonify({
            "success": True,
            "data": stock_in_list
        })

    except Exception as e:
        logging.error(f"API获取待审核入库单列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取入库统计JSON ==========
@stock_in_api_bp.route('/statistics', methods=['GET'])
@login_required
@require_permission('supply.view')
def get_stock_in_statistics():
    """获取入库统计JSON（按类型/月份统计数量和金额）"""
    try:
        from sqlalchemy import func, extract
        from datetime import datetime as dt

        year = request.args.get('year', dt.now().year, type=int)

        # 基础查询：已审核的入库单
        base_query = StockIn.query.filter_by(status='已审核')

        base_query = base_query.filter(
            extract('year', StockIn.stock_in_date) == year
        )

        # 按类型统计
        type_stats = db.session.query(
            StockIn.stock_in_type,
            func.count(StockIn.id).label('count'),
            func.coalesce(func.sum(StockIn.total_amount), 0).label('total_amount')
        ).filter(
            StockIn.status == '已审核',
            extract('year', StockIn.stock_in_date) == year
        )

        type_stats = type_stats.group_by(StockIn.stock_in_type).all()

        type_statistics = [{
            "stock_in_type": ts.stock_in_type,
            "count": ts.count,
            "total_amount": float(ts.total_amount)
        } for ts in type_stats]

        # 按月份统计
        month_stats = db.session.query(
            extract('month', StockIn.stock_in_date).label('month'),
            func.count(StockIn.id).label('count'),
            func.coalesce(func.sum(StockIn.total_amount), 0).label('total_amount')
        ).filter(
            StockIn.status == '已审核',
            extract('year', StockIn.stock_in_date) == year
        )

        month_stats = month_stats.group_by(
            extract('month', StockIn.stock_in_date)
        ).order_by(
            extract('month', StockIn.stock_in_date)
        ).all()

        month_statistics = [{
            "month": int(ms.month),
            "count": ms.count,
            "total_amount": float(ms.total_amount)
        } for ms in month_stats]

        return jsonify({
            "success": True,
            "data": {
                "year": year,
                "by_type": type_statistics,
                "by_month": month_statistics
            }
        })

    except Exception as e:
        logging.error(f"API获取入库统计失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500