from flask import Blueprint, request, jsonify
from datetime import datetime, time
from utils.db import db
from models.utility_room_bill_record import RoomUtilityRecord  # 主表模型
from utils.log import log_operation
from flask_login import login_required, current_user
import traceback
from models.utility_room_meter import UtilityMeterReading  # 新增：导入子表模型
import logging
from models.dorm import Dorm
from models.user import User
from models.room import Room
from models.utility_room_bill_occupant import RoomUtilityOccupant  #导入子表模型
from models.utility_room_bill_checkout import CheckoutUtilityRecord
from decimal import Decimal  # 使用Decimal处理财务数据
from models.fee_subsidy_usage import FeeSubsidyUsage  # 导入费用补贴子表
# 导入权限装饰器
from utils.auth import require_permission

# 主表蓝图
utility_room_bill_records_bp = Blueprint('utility_room_bill_records_bp', __name__, url_prefix='/utility_room_bill_records_bp')

# 模块名称
MODULE_NAME = 'utility_room_bill_records_bp'

@utility_room_bill_records_bp.route('/periods', methods=['GET'])
@login_required
@require_permission('utility.view')
def get_periods():
    """获取所有可用账期列表（供前端选择账期使用）"""
    try:
        # 查询系统中所有不重复的账期
        periods = db.session.query(RoomUtilityRecord.billing_period).distinct().all()
        period_list = [p[0] for p in periods if p[0]]  # 过滤空值，格式化为列表
        
       # 记录日志
        log_operation(
            user_id=current_user.id,
            module="utility",
            operation_type="utility_api",
            action=f"获取所有可用账期列表 [账期数量: {len(period_list)}]",
            result="成功"
        )
        return jsonify({
            'success': True,
            'periods': period_list
        })
        
    except Exception as e:
        if db.session.is_active:
            db.session.rollback()
        
        # 错误日志记录
        log_operation(
            user_id=current_user.id,
            module="utility",
            operation_type="utility_api",
            action=f"获取账期列表 [错误: {str(e)}]",
            result="失败"
        )
        return jsonify({'success': False, 'error': f'获取账期失败: {str(e)}'}), 500

@utility_room_bill_records_bp.route('/period-info/<string:period>', methods=['GET'])
@login_required
@require_permission('utility.view')
def get_period_info(period):
    """获取指定账期的详细信息"""
    try:
        # 查询该账期的第一条记录获取日期范围
        first_record = RoomUtilityRecord.query.filter_by(billing_period=period).first()
        
        if not first_record:
            # 记录查询失败日志
            log_operation(
                user_id=current_user.id,
                module="utility",
                operation_type="utility_api",
                action=f"查询账期信息 [账期: {period}, 原因: 未找到记录]",
                result="失败"
            )
            return jsonify({
                'success': False,
                'error': f'未找到{period}的记录'
            }), 404
            
        # 统计该账期的总记录数
        total_records = RoomUtilityRecord.query.filter_by(billing_period=period).count()
        
        # 统计该账期的总费用
        sum_result = db.session.query(
            db.func.sum(RoomUtilityRecord.total_electric_fee).label('total_electric'),
            db.func.sum(RoomUtilityRecord.total_water_fee).label('total_water'),
            db.func.sum(RoomUtilityRecord.total_fee).label('total_amount')
        ).filter_by(billing_period=period).first()
        
        # 查询该账期对应的抄表记录数
        meter_records_count = UtilityMeterReading.query.join(
            RoomUtilityRecord, 
            UtilityMeterReading.record_id == RoomUtilityRecord.record_id
        ).filter(RoomUtilityRecord.billing_period == period,
                    UtilityMeterReading.reading_type == 1  # 只统计正常抄表
                    ).count()
        
        # 获取最早的创建时间作为生成时间
        earliest_record = RoomUtilityRecord.query.filter_by(billing_period=period).order_by(
            RoomUtilityRecord.created_at
        ).first()
        # 获取当前账期使用的水电单价（从总主表中当前账期内提取）
        # 从当前账期的第一条记录中获取水电单价
        price_record = RoomUtilityRecord.query.filter_by(billing_period=period).first()
        electric_price = float(price_record.electric_price) if price_record and price_record.electric_price else 0
        water_price = float(price_record.water_price) if price_record and price_record.water_price else 0
        # 记录查询成功日志
        log_operation(
            user_id=current_user.id,
            module="utility",
            operation_type="utility_api",
            action=f"查询账期信息 [账期: {period}, 记录数: {total_records}, 抄表数: {meter_records_count}]",
            result="成功"
        )
        return jsonify({
            'success': True,
            'data': {
                'period': period,
                'start_date': first_record.start_date.isoformat() if first_record.start_date else None,
                'end_date': first_record.end_date.isoformat() if first_record.end_date else None,
                'record_count': total_records,
                'meter_count': meter_records_count,
                'generate_time': earliest_record.created_at.isoformat() if earliest_record and earliest_record.created_at else None,
                'total_electric': float(sum_result.total_electric) if sum_result.total_electric else 0,
                'total_water': float(sum_result.total_water) if sum_result.total_water else 0,
                'total_amount': float(sum_result.total_amount) if sum_result.total_amount else 0,
                # 返回从总主表中提取的当前账期水电单价
                'electric_price': electric_price,
                'water_price': water_price
            }
        })
        
    except Exception as e:
        logging.error(f"获取账期信息失败: {str(e)}")
        # 记录异常日志
        log_operation(
            user_id=current_user.id,
            module="utility",
            operation_type="utility_api",
            action=f"查询账期信息 [账期: {period}, 错误: {str(e)}]",
            result="失败"
        )
        return jsonify({
            'success': False, 
            'error': f'获取账期信息失败: {str(e)}'
        }), 500



