from datetime import datetime
from decimal import Decimal
from utils.db import db


class FixedAsset(db.Model):
    """固定资产主表"""
    __tablename__ = 'fixed_assets'

    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    asset_number = db.Column(db.String(50), unique=True, nullable=True, comment='资产编号（允许自定义，留空自动生成）')
    asset_name = db.Column(db.String(255), nullable=False, comment='资产名称')
    asset_category = db.Column(db.String(50), nullable=False, comment='资产分类（从系统配置读取）')

    # 规格与价值
    specification = db.Column(db.String(255), nullable=True, comment='规格型号')
    brand = db.Column(db.String(100), nullable=True, comment='品牌')
    supplier = db.Column(db.String(255), nullable=True, comment='供应商')
    quantity = db.Column(db.Integer, default=1, nullable=False, comment='数量')
    unit = db.Column(db.String(20), default='台', nullable=True, comment='单位')
    original_value = db.Column(db.Numeric(12, 2), default=Decimal('0.00'), nullable=True, comment='原值（元）')
    net_value = db.Column(db.Numeric(12, 2), default=Decimal('0.00'), nullable=True, comment='净值（元）')

    # 日期信息
    purchase_date = db.Column(db.Date, nullable=True, comment='购置日期')
    warranty_expiry = db.Column(db.Date, nullable=True, comment='质保到期日')

    # 位置信息（自由文本输入，不限制）
    storage_location = db.Column(db.String(500), nullable=True, comment='存放位置（自由输入）')

    # 部门信息（通过FK关联departments表）
    company = db.Column(db.String(100), nullable=True, comment='所属公司')
    department_using_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True, comment='使用部门ID')
    department_owning_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True, comment='归属部门ID')

    # 责任人
    responsible_person = db.Column(db.String(50), nullable=True, comment='责任人')

    # 关联房间
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=True, comment='关联房间ID')
    # 关联责任人用户
    responsible_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, comment='责任人用户ID')

    # 来源与状态
    asset_source = db.Column(db.String(20), default='采购', comment='资产来源')
    status = db.Column(db.String(20), default='在用', nullable=False, comment='资产状态')

    # 备注
    remark = db.Column(db.Text, nullable=True, comment='备注信息')

    # 报废信息
    scrap_date = db.Column(db.Date, nullable=True, comment='报废日期')
    scrap_reason = db.Column(db.Text, nullable=True, comment='报废原因')

    # 出售信息
    sale_date = db.Column(db.Date, nullable=True, comment='出售日期')
    sale_price = db.Column(db.Numeric(12, 2), nullable=True, comment='出售金额（元）')
    sale_buyer = db.Column(db.String(255), nullable=True, comment='买方信息')
    sale_remark = db.Column(db.Text, nullable=True, comment='出售备注')

    # 转移信息
    transfer_date = db.Column(db.Date, nullable=True, comment='转移日期')

    # 操作用户
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作用户ID')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 关系定义
    operation_records = db.relationship('AssetOperationRecord', backref='asset', lazy=True, cascade='all, delete-orphan')
    inventory_details = db.relationship('AssetInventoryDetail', backref='asset', lazy=True, cascade='all, delete-orphan')

    # 部门关系映射
    dept_using = db.relationship('Department', foreign_keys=[department_using_id], backref='assets_using_lazy', lazy='select')
    dept_owning = db.relationship('Department', foreign_keys=[department_owning_id], backref='assets_owning_lazy', lazy='select')

    # 关联房间和责任人用户
    room = db.relationship('Room', foreign_keys=[room_id], lazy='select')
    responsible_user = db.relationship('User', foreign_keys=[responsible_user_id], lazy='select')

    # 便捷属性：通过relationship返回部门名称字符串，供模板使用
    @property
    def department_using(self):
        """返回使用部门名称"""
        if self.dept_using:
            return self.dept_using.name
        return None

    @property
    def department_owning(self):
        """返回归属部门名称"""
        if self.dept_owning:
            return self.dept_owning.name
        return None

    @property
    def room_display(self):
        """返回楼栋+房间号"""
        if self.room:
            return f"{self.room.building}{self.room.room_number}"
        return None

    @property
    def responsible_user_name(self):
        """返回责任人姓名"""
        if self.responsible_user:
            return self.responsible_user.name
        return None

    # 删除联动说明：删除资产时，数据库级联删除 operation_records 和 inventory_details；
    # 磁盘上的照片文件需在删除路由中显式调用 AssetPhotoManager.delete_all_files(asset_id) 清理照片目录。
    # 删除操作仅写入 OperationLog(module='asset') 记录摘要，因为 AssetOperationRecord 会被级联删除。

    # 约束与索引
    __table_args__ = (
        db.CheckConstraint('quantity > 0', name='check_quantity_positive'),
        db.CheckConstraint(
            "status IN ('在用', '闲置', '维修中', '已报废', '已转移', '已出售')",
            name='check_asset_status_valid'
        ),
        db.CheckConstraint(
            "asset_source IN ('采购', '捐赠', '调入', '自建', '其他')",
            name='check_asset_source_valid'
        ),
        db.Index('idx_asset_number', 'asset_number'),
        db.Index('idx_asset_category', 'asset_category'),
        db.Index('idx_asset_status', 'status'),
        db.Index('idx_asset_dept_using_id', 'department_using_id'),
        db.Index('idx_asset_dept_owning_id', 'department_owning_id'),
        db.Index('idx_asset_company', 'company'),
        db.Index('idx_asset_location', 'storage_location'),
        db.Index('idx_asset_purchase_date', 'purchase_date'),
        db.Index('idx_asset_scrap_date', 'scrap_date'),
        db.Index('idx_asset_sale_date', 'sale_date'),
        db.Index('idx_asset_room_id', 'room_id'),
        db.Index('idx_asset_responsible_user_id', 'responsible_user_id'),
    )

    def __repr__(self):
        return f"<FixedAsset {self.asset_number or self.id}: {self.asset_name}>"

    @property
    def display_number(self):
        """返回资产编号，若为空则返回自增ID格式"""
        return self.asset_number or f"ZC{self.id:06d}"

    @classmethod
    def generate_asset_number(cls):
        """自动生成资产编号：ZC + 年月 + 4位序号"""
        today = datetime.now()
        prefix = f"ZC{today.strftime('%Y%m')}"
        last_asset = cls.query.filter(
            cls.asset_number.like(f"{prefix}%")
        ).order_by(cls.id.desc()).first()
        if last_asset and last_asset.asset_number:
            try:
                seq = int(last_asset.asset_number[-4:]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        return f"{prefix}{seq:04d}"

    @classmethod
    def create(cls, asset_number=None, asset_name=None, asset_category=None,
               specification=None, brand=None, supplier=None, quantity=1, unit='台',
               original_value=None, net_value=None, purchase_date=None,
               warranty_expiry=None, storage_location=None,
               department_using_id=None, department_owning_id=None,
               company=None,
               responsible_person=None, asset_source=None, status=None,
               remark=None, operator_user_id=None,
               room_id=None, responsible_user_id=None):
        """创建固定资产

        参数说明：
        - department_using_id/department_owning_id: 部门FK ID
        - company: 所属公司
        - room_id: 关联房间ID
        - responsible_user_id: 责任人用户ID
        """
        asset = cls(
            asset_number=asset_number,
            asset_name=asset_name,
            asset_category=asset_category,
            specification=specification,
            brand=brand,
            supplier=supplier or None,
            quantity=quantity,
            unit=unit,
            original_value=original_value or Decimal('0.00'),
            net_value=net_value or Decimal('0.00'),
            purchase_date=purchase_date,
            warranty_expiry=warranty_expiry,
            storage_location=storage_location,
            department_using_id=department_using_id,
            department_owning_id=department_owning_id,
            company=company,
            responsible_person=responsible_person,
            asset_source=asset_source or '采购',
            status=status or '在用',
            remark=remark,
            operator_user_id=operator_user_id,
            room_id=room_id,
            responsible_user_id=responsible_user_id
        )

        db.session.add(asset)
        db.session.flush()  # 获取ID用于自动编号
        if not asset.asset_number:
            asset.asset_number = cls.generate_asset_number()
        db.session.commit()
        return asset