from flask import Blueprint, request, jsonify, flash, redirect, url_for
from models.utility.utility_room_bill_record import RoomUtilityRecord      #导入主表模型
from models.utility.utility_room_bill_occupant import RoomUtilityOccupant  #导入子表模型
from models.dorm.dorm import Dorm
from models.user.user import User  # 假设存在用户模型
from models.department.department import Department
from utils.db import db
from sqlalchemy.exc import SQLAlchemyError
from utils.log import log_operation
from models.room.room import Room
from datetime import datetime, timedelta  # 修正：移除date，保留datetime和timedelta
from collections import defaultdict
from decimal import Decimal
import logging  # 确保导入logging模块
from sqlalchemy.exc import SQLAlchemyError
from flask_login import login_required, current_user
from models.fee_subsidy.fee_subsidy_usage import FeeSubsidyUsage  # 导入费用补贴子表
# 导入权限装饰器
from utils.auth import require_permission
# 创建蓝图
utility_room_bill_occupants_bp = Blueprint('utility_room_bill_occupants', __name__, url_prefix='/utility_room_bill_occupants')

# 获取费用明细数据
@utility_room_bill_occupants_bp.route('/api/fee_records', methods=['GET'])
@login_required
@require_permission('utility.view')
def get_fee_records():
    """获取费用明细数据，支持筛选和分页，新增住宿周期信息"""
    try:
        # 获取请求参数
        billing_period = request.args.get('billingPeriod', '')
        building = request.args.get('building', '')
        department = request.args.get('department', '')
        search_keyword = request.args.get('searchInput', '')
        search_type = request.args.get('searchType', '')  # 新增：获取搜索类型
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        # 解析账期为日期范围（如2025-04 -> 2025-04-01至2025-04-30，返回datetime类型）
        start_date = end_date = None
        if billing_period and len(billing_period) == 7:  # 格式如YYYY-MM
            year, month = map(int, billing_period.split('-'))
            # 修正：使用datetime而非date
            start_date = datetime(year, month, 1)
            # 获取当月最后一天
            if month == 12:
                end_date = datetime(year, month, 31, 23, 59, 59)  # 增加时间部分
            else:
                end_date = datetime(year, month + 1, 1) - timedelta(days=1)
                end_date = end_date.replace(hour=23, minute=59, second=59)  # 增加时间部分
        
        # 基础查询
        query = db.session.query(
            RoomUtilityRecord,
            RoomUtilityOccupant,
            User.name,  # 查询用户名
            Department.name.label('department'),  # 查询部门信息用于筛选
            Dorm,  # 关联Dorm模型获取住宿日期
            Room  # 选择完整的Room对象，确保可以访问room_number字段
        ).join(
            RoomUtilityOccupant, 
            RoomUtilityRecord.record_id == RoomUtilityOccupant.record_id
        ).join(
            User, 
            RoomUtilityOccupant.user_id == User.id
        ).outerjoin(
            Department, User.department_id == Department.id
        ).outerjoin(
            Dorm,  # 通过dorm_id精确关联Dorm表，避免同一用户同一房间多条dorm记录产生笛卡尔积
            Dorm.id == RoomUtilityOccupant.dorm_id
        ).join(
            Room,  # 关联Room表用于获取楼栋信息
            RoomUtilityRecord.room_id == Room.id
        )
        
        # 账期筛选
        if billing_period:
            query = query.filter(RoomUtilityRecord.billing_period == billing_period)
        
        # 楼栋筛选
        if building:
            query = query.filter(Room.building == building)
        
        # 部门筛选 - 确保在所有条件下都能正确应用
        if department:
            query = query.filter(Department.name == department)
        
        # 搜索筛选（根据搜索类型分别处理房间号或姓名）
        if search_keyword:
            # Room表已在基础查询中关联，不需要重复关联
            if search_type == 'room':
                # 房间号搜索，使用精确匹配前模糊匹配后
                query = query.filter(Room.room_number.like(f'%{search_keyword}%'))
            elif search_type == 'name':
                # 姓名搜索
                query = query.filter(User.name.like(f'%{search_keyword}%'))
            else:
                # 默认同时搜索房间号和姓名
                query = query.filter(
                    db.or_(
                        Room.room_number.like(f'%{search_keyword}%'),
                        User.name.like(f'%{search_keyword}%')
                    )
                )
        
        
        # 执行分页查询
        pagination = query.order_by(
            RoomUtilityRecord.billing_period.desc(),
            RoomUtilityRecord.room_id.asc(),
            RoomUtilityOccupant.user_id.asc()
        ).paginate(page=page, per_page=per_page)
        
        # 预过滤：移除无 dorm_record 的项，确保汇总仅包含有效记录
        warnings = []
        valid_items = []
        for item in pagination.items:
            _main, _occupant, _uname, _udept, _dorm, _room = item
            if _dorm is None:
                logging.error(
                    f"分摊记录缺少dorm_id关联: occupant_id={_occupant.id}, "
                    f"user_id={_occupant.user_id}, room_id={_occupant.room_id}, "
                    f"record_id={_occupant.record_id}"
                )
                warnings.append(
                    f"分摊记录ID={_occupant.id}（用户ID={_occupant.user_id}，"
                    f"房间ID={_occupant.room_id}）缺少dorm_id关联，请重新核算账单"
                )
            else:
                valid_items.append(item)

        # 基于有效项构建用户分组和汇总
        user_groups = defaultdict(list)
        for item in valid_items:
            _main, _occupant, _uname, _udept, _dorm, _room = item
            group_key = (_main.billing_period, _main.room_id, _occupant.user_id)
            user_groups[group_key].append((_occupant, _dorm, _main))

        user_summaries = {}
        for group_key, items in user_groups.items():
            occupants = [item[0] for item in items]
            dorm_records = [item[1] for item in items]
            main_records = [item[2] for item in items]
            person_total_fee_sum = sum(Decimal(str(o.total_fee or 0)) for o in occupants)
            user_reduction_fee_sum = sum(Decimal(str(o.user_reduction_fee or 0)) for o in occupants)
            payable_fee_sum = sum(Decimal(str(o.payable_fee or 0)) for o in occupants)
            stay_days_sum = sum(o.stay_days or 0 for o in occupants)
            # 计算住宿周期范围
            _main = main_records[0]
            period_start = start_date if start_date else _main.start_date
            period_end = end_date if end_date else _main.end_date
            check_in_dates = []
            check_out_dates = []
            for dorm in dorm_records:
                actual_check_in = max(dorm.check_in_date, period_start)
                actual_check_out = dorm.check_out_date or period_end
                actual_check_out = min(actual_check_out, period_end)
                check_in_dates.append(actual_check_in)
                check_out_dates.append(actual_check_out)
            min_check_in = min(check_in_dates)
            max_check_out = max(check_out_dates)
            user_summaries[group_key] = {
                'person_total_fee': float(person_total_fee_sum),
                'user_reduction_fee': float(user_reduction_fee_sum),
                'payable_fee': float(payable_fee_sum),
                'stay_days': stay_days_sum,
                'check_in_date': min_check_in.strftime('%Y-%m-%d'),
                'check_out_date': max_check_out.strftime('%Y-%m-%d')
            }
        
        # 处理查询结果
        records = []
        user_first_seen = set()
        for item in valid_items:
            main_record, occupant_record, user_name, user_department, dorm_record, room = item
            
            # 计算用户分组汇总字段
            group_key = (main_record.billing_period, main_record.room_id, occupant_record.user_id)
            user_record_count = len(user_groups[group_key])
            is_user_first = group_key not in user_first_seen
            if is_user_first:
                user_first_seen.add(group_key)
            user_summary = user_summaries[group_key] if is_user_first else None
            
            # 计算账期内的实际住宿周期（datetime类型）
            period_start = start_date if start_date else main_record.start_date
            period_end = end_date if end_date else main_record.end_date
            
            # 确定实际入住和退宿日期（取与账期的交集，datetime比较）
            actual_check_in = max(dorm_record.check_in_date, period_start)
            actual_check_out = dorm_record.check_out_date or period_end
            actual_check_out = min(actual_check_out, period_end)
            
            # 格式化日期时间显示（包含秒）
            check_in_str = actual_check_in.strftime('%Y-%m-%d %H:%M:%S')
            check_out_str = actual_check_out.strftime('%Y-%m-%d %H:%M:%S')
            
            # 获取抄表信息
            electric_reading = f"{main_record.electric_previous} → {main_record.electric_current}" if main_record.electric_previous and main_record.electric_current else ""
            water_reading = f"{main_record.water_previous} → {main_record.water_current}" if main_record.water_previous and main_record.water_current else ""
            
            records.append({
                'billing_period': main_record.billing_period,
                'room_id': main_record.room_id,
                'electric_fee': main_record.billing_electric_fee,
                'water_fee': main_record.billing_water_fee,
                'total_fee': main_record.billing_total_fee,
                'checked_out_total_fee': main_record.checked_out_total_fee,
                'actual_total_fee': main_record.actual_total_fee,
                'room_reduction_fee': main_record.room_reduction_fee,# 新增：房间级减免费用
                'user_name': user_name,
                'user_id': occupant_record.user_id,
                'department': user_department,  # 新增：部门信息
                'person_electric_fee': occupant_record.electric_fee,
                'person_water_fee': occupant_record.water_fee,
                'person_total_fee': occupant_record.total_fee,
                'user_reduction_fee': occupant_record.user_reduction_fee,# 新增：减免费用字段
                'payable_fee': occupant_record.payable_fee,# 新增：用户应付费用字段
                'stay_days': occupant_record.stay_days,
                # 新增：住宿周期信息（包含时间）
                'check_in_date': check_in_str,
                'check_out_date': check_out_str,
                'electric_reading': electric_reading,
                'water_reading': water_reading,
                'record_id': main_record.record_id,
                'occupant_id': occupant_record.id,
                'room_number': room.room_number,  # 新增：房间号字段
                'building': room.building,  # 新增：楼栋字段
                'user_record_count': user_record_count,
                'is_user_first': is_user_first,
                'user_summary': user_summary,
            })
        
        # 记录成功日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='utility_api',
            action=f"查询费用明细 [账期: {billing_period}, 搜索关键词: {search_keyword}, 页码: {page}]",
            result="成功"
        )
        
        # 返回分页数据
        return jsonify({
            'success': True,
            'data': records,
                'room_reduction_fee_field': 'room_reduction_fee',  # 明确指定房间级减免费用字段名
            'pagination': {
                'total': pagination.total,
                'pages': pagination.pages,
                'page': page,
                'per_page': per_page,
                'has_next': pagination.has_next,
                'has_prev': pagination.has_prev
            },
            'warnings': warnings
        })
        
    except Exception as e:
        logging.error(f"获取费用记录失败: {str(e)}")
        # 记录失败日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='utility_api',
            action=f"查询费用明细失败 [错误: {str(e)}]",
            result="失败"
        )
        return jsonify({'success': False, 'message': f'获取数据失败: {str(e)}'}), 500
    
