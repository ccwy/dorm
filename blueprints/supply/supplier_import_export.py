import os
from flask import Blueprint, request, flash, redirect, url_for, send_file
import logging
from utils.db import db
from models.supply.supplier import Supplier
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.lazy_imports import pd  # 延迟导入pandas，避免启动时加载重型库
import io
from datetime import datetime
import traceback
from utils.auth import require_permission
from io import BytesIO

# 创建导入导出专用蓝图
supplier_import_export_bp = Blueprint(
    'supplier_import_export',
    __name__,
    url_prefix='/supplier/import-export',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/supplier/import-export/static'
)


# 导出供应商数据
@supplier_import_export_bp.route('/export', methods=['GET'])
@login_required
@require_permission('supply.export')
def export():
    """导出供应商数据为Excel"""
    try:
        logging.debug('开始执行供应商数据导出')

        # 获取供应商数据
        suppliers = Supplier.query.order_by(Supplier.id).all()
        logging.debug(f'查询到{len(suppliers)}条供应商数据')

        if not suppliers:
            logging.info('没有可导出的供应商数据')
            flash('没有可导出的供应商数据', 'info')
            return redirect(url_for('supplier.index'))

        # 准备导出数据
        data = []
        for s in suppliers:
            try:
                data.append({
                    '供应商名称': s.name or '',
                    '统一社会信用代码': s.unified_social_credit_code or '',
                    '法定代表人': s.legal_representative or '',
                    '联系人': s.contact_person or '',
                    '联系电话': s.contact_phone or '',
                    '邮箱': s.email or '',
                    '地址': s.address or '',
                    '状态': s.status or '启用',
                    '备注': s.remark or '',
                    '创建时间': s.created_at.strftime('%Y-%m-%d %H:%M') if s.created_at else '',
                    '更新时间': s.updated_at.strftime('%Y-%m-%d %H:%M') if s.updated_at else '',
                })
            except Exception as e:
                logging.error(f'处理供应商ID={s.id}时出错: {str(e)}', exc_info=True)
                raise

        logging.debug(f'数据准备完成，共{len(data)}条记录')

        # 生成Excel
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='供应商数据')

        output.seek(0)
        filename = f"供应商数据导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        logging.debug(f'Excel文件生成成功，文件名: {filename}')

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='batch_import_export',
            action=f"导出供应商数据，共 {len(suppliers)} 条记录",
            result="成功"
        )
        logging.info(f'用户{current_user.id}成功导出供应商数据')

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'导出供应商数据失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='batch_import_export',
            action=f"尝试导出供应商数据失败: {str(e)}",
            result="失败"
        )
        flash('导出失败，请联系管理员', 'danger')
        return redirect(url_for('supplier.index'))


