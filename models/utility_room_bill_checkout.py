from datetime import datetime, timedelta
from sqlalchemy.orm import relationship
from utils.db import db
import logging
from decimal import Decimal, InvalidOperation
from models.utility_room_meter import UtilityMeterReading
from models.utility_room_bill_record import RoomUtilityRecord
from models.system_config import SystemConfig
from models.dorm import Dorm
from models.user import User
from models.room import Room
from models.fee_subsidy import FeeSubsidy
from models.fee_subsidy_usage import FeeSubsidyUsage

class CheckoutUtilityRecord(db.Model):
    """退宿人员费用子记录（按账期比例分摊）"""
    __tablename__ = 'utility_room_bill_checkout'
    
    # 字段定义部分（保持不变）
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    record_id = db.Column(
        db.Integer, 
        db.ForeignKey('utility_room_bill_records.record_id', ondelete='CASCADE'),
        nullable=False,
        comment='关联的主账单ID'
    )
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False, comment='退宿人员ID，限制删除')
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='RESTRICT'), nullable=False, comment='退宿人员房间ID，限制删除')
    
    # 时间信息
    checkin_date = db.Column(db.DateTime, nullable=True, comment='入住日期时间')
    checkout_date = db.Column(db.DateTime, nullable=True, comment='退宿日期时间')
    stay_days = db.Column(db.Integer, nullable=True, comment='总住宿天数')
    
    # 当期天数（用于分摊）
    user_period_days = db.Column(db.Integer, nullable=True, comment='退宿人当期住宿天数')
    total_period_days = db.Column(db.Integer, nullable=True, comment='房间当期总住宿天数')
    natural_days = db.Column(db.Integer, nullable=True, comment='当月自然天数')  # 新增

    # 抄表数据（房间级）
    electric_reading = db.Column(db.Numeric(10, 2), nullable=True, comment='退宿时电表读数')
    electric_previous = db.Column(db.Numeric(10, 2), nullable=True, comment='上个账期电表读数')
    water_reading = db.Column(db.Numeric(10, 2), nullable=True, comment='退宿时水表读数')
    water_previous = db.Column(db.Numeric(10, 2), nullable=True, comment='上个账期水表读数')

    # 抄表用量（房间级）
    meter_electric_usage = db.Column(db.Numeric(10, 2), comment='房间总抄表电用量')  # 新增
    meter_water_usage = db.Column(db.Numeric(10, 2), comment='房间总抄表水用量')    # 新增
    # 抄表费用（房间级）
    meter_electric_fee = db.Column(db.Numeric(10, 2), comment='房间总抄表电费')     # 新增
    meter_water_fee = db.Column(db.Numeric(10, 2), comment='房间总抄表水费')       # 新增
    meter_total_fee = db.Column(db.Numeric(10, 2), comment='房间总抄表费用')        # 新增
    

    # 用户用量数据（用户级）
    #用户原始用量
    user_original_electric_usage = db.Column(db.Numeric(10, 2), comment='用户原始电用量')  # 重命名
    user_original_water_usage = db.Column(db.Numeric(10, 2), comment='用户原始水用量')    # 重命名
    # 用户减免用量（用户级）
    user_reduction_electric = db.Column(db.Numeric(10, 2), default=0.00, comment='用户减免电用量')  # 重命名
    user_reduction_water = db.Column(db.Numeric(10, 2), default=0.00, comment='用户减免水用量')    # 重命名
    #用户计费用量（用户级）
    user_billing_electric_usage = db.Column(db.Numeric(10, 2), default=0.00, comment='用户计电费量')  # 重命名
    user_billing_water_usage = db.Column(db.Numeric(10, 2), default=0.00, comment='用户计水费量')    # 重命名

    # 价格信息
    electric_price = db.Column(db.Numeric(10, 2), comment='电费单价')
    water_price = db.Column(db.Numeric(10, 2), comment='水费单价')

    # 费用计算
    #用户原始费用
    user_original_electric_fee = db.Column(db.Numeric(10, 2), comment='用户原始电费')  # 重命名
    user_original_water_fee = db.Column(db.Numeric(10, 2), comment='用户原始水费')    # 重命名
    user_original_total_fee = db.Column(db.Numeric(10, 2), comment='用户原始总费用')  # 重命名
    #用户计费费用
    user_billing_electric_fee = db.Column(db.Numeric(10, 2), default=0.00, comment='用户计费电费')  # 重命名
    user_billing_water_fee = db.Column(db.Numeric(10, 2), default=0.00, comment='用户计费水费')    # 重命名
    user_billing_total_fee = db.Column(db.Numeric(10, 2), default=0.00, comment='用户计费总费用')  # 重命名

    # 减免费用和应付费用字段
    room_total_reduction = db.Column(db.Numeric(10, 2), default=0.00, comment='房间级总减免额度')  # 调整
    user_proportional_reduction = db.Column(db.Numeric(10, 2), default=0.00, comment='用户按比例分摊的减免')  # 新增，用户房间级按比例减免费用
    user_independent_reduction = db.Column(db.Numeric(10, 2), default=0.00, comment='个人级独立减免')  # 新增
    payable_fee = db.Column(db.Numeric(10, 2), default=0.00, comment='用户应付费用')

    # 状态字段
    payment_status = db.Column(db.String(20), default='unpaid', comment='支付状态')
    checkout_status = db.Column(db.String(20), default='pending', comment='处理状态')
    remarks = db.Column(db.Text, nullable=True, comment='备注')

    # 时间戳
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 关联关系
    user = relationship('User', backref='utility_room_bill_checkout', lazy=True)
    room = relationship('Room', backref='utility_room_bill_checkout', lazy=True)


    @classmethod
    def create_from_checkout(cls, room_id, user_id, checkout_date, 
                            electric_reading, water_reading, remarks,
                            calculate_fee=True):
        """创建退宿费用记录"""
        try:
            logging.info(f"\n===== 开始创建退宿费用记录 =====")
            logging.info(f"参数: room_id={room_id}, user_id={user_id}, checkout_date={checkout_date}")

            # 新增：验证用户是否存在并且状态为在职
            user = User.query.get(user_id)
            if not user:
                raise ValueError(f"用户ID不存在: {user_id}")
            if not user.is_status():
                raise ValueError(f"用户ID={user_id}非在职状态，不能进行退宿费用核算")

            # 1.4 获取当期账期
            main_record = RoomUtilityRecord.get_by_room_and_date(room_id, checkout_date)
            if not main_record:
                main_record = RoomUtilityRecord.create_from_meter_reading(room_id, checkout_date)
                logging.info(f"自动创建账期记录: {main_record.billing_period}")
            
            period_start = main_record.start_date
            period_end = main_record.end_date
            billing_period = main_record.billing_period
            
            # 计算当月自然天数
            natural_days = (period_end.date() - period_start.date()).days + 1
            logging.info(f"账期: {period_start} 至 {period_end}, 当月自然天数: {natural_days}天")

            # 1. 基础信息获取
            room = Room.query.get(room_id)
            electric_meter_max = Decimal(str(room.electric_meter_max)) if room else Decimal('9999.99')
            water_meter_max = Decimal(str(room.water_meter_max)) if room else Decimal('9999.99')
            logging.info(f"表计量程 - 电表: {electric_meter_max}, 水表: {water_meter_max}")
            
            # 获取房间额定容量人数（假设Room模型有capacity字段表示房间容量）
            room_capacity = room.capacity or 1  # 默认1人，避免除以0
            if room_capacity <= 0:
                raise ValueError(f"房间容量必须大于0: {room_capacity}")
            logging.info(f"房间{room_id}的额定容量人数: {room_capacity}人")

            # 1.2 获取入住日期和住宿天数信息
            date_info = cls.calculate_stay_information(
                user_id=user_id,
                room_id=room_id,
                checkout_date=checkout_date
            )
            checkin_date = date_info['original_checkin_date']
            user_period_days = date_info['user_period_days']
            total_period_days = date_info['total_period_days']
            actual_occupant_count = date_info['actual_occupant_count']
            logging.info(f"用户{user_id}的原始入住日期: {checkin_date}, 当期居住天数: {user_period_days}, 房间总天数: {total_period_days}")
            logging.info(f"用户{user_id}在账期{period_start}至{period_end}内，实际入住人数: {actual_occupant_count}人")

            # 1.3 验证核心参数
            if not checkout_date or not isinstance(checkout_date, datetime):
                raise ValueError("退宿日期必须是有效的日期时间类型")
            if not checkin_date or checkin_date > checkout_date:
                raise ValueError("入住日期无效或晚于退宿日期")
            if total_period_days <= 0:
                raise ValueError(f"房间总天数必须大于零: {total_period_days}")


            # 1.5 获取上期抄表记录
            latest_meter = UtilityMeterReading.query.filter(
                UtilityMeterReading.room_id == room_id,
                UtilityMeterReading.reading_type == 1,
                UtilityMeterReading.reading_date < period_start
            ).order_by(UtilityMeterReading.reading_date.desc()).first()

            electric_previous = Decimal(str(latest_meter.electric_current)) if latest_meter else Decimal('0')
            water_previous = Decimal(str(latest_meter.water_current)) if latest_meter else Decimal('0')
            logging.info(f"上期抄表记录: 电={electric_previous}, 水={water_previous}")

            # 2. 初始化费用相关临时变量
            user_original_electric_usage = Decimal('0.00')
            user_original_water_usage = Decimal('0.00')
            user_billing_electric_usage = Decimal('0.00')
            user_billing_water_usage = Decimal('0.00')
            user_reduction_electric = Decimal('0.00')
            user_reduction_water = Decimal('0.00')
            
            meter_electric_usage = Decimal('0.00')
            meter_water_usage = Decimal('0.00')
            meter_electric_fee = Decimal('0.00')
            meter_water_fee = Decimal('0.00')
            meter_total_fee = Decimal('0.00')
            
            user_original_electric_fee = Decimal('0.00')
            user_original_water_fee = Decimal('0.00')
            user_original_total_fee = Decimal('0.00')
            
            user_billing_electric_fee = Decimal('0.00')
            user_billing_water_fee = Decimal('0.00')
            user_billing_total_fee = Decimal('0.00')
            
            room_total_reduction = Decimal('0.00')
            user_proportional_reduction = Decimal('0.00')
            user_independent_reduction = Decimal('0.00')
            user_payable = Decimal('0.00')
            
            checkout_status = 'pending_meter'

            # 3. 处理退宿读数
            has_meter_reading = (electric_reading is not None) and (water_reading is not None)
            if has_meter_reading:
                try:
                    electric_reading = Decimal(str(electric_reading))
                    water_reading = Decimal(str(water_reading))
                    logging.info(f"退宿读数 - 电: {electric_reading}, 水: {water_reading}")
                except (InvalidOperation, TypeError) as e:
                    raise ValueError(f"退宿抄表数据格式错误: {str(e)}")

            # 4. 计算住宿天数（确保不超过账期）
            max_possible_days = (period_end.date() - period_start.date()).days + 1
            user_period_days = min(user_period_days, max_possible_days)
            logging.info(f"用户当期已住天数: {user_period_days}")

            if user_period_days < 0:
                raise ValueError(f"当期已住天数不能为负数: {user_period_days}")

            # 初始化补贴变量，确保在任何情况下都有定义
            subsidies = {
                'electric_reduction': Decimal('0.00'),  # 房间总电减免量
                'water_reduction': Decimal('0.00'),    # 房间总水减免量
                'room_total_reduction': Decimal('0.00'),  # 房间级总金额减免
                'user_total_reduction': Decimal('0.00'),   # 个人级总金额减免
                'used_subsidies': []  # 记录已使用的补贴
            }
            
            # 初始化user_proportion变量（其他减免变量已在前面初始化）
            user_proportion = Decimal('0')
            
            if calculate_fee and has_meter_reading:
                # 5. 获取补贴配置及计算
                # 5.1 获取费用减免开关配置
                enable_fee_room_fee = SystemConfig.get_config_value('FEE_ROOM_FEE', False)
                enable_fee_user_fee = SystemConfig.get_config_value('FEE_USER_FEE', False)
                enable_fee_meter_reduction = SystemConfig.get_config_value('FEE_METER_reduction', False)
                logging.info(f"费用减免开关 - 房间级: {'启用' if enable_fee_room_fee else '禁用'}, "
                            f"个人级: {'启用' if enable_fee_user_fee else '禁用'}, "
                            f"用量级: {'启用' if enable_fee_meter_reduction else '禁用'}")

                # 5.2 查询补贴记录（直接从主表获取可用额度）
                room_subsidies = FeeSubsidy.query.filter(
                    FeeSubsidy.room_id == room_id,
                    FeeSubsidy.is_enabled == True,
                    FeeSubsidy.effective_date <= checkout_date
                ).all()
                
                user_subsidies = FeeSubsidy.query.filter(
                    FeeSubsidy.user_id == user_id,
                    FeeSubsidy.fee_type == '住宿补贴',
                    FeeSubsidy.is_enabled == True,
                    FeeSubsidy.effective_date <= checkout_date
                ).all()
                
                # 5.3 处理房间级补贴（直接使用主表额度）
                for subsidy in room_subsidies:
                    # 直接从主表获取额度，不查询子表的剩余额度
                    logging.info(f"房间级补贴[{subsidy.id}]主表额度 - 金额: {subsidy.amount}, "
                                f"电用量: {subsidy.electric_reduction}, 水用量: {subsidy.water_reduction}")
                    
                    if subsidy.fee_type == "房间水电按用量减免" and enable_fee_meter_reduction:
                        # 累加可用的水电减免量（直接使用主表额度）
                        subsidies['electric_reduction'] += Decimal(str(subsidy.electric_reduction or 0))
                        subsidies['water_reduction'] += Decimal(str(subsidy.water_reduction or 0))
                        subsidies['used_subsidies'].append({
                            'subsidy': subsidy,
                            'total_electric': subsidy.electric_reduction or 0,
                            'total_water': subsidy.water_reduction or 0
                        })
                    elif subsidy.fee_type == "房间水电按金额减免" and enable_fee_room_fee:
                        # 累加可用的金额减免（直接使用主表额度）
                        subsidies['room_total_reduction'] += Decimal(str(subsidy.amount or 0))
                        subsidies['used_subsidies'].append({
                            'subsidy': subsidy,
                            'total_amount': subsidy.amount or 0
                        })
                
                # 处理个人级补贴（直接使用主表额度）
                for subsidy in user_subsidies:
                    if enable_fee_user_fee:
                        # 直接从主表获取额度
                        logging.info(f"个人级补贴[{subsidy.id}]主表额度 - 金额: {subsidy.amount}")
                        
                        subsidies['user_total_reduction'] += Decimal(str(subsidy.amount or 0))
                        subsidies['used_subsidies'].append({
                            'subsidy': subsidy,
                            'total_amount': subsidy.amount or 0
                        })
                
                # 计算用户按比例分摊的减免额度
                # 新规则：A的减免比例 = 总额度 / 当月自然天数 / 房间额定容量人数
                # A的减免额度 = 总减免额度 × A的减免比例
                # 不论何时，如果退宿前房间只有1人入住，则使用1作为计算容量
                
                user_proportion = Decimal('0')

                if natural_days > 0:
                    # 使用已获取的房间信息和容量，避免重复查询
                    calculated_room_capacity = room_capacity
                    
                    # 获取特殊减免规则配置
                    checkout_enable_special_reduction = SystemConfig.get_config_value('CHECKOUT_ENABLE_SPECIAL_REDUCTION_RULE', 'True')
                    checkout_room_capacity_half_threshold = SystemConfig.get_config_value('CHECKOUT_ROOM_CAPACITY_HALF_THRESHOLD', 6)
                    
                    # 应用特殊规则：优先检查1人情况，再检查减半规则
                    if checkout_enable_special_reduction:
                        # 如果实际入住只有1人，则使用1作为计算容量
                        if actual_occupant_count == 1:
                            calculated_room_capacity = 1
                            logging.info(f"已启用特殊减免规则，房间{room_id}实际入住{actual_occupant_count}人，使用1人作为计算容量（1人规则）")
                        # 再检查减半规则：如果房间容量>=阈值且实际入住人数<=容量一半时，按一半容量计算
                        elif room and room.capacity >= checkout_room_capacity_half_threshold and actual_occupant_count <= room.capacity / 2:
                            calculated_room_capacity = max(1, room.capacity // 2)  # 向下取整，至少为1
                            logging.info(f"已启用特殊减免规则，房间{room_id}容量为{room.capacity}人，实际入住{actual_occupant_count}人，使用{calculated_room_capacity}人作为计算容量（减半规则）")
                        else:
                            # 其他情况使用房间额定容量
                            calculated_room_capacity = room_capacity
                        logging.info(f"已启用特殊减免规则，房间容量减半阈值：{checkout_room_capacity_half_threshold}人")
                    else:
                        # 如果实际入住只有1人，则使用1作为计算容量
                        if actual_occupant_count == 1:
                            calculated_room_capacity = 1
                            logging.info(f"未启用特殊减免规则，房间{room_id}实际入住{actual_occupant_count}人，使用1人作为计算容量（1人规则）")
                        else:
                            # 未启用特殊减免规则，使用房间额定容量
                            calculated_room_capacity = room_capacity
                            logging.info(f"未启用特殊减免规则，使用房间额定容量{calculated_room_capacity}人作为计算容量")
                    
                    # 应用比例计算公式
                    user_proportion = (Decimal('1') / Decimal(str(natural_days))) / Decimal(str(calculated_room_capacity))
                    logging.info(f"房间{room_id}实际入住人数为{actual_occupant_count}人，使用{calculated_room_capacity}人作为计算容量")

                    user_reduction_electric = round(subsidies['electric_reduction'] * user_proportion * Decimal(str(user_period_days)), 2)
                    user_reduction_water = round(subsidies['water_reduction'] * user_proportion * Decimal(str(user_period_days)), 2)
                    user_proportional_reduction = round(subsidies['room_total_reduction'] * user_proportion * Decimal(str(user_period_days)), 2)
                    logging.info(f"补贴计算 - 房间总减免: 电{subsidies['electric_reduction']}, 水{subsidies['water_reduction']}, 金额{subsidies['room_total_reduction']}")
                    logging.info(f"用户分摊比例: {user_proportion}, 减免 - 电{user_reduction_electric}, 水{user_reduction_water}, 金额{user_proportional_reduction}, 个人独立减免{user_independent_reduction}")

                else:
                    # 处理异常情况
                    user_proportion = Decimal('0')
                    user_reduction_electric = Decimal('0.00')
                    user_reduction_water = Decimal('0.00')
                    user_proportional_reduction = Decimal('0.00')
                    logging.warning(f"无法计算用户分摊比例，自然天数: {natural_days}, 房间容量: {room_capacity}")
            

                # 6. 费用计算
            
                # 6.1 获取价格配置
                price_config = cls.get_price_config_from_system()
                electric_price = Decimal(str(price_config['electric_price']))
                water_price = Decimal(str(price_config['water_price']))
                logging.info(f"价格配置: 电{electric_price}, 水{water_price}")

                # 6.2 计算房间总抄表用量（房间级原始数据）
                meter_electric_usage = round(electric_reading - electric_previous, 2)
                meter_water_usage = round(water_reading - water_previous, 2)
                
                # 处理电表翻转
                if meter_electric_usage < 0:
                    meter_electric_usage = (electric_meter_max - electric_previous) + electric_reading
                if meter_water_usage < 0:
                    meter_water_usage = (water_meter_max - water_previous) + water_reading
                
                # 计算房间总抄表费用
                meter_electric_fee = round(meter_electric_usage * electric_price, 2)
                meter_water_fee = round(meter_water_usage * water_price, 2)
                meter_total_fee = round(meter_electric_fee + meter_water_fee, 2)
                logging.info(f"房间总抄表 - 电用量: {meter_electric_usage}, 水用量: {meter_water_usage}, 总费用: {meter_total_fee}")

                # 6.3 计算用户原始用量 
                # 用户原始用量 = 房间总抄表用量 × (用户实际住宿天数 / 宿舍所有人总住宿天数)
                if total_period_days > 0:
                    user_ratio = Decimal(str(user_period_days)) / Decimal(str(total_period_days))
                    user_original_electric_usage = round(meter_electric_usage * user_ratio, 2)
                    user_original_water_usage = round(meter_water_usage * user_ratio, 2)
                    
                    # 计算用户原始费用
                    user_original_electric_fee = round(user_original_electric_usage * electric_price, 2)
                    user_original_water_fee = round(user_original_water_usage * water_price, 2)
                    user_original_total_fee = round(user_original_electric_fee + user_original_water_fee, 2)
                
                logging.info(f"用户原始用量 - 电: {user_original_electric_usage}, 水: {user_original_water_usage}, 总费用: {user_original_total_fee}")

                # 6.4 计算用户计费用量（减免后）
                user_billing_electric_usage = user_original_electric_usage
                user_billing_water_usage = user_original_water_usage
                
                if enable_fee_meter_reduction:
                    # 实际使用的减免量不能超过可用额度和实际用量
                    actual_electric_reduction = min(user_billing_electric_usage, user_reduction_electric)
                    actual_water_reduction = min(user_billing_water_usage, user_reduction_water)
                    
                    user_billing_electric_usage -= actual_electric_reduction
                    user_billing_water_usage -= actual_water_reduction
                    
                    # 更新实际使用的减免量
                    user_reduction_electric = actual_electric_reduction
                    user_reduction_water = actual_water_reduction
                
                logging.info(f"用户计费用量 - 电: {user_billing_electric_usage}, 水: {user_billing_water_usage}")

                # 6.5 计算用户计费费用
                user_billing_electric_fee = round(user_billing_electric_usage * electric_price, 2)
                user_billing_water_fee = round(user_billing_water_usage * water_price, 2)
                user_billing_total_fee = round(user_billing_electric_fee + user_billing_water_fee, 2)
                
                # 应用房间级按比例减免
                user_billing_total_fee_after_reduction = user_billing_total_fee - user_proportional_reduction
                user_billing_total_fee_after_reduction = Decimal('0.00') if user_billing_total_fee_after_reduction < 0 else user_billing_total_fee_after_reduction
                
                # 应用个人级独立减免 - 修复部分
                # 个人级补贴不按比例计算，只取实际可减免金额
                # 实际减免金额 = min(个人级总补贴金额, 房间级减免后剩余费用)
                user_independent_reduction = min(subsidies['user_total_reduction'], user_billing_total_fee_after_reduction)
                user_independent_reduction = round(user_independent_reduction, 2)
                
                # 计算最终应付费用
                user_payable = user_billing_total_fee_after_reduction - user_independent_reduction
                user_payable = Decimal('0.00') if user_payable < 0 else user_payable
                
                logging.info(f"用户计费费用 - 减免前: {user_billing_total_fee}, 房间级减免后: {user_billing_total_fee_after_reduction}, "
                            f"个人级补贴总额: {subsidies['user_total_reduction']}, 实际个人减免: {user_independent_reduction}, 最终应付: {user_payable}")

            # 7. 创建退宿费用记录
            checkout_record = cls(
                record_id=main_record.record_id,
                user_id=user_id,
                room_id=room_id,
                checkin_date=checkin_date,
                checkout_date=checkout_date,
                stay_days=(checkout_date.date() - checkin_date.date()).days + 1,
                user_period_days=user_period_days,
                total_period_days=total_period_days,
                natural_days=natural_days,
                
                # 抄表数据（房间级）
                meter_electric_usage=meter_electric_usage,
                meter_water_usage=meter_water_usage,
                meter_electric_fee=meter_electric_fee,
                meter_water_fee=meter_water_fee,
                meter_total_fee=meter_total_fee,
                
                electric_reading=electric_reading,
                electric_previous=electric_previous,
                water_reading=water_reading,
                water_previous=water_previous,
                
                # 用户用量数据
                user_original_electric_usage=user_original_electric_usage,
                user_original_water_usage=user_original_water_usage,
                user_reduction_electric=user_reduction_electric,
                user_reduction_water=user_reduction_water,
                user_billing_electric_usage=user_billing_electric_usage,
                user_billing_water_usage=user_billing_water_usage,
                
                # 价格信息
                electric_price=electric_price if calculate_fee else Decimal('0.00'),
                water_price=water_price if calculate_fee else Decimal('0.00'),
                
                # 费用计算
                user_original_electric_fee=user_original_electric_fee,
                user_original_water_fee=user_original_water_fee,
                user_original_total_fee=user_original_total_fee,
                user_billing_electric_fee=user_billing_electric_fee,
                user_billing_water_fee=user_billing_water_fee,
                user_billing_total_fee=user_billing_total_fee,
                
                # 减免费用
                room_total_reduction=subsidies['room_total_reduction'],
                user_proportional_reduction=user_proportional_reduction,
                user_independent_reduction=user_independent_reduction,
                payable_fee=user_payable,
                remarks=remarks,
                
                checkout_status='completed' if calculate_fee else checkout_status
            )
            db.session.add(checkout_record)
            
            # 8. 创建补贴使用记录 - 应用新的用户比例计算方式
            if calculate_fee and has_meter_reading and subsidies['used_subsidies']:
                for used in subsidies['used_subsidies']:
                    subsidy = used['subsidy']
                    # 获取用户姓名
                    user = User.query.get(user_id)
                    user_name = user.name if user else f'用户{user_id}'
                    usage_data = {
                        'room_id': room_id,
                        'user_id': user_id,
                        'is_checkout': 1,  # 标记为退宿费用子表上传
                        'remark': f"退宿费用减免 - {user_name}，账期{billing_period}，比例{user_proportion:.2f}"
                    }
                    
                    # 根据补贴类型设置使用量
                    if 'total_amount' in used:
                        # 房间级补贴按比例计算，个人级补贴使用实际减免值
                        if subsidy.user_id == user_id and subsidy.fee_type == '住宿补贴':
                            # 个人级补贴使用实际减免金额
                            used_amount = user_independent_reduction
                        else:
                            # 房间级补贴按比例计算
                            used_amount = round(Decimal(str(used['total_amount'])) * user_proportion * Decimal(str(user_period_days)), 2)
                        usage_data['used_amount'] = used_amount if used_amount > 0 else Decimal('0.00')
                    if 'total_electric' in used:
                        # 按新比例计算实际使用的电减免量
                        used_electric = round(Decimal(str(used['total_electric'])) * user_proportion * Decimal(str(user_period_days)), 2)
                        usage_data['used_electric'] = used_electric if used_electric > 0 else Decimal('0.00')
                    if 'total_water' in used:
                        # 按新比例计算实际使用的水减免量
                        used_water = round(Decimal(str(used['total_water'])) * user_proportion * Decimal(str(user_period_days)), 2)
                        usage_data['used_water'] = used_water if used_water > 0 else Decimal('0.00')
                    
                    # 创建使用记录
                    FeeSubsidyUsage.create_usage_record(
                        subsidy=subsidy,
                        billing_period=billing_period,
                        usage_data=usage_data
                    )
                    logging.info(f"已记录补贴[{subsidy.id}]按新比例使用情况: {usage_data}")

            # 9. 更新主表
            # 计算减免金额上传到主表

            if has_meter_reading:
                main_record.add_checkout_fees(user_billing_electric_fee, user_billing_water_fee)
                logging.info(f"主记录更新成功: 已结算电费={main_record.checked_out_electric_fee}, 已结算水费={main_record.checked_out_water_fee}")
                
            #db.session.commit()
            logging.info("===== 退宿费用记录创建完成 =====")
            return checkout_record
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"费用计算异常: {str(e)}", exc_info=True)
            raise

    def update_checkout_record(self, new_electric_reading=None, new_water_reading=None,
                              user_period_days=None, total_period_days=None):
        """更新退宿记录"""
        try:
            # 1. 验证主记录和房间信息
            main_record = RoomUtilityRecord.query.get(self.record_id)
            if not main_record:
                raise ValueError(f"关联的主账单记录不存在，record_id={self.record_id}")
            
            room = Room.query.get(main_record.room_id)
            if not room:
                raise ValueError(f"主记录关联的房间不存在，room_id={main_record.room_id}")
            # 获取房间额定容量人数
            room_capacity = room.capacity or 1  # 默认1人，避免除以0
            if room_capacity <= 0:
                raise ValueError(f"房间容量必须大于0: {room_capacity}")
            logging.info(f"房间{self.room_id}的额定容量人数: {room_capacity}人")

            billing_period = main_record.billing_period
            period_start = main_record.start_date
            period_end = main_record.end_date
            natural_days = (period_end.date() - period_start.date()).days + 1

            # 2. 保存旧费用用于计算调整差值
            old_electric_fee = self.user_billing_electric_fee or Decimal('0.00')
            old_water_fee = self.user_billing_water_fee or Decimal('0.00')

            # 3. 初始化临时变量
            usage_updated = False

            # 4. 处理新抄表读数
            if new_electric_reading is not None:
                try:
                    new_electric_reading = Decimal(str(new_electric_reading))
                    if new_electric_reading < 0:
                        raise ValueError("电表读数不能为负数")
                except (InvalidOperation, TypeError):
                    raise ValueError("电表读数必须是有效的数字")

                self.electric_reading = new_electric_reading
                usage_updated = True

            if new_water_reading is not None:
                try:
                    new_water_reading = Decimal(str(new_water_reading))
                    if new_water_reading < 0:
                        raise ValueError("水表读数不能为负数")
                except (InvalidOperation, TypeError):
                    raise ValueError("水表读数必须是有效的数字")

                self.water_reading = new_water_reading
                usage_updated = True

            # 5. 更新天数参数
            days_updated = False
            if user_period_days is not None and user_period_days != self.user_period_days:
                if user_period_days < 0:
                    raise ValueError("用户当期期住宿天数不能为负数")
                self.user_period_days = user_period_days
                days_updated = True

            if total_period_days is not None and total_period_days != self.total_period_days:
                if total_period_days <= 0:
                    raise ValueError("总住宿天数必须大于零")
                self.total_period_days = total_period_days
                days_updated = True

            # 如果没有手动更新天数，重新计算天数
            if not days_updated and (usage_updated or not self.user_period_days or not self.total_period_days):
                date_info = self.calculate_stay_information(
                    user_id=self.user_id,
                    room_id=self.room_id,
                    checkout_date=self.checkout_date,
                    period_start=period_start,
                    period_end=period_end
                )
                self.user_period_days = date_info['user_period_days']
                self.total_period_days = date_info['total_period_days']
                days_updated = True
                actual_occupant_count = date_info['actual_occupant_count']  # 获取实际入住人数
            

            # 验证天数有效性
            if self.total_period_days <= 0:
                raise ValueError(f"房间总天数必须大于零: {self.total_period_days}")
            if self.user_period_days < 0:
                raise ValueError(f"用户当期住宿天数不能为负数: {self.user_period_days}")

            # 6. 补贴计算
            if usage_updated or days_updated:
                # 6.1 获取价格配置
                price_config = self.get_price_config_from_system()
                electric_price = Decimal(str(price_config['electric_price']))
                water_price = Decimal(str(price_config['water_price']))
                self.electric_price = electric_price
                self.water_price = water_price

                # 6.2 获取费用减免开关配置
                enable_fee_room_fee = SystemConfig.get_config_value('FEE_ROOM_FEE', False)
                enable_fee_user_fee = SystemConfig.get_config_value('FEE_USER_FEE', False)
                enable_fee_meter_reduction = SystemConfig.get_config_value('FEE_METER_reduction', False)
                
                # 6.3 重新计算房间总抄表用量
                if self.electric_previous is not None and self.electric_reading is not None:
                    electric_max = Decimal(str(room.electric_meter_max)) if room.electric_meter_max else Decimal('9999.99')
                    raw_usage = self.electric_reading - self.electric_previous
                    self.meter_electric_usage = (electric_max - self.electric_previous) + self.electric_reading if raw_usage < 0 else raw_usage
                    self.meter_electric_fee = round(self.meter_electric_usage * electric_price, 2)
                
                if self.water_previous is not None and self.water_reading is not None:
                    water_max = Decimal(str(room.water_meter_max)) if room.water_meter_max else Decimal('9999.99')
                    raw_usage = self.water_reading - self.water_previous
                    self.meter_water_usage = (water_max - self.water_previous) + self.water_reading if raw_usage < 0 else raw_usage
                    self.meter_water_fee = round(self.meter_water_usage * water_price, 2)
                
                self.meter_total_fee = round(self.meter_electric_fee + self.meter_water_fee, 2)

                # 6.4 计算用户原始用量
                if self.total_period_days > 0:
                    user_ratio = Decimal(str(self.user_period_days)) / Decimal(str(self.total_period_days))
                    self.user_original_electric_usage = round(self.meter_electric_usage * user_ratio, 2) if self.meter_electric_usage else Decimal('0.00')
                    self.user_original_water_usage = round(self.meter_water_usage * user_ratio, 2) if self.meter_water_usage else Decimal('0.00')
                    
                    # 计算用户原始费用
                    self.user_original_electric_fee = round(self.user_original_electric_usage * electric_price, 2)
                    self.user_original_water_fee = round(self.user_original_water_usage * water_price, 2)
                    self.user_original_total_fee = round(self.user_original_electric_fee + self.user_original_water_fee, 2)

                # 6.5 查询补贴记录（直接从主表获取可用额度）
                room_subsidies = FeeSubsidy.query.filter(
                    FeeSubsidy.room_id == self.room_id,
                    FeeSubsidy.is_enabled == True,
                    FeeSubsidy.effective_date <= (self.checkout_date or datetime.now())
                ).all()
                
                user_subsidies = FeeSubsidy.query.filter(
                    FeeSubsidy.user_id == self.user_id,
                    FeeSubsidy.fee_type == '住宿补贴',
                    FeeSubsidy.is_enabled == True,
                    FeeSubsidy.effective_date <= (self.checkout_date or datetime.now())
                ).all()
                
                # 6.6 计算补贴金额（直接使用主表额度）
                subsidies = {
                    'electric_reduction': Decimal('0.00'),
                    'water_reduction': Decimal('0.00'),
                    'room_total_reduction': Decimal('0.00'),
                    'user_total_reduction': Decimal('0.00'),
                    'used_subsidies': []
                }
                
                # 处理房间级补贴（直接使用主表额度）
                for subsidy in room_subsidies:
                    # 直接从主表获取额度，不查询子表的剩余额度
                    logging.info(f"房间级补贴[{subsidy.id}]主表额度 - 金额: {subsidy.amount}, "
                                f"电费: {subsidy.electric_reduction}, 水费: {subsidy.water_reduction}")
                    
                    if subsidy.fee_type == "房间水电按用量减免" and enable_fee_meter_reduction:
                        subsidies['electric_reduction'] += Decimal(str(subsidy.electric_reduction or 0))
                        subsidies['water_reduction'] += Decimal(str(subsidy.water_reduction or 0))
                        subsidies['used_subsidies'].append({
                            'subsidy': subsidy,
                            'total_electric': subsidy.electric_reduction or 0,
                            'total_water': subsidy.water_reduction or 0
                        })
                    elif subsidy.fee_type == "房间水电按金额减免" and enable_fee_room_fee:
                        subsidies['room_total_reduction'] += Decimal(str(subsidy.amount or 0))
                        subsidies['used_subsidies'].append({
                            'subsidy': subsidy,
                            'total_amount': subsidy.amount or 0
                        })
                
                # 处理个人级补贴（直接使用主表额度）
                for subsidy in user_subsidies:
                    if enable_fee_user_fee:
                        # 直接从主表获取额度
                        logging.info(f"个人级补贴[{subsidy.id}]主表额度 - 金额: {subsidy.amount}")
                        
                        subsidies['user_total_reduction'] += Decimal(str(subsidy.amount or 0))
                        subsidies['used_subsidies'].append({
                            'subsidy': subsidy,
                            'total_amount': subsidy.amount or 0
                        })
                
                # 更新房间级总减免
                self.room_total_reduction = subsidies['room_total_reduction']
                
                # 计算用户按比例分摊的减免额度
                # 新规则：A的减免比例 = 总额度 / 当月自然天数 / 房间额定容量
                # A的减免额度 = 总减免额度 × A的减免比例 × 用户实际住宿天数
                # 不论何时，如果退宿前房间只有1人入住，则使用1作为计算容量
                
                if natural_days > 0 and room_capacity > 0:
                    # 应用特殊规则：优先检查1人情况，再检查减半规则
                    calculated_room_capacity = room_capacity
                    
                    # 获取特殊减免规则配置
                    checkout_enable_special_reduction = SystemConfig.get_config_value('CHECKOUT_ENABLE_SPECIAL_REDUCTION_RULE', 'True')
                    checkout_room_capacity_half_threshold = SystemConfig.get_config_value('CHECKOUT_ROOM_CAPACITY_HALF_THRESHOLD', 6)
                    
                    if checkout_enable_special_reduction:
                        # 如果实际入住只有1人，则使用1作为计算容量
                        if actual_occupant_count == 1:
                            calculated_room_capacity = 1
                            logging.info(f"房间{self.room_id}实际入住{actual_occupant_count}人，使用1人作为计算容量（1人规则）")
                        # 再检查减半规则：如果房间容量>=阈值且实际入住人数<=容量一半时，按一半容量计算
                        elif room and room.capacity >= checkout_room_capacity_half_threshold and actual_occupant_count <= room.capacity / 2:
                            calculated_room_capacity = max(1, room.capacity // 2)  # 向下取整，至少为1
                            logging.info(f"已启用特殊减免规则，房间{self.room_id}容量为{room.capacity}人，实际入住{actual_occupant_count}人，使用{calculated_room_capacity}人作为计算容量（减半规则）")
                        else:
                            # 其他情况使用房间额定容量
                            calculated_room_capacity = room_capacity
                        logging.info(f"已启用特殊减免规则，房间容量减半阈值：{checkout_room_capacity_half_threshold}人")
                    else:
                        # 如果实际入住只有1人，则使用1作为计算容量
                        if actual_occupant_count == 1:
                            calculated_room_capacity = 1
                            logging.info(f"未启用特殊减免规则，房间{self.room_id}实际入住{actual_occupant_count}人，使用1人作为计算容量（1人规则）")
                        else:
                            # 未启用特殊减免规则，使用房间额定容量
                            calculated_room_capacity = room_capacity
                            logging.info(f"未启用特殊减免规则，使用房间额定容量{calculated_room_capacity}人作为计算容量")
                    
                    # 应用新的比例计算公式
                    user_proportion = (Decimal('1') / Decimal(str(natural_days))) / Decimal(str(calculated_room_capacity))
                    self.user_reduction_electric = round(subsidies['electric_reduction'] * user_proportion * Decimal(str(self.user_period_days)), 2)
                    self.user_reduction_water = round(subsidies['water_reduction'] * user_proportion * Decimal(str(self.user_period_days)), 2)
                    self.user_proportional_reduction = round(subsidies['room_total_reduction'] * user_proportion * Decimal(str(self.user_period_days)), 2)
                else:
                    self.user_proportion = Decimal('0')
                    self.user_reduction_electric = Decimal('0.00')
                    self.user_reduction_water = Decimal('0.00')
                    self.user_proportional_reduction = Decimal('0.00')
                    logging.warning(f"无法计算用户分摊比例，自然天数: {natural_days}, 房间人数: {room_capacity}")
                
                # 个人级独立减免
                self.user_independent_reduction = subsidies['user_total_reduction']
                
                # 6.7 计算用户计费用量（减免后）
                self.user_billing_electric_usage = self.user_original_electric_usage
                self.user_billing_water_usage = self.user_original_water_usage
                
                if enable_fee_meter_reduction:
                    actual_electric_reduction = min(self.user_billing_electric_usage, self.user_reduction_electric)
                    actual_water_reduction = min(self.user_billing_water_usage, self.user_reduction_water)
                    
                    self.user_billing_electric_usage -= actual_electric_reduction
                    self.user_billing_water_usage -= actual_water_reduction
                    
                    self.user_reduction_electric = actual_electric_reduction
                    self.user_reduction_water = actual_water_reduction

                # 6.8 计算用户计费费用
                self.user_billing_electric_fee = round(self.user_billing_electric_usage * electric_price, 2)
                self.user_billing_water_fee = round(self.user_billing_water_usage * water_price, 2)
                self.user_billing_total_fee = round(self.user_billing_electric_fee + self.user_billing_water_fee, 2)
                
                # 应用房间级按比例减免
                after_room_reduction = self.user_billing_total_fee - self.user_proportional_reduction
                after_room_reduction = Decimal('0.00') if after_room_reduction < 0 else after_room_reduction
                
                # 应用个人级独立减免 - 修复部分
                # 个人级补贴不按比例计算，只取实际可减免金额
                # 实际减免金额 = min(个人级总补贴金额, 房间级减免后剩余费用)
                self.user_independent_reduction = min(subsidies['user_total_reduction'], after_room_reduction)
                self.user_independent_reduction = round(self.user_independent_reduction, 2)
                
                # 计算最终应付费用
                self.payable_fee = after_room_reduction - self.user_independent_reduction
                self.payable_fee = round(self.payable_fee, 2)
                self.payable_fee = Decimal('0.00') if self.payable_fee < 0 else self.payable_fee

                logging.info(f"用户计费费用 - 减免前: {self.user_billing_total_fee}, 房间级减免后: {after_room_reduction}, "
                            f"个人级补贴总额: {subsidies['user_total_reduction']}, 实际个人减免: {self.user_independent_reduction}, 最终应付: {self.payable_fee}")

                # 6.9 费用调整值
                electric_adjustment = self.user_billing_electric_fee - old_electric_fee
                water_adjustment = self.user_billing_water_fee - old_water_fee

                # 7. 更新补贴使用记录（先删除旧记录，再创建新记录）
                # 7.1 删除该记录相关的旧补贴使用记录
                for usage in FeeSubsidyUsage.query.filter(
                    FeeSubsidyUsage.room_id == self.room_id,
                    FeeSubsidyUsage.user_id == self.user_id,
                    FeeSubsidyUsage.billing_period == billing_period,
                    FeeSubsidyUsage.is_checkout == '1'
                ).all():
                    db.session.delete(usage)
                
                # 7.2 创建新的补贴使用记录 - 应用新的用户比例计算方式
                if subsidies['used_subsidies']:
                    for used in subsidies['used_subsidies']:
                        subsidy = used['subsidy']
                        usage_data = {
                            'room_id': self.room_id,
                            'user_id': self.user_id,
                            'is_checkout': 1,
                            'remark': f"退宿费用减免(更新) - 账期{billing_period}，比例{user_proportion}"
                        }
                        
                        # 根据补贴类型设置使用量
                        if 'total_amount' in used:
                            # 房间级补贴按比例计算，个人级补贴使用实际减免值
                            if subsidy.user_id == self.user_id and subsidy.fee_type == '住宿补贴':
                                # 个人级补贴使用实际减免金额
                                used_amount = self.user_independent_reduction
                            else:
                                # 房间级补贴按比例计算
                                used_amount = round(Decimal(str(used['total_amount'])) * user_proportion * Decimal(str(self.user_period_days)), 2)
                            usage_data['used_amount'] = used_amount if used_amount > 0 else Decimal('0.00')
                        if 'total_electric' in used:
                            used_electric = round(Decimal(str(used['total_electric'])) * user_proportion * Decimal(str(self.user_period_days)), 2)
                            usage_data['used_electric'] = used_electric if used_electric > 0 else Decimal('0.00')
                        if 'total_water' in used:
                            used_water = round(Decimal(str(used['total_water'])) * user_proportion * Decimal(str(self.user_period_days)), 2)
                            usage_data['used_water'] = used_water if used_water > 0 else Decimal('0.00')
                        
                        FeeSubsidyUsage.create_usage_record(
                            subsidy=subsidy,
                            billing_period=billing_period,
                            usage_data=usage_data
                        )
                        logging.info(f"已更新补贴[{subsidy.id}]按新比例使用情况: {usage_data}")

             # 计算减免金额上传到主表
            # 8. 同步主表
            if usage_updated or days_updated:
                main_record.add_checkout_fees(electric_adjustment, water_adjustment)
                main_record._recalculate_fees()

            # 9. 更新状态与时间戳
            self.checkout_status = 'completed'
            self.updated_at = datetime.now()
            main_record.updated_at = datetime.now()
            self.natural_days = natural_days

            db.session.commit()
            logging.info(f"退宿记录更新成功: ID={self.id}, 主表ID={main_record.record_id}")
            return self

        except Exception as e:
            db.session.rollback()
            logging.error(f"更新退宿记录失败：{str(e)}", exc_info=True)
            raise

    @classmethod
    def calculate_stay_information(cls, user_id, room_id, checkout_date, period_start=None, period_end=None):
        """统一计算住宿相关日期信息，充分利用住宿链数据"""
        # 实现保持不变
        # 1. 获取用户住宿链信息
        latest_dorm = Dorm.get_user_latest_dorm(user_id)
        if not latest_dorm:
            raise ValueError(f"用户ID={user_id}未找到任何住宿记录")
        
        dorm_chain = latest_dorm.dorm_chain
        if not dorm_chain:
            raise ValueError(f"用户ID={user_id}未找到有效的住宿历史链")
        
        # 取历史链中的第一条记录作为原始入住记录
        original_dorm = dorm_chain[0]
        if not original_dorm.check_in_date:
            raise ValueError(f"用户ID={user_id}的原始住宿记录缺少入住日期")
        
        original_checkin_date = original_dorm.check_in_date
        
        # 2. 获取账期
        if not period_start or not period_end:
            main_record = RoomUtilityRecord.get_by_room_and_date(room_id, checkout_date)
            if main_record:
                period_start = main_record.start_date
                period_end = main_record.end_date
            else:
                # 如果没有主记录，停止计算并输出错误
                logging.error(f"无法获取房间{room_id}在日期{checkout_date}的水电费主记录，无法确定账期")
                raise ValueError(f"无法获取房间{room_id}在日期{checkout_date}的水电费主记录，无法进行退宿费用核算")
        
        # 3. 利用住宿链计算用户当期住宿天数
        user_period_days = 0
        for dorm in dorm_chain:
            # 只计算当前房间的住宿记录
            if dorm.room_id != room_id:
                continue
                
            # 确定该段住宿的有效开始和结束日期
            stay_start = max(dorm.check_in_date, period_start)
            stay_end = min(
                dorm.check_out_date or checkout_date,  # 已退宿用实际日期，在住用当前退宿日期
                checkout_date,
                period_end
            )
            
            # 累加有效住宿天数
            if stay_start <= stay_end:
                days = (stay_end.date() - stay_start.date()).days + 1  # 包含首尾日期
                user_period_days += days
                logging.debug(
                    f"用户{user_id}在房间{room_id}的住宿段: {stay_start}至{stay_end}, "
                    f"计{days}天"
                )
        
        # 4. 计算房间总住宿天数和入住人数 - 利用房间所有有效住宿记录
        # 获取房间所有有效住宿记录，排除自离用户
        room_dorms = Dorm.query.join(User).filter(
            Dorm.room_id == room_id,
            Dorm.status.in_(['active', 'checked_out']),
            Dorm.check_in_date <= checkout_date,
            db.or_(
                Dorm.check_out_date >= period_start,
                Dorm.check_out_date.is_(None)
            ),
            User.status != '自离'  # 排除自离用户
        ).all()
        
        total_period_days = 0
        # 为避免重复计算，使用字典记录每个用户在特定时间段的住宿
        user_stays = {}
        
        for dorm in room_dorms:
            user_key = f"{dorm.user_id}"
            stay_start = max(dorm.check_in_date, period_start)
            stay_end = min(
                dorm.check_out_date or checkout_date,
                checkout_date,
                period_end
            )
            
            if stay_start > stay_end:
                continue
                
            # 计算该用户在该段的住宿天数
            days = (stay_end.date() - stay_start.date()).days + 1
            
            # 记录用户住宿信息，避免重复计算
            if user_key not in user_stays:
                user_stays[user_key] = []
            
            # 检查是否与已有住宿时间段重叠
            overlap = False
            for existing in user_stays[user_key]:
                if not (stay_end < existing['start'] or stay_start > existing['end']):
                    # 有重叠，取并集
                    new_start = min(stay_start, existing['start'])
                    new_end = max(stay_end, existing['end'])
                    existing['start'] = new_start
                    existing['end'] = new_end
                    overlap = True
                    break
            
            if not overlap:
                user_stays[user_key].append({
                    'start': stay_start,
                    'end': stay_end,
                    'days': days
                })
        
        # 累加所有用户的非重叠住宿天数
        for user_key, stays in user_stays.items():
            for stay in stays:
                total_period_days += stay['days']
                logging.debug(
                    f"用户{user_key}在房间{room_id}的有效住宿: {stay['start']}至{stay['end']}, "
                    f"计{stay['days']}天"
                )
        
        # 计算账期内的入住人数（已排除自离用户）
        actual_occupant_count = len(user_stays)
        
        logging.info(
            f"房间{room_id}在账期[{period_start}至{period_end}]内，"
            f"截止到{checkout_date}的总住宿天数：{total_period_days}天，入住人数：{actual_occupant_count}人"
        )
        
        return {
            'original_checkin_date': original_checkin_date,
            'user_period_days': user_period_days,
            'total_period_days': total_period_days,
            'actual_occupant_count': actual_occupant_count  # 添加账期内的入住人数统计
        }

    @classmethod
    def get_price_config_from_system(cls):
        """从系统配置获取水电单价"""
        try:
            return {
                'electric_price': Decimal(SystemConfig.get_config_value('ELECTRICITY_PRICE', 0.56)),
                'water_price': Decimal(SystemConfig.get_config_value('WATER_PRICE', 3.8))
            }
        except (ValueError, TypeError) as e:
            logging.error(f"从系统配置获取价格失败: {str(e)}")
            # 失败时返回默认值，确保系统可用
            return {
                'electric_price': Decimal('0.56'),
                'water_price': Decimal('3.8')
            }


    @classmethod
    def get_by_record(cls, record_id):
        """根据主记录ID查询所有关联的退宿人员费用明细"""
        try:
            records = cls.query.join(
                User, cls.user_id == User.id, isouter=True
            ).filter(
                cls.record_id == record_id
            ).all()

            result = []
            for record in records:
                user = User.query.get(record.user_id) if record.user_id else None
                user_name = "未知用户"
                if user:
                    if hasattr(user, 'name'):
                        user_name = user.name
                    elif hasattr(user, 'username'):
                        user_name = user.username
                    else:
                        user_name = f"用户ID:{record.user_id}"
                else:
                    user_name = f"用户ID:{record.user_id}"
                    
                result.append({
                    # 基础信息
                    "id": record.id,
                    "record_id": record.record_id,
                    "user_id": record.user_id,
                    "user_name": user_name,
                    "room_id": record.room_id,
                    
                    # 时间信息
                    "checkin_date": record.checkin_date.isoformat() if record.checkin_date else None,
                    "checkout_date": record.checkout_date.isoformat() if record.checkout_date else None,
                    "stay_days": record.stay_days,
                    "user_period_days": record.user_period_days,
                    "total_period_days": record.total_period_days,
                    "natural_days": record.natural_days,
                    
                    # 抄表数据（房间级）
                    "meter_electric_usage": Decimal(record.meter_electric_usage) if record.meter_electric_usage else 0,
                    "meter_water_usage": Decimal(record.meter_water_usage) if record.meter_water_usage else 0,
                    "meter_electric_fee": Decimal(record.meter_electric_fee) if record.meter_electric_fee else 0,
                    "meter_water_fee": Decimal(record.meter_water_fee) if record.meter_water_fee else 0,
                    "meter_total_fee": Decimal(record.meter_total_fee) if record.meter_total_fee else 0,
                    
                    # 抄表读数
                    "electric_reading": Decimal(record.electric_reading) if record.electric_reading else 0,
                    "electric_previous": Decimal(record.electric_previous) if record.electric_previous else 0,
                    "water_reading": Decimal(record.water_reading) if record.water_reading else 0,
                    "water_previous": Decimal(record.water_previous) if record.water_previous else 0,
                    
                    # 用户用量数据
                    "user_original_electric_usage": Decimal(record.user_original_electric_usage) if record.user_original_electric_usage else 0,
                    "user_original_water_usage": Decimal(record.user_original_water_usage) if record.user_original_water_usage else 0,
                    "user_reduction_electric": Decimal(record.user_reduction_electric) if record.user_reduction_electric else 0,
                    "user_reduction_water": Decimal(record.user_reduction_water) if record.user_reduction_water else 0,
                    "user_billing_electric_usage": Decimal(record.user_billing_electric_usage) if record.user_billing_electric_usage else 0,
                    "user_billing_water_usage": Decimal(record.user_billing_water_usage) if record.user_billing_water_usage else 0,
                    
                    # 价格信息
                    "electric_price": Decimal(record.electric_price) if record.electric_price else 0,
                    "water_price": Decimal(record.water_price) if record.water_price else 0,
                    
                    # 费用计算
                    "user_original_electric_fee": Decimal(record.user_original_electric_fee) if record.user_original_electric_fee else 0,
                    "user_original_water_fee": Decimal(record.user_original_water_fee) if record.user_original_water_fee else 0,
                    "user_original_total_fee": Decimal(record.user_original_total_fee) if record.user_original_total_fee else 0,
                    "user_billing_electric_fee": Decimal(record.user_billing_electric_fee) if record.user_billing_electric_fee else 0,
                    "user_billing_water_fee": Decimal(record.user_billing_water_fee) if record.user_billing_water_fee else 0,
                    "user_billing_total_fee": Decimal(record.user_billing_total_fee) if record.user_billing_total_fee else 0,
                    
                    # 减免费用
                    "room_total_reduction": Decimal(record.room_total_reduction) if record.room_total_reduction else 0,
                    "user_proportional_reduction": Decimal(record.user_proportional_reduction) if record.user_proportional_reduction else 0,
                    "user_independent_reduction": Decimal(record.user_independent_reduction) if record.user_independent_reduction else 0,
                    "payable_fee": Decimal(record.payable_fee) if record.payable_fee else 0,
                    
                    # 状态信息
                    "payment_status": record.payment_status,
                    "checkout_status": record.checkout_status,
                    "created_at": record.created_at.isoformat() if record.created_at else None,
                    "updated_at": record.updated_at.isoformat() if record.updated_at else None
                })
            return result
        except Exception as e:
            logging.error(f"查询退宿人员费用明细失败: {str(e)}", exc_info=True)
            return []

    @classmethod
    def get_by_user(cls, user_id):
        """根据用户ID查询退宿记录"""
        return cls.query.filter_by(user_id=user_id).all()

    @classmethod
    def get_by_room_and_period(cls, room_id, billing_period):
        """根据房间ID和账期查询退宿记录"""
        main_record = RoomUtilityRecord.query.filter(
            RoomUtilityRecord.room_id == room_id,
            RoomUtilityRecord.billing_period == billing_period
        ).first()
        return cls.query.filter_by(record_id=main_record.record_id).all() if main_record else []

    def mark_as_paid(self):
        """标记记录为已支付"""
        self.payment_status = 'paid'
        self.updated_at = datetime.now()
        return self
