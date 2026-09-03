from datetime import datetime, timedelta
from utils.db import db
from models.user.user import User
from models.room.room import Room
from models.system_config.system_config import SystemConfig  # 导入系统配置模型
from flask_login import current_user  # 用于获取当前登录用户
from decimal import Decimal

class FeeSubsidy(db.Model):
    """费用补贴模型
    已修改说明：
    - 根据系统配置中的ALLOWANCE_TYPES验证费用类型
    - 按照不同费用类型进行参数验证
    """
    __tablename__ = 'fee_subsidy'
    
    # 自增整数主键
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    fee_type = db.Column(db.String(50), nullable=False, comment="费用类型（来自系统配置）")
    amount = db.Column(db.Numeric(10, 2), nullable=True, comment="补贴金额(元)，水电用量减免时为空")
    
    # 水电用量减免专用辅助字段
    electric_reduction = db.Column(db.Numeric(10, 2), nullable=True, comment="用电量减免量（度），仅水电用量减免时填写")
    water_reduction = db.Column(db.Numeric(10, 2), nullable=True, comment="用水量减免量（m³），仅水电用量减免时填写")
    
    # 时间类型字段
    effective_date = db.Column(db.DateTime, nullable=False, comment="生效时间(包含时分秒)")
    is_enabled = db.Column(db.Boolean, default=True, comment="是否启用")
    
    # 时间戳字段
    create_time = db.Column(db.DateTime, default=datetime.now, comment="记录创建时间")
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment="记录更新时间")
    
    # 操作人ID（普通字段）
    operator_id = db.Column(db.Integer, nullable=False, comment="操作人ID")
    change_reason = db.Column(db.String(200), comment="变更原因")
    billing_period = db.Column(db.String(7), nullable=False, comment="账期(格式：YYYY-MM)")
    
    # 账期开始日和结束日字段
    billing_start_date = db.Column(db.DateTime, nullable=False, comment="账期开始日（当月第一天）")
    billing_end_date = db.Column(db.DateTime, nullable=False, comment="账期结束日（当月最后一天）")
    
    # 用户ID和房间ID（外键）
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=True, comment="用户ID，限制删除")  # 注意：User表名是'users'
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='RESTRICT'), nullable=True, comment="房间ID，限制删除")  # 注意：Room表名是'rooms'
    
    # 添加与User和Room模型的关联关系
    user = db.relationship('User', backref='fee_subsidies', lazy=True)
    room = db.relationship('Room', backref='fee_subsidies', lazy=True)
    
    def to_dict(self):
        """转换为字典用于API返回"""
        result = {
            'id': self.id,
            'fee_type': self.fee_type,
            'effective_date': self.effective_date.strftime('%Y-%m-%d %H:%M:%S') if self.effective_date else None,
            'is_enabled': self.is_enabled,
            'create_time': self.create_time.strftime('%Y-%m-%d %H:%M:%S') if self.create_time else None,
            'update_time': self.update_time.strftime('%Y-%m-%d %H:%M:%S') if self.update_time else None,
            'operator_id': self.operator_id,
            'change_reason': self.change_reason,
            'billing_period': self.billing_period,
            'billing_start_date': self.billing_start_date.strftime('%Y-%m-%d %H:%M:%S') if self.billing_start_date else None,
            'billing_end_date': self.billing_end_date.strftime('%Y-%m-%d %H:%M:%S') if self.billing_end_date else None,
            'user_id': self.user_id,
            'room_id': self.room_id
        }
        
        # 区分费用类型返回对应字段
        # 调整逻辑：除"房间水电按用量减免"外，其他类型都返回amount
        if self.fee_type != "房间水电按用量减免":
        # 非房间水电按用量减免类型：返回金额字段
            result['amount'] = self.amount
        else:
        # 房间水电按用量减免类型：返回水电减免字段（不返回amount）
            result.update({
                'electric_reduction': self.electric_reduction,
                'water_reduction': self.water_reduction
            })
            
        return result
    
    @classmethod
    def add_fee(cls, new_subsidy_data):
        """添加新记录（新增住宿状态校验逻辑）"""
        # 1. 系统配置校验（保持不变）
        allowed_types = SystemConfig.get_config_value('ALLOWANCE_TYPES', [])
        if not allowed_types:
            raise ValueError("未配置有效的费用类型，请联系系统管理员")
        
        fee_type = new_subsidy_data.get('fee_type')
        if not fee_type or fee_type not in allowed_types:
            raise ValueError(f"不支持的费用类型：{fee_type}，允许的类型为：{','.join(allowed_types)}")
        
        
        user_id = new_subsidy_data.get('user_id')
        #验证用户状态
        if user_id:
            user = User.query.get(user_id)
            if not user:
                raise ValueError(f"用户ID {user_id} 不存在")
            if not user.is_status():
                raise ValueError(f"用户状态不是'在职'（当前状态：{user.status}），无法添加费用补贴")

        # 2. 新增：根据费用类型校验用户住宿状态（核心逻辑）
        if fee_type in ["外宿补贴", "住宿补贴"] and user_id:
            # 延迟导入Dorm模型，避免循环依赖
            from models.dorm.dorm import Dorm
            # 获取用户最新的住宿记录（通过Dorm模型的住宿链）
            latest_dorm = Dorm.get_user_latest_dorm(user_id)
            
            if fee_type == "外宿补贴":
                # 外宿补贴：用户当前不能处于活跃住宿状态
                if latest_dorm and latest_dorm.status == 'active':
                    # 若有活跃住宿记录，不允许保存外宿补贴
                    room = Room.query.get(latest_dorm.room_id)
                    room_info = f"{room.building}{room.room_number}" if room else f"房间ID:{latest_dorm.room_id}"
                    raise ValueError(f"用户当前在住（{room_info}），无法添加外宿补贴")
            
            elif fee_type == "住宿补贴":
                # 住宿补贴：用户当前不能处于退宿状态
                if latest_dorm and latest_dorm.status == 'checked_out':
                    # 若已退宿，不允许保存住宿补贴
                    raise ValueError(f"用户已退宿（退宿时间：{latest_dorm.check_out_date.strftime('%Y-%m-%d')}），无法添加住宿补贴")
                # 额外校验：若用户无任何住宿记录，也不允许添加住宿补贴
                if not latest_dorm:
                    raise ValueError("用户无住宿记录，无法添加住宿补贴")
        
        # 3. 原有字段校验逻辑（保持不变）
        if fee_type in ["外宿补贴", "住宿补贴"]:
            if 'amount' not in new_subsidy_data or new_subsidy_data['amount'] is None:
                raise ValueError(f"{fee_type}必须填写金额")
            if not user_id:
                raise ValueError(f"{fee_type}必须关联用户ID")
            new_subsidy_data.pop('electric_reduction', None)
            new_subsidy_data.pop('water_reduction', None)
            new_subsidy_data.pop('room_id', None)
            
        elif fee_type == "房间水电按用量减免":
            # 水电类补贴不涉及用户住宿状态校验，保持原有逻辑
            if ('electric_reduction' not in new_subsidy_data or new_subsidy_data['electric_reduction'] is None or
                'water_reduction' not in new_subsidy_data or new_subsidy_data['water_reduction'] is None):
                raise ValueError("水电用量减免必须填写电费减免量和水费减免量")
            if not new_subsidy_data.get('room_id'):
                raise ValueError("水电用量减免必须关联房间ID")
            new_subsidy_data['amount'] = None
            new_subsidy_data.pop('user_id', None)
                    
        elif fee_type == "房间水电按金额减免":
            if 'amount' not in new_subsidy_data or new_subsidy_data['amount'] is None:
                raise ValueError("房间水电按金额减免必须填写减免金额")
            if not new_subsidy_data.get('room_id'):
                raise ValueError("房间水电按金额减免必须关联房间ID")
            new_subsidy_data.pop('electric_reduction', None)
            new_subsidy_data.pop('water_reduction', None)
            new_subsidy_data.pop('user_id', None)
        
        # 4. 生效时间、账期等其他逻辑（保持不变）
        effective_date = new_subsidy_data.get('effective_date')
        if not effective_date:
            raise ValueError("生效时间不能为空，无法生成账期")
        
        if isinstance(effective_date, str):
            try:
                effective_date = datetime.strptime(effective_date, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                raise ValueError(f"生效时间格式错误，必须为'YYYY-MM-DD HH:MM:SS'，实际收到：{effective_date}")
        
        if not isinstance(effective_date, datetime):
            raise TypeError(f"生效时间必须是datetime对象，实际类型：{type(effective_date)}")
        new_subsidy_data['effective_date'] = effective_date
        
        billing_period = effective_date.strftime('%Y-%m')
        new_subsidy_data['billing_period'] = billing_period
        billing_start_date = datetime(effective_date.year, effective_date.month, 1)
        new_subsidy_data['billing_start_date'] = billing_start_date
        if effective_date.month == 12:
            next_month = 1
            next_year = effective_date.year + 1
        else:
            next_month = effective_date.month + 1
            next_year = effective_date.year
        billing_end_date = datetime(next_year, next_month, 1) - timedelta(seconds=1)
        new_subsidy_data['billing_end_date'] = billing_end_date
        
        if not hasattr(current_user, 'id'):
            raise ValueError("未获取到当前登录用户信息，请重新登录")
        new_subsidy_data['operator_id'] = current_user.id
        
        # 5. 旧记录禁用逻辑（保持不变）
        user_id = new_subsidy_data.get('user_id')
        room_id = new_subsidy_data.get('room_id')
        query = cls.query.filter(cls.is_enabled == True)
        if room_id and fee_type in ["房间水电按用量减免", "房间水电按金额减免"]:
            query = query.filter(cls.room_id == room_id)
        elif user_id:
            query = query.filter(
                cls.fee_type == fee_type,
                cls.user_id == user_id
            )
        else:
            query = query.filter(cls.fee_type == fee_type)
        
        old_subsidies = query.all()
        for old in old_subsidies:
            old.is_enabled = False
            old.change_reason = f"被新记录替代: {new_subsidy_data.get('change_reason', '')}"
            db.session.add(old)
            
            if old.fee_type == "外宿补贴" and old.user_id:
                user = User.query.get(old.user_id)
                if user:
                    user.lodging_allowance = Decimal('0.00')
                    db.session.add(user)
            elif old.fee_type == "住宿补贴" and old.user_id:
                user = User.query.get(old.user_id)
                if user:
                    user.reduction_fee = Decimal('0.00')
                    db.session.add(user)
            elif old.fee_type == "房间水电按用量减免" and old.room_id:
                room = Room.query.get(old.room_id)
                if room:
                    room.electric_reduction = Decimal('0.00')
                    room.water_reduction = Decimal('0.00')
                    db.session.add(room)
            elif old.fee_type == "房间水电按金额减免" and old.room_id:
                room = Room.query.get(old.room_id)
                if room:
                    room.reduction_fee = Decimal('0.00')
                    db.session.add(room)
        
        # 6. 创建新记录并更新关联模型（保持不变）
        new_subsidy = cls(** new_subsidy_data)
        new_subsidy.is_enabled = True
        db.session.add(new_subsidy)
        
        if fee_type == "外宿补贴" and user_id:
            user = User.query.get(user_id)
            if not user:
                raise ValueError(f"用户ID {user_id} 不存在，无法更新外宿补贴")
            user.lodging_allowance = Decimal(str(new_subsidy_data['amount']))
            db.session.add(user)
        elif fee_type == "住宿补贴" and user_id:
            user = User.query.get(user_id)
            if not user:
                raise ValueError(f"用户ID {user_id} 不存在，无法更新住宿补贴")
            user.reduction_fee = Decimal(str(new_subsidy_data['amount']))
            db.session.add(user)
        elif fee_type == "房间水电按用量减免" and room_id:
            room = Room.query.get(room_id)
            if not room:
                raise ValueError(f"房间ID {room_id} 不存在，无法更新水电用量减免")
            room.electric_reduction = Decimal(str(new_subsidy_data['electric_reduction']))
            room.water_reduction = Decimal(str(new_subsidy_data['water_reduction']))
            db.session.add(room)
        elif fee_type == "房间水电按金额减免" and room_id:
            room = Room.query.get(room_id)
            if not room:
                raise ValueError(f"房间ID {room_id} 不存在，无法更新房间水电按金额减免")
            room.reduction_fee = Decimal(str(new_subsidy_data['amount']))
            db.session.add(room)
        
        return new_subsidy

    @classmethod
    def disabled_subsidy(cls, subsidy_id, operator_id, reason="手动禁用"):
        """逻辑禁用记录（非删除），同时重置User和Room模型的对应字段"""
        subsidy = cls.query.get(subsidy_id)
        if not subsidy:
            return False
        
        # 根据费用类型重置关联模型的字段
        if subsidy.fee_type == "外宿补贴" and subsidy.user_id:
            user = User.query.get(subsidy.user_id)
            if user:
                user.lodging_allowance = Decimal('0.00')
                db.session.add(user)
        
        elif subsidy.fee_type == "住宿补贴" and subsidy.user_id:
            user = User.query.get(subsidy.user_id)
            if user:
                user.reduction_fee = Decimal('0.00')
                db.session.add(user)
        
        elif subsidy.fee_type == "房间水电按用量减免" and subsidy.room_id:
            room = Room.query.get(subsidy.room_id)
            if room:
                room.electric_reduction = Decimal('0.00')
                room.water_reduction = Decimal('0.00')
                db.session.add(room)
        
        elif subsidy.fee_type == "房间水电按金额减免" and subsidy.room_id:
            room = Room.query.get(subsidy.room_id)
            if room:
                room.reduction_fee = Decimal('0.00')
                db.session.add(room)
        
        subsidy.is_enabled = False
        subsidy.change_reason = f"已禁用：{reason}"
        subsidy.operator_id = operator_id
        
        db.session.add(subsidy)
        
        return True
    