# -*- coding: utf-8 -*-
"""角色管理API蓝图 - AJAX接口（添加/移除用户、搜索用户）"""
from flask import request, jsonify
from flask_login import login_required, current_user
from utils.db import db
from models.role import Role, RolePermission
from models.user import User
from utils.log import log_operation
from utils.auth import require_permission
import logging
import traceback
from .role import role_bp


# ========== 搜索用户（用于添加用户弹窗） ==========
@role_bp.route('/api/users/search', methods=['GET'])
@login_required
@require_permission('role.edit')
def api_search_users():
    """搜索用户 - 用于角色详情页添加用户弹窗"""
    try:
        keyword = request.args.get('keyword', '').strip()
        role_id = request.args.get('role_id', type=int)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)

        if not role_id:
            return jsonify({'success': False, 'message': '缺少角色ID'}), 400

        role = Role.query.get(role_id)
        if not role:
            return jsonify({'success': False, 'message': '角色不存在'}), 404

        # 查询不在当前角色中的用户
        query = User.query.filter(
            db.or_(User.role_id != role_id, User.role_id.is_(None))
        )

        # 超级管理员保护：非super_admin角色搜索用户时排除内置admin账号
        if role.code != 'super_admin':
            query = query.filter(User.id != 1)

        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(User.name.ilike(search_filter), User.username.ilike(search_filter))
            )

        pagination = query.order_by(User.id.asc()).paginate(page=page, per_page=per_page, error_out=False)
        users = pagination.items

        user_list = []
        for user in users:
            user_list.append({
                'id': user.id,
                'name': user.name or '',
                'username': user.username or '',
                'department': user.department or '',
                'current_role': user.user_role.name if user.user_role else '无角色'
            })

        return jsonify({
            'success': True,
            'users': user_list,
            'total': pagination.total,
            'pages': pagination.pages,
            'current_page': pagination.page
        })

    except Exception as e:
        logging.error(f"搜索用户失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ========== 添加用户到角色 ==========
@role_bp.route('/api/users/add', methods=['POST'])
@login_required
@require_permission('role.edit')
def api_add_users():
    """添加用户到角色 - 支持单个和批量"""
    try:
        role_id = request.form.get('role_id', type=int)
        user_ids = request.form.getlist('user_ids')

        if not role_id:
            return jsonify({'success': False, 'message': '缺少角色ID'}), 400

        role = Role.query.get(role_id)
        if not role:
            return jsonify({'success': False, 'message': '角色不存在'}), 404

        if not user_ids:
            return jsonify({'success': False, 'message': '请选择要添加的用户'}), 400

        # 超级管理员保护：内置admin账号(ID=1)不可被分配到其他角色
        protected_count = 0
        if role.code != 'super_admin':
            admin_id_str = '1'
            protected_count = user_ids.count(admin_id_str)
            user_ids = [uid for uid in user_ids if uid != admin_id_str]
            if protected_count > 0 and not user_ids:
                return jsonify({'success': False, 'message': '内置超级管理员账号不可分配到其他角色'}), 403

        added_count = 0
        for uid_str in user_ids:
            uid = int(uid_str)
            user = User.query.get(uid)
            if user and user.role_id != role_id:
                user.role_id = role_id
                added_count += 1

        # 记录角色变更
        from models.user_operation_record import UserOperationRecord
        for uid_str in user_ids:
            uid = int(uid_str)
            user = User.query.get(uid)
            if user and user.role_id == role_id:
                old_role_name = user.user_role.name if user.user_role else '无角色'
                UserOperationRecord.create_record(
                    target_user_id=uid,
                    operation_type='role_change',
                    operator_id=current_user.id,
                    operator_name=current_user.name,
                    change_detail={
                        'old_role': old_role_name,
                        'new_role': role.name,
                        'action': '分配角色'
                    },
                    summary=f'角色变更：{old_role_name} → {role.name}'
                )

        db.session.commit()

        log_operation(
            user_id=current_user.id,
            module='role',
            operation_type='edit',
            action=f'向角色 {role.name} 添加 {added_count} 个用户',
            result='成功'
        )
        msg = f'成功添加 {added_count} 个用户'
        if protected_count > 0:
            msg += f'（已自动排除 {protected_count} 个内置超级管理员账号）'
        return jsonify({'success': True, 'message': msg})

    except Exception as e:
        db.session.rollback()
        logging.error(f"添加用户到角色失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500


# ========== 从角色移除用户 ==========
@role_bp.route('/api/users/remove', methods=['POST'])
@login_required
@require_permission('role.edit')
def api_remove_users():
    """从角色移除用户 - 支持单个和批量"""
    try:
        role_id = request.form.get('role_id', type=int)
        user_ids = request.form.getlist('user_ids')

        if not role_id:
            return jsonify({'success': False, 'message': '缺少角色ID'}), 400

        role = Role.query.get(role_id)
        if not role:
            return jsonify({'success': False, 'message': '角色不存在'}), 404

        if not user_ids:
            return jsonify({'success': False, 'message': '请选择要移除的用户'}), 400

        # 超级管理员角色保护：内置admin账号(ID=1)不可移除
        if role.code == 'super_admin':
            admin_id_str = '1'
            protected_count = user_ids.count(admin_id_str)
            user_ids = [uid for uid in user_ids if uid != admin_id_str]
            if protected_count > 0 and not user_ids:
                    return jsonify({'success': False, 'message': '内置超级管理员账号不可从超级管理员角色中移除'}), 403

        removed_count = 0
        for uid_str in user_ids:
            uid = int(uid_str)
            user = User.query.get(uid)
            if user and user.role_id == role_id:
                user.role_id = None
                removed_count += 1

        # 记录角色移除
        from models.user_operation_record import UserOperationRecord
        for uid_str in user_ids:
            uid = int(uid_str)
            user = User.query.get(uid)
            if user:
                UserOperationRecord.create_record(
                    target_user_id=uid,
                    operation_type='role_change',
                    operator_id=current_user.id,
                    operator_name=current_user.name,
                    change_detail={
                        'old_role': role.name,
                        'new_role': '无角色',
                        'action': '移除角色'
                    },
                    summary=f'角色变更：{role.name} → 无角色'
                )

        db.session.commit()

        log_operation(
            user_id=current_user.id,
            module='role',
            operation_type='edit',
            action=f'从角色 {role.name} 移除 {removed_count} 个用户',
            result='成功'
        )
        return jsonify({'success': True, 'message': f'成功移除 {removed_count} 个用户'})

    except Exception as e:
        db.session.rollback()
        logging.error(f"从角色移除用户失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': str(e)}), 500