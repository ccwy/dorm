from utils.db import db
from datetime import datetime  # 修改：移除date导入，保留datetime
import logging
import traceback  # 新增：导入traceback模块
from models.room import Room  # 导入房间模型
from models.room_bed import Bed  # 导入床位模型
from models.user import User  # 关键修复：添加User模型的导入
from flask_login import current_user  # 用于获取当前登录用户

class Dorm(db.Model):
    """住宿分配模型（管理用户与房间的关联，解决关系冲突）"""
    __tablename__ = 'dorms'
    
    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False, comment='人员ID（限制删除）')
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='RESTRICT'), nullable=False, comment='房间ID（限制删除）')
    # 新增：关联床位（允许为None兼容旧数据，新记录自动分配）
    bed_id = db.Column(db.Integer, db.ForeignKey('room_beds.id', ondelete='RESTRICT'), nullable=True, comment='床位ID（后端自动分配）')
    
    # 修改：将date改为datetime类型
    check_in_date = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='入住日期时间（默认当前时间）')
    check_out_date = db.Column(db.DateTime, nullable=True, comment='退宿日期时间（未退宿则为None）')
    status = db.Column(db.String(20), default='active', nullable=False, comment='状态：active（在住）/checked_out（已退宿）')
    remarks = db.Column(db.String(500), nullable=True, comment='住宿备注（如分配原因、特殊情况）')
    
    # 新增：关联上一条记录（用于追溯更换历史）
    prev_dorm_id = db.Column(db.Integer, db.ForeignKey('dorms.id', ondelete='SET NULL'), nullable=True, comment='上一条住宿记录ID（更换前的记录）')
    prev_dorm = db.relationship('Dorm', remote_side=[id], backref='next_dorms', lazy='joined')  # 反向引用下一条记录
    
    # 时间记录字段
    created_at = db.Column(db.DateTime, default=datetime.now, comment='记录创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='记录更新时间')
    
    # 新增：操作用户ID字段（不与user表关联）
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作用户ID（办理人）')
    
    # 关系定义（只保留与User与Room的显式关系）
    user = db.relationship('User', backref=db.backref('dorms', lazy='dynamic'))
    room = db.relationship('Room', backref=db.backref('dorms', lazy='dynamic'))  # 显式定义room关系
    # 新增：关联床位模型（后端用，前端无感知）
    bed = db.relationship(
        'Bed',  # 模型名是Bed（来自room_bed.py）
        backref=db.backref('dorms', lazy='dynamic')
    )
    # 因为Room模型的`dorms`关系已经通过`backref='room'`自动在Dorm中创建了`room`属性
    # 重复定义会导致冲突
    
    def __repr__(self):
        status_text = "在住" if self.status == 'active' else "已退宿"
        return f"<住宿分配 {self.user_id} -> 房间{self.room_id}（{status_text}）>"
        # --------------------------
    # 新增：利用prev_dorm和next_dorms的核心方法
    # --------------------------
    @property
    def dorm_chain(self):
        """
        获取用户完整的住宿历史链（包含所有换宿记录）
        格式：[最早记录, ..., 上一条记录, 当前记录, 下一条记录, ..., 最新记录]
        """
        # 向前追溯（通过prev_dorm获取所有历史记录）
        history = []
        current = self
        while current:
            history.append(current)
            current = current.prev_dorm  # 关键：通过prev_dorm跳转到上一条记录
        history.reverse()  # 反转后按时间正序排列
        
        # 向后追溯（通过next_dorms获取所有后续记录）
        current = self.next_dorms[0] if self.next_dorms else None  # 关键：通过backref获取下一条记录
        while current:
            history.append(current)
            current = current.next_dorms[0] if current.next_dorms else None  # 继续获取下一条
        
        return history
    
    @classmethod
    def get_user_latest_dorm(cls, user_id):
        """获取用户最新的住宿记录（含换宿链的终点）"""
        # 先找最新的活跃记录
        latest_active = cls.query.filter(
            cls.user_id == user_id,
            cls.status == 'active'
        ).order_by(cls.updated_at.desc()).first()
        
        if latest_active:
            return latest_active
        
        # 若无活跃记录，找最后一条退宿记录
        latest_checked_out = cls.query.filter(
            cls.user_id == user_id,
            cls.status == 'checked_out'
        ).order_by(cls.check_out_date.desc()).first()
        
        return latest_checked_out
    
    def get_transfer_details(self):
        """获取当前记录的换宿详情（上一站/下一站信息）"""
        prev_details = None
        if self.prev_dorm:
            # 上一条记录（换出的房间）
            prev_room = Room.query.get(self.prev_dorm.room_id)
            prev_details = {
                'dorm_id': self.prev_dorm.id,
                'room_id': self.prev_dorm.room_id,
                'room_number': f"{prev_room.building}{prev_room.room_number}" if prev_room else f"ID:{self.prev_dorm.room_id}",
                'check_in': self.prev_dorm.check_in_date,
                'check_out': self.prev_dorm.check_out_date,
                'bed_number': self.prev_dorm.bed.bed_number if self.prev_dorm.bed else None
            }
        
        next_details = None
        # 修复：使用索引访问第一个元素，而不是first()方法
        if self.next_dorms:  # 先检查是否有下一条记录
            next_dorm = self.next_dorms[0]  # 使用索引获取第一个元素
        # 下一条记录（换入的房间）
            next_room = Room.query.get(next_dorm.room_id)
            next_details = {
                'dorm_id': next_dorm.id,
                'room_id': next_dorm.room_id,
                'room_number': f"{next_room.building}{next_room.room_number}" if next_room else f"ID:{next_dorm.room_id}",
                'check_in': next_dorm.check_in_date,
                'check_out': next_dorm.check_out_date,
                'bed_number': next_dorm.bed.bed_number if next_dorm.bed else None
            }
        
        return {
            'current_dorm_id': self.id,
            'prev': prev_details,  # 换宿来源
            'next': next_details   # 换宿去向
        }
            
    @property
    def stay_days(self):
        """计算住宿总天数，入住当天算1天"""
        if not self.check_in_date:
            return 0
        
        # 使用datetime类型计算
        end_date = self.check_out_date or datetime.now()
        
        # 只比较日期部分，忽略时间
        check_in_date_only = self.check_in_date.date() if isinstance(self.check_in_date, datetime) else self.check_in_date
        end_date_only = end_date.date() if isinstance(end_date, datetime) else end_date
        
        # 计算日期差，加1天确保入住当天被计算在内
        if end_date_only >= check_in_date_only:
            delta_days = (end_date_only - check_in_date_only).days
            return max(delta_days + 1, 0)  # 加1天
        
        return 0


    @classmethod
    def _sync_room_status(cls, room_id):
        """提取房间状态同步逻辑为公共方法"""
        room = Room.query.get(room_id)
        if not room:
            raise ValueError(f"房间{room_id}不存在")
            
        # 统计实际可用床位数
        actual_available = Bed.query.filter_by(
            room_id=room_id,
            status='available'
        ).count()
        
        # 计算理论可用床位数
        theoretical_available = room.capacity - room.current_occupancy
        
        # 数据不一致时修复
        if actual_available != theoretical_available:
            room.current_occupancy = room.capacity - actual_available
            room.status = 'available' if actual_available > 0 else 'full'
            db.session.add(room)

        return room
    
  
    # 新增：性别验证公共方法
    @classmethod
    def _validate_gender_match(cls, user_gender, dorm_gender_restriction):
        """
        验证用户性别与宿舍性别限制是否匹配（修复类型错误）
        """
        # 修复核心：先将user_gender转为字符串，避免int类型导致的错误
        # 处理空值或非字符串类型（如整数）
        if user_gender is None:
            return False, "用户性别信息未提供"
        
        # 强制转换为字符串（处理可能的整数类型）
        user_gender_str = str(user_gender).strip()
        
        # 验证性别有效性（只接受"男"/"女"）
        if user_gender_str not in ["男", "女"]:
            return False, f"无效的用户性别: {user_gender_str}（类型错误，应为字符串）"
        
        # 无限制的宿舍直接通过
        if dorm_gender_restriction == "无限制":
            return True, ""
        
        # 直接使用宿舍限制性别值
        dorm_gender = dorm_gender_restriction
        
        # 验证匹配
        if user_gender_str == dorm_gender:
            return True, ""
        else:
            return False, f"该宿舍仅限{ dorm_gender }使用，与用户性别不匹配"

        
    # --------------------------
    # 新增住宿分配核心方法
    # --------------------------
    @classmethod
    def create_allocation(cls, user_id, room_id, bed_id, check_in_date, remarks):
        """创建新的住宿分配记录，占用床位并更新房间状态"""
        # 获取房间信息
        room = Room.query.get(room_id)
        if not room:
            raise ValueError(f"房间{room_id}不存在")

        # 关键新增：验证用户性别与房间性别限制是否匹配
        # 1. 确保用户对象存在
        # 确保用户存在
        user = User.query.get(user_id)
        if not user:
            logging.warning(f"用户ID:{user_id}不存在，无法验证性别")
            raise ValueError(f"用户ID:{user_id}不存在，无法验证性别")
        # 确保用户状态正确
        if not user.is_status:
            logging.warning(f"用户 {user_id} 状态验证失败")
            raise ValueError(f"用户ID:{user_id}状态验证失败")

        
        # 2. 调用性别验证方法（传递正确参数）
        is_valid, error_msg = cls._validate_gender_match(
            user_gender=user.gender,  # 传递用户性别
            dorm_gender_restriction=room.gender_restriction  # 传递房间性别限制
            )
                
        # 3. 验证失败则终止流程
        if not is_valid:
            raise ValueError(error_msg)

        # 验证房间存在性（加锁防并发）
        room = Room.query.filter_by(id=room_id).with_for_update().first()
        if not room:
            logging.warning(f"房间{room_id}不存在")
            raise ValueError(f"房间{room_id}不存在")
        
        # 验证床位有效性（加锁防并发抢占）
        bed = Bed.query.filter_by(id=bed_id).with_for_update().first()
        if not bed:
            raise ValueError(f"床位{bed_id}不存在")
        if bed.status != 'available':
            raise ValueError(f"床位{bed_id}当前状态为{bed.status}，无法分配（需为available）")
        
        # 占用床位
        bed.status = 'occupied'
        
        # 创建新住宿记录
        new_dorm = cls(
            user_id=user_id,
            room_id=room_id,
            bed_id=bed_id,
            check_in_date=check_in_date,  # 已改为datetime类型
            status='active',
            remarks=remarks,
            operator_user_id=current_user.id if current_user.is_authenticated else None
        )
        
        # 更新房间 occupancy 和状态
        room.current_occupancy += 1
        if room.current_occupancy >= room.capacity:
            room.status = 'full'
        
        db.session.add(new_dorm)
        


        # 更新房间平均年龄
        if room:
            room.calculate_average_age()
        return new_dorm

    # --------------------------
    # 退宿核心方法
    # --------------------------
    def check_out(self, check_out_date, remarks):
        """处理退宿逻辑，释放床位并更新房间状态"""
     
        if self.status != 'active':
            raise ValueError("只能对活跃的住宿记录执行退宿")
        
        # 释放床位（加锁防并发）
        if self.bed_id:
            bed = Bed.query.filter_by(id=self.bed_id).with_for_update().first()
            if bed:
                if bed.status == 'occupied':
                    bed.status = 'available'

        # 更新住宿记录状态
        self.check_out_date = check_out_date  # 已改为datetime类型
        self.status = 'checked_out'
        self.remarks = remarks if remarks else self.remarks
        self.operator_user_id = current_user.id if current_user.is_authenticated else None
        
        # 更新房间 occupancy 和状态
        room = Room.query.get(self.room_id)
        if room:
            if room.current_occupancy > 0:
                room.current_occupancy -= 1           
                # 房间状态从满员改为可用          
                if room.current_occupancy < room.capacity and room.status == 'full':
                    room.status = 'available'
        
        db.session.add(self)

        # 更新房间平均年龄
        if room:
            room.calculate_average_age()
        return True

    
    # --------------------------
    # 单人更换宿舍核心方法
    # --------------------------
    @classmethod
    def change_dorm(cls, user_id, target_room_id, reason="自愿换宿", 
                   change_date=None):
        """单人更换宿舍：复用退宿和分配函数，简化逻辑"""
        # 处理用户名
        user = User.query.get(user_id)
        
        # 初始化变量，避免作用域问题
        current_dorm = None
        target_room = None
        old_room_id = None  # 单独记录旧房间ID

        try:
            session = db.session()
            has_active_transaction = session.in_transaction()
            
            if not has_active_transaction:
                db.session.begin()

            try:
                # 修改：使用datetime类型的当前时间作为默认值
                change_date = change_date or datetime.now()

                # 1. 获取当前住宿记录并验证
                current_dorm = cls.query.filter(
                    cls.user_id == user_id,
                    cls.status == 'active',
                    cls.check_out_date.is_(None)
                ).with_for_update().first()
                
                if not current_dorm:
                    raise ValueError(f"用户{user_id}无当前有效住宿记录，无法换宿")

                # 添加时间验证：确保换宿时间不小于前宿舍入住时间
                if change_date < current_dorm.check_in_date:
                    raise ValueError(f"换宿时间({change_date.strftime('%Y-%m-%d')})不能小于当前宿舍入住时间({current_dorm.check_in_date.strftime('%Y-%m-%d')})")
                    
                 # 记录旧房间ID
                old_room_id = current_dorm.room_id
                
                # 增强：多次尝试获取旧房间信息
                old_room = None
                # 第一次尝试直接查询
                old_room = Room.query.get(old_room_id)
                
                # 第二次尝试：如果直接查询失败，尝试用filter查询
                if not old_room:
                    old_room = Room.query.filter_by(id=old_room_id).first()
                
                # 第三次尝试：如果仍失败，刷新会话后再试
                if not old_room:
                    db.session.refresh(current_dorm)
                    old_room = Room.query.get(old_room_id)


                # 2. 验证目标房间并同步数据（保持数据修复逻辑）
                target_room = Room.query.filter_by(id=target_room_id).with_for_update().first()
                if not target_room:
                    raise ValueError(f"目标房间{target_room_id}不存在")

                # 关键修复：正确验证用户性别与目标房间性别限制是否匹配
                # 1. 确保用户对象存在
                if not user:
                    raise ValueError(f"用户ID:{user_id}不存在，无法验证性别")
                
                # 2. 调用性别验证方法（传递正确参数）
                is_valid, error_msg = cls._validate_gender_match(
                    user_gender=user.gender,  # 传递用户性别
                    dorm_gender_restriction=target_room.gender_restriction  # 传递房间性别限制
                )
                
                # 3. 验证失败则终止流程
                if not is_valid:
                    raise ValueError(error_msg)

                # 强制刷新并同步房间状态
                cls._sync_room_status(target_room.id)

                # 3. 检查目标房间是否有可用床位
                available_bed = Bed.query.filter_by(
                    room_id=target_room_id,
                    status='available'
                ).with_for_update().first()
                
                if not available_bed:
                    raise ValueError(f"目标房间{target_room_id}无可用床位（已同步最新数据）")

                # 4. 核心优化点：复用退宿函数处理原住宿
                old_room_id = current_dorm.room_id
                current_dorm.check_out(
                    check_out_date=change_date,  # 已改为datetime类型
                    remarks=f"换宿至房间{target_room_id}，原因：{reason}",
                )
                # 退宿后强制刷新，确保原床位状态已更新
                db.session.expire_all()

                # 5. 核心优化点：复用分配函数处理新住宿
                # create_allocation方法已经自动设置operator_user_id
                new_dorm = cls.create_allocation(
                    user_id=user_id,
                    room_id=target_room_id,
                    bed_id=available_bed.id,
                    check_in_date=change_date,  # 已改为datetime类型
                    remarks=f"从房间{old_room_id}换入，原因：{reason}"
                )
                new_dorm.prev_dorm_id = current_dorm.id

                # 6. 验证新分配结果
                if not new_dorm:
                    raise RuntimeError("新宿舍分配失败，未创建住宿记录")

                if not has_active_transaction:
                    db.session.add()

            except Exception as e:
                if not has_active_transaction:
                    db.session.rollback()
                raise e

            
            # 换宿成功后，记录完整的换宿链
            if new_dorm:
            # 关键：使用accommodation_chain获取完整历史
                history_chain = new_dorm.dorm_chain
                history_ids = [d.id for d in history_chain]
                logging.info(
                    f"用户{user_id}换宿后完整住宿链：{history_ids}，当前记录ID：{new_dorm.id}"
                )

            return new_dorm
            
        except ValueError as e:
           # 业务验证失败处理
            logging.error(f"业务验证失败处理：{str(e)}\n{traceback.format_exc()}")
            raise e
        except Exception as e:
            logging.error(f"系统异常处理：{str(e)}\n{traceback.format_exc()}")
            # 系统异常处理          
            raise e
    
    # --------------------------
    # 两人互换宿舍核心方法
    # --------------------------
    @classmethod
    def exchange_dorm(cls, user_a_id, user_b_id, reason="自愿互换",
                     exchange_date=None):
        """两人互换宿舍：复用退宿和分配函数"""
        try:
            # 关键修复1：在函数开始处初始化用户变量，避免未绑定错误
            user_a = None
            user_b = None
            room_a = None
            room_b = None
            session = db.session()
            has_active_transaction = session.in_transaction()
            
            if not has_active_transaction:
                db.session.begin()

            try:
                # 修改：使用datetime类型的当前时间作为默认值
                exchange_date = exchange_date or datetime.now()

                # 1. 获取双方用户信息（用于性别验证）
                user_a = User.query.get(user_a_id)
                if not user_a:
                    raise ValueError(f"用户A（ID:{user_a_id}）不存在")
                
                user_b = User.query.get(user_b_id)
                if not user_b:
                    raise ValueError(f"用户B（ID:{user_b_id}）不存在")

                # 1. 获取双方当前住宿记录
                dorm_a = cls.query.filter_by(
                    user_id=user_a_id, 
                    status='active', 
                    check_out_date=None
                ).with_for_update().first()
                
                dorm_b = cls.query.filter_by(
                    user_id=user_b_id, 
                    status='active', 
                    check_out_date=None
                ).with_for_update().first()

                if not dorm_a:
                    raise ValueError(f"用户{user_a_id}无有效住宿记录")
                if not dorm_b:
                    raise ValueError(f"用户{user_b_id}无有效住宿记录")

                # 添加时间验证：确保换宿时间不小于双方前宿舍入住时间
                if exchange_date < dorm_a.check_in_date:
                    raise ValueError(f"换宿时间({exchange_date.strftime('%Y-%m-%d')})不能小于用户A当前宿舍入住时间({dorm_a.check_in_date.strftime('%Y-%m-%d')})")
                if exchange_date < dorm_b.check_in_date:
                    raise ValueError(f"换宿时间({exchange_date.strftime('%Y-%m-%d')})不能小于用户B当前宿舍入住时间({dorm_b.check_in_date.strftime('%Y-%m-%d')})")

                # 2. 获取双方房间信息并拼接完整编号
                room_a = Room.query.get(dorm_a.room_id)
                room_b = Room.query.get(dorm_b.room_id)
                
                if not room_a:
                    raise ValueError(f"用户A的房间{ dorm_a.room_id }不存在")
                if not room_b:
                    raise ValueError(f"用户B的房间{ dorm_b.room_id }不存在")

                # 关键修复2：增加变量存在性检查，确保验证前变量已正确初始化
                if not user_a or not user_b or not room_a or not room_b:
                    raise RuntimeError("用户或房间信息获取不完整，无法进行性别验证")

                # 验证1：用户A的性别是否符合用户B原房间（room_b）的限制
                is_valid_a, error_msg_a = cls._validate_gender_match(
                    user_gender=user_a.gender,  # 传递用户A的性别
                    dorm_gender_restriction=room_b.gender_restriction  # 传递用户B房间的限制
                )
                if not is_valid_a:
                    raise ValueError(f"用户A无法换入用户B的房间：{error_msg_a}")

                # 验证2：用户B的性别是否符合用户A原房间（room_a）的限制
                is_valid_b, error_msg_b = cls._validate_gender_match(
                    user_gender=user_b.gender,  # 传递用户B的性别
                    dorm_gender_restriction=room_a.gender_restriction  # 传递用户A房间的限制
                )
                if not is_valid_b:
                    raise ValueError(f"用户B无法换入用户A的房间：{error_msg_b}")
                

                # 保存原始住宿信息
                room_a_full = f"{room_a.building}{room_a.room_number}"
                room_b_full = f"{room_b.building}{room_b.room_number}"
                room_a_id = dorm_a.room_id
                room_b_id = dorm_b.room_id
                bed_a_id = dorm_a.bed_id
                bed_b_id = dorm_b.bed_id

                # 2. 同步双方房间状态
                cls._sync_room_status(room_a_id)
                cls._sync_room_status(room_b_id)

                # 3. 核心优化点：双方先执行退宿
                dorm_a.check_out(
                    check_out_date=exchange_date,  # 已改为datetime类型
                    remarks=f"与用户{user_b_id}互换至房间{room_b_full}，原因：{reason}"
                )
                dorm_b.check_out(
                    check_out_date=exchange_date,  # 已改为datetime类型
                    remarks=f"与用户{user_a_id}互换至房间{room_a_full}，原因：{reason}"
                )
                # 退宿后强制刷新
                db.session.expire_all()

                # 4. 验证双方原床位是否已释放
                bed_a = Bed.query.get(bed_a_id)
                bed_b = Bed.query.get(bed_b_id)
                if bed_a.status != 'available':
                    raise ValueError(f"用户A原床位{bed_a_id}未正常释放（当前状态：{bed_a.status}）")
                if bed_b.status != 'available':
                    raise ValueError(f"用户B原床位{bed_b_id}未正常释放（当前状态：{bed_b.status}）")

                # 5. 核心优化点：双方互换入住对方房间
                # create_allocation方法已经自动设置operator_user_id
                new_dorm_a = cls.create_allocation(
                    user_id=user_a_id,
                    room_id=room_b_id,
                    bed_id=bed_b_id,
                    check_in_date=exchange_date,  # 已改为datetime类型
                    remarks=f"与用户{user_b_id}互换，原房间{room_a_full}"
                )
                new_dorm_b = cls.create_allocation(
                    user_id=user_b_id,
                    room_id=room_a_id,
                    bed_id=bed_a_id,
                    check_in_date=exchange_date,  # 已改为datetime类型
                    remarks=f"与用户{user_a_id}互换，原房间{room_b_full}"
                )

                # 关联历史记录
                new_dorm_a.prev_dorm_id = dorm_a.id
                new_dorm_b.prev_dorm_id = dorm_b.id

                if not has_active_transaction:
                    db.session.commit()

            except Exception as e:
                if not has_active_transaction:
                    db.session.rollback()
                raise e

            # 互换成功后，记录双方的换宿链
            if new_dorm_a and new_dorm_b:
                chain_a = new_dorm_a.dorm_chain
                chain_b = new_dorm_b.dorm_chain
                logging.info(
                    f"用户A({user_a_id})互换后住宿链：{[d.id for d in chain_a]}，"
                    f"用户B({user_b_id})互换后住宿链：{[d.id for d in chain_b]}"
                )


            return (new_dorm_a, new_dorm_b)

        except ValueError as e:
            logging.error(f"互换异常: {str(e)}\n{traceback.format_exc()}")
             # 关键修复4：异常场景下安全获取用户名
            raise e
        except Exception as e:
            logging.error(f"互换异常: {str(e)}\n{traceback.format_exc()}")
            # 关键修复5：错误日志中安全处理变量
            raise e
    