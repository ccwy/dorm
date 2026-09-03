# -*- coding: utf-8 -*-
"""角色管理蓝图 - 角色列表页和角色详情页"""
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from utils.db import db
from models.role import Role, RolePermission
from models.user.user import User
from models.department.department import Department
from utils.log import log_operation
from utils.auth import require_permission, PERMISSIONS
import logging

# 定义蓝图
role_bp = Blueprint(
    'role',
    __name__,
    url_prefix='/role',
    template_folder='../../templates',
    static_folder='../../static'
)

# 导入操作模块和API模块（路由注册到role_bp上）
from . import role_operations
from . import role_api


# ========== 角色列表页 ==========
@role_bp.route('/', methods=['GET'])
@login_required
@require_permission('role.view')
def role_list():
    """角色列表页"""
    try:
        # 获取所有角色，按sort_order排序
        roles = Role.query.order_by(Role.sort_order.asc(), Role.id.asc()).all()

        # 构建角色信息列表
        role_list_data = []
        for role in roles:
            permission_codes = role.get_permission_codes()
            role_list_data.append({
                'id': role.id,
                'name': role.name,
                'code': role.code,
                'description': role.description or '',
                'is_system': role.is_system,
                'sort_order': role.sort_order,
                'user_count': role.get_user_count(),
                'permission_count': len(permission_codes),
                'created_at': role.created_at.strftime('%Y-%m-%d %H:%M') if role.created_at else ''
            })

        log_operation(
            user_id=current_user.id,
            module='role',
            operation_type='view',
            action='访问角色列表页',
            result='成功'
        )
        return render_template('role_manage/role_list.html', title='角色管理', roles=role_list_data)
    except Exception as e:
        logging.error(f"访问角色列表页失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='role',
            operation_type='view',
            action=f'访问角色列表页 [错误: {str(e)}]',
            result='失败'
        )
        return render_template('role_manage/role_list.html', title='角色管理', roles=[], error=str(e))


# ========== 角色详情页（查看角色下的用户） ==========
@role_bp.route('/detail/<int:id>', methods=['GET'])
@login_required
@require_permission('role.view')
def role_detail(id):
    """角色详情页 - 查看角色下的用户列表"""
    try:
        role = Role.query.get_or_404(id)

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = 20

        # 搜索和筛选参数
        keyword = request.args.get('keyword', '', type=str).strip()
        filter_company = request.args.get('company', '', type=str).strip()
        filter_department = request.args.get('department', '', type=str).strip()

        # 构建查询 - 基础条件：该角色下的用户
        query = User.query.filter_by(role_id=role.id)

        # 关键字搜索（姓名、用户名、工号）
        if keyword:
            search_pattern = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    User.name.like(search_pattern),
                    User.username.like(search_pattern),
                    User.student_id.like(search_pattern)
                )
            )

        # 公司筛选（通过Department表关联查询，确保数据源统一）
        if filter_company:
            query = query.join(Department, User.department_id == Department.id).filter(Department.company == filter_company)

        # 部门筛选（通过department_id关联Department表）
        if filter_department:
            dept = Department.query.filter_by(name=filter_department).first()
            if dept:
                query = query.filter(User.department_id == dept.id)
            else:
                # 部门不存在则返回空结果
                query = query.filter(User.department_id == -1)

        # 排序和分页
        users_pagination = query.order_by(User.id.asc())\
            .paginate(page=page, per_page=per_page, error_out=False)

        # 获取所有公司列表（从Department表获取，与部门管理模块数据源一致）
        company_list = Department.get_all_companies()

        department_list = db.session.query(Department.name)\
            .join(User, User.department_id == Department.id)\
            .filter(User.role_id == role.id)\
            .distinct().order_by(Department.name).all()
        department_list = [d[0] for d in department_list]

        # 获取所有角色（用于导航）
        all_roles = Role.query.order_by(Role.sort_order.asc(), Role.id.asc()).all()

        # 分页工具
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

        page_range = generate_page_range(page, users_pagination.pages)

        # 构建权限信息（按模块分组）
        permission_codes = set(role.get_permission_codes())
        permissions_info = []
        if role.code != 'super_admin':
            for module_code, module_info in PERMISSIONS.items():
                module_actions = []
                for action_code, action_name in module_info['actions'].items():
                    if f"{module_code}.{action_code}" in permission_codes:
                        module_actions.append({'code': action_code, 'name': action_name})
                if module_actions:
                    permissions_info.append({
                        'module_code': module_code,
                        'module_name': module_info['name'],
                        'actions': module_actions
                    })

        log_operation(
            user_id=current_user.id,
            module='role',
            operation_type='view',
            action=f'查看角色详情: {role.name}',
            result='成功'
        )
        return render_template(
            'role_manage/role_detail.html',
            title=f'角色详情 - {role.name}',
            role=role,
            users=users_pagination.items,
            pagination=users_pagination,
            page_range=page_range,
            all_roles=all_roles,
            permissions_info=permissions_info,
            keyword=keyword,
            filter_company=filter_company,
            filter_department=filter_department,
            company_list=company_list,
            department_list=department_list
        )
    except Exception as e:
        logging.error(f"访问角色详情页失败: {str(e)}")
        flash(f'访问角色详情页失败: {str(e)}', 'danger')
        return redirect(url_for('role.role_list'))