from flask import Flask, redirect, url_for, render_template, current_app, Blueprint, jsonify
import os
import sys
import threading
import signal
import logging
import time
from datetime import datetime, date
from flask_login import LoginManager, current_user, login_required  

# ===== 启动计时 profiling =====
_startup_time = time.perf_counter()
def _stamp(label):
    """记录启动阶段耗时"""
    elapsed = time.perf_counter() - _startup_time
    logging.info(f"[启动计时] {label}: {elapsed:.3f}s")

# 导入配置类
from config import Config, config
_stamp("导入config")
# 从外部配置获取数据库连接
from utils.db_config import DatabaseConfig
from utils.db import db, init_db
_stamp("导入db_config+db")

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
_stamp("初始化日志系统")

# 仅导入User模型（login_manager.user_loader需要）
# 其他模型在init_db()中按需导入，无需在此重复导入
from models.user import User
_stamp("导入User模型")

# 蓝图导入
from blueprints import (
    login_bp, user_bp, user_api_bp, user_operations_bp,
    user_import_export_bp, room_import_export_bp,
    room_bp, room_api_bp,
    dorm_bp, dorm_import_export_bp,
    system_config_bp, log_bp,
    utility_room_meter_bp, utility_room_meter_import_export_bp,
    utility_index_bp,
    utility_room_bill_records_bp, utility_room_bill_occupants_bp, utility_room_bill_checkout_bp,
    fee_subsidy_bp, fee_subsidy_import_export_bp,
    utility_user_records_detail_bp,
    file_sharing_bp, ticket_user_bp, ticket_admin_bp, todo_bp, other_bp, chat_bp,
    fixed_asset_bp, fixed_asset_api_bp, fixed_asset_import_export_bp,
    department_bp, department_api_bp, department_import_export_bp,
    supplier_bp, supplier_api_bp, supplier_import_export_bp,
    supply_index_bp,
    supply_item_bp, supply_item_api_bp, supply_item_import_export_bp,
    storage_location_bp, storage_location_api_bp, storage_location_import_export_bp,
    supply_stock_detail_bp, supply_stock_detail_api_bp,
    stock_in_bp, stock_in_api_bp, stock_in_import_export_bp,
    stock_out_bp, stock_out_api_bp, stock_out_import_export_bp,
    supply_inventory_bp, supply_inventory_api_bp, supply_inventory_import_export_bp,
    supply_stock_record_bp, supply_stock_record_api_bp,
    role_bp,
    contract_bp, contract_api_bp, contract_import_export_bp,
    maintenance_user_bp, maintenance_admin_bp, maintenance_staff_bp, maintenance_api_bp
)
_stamp("导入37个蓝图")
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
app.register_blueprint(fee_subsidy_import_export_bp)
app.register_blueprint(file_sharing_bp)# 注册文件管理蓝图
app.register_blueprint(ticket_user_bp)# 注册留言管理蓝图
app.register_blueprint(ticket_admin_bp)
app.register_blueprint(todo_bp)# 注册待办事项蓝图
app.register_blueprint(other_bp)# 注册其他功能入口蓝图
app.register_blueprint(chat_bp)# 注册聊天功能蓝图
app.register_blueprint(fixed_asset_bp)
app.register_blueprint(fixed_asset_api_bp)
app.register_blueprint(fixed_asset_import_export_bp)
app.register_blueprint(department_bp)
app.register_blueprint(department_api_bp)
app.register_blueprint(department_import_export_bp)
# 注册低值易耗品进销存管理蓝图
app.register_blueprint(supply_index_bp)
app.register_blueprint(supplier_bp)
app.register_blueprint(supplier_api_bp)
app.register_blueprint(supplier_import_export_bp)
app.register_blueprint(supply_item_bp)
app.register_blueprint(supply_item_api_bp)
app.register_blueprint(supply_item_import_export_bp)
app.register_blueprint(storage_location_bp)
app.register_blueprint(storage_location_api_bp)
app.register_blueprint(storage_location_import_export_bp)
app.register_blueprint(supply_stock_detail_bp)
app.register_blueprint(supply_stock_detail_api_bp)
app.register_blueprint(stock_in_bp)
app.register_blueprint(stock_in_api_bp)
app.register_blueprint(stock_in_import_export_bp)
app.register_blueprint(stock_out_bp)
app.register_blueprint(stock_out_api_bp)
app.register_blueprint(stock_out_import_export_bp)
app.register_blueprint(supply_inventory_bp)
app.register_blueprint(supply_inventory_api_bp)
app.register_blueprint(supply_inventory_import_export_bp)
app.register_blueprint(supply_stock_record_bp)
app.register_blueprint(supply_stock_record_api_bp)
app.register_blueprint(role_bp)
# 合同管理相关
app.register_blueprint(contract_bp)
app.register_blueprint(contract_api_bp)
app.register_blueprint(contract_import_export_bp)
# 后勤维修管理相关
app.register_blueprint(maintenance_user_bp)
app.register_blueprint(maintenance_admin_bp)
app.register_blueprint(maintenance_staff_bp)
app.register_blueprint(maintenance_api_bp)
_stamp("注册38个蓝图")



