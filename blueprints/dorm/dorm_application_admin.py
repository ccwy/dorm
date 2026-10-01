from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from utils.db import db
from models.dorm.dorm_application import DormApplication
from models.dorm.dorm import Dorm
from models.user.user import User
from models.room.room import Room, RoomStatus
from models.utility.utility_room_meter import UtilityMeterReading
from models.utility.utility_room_bill_checkout import CheckoutUtilityRecord
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.log import log_operation
from sqlalchemy.orm import joinedload
from sqlalchemy import or_
from datetime import datetime
import logging


# 创建宿舍申请管理端蓝图
dorm_application_admin_bp = Blueprint('dorm_application_admin', __name__, url_prefix='/admin/dorm_application')


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


# 申请管理列表页
@dorm_application_admin_bp.route('/')
@login_required
@require_permission('dorm_application.manage')
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
        per_page = request.args.get('per_page', 20, type=int)

        # 获取筛选参数
        application_type = request.args.get('application_type', '').strip()
        status = request.args.get('status', '').strip()
        search = request.args.get('search', '').strip()

        # 查询所有申请（管理端可查看所有）
        query = DormApplication.query.options(
            joinedload(DormApplication.user),
            joinedload(DormApplication.current_room),
            joinedload(DormApplication.target_room),
            joinedload(DormApplication.reviewer)
        )

        # 处理申请类型筛选
        if application_type:
            query = query.filter_by(application_type=application_type)

        # 处理状态筛选
        if status:
            query = query.filter_by(status=status)

        # 处理关键字搜索（用户名/申请编号）
        if search:
            query = query.join(User, DormApplication.user_id == User.id).filter(
                or_(
                    User.name.like(f'%{search}%'),
                    DormApplication.application_number.like(f'%{search}%')
                )
            )

        # 排序和分页
        pagination = query.order_by(DormApplication.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        applications = pagination.items

        # 分页范围
        page_range = generate_page_range(page, pagination.pages)

        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员 [{user_id}] 访问宿舍申请管理列表",
            result="成功",
            module="dorm_application",
            operation_type="records"
        )
        logging.info(f"管理员 [{user_id}] 成功访问宿舍申请管理列表")
        return render_template('dorm_manage/application_admin_list.html',
                              title="宿舍申请管理",
                              applications=applications, pagination=pagination,
                              page=page, per_page=per_page, page_range=page_range,
                              application_type_filter=application_type, status_filter=status,
                              search_query=search)
    except Exception as e:
        logging.error(f"获取宿舍申请管理列表失败: {str(e)}")
        flash('获取宿舍申请管理列表失败，请稍后重试', 'error')
        return redirect(url_for('index'))


# 审核详情页
@dorm_application_admin_bp.route('/detail/<int:id>')
@login_required
@require_permission('dorm_application.manage')
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

        if not application:
            logging.warning(f"管理员 {user_id} 尝试查看不存在的宿舍申请 {id}")
            flash('申请不存在', 'error')
            return redirect(url_for('dorm_application_admin.application_list'))

        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员 {user_id} 查看宿舍申请详情，申请编号: {application.application_number}",
            result="成功",
            module="dorm_application",
            operation_type="records"
        )
        logging.info(f"管理员 [{user_id}] 成功查看宿舍申请详情，申请ID: {id}")

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

        # 获取上次水电表读数（退宿申请时显示）
        last_water_reading = None
        last_electric_reading = None
        if application.application_type == 'checkout' and current_dorm and current_dorm.room_id:
            latest_water = UtilityMeterReading.get_latest_water_reading(current_dorm.room_id)
            latest_electric = UtilityMeterReading.get_latest_electric_reading(current_dorm.room_id)
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

        return render_template('dorm_manage/application_admin_detail.html',
                              title="审核详情",
                              application=application,
                              current_dorm=current_dorm,
                              stay_days=stay_days,
                              is_checked_out=is_checked_out,
                              last_water_reading=last_water_reading,
                              last_electric_reading=last_electric_reading,
                              checkout_fee_record=checkout_fee_record,
                              checkout_billing_period=checkout_billing_period,
                              building_list=Room.query.with_entities(Room.building).distinct().order_by(Room.building).all(),
                              room_type_list=Room.get_valid_room_types(),
                              room_level_list=Room.get_valid_room_levels())
    except Exception as e:
        logging.error(f"查看宿舍申请详情失败: {str(e)}")
        flash('查看申请详情失败，请稍后重试', 'error')
        return redirect(url_for('dorm_application_admin.application_list'))


