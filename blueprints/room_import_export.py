import os
from flask import Blueprint, request, flash, redirect, url_for, send_file
import logging
from utils.db import db
from models.room import Room, RoomStatus
from models.room_facility import RoomFacility  # 导入房间设施模型
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.lazy_imports import pd  # 延迟导入pandas，避免启动时加载重型库
import io
from datetime import datetime, timedelta
import traceback
from models.system_config import SystemConfig
from io import BytesIO
from utils.auth import require_permission
from utils.excel_date_utils import excel_date_utils

# 创建导入导出专用蓝图
room_import_export_bp = Blueprint(
    'room_import_export', 
    __name__, 
    url_prefix='/room', 
    template_folder='../templates',
    static_folder='../static',
    static_url_path='/room/static'
)


# 导出房间数据
@room_import_export_bp.route('/export', methods=['GET'])
@login_required
@require_permission('room.export')
def export():
    try:
        logging.debug('开始执行房间数据导出')
        
        # 获取房间数据
        rooms = Room.query.all()
        logging.debug(f'查询到{len(rooms)}条房间数据')
        
        if not rooms:
            logging.info('没有可导出的房间数据')
            flash('没有可导出的房间数据', 'info')
            return redirect(url_for('room.manage'))
        
        # 准备导出数据
        logging.debug('开始准备导出数据')
        data = []
        for room in rooms:
            try:
                # 使用房间设施模型的方法获取设施列表
                facilities = RoomFacility.query.filter_by(room_id=room.id).all()
                facilities_str = ','.join([f'{f.name}:{f.quantity}' for f in facilities])
                
                # 获取当前在住人员信息
                from models.dorm import Dorm
                from models.user import User
                active_dorms = Dorm.query.filter(
                    Dorm.room_id == room.id,
                    Dorm.status == 'active'
                ).all()
                
                # 获取在住人员姓名列表
                occupants = []
                if active_dorms:
                    user_ids = [dorm.user_id for dorm in active_dorms]
                    users = User.query.filter(User.id.in_(user_ids)).all()
                    # 按姓名排序，只显示姓名
                    users.sort(key=lambda x: x.name)
                    occupants = [f'{user.name}' for user in users]
                
                # 格式化为逗号分隔的字符串
                occupants_str = ','.join(occupants) if occupants else ''
                
                data.append({
                    'ID': room.id,
                    '楼栋': room.building,
                    '房间号': room.room_number,
                    '地址': room.address or '',
                    '房间类型': room.room_type,
                    '房间级别': room.room_level or '',
                    '性别限制': room.gender_restriction,
                    '容量': room.capacity,
                    '当前入住': room.current_occupancy,
                    '入住率': room.occupancy_rate,
                    '当前在住人员': occupants_str,  # 添加当前在住人员列
                    '状态': room.get_status_display,
                    '对外租金': room.external_rent,
                    '成本租金': room.cost_rent,
                    '房间设施': facilities_str,  # 使用从设施模型获取的数据
                    '电表最大量程': room.electric_meter_max,
                    '水表最大量程': room.water_meter_max,
                    '房间水电费减免金额': room.reduction_fee,
                    '用水量减免度数': room.water_reduction,
                    '用电量减免度数': room.electric_reduction,
                    '备注': room.remark or '',
                    '添加时间': room.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    '更新时间': room.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                })
            except Exception as e:
                logging.error(f'处理房间ID={room.id}时出错: {str(e)}', exc_info=True)
                raise
            
        logging.debug(f'数据准备完成，共{len(data)}条记录')
        
        # 生成Excel
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='房间数据')
        
        output.seek(0)
        filename = f"房间数据导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        logging.debug(f'Excel文件生成成功，文件名: {filename}')
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='batch_import_export',
            action=f"导出房间数据，共 {len(rooms)} 条记录",
            result="成功"
        )
        logging.info(f'用户{current_user.id}成功导出房间数据')
        
        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    except Exception as e:
        logging.error(f'导出房间数据失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='batch_import_export',
            action=f"尝试导出房间数据失败: {str(e)}",
            result="失败"
        )
        flash(f'导出失败，请联系管理员', 'danger')
        return redirect(url_for('room.manage'))




