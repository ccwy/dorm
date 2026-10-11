from datetime import datetime
from utils.db import db
import logging

class RoomItemAssignment(db.Model):
    """物品分配记录模型"""
    __tablename__ = 'room_item_assignments'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('room_items.id', ondelete='CASCADE'), nullable=False, comment='关联的物品ID')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False, comment='分配给的用户ID')
    quantity = db.Column(db.Integer, default=1, nullable=False, comment='分配数量')
    status = db.Column(db.String(20), default='active', nullable=False, comment='状态：active/returned/damaged/lost/scrapped')
    dorm_id = db.Column(db.Integer, db.ForeignKey('dorms.id', ondelete='SET NULL'), nullable=True, comment='关联的住宿分配记录ID')
    assigned_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='分配时间')
    returned_at = db.Column(db.DateTime, nullable=True, comment='归还时间')
    remarks = db.Column(db.String(500), nullable=True, comment='备注')

    # 关系
    user = db.relationship('User', foreign_keys=[user_id])
    dorm = db.relationship('Dorm', foreign_keys=[dorm_id])

    # 索引和约束
    __table_args__ = (
        db.Index('idx_item_assignment_item_id', 'item_id'),
        db.Index('idx_item_assignment_user_id', 'user_id'),
        db.Index('idx_item_assignment_status', 'status'),
        db.Index('ix_assignment_item_user_status', 'item_id', 'user_id', 'status'),
        db.CheckConstraint('quantity > 0', name='check_assign_qty_positive'),
        db.CheckConstraint("status IN ('active', 'returned', 'damaged', 'lost', 'scrapped')", name='check_assign_status_valid'),
    )

    STATUS_MAP = {'active': '持有中', 'returned': '已归还', 'damaged': '已损坏', 'lost': '已丢失', 'scrapped': '已报废'}

    @classmethod
    def create_assignment(cls, item_id, user_id, quantity=1, dorm_id=None, remarks=None):
        """创建分配记录"""
        # 验证item_id对应的RoomItem存在
        from models.room.room_item import RoomItem
        item = RoomItem.query.get(item_id)
        if not item:
            raise ValueError(f'物品ID {item_id} 不存在')

        # 验证user_id存在性
        from models.user.user import User
        user = User.query.get(user_id)
        if not user:
            raise ValueError(f'用户ID {user_id} 不存在')

        # 验证可用数量是否足够
        if item.available_quantity < quantity:
            raise ValueError(f'物品可用数量不足，当前可用: {item.available_quantity}，需要: {quantity}')

        # 扣减可用数量
        item.available_quantity -= quantity

        assignment = cls(
            item_id=item_id, user_id=user_id, quantity=quantity,
            dorm_id=dorm_id, remarks=remarks
        )
        db.session.add(assignment)
        logging.info(f"分配物品: 物品ID={item_id}, 用户ID={user_id}, 数量={quantity}")
        return assignment

    def __repr__(self):
        return f"<RoomItemAssignment item_id={self.item_id} user_id={self.user_id} qty={self.quantity} status={self.status}>"