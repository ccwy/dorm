import os
import sys
from datetime import timedelta
from utils.db_config import DatabaseConfig

# 确定配置文件路径，支持开发环境和打包环境
def get_app_dir():
    if getattr(sys, 'frozen', False):
        # 打包环境 - 配置文件始终存储在应用程序所在目录
        return os.path.dirname(sys.executable)
    else:
        # 开发环境 - 使用项目根目录
        return os.path.abspath(os.path.dirname(__file__))

# 启动时仅加载一次配置，避免Config/ProductionConfig/DevelopmentConfig重复调用load_config()
_shared_db_config = DatabaseConfig.load_config()

class Config:
    # 基础配置
    SECRET_KEY = 'cDds8dsjhuHUDSHUd3SH78chfdsufnhuyr78djsHDSHADEU'
    SESSION_COOKIE_NAME = 'CRspli9ois'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=12)
    
    # Cookie安全配置
    # 这些配置会被cookie_secure模块用来设置Cookie的默认参数
    # 注意：具体项目中可能需要根据实际域名和环境调整这些设置
    COOKIE_DOMAIN = None  # Cookie域名，默认为None（当前域名）
    COOKIE_SECURE = None  # 是否仅通过HTTPS传输，默认None表示根据环境自动决定
    COOKIE_PATH = '/'  # Cookie路径，默认为根路径
    COOKIE_HTTPONLY = True  # 是否仅HTTP可用，默认为True（防止XSS攻击）
    COOKIE_SAMESITE = 'Lax'  # SameSite策略，默认为'Lax'（防止CSRF攻击）
    COOKIE_MAX_AGE = 24 * 60 * 60  # Cookie最大存活时间（秒），默认为24小时
    
    # 会话不活动超时设置
    # 用户在这段时间内没有任何操作将被自动退出登录
    SESSION_INACTIVITY_TIMEOUT = 3 * 60 * 60  # 3小时不活动自动退出
    
    # 基础目录
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # 从外部数据库配置文件获取连接信息（使用共享配置，避免重复load_config调用）
    db_config = _shared_db_config
    SQL_TYPE = db_config.get('SQL_TYPE', "SQLITE")
    # 服务器配置
    SERVER_HOST = '0.0.0.0'
    SERVER_PORT = db_config.get('SERVER_PORT', 35168)  # 使用安全的端口，避免浏览器阻止

    # 备份目录配置
    if os.environ.get('DOCKER_ENV', 'false').lower() == 'true':  # 优先检查Docker环境
        BACKUP_DIR = '/data/backups'    # Docker环境 - 使用外部数据卷路径
    elif getattr(sys, 'frozen', False):
        APP_DIR = get_app_dir()   # 打包环境 - 备份目录保存在应用程序所在目录的data/backups下
        BACKUP_DIR = os.path.join(APP_DIR, 'data', 'backups')
    else:
        BACKUP_DIR = os.path.join(BASE_DIR, 'data', 'backups')  # 开发环境 - 保持原有路径
    
    # 初始化数据库连接字符串
    SQLALCHEMY_DATABASE_URI = DatabaseConfig.get_db_uri()
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False  # 禁用修改跟踪

    # 数据库引擎选项配置
    SQLALCHEMY_ENGINE_OPTIONS = {}  # 默认为空字典，将在运行时根据数据库类型被覆盖
    
    # 配置：控制使用Web浏览器还是桌面窗口
    is_docker = os.environ.get('DOCKER_ENV', 'false').lower() == 'true'
    if is_docker:
        USE_DESKTOP_VIEW = False
    else:
        USE_DESKTOP_VIEW = True  # False为开发网页模式，True为桌面窗口模式，方便开发调试
    
    DEBUG = True  # 是否开启调试模式

    # 开发模式自动登录开关
    # 设置为True时，程序运行免登录，自动以admin账号登录
    # 仅建议在开发环境中开启，生产环境必须为False
    DEV_AUTO_LOGIN = False

    # API配置
    API_BASE_URL = ""  # 基础API地址
    API_TIMEOUT = 10  # API调用超时时间（秒）

#生产环境
class ProductionConfig(Config):
    db_config = _shared_db_config  # 使用共享配置，避免重复load_config调用
    SECRET_KEY = 'WUQIOkxuidS3zcadSwdsdSQzcsWa8dsa'
    DEBUG = True
    SYSTEM_TITLE = db_config.get('SERVER_PORT', "行政后勤管理系统")
    # 根据SERVER_MODE配置决定SERVER_HOST
    # 服务端模式：使用0.0.0.0
    # 客户端模式：使用127.0.0.1
    # 同时保留Docker环境的优先判断
    if os.environ.get('DOCKER_ENV', 'false').lower() == 'true':
        SERVER_HOST = '0.0.0.0'
    else:
        server_mode = db_config.get('SERVER_MODE', '客户端')
        SERVER_HOST = '0.0.0.0' if server_mode == '服务端' else '127.0.0.1'
    SERVER_PORT = int(db_config.get('SERVER_PORT', 35168))

#开发环境
class DevelopmentConfig(Config):
    db_config = _shared_db_config  # 使用共享配置，避免重复load_config调用
    # 根据SERVER_MODE配置决定SERVER_HOST
    # 服务端模式：使用0.0.0.0
    # 客户端模式：使用127.0.0.1
    # 同时保留Docker环境的优先判断
    if os.environ.get('DOCKER_ENV', 'false').lower() == 'true':
        SERVER_HOST = '0.0.0.0'
    else:
        server_mode = db_config.get('SERVER_MODE', '客户端')
        SERVER_HOST = '0.0.0.0' if server_mode == '服务端' else '127.0.0.1'
    SERVER_PORT = int(db_config.get('SERVER_PORT', 35168))
    DEBUG = True
    SYSTEM_TITLE = "行政后勤管理系统（开发模式）"
    DEV_AUTO_LOGIN = True  # 开发模式自动登录为admin账号

#模式选择
config = {
    'development': DevelopmentConfig, #开发环境
    'production': ProductionConfig,   #生产环境
    'default': ProductionConfig       #系统默认使用开发环境配置，但桌面窗口模式由USE_DESKTOP_VIEW控制
}
