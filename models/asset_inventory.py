from datetime import datetime
from utils.db import db


class AssetInventory(db.Model):
    """资产盘点主表"""
    __tablename__ = 'asset_inventories'

    id = db.Column(db.Integer, primary_key=True)
    inventory_number = db.Column(db.String(50), unique=True, nullable=False, comment='盘点单号')
    title = db.Column(db.String(255), nullable=False, comment='盘点标题')
    inventory_date = db.Column(db.Date, nullable=False, comment='盘点日期')
    status = db.Column(db.String(20), default='进行中', nullable=False, comment='盘点状态：进行中/已完成/已取消')
    total_count = db.Column(db.Integer, default=0, comment='应盘资产数')
    checked_count = db.Column(db.Integer, default=0, comment='已盘资产数')
    normal_count = db.Column(db.Integer, default=0, comment='正常数')
    abnormal_count = db.Column(db.Integer, default=0, comment='异常数')
    remark = db.Column(db.Text, nullable=True, comment='备注')
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作用户ID')
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 关系
    details = db.relationship('AssetInventoryDetail', backref='inventory', lazy=True, cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('idx_inventory_number', 'inventory_number'),
        db.Index('idx_inventory_status', 'status'),
        db.Index('idx_inventory_date', 'inventory_date'),
    )

    def __repr__(self):
        return f"<AssetInventory {self.inventory_number}: {self.title}>"