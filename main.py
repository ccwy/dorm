from flask import Flask, redirect, url_for, render_template, current_app, Blueprint, jsonify
import os
import sys
import threading
import signal
import logging
from datetime import datetime, date
from flask_login import LoginManager, current_user, login_required  
from waitress import serve
import webview
# 导入配置类
from config import Config, config
# 从外部配置获取数据库连接
from utils.db_config import DatabaseConfig
from utils.db import db, init_db

# 确定运行环境（优先从命令行参数获取，然后是环境变量，最后是默认值）
import argparse
parser_env = argparse.ArgumentParser(add_help=False)
parser_env.add_argument('--config', type=str)
parser_env.add_argument('--restarted', action='store_true')
args_env, _ = parser_env.parse_known_args()
env = args_env.config if args_env.config else os.environ.get('FLASK_ENV', 'default')

# 确保环境值有效
if env not in config:
    env = 'default'
current_config = config[env]
print(f"当前环境: {env}")
print(f"当前配置: {current_config}")

# 检测是否是重载操作
is_restarted = args_env.restarted
if is_restarted:
    print("检测到重载操作，将重新从本地文件加载数据库配置")
    # 强制重新加载数据库配置，忽略缓存
    import importlib
    from utils import db_config
    importlib.reload(db_config)
    print("数据库配置已重新加载")
else:
    print("数据库配置未重新加载")

# 初始化应用
base_dir = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, 'frozen', False):
    # 打包后的环境
    template_folder = os.path.join(sys._MEIPASS, 'templates')
    static_folder = os.path.join(sys._MEIPASS, 'static')
    app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
    app.config['SQLALCHEMY_DATABASE_URI'] = DatabaseConfig.get_db_uri()
    print(f"打包环境数据库连接: {app.config['SQLALCHEMY_DATABASE_URI']}")
else:
    # 开发环境
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = DatabaseConfig.get_db_uri()
    print(f"开发环境数据库连接: {app.config['SQLALCHEMY_DATABASE_URI']}")

# 应用配置 - 使用当前环境配置
app.config.from_object(current_config)
app.secret_key = current_config.SECRET_KEY
app.permanent_session_lifetime = current_config.PERMANENT_SESSION_LIFETIME
print(f"会话超时时间: {app.permanent_session_lifetime}")

# 在导入其他模块前先初始化日志系统
from utils.log import setup_file_logging
logger = setup_file_logging()  # 初始化日志系统

# 模型导入（补充所有核心模型，确保上下文加载）
from models.user import User
from models.room import Room
from models.room_facility import RoomFacility  # 房间设施模型
from models.dorm import Dorm
from models.utility_room_meter import UtilityMeterReading
from models.log import OperationLog
from models.system_config import SystemConfig  # 确保系统配置模型被导入
from models.room_bed import Bed  # 必须显式导入 Bed 模型
from models.utility_room_bill_record import RoomUtilityRecord  #房间费用主表
from models.utility_room_bill_occupant import RoomUtilityOccupant  #房间人员住宿费用子表
from models.utility_room_bill_checkout import CheckoutUtilityRecord #退宿人员子表
from models.fee_subsidy import FeeSubsidy  #补贴模型
from models.fee_subsidy_usage import FeeSubsidyUsage #补贴子表
from models.ticket import Ticket # 留言模型
from models.ticket_reply import TicketReply # 留言回复模型
from models.todo import Todo # 待办事项模型
from models.todo_progress import TodoProgress # 待办事项进度记录模型
from models.chat_session import ChatSession
from models.chat_participant import ChatParticipant
from models.chat_message import ChatMessage # 聊天模型
logging.info("导入模型完成")

# 蓝图导入
from blueprints import (
    login_bp, user_bp, user_api_bp, user_operations_bp, user_import_export_bp,
    room_bp, room_api_bp, room_import_export_bp,
    dorm_bp, dorm_import_export_bp, system_config_bp, log_bp,
    utility_room_meter_bp, utility_room_meter_import_export_bp, utility_index_bp,
    utility_room_bill_records_bp, utility_room_bill_occupants_bp,utility_room_bill_checkout_bp,
    fee_subsidy_bp,fee_subsidy_import_export_bp,utility_user_records_detail_bp,
    file_sharing_bp,ticket_user_bp, ticket_admin_bp,todo_bp, other_bp, chat_bp
)
# 注册蓝图（保持不变）
app.register_blueprint(login_bp)
app.register_blueprint(user_bp)
app.register_blueprint(user_api_bp)
app.register_blueprint(user_operations_bp)
app.register_blueprint(user_import_export_bp)
app.register_blueprint(room_bp)
app.register_blueprint(room_api_bp)
app.register_blueprint(room_import_export_bp)
app.register_blueprint(dorm_bp)
app.register_blueprint(dorm_import_export_bp)
app.register_blueprint(system_config_bp)
app.register_blueprint(log_bp)
app.register_blueprint(utility_room_meter_bp)
app.register_blueprint(utility_room_meter_import_export_bp)
app.register_blueprint(utility_index_bp)
app.register_blueprint(utility_room_bill_records_bp)# 注册主表蓝图
app.register_blueprint(utility_room_bill_occupants_bp)# 注册子表蓝图（独立注册）
app.register_blueprint(utility_room_bill_checkout_bp)
app.register_blueprint(utility_user_records_detail_bp)
app.register_blueprint(fee_subsidy_bp)
app.register_blueprint(fee_subsidy_import_export_bp)#费用补贴导出蓝图
app.register_blueprint(file_sharing_bp)# 注册文件管理蓝图
app.register_blueprint(ticket_user_bp)# 注册留言管理蓝图
app.register_blueprint(ticket_admin_bp)
app.register_blueprint(todo_bp)# 注册待办事项蓝图
app.register_blueprint(other_bp)# 注册其他功能入口蓝图
app.register_blueprint(chat_bp)# 注册聊天功能蓝图
logging.info("导入蓝图完成")

