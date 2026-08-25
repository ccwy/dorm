from flask import request, jsonify
from utils.db import db
from models.user import User
from models.room import Room
from models.utility_room_bill_record import RoomUtilityRecord
from models.utility_room_bill_checkout import CheckoutUtilityRecord
from models.utility_room_meter import UtilityMeterReading
from flask_login import login_required, current_user
from utils.log import log_operation
import traceback
from datetime import datetime
from decimal import Decimal, InvalidOperation
import logging
from .utility_room_bill_checkout import utility_room_bill_checkout_bp  # 导入退宿费用子表主蓝图
from models.fee_subsidy_usage import FeeSubsidyUsage  # 导入费用补贴使用记录模型
# 导入admin_required装饰器
from blueprints.system_settings import admin_required

@utility_room_bill_checkout_bp.route('/create', methods=['POST'])
@login_required
@admin_required
def create_checkout_record():
    """创建退宿费用记录"""
    try:
        # 获取请求数据
        data = request.get_json()
        
        # 验证必要参数
        required_fields = ['user_id', 'room_id', 'checkout_date']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({
                    'success': False,
                    'message': f'缺少必要参数: {field}'
                }), 400
        
        # 解析参数
        user_id = data['user_id']
        room_id = data['room_id']
        
        
        # 解析退宿日期（支持带时间的格式）
        try:
            # 尝试多种日期时间格式
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
                try:
                    checkout_date = datetime.strptime(data['checkout_date'], fmt)
                    break
                except ValueError:
                    continue
            else:
                # 如果所有格式都尝试失败
                raise ValueError("无法解析日期格式")
        except ValueError:
            return jsonify({
                'success': False,
                'message': '退宿日期格式错误，应为YYYY-MM-DD或YYYY-MM-DD HH:MM或YYYY-MM-DD HH:MM:SS'
            }), 400
        
        # 解析抄表数据（可选）
        electric_reading = None
        water_reading = None
        
        if 'electric_reading' in data and data['electric_reading'] is not None:
            try:
                electric_reading = Decimal(str(data['electric_reading']))
            except (InvalidOperation, TypeError):
                return jsonify({
                    'success': False,
                    'message': '电表读数格式错误'
                }), 400
                
        if 'water_reading' in data and data['water_reading'] is not None:
            try:
                water_reading = Decimal(str(data['water_reading']))
            except (InvalidOperation, TypeError):
                return jsonify({
                    'success': False,
                    'message': '水表读数格式错误'
                }), 400
        
        

        # 验证用户和房间是否存在
        user = User.query.get(user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': f'用户ID不存在: {user_id}'
            }), 404
            
        room = Room.query.get(room_id)
        if not room:
            return jsonify({
                'success': False,
                'message': f'房间ID不存在: {room_id}'
            }), 404

        reading_date = None
        if data.get('checkout_date'):
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
                try:
                    reading_date = datetime.strptime(data['checkout_date'], fmt)
                    break
                except ValueError:
                    continue
            if reading_date is None:
                return jsonify({
                    'success': False, 
                    'message': '日期格式错误，请使用 yyyy-mm-dd 或 yyyy-mm-dd HH:MM 或 yyyy-mm-dd HH:MM:SS'
                }), 400

        #如果抄表记录不为空则创建抄表记录
        if (electric_reading or water_reading):
            # 获取用户姓名
            user = User.query.get(user_id)
            user_name = user.name if user else f"未知用户({user_id})"

            # 调用模型方法创建记录
            UtilityMeterReading.create_reading(
                room_id=room_id,
                water_current=water_reading,
                electric_current=electric_reading,
                reading_date=reading_date or datetime.now(),
                meter_reader_id=current_user.id,
                water_notes=f"自动创建水表退宿抄表记录 - 用户:{user_name}",
                electric_notes=f"自动创建电表退宿抄表记录 - 用户:{user_name}",
                reading_type=2,  # 退宿抄表类型标识
                user_id=user_id,
                water_meter_replaced=False,
                electric_meter_replaced=False
            )

            # 解析是否计算费用参数（默认为True）
            calculate_fee = data.get('calculate_fee', True)
            if not isinstance(calculate_fee, bool):
                return jsonify({
                    'success': False,
                    'message': 'calculate_fee必须是布尔值'
                 }), 400
        else:
            calculate_fee = False
            electric_reading = Decimal('0')
            water_reading = Decimal('0')

        # 创建退宿费用记录
        checkout_record = CheckoutUtilityRecord.create_from_checkout(
            room_id=room_id,
            user_id=user_id,
            checkout_date=checkout_date,
            electric_reading=electric_reading,
            water_reading=water_reading,
            calculate_fee=calculate_fee
        )
        
        db.session.commit()
                # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='checkout_fee',
            action=f'创建退宿费用记录: 用户ID={user_id}, 房间ID={room_id}',
            result='成功'
        )
        # 记录抄表操作日志
        log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='meter',
                action=f'创建退宿抄表记录: 用户ID={user_id}, 房间ID={room_id}',
                result='成功'
        )

        # 返回成功响应
        return jsonify({
            'success': True,
            'message': '退宿费用记录创建成功',
            'data': {
                'id': checkout_record.id,
                'record_id': checkout_record.record_id,
                'total_fee': float(checkout_record.user_billing_total_fee) if checkout_record.user_billing_total_fee else 0,
                'checkout_status': checkout_record.checkout_status
            }
        }), 201
        
    except Exception as e:
        db.session.rollback()
        # 记录错误日志
        logging.error(f"创建退宿费用记录失败: {str(e)}")
        traceback.print_exc()
        
        # 记录失败日志
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else None,
            module='utility',
            operation_type='checkout_fee',
            action=f'创建退宿费用记录失败: {str(e)}',
            result='失败'
        )
        
        # 返回错误响应
        return jsonify({
            'success': False,
            'message': f'创建退宿费用记录失败: {str(e)}'
        }), 500

