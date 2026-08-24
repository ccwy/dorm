from datetime import datetime
from utils.db import db
from .user import User

class TodoProgress(db.Model):
    __tablename__ = 'todo_progresses'
    
    id = db.Column(db.Integer, primary_key=True)
    todo_id = db.Column(db.Integer, db.ForeignKey('todos.id'), nullable=False, comment='待办事项ID')
    progress_percent = db.Column(db.Integer, nullable=False, comment='更新后的进度百分比')
    completed_task = db.Column(db.Text, nullable=False, comment='完成的任务描述')
    updated_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='更新人ID')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    
    # 外键关联
    todo = db.relationship('Todo', overlaps="progresses")
    updated_user = db.relationship('User')
    
    def __repr__(self):
        return f'<TodoProgress {self.id} for Todo {self.todo_id}>'
    
    @classmethod
    def create(cls, todo_id, progress_percent, completed_task, updated_by):
        """创建新的进度记录"""
        progress = cls(
            todo_id=todo_id,
            progress_percent=progress_percent,
            completed_task=completed_task,
            updated_by=updated_by
        )
        db.session.add(progress)
        db.session.commit()
        return progress
    
    @classmethod
    def get_by_todo_id(cls, todo_id):
        """获取指定待办事项的所有进度记录（倒序）"""
        return cls.query.filter_by(todo_id=todo_id).order_by(cls.created_at.desc()).all()
    
    @classmethod
    def delete_by_todo_id(cls, todo_id):
        """删除指定待办事项的所有进度记录"""
        cls.query.filter_by(todo_id=todo_id).delete(synchronize_session=False)
        db.session.commit()
        return True