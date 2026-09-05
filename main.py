import os
import sys
import threading
import logging
import time
from datetime import datetime, date

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
_stamp("导入db_config")

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
    import importlib
    from utils import db_config
    importlib.reload(db_config)
    print("数据库配置已重新加载")
else:
    print("数据库配置未重新加载")


def _load_splash_html(system_title):
    """加载闪屏HTML模板，支持打包和开发环境"""
    if getattr(sys, 'frozen', False):
        splash_path = os.path.join(sys._MEIPASS, 'templates', 'splash.html')
    else:
        splash_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates', 'splash.html')
    with open(splash_path, 'r', encoding='utf-8') as f:
        return f.read().replace('{{SYSTEM_TITLE}}', system_title)

def init_flask_app(progress_callback=None):
    """
    初始化Flask应用及所有依赖。
    
    Args:
        progress_callback: 可选回调函数，接受(progress_pct: int, message: str)参数
    Returns:
        tuple: (app, process_cleaner, run_server)
    """
    # 延迟导入重型模块，加速启动
    from flask import Flask, redirect, url_for, render_template, current_app, Blueprint, jsonify
    from flask_login import LoginManager, current_user, login_required
    from utils.db import db, init_db
    _stamp("导入db")

    # 阶段1：创建Flask应用实例
    if progress_callback:
        progress_callback(5, "正在创建应用实例...")
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, 'frozen', False):
        template_folder = os.path.join(sys._MEIPASS, 'templates')
        static_folder = os.path.join(sys._MEIPASS, 'static')
        app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)
        app.config['SQLALCHEMY_DATABASE_URI'] = DatabaseConfig.get_db_uri()
        print(f"打包环境数据库连接: {app.config['SQLALCHEMY_DATABASE_URI']}")
    else:
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = DatabaseConfig.get_db_uri()
        print(f"开发环境数据库连接: {app.config['SQLALCHEMY_DATABASE_URI']}")

    app.config.from_object(current_config)
    app.secret_key = current_config.SECRET_KEY
    app.permanent_session_lifetime = current_config.PERMANENT_SESSION_LIFETIME
    print(f"会话超时时间: {app.permanent_session_lifetime}")
    
    # 阶段2：加载核心模块
    if progress_callback:
        progress_callback(10, "正在加载核心模块...")
    
    from utils.log import setup_file_logging
    logger = setup_file_logging()
    _stamp("初始化日志系统")

    from models.user.user import User
    _stamp("导入User模型")
    
    # 阶段3：注册功能模块
    if progress_callback:
        progress_callback(30, "正在注册功能模块...")

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
    app.register_blueprint(contract_bp)
    app.register_blueprint(contract_api_bp)
    app.register_blueprint(contract_import_export_bp)
    app.register_blueprint(maintenance_user_bp)
    app.register_blueprint(maintenance_admin_bp)
    app.register_blueprint(maintenance_staff_bp)
    app.register_blueprint(maintenance_api_bp)
    _stamp("注册38个蓝图")

    # 阶段4：初始化数据库
    if progress_callback:
        progress_callback(50, "正在初始化数据库...")

    with app.app_context():
        db_config_data = DatabaseConfig.load_config()
        needs_force_check = False
        if db_config_data.get("AUTO_SWITCHED_TO_SQLITE", False):
            needs_force_check = True
            logging.info("检测到之前MySQL连接失败，将重新检查连接状态")
        elif db_config_data.get("SQL_TYPE", "").upper() == "SQLITE":
            sqlite_path = db_config_data.get("SQLITE_DB_PATH", "")
            if not sqlite_path or not os.path.exists(sqlite_path):
                needs_force_check = True
                logging.info("SQLite数据库文件不存在，将执行首次启动检查")
        elif db_config_data.get("SQL_TYPE", "").upper() == "MYSQL":
            if db_config_data.get("LAST_FAILED_MYSQL_ATTEMPT"):
                needs_force_check = True
                logging.info("检测到MySQL历史连接失败记录，将检查连接状态")
        db_uri = DatabaseConfig.get_db_uri(force_check=needs_force_check)
        app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
        _stamp("数据库连接检查")
        config = DatabaseConfig.load_config()
        if config.get("AUTO_SWITCHED_TO_SQLITE", False):
            logging.warning("系统已自动切换到SQLite数据库，因为MySQL连接失败")

    init_db(app)
    logging.info("初始化数据库实例")
    _stamp("初始化数据库")

    # 阶段5：配置系统服务
    if progress_callback:
        progress_callback(70, "正在配置系统服务...")

    @app.context_processor
    def inject_common_common_variables():
        from models.system_config.system_config import SystemConfig
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

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login.login'
    login_manager.login_message = '请先登录以访问此页面'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    logging.getLogger('werkzeug').setLevel(logging.DEBUG)
    logging.getLogger('flask').setLevel(logging.DEBUG)

    from utils.process_cleaner import ProcessCleaner
    process_cleaner = ProcessCleaner()
    _stamp("创建进程清理实例")

    _backup_initialized = False
    def _init_backup_thread():
        nonlocal _backup_initialized
        if _backup_initialized:
            return
        _backup_initialized = True
        try:
            from utils.backup import auto_backup
            def start_backup():
                with app.app_context():
                    auto_backup(app)
            if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
                backup_threads = [t for t in threading.enumerate() if t.name == "auto_backup_thread"]
                if not backup_threads:
                    backup_thread = threading.Thread(
                        target=start_backup, 
                        daemon=True,
                        name="auto_backup_thread"
                    )
                    backup_thread.start()
                    with app.app_context():
                        logging.info(f"主进程启动备份线程，ID: {backup_thread.ident}")
                else:
                    with app.app_context():
                        logging.info("备份线程已存在，无需重复启动")
            logging.info("延迟初始化备份线程完成")
        except Exception as e:
            logging.error(f"延迟初始化备份线程失败: {e}")

    from utils.session_timeout import setup_session_timeout_handler
    setup_session_timeout_handler(app)
    _stamp("初始化会话超时")

    _scheduler_initialized = False
    def _init_scheduler():
        nonlocal _scheduler_initialized
        if _scheduler_initialized:
            return
        _scheduler_initialized = True
        try:
            from utils.utility_room_bill_record_scheduler import init_scheduler
            scheduler = init_scheduler(app)
            logging.info("延迟初始化调度器完成")
        except Exception as e:
            logging.error(f"延迟初始化调度器失败: {e}")

    @app.before_request
    def _init_background_services():
        if not _backup_initialized:
            _init_backup_thread()
        if not _scheduler_initialized:
            _init_scheduler()

    # 阶段6：注册路由
    if progress_callback:
        progress_callback(90, "正在注册路由...")

    @app.route('/')
    def root():
        return redirect(url_for('login.login'))

    @app.route('/index')
    @login_required
    def index():
        if not current_user.role_id:
            return redirect(url_for('user.user_info'))
        return render_template('index.html',title=f"主页")

    @app.route('/.well-known/appspecific/com.chrome.devtools.json')
    def handle_chrome_devtools():
        return jsonify({}), 200

    def run_server():
        _stamp("Flask应用初始化完成，准备启动服务器")
        from waitress import serve
        serve(app, host=current_config.SERVER_HOST, port=current_config.SERVER_PORT)
        logging.info(f"服务器已启动，监听 {current_config.SERVER_HOST}:{current_config.SERVER_PORT}")
        logging.info("服务器启动完成")

    return app, process_cleaner, run_server