# 辅助函数：获取上一个账期
def get_previous_period(current_period):
    """计算上一个账期，格式为YYYY-MM"""
    try:
        year, month = map(int, current_period.split('-'))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
        return f"{year}-{month:02d}"
    except Exception as e:
        logging.error(f"计算上一个账期失败: {str(e)}")
        return None


# 辅助函数：获取房间的历史抄表记录
def get_room_history_readings(room_id, current_period):
    """获取房间的历史抄表记录，包括上月最后一次读数"""
    try:
        # 获取上一个账期
        prev_period = get_previous_period(current_period)
        if not prev_period:
            return []
            
        # 查询上一个账期的主表记录
        prev_main_record = RoomUtilityRecord.query.filter_by(
            room_id=room_id,
            billing_period=prev_period
        ).first()
        
        if not prev_main_record:
            return []
            
        # 查询上一个账期的最后一次抄表记录
        prev_readings = UtilityMeterReading.query.filter_by(
            record_id=prev_main_record.record_id,
            reading_type=1  # 正常抄表
        ).order_by(UtilityMeterReading.reading_date.desc()).limit(1).all()
        
        return prev_readings
    except Exception as e:
        logging.error(f"获取房间历史抄表记录失败: {str(e)}")
        return []


@utility_room_bill_records_bp.route('/by-period', methods=['GET'])
@login_required
@require_permission('utility.view')
def get_records_by_period():
    """按账期批量查询接口"""
    try:
        room_id = request.args.get('room_id', type=int)
        period = request.args.get('period')
        year = request.args.get('year', type=int)
        month = request.args.get('month', type=int)

        if not period and not (year and month):
            # 记录参数错误日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='utility_api',
                action=f"按账期查询记录 [房间ID: {room_id}, 账期: {period}, 年份: {year}, 月份: {month}, 原因: 参数不完整]",
                result="失败"
            )
            return jsonify({'error': '请提供账期（period）或年份+月份'}), 400
            
        # 调用模型的查询方法
        records = RoomUtilityRecord.get_by_period(
            room_id=room_id,
            period=period,
            year=year,
            month=month
        )
        
        # 转换为字典列表
        result = []
        for record in records:
            # 1. 查询当前主表记录对应的子表抄表记录
            current_readings = UtilityMeterReading.query.filter_by(
                record_id=record.record_id,
                reading_type=1  # 正常抄表
            ).all()
            
            # 2. 获取上一个账期的最后一次抄表记录（跨月数据）
            history_readings = get_room_history_readings(record.room_id, record.billing_period)
            
            # 3. 合并当前和历史记录，并按日期排序
            all_readings = current_readings + history_readings
            all_readings.sort(key=lambda x: x.reading_date, reverse=True)
            
            # 4. 转换为字典列表
            sub_records = [reading.to_dict() for reading in all_readings]
            
            result.append({
                'record_id': record.record_id,
                'room_id': record.room_id,
                'billing_period': record.billing_period,
                'start_date': record.start_date.isoformat() if record.start_date else None,
                'end_date': record.end_date.isoformat() if record.end_date else None,
                'electric_current': record.electric_current,
                'electric_previous': record.electric_previous,
                'electric_usage': record.electric_usage,
                'electric_reduction': record.electric_reduction,# 新增：用电量减免度数
                'electric_billing_usage': record.electric_billing_usage,# 新增：用电量计费用量（实际收费的用电量）
                'electric_price': record.electric_price,
                'water_current': record.water_current,
                'water_previous': record.water_previous,
                'water_usage': record.water_usage,
                'water_reduction': record.water_reduction,# 新增：用水量减免度数
                'water_billing_usage': record.water_billing_usage,# 新增：用水量计费用量（实际收费的用水量）
                'water_price': record.water_price,
                'total_electric_fee': record.total_electric_fee,
                'total_water_fee': record.total_water_fee,
                'total_fee': record.total_fee,
                'billing_electric_fee': record.billing_electric_fee,# 新增：计费用量总电费、总水费、总费用
                'billing_water_fee': record.billing_water_fee,
                'billing_total_fee': record.billing_total_fee,
                'room_reduction_fee': record.room_reduction_fee,# 新增：费用减免
                'checked_out_total_fee': record.checked_out_total_fee,
                'actual_total_fee': record.actual_total_fee,
                'status': record.status,
                'created_at': record.created_at.isoformat() if record.created_at else None,
                'updated_at': record.updated_at.isoformat() if record.updated_at else None,
                # 包含所有抄表记录（当前+历史）
                'meter_readings': sub_records
            })
            
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module="utility",
            operation_type="utility_api",
            action=f"按账期查询房间水电费记录 [房间ID: {room_id}, 账期: {period}, 年份: {year}, 月份: {month}, 记录数: {len(result)}]",
            result="成功"
        )
        return jsonify({
            'success': True,
            'data': result,
            'count': len(result)
        })
        
    except Exception as e:
        logging.error(f"按账期查询记录失败: {str(e)}")
        traceback.print_exc()
        
        # 记录错误日志
        log_operation(
            user_id=current_user.id,
            module="utility",
            operation_type="utility_api",
            action=f"按账期查询房间水电费记录 [房间ID: {room_id}, 账期: {period}, 年份: {year}, 月份: {month}, 错误: {str(e)}]",
            result="失败"
        )
        
        return jsonify({'error': f'查询失败: {str(e)}'}), 500
