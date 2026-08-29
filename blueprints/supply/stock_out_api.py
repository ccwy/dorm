from flask import Blueprint, request, jsonify
import logging
from utils.db import db
from flask_login import login_required, current_user
from utils.log import log_operation
import traceback
from utils.auth import admin_required
from models.supply.stock_out import StockOut
from models.supply.stock_out_detail import StockOutDetail

stock_out_api_bp = Blueprint('stock_out_api', __name__, url_prefix='/api/stock-outs')


# ========== 获取出库单列表JSON（分页+筛选） ==========
@stock_out_api_bp.route('/', methods=['GET'])
@login_required
@admin_required
def get_stock_out_list():
    """获取出库单列表JSON，支持分页和多条件筛选"""
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        stock_out_type = request.args.get('stock_out_type', '').strip()
        status = request.args.get('status', '').strip()
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()

        # 分页参数
        page = max(request.args.get('page', 1, type=int), 1)
        per_page = min(max(request.args.get('per_page', 20, type=int), 1), 100)

        # 构建查询
        query = StockOut.query.order_by(StockOut.id.desc())

        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    StockOut.stock_out_number.ilike(search_filter),
                    StockOut.remark.ilike(search_filter)
                )
            )
        if stock_out_type:
            query = query.filter(StockOut.stock_out_type == stock_out_type)
        if status:
            query = query.filter(StockOut.status == status)
        if date_from:
            try:
                from datetime import datetime as dt
                date_from_val = dt.strptime(date_from, '%Y-%m-%d').date()
                query = query.filter(StockOut.stock_out_date >= date_from_val)
            except ValueError:
                pass
        if date_to:
            try:
                from datetime import datetime as dt
                date_to_val = dt.strptime(date_to, '%Y-%m-%d').date()
                query = query.filter(StockOut.stock_out_date <= date_to_val)
            except ValueError:
                pass

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # 格式化出库单数据
        stock_out_list = []
        for so in pagination.items:
            stock_out_data = {
                "id": so.id,
                "stock_out_number": so.stock_out_number,
                "stock_out_type": so.stock_out_type,
                "stock_out_date": so.stock_out_date.strftime('%Y-%m-%d') if so.stock_out_date else None,
                "recipient_user_id": so.recipient_user_id,
                "recipient_name": so.recipient_name,
                "department_id": so.department_id,
                "department_name": so.department_name,
                "handler_user_id": so.handler_user_id,
                "handler_name": so.handler_name,
                "status": so.status,
                "total_amount": float(so.total_amount) if so.total_amount else 0,
                "remark": so.remark or '',
                "detail_count": so.detail_count,
                "created_at": so.created_at.strftime('%Y-%m-%d %H:%M') if so.created_at else None,
                "updated_at": so.updated_at.strftime('%Y-%m-%d %H:%M') if so.updated_at else None
            }
            stock_out_list.append(stock_out_data)

        response = {
            "success": True,
            "data": stock_out_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages
            }
        }

        log_operation(
            user_id=current_user.id,
            module='stock_out',
            operation_type='api_query',
            action=f"API查询出库单列表，页码:{page}，每页:{per_page}",
            result="成功"
        )

        return jsonify(response)

    except Exception as e:
        logging.error(f"API获取出库单列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取出库单详情JSON ==========
@stock_out_api_bp.route('/<int:id>', methods=['GET'])
@login_required
@admin_required
def get_stock_out_detail(id):
    """获取出库单详情JSON（含明细列表）"""
    try:
        stock_out = StockOut.query.get_or_404(id)

        # 获取明细列表
        details = StockOutDetail.query.filter_by(stock_out_id=id).order_by(StockOutDetail.id).all()
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
                "quantity": d.quantity,
                "unit_price": float(d.unit_price) if d.unit_price else 0,
                "total_price": float(d.total_price) if d.total_price else 0,
                "remark": d.remark or ''
            }
            detail_list.append(detail_data)

        stock_out_data = {
            "id": stock_out.id,
            "stock_out_number": stock_out.stock_out_number,
            "stock_out_type": stock_out.stock_out_type,
            "stock_out_date": stock_out.stock_out_date.strftime('%Y-%m-%d') if stock_out.stock_out_date else None,
            "recipient_user_id": stock_out.recipient_user_id,
            "recipient_name": stock_out.recipient_name,
            "department_id": stock_out.department_id,
            "department_name": stock_out.department_name,
            "handler_user_id": stock_out.handler_user_id,
            "handler_name": stock_out.handler_name,
            "status": stock_out.status,
            "total_amount": float(stock_out.total_amount) if stock_out.total_amount else 0,
            "remark": stock_out.remark or '',
            "review_user_id": stock_out.review_user_id,
            "review_time": stock_out.review_time.strftime('%Y-%m-%d %H:%M') if stock_out.review_time else None,
            "review_remark": stock_out.review_remark or '',
            "details": detail_list,
            "created_at": stock_out.created_at.strftime('%Y-%m-%d %H:%M') if stock_out.created_at else None,
            "updated_at": stock_out.updated_at.strftime('%Y-%m-%d %H:%M') if stock_out.updated_at else None
        }

        return jsonify({
            "success": True,
            "data": stock_out_data
        })

    except Exception as e:
        logging.error(f"API获取出库单详情失败 [ID: {id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取待审核出库单列表JSON ==========
@stock_out_api_bp.route('/pending', methods=['GET'])
@login_required
@admin_required
def get_pending_stock_outs():
    """获取待审核出库单列表JSON"""
    try:
        query = StockOut.query.filter_by(status='待审核').order_by(StockOut.id.desc())

        stock_outs = query.all()

        stock_out_list = [{
            "id": so.id,
            "stock_out_number": so.stock_out_number,
            "stock_out_type": so.stock_out_type,
            "stock_out_date": so.stock_out_date.strftime('%Y-%m-%d') if so.stock_out_date else None,
            "recipient_name": so.recipient_name,
            "department_name": so.department_name,
            "handler_name": so.handler_name,
            "total_amount": float(so.total_amount) if so.total_amount else 0,
            "detail_count": so.detail_count,
            "created_at": so.created_at.strftime('%Y-%m-%d %H:%M') if so.created_at else None
        } for so in stock_outs]

        return jsonify({
            "success": True,
            "data": stock_out_list
        })

    except Exception as e:
        logging.error(f"API获取待审核出库单列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取出库统计JSON ==========
@stock_out_api_bp.route('/statistics', methods=['GET'])
@login_required
@admin_required
def get_stock_out_statistics():
    """获取出库统计JSON（按类型/月份统计数量和金额）"""
    try:
        from sqlalchemy import func, extract
        from datetime import datetime as dt

        year = request.args.get('year', dt.now().year, type=int)

        # 基础查询：已审核的出库单
        base_query = StockOut.query.filter_by(status='已审核')

        base_query = base_query.filter(
            extract('year', StockOut.stock_out_date) == year
        )

        # 按类型统计
        type_stats = db.session.query(
            StockOut.stock_out_type,
            func.count(StockOut.id).label('count'),
            func.coalesce(func.sum(StockOut.total_amount), 0).label('total_amount')
        ).filter(
            StockOut.status == '已审核',
            extract('year', StockOut.stock_out_date) == year
        )

        type_stats = type_stats.group_by(StockOut.stock_out_type).all()

        type_statistics = [{
            "stock_out_type": ts.stock_out_type,
            "count": ts.count,
            "total_amount": float(ts.total_amount)
        } for ts in type_stats]

        # 按月份统计
        month_stats = db.session.query(
            extract('month', StockOut.stock_out_date).label('month'),
            func.count(StockOut.id).label('count'),
            func.coalesce(func.sum(StockOut.total_amount), 0).label('total_amount')
        ).filter(
            StockOut.status == '已审核',
            extract('year', StockOut.stock_out_date) == year
        )

        month_stats = month_stats.group_by(
            extract('month', StockOut.stock_out_date)
        ).order_by(
            extract('month', StockOut.stock_out_date)
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
        logging.error(f"API获取出库统计失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500