from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from utils.db import db
from models.dorm.dorm import Dorm
from models.dorm.dorm_application import DormApplication
from models.user.user import User
from models.room.room import Room
from models.room.room_bed import Bed
from models.utility.utility_room_meter import UtilityMeterReading
from models.utility.utility_room_bill_checkout import CheckoutUtilityRecord
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.log import log_operation
from utils.media.room_meter_checkout_photo import room_meter_checkout_photo_manager
from sqlalchemy.orm import joinedload
from datetime import datetime
import logging
from models.system_config.system_config import SystemConfig


# 创建宿舍申请用户端蓝图
dorm_application_user_bp = Blueprint('dorm_application_user', __name__, url_prefix='/user/dorm_application')


def generate_page_range(current_page, total_pages, show_pages=5):
    """生成分页页码范围"""
    if total_pages <= show_pages:
        return list(range(1, total_pages + 1))
    half = show_pages // 2
    start = max(1, current_page - half)
    end = min(total_pages, start + show_pages - 1)
    if end - start + 1 < show_pages:
        start = max(1, end - show_pages + 1)
    return list(range(start, end + 1))


def parse_datetime(date_str):
    """解析日期字符串，支持多种格式"""
    if not date_str:
        return None
    try:
        if 'T' in date_str:
            try:
                return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S')
            except ValueError:
                return datetime.strptime(date_str, '%Y-%m-%dT%H:%M')
        else:
            return datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return None


# 我的申请列表
@dorm_application_user_bp.route('/')
@login_required
@require_permission('dorm_application.view')
def application_list():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))

        # 确保用户ID为整数类型
        user_id = int(str(user_id))

        # 分页参数处理
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)

        # 获取筛选参数
        application_type = request.args.get('application_type', '').strip()
        status = request.args.get('status', '').strip()

        # 查询当前用户的申请
        query = DormApplication.query.filter_by(user_id=user_id).options(
            joinedload(DormApplication.target_room),
            joinedload(DormApplication.current_room)
        )

        # 处理申请类型筛选
        if application_type:
            query = query.filter_by(application_type=application_type)

        # 处理状态筛选
        if status:
            query = query.filter_by(status=status)

        # 排序和分页
        pagination = query.order_by(DormApplication.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        applications = pagination.items

        # 分页范围
        page_range = generate_page_range(page, pagination.pages)

        # 检查用户是否有活跃住宿记录
        has_active_dorm = Dorm.query.filter_by(user_id=user_id, status='active').first() is not None

        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 [{user_id}] 访问宿舍申请列表",
            result="成功",
            module="dorm_application",
            operation_type="records"
        )
        logging.info(f"用户 [{user_id}] 成功访问宿舍申请列表")
        return render_template('dorm_manage/application_user_list.html',
                              title="我的宿舍申请",
                              applications=applications, pagination=pagination,
                              page=page, per_page=per_page, page_range=page_range,
                              application_type_filter=application_type, status_filter=status,
                              has_active_dorm=has_active_dorm)
    except Exception as e:
        logging.error(f"获取宿舍申请列表失败: {str(e)}")
        flash('获取宿舍申请列表失败，请稍后重试', 'error')
        return redirect(url_for('index'))


