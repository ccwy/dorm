from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
import logging
from models.utility.utility_room_bill_record import RoomUtilityRecord      #导入主表模型
from models.user.user import User  # 导入用户模型获取部门信息
from models.department.department import Department  # 导入部门模型
from models.room.room import Room  # 导入房间模型获取楼栋信息
from utils.db import db
from utils.log import log_operation

from utils.auth import require_permission
from models.utility.utility_room_bill_checkout import CheckoutUtilityRecord # 退宿费用子表
from models.utility.utility_room_bill_occupant import RoomUtilityOccupant # 在住人员费用分摊子表
from models.utility.utility_room_meter import UtilityMeterReading  # 抄表记录子表
from models.system_config.system_config import SystemConfig  # 系统配置
from models.dorm.dorm import Dorm  # 住宿记录模型（判断换宿）

# 蓝图定义，前缀设为'/utility'便于区分系统其他模块
utility_index_bp = Blueprint('utility_index', __name__, url_prefix='/utility')

@utility_index_bp.route('', methods=['GET'])
@login_required
@require_permission('utility.view')
def utility_home():
    """水电费管理系统首页（默认路由）"""
    try:
        # 记录页面访问日志
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"访问水电费管理首页",#这里记载成功与失败的记录
            result="成功"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_index.html', title=f"水电费管理")
    except Exception as e:
        logging.error(f"访问水电费管理首页失败: {str(e)}")
        flash(str(e), 'danger')
        return render_template('utility_bill/utility_index.html', title=f"水电费管理")

@utility_index_bp.route('/index', methods=['GET'])
@login_required
@require_permission('utility.view')
def utility_index():
    """冗余路由，确保通过/index也能访问首页（兼容前端可能的跳转）"""
    try:
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"通过/index访问水电费管理首页",#这里记载成功与失败的记录
            result="成功"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_index.html', title=f"水电费管理")
    except Exception as e:
        logging.error(f"通过/index访问首页失败: {str(e)}")
        flash(str(e), 'danger')
        return render_template('utility_bill/utility_index.html', title=f"水电费管理")


# 水电费核算页面
@utility_index_bp.route('/utility_room_records_bill', methods=['GET'])
@login_required
@require_permission('utility.view')
def utility_room_records_bill():
    """核算房间水电费页面（已修正模板文件名）"""
    try:
        billing_period = request.args.get('billing_period', '')
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"访问核算房间水电费页面",#这里记载成功与失败的记录
            result="成功"#这里只有成功与失败
        )
        rooms = Room.query.order_by(Room.building, Room.room_number).all()
        return render_template('utility_bill/utility_room_records_bill.html', title=f"核算房间水电费", billing_period=billing_period, rooms=rooms)
    except Exception as e:
        logging.error(f"访问核算房间水电费页面失败: {str(e)}")
        flash(str(e), 'danger')
        billing_period = request.args.get('billing_period', '')
        rooms = Room.query.order_by(Room.building, Room.room_number).all()
        return render_template('utility_bill/utility_room_records_bill.html', title=f"核算房间水电费", billing_period=billing_period, rooms=rooms)

@utility_index_bp.route('/utility_room_records_detail')
@login_required
@require_permission('utility.room_records_detail')
def utility_room_records_detail():
    """显示房间费用记录查询页面"""
    try:
        # 获取查询参数用于日志
        room_id = request.args.get('room_id', '未指定')
        billing_period = request.args.get('billing_period', '')
        
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"访问房间水电费查询页面 [房间ID: {room_id}, 账期: {billing_period}]",#这里记载成功与失败的记录
            result="成功"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_room_records_detail.html', title=f"房间水电费查询")
    except Exception as e:
        logging.error(f"访问房间水电费查询页面失败: {str(e)}")
        flash(str(e), 'danger')
        return render_template('utility_bill/utility_room_records_detail.html', title=f"房间水电费查询")