# 一键一键核算接口（仅保留核算功能，保持改动原有标识）
@utility_room_bill_records_bp.route('/fee_bill', methods=['POST'])  # 保持原有路由
@login_required
@require_permission('utility.calculate')
def create_record():  # 保持原有接口名称
    """一键核算费用接口，仅处理批量核算逻辑"""
    try:
        data = request.get_json()
        
        # 仅保留一键核算逻辑，移除单个记录的创建/更新逻辑
        # 验证核算必要参数
        if not data.get('calculate') or not data.get('billing_period'):
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type="bill_update",  # 保持原有日志类型
                action="缺少必要参数：calculate和billing_period为必填项",
                result="失败"
            )
            return jsonify({
                'success': False,
                'error': '缺少必要参数：calculate和billing_period为必填项'
            }), 400
        
        # 1. 查询该账期的所有主表记录
        main_records = RoomUtilityRecord.query.filter_by(
            billing_period=data['billing_period']
        ).all()
        
        if not main_records:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type="bill_update",  # 保持原有日志类型
                action=f"未找到{data['billing_period']}的主表记录，请先确保主表已初始化",
                result="失败"
            )
            return jsonify({
                'success': False,
                'error': f'未找到{data["billing_period"]}的主表记录，请先初始化主表'
            }), 400
        
        # 2. 提取所有主表ID，查询关联的子表抄表记录
        main_record_ids = [record.record_id for record in main_records]
        meter_readings = UtilityMeterReading.query.filter(
            UtilityMeterReading.record_id.in_(main_record_ids),
            UtilityMeterReading.reading_type == 1  # 正常抄表
        ).all()
        
        if not meter_readings:
            return jsonify({
                'success': False,
                'error': f'{data["billing_period"]}的主表记录未关联任何抄表数据，请先完成抄表'
            }), 400
        
        # 3. 调用模型层的批量更新方法（核心逻辑完全由模型层处理）
        updated_count = RoomUtilityRecord.batch_update_from_meter(
            billing_period=data['billing_period'],
            meter_readings=meter_readings,
            main_records=main_records
        )
        db.session.commit()
        
        # 4. 记录操作日志并返回结果
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type="bill_update",  # 保持原有日志类型
            action=f"费用核算：{data['billing_period']}，更新{updated_count}条记录",
            result="成功"
        )
        return jsonify({
            'success': True, 
            'message': f'费用核算完成，共更新{updated_count}条主表记录',
            'updated_count': updated_count
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"核算处理失败: {str(e)}")
        traceback.print_exc()
        
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type="bill_update",  # 保持原有日志类型
            action=f"核算处理失败: {str(e)}",
            result="失败"
        )
        return jsonify({'error': f'核算处理失败: {str(e)}'}), 500


@utility_room_bill_records_bp.route('/<int:record_id>', methods=['DELETE'])
@login_required
@require_permission('utility.delete')
def delete_single_record(record_id):
    """删除单条账单记录（单行删除功能）"""
    try:
        
        # 验证记录存在
        record = RoomUtilityRecord.get_by_id(record_id)
        if not record:
            # 记录失败日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type="delete",
                action=f"删除单条记录 [记录ID: {record_id}, 原因: 记录不存在]",
                result="失败"
            )
            
            return jsonify({'error': f'记录ID={record_id}不存在'}), 404
        
        # 保存记录信息用于日志
        room_id = record.room_id
        billing_period = record.billing_period

        # 连带删除关联的费用补贴子表记录（与清空账期保持一致的is_checkout=2条件）
        subsidy_deleted_count = FeeSubsidyUsage.query.filter(
            FeeSubsidyUsage.room_id == room_id,
            FeeSubsidyUsage.billing_period == billing_period,
            FeeSubsidyUsage.is_checkout == 2
        ).delete(synchronize_session=False)
        
        # 执行删除（调用主表delete方法，会级联删除关联子表）
        record.delete()
        db.session.commit()
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type="delete",
            action=f"删除单条记录 [记录ID: {record_id}, 房间ID: {room_id}, 账期: {billing_period}], "
                   f"连带删除补贴记录数量: {subsidy_deleted_count}",
            result="成功"
        )
        
        logging.info(
            f"用户{current_user.id}删除了账单记录ID={record_id}（房间{room_id}），"
            f"连带删除补贴记录{subsidy_deleted_count}条"
        )
        return jsonify({
            'success': True,
            'message': f'记录ID={record_id}已成功删除',
            'record_id': record_id,
            'subsidy_deleted_count': subsidy_deleted_count
        })
        
    except Exception as e:
        db.session.rollback()
        try:
            logging.error(f"删除单条记录失败: {str(e)}")
        except:
            logging.error(f"删除单条记录失败: {str(e)}")
        
        # 记录错误日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type="delete",
            action=f"删除单条记录 [记录ID: {record_id}, 错误: {str(e)}]",
            result="失败"
        )
        
        return jsonify({'error': f'删除失败: {str(e)}'}), 500