# 数据库连接配置 - 智能连接检查
with app.app_context():
    # 智能判断是否需要强制检查数据库连接：
    # 仅在首次启动（数据库文件不存在）或之前MySQL连接失败时强制检查
    # 非首次启动跳过MySQL连接测试，避免10秒超时延迟
    db_config_data = DatabaseConfig.load_config()
    needs_force_check = False
    
    if db_config_data.get("AUTO_SWITCHED_TO_SQLITE", False):
        # 之前MySQL连接失败过，需要再次检查是否恢复
        needs_force_check = True
        logging.info("检测到之前MySQL连接失败，将重新检查连接状态")
    elif db_config_data.get("SQL_TYPE", "").upper() == "SQLITE":
        # SQLite模式：检查数据库文件是否存在来判断是否首次启动
        sqlite_path = db_config_data.get("SQLITE_DB_PATH", "")
        if not sqlite_path or not os.path.exists(sqlite_path):
            needs_force_check = True
            logging.info("SQLite数据库文件不存在，将执行首次启动检查")
    elif db_config_data.get("SQL_TYPE", "").upper() == "MYSQL":
        # MySQL模式：检查是否有成功连接的历史记录
        # 如果LAST_FAILED_MYSQL_ATTEMPT为空且未自动切换，说明之前连接正常
        if db_config_data.get("LAST_FAILED_MYSQL_ATTEMPT"):
            needs_force_check = True
            logging.info("检测到MySQL历史连接失败记录，将检查连接状态")
    
    db_uri = DatabaseConfig.get_db_uri(force_check=needs_force_check)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    _stamp("数据库连接检查")
    
    # 检查是否是自动切换到SQLite的情况
    config = DatabaseConfig.load_config()
    if config.get("AUTO_SWITCHED_TO_SQLITE", False):
        logging.warning("系统已自动切换到SQLite数据库，因为MySQL连接失败")

# 初始化数据库（确保所有模型已导入后再初始化）
init_db(app)
logging.info("初始化数据库实例")
_stamp("初始化数据库")

# 上下文处理器
@app.context_processor
def inject_common_common_variables():
    # 从数据库获取系统标题
    from models.system_config import SystemConfig  # 延迟导入，init_db已加载模型模块
    config = DatabaseConfig.load_config()
    system_title = config.get('SYSTEM_TITLE', '行政后勤管理系统')
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
_stamp("创建进程清理实例")

# 导入自动备份线程（延迟到首次请求时初始化，避免启动时加载pymysql等重型库）
_backup_initialized = False
def _init_backup_thread():
    """延迟初始化备份线程"""
    global _backup_initialized
    if _backup_initialized:
        return
    _backup_initialized = True
    try:
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
        logging.info("延迟初始化备份线程完成")
    except Exception as e:
        logging.error(f"延迟初始化备份线程失败: {e}")

