from datetime import datetime
from utils.db import db
import logging

class RoomItemRecord(db.Model):
    """物品操作记录模型"""
    __tablename__ = 'room_item_records'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('room_items.id', ondelete='CASCADE'), nullable=False, comment='关联的物品ID')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, comment='操作涉及的用户ID')
    from_room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='SET NULL'), nullable=True, comment='来源房间ID')
    to_room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='SET NULL'), nullable=True, comment='目标房间ID')
    operation_type = db.Column(db.String(20), nullable=False, comment='操作类型：allocate/return/transfer/damage/loss/scrap/dorm_transfer/dorm_exchange/dorm_checkout')
    quantity = db.Column(db.Integer, nullable=False, comment='操作数量')
    before_quantity = db.Column(db.Integer, nullable=True, comment='操作前可用数量')
    after_quantity = db.Column(db.Integer, nullable=True, comment='操作后可用数量')
    operator_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, comment='操作人ID')
    remarks = db.Column(db.String(500), nullable=True, comment='备注')
    operated_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='操作时间')

    # 关系
    user = db.relationship('User', foreign_keys=[user_id])
    from_room = db.relationship('Room', foreign_keys=[from_room_id])
    to_room = db.relationship('Room', foreign_keys=[to_room_id])
    operator = db.relationship('User', foreign_keys=[operator_id])

    # 索引和约束
    __table_args__ = (
        db.Index('idx_item_record_item_id', 'item_id'),
        db.Index('idx_item_record_user_id', 'user_id'),
        db.Index('idx_item_record_type', 'operation_type'),
        db.Index('idx_item_record_time', 'operated_at'),
        db.CheckConstraint('quantity > 0', name='check_record_qty_positive'),
        db.CheckConstraint("operation_type IN ('allocate', 'return', 'transfer', 'damage', 'loss', 'scrap', 'dorm_transfer', 'dorm_exchange', 'dorm_checkout', 'create', 'edit', 'delete', 'import')", name='check_operation_type_valid'),
    )

    OPERATION_TYPE_MAP = {
        'allocate': '分配', 'return': '归还', 'transfer': '转移',
        'damage': '损坏', 'loss': '丢失', 'scrap': '报废',
        'dorm_transfer': '换宿触发', 'dorm_exchange': '互换触发', 'dorm_checkout': '退宿触发',
        'create': '创建', 'edit': '编辑', 'delete': '删除',
        'import': '导入'
    }

    VALID_OPERATION_TYPES = set(OPERATION_TYPE_MAP.keys())

    @classmethod
    def add_record(cls, item_id, operation_type, quantity, before_quantity=None, after_quantity=None,
                   user_id=None, from_room_id=None, to_room_id=None, operator_id=None, remarks=None):
        """添加操作记录"""
        # 输入验证
        if operation_type not in cls.VALID_OPERATION_TYPES:
            raise ValueError(f'无效的操作类型: {operation_type}，有效值为: {", ".join(cls.VALID_OPERATION_TYPES)}')
        if quantity <= 0:
            raise ValueError('操作数量必须大于0')

        record = cls(
            item_id=item_id, operation_type=operation_type, quantity=quantity,
            before_quantity=before_quantity, after_quantity=after_quantity,
            user_id=user_id, from_room_id=from_room_id, to_room_id=to_room_id,
            operator_id=operator_id, remarks=remarks
        )
        db.session.add(record)
        logging.info(f"物品操作记录: 物品ID={item_id}, 类型={operation_type}, 数量={quantity}")
        return record

    def __repr__(self):
        return f"<RoomItemRecord item_id={self.item_id} type={self.operation_type} qty={self.quantity}>"