@utility_room_bill_records_bp.route('/batch-delete', methods=['POST'])
@login_required
@require_permission('utility.delete')
def batch_delete_records():
    """批量删除账单记录（支持删除当期账单），连带删除关联的费用补贴记录"""
    try:
        
        # 获取请求数据（要求前端传递JSON格式的record_ids列表）
        data = request.get_json()
        if not data or 'record_ids' not in data:
            # 记录参数错误日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type="delete",
                action=f"批量删除记录 [数据: {str(data)}, 原因: 未提供record_ids参数]",
                result="失败"
            )
            
            return jsonify({'error': '请提供要删除的记录ID列表（参数名：record_ids）'}), 400
        
        record_ids = data['record_ids']
        # 验证参数格式
        if not isinstance(record_ids, list) or len(record_ids) == 0:
            # 记录参数错误日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type="delete",
                action=f"批量删除记录 [record_ids: {str(record_ids)}, 原因: record_ids必须是包含至少一个ID的列表]",
                result="失败"
            )
            return jsonify({'error': 'record_ids必须是包含至少一个ID的列表'}), 400
        
        # 验证所有记录存在并收集关联信息
        records = []
        room_period_pairs = []  # 用于存储(room_id, billing_period)对
        for record_id in record_ids:
            record = RoomUtilityRecord.get_by_id(record_id)
            if not record:
                # 记录错误日志
                log_operation(
                    user_id=current_user.id,
                    module='utility',
                    operation_type="delete",
                    action=f"批量删除记录 [记录ID: {record_id}, 原因: 记录不存在]",
                    result="失败"
                )
                return jsonify({'error': f'记录ID={record_id}不存在，无法删除'}), 404
            records.append(record)
            room_period_pairs.append((record.room_id, record.billing_period))
        
        # 批量删除关联的费用补贴子表记录
        total_subsidy_deleted = 0
        for room_id, billing_period in room_period_pairs:
            deleted = FeeSubsidyUsage.query.filter(
                FeeSubsidyUsage.room_id == room_id,
                FeeSubsidyUsage.billing_period == billing_period,
                FeeSubsidyUsage.is_checkout.in_([1, 2, 3])  # 用IN更简洁
            ).delete(synchronize_session=False)
            total_subsidy_deleted += deleted
        
        # 执行批量删除主表记录
        deleted_ids = []
        for record in records:
            record.delete()  # 调用主表delete方法，级联删除子表
            deleted_ids.append(record.record_id)
        
        db.session.commit()
        
        logging.info(
            f"用户{current_user.id}批量删除了账单记录，ID列表: {deleted_ids}, "
            f"连带删除补贴记录{total_subsidy_deleted}条"
        )
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type="delete",
            action=f"批量删除记录 [删除数量: {len(deleted_ids)}, 删除ID列表: {deleted_ids}, "
                   f"连带删除补贴记录数量: {total_subsidy_deleted}]",
            result="成功"
        )
        return jsonify({
            'success': True,
            'message': f'成功删除{len(deleted_ids)}条记录，连带删除补贴记录{total_subsidy_deleted}条',
            'deleted_ids': deleted_ids,
            'subsidy_deleted_count': total_subsidy_deleted
        })
        
    except Exception as e:
        db.session.rollback()
        try:
            logging.error(f"批量删除记录失败: {str(e)}")
        except:
            logging.error(f"批量删除记录失败: {str(e)}")
            # 记录错误日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type="delete",
            action=f"批量删除记录 [record_ids: {str(request.get_json().get('record_ids'))}, 错误: {str(e)}]",
            result="失败"
        )
        return jsonify({'error': f'删除失败: {str(e)}'}), 500