# 申请宿舍
@dorm_application_user_bp.route('/create_allocate', methods=['GET', 'POST'])
@login_required
@require_permission('dorm_application.create')
def create_allocate():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))

        # 确保用户ID为整数类型
        user_id = int(str(user_id))

        if request.method == 'GET':
            # 检查用户是否已有活跃住宿记录
            active_dorm = Dorm.query.filter_by(user_id=user_id, status='active').first()
            if active_dorm:
                flash('您已有活跃的住宿记录，无法申请宿舍', 'warning')
                return redirect(url_for('dorm_application_user.application_list'))

            # 检查是否有待审核的申请
            pending_app = DormApplication.query.filter_by(user_id=user_id, status='pending').first()
            if pending_app:
                type_map = {'allocate': '申请宿舍', 'change': '申请换宿', 'checkout': '申请退宿'}
                flash(f'您已有一份待审核的{type_map.get(pending_app.application_type, "")}申请（编号:{pending_app.application_number}），请勿重复申请', 'warning')
                return redirect(url_for('dorm_application_user.application_list'))

            # 获取用户信息（用于性别过滤）
            user = User.query.get(user_id)

            # 从Room模型查询去重后的筛选条件数据
            buildings = db.session.query(Room.building).distinct().order_by(Room.building).all()
            building_list = [b[0] for b in buildings if b[0]]

            logging.info(f"用户 [{user_id}] 访问申请宿舍页面")
            # 生成默认日期时间（当前时间，精确到分钟）
            default_datetime = datetime.now().strftime('%Y-%m-%dT%H:%M')
            return render_template('dorm_manage/application_create.html',
                                  title="申请宿舍",
                                  application_type='allocate',
                                  user=user,
                                  active_dorm=None,
                                  default_datetime=default_datetime,
                                  building_list=building_list)

        # POST请求 - 创建申请
        target_room_id = request.form.get('target_room_id', type=int)
        target_bed_id = request.form.get('target_bed_id', type=int)
        if target_bed_id and not SystemConfig.get_config_value('USER_BED_SELECTION_ENABLED', True):
            target_bed_id = None
        check_in_date_str = request.form.get('check_in_date', '').strip()
        reason = request.form.get('reason', '').strip()

        # 验证必填字段
        if not target_room_id or not check_in_date_str or not reason:
            logging.warning(f"用户 {user_id} 申请宿舍参数不完整")
            flash('请填写所有必填字段（目标房间、入住日期、申请原因）', 'error')
            return redirect(url_for('dorm_application_user.create_allocate'))

        # 解析日期
        check_in_date = parse_datetime(check_in_date_str)
        if not check_in_date:
            flash('日期格式不正确，请使用YYYY-MM-DD或YYYY-MM-DDTHH:MM格式', 'error')
            return redirect(url_for('dorm_application_user.create_allocate'))

        # 创建申请
        application = DormApplication.create_application(
            user_id=user_id,
            application_type='allocate',
            target_room_id=target_room_id,
            target_bed_id=target_bed_id,
            check_in_date=check_in_date,
            reason=reason
        )

        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 {user_id} 申请宿舍成功，申请编号: {application.application_number}",
            result="成功",
            module="dorm_application",
            operation_type="create"
        )

        flash(f'宿舍申请提交成功，申请编号: {application.application_number}', 'success')
        return redirect(url_for('dorm_application_user.application_list'))
    except ValueError as e:
        db.session.rollback()
        logging.warning(f"用户申请宿舍验证失败: {str(e)}")
        flash(str(e), 'error')
        return redirect(url_for('dorm_application_user.create_allocate'))
    except Exception as e:
        db.session.rollback()
        logging.error(f"申请宿舍失败: {str(e)}")
        flash('申请宿舍失败，请稍后重试', 'error')
        return redirect(url_for('dorm_application_user.create_allocate'))


