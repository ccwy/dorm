from datetime import datetime
from utils.db import db


class SupplyInventory(db.Model):
    """盘点主表（复刻固定资产盘点方式）"""
    __tablename__ = 'supply_inventories'

    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    inventory_number = db.Column(db.String(50), unique=True, nullable=False, comment='盘点单号（自动生成，如PD2026080001）')
    title = db.Column(db.String(255), nullable=False, comment='盘点标题')
    inventory_date = db.Column(db.Date, nullable=False, comment='盘点日期')

    # 状态
    status = db.Column(db.String(20), default='进行中', nullable=False, comment='盘点状态：进行中/已完成/已取消')

    # 统计字段
    total_count = db.Column(db.Integer, default=0, comment='应盘物品数')
    checked_count = db.Column(db.Integer, default=0, comment='已盘物品数')
    normal_count = db.Column(db.Integer, default=0, comment='正常数')
    abnormal_count = db.Column(db.Integer, default=0, comment='异常数')

    # 备注
    remark = db.Column(db.Text, nullable=True, comment='备注信息')

    # 操作用户
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作用户ID')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 关系定义
    details = db.relationship('SupplyInventoryDetail', backref='supply_inventory', lazy=True, cascade='all, delete-orphan')

    # 约束与索引
    __table_args__ = (
        db.UniqueConstraint('inventory_number', name='uq_supply_inventory_number', comment='盘点单号唯一'),
        db.CheckConstraint(
            "status IN ('进行中', '已完成', '已取消')",
            name='check_supply_inventory_status_valid'
        ),
        db.Index('idx_sinv_inventory_number', 'inventory_number'),
        db.Index('idx_sinv_date', 'inventory_date'),
        db.Index('idx_sinv_status', 'status'),
    )

    def __repr__(self):
        return f"<SupplyInventory {self.inventory_number}: {self.title}>"

    @property
    def display_number(self):
        """返回显示编号"""
        return self.inventory_number

    @property
    def display_status(self):
        """返回状态显示文本"""
        return self.status

    @property
    def creator_name(self):
        """返回创建人姓名"""
        if self.operator_user_id:
            from models.user import User
            user = User.query.get(self.operator_user_id)
            return user.name if user else '未知'
        return '-'

    @property
    def detail_count(self):
        """返回明细数量"""
        return len(self.details)

    @classmethod
    def create(cls, title, inventory_date, remark=None, operator_user_id=None, inventory_number=None):
        """创建盘点单（支持手动指定编号或自动生成）"""
        from models.system_config import SystemConfig
        auto_number = SystemConfig.get_config_value('supply_auto_number', True)
        if inventory_number:
            final_number = inventory_number
        elif auto_number:
            final_number = cls.generate_inventory_number()
        else:
            raise ValueError("自动编号已关闭，请手动输入盘点单号")
        inventory = cls(
            inventory_number=final_number,
            title=title,
            inventory_date=inventory_date,
            status='进行中',
            total_count=0,
            checked_count=0,
            normal_count=0,
            abnormal_count=0,
            remark=remark,
            operator_user_id=operator_user_id
        )
        db.session.add(inventory)
        db.session.commit()
        return inventory

    @classmethod
    def generate_inventory_number(cls):
        """生成盘点单号：前缀+年月+4位序号（前缀从系统配置获取）"""
        from models.system_config import SystemConfig
        prefix_config = SystemConfig.get_config_value('supply_number_prefix', {})
        inventory_prefix = prefix_config.get('inventory', 'PD') if isinstance(prefix_config, dict) else 'PD'
        prefix = inventory_prefix + datetime.now().strftime('%Y%m')
        last = cls.query.filter(
            cls.inventory_number.like(prefix + '%')
        ).order_by(cls.inventory_number.desc()).first()

        if last and last.inventory_number.startswith(prefix):
            try:
                seq = int(last.inventory_number[len(prefix):]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f'{prefix}{seq:04d}'

    @classmethod
    def complete(cls, inventory_id, operator_user_id=None):
        """
        完成盘点 - 更新盘点状态为已完成，调整库存
        完成盘点时：
        1. 更新盘点单状态为"已完成"
        2. 遍历盘点明细，对有差异的明细更新库存
        3. 未盘点的明细自动标记为异常
        4. 写入 SupplyStockRecord（盘点调整记录）
        """
        from models.supply.supply_stock_detail import SupplyStockDetail
        from models.supply.supply_stock_record import SupplyStockRecord

        inventory = cls.query.get(inventory_id)
        if not inventory or inventory.status != '进行中':
            return None

        inventory.status = '已完成'

        surplus_count = 0  # 盘盈数
        shortage_count = 0  # 盘亏数

        # 遍历盘点明细，调整库存
        for detail in inventory.details:
            if detail.inventory_result == '未盘点':
                # 未盘点的自动标记为异常
                detail.inventory_result = '异常'
                inventory.abnormal_count = (inventory.abnormal_count or 0) + 1
                continue

            if detail.inventory_result != '正常' and detail.inventory_result != '异常':
                continue

            # 获取物品在对应位置的当前库存
            stock_detail = SupplyStockDetail.query.filter_by(
                item_id=detail.item_id,
                location_id=detail.location_id
            ).first()

            if stock_detail is None:
                continue

            old_quantity = stock_detail.quantity
            new_quantity = detail.actual_quantity if detail.actual_quantity is not None else old_quantity
            difference = new_quantity - old_quantity

            if difference != 0:
                # 更新库存明细
                SupplyStockDetail.adjust_stock(
                    item_id=detail.item_id,
                    location_id=detail.location_id,
                    new_quantity=new_quantity,
                    operator_user_id=operator_user_id
                )

                # 写入进出库记录
                record_type = '盘盈' if difference > 0 else '盘亏'
                SupplyStockRecord.create_record(
                    record_type=record_type,
                    item_id=detail.item_id,
                    location_id=detail.location_id,
                    quantity=abs(difference),
                    unit_price=detail.unit_price,
                    source_number=inventory.inventory_number,
                    source_type='盘点调整',
                    operator_user_id=operator_user_id,
                    remark=f'盘点单{inventory.inventory_number}完成，{record_type}{abs(difference)}件'
                )

                if difference > 0:
                    surplus_count += 1
                else:
                    shortage_count += 1

        db.session.commit()
        return inventory

    @classmethod
    def cancel(cls, inventory_id, operator_user_id=None):
        """取消盘点单（仅进行中状态可取消）"""
        inventory = cls.query.get(inventory_id)
        if not inventory or inventory.status != '进行中':
            return None
        inventory.status = '已取消'
        inventory.operator_user_id = operator_user_id
        db.session.commit()
        return inventory