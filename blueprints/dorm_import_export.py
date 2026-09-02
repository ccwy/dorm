from flask import Blueprint, request, make_response, abort, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.log import log_operation
from utils.lazy_imports import pd, Font, Alignment  # 延迟导入重型库
from io import BytesIO
import requests
from urllib.parse import quote
from datetime import datetime, timedelta  # 修改：移除date导入
import traceback
import re
import logging
from dateutil import parser

# 导入数据模型
from models.dorm import Dorm
from models.user import User
from models.room import Room, Bed
from utils.db import db
# 导入Excel日期处理工具
from utils.excel_date_utils import excel_date_utils

# 导出蓝图
dorm_import_export_bp = Blueprint('dorm_import_export', __name__, url_prefix='/dorm_import_export')



def is_date_in_range(record_date, start_date, end_date):
    """判断日期是否在指定范围内"""
    if not record_date:
        return False
    try:
        # 修改：使用datetime而非date
        record_dt = datetime.strptime(record_date, '%Y-%m-%d')
        start_dt = datetime.strptime(start_date, '%Y-%m-%d') if start_date else datetime.strptime('1900-01-01', '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d') if end_date else datetime.now()
        return start_dt <= record_dt <= end_dt
    except ValueError:
        return False

# 添加一个辅助函数来格式化日期，移除'T'字符
def format_date(date_str):
    if not date_str or date_str == '未知':
        return date_str
    # 检查是否包含'T'字符
    if 'T' in date_str:
    # 分割日期和时间部分，只保留日期部分
        date_part = date_str.split('T')[0]
        return date_part
    return date_str
    