# 申请换宿
@dorm_application_user_bp.route('/create_change', methods=['GET', 'POST'])
@login_required
@require_permission('dorm_application.create')
def create_change():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))

        # 确保用户ID为整数类型
        user_id = int(str(user_id))

        # 获取用户当前活跃住宿记录
        active_dorm = Dorm.query.filter_by(user_id=user_id, status='active').first()

        if request.method == 'GET':
            if not active_dorm:
                flash('您当前没有活跃的住宿记录，无法申请换宿', 'warning')
                return redirect(url_for('dorm_application_user.application_list'))

            # 检查是否有待审核的申请
            pending_app = DormApplication.query.filter_by(user_id=user_id, status='pending').first()
            if pending_app:
                type_map = {'allocate': '申请宿舍', 'change': '申请换宿', 'checkout': '申请退宿'}
                flash(f'您已有一份待审核的{type_map.get(pending_app.application_type, "")}申请（编号:{pending_app.application_number}），请勿重复申请', 'warning')
                return redirect(url_for('dorm_application_user.application_list'))

            # 获取当前房间信息
            current_room = Room.query.get(active_dorm.room_id) if active_dorm.room_id else None
            current_bed = Bed.query.get(active_dorm.bed_id) if active_dorm.bed_id else None

            # 获取用户信息（用于性别过滤）
            user = User.query.get(user_id)

            # 从Room模型查询去重后的筛选条件数据
            buildings = db.session.query(Room.building).distinct().order_by(Room.building).all()
            building_list = [b[0] for b in buildings if b[0]]

            logging.info(f"用户 [{user_id}] 访问申请换宿页面")
            # 生成默认日期时间（当前时间，精确到分钟）
            default_datetime = datetime.now().strftime('%Y-%m-%dT%H:%M')
            # 计算已住天数
            stay_days = 0
            if active_dorm and active_dorm.check_in_date:
                check_in = active_dorm.check_in_date.date() if hasattr(active_dorm.check_in_date, 'date') else active_dorm.check_in_date
                today = datetime.now().date()
                stay_days = max(0, (today - check_in).days + 1)
            return render_template('dorm_manage/application_create.html',
                                  title="申请换宿",
                                  application_type='change',
                                  user=user,
                                  active_dorm=active_dorm,
                                  current_room=current_room,
                                  current_bed=current_bed,
                                  default_datetime=default_datetime,
                                  building_list=building_list,
                                  stay_days=stay_days)

        # POST请求 - 创建换宿申请
        target_room_id = request.form.get('target_room_id', type=int)
        target_bed_id = request.form.get('target_bed_id', type=int)
        if target_bed_id and not SystemConfig.get_config_value('USER_BED_SELECTION_ENABLED', True):
            target_bed_id = None
        check_in_date_str = request.form.get('check_in_date', '').strip()
        reason = request.form.get('reason', '').strip()

        # 验证必填字段
        if not target_room_id or not check_in_date_str or not reason:
            logging.warning(f"用户 {user_id} 申请换宿参数不完整")
            flash('请填写所有必填字段（目标房间、入住日期、申请原因）', 'error')
            return redirect(url_for('dorm_application_user.create_change'))

        # 解析日期
        check_in_date = parse_datetime(check_in_date_str)
        if not check_in_date:
            flash('日期格式不正确，请使用YYYY-MM-DD或YYYY-MM-DDTHH:MM格式', 'error')
            return redirect(url_for('dorm_application_user.create_change'))

        # 创建换宿申请（current_room_id和current_bed_id由模型自动填充）
        application = DormApplication.create_application(
            user_id=user_id,
            application_type='change',
            current_room_id=active_dorm.room_id if active_dorm else None,
            current_bed_id=active_dorm.bed_id if active_dorm else None,
            target_room_id=target_room_id,
            target_bed_id=target_bed_id,
            check_in_date=check_in_date,
            reason=reason
        )

        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 {user_id} 申请换宿成功，申请编号: {application.application_number}",
            result="成功",
            module="dorm_application",
            operation_type="create"
        )

        flash(f'换宿申请提交成功，申请编号: {application.application_number}', 'success')
        return redirect(url_for('dorm_application_user.application_list'))
    except ValueError as e:
        db.session.rollback()
        logging.warning(f"用户申请换宿验证失败: {str(e)}")
        flash(str(e), 'error')
        return redirect(url_for('dorm_application_user.create_change'))
    except Exception as e:
        db.session.rollback()
        logging.error(f"申请换宿失败: {str(e)}")
        flash('申请换宿失败，请稍后重试', 'error')
        return redirect(url_for('dorm_application_user.create_change'))