@utility_index_bp.route('/utility_room_checkout')
@login_required
@require_permission('utility.view')
def utility_room_checkout():
    """退宿人员费用查询页面"""
    try:
        # 获取查询参数用于日志
        checkout_date = request.args.get('date', '未指定')
        room_id = request.args.get('room_id', '未指定')
        billing_period = request.args.get('billing_period', '')
        
        # 获取所有部门信息（去重并排序）
        departments_list = [d.name for d in Department.query.filter_by(status='正常').order_by(Department.name).all()]
        
        # 获取所有楼栋信息（去重并排序）
        buildings = db.session.query(Room.building).distinct().filter(Room.building.isnot(None)).filter(Room.building != '').all()
        # 转换为列表格式并排序
        buildings_list = sorted([building[0] for building in buildings])
        
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"访问退宿人员费用查询页面 [房间ID: {room_id}, 退宿日期: {checkout_date}]",#这里记载成功与失败的记录
            result="成功"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_room_checkout.html', title=f"退宿人员费用查询", departments=departments_list, buildings=buildings_list, billing_period=billing_period)
    except Exception as e:
        logging.error(f"访问退宿人员费用查询页面失败: {str(e)}")
        # 即使出错也尝试获取部门和楼栋信息
        try:
            departments_list = [d.name for d in Department.query.filter_by(status='正常').order_by(Department.name).all()]
            buildings = db.session.query(Room.building).distinct().filter(Room.building.isnot(None)).filter(Room.building != '').all()
            buildings_list = sorted([building[0] for building in buildings])
        except Exception:
            departments_list = []
            buildings_list = []
            
        flash(str(e), 'danger')
        return render_template('utility_bill/utility_room_checkout.html', title=f"退宿人员费用查询", departments=departments_list, buildings=buildings_list, billing_period=billing_period)