@utility_room_bill_records_bp.route('/clear-period', methods=['POST'])
@login_required
@require_permission('utility.delete')
def clear_period_data():
    """清空指定账期的主表数据（保留记录，清除抄表和费用信息）"""
    try:
        data = request.get_json()
        if not data or 'billing_period' not in data:
            # 记录参数错误日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type="delete",
                action=f"清空账期数据 [数据: {str(data)}, 原因: 未提供账期参数]",
                result="失败"
            )
            return jsonify({'error': '请提供账期参数（billing_period）'}), 400
            
        period = data['billing_period']
        
        # 查询该账期的所有主表记录
        records = RoomUtilityRecord.query.filter_by(billing_period=period).all()
        if not records:
            # 记录失败日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type="delete",
                action=f"清空账期数据 [账期: {period}, 原因: 未找到主表记录]",
                result="失败"
            )
            return jsonify({
                'success': False,
                'error': f'未找到{period}的主表记录'
            }), 404

        # 提取所有主表记录ID，用于删除关联子表
        record_ids = [record.record_id for record in records]
        
        # 删除关联的在住人员费用子表记录
        room_utility_occupant_deleted = RoomUtilityOccupant.query.filter(
            RoomUtilityOccupant.record_id.in_(record_ids)
        ).delete(synchronize_session=False)
        
        # 删除对应账期+类型的费用补贴子表记录（双重条件）
        subsidy_usage_deleted = FeeSubsidyUsage.query.filter(
            FeeSubsidyUsage.billing_period == period,
            FeeSubsidyUsage.is_checkout.in_([2, 3])  # 用IN更简洁
        ).delete(synchronize_session=False)

        # 删除关联的退宿费用子表记录
       # checkout_utility_deleted = CheckoutUtilityRecord.query.filter(
        #    CheckoutUtilityRecord.record_id.in_(record_ids)
        #).delete(synchronize_session=False)
        
            
        # 清空抄表信息和费用核算信息
        cleared_count = 0
        for record in records:
            # 清除抄表读数信息
            record.electric_previous = Decimal('0.00')
            record.electric_current = Decimal('0.00')
            record.electric_usage = Decimal('0.00')
            record.electric_reduction = Decimal('0.00') # 新增：用电量减免度数
            record.electric_billing_usage = Decimal('0.00') # 新增：用电量计费用量（实际收费的用电量）
            record.water_previous = Decimal('0.00')
            record.water_current = Decimal('0.00')
            record.water_usage = Decimal('0.00') # 新增：用水量减免度数
            record.water_reduction = Decimal('0.00') # 新增：用水量计费用量（实际收费的用水量）
            record.water_billing_usage = Decimal('0.00')
            
            # 清除水电费单价
            record.electric_price = Decimal('0.00')
            record.water_price = Decimal('0.00')

            # 关键修改：临时开启内部更新标志，绕过字段保护
            try:
                # 开启内部更新模式
                record._internal_update = True
                # 重置受保护的实际费用字段
                record.actual_electric_fee = Decimal('0.00')
                record.actual_water_fee = Decimal('0.00')
                record.actual_total_fee = Decimal('0.00')
            finally:
                # 确保无论是否出错，都关闭内部更新模式
                record._internal_update = False

            # 清除费用核算信息
            record.total_electric_fee = Decimal('0.00')
            record.total_water_fee = Decimal('0.00')
            record.total_fee = Decimal('0.00')
            record.billing_electric_fee = Decimal('0.00')# 新增：计费用量总电费、总水费、总费用
            record.billing_water_fee = Decimal('0.00')
            record.billing_total_fee = Decimal('0.00')
            record.actual_electric_fee = Decimal('0.00')
            record.actual_water_fee = Decimal('0.00')
            record.actual_total_fee = Decimal('0.00')
            record.room_reduction_fee = Decimal('0.00') # 新增：费用减免

            # 重置状态为待核算
            record.status = 'pending'
            record.updated_at = datetime.now()
            
            cleared_count += 1
        
        db.session.commit()

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type="delete",
            action=f"清空账期数据 [账期: {period}, 主表清除数量: {cleared_count}, 在住人员子表删除数量: {room_utility_occupant_deleted}，补贴子表删除数量: {subsidy_usage_deleted}]",
            result="成功"
        )
        return jsonify({
            'success': True,
            'message': f'成功清空{period}账期数据，主表{cleared_count}条，在住人员子表{room_utility_occupant_deleted}条',
            'cleared_count': cleared_count,
            'deleted_occupant_records': room_utility_occupant_deleted
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"清空账期数据失败: {str(e)}")
        # 记录错误日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type="delete",
            action=f"清空账期数据 [账期: {data.get('billing_period')}, 错误: {str(e)}]",
            result="失败"
        )
        return jsonify({'error': f'清空失败: {str(e)}'}), 500


