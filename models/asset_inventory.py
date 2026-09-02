from datetime import datetime
from utils.db import db


class AssetInventory(db.Model):
    """资产盘点主表"""
    __tablename__ = 'asset_inventories'

    id = db.Column(db.Integer, primary_key=True)
    inventory_number = db.Column(db.String(50), unique=True, nullable=False, comment='盘点单号')
    title = db.Column(db.String(255), nullable=False, comment='盘点标题')
    inventory_date = db.Column(db.Date, nullable=False, comment='盘点日期')
    status = db.Column(db.String(20), default='进行中', nullable=False, comment='盘点状态：进行中/已完成/已取消')
    total_count = db.Column(db.Integer, default=0, comment='应盘资产数')
    checked_count = db.Column(db.Integer, default=0, comment='已盘资产数')
    normal_count = db.Column(db.Integer, default=0, comment='正常数')
    abnormal_count = db.Column(db.Integer, default=0, comment='异常数')
    remark = db.Column(db.Text, nullable=True, comment='备注')
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作用户ID')
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 关系
    details = db.relationship('AssetInventoryDetail', backref='inventory', lazy=True, cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('idx_inventory_number', 'inventory_number'),
        db.Index('idx_inventory_status', 'status'),
        db.Index('idx_inventory_date', 'inventory_date'),
    )

    @classmethod
    def unapprove(cls, inventory_id, operator_user_id=None):
        """
        反审核盘点单（仅已完成状态可反审核）
        反审核时：
        1. 检查盘盈资产数量是否充足（扣减后不能为0以下）
        2. 更新盘点单状态为"进行中"
        3. 遍历有差异的盘点明细，回滚资产数量：
           - 盘盈的：扣减资产数量（反盘盈）
           - 盘亏的：恢复资产数量（反盘亏）
        4. 新增"inventory_unapprove"操作记录（保留审核历史，反审核操作留痕）
        """
        from models.fixed_asset import FixedAsset
        from models.asset_inventory_detail import AssetInventoryDetail
        from models.asset_operation_record import AssetOperationRecord

        inventory = cls.query.get(inventory_id)
        if not inventory or inventory.status != '已完成':
            return None

        details = AssetInventoryDetail.query.filter_by(inventory_id=inventory_id).all()

        # 检查盘盈资产数量充足性（扣减后不能为0以下）
        insufficient_items = []
        for detail in details:
            if detail.inventory_result == '未盘点':
                continue
            asset = FixedAsset.query.get(detail.asset_id) if detail.asset_id else None
            if not asset:
                continue
            if detail.actual_quantity is not None and detail.actual_quantity != asset.quantity:
                diff = detail.actual_quantity - asset.quantity
                # 盘盈的：完成时增加了数量，反审核需要扣减
                if diff > 0:
                    if asset.quantity < diff:
                        insufficient_items.append({
                            'asset_name': asset.asset_name,
                            'asset_number': asset.asset_number,
                            'current_quantity': asset.quantity,
                            'need_deduct': diff
                        })

        if insufficient_items:
            return {'error': '盘盈资产数量不足，无法反审核', 'details': insufficient_items}

        # 执行回滚：盘盈扣减/盘亏恢复 + 创建反审核操作记录
        for detail in details:
            if detail.inventory_result == '未盘点':
                continue
            asset = FixedAsset.query.get(detail.asset_id) if detail.asset_id else None
            if not asset:
                continue

            if detail.actual_quantity is not None and detail.actual_quantity != asset.quantity:
                old_quantity = asset.quantity
                diff = detail.actual_quantity - old_quantity

                if diff > 0:
                    # 盘盈：反审核扣减数量
                    asset.quantity = old_quantity - diff
                    change_type = '反盘盈'
                    summary = f"盘点反审核-反盘盈：{asset.asset_name}，数量从{old_quantity}{asset.unit or '台'}扣减{diff}{asset.unit or '台'}至{asset.quantity}{asset.unit or '台'}"
                else:
                    # 盘亏：反审核恢复数量
                    asset.quantity = old_quantity - diff  # diff为负，减负等于加
                    change_type = '反盘亏'
                    summary = f"盘点反审核-反盘亏：{asset.asset_name}，数量从{old_quantity}{asset.unit or '台'}恢复{-diff}{asset.unit or '台'}至{asset.quantity}{asset.unit or '台'}"

                change_detail = {
                    'inventory_id': inventory_id,
                    'inventory_number': inventory.inventory_number,
                    'asset_id': asset.id,
                    'asset_name': asset.asset_name,
                    'operation': 'unapprove',
                    'old_quantity': old_quantity,
                    'new_quantity': asset.quantity,
                    'difference': -diff,
                    'remark': f'盘点反审核，{change_type}'
                }

                AssetOperationRecord.create_record(
                    asset_id=asset.id,
                    operation_type='inventory_unapprove',
                    operator_id=operator_user_id,
                    change_detail=change_detail,
                    summary=summary
                )

        inventory.status = '进行中'
        db.session.commit()
        return inventory

    def __repr__(self):
        return f"<AssetInventory {self.inventory_number}: {self.title}>"