from flask_login import current_user
import logging
from utils.db import db
from datetime import datetime
import enum
from werkzeug.utils import secure_filename
from models.room_bed import Bed, BedStatus  # 导入床位模型和状态枚举
from models.room_facility import RoomFacility  # 导入房间设施模型
from models.system_config import SystemConfig  # 导入系统配置模型
from decimal import Decimal

class RoomStatus(str, enum.Enum):
    """房间状态枚举"""
    AVAILABLE = "available"  # 可用
    FULL = "full"  # 已满
    MAINTENANCE = "maintenance"  # 维护中
    CLOSED = "closed"  # 已关闭

class Room(db.Model):
    """房间模型（支持完整的CRUD操作）"""
    __tablename__ = 'rooms'
    
    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    building = db.Column(db.String(50), nullable=False, comment='楼栋（如：A栋、1号楼）')
    room_number = db.Column(db.String(10), nullable=False, comment='房间号（如：01、102）')
    address = db.Column(db.String(500), nullable=True, comment='房间地址')
    room_type = db.Column(db.String(20),nullable=False,comment='房间类型，从系统配置中读取')
    room_level = db.Column(db.String(50), nullable=True, comment='房间级别，从系统配置中读取')
    capacity = db.Column(db.Integer, default=4, nullable=False, comment='房间最大容量（正整数）')
    current_occupancy = db.Column(db.Integer, default=0, nullable=False, comment='当前入住人数')
    average_age = db.Column(db.Integer, nullable=True, comment='房间住户平均年龄')
    gender_restriction = db.Column(db.String(20), nullable=False, default="无限制", comment="性别限制：男、女、无限制")
    status = db.Column(db.String(20), default=RoomStatus.AVAILABLE.value, nullable=False, comment=f'房间状态：{[s.value for s in RoomStatus]}')

    # 租金字段
    external_rent = db.Column(db.Numeric(10, 2), default=Decimal('0.00'), nullable=True, comment='对外租金（元/月）')
    cost_rent = db.Column(db.Numeric(10, 2), default=Decimal('0.00'), nullable=True, comment='成本租金（元/月，内部核算用）')
    remark = db.Column(db.Text, nullable=True, comment='房间备注信息')

    #费用补贴
    electric_reduction = db.Column(db.Numeric(10, 2), default=Decimal('0.00'), nullable=True, comment='用电量减免kWh数（kWh/月）')
    water_reduction = db.Column(db.Numeric(10, 2), default=Decimal('0.00'), nullable=True, comment='用水量减免度数（m³/月）')
    reduction_fee = db.Column(db.Numeric(10, 2), default=Decimal('0.00'), nullable=True, comment='房间水电费减免金额（元/月）')
    
    # 表计量程配置（带默认值）
    electric_meter_max = db.Column(db.Numeric(10, 2), default=Decimal('9999.99'), nullable=True, comment='电表最大量程（默认9999.99kWh）')
    water_meter_max = db.Column(db.Numeric(10, 2), default=Decimal('9999.99'), nullable=True, comment='水表最大量程（默认9999.99m³）')
    
    # 操作用户ID字段（不与User表关联）
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作用户ID（办理人）')

    # 时间记录字段
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间（添加房间时间）')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间（修改房间时间）')
    
    # 关系定义：与床位的关联（一个房间包含多个床位）
    room_beds = db.relationship('Bed', backref=db.backref('room', lazy=True), lazy=True, cascade="all, delete-orphan")
    
    # 关系定义：与设施物品的关联（一个房间包含多个设施物品）
    room_facilities = db.relationship('RoomFacility', backref=db.backref('room', lazy=True), lazy=True, cascade="all, delete-orphan")
    
    # 约束定义
    __table_args__ = (
        db.UniqueConstraint('building', 'room_number', name='unique_room_identifier'),
        db.CheckConstraint('capacity > 0', name='check_capacity_positive'),
        db.CheckConstraint('current_occupancy >= 0 AND current_occupancy <= capacity', name='check_occupancy_valid'),
        db.CheckConstraint(
            f"status IN ('{RoomStatus.AVAILABLE.value}', '{RoomStatus.FULL.value}', "
            f"'{RoomStatus.MAINTENANCE.value}', '{RoomStatus.CLOSED.value}')",
            name='check_status_valid'
        ),
        db.CheckConstraint(
            "gender_restriction IN ('男', '女', '无限制')",
            name='check_gender_restriction_valid'
        ),

        db.Index('idx_room_building', 'building'),
        db.Index('idx_room_status', 'status'),
        db.Index('idx_room_gender', 'gender_restriction'),
        db.Index('idx_room_type', 'room_type'),
        db.Index('idx_room_bs', 'building', 'status')
    )
    
    def __repr__(self):
        return f"<Room {self.building}-{self.room_number}>"
    
    @property
    def room_full_identifier(self):
        """返回完整房间编号（如：A栋01）"""
        return f"{self.building}{self.room_number}"
    
    def is_available(self):
        """判断房间是否可用"""
        return self.status == RoomStatus.AVAILABLE.value and self.current_occupancy < self.capacity
    
    @property
    def get_type_display(self):
        """返回房间类型的显示文本（直接使用类型值，因为从配置读取的已经是中文）"""
        return self.room_type
        
    def calculate_average_age(self):
        """计算房间住户的平均年龄"""
        from models.dorm import Dorm  # 避免循环导入
        from models.user import User
        
        # 查询当前房间内所有活跃的住宿记录
        active_dorms = Dorm.query.filter(
            Dorm.room_id == self.id,
            Dorm.status == 'active'
        ).all()
        
        if not active_dorms:
            self.average_age = None
            return
        
        # 批量获取用户ID
        user_ids = [dorm.user_id for dorm in active_dorms]
        
        try:
            # 从User表批量查询这些用户
            users = User.query.filter(User.id.in_(user_ids)).all()
            user_dict = {user.id: user for user in users}
            
            total_age = 0
            valid_count = 0
            
            # 计算所有住户的平均年龄
            for user_id in user_ids:
                user = user_dict.get(user_id)
                if user:
                    age = user.get_age()
                    if age is not None:
                        total_age += age
                        valid_count += 1
        except Exception as e:
            logging.error(f"计算房间平均年龄时出错: {str(e)}")
            self.average_age = None
            return
        
        # 更新平均年龄
        if valid_count > 0:
            self.average_age = round(total_age / valid_count)
        else:
            self.average_age = None
        
        db.session.add(self)
        return True

    @classmethod
    def get_valid_room_levels(cls):
        """从系统配置获取有效的房间级别"""
        return SystemConfig.get_config_value('ROOM_LEVELS', ['普通房间', '标准房间', '高级房间', '豪华房间', 'VIP房间'])
    
    # 房间状态显示文本方法
    @property
    def get_status_display(self):
        """返回房间状态的显示文本"""
        status_mapping = {
            RoomStatus.AVAILABLE.value: "可用",
            RoomStatus.FULL.value: "已满",
            RoomStatus.MAINTENANCE.value: "维护中",
            RoomStatus.CLOSED.value: "已关闭"
        }
        return status_mapping.get(self.status, self.status)  # 容错处理，默认返回原始值
    
    @property
    def occupancy_rate(self):
        """计算入住率，返回百分比字符串或'-'"""
        if self.capacity == 0:
            return "-"
        try:
            rate = (self.current_occupancy / self.capacity) * 100
            return f"{rate:.1f}%"
        except (ZeroDivisionError, TypeError):
            return "-"
            
    # ------------------------------
    # 核心CRUD操作方法（增加设施处理）
    # ------------------------------
    @classmethod
    def create(cls, data):
        try:
            # 验证必填字段
            required_fields = ['building', 'room_number']
            for field in required_fields:
                if field not in data or not str(data[field]).strip():
                    return None, f"缺少必填字段: {field}"
            
            # 检查房间是否已存在
            existing = cls.query.filter_by(
                building=data['building'].strip(),
                room_number=data['room_number'].strip()
            ).first()
            if existing:
                return None, f"房间 {data['building']}-{data['room_number']} 已存在"
            
            # 处理容量
            capacity = int(data.get('capacity', 4))
            if capacity <= 0:
                return None, "容量必须为正整数"
            
            # 获取有效的房间类型列表
            valid_room_types = SystemConfig.get_config_value('ROOM_TYPES', [])
            if not valid_room_types:
                valid_room_types = ["单人间", "双人间", "四人间", "六人间", "其他类型"]
                
            # 处理房间类型
            room_type = data.get('room_type', valid_room_types[0])
            if room_type not in valid_room_types:
                return None, f"无效的房间类型: {room_type}，有效类型: {', '.join(valid_room_types)}"

            # 处理房间级别
            valid_room_levels = cls.get_valid_room_levels()
            room_level = data.get('room_level')
            if room_level is not None and room_level not in valid_room_levels:
                return None, f"无效的房间级别: {room_level}，有效级别: {', '.join(valid_room_levels)}"
                
                
            gender_restriction = data.get('gender_restriction', "无限制")
            valid_gender_restrictions = cls.get_valid_gender_restrictions()
            if gender_restriction not in valid_gender_restrictions:
                return None, f"无效的性别限制: {gender_restriction}，有效限制: {', '.join(valid_gender_restrictions)}"
                
            status = data.get('status', RoomStatus.AVAILABLE.value)
            if status not in [s.value for s in RoomStatus]:
                return None, f"无效的房间状态: {status}"
            
            # 处理租金
            try:
                external_rent = Decimal(str(data.get('external_rent', '0')))
                cost_rent = Decimal(str(data.get('cost_rent', '0')))
                if external_rent < 0 or cost_rent < 0:
                    return None, "租金不能为负数"
            except (ValueError, TypeError):
                return None, "租金必须为有效的数字"
            
            
            # 创建房间实例
            new_room = cls(
                building=data['building'].strip(),
                room_number=data['room_number'].strip(),
                address=str(data.get('address', '')).strip(),
                room_type=room_type,
                room_level=room_level,
                capacity=capacity,
                gender_restriction=gender_restriction,
                status=status,
                current_occupancy=0,
                external_rent=external_rent,
                cost_rent=cost_rent,
                remark=data.get('remark', '').strip(),
                electric_meter_max=Decimal(str(data.get('electric_meter_max', '9999.99'))),
                water_meter_max=Decimal(str(data.get('water_meter_max', '9999.99'))),
                operator_user_id=current_user.id if current_user.is_authenticated else None,
                created_at=data.get('created_at', datetime.now()),  # 优先使用传入的创建时间，否则使用当前时间
                updated_at=data.get('created_at', datetime.now())
            )
            
            db.session.add(new_room)
            db.session.flush()  # 刷新以获取ID
            
            # 创建对应床位
            cls._create_beds_for_room(new_room, capacity)

            # 通知费用主表创建记录，并传递房间创建时间
            from models.utility_room_bill_record import RoomUtilityRecord
            RoomUtilityRecord.create_for_new_room(new_room.id, new_room.created_at)
            
            db.session.commit()
            logging.info(f"创建房间并通知费用主表: {new_room.room_full_identifier}")
            return new_room, None
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"创建房间失败: {str(e)}"
            logging.error(error_msg)
            return None, error_msg

    def update(self, data):
        try:
            # 处理楼栋和房间号（允许修改，但需检查唯一性）
            if 'building' in data or 'room_number' in data:
                new_building = data.get('building', self.building).strip()
                new_room_number = data.get('room_number', self.room_number).strip()
                
                # 检查是否与其他房间冲突
                if new_building != self.building or new_room_number != self.room_number:
                    existing = Room.query.filter_by(
                        building=new_building,
                        room_number=new_room_number
                    ).first()
                    if existing and existing.id != self.id:
                        return None, f"房间 {new_building}-{new_room_number} 已存在"
                
                self.building = new_building
                self.room_number = new_room_number
            
            # 处理容量变更（需调整床位）
            if 'capacity' in data:
                new_capacity = int(data['capacity'])
                if new_capacity <= 0:
                    return None, "容量必须为正整数"
                
                # 调整床位
                Room._adjust_beds_for_room(self, new_capacity)
                self.capacity = new_capacity
                
                # 检查入住人数是否超过新容量
                if self.current_occupancy > new_capacity:
                    self.current_occupancy = new_capacity
                    self.status = RoomStatus.FULL.value
            
           # 处理房间地址更新
            if 'address' in data:
                self.address = data['address'].strip()
            
            # 处理房间类型更新
            if 'room_type' in data:
                # 获取有效的房间类型列表
                valid_room_types = SystemConfig.get_config_value('ROOM_TYPES', [])
                if not valid_room_types:
                    valid_room_types = ["单人间", "双人间", "四人间", "六人间", "其他类型"]
                
                if data['room_type'] in valid_room_types:
                    self.room_type = data['room_type']
                else:
                    return None, f"无效的房间类型: {data['room_type']}，有效类型: {', '.join(valid_room_types)}"

            # 处理房间级别更新
            if 'room_level' in data:
                # 获取有效的房间级别列表
                valid_room_levels = self.get_valid_room_levels()
                if data['room_level'] in valid_room_levels or data['room_level'] is None:
                    self.room_level = data['room_level']
                else:
                    return None, f"无效的房间级别: {data['room_level']}，有效级别: {', '.join(valid_room_levels)}"
                
            if 'gender_restriction' in data:
                valid_gender_restrictions = self.get_valid_gender_restrictions()
                if data['gender_restriction'] in valid_gender_restrictions:
                    self.gender_restriction = data['gender_restriction']
                
            if 'status' in data:
                new_status = data['status']
                if new_status not in [s.value for s in RoomStatus]:
                    return None, f"无效的房间状态: {new_status}"
                
                # 检查关闭房间时是否有人入住
                if new_status == RoomStatus.CLOSED.value and self.current_occupancy > 0:
                    return None, "房间有人入住，无法设置为关闭状态"
                
                self.status = new_status
            
            # 处理租金更新
            if 'external_rent' in data:
                try:
                    external_rent = Decimal(str(data['external_rent']))
                    if external_rent >= 0:
                        self.external_rent = external_rent
                    else:
                        return None, "租金不能为负数"
                except (ValueError, TypeError):
                    return None, "租金必须为有效的数字"
                    
            if 'cost_rent' in data:
                try:
                    cost_rent = Decimal(str(data['cost_rent']))
                    if cost_rent >= 0:
                        self.cost_rent = cost_rent
                    else:
                        return None, "租金不能为负数"
                except (ValueError, TypeError):
                    return None, "租金必须为有效的数字"
            
            # 处理其他字段
            if 'remark' in data:
                self.remark = data['remark'].strip()
                
            if 'electric_meter_max' in data:
                try:
                    self.electric_meter_max = Decimal(str(data['electric_meter_max']))
                except (ValueError, TypeError):
                    return None, "电表最大量程必须为有效的数字"
                
            if 'water_meter_max' in data:
                try:
                    self.water_meter_max = Decimal(str(data['water_meter_max']))
                except (ValueError, TypeError):
                    return None, "水表最大量程必须为有效的数字"
            
            # 自动更新状态
            if self.status == RoomStatus.AVAILABLE.value and self.current_occupancy >= self.capacity:
                self.status = RoomStatus.FULL.value
            
            db.session.commit()
            # 设置操作用户ID
            if current_user.is_authenticated:
                self.operator_user_id = current_user.id
                
            logging.info(f"更新房间成功: {self.room_full_identifier}")
            return self, None
            
        except Exception as e:
            db.session.rollback()
            error_msg = f"更新房间失败: {str(e)}"
            logging.error(error_msg)
            return None, error_msg

    def delete(self):
        """
        房间删除方法
        
        权限控制逻辑：
        - 超级管理员：拥有全部权限，可删除任何房间及关联记录
        - 普通管理员：仅能删除无住户且无任何关联记录的房间
        - 非管理员：无删除权限
        
        删除流程：
        1. 权限校验
        2. 关联记录检查（仅普通管理员）
        3. 按顺序删除关联记录（仅超级管理员）
        4. 删除房间本身
        5. 返回操作结果
        
        返回值：
            dict: 包含'success'（布尔值）和'message'（操作信息）的字典
        """
        try:
            # 局部导入关联模型
            from models.utility_room_bill_record import RoomUtilityRecord
            from models.dorm import Dorm
            from models.fee_subsidy import FeeSubsidy
            from models.utility_room_bill_checkout import CheckoutUtilityRecord
            from models.utility_room_meter import UtilityMeterReading
            from models.room_bed import Bed  # 导入床位模型
            
            # 初始化删除统计
            delete_stats = {
                'beds': 0,                # 床位数（通过级联删除）
                'meter_records': 0,       # 抄表记录数
                'subsidy_records': 0,     # 费用补贴记录数
                'checkout_records': 0,    # 退宿费用记录数
                'utility_records': 0,     # 费用主记录数
                'occupant_records': 0,     # 在住用户费用记录数
                'dorm_records': 0,        # 住宿记录数
                'facility_records': 0,     # 房间设施记录数
                'photos_deleted': False,   # 房间照片是否已删除
                'meter_photos_deleted': False  # 抄表记录照片是否已删除
            }

            # 1. 权限检查（保持不变）
            if not current_user.is_authenticated:
                message = "未授权访问，需要登录"
                logging.warning(message)
                return {'success': False, 'message': message}
                
            is_super_admin = (current_user.user_role and current_user.user_role.code == 'super_admin') if hasattr(current_user, 'user_role') else False
            
            if not is_super_admin:
                if not current_user.has_permission('room.delete'):
                    message = "权限不足，只有拥有删除权限的用户可以删除房间"
                    return {'success': False, 'message': message}
                
                if self.current_occupancy > 0:
                    message = f"房间 {self.building}-{self.room_number} 尚有住户，无法删除"
                    return {'success': False, 'message': message}
                
                related_records = []
                if UtilityMeterReading.query.filter_by(room_id=self.id).first():
                    related_records.append("抄表记录")
                if FeeSubsidy.query.filter_by(room_id=self.id).first():
                    related_records.append("费用补贴记录")
                if CheckoutUtilityRecord.query.filter_by(room_id=self.id).first():
                    related_records.append("退宿费用记录")
                if RoomUtilityRecord.query.filter_by(room_id=self.id).first():
                    related_records.append("费用主记录")
                if Dorm.query.filter_by(room_id=self.id).first():
                    related_records.append("住宿记录")
                
                if related_records:
                    message = f"房间 {self.building}-{self.room_number} 存在关联记录：{', '.join(related_records)}，无法删除"
                    return {'success': False, 'message': message}
            
            # 2. 超级管理员执行关联记录删除（按依赖顺序）
            # 2.1 删除房间设施记录并统计
            facility_records = RoomFacility.query.filter_by(room_id=self.id).all()
            delete_stats['facility_records'] = len(facility_records)
            for facility in facility_records:
                db.session.delete(facility)

            # 2.2 统计床位数量（不单独删除，依赖级联）
            bed_records = Bed.query.filter_by(room_id=self.id).all()
            delete_stats['beds'] = len(bed_records)  # 仅统计，不手动删除
            
            # 2.3 先获取抄表记录信息用于删除照片
            meter_readings = UtilityMeterReading.query.filter_by(room_id=self.id).all()
            delete_stats['meter_records'] = len(meter_readings)
            
            # 2.4 同步删除房间抄表记录照片（确保在费用主记录和抄表记录删除前能获取账期）
            try:
                from utils.room_meter_photo import room_meter_manager
                
                # 使用工具类的方法删除房间所有抄表记录照片
                logging.info(f"尝试删除房间 {self.id} 的所有抄表记录照片")
                result = room_meter_manager.delete_media_by_room(self.id)
                
                if result:
                    delete_stats['meter_photos_deleted'] = True
                    logging.info(f"成功删除房间 {self.id} 的所有抄表记录照片")
                else:
                    logging.warning(f"删除房间 {self.id} 的部分或全部抄表记录照片失败")
            except Exception as e:
                # 记录错误但不中断删除流程
                logging.error(f"删除房间抄表记录照片失败: {str(e)}")
            
            # 2.5 手动删除抄表记录（确保在费用主记录之前删除）
            # 这是为了避免外键约束问题，确保先删除子表再删除主表
            for record in meter_readings:
                db.session.delete(record)
            logging.debug(f"手动删除了{len(meter_readings)}条抄表记录")
            
            # 2.6 删除费用补贴记录并统计
            subsidy_records = FeeSubsidy.query.filter_by(room_id=self.id).all()
            delete_stats['subsidy_records'] = len(subsidy_records)
            for subsidy in subsidy_records:
                db.session.delete(subsidy)
            
            # 2.7 删除退宿费用记录并统计
            checkout_records = CheckoutUtilityRecord.query.filter_by(room_id=self.id).all()
            delete_stats['checkout_records'] = len(checkout_records)
            for record in checkout_records:
                db.session.delete(record)
            
            # 2.8 处理费用主记录并统计（在抄表记录删除之后）
            utility_result = RoomUtilityRecord.handle_room_deletion(self.id)
            if utility_result['success']:
                delete_stats['utility_records'] = utility_result['deleted_count']
                # 新增：统计在住人员子表删除数量
                delete_stats['occupant_records'] = utility_result['occupant_records_deleted']
            else:
                raise Exception(f"处理费用记录失败: {utility_result['message']}")

            # 2.9 处理住宿记录：先更新用户信息，再删除记录
            dorm_records = Dorm.query.filter_by(room_id=self.id).all()
            delete_stats['dorm_records'] = len(dorm_records)
            
            # 删除住宿记录（不再关联User模型）
            for dorm in dorm_records:
                db.session.delete(dorm)
            
            # 3. 同步删除房间照片
            try:
                from utils.room_photo import room_photo_manager
                
                # 使用RoomPhotoManager提供的方法删除整个房间的媒体目录
                success = room_photo_manager.delete_room_directory(self.id)
                if success:
                    delete_stats['photos_deleted'] = True
                    logging.info(f"成功删除房间 {self.id} 的媒体目录")
            except Exception as e:
                # 记录错误但不中断删除流程
                logging.error(f"删除房间照片失败: {str(e)}")
            
            # 6. 执行房间删除（触发床位级联删除）
            db.session.delete(self)  # 此时ORM会自动删除关联的床位
            
            # 7. 构建详细的成功消息
            base_message = f"房间 {self.building}{self.room_number} 已成功删除"
            
            related_deletions = []
            if delete_stats['beds'] > 0:
                related_deletions.append(f"{delete_stats['beds']}个床位")
            if delete_stats['dorm_records'] > 0:
                related_deletions.append(f"{delete_stats['dorm_records']}条住宿记录")
            if delete_stats['meter_records'] > 0:
                related_deletions.append(f"{delete_stats['meter_records']}条抄表记录")
            if delete_stats['subsidy_records'] > 0:
                related_deletions.append(f"{delete_stats['subsidy_records']}条费用补贴记录")
            if delete_stats['checkout_records'] > 0:
                related_deletions.append(f"{delete_stats['checkout_records']}条退宿费用记录")
            if delete_stats['utility_records'] > 0:
                related_deletions.append(f"{delete_stats['utility_records']}条费用主记录")
            if delete_stats['occupant_records'] > 0:
                related_deletions.append(f"{delete_stats['occupant_records']}条在住用户分摊记录")
            
            if delete_stats['facility_records'] > 0:
                related_deletions.append(f"{delete_stats['facility_records']}条房间设施记录")
            
            # 添加房间照片删除信息
            if delete_stats['photos_deleted']:
                related_deletions.append(f"房间照片")
            
            # 添加抄表记录照片删除信息
            if delete_stats['meter_photos_deleted']:
                related_deletions.append(f"抄表记录照片")

            if related_deletions:
                message = f"{base_message}，同时删除了：{', '.join(related_deletions)}"
            else:
                message = base_message
            
            logging.info(f"用户 {current_user.id} {message}")
            return {'success': True, 'message': message}
            
        except Exception as e:
            db.session.rollback()
            message = f"删除房间失败：{str(e)}"
            logging.error(message, exc_info=True)
            return {'success': False, 'message': message}

    # 其他方法保持不变
    @classmethod
    def get_valid_room_types(cls):
        """从系统配置获取有效的房间类型"""
        return SystemConfig.get_config_value('ROOM_TYPES', ["单人间", "双人间", "四人间", "六人间", "其他类型"])
    
    @classmethod
    def get_valid_gender_restrictions(cls):
        return ["男", "女", "无限制"]
    
    @classmethod
    def get_valid_statuses(cls):
        return [
            "可用",      # 对应RoomStatus.AVAILABLE
            "已满",      # 对应RoomStatus.FULL
            "维护中",    # 对应RoomStatus.MAINTENANCE
            "已关闭"     # 对应RoomStatus.CLOSED
        ]
    
    
    @classmethod
    def bulk_create_or_update(cls, rooms_data, override=False):
        success_create = 0
        success_update = 0
        errors = []
        created_rooms = []  # 新增：存储新创建的房间实例
        
        # 类型映射 - 显示文本到数据库值
        # 从系统配置获取房间类型
        room_types = cls.get_valid_room_types()
        # 创建类型映射 - 显示文本到数据库值
        TYPE_MAPPING = {t: t for t in room_types}
        
        
        STATUS_MAPPING = {
            '可用': RoomStatus.AVAILABLE.value,
            '已满': RoomStatus.FULL.value,
            '维护中': RoomStatus.MAINTENANCE.value,
            '已关闭': RoomStatus.CLOSED.value
        }
        
        for index, data in enumerate(rooms_data):
            try:
                row_num = index + 1  # 数据行号，用于错误提示
                
                # 提取并验证数据
                building = str(data.get('楼栋', '')).strip()
                room_number = str(data.get('房间号', '')).strip()
                
                if not building or not room_number:
                    errors.append(f"第{row_num}行：楼栋和房间号为必填项")
                    continue
                
                # 转换房间类型
                room_type_text = str(data.get('房间类型', '')).strip()
                if room_type_text not in TYPE_MAPPING:
                    errors.append(f"第{row_num}行：无效的房间类型 '{room_type_text}'，有效类型: {', '.join(room_types)}")
                    continue
                room_type = TYPE_MAPPING[room_type_text]

                gender_restriction = str(data.get('性别限制', '')).strip()
                valid_gender_restrictions = cls.get_valid_gender_restrictions()
                if gender_restriction not in valid_gender_restrictions:
                    errors.append(f"第{row_num}行：无效的性别限制 '{gender_restriction}'，有效限制: {', '.join(valid_gender_restrictions)}")
                    continue
                status = STATUS_MAPPING[str(data.get('状态', '')).strip()]


                # 验证容量
                try:
                    capacity = int(data.get('容量', 0))
                    if capacity <= 0:
                        errors.append(f"第{row_num}行：容量必须为正整数")
                        continue
                except (ValueError, TypeError):
                    errors.append(f"第{row_num}行：容量必须为有效的整数")
                    continue

                # 处理租金
                try:
                    external_rent = Decimal(str(data.get('对外租金', '0')))
                    cost_rent = Decimal(str(data.get('成本租金', '0')))
                    if external_rent < 0 or cost_rent < 0:
                        errors.append(f"第{row_num}行：租金不能为负数")
                        continue
                except (ValueError, TypeError):
                    errors.append(f"第{row_num}行：租金必须为有效的数字")
                    continue

                # 处理备注
                remark = str(data.get('备注', '')).strip()
                
                # 检查房间是否已存在
                existing_room = cls.query.filter_by(
                    building=building,
                    room_number=room_number
                ).first()
                
                if existing_room:
                    # 房间已存在
                    if override:
                        # 检查是否有人住宿且尝试设置为关闭状态
                        if status == RoomStatus.CLOSED.value and existing_room.current_occupancy > 0:
                            errors.append(f"第{row_num}行：房间 {building}-{room_number} 有人住宿，无法设置为关闭状态")
                            continue
                            
                        # 更新房间信息
                        existing_room.room_type = room_type
                        existing_room.capacity = capacity
                        existing_room.gender_restriction = gender_restriction
                        existing_room.status = status
                        existing_room.external_rent = external_rent
                        existing_room.cost_rent = cost_rent
                        existing_room.remark = remark
                        # 更新地址
                        existing_room.address = str(data.get('地址', '')).strip()
                        try:
                            existing_room.electric_meter_max = Decimal(str(data.get('电表最大量程', '9999.99') or '9999.99'))
                            existing_room.water_meter_max = Decimal(str(data.get('水表最大量程', '9999.99') or '9999.99'))
                        except (ValueError, TypeError, Decimal.TypeError):
                            errors.append(f"第{row_num}行：水电表最大量程必须为有效的数字")
                            continue

                        # 自动调整状态
                        if status == RoomStatus.AVAILABLE.value and existing_room.current_occupancy >= capacity:
                            existing_room.status = RoomStatus.FULL.value
                        
                        # 根据新容量调整床位
                        cls._adjust_beds_for_room(existing_room, capacity)    
                        success_update += 1
                    else:
                        errors.append(f"第{row_num}行：房间 {building}-{room_number} 已存在，未更新")
                else:
                    # 创建新房间
                    # 处理房间级别
                    valid_room_levels = cls.get_valid_room_levels()
                    room_level = data.get('房间级别')
                    if room_level is not None and room_level not in valid_room_levels:
                        errors.append(f"第{row_num}行：无效的房间级别 '{room_level}'，有效级别: {', '.join(valid_room_levels)}")
                        continue
                    
                    # 处理添加时间
                    created_at = data.get('添加时间')
                    # 验证添加时间的有效性
                    if created_at is not None and not isinstance(created_at, datetime):
                        errors.append(f"第{row_num}行：添加时间格式无效，请使用正确的日期时间格式")
                        continue

                    new_room = cls(
                            building=building,
                            room_number=room_number,
                            address=str(data.get('地址', '')).strip(),
                            room_type=room_type,
                            room_level=room_level,
                            capacity=capacity,
                            gender_restriction=gender_restriction,
                            status=status,
                            current_occupancy=0,
                            external_rent=external_rent,
                            cost_rent=cost_rent,
                            electric_meter_max=Decimal(str(data.get('电表最大量程', '9999.99') or '9999.99')),
                            water_meter_max=Decimal(str(data.get('水表最大量程', '9999.99') or '9999.99')),
                            remark=remark,
                            operator_user_id=current_user.id if current_user.is_authenticated else None,
                            created_at=created_at,
                            updated_at=created_at
                    )
                    db.session.add(new_room)
                    # 提交以获取新房间ID（用于关联床位）
                    db.session.flush()
                    # 为新房间创建对应数量的床位
                    cls._create_beds_for_room(new_room, capacity)
                    # 调用费用主表的创建方法，同步生成本期账单，并传递房间创建时间
                    from models.utility_room_bill_record import RoomUtilityRecord
                    RoomUtilityRecord.create_for_new_room(new_room.id, new_room.created_at)
                    
                    success_create += 1
                    created_rooms.append(new_room)  # 关键：将新房间添加到列表
                    logging.info(f"批量导入新房间 {new_room.room_full_identifier} 及费用记录")
                
            except Exception as e:
                errors.append(f"第{row_num}行：处理失败 - {str(e)}")
                continue
        
        try:
            db.session.commit()
            logging.info(f"批量操作完成：创建{success_create}个，更新{success_update}个房间")
        except Exception as e:
            db.session.rollback()
            errors.append(f"批量提交失败：{str(e)}")
            logging.error(f"批量提交失败：{str(e)}")
        # 返回4个值：新增数量、更新数量、错误列表、新创建的房间列表    
        return (success_create, success_update, errors, created_rooms)

    @staticmethod
    def _create_beds_for_room(room, capacity):
        if not room.id:
            logging.error("房间ID为空，无法创建床位！")
            raise ValueError("房间ID不存在，无法创建床位")
        
        # 先清理该房间可能存在的旧床位（避免约束冲突）
        existing_beds = Bed.query.filter_by(room_id=room.id).all()
        if existing_beds:
            logging.warning(f"房间 {room.id} 存在{len(existing_beds)}个旧床位，将被删除")
            for bed in existing_beds:
                db.session.delete(bed)

        # 创建新床位
        for i in range(1, capacity + 1):
            try:
                bed = Bed(
                    room_id=room.id,
                    bed_number=str(i),
                    status=BedStatus.AVAILABLE.value
                )
                db.session.add(bed)
                db.session.flush()
                logging.info(f"已添加床位：room_id={room.id}, bed_number={i}")
            except Exception as e:
                raise ValueError(f"创建床位 {i} 失败：{str(e)}") from e

    @staticmethod
    def _adjust_beds_for_room(room, new_capacity):
        current_bed_count = len(room.room_beds)
        
        if new_capacity > current_bed_count:
            # 容量增加：补充新床位
            for i in range(current_bed_count + 1, new_capacity + 1):
                bed = Bed(
                    room_id=room.id,
                    bed_number=str(i),
                    status=BedStatus.AVAILABLE.value
                )
                db.session.add(bed)
        elif new_capacity < current_bed_count:
            # 容量减少：删除多余床位（先检查是否已占用）
            # 按床位号排序，确保删除的是编号较大的床位
            sorted_beds = sorted(room.room_beds, key=lambda x: (int(x.bed_number) if x.bed_number.isdigit() else float('inf'), x.bed_number))
            beds_to_delete = sorted_beds[new_capacity:]  # 超出新容量的床位
            
            # 检查待删除床位是否有已占用的，有则阻止操作
            for bed in beds_to_delete:
                if bed.status == BedStatus.OCCUPIED.value:
                    raise ValueError(f"房间{room.room_full_identifier}的床位{bed.bed_number}已占用，无法减少容量")
            
            # 执行删除
            for bed in beds_to_delete:
                db.session.delete(bed)
    
    