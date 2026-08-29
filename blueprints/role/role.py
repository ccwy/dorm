# -*- coding: utf-8 -*-
"""角色管理蓝图 - 角色列表页和角色详情页"""
from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from utils.db import db
from models.role import Role, RolePermission
from models.user import User
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

        # 获取该角色下的用户（分页）
        users_pagination = User.query.filter_by(role_id=role.id)\
            .order_by(User.id.asc())\
            .paginate(page=page, per_page=per_page, error_out=False)

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
            permissions_info=permissions_info
        )
    except Exception as e:
        logging.error(f"访问角色详情页失败: {str(e)}")
        flash(f'访问角色详情页失败: {str(e)}', 'danger')
        return redirect(url_for('role.role_list'))