def _wait_for_server(port, timeout=30, interval=0.5):
    """等待服务器就绪，通过HTTP请求确认服务可用，替代固定time.sleep"""
    import urllib.request
    import urllib.error
    start_time = time.time()
    url = f'http://127.0.0.1:{port}/login'
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=3) as response:
                return True
        except (urllib.error.URLError, ConnectionRefusedError, OSError):
            pass
        time.sleep(interval)
    raise TimeoutError(f"服务器在{timeout}秒内未就绪")


def run_server():
    """Docker入口函数：初始化Flask应用并直接启动服务器"""
    app, process_cleaner, _run_server = init_flask_app()
    process_cleaner.register_signal_handlers()
    _run_server()


# 主程序入口
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='行政后勤管理系统')
    parser.add_argument('--uninstall', action='store_true', help='执行卸载清理操作')
    parser.add_argument('--no-reload', action='store_true', help='禁用自动重载')
    parser.add_argument('--config', type=str, help='指定配置环境')
    args = parser.parse_args()
    logging.info("解析命令行参数")
    from utils.system_detector import is_win7, is_android
    
    if args.uninstall:
        is_docker = os.environ.get('DOCKER_ENV', 'false').lower() == 'true'
        if is_docker or is_android():
            logging.warning("在 Docker/Android 环境中，不执行卸载操作。")
        else:
            from utils.uninstall_handler import handle_uninstall
            handle_uninstall()
    logging.info("处理卸载参数")
    
    # Android 环境检测 - 必须在所有其他分支之前
    if is_android():
        logging.info("检测到 Android 环境，启动 Android 客户端模式")
        from utils.android_adapter import install_stub_modules, setup_android_env
        # 1. 安装 stub 模块（必须在所有 import 之前）
        install_stub_modules()
        # 2. 配置 Android 环境
        setup_android_env()
        # 3. 初始化 Flask 应用
        app, process_cleaner, run_server = init_flask_app()
        # 4. 启动 waitress 服务器（后台线程）
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        # 5. 等待服务器就绪
        port = current_config.SERVER_PORT if hasattr(current_config, 'SERVER_PORT') else 5000
        if _wait_for_server(port):
            logging.info(f"Android 服务器已就绪: http://127.0.0.1:{port}")
        # 6. Android 上由 Java 层 WebView 加载页面，Python 进程保持运行
        logging.info("Android Flask 服务已启动，等待 WebView 连接...")
        # 保持主线程运行
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info("收到中断信号，关闭服务器")
        sys.exit(0)

    config_data = DatabaseConfig.load_config()
    server_mode = config_data.get("SERVER_MODE", "客户端")
    if is_win7():
        server_mode = "服务端"
    
    if server_mode == "服务端" and current_config.USE_DESKTOP_VIEW:
        logging.info("以服务端模式启动，不启动WebView2")
        
        app, process_cleaner, run_server = init_flask_app()
        
        server_thread = threading.Thread(target=run_server, daemon=True)
        server_thread.start()
        
        import time
        time.sleep(1)
        
        process_cleaner.set_resources(
            app=app,
            server_thread=server_thread,
            webview_ref=None
        )
        process_cleaner.register_signal_handlers()
        
        from utils.server_gui import run_server_gui
        gui_thread = threading.Thread(target=lambda: run_server_gui(on_exit_callback=None), daemon=False)
        gui_thread.start()
        
        gui_thread.join()
        
    elif server_mode == "客户端" and current_config.USE_DESKTOP_VIEW:
        import webview
        
        logging.info("启动WebView窗口（闪屏模式）")
        
        system_title = config_data.get('SYSTEM_TITLE', '行政后勤管理系统')
        splash_html = _load_splash_html(system_title)
        
        window = webview.create_window(
            title=system_title,
            html=splash_html,
            width=1200,
            height=800,
            resizable=True
        )
        
        resources = {}
        init_completed = threading.Event()
        
        def background_init(window):
            """WebView窗口显示后，在后台线程中执行Flask初始化"""
            try:
                def progress_callback(pct, msg):
                    try:
                        safe_msg = msg.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
                        window.evaluate_js(f'updateProgress({pct}, "{safe_msg}")')
                    except Exception:
                        pass
                
                app, process_cleaner, run_server = init_flask_app(progress_callback)
                resources['app'] = app
                resources['process_cleaner'] = process_cleaner
                
                progress_callback(80, "正在启动服务器...")
                server_thread = threading.Thread(target=run_server, daemon=True)
                server_thread.start()
                resources['server_thread'] = server_thread
                
                progress_callback(90, "正在检查服务状态...")
                _wait_for_server(current_config.SERVER_PORT)
                
                progress_callback(100, "即将进入系统...")
                time.sleep(0.3)
                
                server_url = f'http://127.0.0.1:{current_config.SERVER_PORT}'
                window.load_url(server_url)
                
                # 标记初始化完成（在可能失败的后初始化步骤之前）
                init_completed.set()
                
                # 后初始化步骤（失败不影响核心功能）
                try:
                    with app.app_context():
                        from utils.auto_logout import auto_logout_on_startup
                        auto_logout_on_startup()
                    from utils.webview_injector import start_delayed_injection
                    start_delayed_injection()
                    process_cleaner.set_resources(
                        app=app, server_thread=server_thread, webview_ref=window
                    )
                    process_cleaner.register_signal_handlers()
                except Exception as post_e:
                    logging.warning(f"后初始化步骤失败（不影响核心功能）: {post_e}")
                
            except Exception as e:
                logging.error(f"后台初始化失败: {str(e)}", exc_info=True)
                try:
                    safe_error = str(e).replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
                    window.evaluate_js(f'showError("{safe_error}")')
                except Exception:
                    pass
        
        webview.start(func=background_init, args=(window,), debug=current_config.DEBUG)
        
        logging.info("WebView窗口已关闭，开始执行彻底的资源清理...")
        
        if init_completed.is_set():
            process_cleaner = resources.get('process_cleaner')
            server_thread = resources.get('server_thread')
            
            if process_cleaner:
                process_cleaner.cleanup_all_resources(signal_received=0)
            
            if server_thread and server_thread.is_alive():
                os._exit(0)
        else:
            logging.info("初始化未完成即关闭窗口，直接退出")
            os._exit(0)
    
    else:
        logging.info("以开发模式启动")
        
        app, process_cleaner, run_server = init_flask_app()
        
        process_cleaner.set_resources(app=app)
        process_cleaner.register_signal_handlers()
        
        app.run(
            host=current_config.SERVER_HOST,
            port=current_config.SERVER_PORT,
            debug=current_config.DEBUG,
            use_reloader=current_config.DEBUG
        )