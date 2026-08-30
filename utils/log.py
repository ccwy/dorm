import sys
import os
import logging
import json
from logging.handlers import RotatingFileHandler
from flask import request
import datetime

# 模块名称映射 (module -> 中文)
MODULE_MAP = {
    'room': '房间管理',
    'dorm': '宿舍管理',
    'system': '系统设置',
    'user': '用户管理',
    'utility': '水电费管理',
    'login': '登录',
    'feesubsidy': '补贴管理',
    'ticket': '留言管理',
    'todo': '待办事项管理',
    'asset': '固定资产管理',
    'department': '部门管理',
    'other': '其他操作',
    # 低值易耗品管理模块
    'supply': '低值易耗品管理',
    'stock_in': '入库管理',
    'stock_out': '出库管理',
    'storage_location': '存放位置管理',
    'supplier': '供应商管理',
    'supply_item': '物品管理',
    'supply_inventory': '盘点管理',
    'supply_stock_detail': '库存明细',
    'supply_stock_record': '库存记录',
    'contract': '合同管理',
    'default': '其他模块'  # 默认值
}

# 操作类型映射 ((module, operation_type) -> 中文)
OPERATION_TYPE_MAP = {
    # 房间管理模块
    ('room', 'room_add'): '添加房间',
    ('room', 'room_edit'): '编辑房间',
    ('room', 'room_delete'): '删除房间',
    ('room', 'room_update'): '房间更新',
    ('room', 'batch_import_export'): '导入导出',
    ('room', 'room_api'): '调用接口',
    ('room', 'room_view'): '查看房间',
    ('room', 'records'): '访问页面',
    ('room', 'upload_photo'): '上传照片',
    ('room', 'delete_photo'): '删除照片',

    # 宿舍管理模块（示例扩展）
    ('dorm', 'records'): '访问页面',
    ('dorm', 'allocate'): '分配宿舍',
    ('dorm', 'checkout'): '退宿处理',
    ('dorm', 'change'): '更换宿舍',
    ('dorm', 'batch_import_export'): '导入导出',
    # 系统模块（示例扩展）
    ('system', 'config_update'): '更新配置',
    ('system', 'restore_backup'): '恢复备份',
    ('system', 'delete_backup'): '删除备份',
    ('system', 'list_backups'): '备份列表',
    ('system', 'create_backup'): '新建备份',
    ('system', 'initialize'): '初始化',
    ('system', 'normalized_category'): '获取配置',
    ('system', 'module'): '获取模块',
    ('system', 'records'): '访问页面',
    ('system', 'system_api'): '调用接口',
    # 用户管理模块
    ('user', 'user_api'): '调用接口',
    ('user', 'records'): '访问页面',
    ('user', 'batch_import_export'): '导入导出',
    ('user', 'user_add'): '增加用户',
    ('user', 'user_edit'): '编辑用户',
    ('user', 'user_delete'): '删除用户',
    ('user', 'user_view'): '查看用户',
    # 水电费管理模块
    ('utility', 'batch_import_export'): '导入导出',
    ('utility', 'meter'): '抄表记录',
    ('utility', 'delete'): '删除',
    ('utility', 'utility_api'): '调用接口',
    ('utility', 'bill_update'): '费用核算',
    ('utility', 'checkout_fee'): '退宿费用',
    ('utility', 'occupant_fee'): '在住费用',
    ('utility', 'records'): '访问页面',
    #补贴管理
    ('feesubsidy', 'records'): '访问页面',
    ('feesubsidy', 'feesub_api'): '调用接口页面',
    ('feesubsidy', 'feesub_add'): '增加补贴',
    ('feesubsidy', 'delete'): '禁用补贴',
    ('feesubsidy', 'batch_import_export'): '导入导出',
    # 登录管理
    ('login', 'login'): '登录',
    ('login', 'logout'): '登出',

    # 留言管理模块
    ('ticket', 'records'): '访问页面',
    ('ticket', 'create'): '创建留言',
    ('ticket', 'reply'): '回复留言',
    ('ticket', 'close'): '关闭留言',
    ('ticket', 'delete'): '删除留言',
    ('ticket', 'upload_media'): '上传媒体',
    ('ticket', 'delete_media'): '删除媒体',
    
    # 待办事项管理模块
    ('todo', 'records'): '访问页面',
    ('todo', 'create'): '创建待办事项',
    ('todo', 'update'): '更新待办事项',
    ('todo', 'delete'): '删除待办事项',
    ('todo', 'batch_import_export'): '导入导出',
    # 固定资产管理模块
    ('asset', 'asset_add'): '新增资产',
    ('asset', 'asset_edit'): '编辑资产',
    ('asset', 'asset_delete'): '删除资产',
    ('asset', 'asset_batch_delete'): '批量删除资产',
    ('asset', 'asset_transfer'): '资产转移',
    ('asset', 'asset_scrap'): '资产报废',
    ('asset', 'asset_sell'): '资产出售',
    ('asset', 'asset_inventory_create'): '创建盘点',
    ('asset', 'asset_inventory_check'): '执行盘点',
    ('asset', 'asset_inventory_complete'): '完成盘点',
    ('asset', 'batch_import_export'): '导入导出',
    ('asset', 'asset_api'): '调用接口',
    ('asset', 'asset_view'): '查看资产',
    ('asset', 'upload_photo'): '上传照片',
    ('asset', 'delete_photo'): '删除照片',
    ('asset', 'records'): '访问页面',
    # 部门管理模块
    ('department', 'department_add'): '新增部门',
    ('department', 'department_edit'): '编辑部门',
    ('department', 'department_delete'): '删除部门',
    ('department', 'batch_import_export'): '导入导出',
    # 合同管理模块
    ('contract', 'records'): '访问页面',
    ('contract', 'contract_add'): '新增合同',
    ('contract', 'contract_edit'): '编辑合同',
    ('contract', 'contract_delete'): '删除合同',
    ('contract', 'contract_batch_delete'): '批量删除合同',
    ('contract', 'status_change'): '状态变更',
    ('contract', 'upload_attachment'): '上传附件',
    ('contract', 'delete_attachment'): '删除附件',
    ('contract', 'download_attachment'): '下载附件',
    ('contract', 'contract_renew'): '续签合同',
    ('contract', 'api_query'): '调用接口',
    ('contract', 'batch_import_export'): '导入导出',

    # 其他操作模块
    ('other', 'records'): '访问页面',

    # 低值易耗品管理 - 总入口
    ('supply', 'index'): '访问首页',
    ('supply', 'records'): '访问页面',

    # 入库管理模块
    ('stock_in', 'records'): '访问页面',
    ('stock_in', 'stock_in_add'): '新增入库单',
    ('stock_in', 'stock_in_edit'): '编辑入库单',
    ('stock_in', 'stock_in_delete'): '删除入库单',
    ('stock_in', 'stock_in_batch_delete'): '批量删除入库单',
    ('stock_in', 'stock_in_approve'): '审核入库单',
    ('stock_in', 'stock_in_unapprove'): '反审核入库单',
    ('stock_in', 'stock_in_cancel'): '作废入库单',
    ('stock_in', 'api_query'): '调用接口',
    ('stock_in', 'batch_import_export'): '导入导出',

    # 出库管理模块
    ('stock_out', 'records'): '访问页面',
    ('stock_out', 'stock_out_add'): '新增出库单',
    ('stock_out', 'stock_out_edit'): '编辑出库单',
    ('stock_out', 'stock_out_delete'): '删除出库单',
    ('stock_out', 'stock_out_batch_delete'): '批量删除出库单',
    ('stock_out', 'stock_out_approve'): '审核出库单',
    ('stock_out', 'stock_out_unapprove'): '反审核出库单',
    ('stock_out', 'stock_out_cancel'): '作出库单',
    ('stock_out', 'api_query'): '调用接口',
    ('stock_out', 'batch_import_export'): '导入导出',

    # 存放位置管理模块
    ('storage_location', 'records'): '访问页面',
    ('storage_location', 'storage_location_add'): '新增存放位置',
    ('storage_location', 'storage_location_edit'): '编辑存放位置',
    ('storage_location', 'storage_location_delete'): '删除存放位置',
    ('storage_location', 'storage_location_batch_delete'): '批量删除存放位置',
    ('storage_location', 'api_query'): '调用接口',
    ('storage_location', 'batch_import_export'): '导入导出',

    # 供应商管理模块
    ('supplier', 'records'): '访问页面',
    ('supplier', 'supplier_add'): '新增供应商',
    ('supplier', 'supplier_edit'): '编辑供应商',
    ('supplier', 'supplier_delete'): '删除供应商',
    ('supplier', 'supplier_batch_delete'): '批量删除供应商',
    ('supplier', 'supplier_toggle_status'): '切换供应商状态',
    ('supplier', 'api_query'): '调用接口',
    ('supplier', 'quick_create'): '快速创建供应商',
    ('supplier', 'batch_import_export'): '导入导出',

    # 物品管理模块
    ('supply_item', 'records'): '访问页面',
    ('supply_item', 'supply_item_add'): '新增物品',
    ('supply_item', 'supply_item_edit'): '编辑物品',
    ('supply_item', 'supply_item_delete'): '删除物品',
    ('supply_item', 'supply_item_batch_delete'): '批量删除物品',
    ('supply_item', 'supply_item_recalculate_stock'): '重新计算库存',
    ('supply_item', 'api_query'): '调用接口',
    ('supply_item', 'batch_import_export'): '导入导出',

    # 盘点管理模块
    ('supply_inventory', 'records'): '访问页面',
    ('supply_inventory', 'inventory_create'): '创建盘点',
    ('supply_inventory', 'inventory_check'): '执行盘点',
    ('supply_inventory', 'inventory_complete'): '完成盘点',
    ('supply_inventory', 'inventory_delete'): '删除盘点',
    ('supply_inventory', 'api_query'): '调用接口',
    ('supply_inventory', 'batch_import_export'): '导入导出',

    # 库存明细模块
    ('supply_stock_detail', 'records'): '访问页面',
    ('supply_stock_detail', 'update'): '更新库存',
    ('supply_stock_detail', 'api_query'): '调用接口',
    ('supply_stock_detail', 'batch_import_export'): '导入导出',

    # 库存记录模块
    ('supply_stock_record', 'records'): '访问页面',
    ('supply_stock_record', 'api_query'): '调用接口',

    # 默认值
    ('default', 'default'): '未知操作',
}

