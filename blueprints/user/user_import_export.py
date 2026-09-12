from flask import Blueprint, request, flash, redirect, url_for, send_file
from flask_login import login_required, current_user
from utils.db import db
from models.user.user import User
from models.dorm.dorm import Dorm
from utils.log import log_operation
from utils.user_utils import (
    get_user_model_fields, 
    get_importable_fields, 
    process_field_value,
    generate_student_id,
    generate_username
) #引入工具类
from utils.excel_date_utils import excel_date_utils
import re  # 正则表达式模块，用于处理字符串
import datetime
import logging
from utils.lazy_imports import pd  # 延迟导入pandas，避免启动时加载重型库
from io import BytesIO
from models.system_config.system_config import SystemConfig  # 导入系统配置模型
from models.role import Role  # 导入角色模型

from utils.auth import require_permission

# 创建导入导出蓝图
user_import_export_bp = Blueprint('user_import_export', __name__, url_prefix='/user/import-export')


# ------------------------------
# 公共辅助函数
# ------------------------------

def _validate_uploaded_file(operation_label='操作'):
    """检查文件上传，返回 (file, error_response) 元组。error_response 为 None 时表示校验通过。"""
    if 'file' not in request.files:
        flash('未找到上传文件', 'danger')
        logging.error(f"{operation_label}，未找到上传文件")
        return None, redirect(url_for('user.manage'))
    
    file = request.files['file']
    if file.filename == '' or not (file.filename.endswith('.xlsx') or file.filename.endswith('.xls')):
        flash('请上传有效的Excel文件（.xlsx或.xls）', 'danger')
        logging.error(f"{operation_label}，上传文件格式无效")
        return None, redirect(url_for('user.manage'))
    
    return file, None


def _read_excel_with_dtype(file_bytes):
    """读取Excel并构建dtype字典，返回 (df, excel_columns, display_to_field) 元组。"""
    importable_fields = get_importable_fields()
    display_to_field = {v: k for k, v in importable_fields.items()}
    
    # 首先读取第一行获取列名
    temp_df = pd.read_excel(file_bytes, nrows=1)
    file_bytes.seek(0)  # 重置文件指针
    
    # 构建dtype字典，将特定字段设置为字符串类型
    str_columns = []
    for col in temp_df.columns:
        if col in display_to_field and display_to_field[col] in ['phone', 'id_card', 'emergency_phone']:
            str_columns.append(col)
    
    # 读取整个Excel，将特定列设为字符串类型
    dtype_dict = {col: str for col in str_columns}
    df = pd.read_excel(file_bytes, dtype=dtype_dict)
    excel_columns = df.columns.tolist()
    
    # 重新获取映射（确保与实际列一致）
    importable_fields = get_importable_fields()
    display_to_field = {v: k for k, v in importable_fields.items()}
    
    return df, excel_columns, display_to_field


def _batch_parse_hire_dates(df):
    """批量解析入职日期，返回 parsed_hire_dates。失败时抛出异常由调用方处理。"""
    hire_date_values = df.get('入职日期', pd.Series([None] * len(df)))
    parsed_hire_dates = excel_date_utils.parse_excel_date(hire_date_values, field_name='入职日期')
    logging.info("日期时间解析成功")
    return parsed_hire_dates


def _process_field_value(field_name, value, parsed_hire_dates, row_idx):
    """统一处理日期/字符串/布尔字段转换，返回处理后的值或 None（表示跳过）。"""
    # 日期字段
    if field_name == 'hire_date':
        parsed_date = parsed_hire_dates[row_idx]
        return parsed_date if parsed_date else None
    
    # 字符串数字字段（Excel中纯数字会被pandas读取为float，需先转int再转str）
    if field_name in ['phone', 'id_card', 'emergency_phone']:
        if isinstance(value, (int, float)):
            return str(int(value))
        return str(value).strip()
    
    # 密码字段 - 确保转为字符串（Excel中纯数字密码会被pandas读取为float）
    if field_name == 'password':
        if isinstance(value, (int, float)):
            return str(int(value))
        return str(value).strip()
    
    # 布尔字段
    if field_name in ['is_active', 'is_banned']:
        if isinstance(value, str):
            stripped = value.strip().lower()
            if stripped in ['true', '是', '1']:
                return True
            elif stripped in ['false', '否', '0']:
                return False
            else:
                return None  # 无效值，跳过
        return value
    
    # 通用字符串处理
    if isinstance(value, str):
        return value.strip()
    
    return value


