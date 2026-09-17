import logging
import secrets
from flask import current_app, session, make_response
from flask_login import login_user, logout_user


def setup_secure_user_session(user, remember=True, response=None):
    """登录时设置用户会话
    
    Args:
        user: Flask-Login用户对象
        remember: 是否记住登录
        response: Flask响应对象
    
    Returns:
        Response: 设置了会话的响应对象
    """
    from datetime import datetime
    
    login_user(user, remember=remember)
    
    # 显式控制session.permanent：
    # - 勾选"记住我"：session.permanent=True，cookie带Max-Age（PERMANENT_SESSION_LIFETIME），
    #   同时Flask-Login设置remember cookie（REMEMBER_COOKIE_DURATION=30天）
    # - 未勾选：session.permanent=False，cookie为浏览器会话级，关闭浏览器即失效
    session.permanent = remember
    
    current_time = datetime.now().isoformat()
    session['login_time'] = current_time
    session['last_activity_time'] = current_time
    session.modified = True
    
    logging.info(f"用户 {user.id} 登录成功，会话已设置")
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
    # 确保after_request处理器能正确删除remember cookie
    session.clear()
    logout_user()
    session.modified = True
    
    # 防止缓存
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    logging.info("用户已安全退出登录")
    return response


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