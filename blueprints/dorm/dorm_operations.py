from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
import logging
from datetime import datetime  # 保留datetime导入
from sqlalchemy import func  # 关键修复：导入func
from utils.db import db
from models.dorm.dorm import Dorm
from models.user.user import User
from models.department.department import Department
from models.room.room import Room
from models.room.room_bed import Bed  # 【新增】导入床位模型
from models.role import Role  # 导入角色模型
from utils.log import log_operation
from .dorm import dorm_bp  # 导入dorm蓝图

# 导入需要的模型
from models.utility.utility_room_meter import UtilityMeterReading  # 抄表记录模型
from models.utility.utility_room_bill_checkout import CheckoutUtilityRecord # 退宿费用子表
from models.utility.utility_room_bill_occupant import RoomUtilityOccupant # 住户费用子表
from models.fee_subsidy.fee_subsidy import FeeSubsidy #费用补贴主表
from models.fee_subsidy.fee_subsidy_usage import FeeSubsidyUsage
# 导入require_permission装饰器
from utils.auth import require_permission


# --------------------------
# 创建宿舍分配端点（用于查看用户页面的分配按钮）
# --------------------------
@dorm_bp.route('/create_allocation', methods=['GET', 'POST'])
@login_required
@require_permission('dorm.allocate')
def create_allocation():
    """分配宿舍：
    - GET: 接收user_id参数，查询用户信息和可用房间列表
    - POST: 接收分配表单数据，调用Dorm模型的create_allocation方法处理分配
    """
    
    # 处理GET请求（显示分配页面）
    if request.method == 'GET':
        # 从URL获取用户ID
        user_id = request.args.get('user_id', type=int)
        
        if not user_id:
            flash('用户ID不能为空', 'danger')
            logging.error(f"创建分配宿舍失败：用户ID为空（GET请求）")
            return redirect(url_for('user.manage'))
        
        # 验证用户是否存在
        user = User.query.get(user_id)
        if not user:
            flash('用户不存在', 'danger')
            logging.error(f"创建分配宿舍失败：用户ID {user_id} 不存在（GET请求）")
            return redirect(url_for('user.manage'))
        
        # 检查用户是否为超级管理员，超级管理员不能分配宿舍
        if user.user_role and user.user_role.code == 'super_admin':
            flash('超级管理员不能分配宿舍', 'danger')
            logging.error(f"创建分配宿舍失败：用户ID {user_id} 是超级管理员，不能分配宿舍（GET请求）")
            return redirect(url_for('user.manage'))
        
        # 检查用户是否已有活跃住宿记录
        existing_dorm = Dorm.query.filter_by(user_id=user_id, status='active').first()
        if existing_dorm:
            flash('该用户已有活跃的住宿记录', 'danger')
            logging.error(f"创建分配宿舍失败：用户ID {user_id} 已有活跃住宿记录（GET请求）")
            return redirect(url_for('user.view', id=user_id))
        
        # 查询用户的换宿记录（用于展示历史信息）
        transfer_records = []
        dorm_records = Dorm.query.filter_by(user_id=user_id).order_by(Dorm.check_in_date.desc()).all()
        for record in dorm_records:
            if record.room:
                transfer_records.append({
                    'room_id': record.room_id, 
                    'room_number': f"{record.room.building}{record.room.room_number}",
                    'gender_restriction': record.room.gender_restriction if record.room.gender_restriction else '-',
                    'average_age': record.room.average_age if record.room.average_age else '-',
                    'room_type': record.room.room_type if record.room.room_type else '-',
                    'room_level': record.room.room_level if record.room.room_level else '-',
                    'check_in_date': record.check_in_date if record.check_in_date else '',
                    'check_out_date': record.check_out_date if record.check_out_date else '',
                    'status': '在住' if record.status == 'active' else '已退宿',
                    'remarks': record.remarks
                })
        
        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            action=f"访问分配宿舍页面（用户ID: {user_id}）",
            result="成功",
            module='dorm',
            operation_type='records',
            ip_address=request.headers.get('X-Real-IP', request.remote_addr)
        )
        
        # 生成默认日期时间
        default_datetime = datetime.now().strftime('%Y-%m-%dT%H:%M')
        
        # 从Room模型查询去重后的筛选条件数据
        buildings = db.session.query(Room.building).distinct().order_by(Room.building).all()
        room_types = db.session.query(Room.room_type).distinct().order_by(Room.room_type).all()
        room_levels = db.session.query(Room.room_level).distinct().order_by(Room.room_level).all()
        
        # 转换为列表格式
        building_list = [b[0] for b in buildings if b[0]]
        room_type_list = [rt[0] for rt in room_types if rt[0]]
        room_level_list = [rl[0] for rl in room_levels if rl[0]]
        
        return render_template('dorm_manage/dorm_create_allocation.html',
                              title=f"分配宿舍 - {user.name}(ID:{user_id})",
                              user=user,
                              transfer_records=transfer_records,
                              default_datetime=default_datetime,
                              building_list=building_list,
                              room_type_list=room_type_list,
                              room_level_list=room_level_list,
                              datetime=datetime
                              )
                              
    
    # 处理POST请求（提交分配表单）
    elif request.method == 'POST':
        try:
            # 从表单获取数据
            user_id = request.form.get('user_id', type=int)
            room_id = request.form.get('new_room_id', type=int)  # 保留字段名以兼容前端表单
            check_in_date = request.form.get('check_in_date')
            remarks = request.form.get('remarks', '')
            
            # 基础参数验证
            if not all([user_id, room_id, check_in_date]):
                logging.error(f"创建分配宿舍失败：用户ID {user_id} 缺少必要参数（POST请求）")
                flash('缺少必要参数', 'danger')
                return redirect(url_for('dorm.create_allocation', user_id=user_id))
            
            # 验证用户是否存在
            user = User.query.get(user_id)
            if not user:
                flash('用户不存在', 'danger')
                logging.error(f"创建分配宿舍失败：用户ID {user_id} 不存在（POST请求）")
                return redirect(url_for('user.manage'))
            
            # 检查用户是否为超级管理员，超级管理员不能分配宿舍
            if user.user_role and user.user_role.code == 'super_admin':
                flash('超级管理员不能分配宿舍', 'danger')
                logging.error(f"创建分配宿舍失败：用户ID {user_id} 是超级管理员，不能分配宿舍（POST请求）")
                return redirect(url_for('dorm.create_allocation', user_id=user_id))
            
            # 验证房间是否存在
            room = Room.query.get(room_id)
            if not room:
                flash('目标房间不存在', 'danger')
                logging.error(f"创建分配宿舍失败：房间ID {room_id} 不存在（POST请求）")
                return redirect(url_for('dorm.create_allocation', user_id=user_id))
            
            # 验证性别匹配
            if room.gender_restriction != '无限制' and user.gender and room.gender_restriction != user.gender:
                flash(f'房间 {room.building}{room.room_number} 的性别要求与用户不匹配', 'danger')
                logging.error(f"创建分配宿舍失败：用户ID {user_id} 性别 {user.gender} 与房间 {room.building}{room.room_number} 的性别要求 {room.gender_restriction} 不匹配（POST请求）")
                return redirect(url_for('dorm.create_allocation', user_id=user_id))
            
            # 日期格式转换
            try:
                # 尝试解析包含时间的格式
                if 'T' in check_in_date:
                    try:
                        check_in_date = datetime.strptime(check_in_date, '%Y-%m-%dT%H:%M:%S')
                    except ValueError:
                        check_in_date = datetime.strptime(check_in_date, '%Y-%m-%dT%H:%M')
                else:
                    check_in_date = datetime.strptime(check_in_date, '%Y-%m-%d')
            except ValueError:
                logging.error(f"创建分配宿舍失败：用户ID {user_id} 提供的入住日期 {check_in_date} 格式不正确（POST请求）")
                flash('日期格式不正确，请使用YYYY-MM-DD、YYYY-MM-DDTHH:MM或YYYY-MM-DDTHH:MM:SS', 'danger')
                return redirect(url_for('dorm.create_allocation', user_id=user_id))
            
            # 检查房间是否已满
            if room.current_occupancy >= room.capacity:
                flash(f'房间 {room.building}{room.room_number} 已满', 'danger')
                logging.error(f"创建分配宿舍失败：房间ID {room_id} 已满（POST请求）")
                return redirect(url_for('dorm.create_allocation', user_id=user_id))
            
            # 自动分配床位
            available_bed = Bed.query.filter_by(
                room_id=room_id,
                status='available'
            ).order_by(Bed.bed_number).first()
            
            if not available_bed:
                flash(f'房间 {room.building}{room.room_number} 无可用床位', 'danger')
                logging.error(f"创建分配宿舍失败：房间ID {room_id} 无可用床位（POST请求）")
                return redirect(url_for('dorm.create_allocation', user_id=user_id))
            
            # 调用模型方法创建分配记录
            new_dorm = Dorm.create_allocation(
                user_id=user_id,
                room_id=room_id,
                bed_id=available_bed.id,
                check_in_date=check_in_date,
                remarks=remarks
            )
            
            # 自动禁用用户的外宿补贴
            active_lodging_subsidies = FeeSubsidy.query.filter(
                FeeSubsidy.user_id == user_id,
                FeeSubsidy.fee_type.in_(['外宿补贴', '住宿补贴']),
                FeeSubsidy.is_enabled == True
            ).all()
            
            subsidies_disabled = False
            if active_lodging_subsidies:
                for subsidy in active_lodging_subsidies:
                    subsidy.is_enabled = False
                    subsidy.change_reason = f"分配宿舍自动禁用: {remarks}"
                    subsidy.operator_id = current_user.id if hasattr(current_user, 'id') else 0
                    db.session.add(subsidy)
                    
                # 更新用户的外宿补贴金额为0
                user.lodging_allowance = 0
                db.session.add(user)
                subsidies_disabled = True
            
            # 分配成功日志
            user_name = user.name if (user and user.name) else f"未知用户（ID:{user_id}）"
            room_full_number = f"{room.building}{room.room_number}"
            
            if subsidies_disabled:
                logging.info(f"用户ID {user_id}（{user.name if user.name else '未知用户'}）外宿补贴已自动禁用（POST请求）")
                
            log_operation(
                user_id=current_user.id,
                action=f"分配成功：{user_name}（ID:{user_id}）已分配至{room_full_number}房间{', 外宿补贴已禁用' if subsidies_disabled else ''}",
                result="成功",
                module='dorm',
                operation_type='allocate',
                ip_address=request.headers.get('X-Real-IP', request.remote_addr)
            )
            db.session.commit()
            
            message = f"宿舍分配成功：{user_name}（ID:{user_id}）已分配至{room_full_number}房间"
            if subsidies_disabled:
                message += "，外宿补贴已自动禁用"
            flash(message, 'success')
            
            logging_message = f"用户ID {user_id}（{user_name}）成功分配至房间 {room_full_number}（POST请求）"
            if subsidies_disabled:
                logging_message += "，外宿补贴已自动禁用"
            logging.info(logging_message)
            return redirect(url_for('dorm.dorm_query'))
            
        except ValueError as e:
            db.session.rollback()
            flash(str(e), 'danger')
            logging.error(f"创建分配宿舍失败：{str(e)}（POST请求）")
            return redirect(url_for('dorm.create_allocation', user_id=user_id))
        except Exception as e:
            db.session.rollback()
            logging.error(f"处理宿舍分配失败: {str(e)}（POST请求）")
            flash('服务器处理失败，请稍后重试', 'danger')
            return redirect(url_for('dorm.create_allocation', user_id=request.form.get('user_id', type=int)))


