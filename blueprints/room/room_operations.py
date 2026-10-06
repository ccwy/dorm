from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from utils.db import db
from models.room.room import Room, RoomStatus
from models.dorm.dorm import Dorm
from config import Config
from utils.log import log_operation
import logging
from .room import room_bp  # 导入room蓝图
import traceback
from models.system_config.system_config import SystemConfig  # 新增：导入系统配置模型
from utils.media.room_photo import RoomPhotoManager
from datetime import datetime

from utils.auth import require_permission
from models.room.room_facility import RoomFacility  # 新增：导入房间设施模型
from utils.custom_fields import get_custom_field_definitions, parse_custom_fields_data, validate_custom_fields, serialize_custom_fields, deserialize_custom_fields

# 获取所有有效的楼栋列表（供内部使用）
def get_buildings_from_config():
    """从系统配置和数据库获取所有有效的楼栋列表"""
    try:
        # 1. 从系统配置获取楼栋列表
        config_buildings = SystemConfig.get_config_value('ROOM_building', ["1号楼", "2号楼", "3号楼", "4号楼", "5号楼"])
        
        # 确保系统配置返回格式为列表
        if not isinstance(config_buildings, list):
            config_buildings = [config_buildings] if config_buildings else []

        # 2. 从数据库获取已存在的楼栋列表
        from models.room.room import Room
        db_buildings = db.session.query(Room.building).distinct().all()
        db_buildings = [building[0] for building in db_buildings]  # 提取元组中的值

        # 3. 合并两个列表并去重（保持系统配置的顺序，然后添加数据库中独有的楼栋）
        merged_buildings = config_buildings.copy()
        for building in db_buildings:
            if building not in merged_buildings:
                merged_buildings.append(building)

        return merged_buildings
    except Exception as e:
        logging.error(f"获取楼栋列表失败: {str(e)}")
        # 出错时返回默认列表
        return ["1号楼", "2号楼", "3号楼", "4号楼", "5号楼"]