# 数据库连接配置 - 带连接检查
with app.app_context():
    # 强制检查数据库连接状态
    db_uri = DatabaseConfig.get_db_uri(force_check=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    
    # 检查是否是自动切换到SQLite的情况
    config = DatabaseConfig.load_config()
    if config.get("AUTO_SWITCHED_TO_SQLITE", False):
        logging.warning("系统已自动切换到SQLite数据库，因为MySQL连接失败")

# 初始化数据库（确保所有模型已导入后再初始化）
init_db(app)
logging.info("初始化数据库实例")

# 上下文处理器
@app.context_processor
def inject_common_common_variables():
    # 从数据库获取系统标题
    config = DatabaseConfig.load_config()
    system_title = config.get('SYSTEM_TITLE', '宿舍管理系统')
    return {
        'current_year': datetime.now().year,
        'Config': current_config,
        'date': date,
        'current_user': current_user,
        'system_title': system_title,
        'get_config_value': SystemConfig.get_config_value
    }

# 初始化登录管理器
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login.login'
login_manager.login_message = '请先登录以访问此页面'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# 增加Flask和Werkzeug的日志级别为DEBUG
logging.getLogger('werkzeug').setLevel(logging.DEBUG)
logging.getLogger('flask').setLevel(logging.DEBUG)

# 创建进程清理器实例（关键修改：提前创建以便处理信号）
from utils.process_cleaner import ProcessCleaner #导入进程清理
process_cleaner = ProcessCleaner()
logging.info("创建进程清理实例")

# 导入自动备份线程
from utils.backup import auto_backup
def start_backup():
    with app.app_context():
        auto_backup(app)
# 关键修改：只在主进程中启动备份线程，避免Flask重载导致的重复启动
if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
    # 检查是否已有同名线程
    backup_threads = [t for t in threading.enumerate() if t.name == "auto_backup_thread"]
    if not backup_threads:
        backup_thread = threading.Thread(
            target=start_backup, 
            daemon=True,
            name="auto_backup_thread"  # 指定唯一名称
        )
        backup_thread.start()
        # 记录线程信息便于调试
        with app.app_context():
            logging.info(f"主进程启动备份线程，ID: {backup_thread.ident}")
    else:
        with app.app_context():
            logging.info("备份线程已存在，无需重复启动")

# 初始化会话超时处理器
from utils.session_timeout import setup_session_timeout_handler
setup_session_timeout_handler(app)

# 初始化费用主表记录自动生成调度器
from utils.utility_room_bill_record_scheduler import init_scheduler
scheduler = init_scheduler(app)

# 根路由
@app.route('/')
def root():
    return redirect(url_for('login.login'))

# 导航页路由
@app.route('/index')
@login_required
def index():
    # 判断用户是否为管理员
    if not current_user.is_admin():
        # 非管理员用户重定向到用户信息页面
        return redirect(url_for('user.user_info'))
    # 管理员用户继续访问首页
    return render_template('index.html',title=f"主页")

#解决日志内"GET /.well-known/appspecific/com.chrome.devtools.json HTTP/1.1" 404 -错误
@app.route('/.well-known/appspecific/com.chrome.devtools.json')
def handle_chrome_devtools():
    return jsonify({}), 200 # 返回空JSON对象，状态码200

# 服务器启动函数
def run_server():
    """启动生产环境服务器"""
    # 使用配置中的服务器端口和地址，而不是数据库的
    serve(app, host=current_config.SERVER_HOST, port=current_config.SERVER_PORT)
    logging.info(f"服务器已启动，监听 {current_config.SERVER_HOST}:{current_config.SERVER_PORT}")
    logging.info("服务器启动完成")

# 主程序入口
if __name__ == '__main__':
    # 处理命令行参数
    import argparse
    parser = argparse.ArgumentParser(description='宿舍管理系统')
    parser.add_argument('--uninstall', action='store_true', help='执行卸载清理操作')
    parser.add_argument('--no-reload', action='store_true', help='禁用自动重载')
    parser.add_argument('--config', type=str, help='指定配置环境')
    args = parser.parse_args()
    logging.info("解析命令行参数")
    
    # 处理卸载参数
    if args.uninstall:
        # 检查是否在Docker环境中
        is_docker = os.environ.get('DOCKER_ENV', 'false').lower() == 'true'
        if is_docker:
            logging.warning("在Docker环境中，不执行卸载操作。")
        else:
            from utils.uninstall_handler import handle_uninstall
            handle_uninstall()
    logging.info("处理卸载参数")
    
    # 加载配置
    config_data = DatabaseConfig.load_config()
    
    # 根据配置决定启动模式
    server_mode = config_data.get("SERVER_MODE", "")
    if server_mode == "服务端" and current_config.USE_DESKTOP_VIEW:
        # 服务端模式：不启动WebView2，只启动服务端GUI
        logging.info("以服务端模式启动，不启动WebView2")
        
        # 先启动Flask服务器
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        
        # 等待服务器启动
        import time
        time.sleep(1)
        
        # 与WebView模式一样设置资源引用并注册信号处理器
        process_cleaner.set_resources(
            app=app,
            server_thread=server_thread,
            # 服务端模式没有webview_ref，但可以传入None或其他标识
            webview_ref=None
        )
        process_cleaner.register_signal_handlers()
        
        # 在单独的线程中启动服务端GUI
        from utils.server_gui import run_server_gui
        # 不需要传递自定义exit_app函数，因为process_cleaner会自动处理退出清理
        gui_thread = threading.Thread(target=lambda: run_server_gui(on_exit_callback=None), daemon=False)
        gui_thread.start()
        
        # 等待GUI线程结束
        gui_thread.join()
        
        # GUI关闭后，退出应用 - process_cleaner会自动处理退出清理
    elif server_mode == "客户端" and current_config.USE_DESKTOP_VIEW:
        # 客户端模式：启动WebView2窗口
        logging.info("启动Flask服务器")
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        
        import time
        time.sleep(1)
        logging.info("启动WebView窗口")
        # 在应用上下文中从数据库获取系统标题
        try:
            with app.app_context():
                config = DatabaseConfig.load_config()
                system_title = config.get('SYSTEM_TITLE', '宿舍管理系统')
        except Exception as e:
            logging.error(f"获取系统标题时出错: {str(e)}")
            system_title = '宿舍管理系统'
        
        # 创建窗口并保存实例引用
        window = webview.create_window(
            title=system_title,
            # 使用服务器的地址和端口，而不是数据库的
            url=f'http://{current_config.SERVER_HOST}:{current_config.SERVER_PORT}',
            width=1200,
            height=800,
            resizable=True
        )
        logging.info("WebView窗口创建完成")
        
        # 在应用完全启动后执行自动退出登录机制
        # 确保在服务器启动且WebView窗口创建后执行
        logging.info("应用完全启动，执行自动退出登录机制...")
        from utils.auto_logout import auto_logout_on_startup
        with app.app_context():
            auto_logout_on_startup()
        
        # 启动延迟注入线程，确保WebView完全初始化后再注入JavaScript
        from utils.webview_injector import start_delayed_injection
        injection_thread = start_delayed_injection()
        
        # 设置资源引用并注册信号处理器
        process_cleaner.set_resources(
            app=app,
            server_thread=server_thread,
            webview_ref=window  # 传递窗口实例而不是模块
        )
        process_cleaner.register_signal_handlers()
        
        # 启动WebView并等待其关闭
        webview.start(debug=current_config.DEBUG)
        
        # WebView窗口已关闭，执行彻底的资源清理
        logging.info("WebView窗口已关闭，开始执行彻底的资源清理...")
        
        # 调用增强版cleanup_all_resources进行优雅清理
        process_cleaner.cleanup_all_resources(signal_received=0)  # 传递0表示非信号触发的清理
        # 检查并强制终止服务器线程
        if server_thread.is_alive():
            logging.warning("服务器线程未能正常终止，强制退出程序")
            os._exit(0)
        logging.info("资源清理完成，程序即将退出")
        
        # 最后的安全检查，确保所有线程都已终止
        try:
            if server_thread.is_alive():
                logging.warning("最后的安全检查：服务器线程仍然存活，强制退出")
                os._exit(0)
        except:
            # 确保无论如何都会退出
            os._exit(0)
    else:
        # 开发模式：根据配置决定启动网页模式
        logging.info("以开发模式启动")
        process_cleaner.set_resources(app=app)
        process_cleaner.register_signal_handlers()
        # 开发环境启动网页模式
        app.run(
            host=current_config.SERVER_HOST,  # 使用服务器主机配置
            port=current_config.SERVER_PORT,  # 使用服务器端口配置
            debug=current_config.DEBUG,
            use_reloader=current_config.DEBUG
        )