@utility_room_bill_records_bp.route('/search', methods=['GET'])
@login_required
@require_permission('utility.view')
def search_records():
    """搜索接口，确保抄表记录正确加载"""
    try:

        # 获取查询参数
        room_id = request.args.get('room_id', type=int)
        room_number = request.args.get('room_number')
        billing_period = request.args.get('billing_period')
        status = request.args.get('status')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        building = request.args.get('building')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # 基础查询 - 强制加载关联的抄表记录和房间信息
        query = RoomUtilityRecord.query.options(
            db.joinedload(RoomUtilityRecord.meter_readings).joinedload(UtilityMeterReading.meter_reader),
            db.joinedload(RoomUtilityRecord.room)
        )
        
        # 应用筛选条件
        if room_id:
            query = query.filter_by(room_id=room_id)
        if billing_period:
            query = query.filter_by(billing_period=billing_period)
        if status:
            query = query.filter_by(status=status)
        if start_date:
            try:
                # 转换为datetime类型，精确到秒
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                start_date_obj = datetime.combine(start_date_obj, time.min)
                query = query.filter(RoomUtilityRecord.start_date >= start_date_obj)
            except ValueError:
                # 记录参数错误日志
                log_operation(
                    user_id=current_user.id,
                    module='utility',
                    operation_type="utility_api",
                    action=f"搜索记录 [开始日期: {start_date}, 原因: 开始日期格式错误]",
                    result="失败"
                )
                return jsonify({'error': '开始日期格式错误，应为YYYY-MM-DD'}), 400
        if end_date:
            try:
                # 转换为datetime类型，精确到秒
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d')
                end_date_obj = datetime.combine(end_date_obj, time.max)
                query = query.filter(RoomUtilityRecord.end_date <= end_date_obj)
            except ValueError:
                # 记录参数错误日志
                log_operation(
                    user_id=current_user.id,
                    module='utility',
                    operation_type="utility_api",
                    action=f"搜索记录 [结束日期: {end_date}, 原因: 结束日期格式错误]",
                    result="失败"
                )
                return jsonify({'error': '结束日期格式错误，应为YYYY-MM-DD'}), 400
        
        # 房间号筛选
        if room_number:
            # 移除房间号中的"-"字符以支持模糊匹配
            clean_room_number = room_number.replace("-", "")
            query = query.filter(RoomUtilityRecord.room.has(Room.room_number.ilike(f'%{clean_room_number}%')))

        # 楼栋筛选
        if building:
            query = query.filter(RoomUtilityRecord.room.has(building=building))
        
        # 执行查询并处理结果
        total = query.count()
        pagination = query.order_by(RoomUtilityRecord.billing_period.desc(), RoomUtilityRecord.room_id.asc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        records = pagination.items
        
        # 转换为字典列表（严格匹配子表字段）
        result = []
        for record in records:
            # 1. 获取当前账期的抄表记录
            current_readings = [reading for reading in record.meter_readings 
                               if reading.reading_type == 1]
            
            # 2. 获取上一个账期的最后一次抄表记录（跨月数据）
            history_readings = get_room_history_readings(record.room_id, record.billing_period)
            
            # 3. 合并当前和历史记录，并按日期排序
            all_readings = current_readings + history_readings
            all_readings.sort(key=lambda x: x.reading_date, reverse=True)
            
            # 处理子表数据
            sub_records = []
            for reading in all_readings:
                try:
                    sub_records.append({
                        'reading_id': reading.id,
                        'reading_date': reading.reading_date.strftime('%Y-%m-%dT%H:%M:%S') if reading.reading_date else None,
                        'electric_reading': float(reading.electric_current) if reading.electric_current else None,
                        'electric_meter_replaced': reading.electric_meter_replaced,
                        'electric_notes': reading.electric_notes,
                        'water_reading': float(reading.water_current) if reading.water_current else None,
                        'water_meter_replaced': reading.water_meter_replaced,
                        'water_notes': reading.water_notes,
                        'reader': reading.meter_reader.name if (reading.meter_reader and hasattr(reading.meter_reader, 'name')) else None,
                        'reading_type': reading.reading_type
                    })
                except Exception as e:
                    logging.warning(f"处理抄表记录{reading.id}失败: {str(e)}")
            
            # 构建主表数据
            result.append({
                'record_id': record.record_id,
                'room_id': record.room_id,
                'billing_period': record.billing_period,
                'start_date': record.start_date.isoformat() if record.start_date else None,
                'end_date': record.end_date.isoformat() if record.end_date else None,
                'electric_previous': record.electric_previous,
                'electric_current': record.electric_current,
                'electric_usage': record.electric_usage,
                'electric_reduction': record.electric_reduction, # 新增：用电量减免度数
                'electric_billing_usage': record.electric_billing_usage, # 新增：用电量计费用量（实际收费的用电量）
                'electric_price': record.electric_price,
                'water_previous': record.water_previous,
                'water_current': record.water_current,
                'water_usage': record.water_usage,
                'water_reduction': record.water_reduction, # 新增：用水量减免度数
                'water_billing_usage': record.water_billing_usage, # 新增：用水量计费用量（实际收费的用水量）
                'water_price': record.water_price,
                'total_electric_fee': record.total_electric_fee,
                'total_water_fee': record.total_water_fee,
                'total_fee': record.total_fee,
                'billing_electric_fee': record.billing_electric_fee,# 新增：计费用量总电费、总水费、总费用
                'billing_water_fee': record.billing_water_fee,
                'billing_total_fee': record.billing_total_fee,
                'room_reduction_fee': record.room_reduction_fee,  # 新增：费用减免
                'checked_out_total_fee': record.checked_out_total_fee,
                'actual_electric_fee': record.actual_electric_fee,
                'actual_water_fee': record.actual_water_fee,
                'actual_total_fee': record.actual_total_fee,
                'status': record.status,
                'created_at': record.created_at.isoformat() if record.created_at else None,
                'updated_at': record.updated_at.isoformat() if record.updated_at else None,
                'meter_readings': sub_records
            })
        # 记录查询成功日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type="utility_api",
            action=f"搜索记录 [房间ID: {room_id}, 账期: {billing_period}, 状态: {status}, 开始日期: {start_date}, 结束日期: {end_date}, 页码: {page}, 每页数量: {per_page}, 总记录数: {total}]",
            result="成功"
        )
        return jsonify({
            'success': True,
            'data': result,
            'pagination': {
                'total': total,
                'page': page,
                'per_page': per_page,
                'pages': pagination.pages
            }
        })
        
    except Exception as e:
        # 确保错误日志能被记录
        logging.error(f"搜索记录失败: {str(e)}")
        # 记录错误日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type="utility_api",
            action=f"搜索记录 [房间ID: {room_id}, 账期: {billing_period}, 状态: {status}, 错误: {str(e)}]",
            result="失败"
        )
        return jsonify({'error': f'搜索失败: {str(e)}'}), 500


