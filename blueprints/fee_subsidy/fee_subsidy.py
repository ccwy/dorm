from flask import Blueprint, request, jsonify, render_template, flash, redirect, url_for
from flask_login import login_required, current_user
import logging
from utils.db import db
from models.fee_subsidy.fee_subsidy import FeeSubsidy
from models.user.user import User
from models.department.department import Department
from models.room.room import Room
from models.system_config.system_config import SystemConfig
from sqlalchemy import or_, and_
from utils.log import log_operation  # 导入日志工具
# 导入权限装饰器
from utils.auth import require_permission

# 创建蓝图
fee_subsidy_bp = Blueprint('fee_subsidy', __name__, url_prefix='/fee_subsidy')

# 添加补贴页面
@fee_subsidy_bp.route('/fee_subsidy_add')
@login_required
@require_permission('fee_subsidy.create')
def fee_subsidy_add():
    """加载添加补贴页面"""
    # 获取允许的费用类型
    all_types = SystemConfig.get_config_value('ALLOWANCE_TYPES', [])
    filtered_types = []
    for fee_type in all_types:
        if fee_type == '房间水电按用量减免' and not SystemConfig.get_config_value('FEE_METER_reduction', True):
            continue
        elif fee_type == '房间水电按金额减免' and not SystemConfig.get_config_value('FEE_ROOM_FEE', True):
            continue
        elif fee_type == '住宿补贴' and not SystemConfig.get_config_value('FEE_USER_FEE', True):
            continue
        elif fee_type == '外宿补贴' and not SystemConfig.get_config_value('lodging_allowance', True):
            continue
        filtered_types.append(fee_type)
    
    # 记录访问日志
    log_operation(
        user_id=current_user.id,
        module='feesubsidy',
        operation_type='records',
        action="访问添加补贴页面",
        result="成功"
    )
    return render_template('fee_subsidy/fee_subsidy_add.html', title=f"添加补贴", allowed_fee_types=filtered_types)

# 补贴管理页面
@fee_subsidy_bp.route('/fee_subsidy_index')
@login_required
@require_permission('fee_subsidy.view')
def fee_subsidy_index():
    """加载补贴管理页面"""
    try:
        # 查询所有不重复的楼栋名称（过滤空值和空字符串）
        buildings = db.session.query(Room.building).distinct()
        building_list = [b[0] for b in buildings if b[0] and b[0].strip()]
        # 对楼栋列表进行排序
        building_list.sort()
    except Exception as e:
        # 记录错误日志
        logging.error(f'获取楼栋列表失败：{str(e)}')
        building_list = []
    
    # 获取允许的费用类型
    all_types = SystemConfig.get_config_value('ALLOWANCE_TYPES', [])
    filtered_types = []
    for fee_type in all_types:
        if fee_type == '房间水电按用量减免' and not SystemConfig.get_config_value('FEE_METER_reduction', True):
            continue
        elif fee_type == '房间水电按金额减免' and not SystemConfig.get_config_value('FEE_ROOM_FEE', True):
            continue
        elif fee_type == '住宿补贴' and not SystemConfig.get_config_value('FEE_USER_FEE', True):
            continue
        elif fee_type == '外宿补贴' and not SystemConfig.get_config_value('lodging_allowance', True):
            continue
        filtered_types.append(fee_type)
    
    # 记录访问日志
    log_operation(
        user_id=current_user.id,
        module='feesubsidy',
        operation_type='records',
        action="访问补贴管理页面",
        result="成功"
    )
    return render_template('fee_subsidy/fee_subsidy_index.html', title=f"补贴管理", buildings=building_list, allowed_fee_types=filtered_types)

