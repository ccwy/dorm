from datetime import datetime
from utils.db import db


class StockOut(db.Model):
    """出库主表"""
    __tablename__ = 'stock_outs'

    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    stock_out_number = db.Column(db.String(50), unique=True, nullable=False, comment='出库单号（自动生成，如CK2026080001）')
    stock_out_type = db.Column(db.String(50), nullable=False, comment='出库类型（正常领用/其他出库，从系统配置获取）')
    stock_out_date = db.Column(db.Date, nullable=False, comment='出库日期')

    # 领用人/部门
    recipient_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, comment='领用人用户ID')
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id', ondelete='SET NULL'), nullable=True, comment='领用部门ID')

    # 经手人
    handler_user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, comment='经手人用户ID')

    # 状态
    status = db.Column(db.String(20), default='待审核', nullable=False, comment='状态：待审核/已审核/已取消')

    # 金额信息
    total_amount = db.Column(db.Numeric(12, 2), default=0, nullable=False, comment='出库总金额')

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
    details = db.relationship('StockOutDetail', backref='stock_out', lazy=True, cascade='all, delete-orphan')

    # 约束与索引
    __table_args__ = (
        db.UniqueConstraint('stock_out_number', name='uq_stock_out_number', comment='出库单号唯一'),
        db.CheckConstraint(
            "status IN ('待审核', '已审核', '已取消')",
            name='check_stock_out_status_valid'
        ),
        db.CheckConstraint(
            "total_amount >= 0",
            name='check_stock_out_total_amount_non_negative'
        ),
        db.Index('idx_so_stock_out_number', 'stock_out_number'),
        db.Index('idx_so_type', 'stock_out_type'),
        db.Index('idx_so_date', 'stock_out_date'),
        db.Index('idx_so_status', 'status'),
        db.Index('idx_so_recipient', 'recipient_user_id'),
        db.Index('idx_so_department', 'department_id'),
        db.Index('idx_so_handler', 'handler_user_id'),
    )

    def __repr__(self):
        return f"<StockOut {self.stock_out_number}>"

    @property
    def display_number(self):
        """返回显示编号"""
        return self.stock_out_number

    @property
    def display_status(self):
        """返回状态显示文本"""
        return self.status

    @property
    def recipient_name(self):
        """返回领用人姓名"""
        if self.recipient_user_id:
            from models.user import User
            user = User.query.get(self.recipient_user_id)
            return user.name if user else '未知'
        return '未指定'

    @property
    def department_name(self):
        """返回领用部门名称"""
        if self.department_id:
            from models.department import Department
            dept = Department.query.get(self.department_id)
            return dept.name if dept else '未知'
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
    def operator_name(self):
        """返回操作人姓名"""
        if self.operator_user_id:
            from models.user import User
            user = User.query.get(self.operator_user_id)
            return user.name if user else '未知'
        return '系统'

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
    def create(cls, stock_out_type, stock_out_date, recipient_user_id=None,
               department_id=None, handler_user_id=None,
               remark=None, operator_user_id=None, stock_out_number=None):
        """创建出库单（支持手动指定编号或自动生成）"""
        from models.system_config import SystemConfig
        auto_number = SystemConfig.get_config_value('supply_auto_number', True)
        if stock_out_number:
            final_number = stock_out_number
        elif auto_number:
            final_number = cls.generate_stock_out_number()
        else:
            raise ValueError("自动编号已关闭，请手动输入出库单号")
        stock_out = cls(
            stock_out_number=final_number,
            stock_out_type=stock_out_type,
            stock_out_date=stock_out_date,
            recipient_user_id=recipient_user_id,
            department_id=department_id,
            handler_user_id=handler_user_id,
            remark=remark,
            operator_user_id=operator_user_id
        )
        db.session.add(stock_out)
        db.session.commit()
        return stock_out

    @classmethod
    def generate_stock_out_number(cls):
        """生成出库单号：前缀+年月+4位序号（前缀从系统配置获取）"""
        from models.system_config import SystemConfig
        prefix_config = SystemConfig.get_config_value('supply_number_prefix', {})
        stock_out_prefix = prefix_config.get('stock_out', 'CK') if isinstance(prefix_config, dict) else 'CK'
        prefix = stock_out_prefix + datetime.now().strftime('%Y%m')
        last = cls.query.filter(
            cls.stock_out_number.like(prefix + '%')
        ).order_by(cls.stock_out_number.desc()).first()

        if last and last.stock_out_number.startswith(prefix):
            seq = int(last.stock_out_number[len(prefix):]) + 1
        else:
            seq = 1
        return f'{prefix}{seq:04d}'

    @classmethod
    def approve(cls, stock_out_id, review_user_id, review_remark=None):
        """
        审核出库单
        审核通过时：
        1. 检查每个明细的库存是否充足（按位置检查 SupplyStockDetail）- 可通过supply_stock_out_check配置控制
        2. 更新出库单状态为"已审核"
        3. 遍历出库明细，更新 SupplyStockDetail（按位置减少库存）
        4. 遍历出库明细，更新 SupplyItem.current_stock（汇总减少）
        5. 遍历出库明细，写入 SupplyStockRecord（出库记录）
        如果任何明细库存不足，审核失败并返回错误信息
        """
        from models.supply.supply_stock_detail import SupplyStockDetail
        from models.supply.supply_stock_record import SupplyStockRecord
        from models.system_config import SystemConfig

        stock_out = cls.query.get(stock_out_id)
        if not stock_out or stock_out.status != '待审核':
            return None

        # 根据配置决定是否检查库存充足性
        stock_out_check = SystemConfig.get_config_value('supply_stock_out_check', True)
        if stock_out_check:
            # 先检查所有明细的库存是否充足
            insufficient_items = []
            for detail in stock_out.details:
                stock_detail = SupplyStockDetail.query.filter_by(
                    item_id=detail.item_id,
                    location_id=detail.location_id
                ).first()
                if not stock_detail or stock_detail.quantity < detail.quantity:
                    insufficient_items.append({
                        'item_name': detail.item_name,
                        'location_name': detail.location_name,
                        'available': stock_detail.quantity if stock_detail else 0,
                        'required': detail.quantity
                    })

            if insufficient_items:
                return {'error': '库存不足', 'details': insufficient_items}

        # 库存充足，执行出库
        stock_out.status = '已审核'
        stock_out.review_user_id = review_user_id
        stock_out.review_time = datetime.now()
        stock_out.review_remark = review_remark

        for detail in stock_out.details:
            # 更新库存明细（按位置减少）
            SupplyStockDetail.subtract_stock(
                item_id=detail.item_id,
                location_id=detail.location_id,
                quantity=detail.quantity,
                operator_user_id=review_user_id
            )
            # 写入进出库记录
            SupplyStockRecord.create_record(
                record_type='出库',
                item_id=detail.item_id,
                location_id=detail.location_id,
                quantity=detail.quantity,
                unit_price=detail.unit_price,
                source_number=stock_out.stock_out_number,
                source_type=stock_out.stock_out_type,
                operator_user_id=review_user_id,
                recipient_user_id=stock_out.recipient_user_id,
                department_id=stock_out.department_id,
                remark=f'出库单{stock_out.stock_out_number}审核通过'
            )

        db.session.commit()
        return stock_out

    @classmethod
    def unapprove(cls, stock_out_id, operator_user_id=None):
        """
        反审核出库单（仅已审核状态可反审核）
        反审核时：
        1. 更新出库单状态为"待审核"
        2. 遍历出库明细，回滚 SupplyStockDetail（按位置增加库存）
        3. 遍历出库明细，回滚 SupplyItem.current_stock（汇总增加）
        4. 新增"出库反审核"进出库记录（保留审核历史，反审核操作留痕）
        """
        from models.supply.supply_stock_detail import SupplyStockDetail
        from models.supply.supply_stock_record import SupplyStockRecord
        from models.supply.supply_item import SupplyItem

        stock_out = cls.query.get(stock_out_id)
        if not stock_out or stock_out.status != '已审核':
            return None

        # 遍历出库明细，回滚库存（出库时减少了库存，反审核需加回来）
        # 直接操作数据库，保证事务一致性
        for detail in stock_out.details:
            # 回滚库存明细（按位置增加）
            stock_detail = SupplyStockDetail.get_or_create(
                item_id=detail.item_id,
                location_id=detail.location_id,
                operator_user_id=operator_user_id
            )
            stock_detail.quantity += detail.quantity
            stock_detail.operator_user_id = operator_user_id

            # 回滚物品汇总库存
            item = SupplyItem.query.get(detail.item_id)
            if item:
                item.current_stock += detail.quantity

            # 新增"出库反审核"进出库记录（保留审核历史，反审核操作留痕）
            record = SupplyStockRecord(
                record_type='出库反审核',
                item_id=detail.item_id,
                item_name=detail.item_name,
                location_id=detail.location_id,
                location_name=detail.location_name,
                quantity=detail.quantity,
                unit_price=detail.unit_price,
                total_price=detail.quantity * detail.unit_price if detail.unit_price else 0,
                source_number=stock_out.stock_out_number,
                source_type=stock_out.stock_out_type,
                operator_user_id=operator_user_id,
                recipient_user_id=stock_out.recipient_user_id,
                department_id=stock_out.department_id,
                remark=f'出库单{stock_out.stock_out_number}反审核，库存回滚'
            )
            db.session.add(record)

        # 更新出库单状态
        stock_out.status = '待审核'
        stock_out.review_user_id = None
        stock_out.review_time = None
        stock_out.review_remark = None

        db.session.commit()
        return stock_out

    @classmethod
    def cancel(cls, stock_out_id, operator_user_id=None):
        """取消出库单（仅待审核状态可取消）"""
        stock_out = cls.query.get(stock_out_id)
        if not stock_out or stock_out.status != '待审核':
            return None
        stock_out.status = '已取消'
        stock_out.operator_user_id = operator_user_id
        db.session.commit()
        return stock_out

    @classmethod
    def recalculate_total_amount(cls, stock_out_id):
        """根据明细重新计算出库总金额"""
        from sqlalchemy import func
        from models.supply.stock_out_detail import StockOutDetail
        total = db.session.query(func.coalesce(func.sum(
            StockOutDetail.quantity * StockOutDetail.unit_price
        ), 0)).filter(StockOutDetail.stock_out_id == stock_out_id).scalar()
        stock_out = cls.query.get(stock_out_id)
        if stock_out:
            stock_out.total_amount = total
            db.session.commit()
        return stock_out