def _sync_company_department(user_data, operation_label='操作', row_label=''):
    """当 company 有值但 department 为空时，将 company 赋给 department。"""
    company_val = user_data.get('company')
    dept_val = user_data.get('department')
    if company_val and not dept_val:
        user_data['department'] = company_val
        logging.info(f"{operation_label}，{row_label}用户有公司'{company_val}'但无部门，自动将公司名设为部门")


def _build_department_cache(include_no_company_suffix=False):
    """预加载部门缓存字典，返回缓存dict。

    参数:
        include_no_company_suffix: 是否额外缓存无公司后缀的版本（如 "技术部_"），
                                   import_users 需要此选项以匹配无公司后缀的查询。
    """
    from models.department.department import Department
    dept_records = Department.query.all()
    department_cache = {}
    for dept in dept_records:
        key = f"{dept.name}_{dept.company or ''}"
        department_cache[key] = (dept.id, dept.company)
        if include_no_company_suffix:
            department_cache[f"{dept.name}_"] = (dept.id, dept.company)
    return department_cache


def _commit_batch_result(result, current_user, operation_type, summary_template,
                         is_create=False, change_detail_fn=None):
    """合并的结果提交函数：flush → auto_complete_info → 创建操作记录 → commit → 日志记录 → flash消息

    参数:
        result: batch_create_users/batch_update_users 的返回结果
        current_user: 当前登录用户
        operation_type: 操作类型 ('import' / 'batch_update')
        summary_template: 操作记录摘要模板，如 '批量导入新增用户：{name}'
        is_create: 是否为创建操作（需要add_all+flush分配ID）
        change_detail_fn: 可选，生成change_detail的函数，接收user返回dict；
                          默认返回 {'name': user.name, 'student_id': user.student_id}

    返回:
        True(成功提交) / False(没有成功记录) / None(提交失败，已回滚)
    """
    if not result['success']:
        return False
    
    try:
        if is_create:
            db.session.add_all(result['success'])
        db.session.flush()
        
        # 批量补全信息
        for user in result['success']:
            user.auto_complete_info()
        
        # 批量创建操作记录
        from models.user.user_operation_record import UserOperationRecord
        for user in result['success']:
            detail = change_detail_fn(user) if change_detail_fn else {
                'name': user.name,
                'student_id': user.student_id
            }
            UserOperationRecord.create_record(
                target_user_id=user.id,
                operation_type=operation_type,
                operator_id=current_user.id,
                operator_name=current_user.name,
                change_detail=detail,
                summary=summary_template.format(name=user.name)
            )
        
        # 一次性提交所有变更
        db.session.commit()
        
        success_count = len(result['success'])
        failed_count = len(result['failed'])
        skipped_count = result.get('skipped', 0)
        
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='batch_import_export',
            action=f"{operation_type}用户数据，成功{success_count}条" + (f"，跳过{skipped_count}条（无变化）" if skipped_count else "") + (f"，失败{failed_count}条" if failed_count else ""),
            result="成功"
        )
        
        # flash消息
        parts = [f'成功{operation_type}{success_count}条']
        if skipped_count:
            parts.append(f'跳过{skipped_count}条（无变化）')
        if failed_count > 0:
            parts.append(f'失败{failed_count}条')
        msg = '，'.join(parts)
        flash(msg, 'success')
        if failed_count > 0:
            flash('查看日志了解失败详情', 'warning')
        
        logging.info(f"{operation_type}用户数据操作，成功{success_count}条记录")
        return True
        
    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='batch_import_export',
            action=f"尝试{operation_type}用户数据失败: {str(e)}",
            result="失败"
        )
        flash(f'数据提交失败: {str(e)}', 'danger')
        logging.error(f"{operation_type}用户数据操作，提交数据库失败: {str(e)}")
        return None