# 导入房间数据（使用模型的批量处理方法）
@room_import_export_bp.route('/import', methods=['POST'])
@login_required
@require_permission('room.import')
def import_rooms():
    """批量导入房间数据"""
    try:
        logging.debug('开始批量导入房间数据')
        # 验证文件是否存在
        if 'file' not in request.files:
            flash('请选择要导入的文件', 'danger')
            logging.error('导入房间数据失败：未选择文件')
            return redirect(url_for('room.manage'))
        
        file = request.files['file']
        if file.filename == '':
            flash('请选择要导入的文件', 'danger')
            logging.error('导入房间数据失败：未选择文件')
            return redirect(url_for('room.manage'))
        
        # 文件类型验证
        allowed_extensions = {'xlsx', 'xls'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            flash(f'请上传Excel格式的文件（.xlsx 或 .xls），当前文件类型：.{file_ext}', 'danger')
            logging.error(f'导入房间数据失败：文件类型无效，当前文件类型：.{file_ext}')
            return redirect(url_for('room.manage'))
        
        # 限制文件大小（10MB）
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        if file_size > 10 * 1024 * 1024:
            flash('文件大小超过限制（最大10MB）', 'danger')
            logging.error('导入房间数据失败：文件大小超过限制（最大10MB）')
            return redirect(url_for('room.manage'))
        
        try:
            file_content = file.read()
            file_bytes = BytesIO(file_content)
            file_bytes.seek(0)
            df = pd.read_excel(file_bytes)
        except Exception as e:
            detailed_error = f"文件解析失败：{str(e)}"
            log_operation(
                user_id=current_user.id,
                action="解析Excel文件",
                result=f"失败: {detailed_error}"
            )
            flash(detailed_error, 'danger')
            logging.error(f'导入房间数据失败：文件解析失败 - {detailed_error}')
            return redirect(url_for('room.manage'))
        
        # 忽略ID列
        for col in ['ID', 'id']:
            if col in df.columns:
                df = df.drop(columns=[col])
        
        # 验证必要列
        required_columns = ['楼栋', '房间号', '房间类型', '容量', '性别限制']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            flash(f'导入失败：文件缺少必要的列 - {", ".join(missing_columns)}', 'danger')
            logging.error(f'导入房间数据失败：文件缺少必要的列 - {", ".join(missing_columns)}')
            return redirect(url_for('room.manage'))
        
        # 获取有效的配置数据
        valid_room_types = Room.get_valid_room_types()
        if not valid_room_types:
            flash('系统配置中未设置有效的房间类型，请先配置房间类型', 'danger')
            logging.error('导入房间数据失败：系统配置中未设置有效的房间类型')
            return redirect(url_for('room.manage'))

        valid_room_levels = Room.get_valid_room_levels() or []
        valid_facilities = RoomFacility.get_all_valid_facilities()  # 获取有效的设施列表
        
        # 准备导入数据列表
        rooms_data = []
        facilities_data = {}  # 存储每个房间的设施数据，key为"楼栋+房间号"
        error_records = []
        
        # 提取所有添加时间值进行批量解析
        created_at_values = df.get('添加时间', pd.Series([None] * len(df)))  # 获取添加时间列或创建空Series
        try:
            # 使用excel_date_utils批量解析添加时间
            parsed_dates = excel_date_utils.parse_excel_date(created_at_values, field_name='添加时间', raise_error=False)
        except Exception as e:
            # 捕获任何批量处理过程中可能出现的异常
            flash(f'批量解析添加时间失败：{str(e)}', 'danger')
            logging.error(f'批量解析添加时间失败：{str(e)}')
            return redirect(url_for('room.manage'))
        
        for index, row in df.iterrows():
            try:
                row_num = index + 2
                
                # 处理楼栋和房间号（用于唯一标识房间）
                building_val = row['楼栋']
                building = str(building_val).strip() or 'A'

                room_number_val = row['房间号']
                if pd.isna(room_number_val):
                    error_records.append(f"第{row_num}行：房间号不能为空")
                    continue
                
                try:
                    room_number_int = int(float(str(room_number_val).strip()))
                    room_number = str(room_number_int)
                except ValueError:
                    room_number = str(room_number_val).strip()
                
                if not room_number:
                    error_records.append(f"第{row_num}行：房间号不能为空")
                    continue
                
                room_key = f"{building}_{room_number}"  # 用于关联设施数据
                
                # 处理房间级别
                room_level_val = row.get('房间级别')
                if pd.isna(room_level_val) or str(room_level_val).strip() == '':
                    room_level = '员工'
                else:
                    room_level = str(room_level_val).strip()
                    if valid_room_levels and room_level not in valid_room_levels:
                        room_level = '员工'
                
                # 处理房间类型
                room_type_val = row['房间类型']
                room_type_text = str(room_type_val).strip() if not pd.isna(room_type_val) else '四人间'

                if room_type_text not in valid_room_types:
                    error_records.append(
                        f"第{row_num}行：房间类型 '{room_type_text}' 无效，有效类型为：{', '.join(valid_room_types)}"
                    )

                # 处理容量
                capacity_val = row['容量']
                if pd.isna(capacity_val):
                    capacity = 4
                else:
                    try:
                        capacity = int(str(capacity_val).strip())
                    except ValueError:
                        error_records.append(f"第{row_num}行：容量必须为整数")
                        continue
                
                # 处理性别限制
                gender_val = row['性别限制']
                gender_text = str(gender_val).strip() if not pd.isna(gender_val) else '无限制'
                
                # 处理状态字段
                status_val = row.get('状态')
                status_text = str(status_val).strip() if not pd.isna(status_val) else '可用'
                
                # 处理租金字段
                try:
                    external_rent_val = row.get('对外租金', 0) or 0
                    external_rent = float(external_rent_val)
                    if pd.isna(external_rent):
                        external_rent = 0.0
                    external_rent = int(external_rent)

                    cost_rent_val = row.get('成本租金', 0) or 0
                    cost_rent = float(cost_rent_val)
                    if pd.isna(cost_rent):
                        cost_rent = 0.0
                    cost_rent = int(cost_rent)
                except (ValueError, TypeError):
                    error_records.append(f"第{row_num}行：租金必须为有效的数字")
                    continue
                
                # 处理房间设施
                facilities_str = str(row.get('房间设施', '')).strip() if not pd.isna(row.get('房间设施')) else ''
                facilities = []
                
                if facilities_str:
                    facility_items = facilities_str.split(',')
                    for item in facility_items:
                        if ':' in item:
                            name, quantity_str = item.split(':', 1)
                            name = name.strip()
                            quantity_str = quantity_str.strip()
                            
                            # 验证设施名称是否有效
                            if name not in valid_facilities:
                                error_records.append(
                                    f"第{row_num}行：设施 '{name}' 无效，有效设施为：{', '.join(valid_facilities[:5])}..."
                                )
                                continue
                            
                            try:
                                quantity = int(quantity_str)
                                if quantity > 0:  # 只保留正数量的设施
                                    facilities.append({'name': name, 'quantity': quantity})
                            except ValueError:
                                error_records.append(f"第{row_num}行：设施 '{name}' 的数量必须为整数")
                
                # 存储设施数据，与房间关联
                facilities_data[room_key] = facilities
                
                # 处理备注
                remark = str(row.get('备注', '')).strip() if not pd.isna(row.get('备注')) else ''
                
                # 基础数据验证
                if capacity <= 0:
                    error_records.append(f"第{row_num}行：容量必须为正整数")
                    continue
                
                if external_rent < 0 or cost_rent < 0:
                    error_records.append(f"第{row_num}行：租金不能为负数")
                    continue
                
                # 处理添加时间（使用批量解析的结果）
                created_at_value = row.get('添加时间')
                created_at = parsed_dates[index]  # 使用批量解析的结果
                
                # 如果原始值存在但解析结果为None，添加错误信息
                if pd.notna(created_at_value) and created_at is None:
                    error_records.append(f"第{row_num}行：添加时间格式无效，请使用正确的日期时间格式")
                    continue
                
                # 添加到数据列表
                rooms_data.append({
                    '楼栋': building,
                    '房间号': room_number,
                    '地址': str(row.get('地址', '')).strip() if not pd.isna(row.get('地址')) else '',
                    '房间类型': room_type_text,
                    '房间级别': room_level,
                    '容量': capacity,
                    '性别限制': gender_text,
                    '状态': status_text,
                    '对外租金': external_rent,
                    '成本租金': cost_rent,
                    '电表最大量程': float(row.get('电表最大量程', 9999.99) or 9999.99),
                    '水表最大量程': float(row.get('水表最大量程', 9999.99) or 9999.99),
                    '备注': remark,
                    '添加时间': created_at
                })
                
            except Exception as e:
                error_records.append(f"第{row_num}行：数据处理失败 - {str(e)}")
                logging.error(f'导入房间数据失败：第{row_num}行数据处理失败 - {str(e)}')
                continue
        
        # 如果有基础数据错误，直接返回
        if error_records:
            message = f"数据验证失败：共{len(error_records)}条错误<br>" + "<br>".join(error_records[:5])
            if len(error_records) > 5:
                message += f"<br>... 还有 {len(error_records)-5} 条错误"
            flash(message, 'danger')
            logging.error(f'导入房间数据失败：数据验证失败，共{len(error_records)}条错误')
            return redirect(url_for('room.manage'))
        
        # 调用模型的批量创建或更新方法
        override = 'override' in request.form
        success_create, success_update, model_errors, created_rooms = Room.bulk_create_or_update(rooms_data, override)
        
        # 处理设施数据 - 为新创建或更新的房间添加设施
        facility_errors = []
        try:
            # 处理新创建的房间
            for room in created_rooms:
                room_key = f"{room.building}_{room.room_number}"
                if room_key in facilities_data:
                    facilities = facilities_data[room_key]
                    # 调用设施模型的批量更新方法
                    result = RoomFacility.bulk_update_facilities(room.id, facilities, remark="批量导入设施")
                    if not result:
                        facility_errors.append(f"房间 {room.building}{room.room_number} 的设施更新失败")
            
            # 处理已存在的房间（更新操作）
            # 这里假设bulk_create_or_update返回的rooms_data中包含所有成功更新的房间信息
            for room_data in rooms_data:
                if any(room.id for room in created_rooms if 
                       room.building == room_data['楼栋'] and 
                       room.room_number == room_data['房间号']):
                    continue  # 已处理过的新房间
                
                # 查找已存在的房间
                existing_room = Room.query.filter_by(
                    building=room_data['楼栋'],
                    room_number=room_data['房间号']
                ).first()
                
                if existing_room:
                    room_key = f"{room_data['楼栋']}_{room_data['房间号']}"
                    if room_key in facilities_data:
                        facilities = facilities_data[room_key]
                        result = RoomFacility.bulk_update_facilities(existing_room.id, facilities, remark="批量更新设施")
                        if not result:
                            facility_errors.append(f"房间 {existing_room.building}{existing_room.room_number} 的设施更新失败")
        
        except Exception as e:
            facility_errors.append(f"设施处理过程出错: {str(e)}")
            logging.error(f"批量处理设施时出错: {str(e)}")
        
        # 处理所有错误
        all_errors = model_errors + facility_errors
        
        # 计算总成功数并判断结果状态
        total_success = success_create + success_update
        if total_success > 0:
            result_status = "部分成功" if all_errors else "成功"
        else:
            result_status = "失败"
        
        # 生成日志描述
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='batch_import_export',
            action=f"导入房间数据，成功{success_create}条，更新{success_update}条，失败{len(all_errors)}条",
            result=result_status
        )
        
        # 生成提示信息
        if result_status == "部分成功":
            message = f"导入部分成功：成功导入 {success_create} 个，更新 {success_update} 个"
            if facility_errors:
                message += f"，{len(facility_errors)} 个房间的设施处理失败"
            message += f"，{len(model_errors)} 条房间数据处理失败：<br>" + "<br>".join(all_errors[:5])
            if len(all_errors) > 5:
                message += f"<br>... 还有 {len(all_errors)-5} 条错误"
        elif result_status == "成功":
            message = f"导入全部成功：共处理{total_success}条（新增{success_create}个，更新{success_update}个）"
            if facility_errors:
                message += f"，但有 {len(facility_errors)} 个房间的设施处理失败"
        else:
            message = f"导入全部失败：共{len(all_errors)}条记录处理失败：<br>" + "<br>".join(all_errors[:5])
            if len(all_errors) > 5:
                message += f"<br>... 还有 {len(all_errors)-5} 条错误"
        
        logging.info(message)
        flash(message, 'success' if result_status == "成功" else 'warning' if result_status == "部分成功" else 'danger')
        return redirect(url_for('room.manage'))
        
    except Exception as e:
        db.session.rollback()
        detailed_error = f"导入过程出错：{str(e)}"
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='batch_import_export',
            action=f"房间数据导入失败: {detailed_error}\n{traceback.format_exc()}",
            result="失败"
        )
        flash(detailed_error, 'danger')
        logging.error(f'导入房间数据失败：{detailed_error}')
        return redirect(url_for('room.manage'))

