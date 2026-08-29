from datetime import datetime
from utils.db import db


class SupplyItem(db.Model):
    """低值易耗品基础资料表"""
    __tablename__ = 'supply_items'

    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    item_number = db.Column(db.String(50), unique=True, nullable=False, comment='物品编号（自动生成，如YP2026080001）')
    name = db.Column(db.String(200), nullable=False, comment='物品名称')
    category = db.Column(db.String(100), nullable=True, comment='物品分类（从系统配置获取）')
    specification = db.Column(db.String(200), nullable=True, comment='规格型号')
    unit = db.Column(db.String(20), nullable=True, comment='计量单位（个/盒/箱/包/瓶/支/本/套等）')

    # 供应商关联
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id', ondelete='SET NULL'), nullable=True, comment='默认供应商ID')

    # 价格信息
    unit_price = db.Column(db.Numeric(10, 2), default=0, nullable=False, comment='单价')
    reference_price = db.Column(db.Numeric(10, 2), nullable=True, comment='参考价格')

    # 库存信息（汇总维度，由SupplyStockDetail聚合计算）
    current_stock = db.Column(db.Integer, default=0, nullable=False, comment='当前总库存数量（所有存放位置汇总）')
    min_stock = db.Column(db.Integer, default=0, nullable=False, comment='最低库存预警数量')
    max_stock = db.Column(db.Integer, nullable=True, comment='最高库存数量')

    # 状态与关联
    status = db.Column(db.String(20), default='启用', nullable=False, comment='状态：启用/停用')

    # 备注
    remark = db.Column(db.Text, nullable=True, comment='备注信息')

    # 操作用户
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作用户ID')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 关系定义
    stock_details = db.relationship('SupplyStockDetail', back_populates='item', lazy=True, cascade='all, delete-orphan')
    stock_in_details = db.relationship('StockInDetail', backref='supply_item', lazy=True)
    stock_out_details = db.relationship('StockOutDetail', backref='supply_item', lazy=True)
    inventory_details = db.relationship('SupplyInventoryDetail', backref='supply_item', lazy=True)
    stock_records = db.relationship('SupplyStockRecord', backref='supply_item', lazy=True)

    # 约束与索引
    __table_args__ = (
        db.UniqueConstraint('item_number', name='uq_supply_item_item_number', comment='物品编号唯一'),
        db.CheckConstraint(
            "status IN ('启用', '停用')",
            name='check_supply_item_status_valid'
        ),
        db.CheckConstraint(
            "current_stock >= 0",
            name='check_supply_item_stock_non_negative'
        ),
        db.CheckConstraint(
            "min_stock >= 0",
            name='check_supply_item_min_stock_non_negative'
        ),
        db.Index('idx_si_name', 'name'),
        db.Index('idx_si_category', 'category'),
        db.Index('idx_si_supplier', 'supplier_id'),
        db.Index('idx_si_status', 'status'),
        db.Index('idx_si_item_number', 'item_number'),
    )

    def __repr__(self):
        return f"<SupplyItem {self.item_number} - {self.name}>"

    @property
    def display_number(self):
        """返回显示编号"""
        return self.item_number or f'YP-{self.id:06d}'

    @property
    def display_status(self):
        """返回状态显示文本"""
        return self.status

    @property
    def is_low_stock(self):
        """是否低于最低库存（受supply_low_stock_alert配置控制）"""
        from models.system_config import SystemConfig
        if not SystemConfig.get_config_value('supply_low_stock_alert', True):
            return False  # 低库存预警关闭时始终返回False
        return self.current_stock <= self.min_stock

    @property
    def supplier_name(self):
        """返回供应商名称"""
        if self.supplier_id:
            from models.supply.supplier import Supplier
            supplier = Supplier.query.get(self.supplier_id)
            return supplier.name if supplier else '未知'
        return '未指定'

    @classmethod
    def create(cls, name, category=None, specification=None, unit=None,
               supplier_id=None, unit_price=0, reference_price=None,
               min_stock=0, max_stock=None, status='启用',
               remark=None, operator_user_id=None, item_number=None):
        """创建物品（支持手动指定编号或自动生成）"""
        from models.system_config import SystemConfig
        auto_number = SystemConfig.get_config_value('supply_auto_number', True)
        # 如果提供了手动编号则使用，否则根据配置决定是否自动生成
        if item_number:
            final_number = item_number
        elif auto_number:
            final_number = cls.generate_item_number()
        else:
            raise ValueError("自动编号已关闭，请手动输入物品编号")
        item = cls(
            item_number=final_number,
            name=name,
            category=category,
            specification=specification,
            unit=unit,
            supplier_id=supplier_id,
            unit_price=unit_price,
            reference_price=reference_price,
            min_stock=min_stock,
            max_stock=max_stock,
            status=status,
            remark=remark,
            operator_user_id=operator_user_id
        )
        db.session.add(item)
        db.session.commit()
        return item

    @classmethod
    def generate_item_number(cls):
        """生成物品编号：前缀+年月+4位序号（前缀从系统配置获取）"""
        from models.system_config import SystemConfig
        prefix_config = SystemConfig.get_config_value('supply_number_prefix', {})
        item_prefix = prefix_config.get('item', 'YP') if isinstance(prefix_config, dict) else 'YP'
        prefix = item_prefix + datetime.now().strftime('%Y%m')
        last_item = cls.query.filter(
            cls.item_number.like(prefix + '%')
        ).order_by(cls.item_number.desc()).first()

        if last_item and last_item.item_number.startswith(prefix):
            seq = int(last_item.item_number[len(prefix):]) + 1
        else:
            seq = 1
        return f'{prefix}{seq:04d}'

    @classmethod
    def is_name_exists(cls, name, exclude_id=None):
        """检查物品名称是否已存在"""
        query = cls.query.filter_by(name=name)
        if exclude_id:
            query = query.filter(cls.id != exclude_id)
        return query.first() is not None

    @classmethod
    def check_usage(cls, item_id):
        """
        检查物品是否被使用，返回使用详情
        """
        from models.supply.supply_stock_detail import SupplyStockDetail
        from models.supply.stock_in_detail import StockInDetail
        from models.supply.stock_out_detail import StockOutDetail

        # 检查库存明细
        stock_count = SupplyStockDetail.query.filter_by(item_id=item_id).count()
        # 检查入库明细
        in_count = StockInDetail.query.filter_by(item_id=item_id).count()
        # 检查出库明细
        out_count = StockOutDetail.query.filter_by(item_id=item_id).count()

        used = stock_count > 0 or in_count > 0 or out_count > 0

        return {
            'used': used,
            'details': {
                'stock_detail_count': stock_count,
                'stock_in_count': in_count,
                'stock_out_count': out_count
            }
        }

    @classmethod
    def get_active_items(cls):
        """获取所有启用的物品列表"""
        return cls.query.filter_by(status='启用').order_by(cls.name).all()

    @classmethod
    def get_low_stock_items(cls):
        """获取低于最低库存的物品列表（受supply_low_stock_alert配置控制）"""
        from models.system_config import SystemConfig
        if not SystemConfig.get_config_value('supply_low_stock_alert', True):
            return []  # 低库存预警关闭时返回空列表
        return cls.query.filter(cls.current_stock <= cls.min_stock, cls.status == '启用').all()

    @classmethod
    def recalculate_stock(cls, item_id):
        """根据SupplyStockDetail重新计算物品总库存"""
        from models.supply.supply_stock_detail import SupplyStockDetail
        from sqlalchemy import func
        total = db.session.query(func.coalesce(func.sum(SupplyStockDetail.quantity), 0)).filter(
            SupplyStockDetail.item_id == item_id
        ).scalar()
        item = cls.query.get(item_id)
        if item:
            item.current_stock = total
            db.session.commit()
        return item

    @classmethod
    def get_all_names(cls):
        """获取所有物品名称列表"""
        items = cls.query.order_by(cls.name).all()
        return [item.name for item in items]