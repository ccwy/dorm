from datetime import datetime, date, timedelta
from decimal import Decimal
from utils.db import db


class Contract(db.Model):
    """合同主表"""
    __tablename__ = 'contracts'

    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    contract_number = db.Column(db.String(50), unique=True, nullable=True, comment='合同编号（允许自定义，留空自动生成）')
    contract_name = db.Column(db.String(255), nullable=False, comment='合同名称')

    # 甲乙双方（关联供应商表）
    party_a_id = db.Column(db.Integer, db.ForeignKey('suppliers.id', ondelete='SET NULL'), nullable=True, comment='甲方供应商ID')
    party_b_id = db.Column(db.Integer, db.ForeignKey('suppliers.id', ondelete='SET NULL'), nullable=True, comment='乙方供应商ID')

    # 甲方快照信息（保存签约时的甲方信息）
    party_a_contact_person = db.Column(db.String(100), nullable=True, comment='甲方联系人')
    party_a_contact_phone = db.Column(db.String(50), nullable=True, comment='甲方联系电话')
    party_a_address = db.Column(db.String(500), nullable=True, comment='甲方地址')
    party_a_credit_code = db.Column(db.String(18), nullable=True, comment='甲方统一社会信用代码')
    party_a_legal_representative = db.Column(db.String(100), nullable=True, comment='甲方法定代表人')

    # 乙方快照信息（保存签约时的乙方信息）
    party_b_contact_person = db.Column(db.String(100), nullable=True, comment='乙方联系人')
    party_b_contact_phone = db.Column(db.String(50), nullable=True, comment='乙方联系电话')
    party_b_address = db.Column(db.String(500), nullable=True, comment='乙方地址')
    party_b_credit_code = db.Column(db.String(18), nullable=True, comment='乙方统一社会信用代码')
    party_b_legal_representative = db.Column(db.String(100), nullable=True, comment='乙方法定代表人')

    # 合同类型与分类
    contract_type = db.Column(db.String(50), nullable=True, comment='合同类型（从系统配置读取，如：采购合同/服务合同/租赁合同/其他）')
    contract_category = db.Column(db.String(50), nullable=True, comment='合同分类（从系统配置读取）')

    # 金额信息
    contract_amount = db.Column(db.Numeric(14, 2), default=Decimal('0.00'), nullable=True, comment='合同金额（元）')
    currency = db.Column(db.String(10), default='CNY', nullable=True, comment='币种')

    # 税率信息
    tax_rate = db.Column(db.Numeric(5, 2), nullable=True, comment='合同税率（%，可从供应商自动获取，支持自定义覆盖）')
    tax_amount = db.Column(db.Numeric(14, 2), nullable=True, comment='税额（元，由合同金额×税率/100自动计算）')

    # 日期信息
    signing_date = db.Column(db.Date, default=date.today, nullable=True, comment='签订日期（默认当天）')
    start_date = db.Column(db.Date, default=date.today, nullable=True, comment='合同开始日期（默认当天）')
    end_date = db.Column(db.Date, default=lambda: date.today() + timedelta(days=365), nullable=True, comment='合同结束日期（默认1年后）')

    # 合同状态
    status = db.Column(db.String(20), default='草稿', nullable=False, comment='合同状态：草稿/生效中/即将到期/已到期/已终止/已归档')

    # 经手人
    handler_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, comment='经手人用户ID')

    # 关联部门
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id', ondelete='SET NULL'), nullable=True, comment='归属部门ID')

    # 备注
    remark = db.Column(db.Text, nullable=True, comment='备注信息')

    # 存放位置
    storage_location_id = db.Column(db.Integer, db.ForeignKey('storage_locations.id', ondelete='SET NULL'), nullable=True, comment='存放位置ID')

    # 续签关系
    previous_contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id', ondelete='SET NULL'), nullable=True, comment='上一份合同ID（续签关系链，指向原合同）')

    # 操作用户
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作用户ID')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 关系定义
    # attachments = db.relationship('ContractAttachment', backref='contract', lazy=True, cascade='all, delete-orphan')
    operation_records = db.relationship('ContractOperationRecord', backref='contract', lazy=True, cascade='all, delete-orphan')

    # 甲方乙方关系（需要指定foreign_keys避免歧义）
    party_a = db.relationship('Supplier', foreign_keys=[party_a_id], backref='contracts_as_party_a', lazy='select')
    party_b = db.relationship('Supplier', foreign_keys=[party_b_id], backref='contracts_as_party_b', lazy='select')

    # 经手人关系
    handler = db.relationship('User', foreign_keys=[handler_user_id], backref='handled_contracts', lazy='select')

    # 部门关系
    department = db.relationship('Department', foreign_keys=[department_id], backref='contracts', lazy='select')

    # 存放位置关系
    storage_location = db.relationship('StorageLocation', foreign_keys=[storage_location_id])

    # 续签关系（自引用外键）
    previous_contract = db.relationship('Contract', remote_side=[id], foreign_keys=[previous_contract_id], backref='renewed_contracts', lazy='select')

    # 约束与索引
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('草稿', '生效中', '即将到期', '已到期', '已终止', '已归档')",
            name='check_contract_status_valid'
        ),
        db.CheckConstraint(
            "end_date >= start_date",
            name='check_contract_date_range'
        ),
        db.Index('idx_contract_number', 'contract_number'),
        db.Index('idx_contract_name', 'contract_name'),
        db.Index('idx_contract_status', 'status'),
        db.Index('idx_contract_type', 'contract_type'),
        db.Index('idx_contract_party_a', 'party_a_id'),
        db.Index('idx_contract_party_b', 'party_b_id'),
        db.Index('idx_contract_start_date', 'start_date'),
        db.Index('idx_contract_end_date', 'end_date'),
        db.Index('idx_contract_signing_date', 'signing_date'),
        db.Index('idx_contract_handler', 'handler_user_id'),
        db.Index('idx_contract_department', 'department_id'),
        db.Index('idx_contract_previous', 'previous_contract_id'),
        db.Index('idx_contract_storage_location', 'storage_location_id'),
    )

    def __repr__(self):
        return f"<Contract {self.contract_number} - {self.contract_name}>"

    @property
    def display_status(self):
        """返回状态显示文本"""
        status_map = {
            '草稿': '草稿',
            '生效中': '生效中',
            '即将到期': '即将到期',
            '已到期': '已到期',
            '已终止': '已终止',
            '已归档': '已归档'
        }
        return status_map.get(self.status, self.status)

    @property
    def status_color(self):
        """返回状态对应的颜色标识（用于前端显示）"""
        color_map = {
            '草稿': 'gray',
            '生效中': 'green',
            '即将到期': 'yellow',
            '已到期': 'red',
            '已终止': 'red',
            '已归档': 'blue'
        }
        return color_map.get(self.status, 'gray')

    @property
    def days_until_expiry(self):
        """计算距到期日的天数，None表示无结束日期"""
        if self.end_date is None:
            return None
        delta = self.end_date - date.today()
        return delta.days

    @property
    def is_expiring_soon(self):
        """判断是否即将到期（30天内）"""
        days = self.days_until_expiry
        return days is not None and 0 < days <= 30

    @property
    def is_expired(self):
        """判断是否已到期"""
        days = self.days_until_expiry
        return days is not None and days <= 0

    @property
    def party_a_name(self):
        """返回甲方名称"""
        return self.party_a.name if self.party_a else '未指定'

    @property
    def party_b_name(self):
        """返回乙方名称"""
        return self.party_b.name if self.party_b else '未指定'

    @property
    def handler_name(self):
        """返回经手人姓名"""
        if self.handler_user_id:
            from models.user import User
            user = User.query.get(self.handler_user_id)
            return user.name if user else '未知'
        return '未指定'

    @property
    def department_name(self):
        """返回归属部门名称"""
        if self.department_id:
            from models.department import Department
            dept = Department.query.get(self.department_id)
            return dept.name if dept else '未知'
        return '未指定'

    @property
    def storage_location_name(self):
        """返回存放位置名称"""
        if self.storage_location_id:
            from models.supply.storage_location import StorageLocation
            location = StorageLocation.query.get(self.storage_location_id)
            return location.display_name if location else '未知'
        return '未指定'

    @property
    def attachment_count(self):
        """返回附件数量"""
        from utils.contract_attachment import ContractAttachmentManager
        try:
            files = ContractAttachmentManager.get_media_files(self.id)
            return len(files) if files else 0
        except Exception:
            return 0

    @property
    def renewal_chain(self):
        """返回续签关系链（从当前合同向上追溯所有前序合同）
        返回列表按时间正序排列，最早的合同在前
        """
        chain = []
        current = self
        while current.previous_contract_id:
            prev = Contract.query.get(current.previous_contract_id)
            if prev:
                chain.insert(0, prev)
                current = prev
            else:
                break
        return chain

    @property
    def is_renewal(self):
        """判断当前合同是否为续签合同"""
        return self.previous_contract_id is not None

    @property
    def renewal_count(self):
        """返回此合同被续签的次数"""
        return len(self.renewed_contracts) if self.renewed_contracts else 0

    @property
    def has_renewed(self):
        """判断此合同是否已被续签（有续签合同指向它）"""
        return self.renewed_contracts is not None and len(self.renewed_contracts) > 0

    @classmethod
    def create(cls, contract_name, contract_number=None, party_a_id=None, party_b_id=None,
               contract_type=None, contract_category=None, contract_amount=None,
               currency='CNY', tax_rate=None, tax_amount=None, signing_date=None, start_date=None, end_date=None,
               status='草稿', handler_user_id=None, department_id=None,
               previous_contract_id=None, storage_location_id=None, remark=None, operator_user_id=None,
               party_a_contact_person=None, party_a_contact_phone=None, party_a_address=None,
               party_a_credit_code=None, party_a_legal_representative=None,
               party_b_contact_person=None, party_b_contact_phone=None, party_b_address=None,
               party_b_credit_code=None, party_b_legal_representative=None):
        """创建合同"""
        contract = cls(
            contract_name=contract_name,
            contract_number=contract_number,
            party_a_id=party_a_id,
            party_b_id=party_b_id,
            contract_type=contract_type,
            contract_category=contract_category,
            contract_amount=contract_amount,
            currency=currency,
            tax_rate=tax_rate,
            tax_amount=tax_amount,
            signing_date=signing_date or date.today(),
            start_date=start_date or date.today(),
            end_date=end_date or (date.today() + timedelta(days=365)),
            status=status,
            handler_user_id=handler_user_id,
            department_id=department_id,
            previous_contract_id=previous_contract_id,
            storage_location_id=storage_location_id,
            remark=remark,
            operator_user_id=operator_user_id,
            party_a_contact_person=party_a_contact_person,
            party_a_contact_phone=party_a_contact_phone,
            party_a_address=party_a_address,
            party_a_credit_code=party_a_credit_code,
            party_a_legal_representative=party_a_legal_representative,
            party_b_contact_person=party_b_contact_person,
            party_b_contact_phone=party_b_contact_phone,
            party_b_address=party_b_address,
            party_b_credit_code=party_b_credit_code,
            party_b_legal_representative=party_b_legal_representative
        )
        db.session.add(contract)
        db.session.commit()
        return contract

    @classmethod
    def is_number_exists(cls, contract_number, exclude_id=None):
        """检查合同编号是否已存在"""
        if not contract_number:
            return False
        query = cls.query.filter_by(contract_number=contract_number)
        if exclude_id:
            query = query.filter(cls.id != exclude_id)
        return query.first() is not None

    @classmethod
    def check_usage(cls, contract_id):
        """检查合同是否被使用，返回使用详情"""
        from utils.contract_attachment import ContractAttachmentManager
        from models.contract.contract_operation_record import ContractOperationRecord

        try:
            files = ContractAttachmentManager.get_media_files(contract_id)
            attachment_count = len(files) if files else 0
        except Exception:
            attachment_count = 0
        record_count = ContractOperationRecord.query.filter_by(contract_id=contract_id).count()

        return {
            'used': attachment_count > 0 or record_count > 0,
            'details': {
                'attachment_count': attachment_count,
                'record_count': record_count
            }
        }

    @classmethod
    def update_expiry_status(cls):
        """批量更新合同到期状态（可由定时任务调用）
        - 生效中的合同，如果已过期 → 更新为'已到期'
        - 生效中的合同，如果在配置的提醒天数内到期 → 更新为'即将到期'
        """
        from models.system_config import SystemConfig
        warning_days = SystemConfig.get_config_value('CONTRACT_EXPIRY_WARNING_DAYS', 30)
        if isinstance(warning_days, str):
            warning_days = int(warning_days)

        today = date.today()
        warning_date = today + timedelta(days=warning_days)

        # 更新已到期
        expired_contracts = cls.query.filter(
            cls.status == '生效中',
            cls.end_date < today
        ).all()
        for c in expired_contracts:
            c.status = '已到期'

        # 更新即将到期
        expiring_contracts = cls.query.filter(
            cls.status == '生效中',
            cls.end_date >= today,
            cls.end_date <= warning_date
        ).all()
        for c in expiring_contracts:
            c.status = '即将到期'

        db.session.commit()
        return len(expired_contracts), len(expiring_contracts)

    @classmethod
    def get_expiring_contracts(cls, days=None):
        """获取即将到期的合同列表，默认天数从系统配置读取"""
        from models.system_config import SystemConfig
        if days is None:
            days = SystemConfig.get_config_value('CONTRACT_EXPIRY_WARNING_DAYS', 30)
            if isinstance(days, str):
                days = int(days)
        today = date.today()
        warning_date = today + timedelta(days=days)
        return cls.query.filter(
            cls.end_date >= today,
            cls.end_date <= warning_date,
            cls.status.in_(['生效中', '即将到期'])
        ).order_by(cls.end_date).all()

    @classmethod
    def get_expired_contracts(cls):
        """获取已到期但未处理的合同列表"""
        today = date.today()
        return cls.query.filter(
            cls.end_date < today,
            cls.status.in_(['生效中', '即将到期'])
        ).order_by(cls.end_date).all()