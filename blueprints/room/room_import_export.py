import os
from flask import Blueprint, request, flash, redirect, url_for, send_file
import logging
from utils.db import db
from models.room.room import Room, RoomStatus
from models.room.room_facility import RoomFacility  # 导入房间设施模型
from models.dorm.dorm import Dorm
from models.user.user import User
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.log import log_operation
from utils.lazy_imports import pd  # 延迟导入pandas，避免启动时加载重型库
import io
from datetime import datetime, timedelta
import traceback
from models.system_config.system_config import SystemConfig
from io import BytesIO
from utils.excel_date_utils import excel_date_utils
from decimal import Decimal

# 创建导入导出专用蓝图
room_import_export_bp = Blueprint(
    'room_import_export', 
    __name__, 
    url_prefix='/room', 
    template_folder='../../templates',
    static_folder='../../static',
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
        
        # 准备房间导出数据
        logging.debug('开始准备导出数据')
        data = []
        for room in rooms:
            try:
                # 使用房间设施模型的方法获取设施列表
                facilities = RoomFacility.query.filter_by(room_id=room.id).all()
                facilities_str = ','.join([f'{f.name}:{f.quantity}' for f in facilities])
                
                # 获取当前在住人员信息
                from models.dorm.dorm import Dorm
                from models.user.user import User
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
            
        logging.debug(f'房间数据准备完成，共{len(data)}条记录')
        
        # 准备设施数据（Sheet 2）
        logging.debug('开始准备设施数据')
        facility_data = []
        all_facilities = RoomFacility.query.order_by(RoomFacility.room_id).all()
        for facility in all_facilities:
            room = Room.query.get(facility.room_id)
            if room:
                facility_data.append({
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
                })
        logging.debug(f'设施数据准备完成，共{len(facility_data)}条记录')
        
        # 生成Excel（多sheet）
        df_rooms = pd.DataFrame(data)
        df_facilities = pd.DataFrame(facility_data)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_rooms.to_excel(writer, index=False, sheet_name='房间数据')
            df_facilities.to_excel(writer, index=False, sheet_name='设施数据')
        
        output.seek(0)
        filename = f"房间数据导出_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        logging.debug(f'Excel文件生成成功，文件名: {filename}')
        
        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='batch_import_export',
            action=f"导出房间数据，共 {len(rooms)} 条记录，设施数据 {len(all_facilities)} 条记录",
            result="成功"
        )
        logging.info(f'用户{current_user.id}成功导出房间数据和设施数据')
        
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
        
        # 白名单模式：只识别必填列和可选列，其余列全部自动忽略
        # 必填列（缺失时报错）
        required_columns = ['楼栋', '房间号', '房间类型', '容量', '性别限制']
        # 可选列（缺失时不报错）
        optional_columns = ['地址', '房间级别', '状态', '对外租金', '成本租金', '电表最大量程', '水表最大量程', '房间设施', '备注', '添加时间']
        # 列名别名映射：将Excel中可能出现的列名映射到标准列名
        column_alias_map = {
            '房间ID': ['房间ID（批量更新必填）', '房间ID(批量更新必填)', 'ID', 'id'],
        }
        # 所有可能需要识别的标准列名
        all_known_columns = set(required_columns) | set(optional_columns)

        # 构建列名映射：只保留白名单中的列，其余自动忽略
        column_mapping = {}
        ignored_columns = []
        for col in df.columns:
            # 先检查是否直接匹配标准列名
            if col in all_known_columns:
                continue  # 标准列名无需映射
            # 再检查是否匹配某个标准列名的别名
            matched = False
            for standard_name, aliases in column_alias_map.items():
                if col in aliases:
                    column_mapping[col] = standard_name
                    matched = True
                    break
            if not matched:
                ignored_columns.append(col)

        if ignored_columns:
            logging.info(f'导入房间数据：自动忽略未识别列 {ignored_columns}')

        # 重命名列以统一标准，并只保留白名单中的列（房间ID为别名映射列，导入时忽略）
        if column_mapping:
            df = df.rename(columns=column_mapping)
        whitelist_columns = [col for col in df.columns if col in all_known_columns]
        df = df[whitelist_columns]

        # 验证必要列
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
        
        # 调用模型的批量创建方法（始终只创建，不更新）
        success_create, success_update, model_errors, created_rooms = Room.bulk_create_or_update(rooms_data, override=False)
        
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
            "房间ID（批量更新必填）": ["", "1", ""],
            "楼栋": ["A栋", "B栋", "C栋"],
            "房间号": ["101", "202", "303"],
            "地址": ["XX路XX号X单元101室", "YY路YY号Y单元202室", ""],
            "房间类型": [valid_room_types[0], "", ""],
            "房间级别": [valid_room_levels[0], "", ""],
            "性别限制": ["男", "女", "无限制"],
            "容量": [4, 2, 6],
            "状态": ["可用", "维护中", ""],
            "对外租金": [800.00, 1200.00, ""],
            "成本租金": [500.00, 700.00, ""],
            "房间设施": [
                f"{valid_facilities[0]}:2,{valid_facilities[1]}:1",
                f"{valid_facilities[0]}:2,{valid_facilities[1]}:1,{valid_facilities[2]}:1",
                ""
            ],
            "电表最大量程": [9999.99, "", ""],
            "水表最大量程": [9999.99, "", ""],
            "添加时间": [datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 
                         (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S'), 
                         ""],
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
            "新增时留空，更新时必填",
            "*必填项（导入时会校验非空）",
            "*必填项（导入时会校验非空）",
            "文本（可留空）",
            f"*必填项，必须是：{', '.join(valid_room_types)}",
            f"可选值: {', '.join(valid_room_levels)}（可留空）",
            f"可选值: {', '.join(['男', '女', '无限制'])}",
            "*必填项，必须为正整数",
            f"可选值: {', '.join([status_mapping.get(s.value, s.value) for s in RoomStatus])}",
            "非负数（可留空，默认为0）",
            "非负数（可留空，默认为0）",
            f"格式：设施名:数量,设施名:数量（有效设施：{', '.join(valid_facilities[:5])}...）",
            "非负数（可留空，默认9999.99）",
            "非负数（可留空，默认9999.99）",
            "日期时间（可留空，格式示例：YYYY-MM-DD HH:MM:SS）",
            "文本（可留空）"
        ]
        df.loc[-1] = instructions
        df.index = df.index + 1
        df = df.sort_index()
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='房间数据导入模板')
            worksheet = writer.sheets['房间数据导入模板']
            column_widths = [18, 12, 10, 30, 12, 12, 12, 8, 10, 12, 12, 30, 16, 16, 20, 20]
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