# 导入供应商数据
@supplier_import_export_bp.route('/import', methods=['POST'])
@login_required
@require_permission('supply.import')
def import_suppliers():
    """批量导入供应商数据"""
    try:
        logging.debug('开始批量导入供应商数据')
        # 验证文件是否存在
        if 'file' not in request.files:
            flash('请选择要导入的文件', 'danger')
            logging.error('导入供应商数据失败：未选择文件')
            return redirect(url_for('supplier.index'))

        file = request.files['file']
        if file.filename == '':
            flash('请选择要导入的文件', 'danger')
            logging.error('导入供应商数据失败：未选择文件')
            return redirect(url_for('supplier.index'))

        # 文件类型验证
        allowed_extensions = {'xlsx', 'xls'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            flash(f'请上传Excel格式的文件（.xlsx 或 .xls），当前文件类型：.{file_ext}', 'danger')
            logging.error(f'导入供应商数据失败：文件类型无效，当前文件类型：.{file_ext}')
            return redirect(url_for('supplier.index'))

        # 限制文件大小（10MB）
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > 10 * 1024 * 1024:
            flash('文件大小超过限制（最大10MB）', 'danger')
            logging.error('导入供应商数据失败：文件大小超过限制（最大10MB）')
            return redirect(url_for('supplier.index'))

        try:
            file_content = file.read()
            file_bytes = BytesIO(file_content)
            file_bytes.seek(0)
            df = pd.read_excel(file_bytes)
        except Exception as e:
            detailed_error = f"文件解析失败：{str(e)}"
            flash(detailed_error, 'danger')
            logging.error(f'导入供应商数据失败：文件解析失败 - {detailed_error}')
            return redirect(url_for('supplier.index'))

        # 验证必要列
        required_columns = ['供应商名称']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            flash(f'导入失败：文件缺少必要的列 - {", ".join(missing_columns)}', 'danger')
            logging.error(f'导入供应商数据失败：文件缺少必要的列 - {", ".join(missing_columns)}')
            return redirect(url_for('supplier.index'))

        # 是否覆盖已有数据
        override = request.form.get('override', '') == '1'

        # 准备导入数据列表
        success_count = 0
        fail_count = 0
        error_records = []

        for index, row in df.iterrows():
            try:
                row_num = index + 2

                # 供应商名称（必填）
                name_val = row.get('供应商名称')
                if pd.isna(name_val) or str(name_val).strip() == '':
                    error_records.append(f"第{row_num}行：供应商名称不能为空")
                    fail_count += 1
                    continue
                name = str(name_val).strip()

                # 统一社会信用代码（可选）
                unified_social_credit_code_val = row.get('统一社会信用代码')
                unified_social_credit_code = str(unified_social_credit_code_val).strip() if pd.notna(unified_social_credit_code_val) and str(unified_social_credit_code_val).strip() else None

                # 法定代表人（可选）
                legal_representative_val = row.get('法定代表人')
                legal_representative = str(legal_representative_val).strip() if pd.notna(legal_representative_val) and str(legal_representative_val).strip() else None

                # 联系人（可选）
                contact_person_val = row.get('联系人')
                contact_person = str(contact_person_val).strip() if pd.notna(contact_person_val) and str(contact_person_val).strip() else None

                # 联系电话（可选）
                contact_phone_val = row.get('联系电话')
                contact_phone = str(contact_phone_val).strip() if pd.notna(contact_phone_val) and str(contact_phone_val).strip() else None

                # 邮箱（可选）
                email_val = row.get('邮箱')
                email = str(email_val).strip() if pd.notna(email_val) and str(email_val).strip() else None

                # 地址（可选）
                address_val = row.get('地址')
                address = str(address_val).strip() if pd.notna(address_val) and str(address_val).strip() else None

                # 状态（可选，默认"启用"）
                status_val = row.get('状态')
                status = str(status_val).strip() if pd.notna(status_val) and str(status_val).strip() else '启用'
                if status not in ['启用', '停用']:
                    status = '启用'

                # 备注（可选）
                remark_val = row.get('备注')
                remark = str(remark_val).strip() if pd.notna(remark_val) and str(remark_val).strip() else None

                # 检查名称是否重复
                existing = Supplier.query.filter_by(name=name).first()
                if existing:
                    if override:
                        # 覆盖更新
                        existing.unified_social_credit_code = unified_social_credit_code or existing.unified_social_credit_code
                        existing.legal_representative = legal_representative or existing.legal_representative
                        existing.contact_person = contact_person or existing.contact_person
                        existing.contact_phone = contact_phone or existing.contact_phone
                        existing.email = email or existing.email
                        existing.address = address or existing.address
                        existing.status = status
                        existing.remark = remark or existing.remark
                        existing.handler_user_id = current_user.id
                        success_count += 1
                        continue
                    else:
                        error_records.append(f'第{row_num}行：供应商名称"{name}"已存在')
                        fail_count += 1
                        continue

                # 创建供应商
                Supplier.create(
                    name=name,
                    unified_social_credit_code=unified_social_credit_code,
                    legal_representative=legal_representative,
                    contact_person=contact_person,
                    contact_phone=contact_phone,
                    email=email,
                    address=address,
                    status=status,
                    handler_user_id=current_user.id,
                    remark=remark,
                    operator_user_id=current_user.id
                )
                success_count += 1

            except Exception as e:
                error_records.append(f"第{row_num}行：创建供应商失败 - {str(e)}")
                fail_count += 1
                logging.error(f'导入供应商数据失败：第{row_num}行创建供应商失败 - {str(e)}')
                continue

        db.session.commit()

        # 记录操作日志
        total_count = success_count + fail_count
        if success_count > 0:
            result_status = "部分成功" if fail_count > 0 else "成功"
        else:
            result_status = "失败"

        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='batch_import_export',
            action=f"导入供应商数据，成功{success_count}条，失败{fail_count}条",
            result=result_status
        )

        # 生成提示信息
        if result_status == "部分成功":
            message = f"导入部分成功：成功导入 {success_count} 条，失败 {fail_count} 条"
            message += f"<br>失败详情：<br>" + "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"
        elif result_status == "成功":
            message = f"导入全部成功：共导入 {success_count} 条供应商数据"
        else:
            message = f"导入全部失败：共{len(error_records)}条记录处理失败：<br>" + "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"

        logging.info(message)
        flash(message, 'success' if result_status == "成功" else 'warning' if result_status == "部分成功" else 'danger')
        return redirect(url_for('supplier.index'))

    except Exception as e:
        db.session.rollback()
        detailed_error = f"导入过程出错：{str(e)}"
        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='batch_import_export',
            action=f"供应商数据导入失败: {detailed_error}\n{traceback.format_exc()}",
            result="失败"
        )
        flash(detailed_error, 'danger')
        logging.error(f'导入供应商数据失败：{detailed_error}')
        return redirect(url_for('supplier.index'))


# 下载导入模板
@supplier_import_export_bp.route('/template', methods=['GET'])
@login_required
@require_permission('supply.import')
def download_template():
    """生成并下载供应商数据导入模板"""
    try:
        logging.debug('开始生成供应商数据导入模板')

        # 模板数据生成
        template_data = {
            "供应商名称": ["示例供应商A", "示例供应商B", "示例供应商C"],
            "统一社会信用代码": ["91110000MA01ABCD1X", "91310000MA02EFGH2Y", "91440000MA03IJKL3Z"],
            "法定代表人": ["张三", "李四", "王五"],
            "联系人": ["张三", "李四", "王五"],
            "联系电话": ["13800138001", "13800138002", "13800138003"],
            "邮箱": ["zhangsan@example.com", "lisi@example.com", "wangwu@example.com"],
            "地址": ["北京市朝阳区", "上海市浦东新区", "广州市天河区"],
            "状态": ["启用", "启用", "停用"],
            "备注": ["主要供应商", "备选供应商", ""],
        }

        df = pd.DataFrame(template_data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='供应商数据')

        output.seek(0)
        filename = "供应商数据导入模板.xlsx"

        log_operation(
            user_id=current_user.id,
            module='supplier',
            operation_type='batch_import_export',
            action="下载供应商数据导入模板",
            result="成功"
        )

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'生成供应商数据导入模板失败: {str(e)}', exc_info=True)
        flash('生成模板失败，请联系管理员', 'danger')
        return redirect(url_for('supplier.index'))