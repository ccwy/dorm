from datetime import datetime
from utils.db import db


class SupplyStockDetail(db.Model):
    """库存明细表 - 按物品+存放位置维度记录实时库存数量"""
    __tablename__ = 'supply_stock_details'

    id = db.Column(db.Integer, primary_key=True)

    # 关联字段
    item_id = db.Column(db.Integer, db.ForeignKey('supply_items.id', ondelete='CASCADE'), nullable=False, comment='物品ID')
    location_id = db.Column(db.Integer, db.ForeignKey('storage_locations.id', ondelete='CASCADE'), nullable=False, comment='存放位置ID')

    # 库存数量
    quantity = db.Column(db.Integer, default=0, nullable=False, comment='当前库存数量')

    # 操作用户
    operator_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, comment='操作用户ID')
    operator = db.relationship('User', foreign_keys=[operator_user_id])
    item = db.relationship('SupplyItem', foreign_keys=[item_id], back_populates='stock_details')
    location = db.relationship('StorageLocation', foreign_keys=[location_id], back_populates='stock_details')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 约束与索引
    __table_args__ = (
        db.UniqueConstraint('item_id', 'location_id', name='uq_supply_stock_detail_item_location', comment='同一物品在同一位置唯一'),
        db.CheckConstraint(
            "quantity >= 0",
            name='check_supply_stock_detail_quantity_non_negative'
        ),
        db.Index('idx_ssd_item_id', 'item_id'),
        db.Index('idx_ssd_location_id', 'location_id'),
        db.Index('idx_ssd_quantity', 'quantity'),
        db.Index('idx_ssd_operator_user_id', 'operator_user_id'),
    )

    def __repr__(self):
        return f"<SupplyStockDetail item={self.item_id} location={self.location_id} qty={self.quantity}>"

    @property
    def item_name(self):
        """返回物品名称"""
        from models.supply.supply_item import SupplyItem
        item = SupplyItem.query.get(self.item_id)
        return item.name if item else '未知'

    @property
    def location_name(self):
        """返回位置名称"""
        from models.supply.storage_location import StorageLocation
        location = StorageLocation.query.get(self.location_id)
        return location.name if location else '未知'

    @classmethod
    def get_or_create(cls, item_id, location_id, operator_user_id=None):
        """获取或创建库存明细记录"""
        detail = cls.query.filter_by(item_id=item_id, location_id=location_id).first()
        if not detail:
            detail = cls(
                item_id=item_id,
                location_id=location_id,
                quantity=0,
                operator_user_id=operator_user_id
            )
            db.session.add(detail)
            db.session.flush()
        return detail

    @classmethod
    def add_stock(cls, item_id, location_id, quantity, operator_user_id=None):
        """
        增加库存（入库时调用）
        同时更新 SupplyItem.current_stock 汇总库存
        返回更新后的库存明细记录
        """
        from models.supply.supply_item import SupplyItem

        detail = cls.get_or_create(item_id, location_id, operator_user_id)
        detail.quantity += quantity
        detail.operator_user_id = operator_user_id

        # 同步更新物品汇总库存
        item = SupplyItem.query.get(item_id)
        if item:
            item.current_stock += quantity

        db.session.commit()
        return detail

    @classmethod
    def subtract_stock(cls, item_id, location_id, quantity, operator_user_id=None):
        """
        减少库存（出库时调用）
        同时更新 SupplyItem.current_stock 汇总库存
        如果库存不足，返回None并回滚
        返回更新后的库存明细记录
        """
        from models.supply.supply_item import SupplyItem

        detail = cls.query.filter_by(item_id=item_id, location_id=location_id).first()
        if not detail or detail.quantity < quantity:
            return None  # 库存不足

        detail.quantity -= quantity
        detail.operator_user_id = operator_user_id

        # 同步更新物品汇总库存
        item = SupplyItem.query.get(item_id)
        if item:
            item.current_stock -= quantity

        db.session.commit()
        return detail

    @classmethod
    def adjust_stock(cls, item_id, location_id, new_quantity, operator_user_id=None):
        """
        调整库存到指定数量（盘点时调用）
        同时更新 SupplyItem.current_stock 汇总库存
        返回更新后的库存明细记录
        """
        from models.supply.supply_item import SupplyItem

        detail = cls.get_or_create(item_id, location_id, operator_user_id)
        old_quantity = detail.quantity
        detail.quantity = new_quantity
        detail.operator_user_id = operator_user_id

        # 同步更新物品汇总库存（差值调整）
        item = SupplyItem.query.get(item_id)
        if item:
            item.current_stock += (new_quantity - old_quantity)

        db.session.commit()
        return detail

    @classmethod
    def get_stock_by_item(cls, item_id):
        """获取物品在各存放位置的库存明细列表"""
        return cls.query.filter_by(item_id=item_id).order_by(cls.location_id).all()

    @classmethod
    def get_stock_by_location(cls, location_id):
        """获取存放位置下各物品的库存明细列表"""
        return cls.query.filter_by(location_id=location_id).order_by(cls.item_id).all()

    @classmethod
    def get_all_stock_summary(cls):
        """获取所有物品的库存汇总（物品维度）"""
        from models.supply.supply_item import SupplyItem
        return SupplyItem.query.order_by(SupplyItem.name).all()

    @classmethod
    def get_low_stock_details(cls):
        """获取低于最低库存的物品在各位置的库存明细"""
        from models.supply.supply_item import SupplyItem
        low_items = SupplyItem.get_low_stock_items()
        item_ids = [item.id for item in low_items]
        if not item_ids:
            return []
        return cls.query.filter(cls.item_id.in_(item_ids)).order_by(cls.item_id, cls.location_id).all()