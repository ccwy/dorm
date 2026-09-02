from datetime import datetime
from utils.db import db


class AssetInventoryDetail(db.Model):
    """资产盘点明细表"""
    __tablename__ = 'asset_inventory_details'

    id = db.Column(db.Integer, primary_key=True)
    inventory_id = db.Column(db.Integer, db.ForeignKey('asset_inventories.id', ondelete='CASCADE'), nullable=False, comment='盘点主表ID')
    asset_id = db.Column(db.Integer, db.ForeignKey('fixed_assets.id', ondelete='CASCADE'), nullable=False, comment='资产ID')
    inventory_result = db.Column(db.String(20), default='未盘点', comment='盘点结果：正常/异常/未盘点')
    inventory_remark = db.Column(db.Text, nullable=True, comment='盘点备注')
    actual_quantity = db.Column(db.Integer, nullable=True, comment='实盘数量')
    book_quantity = db.Column(db.Integer, nullable=True, comment='盘点前账面数量（完成盘点时记录，用于反审核回滚）')
    book_status = db.Column(db.String(20), nullable=True, comment='盘点前资产状态（完成盘点时记录，用于反审核回滚）')
    checked_by = db.Column(db.String(50), nullable=True, comment='盘点人')
    checked_at = db.Column(db.DateTime, nullable=True, comment='盘点时间')

    __table_args__ = (
        db.UniqueConstraint('inventory_id', 'asset_id', name='unique_inventory_asset'),
        db.Index('idx_aid_inventory_id', 'inventory_id'),
        db.Index('idx_aid_asset_id', 'asset_id'),
        db.Index('idx_aid_result', 'inventory_result'),
    )

    def __repr__(self):
        return f"<AssetInventoryDetail inventory={self.inventory_id} asset={self.asset_id}>"