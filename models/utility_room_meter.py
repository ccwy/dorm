from utils.db import db
from datetime import datetime
from sqlalchemy import CheckConstraint
from decimal import Decimal
import logging
from models.user import User  # 导入User模型

class UtilityMeterReading(db.Model):
    __tablename__ = 'utility_room_meter_readings'
    
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='RESTRICT'), 
                      nullable=False, comment='房间ID')
    
    # 关联主表的外键
    record_id = db.Column(
        db.Integer, 
        db.ForeignKey(
            'utility_room_bill_records.record_id', 
            ondelete='CASCADE'
        ),
        nullable=False, 
        comment='关联的账单主表ID'
    )

    # 水表相关字段
    water_current = db.Column(db.Numeric(10, 2), nullable=True, comment='当前水表读数（m³）')
    water_previous = db.Column(db.Numeric(10, 2), nullable=True, comment='上次水表读数（m³）')
    water_usage = db.Column(db.Numeric(10, 2), nullable=True, comment='本次用水量（m³）')
    water_meter_replaced = db.Column(db.Boolean, default=False, comment='是否为水表更换后的记录')
    
    # 电表相关字段
    electric_current = db.Column(db.Numeric(10, 2), nullable=True, comment='当前电表读数（度）')
    electric_previous = db.Column(db.Numeric(10, 2), nullable=True, comment='上次电表读数（度）')
    electric_usage = db.Column(db.Numeric(10, 2), nullable=True, comment='本次用电量（kWh）')
    electric_meter_replaced = db.Column(db.Boolean, default=False, comment='是否为电表更换后的记录')
    
    reading_type = db.Column(db.Integer, nullable=True, comment='1:正常抄表, 2:退宿抄表')
    user_id = db.Column(db.Integer,nullable=True, comment="关联的用户ID；仅退宿抄表时自动填写，其他类型可留空")

    reading_date = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='抄表日期时间')
    meter_reader_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), 
                              nullable=True, comment='抄表人ID')
    water_notes = db.Column(db.Text, nullable=True, comment='水表备注')
    electric_notes = db.Column(db.Text, nullable=True, comment='电表备注')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='记录创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='记录更新时间')
    
    # 关系关联
    room = db.relationship('Room', backref=db.backref('meter_readings', lazy='dynamic', 
                                                     cascade='all, delete-orphan'))
    meter_reader = db.relationship('User', backref=db.backref('meter_readings', lazy='dynamic'))

    # 约束 - 确保读数不为负数
    __table_args__ = (
        CheckConstraint('water_current >= 0', name='check_water_current_positive'),
        CheckConstraint('water_previous >= 0', name='check_water_previous_positive'),
        CheckConstraint('electric_current >= 0', name='check_electric_current_positive'),
        CheckConstraint('electric_previous >= 0', name='check_electric_previous_positive'),
    )
    
    def __repr__(self):
        return f"<UtilityMeterReading room_id={self.room_id} date={self.reading_date.strftime('%Y-%m-%d %H:%M:%S')}>"
    
    # 水表最新记录查询 - 修复核心：移除record_id过滤，获取房间所有历史记录
    @classmethod
    def get_latest_water_reading(cls, room_id):
            """获取指定房间最新的有效水表记录（跨账期查询）"""
            query = cls.query.filter_by(room_id=room_id)\
                             .filter(cls.water_current.isnot(None))\
                             .filter(cls.reading_type == 1)\
                             .order_by(cls.reading_date.desc(), cls.id.desc())
            
            # 处理水表更换记录
            latest_replace = query.filter(cls.water_meter_replaced == True).first()
            if latest_replace:
                query = query.filter(cls.reading_date >= latest_replace.reading_date)
            
            latest = query.first()
            if latest:
                latest_date = latest.reading_date.date() if isinstance(latest.reading_date, datetime) else latest.reading_date
                logging.debug(f"房间{room_id}最新水表记录：{latest_date}（跨账期查询）")
            else:
                logging.debug(f"房间{room_id}无历史水表记录，视为首次抄表")
            # 首次抄表时返回None，调用方应直接使用本次抄表值
            return latest
    
    # 电表最新记录查询 - 修复核心：移除record_id过滤
    @classmethod
    def get_latest_electric_reading(cls, room_id):
            """获取指定房间最新的有效电表记录（跨账期查询）"""
            query = cls.query.filter_by(room_id=room_id)\
                             .filter(cls.electric_current.isnot(None))\
                             .filter(cls.reading_type == 1)\
                             .order_by(cls.reading_date.desc(), cls.id.desc())
            
            # 处理电表更换记录
            latest_replace = query.filter(cls.electric_meter_replaced == True).first()
            if latest_replace:
                query = query.filter(cls.reading_date >= latest_replace.reading_date)
            
            latest = query.first()
            if latest:
                latest_date = latest.reading_date.date() if isinstance(latest.reading_date, datetime) else latest.reading_date
                logging.debug(f"房间{room_id}最新电表记录：{latest_date}（跨账期查询）")
            else:
                logging.debug(f"房间{room_id}无历史电表记录，视为首次抄表")
            # 首次抄表时返回None，调用方应直接使用本次抄表值
            return latest
    
    @staticmethod
    def calculate_usage_with_rollover(current, previous, max_value):
        """计算用量，支持表计归零场景"""
        if current is None or previous is None:
            return None

        current_dec = Decimal(str(current)) if not isinstance(current, Decimal) else current
        previous_dec = Decimal(str(previous)) if not isinstance(previous, Decimal) else previous
        max_dec = Decimal(str(max_value)) if not isinstance(max_value, Decimal) else max_value

        if current >= previous:
            return round(float(current - previous), 2)
        else:
            # 处理表计归零情况（如9999.99 -> 0.00）
            return round(float((max_value - previous) + current), 2)
    
    # 新增：获取房间最新的抄表日期（跨账期）
    @classmethod
    def get_latest_reading_date(cls, room_id):
            """获取指定房间最新的抄表日期（跨账期）"""
            query = cls.query.filter_by(room_id=room_id)\
                             .filter((cls.water_current.isnot(None)) | (cls.electric_current.isnot(None)))\
                             .order_by(cls.reading_date.desc())
            latest_record = query.first()
            
            if latest_record:
                latest_date = latest_record.reading_date.date() if isinstance(latest_record.reading_date, datetime) else latest_record.reading_date
                logging.debug(f"房间{room_id}最新抄表日期：{latest_date}（跨账期查询）")
            
            return latest_record.reading_date if latest_record else None


     # 新增抄表记录   
    @classmethod
    def create_reading(cls, room_id, water_current=None, electric_current=None,
                      water_meter_replaced=False, electric_meter_replaced=False,
                      reading_date=None, meter_reader_id=None,
                      water_notes=None, electric_notes=None,
                      record_id=None, reading_type=None, user_id=None):
        # 延迟导入
        from datetime import datetime, date
        from calendar import monthrange
        from models.utility_room_bill_record import RoomUtilityRecord
        from models.room import Room
        
        # 验证房间存在
        room = Room.query.get(room_id)
        if not room:
            raise ValueError(f"房间ID={room_id}不存在")
        
        # 确保抄表时间精确到秒
        reading_datetime = reading_date or datetime.now()
        
        # 获取各类最新时间
        latest_overall_date = cls.get_latest_reading_date(room_id)
        last_water = cls.get_latest_water_reading(room_id)  # 修复：不传递record_id
        last_water_date = last_water.reading_date if last_water else None
        last_electric = cls.get_latest_electric_reading(room_id)  # 修复：不传递record_id
        last_electric_date = last_electric.reading_date if last_electric else None
        # 只效验类型为1的正常抄表记录时间
        if reading_type == 1 :
         # 水表单独校验
            if water_current is not None:
                if last_water_date and reading_datetime < last_water_date:
                    raise ValueError(
                        f"新增失败：水表抄表时间({reading_datetime.strftime('%Y-%m-%d %H:%M:%S')}) "
                        f"早于上次水表记录时间({last_water_date.strftime('%Y-%m-%d %H:%M:%S')})"
                    )
                if not last_water_date and latest_overall_date and reading_datetime < latest_overall_date:
                    raise ValueError(
                        f"新增失败：水表抄表时间({reading_datetime.strftime('%Y-%m-%d %H:%M:%S')}) "
                        f"早于房间内其他表的最晚记录时间({latest_overall_date.strftime('%Y-%m-%d %H:%M:%S')})"
                    )

            # 电表单独校验
            if electric_current is not None:
                if last_electric_date and reading_datetime < last_electric_date:
                    raise ValueError(
                        f"新增失败：电表抄表时间({reading_datetime.strftime('%Y-%m-%d %H:%M:%S')}) "
                        f"早于上次电表记录时间({last_electric_date.strftime('%Y-%m-%d %H:%M:%S')})"
                    )
                if not last_electric_date and latest_overall_date and reading_datetime < latest_overall_date:
                    raise ValueError(
                        f"新增失败：电表抄表时间({reading_datetime.strftime('%Y-%m-%d %H:%M:%S')}) "
                        f"早于房间内其他表的最晚记录时间({latest_overall_date.strftime('%Y-%m-%d %H:%M:%S')})"
                    )

        # 自动匹配或验证主表ID
        if not record_id:
            # 自动匹配当前日期所属的主表
            bill_record = RoomUtilityRecord.query.filter(
                RoomUtilityRecord.room_id == room_id,
                RoomUtilityRecord.start_date <= reading_datetime,
                RoomUtilityRecord.end_date >= reading_datetime
            ).first()
            
            # 没有找到对应账期的主表，自动创建
            if not bill_record:
                reading_datetime = reading_date or datetime.now()            
                bill_record = RoomUtilityRecord.create_from_meter_reading(
                    room_id=room_id,
                    reading_date=reading_datetime
                )
            record_id = bill_record.record_id
        else:
            # 验证手动指定的主表
            bill_record = RoomUtilityRecord.get_by_id(record_id)
            if not bill_record or bill_record.room_id != room_id:
                raise ValueError(f"主表{record_id}无效或不属于房间{room_id}")
        
        # 获取房间信息
        room = Room.query.get_or_404(room_id)
        
        # 量程默认值
        electric_max = getattr(room, 'electric_meter_max', 9999.99)
        water_max = getattr(room, 'water_meter_max', 9999.99)
        
        # 水表验证与计算
        water_previous = None
        water_usage = None
        if water_current is not None:
            water_current = Decimal(str(water_current)) if not isinstance(water_current, Decimal) else water_current
            # 仅类型1需要校验读数合理性，类型2跳过
            if reading_type == 1:  # 新增类型判断
                if not water_meter_replaced and last_water:
                    if water_current < last_water.water_current:
                        if not (last_water.water_current > water_max * 0.9 and water_current < water_max * 0.1):
                            raise ValueError(f"水表当前读数({water_current})不能小于上次读数({last_water.water_current})，除非标记表具更换或表计归零")
            
            # 确定上次读数（核心：使用跨账期的历史记录）
            # 如果是首次抄表（last_water为None）或更换水表，以上次读数作为初始值
            if water_meter_replaced or not last_water:
                water_previous = water_current  # 更换水表或首次抄表时以上次读数作为初始值
                water_usage = 0
            else:
                water_previous = last_water.water_current
                water_usage = cls.calculate_usage_with_rollover(water_current, water_previous, water_max)
        
        # 电表验证与计算
        electric_previous = None
        electric_usage = None
        if electric_current is not None:
            electric_current = Decimal(str(electric_current)) if not isinstance(electric_current, Decimal) else electric_current
            # 仅类型1需要校验读数合理性，类型2跳过
            if reading_type == 1:  # 新增类型判断
                if not electric_meter_replaced and last_electric:
                    if electric_current < last_electric.electric_current:
                        if not (last_electric.electric_current > electric_max * 0.9 and electric_current < electric_max * 0.1):
                            raise ValueError(f"电表当前读数({electric_current})不能小于上次读数({last_electric.electric_current})，除非标记表具更换或表计归零")
            
            # 确定上次读数（核心：使用跨账期的历史记录）
            if electric_meter_replaced or not last_electric:
                electric_previous = electric_current  # 更换电表时以上次读数作为初始值
                electric_usage = 0
            else:
                electric_previous = last_electric.electric_current
                electric_usage = cls.calculate_usage_with_rollover(electric_current, electric_previous, electric_max)
        
        # 至少需要一项读数
        if water_current is None and electric_current is None:
            raise ValueError("至少需要提供一项表的读数")
        
        # 创建新记录
        new_reading = cls(
            room_id=room_id,
            record_id=record_id,
            water_current=water_current,
            water_previous=water_previous,  # 自动填充上次读数
            water_usage=water_usage,        # 自动计算用量
            water_meter_replaced=water_meter_replaced,
            electric_current=electric_current,
            electric_previous=electric_previous,  # 自动填充上次读数
            electric_usage=electric_usage,        # 自动计算用量
            electric_meter_replaced=electric_meter_replaced,
            reading_date=reading_datetime,
            meter_reader_id=meter_reader_id,
            water_notes=water_notes,
            reading_type=reading_type,
            user_id=user_id,
            electric_notes=electric_notes
        )
        
        db.session.add(new_reading)
        return new_reading

        
    # 更新抄表记录
    def update(self, **kwargs):
        # 延迟导入
        from models.room import Room
        
        updated_fields = []
        original_values = {}
            
        for key in kwargs:
            if hasattr(self, key):
                original_values[key] = getattr(self, key)
                updated_fields.append(key)

        room = Room.query.get_or_404(self.room_id)
        electric_max = getattr(room, 'electric_meter_max', 9999.99)
        water_max = getattr(room, 'water_meter_max', 9999.99)
        
        # 处理时间更新的特殊验证
        if 'reading_date' in kwargs:
            new_date = kwargs['reading_date']
            room_id = self.room_id
            
            # 检查水表记录（修复：不传递record_id）
            last_water = self.get_latest_water_reading(room_id)
            if last_water and last_water.id != self.id and new_date < last_water.reading_date:
                raise ValueError(f"更新后的抄表时间不能早于后续水表记录时间({last_water.reading_date.strftime('%Y-%m-%d %H:%M:%S')})\n请先检查和调整后续的记录")
            
            # 检查电表记录（修复：不传递record_id）
            last_electric = self.get_latest_electric_reading(room_id)
            if last_electric and last_electric.id != self.id and new_date < last_electric.reading_date:
                raise ValueError(f"更新后的抄表时间不能早于后续电表记录时间({last_electric.reading_date.strftime('%Y-%m-%d %H:%M:%S')})\n请先检查和调整后续的记录")
            
            # 将验证通过的日期赋值给对象属性
            self.reading_date = new_date
        
        if 'water_meter_replaced' in kwargs:
            self.water_meter_replaced = kwargs['water_meter_replaced']
        
        if 'electric_meter_replaced' in kwargs:
            self.electric_meter_replaced = kwargs['electric_meter_replaced']
        
        # 处理水表更新
        if 'water_current' in kwargs:
            new_water_current = kwargs['water_current']
            
            if not self.water_meter_replaced:
                # 修复：不传递record_id，获取所有历史记录
                last_water = self.get_latest_water_reading(self.room_id)
                if last_water and last_water.id == self.id:
                    last_water = UtilityMeterReading.query\
                        .filter_by(room_id=self.room_id)\
                        .filter(UtilityMeterReading.water_current.isnot(None))\
                        .filter(UtilityMeterReading.id != self.id)\
                        .order_by(UtilityMeterReading.reading_date.desc())\
                        .first()
                
                if last_water and new_water_current < last_water.water_current:
                    if not (last_water.water_current > water_max * 0.9 and new_water_current < water_max * 0.1):
                        raise ValueError(f"水表当前读数({new_water_current})不能小于上次读数({last_water.water_current})，除非标记表具更换或表计归零")
            
            self.water_current = new_water_current
            
            if self.water_meter_replaced:
                self.water_previous = self.water_current
                self.water_usage = 0
            else:
                # 修复：不传递record_id
                last_water = self.get_latest_water_reading(self.room_id)
                if last_water and last_water.id == self.id:
                    last_water = UtilityMeterReading.query\
                        .filter_by(room_id=self.room_id)\
                        .filter(UtilityMeterReading.water_current.isnot(None))\
                        .filter(UtilityMeterReading.id != self.id)\
                        .order_by(UtilityMeterReading.reading_date.desc())\
                        .first()
                
                self.water_previous = last_water.water_current if last_water else 0
                # 首次抄表判断：如果没有历史记录（last_water为None），用量始终为0
                if last_water is None:
                    self.water_usage = 0
                else:
                    self.water_usage = self.calculate_usage_with_rollover(
                        self.water_current, self.water_previous, water_max
                    )
        
        # 处理电表更新
        if 'electric_current' in kwargs:
            new_electric_current = kwargs['electric_current']
            
            if not self.electric_meter_replaced:
                # 修复：不传递record_id
                last_electric = self.get_latest_electric_reading(self.room_id)
                if last_electric and last_electric.id == self.id:
                    last_electric = UtilityMeterReading.query\
                        .filter_by(room_id=self.room_id)\
                        .filter(UtilityMeterReading.electric_current.isnot(None))\
                        .filter(UtilityMeterReading.id != self.id)\
                        .order_by(UtilityMeterReading.reading_date.desc())\
                        .first()
                
                if last_electric and new_electric_current < last_electric.electric_current:
                    if not (last_electric.electric_current > electric_max * 0.9 and new_electric_current < electric_max * 0.1):
                        raise ValueError(f"电表当前读数({new_electric_current})不能小于上次读数({last_electric.electric_current})，除非标记表具更换或表计归零")
            
            self.electric_current = new_electric_current
            
            if self.electric_meter_replaced:
                self.electric_previous = self.electric_current
                self.electric_usage = 0
            else:
                # 修复：不传递record_id
                last_electric = self.get_latest_electric_reading(self.room_id)
                if last_electric and last_electric.id == self.id:
                    last_electric = UtilityMeterReading.query\
                        .filter_by(room_id=self.room_id)\
                        .filter(UtilityMeterReading.electric_current.isnot(None))\
                        .filter(UtilityMeterReading.id != self.id)\
                        .order_by(UtilityMeterReading.reading_date.desc())\
                        .first()
                
                self.electric_previous = last_electric.electric_current if last_electric else 0
                # 首次抄表判断：如果没有历史记录（last_electric为None），用量始终为0
                if last_electric is None:
                    self.electric_usage = 0
                else:
                    self.electric_usage = self.calculate_usage_with_rollover(
                        self.electric_current, self.electric_previous, electric_max
                    )
        
        # 更新其他字段
        for key, value in kwargs.items():
            if key not in ['water_current', 'electric_current', 
                          'water_meter_replaced', 'electric_meter_replaced', 'reading_date'] and hasattr(self, key):
                setattr(self, key, value)
        
        self.updated_at = datetime.now()
        return self
    
    @classmethod
    def get_room_readings(cls, room_id, start_date=None, end_date=None, type_filter=None):
        query = cls.query.filter_by(room_id=room_id)
        
        if start_date:
            query = query.filter(cls.reading_date >= start_date)
        if end_date:
            query = query.filter(cls.reading_date <= end_date)
        if type_filter == 'water':
            query = query.filter(cls.water_current.isnot(None))
        elif type_filter == 'electric':
            query = query.filter(cls.electric_current.isnot(None))
            
        return query.order_by(cls.reading_date.desc(), cls.id.desc()).all()
    
    def to_dict(self):
        from models.user import User
        from models.utility_room_bill_record import RoomUtilityRecord
        # 直接过滤查询最新的正常抄表记录（排除当前记录）
        # 以自身抄表日期为基准，查询该日期之前的最新正常抄表记录（排除当前记录）
        latest_normal_water = UtilityMeterReading.query\
            .filter_by(room_id=self.room_id)\
            .filter(UtilityMeterReading.water_current.isnot(None))\
            .filter(UtilityMeterReading.reading_type == 1)\
            .filter(UtilityMeterReading.id != self.id)\
            .filter(UtilityMeterReading.reading_date <= self.reading_date)\
            .order_by(UtilityMeterReading.reading_date.desc(), UtilityMeterReading.id.desc())\
            .first()
        
        latest_normal_electric = UtilityMeterReading.query\
            .filter_by(room_id=self.room_id)\
            .filter(UtilityMeterReading.electric_current.isnot(None))\
            .filter(UtilityMeterReading.reading_type == 1)\
            .filter(UtilityMeterReading.id != self.id)\
            .filter(UtilityMeterReading.reading_date <= self.reading_date)\
            .order_by(UtilityMeterReading.reading_date.desc(), UtilityMeterReading.id.desc())\
            .first()

        # 获取主表账期信息
        billing_period = None
        if self.record_id:
            bill_record = RoomUtilityRecord.query.get(self.record_id)
            if bill_record:
                billing_period = bill_record.billing_period

        return {
            'id': self.id,
            'room_id': self.room_id,
            'record_id': self.record_id,
            'billing_period': billing_period,
            'building': self.room.building if self.room else None,
            'room_number': self.room.room_number if self.room else None,
            'water': {
                'current': float(self.water_current) if self.water_current else None,
                'previous': float(latest_normal_water.water_current) if latest_normal_water else None, # 上次读数
                'usage': float(self.water_usage) if self.water_usage else None,          # 自动计算的用量
                'replaced': self.water_meter_replaced,
                'notes': self.water_notes
            },
            'electric': {
                'current': float(self.electric_current) if self.electric_current else None,
                'previous': float(latest_normal_electric.electric_current) if latest_normal_electric else None,  # 上次读数
                'usage': float(self.electric_usage) if self.electric_usage else None,          # 自动计算的用量
                'replaced': self.electric_meter_replaced,
                'notes': self.electric_notes
            },
            'reading_type': self.reading_type,
            'user_id': self.user_id,
            'reading_date': self.reading_date.strftime('%Y-%m-%dT%H:%M:%S'),
            'meter_reader': self.meter_reader.name if self.meter_reader else None,
            'created_at': self.created_at.strftime('%Y-%m-%dT%H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%dT%H:%M:%S') if self.updated_at else None
        }

