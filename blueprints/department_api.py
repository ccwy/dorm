from flask import Blueprint, request, jsonify
import logging
from utils.db import db
from flask_login import login_required, current_user
from utils.log import log_operation
import traceback
from utils.auth import require_permission
from models.department import Department

department_api_bp = Blueprint('department_api', __name__, url_prefix='/api/departments')


# ========== 获取部门列表JSON（分页+筛选） ==========
@department_api_bp.route('/list', methods=['GET'])
@login_required
@require_permission('department.view')
def get_department_list():
    """获取部门列表JSON，支持分页和多条件筛选"""
    try:
        # 获取筛选参数
        company = request.args.get('company', '').strip()
        keyword = request.args.get('keyword', '').strip()

        # 分页参数
        page = max(request.args.get('page', 1, type=int), 1)
        per_page = min(max(request.args.get('per_page', 20, type=int), 1), 100)

        # 构建查询
        query = Department.query.order_by(Department.id.desc())

        if company:
            if company == '__none__':
                query = query.filter(Department.company.is_(None))
            else:
                query = query.filter(Department.company == company)
        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    Department.name.ilike(search_filter),
                    Department.description.ilike(search_filter)
                )
            )

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # 格式化部门数据
        department_list = []
        for dept in pagination.items:
            dept_data = {
                "id": dept.id,
                "name": dept.name,
                "company": dept.company or '',
                "description": dept.description or '',
                "status": dept.status or '正常',
                "created_date": dept.created_date.strftime('%Y-%m-%d') if dept.created_date else None,
                "created_at": dept.created_at.strftime('%Y-%m-%d %H:%M') if dept.created_at else None,
                "updated_at": dept.updated_at.strftime('%Y-%m-%d %H:%M') if dept.updated_at else None
            }
            department_list.append(dept_data)

        response = {
            "success": True,
            "data": department_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages
            }
        }

        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='api_query',
            action=f"API查询部门列表，页码:{page}，每页:{per_page}",
            result="成功"
        )

        return jsonify(response)

    except Exception as e:
        logging.error(f"API获取部门列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取所有部门名称（供下拉选择使用） ==========
@department_api_bp.route('/names', methods=['GET'])
@login_required
def get_department_names():
    """获取所有部门名称列表，供下拉选择使用"""
    try:
        names = Department.get_all_names()
        return jsonify({
            "success": True,
            "data": names
        })
    except Exception as e:
        logging.error(f"API获取部门名称列表失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取所有公司名称（供下拉选择使用） ==========
@department_api_bp.route('/companies', methods=['GET'])
@login_required
def get_companies():
    """获取所有公司名称列表，供下拉选择使用"""
    try:
        companies = Department.get_all_companies()
        return jsonify({
            "success": True,
            "data": companies
        })
    except Exception as e:
        logging.error(f"API获取公司列表失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 根据公司获取部门列表 ==========
@department_api_bp.route('/by-company/<string:company>', methods=['GET'])
@login_required
def get_departments_by_company(company):
    """根据公司名称获取部门列表"""
    try:
        departments = Department.get_by_company(company)
        dept_list = [{"id": d.id, "name": d.name, "description": d.description or ''} for d in departments]
        return jsonify({
            "success": True,
            "data": dept_list
        })
    except Exception as e:
        logging.error(f"API获取公司部门列表失败: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500