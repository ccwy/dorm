from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from utils.db import db
from models.room import Room, RoomStatus
from models.dorm import Dorm
from config import Config
from utils.log import log_operation
import logging
from .room import room_bp  # 导入room蓝图
import traceback
from models.system_config import SystemConfig  # 新增：导入系统配置模型
from utils.room_photo import RoomPhotoManager
from datetime import datetime
# 导入admin_required装饰器
from utils.auth import admin_required
from models.room_facility import RoomFacility  # 新增：导入房间设施模型

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
        from models.room import Room
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
@admin_required
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
                'capacity': int(request.form.get('capacity', 4)),
                'status': request.form.get('status', RoomStatus.AVAILABLE.value),
                'remark': request.form.get('remark', '').strip(),
                'external_rent': float(request.form.get('external_rent', 0) or 0),
                'cost_rent': float(request.form.get('cost_rent', 0) or 0),
                'electric_meter_max': float(request.form.get('electric_meter_max', 0) or 9999.99),
                'water_meter_max': float(request.form.get('water_meter_max', 0) or 9999.99),
                'facilities': facilities  # 传递包含数量的设施对象数组
            }
            
            # 处理创建时间
            created_at_str = request.form.get('created_at')
            if created_at_str:
                try:
                    # 转换为datetime对象

                    created_at = datetime.strptime(created_at_str, '%Y-%m-%dT%H:%M')
                    room_data['created_at'] = created_at
                except ValueError:
                    logging.error(f'无效的创建时间格式: {created_at_str}')
            
            # 调用模型的create方法（实际创建房间）
            logging.info(f"尝试添加房间数据: {room_data}")
            new_room, error = Room.create(room_data)
            
            if error:
                flash(error, 'danger')
                return render_template('room_manage/room_add.html', 
                    facilities=valid_facilities,
                    room_types=room_types,
                    buildings=buildings)

            # 房间创建成功后，添加设施
            RoomFacility.bulk_update_facilities(
                room_id=new_room.id, 
                facilities=facilities,
                remark="添加房间时自动添加"
            )
            
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
                    buildings=buildings  # 传递楼栋列表到前端
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
        current_time=current_time  # 传递当前时间作为默认值
    )
    
@room_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
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

    if request.method == 'POST':
        try:
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
            
            # 如果有用户入住，不允许修改性别限制、容量、状态和房间类型
            # 注意：前端在这种情况下会禁用这些字段，表单不会提交这些值
            # 所以必须使用数据库中已有的值，而不是尝试从请求中获取
            if has_occupants or has_active_dorm:
                update_data['gender_restriction'] = room.gender_restriction
                update_data['capacity'] = room.capacity
                update_data['status'] = room.status
                update_data['room_type'] = room.room_type
            else:
                # 没有用户入住时，使用表单提交的值
                update_data['gender_restriction'] = request.form.get('gender_restriction', '无限制')
                update_data['capacity'] = int(request.form.get('capacity', 4))
                update_data['status'] = request.form.get('status', RoomStatus.AVAILABLE.value)
                update_data['room_type'] = request.form.get('room_type', default_room_type)
            
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
                    media_files=media_files  # 传递房间媒体文件
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
        media_files=media_files  # 传递房间媒体文件
    )

# 删除房间 - 详细日志版本
@room_bp.route('/delete/<int:id>', methods=['GET'])
@login_required
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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
@admin_required
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