# 加载账单数据
@utility_room_bill_occupants_bp.route('/api/load_bill', methods=['POST'])
@login_required
@require_permission('utility.view')
def load_bill():
    """加载指定账期的账单数据"""
    try:
        data = request.json
        billing_period = data.get('billingPeriod')
        
        if not billing_period:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='utility_api',
                action=f"加载账单数据失败 [原因: 未提供账期参数]",
                result="失败"
            )
            return jsonify({'success': False, 'message': '请选择账期'}), 400
            
        # 查找该账期的所有主表记录
        main_records = RoomUtilityRecord.get_by_period(None, period=billing_period)
        
        if not main_records:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='utility_api',
                action=f"加载账单数据失败 [账期: {billing_period}, 原因: 未找到记录]",
                result="失败"
            )
            return jsonify({
                'success': False, 
                'message': f'未找到{ billing_period }的账单记录'
            }), 404
        
        # 加载对应的子表记录
        record_ids = [r.record_id for r in main_records]
        occupant_records = RoomUtilityOccupant.query.filter(
            RoomUtilityOccupant.record_id.in_(record_ids)
        ).all()
        # 记录成功日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='utility_api',
            action=f"加载账单数据 [账期: {billing_period}, 主表记录数: {len(main_records)}, 子表记录数: {len(occupant_records)}]",
            result="成功"
        )
        return jsonify({
            'success': True,
            'message': f'已加载{ billing_period }的账单记录',
            'record_count': len(main_records),
            'occupant_count': len(occupant_records)
        })
        
    except Exception as e:
        logging.error(f"加载账单失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='utility_api',
            action=f"加载账单数据失败 [错误: {str(e)}]",
            result="失败"
        )
        return jsonify({'success': False, 'message': f'加载失败: {str(e)}'}), 500