@user_import_export_bp.route('/export', methods=['GET'])
@login_required
@require_permission('user.export')
def export_users():
    """导出用户数据为Excel"""
    try:
        users = User.query.all()
        if not users:
            flash('没有可导出的用户数据', 'info')
            logging.info("导出用户数据操作，未找到任何用户记录")
            return redirect(url_for('user.manage'))
        
        model_fields = get_user_model_fields()
        
        export_fields = {k: v for k, v in model_fields.items() if k != 'password_hash'}
        field_names = list(export_fields.keys())
        
        # 构建导出数据
        data = []
        # 先获取每个用户的最新住宿记录
        user_dorm_map = {}
        for user in users:
            latest_dorm = Dorm.get_user_latest_dorm(user.id)
            user_dorm_map[user.id] = latest_dorm
            
        for user in users:
            row = {}
            latest_dorm = user_dorm_map.get(user.id)
            # 判断用户是否在住
            is_currently_boarding = latest_dorm is not None and latest_dorm.status == 'active'
            
            for field_name in field_names:
                # 补充计算字段（如年龄、籍贯）
                if field_name == 'age' and not user.age:
                    user.age = user.get_age()
                if field_name == 'birth_date' and not user.birth_date:
                    user.birth_date = user.get_birth_date_from_id()
                if field_name == 'native_place' and not user.native_place:
                    user.native_place = user.extract_native_place()
                
                # 使用Dorm模型获取宿舍相关信息，只对在住用户显示住宿信息
                if field_name == 'is_boarding':
                    field_value = is_currently_boarding
                elif field_name == 'room_number':
                    field_value = f"{latest_dorm.room.building}{latest_dorm.room.room_number}" if is_currently_boarding and latest_dorm and latest_dorm.room else ""
                elif field_name == 'days_stayed':
                    field_value = latest_dorm.stay_days if is_currently_boarding and latest_dorm else ''
                elif field_name == 'checkin_date':
                    field_value = latest_dorm.check_in_date if is_currently_boarding and latest_dorm else None
                else:
                    field_value = getattr(user, field_name, "")
                    
                row[export_fields[field_name]] = process_field_value(field_name, field_value)
            
            data.append(row)
        
        # 生成Excel
        df = pd.DataFrame(data)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='用户数据')
        
        output.seek(0)
        
        # 日志记录
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='batch_import_export',
            action=f"导出用户数据（{len(export_fields)}个字段），成功，共导出{len(users)}条记录",
            result="成功"
        )
        logging.info(f"导出用户数据操作，成功导出 {len(users)} 条记录")
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            download_name=f"导出用户数据_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
        )
    
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='batch_import_export',
            action=f"尝试导出用户数据失败: {str(e)}",
            result="失败"
        )
        flash(f'导出失败: {str(e)}', 'danger')
        logging.error(f"导出用户数据操作失败，异常信息: {str(e)}")
        return redirect(url_for('user.manage'))

