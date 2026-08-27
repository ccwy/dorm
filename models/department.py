from datetime import datetime
from utils.db import db


class Department(db.Model):
    """部门表 - 统一管理部门字典"""
    __tablename__ = 'departments'

    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, comment='部门名称')
    company = db.Column(db.String(100), nullable=True, comment='所属公司')
    description = db.Column(db.String(500), nullable=True, comment='部门描述')
    created_date = db.Column(db.Date, nullable=True, comment='新增日期')
    status = db.Column(db.String(10), nullable=False, default='正常', comment='状态（正常/停用）')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 约束与索引
    __table_args__ = (
        db.UniqueConstraint('name', 'company', name='uq_department_name_company', comment='同公司下部门名称唯一'),
        db.Index('idx_department_name', 'name'),
        db.Index('idx_department_company', 'company'),
    )

    def __repr__(self):
        return f"<Department {self.name} ({self.company})>"

    @classmethod
    def get_all_names(cls):
        """获取所有部门名称列表（用于同步SystemConfig）"""
        departments = cls.query.order_by(cls.name).all()
        return [d.name for d in departments]

    @classmethod
    def get_all_companies(cls):
        """获取所有公司列表（去重，用于同步SystemConfig的COMPANIES配置项）"""
        companies = db.session.query(cls.company).filter(cls.company.isnot(None), cls.company != '').distinct().order_by(cls.company).all()
        return [c[0] for c in companies]

    @classmethod
    def get_by_company(cls, company):
        """根据公司名称获取部门列表"""
        return cls.query.filter_by(company=company).order_by(cls.name).all()

    @classmethod
    def get_active_by_company(cls, company):
        """获取指定公司下状态为正常的部门列表"""
        if company:
            return cls.query.filter_by(company=company, status='正常').order_by(cls.name).all()
        else:
            return cls.query.filter_by(company=None, status='正常').order_by(cls.name).all()

    @classmethod
    def is_name_exists(cls, name, company=None, exclude_id=None):
        """检查部门名称是否已存在（同公司下名称唯一）"""
        query = cls.query.filter_by(name=name)
        if company:
            query = query.filter(db.or_(cls.company == company, cls.company.is_(None)))
        else:
            query = query.filter(cls.company.is_(None))
        if exclude_id:
            query = query.filter(cls.id != exclude_id)
        return query.first() is not None

    @classmethod
    def check_usage(cls, dept_id):
        """
        检查部门是否被使用，返回使用信息字典
        参数: dept_id - 部门ID（整数）
        """
        from models.user import User
        from models.fixed_asset import FixedAsset

        dept = cls.query.get(dept_id)
        if not dept:
            return {
                'used': False,
                'details': {
                    'user_count': 0,
                    'asset_using_count': 0,
                    'asset_owning_count': 0
                }
            }
        dept_name = dept.name

        # 检查 User.department_id（FK关联）
        user_count = User.query.filter_by(department_id=dept_id).count()

        # 检查 FixedAsset FK字段
        asset_using_count = FixedAsset.query.filter_by(department_using_id=dept_id).count()
        asset_owning_count = FixedAsset.query.filter_by(department_owning_id=dept_id).count()

        used = (user_count > 0 or asset_using_count > 0 or asset_owning_count > 0)

        return {
            'used': used,
            'details': {
                'user_count': user_count,
                'asset_using_count': asset_using_count,
                'asset_owning_count': asset_owning_count,
                'dept_name': dept_name
            }
        }

    @classmethod
    def create(cls, name, description=None, company=None, created_date=None, status='正常'):
        """创建部门"""
        department = cls(name=name, description=description, company=company, created_date=created_date, status=status)
        db.session.add(department)
        db.session.commit()
        return department

    @classmethod
    def get_all_statuses(cls):
        """获取所有状态列表"""
        return ['正常', '停用']

    @classmethod
    def get_name_by_id(cls, dept_id):
        """根据ID获取部门名称"""
        dept = cls.query.get(dept_id)
        return dept.name if dept else None