# 添加房间
@room_bp.route('/add', methods=['GET', 'POST'])
@login_required
@require_permission('room.create')
def add():
    
    # 从系统配置获取房间类型
    room_types = Room.get_valid_room_types()
    # 获取默认房间类型（取第一个或自定义默认值）
    default_room_type = room_types[0] if room_types else ''
    # 从系统配置获取房间级别
    room_levels = Room.get_valid_room_levels()
    # 从系统配置获取楼栋列表
    buildings = get_buildings_from_config()
    # 获取所有有效设施（用于前端展示）
    valid_facilities = RoomFacility.get_valid_facilities_for_display()
    # 获取房间自定义字段定义
    custom_field_defs = get_custom_field_definitions('room.custom_field')

    if request.method == 'POST':
        try:
             # 处理设施数据（名称+数量）
            facility_names = request.form.getlist('facility_name[]')
            # 记录前端提交的完整表单数据
            facilities = []
            for name in facility_names:
                # 直接获取对应设施名称的数量
                quantity = request.form.get(f'facility_quantity[{name}]')
                logging.info(f"设施 {name} 的数量: {quantity}")
                if quantity:
                    try:
                        qty = int(quantity)
                        if qty > 0:  # 只保留数量为正的设施
                            facilities.append({'name': name, 'quantity': qty})
                    except ValueError:
                        logging.error(f'无效的设施数量: {quantity}')
                        continue  # 跳过数量无效的设施
            logging.info(f"处理后的设施数据: {facilities}")

            # 收集表单数据（全部来自实际表单提交）
            room_data = {
                'building': request.form.get('building', '').strip(),
                'room_number': request.form.get('room_number', '').strip(),
                'address': request.form.get('address', '').strip(),
                'room_type': request.form.get('room_type', default_room_type),
                'room_level': request.form.get('room_level'),
                'gender_restriction': request.form.get('gender_restriction', '无限制'),
                'remark': request.form.get('remark', '').strip(),
                'facilities': facilities  # 传递包含数量的设施对象数组
            }
            # 安全转换数值字段，捕获异常
            try:
                room_data['capacity'] = int(request.form.get('capacity', 4))
            except (ValueError, TypeError):
                room_data['capacity'] = 4
                flash('容纳人数格式无效，已使用默认值4', 'warning')
            try:
                room_data['status'] = request.form.get('status', RoomStatus.AVAILABLE.value)
            except (ValueError, TypeError):
                room_data['status'] = RoomStatus.AVAILABLE.value
            try:
                room_data['external_rent'] = float(request.form.get('external_rent', 0) or 0)
            except (ValueError, TypeError):
                room_data['external_rent'] = 0.0
                flash('外部租金格式无效，已使用默认值0', 'warning')
            try:
                room_data['cost_rent'] = float(request.form.get('cost_rent', 0) or 0)
            except (ValueError, TypeError):
                room_data['cost_rent'] = 0.0
                flash('成本租金格式无效，已使用默认值0', 'warning')
            try:
                room_data['electric_meter_max'] = float(request.form.get('electric_meter_max', 0) or 9999.99)
            except (ValueError, TypeError):
                room_data['electric_meter_max'] = 9999.99
                flash('电表最大量程格式无效，已使用默认值', 'warning')
            try:
                room_data['water_meter_max'] = float(request.form.get('water_meter_max', 0) or 9999.99)
            except (ValueError, TypeError):
                room_data['water_meter_max'] = 9999.99
                flash('水表最大量程格式无效，已使用默认值', 'warning')
            
            # 处理创建时间
            created_at_str = request.form.get('created_at')
            if created_at_str:
                try:
                    # 转换为datetime对象

                    created_at = datetime.strptime(created_at_str, '%Y-%m-%dT%H:%M')
                    room_data['created_at'] = created_at
                except ValueError:
                    logging.error(f'无效的创建时间格式: {created_at_str}')
            
            # 处理自定义字段
            custom_data = parse_custom_fields_data(request.form, custom_field_defs)
            custom_errors = validate_custom_fields(custom_data, custom_field_defs)
            if custom_errors:
                for err in custom_errors:
                    flash(err, 'danger')
                return render_template('room_manage/room_add.html', 
                    title="添加房间",
                    room_types=room_types,
                    room_levels=room_levels,
                    gender_restrictions=Room.get_valid_gender_restrictions(),
                    valid_facilities=valid_facilities,
                    buildings=buildings,
                    custom_field_defs=custom_field_defs,
                    temp_key=request.form.get('temp_key', ''),
                    current_time=datetime.now().strftime('%Y-%m-%dT%H:%M'))
            room_data['custom_fields'] = serialize_custom_fields(custom_data)
            
            # 调用模型的create方法（实际创建房间）
            logging.info(f"尝试添加房间数据: {room_data}")
            new_room, error = Room.create(room_data)
            
            if error:
                flash(error, 'danger')
                return render_template('room_manage/room_add.html', 
                    title="添加房间",
                    room_types=room_types,
                    room_levels=room_levels,
                    gender_restrictions=Room.get_valid_gender_restrictions(),
                    valid_facilities=valid_facilities,
                    buildings=buildings,
                    custom_field_defs=custom_field_defs,
                    temp_key=request.form.get('temp_key', ''),
                    current_time=datetime.now().strftime('%Y-%m-%dT%H:%M'))

            # 房间创建成功后，添加设施
            RoomFacility.bulk_update_facilities(
                room_id=new_room.id, 
                facilities=facilities,
                remark="添加房间时自动添加"
            )
            
            # 将临时上传的照片/视频移动到新创建房间的正式目录
            temp_key = request.form.get('temp_key', '')
            if temp_key:
                # 安全处理temp_key，防止路径遍历
                original_temp_key = temp_key
                temp_key = secure_filename(temp_key)
                if temp_key:
                    try:
                        logging.info(f"开始移动临时文件: original_key={original_temp_key}, secure_key={temp_key}, room_id={new_room.id}")
                        move_result = RoomPhotoManager.move_temp_to_permanent(temp_key, new_room.id)
                        logging.info(f"临时文件移动结果: {move_result}")
                        if move_result.get('errors'):
                            logging.warning(f"部分文件移动失败: {move_result['errors']}")
                            flash(f'部分照片/视频保存失败（{len(move_result["errors"])}个），房间已创建成功', 'warning')
                            # 清理残留临时文件
                            clear_result = RoomPhotoManager.clear_temp_files(temp_key)
                            logging.info(f"残留文件清理结果: {clear_result}")
                        if move_result.get('moved', 0) > 0:
                            logging.info(f"房间 {new_room.id} 创建成功，从临时目录移动了 {move_result['moved']} 个媒体文件")
                    except Exception as e:
                        logging.error(f"移动临时文件异常: {str(e)}, temp_key={temp_key}, room_id={new_room.id}")
                        try:
                            RoomPhotoManager.clear_temp_files(temp_key)
                        except Exception as clear_err:
                            logging.warning(f"清理临时文件失败: {str(clear_err)}, temp_key={temp_key}")
                else:
                    logging.warning(f"temp_key经secure_filename处理后为空: original={original_temp_key}")
                    flash('临时文件标识无效，照片/视频未保存', 'warning')
            
            # 记录真实操作日志
            log_operation(
                user_id=current_user.id,
                module='room',
                operation_type='room_add',
                action=f"添加房间 {new_room.building}{new_room.room_number}（含{new_room.capacity}个床位）",
                result="成功"
            )

            # 根据action参数决定重定向目标
            if request.form.get('action') == 'continue':
                flash(f'房间 {new_room.building}{new_room.room_number} 及床位添加成功，继续添加', 'success')
                logging.info(f"添加房间成功，房间ID: {new_room.id}，继续添加")
                return redirect(url_for('room.add'))
            else:
                flash(f'房间 {new_room.building}{new_room.room_number} 及床位添加成功', 'success')
                logging.info(f"添加房间成功，房间ID: {new_room.id}")
                return redirect(url_for('room.manage'))
            
        except Exception as e:
            log_operation(
                user_id=current_user.id,
                module='room',
                operation_type='room_add',
                action=f"尝试添加房间失败: {str(e)}",
                result="失败"
            )
            flash('添加房间失败，请重试', 'danger')
            logging.error(f"添加房间失败: {str(e)}\n{traceback.format_exc()}")
            return render_template('room_manage/room_add.html', 
                    title="添加房间",
                    room_types=room_types,
                    room_levels=room_levels,
                    gender_restrictions=Room.get_valid_gender_restrictions(),
                    valid_facilities=valid_facilities,  # 传递有效设施列表
                    buildings=buildings,  # 传递楼栋列表到前端
                    custom_field_defs=custom_field_defs,
                    temp_key=request.form.get('temp_key', ''),
                    current_time=datetime.now().strftime('%Y-%m-%dT%H:%M')
            )
    # 记录访问日志
    log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='records',
            action="访问添加房间页面",
            result="成功"
    )
    # GET请求：显示添加表单（设施列表从实际方法获取）
    # 获取当前时间并格式化为datetime-local输入框所需的格式
    current_time = datetime.now().strftime('%Y-%m-%dT%H:%M')
    
    return render_template(
        'room_manage/room_add.html',
        title="添加房间",
        room_types=room_types,
        room_levels=room_levels,
        gender_restrictions=Room.get_valid_gender_restrictions(),
        valid_facilities=valid_facilities,  # 传递有效设施列表
        buildings=buildings,  # 传递楼栋列表到前端
        current_time=current_time,  # 传递当前时间作为默认值
        custom_field_defs=custom_field_defs,
        temp_key=''  # GET请求时无临时文件
    )
    
