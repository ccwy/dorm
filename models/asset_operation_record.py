from datetime import datetime
from utils.db import db


class AssetOperationRecord(db.Model):
    """资产操作记录表 - 记录所有增加/修改/转移/盘点操作的详细变更"""
    __tablename__ = 'asset_operation_records'

    id = db.Column(db.Integer, primary_key=True)
    asset_id = db.Column(db.Integer, db.ForeignKey('fixed_assets.id', ondelete='CASCADE'), nullable=False, comment='关联资产ID')
    operation_type = db.Column(db.String(20), nullable=False, comment='操作类型：add/edit/transfer/inventory/scrap/sell/delete')
    operator_id = db.Column(db.Integer, nullable=True, comment='操作人ID')
    operator_name = db.Column(db.String(50), nullable=True, comment='操作人姓名')
    operation_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='操作时间')

    # 变更详情（JSON格式，记录变更前后值）
    change_detail = db.Column(db.Text, nullable=True, comment='变更详情（JSON格式）')
    # 示例: {"field": "status", "old_value": "在用", "new_value": "闲置"}
    # 编辑操作: [{"field": "asset_name", "old": "电脑", "new": "笔记本电脑"}, {"field": "status", "old": "在用", "new": "闲置"}]
    # 转移操作: {"from_location": "A楼", "to_location": "B楼", "from_dept_using": "部门1", "to_dept_using": "部门2", "from_responsible": "张三", "to_responsible": "李四"}
    # 盘点操作: {"inventory_id": 1, "result": "正常", "remark": "盘点确认"}

    # 操作摘要（便于快速查看）
    summary = db.Column(db.String(500), nullable=True, comment='操作摘要')

    # 索引
    __table_args__ = (
        db.Index('idx_aor_asset_id', 'asset_id'),
        db.Index('idx_aor_operation_type', 'operation_type'),
        db.Index('idx_aor_operation_time', 'operation_time'),
        db.Index('idx_aor_asset_time', 'asset_id', 'operation_time'),
    )

    def __repr__(self):
        return f"<AssetOperationRecord asset={self.asset_id} type={self.operation_type}>"

    @classmethod
    def create_record(cls, asset_id, operation_type, operator_id=None,
                      operator_name=None, change_detail=None, summary=None):
        """创建操作记录"""
        import json
        record = cls(
            asset_id=asset_id,
            operation_type=operation_type,
            operator_id=operator_id,
            operator_name=operator_name,
            change_detail=json.dumps(change_detail, ensure_ascii=False) if isinstance(change_detail, (dict, list)) else change_detail,
            summary=summary
        )
        db.session.add(record)
        db.session.commit()
        return record