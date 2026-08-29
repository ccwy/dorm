from datetime import datetime
from utils.db import db


class StorageLocation(db.Model):
    """存放位置表"""
    __tablename__ = 'storage_locations'

    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, comment='位置名称')
    code = db.Column(db.String(50), nullable=True, comment='位置编码')
    building = db.Column(db.String(100), nullable=True, comment='楼栋')
    floor = db.Column(db.String(50), nullable=True, comment='楼层')
    room = db.Column(db.String(100), nullable=True, comment='房间号')
    address = db.Column(db.String(500), nullable=True, comment='地址')

    # 状态与关联
    status = db.Column(db.String(20), default='启用', nullable=False, comment='状态：启用/停用')
    handler_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, comment='经手人用户ID')

    # 备注
    remark = db.Column(db.Text, nullable=True, comment='备注信息')

    # 操作用户
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作用户ID')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 关系定义
    stock_details = db.relationship('SupplyStockDetail', back_populates='location', lazy=True, cascade='all, delete-orphan')
    stock_records = db.relationship('SupplyStockRecord', backref='storage_location', lazy=True)

    # 约束与索引
    __table_args__ = (
        db.UniqueConstraint('name', name='uq_storage_location_name', comment='位置名称唯一'),
        db.CheckConstraint(
            "status IN ('启用', '停用')",
            name='check_storage_location_status_valid'
        ),
        db.Index('idx_sl_name', 'name'),
        db.Index('idx_sl_code', 'code'),
        db.Index('idx_sl_status', 'status'),
        db.Index('idx_sl_handler', 'handler_user_id'),
    )

    def __repr__(self):
        return f"<StorageLocation {self.name}>"

    @property
    def display_name(self):
        """返回完整位置名称（楼栋+楼层+房间+名称）"""
        parts = []
        if self.building:
            parts.append(self.building)
        if self.floor:
            parts.append(f'{self.floor}层')
        if self.room:
            parts.append(self.room)
        parts.append(self.name)
        return '-'.join(parts)

    @property
    def display_status(self):
        """返回状态显示文本"""
        return self.status

    @property
    def handler_name(self):
        """返回经手人姓名"""
        if self.handler_user_id:
            from models.user import User
            user = User.query.get(self.handler_user_id)
            return user.name if user else '未知'
        return '未指定'

    @classmethod
    def create(cls, name, code=None, building=None, floor=None, room=None, address=None,
               status='启用', handler_user_id=None, remark=None, operator_user_id=None):
        """创建存放位置"""
        location = cls(
            name=name,
            code=code,
            building=building,
            floor=floor,
            room=room,
            address=address,
            status=status,
            handler_user_id=handler_user_id,
            remark=remark,
            operator_user_id=operator_user_id
        )
        db.session.add(location)
        db.session.commit()
        return location

    @classmethod
    def is_name_exists(cls, name, exclude_id=None):
        """检查位置名称是否已存在"""
        query = cls.query.filter_by(name=name)
        if exclude_id:
            query = query.filter(cls.id != exclude_id)
        return query.first() is not None

    @classmethod
    def check_usage(cls, location_id):
        """
        检查存放位置是否被使用，返回使用详情
        """
        from models.supply.supply_stock_detail import SupplyStockDetail
        from models.supply.supply_stock_record import SupplyStockRecord

        # 检查库存明细
        stock_count = SupplyStockDetail.query.filter_by(location_id=location_id).count()
        # 检查进出库记录
        record_count = SupplyStockRecord.query.filter_by(location_id=location_id).count()

        used = stock_count > 0 or record_count > 0

        return {
            'used': used,
            'details': {
                'stock_detail_count': stock_count,
                'stock_record_count': record_count
            }
        }

    @classmethod
    def get_active_locations(cls):
        """获取所有启用的存放位置列表"""
        return cls.query.filter_by(status='启用').order_by(cls.name).all()

    @classmethod
    def get_all_names(cls):
        """获取所有位置名称列表"""
        locations = cls.query.order_by(cls.name).all()
        return [loc.name for loc in locations]