# --------------------------
# 添加宿舍分配路由
# --------------------------
@dorm_bp.route('/add', methods=['GET', 'POST'])
@login_required
@require_permission('dorm.allocate')
def add():
    """添加宿舍分配：处理表单提交和页面渲染"""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    if request.method == 'POST':
        try:
            # 获取表单数据并验证
            user_id = request.form.get('user_id', type=int)
            room_id = request.form.get('room_id', type=int)
            check_in_date_str = request.form.get('check_in_date')
            remarks = request.form.get('remarks', '')
            
            # 基础参数校验
            if not (user_id and room_id and check_in_date_str):
                error_msg = '人员、房间和入住日期为必填项'
                if is_ajax:
                    return jsonify({"success": False, "message": error_msg}), 400
                flash(error_msg, 'danger')
                logging.error(f"添加宿舍分配失败：{error_msg}（POST请求）")
                return render_template('dorm_manage/dorm_add.html',title=f"分配宿舍")
            
            # 验证用户角色（禁止为超级管理员分配宿舍）
            user = User.query.get(user_id)
            if (user.user_role and user.user_role.code == 'super_admin') and not (current_user.user_role and current_user.user_role.code == 'super_admin'):
                error_msg = '禁止为超级管理员分配宿舍'
                if is_ajax:
                    return jsonify({"success": False, "message": error_msg}), 400
                flash(error_msg, 'danger')
                logging.error(f"添加宿舍分配失败：{error_msg}（POST请求）")
                return render_template('dorm_manage/dorm_add.html',title=f"分配宿舍")

            # 日期格式转换 - 修改：支持datetime格式
            try:
                # 尝试解析包含时间的格式
                if 'T' in check_in_date_str:
                    try:
                        check_in_date = datetime.strptime(check_in_date_str, '%Y-%m-%dT%H:%M:%S')
                    except ValueError:
                        check_in_date = datetime.strptime(check_in_date_str, '%Y-%m-%dT%H:%M')
                else:
                    check_in_date = datetime.strptime(check_in_date_str, '%Y-%m-%d')
            except ValueError:
                error_msg = '日期格式错误，请使用YYYY-MM-DD、YYYY-MM-DDTHH:MM或YYYY-MM-DDTHH:MM:SS格式'
                if is_ajax:
                    return jsonify({"success": False, "message": error_msg}), 400
                flash(error_msg, 'danger')
                logging.error(f"添加宿舍分配失败：{error_msg}（POST请求）")
                return render_template('dorm_manage/dorm_add.html',title=f"分配宿舍")
            
            # 检查是否已有活跃住宿记录
            existing_dorm = Dorm.query.filter_by(user_id=user_id, status='active').first()
            if existing_dorm:
                error_msg = '该人员已有活跃的住宿记录'
                if is_ajax:
                    return jsonify({"success": False, "message": error_msg}), 400
                flash(error_msg, 'danger')
                logging.error(f"添加宿舍分配失败：{error_msg}（POST请求）")
                return render_template('dorm_manage/dorm_add.html',title=f"分配宿舍")
            
            # 验证房间状态
            room = Room.query.get_or_404(room_id)
            if room.current_occupancy >= room.capacity:
                error_msg = f'房间 {room.building}-{room.room_number} 已满'
                if is_ajax:
                    return jsonify({"success": False, "message": error_msg}), 400
                flash(error_msg, 'danger')
                logging.error(f"添加宿舍分配失败：{error_msg}（POST请求）")
                return render_template('dorm_manage/dorm_add.html',title=f"分配宿舍")

            # 自动分配床位
            available_bed = Bed.query.filter_by(
                room_id=room_id,
                status='available'
            ).order_by(Bed.bed_number).first()
            
            if not available_bed:
                error_msg = f'房间 {room.building}-{room.room_number} 无可用床位'
                if is_ajax:
                    return jsonify({"success": False, "message": error_msg}), 400
                flash(error_msg, 'danger')
                logging.error(f"添加宿舍分配失败：{error_msg}（POST请求）")
                return render_template('dorm_manage/dorm_add.html',title=f"分配宿舍")
            
            # 调用模型方法创建分配记录（使用事务确保原子性）
            new_dorm = Dorm.create_allocation(
                user_id=user_id,
                room_id=room_id,
                bed_id=available_bed.id,
                check_in_date=check_in_date,  # 已改为datetime类型
                remarks=remarks
            )
            
            # 自动禁用用户的外宿补贴
            subsidies_disabled = False
            # 查询用户启用的外宿补贴
            active_lodging_subsidies = FeeSubsidy.query.filter(
                FeeSubsidy.user_id == user_id,
                FeeSubsidy.fee_type.in_(['外宿补贴', '住宿补贴']),
                FeeSubsidy.is_enabled == True
            ).all()
            
            # 禁用这些外宿补贴（如果存在）
            if active_lodging_subsidies:
                subsidies_disabled = True
                for subsidy in active_lodging_subsidies:
                    subsidy.is_enabled = False
                    subsidy.change_reason = f"分配宿舍自动禁用: {remarks}"
                    subsidy.operator_id = current_user.id if hasattr(current_user, 'id') else 0
                    db.session.add(subsidy)
                    
                    # 更新用户的外宿补贴金额为0
                    user.lodging_allowance = 0
                    db.session.add(user)
                    
                    logging.info(f"为用户ID:{user_id}分配宿舍时，已自动禁用其外宿补贴(ID:{subsidy.id})")
            
            # 分配成功日志
            user_name = user.name if (user and user.name) else f"未知用户（ID:{user_id}）"
            room_full_number = f"{room.building}{room.room_number}"
            log_action = f"分配成功：{user_name}已分配至{room_full_number}房间"
            if subsidies_disabled:
                log_action += "，并自动禁用了外宿补贴"
            log_operation(
                user_id=current_user.id,
                action=log_action,
                result="成功",
                module='dorm',
                operation_type='allocate',
                ip_address=request.headers.get('X-Real-IP', request.remote_addr)
            )
            db.session.commit()
            # 响应处理（AJAX/页面跳转）
            if is_ajax:
                success_message = f"添加宿舍分配成功：{user_name}已分配至{room_full_number}房间"
                if subsidies_disabled:
                    success_message += "，并自动禁用了外宿补贴"
                return jsonify({
                    "success": True,
                    "message": success_message,
                    "data": {
                        "dorm_id": new_dorm.id,
                        "user_id": user_id,
                        "room_id": room_id,
                        "bed_id": available_bed.id
                    }
                })
            
            success_message = '宿舍分配添加成功'
            if subsidies_disabled:
                success_message += '，并自动禁用了外宿补贴'
            flash(success_message, 'success')
            logging_message = f"添加宿舍分配成功：{user_name}已分配至{room_full_number}房间"
            if subsidies_disabled:
                logging_message += "，并自动禁用了外宿补贴"
            logging.info(logging_message + "（POST请求）")
            return redirect(url_for('dorm.manage'))
            
        except Exception as e:
            db.session.rollback()
            # 记录错误日志
            log_operation(
                user_id=current_user.id,
                action="尝试添加宿舍分配",
                result=f"失败: {str(e)}",
                module='dorm',
                operation_type='allocate',
                ip_address=request.headers.get('X-Real-IP', request.remote_addr)
            )
            
            # 错误响应
            if is_ajax:
                return jsonify({
                    "success": False,
                    "message": f'添加失败：{str(e)}'
                }), 500
            
            # 记录错误日志
            logging.error(f"添加宿舍分配失败：{str(e)}（POST请求）")
            
            flash(f'添加失败：{str(e)}', 'danger')
    
    # GET请求：渲染添加页面
    # 获取未分配宿舍的用户（无活跃住宿记录，排除超级管理员）
    super_admin_role = Role.query.filter_by(code='super_admin').first()
    users_query = User.query.filter(
        User.status == '在职',
        ~User.id.in_(
            db.session.query(Dorm.user_id).filter(Dorm.status == 'active')
        )
    )
    if super_admin_role:
        users_query = users_query.filter(User.role_id != super_admin_role.id)
    users = users_query.all()
    available_rooms = Room.query.filter_by(status='available').all()
    # 记录访问日志
    log_operation(
            user_id=current_user.id,
            module='dorm',
            operation_type='records',
            action="访问添加宿舍分配页面",
            result="成功"
    )
    return render_template(
        'dorm_manage/dorm_add.html',
        title="添加宿舍分配",
        users=users,
        available_rooms=available_rooms
    )

