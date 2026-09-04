from datetime import datetime
from utils.db import db


class AssetInventoryDetail(db.Model):
    """资产盘点明细表 - 按库存明细(stock_item)维度记录，同一资产不同位置各一条"""
    __tablename__ = 'asset_inventory_details'

    id = db.Column(db.Integer, primary_key=True)
    inventory_id = db.Column(db.Integer, db.ForeignKey('asset_inventories.id', ondelete='CASCADE'), nullable=False, comment='盘点主表ID')
    asset_id = db.Column(db.Integer, db.ForeignKey('fixed_assets.id', ondelete='CASCADE'), nullable=False, comment='资产ID')
    stock_item_id = db.Column(db.Integer, db.ForeignKey('asset_stock_items.id', ondelete='SET NULL'), nullable=True, comment='库存明细ID（关联AssetStockItem）')
    inventory_result = db.Column(db.String(20), default='未盘点', comment='盘点结果：正常/异常/未盘点')
    inventory_remark = db.Column(db.Text, nullable=True, comment='盘点备注')
    actual_quantity = db.Column(db.Integer, nullable=True, comment='实盘数量')
    book_quantity = db.Column(db.Integer, nullable=True, comment='盘点前账面数量（完成盘点时记录，用于反审核回滚）')
    book_status = db.Column(db.String(20), nullable=True, comment='盘点前资产状态（完成盘点时记录，用于反审核回滚）')
    checked_by = db.Column(db.String(50), nullable=True, comment='盘点人')
    checked_at = db.Column(db.DateTime, nullable=True, comment='盘点时间')

    # 位置冗余字段（从AssetStockItem快照，避免关联丢失后无法显示）
    storage_location = db.Column(db.String(500), nullable=True, comment='存放位置')
    room_id = db.Column(db.Integer, nullable=True, comment='关联房间ID')
    company = db.Column(db.String(100), nullable=True, comment='所属公司')
    department_using_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True, comment='使用部门ID')
    department_owning_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True, comment='归属部门ID')
    responsible_person = db.Column(db.String(50), nullable=True, comment='责任人')

    # 关系
    asset = db.relationship('FixedAsset', foreign_keys=[asset_id], backref=db.backref('inventory_details', lazy=True, cascade='all, delete-orphan'))
    stock_item = db.relationship('AssetStockItem', foreign_keys=[stock_item_id], lazy='select')
    dept_using = db.relationship('Department', foreign_keys=[department_using_id], lazy='select')
    dept_owning = db.relationship('Department', foreign_keys=[department_owning_id], lazy='select')

    __table_args__ = (
        db.UniqueConstraint('inventory_id', 'stock_item_id', name='unique_inventory_stock_item'),
        db.Index('idx_aid_inventory_id', 'inventory_id'),
        db.Index('idx_aid_asset_id', 'asset_id'),
        db.Index('idx_aid_stock_item_id', 'stock_item_id'),
        db.Index('idx_aid_result', 'inventory_result'),
    )

    @property
    def department_using(self):
        """返回使用部门名称"""
        if self.dept_using:
            return self.dept_using.name
        return None

    @property
    def department_owning(self):
        """返回归属部门名称"""
        if self.dept_owning:
            return self.dept_owning.name
        return None

    def __repr__(self):
        return f"<AssetInventoryDetail inventory={self.inventory_id} asset={self.asset_id} stock_item={self.stock_item_id}>"