# 获取日志目录 - 严格遵循项目data文件夹使用规范
def get_log_directory():
    # 检查是否在Docker环境中
    is_docker = os.environ.get('DOCKER_ENV') == 'true'
    
    if is_docker:
        # Docker环境 - 使用简化的外部数据卷路径
        log_dir = '/data/logs'
    else:
        # 非Docker环境
        if getattr(sys, 'frozen', False):
            # 打包环境
            app_dir = os.path.dirname(sys.executable)
        else:
            # 开发环境
            current_file_dir = os.path.abspath(os.path.dirname(__file__))
            app_dir = os.path.abspath(os.path.join(current_file_dir, os.pardir))
        
        # 日志文件始终存储在data/logs文件夹
        log_dir = os.path.join(app_dir, 'data', 'logs')
    
    # 确保日志目录存在
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
            print(f"创建日志目录: {log_dir}")
        except OSError as e:
            print(f"创建日志目录失败: {str(e)}", file=sys.stderr)
    
    return log_dir

# 设置文件日志
def setup_file_logging():
    # 获取日志目录
    log_dir = get_log_directory()
    
    # 创建主日志文件路径
    app_log_path = os.path.join(log_dir, 'app.log')
    error_log_path = os.path.join(log_dir, 'error.log')
    
    # 获取根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # 清除现有处理器
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 创建格式化器
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 创建主日志处理器（全部日志）
    app_handler = RotatingFileHandler(
        app_log_path, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
    )
    # 设置日志处理器级别
    app_handler.setLevel(logging.DEBUG)  # 修改为DEBUG级别，记录所有日志
    app_handler.setFormatter(formatter)
    root_logger.addHandler(app_handler)
    
    # 创建错误日志处理器（仅错误日志）
    error_handler = RotatingFileHandler(
        error_log_path, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)  # 保持错误级别
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)  # 修改为DEBUG级别，在控制台显示所有日志
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # 设置根日志记录器级别
    root_logger.setLevel(logging.DEBUG)  # 确保根日志级别也是DEBUG

    # 记录日志初始化信息
    logging.info(f"日志系统初始化完成 - 全部日志: {app_log_path}")
    logging.info(f"日志系统初始化完成 - 错误日志: {error_log_path}")
    
    return root_logger