@room_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@require_permission('room.edit')
def edit(id):
    room = Room.query.get_or_404(id)
    # 从系统配置获取楼栋列表（统一来源）
    buildings = get_buildings_from_config()
    
    # 从系统配置获取房间类型
    room_types = Room.get_valid_room_types()
    default_room_type = room_types[0] if room_types else ''
    # 从系统配置获取房间级别
    room_levels = Room.get_valid_room_levels()
    # 获取所有有效设施和当前房间的设施信息
    valid_facilities = RoomFacility.get_valid_facilities_for_display()
    # 直接查询RoomFacility表获取当前房间的设施列表
    current_facilities = RoomFacility.query.filter_by(room_id=room.id).all()
    # 转换为前端需要的格式
    current_facilities = [{'name': f.name, 'quantity': f.quantity} for f in current_facilities]
    # 获取房间自定义字段定义
    custom_field_defs = get_custom_field_definitions('room.custom_field')
    # 反序列化当前房间的自定义字段值
    custom_field_values = deserialize_custom_fields(room.custom_fields)

    if request.method == 'POST':
        try:
            # 在POST处理开始时解析自定义字段数据（用于验证错误时保留用户输入）
            form_custom_data = parse_custom_fields_data(request.form, custom_field_defs)
            # 检查是否有活跃住宿记录
            has_active_dorm = Dorm.query.filter_by(room_id=id, status='active').first() is not None
            # 处理设施数据（名称+数量）
            facility_names = request.form.getlist('facility_name[]')
            facilities = []
            
            for name in facility_names:
                if name:
                    # 获取对应设施名称的数量
                    quantity = request.form.get(f'facility_quantity[{name}]')
                    if quantity:
                        try:
                            qty = int(quantity)
                            if qty > 0:  # 只保留数量为正的设施
                                facilities.append({"name": name, "quantity": qty})
                        except ValueError:
                            logging.error(f'无效的设施数量: {quantity}')
                            continue  # 跳过数量无效的设施
            logging.info(f"处理后的设施数据: {facilities}")
            
            # 收集表单数据
            update_data = {
                'building': request.form.get('building', '').strip(),
                'room_number': request.form.get('room_number', '').strip(),
                'address': request.form.get('address', '').strip(),
                'room_level': request.form.get('room_level'),
                'remark': request.form.get('remark', '').strip(),
                # 租金相关字段
                'external_rent': float(request.form.get('external_rent', 0) or 0),
                'cost_rent': float(request.form.get('cost_rent', 0) or 0),
                # 水电表最大量程
                'electric_meter_max': float(request.form.get('electric_meter_max', 0) or 0),
                'water_meter_max': float(request.form.get('water_meter_max', 0) or 0),
                # 设施字段（包含数量）
                'facilities': facilities
            }
            
            # 检查房间当前是否有人入住（与前端判断条件保持一致）
            has_occupants = room.current_occupancy > 0

            # 始终从表单获取值
            update_data['gender_restriction'] = request.form.get('gender_restriction', '无限制')
            update_data['capacity'] = int(request.form.get('capacity', 4))
            update_data['status'] = request.form.get('status', RoomStatus.AVAILABLE.value)
            update_data['room_type'] = request.form.get('room_type', default_room_type)

            # 有用户入住时的条件验证
            if has_occupants or has_active_dorm:
                # 1. 容量不能低于当前已住人数
                if update_data['capacity'] < room.current_occupancy:
                    flash(f'有用户入住时，容纳人数不能低于当前已住人数({room.current_occupancy}人)', 'danger')
                    media_files = RoomPhotoManager.get_media_files(room.id)
                    return render_template(
                        'room_manage/room_edit.html',
                        title=f"编辑房间 - {room.building}{room.room_number}",
                        room=room,
                        room_types=room_types,
                        room_levels=room_levels,
                        gender_restrictions=Room.get_valid_gender_restrictions(),
                        valid_facilities=valid_facilities,
                        current_facilities=current_facilities,
                        buildings=buildings,
                        media_files=media_files,
                        custom_field_defs=custom_field_defs,
                        custom_field_values=form_custom_data
                    )
                
                # 2. 房间类型对应的容量不能低于当前已住人数
                room_type_capacity_map = {
                    '单人间': 1, '双人间': 2, '三人间': 3, '四人间': 4,
                    '五人间': 5, '六人间': 6, '七人间': 7, '八人间': 8
                }
                new_room_type = update_data['room_type']
                if new_room_type in room_type_capacity_map and room_type_capacity_map[new_room_type] < room.current_occupancy:
                    flash(f'有用户入住时，不能修改为容纳人数低于当前已住人数({room.current_occupancy}人)的房间类型', 'danger')
                    media_files = RoomPhotoManager.get_media_files(room.id)
                    return render_template(
                        'room_manage/room_edit.html',
                        title=f"编辑房间 - {room.building}{room.room_number}",
                        room=room,
                        room_types=room_types,
                        room_levels=room_levels,
                        gender_restrictions=Room.get_valid_gender_restrictions(),
                        valid_facilities=valid_facilities,
                        current_facilities=current_facilities,
                        buildings=buildings,
                        media_files=media_files,
                        custom_field_defs=custom_field_defs,
                        custom_field_values=form_custom_data
                    )
                
                # 3. 房间状态不能改为已关闭
                if update_data['status'] == RoomStatus.CLOSED.value:
                    flash('有用户入住时，不能将房间状态修改为已关闭', 'danger')
                    media_files = RoomPhotoManager.get_media_files(room.id)
                    return render_template(
                        'room_manage/room_edit.html',
                        title=f"编辑房间 - {room.building}{room.room_number}",
                        room=room,
                        room_types=room_types,
                        room_levels=room_levels,
                        gender_restrictions=Room.get_valid_gender_restrictions(),
                        valid_facilities=valid_facilities,
                        current_facilities=current_facilities,
                        buildings=buildings,
                        media_files=media_files,
                        custom_field_defs=custom_field_defs,
                        custom_field_values=form_custom_data
                    )
                
                # 4. 性别限制不能改为对立性别
                new_gender = update_data['gender_restriction']
                current_gender = room.gender_restriction
                if current_gender == '男' and new_gender == '女':
                    flash('当前房间有男性入住，不能将性别限制改为女', 'danger')
                    media_files = RoomPhotoManager.get_media_files(room.id)
                    return render_template(
                        'room_manage/room_edit.html',
                        title=f"编辑房间 - {room.building}{room.room_number}",
                        room=room,
                        room_types=room_types,
                        room_levels=room_levels,
                        gender_restrictions=Room.get_valid_gender_restrictions(),
                        valid_facilities=valid_facilities,
                        current_facilities=current_facilities,
                        buildings=buildings,
                        media_files=media_files,
                        custom_field_defs=custom_field_defs,
                        custom_field_values=form_custom_data
                    )
                elif current_gender == '女' and new_gender == '男':
                    flash('当前房间有女性入住，不能将性别限制改为男', 'danger')
                    media_files = RoomPhotoManager.get_media_files(room.id)
                    return render_template(
                        'room_manage/room_edit.html',
                        title=f"编辑房间 - {room.building}{room.room_number}",
                        room=room,
                        room_types=room_types,
                        room_levels=room_levels,
                        gender_restrictions=Room.get_valid_gender_restrictions(),
                        valid_facilities=valid_facilities,
                        current_facilities=current_facilities,
                        buildings=buildings,
                        media_files=media_files,
                        custom_field_defs=custom_field_defs,
                        custom_field_values=form_custom_data
                    )
            
            # 处理自定义字段
            custom_data = parse_custom_fields_data(request.form, custom_field_defs)
            custom_errors = validate_custom_fields(custom_data, custom_field_defs)
            if custom_errors:
                for err in custom_errors:
                    flash(err, 'danger')
                media_files = RoomPhotoManager.get_media_files(room.id)
                return render_template(
                    'room_manage/room_edit.html',
                    title=f"编辑房间 - {room.building}{room.room_number}",
                    room=room,
                    room_types=room_types,
                    room_levels=room_levels,
                    gender_restrictions=Room.get_valid_gender_restrictions(),
                    valid_facilities=valid_facilities,
                    current_facilities=current_facilities,
                    buildings=buildings,
                    media_files=media_files,
                    custom_field_defs=custom_field_defs,
                    custom_field_values=form_custom_data
                )
            update_data['custom_fields'] = serialize_custom_fields(custom_data)
            
            # 调用模型的update方法
            logging.info(f"尝试编辑房间数据: {update_data}")
            updated_room, error = room.update(update_data)
            
            if error:
                flash(error, 'danger')
                return render_template(
                    'room_manage/room_edit.html', 
                    title=f"编辑房间 - {room.building}{room.room_number}",
                    room=room,
                    room_types=room_types,
                    room_levels=room_levels,
                    gender_restrictions=Room.get_valid_gender_restrictions(),
                    valid_facilities=valid_facilities,  # 所有有效设施
                    current_facilities=current_facilities,  # 当前房间的设施（含数量）
                    buildings=buildings,  # 传递宿舍楼列表
                    media_files=media_files,  # 传递房间媒体文件
                    custom_field_defs=custom_field_defs,
                    custom_field_values=form_custom_data
                )

            # 调用批量更新方法处理设施
            RoomFacility.bulk_update_facilities(
                room_id=id, 
                facilities=facilities,
                remark="编辑房间时自动更新"
            )
            
            # 记录操作日志
            log_operation(
                user_id=current_user.id,
                module='room',
                operation_type='room_edit',
                action=f"编辑房间 {updated_room.building}{updated_room.room_number}",
                result="成功"
            )
            flash(f'编辑房间成功: {updated_room.building}{updated_room.room_number} 信息更新成功', 'success')
            logging.info(f"编辑房间成功，房间号: {updated_room.building}{updated_room.room_number}")
            return redirect(url_for('room.manage'))
            
        except Exception as e:
            log_operation(
                user_id=current_user.id,
                module='room',
                operation_type='room_edit',
                action=f"尝试编辑房间 [ID: {id}]失败: {str(e)}",
                result="失败"
            )
            flash('更新失败，请重试', 'danger')
            logging.error(f"编辑房间失败: {str(e)}\n{traceback.format_exc()}")
    # 记录访问日志
    log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='records',
            action="访问编辑房间页面",
            result="成功"
    )
    # GET请求：传递所有必要数据到模板
    # 获取房间媒体文件
    media_files = RoomPhotoManager.get_media_files(room.id)
    
    return render_template(
        'room_manage/room_edit.html',
        title=f"编辑房间 - {room.building}{room.room_number}",
        room=room,
        room_types=room_types,
        room_levels=room_levels,
        gender_restrictions=Room.get_valid_gender_restrictions(),
        valid_facilities=valid_facilities,  # 所有有效设施
        current_facilities=current_facilities,  # 当前房间的设施（含数量）
        buildings=buildings,  # 传递宿舍楼列表
        media_files=media_files,  # 传递房间媒体文件
        custom_field_defs=custom_field_defs,
        custom_field_values=custom_field_values
    )

