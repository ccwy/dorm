from datetime import datetime
from utils.db import db
from .user import User

class Todo(db.Model):
    __tablename__ = 'todos'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False, comment='待办事项标题')
    description = db.Column(db.Text, nullable=True, comment='待办事项描述')
    status = db.Column(db.String(50), default='未开始', nullable=False, comment='状态：未开始、进行中、已完成、已延迟、已取消')
    priority = db.Column(db.String(20), default='中', nullable=True, comment='优先级：低、中、高、紧急')
    category = db.Column(db.String(50), nullable=True, comment='待办事项分类')
    start_time = db.Column(db.DateTime, nullable=True, comment='开始时间')
    planned_end_time = db.Column(db.DateTime, nullable=True, comment='计划完成时间')
    actual_end_time = db.Column(db.DateTime, nullable=True, comment='实际完成时间')
    progress = db.Column(db.Integer, default=0, comment='当前进度百分比')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='创建人ID')
    assignee = db.Column(db.String(50), nullable=True, comment='负责人')
    
    # 外键关联
    created_user = db.relationship('User', backref='todos_created')
    progresses = db.relationship('TodoProgress', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Todo {self.id}: {self.title}>'
    
    @classmethod
    def create(cls, title, description, created_by, start_time=None, planned_end_time=None, status='未开始', priority='中', category=None, assignee=None, progress=0):
        """创建新的待办事项"""
        todo = cls(
            title=title,
            description=description,
            created_by=created_by,
            start_time=start_time,
            planned_end_time=planned_end_time,
            status=status,
            priority=priority,
            category=category,
            assignee=assignee,
            progress=progress
        )
        db.session.add(todo)
        db.session.commit()
        return todo
    
    def update(self, title=None, description=None, status=None, start_time=None, 
               planned_end_time=None, actual_end_time=None, progress=None, priority=None, category=None, assignee=None):
        """更新待办事项信息"""
        if title is not None:
            self.title = title
        if description is not None:
            self.description = description
        if status is not None:
            self.status = status
            # 如果状态变为已完成，记录实际完成时间
            if status == '已完成' and self.actual_end_time is None:
                self.actual_end_time = datetime.now()
        if start_time is not None:
            self.start_time = start_time
        if planned_end_time is not None:
            self.planned_end_time = planned_end_time
        if actual_end_time is not None:
            self.actual_end_time = actual_end_time
        if progress is not None:
            self.progress = progress
        if priority is not None:
            self.priority = priority
        if category is not None:
            self.category = category
        if assignee is not None:
            self.assignee = assignee
        self.updated_at = datetime.now()
        db.session.commit()
        return self
    
    def delete(self):
        """删除待办事项"""
        db.session.delete(self)
        db.session.commit()
        return True
    
    @classmethod
    def get_by_id(cls, todo_id):
        """根据ID获取待办事项"""
        return cls.query.get(todo_id)
    
    @classmethod
    def get_by_user_id(cls, user_id):
        """获取指定用户的所有待办事项"""
        return cls.query.filter_by(created_by=user_id).order_by(cls.created_at.desc()).all()
    
    @classmethod
    def get_all(cls):
        """获取所有待办事项"""
        return cls.query.order_by(cls.created_at.desc()).all()
    

    @classmethod
    def search(cls, keyword=None, status=None, start_date=None, end_date=None):
        """搜索待办事项"""
        query = cls.query
        
        # 处理关键字搜索
        if keyword and keyword.strip():
            query = query.filter(
                cls.title.like(f'%{keyword}%') | 
                cls.description.like(f'%{keyword}%')
            )
        
        # 处理状态搜索
        if status and status.strip():
            query = query.filter_by(status=status)
        
        # 处理时间范围搜索
        if start_date:
            query = query.filter(cls.created_at >= start_date)
        if end_date:
            query = query.filter(cls.created_at <= end_date)
        
        return query.order_by(cls.created_at.desc()).all()
    
    @classmethod
    def batch_delete(cls, todo_ids):
        """批量删除待办事项"""
        for todo_id in todo_ids:
            todo = cls.get_by_id(todo_id)
            if todo:
                todo.delete()
        return True
    
    def add_progress_record(self, progress_percent, completed_task, updated_by):
        """添加进度记录"""
        from models.todo_progress import TodoProgress
        
        # 创建进度记录
        progress_record = TodoProgress.create(
            todo_id=self.id,
            progress_percent=progress_percent,
            completed_task=completed_task,
            updated_by=updated_by
        )
        
        # 更新待办事项的进度
        self.progress = progress_percent
        
        # 如果进度达到100%，更新状态为已完成
        if progress_percent >= 100:
            self.status = '已完成'
            self.actual_end_time = datetime.now()
        elif progress_percent > 0:
            self.status = '进行中'
        
        self.updated_at = datetime.now()
        db.session.commit()
        
        return progress_record