@utility_room_bill_checkout_bp.route('/delete', methods=['POST'])
@login_required
@admin_required
def delete_checkout_record():
    """删除单条退宿费用记录，同步删除关联的补贴使用记录并减少主表已结算费用"""
    try:
        data = request.get_json() or {}
        
        # 验证必要参数
        record_id = data.get('id')
        if not record_id:
            log_operation(
                user_id=current_user.id,
                module="utility",
                operation_type="delete",
                action=f"删除退宿费用记录失败，缺少记录ID参数",
                result="失败"
            )
            return jsonify({'success': False, 'message': '缺少记录ID参数'}), 400
        
        # 查询记录是否存在
        record = CheckoutUtilityRecord.query.get(record_id)
        if not record:
            log_operation(
                user_id=current_user.id,
                module="utility",
                operation_type="delete",
                action=f"删除退宿费用记录 [记录ID: {record_id}]失败，未找到退宿记录",
                result="失败"
            )
            return jsonify({'success': False, 'message': f'未找到ID为{record_id}的退宿记录'}), 404
        
        # 从主表获取账期信息
        main_record = RoomUtilityRecord.query.get(record.record_id)
        if not main_record:
            log_operation(
                user_id=current_user.id,
                module="utility",
                operation_type="delete",
                action=f"删除退宿费用记录 [记录ID: {record_id}]失败，关联的主表记录不存在",
                result="失败"
            )
            return jsonify({'success': False, 'message': f'关联的主表记录不存在'}), 404
        
        # 关键新增：记录要删除的费用金额，用于从主表中减去
        deleted_electric_fee = record.user_billing_electric_fee or 0
        deleted_water_fee = record.user_billing_water_fee or 0
        
        # 关键新增：从主表已结算费用中减去当前退宿记录的费用
        # 使用负数调用add_checkout_fees方法来实现减法
        main_record.add_checkout_fees(-deleted_electric_fee, -deleted_water_fee)
        
        billing_period = main_record.billing_period
        user_id = record.user_id
        room_id = record.room_id  # 从退宿子表获取房间ID
        
        # 查找并删除关联的抄表记录（退宿类型且用户ID匹配）
        meter_readings = UtilityMeterReading.query.filter(
            UtilityMeterReading.record_id == record.record_id,
            UtilityMeterReading.reading_type == 2,  # 退宿抄表类型
            UtilityMeterReading.user_id == user_id  # 验证用户ID匹配
        ).all()
        
        # 查找并删除关联的费用补贴使用记录（退宿相关且账期匹配）
        subsidy_usages = FeeSubsidyUsage.query.filter(
            FeeSubsidyUsage.user_id == user_id,
            FeeSubsidyUsage.room_id == room_id,
            FeeSubsidyUsage.billing_period == billing_period,  # 验证账期匹配
            FeeSubsidyUsage.is_checkout == 1  # 1表示退宿费用子表上传
        ).all()
        
        deleted_meter_ids = []
        if meter_readings:
            deleted_meter_ids = [reading.id for reading in meter_readings]
            for reading in meter_readings:
                db.session.delete(reading)
        
        deleted_subsidy_ids = []
        if subsidy_usages:
            deleted_subsidy_ids = [usage.id for usage in subsidy_usages]
            for usage in subsidy_usages:
                db.session.delete(usage)

        # 执行删除操作
        db.session.delete(record)
        db.session.commit()
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module="utility",
            operation_type="delete",
            action=f"删除退宿费用记录 [记录ID: {record_id}, 账期: {billing_period}, 用户ID: {user_id}, 房间ID: {room_id}]，"
                   f"同步减少主表已结算费用: 电费{deleted_electric_fee}元, 水费{deleted_water_fee}元，"
                   f"同步删除抄表记录ID: {deleted_meter_ids}，同步删除补贴使用记录ID: {deleted_subsidy_ids}",
            result="成功"
        )
        
        return jsonify({
            'success': True,
            'message': '退宿记录已成功删除',
            'data': {
                'deleted_id': record_id,
                'billing_period': billing_period,
                'deleted_electric_fee': float(deleted_electric_fee),
                'deleted_water_fee': float(deleted_water_fee),
                'deleted_meter_ids': deleted_meter_ids,
                'deleted_subsidy_ids': deleted_subsidy_ids
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"删除退宿记录失败: {str(e)}\n{traceback.format_exc()}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else None,
            module="utility",
            operation_type="delete",
            action=f"删除退宿记录失败 [记录ID: {record_id if 'record_id' in locals() else ''}]: {str(e)}",
            result="失败"
        )
        return jsonify({
            'success': False,
            'message': '删除退宿记录失败',
            'error': str(e)
        }), 500


@utility_room_bill_checkout_bp.route('/batch_delete', methods=['POST'])
@login_required
@admin_required
def batch_delete_checkout_records():
    """批量删除退宿费用记录，同步删除关联记录并减少主表已结算费用"""
    try:
        data = request.get_json() or {}
        
        # 验证必要参数
        record_ids = data.get('ids', [])
        if not isinstance(record_ids, list) or len(record_ids) == 0:
            log_operation(
                user_id=current_user.id,
                module="utility",
                operation_type="delete",
                action=f"批量删除退宿费用记录失败，请提供有效的记录ID列表",
                result="失败"
            )
            return jsonify({'success': False, 'message': '请提供有效的记录ID列表'}), 400
        
        # 验证所有记录是否存在
        existing_records = CheckoutUtilityRecord.query.filter(
            CheckoutUtilityRecord.id.in_(record_ids)
        ).all()
        
        existing_ids = [record.id for record in existing_records]
        non_existing_ids = [id for id in record_ids if id not in existing_ids]
        
        # 处理不存在的记录ID
        if non_existing_ids:
            logging.warning(f"批量删除时发现不存在的记录ID: {non_existing_ids}")

        # 查找并删除关联的抄表记录和补贴使用记录，带用户ID和账期验证
        deleted_meter_ids = []
        deleted_subsidy_ids = []
        valid_records = []
        operation_details = []
        total_deleted_electric = 0
        total_deleted_water = 0
        
        # 先验证所有记录的用户和主表记录是否存在
        for record in existing_records:
            # 验证用户是否存在
            user = User.query.get(record.user_id)
            if not user:
                log_operation(
                    user_id=current_user.id,
                    module="utility",
                    operation_type="delete",
                    action=f"批量删除退宿记录跳过无效记录 [记录ID: {record.id}, 无效用户ID: {record.user_id}]",
                    result="警告"
                )
                continue
            
            # 验证主表记录是否存在并获取账期
            main_record = RoomUtilityRecord.query.get(record.record_id)
            if not main_record:
                log_operation(
                    user_id=current_user.id,
                    module="utility",
                    operation_type="delete",
                    action=f"批量删除退宿记录跳过无效记录 [记录ID: {record.id}, 关联主表记录不存在]",
                    result="警告"
                )
                continue
                
            valid_records.append({
                'checkout_record': record,
                'main_record': main_record
            })
        
        # 执行批量删除
        if valid_records:
            # 逐条处理确保用户ID和账期匹配
            for item in valid_records:
                checkout_record = item['checkout_record']
                main_record = item['main_record']
                user_id = checkout_record.user_id
                room_id = checkout_record.room_id  # 从退宿子表获取房间ID
                billing_period = main_record.billing_period
                
                # 关键新增：获取要删除的费用金额
                deleted_electric = checkout_record.user_billing_electric_fee or 0
                deleted_water = checkout_record.user_billing_water_fee or 0
                total_deleted_electric += float(deleted_electric)
                total_deleted_water += float(deleted_water)
                
                # 关键新增：从主表已结算费用中减去
                main_record.add_checkout_fees(-deleted_electric, -deleted_water)
                
                # 只删除匹配当前退宿记录用户ID的抄表记录
                user_meters = UtilityMeterReading.query.filter(
                    UtilityMeterReading.record_id == checkout_record.record_id,
                    UtilityMeterReading.reading_type == 2,  # 退宿抄表类型
                    UtilityMeterReading.user_id == user_id  # 验证用户ID匹配
                ).all()
                
                if user_meters:
                    deleted_meter_ids.extend([m.id for m in user_meters])
                    for m in user_meters:
                        db.session.delete(m)
                
                # 只删除匹配当前退宿记录的补贴使用记录（带账期验证）
                user_subsidies = FeeSubsidyUsage.query.filter(
                    FeeSubsidyUsage.user_id == user_id,
                    FeeSubsidyUsage.room_id == room_id,
                    FeeSubsidyUsage.billing_period == billing_period,  # 验证账期匹配
                    FeeSubsidyUsage.is_checkout == 1  # 1表示退宿费用子表上传
                ).all()
                
                if user_subsidies:
                    deleted_subsidy_ids.extend([s.id for s in user_subsidies])
                    for s in user_subsidies:
                        db.session.delete(s)
                
                operation_details.append(
                    f"记录ID: {checkout_record.id}, 账期: {billing_period}, "
                    f"用户ID: {user_id}, 房间ID: {room_id}, "
                    f"删除费用: 电费{deleted_electric}元, 水费{deleted_water}元"
                )

            # 保存用于日志的信息
            checkout_ids = [item['checkout_record'].id for item in valid_records]
            
            CheckoutUtilityRecord.query.filter(
                CheckoutUtilityRecord.id.in_(checkout_ids)
            ).delete(synchronize_session=False)
            
            db.session.commit()
            
            # 记录操作日志
            log_operation(
                user_id=current_user.id,
                module="utility",
                operation_type="delete",
                action=f"批量删除退宿费用记录 [共{len(valid_records)}条, 详情: {'; '.join(operation_details)}]，"
                       f"总计减少主表已结算费用: 电费{total_deleted_electric}元, 水费{total_deleted_water}元，"
                       f"同步删除抄表记录ID: {deleted_meter_ids}，同步删除补贴使用记录ID: {deleted_subsidy_ids}",
                result="成功"
            )
        
        return jsonify({
            'success': True,
            'message': f'成功删除{len(valid_records)}条退宿记录',
            'data': {
                'deleted_ids': [item['checkout_record'].id for item in valid_records],
                'billing_periods': list({item['main_record'].billing_period for item in valid_records}),
                'total_deleted_electric': total_deleted_electric,
                'total_deleted_water': total_deleted_water,
                'deleted_meter_ids': deleted_meter_ids,
                'deleted_subsidy_ids': deleted_subsidy_ids,
                'not_found_ids': non_existing_ids,
                'invalid_records': [id for id in existing_ids if id not in [item['checkout_record'].id for item in valid_records]],
                'total_deleted': len(valid_records)
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"批量删除退宿记录失败: {str(e)}\n{traceback.format_exc()}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else 0,
            module="utility",
            operation_type="delete",
            action=f"批量删除退宿记录失败 [ID列表: {record_ids if 'record_ids' in locals() else ''}]: {str(e)}",
            result="失败"
        )
        return jsonify({
            'success': False,
            'message': '批量删除退宿记录失败',
            'error': str(e)
        }), 500


@utility_room_bill_checkout_bp.route('/delete_period', methods=['POST'])
@login_required
@admin_required
def delete_period_records():
    """删除指定账期的所有退宿费用记录，同步更新主表已结算费用"""
    try:
        data = request.get_json() or {}
        
        # 验证必要参数
        billing_period = str(data.get('billing_period', '')).strip()
        if not billing_period:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"删除账期退宿记录失败，缺少账期参数",
                result="失败"
            )
            return jsonify({'success': False, 'message': '缺少账期参数'}), 400
        
        # 验证账期格式
        try:
            datetime.strptime(billing_period, '%Y-%m')
        except ValueError:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"删除账期退宿记录 [账期: {billing_period}]失败，账期格式错误",
                result="失败"
            )
            return jsonify({
                'success': False, 
                'message': '账期格式错误，应为YYYY-MM'
            }), 400
        
        # 查询该账期下的所有主表记录
        main_records = RoomUtilityRecord.query.filter(
            RoomUtilityRecord.billing_period == billing_period
        ).all()
        
        if not main_records:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"删除账期退宿记录 [账期: {billing_period}]失败，未找到{format_period(billing_period)}的任何账单记录",
                result="失败"
            )
            return jsonify({
                'success': False, 
                'message': f'未找到{format_period(billing_period)}的任何账单记录'
            }), 404
        
        # 获取所有相关的退宿记录ID
        main_record_ids = [record.record_id for record in main_records]
        checkout_records = CheckoutUtilityRecord.query.filter(
            CheckoutUtilityRecord.record_id.in_(main_record_ids)
        ).all()
        
        if not checkout_records:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"删除账期退宿记录 [账期: {billing_period}]失败，{format_period(billing_period)}没有退宿费用记录",
                result="失败"
            )
            return jsonify({
                'success': False, 
                'message': f'{format_period(billing_period)}没有退宿费用记录'
            }), 404
        
        # 保存用于日志的信息
        record_ids = [record.id for record in checkout_records]
        total_deleted_electric = 0
        total_deleted_water = 0
        
        # 查找并删除关联的抄表记录和补贴使用记录（带用户ID和账期验证）
        deleted_meter_ids = []
        deleted_subsidy_ids = []
        
        for checkout_record in checkout_records:
            # 获取主表信息（再次验证账期）
            main_record = RoomUtilityRecord.query.get(checkout_record.record_id)
            if not main_record or main_record.billing_period != billing_period:
                logging.warning(
                    f"跳过不匹配账期的记录 [退宿记录ID: {checkout_record.id}, "
                    f"主表账期: {main_record.billing_period if main_record else '不存在'}, "
                    f"目标账期: {billing_period}]"
                )
                continue
                
            user_id = checkout_record.user_id
            room_id = checkout_record.room_id  # 从退宿子表获取房间ID
            
            # 关键新增：获取要删除的费用金额
            deleted_electric = checkout_record.user_billing_electric_fee or 0
            deleted_water = checkout_record.user_billing_water_fee or 0
            total_deleted_electric += float(deleted_electric)
            total_deleted_water += float(deleted_water)
            
            # 关键新增：从主表已结算费用中减去
            main_record.add_checkout_fees(-deleted_electric, -deleted_water)
            
            # 删除关联的抄表记录
            meter_readings = UtilityMeterReading.query.filter(
                UtilityMeterReading.record_id == checkout_record.record_id,
                UtilityMeterReading.reading_type == 2,  # 退宿抄表类型
                UtilityMeterReading.user_id == user_id  # 验证用户ID匹配
            ).all()
            
            if meter_readings:
                deleted_meter_ids.extend([reading.id for reading in meter_readings])
                for reading in meter_readings:
                    db.session.delete(reading)
            
            # 删除关联的补贴使用记录（带账期验证）
            subsidy_usages = FeeSubsidyUsage.query.filter(
                FeeSubsidyUsage.user_id == user_id,
                FeeSubsidyUsage.room_id == room_id,
                FeeSubsidyUsage.billing_period == billing_period,  # 验证账期匹配
                FeeSubsidyUsage.is_checkout == 1  # 1表示退宿费用子表上传
            ).all()
            
            if subsidy_usages:
                deleted_subsidy_ids.extend([usage.id for usage in subsidy_usages])
                for usage in subsidy_usages:
                    db.session.delete(usage)
        
        # 执行删除操作
        CheckoutUtilityRecord.query.filter(
            CheckoutUtilityRecord.record_id.in_(main_record_ids)
        ).delete(synchronize_session=False)
        
        db.session.commit()
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"删除账期所有退宿记录 [账期: {billing_period}, 共{len(record_ids)}条记录，"
                   f"总计减少主表已结算费用: 电费{total_deleted_electric}元, 水费{total_deleted_water}元，"
                   f"同步删除抄表记录ID: {deleted_meter_ids}，同步删除补贴使用记录ID: {deleted_subsidy_ids}]",
            result="成功"
        )
        
        return jsonify({
            'success': True,
            'message': f'已成功删除{format_period(billing_period)}的所有退宿费用记录',
            'data': {
                'billing_period': billing_period,
                'deleted_count': len(record_ids),
                'total_deleted_electric': total_deleted_electric,
                'total_deleted_water': total_deleted_water,
                'deleted_meter_ids': deleted_meter_ids,
                'deleted_subsidy_ids': deleted_subsidy_ids,
                'deleted_ids': record_ids
            }
        })
        
    except Exception as e:
        db.session.rollback()
        logging.error(f"删除账期记录失败: {str(e)}\n{traceback.format_exc()}")
        log_operation(
            user_id=current_user.id if current_user.is_authenticated else None,
            module='utility',
            operation_type='delete',
            action=f"删除账期记录失败 [账期: {billing_period if 'billing_period' in locals() else ''}]: {str(e)}",
            result="失败"
        )
        return jsonify({
            'success': False,
            'message': '删除账期记录失败',
            'error': str(e)
        }), 500

# 辅助函数：格式化账期显示
def format_period(period):
    """将YYYY-MM格式的账期转换为更友好的显示格式"""
    if not period:
        return ""
    try:
        year, month = period.split('-')
        return f"{year}年{month}月"
    except ValueError:
        return period
