from flask import Blueprint, request, render_template, redirect, url_for, flash, jsonify
from models.todo import Todo
from models.todo_progress import TodoProgress
from models.system_config import SystemConfig
from utils.db import db
from utils.log import log_operation
from flask_login import login_required, current_user
import logging
from datetime import datetime

# 创建待办事项蓝图
todo_bp = Blueprint('todo', __name__, url_prefix='/todo')
from . import todo_photo  # 包含新的在住人员查询API
from . import todo_export  # 包含新的在住人员查询API

@todo_bp.route('/')
@login_required
def index():
    """待办事项列表页面"""
    # 获取查询参数
    search = request.args.get('search', '').strip()
    status = request.args.get('status', '进行中').strip()
    priority = request.args.get('priority', '').strip()
    category = request.args.get('category', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)

    
    # 构建查询
    query = Todo.query
    
    # 根据用户权限过滤待办事项
    if not current_user.is_super_admin():
        # 非超级管理员只能查看自己创建的待办事项
        query = query.filter(Todo.created_by == current_user.id)
    
    # 应用搜索条件
    if search:
        query = query.filter(
            Todo.title.like(f'%{search}%') |
            Todo.description.like(f'%{search}%')
        )
    
    # 应用状态过滤
    if status:
        query = query.filter_by(status=status)
    
    # 应用优先级过滤
    if priority:
        query = query.filter_by(priority=priority)
    
    # 应用分类过滤
    if category:
        query = query.filter_by(category=category)
    
    # 分页
    pagination = query.order_by(Todo.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    todos = pagination.items
    
    # 获取所有状态用于筛选
    statuses = db.session.query(Todo.status).distinct().all()
    status_options = [status[0] for status in statuses]
    
    # 获取所有优先级用于筛选
    priorities = db.session.query(Todo.priority).distinct().all()
    priority_options = [p[0] for p in priorities if p[0]]
    
    # 获取所有分类用于筛选
    categories = db.session.query(Todo.category).distinct().all()
    category_options = [c[0] for c in categories if c[0]]
    
    # 记录访问日志
    log_operation(
        user_id=current_user.id,
        module='todo',
        operation_type='records',
        action="查看待办事项列表",
        result="成功"
    )
    
    return render_template('todo_manage/todo_index.html',
                           title="待办事项管理",
                           todos=todos,
                           pagination=pagination,
                           page=page,
                           per_page=per_page,
                           search=search,
                           status=status,
                           status_options=status_options,
                           priority=priority,
                           priority_options=priority_options,
                           category=category,
                           category_options=category_options)

@todo_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add():
    """添加待办事项"""
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            description = request.form.get('description')
            status = request.form.get('status')
            priority = request.form.get('priority')
            start_time_str = request.form.get('start_time')
            planned_end_time_str = request.form.get('planned_end_time')
            assignee = request.form.get('assignee')
            progress = request.form.get('progress', '0')
            
            # 验证必填字段
            if not title:
                flash('标题不能为空', 'danger')
                logging.error("添加待办事项失败: 标题不能为空")
                return redirect(url_for('todo.add'))
            
            # 处理日期时间
            start_time = None
            if start_time_str:
                try:
                    start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    flash('开始时间格式不正确', 'danger')
                    logging.error("添加待办事项失败: 开始时间格式不正确")
                    return redirect(url_for('todo.add'))
            
            planned_end_time = None
            if planned_end_time_str:
                try:
                    planned_end_time = datetime.strptime(planned_end_time_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    flash('计划完成时间格式不正确', 'danger')
                    logging.error("添加待办事项失败: 计划完成时间格式不正确")
                    return redirect(url_for('todo.add'))
            
            # 创建待办事项
            # 获取表单中的分类值
            category = request.form.get('category')
            
            todo = Todo.create(
                title=title,
                description=description,
                status=status,
                priority=priority,
                category=category,
                created_by=current_user.id,
                start_time=start_time,
                planned_end_time=planned_end_time,
                assignee=assignee,
                progress=int(progress)
            )
            
            # 记录操作日志
            log_operation(
                user_id=current_user.id,
                module='todo',
                operation_type='create',
                action=f"创建待办事项：{title}",
                result="成功"
            )
            
            flash(f'待办事项创建成功，ID: {todo.id}', 'success')
            logging.info(f"待办事项创建成功，ID: {todo.id}")
            # 如果是连续保存，则重定向回添加页面
            if request.form.get('continuous') == 'true':
                return redirect(url_for('todo.add'))
            # 否则重定向到列表页
            return redirect(url_for('todo.index'))
        except Exception as e:
            logging.error(f"创建待办事项失败: {str(e)}")
            log_operation(
                user_id=current_user.id,
                module='todo',
                operation_type='create',
                action="创建待办事项失败",
                result="失败"
            )
            flash(f'创建失败: {str(e)}', 'danger')
            return redirect(url_for('todo.add'))
    
    # 获取待办事项分类选项
    todo_categories = SystemConfig.get_config_value('TODO_CATEGORIES', [])
    return render_template('todo_manage/todo_add.html', title="添加待办事项", current_user=current_user, todo_categories=todo_categories)

@todo_bp.route('/edit/<int:todo_id>', methods=['GET', 'POST'])
@login_required
def edit(todo_id):
    """编辑待办事项"""
    todo = Todo.get_by_id(todo_id)
    
    if not todo:
        flash('待办事项不存在', 'danger')
        logging.error(f"编辑待办事项失败: 待办事项ID {todo_id} 不存在")
        return redirect(url_for('todo.index'))
    
    # 检查权限：非超级管理员只能编辑自己创建的待办事项
    if not current_user.is_super_admin() and todo.created_by != current_user.id:
        flash('您没有权限编辑此待办事项', 'danger')
        logging.error(f"编辑待办事项失败: 用户{current_user.id}没有权限编辑待办事项ID {todo_id}")
        log_operation(
            user_id=current_user.id,
            module='todo',
            operation_type='update',
            action=f"尝试编辑待办事项但无权限待办事项ID:  ({todo_id})",
            result="失败"
        )
        return redirect(url_for('todo.index'))
    
    if request.method == 'POST':
        try:
            title = request.form.get('title')
            description = request.form.get('description')
            status = request.form.get('status')
            priority = request.form.get('priority')
            start_time_str = request.form.get('start_time')
            planned_end_time_str = request.form.get('planned_end_time')
            actual_end_time_str = request.form.get('actual_end_time')
            assignee = request.form.get('assignee')
            
            # 验证必填字段
            if not title:
                flash('标题不能为空', 'danger')
                logging.error(f"编辑待办事项失败: 待办事项ID {todo_id} 标题不能为空")
                return redirect(url_for('todo.edit', todo_id=todo_id))
            
            # 处理日期时间
            start_time = None
            if start_time_str:
                try:
                    start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    flash('开始时间格式不正确', 'danger')
                    logging.error(f"编辑待办事项失败: 待办事项ID {todo_id} 开始时间格式不正确")
                    return redirect(url_for('todo.edit', todo_id=todo_id))
            
            planned_end_time = None
            if planned_end_time_str:
                try:
                    planned_end_time = datetime.strptime(planned_end_time_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    flash('计划完成时间格式不正确', 'danger')
                    logging.error(f"编辑待办事项失败: 待办事项ID {todo_id} 计划完成时间格式不正确")
                    return redirect(url_for('todo.edit', todo_id=todo_id))
            
            actual_end_time = None
            if actual_end_time_str:
                try:
                    actual_end_time = datetime.strptime(actual_end_time_str, '%Y-%m-%dT%H:%M')
                except ValueError:
                    flash('实际完成时间格式不正确', 'danger')
                    logging.error(f"编辑待办事项失败: 待办事项ID {todo_id} 实际完成时间格式不正确")
                    return redirect(url_for('todo.edit', todo_id=todo_id))
            
            # 获取表单中的分类值
            category = request.form.get('category')
            
            # 更新待办事项
            todo.update(
                title=title,
                description=description,
                status=status,
                priority=priority,
                category=category,
                start_time=start_time,
                planned_end_time=planned_end_time,
                actual_end_time=actual_end_time,
                assignee=assignee
            )
            
            # 当状态更新为已完成时，自动设置进度为100%并添加进度记录            
            if status == '已完成' and todo.progress != 100:                
                # 调用add_progress_record方法会自动在todo_progresses表中添加一条进度记录
                todo.add_progress_record(100, '待办事项已完成', current_user.id)
            
            # 记录操作日志
            log_operation(
                user_id=current_user.id,
                module='todo',
                operation_type='update',
                action=f"更新待办事项：{todo.title} (ID: {todo.id})",
                result="成功"
            )
            
            flash(f'待办事项更新成功，ID: {todo.id}', 'success')
            logging.info(f"待办事项更新成功，ID: {todo.id}")
            return redirect(url_for('todo.index'))
        except Exception as e:
            logging.error(f"更新待办事项失败: {str(e)}")
            log_operation(
                user_id=current_user.id,
                module='todo',
                operation_type='update',
                action=f"更新待办事项失败 (ID: {todo_id})",
                result="失败"
            )
            flash(f'更新失败: {str(e)}', 'danger')
            return redirect(url_for('todo.edit', todo_id=todo_id))
    
    # 格式化时间显示
    start_time_formatted = todo.start_time.strftime('%Y-%m-%dT%H:%M') if todo.start_time else ''
    planned_end_time_formatted = todo.planned_end_time.strftime('%Y-%m-%dT%H:%M') if todo.planned_end_time else ''
    actual_end_time_formatted = todo.actual_end_time.strftime('%Y-%m-%dT%H:%M') if todo.actual_end_time else ''
    
    # 获取待办事项分类选项
    todo_categories = SystemConfig.get_config_value('TODO_CATEGORIES', [])
    
    return render_template('todo_manage/todo_edit.html', 
                           title="编辑待办事项", 
                           todo=todo,
                           todo_categories=todo_categories,
                           start_time_formatted=start_time_formatted,
                           planned_end_time_formatted=planned_end_time_formatted,
                           actual_end_time_formatted=actual_end_time_formatted)

@todo_bp.route('/detail/<int:todo_id>')
@login_required
def detail(todo_id):
    """查看待办事项详情"""
    todo = Todo.get_by_id(todo_id)
    
    if not todo:
        flash('待办事项不存在', 'danger')
        logging.error(f"查看待办事项详情失败: 待办事项ID {todo_id} 不存在")
        return redirect(url_for('todo.index'))
    
    # 检查权限：非超级管理员只能查看自己创建的待办事项
    if not current_user.is_super_admin() and todo.created_by != current_user.id:
        flash('您没有权限查看此待办事项', 'danger')
        logging.error(f"查看待办事项详情失败: 用户{current_user.id}没有权限查看待办事项ID {todo_id}")
        log_operation(
            user_id=current_user.id,
            module='todo',
            operation_type='records',
            action=f"尝试查看待办事项详情但无权限查看待办事项ID： ({todo_id})",
            result="失败"
        )
        return redirect(url_for('todo.index'))
    
    # 获取进度记录
    progresses = TodoProgress.get_by_todo_id(todo_id)
    
    # 获取媒体文件，添加错误处理
    try:
        from utils.todo_photo import TodoMediaManager
        media_files = TodoMediaManager.get_media_files(todo_id)
    except Exception as e:
        logging.error(f"获取待办事项媒体文件时发生错误: {str(e)}")
        media_files = []  # 即使出错也返回空列表，不影响页面加载
    
    # 记录访问日志
    log_operation(
        user_id=current_user.id,
        module='todo',
        operation_type='records',
        action=f"查看待办事项详情：{todo.title} (ID: {todo_id})",
        result="成功"
    )
    
    return render_template('todo_manage/todo_detail.html', 
                           title="待办事项详情", 
                           todo=todo,
                           progresses=progresses,
                           media_files=media_files)

@todo_bp.route('/delete/<int:todo_id>', methods=['POST'])
@login_required
def delete(todo_id):
    """删除待办事项"""
    try:
        todo = Todo.get_by_id(todo_id)
        
        if not todo:
            flash('待办事项不存在', 'danger')
            logging.error(f"删除待办事项失败: 待办事项ID {todo_id} 不存在")
            return redirect(url_for('todo.index'))
        
        # 检查权限：非超级管理员只能删除自己创建的待办事项
        if not current_user.is_super_admin() and todo.created_by != current_user.id:
            flash('您没有权限删除此待办事项', 'danger')
            logging.error(f"删除待办事项失败: 用户{current_user.id}没有权限删除待办事项ID {todo_id}")
            log_operation(
                user_id=current_user.id,
                module='todo',
                operation_type='delete',
                action=f"尝试删除待办事项但无权限删除待办事项ID： ({todo_id})",
                result="失败"
            )
            return redirect(url_for('todo.index'))
        
        # 记录要删除的待办事项标题
        todo_title = todo.title
        
        # 删除待办事项
        todo.delete()
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='todo',
            operation_type='delete',
            action=f"删除待办事项：{todo_title} (ID: {todo_id})",
            result="成功"
        )
        
        flash(f'待办事项已成功删除，ID: {todo_id}', 'success')
        logging.info(f"待办事项删除成功，ID: {todo_id}")
        return redirect(url_for('todo.index'))
    except Exception as e:
        logging.error(f"删除待办事项失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='todo',
            operation_type='delete',
            action=f"删除待办事项失败 (ID: {todo_id})",
            result="失败"
        )
        flash(f'删除失败: {str(e)}', 'danger')
        return redirect(url_for('todo.index'))

@todo_bp.route('/batch_delete', methods=['POST'])
@login_required
def batch_delete():
    """批量删除待办事项"""
    try:
        todo_ids = request.form.getlist('todo_ids[]')
        
        if not todo_ids:
            flash('请选择要删除的待办事项', 'danger')
            logging.error(f"批量删除待办事项失败: 未选择待办事项")
            return redirect(url_for('todo.index'))
        
        # 转换ID为整数
        valid_todo_ids = []
        for id_str in todo_ids:
            try:
                valid_todo_ids.append(int(id_str))
            except ValueError:
                continue
        
        if not valid_todo_ids:
            flash('没有有效的待办事项ID', 'danger')
            logging.error(f"批量删除待办事项失败: 未选择有效待办事项ID")
            return redirect(url_for('todo.index'))
        
        # 非超级管理员只能批量删除自己创建的待办事项
        if not current_user.is_super_admin():
            # 获取所有选中的待办事项
            todos = Todo.query.filter(Todo.id.in_(valid_todo_ids)).all()
            
            # 过滤出用户有权删除的待办事项
            allowed_todo_ids = [todo.id for todo in todos if todo.created_by == current_user.id]
            
            # 检查是否有无权删除的待办事项
            if len(allowed_todo_ids) != len(valid_todo_ids):
                flash('您只能删除自己创建的待办事项', 'danger')
                logging.error(f"批量删除待办事项失败: 用户{current_user.id}没有权限删除某些待办事项")
                log_operation(
                    user_id=current_user.id,
                    module='todo',
                    operation_type='delete',
                    action=f"尝试批量删除待办事项但无权限删除所有选中项",
                    result="失败"
                )
                return redirect(url_for('todo.index'))
            
            # 更新有效ID列表为用户有权删除的ID
            valid_todo_ids = allowed_todo_ids
        
        # 批量删除
        Todo.batch_delete(valid_todo_ids)
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='todo',
            operation_type='delete',
            action=f"批量删除待办事项，共{len(valid_todo_ids)}条",
            result="成功"
        )
        
        flash(f'已成功删除{len(valid_todo_ids)}条待办事项', 'success')
        logging.info(f"批量删除待办事项成功，共{len(valid_todo_ids)}条")
        return redirect(url_for('todo.index'))
    except Exception as e:
        logging.error(f"批量删除待办事项失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='todo',
            operation_type='delete',
            action=f"批量删除待办事项失败",
            result="失败"
        )
        flash(f'批量删除失败: {str(e)}', 'danger')
        return redirect(url_for('todo.index'))

@todo_bp.route('/delete_all', methods=['POST'])
@login_required
def delete_all():
    """删除所有待办事项"""
    try:
        # 只有超级管理员可以删除所有待办事项
        if not current_user.is_super_admin():
            flash('只有超级管理员可以执行此操作', 'danger')
            logging.error(f"删除所有待办事项失败: 用户{current_user.id}没有权限")
            log_operation(
                user_id=current_user.id,
                module='todo',
                operation_type='delete',
                action=f"尝试删除所有待办事项但无权限",
                result="失败"
            )
            return redirect(url_for('todo.index'))
        
        todos = Todo.get_all()
        
        if not todos:
            flash('没有待办事项可以删除', 'info')
            logging.info(f"删除所有待办事项失败: 没有待办事项可以删除")
            return redirect(url_for('todo.index'))
        
        # 获取所有待办事项ID
        todo_ids = [todo.id for todo in todos]
        
        # 批量删除
        Todo.batch_delete(todo_ids)
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='todo',
            operation_type='delete',
            action=f"删除所有待办事项，共{len(todo_ids)}条",
            result="成功"
        )
        
        flash(f'已成功删除所有{len(todo_ids)}条待办事项', 'success')
        logging.info(f"删除所有待办事项成功，共{len(todo_ids)}条")
        return redirect(url_for('todo.index'))
    except Exception as e:
        logging.error(f"删除所有待办事项失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='todo',
            operation_type='delete',
            action=f"删除所有待办事项失败",
            result="失败"
        )
        flash(f'删除失败: {str(e)}', 'danger')
        return redirect(url_for('todo.index'))