# 审核通过
@dorm_application_admin_bp.route('/approve/<int:id>', methods=['POST'])
@login_required
@require_permission('dorm_application.approve')
def approve_application(id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))

        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        logging.debug(f"管理员 {user_id} 审核通过宿舍申请 {id}")

        # 获取申请
        application = DormApplication.query.get(id)

        if not application:
            logging.warning(f"管理员 {user_id} 尝试审核不存在的宿舍申请 {id}")
            flash('申请不存在', 'error')
            return redirect(url_for('dorm_application_admin.application_list'))

        # 检查状态
        if application.status != 'pending':
            flash(f'只有待审核状态的申请才能审核通过，当前状态为: {application.status}', 'error')
            return redirect(url_for('dorm_application_admin.application_detail', id=id))

        # 获取表单参数（assigned_room_id为实际分配房间，不修改申请人填写的目标房间）
        assigned_room_id = request.form.get('assigned_room_id', type=int)
        check_in_date_str = request.form.get('check_in_date', '').strip()
        check_out_date_str = request.form.get('check_out_date', '').strip()
        review_remark = request.form.get('review_remark', '').strip()

        # 退宿相关参数
        checkout_type = request.form.get('checkout_type', '').strip()
        billing_period = request.form.get('billing_period', '').strip()
        water_current_str = request.form.get('water_current', '').strip()
        electric_current_str = request.form.get('electric_current', '').strip()

        # 解析日期
        check_in_date = parse_datetime(check_in_date_str) if check_in_date_str else None
        check_out_date = parse_datetime(check_out_date_str) if check_out_date_str else None

        # 解析水电表读数（可为空）
        water_current = float(water_current_str) if water_current_str else None
        electric_current = float(electric_current_str) if electric_current_str else None

        # 验证必填日期
        if application.application_type in ('allocate', 'change') and not check_in_date:
            flash('请填写确认入住日期', 'error')
            return redirect(url_for('dorm_application_admin.application_detail', id=id))

        if application.application_type == 'checkout' and not check_out_date:
            flash('请填写确认退宿日期', 'error')
            return redirect(url_for('dorm_application_admin.application_detail', id=id))

        # 构建退宿额外参数
        checkout_kwargs = {}
        if application.application_type == 'checkout':
            if checkout_type:
                checkout_kwargs['checkout_type'] = checkout_type
            if billing_period:
                checkout_kwargs['billing_period'] = billing_period
            if water_current is not None:
                checkout_kwargs['water_current'] = water_current
            if electric_current is not None:
                checkout_kwargs['electric_current'] = electric_current

        # 调用approve方法（床位自动分配，不修改申请人填写的目标房间信息）
        application.approve(
            reviewer_id=user_id,
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            assigned_room_id=assigned_room_id if assigned_room_id else None,
            review_remark=review_remark if review_remark else None,
            **checkout_kwargs
        )

        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员 {user_id} 审核通过宿舍申请 {application.application_number}",
            result="成功",
            module="dorm_application",
            operation_type="approve"
        )

        logging.info(f"管理员 {user_id} 审核通过宿舍申请 {application.application_number}")
        flash(f'申请 {application.application_number} 审核通过', 'success')
        return redirect(url_for('dorm_application_admin.application_list'))
    except ValueError as e:
        db.session.rollback()
        logging.warning(f"审核通过宿舍申请验证失败: {str(e)}")
        flash(str(e), 'error')
        return redirect(url_for('dorm_application_admin.application_detail', id=id))
    except Exception as e:
        logging.error(f"审核通过宿舍申请失败: {str(e)}")
        db.session.rollback()
        flash('审核通过失败，请稍后重试', 'error')
        return redirect(url_for('dorm_application_admin.application_detail', id=id))


