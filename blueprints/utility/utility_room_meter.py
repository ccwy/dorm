from flask import Blueprint, request, jsonify, render_template, send_from_directory, send_file, flash, redirect, url_for
import logging
import os
from utils.db import db
from models.utility.utility_room_meter import UtilityMeterReading
from models.room.room import Room
from models.user.user import User
from models.utility.utility_room_bill_record import RoomUtilityRecord
from config import Config
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.room_meter_photo import room_meter_manager
import traceback
from datetime import datetime

from utils.auth import require_permission

utility_room_meter_bp = Blueprint('utility_room_meter', __name__, url_prefix='/utility-meter')


def generate_page_range(current_page, total_pages, show_pages=5):
    if total_pages <= show_pages:
        return list(range(1, total_pages + 1))
    half = show_pages // 2
    start = max(1, current_page - half)
    end = min(total_pages, start + show_pages - 1)
    if end - start < show_pages - 1:
        start = max(1, end - show_pages + 1)
    page_range = []
    if start > 1:
        page_range.append(1)
        if start > 2:
            page_range.append('...')
    page_range.extend(range(start, end + 1))
    if end < total_pages:
        if end < total_pages - 1:
            page_range.append('...')
        page_range.append(total_pages)
    return page_range


# 页面路由 - 模板路径: templates/utility_bill
@utility_room_meter_bp.route('/utility_reading', methods=['GET', 'POST'])
@login_required
@require_permission('utility.reading')
def utility_reading():
    """抄表登记页面 - 支持楼栋筛选、房间搜索、分页和获取最新抄表记录，以及单个和批量表单提交保存"""
    if request.method == 'POST':
        try:
            # 提取筛选参数，用于redirect时保留页面状态
            building_filter = request.form.get('building', '')
            search_room = request.form.get('search_room', '')
            page = request.form.get('page', 1, type=int)
            
            # 检查是否为批量保存请求
            is_batch = request.form.get('is_batch') == 'true'
            
            if is_batch:
                # 批量保存处理
                try:
                    # 获取批量数据
                    room_ids = request.form.getlist('room_ids[]', type=int)
                    water_currents = request.form.getlist('water_currents[]')
                    electric_currents = request.form.getlist('electric_currents[]')
                    reading_date_str = request.form.get('batch_reading_date', '')
                    billing_period = request.form.get('billing_period', '').strip()
                    notes_list = request.form.getlist('notes[]')
                    water_meter_replaced_list = request.form.getlist('water_meter_replaced[]')
                    electric_meter_replaced_list = request.form.getlist('electric_meter_replaced[]')
                    
                    # 验证billing_period参数（必填）
                    if not billing_period:
                        log_operation(
                            user_id=current_user.id,
                            module='utility',
                            operation_type='meter',
                            action=f"批量保存抄表记录 [错误: 未提供账期参数]",
                            result="失败"
                        )
                        logging.error(f"批量保存抄表记录 [错误: 未提供账期参数]")
                        flash("批量保存失败：未提供账期参数（billing_period）", "danger")
                        return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
                    
                    # 验证billing_period格式（YYYY-MM）
                    try:
                        datetime.strptime(billing_period, '%Y-%m')
                    except ValueError:
                        log_operation(
                            user_id=current_user.id,
                            module='utility',
                            operation_type='meter',
                            action=f"批量保存抄表记录 [错误: 账期格式错误: {billing_period}]",
                            result="失败"
                        )
                        logging.error(f"批量保存抄表记录 [错误: 账期格式错误: {billing_period}]")
                        flash("批量保存失败：账期格式错误，请使用YYYY-MM格式", "danger")
                        return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
                    
                    # 验证批量数据长度一致
                    if not (len(room_ids) == len(water_currents) == len(electric_currents) == 
                            len(notes_list) == 
                            len(water_meter_replaced_list) == len(electric_meter_replaced_list)):
                        log_operation(
                            user_id=current_user.id,
                            module='utility',
                            operation_type='meter',
                            action=f"批量保存抄表记录 [错误: 批量数据长度不一致]",
                            result="失败"
                        )
                        logging.error(f"批量保存抄表记录 [错误: 批量数据长度不一致]")
                        flash("批量保存失败：数据格式错误，各字段长度不一致", "danger")
                        return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
                    
                    # 处理日期格式
                    reading_date = datetime.now()
                    if reading_date_str:
                        try:
                            reading_date = datetime.strptime(reading_date_str, '%Y-%m-%d %H:%M:%S')
                        except ValueError:
                            try:
                                reading_date = datetime.strptime(reading_date_str, '%Y-%m-%d %H:%M')
                            except ValueError:
                                try:
                                    reading_date = datetime.strptime(reading_date_str, '%Y-%m-%d')
                                except ValueError:
                                    log_operation(
                                        user_id=current_user.id,
                                        module='utility',
                                        operation_type='meter',
                                        action=f"批量保存抄表记录 [错误: 日期格式错误]",
                                        result="失败"
                                    )
                                    logging.error(f"批量保存抄表记录 [错误: 日期格式错误]")
                                    flash("批量保存失败：日期格式错误，请使用 yyyy-mm-dd 或 yyyy-mm-dd HH:MM 或 yyyy-mm-dd HH:MM:SS", "danger")
                                    return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
                    
                    # 准备批量保存数据
                    success_count = 0
                    error_count = 0
                    error_details = []
                    success_rooms = []
                    
                    # 使用事务处理 - Flask-SQLAlchemy会自动管理事务范围
                    try:
                        # 处理每条记录
                        for i in range(len(room_ids)):
                            try:
                                room_id = room_ids[i]
                                water_current = water_currents[i].strip()
                                electric_current = electric_currents[i].strip()
                                notes = notes_list[i].strip() if i < len(notes_list) else ''
                                water_meter_replaced = water_meter_replaced_list[i] == 'true'
                                electric_meter_replaced = electric_meter_replaced_list[i] == 'true'
                                
                                # 验证房间是否存在
                                room = Room.query.get(room_id)
                                if not room:
                                    error_count += 1
                                    error_details.append(f"房间ID {room_id} 不存在")
                                    logging.error(f"批量保存抄表记录 [错误: 房间ID {room_id} 不存在]")
                                    continue
                                
                                # 转换读数为浮点数（如果有值）
                                water_current_float = float(water_current) if water_current else None
                                electric_current_float = float(electric_current) if electric_current else None
                                
                                # 验证至少有一个读数
                                if water_current_float is None and electric_current_float is None:
                                    error_count += 1
                                    error_details.append(f"房间 {room.room_full_identifier}：未提供任何读数")
                                    logging.error(f"批量保存抄表记录 [错误: 房间 {room.room_full_identifier}：未提供任何读数]")
                                    continue
                                
                                # 调用模型的create_reading方法保存记录
                                UtilityMeterReading.create_reading(
                                    room_id=room_id,
                                    billing_period=billing_period,
                                    water_current=water_current_float,
                                    electric_current=electric_current_float,
                                    reading_date=reading_date,
                                    meter_reader_id=current_user.id,
                                    notes=notes,
                                    reading_type=1,  # 正常抄表类型
                                    water_meter_replaced=water_meter_replaced,
                                    electric_meter_replaced=electric_meter_replaced
                                )
                                
                                # 保存成功后，将临时目录的照片移动到正式账期目录
                                try:
                                    move_result = room_meter_manager.move_temp_to_billing_period(room_id, billing_period)
                                    if move_result['moved'] > 0:
                                        logging.info(f"批量保存：移动房间 {room_id} 的 {move_result['moved']} 个临时照片到账期 {billing_period}")
                                except Exception as move_err:
                                    logging.warning(f"批量保存：移动房间 {room_id} 的临时照片失败: {str(move_err)}")
                                
                                success_count += 1
                                success_rooms.append(room.room_full_identifier)
                                
                            except Exception as e:
                                error_count += 1
                                room = Room.query.get(room_ids[i]) if i < len(room_ids) else None
                                room_identifier = room.room_full_identifier if room else f"房间ID {room_ids[i]}"
                                error_details.append(f"{room_identifier}：{str(e)}")
                                
                        # 提交事务
                        db.session.commit()
                        
                        # 记录操作日志
                        log_operation(
                            user_id=current_user.id,
                            module="utility",
                            operation_type="meter",
                            action=f"批量创建抄表记录 [成功: {success_count}, 失败: {error_count}]",
                            result="成功"
                        )
                        logging.info(f"批量保存抄表记录 [成功: {success_count}, 失败: {error_count}]")
                        # 构建成功消息
                        if success_count > 0:
                            success_message = f"成功保存 {success_count} 条抄表记录"
                            if error_count > 0:
                                success_message += f"，{error_count} 条记录保存失败。" + \
                                                  "请检查错误详情并重新提交。"
                                logging.error(f"批量保存抄表记录 [错误: {error_count} 条记录保存失败]")
                            
                            # 重定向回页面，使用flash消息
                            if error_count > 0:
                                flash(f"{success_message} 失败详情：{'；'.join(error_details)}", "warning")
                            else:
                                flash(success_message, "success")
                            return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
                        else:
                            # 全部失败
                            log_operation(
                                user_id=current_user.id,
                                module='utility',
                                operation_type='meter',
                                action=f"批量创建抄表记录全部失败",
                                result="失败"
                            )
                            logging.error(f"批量保存抄表记录 [错误: 所有记录均未能保存]")
                            flash(f"批量保存失败：所有记录均未能保存。失败详情：{'；'.join(error_details)}", "danger")
                            return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
                            
                    except Exception as e:
                        db.session.rollback()
                        logging.error(f"批量创建抄表记录事务失败: {str(e)}")
                        log_operation(
                            user_id=current_user.id,
                            module='utility',
                            operation_type='meter',
                            action=f"批量创建抄表记录 [事务错误: {str(e)}]",
                            result="失败"
                        )
                        flash(f"批量保存失败：{str(e)}", "danger")
                        return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
                        
                except Exception as e:
                    logging.error(f"处理批量抄表记录提交失败: {str(e)}")
                    
                    flash(f"批量处理失败：{str(e)}", "danger")
                    return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
            else:
                # 单个保存处理
                # 从表单获取数据
                room_id = request.form.get('room_id', type=int)
                water_current = request.form.get('water_current', '').strip()
                electric_current = request.form.get('electric_current', '').strip()
                reading_date_str = request.form.get('reading_date', '')
                billing_period = request.form.get('billing_period', '').strip()
                notes = request.form.get('notes', '').strip()
                water_meter_replaced = request.form.get('water_meter_replaced') == 'true'
                electric_meter_replaced = request.form.get('electric_meter_replaced') == 'true'
                
                # 验证必要参数
                if not room_id:
                    
                    logging.error(f"保存抄表记录 [错误: 未提供房间ID]")
                    flash("保存失败：未提供房间ID", "danger")
                    return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
                
                # 验证billing_period参数（必填）
                if not billing_period:
                    
                    logging.error(f"保存抄表记录 [错误: 未提供账期参数]")
                    flash("保存失败：未提供账期参数（billing_period）", "danger")
                    return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
                
                # 验证billing_period格式（YYYY-MM）
                try:
                    datetime.strptime(billing_period, '%Y-%m')
                except ValueError:
                    
                    logging.error(f"保存抄表记录 [错误: 账期格式错误: {billing_period}]")
                    flash("保存失败：账期格式错误，请使用YYYY-MM格式", "danger")
                    return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
                
                # 验证房间是否存在
                room = Room.query.get(room_id)
                if not room:
                    
                    logging.error(f"保存抄表记录 [错误: 房间ID不存在: {room_id}]")
                    flash(f"保存失败：房间ID {room_id} 不存在", "danger")
                    return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
                
                # 处理日期格式
                reading_date = datetime.now()
                if reading_date_str:
                    try:
                        reading_date = datetime.strptime(reading_date_str, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        try:
                            reading_date = datetime.strptime(reading_date_str, '%Y-%m-%d %H:%M')
                        except ValueError:
                            try:
                                reading_date = datetime.strptime(reading_date_str, '%Y-%m-%d')
                            except ValueError:
                                
                                logging.error(f"保存抄表记录 [错误: 日期格式错误]")
                                flash("保存失败：日期格式错误，请使用 yyyy-mm-dd 或 yyyy-mm-dd HH:MM 或 yyyy-mm-dd HH:MM:SS", "danger")
                                return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
                
                # 转换读数为浮点数（如果有值）
                water_current_float = float(water_current) if water_current else None
                electric_current_float = float(electric_current) if electric_current else None
                
                # 验证至少有一个读数
                if water_current_float is None and electric_current_float is None:
                    
                    logging.error(f"保存抄表记录 [错误: 未提供任何读数]")
                    flash("保存失败：至少需要提供一项水表或电表读数", "danger")
                    return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
                
                # 使用事务处理创建记录
                try:
                    # 调用模型的create_reading方法保存记录
                    reading = UtilityMeterReading.create_reading(
                        room_id=room_id,
                        billing_period=billing_period,
                        water_current=water_current_float,
                        electric_current=electric_current_float,
                        reading_date=reading_date,
                        meter_reader_id=current_user.id,
                        notes=notes,
                        reading_type=1,  # 正常抄表类型
                        water_meter_replaced=water_meter_replaced,
                        electric_meter_replaced=electric_meter_replaced
                    )
                    
                    # 提交事务
                    db.session.commit()
                    
                    # 保存成功后，将临时目录的照片移动到正式账期目录
                    try:
                        move_result = room_meter_manager.move_temp_to_billing_period(room_id, billing_period)
                        if move_result['moved'] > 0:
                            logging.info(f"单个保存：移动房间 {room_id} 的 {move_result['moved']} 个临时照片到账期 {billing_period}")
                    except Exception as move_err:
                        logging.warning(f"单个保存：移动房间 {room_id} 的临时照片失败: {str(move_err)}")
                    
                    # 记录操作日志
                    log_operation(
                        user_id=current_user.id,
                        module="utility",
                        operation_type="meter",
                        action=f"创建抄表记录 [房间: {room.room_full_identifier}]",
                        result="成功"
                    )
                    logging.info(f"创建抄表记录 [房间: {room.room_full_identifier}]")
                    # 重定向回页面，使用flash消息
                    flash(f"成功保存房间 {room.room_full_identifier} 的抄表记录", "success")
                    return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
                    
                except Exception as e:
                    db.session.rollback()
                    logging.error(f"创建抄表记录失败: {str(e)}")
                    
                    flash(f"保存失败：{str(e)}", "danger")
                    return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
                    
        except Exception as e:
            logging.error(f"处理抄表记录提交失败: {str(e)}")
            
            flash(f"处理失败：{str(e)}", "danger")
            return redirect(url_for('utility_room_meter.utility_reading', building=building_filter, search_room=search_room, page=page, billing_period=billing_period))
    
    # GET 请求处理
    try:
        # 从Room模型获取去重后的楼栋数据
        buildings = db.session.query(Room.building).distinct().all()
        # 提取楼栋名称并排序
        building_list = [building[0] for building in buildings if building[0]]
        # 智能排序：提取数字部分进行排序
        import re
        building_list.sort(key=lambda x: [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', x)])
        
        # 获取查询参数
        search_room = request.args.get('search_room', '').strip()
        building_filter = request.args.get('building', '')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        # 构建房间查询
        room_query = Room.query
        
        # 应用筛选条件
        if search_room:
            room_query = room_query.filter(Room.room_number.like(f'%{search_room}%'))
        
        if building_filter:
            room_query = room_query.filter(Room.building == building_filter)
        
        # 执行分页查询
        pagination = room_query.order_by(Room.id, Room.building, Room.room_number).paginate(page=page, per_page=per_page, error_out=False)
        rooms = pagination.items
        
        # 为每个房间获取最新抄表记录
        room_with_latest_readings = []
        for room in rooms:
            room_data = {
                'id': room.id,
                'room_number': room.room_number,
                'building': room.building,
                'room_full_identifier': room.room_full_identifier,
                'latest_water_reading': None,
                'latest_electric_reading': None,
                'latest_water_date': None,
                'latest_electric_date': None
            }
            
            try:
                # 获取最新水表读数 - 匹配UtilityMeterReading模型的方法签名
                latest_water = UtilityMeterReading.get_latest_water_reading(room.id)
                if latest_water:
                    room_data['latest_water_reading'] = float(latest_water.water_current) if latest_water.water_current else None
                    room_data['latest_water_date'] = latest_water.reading_date.strftime('%Y-%m-%d %H:%M:%S') if latest_water.reading_date else None
                
                # 获取最新电表读数 - 匹配UtilityMeterReading模型的方法签名
                latest_electric = UtilityMeterReading.get_latest_electric_reading(room.id)
                if latest_electric:
                    room_data['latest_electric_reading'] = float(latest_electric.electric_current) if latest_electric.electric_current else None
                    room_data['latest_electric_date'] = latest_electric.reading_date.strftime('%Y-%m-%d %H:%M:%S') if latest_electric.reading_date else None
                
            except Exception as e:
                logging.error(f"获取房间最新读数失败 [房间ID: {room.id}]: {str(e)}")
                # 继续处理其他房间，不中断整个流程
            
            room_with_latest_readings.append(room_data)
        
        # 补充页面访问日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='records',
            action=f"访问抄表登记页面 [搜索房间: {search_room}, 楼栋筛选: {building_filter}, 页码: {page}]",
            result="成功"
        )
        logging.info(f"访问抄表登记页面 [搜索房间: {search_room}, 楼栋筛选: {building_filter}, 页码: {page}]")
        # 获取当前时间作为默认抄表日期时间，包含秒
        
        current_datetime = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        reading_date_time = request.args.get('reading_date_time', current_datetime)
        
        # 获取可用账期列表（从主表查询去重的billing_period）
        billing_periods = []
        current_billing_period = datetime.now().strftime('%Y-%m')
        try:
            periods = db.session.query(RoomUtilityRecord.billing_period).distinct().order_by(RoomUtilityRecord.billing_period.desc()).all()
            billing_periods = [p[0] for p in periods if p[0]]
        except Exception as e:
            logging.warning(f"获取账期列表失败: {str(e)}")
        
        # 如果URL参数中指定了billing_period，优先使用
        url_billing_period = request.args.get('billing_period', '').strip()
        if url_billing_period:
            try:
                datetime.strptime(url_billing_period, '%Y-%m')
                current_billing_period = url_billing_period
            except ValueError:
                pass  # 格式不正确则使用默认值
        
        # 将数据传递给模板
        return render_template(
            'utility_bill/utility_reading.html',
            title=f"抄表登记",
            buildings=building_list,
            rooms=room_with_latest_readings,
            pagination={
                'total': pagination.total,
                'page': page,
                'per_page': per_page,
                'pages': pagination.pages,
                'has_prev': pagination.has_prev,
                'has_next': pagination.has_next,
                'prev_num': pagination.prev_num,
                'next_num': pagination.next_num
            },
            search_room=search_room,
            building_filter=building_filter,
            reading_date_time=reading_date_time,
            billing_periods=billing_periods,
            current_billing_period=current_billing_period
        )
        
    except Exception as e:
        logging.error(f"访问抄表登记页面失败: {str(e)}")
        
        # 出现异常时返回基本页面，确保前端能正常显示

        current_datetime = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        current_billing_period = datetime.now().strftime('%Y-%m')
        
        flash("加载数据失败，请刷新页面重试", "danger")
        return render_template(
            'utility_bill/utility_reading.html',
            title=f"抄表登记",
            buildings=[],
            rooms=[],
            pagination={'total': 0, 'page': 1, 'per_page': 20, 'pages': 0},
            reading_date_time=current_datetime,
            billing_periods=[],
            current_billing_period=current_billing_period
        )

@utility_room_meter_bp.route('/utility_reading_manage', methods=['GET'])
@login_required
@require_permission('utility.view')
def utility_reading_manage():
    """抄表记录管理页面"""
    # 从Room模型获取去重后的楼栋数据
    try:
        buildings = db.session.query(Room.building).distinct().all()
        building_list = [building[0] for building in buildings if building[0]]
        import re
        building_list.sort(key=lambda x: [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', x)])
    except Exception as e:
        logging.error(f"获取楼栋列表失败: {str(e)}")
        building_list = []
    
    # 获取筛选参数
    billing_period = request.args.get('billing_period', '')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    reading_type = request.args.get('reading_type', type=int)
    building = request.args.get('building', '').strip()
    
    # 查询账期列表
    try:
        periods_raw = db.session.query(RoomUtilityRecord.billing_period).distinct().all()
        period_list = [p[0] for p in periods_raw if p[0]]
        period_list.sort(reverse=True)  # 最新的在前
    except Exception as e:
        logging.error(f"获取账期列表失败: {str(e)}")
        period_list = []
    
    # 查询抄表记录数据
    records = []
    pagination = None
    
    if billing_period:
        try:
            datetime.strptime(billing_period, '%Y-%m')
        except ValueError:
            flash('账期格式错误，请使用YYYY-MM格式', 'error')
            billing_period = ''
    
    if billing_period:
        try:
            # 查询主表记录
            main_records = RoomUtilityRecord.query.filter(
                RoomUtilityRecord.billing_period == billing_period
            ).all()
            
            if main_records:
                record_ids = [record.record_id for record in main_records]
                
                # 基础查询：连接抄表记录和房间表
                query = db.session.query(UtilityMeterReading, Room).join(
                    Room, UtilityMeterReading.room_id == Room.id
                )
                
                # 按主表record_id筛选抄表记录
                query = query.filter(UtilityMeterReading.record_id.in_(record_ids))
                
                # 抄表类型筛选
                if reading_type is not None:
                    query = query.filter(UtilityMeterReading.reading_type == reading_type)
                
                # 搜索逻辑：只匹配房间号
                if search:
                    query = query.filter(Room.room_number == search)
                
                # 楼栋筛选
                if building:
                    query = query.filter(Room.building == building)
                
                # 分页查询
                pagination = query.order_by(Room.id).paginate(
                    page=page, per_page=per_page, error_out=False
                )
                
                # 构建record_id到主表billing_period的映射
                record_period_map = {r.record_id: r.billing_period for r in main_records}
                
                for record, room in pagination.items:
                    prev_record = UtilityMeterReading.query.filter(
                        UtilityMeterReading.room_id == record.room_id,
                        UtilityMeterReading.reading_date < record.reading_date,
                        UtilityMeterReading.reading_type == 1
                    ).order_by(UtilityMeterReading.reading_date.desc()).first()
                    
                    record_dict = record.to_dict()
                    record_dict['prev_reading'] = prev_record.to_dict() if prev_record else None
                    record_dict['billing_period'] = record_period_map.get(record.record_id, billing_period)
                    record_dict['归属_month'] = record_period_map.get(record.record_id, billing_period)
                    record_dict['room_number'] = room.room_number
                    record_dict['room_building'] = room.building
                    record_dict['room_id'] = room.id
                    records.append(record_dict)
        except Exception as e:
            logging.error(f"查询抄表记录失败: {str(e)}\n{traceback.format_exc()}")
            flash(f'查询抄表记录失败: {str(e)}', 'error')
    
    # 补充页面访问日志
    log_operation(
        user_id=current_user.id,
        module='utility',
        operation_type='records',
        action=f"访问抄表记录管理页面",
        result="成功"
    )
    
    # 生成页码范围
    page_range = generate_page_range(page, pagination.pages if pagination else 1)
    
    return render_template('utility_bill/utility_reading_manage.html',
        title="抄表记录管理",
        buildings=building_list,
        billing_period=billing_period,
        periods=period_list,
        records=records,
        pagination=pagination,
        page_range=page_range,
        search=search,
        reading_type=reading_type,
        building=building,
        per_page=per_page)

# 修复：添加带ID参数的编辑页面路由
@utility_room_meter_bp.route('/edit/<int:reading_id>', methods=['GET'])
@login_required
@require_permission('utility.edit')
def utility_reading_edit(reading_id):
    """编辑抄表记录页面 - 带ID参数"""
    # 补充页面访问日志
    log_operation(
        user_id=current_user.id,
        module='utility',
        operation_type='records',
        action=f"访问编辑抄表记录页面 [记录ID: {reading_id}]",
        result="成功"
    )
    # 获取可用账期列表（从主表查询去重的billing_period）
    billing_periods = []
    try:
        periods = db.session.query(RoomUtilityRecord.billing_period).distinct().order_by(RoomUtilityRecord.billing_period.desc()).all()
        billing_periods = [p[0] for p in periods if p[0]]
    except Exception as e:
        logging.warning(f"获取账期列表失败: {str(e)}")
    return render_template('utility_bill/utility_reading_edit.html', reading_id=reading_id, title=f"编辑抄表记录", billing_periods=billing_periods)

@utility_room_meter_bp.route('/<int:reading_id>', methods=['GET'])
@login_required
@require_permission('utility.view')
def get_reading_detail(reading_id):
    """获取抄表记录详情"""
    try:
        reading = UtilityMeterReading.query.get(reading_id)
        if not reading:
            logging.error(f"获取抄表记录详情失败: 记录不存在 [记录ID: {reading_id}]")
            return jsonify({'success': False, 'message': f'抄表记录ID不存在: {reading_id}'}), 404
        return jsonify({'success': True, 'data': reading.to_dict()})
    except Exception as e:
        logging.error(f"获取抄表记录详情失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': "获取记录详情失败" if not Config.DEBUG else str(e)
        }), 500

    
@utility_room_meter_bp.route('/<int:reading_id>/delete', methods=['POST'])
@login_required
@require_permission('utility.delete')
def delete_reading(reading_id):
    """删除单个抄表记录"""
    try:
        # 查询要删除的记录
        reading = UtilityMeterReading.query.get(reading_id)
        if not reading:
            # 补充记录不存在日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"删除抄表记录 [记录ID: {reading_id}, 错误: 记录不存在]",
                result="失败"
            )
            flash(f'抄表记录ID不存在: {reading_id}', 'danger')
            return redirect(url_for('utility_room_meter.utility_reading_manage'))
        
        # 获取billing_period用于redirect
        billing_period = None
        if reading.record_id:
            bill_record = RoomUtilityRecord.query.get(reading.record_id)
            if bill_record:
                billing_period = bill_record.billing_period
        
        # 获取房间信息用于日志
        room = Room.query.get(reading.room_id)
        room_info = room.room_full_identifier if room else f"房间ID: {reading.room_id}"
        
        # 执行删除操作
        db.session.delete(reading)
        db.session.commit()
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module="utility",
            operation_type="delete",
            action=f"删除抄表记录 [ID: {reading_id}，房间: {room_info}]",
            result="成功"
        )
        
        flash(f'抄表记录 {reading_id} 已成功删除', 'success')
        if billing_period:
            return redirect(url_for('utility_room_meter.utility_reading_manage', billing_period=billing_period))
        return redirect(url_for('utility_room_meter.utility_reading_manage'))
        
    except Exception as e:
        logging.error(f"删除抄表记录失败: {str(e)}\n{traceback.format_exc()}")
        db.session.rollback()
        # 补充删除失败日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"删除抄表记录 [记录ID: {reading_id}, 错误: {str(e)}]",
            result="失败"
        )
        flash("删除抄表记录失败" if not Config.DEBUG else str(e), 'danger')
        return redirect(url_for('utility_room_meter.utility_reading_manage'))