# 删除房间 - 详细日志版本
@room_bp.route('/delete/<int:id>', methods=['GET'])
@login_required
@require_permission('room.delete')
def delete(id):
    try:
        room = Room.query.get_or_404(id)
        room_identifier = f"{room.building}{room.room_number}"  # 房间唯一标识
        
        # 记录删除开始日志
        logging.info(f"用户 {current_user.id} 开始删除房间: ID={id}, 标识={room_identifier}")
        
        # 调用模型的delete方法
        result = room.delete()
        
        if not result['success']:
            # 记录删除失败详细日志
            logging.warning(
                f"用户 {current_user.id} 删除房间失败: ID={id}, 标识={room_identifier}, "
                f"原因={result['message']}"
            )
            # 记录操作日志
            log_operation(
                user_id=current_user.id,
                module='room',
                operation_type='room_delete',
                action=f"删除房间 [ID: {id}, {room_identifier}]失败: {result['message']}",
                result="失败"
            )
            flash(f'删除失败：{result["message"]}', 'danger')
            return redirect(url_for('room.manage'))
        
        # 提交事务
        db.session.commit()
        
        # 记录删除成功详细日志（包含关联记录删除信息）
        logging.info(
            f"用户 {current_user.id} 删除房间成功: ID={id}, 标识={room_identifier}, "
            f"详情={result['message']}"
        )
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='room_delete',
            action=f"删除房间 [ID: {id}, {room_identifier}]成功，{result['message'].split('已成功删除')[1].strip()}",
            result="成功"
        )
        flash(result['message'], 'success')
        
    except Exception as e:
        db.session.rollback()
        # 记录异常详细日志
        logging.error(
            f"用户 {current_user.id} 删除房间时发生异常: ID={id}, "
            f"错误信息={str(e)}\n{traceback.format_exc()}"
        )
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='room_delete',
            action=f"删除房间 [ID: {id}]时发生异常: {str(e)}",
            result="失败"
        )
        flash('删除过程发生错误，请重试', 'danger')
    
    return redirect(url_for('room.manage'))