@utility_index_bp.route('/utility_room_checkout_edit')
@login_required
@require_permission('utility.edit')
def utility_room_checkout_edit():
    """编辑退宿人员费用页面（服务端渲染）"""
    from datetime import datetime
    
    checkout_id = request.args.get('id', type=int)
    if not checkout_id:
        flash('参数错误，缺少退宿记录ID', 'danger')
        return redirect(url_for('utility_index.utility_home'))
    
    try:
        # 1. 获取子表记录
        checkout_record = CheckoutUtilityRecord.query.get(checkout_id)
        if not checkout_record:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='utility_api',
                action=f"查询退宿修改数据 [退宿记录ID: {checkout_id}]，退宿记录不存在",
                result="失败"
            )
            flash(f'退宿记录ID={checkout_id}不存在', 'danger')
            return redirect(url_for('utility_index.utility_home'))
        
        # 2. 获取关联的主表和房间信息
        main_record = RoomUtilityRecord.query.get(checkout_record.record_id)
        if not main_record:
            flash('关联的主账单记录不存在', 'danger')
            return redirect(url_for('utility_index.utility_home'))
        
        room = Room.query.get(main_record.room_id)
        if not room:
            flash('关联的房间不存在', 'danger')
            return redirect(url_for('utility_index.utility_home'))
        
        # 3. 获取用户和住宿记录信息
        dorm_record = None
        if checkout_record.dorm_id:
            dorm_record = Dorm.query.get(checkout_record.dorm_id)
        
        if not dorm_record:
            dorm_record = Dorm.query.filter_by(
                user_id=checkout_record.user_id,
                room_id=room.id,
                status='checked_out'
            ).order_by(Dorm.check_out_date.desc()).first()
        
        user = User.query.get(checkout_record.user_id)
        if not user:
            flash('用户信息不存在', 'danger')
            return redirect(url_for('utility_index.utility_home'))
        
        # 4. 判断是否为换宿
        is_transfer = dorm_record.end_operation_type in ('transfer', 'exchange') if dorm_record and dorm_record.end_operation_type else False
        
        # 5. 获取室友信息
        roommates = []
        period_start = main_record.start_date
        period_end = main_record.end_date
        
        all_dorm_records = Dorm.query.filter(
            Dorm.room_id == room.id,
            Dorm.user_id != checkout_record.user_id
        ).all()
        
        unique_user_ids = set()
        for dorm in all_dorm_records:
            if dorm.user_id not in unique_user_ids:
                unique_user_ids.add(dorm.user_id)
                dorm_chain = dorm.dorm_chain
                has_valid_stay = False
                relevant_dorm = None
                period_days = 0
                earliest_checkin = None
                latest_checkout = None
                has_active_stay = False
                
                for chain_dorm in dorm_chain:
                    chain_checkin = chain_dorm.check_in_date
                    chain_checkout = chain_dorm.check_out_date or datetime.now()
                    
                    if (chain_dorm.room_id == room.id and 
                        chain_checkin <= period_end and 
                        chain_checkout >= period_start):
                        
                        transfer_details = chain_dorm.get_transfer_details()
                        has_early_transfer = False
                        
                        if transfer_details['next']:
                            next_checkin = transfer_details['next']['check_in']
                            if isinstance(next_checkin, datetime) and period_start < next_checkin < period_end:
                                has_early_transfer = True
                        
                        if not has_early_transfer:
                            has_valid_stay = True
                            if relevant_dorm is None:
                                relevant_dorm = chain_dorm
                            
                            # 累加该段住宿天数（与模型逻辑一致，使用.date()避免时间部分导致天数偏少）
                            stay_start = max(chain_checkin, period_start)
                            stay_end = min(
                                chain_dorm.check_out_date or checkout_record.checkout_date,
                                checkout_record.checkout_date,
                                period_end
                            )
                            
                            if stay_start <= stay_end:
                                # 同日换宿：入住和退宿为同一天时不计天数
                                if chain_dorm.check_out_date is not None and chain_dorm.check_in_date.date() == chain_dorm.check_out_date.date():
                                    days = 0
                                else:
                                    days = (stay_end.date() - stay_start.date()).days + 1
                                period_days += days
                            
                            # 跟踪最早的入住日期
                            if earliest_checkin is None or chain_checkin < earliest_checkin:
                                earliest_checkin = chain_checkin
                            
                            # 跟踪最晚的退宿日期和在住状态
                            if chain_dorm.check_out_date is None:
                                has_active_stay = True
                            elif latest_checkout is None or chain_dorm.check_out_date > latest_checkout:
                                latest_checkout = chain_dorm.check_out_date
                
                if has_valid_stay and relevant_dorm:
                    rm_user = User.query.get(dorm.user_id)
                    if rm_user:
                        transfer_details = relevant_dorm.get_transfer_details()
                        has_transfer = bool(transfer_details['prev'] or transfer_details['next'])
                        
                        # 判断状态：有在住段或最晚退宿日期晚于账期结束则为在住
                        if has_active_stay or (latest_checkout is not None and latest_checkout > period_end):
                            status_text = "在住"
                            status_type = "success"
                            actual_checkin = earliest_checkin
                            actual_checkout = None
                        else:
                            status_text = "已退宿"
                            status_type = "neutral"
                            actual_checkin = earliest_checkin
                            actual_checkout = latest_checkout
                        
                        if (actual_checkout is not None and 
                            (actual_checkout < actual_checkin or actual_checkout < period_start)):
                            continue
                        
                        transfer_prev_room = None
                        transfer_next_room = None
                        
                        if transfer_details['prev'] and not (transfer_details['next'] and transfer_details['next']['check_in'] <= period_end):
                            transfer_prev_room = transfer_details['prev']['room_number']
                        
                        if transfer_details['next'] and transfer_details['next']['check_in'] <= period_end:
                            transfer_next_room = transfer_details['next']['room_number']
                        
                        roommates.append({
                            "user_id": rm_user.id,
                            "name": rm_user.name,
                            "check_in_date": actual_checkin,
                            "check_out_date": actual_checkout,
                            "status_text": status_text,
                            "status_type": status_type,
                            "has_transfer": has_transfer,
                            "transfer_prev_room": transfer_prev_room,
                            "transfer_next_room": transfer_next_room,
                            "period_days": period_days,
                        })
        
        roommates.sort(key=lambda x: x["check_in_date"] if x["check_in_date"] else datetime.min)
        
        # 6. 记录日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='checkout_edit',
            action=f"访问编辑退宿人员费用页面 [退宿记录ID: {checkout_id}]",
            result="成功"
        )
        
        return render_template('utility_bill/utility_room_checkout_edit.html',
                              title=f"编辑退宿人员费用-{user.name}(ID:{user.id})",
                              checkout_record=checkout_record,
                              user=user,
                              room=room,
                              main_record=main_record,
                              dorm_record=dorm_record,
                              is_transfer=is_transfer,
                              roommates=roommates,
                              billing_period=main_record.billing_period)
    
    except Exception as e:
        logging.error(f"访问编辑退宿人员费用页面失败: {str(e)}", exc_info=True)
        flash(f'加载页面失败: {str(e)}', 'danger')
        return redirect(url_for('utility_index.utility_home'))