# 审核拒绝
@dorm_application_admin_bp.route('/reject/<int:id>', methods=['POST'])
@login_required
@require_permission('dorm_application.approve')
def reject_application(id):
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            logging.error("用户ID为空")
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))

        # 确保用户ID为整数类型
        user_id = int(str(user_id))
        logging.debug(f"管理员 {user_id} 审核拒绝宿舍申请 {id}")

        # 获取申请
        application = DormApplication.query.get(id)

        if not application:
            logging.warning(f"管理员 {user_id} 尝试拒绝不存在的宿舍申请 {id}")
            flash('申请不存在', 'error')
            return redirect(url_for('dorm_application_admin.application_list'))

        # 检查状态
        if application.status != 'pending':
            flash(f'只有待审核状态的申请才能审核拒绝，当前状态为: {application.status}', 'error')
            return redirect(url_for('dorm_application_admin.application_detail', id=id))

        # 获取拒绝原因（必填）
        review_remark = request.form.get('review_remark', '').strip()
        if not review_remark:
            flash('请填写拒绝原因', 'error')
            return redirect(url_for('dorm_application_admin.application_detail', id=id))

        # 调用reject方法
        application.reject(
            reviewer_id=user_id,
            review_remark=review_remark
        )

        # 记录操作日志
        log_operation(
            user_id=user_id,
            action=f"管理员 {user_id} 审核拒绝宿舍申请 {application.application_number}",
            result="成功",
            module="dorm_application",
            operation_type="reject"
        )

        logging.info(f"管理员 {user_id} 审核拒绝宿舍申请 {application.application_number}")
        flash(f'申请 {application.application_number} 已拒绝', 'success')
        return redirect(url_for('dorm_application_admin.application_list'))
    except ValueError as e:
        db.session.rollback()
        logging.warning(f"审核拒绝宿舍申请验证失败: {str(e)}")
        flash(str(e), 'error')
        return redirect(url_for('dorm_application_admin.application_detail', id=id))
    except Exception as e:
        logging.error(f"审核拒绝宿舍申请失败: {str(e)}")
        db.session.rollback()
        flash('审核拒绝失败，请稍后重试', 'error')
        return redirect(url_for('dorm_application_admin.application_detail', id=id))