# 核算当期账单
@utility_room_bill_occupants_bp.route('/api/calculate_bill', methods=['POST'])
@login_required
@require_permission('utility.calculate')
def calculate_bill():
    """核算指定账期的所有房间费用"""
    try:
        data = request.json
        billing_period = data.get('billingPeriod')
        
        if not billing_period:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='occupant_fee',
                action=f"核算账单失败 [原因: 未提供账期参数]",
                result="失败"
            )
            return jsonify({'success': False, 'message': '请选择账期'}), 400
            
        # 获取该账期的所有主表记录（仅核算完成的）
        all_period_records = RoomUtilityRecord.get_by_period(None, period=billing_period)
        main_records = [r for r in all_period_records if r.status == 'completed']
        skipped_count = len(all_period_records) - len(main_records)
        if skipped_count > 0:
            logging.info(f"账期{billing_period}：跳过{skipped_count}个未核算房间")
        
        # 关键修复：按账单开始日期排序，确保补贴按时间顺序使用
        main_records.sort(key=lambda x: x.start_date)

        if not main_records:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='occupant_fee',
                action=f"核算账单失败 [账期: {billing_period}, 原因: 未找到记录]",
                result="失败"
            )
            return jsonify({
                'success': False, 
                'message': f'未找到{ billing_period }的账单记录，请先创建'
            }), 404
        
        # 关键修复2：初始化全局补贴余额字典，跨房间共享
        global_subsidy_balances = {}

        # 再计算子表分摊
        updated_occupant = 0
        updated_room_count = 0  # 新增：统计处理的房间数量
        for record in main_records:
            occupants, global_subsidy_balances = RoomUtilityOccupant.calculate_room_fee(
                record.record_id,
                user_subsidy_balances=global_subsidy_balances # 核心：共享同一个字典
                )  
            updated_occupant += len(occupants)
            updated_room_count += 1  # 每处理一个主表记录，视为处理一个房间
        
        db.session.commit()
        # 记录成功日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='occupant_fee',
            action=f"核算当期账单 [账期: {billing_period}, 房间数: {updated_room_count}, 更新子表记录数: {updated_occupant}]",
            result="成功"
        )
        
        return jsonify({
            'success': True,
            'message': f'{ billing_period }的费用核算完成',
            'updated_room_count': updated_room_count,  # 新增：返回房间数量
            'updated_occupant_count': updated_occupant
        })
        
    except SQLAlchemyError as e:
        db.session.rollback()
        logging.error(f"核算账单数据库错误: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='occupant_fee',
            action=f"核算账单失败 [错误: {str(e)}]",
            result="失败"
        )
        return jsonify({'success': False, 'message': f'数据库错误: {str(e)}'}), 500
    except Exception as e:
        db.session.rollback()
        logging.error(f"核算账单失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='occupant_fee',
            action=f"核算账单失败 [错误: {str(e)}]",
            result="失败"
        )
        return jsonify({'success': False, 'message': f'核算失败: {str(e)}'}), 500

