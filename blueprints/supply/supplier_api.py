from flask import Blueprint, request, jsonify
import logging
from utils.db import db
from flask_login import login_required, current_user
from utils.log import log_operation
import traceback
from utils.auth import require_permission
from models.supply.supplier import Supplier

supplier_api_bp = Blueprint('supplier_api', __name__, url_prefix='/api/suppliers')


# ========== 获取供应商列表JSON（分页+筛选） ==========
@supplier_api_bp.route('/list', methods=['GET'])
@login_required
@require_permission('supplier.view')
def get_supplier_list():
    """获取供应商列表JSON，支持分页和多条件筛选"""
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        status = request.args.get('status', '').strip()

        # 分页参数
        page = max(request.args.get('page', 1, type=int), 1)
        per_page = min(max(request.args.get('per_page', 20, type=int), 1), 100)

        # 构建查询
        query = Supplier.query.order_by(Supplier.id.desc())

        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    Supplier.name.ilike(search_filter),
                    Supplier.unified_social_credit_code.ilike(search_filter),
                    Supplier.legal_representative.ilike(search_filter),
                    Supplier.contact_person.ilike(search_filter),
                    Supplier.contact_phone.ilike(search_filter)
                )
            )
        if status:
            query = query.filter(Supplier.status == status)

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # 格式化供应商数据
        supplier_list = []
        for s in pagination.items:
            supplier_data = {
                "id": s.id,
                "name": s.name,
                "unified_social_credit_code": s.unified_social_credit_code or '',
                "legal_representative": s.legal_representative or '',
                "contact_person": s.contact_person or '',
                "contact_phone": s.contact_phone or '',
                "email": s.email or '',
                "address": s.address or '',
                "status": s.status or '启用',
                "handler_user_id": s.handler_user_id,
                "remark": s.remark or '',
                "created_at": s.created_at.strftime('%Y-%m-%d %H:%M') if s.created_at else None,
                "updated_at": s.updated_at.strftime('%Y-%m-%d %H:%M') if s.updated_at else None
            }
            supplier_list.append(supplier_data)

        response = {
            "success": True,
            "data": supplier_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages
            }
        }

        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='api_query',
            action=f"API查询供应商列表，页码:{page}，每页:{per_page}",
            result="成功"
        )

        return jsonify(response)

    except Exception as e:
        logging.error(f"API获取供应商列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取供应商详情JSON ==========
@supplier_api_bp.route('/<int:id>', methods=['GET'])
@login_required
@require_permission('supplier.view')
def get_supplier_detail(id):
    """获取供应商详情JSON"""
    try:
        supplier = Supplier.query.get_or_404(id)

        supplier_data = {
            "id": supplier.id,
            "name": supplier.name,
            "unified_social_credit_code": supplier.unified_social_credit_code or '',
            "legal_representative": supplier.legal_representative or '',
            "contact_person": supplier.contact_person or '',
            "contact_phone": supplier.contact_phone or '',
            "email": supplier.email or '',
            "address": supplier.address or '',
            "status": supplier.status or '启用',
            "handler_user_id": supplier.handler_user_id,
            "handler_name": supplier.handler_name,
            "remark": supplier.remark or '',
            "tax_rate": float(supplier.tax_rate) if supplier.tax_rate is not None else None,
            "created_at": supplier.created_at.strftime('%Y-%m-%d %H:%M') if supplier.created_at else None,
            "updated_at": supplier.updated_at.strftime('%Y-%m-%d %H:%M') if supplier.updated_at else None
        }

        return jsonify({
            "success": True,
            "data": supplier_data
        })

    except Exception as e:
        logging.error(f"API获取供应商详情失败 [ID: {id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 检查供应商使用情况JSON ==========
@supplier_api_bp.route('/check-usage/<int:id>', methods=['GET'])
@login_required
@require_permission('supplier.view')
def check_supplier_usage(id):
    """检查供应商是否被使用，返回使用详情JSON"""
    try:
        usage = Supplier.check_usage(id)
        return jsonify({
            "success": True,
            "data": usage
        })
    except Exception as e:
        logging.error(f"API检查供应商使用情况失败 [ID: {id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取启用中的供应商列表JSON（用于下拉选择） ==========
@supplier_api_bp.route('/active', methods=['GET'])
@login_required
def get_active_suppliers():
    """获取启用中的供应商列表，用于下拉选择"""
    try:
        suppliers = Supplier.get_active_suppliers()

        supplier_list = [{
            "id": s.id,
            "name": s.name,
            "contact_person": s.contact_person or '',
            "contact_phone": s.contact_phone or ''
        } for s in suppliers]

        return jsonify({
            "success": True,
            "data": supplier_list
        })
    except Exception as e:
        logging.error(f"API获取启用供应商列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取供应商名称列表JSON ==========
@supplier_api_bp.route('/names', methods=['GET'])
@login_required
def get_supplier_names():
    """获取所有供应商名称列表，供下拉选择使用"""
    try:
        names = Supplier.get_all_names()
        return jsonify({
            "success": True,
            "data": names
        })
    except Exception as e:
        logging.error(f"API获取供应商名称列表失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 快速创建供应商JSON（从入库单页面调用） ==========
@supplier_api_bp.route('/quick-create', methods=['POST'])
@login_required
@require_permission('supplier.create')
def quick_create_supplier():
    """快速创建供应商（从入库单页面调用）"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()

        if not name:
            return jsonify({"success": False, "error": "供应商名称不能为空"}), 400

        # 检查是否已存在
        existing = Supplier.query.filter_by(name=name).first()

        if existing:
            return jsonify({"success": True, "data": {"id": existing.id, "name": existing.name}})

        # 创建新供应商
        supplier = Supplier.create(
            name=name,
            status='启用',
            handler_user_id=current_user.id,
            operator_user_id=current_user.id
        )

        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='quick_create',
            action=f"快速创建供应商: {name}",
            result="成功"
        )

        return jsonify({"success": True, "data": {"id": supplier.id, "name": supplier.name}})

    except Exception as e:
        logging.error(f"API快速创建供应商失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500