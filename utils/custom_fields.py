"""
自定义字段工具模块
提供自定义字段的读取、解析、校验功能
"""
import json
import logging
from typing import List, Dict, Any, Optional
from models.system_config.system_config import SystemConfig
from utils.db import db


def cleanup_custom_field_from_models(category: str, field_key: str) -> int:
    """
    删除自定义字段定义后，同步清理模型中对应字段的值
    
    Args:
        category: 'user' 或 'room'
        field_key: 要清理的字段key
    
    Returns:
        清清理的记录数
    """
    try:
        if category == 'user':
            from models.user.user import User
            model_class = User
        elif category == 'room':
            from models.room.room import Room
            model_class = Room
        else:
            return 0
        
        # 查询所有有custom_fields数据的记录
        records = model_class.query.filter(
            model_class.custom_fields.isnot(None),
            model_class.custom_fields != ''
        ).all()
        
        cleaned_count = 0
        for record in records:
            custom_data = deserialize_custom_fields(record.custom_fields)
            if field_key in custom_data:
                del custom_data[field_key]
                record.custom_fields = serialize_custom_fields(custom_data)
                cleaned_count += 1
        
        if cleaned_count > 0:
            db.session.commit()
        
        return cleaned_count
    except Exception as e:
        db.session.rollback()
        logging.error(f"清理自定义字段值失败 ({category}/{field_key}): {e}")
        return 0


def get_custom_field_definitions(category: str) -> List[Dict[str, Any]]:
    """
    获取指定模块的自定义字段定义列表
    
    Args:
        category: 'user' 或 'room'
    
    Returns:
        自定义字段定义列表，每个定义包含:
        - field_key: 字段键名（唯一标识）
        - label: 显示名称
        - type: 字段类型 (text/number/select/date/textarea/checkbox)
        - options: 选项列表（仅select类型使用）
        - required: 是否必填
        - sort_order: 排序顺序
        - default_value: 默认值
    """
    prefix = category.split('.')[0].upper()
    config_key = f"{prefix}_CUSTOM_FIELDS"
    config_value = SystemConfig.get_config_value(config_key, '[]')
    
    try:
        if isinstance(config_value, str):
            fields = json.loads(config_value)
        else:
            fields = config_value if config_value else []
        
        # 按sort_order排序
        fields.sort(key=lambda x: x.get('sort_order', 999))
        return fields
    except (json.JSONDecodeError, TypeError) as e:
        logging.error(f"解析自定义字段配置失败 ({config_key}): {e}")
        return []


def parse_custom_fields_data(form_data, field_definitions: List[Dict]) -> Dict[str, Any]:
    """
    从表单数据中提取自定义字段值
    
    Args:
        form_data: request.form 对象
        field_definitions: 自定义字段定义列表
    
    Returns:
        自定义字段键值对字典
    """
    custom_data = {}
    for field_def in field_definitions:
        field_key = field_def.get('field_key', '')
        if not field_key:
            continue
        
        # 表单中自定义字段使用 custom_ 前缀避免与固定字段冲突
        form_key = f'custom_{field_key}'
        value = form_data.get(form_key, '').strip() if hasattr(form_data, 'get') else ''
        
        # 处理checkbox类型
        if field_def.get('type') == 'checkbox':
            value = 'true' if form_data.get(form_key) else 'false'
        
        # 处理number类型
        if field_def.get('type') == 'number' and value:
            try:
                value = str(float(value))
            except ValueError:
                value = ''
        
        custom_data[field_key] = value
    
    return custom_data


def validate_custom_fields(custom_data: Dict[str, Any], field_definitions: List[Dict]) -> List[str]:
    """
    校验自定义字段值
    
    Args:
        custom_data: 自定义字段键值对
        field_definitions: 自定义字段定义列表
    
    Returns:
        错误消息列表，空列表表示校验通过
    """
    errors = []
    for field_def in field_definitions:
        field_key = field_def.get('field_key', '')
        label = field_def.get('label', field_key)
        value = custom_data.get(field_key, '')
        
        # 必填校验（checkbox类型值为'false'时视为空值）
        effective_value = value
        if field_def.get('type') == 'checkbox' and value == 'false':
            effective_value = ''
        if field_def.get('required', False) and not effective_value:
            errors.append(f'{label}为必填项')
        
        # select类型选项校验
        if value and field_def.get('type') == 'select':
            options = field_def.get('options', [])
            if options and value not in options:
                errors.append(f'{label}的值不在有效选项中')
    
    return errors


def serialize_custom_fields(custom_data: Dict[str, Any]) -> str:
    """
    将自定义字段数据序列化为JSON字符串
    
    Args:
        custom_data: 自定义字段键值对
    
    Returns:
        JSON字符串
    """
    if not custom_data:
        return '{}'
    return json.dumps(custom_data, ensure_ascii=False)


def deserialize_custom_fields(json_str: str) -> Dict[str, Any]:
    """
    将JSON字符串反序列化为自定义字段数据
    
    Args:
        json_str: JSON字符串
    
    Returns:
        自定义字段键值对字典
    """
    if not json_str:
        return {}
    try:
        data = json.loads(json_str)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def get_custom_field_value(model_instance, field_key: str, default: Any = None) -> Any:
    """
    获取模型实例的自定义字段值
    
    Args:
        model_instance: User或Room模型实例
        field_key: 字段键名
        default: 默认值
    
    Returns:
        字段值
    """
    custom_data = deserialize_custom_fields(getattr(model_instance, 'custom_fields', None) or '')
    return custom_data.get(field_key, default)


def get_all_custom_field_definitions() -> List[Dict[str, Any]]:
    """
    获取所有模块的自定义字段定义列表（用户+房间）
    每个字段定义会增加一个 'module' 属性标识所属模块

    Returns:
        自定义字段定义列表，每个定义包含 module 属性 ('user' 或 'room')
    """
    all_fields = []
    for module in ('user', 'room'):
        fields = get_custom_field_definitions(module)
        for field in fields:
            field['module'] = module
        all_fields.extend(fields)

    # 按sort_order排序
    all_fields.sort(key=lambda x: x.get('sort_order', 999))
    return all_fields


def save_custom_field_definitions(category: str, fields: List[Dict], user_id: int = None) -> bool:
    """
    保存自定义字段定义
    
    Args:
        category: 'user' 或 'room'
        fields: 自定义字段定义列表
        user_id: 操作用户ID
    
    Returns:
        是否保存成功
    """
    prefix = category.split('.')[0].upper()
    config_key = f"{prefix}_CUSTOM_FIELDS"
    config_value = json.dumps(fields, ensure_ascii=False)
    
    try:
        config = SystemConfig.query.filter_by(config_key=config_key).first()
        if config:
            config.config_value = config_value
            config.updated_by = user_id
        else:
            config = SystemConfig(
                config_key=config_key,
                config_value=config_value,
                config_type='json',
                category=f'{category}.custom_field',
                description=f'{"用户" if prefix.lower() == "user" else "房间"}自定义字段定义',
                is_system=True,
                is_editable=True,
                sort_order=1,
                updated_by=user_id
            )
            db.session.add(config)
        
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logging.error(f"保存自定义字段定义失败: {e}")
        return False