# --------------------------
# 退宿办理路由（支持user_id参数）
# --------------------------   
@dorm_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
@require_permission('dorm.checkout')
def checkout():
    """退宿办理：
    - GET: 接收user_id参数，查询用户信息、房间信息和室友信息，返回相关数据
    - POST: 接收退宿表单数据，调用Dorm模型的check_out方法处理退宿
    """
    
    # 处理POST请求（提交退宿表单）
    if request.method == 'POST':
        try:
            # 从表单获取数据
            user_id = request.form.get('user_id', type=int)
            check_out_date = request.form.get('check_out_date')
            remarks = request.form.get('remarks', '')
            checkout_type = request.form.get('checkout_type', '离职退宿')
            
            # 获取水电表抄表读数
            water_current = request.form.get('water_current', type=float)
            electric_current = request.form.get('electric_current', type=float)
            
            # 基础参数验证
            if not all([user_id, check_out_date]):
                # 缺少必要参数
                logging.error(f"退宿缺少必要参数（用户ID: {user_id}，退宿日期: {check_out_date}）")
                flash('缺少必要参数（用户ID/退宿日期）', 'danger')
                return redirect(url_for('dorm.checkout', user_id=user_id))
            
            # 验证用户是否存在
            user = User.query.get(user_id)
            if not user:
                logging.error(f"用户不存在（ID: {user_id}）")
                flash(f'用户不存在（ID: {user_id}）', 'danger')
                return redirect(url_for('dorm.dorm_query'))
            
            # 日期格式转换
            try:
                # 尝试解析包含时间的格式
                if 'T' in check_out_date:
                    # 首先尝试带秒的格式
                    try:
                        check_out_date = datetime.strptime(check_out_date, '%Y-%m-%dT%H:%M:%S')
                    except ValueError:
                        # 如果失败，尝试不带秒的格式
                        check_out_date = datetime.strptime(check_out_date, '%Y-%m-%dT%H:%M')
            except ValueError:
                # 日期格式转换失败
                logging.error(f"退宿日期格式错误（用户ID: {user_id}，日期: {check_out_date}）")
                flash('日期格式不正确，请使用YYYY-MM-DD、YYYY-MM-DDTHH:MM或YYYY-MM-DDTHH:MM:SS', 'danger')
                return redirect(url_for('dorm.checkout', user_id=user_id))
            
            # 查询用户的当前住宿记录
            current_dorm = Dorm.query.filter(
                Dorm.user_id == user_id,
                Dorm.status == 'active',
                Dorm.check_out_date.is_(None)
            ).with_for_update().first()
            
            if not current_dorm:
                logging.info(f"用户{user_id}无当前有效住宿记录，无法退宿")
                raise ValueError(f"用户{user_id}无当前有效住宿记录，无法退宿")
            
            # 执行退宿操作
            current_dorm.check_out(
                check_out_date=check_out_date,
                remarks=remarks
            )
            
            # 根据退宿类型进行不同处理
            if checkout_type == '自离退宿':
                
                
                # 禁用用户所有的住宿补贴
                subsidies_disabled = False
                try:
                    # 查询用户所有启用状态的住宿补贴
                    user_subsidies = FeeSubsidy.query.filter(
                        FeeSubsidy.user_id == user_id,
                        FeeSubsidy.is_enabled == True,
                        FeeSubsidy.fee_type == "住宿补贴"
                    ).all()
                    
                    # 如果存在住宿补贴，则逐一禁用
                    if user_subsidies:
                        subsidies_disabled = True
                        for subsidy in user_subsidies:
                            FeeSubsidy.disabled_subsidy(
                                subsidy_id=subsidy.id,
                                operator_id=current_user.id,
                                reason=f"用户 {user.name} 自离退宿自动禁用（退宿日期：{check_out_date.strftime('%Y-%m-%d %H:%M:%S')}）"
                            )
                        
                        logging.info(f"成功禁用用户ID={user_id},{user.name}的所有住宿补贴，共{len(user_subsidies)}条记录")
                except Exception as e:
                    logging.error(f"禁用用户住宿补贴时发生错误：{str(e)}")
                    flash(f"禁用住宿补贴时发生错误：{str(e)}", 'warning')

                # 自离退宿：更新状态为自离，仅办理退宿，跳过费用和抄表记录流程，但费用补贴需要正常禁用
                user.status = '自离'
                user.is_active = False
                user.is_banned = False
                db.session.add(user)

                # 记录自离退宿的特殊日志
                user_name = user.name if (user and user.name) else f"未知用户（ID:{user_id}）"
                log_action = f"用户{user_name}自离从{current_dorm.room.building}{current_dorm.room.room_number}退宿，日期：{check_out_date}" if current_dorm.room else "未知房间"
                if subsidies_disabled:
                    log_action += f"，并自动禁用了该用户{len(user_subsidies)}条住宿补贴"
                log_operation(
                    user_id=current_user.id,
                    action=log_action,
                    result="成功",
                    module='dorm',
                    operation_type='checkout',
                    ip_address=request.headers.get('X-Real-IP', request.remote_addr)
                )
                
                db.session.commit()
                
                # 获取房间信息
                room_info = f"{current_dorm.room.building}{current_dorm.room.room_number}" if current_dorm.room else "未知房间"
                
                # 自离用户退宿成功消息
                success_message = f"自离退宿成功：{user_name}已从{room_info}退宿，日期{check_out_date}"
                if subsidies_disabled:
                    success_message += f"，并自动禁用了{len(user_subsidies)}条住宿补贴"
                flash(success_message, 'success')
                logging.info(f"用户{user_name}自离退宿，仅办理退宿，不创建费用和抄表记录")
                return redirect(url_for('dorm.dorm_query'))
            else:
                # 离职退宿或在职退宿：执行完整的退宿流程（包括抄表和费用计算）
                
                # 添加退宿抄表记录
                room_id = current_dorm.room_id
                
                # 初始化费用计算标志
                calculate_fee = False
                
                # 创建水电表抄表记录
                if water_current is not None or electric_current is not None:
                    # 使用模型提供的方法创建抄表记录
                    meter_reading = UtilityMeterReading.create_reading(
                        room_id=room_id,
                        water_current=water_current if water_current is not None else None,
                        electric_current=electric_current if electric_current is not None else None,
                        reading_date=check_out_date,
                        meter_reader_id=current_user.id,
                        reading_type=2,  # 退宿抄表
                        user_id=user_id,
                        water_notes=f"退宿抄表：{user.name if user else '未知用户'}，{check_out_date.strftime('%Y-%m-%d %H:%M:%S')}",
                        electric_notes=f"退宿抄表：{user.name if user else '未知用户'}，{check_out_date.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    
                    logging.info(f"添加{user.name}的退宿抄表记录：房间ID={room_id}, 用户ID={user_id}, 水表读数={water_current}, 电表读数={electric_current}")
                    
                # 调用退宿费用模型计算费用
                # 如果抄表记录有任意一项是空值则不计算费用，如果是0值不算空
                calculate_fee = (water_current is not None) and (electric_current is not None)
                checkout_record = CheckoutUtilityRecord.create_from_checkout(
                    room_id=room_id,
                    user_id=user_id,
                    checkout_date=check_out_date,
                    electric_reading=electric_current,
                    water_reading=water_current,
                    remarks=f"退宿费用计算：{user.name if user else '未知用户'}，退宿日期：{check_out_date.strftime('%Y-%m-%d %H:%M:%S')}",
                    calculate_fee=calculate_fee
                )
                    
                logging.info(f"计算{user.name}的退宿费用：房间ID={room_id}, 用户ID={user_id}, 是否计算费用={calculate_fee}")
                # 如果计算费用为True，记录费用计算结果
                if calculate_fee:
                    logging.info(f"退宿费用计算结果：房间ID={room_id}, 用户ID={user_id}, 总费用={checkout_record.payable_fee}")
                
                # 禁用用户所有的住宿补贴
                subsidies_disabled = False
                try:
                    # 查询用户所有启用状态的住宿补贴
                    user_subsidies = FeeSubsidy.query.filter(
                        FeeSubsidy.user_id == user_id,
                        FeeSubsidy.is_enabled == True,
                        FeeSubsidy.fee_type == "住宿补贴"
                    ).all()
                    
                    # 如果存在住宿补贴，则逐一禁用
                    if user_subsidies:
                        subsidies_disabled = True
                        for subsidy in user_subsidies:
                            FeeSubsidy.disabled_subsidy(
                                subsidy_id=subsidy.id,
                                operator_id=current_user.id,
                                reason=f"用户 {user.name} 退宿自动禁用（退宿日期：{check_out_date.strftime('%Y-%m-%d %H:%M:%S')}）"
                            )
                        
                        logging.info(f"成功禁用用户ID={user_id},{user.name}的所有住宿补贴，共{len(user_subsidies)}条记录")
                except Exception as e:
                    logging.error(f"禁用用户住宿补贴时发生错误：{str(e)}")
                    flash(f"禁用住宿补贴时发生错误：{str(e)}", 'warning')
                    
                # 根据退宿类型更新用户状态
                if checkout_type == '离职退宿':
                    user.status = '离职'
                    user.is_active = False
                    user.is_banned = False
                elif checkout_type == '在职退宿':
                    user.status = '在职'
                db.session.add(user)

                # 退宿成功日志
                user_name = user.name if (user and user.name) else f"未知用户（ID:{user_id}）"
                log_action = f"用户{user_name}从{current_dorm.room.building}{current_dorm.room.room_number}退宿，日期：{check_out_date}" if current_dorm.room else "未知房间"
                if subsidies_disabled:
                    log_action += f"，并自动禁用了该用户{len(user_subsidies)}条住宿补贴"
                log_operation(
                    user_id=current_user.id,
                    action=log_action,
                    result="成功",
                    module='dorm',
                    operation_type='checkout',
                    ip_address=request.headers.get('X-Real-IP', request.remote_addr)
                )
                
                db.session.commit()
                
                # 获取房间信息
                room_info = f"{current_dorm.room.building}{current_dorm.room.room_number}" if current_dorm.room else "未知房间"
                
                # 构建退宿成功消息，包含费用计算状态和补贴禁用状态
                if calculate_fee:
                    success_message = f"退宿成功：{user_name}已从{room_info}退宿，日期{check_out_date}，费用已计算"
                    if subsidies_disabled:
                        success_message += f"，并自动禁用了{len(user_subsidies)}条住宿补贴"
                    # 跳转到费用结果页面，只需要传递checkout_id参数
                    return redirect(url_for('utility_index.utility_user_checkout_detail', id=checkout_record.id))
                else:
                    success_message = f"退宿成功：{user_name}已从{room_info}退宿，日期{check_out_date}，费用未计算，待补录"
                    if subsidies_disabled:
                        success_message += f"，并自动禁用了{len(user_subsidies)}条住宿补贴"
                    # 使用flash消息并重定向
                    flash(success_message, 'success')
                    logging.info(success_message)
                    return redirect(url_for('dorm.dorm_query'))
            
        except ValueError as e:
            # 退宿验证失败日志
            user = User.query.get(user_id) if user_id else None
            user_name = user.name if (user and user.name) else f"未知用户（ID:{user_id}）"
            log_operation(
                user_id=current_user.id,
                action=f"退宿验证失败：{user_name}",
                result="失败",
                module='dorm',
                operation_type='checkout',
                ip_address=request.headers.get('X-Real-IP', request.remote_addr)
            )
            flash(str(e), 'danger')
            logging.error(f"退宿验证失败: {str(e)}")
            return redirect(url_for('dorm.checkout', user_id=user_id))
        except Exception as e:
            db.session.rollback()
            logging.error(f"处理退宿失败: {str(e)}")
            log_operation(
                user_id=current_user.id,
                action=f"处理退宿异常: {str(e)}",
                result="失败",
                module='dorm',
                operation_type='checkout',
                ip_address=request.headers.get('X-Real-IP', request.remote_addr)
            )
            flash('服务器处理失败，请稍后重试', 'danger')
            return redirect(url_for('dorm.checkout', user_id=user_id))
    
    # 处理GET请求（显示退宿页面）
    # 记录访问日志
    log_operation(
        user_id=current_user.id,
        module='dorm',
        operation_type='records',
        action="访问办理退宿页面",
        result="成功"
    )
    
    # 从URL参数获取user_id
    user_id = request.args.get('user_id', type=int)
    
    # 初始化变量
    user = None
    current_dorm = None
    current_room = None
    roommates = []
    transfer_records = []
    error_message = None
    last_water_reading = {}
    last_electric_reading = {}
    
    try:
        # 如果提供了user_id，则查询相关信息
        if user_id:
            # 查询用户信息
            user = User.query.get(user_id)
            if not user:
                error_message = f"找不到ID为{user_id}的用户"
                logging.info(error_message)
                return render_template(
                    'dorm_manage/dorm_checkout.html',
                    title="办理退宿",
                    user=None,
                    current_dorm=None,
                    current_room=None,
                    roommates=[],
                    transfer_records=[],
                    error_message=error_message,
                    datetime=datetime,
                    user_id=user_id
                )
            
            # 查询用户的当前住宿记录
            current_dorm = Dorm.query.filter_by(
                user_id=user_id,
                status='active'
            ).first()
            
            if not current_dorm:
                error_message = f"用户{user.name}没有活跃的住宿记录"
                logging.info(error_message)
                return render_template(
                    'dorm_manage/dorm_checkout.html',
                    title="办理退宿",
                    user=user,
                    current_dorm=None,
                    current_room=None,
                    roommates=[],
                    transfer_records=[],
                    error_message=error_message,
                    datetime=datetime,
                    user_id=user_id
                )
            
            # 查询当前房间信息
            current_room = Room.query.get(current_dorm.room_id)
            if not current_room:
                error_message = "用户当前住宿的房间信息无效"
                logging.error(error_message)
                return render_template(
                    'dorm_manage/dorm_checkout.html',
                    title="办理退宿",
                    user=user,
                    current_dorm=current_dorm,
                    current_room=None,
                    roommates=[],
                    transfer_records=[],
                    error_message=error_message,
                    datetime=datetime,
                    user_id=user_id
                )
            
            # 获取上次抄表记录值
            # 使用模型中已有的方法获取最新正常抄表记录
            latest_water = UtilityMeterReading.get_latest_water_reading(current_room.id)
            latest_electric = UtilityMeterReading.get_latest_electric_reading(current_room.id)
            
            # 准备传递给前端的数据，包含时间信息
            if latest_water and latest_water.water_current:
                last_water_reading = {
                    'value': float(latest_water.water_current),
                    'date': latest_water.reading_date.strftime('%Y-%m-%d %H:%M:%S')
                }
            
            if latest_electric and latest_electric.electric_current:
                last_electric_reading = {
                    'value': float(latest_electric.electric_current),
                    'date': latest_electric.reading_date.strftime('%Y-%m-%d %H:%M:%S')
                }
            
            # 查询室友信息
            roommates_dorms = Dorm.query.filter(
                Dorm.room_id == current_room.id,
                Dorm.status == 'active',
                Dorm.user_id != user_id  # 排除当前用户
            ).all()
            
            for roommate_dorm in roommates_dorms:
                roommate = User.query.get(roommate_dorm.user_id)
                if roommate:
                    roommates.append({
                        'id': roommate.id,
                        'name': roommate.name,
                        'age': roommate.age if roommate.age else 0,
                        'gender': roommate.gender,
                        'department': roommate.department,
                        'position': roommate.position,
                        'check_in_date': roommate_dorm.check_in_date if roommate_dorm.check_in_date else ''
                    })

            # 获取用户换宿记录
            try:
                user_latest_dorm = Dorm.get_user_latest_dorm(user_id)
                if user_latest_dorm:
                    dorm_chain = user_latest_dorm.dorm_chain
                    for record in dorm_chain:
                        room = Room.query.get(record.room_id)
                        transfer_records.append({
                            'id': record.id,
                            'room_id': record.room_id,
                            'room_number': f"{room.building}{room.room_number}" if room else f"ID:{record.room_id}",
                            'gender_restriction': record.room.gender_restriction if record.room.gender_restriction else '-',
                            'average_age': record.room.average_age if record.room.average_age else '-',
                            'room_type': room.room_type if room and room.room_type else '',
                            'room_level': room.room_level if room and room.room_level else '',
                            'check_in_date': record.check_in_date if record.check_in_date else '',
                            'check_out_date': record.check_out_date if record.check_out_date else '',
                            'status': '在住' if record.status == 'active' else '已退宿',
                            'remarks': record.remarks or ''  # 这里备注是来自dorm住宿记录的备注
                        })
            except Exception as e:
                logging.error(f"获取换宿记录失败: {str(e)}")
            
            
            
    except Exception as e:
        logging.error(f"退宿页面处理异常: {str(e)}")
        error_message = f"加载失败: {str(e)}"
    
    # 设置默认日期时间（当前时间）
    default_datetime = datetime.now().strftime('%Y-%m-%dT%H:%M')
    
    # 获取用户水电费记录
    utility_records = []
    if user_id:
        try:
            # 获取在住人员费用记录
            active_utility_records = RoomUtilityOccupant.query.filter_by(user_id=user_id)
            active_utility_records = active_utility_records.join(RoomUtilityOccupant.main_record)
            active_utility_records = active_utility_records.order_by('billing_period').all()
            
            # 获取退宿人员费用记录
            checkout_utility_records = CheckoutUtilityRecord.query.filter_by(user_id=user_id)
            checkout_utility_records = checkout_utility_records.order_by(CheckoutUtilityRecord.created_at.desc()).all()
            
            # 处理在住人员费用记录
            for record in active_utility_records:
                utility_records.append({
                    'record_id': record.record_id,
                    'billing_period': record.main_record.billing_period,
                    'type': 'active',
                    'electric_fee': record.electric_fee,
                    'water_fee': record.water_fee,
                    'total_fee': record.total_fee,
                    'payable_fee': record.payable_fee,
                    'stay_days': record.stay_days,
                    'room_id': record.room_id,
                    'room_building': record.room.building if record.room else '未知',
                    'room_number': record.room.room_number if record.room else '未知',
                    'created_at': record.created_at,
                    'reduction_fee': record.user_reduction_fee
                })
            
            # 处理退宿人员费用记录
            for record in checkout_utility_records:
                billing_period = record.checkout_date.strftime('%Y-%m')
                utility_records.append({
                    'record_id': record.record_id,
                    'billing_period': billing_period,
                    'type': 'checkout',
                    'electric_fee': record.user_billing_electric_fee,
                    'water_fee': record.user_billing_water_fee,
                    'total_fee': record.user_billing_total_fee,
                    'payable_fee': record.payable_fee,
                    'stay_days': record.user_period_days,
                    'room_id': record.room_id,
                    'room_building': record.room.building if record.room else '未知',
                    'room_number': record.room.room_number if record.room else '未知',
                    'created_at': record.created_at,
                    'reduction_fee': record.user_independent_reduction + record.user_proportional_reduction,
                    'checkout_id': record.id
                })
            
            # 按账期倒序排序
            utility_records.sort(key=lambda x: (x['billing_period'], x['created_at']), reverse=True)
            
        except Exception as e:
            logging.error(f"获取用户水电费记录失败: {str(e)}")
    
    # 渲染模板并返回数据
    return render_template(
        'dorm_manage/dorm_checkout.html',
        title=f"办理退宿 - {user.name if (user and user.name) else '未知用户'}(ID:{user_id})",
        user=user,
        current_dorm=current_dorm,
        current_room=current_room,
        roommates=roommates,
        transfer_records=transfer_records,
        error_message=error_message,
        default_datetime=default_datetime,
        datetime=datetime,
        user_id=user_id,
        last_water_reading=last_water_reading,
        last_electric_reading=last_electric_reading,
        utility_records=utility_records
    )


    
# 退宿办理
@dorm_bp.route('dorm_gameout', methods=['GET'])
@login_required
@require_permission('dorm.checkout')
def dorm_gameout():
    """退宿办理页面 - 返回过滤后的活跃用户数据，支持搜索和筛选"""
    # 记录访问日志
    log_operation(
            user_id=current_user.id,
            module='dorm',
            operation_type='records',
            action="访问办理退宿页面",
            result="成功"
    )
    
    # 获取请求参数
    search_keyword = request.args.get('search_keyword', '').strip()
    department = request.args.get('department', '')
    building = request.args.get('building', '')
    gender = request.args.get('gender', '')
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 20, type=int)
    
    # 查询活跃的住宿记录
    query = Dorm.query.filter_by(status='active')
    
    # 加入用户信息的关联查询
    query = query.join(User).join(Room)
    
    # 按姓名和房间号搜索
    if search_keyword:
        query = query.filter(
            db.or_(
                User.name.ilike(f'%{search_keyword}%'),
                db.func.concat(Room.building, Room.room_number).ilike(f'%{search_keyword}%')
            )
        )
    
    # 按部门筛选
    if department:
        query = query.join(Department, User.department_id == Department.id).filter(Department.name == department)
    
    # 按楼栋筛选
    if building:
        query = query.filter(Room.building == building)
    
    # 按性别筛选
    if gender:
        query = query.filter(User.gender == gender)
    
    # 按房间ID顺序排序
    query = query.order_by(Room.id.asc())
    
    # 计算总数
    total_count = query.count()
    
    # 分页
    pagination = query.paginate(page=page, per_page=page_size, error_out=False)
    dorm_records = pagination.items
    
    # 获取所有部门选项
    departments = [d.name for d in Department.query.filter_by(status='正常').order_by(Department.name).all()]
    
    # 获取所有楼栋选项
    buildings = db.session.query(Room.building).distinct().order_by(Room.building).all()
    buildings = [bld[0] for bld in buildings]
    
    # 处理数据
    residents_data = []
    for dorm in dorm_records:
        # 获取用户信息
        user = dorm.user
        # 获取房间信息
        room = dorm.room
        
        # 计算住宿天数
        today = datetime.now()
        stay_days = (today - dorm.check_in_date).days if dorm.check_in_date else 0
        
        # 构建用户数据
        residents_data.append({
            'user_id': user.id,
            'name': user.name,
            'gender': user.gender,
            'age': user.get_age() if user.birth_date else None,
            'department': user.department,
            'position': user.position,
            'building': room.building,
            'room_number': room.room_number,
            'room_id': room.id,
            'check_in_date': dorm.check_in_date.strftime('%Y-%m-%d') if dorm.check_in_date else '',
            'stay_days': stay_days
        })
    
    # 构建分页信息
    pagination_info = {
        'total_count': total_count,
        'page_size': page_size,
        'current_page': page,
        'total_pages': pagination.pages
    }
    
    # 构建筛选信息
    filter_info = {
        'search_keyword': search_keyword,
        'department': department,
        'building': building,
        'gender': gender
    }
    
    # 渲染模板并传递数据
    return render_template(
        'dorm_manage/dorm_gameout.html',
        title="办理退宿",
        residents_data=residents_data,
        departments=departments,
        buildings=buildings,
        pagination_info=pagination_info,
        filter_info=filter_info
    )