# 补贴历史记录页面
@fee_subsidy_bp.route('/fee_subsidy_history')
@login_required
@require_permission('fee_subsidy.view')
def fee_subsidy_history():
    """加载补贴历史记录页面"""
    try:
        # 查询所有不重复的楼栋名称（过滤空值和空字符串）
        buildings = db.session.query(Room.building).distinct()
        building_list = [b[0] for b in buildings if b[0] and b[0].strip()]
        # 对楼栋列表进行排序
        building_list.sort()
    except Exception as e:
        # 记录错误日志
        logging.error(f'获取楼栋列表失败：{str(e)}')
        building_list = []
    
    # 获取允许的费用类型
    all_types = SystemConfig.get_config_value('ALLOWANCE_TYPES', [])
    filtered_types = []
    for fee_type in all_types:
        if fee_type == '房间水电按用量减免' and not SystemConfig.get_config_value('FEE_METER_reduction', True):
            continue
        elif fee_type == '房间水电按金额减免' and not SystemConfig.get_config_value('FEE_ROOM_FEE', True):
            continue
        elif fee_type == '住宿补贴' and not SystemConfig.get_config_value('FEE_USER_FEE', True):
            continue
        elif fee_type == '外宿补贴' and not SystemConfig.get_config_value('lodging_allowance', True):
            continue
        filtered_types.append(fee_type)
    
    # 记录访问日志
    log_operation(
        user_id=current_user.id,
        module='feesubsidy',
        operation_type='records',
        action="访问补贴历史记录页面",
        result="成功"
    )
    return render_template('fee_subsidy/fee_subsidy_history.html', title=f"补贴历史查询", buildings=building_list, allowed_fee_types=filtered_types)

# 增加记录接口
@fee_subsidy_bp.route('/add', methods=['POST'])
@login_required
@require_permission('fee_subsidy.create')
def add_record():
    try:
        data = request.form.to_dict()
        # 将数值字段从字符串转换
        if data.get('user_id'):
            data['user_id'] = int(data['user_id'])
        if data.get('room_id'):
            data['room_id'] = int(data['room_id'])
        if data.get('amount'):
            data['amount'] = float(data['amount'])
        if data.get('electric_reduction'):
            data['electric_reduction'] = float(data['electric_reduction'])
        if data.get('water_reduction'):
            data['water_reduction'] = float(data['water_reduction'])
        if data.get('is_enabled'):
            data['is_enabled'] = data['is_enabled'].lower() in ('true', '1', 'yes')
        all_types = SystemConfig.get_config_value('ALLOWANCE_TYPES', [])
        
        # 过滤费用类型
        filtered_types = []
        for fee_type in all_types:
            if fee_type == '房间水电按用量减免' and not SystemConfig.get_config_value('FEE_METER_reduction', True):
                continue
            elif fee_type == '房间水电按金额减免' and not SystemConfig.get_config_value('FEE_ROOM_FEE', True):
                continue
            elif fee_type == '住宿补贴' and not SystemConfig.get_config_value('FEE_USER_FEE', True):
                continue
            elif fee_type == '外宿补贴' and not SystemConfig.get_config_value('lodging_allowance', True):
                continue
            filtered_types.append(fee_type)
        
        # 验证费用类型
        if data.get('fee_type') not in filtered_types:
            # 记录日志
            logging.error(f'添加补贴记录失败：不支持的费用类型 - {data.get("fee_type")}')
            raise ValueError(f"不支持的费用类型: {data.get('fee_type')}")
            
        
        # 住宿补贴验证
        if data.get('fee_type') == '住宿补贴':
            user_id = data.get('user_id')
            if not user_id:
                # 记录日志
                logging.error('添加住宿补贴失败：未指定用户ID')
                raise ValueError("添加住宿补贴必须指定用户ID")
    
            # 通过Dorm中间表查询用户是否有住宿记录
            from models.dorm.dorm import Dorm
            has_accommodation = Dorm.query.filter(
                Dorm.user_id == user_id,
                Dorm.status.in_(['active', 'checked_in'])
            ).first() is not None
    
            if not has_accommodation:
                # 记录日志
                logging.error(f'添加住宿补贴失败：用户{user_id}无住宿记录')
                raise ValueError("用户无住宿记录，无法添加住宿补贴")
            
            # 检查是否已有外宿补贴
            has_lodging_allowance = FeeSubsidy.query.filter(
                FeeSubsidy.user_id == user_id,
                FeeSubsidy.fee_type == '外宿补贴',
                FeeSubsidy.is_enabled == True
            ).first() is not None
            
            if has_lodging_allowance:
                # 记录日志
                logging.error(f'添加住宿补贴失败：用户{user_id}已有外宿补贴')
                raise ValueError("用户已有外宿补贴，不能同时申请住宿补贴")
  
        # 外宿补贴验证
        if data.get('fee_type') == '外宿补贴':
            user_id = data.get('user_id')
            if not user_id:
                # 记录日志
                logging.error('添加外宿补贴失败：未指定用户ID')
                raise ValueError("添加外宿补贴必须指定用户ID")
            
            # 检查是否已有住宿补贴
            has_accommodation_subsidy = FeeSubsidy.query.filter(
                FeeSubsidy.user_id == user_id,
                FeeSubsidy.fee_type == '住宿补贴',
                FeeSubsidy.is_enabled == True
            ).first() is not None
            
            if has_accommodation_subsidy:
                # 记录日志
                logging.error(f'添加外宿补贴失败：用户{user_id}已有住宿补贴')
                raise ValueError("用户已有住宿补贴，不能同时申请外宿补贴")
        
        # 添加记录
        data.pop('saveAndContinue', None)
        new_subsidy = FeeSubsidy.add_fee(data)
        db.session.commit()
        
        # 记录添加成功日志
        log_operation(
            user_id=current_user.id,
            module='feesubsidy',
            operation_type='feesub_add',
            action=f"添加{data.get('fee_type')}类型补贴，金额: {data.get('amount')}",
            result="成功"
        )
        # 记录日志
        logging.info(f"添加{data.get('fee_type')}类型补贴，金额: {data.get('amount')}")
        
        # 根据 saveAndContinue 参数决定重定向目标
        save_and_continue = request.form.get('saveAndContinue')
        flash('记录添加成功', 'success')
        if save_and_continue:
            return redirect(url_for('fee_subsidy.fee_subsidy_add'))
        else:
            return redirect(url_for('fee_subsidy.fee_subsidy_index'))
    
    except Exception as e:
        db.session.rollback()
        # 记录日志
        logging.error(f'添加补贴记录失败：{str(e)}')
        flash(f'添加补贴记录失败：{str(e)}', 'danger')
        return redirect(url_for('fee_subsidy.fee_subsidy_add'))
    

