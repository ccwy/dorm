from datetime import datetime
from utils.db import db


class ContractAttachment(db.Model):
    """合同附件表 - 存储合同附件的元数据信息"""
    __tablename__ = 'contract_attachments'

    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id', ondelete='CASCADE'), nullable=False, comment='关联合同ID')

    # 文件信息
    original_filename = db.Column(db.String(500), nullable=False, comment='原始文件名')
    saved_filename = db.Column(db.String(500), nullable=False, comment='存储文件名（时间戳+随机数命名）')
    file_path = db.Column(db.String(1000), nullable=False, comment='文件相对路径')
    file_size = db.Column(db.Integer, nullable=True, comment='文件大小（字节）')
    file_type = db.Column(db.String(20), nullable=True, comment='文件类型：image/video/document/other')
    file_extension = db.Column(db.String(20), nullable=True, comment='文件扩展名')

    # 附件描述
    description = db.Column(db.String(500), nullable=True, comment='附件描述（如：合同正文、补充协议等）')

    # 上传人
    uploader_id = db.Column(db.Integer, nullable=True, comment='上传人ID')
    uploader_name = db.Column(db.String(50), nullable=True, comment='上传人姓名')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='上传时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 索引
    __table_args__ = (
        db.Index('idx_ca_contract_id', 'contract_id'),
        db.Index('idx_ca_file_type', 'file_type'),
        db.Index('idx_ca_uploader', 'uploader_id'),
        db.Index('idx_ca_created_at', 'created_at'),
    )

    def __repr__(self):
        return f"<ContractAttachment {self.original_filename}>"

    @classmethod
    def create(cls, contract_id, original_filename, saved_filename, file_path,
               file_size=None, file_type=None, file_extension=None,
               description=None, uploader_id=None, uploader_name=None):
        """创建附件记录"""
        attachment = cls(
            contract_id=contract_id,
            original_filename=original_filename,
            saved_filename=saved_filename,
            file_path=file_path,
            file_size=file_size,
            file_type=file_type,
            file_extension=file_extension,
            description=description,
            uploader_id=uploader_id,
            uploader_name=uploader_name
        )
        db.session.add(attachment)
        db.session.commit()
        return attachment