# 初始化会话超时处理器
from utils.session_timeout import setup_session_timeout_handler
setup_session_timeout_handler(app)
_stamp("初始化会话超时")

# 初始化费用主表记录自动生成调度器（延迟到首次请求时初始化，避免启动时加载schedule库）
_scheduler_initialized = False
def _init_scheduler():
    """延迟初始化调度器"""
    global _scheduler_initialized
    if _scheduler_initialized:
        return
    _scheduler_initialized = True
    try:
        from utils.utility_room_bill_record_scheduler import init_scheduler
        scheduler = init_scheduler(app)
        logging.info("延迟初始化调度器完成")
    except Exception as e:
        logging.error(f"延迟初始化调度器失败: {e}")

# 合并延迟初始化：首次请求时同时初始化备份线程和调度器
@app.before_request
def _init_background_services():
    """首次请求时延迟初始化后台服务（备份线程、调度器）"""
    if not _backup_initialized:
        _init_backup_thread()
    if not _scheduler_initialized:
        _init_scheduler()

# 根路由
@app.route('/')
def root():
    return redirect(url_for('login.login'))

# 导航页路由
@app.route('/index')
@login_required
def index():
    # 判断用户是否有管理角色
    if not current_user.role_id:
        # 无角色用户重定向到用户信息页面
        return redirect(url_for('user.user_info'))
    # 有角色用户继续访问首页
    return render_template('index.html',title=f"主页")

#解决日志内"GET /.well-known/appspecific/com.chrome.devtools.json HTTP/1.1" 404 -错误
@app.route('/.well-known/appspecific/com.chrome.devtools.json')
def handle_chrome_devtools():
    return jsonify({}), 200 # 返回空JSON对象，状态码200

# 服务器启动函数
def run_server():
    """启动生产环境服务器"""
    _stamp("Flask应用初始化完成，准备启动服务器")
    from waitress import serve  # 延迟导入，避免启动时加载重型库
    serve(app, host=current_config.SERVER_HOST, port=current_config.SERVER_PORT)
    logging.info(f"服务器已启动，监听 {current_config.SERVER_HOST}:{current_config.SERVER_PORT}")
    logging.info("服务器启动完成")

# 主程序入口
if __name__ == '__main__':
    # 处理命令行参数
    import argparse
    parser = argparse.ArgumentParser(description='行政后勤管理系统')
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
    
    # Win7系统强制服务端模式
    from utils.system_detector import is_win7, is_webview2_available
    if is_win7():
        logging.info("检测到Win7系统，强制使用服务端模式（不支持WebView2）")
        server_mode = "服务端"
    
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
        # 检查WebView2是否可用
        if not is_webview2_available():
            logging.warning("WebView2运行时不可用，自动回退到服务端模式")
            server_mode = "服务端"
            # 回退到服务端模式：启动Flask服务器
            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()
            
            import time
            time.sleep(1)
            
            # 设置资源引用并注册信号处理器
            process_cleaner.set_resources(
                app=app,
                server_thread=server_thread,
                webview_ref=None
            )
            process_cleaner.register_signal_handlers()
            
            # 启动服务端GUI
            from utils.server_gui import run_server_gui
            gui_thread = threading.Thread(target=lambda: run_server_gui(on_exit_callback=None), daemon=False)
            gui_thread.start()
            gui_thread.join()
        else:
            # 客户端模式：启动WebView2窗口
            import webview  # 延迟导入，避免启动时加载WebView2重型运行时
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
                    system_title = config.get('SYSTEM_TITLE', '行政后勤管理系统')
            except Exception as e:
                logging.error(f"获取系统标题时出错: {str(e)}")
                system_title = '行政后勤管理系统'
            
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
