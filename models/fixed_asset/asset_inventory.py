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
    def unapprove(cls, inventory_id, operator_user_id=None, operator_name=None):
        """
        反审核盘点单（仅已完成状态可反审核）
        反审核时：
        1. 检查盘盈资产库存明细数量是否充足（扣减后不能为0以下）
        2. 更新盘点单状态为"进行中"
        3. 遍历有差异的盘点明细，按库存明细维度回滚：
           - 盘盈的：恢复到账面数量（反盘盈，减少库存明细数量）
           - 部分盘亏的：恢复到账面数量（反盘亏，增加库存明细数量）
           - 全部盘亏的：恢复资产状态和数量（反盘亏报废，恢复库存明细数量）
        4. 新增"inventory_unapprove"操作记录（保留审核历史，反审核操作留痕）
        """
        from .fixed_asset import FixedAsset
        from .asset_inventory_detail import AssetInventoryDetail
        from .asset_operation_record import AssetOperationRecord
        from .asset_stock_item import AssetStockItem
        from .asset_stock_record import AssetStockRecord

        inventory = cls.query.get(inventory_id)
        if not inventory or inventory.status != '已完成':
            return None

        details = AssetInventoryDetail.query.filter_by(inventory_id=inventory_id).all()

        # 第一遍：检查盘盈库存明细数量充足性（扣减后不能<=0）
        insufficient_items = []
        for detail in details:
            if detail.inventory_result == '未盘点':
                continue
            asset = FixedAsset.query.get(detail.asset_id) if detail.asset_id else None
            if not asset:
                continue

            book_qty = detail.book_quantity if detail.book_quantity is not None else None
            actual_qty = detail.actual_quantity

            if book_qty is None or actual_qty is None:
                continue

            diff = actual_qty - book_qty
            # 盘盈的：完成时增加了库存明细数量，反审核需要扣减回账面数量
            if diff > 0:
                stock_item = AssetStockItem.query.get(detail.stock_item_id) if detail.stock_item_id else None
                current_qty = stock_item.quantity if stock_item else asset.quantity
                deduct_amount = diff  # 需要扣减的量
                if current_qty < deduct_amount:
                    insufficient_items.append({
                        'asset_name': asset.asset_name,
                        'asset_number': asset.asset_number,
                        'current_quantity': current_qty,
                        'need_deduct': deduct_amount,
                        'unit': asset.unit or '台'
                    })

        if insufficient_items:
            return {'error': '盘盈资产数量不足，无法反审核', 'details': insufficient_items}

        # 第二遍：执行回滚
        for detail in details:
            if detail.inventory_result == '未盘点':
                continue
            asset = FixedAsset.query.get(detail.asset_id) if detail.asset_id else None
            if not asset:
                continue

            book_qty = detail.book_quantity if detail.book_quantity is not None else None
            book_status = detail.book_status
            actual_qty = detail.actual_quantity

            # 没有book_quantity的旧数据，无法安全回滚，跳过
            if book_qty is None or actual_qty is None:
                continue

            diff = actual_qty - book_qty

            if diff == 0:
                # 无数量差异，无需回滚数量
                continue

            old_quantity = asset.quantity
            old_status = asset.status
            stock_item = AssetStockItem.query.get(detail.stock_item_id) if detail.stock_item_id else None

            if diff > 0:
                # 盘盈：反审核恢复到账面数量，减少库存明细
                if stock_item:
                    stock_item.quantity = book_qty
                    stock_item.updated_at = datetime.now()
                    asset.quantity = sum(item.quantity for item in asset.stock_items)
                    AssetStockRecord.create_record(
                        record_type='出库',
                        record_subtype='盘亏',
                        asset_id=asset.id,
                        quantity=abs(diff),
                        from_stock_item_id=stock_item.id,
                        storage_location=stock_item.storage_location,
                        room_id=stock_item.room_id,
                        company=stock_item.company,
                        department_using_id=stock_item.department_using_id,
                        department_owning_id=stock_item.department_owning_id,
                        operator_user_id=operator_user_id,
                        operator_name=operator_name,
                        remark=f'盘点反审核-反盘盈：数量从{actual_qty}{asset.unit or "台"}扣减{abs(diff)}{asset.unit or "台"}至{book_qty}{asset.unit or "台"}'
                    )
                else:
                    asset.quantity = book_qty
                change_type = '反盘盈'
                summary = f"盘点反审核-反盘盈：{asset.asset_name}，数量从{old_quantity}{asset.unit or '台'}扣减{diff}{asset.unit or '台'}至{asset.quantity}{asset.unit or '台'}"
            else:
                # 盘亏：反审核恢复到账面数量，增加库存明细
                if stock_item:
                    stock_item.quantity = book_qty
                    stock_item.updated_at = datetime.now()
                    asset.quantity = sum(item.quantity for item in asset.stock_items)
                    AssetStockRecord.create_record(
                        record_type='入库',
                        record_subtype='盘盈',
                        asset_id=asset.id,
                        quantity=abs(diff),
                        to_stock_item_id=stock_item.id,
                        storage_location=stock_item.storage_location,
                        room_id=stock_item.room_id,
                        company=stock_item.company,
                        department_using_id=stock_item.department_using_id,
                        department_owning_id=stock_item.department_owning_id,
                        operator_user_id=operator_user_id,
                        operator_name=operator_name,
                        remark=f'盘点反审核-反盘亏：数量从{actual_qty}{asset.unit or "台"}恢复{abs(diff)}{asset.unit or "台"}至{book_qty}{asset.unit or "台"}'
                    )
                else:
                    asset.quantity = book_qty
                change_type = '反盘亏'

                if actual_qty == 0 and book_status:
                    # 全部盘亏：还需恢复资产状态（完成盘点时设为了已报废）
                    asset.status = book_status
                    # 清除盘亏报废时设置的字段
                    if asset.scrap_reason == '盘亏报废':
                        asset.scrap_date = None
                        asset.scrap_reason = None
                    summary = f"盘点反审核-反盘亏报废：{asset.asset_name}，数量恢复为{book_qty}{asset.unit or '台'}，状态从{old_status}恢复为{book_status}"
                else:
                    # 部分盘亏：仅恢复数量
                    summary = f"盘点反审核-反盘亏：{asset.asset_name}，数量从{old_quantity}{asset.unit or '台'}恢复{-diff}{asset.unit or '台'}至{asset.quantity}{asset.unit or '台'}"

            change_detail = {
                'inventory_id': inventory_id,
                'inventory_number': inventory.inventory_number,
                'asset_id': asset.id,
                'asset_name': asset.asset_name,
                'operation': 'unapprove',
                'old_quantity': old_quantity,
                'new_quantity': asset.quantity,
                'book_quantity': book_qty,
                'actual_quantity': actual_qty,
                'difference': -diff,
                'stock_item_id': detail.stock_item_id,
                'remark': f'盘点反审核，{change_type}'
            }

            if old_status != asset.status:
                change_detail['old_status'] = old_status
                change_detail['new_status'] = asset.status

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