# --------------------------
# 单人换宿路由（重构版）
# --------------------------
@dorm_bp.route('/swap', methods=['GET', 'POST'])
@login_required
@require_permission('dorm.change')
def swap():
    """单人换宿：
    - GET: 接收user_id参数，查询用户信息、房间信息和室友信息，返回可用房间列表
    - POST: 接收换宿表单数据，调用Dorm模型的change_dorm方法处理换宿
    """
    
    # 处理POST请求（提交换宿表单）
    if request.method == 'POST':
        try:
            # 从表单获取数据
            user_id = request.form.get('user_id', type=int)
            new_room_id = request.form.get('new_room_id', type=int)
            change_date = request.form.get('change_date')
            remarks = request.form.get('remarks', '')
            
            # 基础参数验证
            if not all([user_id, new_room_id, change_date]):
                # 缺少必要参数
                logging.error(f"换宿缺少必要参数（用户ID: {user_id}，目标宿舍ID: {new_room_id}，更换日期: {change_date}）")
                flash('缺少必要参数（用户ID/目标宿舍ID/更换日期）', 'danger')
                return redirect(url_for('dorm.swap', user_id=user_id))
            
            # 验证目标宿舍是否存在
            new_room = Room.query.get(new_room_id)
            if not new_room:
                # 目标宿舍不存在
                logging.error(f"目标宿舍不存在（ID: {new_room_id}）")
                flash(f'目标宿舍不存在（ID: {new_room_id}）', 'danger')
                return redirect(url_for('dorm.swap', user_id=user_id))
            
            # 验证用户是否存在
            user = User.query.get(user_id)
            if not user:
                logging.error(f"用户不存在（ID: {user_id}）")
                flash(f'用户不存在（ID: {user_id}）', 'danger')
                return redirect(url_for('dorm.manage'))
            
            # 日期格式转换
            try:
                # 尝试解析包含时间的格式
                if 'T' in change_date:
                    # 首先尝试带秒的格式
                    try:
                        change_date = datetime.strptime(change_date, '%Y-%m-%dT%H:%M:%S')
                    except ValueError:
                        # 如果失败，尝试不带秒的格式
                        change_date = datetime.strptime(change_date, '%Y-%m-%dT%H:%M')
            except ValueError:
                # 日期格式转换失败
                logging.error(f"换宿日期格式错误（用户ID: {user_id}，日期: {change_date}）")
                flash('日期格式不正确，请使用YYYY-MM-DD、YYYY-MM-DDTHH:MM或YYYY-MM-DDTHH:MM:SS', 'danger')
                return redirect(url_for('dorm.swap', user_id=user_id))
            
            # 执行更换操作
            new_allocation = Dorm.change_dorm(
                user_id=user_id,
                target_room_id=new_room_id,
                reason=remarks,
                change_date=change_date
            )
            
            # 获取旧住宿记录并验证
            old_allocation = new_allocation.prev_dorm
            if not old_allocation.room:
                # 旧住宿记录的房间不存在
                logging.error(f"用户旧住宿记录的房间无效（ID: {old_allocation.room_id}）")
                flash(f"用户旧住宿记录的房间无效（ID: {old_allocation.room_id}）", 'danger')
                raise ValueError(f"用户旧住宿记录的房间无效（ID: {old_allocation.room_id}）")
            
            # 换宿成功日志
            user_name = user.name if (user and user.name) else f"未知用户（ID:{user_id}）"
            old_room_str = f"{old_allocation.room.building}{old_allocation.room.room_number}"
            new_room_str = f"{new_room.building}{new_room.room_number}"
            log_operation(
                user_id=current_user.id,
                action=f"单人换宿成功：{user_name}从{old_room_str}→{new_room_str}",
                result="成功",
                module='dorm',
                operation_type='change',
                ip_address=request.headers.get('X-Real-IP', request.remote_addr)
            )
            
            db.session.commit()
            
            # 使用flash消息并重定向
            flash(f"宿舍更换成功：{user_name}从{old_room_str}→{new_room_str}", 'success')
            logging.info(f"宿舍更换成功：{user_name}从{old_room_str}→{new_room_str}")
            return redirect(url_for('dorm.dorm_query'))
            
        except ValueError as e:
            # 换宿验证失败日志
            user = User.query.get(user_id) if user_id else None
            user_name = user.name if (user and user.name) else f"未知用户（ID:{user_id}）"
            log_operation(
                user_id=current_user.id,
                action=f"单人换宿验证失败：{user_name}",
                result="失败",
                module='dorm',
                operation_type='change',
                ip_address=request.headers.get('X-Real-IP', request.remote_addr)
            )
            flash(str(e), 'danger')
            logging.error(f"单人换宿验证失败: {str(e)}")
            return redirect(url_for('dorm.swap', user_id=user_id))
        except Exception as e:
            db.session.rollback()
            logging.error(f"处理更换宿舍失败: {str(e)}")
            log_operation(
                user_id=current_user.id,
                action=f"处理单人换宿异常: {str(e)}",
                result="失败",
                module='dorm',
                operation_type='change',
                ip_address=request.headers.get('X-Real-IP', request.remote_addr)
            )
            flash('服务器处理失败，请稍后重试', 'danger')
            return redirect(url_for('dorm.swap', user_id=user_id))
    
    # 处理GET请求（显示换宿页面）
    # 记录访问日志
    log_operation(
        user_id=current_user.id,
        module='dorm',
        operation_type='records',
        action="访问更换宿舍页面",
        result="成功"
    )
    
    # 从URL参数获取user_id
    user_id = request.args.get('user_id', type=int)
    
    # 初始化变量
    user = None
    current_dorm = None
    current_room = None
    roommates = []
    available_rooms = []
    error_message = None
    
    try:
        # 如果提供了user_id，则查询相关信息
        if user_id:
            # 查询用户信息
            user = User.query.get(user_id)
            if not user:
                error_message = f"找不到ID为{user_id}的用户"
                logging.info(error_message)
                return render_template(
                    'dorm_manage/dorm_swap.html',
                    title="更换宿舍",
                    user=None,
                    current_dorm=None,
                    current_room=None,
                    roommates=[],
                    available_rooms=[],
                    error_message=error_message
                )
            
            # 查询用户的当前住宿记录
            current_dorm = Dorm.query.filter_by(
                user_id=user_id,
                status='active'
            ).first()
            
            if not current_dorm:
                error_message = f"用户{user.name}没有活跃的住宿记录"
                logging.info(error_message)
                return render_template(
                    'dorm_manage/dorm_swap.html',
                    title="更换宿舍",
                    user=user,
                    current_dorm=None,
                    current_room=None,
                    roommates=[],
                    available_rooms=[],
                    error_message=error_message
                )
            
            # 查询当前房间信息
            current_room = Room.query.get(current_dorm.room_id)
            if not current_room:
                error_message = "用户当前住宿的房间信息无效"
                logging.error(error_message)
                return render_template(
                    'dorm_manage/dorm_swap.html',
                    title="更换宿舍",
                    user=user,
                    current_dorm=current_dorm,
                    current_room=None,
                    roommates=[],
                    available_rooms=[],
                    error_message=error_message
                )
            
            # 查询室友信息
            roommates_dorms = Dorm.query.filter(
                Dorm.room_id == current_room.id,
                Dorm.status == 'active',
                Dorm.user_id != user_id  # 排除当前用户
            ).all()
            
            # 获取用户换宿记录
            transfer_records = []
            try:
                user_latest_dorm = Dorm.get_user_latest_dorm(user_id)
                if user_latest_dorm:
                    dorm_chain = user_latest_dorm.dorm_chain
                    for record in dorm_chain:
                        room = Room.query.get(record.room_id)
                        transfer_records.append({
                            'id': record.id,
                            'room_id': record.room_id,
                            'room_number': f"{room.building}{room.room_number}" if room else f"ID:{record.room_id}",
                            'gender_restriction': record.room.gender_restriction if record.room.gender_restriction else '-',
                            'average_age': record.room.average_age if record.room.average_age else '-',
                            'room_type': room.room_type if room and room.room_type else '',
                            'room_level': room.room_level if room and room.room_level else '',
                            'check_in_date': record.check_in_date if record.check_in_date else '',
                            'check_out_date': record.check_out_date if record.check_out_date else '',
                            'status': '在住' if record.status == 'active' else '已退宿',
                            'remarks': record.remarks or ''
                        })
            except Exception as e:
                logging.error(f"获取换宿记录失败: {str(e)}")
            #室友信息
            for roommate_dorm in roommates_dorms:
                roommate = User.query.get(roommate_dorm.user_id)
                if roommate:
                    roommates.append({
                        'id': roommate.id,
                        'name': roommate.name,
                        'age': roommate.age if roommate.age else 0,
                        'gender': roommate.gender,
                        'department': roommate.department,
                        'position': roommate.position,
                        'check_in_date': roommate_dorm.check_in_date if roommate_dorm.check_in_date else ''
                    })
            
            
    except Exception as e:
        logging.error(f"换宿页面处理异常: {str(e)}")
        error_message = f"加载失败: {str(e)}"

    # 设置默认日期时间（当前时间）
    default_datetime = datetime.now().strftime('%Y-%m-%dT%H:%M')
    
    # 获取用户水电费记录
    utility_records = []
    if user_id:
        try:
            # 获取在住人员费用记录
            active_utility_records = RoomUtilityOccupant.query.filter_by(user_id=user_id)
            active_utility_records = active_utility_records.join(RoomUtilityOccupant.main_record)
            active_utility_records = active_utility_records.order_by('billing_period').all()
            
            # 获取退宿人员费用记录
            checkout_utility_records = CheckoutUtilityRecord.query.filter_by(user_id=user_id)
            checkout_utility_records = checkout_utility_records.order_by(CheckoutUtilityRecord.created_at.desc()).all()
            
            # 处理在住人员费用记录
            for record in active_utility_records:
                utility_records.append({
                    'record_id': record.record_id,
                    'billing_period': record.main_record.billing_period,
                    'type': 'active',
                    'electric_fee': record.electric_fee,
                    'water_fee': record.water_fee,
                    'total_fee': record.total_fee,
                    'payable_fee': record.payable_fee,
                    'stay_days': record.stay_days,
                    'room_id': record.room_id,
                    'room_building': record.room.building if record.room else '未知',
                    'room_number': record.room.room_number if record.room else '未知',
                    'created_at': record.created_at,
                    'reduction_fee': record.user_reduction_fee
                })
            
            # 处理退宿人员费用记录
            for record in checkout_utility_records:
                billing_period = record.checkout_date.strftime('%Y-%m')
                utility_records.append({
                    'record_id': record.record_id,
                    'billing_period': billing_period,
                    'type': 'checkout',
                    'electric_fee': record.user_billing_electric_fee,
                    'water_fee': record.user_billing_water_fee,
                    'total_fee': record.user_billing_total_fee,
                    'payable_fee': record.payable_fee,
                    'stay_days': record.user_period_days,
                    'room_id': record.room_id,
                    'room_building': record.room.building if record.room else '未知',
                    'room_number': record.room.room_number if record.room else '未知',
                    'created_at': record.created_at,
                    'reduction_fee': record.user_independent_reduction + record.user_proportional_reduction,
                    'checkout_id': record.id
                })
            
            # 按账期倒序排序
            utility_records.sort(key=lambda x: (x['billing_period'], x['created_at']), reverse=True)
            
        except Exception as e:
            logging.error(f"获取用户水电费记录失败: {str(e)}")
    
    # 渲染模板并返回数据
    return render_template(
        'dorm_manage/dorm_swap.html',
        title=f"更换宿舍 - {user.name if (user and user.name) else '未知用户'}(ID:{user_id})",
        user=user,
        current_dorm=current_dorm,
        current_room=current_room,
        roommates=roommates,
        user_id=user_id,
        error_message=error_message,
        transfer_records=transfer_records,  # 传递换宿记录
        default_datetime=default_datetime,  # 传递默认日期时间
        datetime=datetime,  # 传递datetime模块给模板使用
        utility_records=utility_records  # 传递用户水电费记录
    )