# 批量删除房间 - 详细日志版本
@room_bp.route('/batch-delete', methods=['POST'])
@login_required
@require_permission('room.delete')
def batch_delete():
    try:
        room_id_strings = request.form.getlist('room_ids[]')
        if not room_id_strings:
            logging.warning(f"用户 {current_user.id} 执行批量删除但未选择任何房间")
            flash('请选择要删除的房间', 'danger')
            return redirect(url_for('room.manage'))
            
        # 转换并验证ID格式
        room_ids = []
        invalid_ids = []
        for id_str in room_id_strings:
            try:
                room_id = int(id_str.strip())
                room_ids.append(room_id)
            except ValueError:
                invalid_ids.append(id_str)
        
        # 记录无效ID日志
        if invalid_ids:
            logging.warning(f"用户 {current_user.id} 批量删除包含无效ID: {', '.join(invalid_ids)}")
        
        if not room_ids:
            return redirect(url_for('room.manage'))
        
        # 记录批量删除开始日志
        logging.info(f"用户 {current_user.id} 开始批量删除房间，共{len(room_ids)}个房间ID: {room_ids}")
        
        # 批量处理删除
        deleted_count = 0
        errors = []
        success_details = []  # 记录成功删除的详细信息
        
        for room_id in room_ids:
            try:
                room = Room.query.get(room_id)
                if not room:
                    error_msg = f"房间ID {room_id} 不存在"
                    errors.append(error_msg)
                    logging.warning(f"用户 {current_user.id} 批量删除失败: {error_msg}")
                    continue
                
                room_identifier = f"{room.building}-{room.room_number}"
                result = room.delete()
                
                if result['success']:
                    deleted_count += 1
                    success_details.append(f"{room_identifier}: {result['message']}")
                    logging.info(f"用户 {current_user.id} 批量删除成功: {room_identifier}，{result['message']}")
                else:
                    error_msg = f"房间 {room_identifier}：{result['message']}"
                    errors.append(error_msg)
                    logging.warning(f"用户 {current_user.id} 批量删除失败: {error_msg}")
            
            except Exception as e:
                error_msg = f"处理房间ID {room_id} 时出错：{str(e)}"
                errors.append(error_msg)
                logging.error(f"用户 {current_user.id} 批量删除异常: {error_msg}", exc_info=True)
        
        # 统一提交事务
        db.session.commit()
        
        # 记录批量删除完成日志
        logging.info(
            f"用户 {current_user.id} 批量删除完成: 总数量={len(room_ids)}, "
            f"成功={deleted_count}, 失败={len(errors)}"
        )
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='room_delete',
            action=f"批量删除房间，共{len(room_ids)}个，成功删除{deleted_count}个，失败{len(errors)}个",
            result="成功"
        )
        
        # 展示结果
        if errors:
            for error in errors:
                flash(error, 'warning')
        
        if success_details:
            # 简要提示 + 详细日志
            flash(f'批量操作完成，成功删除{deleted_count}个房间', 'success')
            # 详细信息仅记录到日志，避免前端信息过载
            for detail in success_details:
                logging.info(f"批量删除成功详情: {detail}")
        
    except Exception as e:
        db.session.rollback()
        logging.error(
            f"用户 {current_user.id} 批量删除发生致命错误: {str(e)}\n{traceback.format_exc()}"
        )
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='room_delete',
            action=f"批量删除房间失败: {str(e)}",
            result="失败"
        )
        flash('批量删除过程发生错误，请重试', 'danger')
    
    return redirect(url_for('room.manage'))
    