@room_import_export_bp.route('/download_template', methods=['GET'])
@login_required
@require_permission('room.import')
def download_template():
    """生成并下载房间数据导入模板"""
    try:
        logging.debug('开始生成房间数据导入模板')
        
        # 获取有效配置数据
        valid_room_types = Room.get_valid_room_types() or ["单人间", "双人间", "四人间", "六人间"]
        valid_room_levels = Room.get_valid_room_levels() or ["普通", "豪华", "VIP"]
        valid_facilities = RoomFacility.get_all_valid_facilities() or ["空调", "洗衣机", "冰箱", "热水器"]
        
        # 模板数据生成
        template_data = {
            "楼栋": ["A栋", "B栋", "C栋"],
            "房间号": ["101", "202", "303"],
            "地址": ["XX路XX号X单元101室", "YY路YY号Y单元202室", ""],
            "房间类型": [valid_room_types[0], "", ""],
            "房间级别": [valid_room_levels[0], "", ""],
            "容量": [4, 2, 6],
            "性别限制": ["男", "女", "无限制"],
            "状态": ["可用", "维护中", ""],
            "对外租金": [800.00, 1200.00, ""],
            "成本租金": [500.00, 700.00, ""],
            "电表最大量程": [9999.99, "", ""],
            "水表最大量程": [9999.99, "", ""],
            "添加时间": [datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                         (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S'), 
                         ""],
            "房间设施": [
                f"{valid_facilities[0]}:2,{valid_facilities[1]}:1",
                f"{valid_facilities[0]}:2,{valid_facilities[1]}:1,{valid_facilities[2]}:1",
                ""
            ],
            "备注": ["朝南，带阳台", "", ""]
        }
        
        # 状态映射
        status_mapping = {
                RoomStatus.AVAILABLE.value: "可用",
                RoomStatus.FULL.value: "已满",
                RoomStatus.MAINTENANCE.value: "维护中",
                RoomStatus.CLOSED.value: "已关闭"
        }
        
        # 创建模板DataFrame
        df = pd.DataFrame(template_data)
        instructions = [
            "*必填项（导入时会校验非空）",
            "*必填项（导入时会校验非空）",
            "文本（可留空）",
            f"*必填项，必须是：{', '.join(valid_room_types)}",
            f"可选值: {', '.join(valid_room_levels)}（可留空）",
            "*必填项，必须为正整数",
            f"可选值: {', '.join(['男', '女', '无限制'])}",
            f"可选值: {', '.join([status_mapping.get(s.value, s.value) for s in RoomStatus])}",
            "非负数（可留空，默认为0）",
            "非负数（可留空，默认为0）",
            "非负数（可留空，默认9999.99）",
            "非负数（可留空，默认9999.99）",
            "日期时间（可留空，格式示例：YYYY-MM-DD HH:MM:SS）",
            f"格式：设施名:数量,设施名:数量（有效设施：{', '.join(valid_facilities[:5])}...）",
            "文本（可留空）"
        ]
        df.loc[-1] = instructions
        df.index = df.index + 1
        df = df.sort_index()
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='房间数据导入模板')
            worksheet = writer.sheets['房间数据导入模板']
            column_widths = [12, 10, 30, 12, 12, 8, 12, 10, 12, 12, 16, 16, 20, 30, 20]
            for i, width in enumerate(column_widths, 1):
                worksheet.column_dimensions[chr(64 + i)].width = width
            for cell in worksheet[1]:
                if "*必填项" in str(cell.value):
                    cell.font = cell.font.copy(color="FF0000")
        
        output.seek(0)
        filename = f"房间数据导入模板_{datetime.now().strftime('%Y%m%d')}.xlsx"
        logging.debug(f'模板生成成功: {filename}')
        
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='batch_import_export',
            action="下载房间数据导入模板",
            result="成功"
        )
        
        return send_file(
            output,
            download_name=filename,
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    except Exception as e:
        logging.error(f'模板生成失败: {str(e)}', exc_info=True)
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='batch_import_export',
            action=f"下载模板失败: {str(e)}",
            result="失败"
        )
        flash('模板下载失败，请联系管理员', 'danger')
        return redirect(url_for('room.manage'))

