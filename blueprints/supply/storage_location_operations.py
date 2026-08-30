from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from utils.db import db
from models.supply.storage_location import StorageLocation
from utils.log import log_operation
from utils.auth import require_permission
import logging
import traceback
from datetime import datetime
from .storage_location import storage_location_bp


# ========== 路由：新增存放位置 ==========
@storage_location_bp.route('/operations/add', methods=['POST'])
@login_required
@require_permission('supply.create')
def add_storage_location():
    """新增存放位置"""
    try:
        name = request.form.get('name', '').strip()
        code = request.form.get('code', '').strip() or None
        building = request.form.get('building', '').strip() or None
        floor = request.form.get('floor', '').strip() or None
        room = request.form.get('room', '').strip() or None
        address = request.form.get('address', '').strip() or None
        status = request.form.get('status', '启用').strip() or '启用'
        usage_type = request.form.get('usage_type', 'supply').strip() or 'supply'
        remark = request.form.get('remark', '').strip() or None

        # 必填字段校验
        if not name:
            flash('位置名称不能为空', 'danger')
            return redirect(url_for('storage_location.add_page'))

        # 状态值校验
        if status not in ['启用', '停用']:
            status = '启用'

        # 使用类型校验
        valid_usage_types = ['supply', 'fixed_asset', 'contract']
        if usage_type not in valid_usage_types:
            usage_type = 'supply'

        # 检查名称是否重复（联合usage_type校验）
        if StorageLocation.is_name_exists(name, usage_type=usage_type):
            flash(f'已存在存放位置"{name}"（相同使用类型下）', 'danger')
            return redirect(url_for('storage_location.add_page'))

        location = StorageLocation.create(
            name=name, code=code, building=building, floor=floor,
            room=room, address=address, status=status, usage_type=usage_type,
            remark=remark, handler_user_id=current_user.id,
            operator_user_id=current_user.id
        )

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='storage_location_add',
            action=f"新增存放位置: {name}",
            result="成功"
        )

        flash(f'新增存放位置成功: {name}', 'success')
        logging.info(f"新增存放位置成功，位置ID: {location.id}, 名称: {name}")

        if request.form.get('save_and_continue'):
            return redirect(url_for('storage_location.add_page'))
        return redirect(url_for('storage_location.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='storage_location_add',
            action=f"新增存放位置失败: {str(e)}",
            result="失败"
        )
        flash(f'新增存放位置失败: {str(e)}', 'danger')
        logging.error(f"新增存放位置失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('storage_location.add_page'))


# ========== 路由：编辑存放位置 ==========
@storage_location_bp.route('/operations/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('supply.edit')
def edit_storage_location(id):
    """编辑存放位置"""
    try:
        location = StorageLocation.query.get_or_404(id)
        old_name = location.name
        old_usage_type = location.usage_type

        # 获取表单数据
        new_name = request.form.get('name', '').strip()
        new_code = request.form.get('code', '').strip() or None
        new_building = request.form.get('building', '').strip() or None
        new_floor = request.form.get('floor', '').strip() or None
        new_room = request.form.get('room', '').strip() or None
        new_address = request.form.get('address', '').strip() or None
        new_status = request.form.get('status', '启用').strip() or '启用'
        new_usage_type = request.form.get('usage_type', location.usage_type).strip() or location.usage_type
        new_remark = request.form.get('remark', '').strip() or None

        # 状态值校验
        if new_status not in ['启用', '停用']:
            new_status = '启用'

        # 使用类型校验
        valid_usage_types = ['supply', 'fixed_asset', 'contract']
        if new_usage_type not in valid_usage_types:
            new_usage_type = location.usage_type

        # 必填字段校验
        if not new_name:
            flash('位置名称不能为空', 'danger')
            return redirect(url_for('storage_location.edit_page', id=id))

        # 检查名称是否重复（联合usage_type校验，排除自身）
        if StorageLocation.is_name_exists(new_name, usage_type=new_usage_type, exclude_id=id):
            flash(f'已存在存放位置"{new_name}"（相同使用类型下）', 'danger')
            return redirect(url_for('storage_location.edit_page', id=id))

        # 使用类型中文映射
        usage_type_display = {'supply': '低值易耗品', 'fixed_asset': '固定资产', 'contract': '合同管理'}

        # 记录变更
        changes = []
        if old_name != new_name:
            changes.append(f"名称: {old_name} → {new_name}")
        if location.code != new_code:
            changes.append(f"编码: {location.code or '无'} → {new_code or '无'}")
        if location.building != new_building:
            changes.append(f"楼栋: {location.building or '无'} → {new_building or '无'}")
        if location.floor != new_floor:
            changes.append(f"楼层: {location.floor or '无'} → {new_floor or '无'}")
        if location.room != new_room:
            changes.append(f"房间号: {location.room or '无'} → {new_room or '无'}")
        if location.address != new_address:
            changes.append(f"地址: {location.address or '无'} → {new_address or '无'}")
        if location.status != new_status:
            changes.append(f"状态: {location.status} → {new_status}")
        if old_usage_type != new_usage_type:
            changes.append(f"使用类型: {usage_type_display.get(old_usage_type, old_usage_type)} → {usage_type_display.get(new_usage_type, new_usage_type)}")
        if location.remark != new_remark:
            changes.append("备注已更新")

        # 更新存放位置信息
        location.name = new_name
        location.code = new_code
        location.building = new_building
        location.floor = new_floor
        location.room = new_room
        location.address = new_address
        location.status = new_status
        location.usage_type = new_usage_type
        location.handler_user_id = current_user.id
        location.remark = new_remark
        location.operator_user_id = current_user.id
        db.session.commit()

        # 记录操作日志
        change_summary = '，'.join(changes) if changes else '无变更'
        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='storage_location_edit',
            action=f"编辑存放位置: {old_name} → {new_name}，{change_summary}",
            result="成功"
        )

        flash(f'编辑存放位置成功: {new_name}', 'success')
        logging.info(f"编辑存放位置成功，位置ID: {id}, 变更: {change_summary}")
        return redirect(url_for('storage_location.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='storage_location_edit',
            action=f"编辑存放位置失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'编辑存放位置失败: {str(e)}', 'danger')
        logging.error(f"编辑存放位置失败，位置ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('storage_location.index'))


# ========== 路由：删除存放位置 ==========
@storage_location_bp.route('/operations/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('supply.delete')
def delete_storage_location(id):
    """删除存放位置 - 检查使用情况，被引用时拒绝删除"""
    try:
        location = StorageLocation.query.get_or_404(id)
        location_name = location.name

        # 检查使用情况
        usage = StorageLocation.check_usage(id)
        if usage['used']:
            details = usage['details']
            parts = []
            if details.get('stock_detail_count', 0) > 0:
                parts.append(f"{details['stock_detail_count']}条库存明细")
            if details.get('stock_record_count', 0) > 0:
                parts.append(f"{details['stock_record_count']}条进出库记录")
            usage_detail = '、'.join(parts)
            flash(f'存放位置"{location_name}"正在被使用（{usage_detail}），无法删除', 'danger')
            return redirect(url_for('storage_location.detail', id=id))

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='storage_location_delete',
            action=f"删除存放位置: {location_name}",
            result="成功"
        )

        # 删除存放位置
        db.session.delete(location)
        db.session.commit()

        flash(f'删除存放位置成功: {location_name}', 'success')
        logging.info(f"删除存放位置成功，位置ID: {id}, 名称: {location_name}")
        return redirect(url_for('storage_location.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='storage_location_delete',
            action=f"删除存放位置失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'删除存放位置失败: {str(e)}', 'danger')
        logging.error(f"删除存放位置失败，位置ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('storage_location.index'))


# ========== 路由：批量删除存放位置 ==========
@storage_location_bp.route('/operations/batch-delete', methods=['POST'])
@login_required
@require_permission('supply.delete')
def batch_delete_storage_locations():
    """批量删除存放位置 - 检查使用情况，被引用时跳过"""
    try:
        ids = request.form.getlist('ids')
        if not ids:
            flash('未选择要删除的存放位置', 'warning')
            return redirect(url_for('storage_location.index'))

        success_count = 0
        fail_count = 0

        for id in ids:
            location = StorageLocation.query.get(int(id))
            if location:
                # 检查使用情况
                usage = StorageLocation.check_usage(id)
                if usage['used']:
                    fail_count += 1
                else:
                    db.session.delete(location)
                    success_count += 1
            else:
                fail_count += 1

        db.session.commit()

        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='storage_location_batch_delete',
            action=f"批量删除存放位置: 成功{success_count}条, 失败{fail_count}条",
            result="成功"
        )

        flash(f'批量删除完成: 成功{success_count}条, 失败{fail_count}条', 'success')
        logging.info(f"批量删除存放位置，成功{success_count}条, 失败{fail_count}条")
        return redirect(url_for('storage_location.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='storage_location_batch_delete',
            action=f"批量删除存放位置失败: {str(e)}",
            result="失败"
        )
        flash(f'批量删除失败: {str(e)}', 'danger')
        logging.error(f"批量删除存放位置失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('storage_location.index'))