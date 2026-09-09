from datetime import datetime
from utils.db import db


class AgentDevice(db.Model):
    """Agent设备信息表，存储Windows客户端上报的PC基础信息"""
    __tablename__ = 'agent_devices'

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.String(64), unique=True, nullable=False, comment='Agent设备唯一标识')
    asset_id = db.Column(db.Integer, db.ForeignKey('fixed_assets.id'), nullable=True, comment='关联固定资产ID')
    asset_number = db.Column(db.String(50), nullable=True, comment='关联资产编号')
    hostname = db.Column(db.String(255), nullable=True, comment='主机名')
    os_name = db.Column(db.String(255), nullable=True, comment='操作系统名称')
    os_version = db.Column(db.String(100), nullable=True, comment='操作系统版本')
    os_arch = db.Column(db.String(20), nullable=True, comment='系统架构(如x86_64)')
    cpu_model = db.Column(db.String(255), nullable=True, comment='CPU型号')
    cpu_cores = db.Column(db.Integer, nullable=True, comment='CPU核心数')
    total_memory_mb = db.Column(db.Integer, nullable=True, comment='总内存(MB)')
    available_memory_mb = db.Column(db.Integer, nullable=True, comment='可用内存(MB)')
    disks = db.Column(db.Text, nullable=True, comment='磁盘信息(JSON)')
    mac_address = db.Column(db.String(17), nullable=True, comment='MAC地址')
    ip_address = db.Column(db.String(45), nullable=True, comment='IP地址')
    network_interfaces = db.Column(db.Text, nullable=True, comment='网络接口信息(JSON)')
    agent_version = db.Column(db.String(20), nullable=True, comment='Agent客户端版本')
    logged_in_user = db.Column(db.String(100), nullable=True, comment='当前登录用户名')
    device_fingerprint = db.Column(db.String(64), nullable=True, comment='设备指纹(SHA-256 hex)')
    info_hash = db.Column(db.String(64), nullable=True, comment='系统信息哈希(SHA-256 hex)，用于变更检测')
    uuid = db.Column(db.String(36), unique=True, comment='服务端分配UUID v4')
    platform = db.Column(db.String(20), default='windows', comment='客户端平台标识，当前仅支持windows')
    location = db.Column(db.String(200), nullable=True, comment='存放位置')
    department = db.Column(db.String(100), nullable=True, comment='所属部门')
    responsible_person = db.Column(db.String(50), nullable=True, comment='责任人')
    pending_commands = db.Column(db.Text, nullable=True, comment='待下发远程指令(JSON数组)')
    status = db.Column(db.String(20), default='offline', comment='在线状态: online/offline')
    last_heartbeat_at = db.Column(db.DateTime, nullable=True, comment='最后心跳时间')
    first_seen_at = db.Column(db.DateTime, default=datetime.utcnow, comment='首次上线时间')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')

    # 关系定义
    asset = db.relationship('FixedAsset', foreign_keys=[asset_id], lazy='select')

    __table_args__ = (
        db.CheckConstraint("status IN ('online', 'offline')", name='ck_agent_device_status'),
        db.UniqueConstraint('agent_id', name='uq_agent_device_agent_id'),
        db.UniqueConstraint('uuid', name='uq_agent_device_uuid'),
        db.Index('idx_agent_device_agent_id', 'agent_id'),
        db.Index('idx_agent_device_mac', 'mac_address'),
        db.Index('idx_agent_device_asset_id', 'asset_id'),
        db.Index('idx_agent_device_status', 'status'),
        db.Index('idx_agent_device_hostname', 'hostname'),
        db.Index('idx_agent_device_asset_number', 'asset_number'),
        db.Index('idx_agent_device_fingerprint', 'device_fingerprint'),
        db.Index('idx_agent_device_hostname_mac', 'hostname', 'mac_address'),
        db.Index('idx_agent_device_platform', 'platform'),
    )