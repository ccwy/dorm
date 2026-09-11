from datetime import datetime
from utils.db import db


class UserOperationRecord(db.Model):
    """用户操作记录表 - 记录用户增加/编辑/角色权限变更等操作"""
    __tablename__ = 'user_operation_records'

    id = db.Column(db.Integer, primary_key=True)
    target_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, comment='被操作的用户ID')
    operation_type = db.Column(db.String(20), nullable=False, comment='操作类型：add/edit/role_change/import/batch_update')
    operator_id = db.Column(db.Integer, nullable=True, comment='操作人ID')
    operator_name = db.Column(db.String(50), nullable=True, comment='操作人姓名')
    operation_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='操作时间')
    
    # 变更详情（JSON格式，记录变更前后值）
    change_detail = db.Column(db.Text, nullable=True, comment='变更详情（JSON格式）')
    # 示例: 
    # add操作: {"name": "张三", "student_id": "10001", "category": "员工", "role": "普通用户"}
    # edit操作: [{"field": "name", "old": "张三", "new": "李四"}, {"field": "phone", "old": "138", "new": "139"}]
    # role_change操作: {"old_role": "普通用户", "new_role": "管理员", "old_permissions": [...], "new_permissions": [...]}
    
    # 操作摘要（便于快速查看）
    summary = db.Column(db.String(500), nullable=True, comment='操作摘要')

    # 索引
    __table_args__ = (
        db.Index('idx_uor_target_user_id', 'target_user_id'),
        db.Index('idx_uor_operation_type', 'operation_type'),
        db.Index('idx_uor_operation_time', 'operation_time'),
        db.Index('idx_uor_target_user_time', 'target_user_id', 'operation_time'),
    )

    def __repr__(self):
        return f"<UserOperationRecord target_user={self.target_user_id} type={self.operation_type}>"

    @classmethod
    def create_record(cls, target_user_id, operation_type, operator_id=None,
                      operator_name=None, change_detail=None, summary=None):
        """创建操作记录"""
        import json
        record = cls(
            target_user_id=target_user_id,
            operation_type=operation_type,
            operator_id=operator_id,
            operator_name=operator_name,
            change_detail=json.dumps(change_detail, ensure_ascii=False) if isinstance(change_detail, (dict, list)) else change_detail,
            summary=summary
        )
        db.session.add(record)
        # 注意：不在这里commit，由调用方统一commit
        return record