# 删除全部房间 - 详细日志版本
@room_bp.route('/delete-all', methods=['POST'])
@login_required
@require_permission('room.delete')
def delete_all():
    try:
        # 获取所有房间
        all_rooms = Room.query.all()
        if not all_rooms:
            logging.info(f"用户 {current_user.id} 尝试删除全部房间，但系统中没有房间")
            flash('没有房间可删除', 'info')
            return redirect(url_for('room.manage'))
        
        total_count = len(all_rooms)
        logging.info(f"用户 {current_user.id} 开始删除全部房间，共{total_count}个房间")
        
        # 批量处理删除
        deleted_count = 0
        errors = []
        success_details = []
        
        for room in all_rooms:
            try:
                room_identifier = f"{room.building}-{room.room_number}"
                result = room.delete()
                
                if result['success']:
                    deleted_count += 1
                    success_details.append(f"{room_identifier}: {result['message']}")
                    logging.info(f"用户 {current_user.id} 全部删除成功: {room_identifier}")
                else:
                    error_msg = f"房间 {room_identifier}：{result['message']}"
                    errors.append(error_msg)
                    logging.warning(f"用户 {current_user.id} 全部删除失败: {error_msg}")
            
            except Exception as e:
                error_msg = f"处理房间 {room.building}-{room.room_number} 时出错：{str(e)}"
                errors.append(error_msg)
                logging.error(f"用户 {current_user.id} 全部删除异常: {error_msg}", exc_info=True)
        
        # 统一提交事务
        db.session.commit()
        
        # 记录总体结果日志
        logging.info(
            f"用户 {current_user.id} 删除全部房间完成: 总数量={total_count}, "
            f"成功={deleted_count}, 失败={len(errors)}"
        )
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='room_delete',
            action=f"删除全部房间，共{total_count}个，成功删除{deleted_count}个，失败{len(errors)}个",
            result="成功"
        )
        
        # 展示结果
        if errors:
            for error in errors:
                flash(error, 'warning')
        
        if success_details:
            flash(f'删除全部操作完成，成功删除{deleted_count}个房间', 'success')
            # 详细信息记录到日志
            for detail in success_details:
                logging.info(f"全部删除成功详情: {detail}")
        
    except Exception as e:
        db.session.rollback()
        logging.error(
            f"用户 {current_user.id} 删除全部房间发生致命错误: {str(e)}\n{traceback.format_exc()}"
        )
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='room_delete',
            action=f"删除全部房间失败: {str(e)}",
            result="失败"
        )
        flash('删除全部房间过程发生错误，请重试', 'danger')
    
    return redirect(url_for('room.manage'))