@utility_room_bill_records_bp.route('/create_empty_period', methods=['POST'])
@login_required
@require_permission('utility.calculate')
def create_empty_period_records():
    """
    为指定账期创建空的主表记录，为所有房间初始化该账期的记录
    账期格式为YYYY-MM，记录的日期范围为该月1日至当月最后一天
    会先检查账期是否已存在，存在则不允许创建
    """
    try:
        data = request.get_json()
        
        # 验证必要参数
        if not data or 'billing_period' not in data:
            # 记录参数错误日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='bill_update',
                action=f"创建空账期记录 [数据: {str(data)}, 原因: 未提供账期参数]",
                result="失败"
            )
            return jsonify({
                'success': False,
                'error': '请提供账期参数（billing_period，格式：YYYY-MM）'
            }), 400
            
        billing_period = data['billing_period']
        
        # 验证账期格式
        try:
            datetime.strptime(billing_period, '%Y-%m')
        except ValueError:
            # 记录参数错误日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='bill_update',
                action=f"创建空账期记录 [账期: {billing_period}, 原因: 账期格式错误]",
                result="失败"
            )
            return jsonify({
                'success': False,
                'error': '账期格式错误，应为YYYY-MM'
            }), 400
        
        # 可选参数：指定房间ID列表（如果提供）
        room_ids = data.get('room_ids')
        if room_ids is not None and (not isinstance(room_ids, list) or not all(isinstance(id, int) for id in room_ids)):
            # 记录参数错误日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='bill_update',
                action=f"创建空账期记录 [room_ids: {str(room_ids)}, 原因: room_ids必须是整数列表]",
                result="失败"
            )
            return jsonify({
                'success': False,
                'error': 'room_ids必须是整数列表或不提供'
            }), 400
        
        # 调用模型方法创建空记录
        created_count = RoomUtilityRecord.create_empty_records_for_period(
            billing_period=billing_period,
            room_ids=room_ids
        )

        db.session.commit()
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='bill_update',
            action=f"为账期创建空记录 [账期: {billing_period}, 创建数量: {created_count}, 是否指定房间: {room_ids is not None}]",
            result="成功"
        )
        return jsonify({
            'success': True,
            'message': f'成功为账期{billing_period}创建{created_count}条空记录',
            'created_count': created_count,
            'billing_period': billing_period
        })
        
    except ValueError as e:
        # 处理账期已存在等预期错误
        # 记录错误日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='bill_update',
            action=f"创建空账期记录 [账期: {data.get('billing_period')}, 错误: {str(e)}]",
            result="失败"
        )
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
    except Exception as e:
        db.session.rollback()
        logging.error(f"创建指定账期空记录失败: {str(e)}")
        
        # 记录错误日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='bill_update',
            action=f"创建指定账期空记录 [账期: {data.get('billing_period')}, 错误: {str(e)}]",
            result="失败"
        ) 
        return jsonify({'error': f'创建失败: {str(e)}'}), 500

@utility_room_bill_records_bp.route('/record_details/<int:record_id>', methods=['GET'])
@login_required
@require_permission('utility.view')

