from flask import request, jsonify
from datetime import datetime, timedelta  # 修改：移除date导入
from models.dorm.dorm import Dorm
from models.user.user import User
from models.department.department import Department
from models.room.room import Room
from models.utility.utility_room_meter import UtilityMeterReading
from utils.db import db
import traceback
from .dorm import dorm_bp  # 导入主蓝图
import logging
from flask_login import current_user, login_required
# 导入require_permission装饰器
from utils.auth import require_permission

# 端点注册路径是/dorm ，没有/api这个端点
# 直接使用主蓝图注册路由，无需创建新蓝图
@dorm_bp.route('/resident-details', methods=['POST'])
@login_required
def get_resident_details():
    """
    查询当前在住人员明细及包含历史房间的住宿天数
    支持筛选：用户ID、姓名、房间号、部门、性别
    返回数据包含当前住宿信息、历史房间记录及总住宿天数
    """
    # 记录API调用开始
    request_id = request.headers.get('X-Request-ID', 'unknown')
    user_id = current_user.id if current_user.is_authenticated else 'anonymous'
    logging.info(
        f"API调用开始 [/dorm/resident-details] "  # 修改：修正路径
        f"请求ID: {request_id}, "
        f"操作用户ID: {user_id}, "
        f"客户端IP: {request.remote_addr}, "
        f"请求时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    try:
        # 安全获取请求数据（修复KeyError问题）
        data = {}
        try:
            # 尝试解析JSON数据，不使用silent参数避免版本兼容问题
            json_data = request.get_json()
            if isinstance(json_data, dict):
                data = json_data
        except Exception as e:
            logging.warning(
                f"JSON解析失败 [请求ID: {request_id}] "
                f"错误原因: {str(e)}, 尝试解析表单数据"
            )
            # 解析表单数据作为备选
            form_data = request.form.to_dict()
            if form_data:
                data = form_data
        
        # 获取请求参数
        user_id_filter = data.get('user_id')
        name_filter = data.get('name', '').strip()
        room_number_filter = data.get('room_number', '').strip()
        # 新的合并搜索参数
        search_query = data.get('searchQuery', '').strip()
        department_filter = data.get('department', '').strip()
        gender_filter = data.get('gender', '').strip()
        # 检查是否需要查询水电表读数
        query_meter_readings = str(data.get('queryMeterReadings', '')).lower() in ['true', '1', 'yes']
        
        # 执行查询条件
        current_dorms_query = db.session.query(Dorm).filter(
            Dorm.status == 'active',
            Dorm.check_out_date.is_(None)
        )

        # 如果有搜索查询，设置为姓名或房间号筛选
        if search_query and not name_filter and not room_number_filter:
            # 使用or_来实现姓名或房间号匹配
            from sqlalchemy import or_
            current_dorms_query = current_dorms_query.join(
                User, Dorm.user_id == User.id
            ).join(
                Room, Dorm.room_id == Room.id
            ).filter(
                or_(
                    User.name.ilike(f'%{search_query}%'),
                    Room.room_number.ilike(f'%{search_query}%')
                )
            )
            # 标记已经应用了搜索查询
            search_applied = True
        else:
            search_applied = False
        
        # 记录完整筛选条件
        logging.info(
            f"处理查询请求 [请求ID: {request_id}] "
            f"筛选条件 - "
            f"用户ID: {user_id_filter}, "
            f"姓名: {name_filter}, "
            f"房间号: {room_number_filter}, "
            f"搜索查询: {search_query}, "
            f"部门: {department_filter}, "
            f"性别: {gender_filter}"
        )

        # 应用筛选条件
        if user_id_filter:
            current_dorms_query = current_dorms_query.filter(Dorm.user_id == user_id_filter)
        
        # 关联用户表进行额外筛选 (如果未通过search_query应用)
        if name_filter and not search_applied:
            current_dorms_query = current_dorms_query.join(
                User, Dorm.user_id == User.id
            ).filter(User.name.ilike(f'%{name_filter}%'))
        
        # 应用房间号筛选 (如果未通过search_query应用)
        if room_number_filter and not search_applied:
            current_dorms_query = current_dorms_query.join(
                Room, Dorm.room_id == Room.id
            ).filter(Room.room_number.ilike(f'%{room_number_filter}%'))
        
        # 执行查询获取当前在住记录
        current_dorms = current_dorms_query.all()
        logging.debug(
            f"原始查询结果 [请求ID: {request_id}] "
            f"匹配的在住记录数量: {len(current_dorms)} 条"
        )
        
        if not current_dorms:
            logging.info(
                f"查询完成 [请求ID: {request_id}] "
                f"结果: 未找到符合筛选条件的在住人员"
            )
            return jsonify({
                'success': True,
                'message': '未找到符合条件的在住人员',
                'data': {
                    'total': 0,
                    'residents': []
                }
            })
        
        # 处理每个在住人员的详细信息和历史记录
        residents = []
        today = datetime.now()  # 修改：使用datetime代替date
        
        # 优化：先收集所有需要查询的房间ID，然后批量查询水电表读数
        meter_readings_cache = {}
        if query_meter_readings:
            # 收集所有唯一的房间ID
            room_ids = list({dorm.room_id for dorm in current_dorms})
            
            # 批量查询所有房间的最新水电表读数
            meter_readings_cache = {
                room_id: {
                    'water': UtilityMeterReading.get_latest_water_reading(room_id),
                    'electric': UtilityMeterReading.get_latest_electric_reading(room_id)
                }
                for room_id in room_ids
            }
        
        for current_dorm in current_dorms:
            # 获取用户信息
            user = User.query.get(current_dorm.user_id)
            if not user:
                logging.warning(
                    f"数据异常 [请求ID: {request_id}] "
                    f"住宿记录ID: {current_dorm.id} 关联的用户ID: {current_dorm.user_id} 不存在"
                )
                continue
            
            # 筛选条件二次过滤（部门和性别）
            if department_filter and (not user.department or department_filter not in user.department):
                continue
            if gender_filter and user.gender != gender_filter:
                continue
            
            # 获取当前房间信息
            current_room = Room.query.get(current_dorm.room_id)
            current_room_info = {
                'id': current_room.id if current_room else None,
                'building': current_room.building if current_room else None,
                'room_number': current_room.room_number if current_room else None,
                'full_room': f"{current_room.building}{current_room.room_number}" 
                            if (current_room and current_room.building and current_room.room_number) 
                            else f"房间ID:{current_dorm.room_id}"
            }
            
            # 追溯所有历史住宿记录（通过prev_dorm_id关联）
            history_records = []
            total_stay_days = 0
            current_record = current_dorm
            
            # 循环追溯历史记录链
            while current_record:
                # 获取该记录对应的房间信息
                room = Room.query.get(current_record.room_id)
                room_info = {
                    'id': room.id if room else None,
                    'building': room.building if room else None,
                    'room_number': room.room_number if room else None,
                    'full_room': f"{room.building}{room.room_number}" 
                                if (room and room.building and room.room_number) 
                                else f"房间ID:{current_record.room_id}"
                }
                
                # 计算该房间的住宿天数
                stay_days = 0
                check_in = current_record.check_in_date
                check_out = current_record.check_out_date or today  # 当前房间用当前时间作为退房日期
                
                if check_in:
                    try:
                        # 确保日期格式正确（使用datetime）
                        if isinstance(check_in, str):
                            check_in = datetime.strptime(check_in, '%Y-%m-%d')  # 修改：不转换为date
                        if isinstance(check_out, str):
                            check_out = datetime.strptime(check_out, '%Y-%m-%d')  # 修改：不转换为date
                            
                        delta = check_out - check_in
                        stay_days = max(int(delta.total_seconds() / 86400), 0)  # 修改：使用total_seconds计算天数
                        total_stay_days += stay_days
                    except (TypeError, ValueError) as e:
                        logging.warning(
                            f"日期计算错误 [请求ID: {request_id}] "
                            f"住宿记录ID: {current_record.id}, "
                            f"用户ID: {current_record.user_id}, "
                            f"错误原因: {str(e)}, "
                            f"入住日期: {check_in}, "
                            f"退房日期: {check_out}"
                        )
                        stay_days = -1  # 标记日期异常
                
                # 添加到历史记录
                history_records.append({
                    'dorm_id': current_record.id,
                    'room': room_info,
                    'check_in_date': current_record.check_in_date.isoformat() if check_in else None,
                    'check_out_date': current_record.check_out_date.isoformat() if current_record.check_out_date else None,
                    'stay_days': stay_days,
                    'is_current': current_record.check_out_date is None  # 标记是否为当前房间
                })
                
                # 移动到上一条记录
                current_record = current_record.prev_dorm if current_record.prev_dorm_id else None
            
            # 按入住日期排序历史记录（最新的在前）
            history_records.sort(key=lambda x: x['check_in_date'] or '', reverse=True)
            
            # 检查当前房间是否在筛选范围内
            if room_number_filter:
                current_room_match = (current_room_info['room_number'] and 
                                     room_number_filter in current_room_info['room_number'])
                if not current_room_match:
                    continue  # 过滤掉不匹配的房间
            
            # 从缓存中获取水电表读数，避免重复查询
            latest_water_reading = None
            latest_electric_reading = None
            if query_meter_readings:
                room_readings = meter_readings_cache.get(current_dorm.room_id, {})
                latest_water_reading = room_readings.get('water')
                latest_electric_reading = room_readings.get('electric')
            
            # 构建人员详情（确保包含按钮所需的ID）
            resident = {
                'user': {
                    'id': user.id,  # 换宿舍按钮需要的用户ID
                    'name': user.name,
                    'gender': user.gender or '-',
                    'age': user.get_age() if user.get_age() is not None else '-',
                    'department': user.department or '-',
                    'position': user.position or '-'
                },
                'current_room': {
                    'id': current_room_info['id'],  # 退宿按钮需要的房间ID
                    'full_room': current_room_info['full_room'],
                    'building': current_room_info['building'],
                    'room_number': current_room_info['room_number']
                },
                'current_check_in': current_dorm.check_in_date.isoformat() if current_dorm.check_in_date else None,
                'current_stay_days': next((r['stay_days'] for r in history_records if r['is_current']), 0),
                'total_stay_days': total_stay_days,
                'history_rooms': history_records,  # 包含所有历史房间及对应天数
                'latest_meter_readings': {
                    'water': {
                        'current_reading': latest_water_reading.water_current if latest_water_reading else None,
                        'reading_date': latest_water_reading.reading_date.isoformat() if (latest_water_reading and latest_water_reading.reading_date) else None
                    } if latest_water_reading else None,
                    'electric': {
                        'current_reading': latest_electric_reading.electric_current if latest_electric_reading else None,
                        'reading_date': latest_electric_reading.reading_date.isoformat() if (latest_electric_reading and latest_electric_reading.reading_date) else None
                    } if latest_electric_reading else None
                }
            }
            
            residents.append(resident)
        
        # 记录查询结果统计 - 移除对_cached_json的依赖
        start_time = getattr(request, '_request_start_time', datetime.now().timestamp())
        logging.info(
            f"查询完成 [请求ID: {request_id}] "
            f"结果: 找到符合条件的在住人员 {len(residents)} 名, "
            f"处理耗时: {datetime.now().timestamp() - start_time:.3f}秒, "
            f"响应时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        # 返回结果
        return jsonify({
            'success': True,
            'message': f'共找到 {len(residents)} 名符合条件的在住人员',
            'data': {
                'total': len(residents),
                'query_date': today.isoformat(),  # 现在包含时间信息
                'residents': residents
            }
        })
        
    except Exception as e:
        error_msg = f"查询在住人员明细失败: {str(e)}\n{traceback.format_exc()}"
        logging.error(
            f"API调用失败 [请求ID: {request_id}] "
            f"操作用户ID: {user_id}, "
            f"客户端IP: {request.remote_addr}, "
            f"错误详情: {error_msg}"
        )
        return jsonify({
            'success': False,
            'message': '查询在住人员明细时发生错误',
            'error': error_msg if request.args.get('debug') else str(e)
        }), 500

# 修改请求钩子，使用独立属性存储时间戳，避免与Flask内部属性冲突
@dorm_bp.before_request
def before_request():
    if request.endpoint == 'dorm.get_resident_details':
        # 使用独立的属性名存储时间戳，避免与Flask内部的_cached_json冲突
        request._request_start_time = datetime.now().timestamp()
    

@dorm_bp.route('/user-dorm-details', methods=['POST'])
@login_required
def get_user_dorm_details():
    """
    退宿人员管理页面专用：按用户ID查询完整住宿信息
    返回：入住日期、住宿天数、退宿日期、同住室友信息
    支持查询在住和已退宿人员
    """
    # 日志记录（复用现有格式）
    request_id = request.headers.get('X-Request-ID', 'unknown')
    operator_id = current_user.id if current_user.is_authenticated else 'anonymous'
    logging.info(
        f"API调用开始 [/dorm/user-dorm-details] "  # 修改：修正路径
        f"请求ID: {request_id}, "
        f"操作用户: {operator_id}, "
        f"客户端IP: {request.remote_addr}"
    )

    try:
        # 1. 获取并验证用户ID参数
        data = request.get_json() or request.form.to_dict()
        target_user_id = data.get('user_id')
        
        if not target_user_id:
            logging.warning(f"参数错误 [请求ID: {request_id}] 缺少user_id")
            return jsonify({
                'success': False,
                'message': '用户ID不能为空',
                'error': '缺少user_id参数'
            }), 400

        # 2. 查询用户基本信息
        user = User.query.get(target_user_id)
        if not user:
            logging.info(f"用户不存在 [请求ID: {request_id}] ID: {target_user_id}")
            return jsonify({
                'success': True,
                'message': f'用户ID {target_user_id} 不存在',
                'data': None
            }), 200

        # 3. 查询该用户的所有住宿记录（包括在住和已退宿）
        all_dorm_records = Dorm.query.filter(
            Dorm.user_id == target_user_id
        ).order_by(Dorm.check_in_date.desc()).all()

        if not all_dorm_records:
            logging.info(f"无住宿记录 [请求ID: {request_id}] 用户ID: {target_user_id}")
            return jsonify({
                'success': True,
                'message': '该用户无任何住宿记录',
                'data': {
                    'user': {
                        'id': user.id,
                        'name': user.name,
                        'department': user.department or '-'
                    },
                    'has_records': False
                }
            }), 200

        # 4. 处理每条住宿记录的详细信息
        today = datetime.now()  # 修改：使用datetime代替date
        dorm_records = []
        
        for record in all_dorm_records:
            # 获取房间信息
            room = Room.query.get(record.room_id)
            room_info = {
                'id': room.id if room else None,
                'building': room.building if room else None,
                'room_number': room.room_number if room else None,
                'full_room': f"{room.building}{room.room_number}" 
                            if (room and room.building and room.room_number) 
                            else f"房间ID:{record.room_id}"
            }

            # 计算住宿天数
            check_in = record.check_in_date
            check_out = record.check_out_date or today
            stay_days = 0
            
            if check_in:
                try:
                    if isinstance(check_in, str):
                        check_in = datetime.strptime(check_in, '%Y-%m-%d')  # 修改：不转换为date
                    if isinstance(check_out, str):
                        check_out = datetime.strptime(check_out, '%Y-%m-%d')  # 修改：不转换为date
                    delta = check_out - check_in
                    stay_days = max(int(delta.total_seconds() / 86400), 0)  # 修改：使用total_seconds计算天数
                except (TypeError, ValueError) as e:
                    logging.warning(f"日期计算错误 [请求ID: {request_id}] 记录ID: {record.id}, 错误: {str(e)}")
                    stay_days = -1  # 标记异常

            # 5. 查询同期同住室友（同一房间、时间重叠的其他用户）
            roommates = []
            if room:
                # 计算时间重叠条件
                overlap_conditions = [
                    Dorm.room_id == room.id,
                    Dorm.user_id != target_user_id,  # 排除当前用户
                    Dorm.status.in_(['active'])  # 有效状态
                ]
                
                # 处理入住时间重叠逻辑
                if record.check_out_date:
                    # 已退宿记录：查询在该用户住宿期间入住的其他用户
                    overlap_conditions.extend([
                        Dorm.check_in_date <= record.check_out_date,
                        db.or_(
                            Dorm.check_out_date.is_(None),  # 仍在住
                            Dorm.check_out_date >= record.check_in_date  # 已退宿但时间重叠
                        )
                    ])
                else:
                    # 在住记录：查询当前在同一房间的其他用户
                    overlap_conditions.extend([
                        Dorm.check_in_date <= today,
                        db.or_(
                            Dorm.check_out_date.is_(None),
                            Dorm.check_out_date >= today
                        )
                    ])

                # 执行室友查询
                roommate_records = Dorm.query.filter(*overlap_conditions).all()
                seen_user_ids = set()  # 去重（同一用户可能有多次住宿记录）
                
                for rm in roommate_records:
                    if rm.user_id in seen_user_ids:
                        continue
                    seen_user_ids.add(rm.user_id)
                    
                    rm_user = User.query.get(rm.user_id)
                    if rm_user:
                        roommates.append({
                            'user_id': rm_user.id,
                            'name': rm_user.name,
                            'gender': rm_user.gender or '-',
                            'age': rm_user.get_age() if rm_user.get_age() is not None else '-',
                            'department': rm_user.department or '-',
                            'position': rm_user.position or '-',
                            'check_in_date': rm.check_in_date.isoformat() if rm.check_in_date else None,
                            'check_out_date': rm.check_out_date.isoformat() if rm.check_out_date else None,
                            'is_current': rm.check_out_date is None  # 是否仍在住
                        })

            # 整理单条住宿记录
            dorm_records.append({
                'dorm_id': record.id,
                'room': room_info,
                'check_in_date': check_in.isoformat() if check_in else None,
                'check_out_date': record.check_out_date.isoformat() if record.check_out_date else None,
                'stay_days': stay_days,
                'status': record.status,
                'roommates': roommates  # 该记录期间的同住室友
            })

        # 6. 构建返回数据
        result_data = {
            'user': {
                'id': user.id,
                'name': user.name,
                'gender': user.gender or '-',
                'department': user.department or '-',
                'position': user.position or '-'
            },
            'has_records': True,
            'total_records': len(dorm_records),
            'current_status': all_dorm_records[0].status,  # 最新状态
            'records': dorm_records
        }

        logging.info(f"查询成功 [请求ID: {request_id}] 用户ID: {target_user_id}, 记录数: {len(dorm_records)}")
        return jsonify({
            'success': True,
            'message': f'查询到用户{user.name}的{len(dorm_records)}条住宿记录',
            'data': result_data
        }), 200

    except Exception as e:
        error_msg = f"查询失败: {str(e)}\n{traceback.format_exc()}"
        logging.error(
            f"API错误 [请求ID: {request_id}] "
            f"用户ID: {target_user_id or '-'}, "
            f"错误: {error_msg}"
        )
        return jsonify({
            'success': False,
            'message': '查询用户住宿信息时发生错误',
            'error': error_msg if request.args.get('debug') else str(e)
        }), 500
        
@dorm_bp.route('/checkout-residents', methods=['POST'])
@login_required
def get_checkout_residents():
    """
    查询指定账期内的退宿人员清单（排除换宿人员）
    接收参数：
    - bill_period (格式为yyyy-mm)
    - name (可选，姓名搜索)
    - room_number (可选，房间号搜索)
    返回该月份内所有办理退宿且未换宿的人员详情，包含当月内的已住天数
    """
    # 记录API调用开始
    request_id = request.headers.get('X-Request-ID', 'unknown')
    user_id = current_user.id if current_user.is_authenticated else 'anonymous'
    logging.info(
        f"API调用开始 [/dorm/checkout-residents] "
        f"请求ID: {request_id}, "
        f"操作用户ID: {user_id}, "
        f"客户端IP: {request.remote_addr}, "
        f"请求时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    try:
        # 获取请求数据
        data = {}
        try:
            json_data = request.get_json()
            if isinstance(json_data, dict):
                data = json_data
        except Exception as e:
            logging.warning(
                f"JSON解析失败 [请求ID: {request_id}] "
                f"错误原因: {str(e)}, 尝试解析表单数据"
            )
            form_data = request.form.to_dict()
            if form_data:
                data = form_data
        
        # 获取并验证账期参数
        bill_period = data.get('bill_period', '').strip()
        if not bill_period:
            logging.warning(f"参数错误 [请求ID: {request_id}] 缺少账期参数bill_period")
            return jsonify({
                'success': False,
                'message': '请提供账期参数（格式为yyyy-mm）',
                'error': '缺少bill_period参数'
            }), 400
        
        # 获取搜索参数
        search_name = data.get('name', '').strip()
        search_room = data.get('room_number', '').strip()
        # 获取筛选参数
        building = data.get('building', '').strip()
        department = data.get('department', '').strip()
        
        # 获取分页参数
        page = data.get('page', 1)
        per_page = data.get('per_page', 20)
        
        # 确保分页参数为整数且合理
        try:
            page = int(page)
            per_page = int(per_page)
            per_page = min(per_page, 100)  # 限制最大每页数量
            page = max(page, 1)  # 确保页码至少为1
        except (ValueError, TypeError):
            page = 1
            per_page = 20
        
        # 解析账期为月份的起始和结束日期（使用datetime）
        try:
            year, month = map(int, bill_period.split('-'))
            # 计算当月第一天（datetime）
            start_date = datetime(year, month, 1)
            # 计算当月月最后一天（datetime）
            if month == 12:
                next_month = 1
                next_year = year + 1
            else:
                next_month = month + 1
                next_year = year
            end_date = datetime(next_year, next_month, 1) - timedelta(days=1)
            # 设置为当月最后一天的23:59:59
            end_date = end_date.replace(hour=23, minute=59, second=59)
        except ValueError as e:
            logging.warning(
                f"参数格式错误 [请求ID: {request_id}] "
                f"账期格式应为yyyy-mm，实际值: {bill_period}, 错误: {str(e)}"
            )
            return jsonify({
                'success': False,
                'message': '账期格式错误，请使用yyyy-mm格式',
                'error': str(e)
            }), 400
        
        logging.info(
            f"处理退宿查询请求 [请求ID: {request_id}] "
            f"账期: {bill_period}, "
            f"搜索姓名: {search_name or '无'}, "
            f"搜索房间号: {search_room or '无'}, "
            f"楼栋筛选: {building or '无'}, "
            f"部门筛选: {department or '无'}, "
            f"查询日期范围: {start_date} 至 {end_date}"
        )
        
        # 基础查询：查询该账期内的退宿记录，排除有后续换宿记录的情况
        query = Dorm.query.filter(
            Dorm.status == 'checked_out',
            Dorm.check_out_date >= start_date,
            Dorm.check_out_date <= end_date,
            # 关键过滤条件：没有后续换宿记录的才是真正退宿
            ~Dorm.next_dorms.any()
        )
        
        # 关联用户表用于姓名搜索
        query = query.join(User, Dorm.user_id == User.id)
        
        # 关联房间表用于房间号搜索
        query = query.join(Room, Dorm.room_id == Room.id)
        
        # 添加姓名搜索条件（模糊匹配）
        if search_name:
            query = query.filter(User.name.ilike(f'%{search_name}%'))
        
        # 添加房间号搜索条件（匹配楼栋或房间号）
        if search_room:
            query = query.filter(
                (Room.building.ilike(f'%{search_room}%')) | 
                (Room.room_number.ilike(f'%{search_room}%'))
            )
            
        # 添加楼栋筛选条件
        if building:
            query = query.filter(Room.building == building)
        
        # 添加部门筛选条件
        if department:
            query = query.join(Department, User.department_id == Department.id).filter(Department.name == department)
        
        # 执行分页查询
        paginated_records = query.order_by(Dorm.check_out_date.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        
        checkout_records = paginated_records.items
        
        if not checkout_records:
            logging.info(
                f"查询完成 [请求ID: {request_id}] "
                f"结果: {bill_period}账期内未找到符合条件的退宿人员记录"
            )
            return jsonify({
                'success': True,
                'message': f'{bill_period}账期内未找到退宿人员记录',
                'data': {
                    'bill_period': bill_period,
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'total': 0,
                    'checkout_residents': []
                }
            })
        
        # 处理退宿人员详情
        checkout_residents = []
        for record in checkout_records:
            # 获取用户信息
            user = User.query.get(record.user_id)
            if not user:
                logging.warning(
                    f"数据异常 [请求ID: {request_id}] "
                    f"退宿记录ID: {record.id} 关联的用户ID: {record.user_id} 不存在"
                )
                continue
            
            # 获取原房间信息
            room = Room.query.get(record.room_id)
            room_info = {
                'id': room.id if room else None,
                'building': room.building if room else None,
                'room_number': room.room_number if room else None,
                'full_room': f"{room.building}{room.room_number}" 
                            if (room and room.building and room.room_number) 
                            else f"房间ID:{record.room_id}"
            }
            
            # 计算查询月份内的已住天数（而非累计总天数）
            month_stay_days = 0
            if record.check_in_date and record.check_out_date:
                try:
                    # 确定在查询月份内的实际住宿起始日期
                    # 如果入住日期早于当月开始，则从当月第一天开始计算
                    actual_check_in = max(record.check_in_date, start_date)
                    
                    # 确定在查询月份内的实际住宿结束日期
                    # 如果退宿日期晚于当月结束，则计算到当月最后一天
                    actual_check_out = min(record.check_out_date, end_date)
                    
                    # 计算天数差
                    delta = actual_check_out - actual_check_in
                    month_stay_days = max(int(delta.total_seconds() / 86400) + 1, 0)  # +1是因为包含首尾两天
                except (TypeError, ValueError) as e:
                    logging.warning(
                        f"日期计算错误 [请求ID: {request_id}] "
                        f"退宿记录ID: {record.id}, 错误: {str(e)}"
                    )
                    month_stay_days = -1  # 标记异常
            
            # 构建退宿人员信息，在顶层添加user_id和room_id
            resident = {
                'dorm_record_id': record.id,
                'user_id': user.id,  # 顶层用户ID
                'room_id': record.room_id,  # 顶层房间ID
                'check_out_date': record.check_out_date.isoformat(),
                'user': {
                    'id': user.id,
                    'name': user.name,
                    'gender': user.gender or '-',
                    'department': user.department or '-',
                    'position': user.position or '-'
                },
                'room': room_info,
                'check_in_date': record.check_in_date.isoformat() if record.check_in_date else None,
                'month_stay_days': month_stay_days,  # 当月内的已住天数
                'remarks': record.remarks or ''
            }
            
            checkout_residents.append(resident)
        
        # 记录查询结果
        start_time = getattr(request, '_request_start_time', datetime.now().timestamp())
        logging.info(
            f"查询完成 [请求ID: {request_id}] "
            f"结果: {bill_period}账期内共找到 {len(checkout_residents)} 条退宿记录, "
            f"处理耗时: {datetime.now().timestamp() - start_time:.3f}秒"
        )
        
        # 构建分页信息
        pagination = {
            'total': paginated_records.total,
            'pages': paginated_records.pages,
            'page': page,
            'per_page': per_page,
            'has_next': paginated_records.has_next,
            'has_prev': paginated_records.has_prev
        }
        
        # 返回结果
        return jsonify({
            'success': True,
            'message': f'{bill_period}账期内共找到 {paginated_records.total} 名退宿人员',
            'data': {
                'bill_period': bill_period,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'total': paginated_records.total,
                'checkout_residents': checkout_residents,
                'pagination': pagination
            }
        })
        
    except Exception as e:
        error_msg = f"查询退宿人员失败: {str(e)}\n{traceback.format_exc()}"
        logging.error(
            f"API调用失败 [请求ID: {request_id}] "
            f"错误详情: {error_msg}"
        )
        return jsonify({
            'success': False,
            'message': '查询退宿人员时发生错误',
            'error': error_msg if request.args.get('debug') else str(e)
        }), 500
