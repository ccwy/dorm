# -*- coding: utf-8 -*-
"""认证工具模块 - 提供权限装饰器和权限注册表

基于角色的CRUD操作级权限控制，替代旧的admin_required体系
"""
from functools import wraps
from flask import request, jsonify, flash, redirect, url_for, abort
from flask_login import current_user


# ===========================
# 权限注册表 - 系统所有可用模块及操作权限
# ===========================
PERMISSIONS = {
    'user': {
        'name': '用户管理',
        'actions': {
            'view': '查看',
            'manage': '管理',
            'create': '新增',
            'edit': '编辑',
            'delete': '删除',
            'export': '导出',
            'import': '导入',
        }
    },
    'department': {
        'name': '部门管理',
        'actions': {
            'view': '查看',
            'manage': '管理',
            'create': '新增',
            'edit': '编辑',
            'delete': '删除',
            'export': '导出',
            'import': '导入',
        }
    },
    'room': {
        'name': '房间管理',
        'actions': {
            'view': '查看',
            'manage': '管理',
            'create': '新增',
            'edit': '编辑',
            'delete': '删除',
            'export': '导出',
            'import': '导入',
        }
    },
    'dorm': {
        'name': '宿舍管理',
        'actions': {
            'view': '查看',
            'manage': '管理',
            'allocate': '分配',
            'checkout': '退宿',
            'change': '换宿',
            'delete': '删除',
            'export': '导出',
            'import': '导入',
        }
    },
    'utility': {
        'name': '水电费管理',
        'actions': {
            'view': '查看',
            'manage': '管理',
            'reading': '抄表',
            'calculate': '核算',
            'edit': '编辑',
            'delete': '删除',
            'export': '导出',
            'import': '导入',
        }
    },
    'fee_subsidy': {
        'name': '费用补贴',
        'actions': {
            'view': '查看',
            'manage': '管理',
            'create': '新增',
            'edit': '编辑',
            'delete': '删除',
            'export': '导出',
            'import': '导入',
        }
    },
    'fixed_asset': {
        'name': '固定资产管理',
        'actions': {
            'view': '查看',
            'manage': '管理',
            'create': '新增',
            'edit': '编辑',
            'delete': '删除',
            'scrap': '报废',
            'transfer': '转移',
            'sell': '出售',
            'inventory': '盘点',
            'inventory_approve': '盘点审核',
            'inventory_unapprove': '盘点反审核',
            'export': '导出',
            'import': '导入',
        }
    },
    'supply': {
        'name': '低值易耗品管理',
        'actions': {
            'view': '查看',
            'manage': '管理',
            'create': '新增',
            'edit': '编辑',
            'delete': '删除',
            'approve': '审核',
            'unapprove': '反审核',
            'supplier': '供应商管理',
            'supply_item': '基础物料资料',
            'storage_location': '存放位置管理',
            'supply_stock_detail': '库存明细',
            'stock_in': '入库管理',
            'stock_out': '出库管理',
            'supply_inventory': '盘点管理',
            'supply_stock_record': '进出库记录',
            'export': '导出',
            'import': '导入',
        }
    },
    'file_sharing': {
        'name': '文件共享',
        'actions': {
            'view': '查看',
            'manage': '管理',
            'delete': '删除',
        }
    },
    'ticket': {
        'name': '留言管理',
        'actions': {
            'view': '查看',
            'manage': '管理',
            'create': '新增',
            'edit': '编辑',
            'delete': '删除',
        }
    },
    'maintenance': {
        'name': '后勤维修',
        'actions': {
            'view': '查看',
            'manage': '管理',
            'create': '新增',
            'handle': '处理',
        }
    },
    'todo': {
        'name': '待办事项',
        'actions': {
            'view': '查看',
            'manage': '管理',
            'create': '新增',
            'edit': '编辑',
            'delete': '删除',
            'export': '导出',
        }
    },
    'chat': {
        'name': '聊天',
        'actions': {
            'manage': '管理',
        }
    },
    'system_settings': {
        'name': '系统设置',
        'actions': {
            'manage': '管理',
        }
    },
    'log': {
        'name': '日志',
        'actions': {
            'view': '查看',
            'manage': '管理',
        }
    },
    'contract': {
        'name': '合同管理',
        'actions': {
            'view': '查看',
            'manage': '管理',
            'create': '新增',
            'edit': '编辑',
            'delete': '删除',
            'export': '导出',
            'import': '导入',
        }
    },
    'role': {
        'name': '角色管理',
        'actions': {
            'view': '查看',
            'manage': '管理',
            'create': '新增',
            'edit': '编辑',
            'delete': '删除',
        }
    },
}


def require_permission(permission_code):
    """权限装饰器 - 检查当前用户是否拥有指定权限
    
    工作原理：
    1. 检查当前用户是否已登录 → 未登录则重定向到登录页
    2. 检查当前用户的角色是否拥有该权限 → 无权限则返回403
    3. 超级管理员角色（code为super_admin）自动拥有所有权限
    
    使用示例：
        @require_permission('user.view')
        @require_permission('user.create')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                # 未登录 → 重定向到登录页
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({"success": False, "message": "请先登录"}), 401
                flash('请先登录以访问此页面', 'info')
                return redirect(url_for('login.login'))
            
            if not current_user.has_permission(permission_code):
                # 无权限 → 返回403
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({"success": False, "message": f"无权限访问，需要 {permission_code} 权限"}), 403
                flash(f'无权限访问，需要 {permission_code} 权限', 'danger')
                return redirect(url_for('login.login'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