@room_import_export_bp.route('/export_facilities', methods=['GET'])
@login_required
@require_permission('room.export')
def export_facilities():
    """
    导出设施列表数据（按room_id排序，每个设施单独一行）
    """
    try:
        # 获取所有设施数据，按room_id排序
        facilities = RoomFacility.query.order_by(RoomFacility.room_id).all()
        
        # 准备导出数据
        data = []
        for facility in facilities:
            # 获取关联的房间信息
            room = Room.query.get(facility.room_id)
            if room:
                facility_data = {
                    '设施ID': facility.id,
                    '房间ID': facility.room_id,
                    '楼栋': room.building,
                    '房间号': room.room_number,
                    '设施名称': facility.name,
                    '设施数量': facility.quantity,
                    '设施状态': facility.status,
                    '设施备注': facility.remark or '',
                    '创建时间': facility.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    '更新时间': facility.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                }
                data.append(facility_data)
        
        # 创建DataFrame并导出为Excel
        df = pd.DataFrame(data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='设施数据')
        output.seek(0)
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='batch_import_export',
            action=f"导出设施数据成功，共{len(facilities)}条记录",
            result="成功"
        )
        # 记录日志
        logging.info(f"导出设施数据成功，共{len(facilities)}条记录")
        
        # 返回文件
        filename = f"房间设设施导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        return send_file(output, download_name=filename, as_attachment=True)
        
    except Exception as e:
        logging.error(f"导出设施数据失败: {str(e)}")
        flash('导出设施数据失败，请重试', 'error')
        return redirect(url_for('room.manage'))
