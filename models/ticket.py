from datetime import datetime
from utils.db import db

class Ticket(db.Model):
    __tablename__ = 'tickets'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='提交留言的用户ID')
    title = db.Column(db.String(255), nullable=False, comment='留言标题')
    description = db.Column(db.Text, nullable=False, comment='留言描述')
    status = db.Column(db.String(50), default='待处理', nullable=False, comment='留言状态：待处理、处理中、已解决、已关闭')
    priority = db.Column(db.String(50), default='一般', nullable=False, comment='优先级：低、一般、高、紧急')
    category = db.Column(db.String(50), nullable=False, comment='留言分类')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    closed_at = db.Column(db.DateTime, nullable=True, comment='关闭时间')
    
    # 外键关联
    user = db.relationship('User', backref='tickets')
    replies = db.relationship('TicketReply', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Ticket {self.id}: {self.title}>'
    
    @classmethod
    def create(cls, user_id, title, description, category, priority='一般'):
        """创建新留言"""
        ticket = cls(
            user_id=user_id,
            title=title,
            description=description,
            category=category,
            priority=priority
        )
        db.session.add(ticket)
        db.session.commit()
        return ticket
    
    def update(self, title=None, description=None, status=None, priority=None, category=None):
        """更新留言信息"""
        if title is not None:
            self.title = title
        if description is not None:
            self.description = description
        if status is not None:
            self.status = status
            # 如果状态变为已关闭，记录关闭时间
            if status == '已关闭' and self.closed_at is None:
                self.closed_at = datetime.now()
        if priority is not None:
            self.priority = priority
        if category is not None:
            self.category = category
        self.updated_at = datetime.now()
        db.session.commit()
        return self
    
    def delete(self):
        """删除留言"""
        # 先删除关联的回复
        for reply in self.replies:
            db.session.delete(reply)
        db.session.delete(self)
        db.session.commit()
        return True
    
    @classmethod
    def get_by_id(cls, ticket_id):
        """根据ID获取留言"""
        return cls.query.get(ticket_id)
    
    @classmethod
    def get_by_user_id(cls, user_id):
        """获取指定用户的所有留言"""
        return cls.query.filter_by(user_id=user_id).order_by(cls.created_at.desc()).all()
    
    @classmethod
    def get_all(cls):
        """获取所有留言"""
        return cls.query.order_by(cls.created_at.desc()).all()
    
    @classmethod
    def search(cls, keyword=None, status=None, category=None, priority=None):
        """搜索留言"""
        query = cls.query
        
        # 处理关键字搜索，确保不为空
        if keyword and keyword.strip():
            query = query.filter(
                cls.title.like(f'%{keyword}%') | 
                cls.description.like(f'%{keyword}%')
            )
        
        # 处理状态搜索，确保不为空
        if status and status.strip():
            query = query.filter_by(status=status)
        
        # 处理分类搜索，确保不为空
        if category and category.strip():
            query = query.filter_by(category=category)
        
        # 处理优先级搜索，确保不为空
        if priority and priority.strip():
            query = query.filter_by(priority=priority)
        
        return query.order_by(cls.created_at.desc()).all()
    
    @classmethod
    def batch_delete(cls, ticket_ids):
        """批量删除留言"""
        for ticket_id in ticket_ids:
            ticket = cls.get_by_id(ticket_id)
            if ticket:
                ticket.delete()
        return True