# 申请退宿
@dorm_application_user_bp.route('/create_checkout', methods=['GET', 'POST'])
@login_required
@require_permission('dorm_application.create')
def create_checkout():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))

        # 确保用户ID为整数类型
        user_id = int(str(user_id))

        # 获取用户当前活跃住宿记录
        active_dorm = Dorm.query.filter_by(user_id=user_id, status='active').first()

        if request.method == 'GET':
            if not active_dorm:
                flash('您当前没有活跃的住宿记录，无法申请退宿', 'warning')
                return redirect(url_for('dorm_application_user.application_list'))

            # 检查是否有待审核的申请
            pending_app = DormApplication.query.filter_by(user_id=user_id, status='pending').first()
            if pending_app:
                type_map = {'allocate': '申请宿舍', 'change': '申请换宿', 'checkout': '申请退宿'}
                flash(f'您已有一份待审核的{type_map.get(pending_app.application_type, "")}申请（编号:{pending_app.application_number}），请勿重复申请', 'warning')
                return redirect(url_for('dorm_application_user.application_list'))

            # 获取当前房间信息
            current_room = Room.query.get(active_dorm.room_id) if active_dorm.room_id else None
            current_bed = Bed.query.get(active_dorm.bed_id) if active_dorm.bed_id else None

            # 获取用户信息
            user = User.query.get(user_id)

            # 获取上次水电表读数
            last_water_reading = None
            last_electric_reading = None
            if active_dorm and active_dorm.room_id:
                latest_water = UtilityMeterReading.get_latest_water_reading(active_dorm.room_id, before_date=datetime.now())
                latest_electric = UtilityMeterReading.get_latest_electric_reading(active_dorm.room_id, before_date=datetime.now())
                if latest_water and latest_water.water_current is not None:
                    last_water_reading = {
                        'value': float(latest_water.water_current),
                        'date': latest_water.reading_date.strftime('%Y-%m-%d %H:%M:%S')
                    }
                if latest_electric and latest_electric.electric_current is not None:
                    last_electric_reading = {
                        'value': float(latest_electric.electric_current),
                        'date': latest_electric.reading_date.strftime('%Y-%m-%d %H:%M:%S')
                    }

            logging.info(f"用户 [{user_id}] 访问申请退宿页面")
            # 生成默认日期时间（当前时间，精确到分钟）
            default_datetime = datetime.now().strftime('%Y-%m-%dT%H:%M')
            # 计算已住天数
            stay_days = 0
            if active_dorm and active_dorm.check_in_date:
                check_in = active_dorm.check_in_date.date() if hasattr(active_dorm.check_in_date, 'date') else active_dorm.check_in_date
                today = datetime.now().date()
                stay_days = max(0, (today - check_in).days + 1)
            return render_template('dorm_manage/application_create.html',
                                  title="申请退宿",
                                  application_type='checkout',
                                  user=user,
                                  active_dorm=active_dorm,
                                  current_room=current_room,
                                  current_bed=current_bed,
                                  default_datetime=default_datetime,
                                  stay_days=stay_days,
                                  last_water_reading=last_water_reading,
                                  last_electric_reading=last_electric_reading)

        # POST请求 - 创建退宿申请
        check_out_date_str = request.form.get('check_out_date', '').strip()
        reason = request.form.get('reason', '').strip()
        checkout_type = request.form.get('checkout_type', '在职退宿').strip()
        billing_period = request.form.get('billing_period', '').strip() or None
        water_current_str = request.form.get('water_current', '').strip()
        electric_current_str = request.form.get('electric_current', '').strip()

        # 验证必填字段
        if not check_out_date_str or not reason:
            logging.warning(f"用户 {user_id} 申请退宿参数不完整")
            flash('请填写所有必填字段（退宿日期、申请原因）', 'error')
            return redirect(url_for('dorm_application_user.create_checkout'))



        # 验证退宿类型
        valid_checkout_types = ('在职退宿', '离职退宿', '自离退宿')
        if checkout_type not in valid_checkout_types:
            checkout_type = '在职退宿'

        # 解析日期
        check_out_date = parse_datetime(check_out_date_str)
        if not check_out_date:
            flash('日期格式不正确，请使用YYYY-MM-DD或YYYY-MM-DDTHH:MM格式', 'error')
            return redirect(url_for('dorm_application_user.create_checkout'))

        # 解析水电表读数（可为空）
        water_current = None
        electric_current = None
        if water_current_str:
            try:
                water_current = float(water_current_str)
            except ValueError:
                flash('水表读数格式不正确，请输入数字', 'error')
                return redirect(url_for('dorm_application_user.create_checkout'))
        if electric_current_str:
            try:
                electric_current = float(electric_current_str)
            except ValueError:
                flash('电表读数格式不正确，请输入数字', 'error')
                return redirect(url_for('dorm_application_user.create_checkout'))

        # 创建退宿申请（current_room_id和current_bed_id由模型自动填充）
        application = DormApplication.create_application(
            user_id=user_id,
            application_type='checkout',
            current_room_id=active_dorm.room_id if active_dorm else None,
            current_bed_id=active_dorm.bed_id if active_dorm else None,
            check_out_date=check_out_date,
            reason=reason,
            checkout_type=checkout_type,
            billing_period=billing_period,
            water_current=water_current,
            electric_current=electric_current
        )

        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 {user_id} 申请退宿成功，申请编号: {application.application_number}",
            result="成功",
            module="dorm_application",
            operation_type="create"
        )

        flash(f'退宿申请提交成功，申请编号: {application.application_number}', 'success')
        return redirect(url_for('dorm_application_user.application_list'))
    except ValueError as e:
        db.session.rollback()
        logging.warning(f"用户申请退宿验证失败: {str(e)}")
        flash(str(e), 'error')
        return redirect(url_for('dorm_application_user.create_checkout'))
    except Exception as e:
        db.session.rollback()
        logging.error(f"申请退宿失败: {str(e)}")
        flash('申请退宿失败，请稍后重试', 'error')
        return redirect(url_for('dorm_application_user.create_checkout'))


