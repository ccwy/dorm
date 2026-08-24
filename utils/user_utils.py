import time
import random
from models.user import User
import datetime
from typing import Any, Dict, Set, Optional
from sqlalchemy.inspection import inspect
import logging

def get_user_model_fields() -> Dict[str, str]:
    """获取User模型的字段映射（字段名→显示名）"""
    base_fields = {
        'id': '用户ID',
        'student_id': '工号',
        'name': '姓名',
        'username': '用户名',
        'gender': '性别',
        'category': '人员类别',
        'id_card': '身份证号码',
        'id_address': '身份证地址',
        'lodging_address': '外宿地址',
        'phone': '联系电话',
        'company': '公司',
        'department': '部门',
        'position': '职位',
        'emergency_contact': '紧急联系人',
        'emergency_phone': '紧急联系人电话',
        'remarks': '备注',
        'status': '状态',
        'is_active': '是否激活账号',
        'role': '角色',
        'is_banned': '是否允许登录',
        'hire_date': '入职日期',
        'created_at': '创建时间',
        'updated_at': '更新时间',
        # 基本信息字段
        'birth_date': '出生日期',
        'age': '年龄',
        'native_place': '籍贯',
        'ethnicity': '民族',
        'marital_status': '婚姻状态',
        # 补贴相关字段
        'lodging_allowance': '外宿补贴',
        'reduction_fee': '住宿补贴',
        # 导出用住宿相关字段（实际值从Dorm模型获取）
        'is_boarding': '是否住宿',
        'room_number': '房间号',
        'checkin_date': '入住日期',
        'days_stayed': '已住天数',
        'password': '密码'
    }
    inspector = inspect(User)
    model_columns = [col.key for col in inspector.columns]
    
    # 保留模型中实际存在的字段以及导出用的住宿相关字段（排除密码）
    # 导出用的住宿相关字段：is_boarding, room_number, checkin_date, checkout_date, days_stayed
    export_only_fields = {'is_boarding', 'room_number', 'checkin_date', 'checkout_date', 'days_stayed'}
    model_fields = {field: display_name for field, display_name in base_fields.items() 
                   if field in model_columns or field == 'password' or field in export_only_fields}
    return model_fields
    

def get_importable_fields() -> Dict[str, str]:
    """获取可导入的字段（排除系统自动生成的字段）"""
    all_fields = get_user_model_fields()
    # 系统自动生成的字段 + 导出专用字段（不允许导入）
    non_importable = [
        'id', 'created_at', 'updated_at', 
        'age', 'birth_date', 'native_place', 'lodging_allowance', 'reduction_fee',
        'is_boarding', 'room_number', 'checkin_date', 'checkout_date', 'days_stayed'  # 导出专用字段
    ]
    importable = {k: v for k, v in all_fields.items() if k not in non_importable}

    if 'role' not in importable:
        importable['role'] = '角色'
    return importable
    
def process_field_value(field_name: str, value: Any) -> str:
    """处理字段值（转换日期、布尔等类型为字符串）"""
    if value is None:
        return ""
        
    # 日期类型处理
    if isinstance(value, (datetime.date, datetime.datetime)):
        if isinstance(value, datetime.datetime):
            return value.strftime('%Y-%m-%d %H:%M:%S')
        return value.strftime('%Y-%m-%d')
    
    # 布尔字段处理（是否住宿）
    if field_name == 'is_boarding':
        return '是' if value else '否'
    

    # 通用布尔值处理
    if isinstance(value, bool):
        return '是' if value else '否'
        
    # 字符串处理
    if isinstance(value, str):
        return value.strip()
        
    return str(value)

# 修改：姓名为空时使用"user+时间戳+随机数"确保唯一
def generate_username(name: str, existing_usernames: Set[str], max_attempts: int = 1000) -> str:
    """
    生成唯一用户名，默认使用姓名，若重复则自动添加数字后缀；
    姓名为空时使用"user+时间戳+随机数"确保唯一性
    
    参数:
        name: 姓名
        existing_usernames: 已存在的用户名集合（蓝图层传递，已过滤自身）
        max_attempts: 最大尝试次数
        
    返回:
        str: 唯一的用户名（如"张三"、"张三1"、"user1627834592123"等）
    """
    # 处理空姓名情况：使用user+毫秒级时间戳+3位随机数
    if not name or not name.strip():
        # 生成基于时间的唯一标识（毫秒级时间戳+3位随机数）
        timestamp = int(time.time() * 1000)  # 毫秒级时间戳
        random_suffix = random.randint(100, 999)  # 3位随机数
        base_username = f"user{timestamp}{random_suffix}"
        
        # 检查是否已存在
        if base_username not in existing_usernames:
            return base_username
            
        # 若冲突，尝试增加随机数
        for _ in range(max_attempts):
            random_suffix = random.randint(100, 999)
            candidate = f"user{timestamp}{random_suffix}"
            if candidate not in existing_usernames:
                return candidate
                
        # 多次尝试失败
        return None
    
    # 姓名非空时：使用姓名+数字后缀
    base_username = name.strip()
    
    # 检查基础用户名是否已存在
    if base_username not in existing_usernames:
        return base_username
    
    # 若存在，尝试添加数字后缀（从1开始递增）
    for suffix in range(1, max_attempts + 1):
        candidate_username = f"{base_username}{suffix}"
        if candidate_username not in existing_usernames:
            return candidate_username
    
    # 达到最大尝试次数仍失败
    return None

def generate_student_id(existing_ids: Set[str], max_attempts: int = 100) -> str:
    """
    生成唯一工号（毫秒级时间戳+5位随机数）
    
    参数:
        existing_ids: 已存在的工号集合（蓝图层传递，用于内存比对）
        max_attempts: 最大尝试次数
        
    返回:
        str: 唯一的工号，或None（多次尝试失败时）
    """
    for _ in range(max_attempts):
        now = datetime.datetime.now()
        date_str = now.strftime("%Y%m%d")
        random_str = str(random.randint(1000, 9999))  # 4位随机数
        student_id = f"{date_str}{random_str}"
        
        if student_id not in existing_ids:
            return student_id
    
    # 达到最大尝试次数仍失败
    return None
    