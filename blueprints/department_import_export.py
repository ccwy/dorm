import os
from flask import Blueprint, request, flash, redirect, url_for, send_file
import logging
from utils.db import db
from models.department import Department
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.lazy_imports import pd  # 延迟导入pandas，避免启动时加载重型库
import io
from datetime import datetime
import traceback
from utils.auth import require_permission
from io import BytesIO

# 创建导入导出专用蓝图
department_import_export_bp = Blueprint(
    'department_import_export',
    __name__,
    url_prefix='/department/import-export',
    template_folder='../templates',
    static_folder='../static',
    static_url_path='/department/import-export/static'
)


# 导出部门数据
@department_import_export_bp.route('/export', methods=['GET'])
@login_required
@require_permission('department.export')
def export():
    """导出部门数据为Excel"""
    try:
        logging.debug('开始执行部门数据导出')

        # 获取部门数据
        departments = Department.query.order_by(Department.id).all()
        logging.debug(f'查询到{len(departments)}条部门数据')

        if not departments:
            logging.info('没有可导出的部门数据')
            flash('没有可导出的部门数据', 'info')
            return redirect(url_for('department.index'))

        # 准备导出数据
        logging.debug('开始准备导出数据')
        data = []
        for dept in departments:
            try:
                data.append({
                    '部门名称': dept.name or '',
                    '所属公司': dept.company or '',
                    '部门描述': dept.description or '',
                    '状态': dept.status or '正常',
                    '新增日期': dept.created_date.strftime('%Y-%m-%d') if dept.created_date else '',
                    '创建时间': dept.created_at.strftime('%Y-%m-%d %H:%M') if dept.created_at else '',
                    '更新时间': dept.updated_at.strftime('%Y-%m-%d %H:%M') if dept.updated_at else '',
                })
            except Exception as e:
                logging.error(f'处理部门ID={dept.id}时出错: {str(e)}', exc_info=True)
                raise

        logging.debug(f'数据准备完成，共{len(data)}条记录')

        # 生成Excel
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='部门数据')

        output.seek(0)
        filename = f"部门数据导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        logging.debug(f'Excel文件生成成功，文件名: {filename}')

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='batch_import_export',
            action=f"导出部门数据，共 {len(departments)} 条记录",
            result="成功"
        )
        logging.info(f'用户{current_user.id}成功导出部门数据')

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'导出部门数据失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='batch_import_export',
            action=f"尝试导出部门数据失败: {str(e)}",
            result="失败"
        )
        flash(f'导出失败，请联系管理员', 'danger')
        return redirect(url_for('department.index'))


