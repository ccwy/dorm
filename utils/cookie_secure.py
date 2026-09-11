import os
import logging
import json
import base64
import hmac
import hashlib
import os  # 添加os模块导入
from flask import  make_response, request, session,current_app
from flask_login import  logout_user

# 添加Docker环境检测函数
def is_docker_env():
    """检测是否在Docker环境中"""
    try:
        # 检查环境变量，与config.py中的逻辑保持一致
        if os.environ.get('DOCKER_ENV', 'false').lower() == 'true':
            return True
        # 额外检查Docker特征文件，增强兼容性
        if os.path.exists('/.dockerenv'):
            return True
        return False
    except Exception as e:
        logging.error(f"Docker环境检测失败: {str(e)}")
        return False

class CookieSecureManager:
    """安全Cookie管理类，提供完整的Cookie操作功能
    
    Cookie参数设置入口：
    1. 方法参数：直接在调用set_cookie或delete_cookie方法时传入具体参数值
    2. 应用配置：在config.py中通过COOKIE_*配置项设置全局默认值
    3. 默认值：如果上述两种方式都没有设置，则使用方法内部定义的默认值
    
    参数优先级：方法参数 > 应用配置 > 默认值
    """
    
    @staticmethod
    def _get_secret_key():
        """获取应用的密钥，用于加密"""
        if current_app and hasattr(current_app, 'config') and 'SECRET_KEY' in current_app.config:
            return current_app.config['SECRET_KEY']
        # 回退密钥，不应该在生产环境使用
        return 'fallback_secret_key_should_be_changed_in_production'
    
    @staticmethod
    def _encrypt_value(value):
        """加密Cookie值"""
        try:
            # 如果值不是字符串，先序列化为JSON
            if not isinstance(value, str):
                value = json.dumps(value)
                
            # 使用HMAC-SHA256进行签名
            secret_key = CookieSecureManager._get_secret_key()
            signature = hmac.new(
                secret_key.encode('utf-8'),
                value.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            # 将值和签名组合
            combined = f"{value}::{signature}"
            
            # Base64编码以确保安全传输
            encoded = base64.b64encode(combined.encode('utf-8')).decode('utf-8')
            return encoded
        except Exception as e:
            logging.error(f"加密Cookie值失败: {str(e)}")
            # 出错时返回原始值
            if not isinstance(value, str):
                return json.dumps(value)
            return value
    
    @staticmethod
    def _decrypt_value(encrypted_value):
        """解密Cookie值"""
        try:
            # Base64解码
            decoded = base64.b64decode(encrypted_value.encode('utf-8')).decode('utf-8')
            
            # 分离值和签名
            if '::' in decoded:
                value, signature = decoded.split('::', 1)
                
                # 验证签名
                secret_key = CookieSecureManager._get_secret_key()
                expected_signature = hmac.new(
                    secret_key.encode('utf-8'),
                    value.encode('utf-8'),
                    hashlib.sha256
                ).hexdigest()
                
                if hmac.compare_digest(signature, expected_signature):
                    # 尝试将值解析为JSON
                    try:
                        return json.loads(value)
                    except json.JSONDecodeError:
                        return value
                else:
                    logging.warning("Cookie签名验证失败，可能被篡改")
                    return None
            
            # 如果没有签名，尝试直接解析为JSON或返回字符串
            try:
                return json.loads(decoded)
            except json.JSONDecodeError:
                return decoded
        except Exception as e:
            logging.error(f"解密Cookie值失败: {str(e)}")
            return None
    
    @staticmethod
    def set_cookie(response, key, value='', max_age=None, expires=None, path='/',
                  domain=None, secure=None, httponly=True, samesite='Lax', encrypt=True):
        """安全设置Cookie
        
        Args:
            response (Response): Flask响应对象，必须提供
            key (str): Cookie名称，必须提供
            value (str, optional): Cookie值，默认为空字符串
            max_age (int, optional): Cookie最大存活时间（秒）
            expires (datetime, optional): Cookie过期时间
            path (str, optional): Cookie路径，默认为'/'
            domain (str, optional): Cookie域名
            secure (bool, optional): 是否仅通过HTTPS传输，未指定时自动根据环境决定
            httponly (bool, optional): 是否仅HTTP可用，默认为True（防止XSS）
            samesite (str, optional): SameSite策略，默认为'Lax'（防止CSRF）
            encrypt (bool, optional): 是否加密Cookie值，默认为True
        
        Returns:
            Response: 设置了Cookie的响应对象
        """
        if not response:
            raise ValueError("Cookie设置失败: 必须提供响应对象")
            
        if not key:
            raise ValueError("Cookie设置失败: 必须提供Cookie名称")
        
        try:
            # 从应用配置获取默认参数
            # 优先级: 方法参数 > 应用配置 > 默认值
            if current_app:
                logging.debug(f"从应用配置获取Cookie参数，当前配置: COOKIE_DOMAIN={current_app.config.get('COOKIE_DOMAIN')}, COOKIE_SECURE={current_app.config.get('COOKIE_SECURE')}")
                
                # 从配置中获取默认domain
                if domain is None:
                    domain = current_app.config.get('COOKIE_DOMAIN', None)
                    logging.debug(f"使用配置中的COOKIE_DOMAIN: {domain}")
                
                # 从配置中获取默认secure
                if secure is None:
                    secure_config = current_app.config.get('COOKIE_SECURE')
                    if secure_config is not None:
                        secure = secure_config
                    else:
                        # 如果配置中未设置，根据环境自动决定
                        secure = not current_app.debug
                    logging.debug(f"使用的secure标志: {secure}")
                
                # 从配置中获取默认path
                if path == '/':  # 只有当使用默认值时才从配置获取
                    path_config = current_app.config.get('COOKIE_PATH')
                    if path_config is not None:
                        path = path_config
                    logging.debug(f"使用的path: {path}")
                
                # 从配置中获取默认httponly
                httponly_config = current_app.config.get('COOKIE_HTTPONLY')
                if httponly_config is not None:
                    httponly = httponly_config
                logging.debug(f"使用的httponly: {httponly}")
                
                # 从配置中获取默认samesite
                samesite_config = current_app.config.get('COOKIE_SAMESITE')
                if samesite_config is not None:
                    samesite = samesite_config
                logging.debug(f"使用的samesite: {samesite}")
                
                # 从配置中获取默认max_age
                if max_age is None:
                    max_age_config = current_app.config.get('COOKIE_MAX_AGE')
                    if max_age_config is not None:
                        max_age = max_age_config
                    logging.debug(f"使用配置中的COOKIE_MAX_AGE: {max_age}")
            else:
                # 没有应用上下文时的默认值
                logging.warning("没有应用上下文，使用硬编码默认值")
                if secure is None:
                    secure = False
            
            # 加密Cookie值
            if encrypt:
                value = CookieSecureManager._encrypt_value(value)
            
            # 设置Cookie，添加安全标志
            response.set_cookie(
                key=key,
                value=value,
                max_age=max_age,
                expires=expires,
                path=path,
                domain=domain,
                secure=secure,
                httponly=httponly,
                samesite=samesite
            )
            # 修改日志记录，添加更详细的Cookie信息，包括有效期
            logging.debug(f"已设置Cookie: {key}, max_age={max_age}, expires={expires}, path={path}, domain={domain}, secure={secure}, httponly={httponly}, samesite={samesite}")
        except Exception as e:
            logging.error(f"设置Cookie '{key}' 失败: {str(e)}")
            raise  # 向上抛出异常，确保调用者知道设置失败
            
        return response
    
    @staticmethod
    def get_cookie(key, default=None, decrypt=True):
        """安全获取Cookie"""
        try:
            # 检查请求中是否存在Cookie
            if key in request.cookies:
                value = request.cookies[key]
                
                # 解密Cookie值
                if decrypt:
                    value = CookieSecureManager._decrypt_value(value)
                    # 如果解密失败，返回默认值
                    if value is None:
                        return default
                
                return value
            
            # Cookie不存在，返回默认值
            return default
        except Exception as e:
            logging.error(f"获取Cookie '{key}' 失败: {str(e)}")
            return default
    
    @staticmethod
    def delete_cookie(response, key, path='/', domain=None):
        """安全删除Cookie
        
        Args:
            response (Response): Flask响应对象，必须提供
            key (str): Cookie名称，必须提供
            path (str, optional): Cookie路径，默认为'/'
            domain (str, optional): Cookie域名
        
        Returns:
            Response: 删除了Cookie的响应对象
        """
        if not response:
            raise ValueError("Cookie删除失败: 必须提供响应对象")
            
        if not key:
            raise ValueError("Cookie删除失败: 必须提供Cookie名称")
        
        try:
            # 从应用配置获取默认参数
            # 优先级: 方法参数 > 应用配置 > 默认值
            if current_app:
                logging.debug(f"从应用配置获取删除Cookie参数，当前配置: COOKIE_DOMAIN={current_app.config.get('COOKIE_DOMAIN')}, COOKIE_PATH={current_app.config.get('COOKIE_PATH')}")
                
                # 从配置中获取默认domain
                if domain is None:
                    domain = current_app.config.get('COOKIE_DOMAIN', None)
                    logging.debug(f"使用配置中的COOKIE_DOMAIN: {domain}")
                
                # 从配置中获取默认path
                if path == '/':  # 只有当使用默认值时才从配置获取
                    path_config = current_app.config.get('COOKIE_PATH')
                    if path_config is not None:
                        path = path_config
                    logging.debug(f"使用的path: {path}")
                
                # 从配置中获取默认httponly
                httponly_config = current_app.config.get('COOKIE_HTTPONLY')
                if httponly_config is not None:
                    httponly = httponly_config
                else:
                    httponly = True  # 默认值
                logging.debug(f"使用的httponly: {httponly}")
                
                # 从配置中获取默认samesite
                samesite_config = current_app.config.get('COOKIE_SAMESITE')
                if samesite_config is not None:
                    samesite = samesite_config
                else:
                    samesite = 'Lax'  # 默认值
                logging.debug(f"使用的samesite: {samesite}")
            else:
                # 没有应用上下文时的默认值
                logging.warning("没有应用上下文，使用硬编码默认值")
                httponly = True
                samesite = 'Lax'
            
            # 设置Cookie过期时间为过去时间
            response.set_cookie(
                key=key,
                value='',
                expires=0,  # 立即过期
                path=path,
                domain=domain,
                httponly=httponly,
                samesite=samesite
            )
            logging.debug(f"已删除Cookie: {key}")
        except Exception as e:
            logging.error(f"删除Cookie '{key}' 失败: {str(e)}")
            raise  # 向上抛出异常，确保调用者知道删除失败
            
        return response
    
    @staticmethod
    def has_cookie(key):
        """检查Cookie是否存在"""
        try:
            return key in request.cookies
        except Exception as e:
            logging.error(f"检查Cookie存在性失败: {str(e)}")
            return False
    
    @staticmethod
    def clear_flask_session_cookie(response):
        """清除Flask会话Cookie
        
        Args:
            response (Response): Flask响应对象，必须提供
        
        Returns:
            Response: 已清除会话Cookie的响应对象
        """
        if not response:
            raise ValueError("清除Flask会话Cookie失败: 必须提供响应对象")
            
        try:
            # 获取会话Cookie名称
            session_cookie_name = current_app.config.get('SESSION_COOKIE_NAME', 'session')
            
            # 清除会话Cookie
            CookieSecureManager.delete_cookie(response, session_cookie_name)
            
            # 清除remember_token Cookie（如果使用了Flask-Login）
            remember_token_name = current_app.config.get('REMEMBER_COOKIE_NAME', 'remember_token')
            CookieSecureManager.delete_cookie(response, remember_token_name)
            
            logging.debug(f"已清除Flask会话Cookie和remember_token")
        except Exception as e:
            logging.error(f"清除Flask会话Cookie失败: {str(e)}")
            raise
            
        return response
    
    @staticmethod
    def setup_secure_user_session(user, remember=True, response=None):
        """设置安全的用户会话，自动适应Docker环境"""
        try:
            from flask_login import login_user
            from flask import current_app, session
            from datetime import datetime
            
            # 确保提供了响应对象
            if response is None:
                raise ValueError("必须提供响应对象")
            
            # 登录用户
            login_user(user, remember=remember)
            
            # 使用本地时间，与项目整体保持一致
            current_time = datetime.now().isoformat()
            session['login_time'] = current_time
            session['last_activity_time'] = current_time  # 初始化活动时间
            # 确保会话被标记为已修改
            session.modified = True
            
            # 检查是否在Docker环境中
            docker_env = is_docker_env()
            
            # 根据环境设置Cookie参数
            cookie_params = {
                'secure': False if docker_env else current_app.config.get('COOKIE_SECURE', None),
                'samesite': 'Lax' if docker_env else current_app.config.get('COOKIE_SAMESITE', 'Lax'),
                'max_age': current_app.config.get('COOKIE_MAX_AGE')  # 显式添加max_age参数
            }
            
            # 设置用户会话Cookie（修改为使用与validate_secure_cookie一致的Cookie名称）
            if hasattr(user, 'id'):
                # 创建包含用户信息的字典，而不仅仅是用户ID
                user_info = {
                    'id': user.id,
                    'username': getattr(user, 'username', ''),
                    'name': getattr(user, 'name', '')
                }
                # 使用与validate_secure_cookie一致的Cookie名称
                response = CookieSecureManager.set_cookie(
                    response=response,
                    key='secure_user_info',  # 修改为使用secure_user_info
                    value=user_info,         # 存储完整的用户信息字典
                    **cookie_params
                )
            
            logging.info(f"已为用户 {user.id if hasattr(user, 'id') else 'unknown'} 设置安全会话，Docker环境: {docker_env}")
            return response
        except Exception as e:
            logging.error(f"设置用户会话失败: {str(e)}")
            raise ValueError(f"会话设置失败: {str(e)}")

    @staticmethod
    def logout_user_securely(response=None):
        """安全退出登录，清除所有会话和Cookie信息
        
        Args:
            response (Response, optional): Flask响应对象，如果未提供则创建新的
        
        Returns:
            Response: 已清除会话和Cookie的响应对象
        """
        try:
            # 如果未提供响应对象，创建一个
            if response is None:
                response = make_response()
            elif not response:
                raise ValueError("退出登录失败: 提供的响应对象无效")
            
            # 调用Flask-Login的登出方法
            logout_user()
            
            # 清除Flask-Login存储的用户ID
            session.pop('_user_id', None)
            
            # 彻底清除所有会话数据
            session.clear()
            # 强制标记会话为已修改
            session.modified = True
            
            # 额外清除可能残留的用户相关会话变量
            session.pop('user_id', None)
            session.pop('username', None)
            session.pop('role', None)
            session.pop('student_id', None)
            
            # 生成新的会话ID，防止会话固定攻击
            if hasattr(session, 'regenerate'):
                session.regenerate()
            
            # 确保会话立即过期
            session.permanent = False
            
            # 添加响应头防止缓存
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            
            # 清除Flask会话和remember_token cookie
            response = CookieSecureManager.clear_flask_session_cookie(response)
            
            # 清除我们额外设置的安全用户信息Cookie
            response = CookieSecureManager.delete_cookie(response, 'secure_user_info')
            
            logging.info("用户已安全退出登录")
        except Exception as e:
            logging.error(f"退出登录时发生错误: {str(e)}")
            # 出错时仍返回响应对象
            if response is None:
                response = make_response()
            return response

        return response
    
    # 在validate_secure_cookie方法中增强时间比较逻辑
    @staticmethod
    def validate_secure_cookie():
        """验证安全Cookie的有效性，包括时间验证"""
        try:
            from flask_login import current_user
            from flask import current_app, request, session
            from datetime import datetime
            
            # 检查用户是否已登录
            if not current_user.is_authenticated:
                # 未登录状态返回True，避免影响登录流程
                return True
            
            # 获取安全用户信息Cookie
            secure_user_info = current_user.get_id()  # 简化获取用户ID的方式
            
            if not secure_user_info:
                logging.warning(f"安全用户信息Cookie不存在或格式无效，当前用户: {current_user.username}")
                return False
            
            # 检查Cookie是否过期
            # 从应用配置获取Cookie最大存活时间
            max_age = current_app.config.get('COOKIE_MAX_AGE')
            # 如果设置了max_age，检查会话中的登录时间是否超过了最大存活时间
            if max_age:
                # 获取用户登录时间
                login_time_str = session.get('login_time')
                if login_time_str:
                    try:
                        login_time = datetime.fromisoformat(login_time_str)
                        # 修改为使用本地时间，与session['login_time']保持一致
                        current_time = datetime.now()
                        # 添加调试日志
                        logging.debug(f"验证Cookie过期时间 - 当前时间: {current_time}, 登录时间: {login_time}, 最大存活时间: {max_age}秒")
                        # 检查是否超过了最大存活时间
                        if (current_time - login_time).total_seconds() > max_age:
                            logging.warning(f"用户 {current_user.username} 的会话已超过最大存活时间")
                            return False
                    except Exception as e:
                        logging.error(f"解析登录时间时发生错误: {str(e)}")
                        # 添加详细的错误日志，包含login_time_str的具体值
                        logging.error(f"登录时间字符串值: {login_time_str}")
                        # 解析失败时不影响验证结果
                        pass
        
            # 所有验证通过
            return True
        except Exception as e:
            logging.error(f"验证安全Cookie时发生错误: {str(e)}")
            return False

    @staticmethod
    def handle_cookie_invalidation():
        """处理Cookie失效的情况，执行安全登出
        
        Returns:
            Response: 重定向到登录页面的响应对象
        """
        from flask import redirect, url_for, flash
        
        logging.info("检测到Cookie失效，执行自动安全登出")
        
        # 创建重定向响应
        response = redirect(url_for('login.login'))
        
        # 执行安全登出
        response = CookieSecureManager.logout_user_securely(response)
        
        # 添加提示信息
        flash('您的登录已过期，请重新登录', 'info')
        
        return response

# 创建单例实例，方便直接导入使用
cookie_secure = CookieSecureManager()