# 前端页面展示接口（支持筛选和搜索）
@fee_subsidy_bp.route('/list', methods=['GET'])
@login_required
@require_permission('fee_subsidy.view')
def get_list():
    try:
        # 获取查询参数
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        billing_period = request.args.get('billing_period')
        department = request.args.get('department')
        fee_type = request.args.get('fee_type')
        building = request.args.get('building')  # 楼栋筛选
        search = request.args.get('search', '')  # 用于搜索姓名、部门、房间号
        
        # 1. 获取所有费用类型，并仅过滤受系统开关控制的类型
        all_types = SystemConfig.get_config_value('ALLOWANCE_TYPES', [])
        allowed_types = []
        
        # 需要受系统开关控制的类型列表及其对应配置键
        controlled_types = {
            '房间水电按用量减免': 'FEE_METER_reduction',
            '房间水电按金额减免': 'FEE_ROOM_FEE',
            '住宿补贴': 'FEE_USER_FEE',
            '外宿补贴': 'lodging_allowance'
        }
        
        for type_item in all_types:
            # 检查当前类型是否是受控制的类型
            if type_item in controlled_types:
                # 是受控制的类型，检查对应配置
                config_key = controlled_types[type_item]
                # 配置为True才允许显示
                if SystemConfig.get_config_value(config_key, True):
                    allowed_types.append(type_item)
            else:
                # 非受控类型，直接允许显示
                allowed_types.append(type_item)
        
        # 基础查询：只查询启用的记录，关联用户表和房间表
        query = FeeSubsidy.query\
            .outerjoin(User, FeeSubsidy.user_id == User.id)\
            .outerjoin(Room, FeeSubsidy.room_id == Room.id)\
            .filter(FeeSubsidy.is_enabled == True)\
            .filter(FeeSubsidy.fee_type.in_(allowed_types))  # 关键过滤条件
        
        # 2. 账期筛选
        if billing_period:
            query = query.filter(FeeSubsidy.billing_period == billing_period)
        
        # 3. 费用类型筛选（结合系统配置验证）
        if fee_type:
            # 如果请求的类型不在允许列表中，直接返回空结果
            if fee_type not in allowed_types:
                
                # 记录日志
                logging.info(f'调用补贴列表接口，筛选类型: {fee_type}，无符合条件记录')
                return jsonify({
                    'success': True,
                    'data': {
                        'records': [],
                        'total': 0,
                        'page': page,
                        'per_page': per_page,
                        'pages': 0
                    }
                })
            query = query.filter(FeeSubsidy.fee_type == fee_type)
        
        # 4. 部门筛选
        if department:
            query = query.join(Department, User.department_id == Department.id).filter(Department.name == department)
        
        # 5. 楼栋筛选
        if building:
            query = query.filter(Room.building == building, Room.building.isnot(None))
        
        # 5. 搜索功能
        if search:
            # 确保Department表已关联（用于部门搜索）
            query = query.outerjoin(Department, User.department_id == Department.id)
            # 构建房间号搜索条件：拼接楼栋+房间号（如"A-101"）
            room_search_condition = and_(
                Room.building.isnot(None),
                Room.room_number.isnot(None),
                (Room.building + '-' + Room.room_number).like(f'%{search}%')
            )
            
            # 构建用户姓名搜索条件，添加非空判断
            user_name_condition = and_(
                User.name.isnot(None),
                User.name.like(f'%{search}%')
            )
            
            # 构建部门搜索条件，添加非空判断
            department_condition = and_(
                Department.name.isnot(None),
                Department.name.like(f'%{search}%')
            )
            
            query = query.filter(
                or_(
                    user_name_condition,  # 匹配用户姓名
                    department_condition,  # 匹配用户部门
                    room_search_condition  # 匹配房间号
                )
            )
        
        # 执行查询并分页
        pagination = query.order_by(FeeSubsidy.create_time.desc()).paginate(page=page, per_page=per_page)
        
        # 处理结果，添加用户信息和房间信息
        records = []
        for item in pagination.items:
            record_dict = item.to_dict()
            # 添加用户信息
            if item.user_id:
                user = User.query.get(item.user_id)
                if user:
                    record_dict.update({
                        'user_id': item.user_id,
                        'user_name': user.name,
                        'user_department': user.department,
                        'user_position': user.position,
                        'user_student_id': user.student_id
                    })
            # 添加房间信息
            if item.room_id:
                room = Room.query.get(item.room_id)
                if room:
                    record_dict.update({
                        'room_id': item.room_id,
                        'room_full_number': f"{room.building}{room.room_number}"
                    })
            records.append(record_dict)
        
        # 记录日志
        logging.info(f'调用补贴列表接口，查询到{len(records)}条记录')
        return jsonify({
            'success': True,
            'data': {
                'records': records,
                'total': pagination.total,
                'page': page,
                'per_page': per_page,
                'pages': pagination.pages
            }
        })
    except Exception as e:

        # 记录日志
        logging.error(f'调用补贴列表接口失败：{str(e)}')
        return jsonify({
            'success': False,
            'message': f"获取补贴列表失败: {str(e)}"
        }), 500
    