@utility_room_meter_bp.route('/batch-delete', methods=['POST'])
@login_required
@require_permission('utility.delete')
def batch_delete_readings():
    """批量删除抄表记录"""
    try:
        ids = request.form.getlist('ids')
        
        # 验证请求数据
        if not ids:
            # 补充格式错误日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"批量删除抄表记录 [错误: 请求格式错误]",
                result="失败"
            )
            flash('请求格式错误，应包含ids', 'danger')
            return redirect(url_for('utility_room_meter.utility_reading_manage'))
            
        # 将ids转为整数列表
        try:
            ids = [int(id_str) for id_str in ids]
        except (ValueError, TypeError):
            flash('记录ID格式错误', 'danger')
            return redirect(url_for('utility_room_meter.utility_reading_manage'))
            
        if len(ids) == 0:
            # 补充空ID列表错误日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"批量删除抄表记录 [错误: 未提供任何记录ID]",
                result="失败"
            )
            flash('请至少选择一条记录进行删除', 'danger')
            return redirect(url_for('utility_room_meter.utility_reading_manage'))
            
        # 限制最大批量删除数量
        if len(ids) > 100:
            # 补充数量超限错误日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"批量删除抄表记录 [错误: 记录数量超限{len(ids)}]",
                result="失败"
            )
            flash(f'单次批量删除最多支持100条记录，当前为{len(ids)}条', 'danger')
            return redirect(url_for('utility_room_meter.utility_reading_manage'))
            
        # 查询所有要删除的记录
        readings = UtilityMeterReading.query.filter(UtilityMeterReading.id.in_(ids)).all()
        
        if not readings:
            # 补充无匹配记录错误日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"批量删除抄表记录 [错误: 未找到匹配记录]",
                result="失败"
            )
            flash('未找到任何匹配的记录', 'danger')
            return redirect(url_for('utility_room_meter.utility_reading_manage'))
            
        # 获取billing_period用于redirect（从第一条记录获取）
        billing_period = None
        if readings[0].record_id:
            bill_record = RoomUtilityRecord.query.get(readings[0].record_id)
            if bill_record:
                billing_period = bill_record.billing_period
        
        # 记录要删除的ID和相关信息用于日志
        deleted_ids = [reading.id for reading in readings]
        room_ids = set([reading.room_id for reading in readings])
        rooms = Room.query.filter(Room.id.in_(room_ids)).all()
        room_infos = [room.room_full_identifier for room in rooms]
        
        # 执行批量删除
        for reading in readings:
            db.session.delete(reading)
        
        db.session.commit()
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module="utility",
            operation_type="delete",
            action=f"批量删除抄表记录 [数量: {len(deleted_ids)}，涉及房间: {', '.join(room_infos[:5])}{'...' if len(room_infos) > 5 else ''}]",
            result="成功"
        )
        
        flash(f'成功删除 {len(deleted_ids)} 条抄表记录', 'success')
        if billing_period:
            return redirect(url_for('utility_room_meter.utility_reading_manage', billing_period=billing_period))
        return redirect(url_for('utility_room_meter.utility_reading_manage'))
        
    except Exception as e:
        logging.error(f"批量删除抄表记录失败: {str(e)}\n{traceback.format_exc()}")
        db.session.rollback()
        # 补充批量删除失败日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"批量删除抄表记录 [错误: {str(e)}]",
            result="失败"
        )
        flash("批量删除抄表记录失败" if not Config.DEBUG else str(e), 'danger')
        return redirect(url_for('utility_room_meter.utility_reading_manage'))


