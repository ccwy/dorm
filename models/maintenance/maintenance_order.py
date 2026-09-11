from datetime import datetime
from utils.db import db


class MaintenanceOrder(db.Model):
    """维修工单模型"""
    __tablename__ = 'maintenance_orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(50), unique=True, nullable=False, comment='工单编号（如 WX20250101001）')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='报修人ID')
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=True, comment='房间ID')
    room_number = db.Column(db.String(50), nullable=False, comment='房间号（冗余存储）')
    title = db.Column(db.String(255), nullable=False, comment='工单标题（自动取描述前20字）')
    description = db.Column(db.Text, nullable=False, comment='问题描述')
    maintenance_type = db.Column(db.String(50), nullable=False, comment='维修类型（水电维修、门窗维修等）')
    priority = db.Column(db.String(50), default='一般', nullable=False, comment='优先级：低/一般/高/紧急')
    status = db.Column(db.String(50), default='待处理', nullable=False, comment='状态：待处理/处理中/已解决/已关闭')
    assigned_to = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, comment='分配的维修员ID')
    assignment_type = db.Column(db.String(20), nullable=True, comment='分配方式：auto/manual')
    assigned_at = db.Column(db.DateTime, nullable=True, comment='分配时间')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    completed_at = db.Column(db.DateTime, nullable=True, comment='完成时间')
    closed_at = db.Column(db.DateTime, nullable=True, comment='关闭时间')
    
    # 外键关联
    user = db.relationship('User', foreign_keys=[user_id], backref='maintenance_orders')
    room = db.relationship('Room', backref='maintenance_orders')
    assigned_user = db.relationship('User', foreign_keys=[assigned_to], backref='assigned_maintenance_orders')
    replies = db.relationship('MaintenanceReply', lazy=True, cascade='all, delete-orphan', backref='order')
    
    def __repr__(self):
        return f'<MaintenanceOrder {self.order_no}: {self.title}>'
    
    @classmethod
    def generate_order_no(cls):
        """生成工单编号，格式：WX+日期+3位序号，如 WX20250101001"""
        today = datetime.now().strftime('%Y%m%d')
        prefix = f'WX{today}'
        # 查询当天已有的最大编号
        last_order = cls.query.filter(
            cls.order_no.like(f'{prefix}%')
        ).order_by(cls.order_no.desc()).first()
        
        if last_order:
            # 提取序号部分并+1
            last_seq = int(last_order.order_no[-3:])
            new_seq = last_seq + 1
        else:
            new_seq = 1
        
        return f'{prefix}{new_seq:03d}'
    
    @classmethod
    def create(cls, user_id, room_id, room_number, title, description, maintenance_type, priority='一般'):
        """创建维修工单"""
        # 自动生成工单编号
        order_no = cls.generate_order_no()
        # 自动取描述前20字作为标题（如果未提供）
        if not title or not title.strip():
            title = description[:20] if description else '无标题'
        
        order = cls(
            order_no=order_no,
            user_id=user_id,
            room_id=room_id,
            room_number=room_number,
            title=title,
            description=description,
            maintenance_type=maintenance_type,
            priority=priority
        )
        db.session.add(order)
        db.session.commit()
        return order
    
    @classmethod
    def get_by_id(cls, order_id):
        """根据ID获取维修工单"""
        return cls.query.get(order_id)
    
    @classmethod
    def get_by_user_id(cls, user_id):
        """获取指定报修人的所有工单"""
        return cls.query.filter_by(user_id=user_id).order_by(cls.created_at.desc()).all()
    
    @classmethod
    def get_by_assigned_to(cls, assigned_to):
        """获取指定维修员的所有工单"""
        return cls.query.filter_by(assigned_to=assigned_to).order_by(cls.created_at.desc()).all()
    
    @classmethod
    def get_all(cls):
        """获取所有维修工单"""
        return cls.query.order_by(cls.created_at.desc()).all()
    
    @classmethod
    def search(cls, keyword=None, status=None, maintenance_type=None, priority=None, assigned_to=None):
        """多条件搜索维修工单"""
        query = cls.query
        
        # 处理关键字搜索
        if keyword and keyword.strip():
            query = query.filter(
                cls.title.like(f'%{keyword}%') |
                cls.description.like(f'%{keyword}%') |
                cls.order_no.like(f'%{keyword}%') |
                cls.room_number.like(f'%{keyword}%')
            )
        
        # 处理状态搜索
        if status and status.strip():
            query = query.filter_by(status=status)
        
        # 处理维修类型搜索
        if maintenance_type and maintenance_type.strip():
            query = query.filter_by(maintenance_type=maintenance_type)
        
        # 处理优先级搜索
        if priority and priority.strip():
            query = query.filter_by(priority=priority)
        
        # 处理维修员搜索
        if assigned_to is not None:
            query = query.filter_by(assigned_to=assigned_to)
        
        return query.order_by(cls.created_at.desc()).all()
    
    @classmethod
    def batch_delete(cls, order_ids):
        """批量删除维修工单"""
        for order_id in order_ids:
            order = cls.get_by_id(order_id)
            if order:
                order.delete()
        return True
    
    def update(self, status=None, priority=None, assigned_to=None, assignment_type=None, 
               maintenance_type=None, description=None, title=None):
        """更新维修工单信息"""
        if title is not None:
            self.title = title
        if description is not None:
            self.description = description
        if maintenance_type is not None:
            self.maintenance_type = maintenance_type
        if priority is not None:
            self.priority = priority
        if assigned_to is not None:
            self.assigned_to = assigned_to
        if assignment_type is not None:
            self.assignment_type = assignment_type
            self.assigned_at = datetime.now()
        if status is not None:
            self.status = status
            # 状态变更时更新对应时间字段
            if status == '处理中' and self.assigned_at is None:
                self.assigned_at = datetime.now()
            if status == '已解决' and self.completed_at is None:
                self.completed_at = datetime.now()
            if status == '已关闭' and self.closed_at is None:
                self.closed_at = datetime.now()
        self.updated_at = datetime.now()
        db.session.commit()
        return self
    
    def delete(self):
        """删除维修工单及关联数据"""
        # 先删除关联的回复
        for reply in self.replies:
            db.session.delete(reply)
        db.session.delete(self)
        db.session.commit()
        return True
    
    @property
    def order_number(self):
        """工单编号别名（兼容模板）"""
        return self.order_no
    
    @property
    def room_info(self):
        """房间信息（兼容模板）"""
        return self.room_number
    
    @property
    def creator_name(self):
        """提交人姓名"""
        if self.user:
            return self.user.name
        return '未知'
    
    @property
    def assigned_to_name(self):
        """维修员姓名"""
        if self.assigned_user:
            return self.assigned_user.name
        return ''
    
    @property
    def resolved_at(self):
        """解决时间别名（兼容模板）"""
        return self.completed_at
    
    def get_timeline(self):
        """生成状态时间线数据"""
        status_flow = ['待处理', '处理中', '已解决', '已关闭']
        timeline = []
        
        # 状态对应的时间字段
        time_map = {
            '待处理': self.created_at,
            '处理中': self.assigned_at or self.updated_at,
            '已解决': self.completed_at,
            '已关闭': self.closed_at
        }
        
        current_idx = status_flow.index(self.status) if self.status in status_flow else 0
        
        for i, status in enumerate(status_flow):
            event = {
                'status': status,
                'time': '',
                'description': '',
                'is_current': i == current_idx,
                'is_completed': i < current_idx
            }
            
            time_value = time_map.get(status)
            if time_value:
                event['time'] = time_value.strftime('%Y-%m-%d %H:%M')
                # 添加描述
                if status == '待处理':
                    event['description'] = '工单已提交'
                elif status == '处理中':
                    if self.assigned_user:
                        event['description'] = f'已分配给 {self.assigned_user.name}'
                elif status == '已解决':
                    event['description'] = '维修完成'
                elif status == '已关闭':
                    event['description'] = '工单已关闭'
            
            timeline.append(event)
        
        return timeline