# 退宿费用计算详情结果页面
@utility_index_bp.route('/utility_user_checkout_detail')
@login_required
@require_permission('utility.user_checkout_detail')
def utility_user_checkout_detail():

    # 获取URL参数，只需要checkout_id
    checkout_id = request.args.get('id', type=int)
    
    if not checkout_id:
        flash('参数错误，无法查看费用结果', 'danger')
        return redirect(url_for('dorm.dorm_query'))
    
    # 查询相关记录
    checkout_record = CheckoutUtilityRecord.query.get_or_404(checkout_id)
    
    # 从checkout_record中获取用户和房间信息
    user = User.query.get_or_404(checkout_record.user_id)
    room = Room.query.get_or_404(checkout_record.room_id)
    
    # 获取关联主表的账期信息
    main_record = RoomUtilityRecord.query.get(checkout_record.record_id)
    billing_period = main_record.billing_period if main_record else None
    
    # 通过 dorm_id 关联的 Dorm 记录判断操作类型
    # 换宿(transfer)/互换(exchange)产生的退宿日期不显示，真正退宿(checkout)才显示
    is_transfer = False
    if checkout_record.dorm_id:
        dorm_record = Dorm.query.get(checkout_record.dorm_id)
        if dorm_record and dorm_record.end_operation_type in ('transfer', 'exchange'):
            is_transfer = True
    
    # 渲染费用结果页面
    return render_template('utility_bill/utility_user_checkout_detail.html', 
                          title=f"退宿费用核算详情-{user.name}(ID:{user.id})",
                          checkout_record=checkout_record, 
                          user=user, 
                          room=room,
                          billing_period=billing_period,
                          is_transfer=is_transfer)
    
# 核算用户水电费页面
@utility_index_bp.route('/utility_occupant_manage')
@login_required
@require_permission('utility.view')
def utility_occupant_manage():
    """核算用户水电费页面"""
    try:
        # 获取查询参数用于日志
        billing_period = request.args.get('billing_period', '')
        room_id = request.args.get('room_id', '未指定')
        
        # 获取所有账期用于下拉选择
        periods = db.session.query(RoomUtilityRecord.billing_period).distinct().order_by(RoomUtilityRecord.billing_period.desc()).all()
        billing_periods = [p[0] for p in periods]
        
        # 获取所有楼栋数据用于筛选
        buildings = db.session.query(Room.building).distinct().order_by(Room.building).all()
        building_list = [building[0] for building in buildings if building[0]]
        
        # 获取所有部门数据用于筛选
        department_list = [d.name for d in Department.query.filter_by(status='正常').order_by(Department.name).all()]
        
        log_operation(
            user_id=current_user.id,
            module='utility',#这里记载模块
            operation_type='records',#这里记载类型
            action=f"访问核算用户水电费页面 [账期: {billing_period}, 房间ID: {room_id}, 加载账期数量: {len(billing_periods)}, 加载楼栋数量: {len(building_list)}, 加载部门数量: {len(department_list)}]",#这里记载成功与失败的记录
            result="成功"#这里只有成功与失败
        )
        return render_template('utility_bill/utility_occupant_manage.html', billing_periods=billing_periods, buildings=building_list, departments=department_list, billing_period=billing_period, title=f"核算用户水电费")
    except Exception as e:
        logging.error(f"访问核算用户水电费页面失败: {str(e)}")
        flash(str(e), 'danger')
        return render_template('utility_bill/utility_occupant_manage.html', billing_periods=[], buildings=[], departments=[], billing_period='', title=f"核算用户水电费")

