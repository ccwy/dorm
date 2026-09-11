# -*- coding: utf-8 -*-
"""角色-权限关联表模型"""
from utils.db import db


class RolePermission(db.Model):
    __tablename__ = 'role_permissions'

    id = db.Column(db.Integer, primary_key=True)
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=False, comment='角色ID')
    permission_code = db.Column(db.String(50), nullable=False, comment='权限编码（格式：模块.操作）')

    # 唯一约束：同一角色不能重复分配相同权限
    __table_args__ = (
        db.UniqueConstraint('role_id', 'permission_code', name='uq_role_permission'),
    )

    def __repr__(self):
        return f"<RolePermission role_id={self.role_id} permission={self.permission_code}>"

    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'role_id': self.role_id,
            'permission_code': self.permission_code
        }