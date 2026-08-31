from flask import Blueprint, request, render_template, send_file, jsonify
from flask_login import login_required
from sqlalchemy import or_
from utils.db import db
from models.user import User
from models.department import Department
from models.room import Room
from models.utility_room_bill_record import RoomUtilityRecord
from models.utility_room_bill_checkout import CheckoutUtilityRecord
from models.utility_room_bill_occupant import RoomUtilityOccupant
import logging
from io import BytesIO
from datetime import datetime
from urllib.parse import quote
from utils.log import log_operation
# 导入权限装饰器
from utils.auth import require_permission

# 创建蓝图
utility_user_records_detail_bp = Blueprint('utility_user_records_detail', __name__, url_prefix='/utility')

@utility_user_records_detail_bp.route('/user_records_detail')
@login_required
@require_permission('utility.view')
def user_records_detail():
    """
    用户水电费详情页面
    展示指定筛选条件下的用户水电费详情列表
    通过在住人员费用子表和退宿人员费用子表返回的用户id和房间id查询对应用户信息和房间信息
    账期通过费用主表获取
    """
    try:
        # 获取筛选参数
        billing_period = request.args.get('billing_period', '')
        building = request.args.get('building', '')
        department = request.args.get('department', '')
        user_type = request.args.get('type', '')
        search_keyword = request.args.get('search', '')
        
        # 分页参数
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('pageSize', 20))
        
        # 构建查询 - 在住人员费用
        occupant_query = db.session.query(
            User.id,
            User.name,
            User.gender,
            Department.name.label('department'),
            User.position,
            RoomUtilityOccupant.record_id,
            RoomUtilityOccupant.room_id,
            RoomUtilityOccupant.total_fee,
            RoomUtilityRecord.billing_period,
            Room.building,
            Room.room_number,
            RoomUtilityOccupant.stay_days
        ).join(
            User, User.id == RoomUtilityOccupant.user_id
        ).outerjoin(
            Department, User.department_id == Department.id
        ).join(
            Room, Room.id == RoomUtilityOccupant.room_id
        ).join(
            RoomUtilityRecord, RoomUtilityRecord.record_id == RoomUtilityOccupant.record_id
        )
        
        # 构建查询 - 退宿人员费用
        checkout_query = db.session.query(
            User.id,
            User.name,
            User.gender,
            Department.name.label('department'),
            User.position,
            CheckoutUtilityRecord.record_id,
            CheckoutUtilityRecord.room_id,
            CheckoutUtilityRecord.payable_fee,
            RoomUtilityRecord.billing_period,
            Room.building,
            Room.room_number,
            CheckoutUtilityRecord.user_period_days
        ).join(
            User, User.id == CheckoutUtilityRecord.user_id
        ).outerjoin(
            Department, User.department_id == Department.id
        ).join(
            Room, Room.id == CheckoutUtilityRecord.room_id
        ).join(
            RoomUtilityRecord, RoomUtilityRecord.record_id == CheckoutUtilityRecord.record_id
        )
        
        # 应用筛选条件 - 账期是必需的筛选条件
        if billing_period:
            occupant_query = occupant_query.filter(RoomUtilityRecord.billing_period == billing_period)
            checkout_query = checkout_query.filter(RoomUtilityRecord.billing_period == billing_period)
        else:
            # 如果没有选择账期，则不查询任何数据
            occupant_query = occupant_query.filter(False)
            checkout_query = checkout_query.filter(False)
        
        if building:
            occupant_query = occupant_query.filter(Room.building == building)
            checkout_query = checkout_query.filter(Room.building == building)
        
        if department:
            occupant_query = occupant_query.filter(Department.name == department)
            checkout_query = checkout_query.filter(Department.name == department)
        
        if search_keyword:
            search_filter = or_(
                User.name.contains(search_keyword),
                Room.room_number.contains(search_keyword)
            )
            occupant_query = occupant_query.filter(search_filter)
            checkout_query = checkout_query.filter(search_filter)
        
        # 类型筛选并处理用户数据
        users_data = {}
        total_count = 0
        # 记录在退宿费用表中存在的用户ID
        checkout_user_ids = set()
        
        # 先处理在住人员数据
        if user_type != '退宿':
            # 查询所有符合条件的在住人员数据
            occupant_result = occupant_query.order_by(User.id, Room.id).all()
            total_count += len(occupant_result)
            
            # 处理在住人员数据
            for row in occupant_result:
                user_id = row.id
                if user_id not in users_data:
                    # 初始化用户数据
                    users_data[user_id] = {
                        'user_id': user_id,
                        'name': row.name,
                        'gender': row.gender,
                        'department': row.department,
                        'position': row.position,
                        'total_fee': 0,
                        'rooms': [],
                        'stay_days': [],
                        'type': '在住'
                    }
                
                # 添加房间信息和费用明细
                room_info = f"{row.building}{row.room_number}"
                room_id = getattr(row, 'room_id', None)
                users_data[user_id]['rooms'].append(room_info)
                # 添加房间ID信息
                if 'room_ids' not in users_data[user_id]:
                    users_data[user_id]['room_ids'] = []
                users_data[user_id]['room_ids'].append(room_id)
                users_data[user_id]['stay_days'].append(f"{row.stay_days}天")
                users_data[user_id]['total_fee'] += float(row.total_fee or 0)
                
                # 添加费用明细（结构化格式，方便前端处理）
                if 'fee_details' not in users_data[user_id]:
                    users_data[user_id]['fee_details'] = []
                # 获取记录ID（从RoomUtilityOccupant中获取）
                record_id = row.record_id  # 使用属性访问方式，避免索引位置变化的风险
                users_data[user_id]['fee_details'].append({
                    'room': room_info,
                    'room_id': room_id,
                    'fee': float(row.total_fee or 0),
                    'days': f"{row.stay_days}天",
                    'record_id': record_id
                })
                
                # 保存第一条记录的ID作为用户主记录ID，用于账期链接
                if 'record_id' not in users_data[user_id]:
                    users_data[user_id]['record_id'] = record_id
        
        # 再处理退宿人员数据
        if user_type != '在住':
            # 查询所有符合条件的退宿人员数据
            checkout_result = checkout_query.order_by(User.id, Room.id).all()
            total_count += len(checkout_result)
            
            # 处理退宿人员数据
            for row in checkout_result:
                user_id = row.id
                # 记录退宿费用表中的用户ID
                checkout_user_ids.add(user_id)
                if user_id not in users_data:
                    # 初始化用户数据
                    users_data[user_id] = {
                        'user_id': user_id,
                        'name': row.name,
                        'gender': row.gender,
                        'department': row.department,
                        'position': row.position,
                        'total_fee': 0,
                        'rooms': [],
                        'stay_days': [],
                        'type': '退宿'
                    }
                else:
                    # 如果用户已经存在（同时有在住和退宿记录），保持'在住'类型
                    users_data[user_id]['type'] = '在住'
                
                # 添加房间信息和费用明细
                room_info = f"{row.building}{row.room_number}"
                room_id = getattr(row, 'room_id', None)
                users_data[user_id]['rooms'].append(room_info)
                # 添加房间ID信息
                if 'room_ids' not in users_data[user_id]:
                    users_data[user_id]['room_ids'] = []
                users_data[user_id]['room_ids'].append(room_id)
                # 使用user_period_days字段获取退宿当月已住天数
                users_data[user_id]['stay_days'].append(f"{row.user_period_days}天")
                users_data[user_id]['total_fee'] += float(row.payable_fee or 0)
                
                # 添加费用明细（结构化格式，方便前端处理）
                if 'fee_details' not in users_data[user_id]:
                    users_data[user_id]['fee_details'] = []
                # 获取记录ID（从CheckoutUtilityRecord中获取）
                record_id = row.record_id  # 使用属性访问方式，避免索引位置变化的风险
                users_data[user_id]['fee_details'].append({
                    'room': room_info,
                    'room_id': room_id,
                    'fee': float(row.payable_fee or 0),
                    'days': f"{row.user_period_days}天",
                    'record_id': record_id
                })
                
                # 保存第一条记录的ID作为用户主记录ID，用于账期链接
                if 'record_id' not in users_data[user_id]:
                    users_data[user_id]['record_id'] = record_id
        
        # 对用户数据进行处理，添加多房间标识和换宿判断
        users_list = []
        for user_data in users_data.values():
            # 添加is_multi_room标识，用于前端判断是否显示展开/折叠按钮
            user_data['is_multi_room'] = len(user_data['rooms']) > 1
            
            # 判断换宿：同个账期内有多个房间费用产生，且用户不在退宿费用表中
            if user_data['is_multi_room'] and user_data['user_id'] not in checkout_user_ids:
                user_data['type'] = '换宿'
                
            users_list.append(user_data)
        
        # 根据用户类型筛选数据
        if user_type == '换宿':
            # 如果选择换宿类型，则只显示类型为换宿的用户
            users_list = [user for user in users_list if user['type'] == '换宿']
            total_count = len(users_list)
        elif user_type == '在住':
            # 如果选择在住类型，则只显示类型为在住的用户
            users_list = [user for user in users_list if user['type'] == '在住']
            total_count = len(users_list)
        elif user_type == '退宿':
            # 如果选择退宿类型，则只显示类型为退宿的用户
            users_list = [user for user in users_list if user['type'] == '退宿']
            total_count = len(users_list)
        elif user_type == '在住+换宿':
            # 如果选择在住+换宿类型，则显示类型为在住或换宿的用户
            users_list = [user for user in users_list if user['type'] == '在住' or user['type'] == '换宿']
            total_count = len(users_list)
        
        # 排序并计算总页数
        users_list.sort(key=lambda x: x['user_id'])
        total_pages = (total_count + page_size - 1) // page_size
        
        # 计算分页的起始和结束索引
        start_idx = (page - 1) * page_size
        end_idx = min(page * page_size, len(users_list))
        
        # 获取当前页的用户数据
        paginated_users = users_list[start_idx:end_idx]
        
        # 获取账期列表用于筛选器
        billing_periods = db.session.query(RoomUtilityRecord.billing_period).distinct().order_by(RoomUtilityRecord.billing_period.desc()).all()
        billing_periods = [bp[0] for bp in billing_periods]
        
        # 获取楼栋列表用于筛选器
        buildings = db.session.query(Room.building).distinct().order_by(Room.building).all()
        buildings = [b[0] for b in buildings]
        
        # 获取部门列表用于筛选器
        departments = [d.name for d in Department.query.filter_by(status='正常').order_by(Department.name).all()]
        

        
        # 为每个用户对象添加账期信息
        for user in paginated_users:
            user['billing_period'] = billing_period
            
        # 准备模板数据
        data = {
            'title': "用户水电费查询",
            'users': paginated_users,
            'total_count': total_count,
            'current_page': page,
            'total_pages': total_pages,
            'page_size': page_size,
            'billing_periods': billing_periods,
            'buildings': buildings,
            'departments': departments,
            'current_filters': {
                'billing_period': billing_period,
                'building': building,
                'department': department,
                'type': user_type,
                'search': search_keyword
            }
        }
        
        return render_template('utility_bill/utility_user_records_detail.html', **data)
        
    except Exception as e:
        logging.error(f"获取用户水电费详情失败: {str(e)}")
        return render_template(
            'utility_bill/utility_user_records_detail.html',
            title="用户水电费查询",
            users=[],
            total_count=0,
            current_page=1,
            total_pages=0,
            page_size=20,
            billing_periods=[],
            buildings=[],
            departments=[],
            current_filters={}
        )

