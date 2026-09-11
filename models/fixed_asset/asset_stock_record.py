from datetime import datetime
from utils.db import db


class AssetStockRecord(db.Model):
    """资产库存变动记录表 - 记录所有入库、出库、转移操作的结构化明细"""
    __tablename__ = 'asset_stock_records'

    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    record_type = db.Column(db.String(20), nullable=False, comment='变动类型：入库/出库/转移')
    record_subtype = db.Column(db.String(20), nullable=False, comment='子类型：新增入库/报废出库/出售出库/转移调拨/编辑调整/盘盈/盘亏')
    record_date = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='变动时间')

    # 资产关联
    asset_id = db.Column(db.Integer, db.ForeignKey('fixed_assets.id', ondelete='CASCADE'), nullable=False, comment='关联资产ID')
    asset_name = db.Column(db.String(255), nullable=True, comment='资产名称（冗余存储）')

    # 数量
    quantity = db.Column(db.Integer, nullable=False, comment='变动数量（正数）')

    # 源/目标库存明细（出库/转移时记录源，入库/转移时记录目标）
    from_stock_item_id = db.Column(db.Integer, db.ForeignKey('asset_stock_items.id', ondelete='SET NULL'), nullable=True, comment='源库存明细ID（出库/转移时）')
    to_stock_item_id = db.Column(db.Integer, db.ForeignKey('asset_stock_items.id', ondelete='SET NULL'), nullable=True, comment='目标库存明细ID（入库/转移时）')

    # 位置信息（冗余存储，便于查询展示）
    storage_location = db.Column(db.String(500), nullable=True, comment='存放位置（冗余存储）')
    room_id = db.Column(db.Integer, nullable=True, comment='关联房间ID（冗余存储）')
    company = db.Column(db.String(100), nullable=True, comment='所属公司（冗余存储）')
    department_using_id = db.Column(db.Integer, nullable=True, comment='使用部门ID（冗余存储）')
    department_owning_id = db.Column(db.Integer, nullable=True, comment='归属部门ID（冗余存储）')

    # 转移时的目标位置信息
    to_storage_location = db.Column(db.String(500), nullable=True, comment='转移目标存放位置')
    to_room_id = db.Column(db.Integer, nullable=True, comment='转移目标房间ID')
    to_company = db.Column(db.String(100), nullable=True, comment='转移目标所属公司')
    to_department_using_id = db.Column(db.Integer, nullable=True, comment='转移目标使用部门ID')
    to_department_owning_id = db.Column(db.Integer, nullable=True, comment='转移目标归属部门ID')

    # 操作用户
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作用户ID')
    operator_name = db.Column(db.String(50), nullable=True, comment='操作人姓名')

    # 备注
    remark = db.Column(db.Text, nullable=True, comment='备注信息')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')

    # 关系定义
    asset = db.relationship('FixedAsset', foreign_keys=[asset_id], backref=db.backref('stock_records', lazy=True, cascade='all, delete-orphan'))

    # 约束与索引
    __table_args__ = (
        db.CheckConstraint(
            "record_type IN ('入库', '出库', '转移')",
            name='check_asset_stock_record_type_valid'
        ),
        db.CheckConstraint(
            "record_subtype IN ('新增入库', '报废出库', '出售出库', '转移调拨', '编辑调整', '盘盈', '盘亏')",
            name='check_asset_stock_record_subtype_valid'
        ),
        db.CheckConstraint(
            'quantity > 0',
            name='check_asset_stock_record_quantity_positive'
        ),
        db.Index('idx_asr_record_type', 'record_type'),
        db.Index('idx_asr_record_date', 'record_date'),
        db.Index('idx_asr_asset_id', 'asset_id'),
        db.Index('idx_asr_asset_date', 'asset_id', 'record_date'),
        db.Index('idx_asr_from_stock_item', 'from_stock_item_id'),
        db.Index('idx_asr_to_stock_item', 'to_stock_item_id'),
    )

    def __repr__(self):
        return f"<AssetStockRecord {self.record_type}/{self.record_subtype} asset={self.asset_id} qty={self.quantity}>"

    @property
    def display_record_type(self):
        """返回变动类型显示文本"""
        type_map = {
            '入库': '📥 入库',
            '出库': '📤 出库',
            '转移': '🔄 转移'
        }
        return type_map.get(self.record_type, self.record_type)

    @property
    def display_record_subtype(self):
        """返回子类型显示文本"""
        subtype_map = {
            '新增入库': '新增入库',
            '报废出库': '报废出库',
            '出售出库': '出售出库',
            '转移调拨': '转移调拨',
            '编辑调整': '编辑调整',
            '盘盈': '盘盈',
            '盘亏': '盘亏'
        }
        return subtype_map.get(self.record_subtype, self.record_subtype)

    @classmethod
    def create_record(cls, asset_id, record_type, record_subtype, quantity,
                      from_stock_item_id=None, to_stock_item_id=None,
                      storage_location=None, room_id=None, company=None,
                      department_using_id=None, department_owning_id=None,
                      to_storage_location=None, to_room_id=None, to_company=None,
                      to_department_using_id=None, to_department_owning_id=None,
                      operator_user_id=None, operator_name=None, remark=None):
        """创建库存变动记录"""
        # 获取资产名称
        from models.fixed_asset.fixed_asset import FixedAsset
        asset = FixedAsset.query.get(asset_id)
        asset_name = asset.asset_name if asset else '未知'

        record = cls(
            asset_id=asset_id,
            record_type=record_type,
            record_subtype=record_subtype,
            quantity=quantity,
            asset_name=asset_name,
            from_stock_item_id=from_stock_item_id,
            to_stock_item_id=to_stock_item_id,
            storage_location=storage_location,
            room_id=room_id,
            company=company,
            department_using_id=department_using_id,
            department_owning_id=department_owning_id,
            to_storage_location=to_storage_location,
            to_room_id=to_room_id,
            to_company=to_company,
            to_department_using_id=to_department_using_id,
            to_department_owning_id=to_department_owning_id,
            operator_user_id=operator_user_id,
            operator_name=operator_name,
            remark=remark
        )
        db.session.add(record)
        return record