from flask import Blueprint, render_template, redirect, url_for, request, flash
from utils.db import db
from models.user import User
from models.dorm import Dorm
from models.system_config import SystemConfig  # 导入系统配置模型
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.user_utils import generate_student_id, generate_username  # 引用工具类
from datetime import datetime
import re
from werkzeug.security import generate_password_hash
# 导入admin_required装饰器
from blueprints.system_settings import admin_required
import logging

# 用户操作蓝图（仅保留增删改）
user_operations_bp = Blueprint('user_operations', __name__, url_prefix='/user')

@user_operations_bp.route('/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add():
    # 获取用户类别选项（供模板使用）
    category_options = [
        {'value': item, 'label': item} 
        for item in SystemConfig.get_config_value('USER_TYPES', ['员工', '职员', '高管'])
    ]
    role_options = [
        {'value': item, 'label': item} 
        for item in SystemConfig.get_config_value('USER_ROLES', ['普通用户', '管理员', '超级管理员'])
    ]
    status_options = [
        {'value': item, 'label': item} 
        for item in SystemConfig.get_config_value('USER_STATUS_OPTIONS', ['在职', '离职'])
    ]
    # 从系统配置获取用户婚姻状态选项（替代硬编码）
    marital_status_options = [
        {'value': item, 'label': item} 
        for item in SystemConfig.get_config_value('USER_MARITAL_STATUS', ['未婚', '已婚', '离异', '丧偶'])
    ] 
    
    if request.method == 'POST':
        # 核心修改1：一次查询获取所有已存在的工号和用户名（内存查重）
        existing_data = User.query.with_entities(User.student_id, User.username).all()
        existing_ids = {item.student_id for item in existing_data}  # 工号集合
        existing_usernames = {item.username for item in existing_data}  # 用户名集合

        # 获取用户输入的工号和用户名
        student_id = request.form.get('student_id', '').strip()
        username = request.form.get('username', '').strip()
        name = request.form.get('name', '').strip()
        gender = request.form.get('gender', '').strip() or '男'
        # 从系统配置获取默认用户类别
        category = request.form.get('category', '').strip() or SystemConfig.get_config_value('USER_TYPES', ['员工'])[0]
        id_card = request.form.get('id_card', '').strip()
        id_address = request.form.get('id_address', '').strip()
        lodging_address = request.form.get('lodging_address', '').strip()
        phone = request.form.get('phone', '').strip()
        company = request.form.get('company', '').strip()
        department = request.form.get('department', '').strip()
        position = request.form.get('position', '').strip()
        emergency_contact = request.form.get('emergency_contact', '').strip()
        emergency_phone = request.form.get('emergency_phone', '').strip()
        remarks = request.form.get('remarks', '').strip()
        # 从系统配置获取默认状态
        status = request.form.get('status', '').strip() or SystemConfig.get_config_value('USER_DEFAULT_STATUS', '在职')
        
        # 从系统配置获取默认角色
        role = request.form.get('role', '').strip() or SystemConfig.get_config_value('USER_DEFAULT_ROLE', '普通用户')
        
       # 从系统配置获取默认密码
        password = request.form.get('password', '').strip() or SystemConfig.get_config_value('USER_DEFAULT_PASSWORD', '123456')
       
        ethnicity = request.form.get('ethnicity', '').strip()  # 民族字段
        marital_status = request.form.get('marital_status', '').strip() #婚姻状态

        # 入职时间
        hire_date_str = request.form.get('hire_date', '').strip()
        if hire_date_str:
            # 处理datetime-local格式 (YYYY-MM-DDTHH:MM)
            hire_date = datetime.strptime(hire_date_str, '%Y-%m-%dT%H:%M')
        else:
            hire_date = datetime.now()
       
        # 直接从前端表单接收is_banned和is_active的值
        is_banned = 'is_banned' in request.form
        is_active = 'is_active' in request.form

        # 验证必填项
        required_fields = [
            ('name', '姓名'), 
            ('gender', '性别')
            
        ]
        for field, label in required_fields:
            if not locals()[field]:
                flash(f'{label}为必填项', 'danger')
                logging.error(f"添加用户失败，{label}为必填项")
                return render_template(
                    'user_manage/user_add.html',
                    title=f"添加用户",
                    form_data=request.form,
                    role_options=role_options,
                    status_options=status_options,
                    category_options=category_options,
                    marital_status_options=marital_status_options  # 新增：婚姻状态选项
                )
        
        # 验证身份证格式
        if id_card and not re.match(r'^\d{17}[\dXx]$', id_card):
            flash('身份证号码格式不正确', 'danger')
            logging.error(f"添加用户失败，身份证号码格式不正确: {id_card}")
            return render_template(
                'user_manage/user_add.html',
                title=f"添加用户",
                form_data=request.form,
                role_options=role_options,
                status_options=status_options,
                category_options=category_options,
                marital_status_options=marital_status_options  # 新增：婚姻状态选项
            )
        
        # 检查工号重复
        if student_id and student_id in existing_ids:
            flash(f'工号已存在', 'danger')
            logging.error(f"添加用户失败，工号已存在: {student_id}")
            return render_template(
                'user_manage/user_add.html',
                title=f"添加用户",
                form_data=request.form,
                role_options=role_options,
                status_options=status_options,
                category_options=category_options,
                marital_status_options=marital_status_options  # 新增：婚姻状态选项
            )
        
        # 检查用户名重复
        if User.query.filter_by(username=username).first():
            flash(f'用户名已存在', 'danger')
            logging.error(f"添加用户失败，用户名已存在: {username}")
            return render_template(
                'user_manage/user_add.html',
                title=f"添加用户",
                form_data=request.form,
                role_options=role_options,
                status_options=status_options,
                category_options=category_options,
                marital_status_options=marital_status_options  # 新增：婚姻状态选项
            )
        
        # 如果工号为空，自动生成
        if not student_id:
            # 生成工号（传递现有工号集合）
            student_id = generate_student_id(existing_ids)
            if not student_id:
                flash('生成工号失败，请重试', 'danger')
                return render_template(
                    'user_manage/user_add.html',
                    title=f"添加用户",
                    form_data=request.form,
                    role_options=role_options,
                    status_options=status_options,
                    category_options=category_options,
                    marital_status_options=marital_status_options  # 新增：婚姻状态选项
                )
        
        # 如果用户名为空，自动生成
        if not username:
            # 生成用户名（传递现有用户名集合）
            username = generate_username(name, existing_usernames)
            if not username:
                flash('生成用户名失败，请重试', 'danger')
                return render_template(
                    'user_manage/user_add.html',
                    title=f"添加用户",
                    form_data=request.form,
                    role_options=role_options,
                    status_options=status_options,
                    category_options=category_options,
                    marital_status_options=marital_status_options  # 新增：婚姻状态选项
                )
        
        try:
            # 创建用户
            new_user = User(
                student_id=student_id,
                name=name,
                gender=gender,
                category=category,
                id_card=id_card,
                id_address=id_address,
                lodging_address=lodging_address,
                phone=phone,
                company=company,
                department=department,
                position=position,
                emergency_contact=emergency_contact,
                emergency_phone=emergency_phone,
                remarks=remarks,
                status=status,
                username=username,
                role=role,
                password_hash=generate_password_hash(password),  # 使用设置的密码
                is_banned=is_banned,#账号默认不允许登录
                is_active=is_active,  # 账号激活状态
                ethnicity=ethnicity,  # 民族字段
                marital_status=marital_status,  # 婚姻状态
                hire_date=hire_date  # 入职时间
            )
            
            # 调用save()方法触发自动提取（籍贯、年龄等）
            new_user.save()
            logging.info(f"添加用户成功，用户ID: {new_user.id}, 用户名: {username}")
            
            # 日志记录
            log_operation(
                user_id=current_user.id,
                module='user',
                operation_type='user_add',
                action=f"添加用户 [姓名: {name}, 工号: {student_id}, 类别: {category}]",
                result="成功"
            )
            
            # 根据按钮跳转
            if request.form.get('action') == 'return':
                flash(f"用户ID: {new_user.id}，用户名： {username}  添加成功（登录密码：{password}）", 'success')
                logging.info(f"添加用户成功，用户ID: {new_user.id}, 用户名: {username}")
                return redirect(url_for('user.manage'))
            else:
                flash(f"用户ID: {new_user.id}，用户名： {username}  添加成功（登录密码：{password}），可继续添加", 'success')
                logging.info(f"添加用户成功，用户ID: {new_user.id}, 用户名: {username}，可继续添加")
                return redirect(url_for('user_operations.add'))

        except Exception as e:
            db.session.rollback()
            logging.error(f"添加用户失败: {str(e)}")
            log_operation(
                user_id=current_user.id,
                module='user',
                operation_type='user_add',
                action=f"尝试添加用户 [姓名: {name}]失败: {str(e)}",
                result="失败"
            )
            flash(f'添加失败: {str(e)}', 'danger')
    
    # 获取系统配置的默认状态
    default_is_banned = SystemConfig.get_config_value('USER_DEFAULT_BANNED', False)
    default_is_active = SystemConfig.get_config_value('USER_DEFAULT_ACTIVE', True)
    
    # GET请求渲染表单，传递默认状态值
    return render_template(
        'user_manage/user_add.html',
        title=f"添加用户",
        form_data=None,
        role_options=role_options,
        status_options=status_options,
        category_options=category_options,
        marital_status_options=marital_status_options,  # 新增：婚姻状态选项
        default_is_banned=default_is_banned,
        default_is_active=default_is_active
    )


@user_operations_bp.route('/edit/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit(id):
    user = User.query.get_or_404(id)
    
    # 从系统配置获取用户类别选项（替代硬编码）
    category_options = [
        {'value': item, 'label': item} 
        for item in SystemConfig.get_config_value('USER_TYPES', ['员工', '职员', '高管'])
    ]
    role_options = [
        {'value': item, 'label': item} 
        for item in SystemConfig.get_config_value('USER_ROLES', ['普通用户', '管理员', '超级管理员'])
    ]
    status_options = [
        {'value': item, 'label': item} 
        for item in SystemConfig.get_config_value('USER_STATUS_OPTIONS', ['在职', '离职'])
    ]
    # 从系统配置获取用户婚姻状态选项（替代硬编码）
    marital_status_options = [
        {'value': item, 'label': item} 
        for item in SystemConfig.get_config_value('USER_MARITAL_STATUS', ['未婚', '已婚', '离异', '丧偶'])
    ]
    
    # 检查活跃住宿记录
    has_active_dorm = Dorm.query.filter_by(user_id=id, status='active').first() is not None
    user.has_active_dorm = has_active_dorm
    # 保存原始工号和用户名（用于对比）
    original_student_id = user.student_id
    original_username = user.username

    # 超级管理员保护
    if user.is_super_admin() and not current_user.is_super_admin():
        flash('无权限编辑超级管理员', 'danger')
        logging.error(f"编辑用户失败，无权限编辑超级管理员: {user.id}")
        return redirect(url_for('user.manage'))
    
    if request.method == 'POST':
        old_info = f"姓名: {user.name}, 工号: {user.student_id}, 类别: {user.category}, 登录权限: {'禁止' if user.is_banned else '允许'}"
        student_id = request.form.get('student_id', '').strip()
        name = request.form.get('name', '').strip()
        username = request.form.get('username', '').strip()
        gender = request.form.get('gender', '').strip()
        category = request.form.get('category', user.category).strip()
        id_card = request.form.get('id_card', '').strip()
        id_address = request.form.get('id_address', '').strip()
        lodging_address = request.form.get('lodging_address', '').strip()
        phone = request.form.get('phone', '').strip()
        company = request.form.get('company', '').strip()
        department = request.form.get('department', '').strip()
        position = request.form.get('position', '').strip()
        emergency_contact = request.form.get('emergency_contact', '').strip()
        emergency_phone = request.form.get('emergency_phone', '').strip()
        remarks = request.form.get('remarks', '').strip()
        status = request.form.get('status', user.status)
        role = request.form.get('role', user.role).strip()
        
        ethnicity = request.form.get('ethnicity', user.ethnicity or '').strip()
        marital_status = request.form.get('marital_status', user.marital_status or '').strip() #婚姻状态

        # 入职时间
        hire_date_str = request.form.get('hire_date', '').strip()
        if hire_date_str:
            # 处理datetime-local格式 (YYYY-MM-DDTHH:MM)
            hire_date = datetime.strptime(hire_date_str, '%Y-%m-%dT%H:%M')
        else:
            hire_date = datetime.now()

        # 修复：正确获取复选框状态（存在即表示勾选）
        is_active = 'is_active' in request.form
        is_banned = 'is_banned' in request.form

        new_password = request.form.get('new_password', '').strip()

        # 工号和用户名重复检查
        # 只有当工号发生变化时才检查重复
        if student_id != original_student_id and student_id:
            # 检查是否有其他用户使用了相同的工号
            if User.query.filter(User.id != id, User.student_id == student_id).first():
                flash(f'工号已被其他用户使用', 'danger')
                logging.error(f"编辑用户失败，工号已被其他用户使用: {student_id}")
                return render_template(
                    'user_manage/user_edit.html', 
                    title=f"编辑用户 - {user.name}",
                    user=user,
                    role_options=role_options,
                    status_options=status_options,
                    category_options=category_options,
                    marital_status_options=marital_status_options  # 新增：婚姻状态选项
                )
        
        # 只有当用户名发生变化时才检查重复
        if username != original_username and username:
            # 检查是否有其他用户使用了相同的用户名
            if User.query.filter(User.id != id, User.username == username).first():
                flash(f'用户名已被其他用户使用', 'danger')
                logging.error(f"编辑用户失败，用户名已被其他用户使用: {username}")
                return render_template(
                    'user_manage/user_edit.html', 
                    title=f"编辑用户 - {user.name}",
                    user=user,
                    role_options=role_options,
                    status_options=status_options,
                    category_options=category_options,
                    marital_status_options=marital_status_options  # 新增：婚姻状态选项
                )
        
        # 有活跃住宿时锁定状态和性别
        if has_active_dorm:
            status = user.status
            gender = user.gender  # 使用数据库中已有的性别值，因为前端字段被禁用不会提交
        
        # 验证必填项
        required_fields = [('name', '姓名'), ('gender', '性别')]
        for field, label in required_fields:
            if not locals()[field]:
                flash(f'{label}为必填项', 'danger')
                logging.error(f"编辑用户失败，{label}为必填项: {user.name}({user.id})")
                return render_template(
                    'user_manage/user_edit.html', 
                    title=f"编辑用户 - {user.name}",
                    user=user,
                    role_options=role_options,
                    status_options=status_options,
                    category_options=category_options,
                    marital_status_options=marital_status_options  # 新增：婚姻状态选项
                )
        
        # 验证身份证格式
        if id_card and not re.match(r'^\d{17}[\dXx]$', id_card):
            flash('身份证格式不正确', 'danger')
            logging.error(f"编辑用户失败，身份证格式不正确: {user.id}")
            return render_template(
                'user_manage/user_edit.html', 
                title=f"编辑用户 - {user.name}",
                user=user,
                role_options=role_options,
                status_options=status_options,
                category_options=category_options,
                marital_status_options=marital_status_options  # 新增：婚姻状态选项
            )
        
        
        # 角色权限控制
        if user.is_super_admin() and not current_user.is_super_admin():
            flash('无权限设置超级管理员角色', 'danger')
            logging.error(f"编辑用户失败，无权限设置超级管理员角色: {user.id}")
            return render_template(
                'user_manage/user_edit.html', 
                title=f"编辑用户 - {user.name}",
                user=user,
                role_options=role_options,
                status_options=status_options,
                category_options=category_options,
                marital_status_options=marital_status_options  # 新增：婚姻状态选项
            )
        
        # 登录权限特殊控制：超级管理员不能被禁止登录
        if user.is_super_admin() and not current_user.is_super_admin():
            flash('无权限禁止超级管理员登录', 'danger')
            logging.error(f"编辑用户失败，无权限禁止超级管理员登录: {user.id}")
            return render_template(
                'user_manage/user_edit.html', 
                title=f"编辑用户 - {user.name}",
                user=user,
                role_options=role_options,
                status_options=status_options,
                category_options=category_options,
                marital_status_options=marital_status_options  # 新增：婚姻状态选项
            )
        
        try:
            # 更新用户信息（包含是否允许登录）
            user.student_id = student_id
            user.username = username
            user.name = name
            user.gender = gender
            user.category = category
            user.id_card = id_card
            user.id_address = id_address
            user.lodging_address = lodging_address
            user.phone = phone
            user.company = company
            user.department = department
            user.position = position
            user.emergency_contact = emergency_contact
            user.emergency_phone = emergency_phone
            user.remarks = remarks
            user.status = status
            user.role = role
            user.is_active = is_active
            user.is_banned = is_banned  # 更新是否允许登录状态（True=禁止，False=允许）
            user.ethnicity = ethnicity  # 民族字段
            user.marital_status = marital_status  # 婚姻状态
            user.hire_date = hire_date
            user.updated_at = datetime.now()
            
            if new_password:
                user.password_hash = generate_password_hash(new_password)
            
            user.save()
            logging.info(f"编辑用户成功，用户ID: {user.id}")
            
            log_operation(
                user_id=current_user.id,
                module='user',
                operation_type='user_edit',
                action=f"编辑用户 [原信息: {old_info}]",
                result="成功"
            )
            # 登录状态变更提示
            login_status_msg = "，登录权限已变更" if is_banned != user.is_banned else ""
            flash(f'信息更新成功{login_status_msg}' + ('，密码已更新' if new_password else ''), 'success')
            logging.info(f"编辑用户成功，用户ID: {user.id}，更新信息: {old_info}")
            return redirect(url_for('user.manage'))
            
        except Exception as e:
            db.session.rollback()
            logging.error(f"编辑用户失败，异常信息: {str(e)}")
            log_operation(
                user_id=current_user.id,
                module='user',
                operation_type='user_edit',
                action=f"尝试编辑用户 [ID: {id}]失败: {str(e)}",
                result="失败"
            )
            flash(f'更新失败: {str(e)}', 'danger')
    
    return render_template(
        'user_manage/user_edit.html',
        title=f"编辑用户 - {user.name}",
        user=user,
        role_options=role_options,
        status_options=status_options,
        category_options=category_options,
        marital_status_options=marital_status_options  # 新增：婚姻状态选项
    )
    
    
@user_operations_bp.route('/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete(id):
    user = User.query.get_or_404(id)
    user_detail = f"ID: {user.id}, 姓名: {user.name}, 工号: {user.student_id}"
    
    try:
        result = user.delete()
        
        if result['success']:
            db.session.commit()
            logging.info(f"删除用户成功，用户ID: {user.id}")
            log_operation(
                user_id=current_user.id,
                module='user',
                operation_type='user_delete',
                action=f"删除用户成功 [用户信息: {user_detail}，操作结果: {result['message']}]",
                result="成功"  # 仅保留成功状态
            )
            flash(result['message'], 'success')
        else:
            db.session.rollback()
            logging.error(f"删除用户失败，用户ID: {user.id}，失败原因: {result['message']}")
            log_operation(
                user_id=current_user.id,
                module='user',
                operation_type='user_delete',
                action=f"删除用户失败 [用户信息: {user_detail}，失败原因: {result['message']}]",
                result="失败"  # 仅保留失败状态
            )
            flash(result['message'], 'danger')
    
    except Exception as e:
        db.session.rollback()
        error_msg = f"系统异常: {str(e)}"
        logging.error(f"删除用户异常，用户ID: {user.id}，异常信息: {error_msg}")
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='user_delete',
            action=f"删除用户异常 [用户信息: {user_detail}，异常信息: {error_msg}]",
            result="失败"  # 异常统一归为失败
        )
        flash(f'操作失败: {error_msg}', 'danger')
    
    return redirect(url_for('user.manage'))

@user_operations_bp.route('/batch_delete', methods=['POST'])
@login_required
@admin_required
def batch_delete():
    ids = request.form.get('ids', '').split(',')
    if not ids or ids == ['']:
        flash('请选择要删除的记录', 'warning')
        logging.warning("批量删除用户操作，未选择任何记录")
        return redirect(url_for('user.manage'))
    
    try:
        ids = [int(id) for id in ids]
        users = User.query.filter(User.id.in_(ids)).all()
        if not users:
            flash('未找到选中记录', 'warning')
            logging.warning(f"批量删除用户操作，未找到选中记录，选择ID: {ids}")
            return redirect(url_for('user.manage'))
        
        deleted_count = 0
        failed_records = []
        success_details = []
        failure_details = []
        
        for user in users:
            user_detail = f"ID: {user.id}, 姓名: {user.name}, 工号: {user.student_id}"
            result = user.delete()
            if result['success']:
                deleted_count += 1
                success_details.append(f"[{user_detail}] {result['message']}")
            else:
                failed_records.append(f"{user.name}（工号：{user.student_id}）：{result['message']}")
                failure_details.append(f"[{user_detail}] 失败原因：{result['message']}")
        
        db.session.commit()
        logging.info(f"批量删除用户操作，成功删除 {deleted_count} 条记录，失败 {len(failed_records)} 条记录")
        
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='user_delete',
            action=(f"批量删除用户完成 [总选择: {len(users)}, 成功: {deleted_count}, 失败: {len(failed_records)}]。"
                    f"成功详情: {'; '.join(success_details) if success_details else '无'}。"
                    f"失败详情: {'; '.join(failure_details) if failure_details else '无'}"),
            result="成功"  # 批量操作整体完成归为成功
        )
        
        flash(f'成功删除 {deleted_count} 条记录', 'success')
        if failed_records:
            flash('以下记录删除失败：', 'warning')
            logging.error(f"批量删除用户操作，失败 {len(failed_records)} 条记录，失败详情: {'; '.join(failure_details)}")
            for msg in failed_records:
                flash(f'- {msg}', 'warning')
    
    except Exception as e:
        db.session.rollback()
        error_msg = f"系统异常: {str(e)}"
        logging.error(f"批量删除用户操作异常，异常信息: {error_msg}")
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='user_delete',
            action=f"批量删除用户异常 [选择ID: {ids}, 异常信息: {error_msg}]",
            result="失败"  # 异常统一归为失败
        )
        flash(f'批量删除失败: {error_msg}', 'danger')
    
    return redirect(url_for('user.manage'))