@utility_room_meter_bp.route('/delete-billing-period/<string:year_month>', methods=['POST'])
@login_required
@require_permission('utility.delete')
def delete_readings_by_month(year_month):
    """
    按账期（YYYY-MM）删除抄表记录
    通过billing_period关联主表record_id来查找并删除抄表记录
    """
    try:
        # 验证账期格式
        try:
            datetime.strptime(year_month, '%Y-%m')
        except ValueError:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"按账期删除抄表记录 [错误: 日期格式错误 {year_month}]",
                result="失败"
            )
            flash('日期格式错误，请使用YYYY-MM格式', 'danger')
            return redirect(url_for('utility_room_meter.utility_reading_manage'))
        
        # 通过billing_period查找主表记录，获取record_id列表
        main_records = RoomUtilityRecord.query.filter(
            RoomUtilityRecord.billing_period == year_month
        ).all()
        
        if not main_records:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"按账期删除抄表记录 [账期: {year_month}, 结果: 无主表记录]",
                result="成功"
            )
            flash(f'账期 {year_month} 内没有找到抄表记录', 'info')
            return redirect(url_for('utility_room_meter.utility_reading_manage'))
        
        # 提取主表record_id
        record_ids = [record.record_id for record in main_records]
        
        # 通过record_id关联查询抄表记录
        readings = UtilityMeterReading.query.filter(
            UtilityMeterReading.record_id.in_(record_ids)
        ).all()
        
        if not readings:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"按账期删除抄表记录 [账期: {year_month}, 结果: 无抄表记录]",
                result="成功"
            )
            flash(f'账期 {year_month} 内没有找到抄表记录', 'info')
            return redirect(url_for('utility_room_meter.utility_reading_manage'))
        
        # 收集要删除的记录ID和涉及的房间信息（用于日志）
        deleted_ids = [reading.id for reading in readings]
        room_ids = set([reading.room_id for reading in readings])
        rooms = Room.query.filter(Room.id.in_(room_ids)).all()
        room_infos = [room.room_full_identifier for room in rooms]
        
        # 执行删除操作
        try:
            for reading in readings:
                db.session.delete(reading)
            db.session.commit()
            
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"按账期删除抄表记录 [账期: {year_month}, 数量: {len(deleted_ids)}, 涉及房间: {', '.join(room_infos[:5])}{'...' if len(room_infos) > 5 else ''}]",
                result="成功"
            )
            
            flash(f'成功删除账期 {year_month} 内的 {len(deleted_ids)} 条抄表记录', 'success')
            return redirect(url_for('utility_room_meter.utility_reading_manage'))
        except Exception as e:
            db.session.rollback()
            logging.error(f"按账期删除抄表记录失败: {str(e)}\n{traceback.format_exc()}")
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"按账期删除抄表记录 [账期: {year_month}, 错误: {str(e)}]",
                result="失败"
            )
            flash("删除抄表记录失败" if not Config.DEBUG else str(e), 'danger')
            return redirect(url_for('utility_room_meter.utility_reading_manage'))
            
    except Exception as e:
        logging.error(f"处理按账期删除请求失败: {str(e)}\n{traceback.format_exc()}")
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"按账期删除抄表记录 [错误: {str(e)}]",
            result="失败"
        )
        flash("处理删除请求失败" if not Config.DEBUG else str(e), 'danger')
        return redirect(url_for('utility_room_meter.utility_reading_manage'))