# 获取账期接口
@fee_subsidy_bp.route('/periods', methods=['GET'])
@login_required
@require_permission('fee_subsidy.view')
def get_periods():
    try:
        # 查询所有不重复的账期并按时间排序
        periods = db.session.query(FeeSubsidy.billing_period)\
                            .distinct()\
                            .order_by(FeeSubsidy.billing_period.desc())\
                            .all()
        
        # 提取账期列表
        period_list = [p[0] for p in periods]
        # 记录日志
        logging.info(f'调用账期接口，获取到{len(period_list)}个账期')

        return jsonify({
            'success': True,
            'data': period_list
        })
    except Exception as e:

        # 记录日志
        logging.error(f'调用账期接口失败：{str(e)}')
        return jsonify({
            'success': False,
            'message': f"获取账期失败: {str(e)}"
        }), 500

@fee_subsidy_bp.route('/history', methods=['GET'])
@login_required
@require_permission('fee_subsidy.view')
def get_history():
    try:
        # 获取分页参数
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('page_size', request.args.get('per_page', 10)))
        
        # 获取筛选参数
        billing_period = request.args.get('billing_period')
        department = request.args.get('department')
        fee_type = request.args.get('fee_type')
        building = request.args.get('building')  # 楼栋筛选
        search = request.args.get('search')
        
        # 基础查询
        query = FeeSubsidy.query.outerjoin(
            User, 
            FeeSubsidy.user_id == User.id
        ).outerjoin(
            Room,
            FeeSubsidy.room_id == Room.id
        )
        
        # 筛选条件
        if billing_period:
            query = query.filter(FeeSubsidy.billing_period == billing_period)
        
        if fee_type:
            query = query.filter(FeeSubsidy.fee_type == fee_type)
        
        if department:
            query = query.join(Department, User.department_id == Department.id).filter(
                and_(User.id.isnot(None), Department.name == department)
            )
        
        # 楼栋筛选
        if building:
            query = query.filter(
                and_(Room.id.isnot(None), Room.building == building)
            )
        
        # 状态筛选
        is_enabled = request.args.get('is_enabled')
        if is_enabled is not None:
            query = query.filter(FeeSubsidy.is_enabled == (is_enabled.lower() == 'true'))
            
        # 搜索条件
        if search:
            # 房间号搜索条件
            room_search_condition = and_(
                Room.id.isnot(None),
                Room.building.isnot(None),
                Room.room_number.isnot(None),
                (Room.building + '-' + Room.room_number).like(f'%{search}%')
            )
            
            # 用户姓名搜索条件添加非空判断
            user_name_condition = and_(
                User.id.isnot(None),
                User.name.isnot(None),
                User.name.like(f'%{search}%')
            )
            
            query = query.filter(
                or_(
                    user_name_condition,
                    FeeSubsidy.change_reason.like(f'%{search}%'),
                    room_search_condition
                )
            )
        
        # 执行分页查询
        pagination = query.order_by(FeeSubsidy.create_time.desc()).paginate(
            page=page, 
            per_page=per_page,
            error_out=False
        )
        
        # 处理结果
        records = []
        for item in pagination.items:
            record_dict = {
                'id': item.id,
                'fee_type': item.fee_type,
                'amount': float(item.amount) if item.amount else None,
                'electric_reduction': float(item.electric_reduction) if item.electric_reduction else None,
                'water_reduction': float(item.water_reduction) if item.water_reduction else None,
                'effective_date': item.effective_date.isoformat() if item.effective_date else None,
                'is_enabled': item.is_enabled,
                'create_time': item.create_time.isoformat() if item.create_time else None,
                'update_time': item.update_time.isoformat() if item.update_time else None,
                'operator_id': item.operator_id,
                'change_reason': item.change_reason,
                'billing_period': item.billing_period,
                'billing_start_date': item.billing_start_date.isoformat() if item.billing_start_date else None,
                'billing_end_date': item.billing_end_date.isoformat() if item.billing_end_date else None,
                'user_id': item.user_id,
                'room_id': item.room_id
            }
            
            # 添加用户信息
            if item.user:
                record_dict.update({
                    'user_name': item.user.name,
                    'user_department': item.user.department,
                    'user_position': item.user.position,
                    'user_student_id': item.user.student_id
                })
            else:
                record_dict.update({
                    'user_name': None,
                    'user_department': None,
                    'user_position': None,
                    'user_student_id': None
                })
            
            # 房间号显示
            if item.room:
                record_dict['room_full_number'] = f"{item.room.building}{item.room.room_number}"
            else:
                record_dict['room_full_number'] = None
            
            records.append(record_dict)
        
       
        # 记录日志
        logging.info(f'调用补贴历史接口，查询到{len(records)}条记录')
        return jsonify({
            'success': True,
            'data': {
                'records': records,
                'total': pagination.total,
                'page': page,
                'per_page': per_page,
                'pages': pagination.pages
            }
        })
    except Exception as e:

        # 记录日志
        logging.error(f'调用补贴历史接口失败：{str(e)}')
        return jsonify({
            'success': False,
            'message': f"获取补贴历史失败: {str(e)}"
        }), 500