# 申请详情
@dorm_application_user_bp.route('/detail/<int:id>')
@login_required
@require_permission('dorm_application.view')
def application_detail(id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))

        # 确保用户ID为整数类型
        user_id = int(str(user_id))

        # 获取申请
        application = DormApplication.query.options(
            joinedload(DormApplication.user),
            joinedload(DormApplication.current_room),
            joinedload(DormApplication.current_bed),
            joinedload(DormApplication.target_room),
            joinedload(DormApplication.target_bed),
            joinedload(DormApplication.reviewer),
            joinedload(DormApplication.result_dorm).joinedload(Dorm.room),
            joinedload(DormApplication.result_dorm).joinedload(Dorm.bed)
        ).get(id)

        # 检查权限
        if not application or application.user_id != user_id:
            logging.warning(f"用户 {user_id} 尝试查看不属于自己的宿舍申请 {id}")
            flash('无权查看此申请', 'error')
            return redirect(url_for('dorm_application_user.application_list'))

        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 [{user_id}] 查看宿舍申请详情，申请编号: {application.application_number}",
            result="成功",
            module="dorm_application",
            operation_type="records"
        )
        logging.info(f"用户 [{user_id}] 成功查看宿舍申请详情，申请ID: {id}")

        # 获取申请人住宿记录（用于显示入住时间和已住天数）
        # 退宿审核通过后active记录变为checked_out，需从result_dorm获取
        current_dorm = Dorm.query.filter_by(user_id=application.user_id, status='active').first()
        is_checked_out = False
        if not current_dorm and application.status == 'approved' and application.application_type == 'checkout' and application.result_dorm:
            current_dorm = application.result_dorm
            is_checked_out = True
        stay_days = 0
        if current_dorm and current_dorm.check_in_date:
            check_in = current_dorm.check_in_date.date() if hasattr(current_dorm.check_in_date, 'date') else current_dorm.check_in_date
            if is_checked_out and current_dorm.check_out_date:
                end_date = current_dorm.check_out_date.date() if hasattr(current_dorm.check_out_date, 'date') else current_dorm.check_out_date
            else:
                end_date = datetime.now().date()
            # 同日换宿：入住和退宿为同一天时不计天数
            stay_days = 0 if end_date == check_in else max(0, (end_date - check_in).days + 1)

        # 获取退宿费用核算记录（审核通过的退宿申请）
        checkout_fee_record = None
        checkout_billing_period = None
        if application.application_type == 'checkout' and application.status == 'approved' and application.user_id:
            checkout_fee_record = CheckoutUtilityRecord.query.filter_by(
                user_id=application.user_id
            ).order_by(CheckoutUtilityRecord.created_at.desc()).first()
            if checkout_fee_record and checkout_fee_record.record_id:
                from models.utility.utility_room_bill_record import RoomUtilityRecord
                main_record = RoomUtilityRecord.query.get(checkout_fee_record.record_id)
                if main_record:
                    checkout_billing_period = main_record.billing_period

        return render_template('dorm_manage/application_detail.html',
                              title="申请详情",
                              application=application,
                              current_dorm=current_dorm,
                              stay_days=stay_days,
                              is_checked_out=is_checked_out,
                              checkout_fee_record=checkout_fee_record,
                              checkout_billing_period=checkout_billing_period,
                               bed_management_enabled=SystemConfig.get_config_value('ROOM_BED_MANAGEMENT_ENABLED', True),
                               user_bed_selection_enabled=SystemConfig.get_config_value('USER_BED_SELECTION_ENABLED', True))
    except Exception as e:
        logging.error(f"查看宿舍申请详情失败: {str(e)}")
        flash('查看申请详情失败，请稍后重试', 'error')
        return redirect(url_for('dorm_application_user.application_list'))


