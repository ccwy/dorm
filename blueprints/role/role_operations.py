# -*- coding: utf-8 -*-
"""角色管理操作蓝图 - 新增、编辑、删除角色"""
from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from utils.db import db
from models.role import Role, RolePermission
from models.user import User
from utils.log import log_operation
from utils.auth import require_permission, PERMISSIONS
import logging
import traceback
import random
import string
from .role import role_bp


def _generate_role_code():
    """生成唯一的角色编码，格式: role_ + 6位随机字母数字"""
    while True:
        chars = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        code = f'role_{chars}'
        if not Role.query.filter_by(code=code).first():
            return code


# ========== 新增角色页面 ==========
@role_bp.route('/add', methods=['GET'])
@login_required
@require_permission('role.create')
def add_page():
    """新增角色页面"""
    return render_template(
        'role_manage/role_edit.html',
        title='新增角色',
        role=None,
        permissions=PERMISSIONS,
        selected_permissions=[],
        is_super_admin=False
    )


# ========== 新增角色提交 ==========
@role_bp.route('/operations/add', methods=['POST'])
@login_required
@require_permission('role.create')
def add_role():
    """新增角色"""
    try:
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip()
        description = request.form.get('description', '').strip() or None
        sort_order = request.form.get('sort_order', 0, type=int)

        # 必填字段校验
        if not name:
            flash('角色名称不能为空', 'danger')
            return redirect(url_for('role.add_page'))

        # 角色编码：为空时自动生成，有值时校验格式
        if not code:
            code = _generate_role_code()
        else:
            # 编码格式校验（只允许字母、数字、下划线）
            import re
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', code):
                flash('角色编码只能包含字母、数字和下划线，且必须以字母开头', 'danger')
                return redirect(url_for('role.add_page'))

        # 检查名称和编码是否重复
        if Role.query.filter_by(name=name).first():
            flash(f'已存在角色名称"{name}"', 'danger')
            return redirect(url_for('role.add_page'))
        if Role.query.filter_by(code=code).first():
            flash(f'已存在角色编码"{code}"', 'danger')
            return redirect(url_for('role.add_page'))

        # 创建角色
        role = Role(
            name=name,
            code=code,
            description=description,
            is_system=False,
            sort_order=sort_order
        )
        db.session.add(role)
        db.session.flush()  # 获取role.id

        # 处理权限勾选
        permission_codes = request.form.getlist('permissions')
        for perm_code in permission_codes:
            perm = RolePermission(role_id=role.id, permission_code=perm_code)
            db.session.add(perm)

        db.session.commit()

        # 记录角色权限变更 - 对该角色下的所有用户记录操作
        if role.code != 'super_admin':
            new_permissions = role.get_permission_codes()
            if set(old_permissions) != set(new_permissions):
                from models.user_operation_record import UserOperationRecord
                # 为该角色下的每个用户创建操作记录
                affected_users = User.query.filter_by(role_id=id).all()
                for affected_user in affected_users:
                    UserOperationRecord.create_record(
                        target_user_id=affected_user.id,
                        operation_type='role_change',
                        operator_id=current_user.id,
                        operator_name=current_user.name,
                        change_detail={
                            'action': '角色权限变更',
                            'role_name': role.name,
                            'added_permissions': list(set(new_permissions) - set(old_permissions)),
                            'removed_permissions': list(set(old_permissions) - set(new_permissions))
                        },
                        summary=f'角色【{role.name}】权限变更'
                    )
                db.session.commit()

        log_operation(
            user_id=current_user.id,
            module='role',
            operation_type='create',
            action=f'新增角色: {name}({code})',
            result='成功'
        )
        flash(f'新增角色成功: {name}', 'success')
        return redirect(url_for('role.role_list'))

    except Exception as e:
        db.session.rollback()
        logging.error(f"新增角色失败: {str(e)}\n{traceback.format_exc()}")
        log_operation(
            user_id=current_user.id,
            module='role',
            operation_type='create',
            action=f'新增角色失败: {str(e)}',
            result='失败'
        )
        flash(f'新增角色失败: {str(e)}', 'danger')
        return redirect(url_for('role.add_page'))


# ========== 编辑角色页面 ==========
@role_bp.route('/edit/<int:id>', methods=['GET'])
@login_required
@require_permission('role.edit')
def edit_page(id):
    """编辑角色页面"""
    role = Role.query.get_or_404(id)
    selected_permissions = role.get_permission_codes()
    is_super_admin = (role.code == 'super_admin')

    return render_template(
        'role_manage/role_edit.html',
        title=f'编辑角色 - {role.name}',
        role=role,
        permissions=PERMISSIONS,
        selected_permissions=selected_permissions,
        is_super_admin=is_super_admin
    )


