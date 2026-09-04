from datetime import datetime
from utils.db import db


class AssetStockItem(db.Model):
    """资产库存明细表 - 按资产+存放位置维度记录实时库存数量"""
    __tablename__ = 'asset_stock_items'

    id = db.Column(db.Integer, primary_key=True)

    # 关联字段
    asset_id = db.Column(db.Integer, db.ForeignKey('fixed_assets.id', ondelete='CASCADE'), nullable=False, comment='关联资产ID')

    # 位置信息（与主表字段一致，每条记录代表一个位置的数量）
    storage_location = db.Column(db.String(500), nullable=True, comment='存放位置（自由输入）')
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=True, comment='关联房间ID')
    company = db.Column(db.String(100), nullable=True, comment='所属公司')
    department_using_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True, comment='使用部门ID')
    department_owning_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True, comment='归属部门ID')
    responsible_person = db.Column(db.String(50), nullable=True, comment='责任人')
    responsible_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, comment='责任人用户ID')

    # 库存数量
    quantity = db.Column(db.Integer, default=0, nullable=False, comment='该位置当前数量')

    # 操作用户
    operator_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, comment='操作用户ID')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 关系定义
    asset = db.relationship('FixedAsset', foreign_keys=[asset_id], backref=db.backref('stock_items', lazy=True, cascade='all, delete-orphan'))
    room = db.relationship('Room', foreign_keys=[room_id], lazy='select')
    responsible_user = db.relationship('User', foreign_keys=[responsible_user_id], lazy='select')
    dept_using = db.relationship('Department', foreign_keys=[department_using_id], backref='asset_stock_items_using_lazy', lazy='select')
    dept_owning = db.relationship('Department', foreign_keys=[department_owning_id], backref='asset_stock_items_owning_lazy', lazy='select')

    # 约束与索引
    __table_args__ = (
        # 同一资产在同一位置（storage_location + room_id组合）唯一
        db.UniqueConstraint('asset_id', 'storage_location', 'room_id',
                            name='uq_asset_stock_item_asset_location',
                            comment='同一资产在同一位置唯一'),
        db.CheckConstraint(
            'quantity >= 0',
            name='check_asset_stock_item_quantity_non_negative'
        ),
        db.Index('idx_asi_asset_id', 'asset_id'),
        db.Index('idx_asi_storage_location', 'storage_location'),
        db.Index('idx_asi_room_id', 'room_id'),
        db.Index('idx_asi_dept_using_id', 'department_using_id'),
        db.Index('idx_asi_dept_owning_id', 'department_owning_id'),
        db.Index('idx_asi_responsible_user_id', 'responsible_user_id'),
        db.Index('idx_asi_company', 'company'),
    )

    def __repr__(self):
        return f"<AssetStockItem asset={self.asset_id} location={self.storage_location} qty={self.quantity}>"

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

    @property
    def room_display(self):
        """返回楼栋+房间号"""
        if self.room:
            return f"{self.room.building}{self.room.room_number}"
        return None

    @property
    def responsible_user_name(self):
        """返回责任人姓名"""
        if self.responsible_user:
            return self.responsible_user.name
        return None

    @classmethod
    def get_or_create(cls, asset_id, storage_location=None, room_id=None,
                      company=None, department_using_id=None, department_owning_id=None,
                      responsible_person=None, responsible_user_id=None,
                      operator_user_id=None):
        """获取或创建库存明细记录"""
        detail = cls.query.filter_by(
            asset_id=asset_id,
            storage_location=storage_location,
            room_id=room_id
        ).first()
        if not detail:
            detail = cls(
                asset_id=asset_id,
                storage_location=storage_location,
                room_id=room_id,
                company=company,
                department_using_id=department_using_id,
                department_owning_id=department_owning_id,
                responsible_person=responsible_person,
                responsible_user_id=responsible_user_id,
                quantity=0,
                operator_user_id=operator_user_id
            )
            db.session.add(detail)
            db.session.flush()
        return detail

    @classmethod
    def add_stock(cls, asset_id, quantity, storage_location=None, room_id=None,
                  company=None, department_using_id=None, department_owning_id=None,
                  responsible_person=None, responsible_user_id=None,
                  operator_user_id=None):
        """增加库存（入库时调用），返回库存明细记录和库存变动记录"""
        detail = cls.get_or_create(
            asset_id=asset_id,
            storage_location=storage_location,
            room_id=room_id,
            company=company,
            department_using_id=department_using_id,
            department_owning_id=department_owning_id,
            responsible_person=responsible_person,
            responsible_user_id=responsible_user_id,
            operator_user_id=operator_user_id
        )
        detail.quantity += quantity
        detail.operator_user_id = operator_user_id
        detail.updated_at = datetime.now()

        # 同步更新主表quantity
        from models.fixed_asset.fixed_asset import FixedAsset
        asset = FixedAsset.query.get(asset_id)
        if asset:
            asset.quantity = sum(item.quantity for item in asset.stock_items)

        return detail

    @classmethod
    def reduce_stock(cls, asset_id, quantity, storage_location=None, room_id=None,
                     operator_user_id=None):
        """减少库存（出库时调用），返回库存明细记录，库存不足时返回None"""
        detail = cls.query.filter_by(
            asset_id=asset_id,
            storage_location=storage_location,
            room_id=room_id
        ).first()
        if not detail or detail.quantity < quantity:
            return None

        detail.quantity -= quantity
        detail.operator_user_id = operator_user_id
        detail.updated_at = datetime.now()

        # 如果数量为0，删除该条记录
        if detail.quantity <= 0:
            db.session.delete(detail)

        # 同步更新主表quantity
        from models.fixed_asset.fixed_asset import FixedAsset
        asset = FixedAsset.query.get(asset_id)
        if asset:
            asset.quantity = sum(item.quantity for item in asset.stock_items)

        return detail