from datetime import datetime
from utils.db import db


class AgentConfig(db.Model):
    """Agent业务配置表，key-value结构存储Agent相关配置"""
    __tablename__ = 'agent_config'

    id = db.Column(db.Integer, primary_key=True)
    config_key = db.Column(db.String(100), nullable=False, unique=True, comment='配置键')
    config_value = db.Column(db.Text, nullable=False, default='', comment='配置值')
    description = db.Column(db.String(200), nullable=True, comment='配置说明')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')

    __table_args__ = (
        db.Index('idx_agent_config_key', 'config_key'),
    )

    @staticmethod
    def get_value(key, default=''):
        """获取配置值，不存在则返回默认值"""
        config = AgentConfig.query.filter_by(config_key=key).first()
        if config:
            return config.config_value
        return default

    @staticmethod
    def set_value(key, value, description=None):
        """设置配置值，不存在则创建"""
        config = AgentConfig.query.filter_by(config_key=key).first()
        if config:
            config.config_value = value
            if description is not None:
                config.description = description
        else:
            config = AgentConfig(
                config_key=key,
                config_value=value,
                description=description
            )
            db.session.add(config)
        db.session.commit()
        return config

    @classmethod
    def init_default_configs(cls):
        """初始化默认配置项，仅在对应key不存在时创建"""
        defaults = [
            ('server_url', '', '当前服务器地址（留空则自动检测请求来源地址）'),
            ('inject_server_url', '', '注入到下载客户端的服务器地址（留空则按server_url→请求来源地址顺序fallback）'),
            ('inject_api_key', '', '注入到下载客户端的API Key（留空则自动使用通用下载密钥，首次下载时创建，后续复用）'),
            ('migration_new_url', '', '服务器迁移目标URL'),
            ('migration_enabled', 'false', '是否启用服务器迁移通知'),
            ('heartbeat_interval', '120', 'Agent心跳间隔（秒）'),
            ('offline_threshold', '360', 'Agent离线判定阈值（秒）'),
            ('heartbeat_log_enabled', 'false', '是否记录心跳日志'),
            ('heartbeat_log_retention_days', '30', '心跳日志保留天数'),
            ('allow_remote_stop', 'false', '是否允许服务端远程停止Agent'),
        ]
        for key, value, desc in defaults:
            if not cls.query.filter_by(config_key=key).first():
                config = cls(config_key=key, config_value=value, description=desc)
                db.session.add(config)
        db.session.commit()