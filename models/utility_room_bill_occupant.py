from utils.db import db  # 导入数据库实例
from datetime import datetime
from decimal import Decimal  # 用于精确计算
from models.dorm import Dorm  # 导入住宿记录模型
from models.utility_room_bill_record import RoomUtilityRecord  # 导入水电费主表模型
from models.utility_room_bill_checkout import CheckoutUtilityRecord  # 导入退宿子表
from models.fee_subsidy import FeeSubsidy  # 导入费用补贴模型
import logging  # 导入日志模块
from models.system_config import SystemConfig # 导入系统配置模型


class RoomUtilityOccupant(db.Model):
    """
    房间水电费分摊子表（按在住人员）
    核心业务逻辑：
    - 记录在住人员和换宿人员的水电费分摊明细
    - 退宿人员费用由CheckoutUtilityFee子表单独记录
    - 与主表为多对一关系，级联主表ID关联
    """
    __tablename__ = 'utility_room_bill_occupant'  # 数据库表名

    # 字段定义
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)  # 自增主键
    record_id = db.Column(
        db.Integer, 
        db.ForeignKey('utility_room_bill_records.record_id', ondelete='CASCADE'),
        nullable=False,
        comment='关联主表记录ID，主表删除时级联删除'
    )
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False, comment='用户ID，限制删除')
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='RESTRICT'), nullable=False, comment='当前分摊记录对应的房间ID，限制删除')
    is_transferred = db.Column(db.Boolean, default=False, comment='是否为换宿人员记录（True=换宿，False=正常在住）')
    stay_days = db.Column(db.Integer, default=0, comment='账单周期内的住宿天数')
    electric_fee = db.Column(db.Numeric(10, 2), default=0.00, comment='分摊的电费')
    water_fee = db.Column(db.Numeric(10, 2), default=0.00, comment='分摊的水费')
    total_fee = db.Column(db.Numeric(10, 2), default=0.00, comment='分摊的总费用')
    user_reduction_fee = db.Column(db.Numeric(10, 2), default=0.00, comment='减免费用')
    payable_fee = db.Column(db.Numeric(10, 2), default=0.00, comment='用户应付费用（总费用-减免费用）')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='记录创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='记录更新时间')
    remarks = db.Column(db.Text, nullable=True, comment='备注')

    # 关联配置
    main_record = db.relationship(
        'RoomUtilityRecord',
        backref=db.backref('occupant_records', cascade='all, delete-orphan'),
        lazy='joined'
    )
    user = db.relationship('User', backref='utility_room_bill_occupant', lazy=True)
    room = db.relationship('Room', backref='utility_room_bill_occupant', lazy=True)

    @classmethod
    def calculate_room_fee(cls, record_id, user_subsidy_balances=None):
        """计算房间内所有人员（含换宿）的费用分摊"""
        from models.user import User  # 新增：导入User模型用于用户状态验证
        # 确保字典全局唯一，避免每次调用创建新字典
        if user_subsidy_balances is None:
            user_subsidy_balances = {}
        else:
            if not isinstance(user_subsidy_balances, dict):
                raise TypeError("user_subsidy_balances必须是字典类型")

        main_record = RoomUtilityRecord.get_by_id(record_id)
        if not main_record:
            raise ValueError(f"主表记录ID={record_id}不存在")
            
        if main_record.actual_electric_fee is None or main_record.actual_water_fee is None:
            raise ValueError(f"主表记录ID={record_id}的实际应收费用数据不完整")
        
        # 清空旧记录
        cls.query.filter_by(record_id=record_id).delete()
        
        # 获取账单周期和房间信息
        start_date = main_record.start_date
        end_date = main_record.end_date
        room_id = main_record.room_id
        billing_period = main_record.billing_period

        #获取系统配置内是否启用按用户金额补贴减免
        enable_fee_user_fee = SystemConfig.get_config_value('FEE_USER_FEE', False)
        logging.info(f"系统配置-是否允许使用按房间金额减免参数: {enable_fee_user_fee}")

        # 获取包含换宿记录的完整有效人员信息（已排除退宿人员）
        valid_occupants = cls._get_valid_occupants(room_id, start_date, end_date)
        if not valid_occupants:
            logging.warning(f"房间{room_id}在{start_date}至{end_date}期间无有效住宿人员")
            return [], user_subsidy_balances
        
        # 计算总住宿天数（按房间分段统计）
        occupant_days = []
        total_days = 0
        
        for item in valid_occupants:
            # 只统计当前房间的住宿天数
            if item['room_id'] == room_id:
                # 新增：验证用户状态是否为在职
                user = User.query.get(item['user_id'])
                if user and user.is_status():
                    occupant_days.append({
                        'user_id': item['user_id'],
                        'days': item['days'],
                        'room_id': item['room_id'],
                        'is_transferred': item['is_transferred'],
                        'start': item['start_date'],
                        'end': item['end_date']
                    })
                    total_days += item['days']
                else:
                    logging.warning(f"用户ID={item['user_id']}非在职状态，不参与费用分摊")
        
        if total_days <= 0:
            logging.warning(f"房间{room_id}在{start_date}至{end_date}期间有效住宿总天数为0")
            return [], user_subsidy_balances
        
        # 费用分摊计算
        resident_records = []
        electric_fee = main_record.actual_electric_fee
        water_fee = main_record.actual_water_fee
        total_fee = main_record.actual_total_fee or (electric_fee + water_fee)

        # 按入住时间排序，确保补贴按时间顺序使用
        occupant_days.sort(key=lambda x: x['start'])

        for item in occupant_days:
            user_id = item.get('user_id')
            if user_id is None:
                logging.warning("发现无用户ID的住宿记录，跳过处理")
                continue
            
            ratio = Decimal(str(item['days'])) / Decimal(str(total_days))
            user_electric = round(electric_fee * ratio, 2)
            user_water = round(water_fee * ratio, 2)
            user_total = round(total_fee * ratio, 2)
            
            # 获取用户可用补贴
            if user_id not in user_subsidy_balances:
                total_subsidy = Decimal('0.00')
                user_subsidies = []
                if enable_fee_user_fee:
                    user_subsidies = FeeSubsidy.query.filter(
                        FeeSubsidy.fee_type == "住宿补贴",
                        FeeSubsidy.user_id == user_id,
                        FeeSubsidy.is_enabled == True,
                        FeeSubsidy.effective_date <= end_date
                    ).all()
                
                    for sub in user_subsidies:
                        if enable_fee_user_fee and sub.amount is not None:
                            total_subsidy += Decimal(str(sub.amount))
                
                user_subsidy_balances[user_id] = {
                    'remaining': total_subsidy,
                    'subsidies': user_subsidies
                }

            # 使用当前剩余补贴
            subsidy_info = user_subsidy_balances[user_id]
            available_subsidy = subsidy_info['remaining']
            user_reduction = min(available_subsidy, user_total)
            
            # 创建费用补贴使用记录
            if enable_fee_user_fee and user_reduction > 0:
                remaining_needed = user_reduction
                for subsidy in subsidy_info['subsidies']:
                    if remaining_needed <= 0:
                        break
                        
                    use_amount = min(Decimal(str(subsidy.amount)), remaining_needed)
                    if use_amount > 0:
                        from models.fee_subsidy_usage import FeeSubsidyUsage
                        FeeSubsidyUsage.create_usage_record(
                            subsidy=subsidy,
                            billing_period=billing_period,
                            usage_data={
                                'user_id': user_id,
                                'room_id': room_id,
                                'used_amount': use_amount,
                                'is_checkout': 3,
                                'remark': f"自动核算抵扣（账期{billing_period}）"
                            }
                        )
                        remaining_needed -= use_amount

            # 计算用户应付费用
            user_payable = round(user_total - user_reduction, 2)
            if user_payable < 0:
                user_payable = Decimal('0.00')

            # 更新字典中的剩余金额
            subsidy_info['remaining'] = available_subsidy - user_reduction

            # 设置备注信息
            remark_text = ""
            if user_payable <= Decimal('0.00'):
                remark_text = "经费用核算减免后本月应付费用为0，本月无需支付"
            elif user_reduction > 0:
                remark_text = f"已使用补贴{user_reduction}元，剩余补贴{subsidy_info['remaining']}元"

            record = cls(
                record_id=record_id,
                user_id=user_id,
                room_id=item['room_id'],
                is_transferred=item['is_transferred'],
                stay_days=item['days'],
                electric_fee=user_electric,
                water_fee=user_water,
                total_fee=user_total,
                user_reduction_fee=user_reduction,
                payable_fee=user_payable,
                remarks=remark_text
            )
            db.session.add(record)
            resident_records.append(record)
        
        db.session.flush()
        return resident_records, user_subsidy_balances
    
    @staticmethod
    def batch_calculate_bills(billing_period):
        """批量计算一个账期内所有房间的费用，确保补贴跨房间流转"""
        # 按时间顺序获取该账期内所有房间的主表记录
        main_records = RoomUtilityRecord.query.filter(
            RoomUtilityRecord.billing_period == billing_period
        ).order_by(RoomUtilityRecord.start_date).all()
    
        # 初始化全局唯一的补贴余额字典
        global_subsidy_balances = {}
    
        # 按顺序计算每个房间的费用，持续传递补贴余额字典
        for record in main_records:
            try:
                _, global_subsidy_balances = RoomUtilityOccupant.calculate_room_fee(
                    record_id=record.record_id,
                    user_subsidy_balances=global_subsidy_balances
                )
            except Exception as e:
                logging.error(f"计算房间{record.room_id}费用失败: {str(e)}")
                continue
    
        db.session.commit()
        return True

    @staticmethod
    def _get_valid_occupants(room_id, start_date, end_date):
        """获取房间在账单周期内的所有有效住宿记录（含换宿，排除退宿）"""
        # 先查询基础住宿记录
        base_occupants = Dorm.query.filter(
            Dorm.room_id == room_id,
            Dorm.check_in_date <= end_date,
            db.or_(
                Dorm.check_out_date.is_(None),  # 在住人员
                Dorm.check_out_date >= start_date  # 可能是换宿人员
            )
        ).all()
        
        all_occupancy = []
        processed_records = set()
        
        for dorm in base_occupants:
            if dorm.id in processed_records:
                continue
                
            try:
                chain = dorm.dorm_chain
                if not chain:
                    logging.warning(f"住宿记录{dorm.id}的住宿链为空")
                    continue
            except Exception as e:
                logging.error(f"获取住宿链失败: {str(e)}, dorm_id={dorm.id}")
                chain = [dorm]
                
            for record in chain:
                if record.id in processed_records:
                    continue
                processed_records.add(record.id)
                
                # 关键改进：判断是否为退宿人员（非换宿）
                # 退宿人员定义：有退房日期且没有后续住宿记录
                is_checkout = bool(record.check_out_date) and len(record.next_dorms) == 0
                
                # 如果是退宿人员，直接跳过，不纳入核算
                if is_checkout:
                    logging.debug(f"退宿人员记录{dorm.id}已排除，不纳入费用核算")
                    continue
                
                days = RoomUtilityOccupant._calculate_stay_days(
                    check_in=record.check_in_date,
                    check_out=record.check_out_date,
                    period_start=start_date,
                    period_end=end_date
                )
                
                if days > 0:
                    # 换宿标记：有退房行为且有后续住宿且在当前账期内
                    is_transferred = (
                        bool(record.check_out_date) and 
                        len(record.next_dorms) > 0 and 
                        start_date <= record.check_out_date <= end_date
                    )
                    
                    actual_start = max(record.check_in_date, start_date)
                    actual_end = min(record.check_out_date or end_date, end_date)
                    all_occupancy.append({
                        'user_id': record.user_id,
                        'room_id': record.room_id,
                        'days': days,
                        'is_transferred': is_transferred,
                        'dorm_id': record.id,
                        'start_date': actual_start,
                        'end_date': actual_end
                    })
        
        logging.debug(f"房间{room_id}有效住宿记录: {len(all_occupancy)}条（已排除退宿人员）")
        return all_occupancy
    
    @staticmethod
    def _calculate_stay_days(check_in, check_out, period_start, period_end):
        """精确计算单条住宿记录在账单周期内的天数"""
        if not check_in:
            logging.warning(f"住宿记录缺少入住日期，无法计算天数")
            return 0
            
        actual_check_in = max(check_in, period_start)
        actual_check_out = min(check_out, period_end) if check_out else period_end
        
        if actual_check_in > actual_check_out:
            return 0
            
        delta = actual_check_out - actual_check_in
        return delta.days + 1
    
    
    @classmethod
    def get_by_record(cls, record_id):
        """根据主表ID查询所有分摊记录"""
        return cls.query.filter_by(record_id=record_id).all()
    
    @classmethod
    def get_room_fee_details(cls, record_id):
        """获取房间完整费用明细"""
        main_record = RoomUtilityRecord.get_by_id(record_id)
        if not main_record:
            return None
            
        resident_records = cls.get_by_record(record_id)
        checkout_records = CheckoutUtilityRecord.get_by_record(record_id)
        
        return {
            'main_record': {
                'record_id': main_record.record_id,
                'room_id': main_record.room_id,
                'billing_period': main_record.billing_period,
                'start_date': main_record.start_date,
                'end_date': main_record.end_date,
                'actual_electric_fee': main_record.actual_electric_fee,
                'actual_water_fee': main_record.actual_water_fee,
                'actual_total_fee': main_record.actual_total_fee,
                'checked_out_total_fee': main_record.checked_out_total_fee
            },
            'resident_records': resident_records,  # 在住+换宿人员分摊明细
            'checkout_records': checkout_records   # 退宿人员费用明细
        }