# 取消申请
@dorm_application_user_bp.route('/cancel/<int:id>', methods=['POST'])
@login_required
@require_permission('dorm_application.cancel')
def cancel_application(id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))

        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        logging.debug(f"用户 {user_id} 取消宿舍申请 {id}")

        # 获取申请
        application = DormApplication.query.get(id)

        # 检查权限
        if not application:
            logging.warning(f"用户 {user_id} 尝试取消不存在的宿舍申请 {id}")
            flash('申请不存在', 'error')
            return redirect(url_for('dorm_application_user.application_list'))
        if application.user_id != user_id:
            logging.warning(f"用户 {user_id} 尝试取消不属于自己的宿舍申请 {id}")
            flash('无权操作此申请', 'error')
            return redirect(url_for('dorm_application_user.application_list'))

        # 检查状态
        if application.status != 'pending':
            flash(f'只有待审核状态的申请才能取消，当前状态为: {application.status}', 'error')
            return redirect(url_for('dorm_application_user.application_detail', id=id))

        # 取消申请
        application.cancel(user_id=user_id)

        # 退宿申请取消时清理临时抄表照片
        if application.application_type == 'checkout':
            try:
                room_meter_checkout_photo_manager.clear_user_temp_files(
                    application.current_room_id, application.user_id
                )
            except Exception as e:
                logging.warning(f"清理退宿临时抄表照片失败（申请{application.application_number}）: {str(e)}")

        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"用户 {user_id} 取消宿舍申请 {application.application_number}",
            result="成功",
            module="dorm_application",
            operation_type="cancel"
        )

        logging.info(f"用户 {user_id} 取消宿舍申请 {application.application_number}")
        flash('申请已取消', 'success')
        return redirect(url_for('dorm_application_user.application_list'))
    except ValueError as e:
        db.session.rollback()
        logging.warning(f"取消宿舍申请验证失败: {str(e)}")
        flash(str(e), 'error')
        return redirect(url_for('dorm_application_user.application_detail', id=id))
    except Exception as e:
        db.session.rollback()
        logging.error(f"取消宿舍申请失败: {str(e)}")
        flash('取消申请失败，请稍后重试', 'error')
        return redirect(url_for('dorm_application_user.application_detail', id=id))