# 单人更换宿舍页面（GET）
@dorm_bp.route('/change', methods=['GET'])
@login_required
@require_permission('dorm.change')
def change_page():
    """加载更换宿舍页面，传递必要数据给前端"""
    try:
        # 获取所有在住用户信息（过滤无效房间）
        active_dorms = Dorm.query.filter_by(
            status='active',
            check_out_date=None
        ).options(
            db.joinedload(Dorm.user),
            db.joinedload(Dorm.room)
        ).filter(
            Dorm.room != None  # 过滤掉房间无效的记录
        ).all()
        
        # 获取可用宿舍列表
        available_rooms = Room.query.filter(
            Room.status.in_(['available', 'full']),
            Room.current_occupancy < Room.capacity,
            Room.id != None
        ).all()
        
        return render_template(
            'dorm_manage/dorm_change.html',
            title=f"更换宿舍",
            active_dorms=active_dorms,
            available_rooms=available_rooms,
            current_dorm=None
        )
    except Exception as e:
        logging.error(f"加载更换宿舍页面失败: {str(e)}")
        flash("页面加载失败，请稍后重试", "danger")
        return "页面加载失败，请稍后重试", 500


# 处理单人更换宿舍提交（POST）
@dorm_bp.route('/change', methods=['POST'])
@login_required
@require_permission('dorm.change')
def change():
    """处理单人更换宿舍的表单提交"""
    try:
        # 获取前端表单数据
        user_id = request.form.get('user_id')
        new_room_id = request.form.get('new_room_id')
        change_date = request.form.get('change_date')
        remarks = request.form.get('remarks', '')
        
        
        # 基础参数验证
        if not all([user_id, new_room_id, change_date]):
            return jsonify({
                'success': False,
                'message': '缺少必要参数（用户ID/目标宿舍ID/更换日期）'
            }), 400
        
        # 验证目标宿舍是否存在
        new_room = Room.query.get(new_room_id)
        if not new_room:
            return jsonify({
                'success': False,
                'message': f'目标宿舍不存在（ID: {new_room_id}）'
            }), 400
        
        # 验证用户是否存在
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': f'用户不存在（ID: {user_id}）'
            }), 400
        
        # 日期格式转换 - 修改：支持datetime格式
        try:
            # 尝试解析包含时间的格式
            if 'T' in change_date:
                # 首先尝试带秒的格式
                try:
                    change_date = datetime.strptime(change_date, '%Y-%m-%dT%H:%M:%S')
                except ValueError:
                    # 如果失败，尝试不带秒的格式
                    change_date = datetime.strptime(change_date, '%Y-%m-%dT%H:%M')
        except ValueError:
            return jsonify({
                'success': False,
                'message': '日期格式不正确，请使用YYYY-MM-DD、YYYY-MM-DDTHH:MM或YYYY-MM-DDTHH:MM:SS'
            }), 400
        
        # 执行更换操作
        new_allocation = Dorm.change_dorm(
            user_id=user_id,
            target_room_id=new_room_id,
            reason=remarks,
            change_date=change_date  # 已改为datetime类型
        )
        
        # 获取旧住宿记录并验证
        old_allocation = new_allocation.prev_dorm
        if not old_allocation.room:
            raise ValueError(f"用户旧住宿记录的房间无效（ID: {old_allocation.room_id}）")
        # 换宿成功日志
        user_name = user.name if (user and user.name) else f"未知用户（ID:{user_id}）"
        old_room_str = f"{old_allocation.room.building}{old_allocation.room.room_number}"
        new_room_str = f"{new_room.building}{new_room.room_number}"
        log_operation(
            user_id=current_user.id,
            action=f"单人换宿成功：{user_name}从{old_room_str}→{new_room_str}",
            result="成功",
            module='dorm',
            operation_type='change',
            
            ip_address=request.headers.get('X-Real-IP', request.remote_addr)
        )
        db.session.commit()
        # 构建返回数据
        return jsonify({
            'success': True,
            'message': f"宿舍更换成功：{user_name}从{old_room_str}→{new_room_str}",
            'data': {
                'old_room': f"{old_allocation.room.building}{old_allocation.room.room_number}",
                'new_room': f"{new_room.building}{new_room.room_number}",
                'new_bed': new_allocation.bed_id
            }
        })
        
    except ValueError as e:
        # 换宿验证失败日志
        user = User.query.get(user_id) if user_id else None
        user_name = user.name if (user and user.name) else f"未知用户（ID:{user_id}）"
        log_operation(
            user_id=current_user.id,
            action=f"单人换宿验证失败：{user_name}",
            result="失败",
            module='dorm',
            operation_type='change',
            
            ip_address=request.headers.get('X-Real-IP', request.remote_addr)
        )
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logging.error(f"处理更换宿舍失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            action=f"处理单人换宿异常: {str(e)}",
            result="失败",
            module='dorm',
            operation_type='change',
            
            ip_address=request.headers.get('X-Real-IP', request.remote_addr)
        )
        return jsonify({
            'success': False,
            'message': '服务器处理失败，请稍后重试'
        }), 500