# 获取日志记录器
def get_logger(name=None):
    return logging.getLogger(name)

# 避免循环导入，后面再导入db和OperationLog
def log_operation(
    user_id, 
    action, 
    result="成功", 
    module="", 
    operation_type="", 
    ip_address=None
):
    """
    记录操作日志，支持所有OperationLog模型字段
    
    :param user_id: 操作人ID
    :param action: 操作内容描述
    :param result: 操作结果，默认为"成功"
    :param module: 模块标识（如dorm-宿舍模块），默认为空
    :param operation_type: 操作类型（如allocate-分配宿舍），默认为空
    :param ip_address: 操作IP地址，默认自动获取
    :return: 是否记录成功
    """
    
    # 同时记录到文件日志
    logger = get_logger('operation')
    logger.info(f"用户[{user_id}] - 模块[{module}] - 操作[{operation_type}] - {action} - 结果[{result}]")
    
    try:
        # 在函数内部导入，避免循环导入
        from datetime import datetime
        from utils.db import db
        from models.log import OperationLog
        
        # 自动获取IP地址（如果未提供）
        if ip_address is None:
            ip_address = request.headers.get('X-Real-IP', request.remote_addr) or ""

        # 处理user_id为None的情况，设置为0表示未知用户
        user_id = user_id if user_id is not None else 0

        # 创建日志记录，匹配OperationLog模型所有字段
        new_log = OperationLog(
            user_id=user_id,
            action=action,
            ip_address=ip_address,
            operation_result=result,
            operate_time=datetime.now(),
            module=module,
            operation_type=operation_type
        )
        
        db.session.add(new_log)
        db.session.commit()
        return True  # 记录成功
    except Exception as e:
        # 错误处理
        logger.error(f"错误类型: {type(e).__name__}")
        
        try:
            from utils.db import db
            db.session.rollback()
        except:
            pass
        
        return False  # 记录失败
    