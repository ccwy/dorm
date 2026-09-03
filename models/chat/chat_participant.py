from utils.db import db
from datetime import datetime

class ChatParticipant(db.Model):
    __tablename__ = 'chat_participants'
    
    id = db.Column(db.Integer, primary_key=True)
    chat_session_id = db.Column(db.Integer, db.ForeignKey('chat_sessions.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.now, comment='加入时间')
    last_read_at = db.Column(db.DateTime, default=datetime.now, comment='最后阅读时间')
    is_hidden = db.Column(db.Boolean, default=False, comment='是否隐藏会话')
    
    # 确保一个用户在一个会话中只出现一次
    __table_args__ = (db.UniqueConstraint('chat_session_id', 'user_id'),)