@dorm_import_export_bp.route('/residents', methods=['GET'])
@login_required
@require_permission('dorm.export')
def export_residents():
    """导出在住人员数据及换宿舍历史记录"""
    try:
        # 获取所有筛选参数
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        name = request.args.get('name', '').strip()
        department = request.args.get('department', '').strip()
        gender = request.args.get('gender', '').strip()
        room_number = request.args.get('room_number', '').strip()
        export_all = request.args.get('export_all', 'false').lower() == 'true'

        # 准备当前住宿数据
        current_data = []
        # 准备换宿舍历史记录数据
        history_data = []
        
        if export_all:
            # 记录日志
            logging.info(f'开始导出全部在住人员数据，操作人ID：{current_user.id}')
            # 获取所有活跃状态的住宿记录，不进行任何筛选
            active_dorms = Dorm.query.filter_by(status='active').all()
        else:
            # 记录日志
            logging.info(f'开始导出在住人员数据，筛选条件：开始日期={start_date}, 结束日期={end_date}, 姓名={name}, 部门={department}, 性别={gender}, 房间号={room_number}，操作人ID：{current_user.id}')
            # 获取所有活跃状态的住宿记录并进行筛选
            active_dorms = Dorm.query.filter_by(status='active').all()
            
            # 进行日期范围过滤
            if not export_all and (start_date or end_date):
                filtered_dorms = []
                for dorm in active_dorms:
                    check_in_date = dorm.check_in_date.strftime('%Y-%m-%d') if dorm.check_in_date else None
                    if not check_in_date or is_date_in_range(check_in_date, start_date, end_date):
                        filtered_dorms.append(dorm)
                active_dorms = filtered_dorms

        # 存储已处理的用户ID，避免重复处理
        # 已经在上一步获取并过滤了活跃住宿记录
        processed_user_ids = set()
        
        for dorm in active_dorms:
            user = dorm.user
            room = dorm.room
            
            # 检查是否已经处理过该用户
            if user.id in processed_user_ids:
                continue
            
            # 根据用户筛选条件过滤（仅在不导出全部时应用）
            if not export_all:
                if name and name not in user.name:
                    continue
                if department and department not in user.department:
                    continue
                if gender and gender != user.gender:
                    continue
                if room_number and room_number not in f"{room.building}{room.room_number}":
                    continue
            
            processed_user_ids.add(user.id)
            
            user_basic = {
                '姓名': user.name,
                '性别': user.gender,
                '年龄': user.get_age(),
                '公司': user.company,
                '部门': user.department,
                '职位': user.position
            }
            
            # 添加当前住宿信息
            current_data.append({
                **user_basic,
                '楼栋': room.building,
                '房间号': room.room_number,
                '入住日期': format_date(dorm.check_in_date.strftime('%Y-%m-%d')),
                '住宿天数': dorm.stay_days,
                '累计住宿天数': sum(d.stay_days for d in dorm.dorm_chain)
            })
            
            # 处理换宿舍历史记录
            # 获取完整的住宿链
            dorm_chain = dorm.dorm_chain
            
            for dorm_record in dorm_chain:
                record_room = dorm_record.room
                
                # 检查记录是否符合导出条件
                # 如果导出全部，则不进行任何筛选
                include_record = True
                
                if not export_all:
                    include_record = False
                    
                    # 检查记录是否在时间范围内
                    # 处理入住日期检查
                    if dorm_record.check_in_date:
                        check_in_str = dorm_record.check_in_date.strftime('%Y-%m-%d')
                        if is_date_in_range(check_in_str, start_date, end_date):
                            include_record = True
                    
                    # 处理退房日期检查
                    if dorm_record.check_out_date and not include_record:
                        check_out_str = dorm_record.check_out_date.strftime('%Y-%m-%d')
                        if is_date_in_range(check_out_str, start_date, end_date):
                            include_record = True
                    
                    # 当前住宿且未退房的记录
                    if dorm_record.status == 'active' and not dorm_record.check_out_date:
                        include_record = True
                    
                    # 如果指定了房间号，需要筛选
                    if room_number and not f"{record_room.building}{record_room.room_number}".__contains__(room_number):
                        include_record = False
                
                if include_record:
                    # 构建换宿历史记录
                    history_record = {
                        **user_basic,
                        '楼栋': record_room.building,
                        '房间号': record_room.room_number,
                        '入住日期': format_date(dorm_record.check_in_date.strftime('%Y-%m-%d')) if dorm_record.check_in_date else '未知',
                        '退房日期': format_date(dorm_record.check_out_date.strftime('%Y-%m-%d')) if dorm_record.check_out_date else '当前住宿',
                        '住宿天数': dorm_record.stay_days,
                        '是否当前住宿': '是' if dorm_record.status == 'active' else '否'
                    }
                    
                    # 避免重复添加当前住宿记录到历史记录中
                    if not (dorm_record.status == 'active' and not dorm_record.check_out_date):
                        history_data.append(history_record)
        
        # 生成Excel文件（包含两个工作表）
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # 当前住宿信息表
            pd.DataFrame(current_data).to_excel(
                writer, index=False, sheet_name='当前住宿信息'
            )
            # 换宿舍历史记录表（如果有数据）
            if history_data:
                pd.DataFrame(history_data).to_excel(
                    writer, index=False, sheet_name='换宿舍历史记录'
                )

        output.seek(0)

        # 处理中文文件名编码
        filename = f"住宿数据及换宿记录_{datetime.now().strftime('%Y%m%d')}.xlsx"
        encoded_filename = quote(filename)
        
        # 构建下载响应
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
        response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        log_operation(
            user_id=current_user.id,
            module='dorm',
            operation_type='batch_import_export',
            action=f"成功: {len(current_data)}条住宿记录, {len(history_data)}条换宿记录",
            result="成功"
        )
        # 记录日志
        logging.info(f'成功导出在住人员数据，共导出{len(current_data)}条住宿记录，{len(history_data)}条换宿记录，操作人ID：{current_user.id}')
        return response

    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='dorm',
            operation_type='batch_import_export',
            action=f"导出失败: {str(e)}",
            result="失败"
        )
        # 记录日志
        logging.error(f'导出在住人员数据失败：{str(e)}，操作人ID：{current_user.id}')
        abort(500, description=f"导出失败: {str(e)}")