@room_bp.route('/upload_media', methods=['POST'])
@login_required
@require_permission('room.edit')
def upload_media():
    """上传房间照片或视频"""
    try:
        # 获取表单数据
        room_id = request.form.get('room_id')
        
        # 验证必要参数
        if not room_id:
            logging.warning(f"用户 {current_user.id} 尝试上传房间媒体文件，但缺少房间ID参数")
            return jsonify({'success': False, 'message': '缺少房间ID参数'})
        
        # 检查是否有文件上传
        if 'file' not in request.files:
            logging.warning(f"用户 {current_user.id} 尝试上传房间媒体文件，但没有文件被上传")
            return jsonify({'success': False, 'message': '没有文件被上传'})
        
        file = request.files['file']
        
        # 检查文件名是否为空
        if file.filename == '':
            logging.warning(f"用户 {current_user.id} 尝试上传房间媒体文件，但没有选择文件")
            return jsonify({'success': False, 'message': '没有选择文件'})
        
        # 上传文件
        filename = RoomPhotoManager.upload_file(file, room_id)
        
        if filename:
            # 生成文件URL
            file_url = RoomPhotoManager.get_media_url(filename, room_id)
            logging.info(f"用户 {current_user.id} 上传房间媒体文件成功: {filename}")
            # 记录操作日志
            log_operation(
                user_id=current_user.id,
                module='room',
                operation_type='upload_photo',
                action=f"上传房间ID {room_id} 的媒体文件: {filename}",
                result="成功"
            )
            
            return jsonify({
                'success': True,
                'message': '文件上传成功',
                'filename': filename,
                'url': file_url
            })
        else:
            logging.warning(f"用户 {current_user.id} 尝试上传房间媒体文件，但文件格式不支持")
            return jsonify({'success': False, 'message': '文件格式不支持'})
    except Exception as e:
        logging.error(f"上传房间媒体文件时发生错误: {str(e)}")
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='upload_photo',
            action=f"上传房间媒体文件失败: {str(e)}",
            result="失败"
        )
        return jsonify({'success': False, 'message': f'上传失败: {str(e)}'})


@room_bp.route('/delete_media', methods=['POST'])
@login_required
@require_permission('room.edit')
def delete_media():
    """删除房间照片或视频"""
    try:
        # 获取请求数据
        data = request.get_json()
        room_id = data.get('room_id')
        filename = data.get('filename')
        
        # 验证必要参数
        if not room_id or not filename:
            logging.warning(f"用户 {current_user.id} 尝试删除房间媒体文件，但缺少必要参数")
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        # 验证room_id是否为整数
        try:
            room_id = int(room_id)
        except ValueError:
            logging.warning(f"用户 {current_user.id} 提供的房间ID格式无效: {room_id}")
            return jsonify({'success': False, 'message': '房间ID格式无效'})
        
        # 安全处理文件名，防止路径遍历
        filename = secure_filename(filename)
        if not filename:
            logging.warning(f"用户 {current_user.id} 尝试删除房间媒体文件，但文件名无效")
            return jsonify({'success': False, 'message': '无效的文件名'}), 400
        
        # 删除文件
        success = RoomPhotoManager.delete_file(filename, room_id)
        logging.info(f"用户 {current_user.id} 尝试删除房间ID为 {room_id} 的媒体文件: {filename}")
        if success:
            # 记录操作日志
            log_operation(
                user_id=current_user.id,
                module='room',
                operation_type='delete_photo',
                action=f"删除房间ID为 {room_id} 的媒体文件: {filename}",
                result="成功"
            )
            logging.info(f"用户 {current_user.id} 删除房间媒体文件成功: {filename}")
            return jsonify({'success': True, 'message': '文件删除成功'})
        else:
            logging.warning(f"用户 {current_user.id} 尝试删除房间媒体文件，但文件删除失败或文件不存在")
            return jsonify({'success': False, 'message': '文件删除失败或文件不存在'})
    except Exception as e:
        logging.error(f"删除房间媒体文件时发生错误: {str(e)}")
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='delete_photo',
            action=f"删除房间媒体文件失败: {str(e)}",
            result="失败"
        )
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})


# ========== 临时上传端点（用于添加房间时，房间尚未创建的场景） ==========