# ========== 编辑角色提交 ==========
@role_bp.route('/operations/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('role.edit')
def edit_role(id):
    """编辑角色"""
    try:
        role = Role.query.get_or_404(id)

        # 超级管理员角色只允许修改名称和描述，不允许修改权限
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip() or None
        sort_order = request.form.get('sort_order', 0, type=int)

        # 必填字段校验
        if not name:
            flash('角色名称不能为空', 'danger')
            return redirect(url_for('role.edit_page', id=id))

        # 检查名称是否重复（排除自身）
        existing = Role.query.filter_by(name=name).first()
        if existing and existing.id != id:
            flash(f'已存在角色名称"{name}"', 'danger')
            return redirect(url_for('role.edit_page', id=id))

        # 更新基本信息
        role.name = name
        role.description = description
        role.sort_order = sort_order

        # 超级管理员角色不允许修改权限
        if role.code != 'super_admin':
            # 获取旧权限列表（用于变更记录）
            old_permissions = role.get_permission_codes() if role.code != 'super_admin' else []
            # 删除旧权限
            RolePermission.query.filter_by(role_id=id).delete()

            # 添加新权限
            permission_codes = request.form.getlist('permissions')
            for perm_code in permission_codes:
                perm = RolePermission(role_id=id, permission_code=perm_code)
                db.session.add(perm)

        db.session.commit()

        # 记录角色权限变更 - 对该角色下的所有用户记录操作
        if role.code != 'super_admin':
            new_permissions = role.get_permission_codes()
            if set(old_permissions) != set(new_permissions):
                from models.user_operation_record import UserOperationRecord
                # 为该角色下的每个用户创建操作记录
                affected_users = User.query.filter_by(role_id=id).all()
                for affected_user in affected_users:
                    UserOperationRecord.create_record(
                        target_user_id=affected_user.id,
                        operation_type='role_change',
                        operator_id=current_user.id,
                        operator_name=current_user.name,
                        change_detail={
                            'action': '角色权限变更',
                            'role_name': role.name,
                            'added_permissions': list(set(new_permissions) - set(old_permissions)),
                            'removed_permissions': list(set(old_permissions) - set(new_permissions))
                        },
                        summary=f'角色【{role.name}】权限变更'
                    )
                db.session.commit()

        log_operation(
            user_id=current_user.id,
            module='role',
            operation_type='edit',
            action=f'编辑角色: {name}({role.code})',
            result='成功'
        )
        flash(f'编辑角色成功: {name}', 'success')
        return redirect(url_for('role.role_list'))

    except Exception as e:
        db.session.rollback()
        logging.error(f"编辑角色失败: {str(e)}\n{traceback.format_exc()}")
        log_operation(
            user_id=current_user.id,
            module='role',
            operation_type='edit',
            action=f'编辑角色失败: {str(e)}',
            result='失败'
        )
        flash(f'编辑角色失败: {str(e)}', 'danger')
        return redirect(url_for('role.edit_page', id=id))


# ========== 删除角色 ==========
@role_bp.route('/operations/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('role.delete')
def delete_role(id):
    """删除角色"""
    try:
        role = Role.query.get_or_404(id)

        # 系统内置角色不可删除
        if role.is_system:
            flash('系统内置角色不可删除', 'danger')
            return redirect(url_for('role.role_list'))

        # 检查是否有用户关联
        user_count = role.get_user_count()
        if user_count > 0:
            flash(f'该角色下有 {user_count} 个用户，请先移除用户后再删除', 'danger')
            return redirect(url_for('role.role_list'))

        role_name = role.name
        role_code = role.code

        # 删除角色（级联删除权限关联）
        db.session.delete(role)
        db.session.commit()

        # 记录角色权限变更 - 对该角色下的所有用户记录操作
        if role.code != 'super_admin':
            new_permissions = role.get_permission_codes()
            if set(old_permissions) != set(new_permissions):
                from models.user_operation_record import UserOperationRecord
                # 为该角色下的每个用户创建操作记录
                affected_users = User.query.filter_by(role_id=id).all()
                for affected_user in affected_users:
                    UserOperationRecord.create_record(
                        target_user_id=affected_user.id,
                        operation_type='role_change',
                        operator_id=current_user.id,
                        operator_name=current_user.name,
                        change_detail={
                            'action': '角色权限变更',
                            'role_name': role.name,
                            'added_permissions': list(set(new_permissions) - set(old_permissions)),
                            'removed_permissions': list(set(old_permissions) - set(new_permissions))
                        },
                        summary=f'角色【{role.name}】权限变更'
                    )
                db.session.commit()

        log_operation(
            user_id=current_user.id,
            module='role',
            operation_type='delete',
            action=f'删除角色: {role_name}({role_code})',
            result='成功'
        )
        flash(f'删除角色成功: {role_name}', 'success')
        return redirect(url_for('role.role_list'))

    except Exception as e:
        db.session.rollback()
        logging.error(f"删除角色失败: {str(e)}\n{traceback.format_exc()}")
        log_operation(
            user_id=current_user.id,
            module='role',
            operation_type='delete',
            action=f'删除角色失败: {str(e)}',
            result='失败'
        )
        flash(f'删除角色失败: {str(e)}', 'danger')
        return redirect(url_for('role.role_list'))