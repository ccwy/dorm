from datetime import datetime
from utils.db import db


class ContractOperationRecord(db.Model):
    """合同操作记录表 - 记录所有创建/编辑/状态变更/附件操作的详细变更"""
    __tablename__ = 'contract_operation_records'

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id', ondelete='CASCADE'), nullable=False, comment='关联合同ID')
    operation_type = db.Column(db.String(20), nullable=False, comment='操作类型：add/edit/delete/status_change/upload_attachment/delete_attachment')
    operator_id = db.Column(db.Integer, nullable=True, comment='操作人ID')
    operator_name = db.Column(db.String(50), nullable=True, comment='操作人姓名')
    operation_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='操作时间')

    # 变更详情（JSON格式，记录变更前后值）
    change_detail = db.Column(db.Text, nullable=True, comment='变更详情（JSON格式）')

    # 操作摘要（便于快速查看）
    summary = db.Column(db.String(500), nullable=True, comment='操作摘要')

    # 索引
    __table_args__ = (
        db.Index('idx_cor_contract_id', 'contract_id'),
        db.Index('idx_cor_operation_type', 'operation_type'),
        db.Index('idx_cor_operation_time', 'operation_time'),
        db.Index('idx_cor_contract_time', 'contract_id', 'operation_time'),
    )

    def __repr__(self):
        return f"<ContractOperationRecord contract={self.contract_id} type={self.operation_type}>"

    @classmethod
    def create_record(cls, contract_id, operation_type, operator_id=None,
                      operator_name=None, change_detail=None, summary=None):
        """创建操作记录"""
        import json
        record = cls(
            contract_id=contract_id,
            operation_type=operation_type,
            operator_id=operator_id,
            operator_name=operator_name,
            change_detail=json.dumps(change_detail, ensure_ascii=False) if isinstance(change_detail, (dict, list)) else change_detail,
            summary=summary
        )
        db.session.add(record)
        db.session.commit()
        return record