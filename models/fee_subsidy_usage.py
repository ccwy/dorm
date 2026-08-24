from datetime import datetime, timedelta
from utils.db import db  # 数据库实例，封装SQLAlchemy的db对象
from decimal import Decimal  # 用于金额的精确计算，避免浮点数误差
from sqlalchemy.orm import backref, relationship  # 用于定义ORM模型间的关联关系
from flask_login import current_user  # 用于获取当前登录用户

import logging
# 导入主表模型，用于获取总补贴量
from models.fee_subsidy import FeeSubsidy  # 主表模型

class FeeSubsidyUsage(db.Model):
    """费用补贴使用情况子表（支持级联删除）
    功能：详细记录每笔补贴的使用明细，与主表FeeSubsidy通过subsidy_id字段关联
    级联规则：当主表记录被删除时，子表的关联记录会自动删除（数据库级+ORM级双重保障）
    """
    __tablename__ = 'fee_subsidy_usage'  # 数据库表名
    
    # 主键ID
    id = db.Column(
        db.Integer, 
        primary_key=True, 
        autoincrement=True,
        comment="记录的唯一标识符，自增主键"
    )
    
    # 关联主表的外键（级联删除配置）
    subsidy_id = db.Column(
        db.Integer, 
        db.ForeignKey('fee_subsidy.id', ondelete="CASCADE"),  # 数据库级联删除：主表删除时子表自动删除
        nullable=False, 
        comment="关联到补贴主表的ID，非空约束；主表记录删除时，此记录会被自动删除"
    )
    
    # 账期信息（用于区分不同月份的使用记录）
    billing_period = db.Column(
        db.String(7), 
        nullable=False, 
        comment="账期，固定格式为'YYYY-MM'（如'2025-08'），非空约束"
    )
    billing_start_date = db.Column(
        db.DateTime, 
        nullable=False, 
        comment="账期开始日期，精确到秒，固定为当月1日00:00:00"
    )
    billing_end_date = db.Column(
        db.DateTime, 
        nullable=False, 
        comment="账期结束日期，精确到秒，固定为当月最后一天23:59:59"
    )
    
    # 关联信息（根据补贴类型选择性填写）
    room_id = db.Column(
        db.Integer, 
        db.ForeignKey('rooms.id', ondelete='RESTRICT'),
        nullable=True, 
        comment="关联的房间ID；仅房间级补贴需要填写，其他类型可留空，限制删除"
    )
    user_id = db.Column(
        db.Integer, 
        db.ForeignKey('users.id', ondelete='RESTRICT'),
        nullable=True, 
        comment="关联的用户ID；仅个人级补贴需要填写，其他类型可留空，限制删除"
    )
    
    # 同步主表的核心信息（记录使用时的状态）
    fee_type = db.Column(
        db.String(50), 
        nullable=False, 
        comment="补贴类型，与主表FeeSubsidy的fee_type字段保持一致；非空，用于区分补贴种类"
    )
    is_enabled = db.Column(
        db.Boolean, 
        nullable=False, 
        default=True, 
        comment="使用时的启用状态，同步主表在使用时的is_enabled值；非空，主表后续状态变更不影响此记录"
    )
    is_checkout = db.Column(
        db.String(50),
        comment="业务记录，记录当前业务，1退宿费用子表上传、2费用记录主表上传、3费用分摊核算子表上传；可为空，主表后续状态变更不影响此记录"
    )
    # 使用量记录（根据补贴类型填写对应字段）
    used_amount = db.Column(
        db.Numeric(10, 2),  # 总长度10位，其中小数位2位（支持最大9999999.99）
        default=0.00, 
        comment="本账期使用的金额类补贴（单位：元）；默认为0，仅金额类补贴需填写"
    )
    used_electric = db.Column(
        db.Numeric(10, 2), 
        default=0.00, 
        comment="本账期使用的电量减免量（单位：kWh）；默认为0，仅用电量类补贴需填写"
    )
    used_water = db.Column(
        db.Numeric(10, 2), 
        default=0.00, 
        comment="本账期使用的水量减免量（单位：m³）；默认为0，仅用水量类补贴需填写"
    )
    
    # 操作记录（自动记录当前登录用户）
    operator_id = db.Column(
        db.Integer, 
        nullable=False, 
        comment="操作人ID，非空；自动记录当前登录用户的ID，无需手动传入"
    )
    usage_time = db.Column(
        db.DateTime, 
        default=datetime.now, 
        comment="使用记录产生的时间，默认为当前系统时间"
    )
    remark = db.Column(
        db.String(500), 
        comment="使用说明，可选；例如：'抵扣2025-08月电费超额部分'"
    )
    
    # 时间戳（记录生命周期）
    create_time = db.Column(
        db.DateTime, 
        default=datetime.now, 
        comment="记录创建时间，默认为当前时间，创建后不可修改"
    )
    update_time = db.Column(
        db.DateTime, 
        default=datetime.now, 
        onupdate=datetime.now, 
        comment="记录最后更新时间，每次修改记录时自动更新为当前时间"
    )
    
    # ORM关联关系定义
    subsidy = relationship(
        'FeeSubsidy',  # 关联的主表模型
        backref=backref(
            'usage_records',  # 主表通过此属性访问子表记录（如：subsidy.usage_records）
            cascade="all, delete-orphan"  # ORM级联规则：删除主表时删除子表，不允许存在无主表的子表记录
        ),
        lazy=True  # 延迟加载：访问subsidy属性时才实际执行数据库查询
    )

    # 添加与User和Room模型的关联关系
    user = db.relationship('User', backref='fee_subsidy_usage', lazy=True)
    room = db.relationship('Room', backref='fee_subsidy_usage', lazy=True)

    def to_dict(self):
        """将模型实例转换为字典，用于API接口返回数据
        
        返回值：
            dict：包含所有字段的字典，日期类型转换为字符串格式（YYYY-MM-DD HH:MM:SS）
        """
        return {
            'id': self.id,
            'subsidy_id': self.subsidy_id,
            'billing_period': self.billing_period,
            'billing_start_date': self.billing_start_date.strftime('%Y-%m-%d %H:%M:%S') if self.billing_start_date else None,
            'billing_end_date': self.billing_end_date.strftime('%Y-%m-%d %H:%M:%S') if self.billing_end_date else None,
            'room_id': self.room_id,
            'user_id': self.user_id,
            'fee_type': self.fee_type,
            'is_enabled': self.is_enabled,
            'is_checkout': self.is_checkout,# 判断是否为退宿
            'used_amount': float(self.used_amount) if self.used_amount else 0,
            'used_electric': float(self.used_electric) if self.used_electric else 0,
            'used_water': float(self.used_water) if self.used_water else 0,
            'usage_time': self.usage_time.strftime('%Y-%m-%d %H:%M:%S') if self.usage_time else None,
            'operator_id': self.operator_id,  # 自动记录的当前登录用户ID
            'remark': self.remark,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None
        }
    
    @classmethod
    def create_usage_record(cls, subsidy, billing_period, usage_data):
        """创建补贴使用记录（核心方法），自动获取当前登录用户ID作为operator_id
        
        参数：
            subsidy：FeeSubsidy实例，必须，关联的补贴主表记录
            billing_period：str，必须，账期（格式为'YYYY-MM'）
            usage_data：dict，必须，包含使用记录的相关数据，可包含：
                - room_id：int，可选，房间ID（仅房间级补贴需要）
                - user_id：int，可选，用户ID（仅个人级补贴需要）
                - used_amount：Decimal/str/float，可选，金额使用量（默认0.00）
                - used_electric：Decimal/str/float，可选，电费使用量（默认0.00）
                - used_water：Decimal/str/float，可选，水费使用量（默认0.00）
                - remark：str，可选，使用说明（默认空字符串）
                - is_checkout：str，True/False ，记录本次业务，默认空，1为退宿费用子表上传，2为费用核算主表上传，3为费用分摊核算子表上传
        
        返回值：
            FeeSubsidyUsage实例：创建的补贴使用记录对象
        
        异常：
            ValueError：当未检测到登录用户，或参数错误时抛出，包含具体错误信息
        """
        try:
            if not hasattr(current_user, 'id'):
                raise ValueError("未获取到当前登录用户信息，请重新登录")
            # 从上下文获取当前登录用户ID（核心逻辑）
            current_user_id = current_user.id
            
            # 解析账期，计算起止日期
            year, month = map(int, billing_period.split('-'))
            billing_start_date = datetime(year, month, 1)  # 当月1日00:00:00
            next_month = 1 if month == 12 else month + 1
            next_year = year + 1 if month == 12 else year
            billing_end_date = datetime(next_year, next_month, 1) - timedelta(seconds=1)
            
            # 创建记录对象（operator_id自动填充当前登录用户ID）
            usage_record = cls(
                subsidy_id=subsidy.id,
                billing_period=billing_period,
                billing_start_date=billing_start_date,
                billing_end_date=billing_end_date,
                room_id=usage_data.get('room_id'),
                user_id=usage_data.get('user_id'),
                is_checkout=usage_data.get('is_checkout'),
                fee_type=subsidy.fee_type,
                is_enabled=subsidy.is_enabled,
                used_amount=usage_data.get('used_amount', Decimal('0.00')),
                used_electric=usage_data.get('used_electric', Decimal('0.00')),
                used_water=usage_data.get('used_water', Decimal('0.00')),
                operator_id=current_user_id,
                remark=usage_data.get('remark', '')
            )
            
            db.session.add(usage_record)
            return usage_record
        
        except Exception as e:
            #db.session.rollback()
            raise ValueError(f"创建补贴使用记录失败：{str(e)}")
    
    @classmethod
    def get_period_usage(cls, subsidy_id, billing_period):
        """查询指定补贴在指定账期的使用记录"""
        return cls.query.filter(
            cls.subsidy_id == subsidy_id,
            cls.billing_period == billing_period
        ).first()
    
    @classmethod
    def get_total_usage(cls, subsidy_id, billing_period=None):
        """查询指定补贴的使用总量（支持按账期筛选）
        
        参数:
            subsidy_id: 补贴主表ID
            billing_period: 账期（YYYY-MM），为None时查询所有账期累计
        """
        from sqlalchemy import func
        
        # 基础查询条件
        query = cls.query.filter(cls.subsidy_id == subsidy_id)
        
        # 如果指定了账期，则只查询该账期的使用量
        if billing_period:
            query = query.filter(cls.billing_period == billing_period)
        
        # 使用coalesce处理NULL值，确保返回0而非None
        result = query.with_entities(
            func.coalesce(func.sum(cls.used_amount), 0),
            func.coalesce(func.sum(cls.used_electric), 0),
            func.coalesce(func.sum(cls.used_water), 0)
        ).first()
        
        # 强制转换为Decimal后再转float，避免数据库返回类型问题
        try:
            total_amount = float(Decimal(str(result[0]))) if result[0] is not None else 0.0
            total_electric = float(Decimal(str(result[1]))) if result[1] is not None else 0.0
            total_water = float(Decimal(str(result[2]))) if result[2] is not None else 0.0
        except Exception as e:
            logging.error(f"转换使用总量失败: {str(e)}")
            total_amount = 0.0
            total_electric = 0.0
            total_water = 0.0
            
        return {
            'total_amount': total_amount,
            'total_electric': total_electric,
            'total_water': total_water
        }
    
    
    @classmethod
    def get_remaining_usage(cls, subsidy_id, billing_period):
        """查询指定补贴在指定账期的剩余可用额度（主表通过is_enabled控制启用状态）
        
        核心逻辑：
        1. 主表通过is_enabled字段控制启用状态，长期有效（未禁用）
        2. 账期仅用于查询子表中该账期的已使用量
        3. 剩余额度 = 主表总额度 - 该账期子表已使用量
        """
        # 查询主表（仅通过ID，且必须是启用状态的有效主表）
        subsidy = FeeSubsidy.query.filter(
            FeeSubsidy.id == subsidy_id,
            FeeSubsidy.is_enabled == True  # 仅查询启用状态的主表记录
        ).first()
        
        if not subsidy:
            raise ValueError(f"查询剩余补贴失败：ID为{subsidy_id}的补贴记录不存在或已禁用")
        
        # 仅查询当前账期的子表使用量（账期仅用于子表过滤）
        period_used = cls.get_total_usage(subsidy_id, billing_period)
        logging.info(
            f"补贴{subsidy_id}在{billing_period}账期使用情况 - "
            f"主表总金额: {subsidy.amount if subsidy.amount is not None else '未设置'}, "
            f"本账期已使用: {period_used['total_amount']} - "
            f"主表总电费减免: {subsidy.electric_reduction if subsidy.electric_reduction is not None else '未设置'}, "
            f"本账期已使用: {period_used['total_electric']} - "
            f"主表总水费减免: {subsidy.water_reduction if subsidy.water_reduction is not None else '未设置'}, "
            f"本账期已使用: {period_used['total_water']}"
        )
        
        # 初始化剩余量为0
        remaining_amount = 0
        remaining_electric = 0
        remaining_water = 0
        
        # 精确计算当前账期剩余额度（主表总额 - 本账期已用）
        try:
            # 金额类补贴计算
            if subsidy.amount is not None:
                total_amount = Decimal(str(subsidy.amount))
                used_amount = Decimal(str(period_used['total_amount']))
                remaining_amount = max(Decimal('0.00'), total_amount - used_amount)
                remaining_amount = float(remaining_amount)
            
            # 电费减免计算
            if subsidy.electric_reduction is not None:
                total_electric = Decimal(str(subsidy.electric_reduction))
                used_electric = Decimal(str(period_used['total_electric']))
                remaining_electric = max(Decimal('0.00'), total_electric - used_electric)
                remaining_electric = float(remaining_electric)
            
            # 水费减免计算
            if subsidy.water_reduction is not None:
                total_water = Decimal(str(subsidy.water_reduction))
                used_water = Decimal(str(period_used['total_water']))
                remaining_water = max(Decimal('0.00'), total_water - used_water)
                remaining_water = float(remaining_water)
        except Exception as e:
            logging.error(f"计算{billing_period}账期剩余补贴失败: {str(e)}")
            return {'remaining_amount': 0, 'remaining_electric': 0, 'remaining_water': 0}
        
        # 输出剩余额度日志
        logging.info(
            f"补贴{subsidy_id}在{billing_period}账期剩余可用额度 - "
            f"金额: {remaining_amount}, 用电量: {remaining_electric}, 用水量: {remaining_water}"
        )
        return {
            'remaining_amount': remaining_amount,
            'remaining_electric': remaining_electric,
            'remaining_water': remaining_water
        }