# 禁用接口
@fee_subsidy_bp.route('/delete/<int:subsidy_id>', methods=['POST'])
@login_required
@require_permission('fee_subsidy.delete')
def delete_record(subsidy_id):
    try:
        operator_id = current_user.id
        reason = request.form.get('reason', '手动禁用')
        
        if not operator_id:
           
            # 记录日志
            logging.error(f'禁用补贴失败：操作人ID不能为空，操作人ID：{operator_id}')    
            return jsonify({
                'success': False,
                'message': '操作人ID不能为空'
            }), 400
        
        # 调用模型的禁用方法
        result = FeeSubsidy.disabled_subsidy(subsidy_id, operator_id, reason)
        db.session.commit()
        
        if result:
            # 获取被禁用的记录信息
            subsidy = FeeSubsidy.query.get(subsidy_id)
            fee_type = subsidy.fee_type if subsidy else "未知类型"
            
            log_operation(
                user_id=current_user.id,
                module='feesubsidy',
                operation_type='delete',
                action=f"禁用ID为{subsidy_id}的{fee_type}类型补贴，原因: {reason}",
                result="成功"
            )
            # 记录日志
            logging.info(f'禁用补贴成功：ID为{subsidy_id}的记录已禁用，操作人ID：{operator_id}，禁用原因：{reason}')
            flash('记录禁用成功', 'success')
            return redirect(url_for('fee_subsidy.fee_subsidy_index'))
        else:
            
            # 记录日志
            logging.error(f'禁用补贴失败：ID为{subsidy_id}的记录不存在')
            flash('记录不存在', 'danger')
            return redirect(url_for('fee_subsidy.fee_subsidy_index'))
    except Exception as e:
        db.session.rollback()
        
        # 记录日志
        logging.error(f'禁用补贴失败：ID为{subsidy_id}的记录不存在，{str(e)}')  
        flash(f'禁用补贴失败：{str(e)}', 'danger')
        return redirect(url_for('fee_subsidy.fee_subsidy_index'))