@todo_bp.route('/update_progress/<int:todo_id>', methods=['POST'])
@login_required
def update_progress(todo_id):
    """更新待办事项进度"""
    try:
        todo = Todo.get_by_id(todo_id)
        
        if not todo:
            flash('待办事项不存在', 'danger')
            logging.error(f"更新待办事项进度失败: 待办事项ID {todo_id} 不存在")
            return redirect(url_for('todo.index'))
        
        # 检查权限：非超级管理员只能更新自己创建的待办事项进度
        if not current_user.is_super_admin() and todo.created_by != current_user.id:
            flash('您没有权限更新此待办事项进度', 'danger')
            logging.error(f"更新待办事项进度失败: 用户{current_user.id}没有权限更新待办事项ID {todo_id}的进度")
            log_operation(
                user_id=current_user.id,
                module='todo',
                operation_type='update',
                action=f"尝试更新待办事项进度但无权限 (ID: {todo_id})",
                result="失败"
            )
            return redirect(url_for('todo.index'))
        
        progress_percent = request.form.get('progress_percent', type=int)
        completed_task = request.form.get('completed_task')
        
        # 验证参数
        if progress_percent is None or progress_percent < 0 or progress_percent > 100:
            flash('进度百分比必须在0-100之间', 'danger')
            logging.error(f"更新待办事项进度失败: 待办事项ID {todo_id} 进度百分比 {progress_percent} 无效")
            return redirect(url_for('todo.detail', todo_id=todo_id))
        
        if not completed_task:
            flash('完成任务描述不能为空', 'danger')
            logging.error(f"更新待办事项进度失败: 待办事项ID {todo_id} 完成任务描述为空")
            return redirect(url_for('todo.detail', todo_id=todo_id))
        
        # 添加进度记录
        todo.add_progress_record(progress_percent, completed_task, current_user.id)
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='todo',
            operation_type='update',
            action=f"更新待办事项进度：{todo.title} (ID: {todo_id})，进度：{progress_percent}%",
            result="成功"
        )
        
        flash(f'进度更新成功', 'success')
        logging.info(f"更新待办事项进度成功: 待办事项ID {todo_id}，进度：{progress_percent}%，完成任务：{completed_task}")
        return redirect(url_for('todo.detail', todo_id=todo_id))
    except Exception as e:
        logging.error(f"更新待办事项进度失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='todo',
            operation_type='update',
            action=f"更新待办事项进度失败 (ID: {todo_id})",
            result="失败"
        )
        flash(f'进度更新失败: {str(e)}', 'danger')
        return redirect(url_for('todo.detail', todo_id=todo_id))