@utility_user_records_detail_bp.route('/export_user_records_excel', methods=['GET'])
@login_required
@require_permission('utility.export')
def export_user_records_excel():
    """
    导出用户水电费详情为Excel文件
    包含用户id、工号、用户姓名、用户性别、部门、职位、房间号、类型、应付金额（多房间时汇总）和备注（每个房间金额）
    """
    import pandas as pd  # 延迟导入，避免启动时加载重型库
    try:
        # 获取筛选参数
        billing_period = request.args.get('billing_period', '')
        building = request.args.get('building', '')
        department = request.args.get('department', '')
        user_type = request.args.get('type', '')
        search_keyword = request.args.get('search', '')
        
        # 验证必填参数
        if not billing_period:
            return jsonify({
                'success': False,
                'message': '请选择账期'
            }), 400
        
        # 构建查询 - 在住人员费用
        occupant_query = db.session.query(
            User.id,
            User.student_id,
            User.name,
            User.gender,
            Department.company.label('company'),
            Department.name.label('department'),
            User.position,
            RoomUtilityOccupant.record_id,
            RoomUtilityOccupant.room_id,
            RoomUtilityOccupant.total_fee,
            RoomUtilityRecord.billing_period,
            Room.building,
            Room.room_number,
            RoomUtilityOccupant.stay_days
        ).join(
            User, User.id == RoomUtilityOccupant.user_id
        ).outerjoin(
            Department, User.department_id == Department.id
        ).join(
            Room, Room.id == RoomUtilityOccupant.room_id
        ).join(
            RoomUtilityRecord, RoomUtilityRecord.record_id == RoomUtilityOccupant.record_id
        )
        
        # 构建查询 - 退宿人员费用
        checkout_query = db.session.query(
            User.id,
            User.student_id,
            User.name,
            User.gender,
            Department.company.label('company'),
            Department.name.label('department'),
            User.position,
            CheckoutUtilityRecord.record_id,
            CheckoutUtilityRecord.room_id,
            CheckoutUtilityRecord.payable_fee,
            RoomUtilityRecord.billing_period,
            Room.building,
            Room.room_number,
            CheckoutUtilityRecord.user_period_days
        ).join(
            User, User.id == CheckoutUtilityRecord.user_id
        ).outerjoin(
            Department, User.department_id == Department.id
        ).join(
            Room, Room.id == CheckoutUtilityRecord.room_id
        ).join(
            RoomUtilityRecord, RoomUtilityRecord.record_id == CheckoutUtilityRecord.record_id
        )
        
        # 应用筛选条件
        occupant_query = occupant_query.filter(RoomUtilityRecord.billing_period == billing_period)
        checkout_query = checkout_query.filter(RoomUtilityRecord.billing_period == billing_period)
        
        if building:
            occupant_query = occupant_query.filter(Room.building == building)
            checkout_query = checkout_query.filter(Room.building == building)
        
        if department:
            occupant_query = occupant_query.filter(Department.name == department)
            checkout_query = checkout_query.filter(Department.name == department)
        
        if search_keyword:
            search_filter = or_(
                User.name.contains(search_keyword),
                Room.room_number.contains(search_keyword)
            )
            occupant_query = occupant_query.filter(search_filter)
            checkout_query = checkout_query.filter(search_filter)
        
        # 类型筛选并处理用户数据
        users_data = {}
        # 记录在退宿费用表中存在的用户ID
        checkout_user_ids = set()
        
        # 先处理在住人员数据
        if user_type != '退宿':
            occupant_result = occupant_query.order_by(User.id, Room.id).all()
            
            # 处理在住人员数据
            for row in occupant_result:
                user_id = row.id
                if user_id not in users_data:
                    # 初始化用户数据
                    users_data[user_id] = {
                        'user_id': user_id,
                        'student_id': row.student_id or '',
                        'name': row.name,
                        'gender': row.gender,
                        'company': row.company or '',
                        'department': row.department,
                        'position': row.position,
                        'total_fee': 0,
                        'rooms': [],
                        'room_fees': [],
                        'stay_days_info': [],  # 添加住宿天数信息
                        'type': '在住'
                    }
                
                # 添加房间信息和费用明细
                room_info = f"{row.building}{row.room_number}"
                users_data[user_id]['rooms'].append(room_info)
                users_data[user_id]['room_fees'].append(f"{room_info}: {float(row.total_fee or 0):.2f}元")
                users_data[user_id]['stay_days_info'].append(f"{room_info}: {row.stay_days}天")  # 保存住宿天数信息
                users_data[user_id]['total_fee'] += float(row.total_fee or 0)
        
        # 再处理退宿人员数据
        if user_type != '在住':
            checkout_result = checkout_query.order_by(User.id, Room.id).all()
            
            # 处理退宿人员数据
            for row in checkout_result:
                user_id = row.id
                # 记录退宿费用表中的用户ID
                checkout_user_ids.add(user_id)
                if user_id not in users_data:
                    # 初始化用户数据
                    users_data[user_id] = {
                        'user_id': user_id,
                        'student_id': row.student_id or '',
                        'name': row.name,
                        'gender': row.gender,
                        'company': row.company or '',
                        'department': row.department,
                        'position': row.position,
                        'total_fee': 0,
                        'rooms': [],
                        'room_fees': [],
                        'stay_days_info': [],  # 添加住宿天数信息
                        'type': '退宿'
                    }
                else:
                    # 如果用户已经存在（同时有在住和退宿记录），保持'在住'类型
                    users_data[user_id]['type'] = '在住'
                    # 如果用户已存在但没有stay_days_info字段，则添加
                    if 'stay_days_info' not in users_data[user_id]:
                        users_data[user_id]['stay_days_info'] = []
                
                # 添加房间信息和费用明细
                room_info = f"{row.building}{row.room_number}"
                users_data[user_id]['rooms'].append(room_info)
                users_data[user_id]['room_fees'].append(f"{room_info}: {float(row.payable_fee or 0):.2f}元")
                users_data[user_id]['stay_days_info'].append(f"{room_info}: {row.user_period_days}天")  # 保存退宿当月已住天数信息
                users_data[user_id]['total_fee'] += float(row.payable_fee or 0)
        
        # 对用户数据进行处理，添加多房间标识和换宿判断
        export_data = []
        
        for user_data in users_data.values():
            # 添加is_multi_room标识和换宿判断
            is_multi_room = len(user_data['rooms']) > 1
            
            # 判断换宿：同个账期内有多个房间费用产生，且用户不在退宿费用表中
            if is_multi_room and user_data['user_id'] not in checkout_user_ids:
                user_data['type'] = '换宿'
            
            # 类型已经是中文，不需要转换
            user_type_text = user_data['type']
            
            # 格式化房间号（多房间用逗号分隔）
            rooms_text = ','.join(user_data['rooms'])
            
            # 格式化备注（每个房间金额）
            remarks = ';'.join(user_data['room_fees'])
            
            # 格式化当月已住天数（如果有多房间，用分号分隔）
            stay_days_text = ''
            if 'stay_days_info' in user_data and user_data['stay_days_info']:
                stay_days_text = ';'.join(user_data['stay_days_info'])
            
            # 构建导出数据行
            export_data.append({
                '用户ID': user_data['user_id'],
                '工号': user_data['student_id'],
                '用户姓名': user_data['name'],
                '用户性别': user_data['gender'],
                '公司': user_data['company'],
                '部门': user_data['department'],
                '职位': user_data['position'],
                '账期': billing_period,
                '类型': user_type_text,
                '房间号': rooms_text,
                '当月已住天数': stay_days_text,
                '应付金额': round(user_data['total_fee'], 2),
                '备注': remarks
            })
        
        # 根据用户类型筛选数据
        if user_type == '换宿':
            export_data = [item for item in export_data if item['类型'] == '换宿']
        elif user_type == '在住':
            export_data = [item for item in export_data if item['类型'] == '在住']
        elif user_type == '退宿':
            export_data = [item for item in export_data if item['类型'] == '退宿']
        elif user_type == '在住+换宿':
            export_data = [item for item in export_data if item['类型'] == '在住' or item['类型'] == '换宿']
        
        # 如果没有数据，返回提示
        if not export_data:
            return jsonify({
                'success': False,
                'message': f'没有找到符合条件的用户数据'
            }), 404
        
        # 创建DataFrame
        df = pd.DataFrame(export_data)
        
        # 设置数值格式化
        df['应付金额'] = df['应付金额'].apply(lambda x: f"{x:.2f}")
        
        # 创建Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # 设置工作表名称
            sheet_name = f"用户费用详情_{billing_period}"
            # 写入数据
            df.to_excel(writer, index=False, sheet_name=sheet_name)
            
            # 获取工作表对象
            worksheet = writer.sheets[sheet_name]
            
            # 调整列宽
            for column_cells in worksheet.columns:
                length = max(len(str(cell.value)) for cell in column_cells) + 2
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(length, 30)  # 最大宽度限制
        
        # 准备响应
        output.seek(0)
        
        # 创建类型映射，直接使用中文类型名
        valid_types = ['在住', '退宿', '换宿', '在住+换宿']
        
        # 构建文件名部分，只包含非空的筛选条件
        filename_parts = ["用户费用详情", billing_period]
        
        # 添加楼栋筛选条件
        if building:
            filename_parts.append(f"楼栋{building}")
        
        # 添加部门筛选条件
        if department:
            filename_parts.append(f"部门{department}")
        
        # 添加用户类型筛选条件
        if user_type and user_type in valid_types:
            filename_parts.append(f"{user_type}")
        
        # 添加搜索关键词筛选条件
        if search_keyword:
            filename_parts.append(f"关键词{search_keyword}")
        
        # 添加时间戳确保唯一性
        filename_parts.append(datetime.now().strftime('%Y%m%d_%H%M%S'))
        
        # 组合所有部分生成最终文件名
        filename = "_".join(filename_parts) + ".xlsx"
        # 对中文文件名进行URL编码
        encoded_filename = quote(filename, encoding='utf-8')
        
        # 记录操作日志
        try:
            from flask_login import current_user
            log_operation(
                user_id=current_user.id if current_user.is_authenticated else None,
                module="utility",
                operation_type="batch_import_export",
                action=f"导出用户费用详情成功，[账期: {billing_period}, 导出{len(export_data)}条记录至Excel",
                result="成功"
            )
        except:
            pass
        
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            download_name=filename,
            as_attachment=True
        )
        
    except Exception as e:
        logging.error(f"导出用户费用详情失败: {str(e)}")
        try:
            from flask_login import current_user
            log_operation(
                user_id=current_user.id if current_user.is_authenticated else None,
                module="utility",
                operation_type="batch_import_export",
                action=f"导出用户费用详情失败: {str(e)}",
                result="失败"
            )
        except:
            pass
        return jsonify({
            'success': False,
            'message': '导出用户费用详情失败',
            'error': str(e)
        }), 500