# ------------------------------
# 导入功能（优化版：批量处理提升速度）
# ------------------------------
@user_import_export_bp.route('/import', methods=['POST'])
@login_required
@require_permission('user.import')
def import_users():
    """从Excel导入用户数据"""
    try:
        # 检查文件
        file, error_response = _validate_uploaded_file('导入用户数据操作')
        if error_response:
            return error_response
        
        # 读取Excel
        file_content = file.read()
        file_bytes = BytesIO(file_content)
        file_bytes.seek(0)
        
        # 读取Excel并构建dtype字典
        df, excel_columns, display_to_field = _read_excel_with_dtype(file_bytes)
        logging.info('开始导入用户')
        
        # 检查必要字段（显示名）
        required_display = ['姓名', '性别']
        if not all(req in excel_columns for req in required_display):
            missing = [req for req in required_display if req not in excel_columns]
            msg = f'Excel缺少必要列：{", ".join(missing)}'
            flash(msg, 'danger')
            logging.error(f"导入用户数据操作，Excel缺少必要列：{', '.join(missing)}")
            return redirect(url_for('user.manage'))
        
        # 提示未识别字段
        extra_cols = [col for col in excel_columns if col not in display_to_field.keys()]
        if extra_cols:
            flash(f'忽略未识别字段：{", ".join(extra_cols)}', 'warning')
            logging.warning(f"导入用户数据操作，Excel包含未识别字段：{', '.join(extra_cols)}")

        # 一次性读取数据库中已存在的工号和用户名（优化点）
        existing_data = User.query.with_entities(User.student_id, User.username).all()
        existing_ids = {item.student_id for item in existing_data}
        existing_usernames = {item.username for item in existing_data}
        
        # 跟踪当前批次已生成的工号和用户名，避免同批次重复（优化点）
        batch_ids = set()
        batch_usernames = set()

        logging.info(f"导入用户数据操作，开始处理 {len(df)} 条记录")
        # 准备用户数据列表
        user_data_list = []
        now = datetime.datetime.now()
        # 从Role表获取所有角色，构建名称到ID的映射
        all_roles = Role.query.order_by(Role.sort_order).all()
        role_name_to_id = {r.name: r.id for r in all_roles}
        valid_role_names = [r.name for r in all_roles]
        # 获取默认角色（普通用户）
        default_role = Role.query.filter_by(code='user').first()
        default_role_id = default_role.id if default_role else None
        
        # 提取所有入职时间值进行批量解析
        try:
            parsed_hire_dates = _batch_parse_hire_dates(df)
        except Exception as e:
            msg = f'批量解析入职日期失败：{str(e)}'
            flash(msg, 'danger')
            logging.error(f'批量解析入职日期失败：{str(e)}')
            return redirect(url_for('user.manage'))

        for row_num, row in df.iterrows():
            current_row = row_num + 2  # 行号从2开始
            
            # 跳过空行（姓名为空）
            if pd.isna(row['姓名']):
                logging.warning(f"导入用户数据操作，第{current_row}行：姓名为空，已跳过")
                continue
            
            # 获取姓名并验证
            name = str(row['姓名']).strip() if not pd.isna(row['姓名']) else ""
            if not name:
                flash(f"第{current_row}行：姓名为空，已跳过", 'warning')
                logging.warning(f"导入用户数据操作，第{current_row}行：姓名为空，已跳过")
                continue
                
            # 优先使用Excel中提供的工号，如果没有或已存在则生成新工号
            student_id = None
            if '工号' in excel_columns and not pd.isna(row['工号']):
                # 尝试使用Excel中提供的工号
                provided_student_id = str(row['工号']).strip()
                # 检查是否已存在于数据库或当前批次
                if provided_student_id not in existing_ids and provided_student_id not in batch_ids:
                    student_id = provided_student_id
                else:
                    # 工号已存在，生成新工号
                    flash(f"第{current_row}行：提供的工号'{provided_student_id}'已存在，将自动生成新工号", 'warning')
                    logging.warning(f"导入用户数据操作，第{current_row}行：提供的工号'{provided_student_id}'已存在")
                    
            # 如果没有提供有效的工号，则生成新工号
            if not student_id:
                student_id = generate_student_id(
                    existing_ids.union(batch_ids),  # 合并已有和当前批次的工号
                    max_attempts=1000
                )
                if not student_id:
                    flash(f"第{current_row}行：无法生成唯一工号，已跳过", 'danger')
                    logging.error(f"导入用户数据操作，第{current_row}行：无法生成唯一工号")
                    continue
                
            # 优先使用Excel中提供的用户名，如果没有或已存在则生成新用户名
            username = None
            if '用户名' in excel_columns and not pd.isna(row['用户名']):
                # 尝试使用Excel中提供的用户名
                provided_username = str(row['用户名']).strip()
                # 检查是否已存在于数据库或当前批次
                if provided_username not in existing_usernames and provided_username not in batch_usernames:
                    username = provided_username
                else:
                    # 用户名已存在，生成新用户名
                    flash(f"第{current_row}行：提供的用户名'{provided_username}'已存在，将自动生成新用户名", 'warning')
                    logging.warning(f"导入用户数据操作，第{current_row}行：提供的用户名'{provided_username}'已存在")
                    
            # 如果没有提供有效的用户名，则生成新用户名
            if not username:
                username = generate_username(
                    name,
                    existing_usernames.union(batch_usernames),  # 合并已有和当前批次的用户名
                    max_attempts=1000
                )
                if not username:
                    flash(f"第{current_row}行：无法生成唯一用户名，已跳过", 'danger')
                    logging.error(f"导入用户数据操作，第{current_row}行：无法生成唯一用户名")
                    continue
            
            # 添加到批次集合，防止同批次重复
            batch_ids.add(student_id)
            batch_usernames.add(username)
            
            # 处理密码（只获取明文，不生成哈希，由模型处理）
            if '密码' in excel_columns and not pd.isna(row['密码']):
                pwd_val = row['密码']
                password = str(int(pwd_val)) if isinstance(pwd_val, (int, float)) else str(pwd_val).strip()
            else:
                password = SystemConfig.get_config_value('USER_DEFAULT_PASSWORD', '123456')
            
            # 基础用户数据（不包含password_hash，改为传递password）
            user_data = {
                'student_id': student_id,
                'username': username,
                'name': name,
                'password': password,  # 传递明文密码，由模型处理哈希
                'created_at': now,
                'updated_at': now
            }
            
            # 处理性别
            if '性别' in excel_columns and not pd.isna(row['性别']):
                user_data['gender'] = str(row['性别']).strip()
            else:
                user_data['gender'] = ''  # 会在模型验证中被捕获为错误
            
            # 处理角色
            if '角色' in excel_columns and not pd.isna(row['角色']):
                role_val = str(row['角色']).strip()
                # 通过角色名称查找角色ID
                role_id = role_name_to_id.get(role_val)
                if role_id is None:
                    # 角色名称不匹配，使用默认角色
                    role_id = default_role_id
                    logging.info(f"导入用户数据操作，第{current_row}行：角色'{role_val}'不存在，已设置为默认角色")
                user_data['role_id'] = role_id
            else:
                user_data['role_id'] = default_role_id
                logging.info(f"导入用户数据操作，第{current_row}行：角色为空，已设置为默认角色")
            
            # 处理其他字段
            for display_name, field_name in display_to_field.items():
                # 跳过已处理的字段
                if display_name in ['姓名', '性别', '角色', '密码']:
                    continue
                    
                # 检查Excel中是否有该字段且值不为空
                if display_name in excel_columns and not pd.isna(row[display_name]):
                    value = row[display_name]
                    
                    # 使用公共函数统一处理字段值转换
                    processed = _process_field_value(field_name, value, parsed_hire_dates, row_num)
                    if processed is not None:
                        user_data[field_name] = processed
                
                # 只在Excel中没有提供布尔字段时使用默认值
                if field_name == 'is_active' and '是否激活账号' not in excel_columns and 'is_active' not in user_data:
                    user_data['is_active'] = bool(SystemConfig.get_config_value('USER_DEFAULT_ACTIVE', True))
                    logging.info(f"导入用户数据操作，第{current_row}行：Excel中未提供'是否激活账号'字段，已设置为默认值")
                if field_name == 'is_banned' and '是否允许登录' not in excel_columns and 'is_banned' not in user_data:
                    user_data['is_banned'] = bool(SystemConfig.get_config_value('USER_DEFAULT_BANNED', False))
                    logging.info(f"导入用户数据操作，第{current_row}行：Excel中未提供'是否允许登录'字段，已设置为默认值")
            
            # 同步公司和部门到部门管理模块
            _sync_company_department(user_data, '导入用户数据操作', f'第{current_row}行：')
            
            user_data_list.append(user_data)
        logging.info(f"导入用户数据操作，准备导入 {len(user_data_list)} 条记录")
        
        # 预加载部门缓存，避免循环内DB查询
        department_cache = _build_department_cache(include_no_company_suffix=True)

        # 调用模型方法批量创建用户对象（不提交事务），传递查重集合和部门缓存
        import_result = User.batch_create_users(
            user_data_list,
            existing_student_ids=existing_ids,      # 已在第180行查询
            existing_usernames=existing_usernames,    # 已在第182行查询
            department_cache=department_cache
        )
        logging.info(f"导入用户数据操作，调用模型方法批量创建用户对象，返回结果：{import_result}")
        
        # 处理结果
        if import_result['failed']:
            # 收集错误信息并显示
            error_messages = []
            for error in import_result['failed']:
                error_messages.append(f"第{error['row']}行: {'; '.join(error['errors'])}")
                logging.error(f"导入用户数据操作，第{error['row']}行: {'; '.join(error['errors'])}")
            
            flash(f"导入过程中发现{len(import_result['failed'])}个错误: {'; '.join(error_messages[:5])}{'...' if len(error_messages) > 5 else ''}", 'danger')
            logging.error(f"导入用户数据操作，发现{len(import_result['failed'])}个错误")
        else:
            logging.info(f"导入用户数据操作，成功导入{len(import_result['success'])}条记录")    
        
        # 如果有成功的用户对象，统一提交事务
        commit_result = _commit_batch_result(
            import_result, current_user,
            operation_type='导入',
            summary_template='批量导入新增用户：{name}',
            is_create=True,
            change_detail_fn=lambda u: {'name': u.name, 'student_id': u.student_id, 'category': u.category}
        )
        
        if commit_result is None:
            return redirect(url_for('user.manage'))
        if commit_result is False:
            flash('没有可导入的有效数据', 'warning')
        
        return redirect(url_for('user.manage'))
    
    except Exception as e:
        # 发生异常时回滚事务
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='batch_import_export',
            action=f"尝试导入用户数据失败: {str(e)}",
            result="失败"
        )
        msg = f'导入失败: {str(e)}'
        flash(msg, 'danger')
        logging.error(f"导入用户数据操作，导入失败: {str(e)}", exc_info=True)
        return redirect(url_for('user.manage'))
    


