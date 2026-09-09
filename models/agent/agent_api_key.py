from datetime import datetime
from utils.db import db


class AgentApiKey(db.Model):
    """Agent API Key管理表，用于Agent客户端认证"""
    __tablename__ = 'agent_api_keys'

    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String(64), unique=True, nullable=False, comment='API Key，格式: AGENT_{32位hex}')
    agent_id = db.Column(db.String(64), nullable=True, comment='关联的Agent设备ID，首次注册时回填')
    name = db.Column(db.String(100), nullable=True, comment='Key名称')
    remark = db.Column(db.String(255), nullable=True, comment='Key备注/说明')
    is_active = db.Column(db.Boolean, default=True, comment='是否启用')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    expires_at = db.Column(db.DateTime, nullable=True, comment='过期时间')
    last_used_at = db.Column(db.DateTime, nullable=True, comment='最后使用时间')
    created_by = db.Column(db.Integer, nullable=True, comment='创建人用户ID')

    __table_args__ = (
        db.Index('idx_agent_api_key', 'api_key'),
        db.Index('idx_agent_api_key_active', 'is_active'),
    )