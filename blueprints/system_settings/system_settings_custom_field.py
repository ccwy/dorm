from flask import request, jsonify, redirect, url_for, render_template, flash
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.custom_fields import get_custom_field_definitions, save_custom_field_definitions, get_all_custom_field_definitions, cleanup_custom_field_from_models
from utils.log import log_operation
from .system_settings import system_config_bp
import logging
import re


# ==================== 自定义字段管理独立页面 ====================

@system_config_bp.route('/custom-field', methods=['GET'])
@login_required
@require_permission('system_settings.manage')
def custom_field_page():
    """自定义字段管理独立页面"""
    all_fields = get_all_custom_field_definitions()
    return render_template('system_settings/custom_field.html',
                           all_fields=all_fields,
                           title="自定义字段管理")


@system_config_bp.route('/custom-field/add', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def custom_field_add():
    """添加自定义字段"""
    field_key = request.form.get('field_key', '').strip()
    label = request.form.get('label', '').strip()
    field_type = request.form.get('type', 'text')
    module = request.form.get('module', 'user')
    required = request.form.get('required') == 'on'
    sort_order = request.form.get('sort_order', 0, type=int)
    default_value = request.form.get('default_value', '').strip()
    options_str = request.form.get('options', '').strip()
    description = request.form.get('description', '').strip()

    # 校验
    if not field_key or not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', field_key):
        flash('字段key格式错误，只能以字母开头，包含字母、数字和下划线', 'error')
        return redirect(url_for('system_settings.custom_field_page'))
    if not label:
        flash('字段标签不能为空', 'error')
        return redirect(url_for('system_settings.custom_field_page'))
    if module not in ('user', 'room'):
        flash('使用模块必须为用户或房间', 'error')
        return redirect(url_for('system_settings.custom_field_page'))

    # 获取当前字段列表
    fields = get_custom_field_definitions(module)

    # 检查key唯一性
    if any(f.get('field_key') == field_key for f in fields):
        flash(f"模块'{module}'中已存在字段key '{field_key}'", 'error')
        return redirect(url_for('system_settings.custom_field_page'))

    # 构建新字段
    new_field = {
        'field_key': field_key,
        'label': label,
        'type': field_type,
        'required': required,
        'sort_order': sort_order or len(fields) + 1,
        'default_value': default_value,
        'description': description,
    }
    if field_type == 'select' and options_str:
        new_field['options'] = [opt.strip() for opt in options_str.split(',') if opt.strip()]

    fields.append(new_field)
    success = save_custom_field_definitions(module, fields, current_user.id)

    if success:
        log_operation(user_id=current_user.id, module='system', operation_type='create',
                     action=f"添加{module}自定义字段 '{field_key}'", result="成功")
        flash(f"字段 '{field_key}' 添加成功", 'success')
    else:
        flash("添加字段失败", 'error')

    return redirect(url_for('system_settings.custom_field_page'))


@system_config_bp.route('/custom-field/edit', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def custom_field_edit():
    """编辑自定义字段"""
    original_key = request.form.get('original_key', '').strip()
    original_module = request.form.get('original_module', 'user')
    field_key = request.form.get('field_key', '').strip()
    label = request.form.get('label', '').strip()
    field_type = request.form.get('type', 'text')
    module = request.form.get('module', 'user')
    required = request.form.get('required') == 'on'
    sort_order = request.form.get('sort_order', 0, type=int)
    default_value = request.form.get('default_value', '').strip()
    options_str = request.form.get('options', '').strip()
    description = request.form.get('description', '').strip()

    # 校验
    if not field_key or not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', field_key):
        flash('字段key格式错误', 'error')
        return redirect(url_for('system_settings.custom_field_page'))
    if not label:
        flash('字段标签不能为空', 'error')
        return redirect(url_for('system_settings.custom_field_page'))

    # 如果module变了或key变了，需要处理跨模块移动
    if original_module != module:
        # 从原模块删除
        old_fields = get_custom_field_definitions(original_module)
        old_fields = [f for f in old_fields if f.get('field_key') != original_key]
        save_custom_field_definitions(original_module, old_fields, current_user.id)
        # 添加到新模块
        new_fields = get_custom_field_definitions(module)
    else:
        new_fields = get_custom_field_definitions(module)
        # 如果key变了，检查新key是否重复
        if field_key != original_key and any(f.get('field_key') == field_key for f in new_fields):
            flash(f"模块'{module}'中已存在字段key '{field_key}'", 'error')
            return redirect(url_for('system_settings.custom_field_page'))
        # 移除旧字段
        new_fields = [f for f in new_fields if f.get('field_key') != original_key]

    # 构建更新后的字段
    updated_field = {
        'field_key': field_key,
        'label': label,
        'type': field_type,
        'required': required,
        'sort_order': sort_order,
        'default_value': default_value,
        'description': description,
    }
    if field_type == 'select' and options_str:
        updated_field['options'] = [opt.strip() for opt in options_str.split(',') if opt.strip()]

    new_fields.append(updated_field)
    success = save_custom_field_definitions(module, new_fields, current_user.id)

    if success:
        log_operation(user_id=current_user.id, module='system', operation_type='update',
                     action=f"编辑{module}自定义字段 '{field_key}'", result="成功")
        flash(f"字段 '{field_key}' 更新成功", 'success')
    else:
        flash("更新字段失败", 'error')

    return redirect(url_for('system_settings.custom_field_page'))


@system_config_bp.route('/custom-field/delete', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def custom_field_delete():
    """删除自定义字段"""
    field_key = request.form.get('field_key', '').strip()
    module = request.form.get('module', 'user')

    fields = get_custom_field_definitions(module)
    original_count = len(fields)
    fields = [f for f in fields if f.get('field_key') != field_key]

    if len(fields) == original_count:
        flash(f"未找到字段 '{field_key}'", 'error')
        return redirect(url_for('system_settings.custom_field_page'))

    success = save_custom_field_definitions(module, fields, current_user.id)
    if success:
        # 同步清理模型中对应字段的值
        cleanup_custom_field_from_models(module, field_key)
        log_operation(user_id=current_user.id, module='system', operation_type='delete',
                     action=f"删除{module}自定义字段 '{field_key}'", result="成功")
        flash(f"字段 '{field_key}' 删除成功", 'success')
    else:
        flash("删除字段失败", 'error')

    return redirect(url_for('system_settings.custom_field_page'))


@system_config_bp.route('/custom-field/batch-delete', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def custom_field_batch_delete():
    """批量删除自定义字段"""
    items = request.form.getlist('items[]')
    
    if not items:
        flash('未选择要删除的字段', 'error')
        return redirect(url_for('system_settings.custom_field_page'))
    
    # 按module分组
    deleted_keys = {}
    for item in items:
        parts = item.split(':')
        if len(parts) == 2:
            module, field_key = parts
            if module not in deleted_keys:
                deleted_keys[module] = []
            deleted_keys[module].append(field_key)
    
    total_deleted = 0
    for module, keys in deleted_keys.items():
        fields = get_custom_field_definitions(module)
        original_count = len(fields)
        fields = [f for f in fields if f.get('field_key') not in keys]
        deleted_count = original_count - len(fields)
        
        if deleted_count > 0:
            success = save_custom_field_definitions(module, fields, current_user.id)
            if success:
                # 同步清理模型中对应字段的值
                for field_key in keys:
                    cleanup_custom_field_from_models(module, field_key)
                total_deleted += deleted_count
                log_operation(user_id=current_user.id, module='system', operation_type='delete',
                             action=f"批量删除{module}自定义字段: {keys}", result="成功")
    
    if total_deleted > 0:
        flash(f"成功删除 {total_deleted} 个字段", 'success')
    else:
        flash("未找到要删除的字段", 'error')
    
    return redirect(url_for('system_settings.custom_field_page'))


@system_config_bp.route('/custom-field/delete-all', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def custom_field_delete_all():
    """删除全部自定义字段"""
    total_deleted = 0
    for module in ('user', 'room'):
        fields = get_custom_field_definitions(module)
        if fields:
            # 收集所有要清理的字段key
            keys_to_cleanup = [f.get('field_key') for f in fields]
            success = save_custom_field_definitions(module, [], current_user.id)
            if success:
                # 同步清理模型中对应字段的值
                for field_key in keys_to_cleanup:
                    cleanup_custom_field_from_models(module, field_key)
                total_deleted += len(fields)
                log_operation(user_id=current_user.id, module='system', operation_type='delete',
                             action=f"删除全部{module}自定义字段", result="成功")
    
    if total_deleted > 0:
        flash(f"成功删除全部 {total_deleted} 个字段", 'success')
    else:
        flash("没有可删除的字段", 'warning')
    
    return redirect(url_for('system_settings.custom_field_page'))


@system_config_bp.route('/custom-field/move', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def custom_field_move():
    """移动自定义字段排序（上移/下移）"""
    field_key = request.form.get('field_key', '').strip()
    module = request.form.get('module', 'user')
    direction = request.form.get('direction', 'up')

    fields = get_custom_field_definitions(module)

    # 找到当前字段的索引
    current_index = None
    for i, f in enumerate(fields):
        if f.get('field_key') == field_key:
            current_index = i
            break

    if current_index is None:
        flash(f"未找到字段 '{field_key}'", 'error')
        return redirect(url_for('system_settings.custom_field_page'))

    # 计算目标索引
    if direction == 'up' and current_index > 0:
        target_index = current_index - 1
    elif direction == 'down' and current_index < len(fields) - 1:
        target_index = current_index + 1
    else:
        return redirect(url_for('system_settings.custom_field_page'))

    # 交换位置
    fields[current_index], fields[target_index] = fields[target_index], fields[current_index]

    # 更新sort_order
    for i, f in enumerate(fields):
        f['sort_order'] = i + 1

    success = save_custom_field_definitions(module, fields, current_user.id)
    if not success:
        flash("调整排序失败", 'error')

    return redirect(url_for('system_settings.custom_field_page'))


# ==================== 自定义字段管理API（从system_settings.py迁移） ====================

@system_config_bp.route('/api/custom-fields/<category>', methods=['GET'])
@login_required
@require_permission('system_settings.manage')
def get_custom_fields(category):
    """获取自定义字段定义列表"""
    try:
        if category not in ('user', 'room'):
            return jsonify({
                "success": False,
                "message": f"不支持的自定义字段类别: {category}"
            }), 400

        fields = get_custom_field_definitions(category)
        return jsonify({
            "success": True,
            "data": fields
        })
    except Exception as e:
        logging.error(f"获取自定义字段定义失败 ({category}): {str(e)}")
        return jsonify({
            "success": False,
            "message": f"获取自定义字段定义失败: {str(e)}"
        }), 500


@system_config_bp.route('/api/custom-fields/<category>/save', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def save_custom_fields(category):
    """保存自定义字段定义（整体保存，包含增删改排序）"""
    try:
        if category not in ('user', 'room'):
            return jsonify({
                "success": False,
                "message": f"不支持的自定义字段类别: {category}"
            }), 400

        data = request.get_json()
        fields = data.get('fields', [])

        # 基本校验
        if not isinstance(fields, list):
            return jsonify({
                "success": False,
                "message": "字段定义必须为数组"
            }), 400

        # 校验每个字段定义
        field_keys = set()
        for i, field in enumerate(fields):
            if not isinstance(field, dict):
                return jsonify({
                    "success": False,
                    "message": f"第{i+1}个字段定义格式错误"
                }), 400

            field_key = field.get('field_key', '').strip()
            if not field_key:
                return jsonify({
                    "success": False,
                    "message": f"第{i+1}个字段的key不能为空"
                }), 400

            # 检查key格式（只允许字母、数字、下划线）
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', field_key):
                return jsonify({
                    "success": False,
                    "message": f"字段key '{field_key}' 格式错误，只能以字母开头，包含字母、数字和下划线"
                }), 400

            # 检查key唯一性
            if field_key in field_keys:
                return jsonify({
                    "success": False,
                    "message": f"字段key '{field_key}' 重复"
                }), 400
            field_keys.add(field_key)

            label = field.get('label', '').strip()
            if not label:
                return jsonify({
                    "success": False,
                    "message": f"字段 '{field_key}' 的标签不能为空"
                }), 400

            field_type = field.get('type', 'text')
            if field_type not in ('text', 'number', 'select', 'date', 'checkbox', 'textarea'):
                return jsonify({
                    "success": False,
                    "message": f"字段 '{field_key}' 的类型 '{field_type}' 不支持"
                }), 400

            # select类型必须有options
            if field_type == 'select':
                options = field.get('options', [])
                if not options or not isinstance(options, list):
                    return jsonify({
                        "success": False,
                        "message": f"字段 '{field_key}' 为select类型，必须提供选项列表"
                    }), 400

        # 保存字段定义
        success = save_custom_field_definitions(category, fields, current_user.id)
        if success:
            log_operation(
                user_id=current_user.id,
                module='system',
                operation_type='update',
                action=f"保存{category}自定义字段定义",
                result="成功"
            )
            return jsonify({
                "success": True,
                "message": "自定义字段定义保存成功"
            })
        else:
            return jsonify({
                "success": False,
                "message": "保存自定义字段定义失败"
            }), 500

    except Exception as e:
        logging.error(f"保存自定义字段定义失败 ({category}): {str(e)}")
        return jsonify({
            "success": False,
            "message": f"保存自定义字段定义失败: {str(e)}"
        }), 500


@system_config_bp.route('/api/custom-fields/<category>/delete/<field_key>', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def delete_custom_field(category, field_key):
    """删除单个自定义字段定义"""
    try:
        if category not in ('user', 'room'):
            return jsonify({
                "success": False,
                "message": f"不支持的自定义字段类别: {category}"
            }), 400

        # 获取当前字段定义列表
        fields = get_custom_field_definitions(category)

        # 查找并删除指定字段
        original_count = len(fields)
        fields = [f for f in fields if f.get('field_key') != field_key]

        if len(fields) == original_count:
            return jsonify({
                "success": False,
                "message": f"未找到字段 '{field_key}'"
            }), 404

        # 保存更新后的字段定义
        success = save_custom_field_definitions(category, fields, current_user.id)
        if success:
            # 同步清理模型中对应字段的值
            cleanup_custom_field_from_models(category, field_key)
            log_operation(
                user_id=current_user.id,
                module='system',
                operation_type='delete',
                action=f"删除{category}自定义字段 '{field_key}'",
                result="成功"
            )
            return jsonify({
                "success": True,
                "message": f"字段 '{field_key}' 删除成功"
            })
        else:
            return jsonify({
                "success": False,
                "message": "删除字段失败"
            }), 500

    except Exception as e:
        logging.error(f"删除自定义字段定义失败 ({category}/{field_key}): {str(e)}")
        return jsonify({
            "success": False,
            "message": f"删除自定义字段定义失败: {str(e)}"
        }), 500


# ==================== 合并自定义字段管理API（用户+房间） ====================

@system_config_bp.route('/api/custom-fields/all', methods=['GET'])
@login_required
@require_permission('system_settings.manage')
def get_all_custom_fields():
    """获取所有自定义字段定义列表（用户+房间）"""
    try:
        all_fields = get_all_custom_field_definitions()
        return jsonify({"success": True, "data": all_fields})
    except Exception as e:
        logging.error(f"获取所有自定义字段定义失败: {str(e)}")
        return jsonify({"success": False, "message": f"获取自定义字段定义失败: {str(e)}"}), 500


@system_config_bp.route('/api/custom-fields/save-all', methods=['POST'])
@login_required
@require_permission('system_settings.manage')
def save_all_custom_fields():
    """保存所有自定义字段定义（按module拆分保存）"""
    try:
        data = request.get_json()
        fields = data.get('fields', [])

        if not isinstance(fields, list):
            return jsonify({"success": False, "message": "字段定义必须为数组"}), 400

        # 校验每个字段定义
        field_keys = set()
        for i, field in enumerate(fields):
            if not isinstance(field, dict):
                return jsonify({"success": False, "message": f"第{i+1}个字段定义格式错误"}), 400

            field_key = field.get('field_key', '').strip()
            if not field_key:
                return jsonify({"success": False, "message": f"第{i+1}个字段的key不能为空"}), 400

            if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', field_key):
                return jsonify({"success": False, "message": f"字段key '{field_key}' 格式错误，只能以字母开头，包含字母、数字和下划线"}), 400

            # module校验
            module = field.get('module', '')
            if module not in ('user', 'room'):
                return jsonify({"success": False, "message": f"字段 '{field_key}' 的使用模块必须为'用户'或'房间'"}), 400

            # 同一模块内key唯一性
            module_key = f"{module}:{field_key}"
            if module_key in field_keys:
                return jsonify({"success": False, "message": f"模块'{module}'中字段key '{field_key}' 重复"}), 400
            field_keys.add(module_key)

            label = field.get('label', '').strip()
            if not label:
                return jsonify({"success": False, "message": f"字段 '{field_key}' 的标签不能为空"}), 400

            field_type = field.get('type', 'text')
            if field_type not in ('text', 'number', 'select', 'date', 'checkbox', 'textarea'):
                return jsonify({"success": False, "message": f"字段 '{field_key}' 的类型不支持"}), 400

            if field_type == 'select':
                options = field.get('options', [])
                if not options or not isinstance(options, list):
                    return jsonify({"success": False, "message": f"字段 '{field_key}' 为select类型，必须提供选项列表"}), 400

        # 按module拆分，并移除module属性（避免冗余存储）
        user_fields = [{k: v for k, v in f.items() if k != 'module'} for f in fields if f.get('module') == 'user']
        room_fields = [{k: v for k, v in f.items() if k != 'module'} for f in fields if f.get('module') == 'room']

        # 分别保存
        success_user = save_custom_field_definitions('user', user_fields, current_user.id)
        success_room = save_custom_field_definitions('room', room_fields, current_user.id)

        if success_user and success_room:
            log_operation(user_id=current_user.id, module='system', operation_type='update',
                         action="保存所有自定义字段定义", result="成功")
            return jsonify({"success": True, "message": "自定义字段定义保存成功"})
        else:
            return jsonify({"success": False, "message": "保存自定义字段定义失败"}), 500

    except Exception as e:
        logging.error(f"保存所有自定义字段定义失败: {str(e)}")
        return jsonify({"success": False, "message": f"保存自定义字段定义失败: {str(e)}"}), 500