@room_import_export_bp.route('/batch_update', methods=['POST'])
@login_required
@require_permission('room.edit')
def batch_update():
    """批量更新房间数据（基于房间ID）"""
    try:
        logging.debug('开始批量更新房间数据')
        if 'file' not in request.files:
            flash('请选择要导入的文件', 'danger')
            logging.error('批量更新房间数据失败：未选择文件')
            return redirect(url_for('room.manage'))

        file = request.files['file']
        if file.filename == '':
            flash('请选择要导入的文件', 'danger')
            logging.error('批量更新房间数据失败：未选择文件')
            return redirect(url_for('room.manage'))

        # 文件类型验证
        allowed_extensions = {'xlsx', 'xls'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        if file_ext not in allowed_extensions:
            flash(f'请上传Excel格式的文件（.xlsx 或 .xls），当前文件类型：.{file_ext}', 'danger')
            logging.error(f'批量更新房间数据失败：文件类型无效，当前文件类型：.{file_ext}')
            return redirect(url_for('room.manage'))

        try:
            file_content = file.read()
            file_bytes = BytesIO(file_content)
            file_bytes.seek(0)
            df = pd.read_excel(file_bytes)
        except Exception as e:
            detailed_error = f"文件解析失败：{str(e)}"
            flash(detailed_error, 'danger')
            logging.error(f'批量更新房间数据失败：文件解析失败 - {detailed_error}')
            return redirect(url_for('room.manage'))

        # 白名单模式：只识别必填列和可选列，其余列全部自动忽略
        # 必填列（缺失时报错）
        required_columns = ['房间ID']
        # 可选列（缺失时不报错）
        optional_columns = ['楼栋', '房间号', '地址', '房间类型', '房间级别', '性别限制', '容量', '状态', '对外租金', '成本租金', '房间设施', '电表最大量程', '水表最大量程', '备注', '添加时间']
        # 列名别名映射：将Excel中可能出现的列名映射到标准列名
        column_alias_map = {
            '房间ID': ['房间ID（批量更新必填）', '房间ID(批量更新必填)', 'ID', 'id'],
        }
        # 所有可能需要识别的标准列名
        all_known_columns = set(required_columns) | set(optional_columns)

        # 构建列名映射：只保留白名单中的列，其余自动忽略
        column_mapping = {}
        ignored_columns = []
        for col in df.columns:
            # 先检查是否直接匹配标准列名
            if col in all_known_columns:
                continue  # 标准列名无需映射
            # 再检查是否匹配某个标准列名的别名
            matched = False
            for standard_name, aliases in column_alias_map.items():
                if col in aliases:
                    column_mapping[col] = standard_name
                    matched = True
                    break
            if not matched:
                ignored_columns.append(col)

        if ignored_columns:
            logging.info(f'批量更新房间数据：自动忽略未识别列 {ignored_columns}')

        # 重命名列以统一标准，并只保留白名单中的列
        if column_mapping:
            df = df.rename(columns=column_mapping)
        whitelist_columns = [col for col in df.columns if col in all_known_columns]
        df = df[whitelist_columns]

        # 验证必要列
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            flash(f'导入失败：文件缺少必要的列 - {", " .join(missing_columns)}', 'danger')
            logging.error(f'批量更新房间数据失败：文件缺少必要的列 - {", ".join(missing_columns)}')
            return redirect(url_for('room.manage'))

        # 获取有效的配置数据
        valid_room_types = Room.get_valid_room_types()
        if not valid_room_types:
            flash('系统配置中未设置有效的房间类型，请先配置房间类型', 'danger')
            logging.error('批量更新房间数据失败：系统配置中未设置有效的房间类型')
            return redirect(url_for('room.manage'))

        # 状态映射
        STATUS_MAPPING = {
            '可用': RoomStatus.AVAILABLE.value,
            '已满': RoomStatus.FULL.value,
            '维护中': RoomStatus.MAINTENANCE.value,
            '已关闭': RoomStatus.CLOSED.value
        }

        # 获取有效的设施列表
        valid_facilities = RoomFacility.get_all_valid_facilities() or []

        # 预处理数据
        success_count = 0
        error_list = []
        processed_ids = {}  # 缓存已处理的ID，提高效率

        # 预加载楼栋+房间号映射，用于唯一性校验
        existing_rooms = Room.query.all()
        building_room_to_id = {(r.building, r.room_number): r.id for r in existing_rooms if r.building and r.room_number}
        excel_building_room_set = set()  # 跟踪Excel内部的楼栋+房间号组合

        for index, row in df.iterrows():
            row_num = index + 2
            try:
                # 提取房间ID（处理pandas将数字读取为float的问题）
                raw_id = row['房间ID']
                if pd.isna(raw_id):
                    record_id_str = ''
                elif isinstance(raw_id, float):
                    record_id_str = str(int(raw_id))
                else:
                    record_id_str = str(raw_id).strip()
                if not record_id_str:
                    error_list.append(f"第{row_num}行：房间ID不能为空（批量更新必须提供）")
                    continue

                # 验证ID格式
                try:
                    record_id = int(record_id_str)
                except ValueError:
                    error_list.append(f"第{row_num}行：房间ID必须是数字，当前值：{record_id_str}")
                    continue

                # 提取楼栋和房间号（可选字段，空值=不修改）
                building_val = row.get('楼栋')
                building = str(building_val).strip() if pd.notna(building_val) and str(building_val).strip() else ''
                room_number_val = row.get('房间号')
                room_number = ''
                if pd.notna(room_number_val) and str(room_number_val).strip():
                    try:
                        room_number_int = int(float(str(room_number_val).strip()))
                        room_number = str(room_number_int)
                    except ValueError:
                        room_number = str(room_number_val).strip()

                # 通过ID查询房间（使用缓存）
                cache_key = f"id_{record_id}"
                if cache_key not in processed_ids:
                    room = Room.query.get(record_id)
                    processed_ids[cache_key] = room
                room = processed_ids[cache_key]

                # 验证房间存在性
                if not room:
                    error_list.append(f"第{row_num}行：房间ID {record_id} 不存在")
                    continue

                # 楼栋+房间号唯一性校验（先校验再赋值）
                new_building = building if building else room.building
                new_room_number = room_number if room_number else room.room_number
                building_room_error = False
                if new_building and new_room_number:
                    combo = (new_building, new_room_number)
                    # 有修改楼栋或房间号时，校验新组合的唯一性
                    if building or room_number:
                        # 数据库唯一性校验
                        existing_id = building_room_to_id.get(combo)
                        if existing_id is not None and existing_id != record_id:
                            error_list.append(f"第{row_num}行：房间ID {record_id} 的楼栋+房间号({new_building}-{new_room_number})与数据库中已有记录冲突")
                            logging.warning(f"批量更新房间ID {record_id} 楼栋+房间号({new_building}-{new_room_number})与数据库中已有记录冲突")
                            building_room_error = True
                        # Excel内部唯一性校验
                        elif combo in excel_building_room_set:
                            error_list.append(f"第{row_num}行：房间ID {record_id} 的楼栋+房间号({new_building}-{new_room_number})与Excel中其他行冲突")
                            logging.warning(f"批量更新房间ID {record_id} 楼栋+房间号({new_building}-{new_room_number})与Excel中其他行冲突")
                            building_room_error = True
                        else:
                            excel_building_room_set.add(combo)
                    else:
                        # 未修改楼栋/房间号，仍需跟踪组合防止其他行冲突
                        excel_building_room_set.add(combo)

                # 更新楼栋和房间号（校验通过才赋值）
                if not building_room_error:
                    if building:
                        room.building = building
                    if room_number:
                        room.room_number = room_number

                # 处理房间类型
                room_type_val = row.get('房间类型')
                if pd.notna(room_type_val) and str(room_type_val).strip():
                    room_type_text = str(room_type_val).strip()
                    if room_type_text not in valid_room_types:
                        error_list.append(f"第{row_num}行：房间类型 '{room_type_text}' 无效，有效类型为：{', '.join(valid_room_types)}")
                        continue
                    room.room_type = room_type_text

                # 处理容量
                capacity_val = str(row.get('容量', '')).strip() if pd.notna(row.get('容量', '')) else ''
                if capacity_val:
                    try:
                        capacity = int(capacity_val)
                        if capacity <= 0:
                            error_list.append(f"第{row_num}行：容量必须为正整数")
                            continue
                        if capacity < room.current_occupancy:
                            error_list.append(f"第{row_num}行：房间容量({capacity})不能低于当前入住人数({room.current_occupancy})")
                            logging.warning(f"批量更新房间ID {room.id} 容量校验失败: 容量{capacity} < 当前入住{room.current_occupancy}")
                        else:
                            room.capacity = capacity
                    except ValueError:
                        error_list.append(f'第{row_num}行：容量必须是整数，当前值：{capacity_val}')
                        continue

                # 处理性别限制
                gender_val = row.get('性别限制')
                if pd.notna(gender_val) and str(gender_val).strip():
                    gender_text = str(gender_val).strip()
                    valid_gender_restrictions = Room.get_valid_gender_restrictions()
                    if gender_text in valid_gender_restrictions:
                        # 校验性别限制与入住人员是否冲突
                        if room.current_occupancy > 0 and gender_text != room.gender_restriction:
                            # 查询该房间当前入住用户的性别
                            active_dorms = Dorm.query.filter_by(room_id=room.id, status='active').all()
                            occupant_genders = set()
                            for dorm in active_dorms:
                                user = User.query.get(dorm.user_id)
                                if user and user.gender:
                                    occupant_genders.add(user.gender)
                            
                            # 检查冲突
                            conflict = False
                            if room.gender_restriction == '男' and '男' in occupant_genders and gender_text == '女':
                                conflict = True
                                conflict_msg = f"第{row_num}行：房间 {room.building}-{room.room_number} 有男性入住，不能改为\"女\""
                            elif room.gender_restriction == '女' and '女' in occupant_genders and gender_text == '男':
                                conflict = True
                                conflict_msg = f"第{row_num}行：房间 {room.building}-{room.room_number} 有女性入住，不能改为\"男\""
                            elif room.gender_restriction == '无限制' and occupant_genders and gender_text in ('男', '女'):
                                conflict = True
                                conflict_msg = f"第{row_num}行：房间 {room.building}-{room.room_number} 有不同性别入住，不能改为\"{gender_text}\""
                            
                            if conflict:
                                error_list.append(conflict_msg)
                                logging.warning(f"批量更新房间ID {room.id} 性别限制冲突: {conflict_msg}")
                            else:
                                room.gender_restriction = gender_text
                        else:
                            room.gender_restriction = gender_text

                # 处理状态
                status_val = row.get('状态')
                if pd.notna(status_val) and str(status_val).strip():
                    status_text = str(status_val).strip()
                    if status_text in STATUS_MAPPING:
                        new_status = STATUS_MAPPING[status_text]
                        # 检查是否有人住宿且尝试设置为关闭状态
                        if new_status == RoomStatus.CLOSED.value and room.current_occupancy > 0:
                            error_list.append(f"第{row_num}行：房间 {room.building}-{room.room_number} 有人住宿，无法设置为关闭状态")
                            continue
                        room.status = new_status

                # 处理租金
                try:
                    external_rent_val = row.get('对外租金')
                    if pd.notna(external_rent_val) and str(external_rent_val).strip():
                        room.external_rent = Decimal(str(external_rent_val))
                    cost_rent_val = row.get('成本租金')
                    if pd.notna(cost_rent_val) and str(cost_rent_val).strip():
                        room.cost_rent = Decimal(str(cost_rent_val))
                except (ValueError, TypeError):
                    error_list.append(f"第{row_num}行：租金必须为有效的数字")
                    continue

                # 处理备注
                remark_val = str(row.get('备注', '')).strip() if pd.notna(row.get('备注', '')) else ''
                if remark_val:
                    room.remark = remark_val

                # 处理地址
                address_val = str(row.get('地址', '')).strip() if pd.notna(row.get('地址', '')) else ''
                if address_val:
                    room.address = address_val

                # 处理房间设施（格式：设施名:数量,设施名:数量）
                facilities_val = row.get('房间设施')
                facilities_str = str(facilities_val).strip() if pd.notna(facilities_val) and str(facilities_val).strip() else ''
                if facilities_str:
                    facilities = []
                    facility_parse_error = False
                    facility_items = facilities_str.split(',')
                    for item in facility_items:
                        if ':' in item:
                            name, quantity_str = item.split(':', 1)
                            name = name.strip()
                            quantity_str = quantity_str.strip()
                            # 验证设施名称是否有效
                            if name not in valid_facilities:
                                error_list.append(
                                    f"第{row_num}行：设施 '{name}' 无效，有效设施为：{', '.join(valid_facilities[:5])}..."
                                )
                                facility_parse_error = True
                                break
                            try:
                                quantity = int(quantity_str)
                                if quantity > 0:
                                    facilities.append({'name': name, 'quantity': quantity})
                            except ValueError:
                                error_list.append(f"第{row_num}行：设施 '{name}' 的数量必须为整数")
                                facility_parse_error = True
                                break
                    if not facility_parse_error and facilities:
                        try:
                            result = RoomFacility.bulk_update_facilities(room.id, facilities, remark="批量更新设施")
                            if not result:
                                error_list.append(f"第{row_num}行：房间ID {room.id} 的设施更新失败")
                        except Exception as e:
                            error_list.append(f"第{row_num}行：设施处理失败 - {str(e)}")
                            logging.error(f'批量更新房间ID {room.id} 设施处理失败 - {str(e)}')

                # 处理水电表最大量程
                try:
                    electric_max_val = row.get('电表最大量程')
                    if pd.notna(electric_max_val) and str(electric_max_val).strip():
                        room.electric_meter_max = Decimal(str(electric_max_val))
                    water_max_val = row.get('水表最大量程')
                    if pd.notna(water_max_val) and str(water_max_val).strip():
                        room.water_meter_max = Decimal(str(water_max_val))
                except (ValueError, TypeError):
                    error_list.append(f"第{row_num}行：水电表最大量程必须为有效的数字")
                    continue

                success_count += 1

            except Exception as e:
                error_list.append(f"第{row_num}行：数据处理失败 - {str(e)}")
                logging.error(f'批量更新房间数据失败：第{row_num}行数据处理失败 - {str(e)}')
                continue

        # 如果有错误，回滚并返回
        if error_list:
            db.session.rollback()
            message = f"数据验证失败：共{len(error_list)}条错误<br>" + "<br>".join(error_list[:5])
            if len(error_list) > 5:
                message += f"<br>... 还有 {len(error_list)-5} 条错误"
            flash(message, 'danger')
            logging.error(f'批量更新房间数据失败：数据验证失败，共{len(error_list)}条错误')
            return redirect(url_for('room.manage'))

        # 提交事务
        db.session.commit()

        logging.info(f'批量更新房间数据成功，共更新{success_count}条记录，操作人：{current_user.id}')
        flash(f"批量更新完成，成功更新{success_count}条记录", 'success')
        return redirect(url_for('room.manage'))

    except Exception as e:
        db.session.rollback()
        detailed_error = f"批量更新过程出错：{str(e)}"
        logging.error(f'批量更新房间数据失败：{detailed_error}，操作人：{current_user.id}\n{traceback.format_exc()}')
        flash(detailed_error, 'danger')
        return redirect(url_for('room.manage'))