@user_import_export_bp.route('/import-template', methods=['GET'])
@login_required
@require_permission('user.import')
def import_template():
    """生成并下载用户导入模板"""
    try:
        # 获取可导入的字段
        importable_fields = get_importable_fields()
        
        # 准备模板数据（示例数据）
        sample_data = [
            {
                "姓名": "张三",
                "性别": "男",
                "用户名": "张三",
                "工号": "123",
                "人员类别": "员工",
                "民族": "汉",
                "身份证号码": "110101199001011234",
                "身份证地址": "北京市东城区XX街道",
                "外宿地址": "北京市东城区XX街道",
                "联系电话": "13800138000",
                "公司": "公司A",
                "部门": "技术部",
                "职位": "工程师",
                "紧急联系人": "李四",
                "紧急联系人电话": "13900139000",
                "婚姻状态": "未婚",
                "备注": "无特殊说明",
                "状态": "在职",
                "入职日期": "2023-01-15",
                "角色": "普通用户",
                "是否激活账号": "是",
                "是否允许登录": "否",
                "密码": "123456"  # 默认密码
            },
            {
                "姓名": "李四",
                "性别": "女",
                "用户名": "李四",
                "工号": "456",
                "人员类别": "管理员",
                "民族": "汉",
                "身份证号码": "310101199203155678",
                "身份证地址": "上海市黄浦区XX街道",
                "外宿地址": "上海市黄浦区XX街道",
                "联系电话": "13700137000",
                "公司": "公司A",
                "部门": "行政部",
                "职位": "主管",
                "紧急联系人": "王五",
                "紧急联系人电话": "13600136000",
                "婚姻状态": "未婚",
                "备注": "负责行政事务",
                "状态": "在职",
                "入职日期": "2022-05-10",
                "角色": "管理员",
                "是否激活账号": "是",
                "是否允许登录": "否",
                "密码": "654321"  # 自定义密码
            }
        ]
        
        # 创建DataFrame
        df = pd.DataFrame(sample_data)
        
        # 生成Excel
        output = BytesIO()
        
        # 使用xlsxwriter引擎
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # 关键修复：设置header=False，不自动生成表头
            df.to_excel(writer, index=False, sheet_name='用户导入模板', startrow=1, header=False)
            
            # 获取工作表
            worksheet = writer.sheets['用户导入模板']
            
            # 创建一个加粗的格式
            bold_format = writer.book.add_format({'bold': True})
            
            # 只写入一次表头
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, bold_format)
            
            # 调整列宽
            for i, col in enumerate(df.columns):
                # 计算每列的最大宽度（考虑表头和内容）
                column_width = max(
                    len(str(value)) for value in df[col].fillna('')
                )
                # 确保至少比表头宽一点
                column_width = max(column_width, len(col)) + 2
                worksheet.set_column(i, i, column_width)
        
        output.seek(0)
        
        # 日志记录
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='batch_import_export',
            action=f"下载用户导入模板（{len(importable_fields)}个字段）",
            result="成功"
        )
        logging.info(f"下载用户导入模板操作，成功生成模板，包含{len(importable_fields)}个字段")
        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            download_name=f"用户数据导入模板_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.xlsx"
        )
    
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='batch_import_export',
            action=f"尝试生成用户导入模板失败: {str(e)}",
            result="失败"
        )
        flash(f'生成模板失败: {str(e)}', 'danger')
        logging.error(f"下载用户导入模板操作失败，异常信息: {str(e)}")
        return redirect(url_for('user.manage'))