# 新增：按账期查询抄表记录
@utility_room_meter_bp.route('/by-period', methods=['GET'])
@login_required
@require_permission('utility.view')
def get_readings_by_period():
    """按账期查询抄表记录，通过billing_period查询utility_room_bill_records表获取record_id，再关联查询抄表记录"""
    try:
        # 接收参数
        billing_period = request.args.get('billing_period')
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        room_id = request.args.get('room_id', type=int)
        search = request.args.get('search', '').strip()
        reading_type = request.args.get('reading_type', type=int)
        building = request.args.get('building', '').strip()
        
        # 参数验证
        if not billing_period:
            # 补充参数不足错误日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='utility_api',
                action=f"按账期查询抄表记录 [错误: 未提供billing_period参数]",
                result="失败"
            )
            return jsonify({
                'success': False, 
                'message': '请提供billing_period参数（格式YYYY-MM）'
            }), 400
        
        # 验证billing_period格式
        try:
            datetime.strptime(billing_period, '%Y-%m')
        except ValueError:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='utility_api',
                action=f"按账期查询抄表记录 [错误: billing_period格式错误: {billing_period}]",
                result="失败"
            )
            return jsonify({
                'success': False, 
                'message': 'billing_period格式错误，请使用YYYY-MM格式'
            }), 400
        
        # 从主表查询对应账期的记录（已在文件顶部导入RoomUtilityRecord）
        
        # 查询主表记录
        main_records = RoomUtilityRecord.query.filter(
            RoomUtilityRecord.billing_period == billing_period
        ).all()
        
        if not main_records:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='utility_api',
                action=f"按账期查询抄表记录 [警告: 未找到账期为{billing_period}的主表记录]",
                result="成功"
            )
            return jsonify({
                'success': True,
                'data': {
                    'records': [],
                    'pagination': {
                        'total': 0,
                        'page': page,
                        'per_page': per_page,
                        'pages': 0
                    },
                    'filter_params': {
                        'billing_period': billing_period,
                        'room_id': room_id,
                        'search': search,
                        'reading_type': reading_type
                    }
                }
            })
        
        # 提取主表record_id
        record_ids = [record.record_id for record in main_records]
        
        # 基础查询：连接抄表记录和房间表
        query = db.session.query(UtilityMeterReading, Room).join(
            Room, UtilityMeterReading.room_id == Room.id
        )
        
        # 按主表record_id筛选抄表记录
        query = query.filter(UtilityMeterReading.record_id.in_(record_ids))

        # 房间筛选（按ID精确筛选，单独逻辑）
        if room_id:
            query = query.filter(UtilityMeterReading.room_id == room_id)

        # 抄表类型筛选
        if reading_type is not None:
            query = query.filter(UtilityMeterReading.reading_type == reading_type)
        
        # 搜索逻辑修复：只匹配房间号，不匹配ID
        if search:
            # 无论搜索词是否为数字，都只作为房间号精确匹配
            query = query.filter(Room.room_number == search)
        
        # 添加楼栋筛选
        if building:
            query = query.filter(Room.building == building)
            
        # 修改为按room_id顺序排序
        pagination = query.order_by(Room.id).paginate(
            page=page, per_page=per_page, error_out=False
        )
        current_records = pagination.items
        
        records_with_归属 = []
        # 构建record_id到主表billing_period的映射
        record_period_map = {record.record_id: record.billing_period for record in main_records}
        
        for record, room in current_records:
            prev_record = UtilityMeterReading.query.filter(
                UtilityMeterReading.room_id == record.room_id,
                UtilityMeterReading.reading_date < record.reading_date,
                UtilityMeterReading.reading_type == 1
            ).order_by(UtilityMeterReading.reading_date.desc()).first()
            
            # 直接使用主表的billing_period
            归属_month = record_period_map.get(record.record_id, billing_period)
            
            record_dict = record.to_dict()
            record_dict['prev_reading'] = prev_record.to_dict() if prev_record else None
            record_dict['billing_period'] = 归属_month
            record_dict['归属_month'] = 归属_month
            record_dict['room_number'] = room.room_number
            record_dict['room_building'] = room.building
            record_dict['room_id'] = room.id
            records_with_归属.append(record_dict)
        # 补充查询成功日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='utility_api',
            action=f"按账期查询抄表记录 [billing_period: {billing_period}, 房间ID: {room_id}, 搜索关键词: {search}, 楼栋: {building}, 页码: {page}]",
            result="成功"
        )
        return jsonify({
            'success': True,
            'data': {
                'records': records_with_归属,
                'pagination': {
                    'total': pagination.total,
                    'page': page,
                    'per_page': per_page,
                    'pages': pagination.pages
                },
                'filter_params': {
                        'billing_period': billing_period,
                        'room_id': room_id,
                        'search': search,
                        'building': building
                    }
            }
        })
        
    except Exception as e:
        logging.error(f"查询失败: {str(e)}\n{traceback.format_exc()}")
        # 补充查询失败日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='utility_api',
            action=f"按账期查询抄表记录 [billing_period: {billing_period}, 楼栋: {building}, 错误: {str(e)}]",
            result="失败"
        )
        return jsonify({
            'success': False,
            'message': f"查询失败{str(e)}"   
        }), 500

