import logging
import secrets
from flask import current_app, session, make_response, request
from flask_login import login_user, logout_user


def setup_secure_user_session(user, remember=False, response=None):
    """登录时设置用户会话
    
    Cookie策略（简化架构）：
    - CRspli9ois（Flask session cookie）：始终会话级，关闭浏览器即失效
    - remember_token（Flask-Login remember cookie）：
      - 勾选"记住我"：有效期30天（REMEMBER_COOKIE_DURATION）
      - 未勾选：会话级（参考CRspli9ois，关闭浏览器即失效）
    
    这样"记住登录"的职责完全由remember_token承担，
    session cookie不再需要permanent机制。
    
    Args:
        user: Flask-Login用户对象
        remember: 是否记住登录（默认False）
        response: Flask响应对象
    
    Returns:
        Response: 设置了会话的响应对象
    """
    from datetime import datetime
    
    # 始终以remember=True调用login_user，让Flask-Login设置remember cookie
    # 实际有效期由覆盖的_set_cookie方法根据_remember_choice控制
    login_user(user, remember=True)
    
    # session cookie始终会话级 — "记住登录"职责完全由remember_token承担
    session.permanent = False
    
    # 记录remember选择，供覆盖的_set_cookie方法使用
    session['_remember_choice'] = remember
    
    current_time = datetime.now().isoformat()
    session['login_time'] = current_time
    session['last_activity_time'] = current_time
    session.modified = True
    
    # 记录调试信息
    remember_duration = current_app.config.get('REMEMBER_COOKIE_DURATION', '未配置(将使用Flask-Login默认365天)')
    logging.info(f"用户 {user.id} 登录成功，remember={remember}，"
                 f"session.permanent={session.permanent}，"
                 f"remember_token有效期={'30天' if remember else '会话级'}，"
                 f"REMEMBER_COOKIE_DURATION={remember_duration}")
    
    return response


def logout_user_securely(response=None):
    """安全退出登录，清除所有会话数据
    
    Args:
        response: Flask响应对象
    
    Returns:
        Response: 已清除会话的响应对象
    """
    if response is None:
        response = make_response()
    
    # 先清除自定义会话数据，再调用logout_user()
    # 这样logout_user()设置的session['_remember']='clear'标记不会被session.clear()清除
    # 确保Flask-Login的_update_remember_cookie能正确删除remember cookie
    session.clear()
    logout_user()
    session.modified = True
    
    # 防止缓存
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    logging.info("用户已安全退出登录")
    return response


def setup_cookie_policy(app):
    """统一设置Cookie策略，确保所有cookie符合会话级要求
    
    两层机制协同工作：
    1. 覆盖Flask-Login的_set_cookie方法 → 控制remember_token的有效期
       - 勾选"记住我"：30天有效期（Flask-Login默认行为）
       - 未勾选：会话级（关闭浏览器即失效，与CRspli9ois一致）
    
    2. after_request拦截器 → 覆盖非项目持久化cookie为会话级
       - 目标：stay_login、did、_SSID、_CrPoSt
       - 原理：读取请求中的目标cookie（包括HttpOnly），设置同名会话级cookie覆盖
    """
    # ---- 第1层：remember_token有效期控制 ----
    login_manager = app.login_manager
    original_set_cookie = login_manager._set_cookie
    
    def custom_set_cookie(response):
        from flask_login.utils import encode_cookie
        
        config = current_app.config
        cookie_name = config.get('REMEMBER_COOKIE_NAME', 'remember_token')
        remember_choice = session.get('_remember_choice')
        
        if remember_choice is False:
            # 未勾选"记住我"：设置会话级remember cookie（无expires）
            data = encode_cookie(str(session['_user_id']))
            domain = config.get('REMEMBER_COOKIE_DOMAIN')
            path = config.get('REMEMBER_COOKIE_PATH', '/')
            secure = config.get('REMEMBER_COOKIE_SECURE', False)
            httponly = config.get('REMEMBER_COOKIE_HTTPONLY', True)
            samesite = config.get('REMEMBER_COOKIE_SAMESITE')
            
            response.set_cookie(
                cookie_name,
                value=data,
                domain=domain,
                path=path,
                secure=secure,
                httponly=httponly,
                samesite=samesite,
            )
            logging.info("[Cookie策略] 设置会话级remember_token（用户未选择记住我）")
        else:
            # 勾选"记住我"：使用Flask-Login默认行为（30天有效期）
            original_set_cookie(response)
            remember_duration = config.get('REMEMBER_COOKIE_DURATION', '未配置')
            logging.info(f"[Cookie策略] 设置30天有效期remember_token（用户选择了记住我），"
                         f"REMEMBER_COOKIE_DURATION={remember_duration}")
    
    login_manager._set_cookie = custom_set_cookie
    
    # ---- 第2层：非项目持久化cookie覆盖为会话级 ----
    TARGET_COOKIES = {'stay_login', 'did', '_SSID', '_CrPoSt'}
    
    @app.after_request
    def sanitize_persistent_cookies(response):
        # request.cookies可读取所有cookie（包括HttpOnly），无需前端JS参与
        for name in TARGET_COOKIES:
            value = request.cookies.get(name)
            if value:
                response.set_cookie(
                    name,
                    value=value,
                    path='/',
                    httponly=False,
                    samesite='Lax',
                    secure=request.is_secure,
                    # 不设置max_age和expires → 会话级cookie
                )
                logging.info(f"[Cookie策略] 已覆盖cookie {name} 为会话级")
        
        return response
    
    logging.info("[Cookie策略] 已初始化：remember_token双模式 + 持久化cookie会话级覆盖")


def invalidate_all_sessions():
    """使所有现有session失效，通过更换SECRET_KEY实现
    
    适用场景：
    - 数据库恢复后（users表被重建，旧session指向不存在的用户）
    - 安全事件后（强制所有用户重新登录）
    
    原理：更换 app.secret_key 后，所有旧session cookie的签名验证失败，
    Flask自动创建空session，用户变为未登录状态。
    """
    try:
        new_key = secrets.token_hex(32)
        current_app.secret_key = new_key
        logging.info("[会话安全] 已更换SECRET_KEY，所有旧session自动失效")
        return True
    except Exception as e:
        logging.error(f"[会话安全] 更换SECRET_KEY失败: {e}")
        return False