# 批量禁用接口
@fee_subsidy_bp.route('/batch-delete', methods=['POST'])
@login_required
@require_permission('fee_subsidy.delete')
def batch_delete():
    try:
        data = request.form.to_dict()
        ids_str = data.get('ids', '')
        ids = [int(x) for x in ids_str.split(',') if x.strip()] if ids_str else []
        operator_id = current_user.id
        reason = data.get('reason', '批量禁用')
        
        if not ids or not operator_id:
            
            # 记录日志
            logging.error(f'批量禁用补贴失败：记录ID列表和操作人ID不能为空，记录ID列表：{ids}，操作人ID：{operator_id}')
            flash('记录ID列表和操作人ID不能为空', 'danger')
            return redirect(url_for('fee_subsidy.fee_subsidy_index'))
        
        success_count = 0
        fail_count = 0
        
        for subsidy_id in ids:
            try:
                result = FeeSubsidy.disabled_subsidy(subsidy_id, operator_id, reason)
                if result:
                    success_count += 1
                else:
                    fail_count += 1
            except:
                fail_count += 1
                db.session.rollback()
        
        db.session.commit()
        
        log_operation(
            user_id=current_user.id,
            module='feesubsidy',
            operation_type='delete',
            action=f"批量禁用补贴，共{len(ids)}条，成功{success_count}条，失败{fail_count}条，原因: {reason}",
            result="成功" if success_count > 0 else "失败"
        )
        # 记录日志
        logging.info(f'批量禁用补贴成功：共{len(ids)}条，成功{success_count}条，失败{fail_count}条，操作人ID：{operator_id}，禁用原因：{reason}')
        flash(f'批量禁用完成，成功{success_count}条，失败{fail_count}条', 'success')
        return redirect(url_for('fee_subsidy.fee_subsidy_index'))
    except Exception as e:
        db.session.rollback()
        
        # 记录日志
        logging.error(f'批量禁用补贴失败：{str(e)}')
        flash(f'批量禁用补贴失败：{str(e)}', 'danger')
        return redirect(url_for('fee_subsidy.fee_subsidy_index'))

