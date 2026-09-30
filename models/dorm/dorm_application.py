from utils.db import db
from datetime import datetime
import logging
import traceback
from models.room.room import Room
from models.room.room_bed import Bed
from models.user.user import User
from models.dorm.dorm import Dorm
from flask_login import current_user
from sqlalchemy.exc import IntegrityError


class DormApplication(db.Model):
    """宿舍申请模型（管理宿舍申请、换宿申请、退宿申请）"""
    __tablename__ = 'dorm_applications'

    # 核心字段
    id = db.Column(db.Integer, primary_key=True)
    application_number = db.Column(db.String(20), unique=True, nullable=False, comment='申请编号（如SQ20260929001）')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False, comment='申请人ID')
    application_type = db.Column(db.String(20), nullable=False, comment='申请类型：allocate/change/checkout')
    status = db.Column(db.String(20), default='pending', nullable=False, comment='状态：pending/approved/rejected/cancelled')

    # 当前住宿信息（换宿/退宿时填写）
    current_room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='RESTRICT'), nullable=True, comment='当前房间ID')
    current_bed_id = db.Column(db.Integer, db.ForeignKey('room_beds.id', ondelete='RESTRICT'), nullable=True, comment='当前床位ID')

    # 目标住宿信息（申请/换宿时填写）
    target_room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='RESTRICT'), nullable=True, comment='目标房间ID')
    target_bed_id = db.Column(db.Integer, db.ForeignKey('room_beds.id', ondelete='RESTRICT'), nullable=True, comment='目标床位ID（可空则自动分配）')

    # 申请信息
    reason = db.Column(db.String(500), nullable=True, comment='申请原因')
    check_in_date = db.Column(db.DateTime, nullable=True, comment='期望入住日期（申请/换宿时必填）')
    check_out_date = db.Column(db.DateTime, nullable=True, comment='期望退宿日期（退宿时必填）')

    # 退宿申请附加信息
    checkout_type = db.Column(db.String(20), nullable=True, comment='退宿类型：在职退宿/离职退宿/自离退宿')
    water_current = db.Column(db.Float, nullable=True, comment='退宿水表读数（m³，可为空）')
    electric_current = db.Column(db.Float, nullable=True, comment='退宿电表读数（kWh，可为空）')

    # 审核信息
    reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, comment='审核人ID')
    reviewed_at = db.Column(db.DateTime, nullable=True, comment='审核时间')
    review_remark = db.Column(db.String(500), nullable=True, comment='审核备注')

    # 审核结果关联
    result_dorm_id = db.Column(db.Integer, db.ForeignKey('dorms.id', ondelete='SET NULL'), nullable=True, comment='审核通过后关联的住宿记录ID')

    # 操作用户ID（不与user表关联，与现有Dorm模型一致）
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作用户ID（办理人）')

    # 时间记录字段
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 关系定义
    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('dorm_applications', lazy='dynamic'))
    current_room = db.relationship('Room', foreign_keys=[current_room_id])
    current_bed = db.relationship('Bed', foreign_keys=[current_bed_id])
    target_room = db.relationship('Room', foreign_keys=[target_room_id])
    target_bed = db.relationship('Bed', foreign_keys=[target_bed_id])
    reviewer = db.relationship('User', foreign_keys=[reviewer_id])
    result_dorm = db.relationship('Dorm', foreign_keys=[result_dorm_id])

    # 约束
    __table_args__ = (
        db.CheckConstraint(
            "application_type IN ('allocate', 'change', 'checkout')",
            name='check_application_type_valid'
        ),
        db.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name='check_application_status_valid'
        ),
        db.Index('idx_dorm_application_user_id', 'user_id'),
        db.Index('idx_dorm_application_status', 'status'),
        db.Index('idx_dorm_application_type', 'application_type'),
    )

    def __repr__(self):
        type_map = {'allocate': '申请宿舍', 'change': '申请换宿', 'checkout': '申请退宿'}
        type_text = type_map.get(self.application_type, self.application_type)
        return f"<宿舍申请 {self.application_number}（{type_text}）>"

    @classmethod
    def generate_application_number(cls):
        """生成申请编号，格式：SQ+日期+3位序号，如SQ20260929001
        
        使用重试机制防止并发时生成重复编号
        """
        today = datetime.now().strftime('%Y%m%d')
        prefix = f'SQ{today}'

        max_retries = 3
        for attempt in range(max_retries):
            # 查询当天已有的最大编号
            last_app = cls.query.filter(
                cls.application_number.like(f'{prefix}%')
            ).order_by(cls.application_number.desc()).first()

            if last_app:
                # 提取序号部分并+1
                last_seq = int(last_app.application_number[-3:])
                new_seq = last_seq + 1
            else:
                new_seq = 1

            application_number = f'{prefix}{new_seq:03d}'

            # 尝试验证编号唯一性（通过临时创建和回滚）
            try:
                # 检查编号是否已存在
                existing = cls.query.filter_by(application_number=application_number).first()
                if not existing:
                    return application_number
                # 编号已存在，重试
                logging.warning(f"申请编号{application_number}已存在，重试生成（第{attempt + 1}次）")
            except IntegrityError:
                db.session.rollback()
                logging.warning(f"申请编号{application_number}并发冲突，重试生成（第{attempt + 1}次）")

        # 最后一次直接返回（让数据库约束在commit时捕获）
        return application_number

    @classmethod
    def create_application(cls, user_id, application_type, **kwargs):
        """创建宿舍申请，包含验证逻辑

        Args:
            user_id: 申请人ID
            application_type: 申请类型 allocate/change/checkout
            **kwargs: 可选参数（target_room_id, target_bed_id, reason, check_in_date, check_out_date）

        Returns:
            DormApplication: 创建的申请对象

        Raises:
            ValueError: 验证失败时抛出
        """
        # 验证申请类型
        valid_types = ('allocate', 'change', 'checkout')
        if application_type not in valid_types:
            raise ValueError(f"无效的申请类型：{application_type}，应为 {valid_types}")

        # 验证用户存在且状态为在职
        user = User.query.get(user_id)
        if not user:
            raise ValueError(f"用户ID:{user_id}不存在")
        if not user.is_status:
            raise ValueError(f"用户ID:{user_id}状态非在职，无法申请")

        # 验证用户不是超级管理员
        if user.user_role and user.user_role.code == 'super_admin':
            raise ValueError("超级管理员无需申请宿舍")

        # 获取用户当前活跃住宿记录
        active_dorm = Dorm.query.filter(
            Dorm.user_id == user_id,
            Dorm.status == 'active'
        ).first()

        # 根据申请类型验证
        if application_type == 'allocate':
            # 申请宿舍：验证用户无活跃住宿记录
            if active_dorm:
                raise ValueError(f"用户已有活跃住宿记录（房间ID:{active_dorm.room_id}），无法重复申请")
        elif application_type in ('change', 'checkout'):
            # 换宿/退宿：验证用户有活跃住宿记录
            if not active_dorm:
                raise ValueError(f"用户无活跃住宿记录，无法申请{'换宿' if application_type == 'change' else '退宿'}")

        # 验证用户无pending状态的申请（一个用户不应同时有待审核的申请）
        pending_app = cls.query.filter(
            cls.user_id == user_id,
            cls.status == 'pending'
        ).first()
        if pending_app:
            type_map = {'allocate': '申请宿舍', 'change': '申请换宿', 'checkout': '申请退宿'}
            raise ValueError(f"用户已有一份待审核的{type_map.get(pending_app.application_type, pending_app.application_type)}申请（编号:{pending_app.application_number}），请勿重复申请")

        # 自动填充current_room_id和current_bed_id（换宿/退宿时）
        current_room_id = kwargs.get('current_room_id')
        current_bed_id = kwargs.get('current_bed_id')
        if application_type in ('change', 'checkout') and active_dorm:
            if not current_room_id:
                current_room_id = active_dorm.room_id
            if not current_bed_id:
                current_bed_id = active_dorm.bed_id

        # 生成申请编号
        application_number = cls.generate_application_number()

        # 创建申请记录
        application = cls(
            application_number=application_number,
            user_id=user_id,
            application_type=application_type,
            status='pending',
            current_room_id=current_room_id,
            current_bed_id=current_bed_id,
            target_room_id=kwargs.get('target_room_id'),
            target_bed_id=kwargs.get('target_bed_id'),
            reason=kwargs.get('reason'),
            check_in_date=kwargs.get('check_in_date'),
            check_out_date=kwargs.get('check_out_date'),
            checkout_type=kwargs.get('checkout_type'),
            water_current=kwargs.get('water_current'),
            electric_current=kwargs.get('electric_current'),
            operator_user_id=current_user.id if current_user.is_authenticated else None
        )

        db.session.add(application)
        db.session.commit()
        return application

    def approve(self, reviewer_id, check_in_date=None, check_out_date=None,
                assigned_room_id=None, review_remark=None,
                checkout_type=None, water_current=None, electric_current=None):
        """审核通过申请，调用现有Dorm方法执行对应操作

        Args:
            reviewer_id: 审核人ID
            check_in_date: 入住日期（申请/换宿时使用）
            check_out_date: 退宿日期（退宿时使用）
            assigned_room_id: 实际分配房间ID（申请/换宿时使用，不修改申请人填写的目标房间）
            review_remark: 审核备注
            checkout_type: 退宿类型（退宿时使用：在职退宿/离职退宿/自离退宿）
            water_current: 水表读数（退宿时使用，可为空）
            electric_current: 电表读数（退宿时使用，可为空）

        Raises:
            ValueError: 验证失败时抛出
        """
        # 延迟导入避免循环依赖（models -> blueprints -> models）
        from blueprints.dorm.dorm_service import do_allocation, do_change, do_checkout

        if self.status != 'pending':
            raise ValueError(f"申请状态为{self.status}，只有pending状态可审核通过")

        try:
            try:
                # 使用行级锁防止并发
                app = DormApplication.query.filter_by(id=self.id).with_for_update().first()

                # 二次检查状态（防止并发审核）
                if app.status != 'pending':
                    raise ValueError(f"申请已被处理，当前状态为{app.status}")

                # 更新审核信息
                app.status = 'approved'
                app.reviewer_id = reviewer_id
                app.reviewed_at = datetime.now()
                app.review_remark = review_remark
                app.operator_user_id = current_user.id if current_user.is_authenticated else None

                # 确定实际分配的房间（不修改申请人填写的目标房间信息）
                room_id_for_allocation = assigned_room_id or app.target_room_id

                # 获取用户当前活跃住宿记录
                active_dorm = Dorm.query.filter(
                    Dorm.user_id == app.user_id,
                    Dorm.status == 'active'
                ).first()

                operator_id = current_user.id if current_user.is_authenticated else None

                if app.application_type == 'allocate':
                    # 申请宿舍：分配 + 禁用外宿/住宿补贴 + 清零补贴金额
                    if not room_id_for_allocation:
                        raise ValueError("申请宿舍需要指定目标房间")
                    if not check_in_date:
                        check_in_date = app.check_in_date or datetime.now()

                    # 确定目标床位（自动分配可用床位）
                    available_bed = Bed.query.filter_by(
                        room_id=room_id_for_allocation,
                        status='available'
                    ).with_for_update().first()
                    if not available_bed:
                        raise ValueError("分配房间无可用床位")

                    allocation_result = do_allocation(
                        user_id=app.user_id,
                        room_id=room_id_for_allocation,
                        bed_id=available_bed.id,
                        check_in_date=check_in_date,
                        operator_id=operator_id,
                        remarks=f"通过申请{app.application_number}分配"
                    )
                    app.result_dorm_id = allocation_result['new_dorm'].id

                elif app.application_type == 'change':
                    # 申请换宿：用户/房间验证 + 模型层换宿
                    if not room_id_for_allocation:
                        raise ValueError("申请换宿需要指定目标房间")
                    if not active_dorm:
                        raise ValueError(f"用户{app.user_id}无活跃住宿记录，无法换宿")
                    if not check_in_date:
                        check_in_date = app.check_in_date or datetime.now()

                    change_result = do_change(
                        user_id=app.user_id,
                        target_room_id=room_id_for_allocation,
                        reason=f"通过申请{app.application_number}换宿：{app.reason or '无'}",
                        change_date=check_in_date,
                        operator_id=operator_id
                    )
                    app.result_dorm_id = change_result['new_dorm'].id

                elif app.application_type == 'checkout':
                    # 申请退宿：退宿 + 禁用补贴 + 更新用户状态 + 水电抄表 + 费用计算
                    if not active_dorm:
                        raise ValueError(f"用户{app.user_id}无活跃住宿记录，无法退宿")
                    if not check_out_date:
                        check_out_date = app.check_out_date or datetime.now()

                    # 退宿类型：优先使用审核人确认的，否则使用申请人填写的，默认在职退宿
                    effective_checkout_type = checkout_type or app.checkout_type or '在职退宿'
                    # 水电表读数：优先使用审核人确认的，否则使用申请人填写的
                    effective_water = water_current if water_current is not None else app.water_current
                    effective_electric = electric_current if electric_current is not None else app.electric_current

                    checkout_result = do_checkout(
                        user_id=app.user_id,
                        check_out_date=check_out_date,
                        checkout_type=effective_checkout_type,
                        water_current=effective_water,
                        electric_current=effective_electric,
                        operator_id=operator_id,
                        remarks=f"通过申请{app.application_number}退宿：{app.reason or '无'}"
                    )
                    app.result_dorm_id = checkout_result['dorm'].id

                db.session.commit()

                # 刷新当前对象
                db.session.refresh(self)
                return self

            except Exception as e:
                db.session.rollback()
                raise e

        except ValueError as e:
            logging.error(f"宿舍申请审核业务验证失败：{str(e)}\n{traceback.format_exc()}")
            raise e
        except Exception as e:
            logging.error(f"宿舍申请审核系统异常：{str(e)}\n{traceback.format_exc()}")
            raise e

    def reject(self, reviewer_id, review_remark=None):
        """审核拒绝申请

        Args:
            reviewer_id: 审核人ID
            review_remark: 审核备注

        Raises:
            ValueError: 验证失败时抛出
        """
        if self.status != 'pending':
            raise ValueError(f"申请状态为{self.status}，只有pending状态可审核拒绝")

        # 使用行级锁防止并发
        application = DormApplication.query.filter_by(id=self.id).with_for_update().first()
        if not application or application.status != 'pending':
            raise ValueError(f"申请已被处理，当前状态为{application.status if application else 'unknown'}")

        application.status = 'rejected'
        application.reviewer_id = reviewer_id
        application.reviewed_at = datetime.now()
        application.review_remark = review_remark
        application.operator_user_id = current_user.id if current_user.is_authenticated else None

        db.session.add(application)
        db.session.commit()

        # 刷新当前对象
        db.session.refresh(self)
        return self

    def cancel(self, user_id=None, is_admin=False):
        """取消申请（仅pending状态可取消）

        Args:
            user_id: 取消操作的用户ID，用于验证是否为申请人
            is_admin: 管理员取消时跳过申请人验证

        Raises:
            ValueError: 验证失败时抛出
        """
        if not is_admin and user_id is not None and user_id != self.user_id:
            raise ValueError("只能取消自己的申请")

        if self.status != 'pending':
            raise ValueError(f"申请状态为{self.status}，只有pending状态可取消")

        # 使用行级锁防止并发
        application = DormApplication.query.filter_by(id=self.id).with_for_update().first()
        if not application or application.status != 'pending':
            raise ValueError(f"申请已被处理，当前状态为{application.status if application else 'unknown'}")

        application.status = 'cancelled'
        application.operator_user_id = current_user.id if current_user.is_authenticated else None

        db.session.add(application)
        db.session.commit()

        # 刷新当前对象
        db.session.refresh(self)
        return self