# 获取可调整的房间列表API
@dorm_application_admin_bp.route('/api/adjust_rooms')
@login_required
@require_permission('dorm_application.approve')
def api_adjust_rooms():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            return jsonify({'success': False, 'message': '用户信息无效'}), 401

        user_id = int(str(user_id))

        # 获取参数
        application_id = request.args.get('application_id', type=int)
        gender = request.args.get('gender', '').strip()

        if not application_id:
            return jsonify({'success': False, 'message': '缺少申请ID参数'}), 400

        # 获取申请信息
        application = DormApplication.query.get(application_id)
        if not application:
            return jsonify({'success': False, 'message': '申请不存在'}), 404

        # 查询可用房间：有空位且状态为available
        query = Room.query.filter(
            Room.status == RoomStatus.AVAILABLE.value,
            Room.current_occupancy < Room.capacity
        )

        # 根据性别过滤
        if gender and gender != '无限制':
            query = query.filter(
                or_(
                    Room.gender_restriction == gender,
                    Room.gender_restriction == '无限制'
                )
            )

        # 换宿时排除用户当前房间
        if application.application_type == 'change' and application.current_room_id:
            query = query.filter(Room.id != application.current_room_id)

        rooms = query.order_by(Room.building, Room.room_number).all()

        # 构建返回数据
        result = []
        for room in rooms:
            result.append({
                'id': room.id,
                'building': room.building,
                'room_number': room.room_number,
                'room_type': room.room_type,
                'capacity': room.capacity,
                'current_occupancy': room.current_occupancy,
                'gender_restriction': room.gender_restriction
            })

        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logging.error(f"获取可调整房间列表失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取可调整房间列表失败: {str(e)}'}), 500





# 删除申请
@dorm_application_admin_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('dorm_application.delete')
def delete_application(id):
    try:
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
        user_id = int(str(user_id))

        application = DormApplication.query.get(id)
        if not application:
            flash('申请不存在', 'error')
            return redirect(url_for('dorm_application_admin.application_list'))

        app_number = application.application_number
        db.session.delete(application)
        db.session.commit()

        log_operation(
            user_id=user_id,
            action=f"管理员 {user_id} 删除宿舍申请 {app_number}",
            result="成功",
            module="dorm_application",
            operation_type="delete"
        )
        logging.info(f"管理员 {user_id} 删除宿舍申请 {app_number}")
        flash(f'申请 {app_number} 已删除', 'success')
        return redirect(url_for('dorm_application_admin.application_list'))
    except Exception as e:
        db.session.rollback()
        logging.error(f"删除宿舍申请失败: {str(e)}")
        flash('删除申请失败，请稍后重试', 'error')
        return redirect(url_for('dorm_application_admin.application_list'))


# 批量删除申请
@dorm_application_admin_bp.route('/batch_delete', methods=['POST'])
@login_required
@require_permission('dorm_application.delete')
def batch_delete():
    try:
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            return jsonify({'success': False, 'message': '用户信息无效'}), 401
        user_id = int(str(user_id))

        ids = request.form.getlist('ids[]')
        if not ids:
            return jsonify({'success': False, 'message': '未选择要删除的申请'}), 400

        ids = [int(i) for i in ids]
        applications = DormApplication.query.filter(DormApplication.id.in_(ids)).all()

        if not applications:
            return jsonify({'success': False, 'message': '未找到选中的申请'}), 404

        count = len(applications)
        for app in applications:
            db.session.delete(app)
        db.session.commit()

        log_operation(
            user_id=user_id,
            action=f"管理员 {user_id} 批量删除 {count} 条宿舍申请",
            result="成功",
            module="dorm_application",
            operation_type="delete"
        )
        logging.info(f"管理员 {user_id} 批量删除 {count} 条宿舍申请")
        return jsonify({'success': True, 'message': f'成功删除 {count} 条申请'})
    except Exception as e:
        db.session.rollback()
        logging.error(f"批量删除宿舍申请失败: {str(e)}")
        return jsonify({'success': False, 'message': '批量删除失败，请稍后重试'}), 500


# 取消申请（管理员）
@dorm_application_admin_bp.route('/cancel/<int:id>', methods=['POST'])
@login_required
@require_permission('dorm_application.cancel')
def cancel_application(id):
    try:
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            flash('用户信息无效，请重新登录', 'error')
            return redirect(url_for('login.login'))
        user_id = int(str(user_id))

        application = DormApplication.query.get(id)
        if not application:
            flash('申请不存在', 'error')
            return redirect(url_for('dorm_application_admin.application_list'))

        if application.status != 'pending':
            flash(f'只有待审核状态的申请才能取消，当前状态为: {application.status}', 'error')
            return redirect(url_for('dorm_application_admin.application_detail', id=id))

        application.cancel(user_id=user_id, is_admin=True)

        log_operation(
            user_id=user_id,
            action=f"管理员 {user_id} 取消宿舍申请 {application.application_number}",
            result="成功",
            module="dorm_application",
            operation_type="cancel"
        )
        logging.info(f"管理员 {user_id} 取消宿舍申请 {application.application_number}")
        flash(f'申请 {application.application_number} 已取消', 'success')
        return redirect(url_for('dorm_application_admin.application_detail', id=id))
    except ValueError as e:
        db.session.rollback()
        flash(str(e), 'error')
        return redirect(url_for('dorm_application_admin.application_detail', id=id))
    except Exception as e:
        db.session.rollback()
        logging.error(f"取消宿舍申请失败: {str(e)}")
        flash('取消申请失败，请稍后重试', 'error')
        return redirect(url_for('dorm_application_admin.application_detail', id=id))


# 统计数据API
@dorm_application_admin_bp.route('/api/statistics')
@login_required
@require_permission('dorm_application.manage')
def api_statistics():
    try:
        # 验证用户ID是否有效
        user_id = current_user.id
        if not user_id or str(user_id).strip() == '':
            return jsonify({'success': False, 'message': '用户信息无效'}), 401

        user_id = int(str(user_id))

        # 统计各状态数量
        pending_count = DormApplication.query.filter_by(status='pending').count()
        approved_count = DormApplication.query.filter_by(status='approved').count()
        rejected_count = DormApplication.query.filter_by(status='rejected').count()
        cancelled_count = DormApplication.query.filter_by(status='cancelled').count()

        # 统计各类型数量
        allocate_count = DormApplication.query.filter_by(application_type='allocate').count()
        change_count = DormApplication.query.filter_by(application_type='change').count()
        checkout_count = DormApplication.query.filter_by(application_type='checkout').count()

        # 统计当天创建的申请数
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = DormApplication.query.filter(DormApplication.created_at >= today).count()

        return jsonify({
            'success': True,
            'data': {
                'pending_count': pending_count,
                'approved_count': approved_count,
                'rejected_count': rejected_count,
                'cancelled_count': cancelled_count,
                'allocate_count': allocate_count,
                'change_count': change_count,
                'checkout_count': checkout_count,
                'today_count': today_count
            }
        })
    except Exception as e:
        logging.error(f"获取宿舍申请统计数据失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取统计数据失败: {str(e)}'}), 500