def get_record_details(record_id):
    """
    根据记录ID查询详细信息，包括：
    - 主表记录基本信息
    - 住宿人员信息（数量、具体人员）
    - 费用分摊详情（在住人员和退宿人员）
    - 抄表记录、用量及单价信息
    """
    try:
        # 1. 获取主表记录
        main_record = RoomUtilityRecord.get_by_id(record_id)
        if not main_record:
            # 记录查询失败日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='utility_api',
                action=f"查询记录详情 [记录ID: {record_id}, 原因: 记录不存在]",
                result="失败"
            )
            return jsonify({
                'success': False,
                'error': f'记录ID={record_id}不存在'
            }), 404
        
        # 2. 获取房间信息
        room = Room.query.get(main_record.room_id)
        room_info = {
            'room_id': main_record.room_id,
            'room_number': room.room_number if room else '未知',
            'building': room.building if room else '未知',
            'capacity': room.capacity if room else 0,
            'current_occupancy': room.current_occupancy if room else 0
        }
        
        # 只读取已生成的分摊记录，不做任何修改
        resident_subrecords = RoomUtilityOccupant.query.filter_by(
            record_id=record_id
        ).all()
        logging.info(f"子表中查询到的在住人员分摊记录数: {len(resident_subrecords)}")
        
        # 新增：检查子表数据是否存在，不存在则警告（但不修改数据）
        if not resident_subrecords:
            logging.warning(
                f"记录ID={record_id}的子表分摊记录不存在，可能是生成阶段出现问题"
            )
        # 3. 关联住宿表和用户表，生成current_occupants（仅查询，不修改）
        current_occupants = []
        for subrecord in resident_subrecords:
            user = User.query.get(subrecord.user_id)
            user_name = user.name if user else f'未知用户({subrecord.user_id})'
            
            dorm = Dorm.query.filter(
                Dorm.user_id == subrecord.user_id,
                Dorm.room_id == main_record.room_id
            ).first()
            is_transferred = dorm and dorm.check_out_date is not None
            
            current_occupants.append({
                'user_id': subrecord.user_id,
                'user_name': user_name,
                'stay_days': subrecord.stay_days,
                'electric_fee': float(subrecord.electric_fee or 0),
                'water_fee': float(subrecord.water_fee or 0),
                'total_fee': float(subrecord.total_fee or 0),
                'user_reduction_fee': float(subrecord.user_reduction_fee or 0), #减免费用
                'payable_fee': float(subrecord.payable_fee or 0), #应付费用
                'is_transferred': dorm and dorm.check_out_date is not None and main_record.start_date <= dorm.check_out_date <= main_record.end_date
            })
        # 5. 处理退宿人员信息及费用
        # 4. 退宿人员查询（同样仅读取）
        checkout_occupants = []
        checkout_subrecords = CheckoutUtilityRecord.query.filter_by(record_id=record_id).all()
        for subrecord in checkout_subrecords:
            user = User.query.get(subrecord.user_id)
            checkout_occupants.append({
                'id': subrecord.id,
                'user_id': subrecord.user_id,
                'user_name': user.name if user else f'未知用户({subrecord.user_id})',
                'checkout_date': subrecord.checkout_date.isoformat() if subrecord.checkout_date else None,
                'user_period_days': subrecord.user_period_days,
                'user_original_electric_fee': float(subrecord.user_original_electric_fee or 0),
                'user_original_water_fee': float(subrecord.user_original_water_fee or 0),
                'user_original_total_fee': float(subrecord.user_original_total_fee or 0),
                'user_billing_electric_fee': float(subrecord.user_billing_electric_fee or 0),# 基于减免后用量的费用字段
                'user_billing_water_fee': float(subrecord.user_billing_water_fee or 0),
                'user_billing_total_fee': float(subrecord.user_billing_total_fee or 0),
                'user_proportional_reduction': float(subrecord.user_proportional_reduction or 0),
                'user_independent_reduction': float(subrecord.user_independent_reduction or 0),
                'user_reduction_electric': float(subrecord.user_reduction_electric or 0),  # 用户级减免电用量
                'user_reduction_water': float(subrecord.user_reduction_water or 0),        # 用户级减免水用量
                'payable_fee': float(subrecord.payable_fee or 0) #应付费用
            })
        
        # 6. 整理抄表记录信息
        meter_records = {
            # 电费抄表记录
            'electric': {
                'previous_reading': float(main_record.electric_previous or 0),  # 上期读数
                'current_reading': float(main_record.electric_current or 0),    # 本期读数
                'usage': float(main_record.electric_usage or 0),                # 本期用量
                'electric_reduction': float(main_record.electric_reduction or 0),                # 新增：用电量减免度数
                'electric_billing_usage': float(main_record.electric_billing_usage or 0),        # 新增：用电量计费用量（实际收费的用电量）
                'unit_price': float(main_record.electric_price or 0),           # 单价
                'total_cost': float(main_record.total_electric_fee or 0)        # 总费用
            },
            # 水费抄表记录
            'water': {
                'previous_reading': float(main_record.water_previous or 0),      # 上期读数
                'current_reading': float(main_record.water_current or 0),        # 本期读数
                'usage': float(main_record.water_usage or 0),                    # 本期用量
                'water_reduction': float(main_record.water_reduction or 0),                # 新增：用水量减免度数
                'water_billing_usage': float(main_record.water_billing_usage or 0),        # 新增：用水量计费用量（实际收费的用水量）
                'unit_price': float(main_record.water_price or 0),               # 单价
                'total_cost': float(main_record.total_water_fee or 0)            # 总费用
            }
        }
        
        # 7. 整理返回结果
        result = {
            'success': True,
            'data': {
                # 主记录基本信息
                'record_id': main_record.record_id,
                'billing_period': main_record.billing_period,
                'start_date': main_record.start_date.isoformat(),
                'end_date': main_record.end_date.isoformat(),
                'status': main_record.status,
                
                # 房间信息
                'room_info': room_info,
                
                # 人员统计
                'total_occupants': len(current_occupants) + len(checkout_occupants),
                'current_occupants_count': len(current_occupants),
                'checkout_occupants_count': len(checkout_occupants),
                
                # 人员详情
                'current_occupants': current_occupants,
                'checkout_occupants': checkout_occupants,
                
                # 费用汇总
                'total_fee': {
                    'electric': float(main_record.total_electric_fee or 0),
                    'water': float(main_record.total_water_fee or 0),
                    'total': float(main_record.total_fee or 0),
                    'billing_electric_fee': float(main_record.billing_electric_fee or 0),
                    'billing_water_fee': float(main_record.billing_water_fee or 0),
                    'billing_total_fee': float(main_record.billing_total_fee or 0),
                    'room_reduction_fee': float(main_record.room_reduction_fee or 0)
                },
                'actual_fee': {
                    'electric': float(main_record.actual_electric_fee or 0),
                    'water': float(main_record.actual_water_fee or 0),
                    'total': float(main_record.actual_total_fee or 0)
                },
                'checked_out_fee': {
                    'electric': float(main_record.checked_out_electric_fee or 0),
                    'water': float(main_record.checked_out_water_fee or 0),
                    'total': float(main_record.checked_out_total_fee or 0)
                },
                
                # 抄表记录信息（包含用量和单价）
                'meter_records': meter_records
            }
        }
        # 记录查询成功日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type="utility_api",
            action=f"查询记录详情 [记录ID: {record_id}, 房间ID: {main_record.room_id}, 账期: {main_record.billing_period}, 在住人数: {len(current_occupants)}, 退宿人数: {len(checkout_occupants)}]",
            result="成功"
        )
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"查询记录详情失败: {str(e)}", exc_info=True)
        # 记录错误日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type="utility_api",
            action=f"查询记录详情 [记录ID: {record_id}, 错误: {str(e)}]",
            result="失败"
        )
        
        return jsonify({
            'success': False,
            'error': f'查询失败: {str(e)}'
        }), 500