# 导入部门数据
@department_import_export_bp.route('/import', methods=['POST'])
@login_required
@require_permission('department.import')
def import_departments():
    """批量导入部门数据"""
    try:
        logging.debug('开始批量导入部门数据')
        # 验证文件是否存在
        if 'file' not in request.files:
            flash('请选择要导入的文件', 'danger')
            logging.error('导入部门数据失败：未选择文件')
            return redirect(url_for('department.index'))

        file = request.files['file']
        if file.filename == '':
            flash('请选择要导入的文件', 'danger')
            logging.error('导入部门数据失败：未选择文件')
            return redirect(url_for('department.index'))

        # 文件类型验证
        allowed_extensions = {'xlsx', 'xls'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            flash(f'请上传Excel格式的文件（.xlsx 或 .xls），当前文件类型：.{file_ext}', 'danger')
            logging.error(f'导入部门数据失败：文件类型无效，当前文件类型：.{file_ext}')
            return redirect(url_for('department.index'))

        # 限制文件大小（10MB）
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > 10 * 1024 * 1024:
            flash('文件大小超过限制（最大10MB）', 'danger')
            logging.error('导入部门数据失败：文件大小超过限制（最大10MB）')
            return redirect(url_for('department.index'))

        try:
            file_content = file.read()
            file_bytes = BytesIO(file_content)
            file_bytes.seek(0)
            df = pd.read_excel(file_bytes)
        except Exception as e:
            detailed_error = f"文件解析失败：{str(e)}"
            log_operation(
                user_id=current_user.id,
                module='department',
                operation_type='batch_import_export',
                action="解析Excel文件",
                result=f"失败: {detailed_error}"
            )
            flash(detailed_error, 'danger')
            logging.error(f'导入部门数据失败：文件解析失败 - {detailed_error}')
            return redirect(url_for('department.index'))

        # 验证必要列
        required_columns = ['部门名称']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            flash(f'导入失败：文件缺少必要的列 - {", ".join(missing_columns)}', 'danger')
            logging.error(f'导入部门数据失败：文件缺少必要的列 - {", ".join(missing_columns)}')
            return redirect(url_for('department.index'))

        # 准备导入数据列表
        success_count = 0
        fail_count = 0
        error_records = []

        for index, row in df.iterrows():
            try:
                row_num = index + 2

                # 部门名称（必填）
                name_val = row.get('部门名称')
                if pd.isna(name_val) or str(name_val).strip() == '':
                    error_records.append(f"第{row_num}行：部门名称不能为空")
                    fail_count += 1
                    continue
                name = str(name_val).strip()

                # 所属公司（可选）
                company_val = row.get('所属公司')
                company = str(company_val).strip() if pd.notna(company_val) and str(company_val).strip() else None

                # 部门描述（可选）
                description_val = row.get('部门描述')
                description = str(description_val).strip() if pd.notna(description_val) and str(description_val).strip() else None

                # 新增日期（可选）
                created_date_str = str(row.get('新增日期', '')).strip() if pd.notna(row.get('新增日期')) else ''
                created_date = None
                if created_date_str:
                    try:
                        created_date = datetime.strptime(created_date_str, '%Y-%m-%d').date()
                    except ValueError:
                        pass

                # 状态（可选，默认"正常"）
                status_val = row.get('状态')
                status = str(status_val).strip() if pd.notna(status_val) and str(status_val).strip() else '正常'
                if status not in ['正常', '停用']:
                    status = '正常'

                # 检查名称是否重复（同公司下唯一）
                if Department.is_name_exists(name, company=company):
                    if company:
                        error_records.append(f'第{row_num}行：公司"{company}"下已存在部门"{name}"')
                    else:
                        error_records.append(f'第{row_num}行：已存在部门"{name}"（未指定公司）')
                    fail_count += 1
                    continue

                # 创建部门
                Department.create(name=name, description=description, company=company, created_date=created_date, status=status)
                success_count += 1

            except Exception as e:
                error_records.append(f"第{row_num}行：创建部门失败 - {str(e)}")
                fail_count += 1
                logging.error(f'导入部门数据失败：第{row_num}行创建部门失败 - {str(e)}')
                continue

        # 记录操作日志
        total_count = success_count + fail_count
        if success_count > 0:
            result_status = "部分成功" if fail_count > 0 else "成功"
        else:
            result_status = "失败"

        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='batch_import_export',
            action=f"导入部门数据，成功{success_count}条，失败{fail_count}条",
            result=result_status
        )

        # 生成提示信息
        if result_status == "部分成功":
            message = f"导入部分成功：成功导入 {success_count} 条，失败 {fail_count} 条"
            message += f"<br>失败详情：<br>" + "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"
        elif result_status == "成功":
            message = f"导入全部成功：共导入 {success_count} 条部门数据"
        else:
            message = f"导入全部失败：共{len(error_records)}条记录处理失败：<br>" + "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"

        logging.info(message)
        flash(message, 'success' if result_status == "成功" else 'warning' if result_status == "部分成功" else 'danger')
        return redirect(url_for('department.index'))

    except Exception as e:
        db.session.rollback()
        detailed_error = f"导入过程出错：{str(e)}"
        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='batch_import_export',
            action=f"部门数据导入失败: {detailed_error}\n{traceback.format_exc()}",
            result="失败"
        )
        flash(detailed_error, 'danger')
        logging.error(f'导入部门数据失败：{detailed_error}')
        return redirect(url_for('department.index'))


# 下载导入模板
@department_import_export_bp.route('/template', methods=['GET'])
@login_required
@require_permission('department.import')
def download_template():
    """生成并下载部门数据导入模板"""
    try:
        logging.debug('开始生成部门数据导入模板')

        # 模板数据生成
        template_data = {
            "部门名称": ["行政部", "财务部", "技术部"],
            "所属公司": ["总公司", "总公司", "子公司"],
            "部门描述": ["负责行政管理", "负责财务管理", "负责技术研发"],
            "状态": ["正常", "正常", "停用"],
            "新增日期": ["2026-01-01", "2026-01-15", "2026-02-01"],
        }

        df = pd.DataFrame(template_data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='部门数据')

        output.seek(0)
        filename = "部门数据导入模板.xlsx"

        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='batch_import_export',
            action="下载部门数据导入模板",
            result="成功"
        )

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'生成部门数据导入模板失败: {str(e)}', exc_info=True)
        flash('生成模板失败，请联系管理员', 'danger')
        return redirect(url_for('department.index'))