import logging
import os
import sys
import shutil

from flask import current_app, make_response, has_request_context

# 导入系统环境检测工具
from utils.system_detector import is_docker
# 导入我们的安全Cookie管理模块
from utils.cookie_secure import cookie_secure


def get_force_relogin_file_path():
    """
    [已弃用] 保留此函数以兼容旧调用，强制重新登录已改为内存信号机制
    不再使用文件标志，统一使用 current_app.config['FORCE_RELOGIN']
    """
    logging.warning("get_force_relogin_file_path() 已弃用，请使用 current_app.config['FORCE_RELOGIN']")
    return None

def auto_logout_on_startup():
    """
    应用启动时自动退出所有已登录用户的会话
    确保每次应用启动时都是未登录状态，解决残留登录会话问题
    使用多层防护策略确保彻底清除用户认证状态
    """
    try:
        logging.info("应用启动时执行自动退出登录机制")
        
        # 创建一个空响应对象，用于清除Cookie和会话
        response = make_response()
        
        # 方法1: 使用安全Cookie管理模块提供的完整登出功能
        try:
            # 检查是否存在活跃的请求上下文
            if has_request_context():
                # 只有在有请求上下文时才调用logout_user_securely方法
                # 这个方法会：
                # 1. 调用Flask-Login的登出方法
                # 2. 清除所有会话数据并生成新的会话ID
                # 3. 清除Flask会话Cookie和remember_token
                # 4. 清除我们自定义的安全用户信息Cookie
                # 5. 添加响应头防止缓存
                response = cookie_secure.logout_user_securely(response)
                logging.info("使用cookie_secure模块成功执行了安全登出操作")
            else:
                # 没有请求上下文时，记录一条信息日志并跳过这个步骤
                logging.info("没有活跃的请求上下文，跳过cookie_secure安全登出操作")
        except Exception as inner_e:
            logging.warning(f"使用cookie_secure执行安全登出失败: {str(inner_e)}")
        
        # 方法2: 使用安全Cookie管理模块清除Flask会话目录
        if hasattr(current_app, 'session_interface') and hasattr(current_app.session_interface, 'directory'):
            session_dir = current_app.session_interface.directory
            if session_dir and os.path.exists(session_dir):
                try:
                    # 统计要删除的文件数量
                    file_count = len([f for f in os.listdir(session_dir) if os.path.isfile(os.path.join(session_dir, f))])
                    # 删除目录下所有文件
                    for filename in os.listdir(session_dir):
                        file_path = os.path.join(session_dir, filename)
                        if os.path.isfile(file_path):
                            os.unlink(file_path)
                    logging.info(f"已清除会话目录中的 {file_count} 个会话文件")
                except Exception as inner_e:
                    logging.warning(f"清除会话目录失败: {str(inner_e)}")
        
        # 方法3: 清除临时文件和缓存 - 使用独特的目录名称便于识别
        app_unique_suffix = "dorm_mgmt_v1.0"
        temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', f'temp_{app_unique_suffix}')
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                os.makedirs(temp_dir, exist_ok=True)
                logging.info("已清除临时文件目录")
            except Exception as inner_e:
                logging.warning(f"清除临时文件目录失败: {str(inner_e)}")
        
        # 方法5: 设置全局标志，强制要求重新登录
        current_app.config['FORCE_RELOGIN'] = True
        logging.info("已设置强制重新登录标志")
        
        # 清除可能存在的用户认证相关缓存
        if hasattr(current_app, 'cache'):
            try:
                current_app.cache.clear()
                logging.info("已清除应用缓存")
            except Exception as inner_e:
                logging.warning(f"清除应用缓存失败: {str(inner_e)}")
        
        # 清除应用级别的用户相关属性
        if hasattr(current_app, 'user_id'):
            delattr(current_app, 'user_id')
            logging.debug("已清除应用级别的用户ID")
        if hasattr(current_app, 'username'):
            delattr(current_app, 'username')
            logging.debug("已清除应用级别的用户名")
        if hasattr(current_app, 'is_authenticated'):
            current_app.is_authenticated = False
            logging.debug("已设置应用认证状态为未登录")
        
        # 额外添加内存标志，用于跨请求通信（替代文件标志，更高效可靠）
        current_app.config['FORCE_RELOGIN'] = True
        logging.info("已设置强制重新登录内存标志")
        
        logging.info("自动退出登录机制执行成功，已清除所有可能的残留登录状态")
        
    except Exception as e:
        # 记录错误但不中断应用启动
        logging.error(f"应用启动时自动退出登录机制执行失败: {str(e)}")


def check_force_relogin_flag():
    """
    检查是否存在强制重新登录标志（内存信号）
    使用 current_app.config 替代文件标志，更高效可靠
    """
    try:
        return current_app.config.get('FORCE_RELOGIN', False)
    except RuntimeError:
        # 无应用上下文时返回False
        return False


def clear_force_relogin_flag():
    """
    清除强制重新登录标志（内存信号）
    使用 current_app.config 替代文件标志
    """
    try:
        current_app.config['FORCE_RELOGIN'] = False
        logging.info("已清除强制重新登录内存标志")
    except RuntimeError:
        logging.warning("无应用上下文，无法清除强制重新登录标志")
