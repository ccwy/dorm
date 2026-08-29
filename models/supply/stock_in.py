from datetime import datetime
from utils.db import db


class StockIn(db.Model):
    """入库主表"""
    __tablename__ = 'stock_ins'

    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    stock_in_number = db.Column(db.String(50), unique=True, nullable=False, comment='入库单号（自动生成，如RK2026080001）')
    stock_in_type = db.Column(db.String(50), nullable=False, comment='入库类型（采购入库/其它入库，从系统配置获取）')
    stock_in_date = db.Column(db.Date, nullable=False, comment='入库日期')

    # 供应商关联
    supplier_id = db.Column(db.Integer, db.ForeignKey('suppliers.id', ondelete='SET NULL'), nullable=True, comment='供应商ID')

    # 经手人
    handler_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, comment='经手人用户ID')

    # 状态
    status = db.Column(db.String(20), default='待审核', nullable=False, comment='状态：待审核/已审核/已取消')

    # 金额信息
    total_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False, comment='入库总金额')

    # 备注
    remark = db.Column(db.Text, nullable=True, comment='备注信息')

    # 审核信息
    review_user_id = db.Column(db.Integer, nullable=True, comment='审核人用户ID')
    review_time = db.Column(db.DateTime, nullable=True, comment='审核时间')
    review_remark = db.Column(db.Text, nullable=True, comment='审核备注')

    # 操作用户
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作用户ID')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 关系定义
    details = db.relationship('StockInDetail', backref='stock_in', lazy=True, cascade='all, delete-orphan')

    # 约束与索引
    __table_args__ = (
        db.UniqueConstraint('stock_in_number', name='uq_stock_in_number', comment='入库单号唯一'),
        db.CheckConstraint(
            "status IN ('待审核', '已审核', '已取消')",
            name='check_stock_in_status_valid'
        ),
        db.CheckConstraint(
            "total_amount >= 0",
            name='check_stock_in_total_amount_non_negative'
        ),
        db.Index('idx_stkin_stock_in_number', 'stock_in_number'),
        db.Index('idx_stkin_type', 'stock_in_type'),
        db.Index('idx_stkin_date', 'stock_in_date'),
        db.Index('idx_stkin_status', 'status'),
        db.Index('idx_stkin_supplier', 'supplier_id'),
        db.Index('idx_stkin_handler', 'handler_user_id'),
    )

    def __repr__(self):
        return f"<StockIn {self.stock_in_number}>"

    @property
    def display_number(self):
        """返回显示编号"""
        return self.stock_in_number

    @property
    def display_status(self):
        """返回状态显示文本"""
        return self.status

    @property
    def supplier_name(self):
        """返回供应商名称"""
        if self.supplier_id:
            from models.supply.supplier import Supplier
            supplier = Supplier.query.get(self.supplier_id)
            return supplier.name if supplier else '未知'
        return '未指定'

    @property
    def handler_name(self):
        """返回经手人姓名"""
        if self.handler_user_id:
            from models.user import User
            user = User.query.get(self.handler_user_id)
            return user.name if user else '未知'
        return '未指定'

    @property
    def creator_name(self):
        """返回创建人姓名"""
        if self.operator_user_id:
            from models.user import User
            user = User.query.get(self.operator_user_id)
            return user.name if user else '未知'
        return '-'

    @property
    def reviewer_name(self):
        """返回审核人姓名"""
        if self.review_user_id:
            from models.user import User
            user = User.query.get(self.review_user_id)
            return user.name if user else '未知'
        return '-'

    @property
    def detail_count(self):
        """返回明细数量"""
        return len(self.details)

    @classmethod
    def create(cls, stock_in_type, stock_in_date, supplier_id=None,
               handler_user_id=None, remark=None,
               operator_user_id=None, stock_in_number=None):
        """创建入库单（支持手动指定编号或自动生成）"""
        from models.system_config import SystemConfig
        auto_number = SystemConfig.get_config_value('supply_auto_number', True)
        if stock_in_number:
            final_number = stock_in_number
        elif auto_number:
            final_number = cls.generate_stock_in_number()
        else:
            raise ValueError("自动编号已关闭，请手动输入入库单号")
        stock_in = cls(
            stock_in_number=final_number,
            stock_in_type=stock_in_type,
            stock_in_date=stock_in_date,
            supplier_id=supplier_id,
            handler_user_id=handler_user_id,
            remark=remark,
            operator_user_id=operator_user_id
        )
        db.session.add(stock_in)
        db.session.commit()
        return stock_in

    @classmethod
    def generate_stock_in_number(cls):
        """生成入库单号：前缀+年月+4位序号（前缀从系统配置获取）"""
        from models.system_config import SystemConfig
        prefix_config = SystemConfig.get_config_value('supply_number_prefix', {})
        stock_in_prefix = prefix_config.get('stock_in', 'RK') if isinstance(prefix_config, dict) else 'RK'
        prefix = stock_in_prefix + datetime.now().strftime('%Y%m')
        last = cls.query.filter(
            cls.stock_in_number.like(prefix + '%')
        ).order_by(cls.stock_in_number.desc()).first()

        if last and last.stock_in_number.startswith(prefix):
            seq = int(last.stock_in_number[len(prefix):]) + 1
        else:
            seq = 1
        return f'{prefix}{seq:04d}'

    @classmethod
    def approve(cls, stock_in_id, review_user_id, review_remark=None):
        """
        审核入库单
        审核通过时：
        1. 更新入库单状态为"已审核"
        2. 遍历入库明细，更新 SupplyStockDetail（按位置增加库存）
        3. 遍历入库明细，更新 SupplyItem.current_stock（汇总增加）
        4. 遍历入库明细，写入 SupplyStockRecord（入库记录）
        """
        from models.supply.supply_stock_detail import SupplyStockDetail
        from models.supply.supply_stock_record import SupplyStockRecord

        stock_in = cls.query.get(stock_in_id)
        if not stock_in or stock_in.status != '待审核':
            return None

        stock_in.status = '已审核'
        stock_in.review_user_id = review_user_id
        stock_in.review_time = datetime.now()
        stock_in.review_remark = review_remark

        # 遍历入库明细，更新库存
        for detail in stock_in.details:
            # 更新库存明细（按位置增加）
            SupplyStockDetail.add_stock(
                item_id=detail.item_id,
                location_id=detail.location_id,
                quantity=detail.quantity,
                operator_user_id=review_user_id
            )
            # 写入进出库记录
            SupplyStockRecord.create_record(
                record_type='入库',
                item_id=detail.item_id,
                location_id=detail.location_id,
                quantity=detail.quantity,
                unit_price=detail.unit_price,
                source_number=stock_in.stock_in_number,
                source_type=stock_in.stock_in_type,
                operator_user_id=review_user_id,
                remark=f'入库单{stock_in.stock_in_number}审核通过'
            )

        db.session.commit()
        return stock_in

    @classmethod
    def unapprove(cls, stock_in_id, operator_user_id=None):
        """
        反审核入库单（仅已审核状态可反审核）
        反审核时：
        1. 检查每个明细的库存是否充足（扣减入库数量后不能为负）
        2. 更新入库单状态为"待审核"
        3. 遍历入库明细，回滚 SupplyStockDetail（按位置减少库存）
        4. 遍历入库明细，回滚 SupplyItem.current_stock（汇总减少）
        5. 新增"入库反审核"进出库记录（保留审核历史，反审核操作留痕）
        如果任何明细库存不足，反审核失败并返回错误信息
        """
        from models.supply.supply_stock_detail import SupplyStockDetail
        from models.supply.supply_stock_record import SupplyStockRecord
        from models.supply.supply_item import SupplyItem

        stock_in = cls.query.get(stock_in_id)
        if not stock_in or stock_in.status != '已审核':
            return None

        # 先检查所有明细的库存是否充足（扣减后不能为负）
        insufficient_items = []
        for detail in stock_in.details:
            stock_detail = SupplyStockDetail.query.filter_by(
                item_id=detail.item_id,
                location_id=detail.location_id
            ).first()
            available = stock_detail.quantity if stock_detail else 0
            if available < detail.quantity:
                insufficient_items.append({
                    'item_name': detail.item_name,
                    'location_name': detail.location_name,
                    'available': available,
                    'required': detail.quantity
                })

        if insufficient_items:
            return {'error': '库存不足，无法反审核', 'details': insufficient_items}

        # 库存充足，执行回滚（直接操作数据库，保证事务一致性）
        for detail in stock_in.details:
            # 回滚库存明细（按位置减少）
            stock_detail = SupplyStockDetail.query.filter_by(
                item_id=detail.item_id,
                location_id=detail.location_id
            ).first()
            if stock_detail:
                stock_detail.quantity -= detail.quantity
                stock_detail.operator_user_id = operator_user_id

            # 回滚物品汇总库存
            item = SupplyItem.query.get(detail.item_id)
            if item:
                item.current_stock -= detail.quantity

            # 新增"入库反审核"进出库记录（保留审核历史，反审核操作留痕）
            record = SupplyStockRecord(
                record_type='入库反审核',
                item_id=detail.item_id,
                item_name=detail.item_name,
                location_id=detail.location_id,
                location_name=detail.location_name,
                quantity=detail.quantity,
                unit_price=detail.unit_price,
                total_price=detail.quantity * detail.unit_price if detail.unit_price else 0,
                source_number=stock_in.stock_in_number,
                source_type=stock_in.stock_in_type,
                operator_user_id=operator_user_id,
                remark=f'入库单{stock_in.stock_in_number}反审核，库存回滚'
            )
            db.session.add(record)

        # 更新入库单状态
        stock_in.status = '待审核'
        stock_in.review_user_id = None
        stock_in.review_time = None
        stock_in.review_remark = None

        db.session.commit()
        return stock_in

    @classmethod
    def cancel(cls, stock_in_id, operator_user_id=None):
        """取消入库单（仅待审核状态可取消）"""
        stock_in = cls.query.get(stock_in_id)
        if not stock_in or stock_in.status != '待审核':
            return None
        stock_in.status = '已取消'
        stock_in.operator_user_id = operator_user_id
        db.session.commit()
        return stock_in

    @classmethod
    def recalculate_total_amount(cls, stock_in_id):
        """根据明细重新计算入库总金额"""
        from sqlalchemy import func
        from models.supply.stock_in_detail import StockInDetail
        total = db.session.query(func.coalesce(func.sum(
            StockInDetail.quantity * StockInDetail.unit_price
        ), 0)).filter(StockInDetail.stock_in_id == stock_in_id).scalar()
        stock_in = cls.query.get(stock_in_id)
        if stock_in:
            stock_in.total_amount = total
            db.session.commit()
        return stock_in