# 删除当期子表账单
@utility_room_bill_occupants_bp.route('/api/clear_current_bill', methods=['POST'])
@login_required
@require_permission('utility.delete')
def clear_current_bill():
    """删除指定账期的子表分摊记录（保留主表数据）"""
    try:
        data = request.json
        billing_period = data.get('billingPeriod')
        
        if not billing_period:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"删除子表账单失败 [原因: 未提供账期参数]",
                result="失败"
            )
            return jsonify({'success': False, 'message': '请选择账期'}), 400
            
        # 获取该账期的所有主表记录ID
        main_records = RoomUtilityRecord.get_by_period(None, period=billing_period)
        if not main_records:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"删除子表账单失败 [账期: {billing_period}, 原因: 未找到记录]",
                result="失败"
            )
            return jsonify({
                'success': False, 
                'message': f'未找到{ billing_period }的账单记录'
            }), 404
        
        record_ids = [r.record_id for r in main_records]

        

        # 删除对应子表记录
        deleted_count = RoomUtilityOccupant.query.filter(
            RoomUtilityOccupant.record_id.in_(record_ids)
        ).delete(synchronize_session=False)
        
        period = billing_period
        # 删除对应账期+类型的费用补贴子表记录（双重条件）
        subsidy_usage_deleted = FeeSubsidyUsage.query.filter(
            FeeSubsidyUsage.billing_period == period,
            FeeSubsidyUsage.is_checkout == 3
        ).delete(synchronize_session=False)

        db.session.commit()
        # 记录成功日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"删除当期子表账单 [账期: {billing_period}, 删除记录数: {deleted_count}，补贴子表删除数量: {subsidy_usage_deleted}]",
            result="成功"
        )
        return jsonify({
            'success': True,
            'message': f'{ billing_period }的子表账单数据已删除',
            'deleted_count': deleted_count
        })
        
    except SQLAlchemyError as e:
        db.session.rollback()
        logging.error(f"删除账单数据库错误: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"删除子表账单失败 [错误: {str(e)}]",
            result="失败"
        )
        return jsonify({'success': False, 'message': f'数据库错误: {str(e)}'}), 500
    except Exception as e:
        db.session.rollback()
        logging.error(f"删除账单失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"删除子表账单失败 [错误: {str(e)}]",
            result="失败"
        )
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'}), 500

