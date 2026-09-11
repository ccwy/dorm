from utils.db import db
from datetime import datetime


class PushSubscription(db.Model):
    """Web推送订阅模型"""
    __tablename__ = 'push_subscriptions'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, comment='用户ID')
    endpoint = db.Column(db.String(500), nullable=False, comment='推送端点URL')
    p256dh = db.Column(db.String(200), nullable=False, comment='公钥')
    auth = db.Column(db.String(50), nullable=False, comment='认证密钥')
    subscribed_domain = db.Column(db.String(200), nullable=True, comment='订阅时的页面域名(含端口)')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    user = db.relationship('User', backref='push_subscriptions')

    # 同一用户同一端点唯一约束
    __table_args__ = (db.UniqueConstraint('user_id', 'endpoint', name='uq_user_endpoint'),)

    def __repr__(self):
        return f'<PushSubscription user={self.user_id} endpoint={self.endpoint[:50]}>'