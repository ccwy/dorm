from datetime import datetime
from utils.db import db
import logging

class RoomItem(db.Model):
    """房间物品模型"""
    __tablename__ = 'room_items'

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='CASCADE'), nullable=False, comment='关联的房间ID')
    name = db.Column(db.String(100), nullable=False, comment='物品名称')
    item_code = db.Column(db.String(50), nullable=False, comment='物品编号（自动生成，如WP2026100001）')
    specification = db.Column(db.String(200), nullable=True, comment='物品规格')
    unit = db.Column(db.String(20), nullable=True, comment='物品单位')
    item_type = db.Column(db.String(20), nullable=False, comment='物品类型：room_bound(房间绑定)/transferable(可转移)')
    total_quantity = db.Column(db.Integer, default=1, nullable=False, comment='总数量')
    available_quantity = db.Column(db.Integer, default=1, nullable=False, comment='可用数量')
    damaged_quantity = db.Column(db.Integer, default=0, nullable=False, comment='损坏数量')
    lost_quantity = db.Column(db.Integer, default=0, nullable=False, comment='丢失数量')
    scrapped_quantity = db.Column(db.Integer, default=0, nullable=False, comment='报废数量')
    status = db.Column(db.String(20), default='正常', nullable=False, comment='物品状态：正常/损坏/丢失/报废')
    remark = db.Column(db.String(500), nullable=True, comment='备注')
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 关系
    room = db.relationship('Room', backref=db.backref('room_items', lazy='dynamic', cascade='all, delete-orphan'))
    records = db.relationship('RoomItemRecord', backref='item', lazy='dynamic', cascade='all, delete-orphan')
    assignments = db.relationship('RoomItemAssignment', backref='item', lazy='dynamic', cascade='all, delete-orphan')

    # 索引和约束
    __table_args__ = (
        db.Index('idx_room_item_room_id', 'room_id'),
        db.Index('idx_room_item_status', 'status'),
        db.CheckConstraint('total_quantity >= 0', name='check_room_item_total_qty_nonneg'),
        db.CheckConstraint('available_quantity >= 0', name='check_room_item_avail_qty_nonneg'),
        db.CheckConstraint('available_quantity <= total_quantity', name='check_room_item_avail_le_total'),
        db.CheckConstraint('damaged_quantity >= 0', name='check_room_item_damaged_qty_nonneg'),
        db.CheckConstraint('lost_quantity >= 0', name='check_room_item_lost_qty_nonneg'),
        db.CheckConstraint('scrapped_quantity >= 0', name='check_room_item_scrapped_qty_nonneg'),
        db.CheckConstraint("item_type IN ('room_bound', 'transferable')", name='check_room_item_type_valid'),
        db.CheckConstraint("status IN ('正常', '损坏', '丢失', '报废')", name='check_room_item_status_valid'),
    )

    ITEM_TYPE_MAP = {'room_bound': '房间绑定', 'transferable': '可转移'}
    STATUS_MAP = {'正常': '正常', '损坏': '损坏', '丢失': '丢失', '报废': '报废'}

    VALID_ITEM_TYPES = {'room_bound', 'transferable'}
    VALID_STATUSES = {'正常', '损坏', '丢失', '报废'}

    @classmethod
    def validate_status(cls, status):
        """验证状态值是否合法"""
        if status not in cls.VALID_STATUSES:
            raise ValueError(f'无效的物品状态: {status}，有效值为: {", ".join(cls.VALID_STATUSES)}')
        return status

    @classmethod
    def generate_item_code(cls):
        """生成物品编号：WP+年月+4位序号"""
        prefix = 'WP' + datetime.now().strftime('%Y%m')
        last_item = cls.query.filter(cls.item_code.like(prefix + '%')).order_by(cls.item_code.desc()).first()
        if last_item:
            try:
                seq = int(last_item.item_code[len(prefix):]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f'{prefix}{seq:04d}'

    @classmethod
    def create_item(cls, room_id, name, item_type, total_quantity=1, specification=None, unit=None, remark=None):
        """创建物品"""
        # 输入验证
        if not name or not name.strip():
            raise ValueError('物品名称不能为空')
        if item_type not in cls.VALID_ITEM_TYPES:
            raise ValueError(f'无效的物品类型: {item_type}，有效值为: {", ".join(cls.VALID_ITEM_TYPES)}')
        if total_quantity < 1:
            raise ValueError('物品总数量必须大于0')
        # 验证room_id存在性
        from models.room.room import Room
        room = Room.query.get(room_id)
        if not room:
            raise ValueError(f'房间ID {room_id} 不存在')

        # 查询是否已存在同种物品（名称、规格、单位、类型一致），复用其编号
        existing = cls.query.filter_by(
            name=name.strip(),
            specification=specification or None,
            unit=unit or None,
            item_type=item_type
        ).first()
        item_code = existing.item_code if existing else cls.generate_item_code()

        item = cls(
            room_id=room_id,
            name=name.strip(),
            item_code=item_code,
            specification=specification,
            unit=unit,
            item_type=item_type,
            total_quantity=total_quantity,
            available_quantity=total_quantity,
            damaged_quantity=0,
            lost_quantity=0,
            scrapped_quantity=0,
            remark=remark
        )
        db.session.add(item)
        logging.info(f"创建房间物品: 房间ID={room_id}, 编号={item.item_code}, 名称={name}, 类型={item_type}, 数量={total_quantity}")
        return item

    def __repr__(self):
        return f"<RoomItem {self.item_code} {self.name} 房间{self.room_id}>"