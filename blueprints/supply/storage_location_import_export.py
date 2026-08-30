import os
from flask import Blueprint, request, flash, redirect, url_for, send_file
import logging
from utils.db import db
from models.supply.storage_location import StorageLocation
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.lazy_imports import pd  # 延迟导入pandas，避免启动时加载重型库
import io
from datetime import datetime
import traceback
from utils.auth import require_permission
from io import BytesIO

# 创建导入导出专用蓝图
storage_location_import_export_bp = Blueprint(
    'storage_location_import_export',
    __name__,
    url_prefix='/storage-location/import-export',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/storage-location/import-export/static'
)


# 导出存放位置数据
@storage_location_import_export_bp.route('/export', methods=['GET'])
@login_required
@require_permission('supply.export')
def export():
    """导出存放位置数据为Excel"""
    try:
        logging.debug('开始执行存放位置数据导出')

        # 获取存放位置数据
        locations = StorageLocation.query.order_by(StorageLocation.id).all()
        logging.debug(f'查询到{len(locations)}条存放位置数据')

        if not locations:
            logging.info('没有可导出的存放位置数据')
            flash('没有可导出的存放位置数据', 'info')
            return redirect(url_for('storage_location.index'))

        # 准备导出数据
        data = []
        for loc in locations:
            try:
                data.append({
                    '位置名称': loc.name or '',
                    '位置编码': loc.code or '',
                    '楼栋': loc.building or '',
                    '楼层': loc.floor or '',
                    '房间号': loc.room or '',
                    '使用类型': loc.display_usage_type,
                    '状态': loc.status or '启用',
                    '备注': loc.remark or '',
                    '创建时间': loc.created_at.strftime('%Y-%m-%d %H:%M') if loc.created_at else '',
                    '更新时间': loc.updated_at.strftime('%Y-%m-%d %H:%M') if loc.updated_at else '',
                })
            except Exception as e:
                logging.error(f'处理存放位置ID={loc.id}时出错: {str(e)}', exc_info=True)
                raise

        logging.debug(f'数据准备完成，共{len(data)}条记录')

        # 生成Excel
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='存放位置数据')

        output.seek(0)
        filename = f"存放位置数据导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        logging.debug(f'Excel文件生成成功，文件名: {filename}')

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='batch_import_export',
            action=f"导出存放位置数据，共 {len(locations)} 条记录",
            result="成功"
        )
        logging.info(f'用户{current_user.id}成功导出存放位置数据')

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'导出存放位置数据失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='batch_import_export',
            action=f"尝试导出存放位置数据失败: {str(e)}",
            result="失败"
        )
        flash('导出失败，请联系管理员', 'danger')
        return redirect(url_for('storage_location.index'))