@dorm_import_export_bp.route('/import-residents', methods=['POST'])
@login_required
@require_permission('dorm.import')
def import_residents():
    """批量导入在住人员并自动分配宿舍"""
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
    
    try:
        # 检查是否有文件上传
        if 'file' not in request.files:
            error_msg = '请选择要导入的Excel文件'
            if is_ajax:
                return jsonify({"success": False, "message": error_msg}), 400
            flash(error_msg, 'danger')
            # 记录日志
            logging.error(f'导入在住人员数据失败：{error_msg}，操作人ID：{current_user.id}')
            return redirect(url_for('dorm.dorm_query'))
        
        file = request.files['file']
        
        # 检查文件名
        if file.filename == '':
            error_msg = '未选择文件'
            if is_ajax:
                return jsonify({"success": False, "message": error_msg}), 400
            flash(error_msg, 'danger')
            # 记录日志
            logging.error(f'导入在住人员数据失败：{error_msg}，操作人ID：{current_user.id}')
            return redirect(url_for('dorm.dorm_query'))
        
        # 检查文件类型
        if not file.filename.endswith(('.xlsx', '.xls')):
            error_msg = '请上传Excel格式的文件（.xlsx或.xls）'
            if is_ajax:
                return jsonify({"success": False, "message": error_msg}), 400
            flash(error_msg, 'danger')
            # 记录日志
            logging.error(f'导入在住人员数据失败：{error_msg}，操作人ID：{current_user.id}')
            return redirect(url_for('dorm.dorm_query'))
        
        # 检查文件大小（限制10MB）
        if file.content_length > 10 * 1024 * 1024:
            error_msg = '文件大小不能超过10MB'
            if is_ajax:
                return jsonify({"success": False, "message": error_msg}), 400
            flash(error_msg, 'danger')
            # 记录日志
            logging.error(f'导入在住人员数据失败：{error_msg}，操作人ID：{current_user.id}')    
            return redirect(url_for('dorm.dorm_query'))
        
        # 读取Excel文件
        try:
            # 读取Excel文件的第一个工作表
             # 关键修复2：将文件流转换为BytesIO对象
            file_content = file.read()  # 读取文件内容为字节流
            file_bytes = BytesIO(file_content)  # 转换为BytesIO（支持seekable）
            file_bytes.seek(0)  # 重置指针到开头
            df = pd.read_excel(file_bytes)
            
            # 检查必要的列是否存在
            required_columns = ['姓名', '楼栋', '房间号', '入住日期']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                error_msg = f'Excel文件缺少必要的列：{", ".join(missing_columns)}'
                if is_ajax:
                    return jsonify({"success": False, "message": error_msg}), 400
                flash(error_msg, 'danger')
                # 记录日志
                logging.error(f'导入在住人员数据失败：{error_msg}，操作人ID：{current_user.id}')
                return redirect(url_for('dorm.dorm_query'))
            
            # 检查姓名重复
            name_counts = df['姓名'].value_counts()
            duplicate_names = [name for name, count in name_counts.items() if count > 1]
            if duplicate_names:
                error_msg = f'Excel文件中存在重复的姓名：{", ".join(duplicate_names)}'
                if is_ajax:
                    return jsonify({"success": False, "message": error_msg}), 400
                flash(error_msg, 'danger')
                # 记录日志
                logging.error(f'导入在住人员数据失败：{error_msg}，操作人ID：{current_user.id}')
                return redirect(url_for('dorm.dorm_query'))
            
            # 处理每一行数据
            success_count = 0
            fail_records = []
            
            # 批量处理日期
            check_in_dates = df['入住日期'].tolist()
            try:
                # 使用excel_date_utils实例调用parse_excel_date方法
                parsed_check_in_dates = excel_date_utils.parse_excel_date(check_in_dates, field_name='入住日期')
                logging.info("批量解析入住日期成功")
            except Exception as e:
                error_msg = f'批量解析入住日期失败：{str(e)}'
                logging.error(f'导入在住人员数据失败：{error_msg}，操作人ID：{current_user.id}')
                if is_ajax:
                    return jsonify({"success": False, "message": error_msg}), 500
                flash(error_msg, 'danger')
                return redirect(url_for('dorm.dorm_query'))
            
            for index, row in df.iterrows():
                row_num = index + 2  # 行号从2开始（Excel行号）
                
                try:
                    # 获取基本信息
                    name = str(row['姓名']).strip()
                    building = str(row['楼栋']).strip()
                    room_number = str(row['房间号']).strip()
                    
                    # 验证基本信息
                    if not all([name, building, room_number, check_in_dates[index]]):
                        fail_records.append({
                            'row': row_num,
                            'name': name,
                            'room': f'{building}-{room_number}',
                            'reason': '姓名、楼栋、房间号或入住日期不能为空'
                        })
                        # 记录日志
                        logging.error(f'导入在住人员数据失败：姓名、楼栋、房间号或入住日期不能为空，操作人ID：{current_user.id}')
                        continue
                    
                    # 检查日期是否成功解析
                    if not parsed_check_in_dates[index]:
                        fail_records.append({
                            'row': row_num,
                            'name': name,
                            'room': f'{building}-{room_number}',
                            'reason': f'日期格式错误: 无法解析 {check_in_dates[index]}'
                        })
                        # 记录日志
                        logging.error(f'导入在住人员数据失败：日期格式错误，操作人ID：{current_user.id}')
                        continue
                    
                    # 使用解析后的datetime对象
                    check_in_date = parsed_check_in_dates[index]
                    
                    # 根据姓名查找用户ID
                    user = User.query.filter_by(name=name).first()
                    if not user:
                        fail_records.append({
                            'row': row_num,
                            'name': name,
                            'room': f'{building}-{room_number}',
                            'reason': '未找到该用户',
                            'raw_data': dict(row)
                        })
                        # 记录日志
                        logging.error(f'导入在住人员数据失败：未找到该用户{user.name}，操作人ID：{current_user.id}')
                        continue
                    
                    # 添加用户状态验证 - 检查用户是否在职
                    if not user.is_status():
                        fail_records.append({
                            'row': row_num,
                            'name': name,
                            'room': f'{building}-{room_number}',
                            'reason': '该用户非在职状态，无法分配宿舍',
                            'raw_data': dict(row)
                        })
                        # 记录日志
                        logging.error(f'导入在住人员数据失败：该用户{user.name}非在职状态，无法分配宿舍，操作人ID：{current_user.id}')
                        continue

                    # 验证用户角色（禁止为超级管理员分配宿舍）
                    if user.user_role and user.user_role.code == 'super_admin':
                        fail_records.append({
                            'row': row_num,
                            'name': name,
                            'room': f'{building}-{room_number}',
                            'reason': '禁止为超级管理员分配宿舍',
                            'raw_data': dict(row)
                        })
                        # 记录日志
                        logging.error(f'导入在住人员数据失败：禁止为超级管理员分配宿舍，操作人ID：{current_user.id}')
                        continue
                    
                    # 检查是否已有活跃住宿记录
                    existing_dorm = Dorm.query.filter_by(user_id=user.id, status='active').first()
                    if existing_dorm:
                        fail_records.append({
                            'row': row_num,
                            'name': name,
                            'room': f'{building}-{room_number}',
                            'reason': '该人员已有活跃的住宿记录',
                            'raw_data': dict(row)
                        })
                        # 记录日志
                        logging.error(f'导入在住人员数据失败：该人员{user.name}已有活跃的住宿记录，操作人ID：{current_user.id}')
                        continue
                    
                    # 根据楼栋和房间号查找房间ID
                    room = Room.query.filter_by(building=building, room_number=room_number).first()
                    if not room:
                        fail_records.append({
                            'row': row_num,
                            'name': name,
                            'room': f'{building}-{room_number}',
                            'reason': '未找到该房间',
                            'raw_data': dict(row)
                        })
                        # 记录日志
                        logging.error(f'导入在住人员数据失败：{room.building}{room.room_number}未找到该房间，操作人ID：{current_user.id}')
                        continue
                    
                    # 验证房间状态
                    if room.current_occupancy >= room.capacity:
                        fail_records.append({
                            'row': row_num,
                            'name': name,
                            'room': f'{building}-{room_number}',
                            'reason': '房间已满',
                            'raw_data': dict(row)
                        })
                        # 记录日志
                        logging.error(f'导入在住人员数据失败：{room.building}{room.room_number}房间已满，操作人ID：{current_user.id}')
                        continue

                    # 添加用户性别和房间性别验证
                    if room.gender_restriction != '无限制' and user.gender != room.gender_restriction:
                        fail_records.append({
                            'row': row_num,
                            'name': name,
                            'room': f'{building}-{room_number}',
                            'reason': f'用户性别({user.gender})与房间性别限制({room.gender_restriction})不匹配',
                            'raw_data': dict(row)
                        })
                        # 记录日志
                        logging.error(f'导入在住人员数据失败：用户{user.name}性别({user.gender})与房间{room.building}{room.room_number}性别限制({room.gender_restriction})不匹配，操作人ID：{current_user.id}')
                        continue
                    
                    # 查找可用床位
                    available_bed = Bed.query.filter_by(
                        room_id=room.id,
                        status='available'
                    ).order_by(Bed.bed_number).first()
                    
                    if not available_bed:
                        fail_records.append({
                            'row': row_num,
                            'name': name,
                            'room': f'{building}-{room_number}',
                            'reason': '房间无可用床位',
                            'raw_data': dict(row)
                        })
                        # 记录日志
                        logging.error(f'导入在住人员数据失败：{room.building}{room.room_number}房间无可用床位，操作人ID：{current_user.id}')
                        continue
                    
                    # 创建分配记录
                    Dorm.create_allocation(
                        user_id=user.id,
                        room_id=room.id,
                        bed_id=available_bed.id,
                        check_in_date=check_in_date,  # 已改为datetime类型
                        remarks=f'批量导入分配，导入时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
                    )
                    # 记录日志
                    logging.info(f'导入在住人员数据成功,导入时间：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}，操作人ID：{current_user.id}')
                    success_count += 1
                    
                except Exception as e:
                    fail_records.append({
                        'row': row_num,
                        'name': str(row['姓名']) if '姓名' in row else f'行{row_num}',
                        'room': f"{str(row['楼栋']) if '楼栋' in row else ''}-{str(row['房间号']) if '房间号' in row else ''}",
                        'reason': f'处理失败: {str(e)}',
                        'raw_data': dict(row)
                    })
                    # 记录日志
                    logging.error(f'导入在住人员数据失败,处理失败: {str(e)}，操作人ID：{current_user.id}')
                    continue
            
            # 提交事务
            db.session.commit()
            
            # 记录日志
            logging.info(f'成功导入在住人员数据，共导入{len(df)}条记录，成功{success_count}条，失败{len(fail_records)}条，操作人ID：{current_user.id}')
            
            # 记录操作日志
            log_operation(
                user_id=current_user.id,
                action=f"批量导入住宿记录成功: {success_count}条, 失败: {len(fail_records)}条",
                result="成功",
                module='dorm',
                operation_type='batch_import_export'
            )
            
            # 构建响应消息
            message = f'批量导入完成，成功导入{success_count}条记录，失败{len(fail_records)}条记录'
            
            if is_ajax:
                return jsonify({
                    "success": True,
                    "message": message,
                    "data": {
                        "success_count": success_count,
                        "fail_count": len(fail_records),
                        "fail_records": fail_records
                    }
                })
            
            # 处理非AJAX响应
            flash(message, 'success')
            if fail_records:
                flash(f'失败记录：{len(fail_records)}条', 'warning')
            # 记录日志
            logging.error(f'导入在住人员数据失败,失败记录：{len(fail_records)}条，操作人ID：{current_user.id}')
            return redirect(url_for('dorm.dorm_query'))
            
        except Exception as e:
            db.session.rollback()
            error_msg = f'解析Excel文件失败: {str(e)}'
            log_operation(
                user_id=current_user.id,
                action=f"导入失败: {error_msg}",
                result="失败",
                module='dorm',
                operation_type='batch_import'
            )
            # 记录日志
            logging.error(f'导入在住人员数据失败：{error_msg}，操作人ID：{current_user.id}')
            if is_ajax:
                return jsonify({"success": False, "message": error_msg}), 500
            
            flash(error_msg, 'danger')
            return redirect(url_for('dorm.dorm_query'))
            
    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            action=f"导入失败: {str(e)}",
            result="失败",
            module='dorm',
            operation_type='batch_import'
        )
        # 记录日志
        logging.error(f'导入在住人员数据失败：{error_msg}，操作人ID：{current_user.id}')
        if is_ajax:
            return jsonify({
                "success": False,
                "message": f'导入失败：{str(e)}'
            }), 500
        
        flash(f'导入失败：{str(e)}', 'danger')
        return redirect(url_for('dorm.dorm_query'))

