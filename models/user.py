from utils.db import db
from datetime import datetime  # 修改：仅保留datetime导入，移除date
import re
import logging
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin, current_user  # 导入Flask-Login支持类
from models.department import Department

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(50), unique=True, nullable=True, comment='工号')
    name = db.Column(db.String(50), nullable=False, comment='姓名')
    gender = db.Column(db.String(10), nullable=False, comment='性别')
    category = db.Column(db.String(50), default='员工', nullable=True, comment='人员类别：员工/职员/管理员等')
    id_card = db.Column(db.String(18), nullable=True, comment='身份证号码')
    id_address = db.Column(db.String(500), nullable=True, comment='身份证地址')
    phone = db.Column(db.String(20), nullable=True, comment='电话')
    company = db.Column(db.String(100), nullable=True, comment='公司')
    department_id = db.Column(db.Integer, db.ForeignKey('departments.id'), nullable=True, comment='部门ID')
    position = db.Column(db.String(100), nullable=True, comment='职位')
    emergency_contact = db.Column(db.String(50), nullable=True, comment='紧急联系人')
    emergency_phone = db.Column(db.String(50), nullable=True, comment='紧急联系人电话')
    remarks = db.Column(db.Text, nullable=True, comment='备注')
    status = db.Column(db.String(20), default='在职', comment='状态：在职/离职/自离')
    hire_date = db.Column(db.DateTime, default=datetime.now, comment='入职日期')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    
    # 用户认证相关字段
    username = db.Column(db.String(50), unique=True, nullable=False, comment='用户名')
    password_hash = db.Column(db.String(256), nullable=False, comment='密码哈希')
    role_id = db.Column(db.Integer, db.ForeignKey('roles.id'), nullable=True, comment='角色ID')
    last_login_at = db.Column(db.DateTime, nullable=True, comment='最后登录时间')
    is_active = db.Column(db.Boolean, default=True, nullable=True, comment='是否激活账号')
    is_banned = db.Column(db.Boolean, default=False, nullable=True, comment='是否允许登录')

    # 基本信息相关字段
    birth_date = db.Column(db.DateTime, nullable=True, comment='出生日期')
    age = db.Column(db.Integer, nullable=True, comment='年龄')
    native_place = db.Column(db.String(100), nullable=True, comment='籍贯')
    ethnicity = db.Column(db.String(50), default='', nullable=True, comment='民族')
    marital_status = db.Column(db.String(20), default='', nullable=True, comment='婚姻状态')
    lodging_address = db.Column(db.String(500), nullable=True, comment='外宿地址')
    
    # 补贴相关字段
    reduction_fee = db.Column(db.Numeric(10, 2), default=0, comment='住宿补贴')
    lodging_allowance = db.Column(db.Numeric(10, 2), default=0, comment='外宿补贴')

    # 部门关系映射
    dept = db.relationship('Department', foreign_keys=[department_id], backref='users_lazy', lazy='select')

    @property
    def department(self):
        """返回部门名称（通过relationship获取）"""
        if self.dept:
            return self.dept.name
        return None

    @property
    def role_name(self):
        """返回角色名称（通过relationship获取）"""
        if self.user_role:
            return self.user_role.name
        return '无角色'

    def __repr__(self):
        return f"<User {self.category or '未知'} {self.student_id}: {self.name}>"

    # 密码处理方法
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_id_card_valid(self):
        """验证身份证号码格式"""
        if not self.id_card:
            return True  # 允许为空
        
        if not re.match(r'^\d{17}[\dXx]$', self.id_card):
            return False
        return True
    
    def get_birth_date_from_id(self):
        """从身份证号码提取出生日期（返回datetime类型）"""
        # 确保id_card是字符串类型
        id_card_str = str(self.id_card) if self.id_card else ''
        if not id_card_str or len(id_card_str) != 18:
            return None
            
        try:
            birth_str = id_card_str[6:14]
            # 修改：返回datetime对象而非date
            return datetime.strptime(birth_str, '%Y%m%d')
        except:
            return None
    
    def get_age(self):
        """根据出生日期计算年龄（基于日期部分计算）"""
        if not self.birth_date:
            self.birth_date = self.get_birth_date_from_id()
            
        if not self.birth_date:
            return None
            
        try:
            # 修改：使用datetime.now().date()获取当前日期
            today = datetime.now().date()
            # 取出生日期的日期部分进行比较
            birth_date = self.birth_date.date() if isinstance(self.birth_date, datetime) else self.birth_date
            
            age = today.year - birth_date.year
            if (today.month, today.day) < (birth_date.month, birth_date.day):
                age -= 1
            return age
        except:
            return None
    
    # --------------------------
    # 籍贯提取相关
    # --------------------------
    def extract_native_place(self):
        """从身份证地址提取籍贯，并自动保存到native_place字段"""

        if not self.id_address:  # 无身份证地址，无法提取
            self.native_place = None
            return None
            
        try:
            separators = ['省', '市', '自治区', '自治州', '县', '区', '乡', '镇', '村', '街道']
            # 确保address为字符串类型，防止整数类型调用strip()和len()时出错
            address = str(self.id_address).strip()
            
            # 处理直辖市
            if address.startswith(('北京市', '上海市', '天津市', '重庆市')):
                self.native_place = address[:3]
                return self.native_place
                
            # 提取省份和城市
            for sep in separators:
                index = address.find(sep)
                if index > 0:
                    province_part = address[:index+1]
                    remaining = address[index+1:]
                    for city_sep in separators:
                        city_index = remaining.find(city_sep)
                        if city_index > 0:
                            self.native_place = f"{province_part}{remaining[:city_index+1]}"
                            return self.native_place
                    self.native_place = province_part
                    return self.native_place
            
            # 兜底逻辑：取前2个字符
            self.native_place = address[:2] if len(address) >= 2 else address
            return self.native_place
        except Exception as e:
            logging.warning(f"提取籍贯失败: {str(e)}")
            self.native_place = None
            return None
    

    # --------------------------
    # 信息补全与保存
    # --------------------------
    def auto_complete_info(self):
        logging.debug(f"开始自动补全用户{self.id}信息")
        
        # 1. 身份证信息提取
        # 强制重新提取籍贯，无论是否已有值
        self.extract_native_place()
        
        # 2. 从身份证提取出生日期
        # 强制重新提取出生日期，无论是否已有值
        self.birth_date = self.get_birth_date_from_id()
        self.age = self.get_age()  # 强制更新年龄
        
        logging.debug(f"用户{self.id}自动补全信息完成")
    
    def save(self):
        """保存用户信息时自动触发信息补全"""
        self.auto_complete_info()  # 触发自动补全（含籍贯和住宿信息）
        if self.id is None:
            db.session.add(self)
        db.session.commit()
    
    # Flask-Login认证相关方法
    def get_id(self):
        return str(self.id)

    # 用户登录状态和在职判断
    @property
    def is_authenticated(self):
        return self.status == '在职' and super().is_authenticated

    # 用户状态判断方法
    def is_status(self):
        """判断是否在职"""
        return self.status in ['在职']

    # 管理员判断方法 - 基于角色权限
    def has_permission(self, permission_code):
        """判断用户是否拥有指定权限"""
        if not self.is_authenticated:
            return False
        # 超级管理员自动拥有所有权限
        if self.user_role and self.user_role.code == 'super_admin':
            return True
        # 查询角色权限表
        if self.user_role:
            return self.user_role.has_permission(permission_code)
        return False
    
    # 删除用户的方法
    def delete(self):
        """删除用户记录
        权限限制逻辑：
        - 普通管理员：如果用户存在任何关联记录，禁止删除并显示具体原因
        - 超级管理员：不受关联记录限制，可以删除所有记录及关联数据
        返回值：字典，包含'success'布尔值和'message'字符串
        """
        try:
            from models.dorm import Dorm
            from models.fee_subsidy import FeeSubsidy
            from models.utility_room_bill_checkout import CheckoutUtilityRecord
            from models.utility_room_bill_occupant import RoomUtilityOccupant
            # 导入留言相关模型和工具
            from models.ticket import Ticket
            from utils.ticket_photo import ticket_photo_manager
            
            # 检查当前操作人是否为超级管理员（拥有级联删除权限）
            is_super = current_user.is_authenticated and current_user.user_role and current_user.user_role.code == 'super_admin'
            
            # 1. 禁止删除超级管理员用户（无论谁操作）
            if self.user_role and self.user_role.code == 'super_admin':
                message = f"操作失败：禁止删除超级管理员「{self.name}」"
                logging.warning(message)
                return {'success': False, 'message': message}
                
            # 2. 禁止删除用户自身（无论谁操作）
            if current_user.is_authenticated and current_user.id == self.id:
                message = "操作失败：不能删除当前登录的用户自身"
                logging.warning(message)
                return {'success': False, 'message': message}
            
            # 3. 检查所有关联记录类型（用于提示信息）
            has_dorm = Dorm.query.filter_by(user_id=self.id).first() is not None
            has_subsidy = FeeSubsidy.query.filter_by(user_id=self.id).first() is not None
            has_occupant = RoomUtilityOccupant.query.filter_by(user_id=self.id).first() is not None
            has_checkout = CheckoutUtilityRecord.query.filter_by(user_id=self.id).first() is not None
            # 检查是否有留言记录
            has_ticket = Ticket.query.filter_by(user_id=self.id).first() is not None
            
            # 4. 普通管理员权限限制：存在任何关联记录则禁止删除
            if not is_super:
                # 收集存在的关联记录类型，用于具体提示
                related_records = []
                if has_dorm:
                    related_records.append("住宿记录")
                if has_subsidy:
                    related_records.append("费用补贴记录")
                if has_occupant:
                    related_records.append("在住人员分摊记录")
                if has_checkout:
                    related_records.append("退宿费用记录")
                if has_ticket:
                    related_records.append("留言记录")
                
                if related_records:
                    # 明确列出存在的记录类型，让用户清楚原因
                    message = (
                        f"操作失败：用户「{self.name}」存在以下关联记录，"
                        f"无法删除：{','.join(related_records)}。"
                        "请联系超级管理员处理或先清除相关记录"
                    )
                    logging.warning(message)
                    return {'success': False, 'message': message}
            
            # 5. 超级管理员操作：执行级联删除
            deleted_records = []
            
            # 5.6 删除聊天相关记录
            from models.chat_session import ChatSession
            from models.chat_participant import ChatParticipant
            from models.chat_message import ChatMessage

            # 5.1 还原床位和房间状态，并删除关联的住宿记录
            dorm_records = Dorm.query.filter_by(user_id=self.id).all()
            if dorm_records:
                # 还原床位和房间状态
                from models.room_bed import Bed
                from models.room import Room
                for dorm in dorm_records:
                    # 还原床位状态
                    if dorm.bed_id:
                        bed = Bed.query.get(dorm.bed_id)
                        if bed:
                            bed.status = 'available'
                            db.session.add(bed)
                            deleted_records.append(f"床位 {bed.bed_number} 状态已还原")
                    
                    # 更新房间状态（检查房间是否还有其他住客）
                    if dorm.room_id:
                        room = Room.query.get(dorm.room_id)
                        if room:
                            # 检查房间是否还有其他活跃的住宿记录
                            other_active_dorms = Dorm.query.filter(
                                Dorm.room_id == dorm.room_id,
                                Dorm.user_id != self.id,
                                Dorm.status == 'active'
                            ).first()
                            
                            if not other_active_dorms:
                                room.status = 'available'
                                room.current_occupancy = max(0, room.current_occupancy - 1)
                                room.calculate_average_age()
                                # 触发入住率计算更新
                                _ = room.occupancy_rate
                                db.session.add(room)
                                deleted_records.append(f"房间 {room.room_number} 状态已还原为空闲，当前入住人数更新为 {room.current_occupancy}，平均年龄和入住率已更新")
            
            # 删除住宿记录
            Dorm.query.filter_by(user_id=self.id).delete()
            deleted_records.append(f"住宿记录 {len(dorm_records)} 条")
            
            # 5.2 删除所有费用补贴记录
            subsidy_records = FeeSubsidy.query.filter_by(user_id=self.id).all()
            if subsidy_records:
                FeeSubsidy.query.filter_by(user_id=self.id).delete(synchronize_session=False)
                deleted_records.append(f"费用补贴记录 {len(subsidy_records)} 条")
            
            # 5.3 删除关联的在住人员分摊记录
            occupant_records = RoomUtilityOccupant.query.filter_by(user_id=self.id).all()
            if occupant_records:
                RoomUtilityOccupant.query.filter_by(user_id=self.id).delete(synchronize_session=False)
                deleted_records.append(f"在住人员分摊记录 {len(occupant_records)} 条")

            # 5.4 删除退宿费用记录及相关费用补贴使用记录
            checkout_records = CheckoutUtilityRecord.query.filter_by(user_id=self.id).all()
            if checkout_records:
                # 先删除相关的费用补贴使用记录
                from models.fee_subsidy_usage import FeeSubsidyUsage
                subsidy_usage_records = FeeSubsidyUsage.query.filter(
                    FeeSubsidyUsage.user_id == self.id,
                    FeeSubsidyUsage.is_checkout == '1'
                ).all()
                if subsidy_usage_records:
                    FeeSubsidyUsage.query.filter(
                        FeeSubsidyUsage.user_id == self.id,
                        FeeSubsidyUsage.is_checkout == '1'
                    ).delete()
                    deleted_records.append(f"退宿相关费用补贴使用记录 {len(subsidy_usage_records)} 条")

                # 再删除退宿费用记录
                CheckoutUtilityRecord.query.filter_by(user_id=self.id).delete()
                deleted_records.append(f"退宿费用记录 {len(checkout_records)} 条")
            
            # 5.5 删除用户相关的留言和照片
            tickets = Ticket.query.filter_by(user_id=self.id).all()
            
            # 5.6.1 删除用户发送的聊天消息
            message_records = ChatMessage.query.filter_by(sender_id=self.id).all()
            if message_records:
                ChatMessage.query.filter_by(sender_id=self.id).delete()
                deleted_records.append(f"聊天消息记录 {len(message_records)} 条")
            
            # 5.6.2 获取用户参与的聊天会话
            participant_records = ChatParticipant.query.filter_by(user_id=self.id).all()
            if participant_records:
                # 记录需要检查的会话ID
                session_ids_to_check = [p.chat_session_id for p in participant_records]
                # 删除用户的所有聊天会话参与记录
                ChatParticipant.query.filter_by(user_id=self.id).delete()
                deleted_records.append(f"聊天会话参与记录 {len(participant_records)} 条")
                
                # 5.6.3 检查并删除会话
                for session_id in set(session_ids_to_check):
                    # 获取会话对象
                    session = ChatSession.query.get(session_id)
                    if session:
                        if not session.is_group_chat:
                            # 如果不是群聊，直接删除整个会话
                            db.session.delete(session)
                            deleted_records.append(f"聊天会话 {session.id}（非群聊）")
                        else:
                            # 如果是群聊，检查删除当前用户后是否还有其他参与者
                            remaining_participants = ChatParticipant.query.filter_by(chat_session_id=session_id).count()
                            if remaining_participants == 0:
                                # 如果没有其他参与者，删除整个会话
                                db.session.delete(session)
                                deleted_records.append(f"聊天会话 {session.id}（群聊但无其他参与者）")
            if tickets:
                # 删除每个留言及其照片
                for ticket in tickets:
                    # 删除留言照片
                    ticket_photo_manager.delete_ticket_directory(ticket.id)
                    # 删除留言（留言模型中的delete方法会级联删除回复）
                    ticket.delete()
                deleted_records.append(f"留言记录 {len(tickets)} 条及相关照片")
            
            # 保存用户名以便构建成功消息
            user_name = self.name
            
            # 6. 删除用户自身
            db.session.delete(self)
            
            # 7. 构建成功消息，明确删除的内容
            if deleted_records:
                message = (
                    f"操作成功：用户「{user_name}」已删除，"
                    f"同时清除关联记录：{','.join(deleted_records)}"
                )
            else:
                message = f"操作成功：用户「{user_name}」已删除，无关联记录"
                
            logging.info(message)
            return {'success': True, 'message': message}
            
        except Exception as e:
            # 错误消息包含具体异常信息，便于排查
            error_msg = f"操作失败：删除用户时发生错误 - {str(e)}"
            logging.error(error_msg, exc_info=True)
            return {'success': False, 'message': error_msg}

    @classmethod
    def batch_create_users(cls, user_data_list):
        """
        批量创建用户对象（不提交事务）
        仅创建用户对象并进行基础验证，不处理数据库事务
        返回成功创建的用户对象列表和错误信息
        
        参数:
            user_data_list: 包含用户数据的字典列表
            
        返回:
            字典，包含'success'（用户对象列表）和'failed'（错误信息列表）
        """
        result = {
            'success': [],
            'failed': []
        }
        logging.info(f"开始批量创建用户，共{len(user_data_list)}条数据")
        # 收集现有工号和用户名用于查重
        existing_student_ids = {user.student_id for user in cls.query.with_entities(cls.student_id).all()}
        existing_usernames = {user.username for user in cls.query.with_entities(cls.username).all()}
        
        # 用于检查同批次数据中的重复
        batch_student_ids = set()
        batch_usernames = set()
        
        for idx, user_data in enumerate(user_data_list):
            row_num = idx + 2  # 行号从2开始（Excel表头占1行）
            errors = []
            logging.info(f"验证第{row_num}行必填字段")
            # 验证必填字段（包含password）
            required_fields = ['student_id', 'name', 'gender', 'username', 'password']
            for field in required_fields:
                if field not in user_data or not user_data[field]:
                    errors.append(f"缺少必填字段: {field}")
                    logging.error(f"导入用户数据操作，第{row_num}行：缺少必填字段{field}，已跳过")
            
            # 检查工号唯一性（数据库中已存在）
            if user_data.get('student_id') in existing_student_ids:
                errors.append(f"工号已存在: {user_data.get('student_id')}")
                logging.error(f"导入用户数据操作，第{row_num}行：工号已存在，已跳过")
            
            # 检查工号唯一性（同批次内）
            if user_data.get('student_id') in batch_student_ids:
                errors.append(f"同批次内工号重复: {user_data.get('student_id')}")
                logging.error(f"导入用户数据操作，第{row_num}行：工号重复，已跳过")
            
            # 检查用户名唯一性（数据库中已存在）
            if user_data.get('username') in existing_usernames:
                errors.append(f"用户名已存在: {user_data.get('username')}")
                logging.error(f"导入用户数据操作，第{row_num}行：用户名已存在，已跳过")
            
            # 检查用户名唯一性（同批次内）
            if user_data.get('username') in batch_usernames:
                errors.append(f"同批次内用户名重复: {user_data.get('username')}")
                logging.error(f"导入用户数据操作，第{row_num}行：用户名重复，已跳过")
            
            # 如果有错误，记录并继续处理下一条
            if errors:
                result['failed'].append({
                    'row': row_num,
                    'data': {k: v for k, v in user_data.items() if k != 'password'},  # 不记录密码
                    'errors': errors
                })
                continue
            logging.info(f"第{row_num}行必填字段验证通过，开始创建用户对象")
            try:
                # 创建用户对象但不保存
                user = cls(
                    student_id=user_data['student_id'],
                    name=user_data['name'],
                    gender=user_data['gender'],
                    category=user_data.get('category'),
                    id_card=user_data.get('id_card'),
                    id_address=user_data.get('id_address'),
                    lodging_address=user_data.get('lodging_address'),
                    phone=user_data.get('phone'),
                    company=user_data.get('company'),
                    department_id=_get_department_id(user_data.get('department'), user_data.get('company')),
                    position=user_data.get('position'),
                    marital_status=user_data.get('marital_status'),
                    ethnicity=user_data.get('ethnicity'),
                    emergency_contact=user_data.get('emergency_contact'),
                    emergency_phone=user_data.get('emergency_phone'),
                    remarks=user_data.get('remarks'),
                    status=user_data.get('status', '在职'),
                    hire_date=user_data.get('hire_date'),
                    username=user_data['username'],
                    role_id=user_data.get('role_id'),
                    is_active=user_data.get('is_active', True),
                    is_banned=user_data.get('is_banned', True),
                    created_at=user_data.get('created_at', datetime.now()),
                    updated_at=user_data.get('updated_at', datetime.now())
                    # 不处理住宿相关字段，因为用户不会上传
                )
                # 调用模型的set_password方法处理密码（核心修改点）
                user.set_password(user_data['password'])
                # 添加到成功列表
                result['success'].append(user)
                # 更新批次内查重集合
                batch_student_ids.add(user.student_id)
                batch_usernames.add(user.username)
                logging.info(f"第{row_num}行用户对象创建成功，工号：{user.student_id}，用户名：{user.username}")
            except Exception as e:
                logging.error(f"导入用户数据操作，第{row_num}行：创建用户对象失败，已跳过")
                result['failed'].append({
                    'row': row_num,
                    'data': {k: v for k, v in user_data.items() if k != 'password'},
                    'errors': [f'创建用户对象失败: {str(e)}']
                })
        
        return result

    @classmethod
    def batch_update_users(cls, user_data_list):
        """
        批量更新用户对象（不提交事务）
        根据用户ID查找并更新用户
        返回成功更新的用户对象列表和错误信息
        
        参数:
            user_data_list: 包含用户数据的字典列表，每条数据必须包含id作为唯一标识
            
        返回:
            字典，包含'success'（成功更新的用户对象列表）和'failed'（错误信息列表）
        """
        result = {
            'success': [],
            'failed': []
        }
        logging.info(f"开始批量更新用户对象，共{len(user_data_list)}条数据")
        # 跟踪已处理的用户ID，避免同批次重复更新
        processed_ids = set()
        
        for idx, user_data in enumerate(user_data_list):
            row_num = idx + 2  # 行号从2开始（Excel表头占1行）
            errors = []
            user_id = None
            logging.info(f"批量更新用户操作，第{row_num}行：开始处理用户数据")
            # 验证唯一标识字段（用户ID）
            if not user_data.get('id'):
                errors.append("缺少唯一标识字段：用户ID")
                logging.error(f"批量更新用户操作，第{row_num}行：缺少用户ID，已跳过")
            else:
                try:
                    user_id = int(user_data.get('id'))
                    # 检查用户是否存在
                    if not cls.query.get(user_id):
                        errors.append(f"未找到用户：ID={user_id}")
                        logging.error(f"批量更新用户操作，第{row_num}行：未找到用户，已跳过")
                except ValueError:
                    errors.append(f"无效的用户ID格式：{user_data.get('id')}")
                    logging.error(f"批量更新用户操作，第{row_num}行：无效的用户ID格式，已跳过")
            
            # 检查是否已处理过该用户
            if user_id and user_id in processed_ids:
                errors.append(f"同批次内用户重复更新：用户ID={user_id}")
                logging.error(f"批量更新用户操作，第{row_num}行：用户重复更新，已跳过")
            
            # 检查必填字段（姓名、性别）
            required_fields = ['name', 'gender']
            for field in required_fields:
                if field in user_data and not user_data[field]:
                    errors.append(f"必填字段为空: {field}")
                    logging.warning(f"批量更新用户操作，第{row_num}行：必填字段{field}为空")
            
            # 如果有错误，记录并继续处理下一条
            if errors or not user_id:
                result['failed'].append({
                    'row': row_num,
                    'data': {k: v for k, v in user_data.items() if k != 'password'},  # 不记录密码
                    'errors': errors
                })
                continue
            
            try:
                # 查找用户对象
                user = cls.query.get(user_id)
                if not user:
                    errors.append(f"用户不存在：ID={user_id}")
                    result['failed'].append({
                        'row': row_num,
                        'data': {k: v for k, v in user_data.items() if k != 'password'},
                        'errors': errors
                    })
                    continue
                
                # 更新用户字段
                fields_to_update = ['name', 'gender', 'category', 'id_card', 'id_address', 
                                   'lodging_address', 'phone', 'company', 
                                   'position', 'marital_status', 'ethnicity', 'emergency_contact', 
                                   'emergency_phone', 'remarks', 'status', 'hire_date', 'role_id', 
                                   'is_active', 'is_banned', 'username', 'student_id']
                
                for field in fields_to_update:
                    if field in user_data and user_data[field] is not None:
                        value = user_data[field]
                        setattr(user, field, value)
                
                # 单独处理department → department_id的转换
                if 'department' in user_data and user_data['department'] is not None:
                    user.department_id = _get_department_id(user_data['department'], user_data.get('company'))
                
                # 单独处理密码（如果提供了新密码）
                if 'password' in user_data and user_data['password']:
                    user.set_password(user_data['password'])
                
                # 更新更新时间
                user.updated_at = datetime.now()
                
                # 添加到成功列表
                result['success'].append(user)
                processed_ids.add(user_id)
                logging.info(f"批量更新用户操作，第{row_num}行：用户对象更新成功，用户ID：{user_id}")
            except Exception as e:
                logging.error(f"批量更新用户操作，第{row_num}行：更新用户对象失败，已跳过")
                result['failed'].append({
                    'row': row_num,
                    'data': {k: v for k, v in user_data.items() if k != 'password'},
                    'errors': [f'更新用户对象失败: {str(e)}']
                })
        
        return result


def _get_department_id(dept_name, company=None):
    """根据部门名称和公司查找部门ID，不存在则自动创建"""
    if not dept_name:
        return None
    # 按name+company查找
    query = Department.query.filter_by(name=dept_name)
    if company:
        query = query.filter(db.or_(Department.company == company, Department.company.is_(None)))
    else:
        query = query.filter(Department.company.is_(None))
    existing = query.first()
    if existing:
        return existing.id
    # 不存在则创建
    dept = Department.create(name=dept_name, company=company, status='正常')
    return dept.id