@utility_room_meter_bp.route('/edit/<int:reading_id>/save', methods=['POST'])
@login_required
@require_permission('utility.edit')
def save_edited_reading(reading_id):
    """
    保存编辑后的抄表记录接口
    - POST: 更新抄表记录数据
    """
    try:
        # 查询抄表记录是否存在
        reading = UtilityMeterReading.query.get(reading_id)
        if not reading:
            # 补充记录不存在日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='meter',
                action=f"编辑抄表记录 [记录ID: {reading_id}, 错误: 记录不存在]",
                result="失败"
            )
            flash(f'抄表记录ID不存在: {reading_id}', 'danger')
            return redirect(url_for('utility_room_meter.utility_reading_edit', reading_id=reading_id))
        
        # 从request.form获取数据
        data = {}
        # 获取表单字段
        reading_date = request.form.get('reading_date', '')
        billing_period = request.form.get('billing_period', '')
        water_current = request.form.get('water_current', '')
        electric_current = request.form.get('electric_current', '')
        water_meter_replaced = request.form.get('water_meter_replaced', 'false')
        electric_meter_replaced = request.form.get('electric_meter_replaced', 'false')
        notes = request.form.get('notes', '')
        
        if reading_date:
            data['reading_date'] = reading_date
        if water_current:
            try:
                data['water_current'] = float(water_current)
            except ValueError:
                pass
        if electric_current:
            try:
                data['electric_current'] = float(electric_current)
            except ValueError:
                pass
        data['water_meter_replaced'] = water_meter_replaced in ('true', 'True', '1')
        data['electric_meter_replaced'] = electric_meter_replaced in ('true', 'True', '1')
        if notes:
            data['notes'] = notes
        
        # 处理账期变更：如果提供了billing_period，查找或创建对应的RoomUtilityRecord并更新record_id
        if billing_period:
            try:
                # 查找该房间对应账期的主表记录
                bill_record = RoomUtilityRecord.get_by_room_and_period(reading.room_id, billing_period)
                if bill_record:
                    data['record_id'] = bill_record.record_id
                else:
                    # 如果该账期主表记录不存在，自动创建
                    bill_record = RoomUtilityRecord.create_from_meter_reading(reading.room_id, billing_period)
                    data['record_id'] = bill_record.record_id
                    logging.info(f"编辑抄表记录时自动创建账期主表记录: 房间{reading.room_id}, 账期{billing_period}")
            except Exception as e:
                logging.error(f"处理账期变更失败: {str(e)}")
                flash(f'账期变更失败: {str(e)}', 'danger')
                return redirect(url_for('utility_room_meter.utility_reading_edit', reading_id=reading_id))
        
        # 验证必要字段
        if 'water_current' not in data and 'electric_current' not in data:
            # 补充缺少读数错误日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='meter',
                action=f"编辑抄表记录 [记录ID: {reading_id}, 错误: 未提供水表或电表读数]",
                result="失败"
            )
            flash('至少需要提供一项水表或电表读数', 'danger')
            return redirect(url_for('utility_room_meter.utility_reading_edit', reading_id=reading_id))
        
        # 处理日期格式
        if 'reading_date' in data and data['reading_date']:
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d']:
                try:
                    data['reading_date'] = datetime.strptime(data['reading_date'], fmt)
                    break
                except ValueError:
                    continue
            else:
                # 补充日期格式错误日志
                log_operation(
                    user_id=current_user.id,
                    module='utility',
                    operation_type='meter',
                    action=f"编辑抄表记录 [记录ID: {reading_id}, 错误: 日期格式错误]",
                    result="失败"
                )
                flash('日期格式错误，请使用 yyyy-mm-dd 或 yyyy-mm-dd HH:MM 或 yyyy-mm-dd HH:MM:SS', 'danger')
                return redirect(url_for('utility_room_meter.utility_reading_edit', reading_id=reading_id))
        
        # 调用模型的update方法更新记录
        updated_reading = reading.update(** data)
        
        # 提交事务
        db.session.commit()
        
        # 获取房间信息用于日志
        room = Room.query.get(reading.room_id)
        room_info = room.room_full_identifier if room else f"房间ID: {reading.room_id}"
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module="utility",
            operation_type="meter",
            action=f"更新抄表记录 [ID: {reading_id}，房间: {room_info}]",
            result="成功"
        )
        
        flash('保存成功', 'success')
        return redirect(url_for('utility_room_meter.utility_reading_edit', reading_id=reading_id))
        
    except ValueError as e:
        # 补充值错误日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='meter',
            action=f"编辑抄表记录 [记录ID: {reading_id}, 错误: {str(e)}]",
            result="失败"
        )
        flash(str(e), 'danger')
        return redirect(url_for('utility_room_meter.utility_reading_edit', reading_id=reading_id))
    except Exception as e:
        logging.error(f"处理抄表记录编辑失败: {str(e)}\n{traceback.format_exc()}")
        db.session.rollback()
        # 补充编辑失败日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='meter',
            action=f"编辑抄表记录 [记录ID: {reading_id}, 错误: {str(e)}]",
            result="失败"
        )
        flash("编辑抄表记录失败" if not Config.DEBUG else str(e), 'danger')
        return redirect(url_for('utility_room_meter.utility_reading_edit', reading_id=reading_id))




