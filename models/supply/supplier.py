from datetime import datetime
from utils.db import db


class Supplier(db.Model):
    """供应商表"""
    __tablename__ = 'suppliers'

    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, comment='供应商名称')
    unified_social_credit_code = db.Column(db.String(18), nullable=True, comment='统一社会信用代码')
    legal_representative = db.Column(db.String(100), nullable=True, comment='法定代表人')
    contact_person = db.Column(db.String(100), nullable=True, comment='联系人')
    contact_phone = db.Column(db.String(50), nullable=True, comment='联系电话')
    email = db.Column(db.String(200), nullable=True, comment='邮箱')
    address = db.Column(db.String(500), nullable=True, comment='地址')

    # 状态与关联
    status = db.Column(db.String(20), default='启用', nullable=False, comment='状态：启用/停用')
    handler_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, comment='经手人用户ID')

    # 备注
    remark = db.Column(db.Text, nullable=True, comment='备注信息')

    # 税率信息（合同管理模块新增）
    tax_rate = db.Column(db.Numeric(5, 2), nullable=True, comment='税率（%，从供应商获取，如13.00表示13%）')

    # 操作用户
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作用户ID')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 关系定义
    operation_records = db.relationship('SupplierOperationRecord', backref='supplier', lazy=True, cascade='all, delete-orphan')
    supply_items = db.relationship('SupplyItem', backref='supplier', lazy=True)

    # 约束与索引
    __table_args__ = (
        db.UniqueConstraint('name', name='uq_supplier_name', comment='供应商名称唯一'),
        db.CheckConstraint(
            "status IN ('启用', '停用')",
            name='check_supplier_status_valid'
        ),
        db.Index('idx_supplier_name', 'name'),
        db.Index('idx_supplier_status', 'status'),
        db.Index('idx_supplier_handler', 'handler_user_id'),
    )

    def __repr__(self):
        return f"<Supplier {self.name}>"

    @property
    def display_status(self):
        """返回状态显示文本"""
        status_map = {'启用': '启用', '停用': '停用'}
        return status_map.get(self.status, self.status)

    @property
    def handler_name(self):
        """返回经手人姓名"""
        if self.handler_user_id:
            from models.user import User
            user = User.query.get(self.handler_user_id)
            return user.name if user else '未知'
        return '未指定'

    @classmethod
    def create(cls, name, contact_person=None, contact_phone=None,
               email=None, address=None, status='启用', handler_user_id=None,
               remark=None, operator_user_id=None,
               unified_social_credit_code=None, legal_representative=None,
               tax_rate=None):
        """创建供应商"""
        supplier = cls(
            name=name,
            unified_social_credit_code=unified_social_credit_code,
            legal_representative=legal_representative,
            contact_person=contact_person,
            contact_phone=contact_phone,
            email=email,
            address=address,
            status=status,
            handler_user_id=handler_user_id,
            remark=remark,
            tax_rate=tax_rate,
            operator_user_id=operator_user_id
        )
        db.session.add(supplier)
        db.session.commit()
        return supplier

    @classmethod
    def is_name_exists(cls, name, exclude_id=None):
        """检查供应商名称是否已存在"""
        query = cls.query.filter_by(name=name)
        if exclude_id:
            query = query.filter(cls.id != exclude_id)
        return query.first() is not None

    @classmethod
    def check_usage(cls, supplier_id):
        """
        检查供应商是否被使用，返回使用详情
        返回: {'used': bool, 'details': dict}
        """
        from models.supply.supply_item import SupplyItem

        # 检查 SupplyItem.supplier_id
        item_count = SupplyItem.query.filter_by(supplier_id=supplier_id).count()

        used = item_count > 0

        return {
            'used': used,
            'details': {
                'item_count': item_count
            }
        }

    @classmethod
    def get_active_suppliers(cls):
        """获取所有启用的供应商列表"""
        return cls.query.filter_by(status='启用').order_by(cls.name).all()

    @classmethod
    def get_all_names(cls):
        """获取所有供应商名称列表"""
        suppliers = cls.query.order_by(cls.name).all()
        return [s.name for s in suppliers]