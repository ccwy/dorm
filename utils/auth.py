# -*- coding: utf-8 -*-
"""认证工具模块 - 提供权限装饰器

将admin_required从system_settings.py中分离，避免26个蓝图
导入admin_required时触发system_settings.py的重量级导入链
（system_settings导入了大量模型、工具模块和配置）
"""
from functools import wraps
from flask import request, jsonify, flash, redirect, url_for
from flask_login import current_user


def admin_required(f):
    """管理员权限装饰器 - 要求当前用户必须是管理员"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({"success": False, "message": "无权限访问，需要管理员权限"}), 403
            flash('无权限访问，需要管理员权限', 'danger')
            return redirect(url_for('login.login'))
        return f(*args, **kwargs)
    return decorated_function