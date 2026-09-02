from flask import request, send_file, jsonify
from models.todo import Todo
from models.todo_progress import TodoProgress
from utils.log import log_operation
from utils.auth import require_permission
from flask_login import login_required, current_user
import logging
from datetime import datetime
import io
from .todo import todo_bp  # 导入todo蓝图

@todo_bp.route('/excel', methods=['GET'])
@login_required
@require_permission('todo.export')
def export_excel():
    """导出待办事项为Excel文件"""
    import pandas as pd  # 延迟导入，避免启动时加载重型库
    try:
        # 获取时间范围参数
        start_date_str = request.args.get('start_date')
        end_date_str = request.args.get('end_date')
        
        # 处理日期参数
        start_date = None
        end_date = None
        
        if start_date_str:
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            except ValueError:
                logging.error(f"导出待办事项失败：开始日期格式不正确，应为YYYY-MM-DD，实际值：{start_date_str}")
                return jsonify({'success': False, 'message': '开始日期格式不正确，应为YYYY-MM-DD'}), 400
        
        if end_date_str:
            try:
                end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
                # 将结束日期设置为当天的23:59:59
                end_date = end_date.replace(hour=23, minute=59, second=59)
            except ValueError:
                logging.error(f"导出待办事项失败：结束日期格式不正确，应为YYYY-MM-DD，实际值：{end_date_str}")
                return jsonify({'success': False, 'message': '结束日期格式不正确，应为YYYY-MM-DD'}), 400
        
        # 根据用户权限确定查询范围
        if current_user.user_role and current_user.user_role.code == 'super_admin':
            # 超级管理员可以查询所有待办事项
            todos = Todo.search(start_date=start_date, end_date=end_date)
        else:
            # 非超级管理员只能查询自己创建的待办事项
            todos = Todo.query.filter_by(created_by=current_user.id)
            if start_date:
                todos = todos.filter(Todo.created_at >= start_date)
            if end_date:
                todos = todos.filter(Todo.created_at <= end_date)
            todos = todos.order_by(Todo.created_at.desc()).all()
        
        if not todos:
            logging.error(f"导出待办事项失败：没有找到符合条件的待办事项，开始日期：{start_date_str}，结束日期：{end_date_str}")
            return jsonify({'success': False, 'message': '没有找到符合条件的待办事项'}), 404
        
        # 准备导出数据
        data = []
        for todo in todos:
            # 获取进度记录
            progresses = TodoProgress.get_by_todo_id(todo.id)
            # 进度记录在同一行内编序号，使用换行符分隔
            progress_details = "".join([f"{index+1}. {p.completed_task}\n" for index, p in enumerate(progresses)]).rstrip('\n')
            
            # 格式化时间
            start_time_formatted = todo.start_time.strftime('%Y-%m-%d %H:%M:%S') if todo.start_time else ''
            planned_end_time_formatted = todo.planned_end_time.strftime('%Y-%m-%d %H:%M:%S') if todo.planned_end_time else ''
            actual_end_time_formatted = todo.actual_end_time.strftime('%Y-%m-%d %H:%M:%S') if todo.actual_end_time else ''
            created_at_formatted = todo.created_at.strftime('%Y-%m-%d %H:%M:%S')
            updated_at_formatted = todo.updated_at.strftime('%Y-%m-%d %H:%M:%S')
            
            data.append({
                'ID': todo.id,
                '标题': todo.title,
                '描述': todo.description,
                '状态': todo.status,
                '优先级': todo.priority if todo.priority else '',
                '分类': todo.category if todo.category else '',
                '负责人': todo.assignee if todo.assignee else '',
                '开始时间': start_time_formatted,
                '计划完成时间': planned_end_time_formatted,
                '实际完成时间': actual_end_time_formatted,
                '当前进度(%)': todo.progress,
                '创建时间': created_at_formatted,
                '更新时间': updated_at_formatted,
                '创建人ID': todo.created_by,
                '进度记录': progress_details
            })
        
        # 创建Excel文件
        df = pd.DataFrame(data)
        
        # 创建内存中的文件对象
        output = io.BytesIO()
        
        # 使用ExcelWriter写入Excel文件
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # 写入数据
            df.to_excel(writer, index=False, sheet_name='待办事项')
            
            # 获取工作表
            worksheet = writer.sheets['待办事项']
            
            # 设置列宽
            for col_num, col_name in enumerate(df.columns):
                max_width = max(len(str(row[col_num])) for row in df.itertuples(index=False)) + 2
                worksheet.set_column(col_num, col_num, min(max_width, 50))  # 最大列宽限制为50
        
        # 定位到文件开头
        output.seek(0)
        
        # 构建文件名
        time_range = ''
        if start_date and end_date:
            time_range = f"_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}"
        elif start_date:
            time_range = f"_{start_date.strftime('%Y%m%d')}_至今"
        elif end_date:
            time_range = f"_至今_{end_date.strftime('%Y%m%d')}"
        
        filename = f"待办事项数据导出{time_range}_{datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
        
        # 记录导出日志
        log_operation(
            user_id=current_user.id,
            module='todo',
            operation_type='batch_import_export',
            action=f"导出待办事项数据，共{len(todos)}条记录",
            result="成功"
        )
        
        # 发送文件
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logging.error(f"导出待办事项失败: {str(e)}")
        log_operation(
            user_id=current_user.id,
            module='todo',
            operation_type='batch_import_export',
            action=f"导出待办事项数据失败：{str(e)}",
            result="失败"
        )
        return jsonify({'success': False, 'message': f'导出失败: {str(e)}'}), 500