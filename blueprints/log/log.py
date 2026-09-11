from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from datetime import datetime, timezone, timedelta
from models.log.log import OperationLog  # 已扩展的模型
import logging
from flask_login import login_required, current_user
from utils.log import MODULE_MAP, OPERATION_TYPE_MAP  # 导入字典
from utils.log import log_operation

from utils.auth import require_permission

# 创建蓝图（原有内容不变）
log_bp = Blueprint('log', __name__, url_prefix='/log')

# 页面模板文件
@log_bp.route('/log', methods=['GET'])
@login_required
@require_permission('log.view')
def log():
    # 获取筛选参数
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    user_id = request.args.get('user_id')
    module = request.args.get('module')
    operation_type = request.args.get('operation_type')
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # 设置默认时间范围（开始时间为7天前，结束时间为今天）
    if not start_time:
        # 默认开始时间：7天前
        start_date = datetime.now().date() - timedelta(days=30)
        start_time = start_date.strftime('%Y-%m-%d')
    
    if not end_time:
        # 默认结束时间：今天
        end_time = datetime.now().date().strftime('%Y-%m-%d')
    
    # 构建查询条件
    query = OperationLog.query
    
    # 按日期筛选
    if start_time:
        try:
            start_date = datetime.strptime(start_time, '%Y-%m-%d')
            query = query.filter(OperationLog.operate_time >= start_date)
        except ValueError:
            flash('开始日期格式错误，请使用YYYY-MM-DD格式', 'error')
    
    if end_time:
        try:
            # 结束日期加一天，包含当天的所有时间
            end_date = datetime.strptime(end_time, '%Y-%m-%d')
            end_date = end_date.replace(hour=23, minute=59, second=59)
            query = query.filter(OperationLog.operate_time <= end_date)
        except ValueError:
            flash('结束日期格式错误，请使用YYYY-MM-DD格式', 'error')
    
    # 按用户ID筛选
    if user_id:
        query = query.filter(OperationLog.user_id == user_id)
    
    # 按模块筛选
    if module:
        query = query.filter(OperationLog.module == module)
    
    # 按操作类型筛选
    if operation_type:
        query = query.filter(OperationLog.operation_type == operation_type)
    
    # 按时间倒序排序
    query = query.order_by(OperationLog.operate_time.desc())
    
    # 分页查询
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    logs = pagination.items
    
    # 处理日志数据，添加模块和操作类型的中文名称
    processed_logs = []
    for log_entry in logs:
        # 获取模块中文名称
        module_name = MODULE_MAP.get(log_entry.module, '未知模块')
        
        # 获取操作类型中文名称
        operation_name = OPERATION_TYPE_MAP.get((log_entry.module, log_entry.operation_type), '未知操作')
        
        # 添加处理后的日志到列表
        processed_logs.append({
            'id': log_entry.id,
            'operate_time': log_entry.operate_time,  # 使用与数据库模型一致的字段名
            'user_id': log_entry.user_id,
            'module': module_name,  # 使用中文模块名称（根据utils/log.py中的映射）
            'operation_type': operation_name,  # 使用中文操作类型名称（根据utils/log.py中的映射）
            'action': log_entry.action,
            'ip_address': log_entry.ip_address,
            'result': log_entry.operation_result
        })
    
    # 记录访问日志
    #log_operation(
    #    user_id=current_user.id,
    #    module='system',
    #    operation_type='records',
    #    action="访问系统日志页面",
    #    result="成功"
    #)

    # 传递所有需要的数据到模板
    return render_template('log/log.html',
                           title="系统日志",
                           logs=processed_logs,
                           pagination=pagination,
                           MODULE_MAP=MODULE_MAP,
                           OPERATION_TYPE_MAP=OPERATION_TYPE_MAP,
                           # 当前筛选参数
                           start_time=start_time,
                           end_time=end_time,
                           user_id=user_id,
                           module=module,
                           operation_type=operation_type,
                           per_page=per_page
                           )