# 删除单条费用记录
@utility_room_bill_occupants_bp.route('/api/delete_fee_record/<int:occupant_id>', methods=['DELETE'])
@login_required
@require_permission('utility.delete')
def delete_fee_record(occupant_id):
    """删除单条人员费用记录"""
    try:
        # 查找记录
        record = RoomUtilityOccupant.query.get(occupant_id)
        if not record:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"删除单条费用记录失败 [记录ID: {occupant_id}, 原因: 记录不存在]",
                result="失败"
            )
            return jsonify({'success': False, 'message': '记录不存在'}), 404
            
        # 获取关联信息用于返回
        main_record = RoomUtilityRecord.get_by_id(record.record_id)
        user = User.query.get(record.user_id)
        user_name = user.name if user else '未知用户'
        
        # 获取关联的补贴记录条件
        user_id = record.user_id
        room_id = main_record.room_id
        billing_period = main_record.billing_period
        
        # 连带删除关联的费用补贴子表记录（与账期删除保持一致的is_checkout=3条件）
        subsidy_deleted_count = FeeSubsidyUsage.query.filter(
            FeeSubsidyUsage.user_id == user_id,
            FeeSubsidyUsage.room_id == room_id,
            FeeSubsidyUsage.billing_period == billing_period,
            FeeSubsidyUsage.is_checkout == 3
        ).delete(synchronize_session=False)
        
        # 删除主记录
        db.session.delete(record)
        db.session.commit()
        # 根据room_id获取楼栋和房间号
        room = Room.query.get(room_id)
        # 记录成功日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"删除单条费用记录 [记录ID: {occupant_id}, 账期: {billing_period}, 房间号: {room.building}{room.room_number},"
                   f"用户: {user_name}], 连带删除补贴记录数量: {subsidy_deleted_count}",
            result="成功"
        )
        
        return jsonify({
            'success': True,
            'message': f'已删除 {billing_period} 账期， {room.building}{room.room_number} 房间， {user_name} 的费用记录',
            'subsidy_deleted_count': subsidy_deleted_count
        })
        
    except SQLAlchemyError as e:
        db.session.rollback()
        logging.error(f"删除单条记录数据库错误: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"删除单条费用记录失败 [记录ID: {occupant_id}, 错误: {str(e)}]",
            result="失败"
        )
        return jsonify({'success': False, 'message': f'数据库错误: {str(e)}'}), 500
    except Exception as e:
        db.session.rollback()
        logging.error(f"删除单条记录失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"删除单条费用记录失败 [记录ID: {occupant_id}, 错误: {str(e)}]",
            result="失败"
        )
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'}), 500



