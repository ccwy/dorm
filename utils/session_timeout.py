import logging
from datetime import datetime
from flask import current_app, request, session, redirect, url_for, flash, make_response
from flask_login import current_user, logout_user

# 默认会话不活动超时时间（秒）
DEFAULT_SESSION_INACTIVITY_TIMEOUT = 30 * 60  # 30分钟

def setup_session_timeout_handler(app):
    """
    设置会话超时处理器
    用于检测用户不活动时间并自动退出登录
    """
    # 在check_session_timeout函数中增强会话更新逻辑
    # 修改session_timeout.py文件中的check_session_timeout函数
    @app.before_request
    def check_session_timeout():
        # 跳过静态文件和登录相关路由的检查
        if request.endpoint in ('static', 'login.login', 'login.logout') or \
           request.path.startswith('/static/'):
            return
        
        # 检查用户是否已登录
        if current_user.is_authenticated:
            # 首先检查Cookie的有效性
            from utils.cookie_secure import cookie_secure
            # 使用cookie_secure实例而非类方法进行验证
            if not cookie_secure.validate_secure_cookie():
                logging.info(f"用户 {current_user.username} 的Cookie无效或已过期，自动登出")
                return cookie_secure.handle_cookie_invalidation()
            
            # 获取当前时间 - 修改为使用本地时间
            current_time = datetime.now()
            
            # 获取用户最后活动时间
            last_activity_str = session.get('last_activity_time')
            
            # 如果没有记录最后活动时间，设置当前时间并继续
            if not last_activity_str:
                session['last_activity_time'] = current_time.isoformat()
                # 强制设置会话为已修改
                if not session.modified:
                    session.modified = True  # 确保会话被标记为已修改
                logging.debug(f"初始化最后活动时间: {session['last_activity_time']}")
                return
            
            # 尝试解析最后活动时间
            try:
                last_activity_time = datetime.fromisoformat(last_activity_str)
                
                # 获取超时时间设置 - 修改为先使用SESSION_INACTIVITY_TIMEOUT
                timeout_seconds = current_app.config.get('SESSION_INACTIVITY_TIMEOUT')
                # 如果SESSION_INACTIVITY_TIMEOUT未设置或无效，才使用COOKIE_MAX_AGE或默认值
                if timeout_seconds is None:
                    timeout_seconds = current_app.config.get(
                        'COOKIE_MAX_AGE', 
                        DEFAULT_SESSION_INACTIVITY_TIMEOUT
                    )
                
                # 添加调试日志，显示关键参数值
                logging.debug(f"会话检查 - 当前时间: {current_time}, 最后活动时间: {last_activity_time}, 超时设置: {timeout_seconds}秒")
                
                # 检查是否超过了不活动时间
                if (current_time - last_activity_time).total_seconds() > timeout_seconds:
                    logging.info(f"用户 {current_user.username} 因超过{timeout_seconds//60}分钟不活动而自动退出")
                    
                    # 创建重定向响应
                    response = make_response(redirect(url_for('login.login')))
                    
                    # 执行安全登出
                    response = cookie_secure.logout_user_securely(response)
                    
                    # 添加提示信息
                    flash('您因长时间未操作而自动退出登录', 'info')
                    
                    return response
            except Exception as e:
                logging.error(f"检查会话超时发生错误: {str(e)}")
                # 添加错误日志，帮助排查问题
                logging.error(f"错误详情 - last_activity_str: {last_activity_str}, error_type: {type(e).__name__}")
    
    # 增强update_activity_time函数
    @app.after_request
    def update_activity_time(response):
        # 跳过静态文件的更新
        if request.endpoint == 'static' or request.path.startswith('/static/'):
            return response
        
        # 如果用户已登录，更新最后活动时间
        if current_user.is_authenticated:
            try:
                # 修改为使用本地时间
                previous_time = session.get('last_activity_time')
                session['last_activity_time'] = datetime.now().isoformat()
                # 强制标记会话为已修改
                if not session.modified:
                    session.modified = True
                # 添加调试日志
                logging.debug(f"更新最后活动时间 - 从 {previous_time} 到 {session['last_activity_time']}")
            except Exception as e:
                logging.warning(f"更新最后活动时间失败: {str(e)}")
        
        return response


def set_session_timeout(timeout_minutes):
    """
    动态设置会话不活动超时时间
    
    Args:
        timeout_minutes (int): 超时时间（分钟）
    """
    if current_app:
        current_app.config['SESSION_INACTIVITY_TIMEOUT'] = timeout_minutes * 60
        logging.info(f"会话不活动超时时间已设置为{timeout_minutes}分钟")
        return True
    return False


def get_current_timeout():
    """
    获取当前设置的会话不活动超时时间（分钟）
    """
    if current_app:
        timeout_seconds = current_app.config.get(
            'SESSION_INACTIVITY_TIMEOUT', 
            DEFAULT_SESSION_INACTIVITY_TIMEOUT
        )
        return timeout_seconds // 60
    return DEFAULT_SESSION_INACTIVITY_TIMEOUT // 60