@user_import_export_bp.route('/update', methods=['POST'])
@login_required
@require_permission('user.edit')
def update_users():
    """批量更新用户数据（基于用户ID）"""
    try:
        # 检查文件
        file, error_response = _validate_uploaded_file('批量更新用户数据操作')
        if error_response:
            return error_response
        
        # 读取Excel
        file_content = file.read()
        file_bytes = BytesIO(file_content)
        file_bytes.seek(0)
        
        # 读取Excel并构建dtype字典
        df, excel_columns, display_to_field = _read_excel_with_dtype(file_bytes)
        
        # 检查必要字段（用户ID和姓名）
        required_display = ['用户ID', '姓名']
        if not all(req in excel_columns for req in required_display):
            missing = [req for req in required_display if req not in excel_columns]
            msg = f'Excel缺少必要列：{" ".join(missing)}'
            flash(msg, 'danger')
            logging.error(f"批量更新用户数据操作，Excel缺少必要列：{', '.join(missing)}")
            return redirect(url_for('user.manage'))
        
        # 提示未识别字段
        extra_cols = [col for col in excel_columns if col not in display_to_field.keys() and col != '用户ID']
        if extra_cols:
            flash(f'忽略未识别字段：{" ".join(extra_cols)}', 'warning')
            logging.warning(f"批量更新用户数据操作，Excel包含未识别字段：{', '.join(extra_cols)}")
        
        # 收集要更新的数据
        user_data_list = []
        
        # 获取现有用户的用户名和工号映射关系，用于验证唯一性
        existing_users = User.query.with_entities(User.id, User.username, User.student_id).all()
        username_to_id = {user.username: user.id for user in existing_users if user.username}
        student_id_to_id = {user.student_id: user.id for user in existing_users if user.student_id}
        
        # 预加载部门缓存，避免批量更新时循环内DB查询
        department_cache = _build_department_cache()
        
        # 提取所有入职时间值进行批量解析
        try:
            parsed_hire_dates = _batch_parse_hire_dates(df)
        except Exception as e:
            msg = f'批量解析入职日期失败：{str(e)}'
            flash(msg, 'danger')
            logging.error(f'批量解析入职日期失败：{str(e)}')
            return redirect(url_for('user.manage'))
        
        # 用于跟踪Excel文件内已处理的用户名和工号，防止表格内部重复
        excel_username_set = set()
        excel_student_id_set = set()
        
        for idx, row in df.iterrows():
            user_data = {}
            # 添加用户ID
            if '用户ID' in row and pd.notna(row['用户ID']):
                try:
                    user_data['id'] = int(row['用户ID'])
                except ValueError:
                    logging.warning(f"批量更新用户数据操作，第{idx+2}行：用户ID格式无效")
                    continue
            else:
                logging.warning(f"批量更新用户数据操作，第{idx+2}行：用户ID为空")
                continue
            
            # 验证用户名唯一性
            if '用户名' in row and pd.notna(row['用户名']):
                username = str(row['用户名']).strip()
                if username:
                    # 检查数据库中是否存在该用户名且不属于当前用户
                    if username in username_to_id and username_to_id[username] != user_data['id']:
                        logging.warning(f"批量更新用户数据操作，第{idx+2}行：用户名'{username}'已被其他用户使用")
                        continue
                    # 检查当前Excel文件中是否已经出现过该用户名
                    if username in excel_username_set:
                        logging.warning(f"批量更新用户数据操作，第{idx+2}行：用户名'{username}'在Excel文件中重复出现")
                        continue
                    # 添加到已处理集合
                    excel_username_set.add(username)
                    user_data['username'] = username
            
            # 验证工号唯一性
            if '工号' in row and pd.notna(row['工号']):
                student_id = str(row['工号']).strip()
                if student_id:
                    # 检查数据库中是否存在该工号且不属于当前用户
                    if student_id in student_id_to_id and student_id_to_id[student_id] != user_data['id']:
                        logging.warning(f"批量更新用户数据操作，第{idx+2}行：工号'{student_id}'已被其他用户使用")
                        continue
                    # 检查当前Excel文件中是否已经出现过该工号
                    if student_id in excel_student_id_set:
                        logging.warning(f"批量更新用户数据操作，第{idx+2}行：工号'{student_id}'在Excel文件中重复出现")
                        continue
                    # 添加到已处理集合
                    excel_student_id_set.add(student_id)
                    user_data['student_id'] = student_id
            
            # 处理其他字段
            for col in excel_columns:
                # 跳过已经处理过的字段
                if col in ['用户ID', '用户名', '工号']:
                    continue
                if col in display_to_field:
                    field_name = display_to_field[col]
                    value = row[col]
                    if pd.notna(value):
                        # 使用公共函数统一处理字段值转换
                        processed = _process_field_value(field_name, value, parsed_hire_dates, idx)
                        if processed is not None:
                            user_data[field_name] = processed
            
            # 同步公司和部门到部门管理模块
            _sync_company_department(user_data, '批量更新用户数据操作', f'第{idx+2}行：')
            
            if user_data:
                user_data_list.append(user_data)
        
        if not user_data_list:
            msg = 'Excel中没有可更新的有效数据'
            flash(msg, 'warning')
            logging.warning("批量更新用户数据操作，Excel中没有可更新的有效数据")
            return redirect(url_for('user.manage'))
        
        try:
            # 调用模型的批量更新方法
            update_result = User.batch_update_users(user_data_list, department_cache=department_cache)
            
            # 合并提交结果
            commit_result = _commit_batch_result(
                update_result, current_user,
                operation_type='批量更新',
                summary_template='批量更新用户：{name}',
                is_create=False
            )
            
            if commit_result is None:
                return redirect(url_for('user.manage'))
            
            # 如果有失败记录，显示失败详情
            if update_result['failed']:
                for fail in update_result['failed']:
                    logging.error(f"批量更新用户失败，行号：{fail['row']}，错误：{', '.join(fail['errors'])}")
        
        except Exception as e:
            # 事务回滚
            db.session.rollback()
            log_operation(
                user_id=current_user.id,
                module='user',
                operation_type='batch_import_export',
                action=f"尝试批量更新用户数据失败: {str(e)}",
                result="失败"
            )
            msg = f'数据提交失败: {str(e)}'
            flash(msg, 'danger')
            logging.error(f"批量更新用户数据操作，提交数据库失败: {str(e)}")
            return redirect(url_for('user.manage'))
        
        return redirect(url_for('user.manage'))
        
    except Exception as e:
        # 发生异常时回滚事务
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='batch_import_export',
            action=f"尝试批量更新用户数据失败: {str(e)}",
            result="失败"
        )
        msg = f'更新失败: {str(e)}'
        flash(msg, 'danger')
        logging.error(f"批量更新用户数据操作，更新失败: {str(e)}", exc_info=True)
        return redirect(url_for('user.manage'))