@room_bp.route('/upload_temp_media', methods=['POST'])
@login_required
@require_permission('room.create')
def upload_temp_media():
    """上传临时照片/视频到临时目录（添加房间页面使用，此时房间尚未创建）"""
    try:
        temp_key = request.form.get('temp_key')
        
        if not temp_key:
            return jsonify({'success': False, 'message': '缺少临时标识参数'}), 400
        
        # 安全处理temp_key，防止路径遍历
        temp_key = secure_filename(temp_key)
        if not temp_key:
            return jsonify({'success': False, 'message': '无效的临时标识参数'}), 400
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有文件被上传'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '没有选择文件'}), 400
        
        filename = RoomPhotoManager.upload_temp_file(file, temp_key)
        if not filename:
            logging.warning(f"用户 {current_user.id} 上传临时房间媒体文件失败: 文件格式不支持或文件过大, temp_key={temp_key}")
            return jsonify({'success': False, 'message': '不支持的文件格式或文件过大'}), 400
        
        file_url = RoomPhotoManager.get_temp_media_url(filename, temp_key)
        
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='upload_photo',
            action=f"上传临时房间媒体文件: {filename} (temp_key={temp_key})",
            result="成功"
        )
        
        return jsonify({
            'success': True,
            'message': '上传成功',
            'filename': filename,
            'url': file_url
        })
        
    except Exception as e:
        logging.error(f"上传临时房间媒体文件失败: {str(e)}")
        return jsonify({'success': False, 'message': f'上传失败: {str(e)}'})


@room_bp.route('/get_temp_media_files', methods=['GET'])
@login_required
@require_permission('room.view')
def get_temp_media_files():
    """获取指定temp_key临时目录中的所有媒体文件"""
    try:
        temp_key = request.args.get('temp_key')
        
        if not temp_key:
            return jsonify({'success': False, 'message': '缺少临时标识参数'})
        
        # 安全处理temp_key，防止路径遍历
        temp_key = secure_filename(temp_key)
        if not temp_key:
            return jsonify({'success': False, 'message': '无效的临时标识参数'})
        
        media_files = RoomPhotoManager.get_temp_media_files(temp_key)
        
        result_files = []
        for file in media_files:
            result_files.append({
                'filename': file['filename'],
                'type': file['type'],
                'url': file['url'],
                'upload_time': file.get('upload_time').isoformat() if file.get('upload_time') else None
            })
        
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='records',
            action=f"查询临时媒体文件列表 (temp_key={temp_key}, 共{len(result_files)}个文件)",
            result="成功"
        )
        
        return jsonify({
            'success': True,
            'files': result_files
        })
        
    except Exception as e:
        logging.error(f"获取临时媒体文件列表失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取失败: {str(e)}'})


@room_bp.route('/delete_temp_media', methods=['POST'])
@login_required
@require_permission('room.create')
def delete_temp_media():
    """删除临时目录中的媒体文件"""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'success': False, 'message': '请求数据格式无效'})
        temp_key = data.get('temp_key')
        filename = data.get('filename')
        
        if not temp_key or not filename:
            return jsonify({'success': False, 'message': '缺少必要参数'})
        
        # 安全处理temp_key，防止路径遍历
        temp_key = secure_filename(temp_key)
        if not temp_key:
            return jsonify({'success': False, 'message': '无效的临时标识参数'}), 400
        
        # 安全处理filename（RoomPhotoManager.delete_temp_file内部也会调用secure_filename，
        # 此处提前校验可尽早拒绝无效文件名，避免不必要的文件系统操作）
        filename = secure_filename(filename)
        if not filename:
            return jsonify({'success': False, 'message': '无效的文件名'}), 400
        
        success = RoomPhotoManager.delete_temp_file(filename, temp_key)
        
        if success:
            log_operation(
                user_id=current_user.id,
                module='room',
                operation_type='delete_photo',
                action=f"删除临时房间媒体文件: {filename} (temp_key={temp_key})",
                result="成功"
            )
            return jsonify({'success': True, 'message': '文件删除成功'})
        else:
            return jsonify({'success': False, 'message': '文件删除失败或文件不存在'})
            
    except Exception as e:
        logging.error(f"删除临时媒体文件失败: {str(e)}")
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})


@room_bp.route('/clear_temp_media', methods=['POST'])
@login_required
@require_permission('room.create')
def clear_temp_media():
    """清理指定temp_key临时目录中的所有媒体文件"""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'success': False, 'message': '请求数据格式无效'})
        temp_key = data.get('temp_key')
        
        if not temp_key:
            return jsonify({'success': False, 'message': '缺少临时标识参数'})
        
        # 安全处理temp_key，防止路径遍历
        temp_key = secure_filename(temp_key)
        if not temp_key:
            return jsonify({'success': False, 'message': '无效的临时标识参数'})
        
        result = RoomPhotoManager.clear_temp_files(temp_key)
        
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='delete_photo',
            action=f"清理临时房间媒体文件 (temp_key={temp_key}) [删除: {result['deleted']}]",
            result="成功" if not result['errors'] else "部分成功"
        )
        
        return jsonify({
            'success': True,
            'deleted': result['deleted'],
            'errors': result['errors'],
            'message': f"成功清理 {result['deleted']} 个文件" + (f"，{len(result['errors'])} 个失败" if result['errors'] else "")
        })
        
    except Exception as e:
        logging.error(f"清理临时媒体文件失败: {str(e)}")
        return jsonify({'success': False, 'message': f'清理失败: {str(e)}'})
