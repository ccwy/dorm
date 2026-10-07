from datetime import datetime, date
from decimal import Decimal
from utils.db import db


class PaymentRecord(db.Model):
    """付款记录表 - 管理合同的付款记录"""
    __tablename__ = 'payment_records'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id', ondelete='CASCADE'), nullable=False, comment='关联合同ID')
    payment_number = db.Column(db.String(50), unique=True, nullable=True, comment='付款编号（自动生成，如PAY-2026-001）')

    # 从合同带入的付款方案字段（只读）
    payment_method = db.Column(db.String(50), nullable=True, comment='付款方式（从合同带入）')
    fixed_amount = db.Column(db.Numeric(14, 2), nullable=True, comment='固定金额（从合同带入）')
    payment_rounds = db.Column(db.Integer, nullable=True, comment='付款轮次（从合同带入）')
    current_round = db.Column(db.Integer, nullable=True, comment='当前第几轮付款')
    plan_start_date = db.Column(db.Integer, nullable=True, comment='每月准备日（1-31数字，从合同带入）')
    plan_end_date = db.Column(db.Integer, nullable=True, comment='每月截止日（1-31数字，从合同带入）')

    # 付款记录自身字段
    payment_period = db.Column(db.String(20), nullable=True, comment='付款周期（如2026-10）')
    planned_payment_date = db.Column(db.Date, nullable=True, comment='计划付款日期')
    deadline_date = db.Column(db.Date, nullable=True, comment='截止付款日期')
    planned_amount = db.Column(db.Numeric(14, 2), default=Decimal('0.00'), nullable=True, comment='计划付款金额（元）')
    actual_amount = db.Column(db.Numeric(14, 2), nullable=True, comment='实际付款金额（元）')
    payment_date = db.Column(db.Date, nullable=True, comment='实际付款日期')
    status = db.Column(db.String(20), default='待付款', nullable=False, comment='状态：待付款/已付款/已逾期/已取消')
    remark = db.Column(db.Text, nullable=True, comment='备注')

    # 操作信息
    operator_id = db.Column(db.Integer, nullable=True, comment='操作人ID')
    operator_name = db.Column(db.String(50), nullable=True, comment='操作人姓名')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 关系
    contract = db.relationship('Contract', backref='payment_records', lazy='select')

    # 索引
    __table_args__ = (
        db.Index('idx_pr_contract_id', 'contract_id'),
        db.Index('idx_pr_status', 'status'),
        db.Index('idx_pr_payment_period', 'payment_period'),
        db.Index('idx_pr_payment_date', 'payment_date'),
        db.Index('idx_pr_planned_payment_date', 'planned_payment_date'),
        db.CheckConstraint(
            "status IN ('待付款', '已付款', '已逾期', '已取消')",
            name='check_payment_status_valid'
        ),
    )

    def __repr__(self):
        return f"<PaymentRecord {self.payment_number}>"

    @property
    def display_status(self):
        """显示状态"""
        status_map = {
            '待付款': '待付款',
            '已付款': '已付款',
            '已逾期': '已逾期',
            '已取消': '已取消'
        }
        return status_map.get(self.status, self.status)

    @property
    def status_color(self):
        """状态颜色"""
        color_map = {
            '待付款': 'amber',
            '已付款': 'green',
            '已逾期': 'red',
            '已取消': 'gray'
        }
        return color_map.get(self.status, 'gray')

    @classmethod
    def create(cls, contract_id, payment_number=None, payment_method=None,
               fixed_amount=None, payment_rounds=None, current_round=None, plan_start_date=None, plan_end_date=None,
               payment_period=None, planned_payment_date=None, deadline_date=None,
               planned_amount=None, actual_amount=None, payment_date=None,
               status='待付款', remark=None, operator_id=None, operator_name=None):
        """创建付款记录"""
        record = cls(
            contract_id=contract_id,
            payment_number=payment_number,
            payment_method=payment_method,
            fixed_amount=fixed_amount,
            payment_rounds=payment_rounds,
            current_round=current_round,
            plan_start_date=plan_start_date,
            plan_end_date=plan_end_date,
            payment_period=payment_period,
            planned_payment_date=planned_payment_date,
            deadline_date=deadline_date,
            planned_amount=planned_amount or Decimal('0.00'),
            actual_amount=actual_amount,
            payment_date=payment_date,
            status=status,
            remark=remark,
            operator_id=operator_id,
            operator_name=operator_name
        )
        db.session.add(record)
        db.session.commit()
        return record

    @classmethod
    def generate_payment_number(cls):
        """生成付款编号"""
        today = date.today()
        prefix = f"PAY-{today.strftime('%Y')}-"
        # 查找当年最大编号
        last_record = cls.query.filter(
            cls.payment_number.like(f"{prefix}%")
        ).order_by(cls.id.desc()).first()
        if last_record and last_record.payment_number:
            try:
                num = int(last_record.payment_number.replace(prefix, ''))
                return f"{prefix}{num + 1:03d}"
            except ValueError:
                pass
        return f"{prefix}001"

    @classmethod
    def update_overdue_status(cls):
        """更新逾期状态：将超过截止日期仍未付款的记录标记为已逾期"""
        today = date.today()
        overdue_records = cls.query.filter(
            cls.status == '待付款',
            cls.deadline_date < today
        ).all()
        for record in overdue_records:
            record.status = '已逾期'
        db.session.commit()
        return len(overdue_records)