# 清空当期接口
@fee_subsidy_bp.route('/clear-current-period', methods=['POST'])
@login_required
@require_permission('fee_subsidy.delete')
def clear_current_period():
    try:
        billing_period = request.form.get('billing_period')
        operator_id = current_user.id
        
        if not billing_period or not operator_id:
            
            # 记录日志
            logging.error(f'清空当期补贴失败：账期和操作人ID不能为空，账期：{billing_period}，操作人ID：{operator_id}')
            flash('账期和操作人ID不能为空', 'danger')
            return redirect(url_for('fee_subsidy.fee_subsidy_index'))
        
        # 查询当前账期的所有记录
        records = FeeSubsidy.query.filter_by(billing_period=billing_period).all()
        
        if not records:
            
            # 记录日志
            logging.info(f'清空当期补贴成功：当前账期没有记录，账期：{billing_period}，操作人ID：{operator_id}')
            flash('当前账期没有记录', 'info')
            return redirect(url_for('fee_subsidy.fee_subsidy_index'))
        
        # 批量禁用当前账期的记录
        for record in records:
            FeeSubsidy.disabled_subsidy(record.id, operator_id, f'清空{billing_period}账期记录')
        
        db.session.commit()
        
        log_operation(
            user_id=current_user.id,
            module='feesubsidy',
            operation_type='delete',
            action=f"成功清空{ billing_period }账期的{ len(records) }条补贴记录",
            result="成功"
        )
        # 记录日志
        logging.info(f'清空当期补贴成功：成功清空{len(records)}条{billing_period}账期记录，操作人ID：{operator_id}')
        flash(f'成功清空{len(records)}条{billing_period}账期记录', 'success')
        return redirect(url_for('fee_subsidy.fee_subsidy_index'))
    except Exception as e:
        db.session.rollback()
        
        # 记录日志
        logging.error(f'清空当期补贴失败：{str(e)}')
        flash(f'清空当期补贴失败：{str(e)}', 'danger')
        return redirect(url_for('fee_subsidy.fee_subsidy_index'))

# 获取所有部门接口
@fee_subsidy_bp.route('/departments', methods=['GET'])
@login_required
@require_permission('fee_subsidy.view')
def get_departments():
    """获取所有不重复的部门列表"""
    try:
        # 查询所有不重复且非空的部门
        department_list = [d.name for d in Department.query.filter_by(status='正常').order_by(Department.name).all()]
        
        
        
        return jsonify({
            'success': True,
            'data': department_list
        })
    except Exception as e:
        
        logging.error(f"获取部门列表失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取部门列表失败: {str(e)}'
        }), 500

# 获取房间列表接口
@fee_subsidy_bp.route('/rooms', methods=['GET'])
@login_required
@require_permission('fee_subsidy.view')
def get_rooms():
    """获取所有房间列表，包含完整房间号"""
    try:
        rooms = Room.query.all()
        
        # 格式化房间数据，包含完整房间号
        room_list = [
            {
                'id': room.id,
                'full_number': f"{room.building}-{room.room_number}",
                'building': room.building,
                'room_number': room.room_number,
                'room_type': room.room_type
            }
            for room in rooms
        ]
        
        # 记录日志
        logging.info(f'获取房间列表成功：共{len(room_list)}个房间，操作人ID：{current_user.id}')
        return jsonify({
            'success': True,
            'data': room_list
        })
    except Exception as e:
        
        logging.error(f"获取房间列表失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'获取房间列表失败: {str(e)}'
        }), 500