# 处理两人互换宿舍提交（POST）
@dorm_bp.route('/exchange', methods=['POST'])
@login_required
@require_permission('dorm.change')
def exchange():
    """处理两人互换宿舍的表单提交"""
    try:
        # 获取前端表单数据
        user1_id = request.form.get('user_id')
        user2_id = request.form.get('user2_id')
        exchange_date = request.form.get('change_date')
        remarks = request.form.get('remarks', '')
        
        # 基础参数验证
        if not all([user1_id, user2_id, exchange_date]):
            return jsonify({
                'success': False,
                'message': '缺少必要参数（用户1/用户2/互换日期）'
            }), 400
            
        if user1_id == user2_id:
            return jsonify({
                'success': False,
                'message': '不能与自己互换宿舍'
            }), 400
        
        # 日期格式转换 - 修改：支持datetime格式
        try:
            # 尝试解析包含时间的格式
            if 'T' in exchange_date:
                # 首先尝试带秒的格式
                try:
                    exchange_date = datetime.strptime(exchange_date, '%Y-%m-%dT%H:%M:%S')
                except ValueError:
                    # 如果失败，尝试不带秒的格式
                    exchange_date = datetime.strptime(exchange_date, '%Y-%m-%dT%H:%M')
            else:
                exchange_date = datetime.strptime(exchange_date, '%Y-%m-%d')
        except ValueError:
            return jsonify({
                'success': False,
                'message': '日期格式不正确，请使用YYYY-MM-DD、YYYY-MM-DDTHH:MM或YYYY-MM-DDTHH:MM:SS'
            }), 400
        
        # 调用模型方法执行互换
        new_alloc1, new_alloc2 = Dorm.exchange_dorm(
            user_a_id=user1_id,
            user_b_id=user2_id,
            reason=remarks,
            exchange_date=exchange_date  # 已改为datetime类型
        )

        # 验证旧房间有效性
        if not new_alloc1.prev_dorm.room:
            raise ValueError(f"用户1旧住宿记录的房间无效（ID: {new_alloc1.prev_dorm.room_id}）")
        if not new_alloc2.prev_dorm.room:
            raise ValueError(f"用户2旧住宿记录的房间无效（ID: {new_alloc2.prev_dorm.room_id}）")

        # 获取用户信息
        user1 = User.query.get(user1_id)
        user2 = User.query.get(user2_id)
        user1_name = user1.name if (user1 and user1.name) else f"ID:{user1_id}"
        user2_name = user2.name if (user2 and user2.name) else f"ID:{user2_id}"
        
        # 获取房间信息
        old_room1_str = f"{new_alloc1.prev_dorm.room.building}{new_alloc1.prev_dorm.room.room_number}"
        new_room1_str = f"{new_alloc1.room.building}{new_alloc1.room.room_number}"
        old_room2_str = f"{new_alloc2.prev_dorm.room.building}{new_alloc2.prev_dorm.room.room_number}"
        new_room2_str = f"{new_alloc2.room.building}{new_alloc2.room.room_number}"
        
        # 互换成功日志
        log_operation(
            user_id=current_user.id,
            action=f"宿舍互换成功：{user1_name}({old_room1_str})与{user2_name}({old_room2_str})互换宿舍",
            result="成功",
            module='dorm',
            operation_type='change',
            
            ip_address=request.headers.get('X-Real-IP', request.remote_addr)
        )
        db.session.commit()       
        # 构建返回数据
        return jsonify({
            'success': True,
            'message': f"宿舍互换成功：{user1_name}({old_room1_str})与{user2_name}({old_room2_str})互换宿舍",
            'data': {
                'user1': {
                    'old_room': f"{new_alloc1.prev_dorm.room.building}{new_alloc1.prev_dorm.room.room_number}",
                    'new_room': f"{new_alloc1.room.building}{new_alloc1.room.room_number}",
                    'new_bed': new_alloc1.bed_id
                },
                'user2': {
                    'old_room': f"{new_alloc2.prev_dorm.room.building}{new_alloc2.prev_dorm.room.room_number}",
                    'new_room': f"{new_alloc2.room.building}{new_alloc2.room.room_number}",
                    'new_bed': new_alloc2.bed_id
                }
            }
        })
        
    except ValueError as e:
        # 互换验证失败日志
        user1 = User.query.get(user1_id) if user1_id else None
        user2 = User.query.get(user2_id) if user2_id else None
        user1_name = user1.name if (user1 and user1.name) else f"ID:{user1_id}"
        user2_name = user2.name if (user2 and user2.name) else f"ID:{user2_id}"
        
        log_operation(
            user_id=current_user.id,
            action=f"宿舍互换验证失败：{user1_name}与{user2_name}",
            result="失败",
            module='dorm',
            operation_type='change',
            
            ip_address=request.headers.get('X-Real-IP', request.remote_addr)
        )
        return jsonify({'success': False, 'message': str(e)}), 400
    except Exception as e:
        db.session.rollback()
        logging.error(f"处理宿舍互换失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            action=f"处理宿舍互换异常: {str(e)}",
            result="失败",
            module='dorm',
            operation_type='change',
            
            ip_address=request.headers.get('X-Real-IP', request.remote_addr)
        )
        return jsonify({
            'success': False,
            'message': '服务器处理失败，请稍后重试'
        }), 500
    


