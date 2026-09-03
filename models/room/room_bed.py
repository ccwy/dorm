from utils.db import db
from datetime import datetime
import enum

class BedStatus(str, enum.Enum):
    """床位状态枚举"""
    AVAILABLE = "available"  # 可用（未分配）
    OCCUPIED = "occupied"    # 已占用（有人使用）
    MAINTENANCE = "maintenance"  # 维护中（如损坏）
    CLOSED = "closed"    # 已关闭

class Bed(db.Model):
    """床位模型（与房间关联，后端自动分配）"""
    __tablename__ = 'room_beds'
    
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='CASCADE'), nullable=False, comment='关联的房间ID')
    bed_number = db.Column(db.String(10), nullable=False, comment='床位号（如1、2、A、B等，后端自动生成）')
    status = db.Column(db.String(20), default=BedStatus.AVAILABLE.value, nullable=False, comment=f'床位状态：{[s.value for s in BedStatus]}')
    remark = db.Column(db.String(200), default="", nullable=True, comment='床位备注（如靠窗、上铺等）')
    
    # 时间字段
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间（床位生成时间）')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间（状态变更时间）')
    
    # 约束：同一房间内床位号唯一
    __table_args__ = (
        db.UniqueConstraint('room_id', 'bed_number', name='unique_room_bed_number'),
        db.CheckConstraint(
            f"status IN ('{BedStatus.AVAILABLE.value}', '{BedStatus.OCCUPIED.value}', "
            f"'{BedStatus.MAINTENANCE.value}', '{BedStatus.CLOSED.value}')",  # 状态值与枚举一致
            name='check_bed_status_valid'
        ),
        db.Index('idx_bed_room_id', 'room_id'),
        db.Index('idx_bed_status', 'status')
    )
    
    def __repr__(self):
        return f"<Bed {self.room.building}-{self.room.room_number}-{self.bed_number}>"
    
    @property
    def full_identifier(self):
        """返回完整床位标识（如：A栋-101-1）"""
        return f"{self.room.building}-{self.room.room_number}-{self.bed_number}"
    
    @property
    def status_display(self):
        """返回床位状态的中文显示文本"""
        status_map = {
            BedStatus.AVAILABLE.value: "可用",
            BedStatus.OCCUPIED.value: "已占用",
            BedStatus.MAINTENANCE.value: "维护中",
            BedStatus.CLOSED.value: "已关闭"
        }
        return status_map.get(self.status, self.status)
