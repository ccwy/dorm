from datetime import datetime
from utils.db import db


class AgentHeartbeatLog(db.Model):
    """Agent心跳日志表，记录Agent客户端心跳上报历史"""
    __tablename__ = 'agent_heartbeat_logs'

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.String(64), nullable=False, comment='Agent设备唯一标识')
    heartbeat_at = db.Column(db.DateTime, default=datetime.utcnow, comment='心跳时间')
    ip_address = db.Column(db.String(45), nullable=True, comment='客户端IP地址')

    __table_args__ = (
        db.Index('idx_heartbeat_agent_id', 'agent_id'),
        db.Index('idx_heartbeat_time', 'heartbeat_at'),
    )