@dorm_import_export_bp.route('/download-import-template', methods=['GET'])
@login_required
@require_permission('dorm.import')
def download_import_template():
    """下载导入模板Excel文件"""
    try:
        # 创建模板数据
        data = {
            '姓名': ['张三', '李四'],
            '楼栋': ['A', 'B'],
            '房间号': ['101', '202'],
            '入住日期': ['2023-09-01', '2023-09-01'],
            '备注（可选）': ['', '']
        }
        
        df = pd.DataFrame(data)
        
        # 写入Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='住宿分配导入模板')
            
            # 获取工作表并添加格式说明
            worksheet = writer.sheets['住宿分配导入模板']
            
            # 添加日期格式说明
            worksheet['G1'] = '支持的日期格式：\n- YYYY-MM-DD（推荐）\n- YYYY/MM/DD\n- YYYY年MM月DD日\n- 其他常见格式'
            worksheet['G1'].font = Font(color="FF0000", size=10)
            worksheet['G1'].alignment = Alignment(wrap_text=True, vertical='top')
            
            # 调整列宽
            worksheet.column_dimensions['A'].width = 10
            worksheet.column_dimensions['B'].width = 8
            worksheet.column_dimensions['C'].width = 8
            worksheet.column_dimensions['D'].width = 15
            worksheet.column_dimensions['E'].width = 15
            worksheet.column_dimensions['G'].width = 25
        
        output.seek(0)
        
        # 构建响应
        filename = f"住宿分配导入模板.xlsx"
        encoded_filename = quote(filename)
        
        response = make_response(output.getvalue())
        response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{encoded_filename}"
        response.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        
        log_operation(
            user_id=current_user.id,
            module='dorm',
            operation_type='batch_import',
            action="下载住宿分配导入模板",
            result="成功"
        )
        # 记录日志
        logging.info(f'成功下载住宿分配导入模板，操作人ID：{current_user.id}')
        return response
        
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='dorm',
            operation_type='batch_import',
            action=f"下载住宿分配导入模板失败: {str(e)}",
            result="失败"
        )
        # 记录日志
        logging.error(f'下载住宿分配导入模板失败：{error_msg}，操作人ID：{current_user.id}')
        abort(500, description=f"下载模板失败: {str(e)}")
    