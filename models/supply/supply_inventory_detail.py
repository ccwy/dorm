from datetime import datetime
from utils.db import db


class SupplyInventoryDetail(db.Model):
    """盘点明细表（复刻固定资产盘点方式）"""
    __tablename__ = 'supply_inventory_details'

    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    inventory_id = db.Column(db.Integer, db.ForeignKey('supply_inventories.id', ondelete='CASCADE'), nullable=False, comment='盘点主表ID')

    # 物品关联
    item_id = db.Column(db.Integer, db.ForeignKey('supply_items.id', ondelete='CASCADE'), nullable=False, comment='物品ID')

    # 存放位置
    location_id = db.Column(db.Integer, db.ForeignKey('storage_locations.id', ondelete='CASCADE'), nullable=False, comment='盘点存放位置ID')

    # 盘点结果
    inventory_result = db.Column(db.String(20), default='未盘点', comment='盘点结果：正常/异常/未盘点')
    inventory_remark = db.Column(db.Text, nullable=True, comment='盘点备注')

    # 盘点数量（实盘数量）
    actual_quantity = db.Column(db.Integer, nullable=True, comment='实盘数量')

    # 系统数量（创建盘点时的快照）
    system_quantity = db.Column(db.Integer, nullable=False, default=0, comment='系统数量（盘点时的账面库存）')

    # 价格信息（用于盘点完成时计算差异金额）
    unit_price = db.Column(db.Numeric(10, 2), default=0, nullable=False, comment='单价')

    # 盘点人信息
    checked_by = db.Column(db.String(50), nullable=True, comment='盘点人')
    checked_at = db.Column(db.DateTime, nullable=True, comment='盘点时间')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 约束与索引
    __table_args__ = (
        db.UniqueConstraint('inventory_id', 'item_id', 'location_id', name='unique_supply_inventory_item_location'),
        db.CheckConstraint(
            "inventory_result IN ('正常', '异常', '未盘点')",
            name='check_supply_inventory_detail_result_valid'
        ),
        db.CheckConstraint(
            "system_quantity >= 0",
            name='check_supply_inventory_detail_system_qty_non_negative'
        ),
        db.Index('idx_sinvd_inventory_id', 'inventory_id'),
        db.Index('idx_sinvd_item_id', 'item_id'),
        db.Index('idx_sinvd_location_id', 'location_id'),
        db.Index('idx_sinvd_result', 'inventory_result'),
    )

    def __repr__(self):
        return f"<SupplyInventoryDetail inventory={self.inventory_id} item={self.item_id} result={self.inventory_result}>"

    @property
    def difference_quantity(self):
        """计算差异数量（实盘-系统）"""
        if self.actual_quantity is not None:
            return self.actual_quantity - self.system_quantity
        return 0

    @property
    def difference_amount(self):
        """计算差异金额"""
        return self.difference_quantity * self.unit_price

    @property
    def is_matched(self):
        """是否账实相符"""
        return self.difference_quantity == 0

    @property
    def item_name(self):
        """返回物品名称"""
        if self.item_id:
            from models.supply.supply_item import SupplyItem
            item = SupplyItem.query.get(self.item_id)
            return item.name if item else '未知'
        return '未知'

    @property
    def specification(self):
        """返回规格型号"""
        if self.item_id:
            from models.supply.supply_item import SupplyItem
            item = SupplyItem.query.get(self.item_id)
            return item.specification if item and item.specification else ''
        return ''

    @property
    def unit(self):
        """返回计量单位"""
        if self.item_id:
            from models.supply.supply_item import SupplyItem
            item = SupplyItem.query.get(self.item_id)
            return item.unit if item and item.unit else ''
        return ''

    @property
    def location_name(self):
        """返回存放位置名称"""
        if self.location_id:
            from models.supply.storage_location import StorageLocation
            location = StorageLocation.query.get(self.location_id)
            return location.name if location else '未知'
        return '未知'

    @classmethod
    def get_by_inventory(cls, inventory_id):
        """获取盘点单的所有明细"""
        return cls.query.filter_by(inventory_id=inventory_id).order_by(cls.id).all()

    @classmethod
    def get_difference_details(cls, inventory_id):
        """获取有差异的盘点明细"""
        return cls.query.filter(
            cls.inventory_id == inventory_id,
            cls.actual_quantity != cls.system_quantity
        ).order_by(cls.id).all()