# 获取指定日期的减免额度
@dorm_bp.route('/get_subsidy_by_date', methods=['GET'])
@login_required
@require_permission('dorm.checkout')
def get_subsidy_by_date():
    """根据指定日期获取用户和房间的减免额度"""
    # 获取请求参数
    user_id = request.args.get('user_id')
    room_id = request.args.get('room_id')
    target_date = request.args.get('target_date')
    
    if not user_id or not room_id or not target_date:
        return jsonify({'success': False, 'message': '参数不完整'}), 400
    
    try:
        # 解析目标日期，提取年月，兼容带秒和不带秒的格式
        try:
            # 尝试解析带秒的格式
            target_datetime = datetime.strptime(target_date, '%Y-%m-%dT%H:%M:%S')
        except ValueError:
            # 如果失败，尝试解析不带秒的格式
            target_datetime = datetime.strptime(target_date, '%Y-%m-%dT%H:%M')
        target_month = target_datetime.strftime('%Y-%m')
        
        # 初始化减免额度数据
        subsidy_info = {
            'room_electric_reduction': 0.0,
            'room_water_reduction': 0.0,
            'room_amount_reduction': 0.0,
            'user_amount_reduction': 0.0
        }
        
        # 获取房间水电按用量减免的所有有效补贴，并确保补贴生效日期小于等于目标日期
        room_usage_subsidies = FeeSubsidy.query.filter(
            FeeSubsidy.room_id == room_id,
            FeeSubsidy.fee_type == "房间水电按用量减免",
            FeeSubsidy.is_enabled == True,
            FeeSubsidy.effective_date <= target_datetime  # 时间验证：补贴生效日期必须小于等于退宿日期
        ).all()
        
        # 累计所有房间级水电用量减免的剩余可用额度
        for subsidy in room_usage_subsidies:
            try:
                remaining = FeeSubsidyUsage.get_remaining_usage(subsidy.id, target_month)
                subsidy_info['room_electric_reduction'] += remaining['remaining_electric']
                subsidy_info['room_water_reduction'] += remaining['remaining_water']
            except Exception as e:
                logging.warning(f"获取房间用量补贴{subsidy.id}剩余额度失败: {str(e)}")
        
        # 获取房间水电按金额减免的所有有效补贴，并确保补贴生效日期小于等于目标日期
        room_amount_subsidies = FeeSubsidy.query.filter(
            FeeSubsidy.room_id == room_id,
            FeeSubsidy.fee_type == "房间水电按金额减免",
            FeeSubsidy.is_enabled == True,
            FeeSubsidy.effective_date <= target_datetime  # 时间验证：补贴生效日期必须小于等于退宿日期
        ).all()
        
        # 累计所有房间级金额减免的剩余可用额度
        for subsidy in room_amount_subsidies:
            try:
                remaining = FeeSubsidyUsage.get_remaining_usage(subsidy.id, target_month)
                subsidy_info['room_amount_reduction'] += remaining['remaining_amount']
            except Exception as e:
                logging.warning(f"获取房间金额补贴{subsidy.id}剩余额度失败: {str(e)}")
        
        # 获取当前用户的减免额度，并确保补贴生效日期小于等于目标日期
        user_subsidies = FeeSubsidy.query.filter(
            FeeSubsidy.user_id == user_id,
            FeeSubsidy.fee_type == "住宿补贴",
            FeeSubsidy.is_enabled == True,
            FeeSubsidy.effective_date <= target_datetime  # 时间验证：补贴生效日期必须小于等于退宿日期
        ).all()
        
        for subsidy in user_subsidies:
            try:
                remaining = FeeSubsidyUsage.get_remaining_usage(subsidy.id, target_month)
                subsidy_info['user_amount_reduction'] += remaining['remaining_amount']
            except Exception as e:
                logging.warning(f"获取用户补贴{subsidy.id}剩余额度失败: {str(e)}")
        
        return jsonify({
            'success': True,
            'data': subsidy_info
        })
        
    except ValueError as e:
        logging.error(f"日期格式错误: {str(e)}")
        return jsonify({'success': False, 'message': '日期格式错误'}), 400
    except Exception as e:
        logging.error(f"获取减免额度失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': '获取减免额度失败'
        }), 500
    