# 导入存放位置数据
@storage_location_import_export_bp.route('/import', methods=['POST'])
@login_required
@require_permission('supply.import')
def import_locations():
    """批量导入存放位置数据"""
    try:
        logging.debug('开始批量导入存放位置数据')
        # 验证文件是否存在
        if 'file' not in request.files:
            flash('请选择要导入的文件', 'danger')
            logging.error('导入存放位置数据失败：未选择文件')
            return redirect(url_for('storage_location.index'))

        file = request.files['file']
        if file.filename == '':
            flash('请选择要导入的文件', 'danger')
            logging.error('导入存放位置数据失败：未选择文件')
            return redirect(url_for('storage_location.index'))

        # 文件类型验证
        allowed_extensions = {'xlsx', 'xls'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            flash(f'请上传Excel格式的文件（.xlsx 或 .xls），当前文件类型：.{file_ext}', 'danger')
            logging.error(f'导入存放位置数据失败：文件类型无效，当前文件类型：.{file_ext}')
            return redirect(url_for('storage_location.index'))

        # 限制文件大小（10MB）
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > 10 * 1024 * 1024:
            flash('文件大小超过限制（最大10MB）', 'danger')
            logging.error('导入存放位置数据失败：文件大小超过限制（最大10MB）')
            return redirect(url_for('storage_location.index'))

        try:
            file_content = file.read()
            file_bytes = BytesIO(file_content)
            file_bytes.seek(0)
            df = pd.read_excel(file_bytes)
        except Exception as e:
            detailed_error = f"文件解析失败：{str(e)}"
            flash(detailed_error, 'danger')
            logging.error(f'导入存放位置数据失败：文件解析失败 - {detailed_error}')
            return redirect(url_for('storage_location.index'))

        # 验证必要列
        required_columns = ['位置名称']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            flash(f'导入失败：文件缺少必要的列 - {", ".join(missing_columns)}', 'danger')
            logging.error(f'导入存放位置数据失败：文件缺少必要的列 - {", ".join(missing_columns)}')
            return redirect(url_for('storage_location.index'))

        # 是否覆盖已有数据
        override = request.form.get('override', '') == '1'

        # 准备导入数据列表
        success_count = 0
        fail_count = 0
        error_records = []

        for index, row in df.iterrows():
            try:
                row_num = index + 2

                # 位置名称（必填）
                name_val = row.get('位置名称')
                if pd.isna(name_val) or str(name_val).strip() == '':
                    error_records.append(f"第{row_num}行：位置名称不能为空")
                    fail_count += 1
                    continue
                name = str(name_val).strip()

                # 位置编码（可选）
                code_val = row.get('位置编码')
                code = str(code_val).strip() if pd.notna(code_val) and str(code_val).strip() else None

                # 楼栋（可选）
                building_val = row.get('楼栋')
                building = str(building_val).strip() if pd.notna(building_val) and str(building_val).strip() else None

                # 楼层（可选）
                floor_val = row.get('楼层')
                floor = str(floor_val).strip() if pd.notna(floor_val) and str(floor_val).strip() else None

                # 房间号（可选）
                room_val = row.get('房间号')
                room = str(room_val).strip() if pd.notna(room_val) and str(room_val).strip() else None

                # 状态（可选，默认"启用"）
                status_val = row.get('状态')
                status = str(status_val).strip() if pd.notna(status_val) and str(status_val).strip() else '启用'
                if status not in ['启用', '停用']:
                    status = '启用'

                # 备注（可选）
                remark_val = row.get('备注')
                remark = str(remark_val).strip() if pd.notna(remark_val) and str(remark_val).strip() else None

                # 使用类型（可选，默认"supply"）
                usage_type_display_map = {'低值易耗品': 'supply', '固定资产': 'fixed_asset', '合同管理': 'contract'}
                usage_type_val = row.get('使用类型')
                if pd.notna(usage_type_val) and str(usage_type_val).strip():
                    usage_type = usage_type_display_map.get(str(usage_type_val).strip(), 'supply')
                else:
                    usage_type = 'supply'

                # 检查名称是否重复（联合usage_type校验）
                existing = StorageLocation.query.filter_by(name=name, usage_type=usage_type).first()
                if existing:
                    if override:
                        # 覆盖更新
                        existing.code = code or existing.code
                        existing.building = building or existing.building
                        existing.floor = floor or existing.floor
                        existing.room = room or existing.room
                        existing.status = status
                        existing.usage_type = usage_type
                        existing.remark = remark or existing.remark
                        existing.handler_user_id = current_user.id
                        success_count += 1
                        continue
                    else:
                        error_records.append(f'第{row_num}行：位置名称"{name}"（使用类型：{usage_type_val or "低值易耗品"}）已存在')
                        fail_count += 1
                        continue

                # 创建存放位置
                StorageLocation.create(
                    name=name,
                    code=code,
                    building=building,
                    floor=floor,
                    room=room,
                    status=status,
                    usage_type=usage_type,
                    handler_user_id=current_user.id,
                    remark=remark,
                    operator_user_id=current_user.id
                )
                success_count += 1

            except Exception as e:
                error_records.append(f"第{row_num}行：创建存放位置失败 - {str(e)}")
                fail_count += 1
                logging.error(f'导入存放位置数据失败：第{row_num}行创建存放位置失败 - {str(e)}')
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
            module='storage_location',
            operation_type='batch_import_export',
            action=f"导入存放位置数据，成功{success_count}条，失败{fail_count}条",
            result=result_status
        )

        # 生成提示信息
        if result_status == "部分成功":
            message = f"导入部分成功：成功导入 {success_count} 条，失败 {fail_count} 条"
            message += f"<br>失败详情：<br>" + "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"
        elif result_status == "成功":
            message = f"导入全部成功：共导入 {success_count} 条存放位置数据"
        else:
            message = f"导入全部失败：共{len(error_records)}条记录处理失败：<br>" + "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"

        logging.info(message)
        flash(message, 'success' if result_status == "成功" else 'warning' if result_status == "部分成功" else 'danger')
        return redirect(url_for('storage_location.index'))

    except Exception as e:
        db.session.rollback()
        detailed_error = f"导入过程出错：{str(e)}"
        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='batch_import_export',
            action=f"存放位置数据导入失败: {detailed_error}\n{traceback.format_exc()}",
            result="失败"
        )
        flash(detailed_error, 'danger')
        logging.error(f'导入存放位置数据失败：{detailed_error}')
        return redirect(url_for('storage_location.index'))


# 下载导入模板
@storage_location_import_export_bp.route('/template', methods=['GET'])
@login_required
@require_permission('supply.import')
def download_template():
    """下载存放位置导入模板"""
    try:
        logging.debug('开始生成存放位置数据导入模板')

        # 模板数据生成
        template_data = {
            "位置名称": ["A区仓库", "B区仓库", "办公室1号柜"],
            "位置编码": ["WH-A", "WH-B", "OF-01"],
            "楼栋": ["1号楼", "2号楼", "行政楼"],
            "楼层": ["1", "1", "3"],
            "房间号": ["101", "102", "301"],
            "使用类型": ["低值易耗品", "低值易耗品", "固定资产"],
            "状态": ["启用", "启用", "停用"],
            "备注": ["主仓库", "副仓库", ""],
        }

        df = pd.DataFrame(template_data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='存放位置数据')

        output.seek(0)
        filename = "存放位置数据导入模板.xlsx"

        log_operation(
            user_id=current_user.id,
            module='storage_location',
            operation_type='batch_import_export',
            action="下载存放位置数据导入模板",
            result="成功"
        )

        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        logging.error(f'生成存放位置数据导入模板失败: {str(e)}', exc_info=True)
        flash('生成模板失败，请联系管理员', 'danger')
        return redirect(url_for('storage_location.index'))