@utility_room_meter_bp.route('/upload_media', methods=['POST'])
@login_required
@require_permission('utility.reading')
def upload_meter_media():
    """上传抄表照片或视频"""
    try:
        # 获取请求参数
        billing_period = request.form.get('billing_period')
        room_id = request.form.get('room_id')
        
        # 验证参数
        if not billing_period or not room_id:
            logging.warning(f"用户 {current_user.id} 尝试上传抄表媒体文件，但缺少必要参数")
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        if 'file' not in request.files:
            logging.warning(f"用户 {current_user.id} 尝试上传抄表媒体文件，但没有文件被上传")
            return jsonify({'success': False, 'message': '没有文件被上传'})
        
        file = request.files['file']
        if file.filename == '':
            logging.warning(f"用户 {current_user.id} 尝试上传抄表媒体文件，但没有选择文件")
            return jsonify({'success': False, 'message': '没有选择文件'})
        
        # 上传文件
        filename = room_meter_manager.upload_file(file, billing_period, room_id)
        if not filename:
            logging.warning(f"用户 {current_user.id} 尝试上传抄表媒体文件，但文件格式不支持")
            return jsonify({'success': False, 'message': '不支持的文件格式'})
        
        # 生成文件URL
        file_url = room_meter_manager.get_media_url(filename, billing_period, room_id)
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='meter',
            action=f"上传抄表媒体文件: {filename} 到 {billing_period}/room_{room_id}",
            result="成功"
        )
        
        return jsonify({
            'success': True,
            'message': '上传成功',
            'filename': filename,
            'file_url': file_url
        })
        
    except Exception as e:
        logging.error(f"上传抄表媒体文件失败: {str(e)}")
        traceback.print_exc()
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='meter',
            action=f"上传抄表媒体文件失败",
            result="失败",
            error=str(e)
        )
        
        return jsonify({'success': False, 'message': f'上传失败: {str(e)}'})

