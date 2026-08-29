from flask import Blueprint, request, jsonify
import logging
from utils.db import db
from flask_login import login_required, current_user
from utils.log import log_operation
import traceback
from utils.auth import admin_required
from models.supply.storage_location import StorageLocation
from models.supply.supply_stock_detail import SupplyStockDetail

storage_location_api_bp = Blueprint('storage_location_api', __name__, url_prefix='/api/storage-locations')


# ========== 获取存放位置列表JSON（分页+筛选） ==========
@storage_location_api_bp.route('/list', methods=['GET'])
@login_required
@admin_required
def get_storage_location_list():
    """获取存放位置列表JSON，支持分页和多条件筛选"""
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        status = request.args.get('status', '').strip()

        # 分页参数
        page = max(request.args.get('page', 1, type=int), 1)
        per_page = min(max(request.args.get('per_page', 20, type=int), 1), 100)

        # 构建查询
        query = StorageLocation.query.order_by(StorageLocation.id.desc())

        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    StorageLocation.name.ilike(search_filter),
                    StorageLocation.code.ilike(search_filter),
                    StorageLocation.building.ilike(search_filter),
                    StorageLocation.room.ilike(search_filter)
                )
            )
        if status:
            query = query.filter(StorageLocation.status == status)

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # 格式化存放位置数据
        location_list = []
        for loc in pagination.items:
            location_data = {
                "id": loc.id,
                "name": loc.name,
                "code": loc.code or '',
                "building": loc.building or '',
                "floor": loc.floor or '',
                "room": loc.room or '',
                "display_name": loc.display_name,
                "status": loc.status or '启用',
                "remark": loc.remark or '',
                "created_at": loc.created_at.strftime('%Y-%m-%d %H:%M') if loc.created_at else None,
                "updated_at": loc.updated_at.strftime('%Y-%m-%d %H:%M') if loc.updated_at else None
            }
            location_list.append(location_data)

        response = {
            "success": True,
            "data": location_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages
            }
        }

        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='api_query',
            action=f"API查询存放位置列表，页码:{page}，每页:{per_page}",
            result="成功"
        )

        return jsonify(response)

    except Exception as e:
        logging.error(f"API获取存放位置列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取存放位置详情JSON ==========
@storage_location_api_bp.route('/<int:id>', methods=['GET'])
@login_required
@admin_required
def get_storage_location_detail(id):
    """获取存放位置详情JSON"""
    try:
        location = StorageLocation.query.get_or_404(id)

        location_data = {
            "id": location.id,
            "name": location.name,
            "code": location.code or '',
            "building": location.building or '',
            "floor": location.floor or '',
            "room": location.room or '',
            "display_name": location.display_name,
            "status": location.status or '启用',
            "remark": location.remark or '',
            "operator_user_id": location.operator_user_id,
            "created_at": location.created_at.strftime('%Y-%m-%d %H:%M') if location.created_at else None,
            "updated_at": location.updated_at.strftime('%Y-%m-%d %H:%M') if location.updated_at else None
        }

        return jsonify({
            "success": True,
            "data": location_data
        })

    except Exception as e:
        logging.error(f"API获取存放位置详情失败 [ID: {id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取启用中的存放位置列表JSON（用于下拉选择） ==========
@storage_location_api_bp.route('/active', methods=['GET'])
@login_required
def get_active_storage_locations():
    """获取启用中的存放位置列表，用于下拉选择"""
    try:
        locations = StorageLocation.get_active_locations()

        location_list = [{
            "id": loc.id,
            "name": loc.name,
            "code": loc.code or '',
            "display_name": loc.display_name,
            "building": loc.building or '',
            "room": loc.room or ''
        } for loc in locations]

        return jsonify({
            "success": True,
            "data": location_list
        })
    except Exception as e:
        logging.error(f"API获取启用存放位置列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取存放位置名称列表JSON ==========
@storage_location_api_bp.route('/names', methods=['GET'])
@login_required
def get_storage_location_names():
    """获取所有存放位置名称列表，供下拉选择使用"""
    try:
        names = StorageLocation.get_all_names()
        return jsonify({
            "success": True,
            "data": names
        })
    except Exception as e:
        logging.error(f"API获取存放位置名称列表失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 检查存放位置是否被使用 ==========
@storage_location_api_bp.route('/check-usage/<int:id>', methods=['GET'])
@login_required
@admin_required
def check_storage_location_usage(id):
    """检查存放位置是否被库存明细使用"""
    try:
        location = StorageLocation.query.get_or_404(id)

        # 检查是否有关联的库存明细记录
        stock_count = SupplyStockDetail.query.filter_by(location_id=id).count()

        # 检查是否有非零库存
        non_zero_count = SupplyStockDetail.query.filter_by(location_id=id).filter(
            SupplyStockDetail.quantity > 0
        ).count()

        return jsonify({
            "success": True,
            "data": {
                "id": location.id,
                "name": location.name,
                "display_name": location.display_name,
                "is_used": stock_count > 0,
                "stock_detail_count": stock_count,
                "non_zero_stock_count": non_zero_count,
                "can_delete": stock_count == 0
            }
        })

    except Exception as e:
        logging.error(f"API检查存放位置使用情况失败 [ID: {id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 快速创建存放位置（供入库单等表单使用） ==========
@storage_location_api_bp.route('/quick-create', methods=['POST'])
@login_required
def quick_create_storage_location():
    """快速创建存储位置（供入库单等表单使用）"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip() if data else ''

        if not name:
            return jsonify({'success': False, 'message': '位置名称不能为空'}), 400

        # 检查是否已存在（不区分公司，因为正在移除所属公司）
        existing = StorageLocation.query.filter_by(name=name).first()
        if existing:
            return jsonify({'success': True, 'id': existing.id, 'name': existing.name, 'message': '位置已存在'})

        # 创建新位置
        location = StorageLocation.create(name=name, status='启用', handler_user_id=current_user.id, operator_user_id=current_user.id)
        logging.info(f"快速创建存放位置成功，位置ID: {location.id}, 名称: {name}")

        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='storage_location_add',
            action=f"快速创建存放位置: {name}",
            result="成功"
        )

        return jsonify({'success': True, 'id': location.id, 'name': location.name, 'message': '位置创建成功'})
    except Exception as e:
        logging.error(f"快速创建存放位置失败: {str(e)}")
        return jsonify({'success': False, 'message': f'创建失败: {str(e)}'}), 500