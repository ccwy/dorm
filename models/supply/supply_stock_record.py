from datetime import datetime
from utils.db import db


class SupplyStockRecord(db.Model):
    """进出库记录表 - 自动记录所有入库、出库、盘点调整操作"""
    __tablename__ = 'supply_stock_records'

    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    record_type = db.Column(db.String(20), nullable=False, comment='记录类型：入库/出库/盘盈/盘亏')
    record_date = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='记录时间')

    # 物品关联
    item_id = db.Column(db.Integer, db.ForeignKey('supply_items.id', ondelete='CASCADE'), nullable=False, comment='物品ID')
    item_name = db.Column(db.String(200), nullable=False, comment='物品名称（冗余存储）')

    # 存放位置
    location_id = db.Column(db.Integer, db.ForeignKey('storage_locations.id', ondelete='SET NULL'), nullable=True, comment='存放位置ID')
    location_name = db.Column(db.String(200), nullable=True, comment='存放位置名称（冗余存储）')

    # 数量与价格
    quantity = db.Column(db.Integer, nullable=False, comment='变动数量（正数）')
    unit_price = db.Column(db.Numeric(10, 2), default=0, nullable=False, comment='单价')
    total_price = db.Column(db.Numeric(12, 2), default=0, nullable=False, comment='总金额（数量×单价）')

    # 来源单据
    source_number = db.Column(db.String(50), nullable=True, comment='来源单号（入库单号/出库单号/盘点单号）')
    source_type = db.Column(db.String(50), nullable=True, comment='来源类型（采购入库/正常领用/盘点调整等）')

    # 领用人/部门（出库时记录）
    recipient_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, comment='领用人用户ID（出库时记录）')
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id', ondelete='SET NULL'), nullable=True, comment='领用部门ID（出库时记录）')

    # 操作用户
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作用户ID')

    # 备注
    remark = db.Column(db.Text, nullable=True, comment='备注信息')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')

    # 约束与索引
    __table_args__ = (
        db.CheckConstraint(
            "record_type IN ('入库', '出库', '盘盈', '盘亏', '入库反审核', '出库反审核', '盘盈反审核', '盘亏反审核')",
            name='check_supply_stock_record_type_valid'
        ),
        db.CheckConstraint(
            "quantity > 0",
            name='check_supply_stock_record_quantity_positive'
        ),
        db.Index('idx_ssr_record_type', 'record_type'),
        db.Index('idx_ssr_record_date', 'record_date'),
        db.Index('idx_ssr_item_id', 'item_id'),
        db.Index('idx_ssr_location_id', 'location_id'),
        db.Index('idx_ssr_source_number', 'source_number'),
        db.Index('idx_ssr_recipient', 'recipient_user_id'),
        db.Index('idx_ssr_department', 'department_id'),
        db.Index('idx_ssr_item_date', 'item_id', 'record_date'),
        db.Index('idx_ssr_location_date', 'location_id', 'record_date'),
    )

    def __repr__(self):
        return f"<SupplyStockRecord {self.record_type} item={self.item_name} qty={self.quantity}>"

    @property
    def display_item_name(self):
        """返回物品名称（优先从主表实时查询，冗余字段作为备用）"""
        from models.supply.supply_item import SupplyItem
        item = SupplyItem.query.get(self.item_id)
        if item:
            return item.name
        return self.item_name or '未知'

    @property
    def item_number(self):
        """返回物品编号（从关联物品获取）"""
        if self.item_id:
            from models.supply.supply_item import SupplyItem
            item = SupplyItem.query.get(self.item_id)
            return item.item_number if item else None
        return None

    @property
    def display_location_name(self):
        """返回位置名称（优先从主表实时查询，冗余字段作为备用）"""
        if self.location_id:
            from models.supply.storage_location import StorageLocation
            location = StorageLocation.query.get(self.location_id)
            if location:
                return location.display_name if hasattr(location, 'display_name') else location.name
        return self.location_name or '未知'

    @property
    def recipient_name(self):
        """返回领用人姓名"""
        if self.recipient_user_id:
            from models.user import User
            user = User.query.get(self.recipient_user_id)
            return user.name if user else '未知'
        return '无'

    @property
    def department_name(self):
        """返回领用部门名称"""
        if self.department_id:
            from models.department import Department
            dept = Department.query.get(self.department_id)
            return dept.name if dept else '未知'
        return '无'

    @property
    def specification(self):
        """返回物品规格（从关联物品获取）"""
        if self.item_id:
            from models.supply.supply_item import SupplyItem
            item = SupplyItem.query.get(self.item_id)
            return item.specification if item else None
        return None

    @property
    def unit(self):
        """返回物品单位（从关联物品获取）"""
        if self.item_id:
            from models.supply.supply_item import SupplyItem
            item = SupplyItem.query.get(self.item_id)
            return item.unit if item else None
        return None

    @property
    def operator_name(self):
        """返回操作人姓名"""
        if self.operator_user_id:
            from models.user import User
            user = User.query.get(self.operator_user_id)
            return user.name if user else '未知'
        return '系统'

    @property
    def source_url(self):
        """根据来源类型和单号返回对应的详情页URL"""
        if not self.source_number:
            return None

        try:
            if self.record_type in ('入库', '入库反审核'):
                from models.supply.stock_in import StockIn
                record = StockIn.query.filter_by(stock_in_number=self.source_number).first()
                if record:
                    return f'/stock-in/detail/{record.id}'
            elif self.record_type in ('出库', '出库反审核'):
                from models.supply.stock_out import StockOut
                record = StockOut.query.filter_by(stock_out_number=self.source_number).first()
                if record:
                    return f'/stock-out/detail/{record.id}'
            elif self.record_type in ('盘盈', '盘亏', '盘盈反审核', '盘亏反审核'):
                from models.supply.supply_inventory import SupplyInventory
                record = SupplyInventory.query.filter_by(inventory_number=self.source_number).first()
                if record:
                    return f'/supply-inventory/detail/{record.id}'
        except Exception:
            pass

        return None

    @classmethod
    def create_record(cls, record_type, item_id, location_id=None, location_name=None,
                      quantity=0, unit_price=0, source_number=None, source_type=None,
                      operator_user_id=None, recipient_user_id=None, department_id=None,
                      remark=None):
        """创建进出库记录"""
        from models.supply.supply_item import SupplyItem

        # 获取物品名称
        item = SupplyItem.query.get(item_id)
        item_name = item.name if item else '未知'

        # 获取位置名称
        if location_id and not location_name:
            from models.supply.storage_location import StorageLocation
            location = StorageLocation.query.get(location_id)
            location_name = location.name if location else '未知'

        record = cls(
            record_type=record_type,
            item_id=item_id,
            item_name=item_name,
            location_id=location_id,
            location_name=location_name,
            quantity=quantity,
            unit_price=unit_price,
            total_price=quantity * unit_price if unit_price else 0,
            source_number=source_number,
            source_type=source_type,
            operator_user_id=operator_user_id,
            recipient_user_id=recipient_user_id,
            department_id=department_id,
            remark=remark
        )
        db.session.add(record)
        db.session.commit()
        return record

    @classmethod
    def get_by_item(cls, item_id, start_date=None, end_date=None, record_type=None):
        """获取物品的进出库记录"""
        query = cls.query.filter_by(item_id=item_id)
        if start_date:
            query = query.filter(cls.record_date >= start_date)
        if end_date:
            query = query.filter(cls.record_date <= end_date)
        if record_type:
            query = query.filter_by(record_type=record_type)
        return query.order_by(cls.record_date.desc()).all()

    @classmethod
    def get_by_location(cls, location_id, start_date=None, end_date=None):
        """获取存放位置的进出库记录"""
        query = cls.query.filter_by(location_id=location_id)
        if start_date:
            query = query.filter(cls.record_date >= start_date)
        if end_date:
            query = query.filter(cls.record_date <= end_date)
        return query.order_by(cls.record_date.desc()).all()

    @classmethod
    def get_by_department(cls, department_id, start_date=None, end_date=None):
        """获取部门的领用记录"""
        query = cls.query.filter_by(department_id=department_id, record_type='出库')
        if start_date:
            query = query.filter(cls.record_date >= start_date)
        if end_date:
            query = query.filter(cls.record_date <= end_date)
        return query.order_by(cls.record_date.desc()).all()

    @classmethod
    def get_by_recipient(cls, recipient_user_id, start_date=None, end_date=None):
        """获取领用人的领用记录"""
        query = cls.query.filter_by(recipient_user_id=recipient_user_id, record_type='出库')
        if start_date:
            query = query.filter(cls.record_date >= start_date)
        if end_date:
            query = query.filter(cls.record_date <= end_date)
        return query.order_by(cls.record_date.desc()).all()

    @classmethod
    def get_statistics(cls, start_date=None, end_date=None):
        """获取进出库统计汇总"""
        from sqlalchemy import func

        query = db.session.query(
            cls.record_type,
            func.count(cls.id).label('count'),
            func.sum(cls.quantity).label('total_quantity'),
            func.sum(cls.total_price).label('total_amount')
        )

        if start_date:
            query = query.filter(cls.record_date >= start_date)
        if end_date:
            query = query.filter(cls.record_date <= end_date)

        return query.group_by(cls.record_type).all()