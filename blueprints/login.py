from flask import Blueprint, render_template, redirect, url_for, request, session, flash, make_response, current_app
from flask_login import current_user, logout_user, login_user
from sqlalchemy.exc import SQLAlchemyError
import logging
from datetime import datetime
from utils.log import log_operation
# 导入数据库和用户模型（使用提供的User模型）
from utils.db import db
from models.user import User  # 直接使用User模型
from utils.auto_logout import check_force_relogin_flag, clear_force_relogin_flag
# 导入我们新的安全Cookie管理模块
from utils.cookie_secure import cookie_secure

# 创建蓝图
login_bp = Blueprint('login', __name__, url_prefix='/login')

# 适配Flask-Login的用户类（直接基于数据库模型，因模型已继承UserMixin）
# 注：原User模型已继承UserMixin，此处可直接使用，无需额外封装

@login_bp.route('', methods=['GET', 'POST'])
def login():
    # 创建响应对象以便在需要时操作cookie
    response = make_response()
    
    # 添加调试日志
    print('登录路由访问 - 用户认证状态:', current_user.is_authenticated)
    
    # 检查全局强制重新登录标志（双重保障）
    force_relogin = False
    
    # 检查应用配置中的标志
    if current_app.config.get('FORCE_RELOGIN', False):
        force_relogin = True
        current_app.config['FORCE_RELOGIN'] = False  # 立即重置配置标志
    
    # 检查文件系统中的标志文件
    if check_force_relogin_flag():
        force_relogin = True
        clear_force_relogin_flag()  # 立即清除文件标志
    
    if force_relogin:
        print('检测到强制重新登录标志，强制清除所有用户认证状态')
        # 即使已登录也要强制退出
        if current_user.is_authenticated:
            # 执行登出操作
            logout_user()
            # 彻底清除所有会话数据
            session.clear()
            session.modified = True
            # 清除所有cookie
            for key in list(request.cookies.keys()):
                response.set_cookie(key, '', expires=0, path='/', domain=None, secure=False, httponly=True)
            print('已强制清除用户认证状态、会话数据和cookie')
    
    # 如果用户已登录，直接跳转到主页
    if current_user.is_authenticated:
        print('用户仍处于认证状态，重定向到主页')
        return redirect(url_for('index'))
    
    # 开发模式自动登录：DEV_AUTO_LOGIN开关开启时，直接以admin账号登录
    if current_app.config.get('DEV_AUTO_LOGIN', False):
        try:
            admin_user = User.query.filter_by(username='admin').first()
            if admin_user:
                print(f'[开发模式] 自动登录为admin账号: {admin_user.name}')
                login_user(admin_user, remember=True)
                session['login_time'] = datetime.now().isoformat()
                session['last_activity_time'] = datetime.now().isoformat()
                session.modified = True
                log_operation(
                    user_id=admin_user.id,
                    module='login',
                    operation_type='login',
                    action=f"{admin_user.name}开发模式自动登录",
                    result="成功"
                )
                admin_user.last_login_at = datetime.now()
                db.session.commit()
                flash(f'开发模式自动登录为: {admin_user.name}', 'success')
                return redirect(url_for('index'))
            else:
                print('[开发模式] 未找到admin账号，跳过自动登录')
        except Exception as e:
            print(f'[开发模式] 自动登录失败: {str(e)}')
            logging.error(f'开发模式自动登录失败: {str(e)}')
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username:
            flash('请输入用户名', 'danger')
            logging.error("登录失败，请输入用户名")
            response.set_data(render_template('login/login.html',title=f"登录"))
            return response
        
        if not password:
            flash('请输入密码', 'danger')
            logging.error("登录失败，请输入密码")
            response.set_data(render_template('login/login.html',title=f"登录"))
            return response
        
        try:
            # 1. 从数据库查询用户，支持工号(student_id)和用户名(username)两种方式登录
            user = User.query.filter((User.username == username) | (User.student_id == username)).first()
            
            # 2. 验证用户是否存在
            if not user:
                flash('用户名或密码错误', 'danger')
                logging.error("用户名或密码错误")
                response.set_data(render_template('login/login.html',title=f"登录"))
                return response
            
            # 3. 验证账号是否激活
            if not user.is_active:
                flash('账号未激活', 'danger')
                logging.error("账号未激活")
                response.set_data(render_template('login/login.html',title=f"登录"))
                return response
                
            # 3. 验证账号状态（是否在职）
            if not user.is_active or not user.is_status:
                flash('账号已被停用', 'danger')
                logging.error("账号已被停用")
                response.set_data(render_template('login/login.html',title=f"登录"))
                return response
            
            # 4. 验证是否被禁止登录
            if not user.is_banned:
                flash('您的账号已被禁止登录', 'danger')
                logging.error(f"您的账号已被禁止登录")
                response.set_data(render_template('login/login.html',title=f"登录"))
                return response
            
            # 5. 验证密码（使用模型自带的check_password方法）
            if not user.check_password(password):
                flash('用户名或密码错误', 'danger')
                logging.error("用户名或密码错误")
                response.set_data(render_template('login/login.html',title=f"登录"))
                return response
            
            # 使用安全Cookie管理模块设置用户会话，传入响应对象
            response = cookie_secure.setup_secure_user_session(user, remember=True, response=response)
            
            # 记录访问日志
            log_operation(
                    user_id=user.id,
                    module='login',
                    operation_type='login',
                    action=f"{user.name}登录成功",
                    result="成功"
            )
            
            # 更新用户最后登录时间
            user.last_login_at = datetime.now()
            db.session.commit()
            
            logging.info(f"登录成功，欢迎使用")
            flash('登录成功，欢迎使用系统', 'success')
            # 根据用户角色决定重定向目标
            if user.is_admin():
                # 管理员用户重定向到首页
                redirect_response = redirect(url_for('index'))
            else:
                # 非管理员用户重定向到用户信息页面
                redirect_response = redirect(url_for('user.user_info'))
            
            # 将原始响应中的Cookie复制到重定向响应中
            for cookie in response.headers.getlist('Set-Cookie'):
                redirect_response.headers.add('Set-Cookie', cookie)
            
            return redirect_response
            
        except SQLAlchemyError as e:
            db.session.rollback()
            flash('登录失败：数据库错误', 'danger')
            # 生产环境建议记录日志
            logging.error(f"登录失败: {str(e)}")
            response.set_data(render_template('login/login.html',title=f"登录"))
            return response
    
    # 如果是GET请求，渲染登录页面
    response.set_data(render_template('login/login.html',title=f"登录"))
    return response

@login_bp.route('/logout')
def logout():
    try:
        # 先保存用户信息，因为logout_user_securely会清除认证状态
        user_id = current_user.id if current_user.is_authenticated else 0
        user_name = current_user.name if current_user.is_authenticated else "未知用户"
        # 创建重定向响应
        response = redirect(url_for('login.login'))
        
        # 使用安全Cookie管理模块处理登出流程
        response = cookie_secure.logout_user_securely(response)
        # 记录访问日志
        log_operation(
                user_id=user_id,
                module='login',
                operation_type='logout',
                action=f"{user_name}登出成功",
                result="成功"
        )
        # 添加登出成功提示
        flash('已成功退出登录', 'info')
        logging.info(f'已成功退出登录')
    except Exception as e:

        logging.error(f'退出登录时发生错误: {str(e)}')
        flash(f'退出登录时发生错误: {str(e)}', 'danger')
        response = redirect(url_for('login.login'))
    
    return response
    