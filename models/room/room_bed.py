from utils.db import db
from datetime import datetime
import enum
import logging

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

    @classmethod
    def get_available_beds(cls, room_id):
        """查询指定房间的可用床位列表（带行锁防止并发问题）"""
        return cls.query.filter_by(
            room_id=room_id,
            status=BedStatus.AVAILABLE.value
        ).with_for_update().all()

    @classmethod
    def find_and_occupy(cls, room_id, bed_id=None):
        """查找并占用一个床位
        
        Args:
            room_id: 房间ID
            bed_id: 指定床位ID，为None时自动分配第一个可用床位
        
        Returns:
            Bed对象（成功）或 None（失败或床位管理禁用）
        """
        from models.system_config.system_config import SystemConfig
        
        # 读取床位管理开关配置
        config = SystemConfig.query.filter_by(config_key='ROOM_BED_MANAGEMENT_ENABLED').first()
        enabled = config and config.config_value.lower() == 'true' if config else True
        if not enabled:
            return None
        
        if bed_id is None:
            # 自动分配：取第一个可用床位
            bed = cls.query.filter_by(
                room_id=room_id,
                status=BedStatus.AVAILABLE.value
            ).with_for_update().first()
        else:
            # 手动指定：验证room_id匹配且status可用
            bed = cls.query.filter_by(
                id=bed_id,
                room_id=room_id,
                status=BedStatus.AVAILABLE.value
            ).with_for_update().first()
        
        if not bed:
            logging.warning(f"未找到可用床位: room_id={room_id}, bed_id={bed_id}")
            return None
        
        bed.status = BedStatus.OCCUPIED.value
        return bed

    def release(self):
        """释放床位，标记为可用状态"""
        from models.system_config.system_config import SystemConfig
        
        # 读取床位管理开关配置
        config = SystemConfig.query.filter_by(config_key='ROOM_BED_MANAGEMENT_ENABLED').first()
        enabled = config and config.config_value.lower() == 'true' if config else True
        if not enabled:
            return self
        
        self.status = BedStatus.AVAILABLE.value
        return self

    @classmethod
    def reconcile_beds_for_room(cls, room_id):
        """为指定房间中bed_id=None的活跃Dorm记录补分配床位。
        
        当床位管理从禁用切换为启用时，之前分配的宿舍记录没有bed_id关联，
        此方法为这些记录自动分配可用床位。
        
        Args:
            room_id: 房间ID
            
        Returns:
            int: 成功补分配的记录数
        """
        from models.dorm.dorm import Dorm
        from models.system_config.system_config import SystemConfig
        
        # 仅在床位管理启用时执行
        config = SystemConfig.query.filter_by(config_key='ROOM_BED_MANAGEMENT_ENABLED').first()
        if not config or not (config.config_value.lower() == 'true'):
            return 0
        
        # 查找该房间中bed_id=None的活跃Dorm记录
        orphan_dorms = Dorm.query.filter_by(
            room_id=room_id,
            bed_id=None,
            check_out_date=None
        ).all()
        
        if not orphan_dorms:
            return 0
        
        reconciled = 0
        for dorm in orphan_dorms:
            # 为该用户在同一房间内自动分配可用床位
            bed = cls.find_and_occupy(room_id, bed_id=None)
            if bed:
                dorm.bed_id = bed.id
                reconciled += 1
                logging.info(f"床位补分配: 用户{dorm.user_id}在房间{room_id}分配到床位{bed.id}")
            else:
                logging.warning(f"床位补分配失败: 房间{room_id}无可用床位，用户{dorm.user_id}无法分配")
                break  # 无可用床位，停止分配
        
        if reconciled > 0:
            from utils.db import db
            db.session.commit()
        
        return reconciled

    @classmethod
    def reconcile_all_rooms(cls):
        """为所有房间执行床位补分配。
        
        Returns:
            int: 总成功补分配数
        """
        from models.room.room import Room
        
        rooms = Room.query.all()
        total = 0
        for room in rooms:
            total += cls.reconcile_beds_for_room(room.id)
        
        if total > 0:
            logging.info(f"全局床位补分配完成，共处理{total}条记录")
        
        return total