@utility_room_meter_bp.route('/media/<billing_period>/<room_id>/<filename>')
@login_required
@require_permission('utility.view')
def serve_meter_media(billing_period, room_id, filename):
    """提供抄表媒体文件的访问"""
    try:
        # 获取文件路径
        file_path = room_meter_manager.get_file_path(filename, billing_period, room_id)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            logging.warning(f"尝试访问不存在的抄表媒体文件: {file_path}")
            return jsonify({'success': False, 'message': '文件不存在'}), 404
        
        # 获取文件的MIME类型
        mimetype = None
        if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
            if filename.lower().endswith('.png'):
                mimetype = 'image/png'
            elif filename.lower().endswith(('.jpg', '.jpeg')):
                mimetype = 'image/jpeg'
            elif filename.lower().endswith('.gif'):
                mimetype = 'image/gif'
            elif filename.lower().endswith('.bmp'):
                mimetype = 'image/bmp'
        elif filename.lower().endswith(('.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv')):
            if filename.lower().endswith('.mp4'):
                mimetype = 'video/mp4'
            elif filename.lower().endswith('.avi'):
                mimetype = 'video/x-msvideo'
            elif filename.lower().endswith('.mov'):
                mimetype = 'video/quicktime'
            elif filename.lower().endswith('.wmv'):
                mimetype = 'video/x-ms-wmv'
            elif filename.lower().endswith('.flv'):
                mimetype = 'video/x-flv'
            elif filename.lower().endswith('.mkv'):
                mimetype = 'video/x-matroska'
        
        # 使用send_file提供文件，并确保设置了正确的MIME类型
        # 不设置as_attachment，这样浏览器会尝试直接显示文件而不是下载
        return send_file(file_path, mimetype=mimetype, conditional=True)
        
    except Exception as e:
        logging.error(f"提供抄表媒体文件访问失败: {str(e)}")
        return jsonify({'success': False, 'message': f'访问失败: {str(e)}'}), 500

@utility_room_meter_bp.route('/delete_media', methods=['POST'])
@login_required
@require_permission('utility.edit')
def delete_meter_media():
    """删除抄表媒体文件"""
    try:
        # 获取请求参数
        data = request.json
        billing_period = data.get('billing_period')
        room_id = data.get('room_id')
        filename = data.get('filename')
        
        # 验证参数
        if not billing_period or not room_id or not filename:
            logging.warning(f"用户 {current_user.id} 尝试删除抄表媒体文件，但缺少必要参数")
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        # 删除文件
        success = room_meter_manager.delete_file(filename, billing_period, room_id)
        
        if success:
            # 记录操作日志
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"删除抄表媒体文件: {filename} 从 {billing_period}/room_{room_id}",
                result="成功"
            )
            
            return jsonify({'success': True, 'message': '文件删除成功'})
        else:
            logging.warning(f"用户 {current_user.id} 尝试删除抄表媒体文件，但文件删除失败或文件不存在")
            return jsonify({'success': False, 'message': '文件删除失败或文件不存在'})
            
    except Exception as e:
        logging.error(f"删除抄表媒体文件失败: {str(e)}")
        traceback.print_exc()
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"删除抄表媒体文件失败",
            result="失败",
            error=str(e)
        )
        
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})

@utility_room_meter_bp.route('/get_media_files', methods=['GET'])
@login_required
@require_permission('utility.view')
def get_meter_media_files():
    """获取指定账期和room_id的所有媒体文件"""
    try:
        # 获取请求参数
        billing_period = request.args.get('billing_period')
        room_id = request.args.get('room_id')
        
        # 验证参数
        if not billing_period or not room_id:
            logging.warning(f"用户 {current_user.id} 尝试获取抄表媒体文件，但缺少必要参数")
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        # 获取媒体文件列表
        media_files = room_meter_manager.get_media_files(billing_period, room_id)
        
        # 转换为前端可用的格式
        result_files = []
        for file in media_files:
            file_url = room_meter_manager.get_media_url(file['filename'], billing_period, room_id)
            result_files.append({
                'filename': file['filename'],
                'type': file['type'],
                'url': file_url,
                'upload_time': file.get('upload_time')
            })
        
        # 确保upload_time是JSON可序列化的
        for file in result_files:
            if file['upload_time'] and isinstance(file['upload_time'], datetime):
                file['upload_time'] = file['upload_time'].isoformat()
        
        return jsonify({
            'success': True,
            'files': result_files
        })
        
    except Exception as e:
        logging.error(f"获取抄表媒体文件列表失败: {str(e)}")
        traceback.print_exc()
        
        return jsonify({'success': False, 'message': f'获取失败: {str(e)}'})


# ========== 临时上传相关路由（抄表登记页面使用，账期尚未确定时） ==========

