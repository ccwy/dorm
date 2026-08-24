from datetime import datetime
from utils.db import db

class OperationLog(db.Model):
    __tablename__ = 'logs'
    
    # 核心字段（与硬编码管理员逻辑兼容，仅存储user_id）
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True, comment='操作人ID')  # 操作人ID
    action = db.Column(db.String(255), nullable=True, comment='操作内容描述')  # 操作内容描述
    operate_time = db.Column(db.DateTime, default=datetime.now, comment='操作时间')  # 操作时间
    ip_address = db.Column(db.String(100), comment='操作IP地址')  # 操作IP地址
    operation_result = db.Column(db.String(255), comment='操作结果（成功/失败原因）')  # 操作结果（成功/失败原因）
    
    # 扩展字段（支持模块区分和业务详情存储）
    module = db.Column(db.String(50), default='', comment='模块标识：dorm-宿舍模块，system-系统模块等')
    operation_type = db.Column(db.String(50), default='', comment='操作类型：allocate-分配宿舍，login-登录等')

    # 索引优化（针对高频查询场景）
    __table_args__ = (
        db.Index('idx_operate_time', 'operate_time'),  # 按时间筛选
        db.Index('idx_module', 'module'),  # 按模块筛选（如宿舍模块）
        db.Index('idx_operation_type', 'operation_type'),  # 按操作类型筛选
        db.Index('idx_user_id', 'user_id'),  # 按操作人ID筛选（硬编码管理员ID）
        db.Index('idx_module_time', 'module', 'operate_time'),  # 模块+时间组合查询
    )
    
    def __repr__(self):
        """模型字符串表示（便于调试）"""
        return f'<OperationLog {self.id}: {self.module}/{self.operation_type} by {self.user_id}>'
    