from datetime import datetime
from utils.db import db


class StockOutDetail(db.Model):
    """出库明细表"""
    __tablename__ = 'stock_out_details'

    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    stock_out_id = db.Column(db.Integer, db.ForeignKey('stock_outs.id', ondelete='CASCADE'), nullable=False, comment='出库主表ID')

    # 物品关联
    item_id = db.Column(db.Integer, db.ForeignKey('supply_items.id', ondelete='RESTRICT'), nullable=False, comment='物品ID')
    item_name = db.Column(db.String(200), nullable=False, comment='物品名称（冗余存储）')
    specification = db.Column(db.String(200), nullable=True, comment='规格型号（冗余存储）')
    unit = db.Column(db.String(20), nullable=True, comment='计量单位（冗余存储）')

    # 存放位置
    location_id = db.Column(db.Integer, db.ForeignKey('storage_locations.id', ondelete='RESTRICT'), nullable=False, comment='出库存放位置ID')
    location_name = db.Column(db.String(200), nullable=False, comment='存放位置名称（冗余存储）')

    # 数量与价格
    quantity = db.Column(db.Integer, nullable=False, comment='出库数量')
    unit_price = db.Column(db.Numeric(10, 2), default=0, nullable=False, comment='单价')
    total_price = db.Column(db.Numeric(12, 2), default=0, nullable=False, comment='小计金额（数量×单价）')

    # 备注
    remark = db.Column(db.Text, nullable=True, comment='备注信息')

    # 操作用户
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作用户ID')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 约束与索引
    __table_args__ = (
        db.CheckConstraint(
            "quantity > 0",
            name='check_stock_out_detail_quantity_positive'
        ),
        db.CheckConstraint(
            "unit_price >= 0",
            name='check_stock_out_detail_unit_price_non_negative'
        ),
        db.CheckConstraint(
            "total_price >= 0",
            name='check_stock_out_detail_total_price_non_negative'
        ),
        db.Index('idx_sod_stock_out_id', 'stock_out_id'),
        db.Index('idx_sod_item_id', 'item_id'),
        db.Index('idx_sod_location_id', 'location_id'),
    )

    def __repr__(self):
        return f"<StockOutDetail stock_out={self.stock_out_id} item={self.item_name} qty={self.quantity}>"

    @property
    def display_item_number(self):
        """返回物品编号（优先从主表实时查询）"""
        from models.supply.supply_item import SupplyItem
        item = SupplyItem.query.get(self.item_id)
        if item and item.item_number:
            return item.item_number
        return '-'

    @property
    def display_item_name(self):
        """返回物品名称（优先从主表实时查询，冗余字段作为备用）"""
        from models.supply.supply_item import SupplyItem
        item = SupplyItem.query.get(self.item_id)
        if item:
            return item.name
        return self.item_name or '未知'

    @property
    def display_specification(self):
        """返回规格型号（优先从主表实时查询，冗余字段作为备用）"""
        from models.supply.supply_item import SupplyItem
        item = SupplyItem.query.get(self.item_id)
        if item:
            return item.specification or '-'
        return self.specification or '-'

    @property
    def display_unit(self):
        """返回单位（优先从主表实时查询，冗余字段作为备用）"""
        from models.supply.supply_item import SupplyItem
        item = SupplyItem.query.get(self.item_id)
        if item and item.unit:
            return item.unit
        return self.unit or ''

    @property
    def display_location_name(self):
        """返回位置名称（优先从主表实时查询，冗余字段作为备用）"""
        from models.supply.storage_location import StorageLocation
        location = StorageLocation.query.get(self.location_id)
        if location:
            return location.display_name if hasattr(location, 'display_name') else location.name
        return self.location_name or '未知'

    @classmethod
    def create(cls, stock_out_id, item_id, item_name, location_id, location_name,
               quantity, unit_price=0, specification=None, unit=None,
               remark=None, operator_user_id=None):
        """创建出库明细"""
        from decimal import Decimal
        total_price = Decimal(str(quantity)) * Decimal(str(unit_price))
        detail = cls(
            stock_out_id=stock_out_id,
            item_id=item_id,
            item_name=item_name,
            specification=specification,
            unit=unit,
            location_id=location_id,
            location_name=location_name,
            quantity=quantity,
            unit_price=unit_price,
            total_price=total_price,
            remark=remark,
            operator_user_id=operator_user_id
        )
        db.session.add(detail)
        db.session.commit()
        return detail

    @classmethod
    def get_by_stock_out(cls, stock_out_id):
        """获取出库单的所有明细"""
        return cls.query.filter_by(stock_out_id=stock_out_id).order_by(cls.id).all()