@utility_room_meter_bp.route('/upload_temp_media', methods=['POST'])
@login_required
@require_permission('utility.reading')
def upload_temp_media():
    """上传抄表照片到临时目录（抄表登记页面，账期尚未确定）"""
    try:
        room_id = request.form.get('room_id')
        
        if not room_id:
            return jsonify({'success': False, 'message': '缺少房间ID参数'})
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有文件被上传'})
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '没有选择文件'})
        
        filename = room_meter_manager.upload_to_temp(file, room_id)
        if not filename:
            return jsonify({'success': False, 'message': '不支持的文件格式'})
        
        file_url = room_meter_manager.get_temp_media_url(filename, room_id)
        
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='meter',
            action=f"上传临时抄表媒体文件: {filename} 到 room_{room_id}",
            result="成功"
        )
        
        return jsonify({
            'success': True,
            'message': '上传成功',
            'filename': filename,
            'file_url': file_url
        })
        
    except Exception as e:
        logging.error(f"上传临时抄表媒体文件失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'上传失败: {str(e)}'})


@utility_room_meter_bp.route('/temp_media/<room_id>/<filename>')
@login_required
@require_permission('utility.view')
def serve_temp_media(room_id, filename):
    """提供临时目录中媒体文件的访问"""
    try:
        file_path = room_meter_manager.get_temp_file_path(filename, room_id)
        
        if not os.path.exists(file_path):
            return jsonify({'success': False, 'message': '文件不存在'}), 404
        
        mimetype = None
        if filename.lower().endswith('.png'):
            mimetype = 'image/png'
        elif filename.lower().endswith(('.jpg', '.jpeg')):
            mimetype = 'image/jpeg'
        elif filename.lower().endswith('.gif'):
            mimetype = 'image/gif'
        elif filename.lower().endswith('.bmp'):
            mimetype = 'image/bmp'
        elif filename.lower().endswith('.mp4'):
            mimetype = 'video/mp4'
        elif filename.lower().endswith('.avi'):
            mimetype = 'video/x-msvideo'
        elif filename.lower().endswith('.mov'):
            mimetype = 'video/quicktime'
        
        return send_file(file_path, mimetype=mimetype, conditional=True)
        
    except Exception as e:
        logging.error(f"提供临时媒体文件访问失败: {str(e)}")
        return jsonify({'success': False, 'message': f'访问失败: {str(e)}'}), 500


@utility_room_meter_bp.route('/get_temp_media_files', methods=['GET'])
@login_required
@require_permission('utility.view')
def get_temp_media_files():
    """获取指定房间临时目录中的所有媒体文件"""
    try:
        room_id = request.args.get('room_id')
        
        if not room_id:
            return jsonify({'success': False, 'message': '缺少房间ID参数'})
        
        media_files = room_meter_manager.get_temp_files(room_id)
        
        result_files = []
        for file in media_files:
            file_url = room_meter_manager.get_temp_media_url(file['filename'], room_id)
            result_files.append({
                'filename': file['filename'],
                'type': file['type'],
                'url': file_url,
                'upload_time': file.get('upload_time')
            })
        
        for file in result_files:
            if file['upload_time'] and isinstance(file['upload_time'], datetime):
                file['upload_time'] = file['upload_time'].isoformat()
        
        return jsonify({
            'success': True,
            'files': result_files
        })
        
    except Exception as e:
        logging.error(f"获取临时媒体文件列表失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'获取失败: {str(e)}'})


@utility_room_meter_bp.route('/delete_temp_media', methods=['POST'])
@login_required
@require_permission('utility.edit')
def delete_temp_media():
    """删除临时目录中的媒体文件"""
    try:
        data = request.json
        room_id = data.get('room_id')
        filename = data.get('filename')
        
        if not room_id or not filename:
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        success = room_meter_manager.delete_temp_file(filename, room_id)
        
        if success:
            log_operation(
                user_id=current_user.id,
                module='utility',
                operation_type='delete',
                action=f"删除临时抄表媒体文件: {filename} 从 room_{room_id}",
                result="成功"
            )
            return jsonify({'success': True, 'message': '文件删除成功'})
        else:
            return jsonify({'success': False, 'message': '文件删除失败或文件不存在'})
            
    except Exception as e:
        logging.error(f"删除临时媒体文件失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})


@utility_room_meter_bp.route('/move_temp_to_billing', methods=['POST'])
@login_required
@require_permission('utility.reading')
def move_temp_to_billing():
    """将临时目录中的文件移动到正式账期目录（保存抄表记录时调用）"""
    try:
        data = request.json
        room_id = data.get('room_id')
        billing_period = data.get('billing_period')
        
        if not room_id or not billing_period:
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        result = room_meter_manager.move_temp_to_billing_period(room_id, billing_period)
        
        if result['errors']:
            logging.warning(f"移动临时文件部分失败: {result['errors']}")
        
        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='meter',
            action=f"移动临时抄表照片到账期 {billing_period}/room_{room_id} [成功: {result['moved']}, 失败: {len(result['errors'])}]",
            result="成功" if not result['errors'] else "部分成功"
        )
        
        return jsonify({
            'success': True,
            'moved': result['moved'],
            'errors': result['errors'],
            'message': f"成功移动 {result['moved']} 个文件" + (f"，{len(result['errors'])} 个失败" if result['errors'] else "")
        })
        
    except Exception as e:
        logging.error(f"移动临时文件到账期目录失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'移动失败: {str(e)}'})


@utility_room_meter_bp.route('/clear_room_temp_media', methods=['POST'])
@login_required
@require_permission('utility.reading')
def clear_room_temp_media():
    """清理指定房间临时目录中的所有媒体文件"""
    try:
        data = request.json
        room_id = data.get('room_id')

        if not room_id:
            return jsonify({'success': False, 'message': '缺少房间ID参数'})

        result = room_meter_manager.clear_room_temp_files(room_id)

        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"清理房间 {room_id} 所有临时抄表照片 [删除: {result['deleted']}, 失败: {len(result['errors'])}]",
            result="成功" if not result['errors'] else "部分成功"
        )

        return jsonify({
            'success': True,
            'deleted': result['deleted'],
            'errors': result['errors'],
            'message': f"成功清理 {result['deleted']} 个文件" + (f"，{len(result['errors'])} 个失败" if result['errors'] else "")
        })

    except Exception as e:
        logging.error(f"清理房间临时媒体文件失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'清理失败: {str(e)}'})


@utility_room_meter_bp.route('/clear_all_temp_media', methods=['POST'])
@login_required
@require_permission('utility.reading')
def clear_all_temp_media():
    """清理所有房间临时目录中的媒体文件"""
    try:
        result = room_meter_manager.clear_all_temp_files()

        log_operation(
            user_id=current_user.id,
            module='utility',
            operation_type='delete',
            action=f"清理所有临时抄表照片 [删除: {result['deleted']}, 房间: {result['rooms_cleared']}, 失败: {len(result['errors'])}]",
            result="成功" if not result['errors'] else "部分成功"
        )

        return jsonify({
            'success': True,
            'deleted': result['deleted'],
            'rooms_cleared': result['rooms_cleared'],
            'errors': result['errors'],
            'message': f"成功清理 {result['rooms_cleared']} 个房间共 {result['deleted']} 个文件" + (f"，{len(result['errors'])} 个失败" if result['errors'] else "")
        })

    except Exception as e:
        logging.error(f"清理所有临时媒体文件失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'清理失败: {str(e)}'})
