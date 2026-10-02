from utils.db import db
from datetime import datetime


class DormOperation(db.Model):
    """宿舍操作记录子模型 — 每次操作一条记录，不可变"""
    __tablename__ = 'dorm_operations'

    id = db.Column(db.Integer, primary_key=True)
    dorm_id = db.Column(db.Integer, db.ForeignKey('dorms.id', ondelete='CASCADE'), nullable=False, comment='关联的住宿记录ID')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False, comment='被操作人员ID')

    # 操作类型：allocation(分配入住)/transfer(换宿)/exchange(互换)/checkout(退宿)
    operation_type = db.Column(db.String(20), nullable=False, comment='操作类型')

    # 房间信息快照
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='SET NULL'), nullable=True, comment='目标房间ID（分配/换入的房间）')
    from_room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='SET NULL'), nullable=True, comment='来源房间ID（换宿/互换的原房间，分配时为空）')
    bed_id = db.Column(db.Integer, db.ForeignKey('room_beds.id', ondelete='SET NULL'), nullable=True, comment='目标床位ID')
    from_bed_id = db.Column(db.Integer, db.ForeignKey('room_beds.id', ondelete='SET NULL'), nullable=True, comment='来源床位ID')

    # 操作人
    operator_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, comment='操作用户ID（办理人）')

    # 互换对方（仅互换操作有值）
    swap_with_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, comment='互换对方用户ID（仅互换操作）')

    # 时间
    operated_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='操作时间')

    # 备注
    remarks = db.Column(db.String(500), nullable=True, comment='操作备注')

    # 关系
    dorm = db.relationship('Dorm', backref=db.backref('operations', lazy='dynamic'))
    user = db.relationship('User', foreign_keys=[user_id])
    room = db.relationship('Room', foreign_keys=[room_id])
    from_room = db.relationship('Room', foreign_keys=[from_room_id])
    operator = db.relationship('User', foreign_keys=[operator_user_id])

    # 索引
    __table_args__ = (
        db.Index('idx_dorm_op_dorm_id', 'dorm_id'),
        db.Index('idx_dorm_op_user_id', 'user_id'),
        db.Index('idx_dorm_op_type', 'operation_type'),
        db.Index('idx_dorm_op_time', 'operated_at'),
        db.Index('idx_dorm_op_room', 'room_id'),
    )

    # 操作类型中文映射
    OPERATION_TYPE_TEXT = {
        'allocation': '分配入住',
        'transfer': '换宿',
        'exchange': '互换',
        'checkout': '退宿',
    }

    @property
    def operation_type_text(self):
        """返回操作类型的中文描述"""
        return self.OPERATION_TYPE_TEXT.get(self.operation_type, self.operation_type)

    def __repr__(self):
        return f"<DormOperation {self.operation_type} user={self.user_id} room={self.room_id}>"