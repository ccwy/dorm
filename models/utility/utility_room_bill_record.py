from datetime import datetime, timedelta
from sqlalchemy.orm import relationship, backref
from utils.db import db
import logging
from decimal import Decimal  # 使用Decimal处理财务数据
from models.system_config.system_config import SystemConfig # 导入系统配置模型
from models.room.room import Room  # 新增：导入Room模型
from models.fee_subsidy.fee_subsidy import FeeSubsidy  # 费用补贴主表
from models.fee_subsidy.fee_subsidy_usage import FeeSubsidyUsage  # 导入费用补贴子表

class RoomUtilityRecord(db.Model):
    """
    房间水电费用主表（价格从前端传入版本）
    
    核心特性：
    - 记录房间在特定周期内的水电表读数、用量及费用
    - 价格完全通过前端传入，不依赖本地配置文件
    - 新增和修改记录时必须提供价格配置参数
    - 主表删除时自动同步删除关联的退宿子表记录
    - 支持按周期内天数最多的月份确定账单归属期
    - 实际费用 = 总费用 - 已结算的退宿费用 - 减免费用
    """
    __tablename__ = 'utility_room_bill_records'

    # 数据库层面唯一约束：同一房间同一账期只能有一条记录
    __table_args__ = (
        db.UniqueConstraint('room_id', 'billing_period', name='unique_room_billing_period'),
    )

    # ---------------- 核心字段定义 ----------------
    record_id = db.Column(
        db.Integer, 
        primary_key=True, 
        autoincrement=True,
        comment='记录唯一ID（自增主键）'
    )
    room_id = db.Column(
        db.Integer,
        db.ForeignKey('rooms.id', ondelete='RESTRICT'), 
        nullable=False,
        comment='关联的房间ID（对应房间表主键），限制删除'
    )
    billing_period = db.Column(
        db.String(7), 
        nullable=False,
        comment='账单归属期（格式：YYYY-MM，按周期内天数最多的月份确定）'
    )
    start_date = db.Column(
        db.DateTime, 
        nullable=False,
        comment='费用周期起始日（闭区间，如2025-07-01 00:00:00）'
    )
    end_date = db.Column(
        db.DateTime, 
        nullable=False,
        comment='费用周期结束日（闭区间，如2025-07-31 23:59:59）'
    )

    # 电费相关字段（单位：度）
    electric_current = db.Column(
        db.Numeric(10, 2),
        comment='当前电费表读数（本次抄表时记录的数值）'
    )
    electric_previous = db.Column(
        db.Numeric(10, 2),
        comment='上期电费表读数（上一次抄表记录的数值）'
    )
    electric_usage = db.Column(
        db.Numeric(10, 2),
        comment='抄表电量（自动计算：current - previous，保留2位小数）'
    )
    # 新增：用电量减免度数
    electric_reduction = db.Column(
        db.Numeric(10, 2),
        default=0.00,
        comment='用电量减免度数（可手动设置或根据规则自动计算）'
    )
    # 新增：用电量计费用量（实际收费的用电量）
    electric_billing_usage = db.Column(
        db.Numeric(10, 2),
        comment='用电量计费用量（electric_usage - electric_reduction，保留2位小数）'
    )
    electric_price = db.Column(
        db.Numeric(10, 2),
        comment='电费单价（从系统配置获取，保留2位小数）'
    )

    # 水费相关字段（单位：m³）
    water_current = db.Column(
        db.Numeric(10, 2),
        comment='当前水费表读数（本次抄表时记录的数值）'
    )
    water_previous = db.Column(
        db.Numeric(10, 2),
        comment='上期水费表读数（上一次抄表记录的数值）'
    )
    water_usage = db.Column(
        db.Numeric(10, 2),
        comment='本抄表水量（自动计算：current - previous，保留2位小数）'
    )
    # 新增：用水量减免度数
    water_reduction = db.Column(
        db.Numeric(10, 2),
        default=0.00,
        comment='用水量减免度数（可手动设置或根据规则自动计算）'
    )
    # 新增：用水量计费用量（实际收费的用水量）
    water_billing_usage = db.Column(
        db.Numeric(10, 2),
        comment='用水量计费用量（water_usage - water_reduction，保留2位小数）'
    )
    water_price = db.Column(
        db.Numeric(10, 2),
        comment='水费单价（从系统配置获取，保留2位小数）'
    )

    # 费用计算结果（单位：元）
    total_electric_fee = db.Column(
        db.Numeric(10, 2),
        comment='抄表总电费金额（用抄表电量 × 电费单价，保留2位小数）'
    )
    total_water_fee = db.Column(
        db.Numeric(10, 2),
        comment='抄表总水费金额（用抄表水量 × 水费单价，保留2位小数）'
    )
    total_fee = db.Column(
        db.Numeric(10, 2),
        comment='抄表总费用（电费 + 水费，保留2位小数）'
    )

    # 新增：计费用量总电费、总水费、总费用
    billing_electric_fee = db.Column(
        db.Numeric(10, 2),
        comment='计费用量总电费（electric_billing_usage × electric_price，保留2位小数）'
    )
    billing_water_fee = db.Column(
        db.Numeric(10, 2),
        comment='计费用量总水费（water_billing_usage × water_price，保留2位小数）'
    )
    billing_total_fee = db.Column(
        db.Numeric(10, 2),
        comment='计费用量总费用（billing_electric_fee + billing_water_fee，保留2位小数）'
    )

    # 新增：费用减免
    room_reduction_fee = db.Column(
        db.Numeric(10, 2),
        default=0.00,
        comment='费用减免（特殊减免或者补贴，保留2位小数）'
    )

    # 退宿费用累计字段
    checked_out_electric_fee = db.Column(db.Numeric(10, 2), default=0.0, comment='已结算的电费')
    checked_out_water_fee = db.Column(db.Numeric(10, 2), default=0.0, comment='已结算的水费')
    checked_out_total_fee = db.Column(db.Numeric(10, 2), comment='已结算总费用')
    

    # 实际应收费用字段（实际费用 = 总费用 - 已结算的退宿费用 - 减免费用）
    actual_electric_fee = db.Column(db.Numeric(10, 2), comment='实际应收电费')
    actual_water_fee = db.Column(db.Numeric(10, 2), comment='实际应收水费')
    actual_total_fee = db.Column(db.Numeric(10, 2), comment='实际应收总费用')

    remarks = db.Column(db.Text, nullable=True, comment='备注')
    

    # 状态管理
    status = db.Column(
        db.String(20), 
        default='pending',
        comment='账单状态：pending-待处理/processing-计算中/completed-已完成'
    )

    # 时间戳（自动维护）
    created_at = db.Column(
        db.DateTime, 
        default=datetime.now,
        comment='记录创建时间（自动生成，无需手动设置）'
    )
    updated_at = db.Column(
        db.DateTime, 
        default=datetime.now, 
        onupdate=datetime.now,
        comment='记录最后更新时间（自动更新，无需手动设置）'
    )

    # ---------------- 子表关联配置 ----------------
    # 与退宿子表的关联（修复重叠警告）
    room_checkout_records = relationship(
        'CheckoutUtilityRecord',
        backref='main_record',  # 子表将自动生成此属性，名称唯一
        cascade='all, delete-orphan',   # 保留级联删除
        lazy=True
    )
   
    # 与抄表记录的关联
    meter_readings = relationship(
            'UtilityMeterReading',
        backref='bill_record',
        cascade='all, delete-orphan',
        lazy=True
    )

    # 添加与Room模型的关联关系
    room = db.relationship('Room', backref='utility_room_bill_records', lazy=True)

    # 辅助函数：获取当月最后一天（返回datetime类型，精确到秒）
    @staticmethod
    def get_last_day(year, month):
        if month == 12:
            return datetime(year, 12, 31, 23, 59, 59)
        return datetime(year, month + 1, 1, 0, 0, 0) - timedelta(seconds=1)
    
    @classmethod
    def get_billing_period_dates(cls, period, room_id=None, check_existing=True):
        """
        根据账期参数计算账期的起始日期、结束日期和归属期
        
        参数:
            period: 字符串('YYYY-MM')或datetime对象，表示要计算的账期
            room_id: 可选，房间ID，用于检查是否已有包含该日期的账期记录
            check_existing: 可选，是否检查已有的账期记录，默认为True
        
        返回:
            tuple: (start_date, end_date, billing_period)，分别为账期的起始日期、结束日期和账期
        """
        # 检查是否已有包含该日期的账期记录
        if check_existing and room_id and isinstance(period, datetime):
            existing_record = cls.get_by_room_and_date(room_id, period)
            if existing_record:
                logging.info(f"找到包含日期{period}的现有账期：起始日{existing_record.start_date}，结束日{existing_record.end_date}，归属期{existing_record.billing_period}")
                return existing_record.start_date, existing_record.end_date, existing_record.billing_period
        
        # 根据参数类型进行不同处理
        if isinstance(period, datetime):
            # 如果参数是datetime类型
            date_value = period
            year = date_value.year
            month = date_value.month
            
            # 从系统配置获取抄表日配置
            custom_day = SystemConfig.get_config('CUSTOM_METER_READING_DAY', 1)
            
            # 如果传入的是具体日期，需要判断是否已经过了当月的抄表日
            # 如果日期在抄表日之前，应该返回前一个账期
            if custom_day > 1 and date_value.day < custom_day:
                # 日期在当月抄表日之前，返回前一个账期
                if month == 1:
                    # 1月的前一个月是12月
                    year -= 1
                    month = 12
                else:
                    month -= 1
        elif isinstance(period, str):
            # 如果参数是字符串，解析为年份和月份
            year, month = map(int, period.split('-'))
            # 从系统配置获取抄表日配置
            custom_day = SystemConfig.get_config('CUSTOM_METER_READING_DAY', 1)
        else:
            raise TypeError(f"账期参数必须是字符串('YYYY-MM')或datetime类型，当前类型：{type(period)}")
        
        # 计算该月份的最大天数
        if month == 12:
            days_in_month = 31
        else:
            days_in_month = (datetime(year, month + 1, 1) - datetime(year, month, 1)).days
        
        # 确定起始日：如果抄表日大于该月份的最大日期，则使用该月份的最大日期
        start_day = min(custom_day, days_in_month)
        start_date = datetime(year, month, start_day, 0, 0, 0)
        
        # 确定结束日
        if start_day == 1:
            # 如果起始日为1号，则结束日为当月最后一天
            end_date = cls.get_last_day(year, month)
        else:
            # 如果起始日为其它日期，则结束日为次月抄表日减1
            # 计算次月
            if month == 12:
                next_year = year + 1
                next_month = 1
            else:
                next_year = year
                next_month = month + 1
            
            # 计算次月的最大天数
            if next_month == 12:
                next_month_days = 31
            else:
                next_month_days = (datetime(next_year, next_month + 1, 1) - datetime(next_year, next_month, 1)).days
            
            # 确定次月的抄表日（不超过次月最大天数）
            next_month_meter_day = min(custom_day, next_month_days)
            
            # 计算结束日（次月抄表日减1）
            end_date = datetime(next_year, next_month, next_month_meter_day, 0, 0, 0) - timedelta(days=1)
            end_date = end_date.replace(hour=23, minute=59, second=59)
        
        # 计算账期（复用_determine_billing_period_by_days的逻辑）
        # 转换为日期对象（仅保留日期部分用于计算）
        start_date_date = start_date
        end_date_date = end_date
        
        # 情况1：周期在同一个月内（直接返回该月）
        if start_date_date.year == end_date_date.year and start_date_date.month == end_date_date.month:
            billing_period = start_date_date.strftime("%Y-%m")
            logging.info(f"单月周期（{start_date}至{end_date}），归属期：{billing_period}")
        else:
            # 情况2：跨月周期（统计每个月份包含的天数）
            month_days = {}  # 存储{年月字符串: 天数}的字典
            current_date = start_date_date

            while current_date <= end_date_date:
                # 生成当前日期的年月标识（如"2025-07"）
                year_month = current_date.strftime("%Y-%m")
                
                # 计算当前月份的最后一天（处理12月特殊情况）
                if current_date.month == 12:
                    end_of_month = datetime(current_date.year, 12, 31, 23, 59, 59)
                else:
                    end_of_month = datetime(current_date.year, current_date.month + 1, 1, 0, 0, 0) - timedelta(seconds=1)
                
                # 确定当前月份在周期内的实际结束日（不超过总周期结束日）
                actual_end = min(end_of_month, end_date_date)
                
                # 计算当前月份在周期内的天数（闭区间，包含首尾两天）
                days_in_period = (actual_end - current_date).days + 1
                
                # 累加天数（处理极端情况下的跨月重复统计）
                if year_month in month_days:
                    month_days[year_month] += days_in_period
                else:
                    month_days[year_month] = days_in_period
                
                # 进入下一个月继续计算
                current_date = end_of_month + timedelta(seconds=1)

            # 选择天数最多的月份作为归属期（天数相同则取较晚的月份）
            max_days = -1
            billing_period = None
            # 按年月排序遍历，确保天数相同时取较晚的月份
            for period in sorted(month_days.keys()):
                days = month_days[period]
                if days > max_days:
                    max_days = days
                    billing_period = period
        
        return start_date, end_date, billing_period


    @classmethod
    def exists_by_room_and_period(cls, room_id, billing_period):
        """检查指定房间是否已有指定账期的记录"""
        return cls.query.filter(
            cls.room_id == room_id,
            cls.billing_period == billing_period
        ).first() is not None
        

    # ---------------- 新增记录接口 ----------------
    @classmethod
    def create_from_meter_reading(cls, room_id, reading_date):
        """
        根据抄表数据创建新的费用记录，自动计算初始费用
        """
        # 1. 确保reading_date是datetime类型
        if not isinstance(reading_date, datetime):
            raise ValueError(f"抄表日期必须是datetime类型，当前为：{type(reading_date)}")
        logging.info(f"处理抄表日期：{reading_date}（房间ID：{room_id}，月份：{reading_date.month}）")
        
        # 2. 检查是否已有账期（强化匹配逻辑）
        existing = cls.get_by_room_and_date(room_id, reading_date)
        if existing:
            logging.info(f"匹配到已有账期：{existing.start_date}至{existing.end_date}（归属期：{existing.billing_period}）")
            return existing

        # 3. 检查系统是否启用自定义抄表日
        enable_custom_meter_reading = SystemConfig.get_config('ENABLE_CUSTOM_METER_READING_DAY', False)
        
        if enable_custom_meter_reading:
            # 3.1 启用了自定义抄表日，使用新方法计算账期、起始日和结束日
            start_date, end_date, billing_period = cls.get_billing_period_dates(reading_date)
            logging.info(f"使用自定义抄表日计算账期：起始日{start_date}，结束日{end_date}，归属期{billing_period}")
        else:
            # 3.2 未启用自定义抄表日，使用原有方法计算
            # 计算账期起点
            start_date = datetime(reading_date.year, reading_date.month, 1, 0, 0, 0)
            logging.info(f"首次抄表，强制起点为当月1日0点：{start_date}（抄表月：{reading_date.month}）")
            
            # 计算账期结束日（精确到秒）
            end_date = cls.get_last_day(start_date.year, start_date.month)
            # 校验：结束日必须与起点同月
            if end_date.month != start_date.month:
                logging.error(f"结束日月份异常！起点月：{start_date.month}，结束日：{end_date}")
                end_date = cls.get_last_day(start_date.year, start_date.month)  # 强制修正
            
            # 归属期计算（强制单月归属正确）
            billing_period = cls._determine_billing_period_by_days(start_date, end_date)
            # 最终校验：归属期必须与起点月份一致
            if billing_period != start_date.strftime("%Y-%m"):
                logging.warning(f"归属期计算异常！修正前：{billing_period}，强制修正为：{start_date.strftime('%Y-%m')}")
                billing_period = start_date.strftime("%Y-%m")

        # 6. 新增核心校验：检查该房间是否已有相同账期的记录
        if cls.exists_by_room_and_period(room_id, billing_period):
            logging.warning(f"房间 {room_id} 已存在 {billing_period} 账期的记录，返回已有记录")
            return cls.query.filter_by(room_id=room_id, billing_period=billing_period).first()
        
        # 7. 创建记录，初始化新增的减免和计费用量字段
        new_record = cls(
            room_id=room_id,
            billing_period=billing_period,
            start_date=start_date,
            end_date=end_date,
            status='pending',
            electric_current=Decimal('0.00'),
            electric_previous=Decimal('0.00'),
            water_current=Decimal('0.00'),
            water_previous=Decimal('0.00'),
            electric_usage=Decimal('0.00'),
            water_usage=Decimal('0.00'),
            electric_reduction=Decimal('0.00'),  # 初始化用电量减免度数
            electric_billing_usage=Decimal('0.00'),  # 初始化用电量计费用量
            water_reduction=Decimal('0.00'),  # 初始化用水量减免度数
            water_billing_usage=Decimal('0.00'),  # 初始化用水量计费用量
            electric_price=Decimal('0.00'),  
            water_price=Decimal('0.00'),        
            total_electric_fee=Decimal('0.00'),
            total_water_fee=Decimal('0.00'),
            total_fee=Decimal('0.00'),
             # 初始化新字段
            billing_electric_fee=Decimal('0.00'),
            billing_water_fee=Decimal('0.00'),
            billing_total_fee=Decimal('0.00'),
            room_reduction_fee=Decimal('0.00'),  # 初始化费用减免
            actual_electric_fee=Decimal('0.00'),
            actual_water_fee=Decimal('0.00'),
            actual_total_fee=Decimal('0.00'),
            checked_out_electric_fee=Decimal('0.00'),
            checked_out_water_fee=Decimal('0.00'),
            checked_out_total_fee=Decimal('0.00')
        )
        db.session.add(new_record)
        db.session.flush()
        return new_record

    # ---------------- 新房间初始化接口 ----------------
    @classmethod
    def create_for_new_room(cls, room_id, created_at=None):
        """为新房间初始化当月账单（初始读数和费用均为0）"""
        
        # 如果未提供创建时间，则使用当前时间
        if created_at is None:
            created_at = datetime.now()
            today = created_at
        else:
            today = created_at
        
        # 获取系统配置中的自定义抄表日开关状态
        enable_custom_meter_day = SystemConfig.get_config('ENABLE_CUSTOM_METER_READING_DAY', False)
        
        # 根据开关状态选择不同的日期处理逻辑
        if enable_custom_meter_day:
            # 开启自定义抄表日：使用get_billing_period_dates方法，传递房间ID用于检查已有账期
            start_date, end_date, billing_period = cls.get_billing_period_dates(today, room_id)
        else:
            # 关闭自定义抄表日：使用原来的逻辑（当月第一天到最后一天）
            billing_period = today.strftime("%Y-%m")
            start_date = datetime(today.year, today.month, 1, 0, 0, 0)
            end_date = cls.get_last_day(today.year, today.month)
        
        # 检查是否已有相同账期的记录
        if cls.exists_by_room_and_period(room_id, billing_period):
            logging.warning(f"房间 {room_id} 已存在 {billing_period} 账期的记录，返回已有记录")
            return cls.query.filter_by(room_id=room_id, billing_period=billing_period).first()

        new_record = cls(
            room_id=room_id,
            billing_period=billing_period,
            start_date=start_date,
            end_date=end_date,
            electric_current=Decimal('0.00'),
            electric_previous=Decimal('0.00'),
            water_current=Decimal('0.00'),
            water_previous=Decimal('0.00'),
            electric_usage=Decimal('0.00'),
            water_usage=Decimal('0.00'),
            electric_reduction=Decimal('0.00'),  # 初始化用电量减免度数
            electric_billing_usage=Decimal('0.00'),  # 初始化用电量计费用量
            water_reduction=Decimal('0.00'),  # 初始化用水量减免度数
            water_billing_usage=Decimal('0.00'),  # 初始化用水量计费用量
            electric_price=Decimal('0.00'),
            water_price=Decimal('0.00'),
            actual_electric_fee=Decimal('0.00'),
            actual_water_fee=Decimal('0.00'),
            actual_total_fee=Decimal('0.00'),
            total_electric_fee=Decimal('0.00'),
            total_water_fee=Decimal('0.00'),
            total_fee=Decimal('0.00'),
             # 初始化新字段
            billing_electric_fee=Decimal('0.00'),
            billing_water_fee=Decimal('0.00'),
            billing_total_fee=Decimal('0.00'),
            room_reduction_fee=Decimal('0.00'),  # 初始化费用减免
            status='pending',
            checked_out_electric_fee=Decimal('0.00'),
            checked_out_water_fee=Decimal('0.00'),
            checked_out_total_fee=Decimal('0.00')
        )
        db.session.add(new_record)
        logging.info(f"为新房间{room_id}初始化{billing_period}期账单")
        return new_record

    @classmethod
    def create_empty_records_for_period(cls, billing_period, room_ids=None):
        """为指定账期创建空的主表记录，默认覆盖所有房间"""
        try:
            
            # 获取系统配置中的自定义抄表日开关状态
            enable_custom_meter_day = SystemConfig.get_config('ENABLE_CUSTOM_METER_READING_DAY', False)
            
            if enable_custom_meter_day:
                # 开启自定义抄表日：使用get_billing_period_dates方法，传递billing_period参数
                # 由于我们是批量处理多个房间，这里使用第一个房间ID进行日期计算（如果有）
                first_room_id = room_ids[0] if room_ids else None
                # 设置check_existing=False，避免在批量处理时因部分房间已有记录而影响日期计算
                start_date, end_date, _ = cls.get_billing_period_dates(billing_period, first_room_id, check_existing=False)
                # 确保使用传入的billing_period作为账期
                billing_period = billing_period
            else:
                # 关闭自定义抄表日：使用原来的逻辑（当月第一天到最后一天）
                # 解析账期为年份和月份
                year, month = map(int, billing_period.split('-'))
                
                # 计算该月份的第一天0点和最后一天23:59:59
                start_date = datetime(year, month, 1, 0, 0, 0)
                end_date = cls.get_last_day(year, month)
            
            # 获取需要创建记录的房间ID列表
            if room_ids is None:
                # 假设存在Room模型，获取所有房间ID
                from models.room.room import Room  # 延迟导入避免循环依赖
                rooms = Room.query.all()
                room_ids = [room.id for room in rooms if room.id]
            
            # 验证房间ID列表不为空
            if not room_ids:
                logging.warning("没有可用的房间ID，无法创建记录")
                return 0
                
            created_count = 0
            
            # 为每个房间创建记录
            for room_id in room_ids:
                # 检查该房间是否已有此账期的记录
                if cls.exists_by_room_and_period(room_id, billing_period):
                    logging.info(f"房间 {room_id} 已存在 {billing_period} 账期记录，跳过创建")
                    continue

                # 创建空记录，初始化新增的减免和计费用量字段
                new_record = cls(
                    room_id=room_id,
                    billing_period=billing_period,
                    start_date=start_date,
                    end_date=end_date,
                    status='pending',
                    electric_current=Decimal('0.00'),
                    electric_previous=Decimal('0.00'),
                    water_current=Decimal('0.00'),
                    water_previous=Decimal('0.00'),
                    electric_usage=Decimal('0.00'),
                    water_usage=Decimal('0.00'),
                    electric_reduction=Decimal('0.00'),  # 初始化用电量减免度数
                    electric_billing_usage=Decimal('0.00'),  # 初始化用电量计费用量
                    water_reduction=Decimal('0.00'),  # 初始化用水量减免度数
                    water_billing_usage=Decimal('0.00'),  # 初始化用水量计费用量
                    electric_price=Decimal('0.00'),
                    water_price=Decimal('0.00'),
                    total_electric_fee=Decimal('0.00'),
                    total_water_fee=Decimal('0.00'),
                    total_fee=Decimal('0.00'),
                     # 初始化新字段
                    billing_electric_fee=Decimal('0.00'),
                    billing_water_fee=Decimal('0.00'),
                    billing_total_fee=Decimal('0.00'),
                    room_reduction_fee=Decimal('0.00'),  # 初始化费用减免
                    actual_electric_fee=Decimal('0.00'),
                    actual_water_fee=Decimal('0.00'),
                    actual_total_fee=Decimal('0.00'),
                    checked_out_electric_fee=Decimal('0.00'),
                    checked_out_water_fee=Decimal('0.00'),
                    checked_out_total_fee=Decimal('0.00')
                )
                db.session.add(new_record)
                created_count += 1
            
            db.session.flush()
            logging.info(f"为账期{billing_period}创建了{created_count}条空记录")
            return created_count
            
        except Exception as e:
            logging.error(f"创建指定账期空记录失败: {str(e)}")
            raise
    

    # ---------------- 修改记录接口 ----------------
    def update(self, data):
        """
        更新账单记录，若涉及读数字段则使用前端传入的价格重新计算费用
        """
        # 1. 批量更新字段（跳过主键字段）
        for key, value in data.items():
            if hasattr(self, key) and key != 'record_id':
                setattr(self, key, value)

        # 2. 若包含读数字段或减免字段，重新计算费用
        trigger_fields = {'electric_current', 'electric_previous', 'water_current', 'water_previous',
                          'electric_reduction', 'water_reduction'}
        has_trigger_fields = trigger_fields.intersection(data.keys())
        
        if has_trigger_fields:
            self._recalculate_fees()
            logging.info(f"房间{self.room_id}的{self.billing_period}期账单已重新计算费用")

        # 3. 强制更新时间戳（即使未修改读数字段）
        self.updated_at = datetime.now()
        return self

    # ---------------- 费用计算核心方法 ----------------
    def _recalculate_fees(self):
        """使用Decimal重新实现费用计算，避免精度问题"""
         #1. 从系统配置获取当前水电单价
        try:
            electric_price = Decimal(str(SystemConfig.get_config_value('ELECTRICITY_PRICE', 0.56)))
            water_price = Decimal(str(SystemConfig.get_config_value('WATER_PRICE', 3.8)))
            
            # 保存当前使用的单价到记录中
            self.electric_price = electric_price
            self.water_price = water_price
        except (ValueError, TypeError) as e:
            logging.error(f"获取水电单价失败: {str(e)}")
            raise  # 重新抛出以中断流程并记录

        # 1. 计算用电量
        if self.electric_current is not None and self.electric_previous is not None:
            self.electric_usage = round(
                Decimal(str(self.electric_current)) - Decimal(str(self.electric_previous)), 
                2
            )
        else:
            self.electric_usage = Decimal('0.00')
        
        # 处理电表归零（核心修改：使用房间配置的量程）
        if self.electric_usage < 0:
            # 获取房间配置的电表最大量程
            room = Room.query.get(self.room_id)
            electric_meter_max = Decimal(str(room.electric_meter_max)) if room else Decimal('9999.99')
            self.electric_usage = (electric_meter_max - Decimal(str(self.electric_previous))) + Decimal(str(self.electric_current))
            logging.warning(f"电表归零修正（量程{electric_meter_max}）后用量: {self.electric_usage}")
        
        # 计算用电量计费用量 = 用量 - 减免用量（确保不为负数）
        self.electric_billing_usage = max(
            round(self.electric_usage - (self.electric_reduction or Decimal('0.00')), 2),
            Decimal('0.00')
        )

        # 2. 计算用水量
        if self.water_current is not None and self.water_previous is not None:
            self.water_usage = round(
                Decimal(str(self.water_current)) - Decimal(str(self.water_previous)), 
                2
            )
        else:
            self.water_usage = Decimal('0.00')
        
        # 处理水表归零（核心修改：使用房间配置的量程）
        if self.water_usage < 0:
            # 获取房间配置的水表最大量程
            room = Room.query.get(self.room_id)
            water_meter_max = Decimal(str(room.water_meter_max)) if room else Decimal('9999.99')
            self.water_usage = (water_meter_max - Decimal(str(self.water_previous))) + Decimal(str(self.water_current))
            logging.warning(f"水表归零修正（量程{water_meter_max}）后用量: {self.water_usage}")
        
        # 计算用水量计费用量 = 用量 - 减免用量（确保不为负数）
        self.water_billing_usage = max(
            round(self.water_usage - (self.water_reduction or Decimal('0.00')), 2),
            Decimal('0.00')
        )

        # 3. 计算费用（使用Decimal确保财务精度）
        try:
            # 计算总费用（基于计费用量）
            self.total_electric_fee = round(self.electric_billing_usage * electric_price, 2)
            self.total_water_fee = round(self.water_billing_usage * water_price, 2)
            self.total_fee = round(self.total_electric_fee + self.total_water_fee, 2)

            # 计算计费用量总费用（新增字段计算）
            self.billing_electric_fee = round(self.electric_billing_usage * electric_price, 2)
            self.billing_water_fee = round(self.water_billing_usage * water_price, 2)
            self.billing_total_fee = round(self.billing_electric_fee + self.billing_water_fee, 2)
            
            # 计算已结算总费用
            self._internal_update = True
            total_checked = round(
                (self.checked_out_electric_fee or Decimal('0.00')) + 
                (self.checked_out_water_fee or Decimal('0.00')),
                2
            )
            super(RoomUtilityRecord, self).__setattr__('checked_out_total_fee', total_checked)
            self._internal_update = False  # 移到赋值后
            
            # 核心修改：实际费用 = 总费用 - 已结算的退宿费用 - 减免费用
            # 确保不出现负数（实际费用不能小于0）
            self.actual_electric_fee = max(
                round(self.billing_electric_fee - (self.checked_out_electric_fee or Decimal('0.00')), 2),
                Decimal('0.00')
            )
            
            self.actual_water_fee = max(
                round(self.billing_water_fee - (self.checked_out_water_fee or Decimal('0.00')), 2),
                Decimal('0.00')
            )
            
            # 计算实际总费用，减去减免费用
            self.actual_total_fee = max(
                round(self.billing_total_fee - (self.checked_out_total_fee or Decimal('0.00')) - (self.room_reduction_fee or Decimal('0.00')), 2),
                Decimal('0.00')
            )
            
        except (KeyError, ValueError, TypeError) as e:
            logging.error(f"费用计算失败: {str(e)}")
            raise  # 重新抛出以中断流程并记录

    # ---------------- 归属期计算方法 ----------------
    @staticmethod
    def _determine_billing_period_by_days(start_date, end_date):
        """
        按周期内天数最多的月份确定账单归属期，天数相同则取较晚的月份
        """
        # 转换为日期对象（仅保留日期部分用于计算）
        start_date_date = start_date
        end_date_date = end_date
        
        # 情况1：周期在同一个月内（直接返回该月）
        if start_date_date.year == end_date_date.year and start_date_date.month == end_date_date.month:
            result = start_date_date.strftime("%Y-%m")
            logging.info(f"单月周期（{start_date}至{end_date}），归属期：{result}")
            return result

        # 情况2：跨月周期（统计每个月份包含的天数）
        month_days = {}  # 存储{年月字符串: 天数}的字典
        current_date = start_date_date

        while current_date <= end_date_date:
            # 生成当前日期的年月标识（如"2025-07"）
            year_month = current_date.strftime("%Y-%m")
            
            # 计算当前月份的最后一天（处理12月特殊情况）
            if current_date.month == 12:
                end_of_month = datetime(current_date.year, 12, 31, 23, 59, 59)
            else:
                end_of_month = datetime(current_date.year, current_date.month + 1, 1, 0, 0, 0) - timedelta(seconds=1)
            
            # 确定当前月份在周期内的实际结束日（不超过总周期结束日）
            actual_end = min(end_of_month, end_date_date)
            
            # 计算当前月份在周期内的天数（闭区间，包含首尾两天）
            days_in_period = (actual_end - current_date).days + 1
            
            # 累加天数（处理极端情况下的跨月重复统计）
            if year_month in month_days:
                month_days[year_month] += days_in_period
            else:
                month_days[year_month] = days_in_period
            
            # 进入下一个月继续计算
            current_date = end_of_month + timedelta(seconds=1)

        # 选择天数最多的月份作为归属期（天数相同则取较晚的月份）
        max_days = -1
        selected_period = None
        # 按年月排序遍历，确保天数相同时取较晚的月份
        for period in sorted(month_days.keys()):
            days = month_days[period]
            if days > max_days:
                max_days = days
                selected_period = period

        return selected_period

    # ---------------- 数据查询方法 ----------------
    @classmethod
    def get_by_id(cls, record_id):
        """通过记录ID查询单个账单记录"""
        return cls.query.get(record_id)

    @classmethod
    def get_by_room(cls, room_id, start_date=None, end_date=None):
        """按房间ID和日期范围查询账单记录"""
        # 基础查询：筛选指定房间
        query = cls.query.filter_by(room_id=room_id)
        # 附加日期筛选条件（如果提供）
        if start_date:
            query = query.filter(cls.start_date >= start_date)
        if end_date:
            query = query.filter(cls.end_date <= end_date)
        return query.all()

    @classmethod
    def get_by_period(cls, room_id, period=None, year=None, month=None):
        """按房间ID和归属期查询账单记录（支持多维度筛选）"""
        query = cls.query
        if room_id is not None:  # 仅当room_id不为None时才添加筛选
            query = query.filter_by(room_id=room_id)
        # 按完整归属期筛选
        if period:
            query = query.filter_by(billing_period=period)
        # 按年+月筛选（格式化为YYYY-MM）
        elif year and month:
            period_str = f"{year}-{month:02d}"
            query = query.filter_by(billing_period=period_str)
        # 按年份筛选（匹配全年所有月份）
        elif year:
            query = query.filter(cls.billing_period.like(f"{year}-%"))
        # 按归属期倒序排列（最新的在前）
        return query.order_by(cls.billing_period.desc()).all()

    # 新增：根据房间和日期查询主表（供子表自动匹配）
    @classmethod
    def get_by_room_and_date(cls, room_id, target_date):
        """获取指定房间在目标日期所属周期的主表记录"""
        return cls.query.filter(
            cls.room_id == room_id,
            cls.start_date <= target_date,
            cls.end_date >= target_date
        ).first()

    # ---------------- 记录删除方法 ----------------
    def delete(self):
        """删除当前账单记录（会自动同步删除关联的退宿子表记录和抄表记录照片）"""
        try:
            # 获取当前记录的账期和房间ID用于删除照片
            billing_period = self.billing_period
            room_id = self.room_id
            
            # 删除关联的退宿子表记录
            from .utility_room_bill_occupant import RoomUtilityOccupant  # 延迟导入
            RoomUtilityOccupant.query.filter_by(record_id=self.record_id).delete()
            
            # 删除记录本身
            db.session.delete(self)
            
            # 调用工具删除该账期和房间的抄表记录照片
            try:
                from utils.room_meter_photo import room_meter_manager
                logging.info(f"尝试删除账期 {billing_period} 下房间 {room_id} 的抄表记录照片")
                result = room_meter_manager.delete_media_by_billing_period(billing_period, room_id)
                if result:
                    logging.info(f"成功删除账期 {billing_period} 下房间 {room_id} 的抄表记录照片")
                else:
                    logging.warning(f"删除账期 {billing_period} 下房间 {room_id} 的抄表记录照片失败")
            except Exception as photo_error:
                # 记录错误但不影响主流程
                logging.error(f"调用抄表记录照片删除工具失败: {str(photo_error)}")
            
            return True
        except Exception as e:
            logging.error(f"删除记录ID={self.record_id}失败: {str(e)}")
            raise  # 抛出异常让上层处理回滚

    @classmethod
    def handle_room_deletion(cls, room_id):
        """
        处理房间删除时的关联费用记录
        
        返回值：
            dict: 包含操作结果和删除数量的字典
                - success: 布尔值，操作是否成功
                - deleted_count: 整数，实际删除的记录数
                - message: 字符串，操作详情
        """
        try:
            # 初始化统计变量（主表记录数和子表记录数）
            total_deleted = 0
            total_occupant_deleted = 0
            
            # 查询该房间的所有费用主记录
            room_records = cls.query.filter_by(room_id=room_id).all()
            
            for record in room_records:
                # 统计当前主记录关联的子表数量（使用正确的record_id）
                from .utility_room_bill_occupant import RoomUtilityOccupant  # 延迟导入
                occupant_count = RoomUtilityOccupant.query.filter_by(
                    record_id=record.record_id
                ).count()
                total_occupant_deleted += occupant_count
                
                # 调用主记录的delete方法（会删除当前主记录及关联子表）
                record.delete()
                total_deleted += 1
            
            # 构建包含子表统计的消息
            message = (f"已删除房间ID={room_id}的所有费用记录，共{total_deleted}条主记录，"
                      f"同时删除{total_occupant_deleted}条在住人员分摊子记录")
            logging.info(message)
            
            return {
                'success': True,
                'deleted_count': total_deleted,  # 主表删除数量
                'occupant_records_deleted': total_occupant_deleted,  # 新增子表删除数量
                'message': message
            }
            
        except Exception as e:
            error_msg = f"处理房间ID={room_id}的费用记录删除失败: {str(e)}"
            logging.error(error_msg)
            return {
                'success': False,
                'deleted_count': 0,
                'occupant_records_deleted': 0,  # 异常时子表删除数为0
                'message': error_msg
            }

    ### 1. 修复一键核算功能（batch_update_from_meter方法）
    @classmethod
    def batch_update_from_meter(cls, billing_period, meter_readings, main_records):
        """一键核算所有房间账期费用，自动处理补贴用量跟踪"""
        try:
            from collections import defaultdict
            from .utility_room_meter import UtilityMeterReading  # 统一导入位置
            
            # 核心：系统配置开关（控制是否允许使用按房间金额减免的所有参数）
            enable_fee_room_fee = SystemConfig.get_config_value('FEE_ROOM_FEE', False)
            logging.info(f"系统配置-是否允许使用按房间金额减免参数: {enable_fee_room_fee}")
            enable_room_reduction = SystemConfig.get_config_value('FEE_METER_reduction', False)
            logging.info(f"系统配置-是否允许使用按房间金额减免参数: {enable_room_reduction}")

            # 1. 按房间ID收集所有抄表记录（包含历史记录）
            room_all_readings = defaultdict(list)
            for reading in meter_readings:
                if not reading.record_id or not reading.room_id:
                    raise Exception(f'抄表记录{reading.id}缺少必要关联信息，请检查数据')
                room_all_readings[reading.room_id].append(reading)
            
            # 补充查询该房间的所有历史抄表记录（核心修复点）
            for room_id in room_all_readings.keys():
                current_ids = [r.id for r in room_all_readings[room_id]]
                # 查询未包含在当前记录中的历史数据（跨月记录主要来源）
                history_readings = UtilityMeterReading.query.filter(
                    UtilityMeterReading.room_id == room_id,
                    ~UtilityMeterReading.id.in_(current_ids)  # 取反：排除当前记录
                ).all()
                # 按日期排序历史记录，确保最新的历史记录在最后
                history_readings.sort(key=lambda x: x.reading_date)
                room_all_readings[room_id].extend(history_readings)
            
            # 2. 价格配置
            try:
                price_config = {
                    'electric_price': Decimal(str(SystemConfig.get_config_value('ELECTRICITY_PRICE', 0.56))),
                    'water_price': Decimal(str(SystemConfig.get_config_value('WATER_PRICE', 3.8)))
                }
            except (TypeError, ValueError) as e:
                raise Exception(f"价格配置错误: {str(e)}")
      
            updated_count = 0

            # 4. 遍历主表记录更新数据
            for main_record in main_records:
                month_last_day = main_record.end_date  # 获取主表记录当前账期结束日
                month_first_day = main_record.start_date
                billing_period = main_record.billing_period  # 使用主记录中已有的起始和结束日期
                room_id = main_record.room_id
                all_readings = room_all_readings.get(room_id, [])
                
                if not all_readings:
                    logging.warning(f'房间{room_id}无任何抄表记录，跳过更新')
                    continue
                
                
                # 区分历史记录与当前记录（优化跨月判断）
                historical_readings = []
                current_month_readings = []
                for reading in all_readings:
                    # 确保是datetime类型
                    reading_date = reading.reading_date
                    if not isinstance(reading_date, datetime):
                        reading_date = datetime.combine(reading_date, datetime.min.time())
                    reading_ym = (reading_date.year, reading_date.month)
                    
                    # 从主记录的账期解析年份和月份
                    try:
                        year, month = map(int, billing_period.split('-'))
                        current_month = (year, month)
                        reading_ym = (reading_date.year, reading_date.month)

                        if reading_ym < current_month:
                            historical_readings.append(reading)
                            logging.debug(f'房间{room_id}跨月历史记录：{reading_date}（{reading_ym}）')
                        elif reading_ym == current_month:
                            current_month_readings.append(reading)
                    except Exception as e:
                        logging.error(f"解析账期失败: {billing_period}, 错误: {str(e)}")
                        continue  # 跳过该记录处理
                
                # 调试日志：明确跨月记录数量
                logging.debug(
                    f'房间{room_id}@{billing_period} - 跨月历史记录数：{len(historical_readings)}，'
                    f'当月记录数：{len(current_month_readings)}'
                )
                
                if not current_month_readings:
                    logging.warning(f'房间{room_id}在{billing_period}无当月抄表记录，跳过更新')
                    continue
                
                # 分别为电表和水表各自取值抄表记录
                # 1. 筛选出有电表读数的记录并排序
                electric_readings = [r for r in current_month_readings if r.electric_current is not None]
                if not electric_readings:
                    electric_readings = current_month_readings  # 如果没有专用电表记录，回退到全部记录
                electric_readings.sort(key=lambda x: x.reading_date)
                last_electric_reading = electric_readings[-1]
                
                # 2. 筛选出水表读数的记录并排序
                water_readings = [r for r in current_month_readings if r.water_current is not None]
                if not water_readings:
                    water_readings = current_month_readings  # 如果没有专用水表记录，回退到全部记录
                water_readings.sort(key=lambda x: x.reading_date)
                last_water_reading = water_readings[-1]
                
                # 3. 确定电表的上期读数
                first_electric_reading = None
                if historical_readings:
                    historical_electric = [r for r in historical_readings if r.electric_current is not None]
                    if not historical_electric:
                        historical_electric = historical_readings
                    historical_electric.sort(key=lambda x: x.reading_date)
                     
                    # 简化换表记录处理：检查本次抄表记录是否有换表标记
                    current_electric_reading = electric_readings[-1]  # 本次抄表记录
                     
                    if current_electric_reading.electric_meter_replaced:
                        # 如果本次抄表记录是换表记录，则以上次读数作为初始值
                        first_electric_reading = current_electric_reading
                        logging.debug(f'房间{room_id}本次抄表记录是换表记录，以上次读数作为初始值')
                    else:
                        # 没有换表记录，使用最后一条历史记录
                        first_electric_reading = historical_electric[-1]
                        first_date = first_electric_reading.reading_date
                        if not isinstance(first_date, datetime):
                            first_date = datetime.combine(first_date, datetime.min.time())
                        logging.debug(
                            f'房间{room_id}使用跨月历史记录作为电表上期读数：{first_date}（{first_date.year}-{first_date.month}）'
                        )
                else:
                    electric_readings.sort(key=lambda x: x.reading_date)
                    first_electric_reading = electric_readings[0]
                    logging.info(f'房间{room_id}无跨月历史记录，使用当月首次记录作为电表上期读数')
                
                # 4. 确定水表的上期读数
                first_water_reading = None
                if historical_readings:
                    historical_water = [r for r in historical_readings if r.water_current is not None]
                    if not historical_water:
                        historical_water = historical_readings
                    historical_water.sort(key=lambda x: x.reading_date)
                    
                    # 简化换表记录处理：检查本次抄表记录是否有换表标记
                    current_reading = water_readings[-1]  # 本次抄表记录
                    
                    if current_reading.water_meter_replaced:
                        # 如果本次抄表记录是换表记录，则以上次读数作为初始值
                        first_water_reading = current_reading
                        logging.debug(f'房间{room_id}本次抄表记录是换表记录，以上次读数作为初始值')
                    else:
                        # 没有换表记录，使用最后一条历史记录
                        first_water_reading = historical_water[-1]
                        first_date = first_water_reading.reading_date
                        if not isinstance(first_date, datetime):
                            first_date = datetime.combine(first_date, datetime.min.time())
                        logging.debug(
                            f'房间{room_id}使用跨月历史记录作为水表上期读数：{first_date}（{first_date.year}-{first_date.month}）'
                        )
                else:
                    water_readings.sort(key=lambda x: x.reading_date)
                    first_water_reading = water_readings[0]
                    logging.info(f'房间{room_id}无跨月历史记录，使用当月首次记录作为水表上期读数')
                
                # 计算用量
                try:
                    electric_usage = Decimal(last_electric_reading.electric_current or 0) - Decimal(first_electric_reading.electric_current or 0)
                    water_usage = Decimal(last_water_reading.water_current or 0) - Decimal(first_water_reading.water_current or 0)
                except (TypeError, ValueError) as e:
                    raise Exception(f"读数格式错误: {str(e)}")

                # 获取房间表计量程配置（核心修改）
                room = Room.query.get(room_id)
                electric_meter_max = Decimal(str(room.electric_meter_max)) if room else Decimal('9999.99')
                water_meter_max = Decimal(str(room.water_meter_max)) if room else Decimal('9999.99')
                logging.info(f"房间{room_id}表计量程 - 电表: {electric_meter_max}, 水表: {water_meter_max}")
                
                # 处理表计归零（核心修改：使用房间配置的量程）
                if electric_usage < 0:
                    electric_usage = (electric_meter_max - Decimal(first_electric_reading.electric_current or 0)) + Decimal(last_electric_reading.electric_current or 0)
                    logging.warning(f"电表归零修正（量程{electric_meter_max}）后用量: {electric_usage}")
                
                if water_usage < 0:
                    water_usage = (water_meter_max - Decimal(first_water_reading.water_current or 0)) + Decimal(last_water_reading.water_current or 0)
                    logging.warning(f"水表归零修正（量程{water_meter_max}）后用量: {water_usage}")

                # 查询有效的房间级补贴（按类型分组）
                subsidies = FeeSubsidy.query.filter(
                    FeeSubsidy.room_id == room_id,
                    FeeSubsidy.is_enabled == True,
                    FeeSubsidy.effective_date <= month_last_day
                ).all()
                
                # 按补贴类型分组
                amount_subsidies = []  # 房间水电按金额减免
                usage_subsidies = []   # 房间水电按用量减免
                
                for subsidy in subsidies:
                    if subsidy.fee_type == "房间水电按金额减免":
                        amount_subsidies.append(subsidy)
                    elif subsidy.fee_type == "房间水电按用量减免":
                        usage_subsidies.append(subsidy)
                
                
                # 2. 处理用量类补贴（房间水电按用量减免）
                total_electric_reduction = Decimal('0.00')
                total_water_reduction = Decimal('0.00')  
                actual_electric_used = Decimal('0.00')
                actual_water_used = Decimal('0.00') 
                if enable_room_reduction and usage_subsidies:
                    for subsidy in usage_subsidies:
                        # 获取该补贴的剩余可用量
                        remaining = FeeSubsidyUsage.get_remaining_usage(subsidy.id, billing_period)
                        remaining_electric = Decimal(str(remaining['remaining_electric']))
                        remaining_water = Decimal(str(remaining['remaining_water']))
                        #原始用量必须大于0才可以进行下一步
                        if electric_usage > 0 or water_usage > 0:
                            # 实际可使用的补贴量（不超过剩余量），判断如果原始用量小于等于0，则可用量为0
                            if electric_usage > 0:
                                actual_electric_used = min(remaining_electric, electric_usage)
                            else:
                                actual_electric_used = Decimal('0.00')

                            if water_usage > 0:
                                actual_water_used = min(remaining_water, water_usage)
                            else:
                                actual_water_used = Decimal('0.00') 

                            total_electric_reduction += remaining_electric
                            total_water_reduction += remaining_water

                            # 记录补贴使用情况到子表
                            FeeSubsidyUsage.create_usage_record(
                                subsidy=subsidy,
                                billing_period=billing_period,
                                usage_data={
                                    'room_id': room_id,
                                    'used_electric': actual_electric_used,
                                    'used_water': actual_water_used,
                                    'is_checkout': 2,
                                    'remark': f"房间{room_id}@{billing_period}自动核算抵扣"
                                }
                            )
                            logging.info(
                                f"房间{room_id}使用补贴{subsidy.id}用量: "
                                f"电{actual_electric_used}度（剩余{remaining_electric - actual_electric_used}度）, "
                                f"水{actual_water_used}m³（剩余{remaining_water - actual_water_used}m³）"
                            )
                        else:
                            logging.info(f"房间{room_id}@{billing_period}用量为0，不进行抵扣")
                
                # 计算计费用量 = 用量 - 减免用量（不超过实际用量）
                electric_billing_usage = max(
                    round(electric_usage - total_electric_reduction, 2),
                    Decimal('0.00')
                )
                
                water_billing_usage = max(
                    round(water_usage - total_water_reduction, 2),
                    Decimal('0.00')
                )
                
                # 计算费用及更新主表
                electric_fee = round(electric_usage * price_config['electric_price'], 2)
                water_fee = round(water_usage * price_config['water_price'], 2)
                
                # 计算计费用量总费用（新增字段）
                billing_electric_fee = round(electric_billing_usage * price_config['electric_price'], 2)
                billing_water_fee = round(water_billing_usage * price_config['water_price'], 2)
                billing_total_fee = round(billing_electric_fee + billing_water_fee, 2)

                # 1. 处理金额类补贴（房间水电按金额减免）
                total_room_reduction_fee = Decimal('0.00')
                actual_used = Decimal('0.00')
                if enable_fee_room_fee and amount_subsidies:
                    for subsidy in amount_subsidies:
                        # 获取该补贴的剩余可用金额
                        remaining = FeeSubsidyUsage.get_remaining_usage(subsidy.id, billing_period)
                        remaining_amount = Decimal(str(remaining['remaining_amount']))
                        
                        if remaining_amount > 0 and billing_total_fee > 0:
                            # 实际可使用的补贴金额（不超过剩余金额）
                            actual_used = min(remaining_amount, billing_total_fee)
                            total_room_reduction_fee += remaining_amount
                            
                            # 记录补贴使用情况到子表
                            FeeSubsidyUsage.create_usage_record(
                                subsidy=subsidy,
                                billing_period=billing_period,
                                usage_data={
                                    'room_id': room_id,
                                    'used_amount': actual_used,
                                    'is_checkout': 2,
                                    'remark': f"房间{room_id}@{billing_period}自动核算抵扣"
                                }
                            )
                            logging.info(f"房间{room_id}使用补贴{subsidy.id}金额: {actual_used}元，剩余: {remaining_amount - actual_used}元")
                

                # 更新主表字段
                main_record.electric_previous = Decimal(first_electric_reading.electric_current or 0)
                main_record.electric_current = Decimal(last_electric_reading.electric_current or 0)
                main_record.electric_usage = round(electric_usage, 2)
                main_record.electric_billing_usage = electric_billing_usage  # 更新计费用量
                main_record.electric_price = price_config['electric_price']  # 保存当前单价
                main_record.total_electric_fee = electric_fee
                
                main_record.water_previous = Decimal(first_water_reading.water_current or 0)
                main_record.water_current = Decimal(last_water_reading.water_current or 0)
                main_record.water_usage = water_usage
                main_record.water_billing_usage = water_billing_usage  # 更新计费用量
                main_record.water_price = price_config['water_price']  # 保存当前单价
                main_record.total_water_fee = water_fee
                
                main_record.total_fee = round(electric_fee + water_fee, 2)
                
                # 更新新增字段
                main_record.billing_electric_fee = billing_electric_fee
                main_record.billing_water_fee = billing_water_fee
                main_record.billing_total_fee = billing_total_fee
                
                # 更新主表的减免字段（实际使用的补贴量）
                main_record.room_reduction_fee = actual_used
                main_record.electric_reduction = actual_electric_used
                main_record.water_reduction = actual_water_used

                # 计算已结算费用
                main_record._internal_update = True  # 通过实例访问
                total_checked = round(
                    (main_record.checked_out_electric_fee or 0) + 
                    (main_record.checked_out_water_fee or 0), 
                    2
                )
                super(RoomUtilityRecord, main_record).__setattr__('checked_out_total_fee', total_checked)
                main_record._internal_update = False
                
                # 计算实际费用（实际费用 = 总费用 - 已结算的退宿费用 - 减免费用）
                main_record.actual_electric_fee = max(
                    round(main_record.billing_electric_fee - (main_record.checked_out_electric_fee or 0), 2),
                    0
                )
                
                main_record.actual_water_fee = max(
                    round(main_record.billing_water_fee - (main_record.checked_out_water_fee or 0), 2),
                    0
                )
                
                main_record.actual_total_fee = max(
                    round(main_record.billing_total_fee - (main_record.checked_out_total_fee or 0) - (main_record.room_reduction_fee or 0), 2),
                    0
                )
                
                # 新增：判断实际费用是否为0，设置备注信息
                if not hasattr(main_record, 'remark'):
                    main_record.remark = ""
                
                # 检查实际总费用是否为0（经减免后）
                if main_record.actual_total_fee <= Decimal('0.00'):
                    # 确保实际费用为0
                    main_record.actual_total_fee = Decimal('0.00')
                    main_record.actual_electric_fee = Decimal('0.00')
                    main_record.actual_water_fee = Decimal('0.00')
                    
                    # 设置备注信息
                    current_remark = main_record.remark or ""
                    new_remark = "当前房间实际费用经核算减免后为0，本月无需支付"
                    
                    # 如果已有备注，拼接而不是覆盖
                    if current_remark:
                        main_record.remark = f"{current_remark}; {new_remark}"
                    else:
                        main_record.remark = new_remark
                    
                    logging.info(f"房间{room_id}@{billing_period}实际费用为0，已添加备注信息")
                
                main_record.status = 'completed'
                main_record.updated_at = datetime.now()
                
                updated_count += 1
            
            return updated_count
        
        except Exception as e:
            #db.session.rollback()
            logging.error(f"一键核算失败: {str(e)}")
            raise e
    
    # 新增：获取上个账期记录的方法
    @classmethod
    def get_previous_period_record(cls, room_id, current_period):
        """获取指定房间的上个账期记录，增强版查询逻辑"""
        try:
            # 解析当前账期
            try:
                year, month = map(int, current_period.split('-'))
                logging.info(f"成功解析当前账期: {current_period} -> 年={year}, 月={month}")
            except Exception as e:
                logging.error(f"解析当前账期失败: {current_period}, 错误: {str(e)}")
                raise ValueError(f"当前账期格式错误: {current_period}，应为YYYY-MM")
            
            # 计算上个账期
            if month == 1:
                prev_year = year - 1
                prev_month = 12
            else:
                prev_year = year
                prev_month = month - 1
            
            previous_period = f"{prev_year}-{prev_month:02d}"
            logging.info(f"===== 开始查询上个账期记录 =====")
            logging.info(f"房间ID: {room_id}, 当前账期: {current_period}, 目标上个账期: {previous_period}")
            
            # 首先查询该房间的所有记录，用于调试
            all_room_records = cls.query.filter(cls.room_id == room_id).all()
            all_periods = [rec.billing_period for rec in all_room_records]
            logging.info(f"房间{room_id}的所有账期记录: {all_periods}")
            
            if not all_room_records:
                logging.warning(f"房间{room_id}没有任何账期记录")
                return None
            
            # 1. 精确查询上个账期记录（优先使用）
            previous_record = cls.query.filter(
                cls.room_id == room_id,
                cls.billing_period == previous_period
            ).first()
            
            if previous_record:
                logging.info(f"1. 精确匹配到上个账期记录: ID={previous_record.record_id}, 账期={previous_record.billing_period}, 状态={previous_record.status}")
                return previous_record
            
            # 2. 检查是否有格式相似的账期（如多空格、大小写问题）
            logging.warning(f"未找到精确匹配的{previous_period}账期记录，尝试格式容错查询")
            # 移除可能的空格并统一格式
            normalized_target = previous_period.replace(" ", "")
            
            # 遍历所有记录检查格式相似的账期
            for record in all_room_records:
                normalized_period = record.billing_period.replace(" ", "")
                if normalized_period == normalized_target:
                    logging.warning(f"2. 格式容错匹配到记录: 原始账期='{record.billing_period}', 标准化后='{normalized_period}'")
                    return record
            
            # 3. 尝试按年份和月份分别匹配（处理可能的格式错误）
            logging.warning(f"格式容错查询失败，尝试按年月拆分查询")
            previous_record = cls.query.filter(
                cls.room_id == room_id,
                cls.billing_period.like(f"{prev_year}%{prev_month:02d}%")
            ).first()
            
            if previous_record:
                logging.warning(f"3. 年月拆分匹配到记录: 账期={previous_record.billing_period}, 预期={previous_period}")
                return previous_record
            
            # 4. 按日期范围查询（覆盖整个上个月）
            logging.warning(f"年月拆分查询失败，尝试按日期范围查询")
            try:
                prev_first_day = datetime(prev_year, prev_month, 1, 0, 0, 0)
                prev_last_day = cls.get_last_day(prev_year, prev_month)
                
                logging.info(f"查询日期范围: {prev_first_day} 至 {prev_last_day}")
                
                # 查找完全包含在上个月内的记录
                previous_record = cls.query.filter(
                    cls.room_id == room_id,
                    cls.start_date >= prev_first_day,
                    cls.end_date <= prev_last_day
                ).first()
                
                if previous_record:
                    logging.warning(f"4. 找到日期范围内的记录: ID={previous_record.record_id}, "
                                  f"账期={previous_record.billing_period}, "
                                  f"日期范围={previous_record.start_date}至{previous_record.end_date}")
                    return previous_record
            except Exception as e:
                logging.error(f"日期范围查询出错: {str(e)}")
            
            # 5. 查找状态为已完成的最新历史记录
            logging.warning(f"所有查询方式均失败，尝试返回最新的已完成记录")
            current_month_start = datetime(year, month, 1, 0, 0, 0)
            previous_record = cls.query.filter(
                cls.room_id == room_id,
                cls.status == 'completed',
                cls.end_date < current_month_start  # 结束日期在上个月之前
            ).order_by(cls.end_date.desc()).first()
            
            if previous_record:
                logging.warning(f"5. 使用最新已完成记录替代: ID={previous_record.record_id}, "
                              f"账期={previous_record.billing_period}, "
                              f"结束日期={previous_record.end_date}, 状态={previous_record.status}")
                return previous_record
            
            # 6. 最后尝试返回任何状态的最新历史记录
            logging.warning(f"未找到已完成的历史记录，尝试返回任何状态的最新记录")
            previous_record = cls.query.filter(
                cls.room_id == room_id,
                cls.end_date < current_month_start  # 结束日期在上个月之前
            ).order_by(cls.end_date.desc()).first()
            
            if previous_record:
                logging.warning(f"6. 使用最新记录替代: ID={previous_record.record_id}, "
                              f"账期={previous_record.billing_period}, "
                              f"结束日期={previous_record.end_date}, 状态={previous_record.status}")
                return previous_record
            
            # 所有查询都失败
            logging.error(f"所有查询方式均失败，房间{room_id}的上个账期({previous_period})记录不存在")
            logging.error(f"该房间的所有账期: {all_periods}")
            return None
            
        except Exception as e:
            logging.error(f"获取上个账期记录失败: {str(e)}", exc_info=True)
            return None

    @classmethod
    def get_latest_completed_record(cls, room_id):
        """获取房间最新的已完成状态的记录（用于退宿时的基准读数）"""
        return cls.query.filter(
            cls.room_id == room_id,
            cls.status == 'completed'
        ).order_by(cls.end_date.desc()).first()

    @classmethod
    def get_latest_record(cls, room_id):
        """获取房间最新的记录（无论状态）"""
        return cls.query.filter(
            cls.room_id == room_id
        ).order_by(cls.end_date.desc()).first()
    
    # ---------------- 修复：退宿费用累计更新方法 ----------------
    # ---------------- 退宿费用累计更新方法 ----------------
    def add_checkout_fees(self, user_billing_electric_fee, user_billing_water_fee):
        """
        添加退宿费用到累计字段（核心逻辑：叠加而非覆盖）
        
        每次退宿时调用此方法，将当前退宿人员的水电费用累加到主表的已结算费用中，
        确保多次退宿的费用能够正确叠加，而非被新的费用覆盖。
        
        实际费用计算逻辑：
        实际费用 = 总费用 - 累计已结算的退宿费用 - 减免费用
        （实际费用将用于剩余在住人员的费用分摊）
        
        参数:
            electric_billing_fee: 本次退宿的电费金额
            water_billing_fee: 本次退宿的水费金额
            
        返回:
            bool: 操作是否成功
        """
        try:
            # 关键修复：开启内部更新标志，允许修改受保护字段
            self._internal_update = True
            # 转换为Decimal进行精确计算，避免浮点数精度问题
            electric = Decimal(str(user_billing_electric_fee))
            water = Decimal(str(user_billing_water_fee))
            # 记录传入值是否为负数，用于后续状态判断
            has_negative = electric < 0 or water < 0
             # 确保总费用字段已初始化
            if self.billing_electric_fee is None:
                self.billing_electric_fee = Decimal('0.00')
            if self.billing_water_fee is None:
                self.billing_water_fee = Decimal('0.00')
            if self.billing_total_fee is None:
                self.billing_total_fee = Decimal('0.00')
                
            # 关键逻辑：累加费用而非覆盖
            # 初始值处理：如果为None则视为0
            current_checked_electric = self.checked_out_electric_fee or Decimal('0.00')
            current_checked_water = self.checked_out_water_fee or Decimal('0.00')
            # 累加计算新的已结算费用
            self.checked_out_electric_fee = round(current_checked_electric + electric, 2)
            self.checked_out_water_fee = round(current_checked_water + water, 2)
            self.checked_out_total_fee = round(
                self.checked_out_electric_fee + self.checked_out_water_fee, 
                2
            )
            
            # 重新计算实际费用（总费用 - 已结算的退宿费用 - 减免费用）
            # 确保实际费用不会为负数（使用max函数）
            self.actual_electric_fee = max(
                round(self.billing_electric_fee  or Decimal('0.00') - self.checked_out_electric_fee  or Decimal('0.00'), 2),
                Decimal('0.00')
            )
            self.actual_water_fee = max(
                round(self.billing_water_fee  or Decimal('0.00') - self.checked_out_water_fee  or Decimal('0.00'), 2),
                Decimal('0.00')
            )
            self.actual_total_fee = max(
                round(self.billing_total_fee  or Decimal('0.00') - self.checked_out_total_fee  or Decimal('0.00') - (self.room_reduction_fee or Decimal('0.00')), 2),
                Decimal('0.00')
            )
            # 更新状态和时间戳
            # 新增逻辑：如果传入负数且已结算值都为0，状态设为pending
            if has_negative and self.checked_out_electric_fee == Decimal('0.00') and self.checked_out_water_fee == Decimal('0.00') and self.checked_out_total_fee == Decimal('0.00'):
                self.status = 'pending'
                logging.info(f"房间{self.room_id}@{self.billing_period}已结算费用清零，状态更新为pending")
            else:
                self.status = 'processing'
                
            self.updated_at = datetime.now()

            # 记录日志，便于追踪多次退宿的费用叠加情况
            logging.info(
                f"房间{self.room_id}@{self.billing_period}退宿费用更新 - "
                f"新增电费: {electric}, 累计电费: {self.checked_out_electric_fee} - "
                f"新增水费: {water}, 累计水费: {self.checked_out_water_fee} - "
                f"当前实际费用: {self.actual_total_fee}"
            )
            
            return True
            
        except (ValueError, TypeError) as e:
            logging.error(f"更新退宿累计费用失败: {str(e)}")
            raise
        finally:
            # 确保无论是否出错，内部更新标志都关闭
            self._internal_update = False
    

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)  # 先调用父类
        self._internal_update = False  # 再初始化子类属性

    # 添加一个保护机制，防止直接修改累计退宿费用字段
    def __setattr__(self, name, value):
        # 禁止直接修改累计退宿费用字段，必须通过add_checkout_fees方法
        # 允许内部更新时跳过检查
        if hasattr(self, '_internal_update') and self._internal_update:
            super().__setattr__(name, value)
            return
        if name in ['checked_out_electric_fee', 'checked_out_water_fee', 'checked_out_total_fee']:
            # 允许初始化时设置为0
            if (name in self.__dict__ and self.__dict__[name] is not None) or value != 0:
                raise AttributeError(f"不允许直接修改{name}，请使用add_checkout_fees方法进行累加")
        super().__setattr__(name, value)
