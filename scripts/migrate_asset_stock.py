"""
数据迁移脚本：为已有固定资产创建库存明细初始记录
将主表的quantity、storage_location、room_id、company、department_using_id、
department_owning_id、responsible_person、responsible_user_id等字段
迁移到AssetStockItem库存明细表中，并创建对应的"新增入库"变动记录。

使用方法：
    cd dorm项目根目录
    python -m scripts.migrate_asset_stock
"""

import sys
import os

# 确保项目根目录在sys.path中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from models.fixed_asset.fixed_asset import FixedAsset
from models.fixed_asset.asset_stock_item import AssetStockItem
from models.fixed_asset.asset_stock_record import AssetStockRecord


def migrate():
    app = create_app()
    with app.app_context():
        # 检查表是否存在
        inspector = db.inspect(db.engine)
        existing_tables = inspector.get_table_names()
        
        if 'asset_stock_items' not in existing_tables:
            print("错误：asset_stock_items表不存在，请先运行数据库迁移创建新表")
            return
        
        if 'asset_stock_records' not in existing_tables:
            print("错误：asset_stock_records表不存在，请先运行数据库迁移创建新表")
            return

        # 获取所有未删除的固定资产
        assets = FixedAsset.query.filter(FixedAsset.is_deleted == False).all()
        print(f"找到 {len(assets)} 条未删除的固定资产记录")

        migrated = 0
        skipped = 0

        for asset in assets:
            # 检查是否已有库存明细
            existing_items = AssetStockItem.query.filter_by(asset_id=asset.id).all()
            if existing_items:
                skipped += 1
                continue

            # 创建库存明细记录
            if asset.quantity and asset.quantity > 0:
                stock_item = AssetStockItem(
                    asset_id=asset.id,
                    storage_location=asset.storage_location or '',
                    room_id=asset.room_id,
                    company=asset.company or '',
                    department_using_id=asset.department_using_id,
                    department_owning_id=asset.department_owning_id,
                    responsible_person=asset.responsible_person or '',
                    responsible_user_id=asset.responsible_user_id,
                    quantity=asset.quantity
                )
                db.session.add(stock_item)

                # 创建入库变动记录
                stock_record = AssetStockRecord(
                    asset_id=asset.id,
                    record_type='入库',
                    record_subtype='新增入库',
                    quantity=asset.quantity,
                    from_stock_item_id=None,
                    to_stock_item_id=None,
                    storage_location=asset.storage_location or '',
                    room_id=asset.room_id,
                    company=asset.company or '',
                    department_using_id=asset.department_using_id,
                    department_owning_id=asset.department_owning_id,
                    operator_id=None,
                    remark='数据迁移：初始库存记录'
                )
                db.session.add(stock_record)
                migrated += 1
            else:
                skipped += 1

        if migrated > 0:
            db.session.commit()
            print(f"迁移完成：成功创建 {migrated} 条库存明细和变动记录")
        else:
            print("无需迁移：所有资产已有库存明细或数量为0")

        if skipped > 0:
            print(f"跳过 {skipped} 条记录（已有库存明细或数量为0）")


if __name__ == '__main__':
    migrate()