@user_operations_bp.route('/delete_all', methods=['POST'])
@login_required
@admin_required
def delete_all():
    if not current_user.is_super_admin():
        flash('只有超级管理员可以执行删除全部操作', 'danger')
        logging.warning(f"非超级管理员[{current_user.id}:{current_user.name}]尝试执行删除全部操作，被拒绝")
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='user_delete',
            action=f"非超级管理员[{current_user.id}:{current_user.name}]尝试执行删除全部操作，被拒绝",
            result="失败"  # 权限不足归为失败
        )
        return redirect(url_for('user.manage'))
    
    try:
        all_users = User.query.all()
        if not all_users:
            flash('没有用户记录可删除', 'warning')
            logging.warning("删除全部用户操作，未找到任何用户记录")
            return redirect(url_for('user.manage'))
        
        deleted_count = 0
        failed_records = []
        success_details = []
        failure_details = []
        
        for user in all_users:
            user_detail = f"ID: {user.id}, 姓名: {user.name}, 工号: {user.student_id}"
            result = user.delete()
            if result['success']:
                deleted_count += 1
                success_details.append(f"[{user_detail}] {result['message']}")
            else:
                failed_records.append(f"{user.name}（工号：{user.student_id}）：{result['message']}")
                failure_details.append(f"[{user_detail}] 失败原因：{result['message']}")
        
        db.session.commit()
        
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='user_delete',
            action=(f"删除全部用户完成 [总用户数: {len(all_users)}, 成功删除: {deleted_count}, "
                    f"删除失败: {len(failed_records)}]。"
                    ),
            result="成功"  # 整体操作完成归为成功
        )
        logging.info(f"删除全部用户操作，成功删除 {deleted_count} 个符合条件的用户，失败 {len(failed_records)} 条记录")
        
        flash(f'成功删除 {deleted_count} 个符合条件的用户', 'success')
        if failed_records:
            flash('以下记录删除失败：', 'warning')
            logging.error(f"删除全部用户操作，失败 {len(failed_records)} 条记录，失败详情: {'; '.join(failure_details)}")
            for msg in failed_records:
                flash(f'- {msg}', 'warning')
    
    except Exception as e:
        db.session.rollback()
        error_msg = f"系统异常: {str(e)}"
        logging.error(f"删除全部用户操作异常，异常信息: {error_msg}")
        log_operation(
            user_id=current_user.id,
            module='user',
            operation_type='user_delete',
            action=f"删除全部用户异常 [异常信息: {error_msg}]",
            result="失败"  # 异常统一归为失败
        )
        flash(f'删除全部用户失败: {error_msg}', 'danger')
    
    return redirect(url_for('user.manage'))