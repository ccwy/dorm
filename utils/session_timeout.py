import logging
from datetime import datetime
from flask import current_app, request, session, redirect, url_for, flash, make_response
from flask_login import current_user, logout_user


def setup_session_timeout_handler(app):
    """设置会话超时处理器，检测用户不活动时间并自动退出登录"""

    @app.before_request
    def check_session_timeout():
        # 跳过静态文件和登录相关路由
        if request.endpoint in ('static', 'login.login', 'login.logout') or \
           request.path.startswith('/static/'):
            return

        if not current_user.is_authenticated:
            return

        current_time = datetime.now()
        last_activity_str = session.get('last_activity_time')

        # 首次访问，初始化活动时间
        if not last_activity_str:
            session['last_activity_time'] = current_time.isoformat()
            session.modified = True
            return

        try:
            last_activity_time = datetime.fromisoformat(last_activity_str)
            timeout_seconds = current_app.config.get('SESSION_INACTIVITY_TIMEOUT', 3 * 60 * 60)

            if (current_time - last_activity_time).total_seconds() > timeout_seconds:
                logging.info(f"用户 {current_user.username} 因超过{timeout_seconds // 60}分钟不活动而自动退出")
                # 先清除会话再调用logout_user()，确保remember cookie被正确删除
                session.clear()
                logout_user()
                session.modified = True
                flash('您因长时间未操作而自动退出登录', 'info')
                return redirect(url_for('login.login'))
        except Exception as e:
            logging.error(f"检查会话超时发生错误: {e}")

    @app.after_request
    def update_activity_time(response):
        # 跳过静态文件
        if request.endpoint == 'static' or request.path.startswith('/static/'):
            return response

        # 已登录用户更新活动时间
        if current_user.is_authenticated:
            try:
                session['last_activity_time'] = datetime.now().isoformat()
                session.modified = True
            except Exception as e:
                logging.warning(f"更新活动时间失败: {e}")

        return response