@utility_index_bp.route('/utility_room_records_edit/<int:record_id>', methods=['GET'])
@login_required
@require_permission('utility.edit')
def utility_room_records_edit(record_id):
    """编辑房间水电费数据页面"""
    # 检查功能开关
    if not SystemConfig.get_config_value('UTILITY_BILL_EDIT_ENABLED', False):
        flash('直接编辑房间水电费功能未启用，请在系统配置中开启', 'warning')
        return redirect(url_for('utility_index.utility_room_records_bill'))
    
    try:
        record = RoomUtilityRecord.query.get(record_id)
        if not record:
            flash(f'记录ID={record_id}不存在', 'danger')
            return redirect(url_for('utility_index.utility_room_records_bill'))
        
        room = Room.query.get(record.room_id)
        
        # 获取账期参数
        billing_period = request.args.get('billing_period', record.billing_period)
        
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='records',
            action=f"访问编辑房间水电费页面 [记录ID: {record_id}]",
            result="成功"
        )
        
        return render_template(
            'utility_bill/utility_room_records_edit.html',
            title='编辑房间水电费',
            record=record,
            room=room,
            billing_period=billing_period
        )
    except Exception as e:
        logging.error(f"加载编辑页面失败: {str(e)}")
        flash(f'加载编辑页面失败: {str(e)}', 'danger')
        billing_period = request.args.get('billing_period', '')
        return redirect(url_for('utility_index.utility_room_records_bill', billing_period=billing_period))

@utility_index_bp.route('/utility_occupant_edit/<int:record_id>', methods=['GET'])
@login_required
@require_permission('utility.edit')
def utility_occupant_edit(record_id):
    """编辑用户费用分摊数据页面"""
    # 检查功能开关
    if not SystemConfig.get_config_value('UTILITY_OCCUPANT_EDIT_ENABLED', False):
        flash('直接编辑用户费用分摊功能未启用，请在系统配置中开启', 'warning')
        return redirect(url_for('utility_index.utility_occupant_manage'))
    
    try:
        record = RoomUtilityRecord.query.get(record_id)
        if not record:
            flash(f'记录ID={record_id}不存在', 'danger')
            return redirect(url_for('utility_index.utility_occupant_manage'))
        
        room = Room.query.get(record.room_id)
        
        billing_period = request.args.get('billing_period', record.billing_period)
        
        # 查询在住人员费用分摊记录，按用户名排序
        occupant_records = (RoomUtilityOccupant.query
            .filter_by(record_id=record_id)
            .join(User, RoomUtilityOccupant.user_id == User.id)
            .order_by(User.username)
            .all())
        
        log_operation(user_id=current_user.id, module='utility', operation_type='utility_edit',
            action=f"访问编辑用户费用分摊页面 [记录ID: {record_id}]", result="成功")
        
        return render_template('utility_bill/utility_occupant_edit.html',
            title='编辑用户费用分摊', record=record, room=room,
            billing_period=billing_period, occupant_records=occupant_records)
    except Exception as e:
        logging.error(f"加载编辑页面失败: {str(e)}")
        flash(f'加载编辑页面失败: {str(e)}', 'danger')
        return redirect(url_for('utility_index.utility_occupant_manage'))

