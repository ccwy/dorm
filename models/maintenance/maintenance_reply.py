from datetime import datetime
from utils.db import db


class MaintenanceReply(db.Model):
    """维修工单回复模型"""
    __tablename__ = 'maintenance_replies'
    
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('maintenance_orders.id'), nullable=False, comment='工单ID')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='回复用户ID')
    content = db.Column(db.Text, nullable=False, comment='回复内容')
    reply_type = db.Column(db.String(50), default='reply', comment='回复类型：reply/assignment/status_change')
    assignment_type = db.Column(db.String(20), nullable=True, comment='分配方式：auto/manual（仅assignment类型回复使用）')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='回复时间')
    
    # 外键关联
    user = db.relationship('User')
    
    def __repr__(self):
        return f'<MaintenanceReply {self.id} for Order {self.order_id}>'
    
    @classmethod
    def create(cls, order_id, user_id, content, reply_type='reply'):
        """创建维修工单回复"""
        reply = cls(
            order_id=order_id,
            user_id=user_id,
            content=content,
            reply_type=reply_type
        )
        db.session.add(reply)
        db.session.commit()
        
        # 更新工单的更新时间
        from models.maintenance.maintenance_order import MaintenanceOrder
        order = MaintenanceOrder.get_by_id(order_id)
        if order:
            order.updated_at = datetime.now()
            db.session.commit()
        
        return reply
    
    @classmethod
    def get_by_order_id(cls, order_id):
        """获取指定工单的所有回复，按时间升序"""
        return cls.query.filter_by(order_id=order_id).order_by(cls.created_at.asc()).all()
    
    @classmethod
    def create_assignment_reply(cls, order_id, assigned_to_user, assigned_by_user, assignment_type='manual'):
        """创建分配通知回复"""
        content = f'系统通知：工单已分配给维修员【{assigned_to_user.name}】'
        reply = cls(
            order_id=order_id,
            user_id=assigned_by_user.id,
            content=content,
            reply_type='assignment',
            assignment_type=assignment_type
        )
        db.session.add(reply)
        db.session.commit()
        
        # 更新工单的更新时间
        from models.maintenance.maintenance_order import MaintenanceOrder
        order = MaintenanceOrder.get_by_id(order_id)
        if order:
            order.updated_at = datetime.now()
            db.session.commit()
        
        return reply
    
    @classmethod
    def create_status_change_reply(cls, order_id, old_status, new_status, user):
        """创建状态变更通知回复"""
        content = f'系统通知：工单状态由【{old_status}】变更为【{new_status}】'
        return cls.create(order_id, user.id, content, reply_type='status_change')
    
    @property
    def author_name(self):
        """回复者姓名"""
        if self.user:
            return self.user.name
        return '未知'
    
    @property
    def old_status(self):
        """状态变更：旧状态（从content解析）"""
        if self.reply_type == 'status_change' and self.content:
            import re
            match = re.search(r'由【(.+?)】变更为', self.content)
            if match:
                return match.group(1)
        return ''
    
    @property
    def new_status(self):
        """状态变更：新状态（从content解析）"""
        if self.reply_type == 'status_change' and self.content:
            import re
            match = re.search(r'变更为【(.+?)】', self.content)
            if match:
                return match.group(1)
        return ''
    
    @property
    def assigned_name(self):
        """分配的维修员姓名（从content解析）"""
        if self.reply_type == 'assignment' and self.content:
            import re
            match = re.search(r'分配给维修员【(.+?)】', self.content)
            if match:
                return match.group(1)
        return ''