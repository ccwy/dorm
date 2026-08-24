from utils.db import db
from datetime import datetime

class ChatSession(db.Model):
    __tablename__ = 'chat_sessions'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=True, comment='会话名称（群聊使用）')
    is_group_chat = db.Column(db.Boolean, default=False, comment='是否为群聊')
    participant_count = db.Column(db.Integer, default=0, comment='群聊人数')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    # 关系：一个会话包含多条消息
    messages = db.relationship('ChatMessage', backref='session', lazy=True, cascade='all, delete-orphan')
    # 关系：一个会话有多个参与者
    participants = db.relationship('User', secondary='chat_participants', backref='chat_sessions')