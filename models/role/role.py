# -*- coding: utf-8 -*-
"""角色表模型"""
from utils.db import db
from datetime import datetime


class Role(db.Model):
    __tablename__ = 'roles'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False, comment='角色名称')
    code = db.Column(db.String(50), unique=True, nullable=False, comment='角色编码')
    description = db.Column(db.String(200), nullable=True, comment='角色描述')
    is_system = db.Column(db.Boolean, default=False, comment='是否系统内置角色（不可删除）')
    sort_order = db.Column(db.Integer, default=0, comment='排序权重')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')

    # 关系：角色拥有的权限列表
    permissions = db.relationship('RolePermission', backref='role', lazy='dynamic',
                                  cascade='all, delete-orphan')
    # 关系：角色下的用户列表
    users = db.relationship('User', backref='user_role', lazy='dynamic',
                            foreign_keys='User.role_id')

    def __repr__(self):
        return f"<Role {self.code}: {self.name}>"

    def has_permission(self, permission_code):
        """判断角色是否拥有指定权限"""
        # 超级管理员自动拥有所有权限
        if self.code == 'super_admin':
            return True
        return self.permissions.filter_by(permission_code=permission_code).first() is not None

    def get_permission_codes(self):
        """获取角色的所有权限编码列表"""
        if self.code == 'super_admin':
            from utils.auth import PERMISSIONS
            codes = []
            for module_code, module_info in PERMISSIONS.items():
                for action_code in module_info['actions']:
                    codes.append(f"{module_code}.{action_code}")
            return codes
        return [p.permission_code for p in self.permissions.all()]

    def get_user_count(self):
        """获取角色下的用户数量"""
        return self.users.count()

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'description': self.description,
            'is_system': self.is_system,
            'sort_order': self.sort_order,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S') if self.created_at else None,
            'user_count': self.get_user_count(),
            'permission_count': self.permissions.count()
        }