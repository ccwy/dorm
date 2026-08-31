import tkinter as tk
from tkinter import ttk, messagebox
import threading
import logging
import platform
import socket

# 导入托盘和图像处理库
from pystray import Icon, Menu, MenuItem
from PIL import Image
import os
import sys

# 设置PIL的日志级别为WARNING或更高级别，减少日志输出
import logging as pil_logging
pil_logger = pil_logging.getLogger('PIL')
pil_logger.setLevel(pil_logging.WARNING)

# 导入数据库配置类
from utils.db_config import DatabaseConfig
# 导入Windows服务重装工具
from utils.reload_windows_service import reload_service as reload_windows_service

class ServerGUI:
    def __init__(self, on_exit_callback=None):
        # 保存退出回调函数
        self.on_exit_callback = on_exit_callback
        
        # 创建主窗口
        self.root = tk.Tk()
        # 获取系统标题配置
        db_config = DatabaseConfig.load_config()
        self.system_title = db_config.get("SYSTEM_TITLE", "行政后勤管理系统") + " - 服务端"
        self.root.title(self.system_title)
        
        # 设置窗口大小
        window_width = 600
        window_height = 500
        self.root.geometry(f"{window_width}x{window_height}")
        self.root.resizable(True, True)
        
        # 计算窗口居中位置
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x_position = (screen_width - window_width) // 2
        y_position = (screen_height - window_height) // 2
        
        # 设置窗口位置使其居中
        self.root.geometry(f"{window_width}x{window_height}+{x_position}+{y_position}")
        
        # 设置中文字体支持（仅Windows系统使用）
        self.font_config = {"font": ("SimHei", 10)}
        
        # 配置变量
        self.config_data = {}
        self.is_server_mode = tk.StringVar(value="服务端")
        self.auto_start_var = tk.BooleanVar(value=False)
        
        # 初始化UI
        self._init_ui()
        
        # 加载配置
        self._load_config()
        
        # 初始化托盘图标
        self._init_tray()
        
        # 窗口关闭事件处理
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # 设置窗口图标
        self._set_window_icon()
        
    def _init_ui(self):
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 配置标签
        config_label = ttk.Label(main_frame, text=self.system_title, font=("SimHei", 14, "bold"))
        config_label.pack(pady=10)
        
        # 创建内容框架 - 用于放置可滚动区域和按钮区域
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # 创建滚动区域
        scrollable_area = ttk.Frame(content_frame)
        scrollable_area.pack(fill=tk.BOTH, expand=True)
        
        # 创建Canvas组件并设置无边框
        canvas = tk.Canvas(scrollable_area, bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scrollable_area, orient="vertical", command=canvas.yview)
        self.scrollable_frame = ttk.Frame(canvas)
        
        # 定义一个居中对齐的函数
        def center_frame(event):
            canvas_width = canvas.winfo_width()
            frame_width = self.scrollable_frame.winfo_width()
            x = max(0, (canvas_width - frame_width) // 2)  # 确保不小于0
            canvas.coords("all", x, 0)  # 更新窗口位置
            canvas.configure(scrollregion=canvas.bbox("all"))
        
        # 绑定配置事件，实现居中对齐
        self.scrollable_frame.bind("<Configure>", center_frame)
        canvas.bind("<Configure>", center_frame)  # 当canvas大小改变时也居中
        
        # 创建窗口，使用锚点居中
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # 添加鼠标滚轮事件支持
        def _on_mousewheel(event):
            # 只处理Windows系统的鼠标滚轮事件
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        # 根据测试结果，只有绑定根窗口才能实现滚动功能
        self.root.bind("<MouseWheel>", _on_mousewheel)
        # 所有其他绑定都无效，已移除
         
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 创建配置项
        self.config_entries = {}
        
        # 启动模式选择
        mode_frame = ttk.LabelFrame(self.scrollable_frame, text="启动模式", padding="10")
        mode_frame.pack(fill=tk.X, pady=5)
        
        # 标签
        ttk.Label(mode_frame, text="请选择启动模式：", **self.font_config).pack(anchor=tk.W, pady=(0, 5))
        
        # 创建水平框架同时放置启动模式和服务器端口
        mode_and_port_frame = ttk.Frame(mode_frame)
        mode_and_port_frame.pack(fill=tk.X, pady=5)
        
        # 左侧放置启动模式选择
        mode_options_frame = ttk.Frame(mode_and_port_frame)
        mode_options_frame.pack(side=tk.LEFT)
        
        # 使用单选按钮设置启动模式
        client_rb = ttk.Radiobutton(
            mode_options_frame, 
            text="客户端(Win7不可用)", 
            variable=self.is_server_mode, 
            value="客户端",
            command=self._on_mode_change,
            state='disabled'
        )
        client_rb.pack(side=tk.LEFT, padx=10)
        
        server_rb = ttk.Radiobutton(
            mode_options_frame, 
            text="服务端", 
            variable=self.is_server_mode, 
            value="服务端",
            command=self._on_mode_change
        )
        server_rb.pack(side=tk.LEFT, padx=10)
        
        # Win7版本模式说明标签
        ttk.Label(mode_options_frame, text="（Win7版本仅支持服务端模式）", foreground="gray").pack(side=tk.LEFT, padx=5)
        
        # 右侧放置开机自启和端口设置
        right_frame = ttk.Frame(mode_and_port_frame)
        right_frame.pack(side=tk.RIGHT)
        
        # 开机自启复选框
        auto_start_check = ttk.Checkbutton(
            right_frame,
            text="开机自启",
            variable=self.auto_start_var,
            command=self._on_auto_start_toggle
        )
        auto_start_check.pack(side=tk.LEFT, padx=10)
        
        # 服务器端口设置
        port_var = tk.StringVar()
        port_entry = ttk.Entry(right_frame, textvariable=port_var, width=10)
        port_entry.pack(side=tk.RIGHT, padx=5)
        
        port_label = ttk.Label(right_frame, text="服务器端口：", **self.font_config)
        port_label.pack(side=tk.RIGHT, padx=(5, 0))
        self.config_entries["SERVER_PORT"] = (port_var, port_entry)
        
        # 说明文字
        ttk.Label(
            mode_frame, 
            text="客户端模式：无后台服务，启动客户端使用\n服务端模式：仅提供后台服务，无客户端，仅能通过网页访问", 
            font=("SimHei", 9),
            justify=tk.LEFT
        ).pack(anchor=tk.W, pady=5)
        
        # 服务器地址和端口显示卡片（仅在服务端模式显示）
        self.server_card_frame = ttk.LabelFrame(mode_frame, text="服务器访问信息", padding="10")
        
        # 卡片内的内容
        card_content_frame = ttk.Frame(self.server_card_frame)
        card_content_frame.pack(fill=tk.X, pady=5)
        
        # 网卡地址显示
        network_row_frame = ttk.Frame(card_content_frame)
        network_row_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(network_row_frame, text="网卡地址:", font=(("SimHei", 12)), width=8).pack(side=tk.LEFT, padx=(0, 5))
        self.network_card_url_var = tk.StringVar(value="http://localhost:35168")
        network_card_url_label = ttk.Label(network_row_frame, textvariable=self.network_card_url_var, 
                                           font=(("SimHei", 12, "underline")), foreground="blue", cursor="hand2")
        network_card_url_label.pack(side=tk.LEFT)
        network_card_url_label.bind("<Button-1>", lambda e: self._open_browser(self.network_card_url_var.get()))
        
        # 本地地址显示
        local_row_frame = ttk.Frame(card_content_frame)
        local_row_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(local_row_frame, text="本地地址:", font=(("SimHei", 12)), width=8).pack(side=tk.LEFT, padx=(0, 5))
        self.local_url_var = tk.StringVar(value="http://localhost:35168")
        local_url_label = ttk.Label(local_row_frame, textvariable=self.local_url_var, 
                                    font=(("SimHei", 12, "underline")), foreground="blue", cursor="hand2")
        local_url_label.pack(side=tk.LEFT)
        local_url_label.bind("<Button-1>", lambda e: self._open_browser(self.local_url_var.get()))
        
        # 提示文字
        ttk.Label(
            self.server_card_frame, 
            text="点击上方链接在浏览器中打开管理系统", 
            font=("SimHei", 9),
            justify=tk.LEFT
        ).pack(anchor=tk.W, pady=5)
        
        # 初始时隐藏卡片
        self.server_card_frame.pack_forget()
        
        # 数据库类型选择
        db_type_frame = ttk.LabelFrame(self.scrollable_frame, text="数据库设置", padding="10")
        db_type_frame.pack(fill=tk.X, pady=5)
        
        self.db_type_var = tk.StringVar()
        db_type_frame_inner = ttk.Frame(db_type_frame)
        db_type_frame_inner.pack(fill=tk.X)
        
        ttk.Radiobutton(
            db_type_frame_inner, 
            text="SQLite", 
            variable=self.db_type_var, 
            value="SQLITE",
            command=self._on_db_type_change
        ).pack(side=tk.LEFT, padx=10)
        
        ttk.Radiobutton(
            db_type_frame_inner, 
            text="MySQL", 
            variable=self.db_type_var, 
            value="MYSQL",
            command=self._on_db_type_change
        ).pack(side=tk.LEFT, padx=10)
        
        # SQLite配置
        self.sqlite_frame = ttk.LabelFrame(self.scrollable_frame, text="SQLite配置", padding="10")
        self.sqlite_frame.pack(fill=tk.X, pady=5)
        
        self._create_config_entry(self.sqlite_frame, "SQLITE_DB_PATH", "SQLite数据库路径:", is_readonly=True)
        
        # MySQL配置
        self.mysql_frame = ttk.LabelFrame(self.scrollable_frame, text="MySQL配置", padding="10")
        self.mysql_frame.pack(fill=tk.X, pady=5)
        
        self._create_config_entry(self.mysql_frame, "MYSQL_HOST", "主机地址:")
        self._create_config_entry(self.mysql_frame, "MYSQL_PORT", "端口:")
        self._create_config_entry(self.mysql_frame, "MYSQL_DB", "数据库名称:")
        self._create_config_entry(self.mysql_frame, "MYSQL_USER", "用户名:")
        self._create_config_entry(self.mysql_frame, "MYSQL_PASSWORD", "密码:", is_password=True)
        
        # 按钮区域 - 放置在内容框架的底部
        button_frame = ttk.Frame(content_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        # 左侧空白框架，保持与右侧平衡
        left_spacer = ttk.Frame(button_frame)
        left_spacer.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        test_conn_btn = ttk.Button(button_frame, text="测试连接", command=self._test_connection)
        test_conn_btn.pack(side=tk.LEFT, padx=5)
        
        save_btn = ttk.Button(button_frame, text="保存配置", command=self._save_config)
        save_btn.pack(side=tk.LEFT, padx=5)
        
        reset_btn = ttk.Button(button_frame, text="重置", command=self._load_config)
        reset_btn.pack(side=tk.LEFT, padx=5)
        
        # 重启系统按钮
        restart_btn = ttk.Button(button_frame, text="重启系统", command=self._restart_system)
        restart_btn.pack(side=tk.LEFT, padx=5)
        
        # 退出按钮
        exit_btn = ttk.Button(button_frame, text="退出系统", command=self._exit_app)
        exit_btn.pack(side=tk.LEFT, padx=5)
        
        # 右侧空白框架，确保按钮不会过于靠右
        right_spacer = ttk.Frame(button_frame)
        right_spacer.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # 状态标签
        self.status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(main_frame, textvariable=self.status_var, foreground="blue")
        status_label.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
    
    def _create_config_entry(self, parent, key, label_text, is_password=False, is_readonly=False):
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(frame, text=label_text, width=21, **self.font_config).pack(side=tk.LEFT, padx=5)
        
        var = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=var, width=50)
        
        if is_password:
            entry.config(show="*")
        if is_readonly:
            entry.config(state="readonly")
            
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.config_entries[key] = (var, entry)
        
    def _init_tray(self):
        # 检查root属性是否存在（表示GUI已成功初始化）
        if not hasattr(self, 'root') or self.root is None:
            return
            
        # 获取图标文件路径（支持打包环境）
        icon_path = self._get_icon_path()
        
        # 加载图标文件
        image = Image.open(icon_path)
        
        # 创建托盘菜单
        # 添加一个默认菜单项，当直接点击图标时会触发
        # 使用default=True和visible=False来实现点击图标直接触发而不显示在菜单中
        menu = Menu(
            MenuItem("显示窗口", self._show_window, default=True, visible=False),
            MenuItem("显示窗口", self._show_window),
            MenuItem("退出系统", self._exit_app)
        )
        
        # 创建托盘图标
        self.tray_icon = Icon(self.system_title, image, self.system_title, menu)
        
        # 在单独的线程中运行托盘图标
        self.tray_thread = threading.Thread(target=self.tray_icon.run, daemon=True)
        self.tray_thread.start()
            
    def _get_icon_path(self):
        """获取图标文件路径，支持打包环境"""
        # 检查是否是打包后的环境
        if getattr(sys, 'frozen', False):
            # 打包环境：使用sys._MEIPASS路径
            icon_path = os.path.join(sys._MEIPASS, 'static', 'favicon.ico')
        else:
            # 开发环境：使用相对路径
            current_dir = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(current_dir, '..', 'static', 'favicon.ico')
        
        return icon_path
        
    def _set_window_icon(self):
        # 检查root属性是否存在（表示GUI已成功初始化）
        if not hasattr(self, 'root') or self.root is None:
            return
            
        # 获取图标文件路径（支持打包环境）
        icon_path = self._get_icon_path()
        
        # 直接使用Tkinter的iconbitmap方法设置.ico文件作为窗口图标
        self.root.iconbitmap(icon_path)
    
    def _restart_system(self):
        """重启系统"""
        try:
            self.status_var.set("正在重启系统中...")
            self.root.update()
            
            # 直接调用重载服务
            reload_windows_service()
            
            self.status_var.set("系统正在重启中...")
            messagebox.showinfo("成功", "系统正在重启，请稍等...")
        except Exception as e:
            logging.error(f"重启系统失败: {str(e)}")
            messagebox.showerror("错误", f"重启系统失败: {str(e)}")
            self.status_var.set("重启系统失败")
            
    def _load_config(self):
        try:
            # 加载配置
            self.config_data = DatabaseConfig.load_config()
            
            # 更新界面
            if "SQL_TYPE" in self.config_data:
                self.db_type_var.set(self.config_data["SQL_TYPE"])
                self._on_db_type_change()
            
            for key, (var, entry) in self.config_entries.items():
                if key in self.config_data:
                    var.set(str(self.config_data[key]))
            
            # 加载服务端模式配置，Win7版本强制使用服务端模式
            server_mode_value = self.config_data.get("SERVER_MODE", "服务端")
            # Win7版本不支持客户端模式，强制设为服务端
            if server_mode_value == "客户端":
                logging.warning("Win7版本不支持客户端模式，已自动切换为服务端模式")
                messagebox.showinfo("提示", "Win7版本不支持客户端模式，已自动切换为服务端模式")
                self.is_server_mode.set("服务端")
            else:
                self.is_server_mode.set("服务端")
            
            # 更新服务器卡片显示
            self._update_server_card()
            
            # 同步开机自启复选框状态
            try:
                self.auto_start_var.set(self._is_auto_start_enabled())
            except Exception as e:
                logging.warning(f"检测开机自启状态失败: {str(e)}")
                self.auto_start_var.set(False)
            
            self.status_var.set("配置已加载")
        except Exception as e:
            logging.error(f"加载配置时出错: {str(e)}")
            messagebox.showerror("错误", f"加载配置失败: {str(e)}")
            self.status_var.set("加载配置失败")
            
    def _save_config(self):
        try:
            # 获取配置
            new_config = self.config_data.copy()
            
            # 更新数据库类型
            new_config["SQL_TYPE"] = self.db_type_var.get()
            
            # 更新配置项
            for key, (var, _) in self.config_entries.items():
                # 处理数字类型
                if key in ["MYSQL_PORT", "SERVER_PORT"]:
                    try:
                        new_config[key] = int(var.get())
                    except ValueError:
                        messagebox.showerror("错误", f"{key}必须是整数")
                        return
                else:
                    new_config[key] = var.get()
            
            # 保存服务端模式配置，Win7版本强制保存为服务端
            new_config["SERVER_MODE"] = "服务端"
            
            # 保存配置
            success = DatabaseConfig.save_config(new_config)
            
            if success:
                self.config_data = new_config
                try:
                    self.status_var.set("正在重启服务中...")
                    self.root.update()
                    
                    # 直接调用重载服务，与_restart_system方法保持一致
                    reload_windows_service()
                    
                    self.status_var.set("配置已保存")
                    messagebox.showinfo("成功", "配置保存成功，系统将自动重启服务以应用新配置")
                except Exception as e:
                    logging.error(f"自动重启服务失败: {str(e)}")
                    messagebox.showerror("错误", f"自动重启服务失败: {str(e)}")
                    self.status_var.set("配置已保存，但服务重启失败")
            else:
                self.status_var.set("保存配置失败")
                messagebox.showerror("错误", "保存配置失败")
        except Exception as e:
            logging.error(f"保存配置时出错: {str(e)}")
            messagebox.showerror("错误", f"保存配置失败: {str(e)}")
            self.status_var.set("保存配置失败")
            
    def _test_connection(self):
        try:
            self.status_var.set("正在测试连接...")
            self.root.update()
            
            # 创建临时配置用于测试
            test_config = self.config_data.copy()
            test_config["SQL_TYPE"] = self.db_type_var.get()
            
            # 更新测试配置
            for key, (var, _) in self.config_entries.items():
                if key in ["MYSQL_PORT", "SERVER_PORT"]:
                    try:
                        test_config[key] = int(var.get())
                    except ValueError:
                        messagebox.showerror("错误", f"{key}必须是整数")
                        self.status_var.set("测试连接失败")
                        return
                else:
                    test_config[key] = var.get()
            
            # 测试连接
            if test_config["SQL_TYPE"] == "MYSQL":
                success, msg = DatabaseConfig.test_mysql_connection(test_config)
            else:
                success, msg = DatabaseConfig.test_sqlite_connection(test_config)
            
            if success:
                self.status_var.set(f"连接成功: {msg}")
                messagebox.showinfo("成功", msg)
            else:
                self.status_var.set(f"连接失败: {msg}")
                messagebox.showerror("错误", msg)
        except Exception as e:
            logging.error(f"测试连接时出错: {str(e)}")
            messagebox.showerror("错误", f"测试连接失败: {str(e)}")
            self.status_var.set("测试连接失败")
            
    def _on_db_type_change(self):
        # 根据数据库类型显示/隐藏配置区域
        if self.db_type_var.get() == "MYSQL":
            self.mysql_frame.pack(fill=tk.X, pady=5)
            self.sqlite_frame.pack_forget()
        else:
            self.sqlite_frame.pack(fill=tk.X, pady=5)
            self.mysql_frame.pack_forget()
            
    def _on_auto_start_toggle(self):
        """开机自启复选框切换事件，实时生效"""
        try:
            if self.auto_start_var.get():
                # 勾选：创建快捷方式
                success = self._create_startup_shortcut()
                if success:
                    self.status_var.set("已开启开机自启")
                    logging.info("开机自启已开启")
                else:
                    # 创建失败，恢复复选框状态
                    self.auto_start_var.set(False)
                    self.status_var.set("开启开机自启失败")
                    messagebox.showerror("错误", "无法创建开机自启快捷方式，请检查权限")
            else:
                # 取消勾选：删除快捷方式
                success = self._remove_startup_shortcut()
                if success:
                    self.status_var.set("已关闭开机自启")
                    logging.info("开机自启已关闭")
                else:
                    # 删除失败，恢复复选框状态
                    self.auto_start_var.set(True)
                    self.status_var.set("关闭开机自启失败")
                    messagebox.showerror("错误", "无法移除开机自启快捷方式")
        except Exception as e:
            logging.error(f"切换开机自启失败: {str(e)}")
            messagebox.showerror("错误", f"切换开机自启失败: {str(e)}")
            # 恢复之前的复选框状态
            self.auto_start_var.set(not self.auto_start_var.get())
    
    def _get_startup_folder(self):
        """获取Windows开机自启文件夹路径"""
        import ctypes.wintypes
        # 使用CSIDL_STARTUP获取启动文件夹路径
        CSIDL_STARTUP = 7
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_STARTUP, None, 0, buf)
        return buf.value
    
    def _get_startup_shortcut_path(self):
        """获取开机自启快捷方式的完整路径"""
        startup_folder = self._get_startup_folder()
        # 快捷方式名称与当前可执行文件名一致
        if getattr(sys, 'frozen', False):
            app_name = os.path.splitext(os.path.basename(sys.executable))[0]
        else:
            app_name = "行政后勤管理系统"
        return os.path.join(startup_folder, f"{app_name}.lnk")
    
    def _is_auto_start_enabled(self):
        """检查开机自启是否已开启（快捷方式是否存在）"""
        shortcut_path = self._get_startup_shortcut_path()
        return os.path.exists(shortcut_path)
    
    def _create_startup_shortcut(self):
        """在Windows开机自启文件夹创建快捷方式"""
        try:
            shortcut_path = self._get_startup_shortcut_path()
            
            # 获取目标路径和工作目录
            if getattr(sys, 'frozen', False):
                # 打包环境：指向exe文件
                target_path = sys.executable
                work_dir = os.path.dirname(sys.executable)
                arguments = ""
            else:
                # 开发环境：指向python解释器，参数为main.py
                target_path = sys.executable
                work_dir = os.getcwd()
                main_py = os.path.join(work_dir, 'main.py')
                if not os.path.exists(main_py):
                    logging.error(f"开发环境下未找到main.py: {main_py}")
                    return False
                arguments = f'"{main_py}"'
            
            return self._create_shortcut_via_powershell(shortcut_path, target_path, work_dir, arguments)
        except Exception as e:
            logging.error(f"创建开机自启快捷方式失败: {str(e)}")
            return False
    
    def _create_shortcut_via_powershell(self, lnk_path, target_path, work_dir, arguments=""):
        """通过PowerShell创建快捷方式"""
        try:
            import subprocess
            
            # 构建PowerShell命令，使用单引号避免路径中的特殊字符问题
            ps_command = (
                f"$ws = New-Object -ComObject WScript.Shell; "
                f"$sc = $ws.CreateShortcut('{lnk_path}'); "
                f"$sc.TargetPath = '{target_path}'; "
                f"$sc.WorkingDirectory = '{work_dir}'; "
                f"$sc.Description = '行政后勤管理系统开机自启'; "
            )
            if arguments:
                ps_command += f"$sc.Arguments = '{arguments}'; "
            ps_command += "$sc.Save()"
            
            # 执行PowerShell命令（隐藏窗口，避免闪现控制台）
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            
            result = subprocess.run(
                ['powershell', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-Command', ps_command],
                capture_output=True, text=True, timeout=10,
                startupinfo=startupinfo
            )
            
            if result.returncode == 0:
                logging.info(f"已创建开机自启快捷方式: {lnk_path}")
                return True
            else:
                logging.error(f"PowerShell创建快捷方式失败: {result.stderr}")
                return False
        except Exception as e:
            logging.error(f"PowerShell方式创建快捷方式失败: {str(e)}")
            return False
    
    def _remove_startup_shortcut(self):
        """移除Windows开机自启文件夹中的快捷方式"""
        try:
            shortcut_path = self._get_startup_shortcut_path()
            if os.path.exists(shortcut_path):
                os.remove(shortcut_path)
                logging.info(f"已移除开机自启快捷方式: {shortcut_path}")
            return True
        except Exception as e:
            logging.error(f"移除开机自启快捷方式失败: {str(e)}")
            return False

    def _on_mode_change(self):
        # Win7版本保护：防止切换到客户端模式
        if self.is_server_mode.get() == "客户端":
            logging.warning("Win7版本不支持客户端模式，已自动切换为服务端模式")
            messagebox.showinfo("提示", "Win7版本不支持客户端模式，已自动切换为服务端模式")
            self.is_server_mode.set("服务端")
        # 当启动模式改变时的处理
        self._update_server_card()
        
    def _update_server_card(self):
        # 根据启动模式显示或隐藏服务器卡片
        if self.is_server_mode.get() == "服务端":
            # 获取服务器端口
            server_port = "5000"  # 默认端口
            if "SERVER_PORT" in self.config_entries:
                port_value = self.config_entries["SERVER_PORT"][0].get()
                if port_value and port_value.isdigit():
                    server_port = port_value
                    
            try:
                # 获取本机IP地址（网卡地址）
                hostname = socket.gethostname()
                ip_address = socket.gethostbyname(hostname)
                
                # 特殊处理：如果是127.x.x.x的地址，尝试获取其他网卡地址
                if ip_address.startswith('127.'):
                    import subprocess
                    if platform.system() == 'Windows':
                        # Windows系统获取所有网卡地址
                        output = subprocess.check_output(['ipconfig', '/all'], shell=True).decode('gbk')
                        for line in output.split('\n'):
                            if 'IPv4 地址' in line or 'IPv4 Address' in line:
                                parts = line.strip().split(':')
                                if len(parts) > 1:
                                    candidate = parts[1].strip().split('(')[0].strip()
                                    if not candidate.startswith('127.') and '.' in candidate:
                                        ip_address = candidate
                                        break
                
            except Exception as e:
                logging.error(f"获取网卡地址失败: {str(e)}")
                ip_address = 'localhost'
                
            # 更新服务器URL
            network_url = f"http://{ip_address}:{server_port}"
            self.network_card_url_var.set(network_url)
            self.local_url_var.set(f"http://localhost:{server_port}")
            
            # 显示卡片
            self.server_card_frame.pack(fill=tk.X, pady=5)
            
            # 自动打开网卡地址
            # 只在首次显示卡片时打开一次
            if not hasattr(self, '_browser_opened'):
                self._browser_opened = True
                # 使用线程延迟打开，避免影响UI响应
                import threading
                def open_browser_delayed():
                    try:
                        self._open_browser(network_url)
                    except Exception as e:
                        logging.error(f"自动打开浏览器失败: {str(e)}")
                threading.Thread(target=open_browser_delayed, daemon=True).start()
        else:
            # 隐藏卡片
            self.server_card_frame.pack_forget()
            
    def _open_browser(self, url):
        # 打开浏览器访问指定URL
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception as e:
            logging.error(f"打开浏览器失败: {str(e)}")
            messagebox.showerror("错误", f"打开浏览器失败: {str(e)}")
            
    def _show_window(self):
        # 显示窗口
        self.root.deiconify()
        self.root.lift()
        
    def _hide_window(self):
        # 隐藏窗口到托盘，不显示在任务栏
        self.root.withdraw()
        
    def _on_closing(self):
        # 窗口关闭事件处理
        if self.tray_icon:
            self._hide_window()
        else:
            self._exit_app()
            
    def _exit_app(self):
        # 退出应用
        if self.tray_icon:
            self.tray_icon.stop()
        
        if self.on_exit_callback:
            self.on_exit_callback()
        
        self.root.destroy()
        
    def run(self):
        # 运行GUI主循环
        self.root.mainloop()

# 创建并运行服务端GUI的函数
def run_server_gui(on_exit_callback=None):
    
    # 只在Windows系统上创建GUI（此脚本设计为仅在Windows系统运行）
    if platform.system() == "Windows":
        try:
            # 创建并运行GUI
            gui = ServerGUI(on_exit_callback=on_exit_callback)
            gui.run()
        except Exception as e:
            logging.error(f"服务端GUI运行时出错: {str(e)}")
            # 如果GUI运行失败，尝试显示错误消息
            try:
                root = tk.Tk()
                root.withdraw()  # 隐藏主窗口
                messagebox.showerror("错误", f"服务端GUI运行失败: {str(e)}")
                root.destroy()
            except:
                pass
    else:
        logging.warning("当前系统不是Windows，无法运行服务端GUI")        
        return
