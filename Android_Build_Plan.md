# 宿舍管理系统 — Android 打包技术方案

> 文档版本：v5.0  
> 编写日期：2026-09-05  
> 目标平台：Android 8+（API Level 26）  
> 架构模式：Chaquopy 本地 Flask 后端 + Android WebView 前端  
> 核心原则：**绝对不破坏 Windows 和 Docker 端的现有代码和构建流程**

---

## 1. 项目概述

### 1.1 项目现状

宿舍管理系统（dorm）是一套基于 Python Flask 的全栈 Web 应用，当前支持 **Windows + Docker** 双端运行：

| 维度 | Windows 端 | Docker 端 |
|------|-----------|----------|
| **Python 运行时** | CPython（系统安装 / PyInstaller 打包） | CPython（Docker 容器内） |
| **前端容器** | pywebview 桌面窗口 | 浏览器（外部访问） |
| **服务端 GUI** | tkinter + pystray 系统托盘 | 无（纯服务模式） |
| **WSGI 服务器** | waitress | waitress |
| **环境标识** | 默认（无特殊环境变量） | `DOCKER_ENV=true` |
| **桌面模式** | `USE_DESKTOP_VIEW=True` | `USE_DESKTOP_VIEW=False` |
| **服务端地址** | `SERVER_MODE` 决定（客户端=127.0.0.1 / 服务端=0.0.0.0） | 强制 `0.0.0.0` |
| **数据库** | SQLite（默认）/ MySQL（可选） | SQLite（默认）/ MySQL（可选） |
| **打包方式** | PyInstaller + Inno Setup | Docker Buildx |
| **CI/CD** | `build-windows` job | `build-docker` job |

核心特性：
- 46+ 个 SQLAlchemy 模型，38+ 个 Blueprint 模块
- 前端使用 Jinja2 模板 + Tailwind CSS + jQuery + Font Awesome
- 支持 SQLite（默认）和 MySQL 双数据库，通过 `db_config.json` 动态切换
- 延迟导入机制（`lazy_imports.py`）优化 pandas、openpyxl 等重型库的启动性能
- 平台检测机制（`utils/system_detector.py`）已支持 `is_docker()`、`is_windows()`、`get_environment()`

### 1.2 三端架构总览

新增 Android 端后，系统形成 **Windows + Docker + Android** 三端架构：

| 维度 | Windows 端 | Docker 端 | Android 端（新增） |
|------|-----------|----------|-------------------|
| **Python 运行时** | CPython（PyInstaller） | CPython（Docker 容器） | Chaquopy 嵌入 CPython |
| **前端容器** | pywebview 桌面窗口 | 浏览器（外部访问） | Android WebView |
| **服务端 GUI** | tkinter + pystray | 无 | 无（无桌面环境） |
| **进程管理** | psutil | Docker 守护进程 | Activity 生命周期 |
| **环境标识** | 默认 | `DOCKER_ENV=true` | `ANDROID_ENV=true` |
| **桌面模式** | `USE_DESKTOP_VIEW=True` | `USE_DESKTOP_VIEW=False` | `USE_DESKTOP_VIEW=False` |
| **服务端地址** | `SERVER_MODE` 决定 | 强制 `0.0.0.0` | 强制 `127.0.0.1` |
| **数据库路径** | Windows 文件系统 | Docker 数据卷 `/data` | `getFilesDir()` 内部存储 |
| **文件操作** | 直接文件系统访问 | 直接文件系统访问 | JS Bridge 桥接原生 API |
| **打包方式** | PyInstaller + Inno Setup | Docker Buildx | Gradle + Chaquopy → APK |
| **CI/CD** | `build-windows` job | `build-docker` job | `build-android` job（新增） |
| **分发方式** | 绿色版 exe / 安装程序 | Docker tar 镜像 | APK 直接分发 |

### 1.3 Android 适配目标

- Android 应用内嵌 Python 运行时（Chaquopy），Flask+waitress 在后台线程运行
- Android WebView 作为前端容器，加载本地 Flask 服务渲染的页面（`http://127.0.0.1:35168`）
- 移除 Android 上不适用的桌面组件：tkinter 服务端 GUI、pystray 系统托盘、psutil 进程管理
- 强制使用"客户端模式"：Flask 监听 `127.0.0.1`，WebView 加载本地页面
- **最低兼容 Android 8（API Level 26）**，覆盖 95%+ 的活跃 Android 设备
- 支持 **x86_64**（模拟器/少数设备）和 **ARM64**（主流设备）双架构
- 所有构建在 GitHub Actions 上完成，无需本地 Android SDK 环境
- 通过 APK 直接分发，不需要上架应用商店

### 1.4 核心原则

> **绝对不破坏 Windows 和 Docker 端的现有代码和构建流程**

具体措施：
1. **平台检测隔离**：新增 `ANDROID_ENV` 环境变量（类似 `DOCKER_ENV`），在 `system_detector.py` 中新增 `is_android()` 函数
2. **条件导入/执行**：tkinter、pywebview、pystray、psutil 等桌面依赖在 Android 上通过 `if not is_android():` 跳过，**不删除任何现有代码**
3. **Android 适配层独立文件**：新建 `utils/android_adapter.py`，不修改现有文件的核心逻辑
4. **共享代码不变**：Flask 路由、模型、蓝图、模板、静态文件等核心业务代码完全不变
5. **CI/CD 增量扩展**：现有 `build-windows` 和 `build-docker` job 保持不变，仅新增 `build-android` job

---

## 2. 技术方案选型

### 2.1 Chaquopy + WebView 方案

选择 **Chaquopy** 作为 Android 端 Python 运行时方案：

| 对比维度 | Chaquopy + WebView | Kivy + Buildozer | BeeWare (Briefcase) | 远程服务器方案 |
|---------|-------------------|-----------------|-------------------|-------------|
| **代码复用率** | ~95%（核心业务代码零修改） | ~30%（需重写前端） | ~40%（需适配 GUI 框架） | ~95%（但需服务器部署） |
| **前端一致性** | 完全一致（同一套 Jinja2 模板） | 需重写为 Kivy UI | 需重写为原生 UI | 完全一致 |
| **离线可用** | ✅ 完全离线 | ✅ 完全离线 | ✅ 完全离线 | ❌ 依赖网络 |
| **部署复杂度** | 低（APK 直接安装） | 中 | 中 | 高（需运维服务器） |
| **Python 版本** | 3.8+（与项目一致） | 3.8+ | 3.8+ | 无限制 |
| **ARM 兼容性** | ✅ 官方预编译包 | ⚠️ 需自行编译 | ⚠️ 需自行编译 | N/A |
| **维护活跃度** | ✅ 活跃（JetBrains 支持） | ⚠️ 社区维护 | ⚠️ 较新 | N/A |

### 2.2 为何选择本地 Flask 后端而非远程服务器

1. **离线优先**：宿舍管理场景中，网络可能不稳定，本地后端确保随时可用
2. **数据安全**：敏感数据保存在本地设备，不经过网络传输
3. **零运维成本**：无需维护远程服务器，降低部署和运维复杂度
4. **与现有架构一致**：Windows 和 Docker 端均为本地 Flask 后端，Android 端保持架构一致性
5. **代码复用最大化**：Flask 路由、模型、蓝图等核心代码完全复用，无需任何修改

---

## 3. 三端架构设计

### 3.1 三端共享代码层

以下代码在三个平台完全共享，**不做任何修改**：

```
共享代码（不修改）
├── blueprints/          # 38+ 个蓝图模块（路由逻辑）
├── models/              # 46+ 个 SQLAlchemy 模型
├── templates/           # Jinja2 模板文件
├── static/              # CSS/JS/图片/字体等静态资源
├── utils/
│   ├── db.py            # 数据库初始化
│   ├── db_config.py     # 数据库配置
│   ├── auth.py          # 认证工具
│   ├── log.py           # 日志系统
│   ├── backup.py        # 数据备份
│   ├── cookie_secure.py # Cookie 安全
│   ├── session_timeout.py # 会话超时
│   ├── excel_date_utils.py # Excel 日期工具
│   ├── lazy_imports.py  # 延迟导入
│   ├── user_utils.py    # 用户工具
│   └── ...              # 其他共享工具
├── config.py            # 配置（新增 ANDROID_ENV 分支，不影响现有逻辑）
└── main.py              # 入口（新增条件导入，不删除现有代码）
```

### 3.2 平台差异隔离层

```
平台差异隔离
├── utils/system_detector.py   # 扩展：新增 is_android() 函数
│   ├── is_docker()            # 现有：检测 Docker 环境
│   ├── is_windows()           # 现有：检测 Windows 环境
│   ├── is_android()           # 新增：检测 Android 环境（通过 ANDROID_ENV 环境变量）
│   └── get_environment()      # 扩展：新增 "android" 返回值
│
├── utils/android_adapter.py   # 新增：Android 适配层（独立文件）
│   ├── get_android_context()  # 获取 Android Context
│   ├── get_files_dir()        # 获取内部存储路径
│   ├── get_cache_dir()        # 获取缓存路径
│   ├── setup_android_env()    # 设置 Android 环境变量
│   └── stub 模块提供          # tkinter/pywebview/pystray/psutil 空模块替换
│
└── config.py                  # 扩展：新增 ANDROID_ENV 分支
    ├── DOCKER_ENV 分支        # 现有：Docker 环境配置
    ├── ANDROID_ENV 分支       # 新增：Android 环境配置
    └── 默认分支               # 现有：Windows 环境配置
```

### 3.3 各端运行模式对比

| 运行阶段 | Windows 端 | Docker 端 | Android 端 |
|---------|-----------|----------|-----------|
| **启动入口** | `main.py` → `__main__` | `main.run_server()` | `MainActivity.onCreate()` → Chaquopy → `main.run_android()` |
| **Flask 初始化** | `init_flask_app()` | `init_flask_app()` | `init_flask_app()`（相同） |
| **WSGI 服务器** | waitress | waitress | waitress（后台线程） |
| **前端显示** | pywebview 窗口 | 外部浏览器 | Android WebView |
| **服务端 GUI** | tkinter + pystray | 无 | 无 |
| **进程管理** | psutil + signal | Docker 守护进程 | Activity 生命周期 |
| **数据库路径** | `BASE_DIR/data/` | `/data/`（数据卷） | `getFilesDir()/data/` |
| **日志路径** | `BASE_DIR/logs/` | `/data/logs/` | `getFilesDir()/logs/` |
| **备份路径** | `BACKUP_DIR` | `/data/backups/` | `getFilesDir()/backups/` |

### 3.4 通信机制

```
┌─────────────────────────────────────────────────┐
│                  Android 端                      │
│                                                  │
│  ┌──────────────┐    HTTP localhost:35168        │
│  │  WebView     │◄──────────────────────────┐   │
│  │  (前端渲染)   │                           │   │
│  └──────┬───────┘                           │   │
│         │ JS Bridge                         │   │
│         │ (文件选择/相机/通知等)               │   │
│         ▼                                    │   │
│  ┌──────────────┐    Chaquopy API            │   │
│  │  Android     │─────────────────────┐     │   │
│  │  Native      │                     │     │   │
│  └──────────────┘                     │     │   │
│                                       │     │   │
│  ┌──────────────┐◄────────────────────┘     │   │
│  │  Flask+      │  waitress (后台线程)        │   │
│  │  waitress    │───────────────────────────┘   │
│  │  (Python)    │                               │
│  └──────────────┘                               │
│         │                                       │
│         ▼                                       │
│  ┌──────────────┐                               │
│  │  SQLite/     │                               │
│  │  MySQL       │                               │
│  └──────────────┘                               │
└─────────────────────────────────────────────────┘

Windows/Docker 端：
  pywebview/浏览器 ──HTTP──► Flask+waitress ──► SQLite/MySQL
```

**三种通信方式**：
1. **HTTP localhost**：WebView 与 Flask 之间的主要通信方式，与 Windows/Docker 端完全一致
2. **Chaquopy API**：Android Native 层调用 Python 代码（启动/停止 Flask 服务、获取状态）
3. **JS Bridge**：WebView 中 JavaScript 调用 Android 原生功能（文件选择、相机、通知等）

---

## 4. 后端适配方案（不破坏现有代码）

### 4.1 平台检测扩展

在 `utils/system_detector.py` 中新增 `is_android()` 函数，遵循现有 `is_docker()` 的设计模式：

```python
# utils/system_detector.py — 新增内容（不修改现有代码）

# 模块级变量，用于跟踪Android检测错误是否已记录
android_detection_error_logged = False

class SystemDetector:
    # ... 现有方法保持不变 ...

    @staticmethod
    def is_android() -> bool:
        """
        判断当前环境是否为Android平台
        
        通过 ANDROID_ENV 环境变量检测，与 is_docker() 的 DOCKER_ENV 机制一致。
        Chaquopy 启动时会自动设置 ANDROID_ENV=true。
        
        返回:
            bool: 如果在Android平台上返回True，否则返回False
        """
        # 检查环境变量（最可靠和最快的方法）
        if os.getenv('ANDROID_ENV', 'false').lower() == 'true':
            return True
        
        # 备用检测：检查Chaquopy特有属性
        try:
            import sys
            if hasattr(sys, '_chaquopy') or 'chaquopy' in sys.modules:
                return True
        except Exception as e:
            global android_detection_error_logged
            if not android_detection_error_logged:
                logging.debug(f"Android环境检测出错: {str(e)}")
                android_detection_error_logged = True
        
        return False

    @staticmethod
    def get_environment() -> str:
        """
        获取综合环境类型（优先判断容器和移动环境）
        
        返回:
            str: 环境类型，可能值为"android"、"docker"、"windows"、"linux"、"macos"或"unknown"
        """
        # Android环境优先（在Docker之前检测，因为Android也可能运行Docker）
        if SystemDetector.is_android():
            return "android"
        
        # 容器环境次优先
        if SystemDetector.is_docker():
            return "docker"
        
        # 否则返回操作系统类型
        return SystemDetector.get_os()

# 新增便捷函数
def is_android() -> bool:
    """便捷函数：判断是否为Android环境"""
    return SystemDetector.is_android()
```

**关键设计**：
- `is_android()` 遵循与 `is_docker()` 完全相同的设计模式
- `get_environment()` 中 Android 检测优先于 Docker（避免边缘情况误判）
- 现有的 `is_docker()`、`is_windows()`、`get_os()` 函数**不做任何修改**

### 4.2 条件导入策略

在 `main.py` 中通过条件导入跳过 Android 上不可用的桌面依赖，**不删除任何现有导入**：

```python
# main.py — 修改说明（仅新增条件判断，不删除现有代码）

import os
import sys
import threading
import logging
import time
from datetime import datetime, date

# 新增：平台检测（在文件顶部导入）
from utils.system_detector import is_android

# ===== 启动计时 profiling =====
_startup_time = time.perf_counter()
def _stamp(label):
    """记录启动阶段耗时"""
    elapsed = time.perf_counter() - _startup_time
    logging.info(f"[启动计时] {label}: {elapsed:.3f}s")

# 导入配置类
from config import Config, config
_stamp("导入config")
from utils.db_config import DatabaseConfig
_stamp("导入db_config")

# ... 中间代码保持不变 ...

# 主程序入口
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='行政后勤管理系统')
    parser.add_argument('--uninstall', action='store_true', help='执行卸载清理操作')
    parser.add_argument('--no-reload', action='store_true', help='禁用自动重载')
    parser.add_argument('--config', type=str, help='指定配置环境')
    args = parser.parse_args()
    logging.info("解析命令行参数")
    
    if args.uninstall:
        is_docker_env = os.environ.get('DOCKER_ENV', 'false').lower() == 'true'
        # 新增：Android 环境也不执行卸载操作
        is_android_env = is_android()
        if is_docker_env or is_android_env:
            logging.warning("在Docker/Android环境中，不执行卸载操作。")
        else:
            from utils.uninstall_handler import handle_uninstall
            handle_uninstall()
    logging.info("处理卸载参数")
    
    config_data = DatabaseConfig.load_config()
    server_mode = config_data.get("SERVER_MODE", "客户端")
    
    # 新增：Android 强制客户端模式
    if is_android():
        server_mode = "客户端"
        logging.info("Android环境，强制使用客户端模式")
    else:
        from utils.system_detector import is_win7
        if is_win7():
            server_mode = "服务端"
    
    # 新增：Android 入口分支
    if is_android():
        logging.info("以Android模式启动")
        app, process_cleaner, run_server = init_flask_app()
        process_cleaner.register_signal_handlers()
        # Android 上 waitress 在后台线程运行，由 Chaquopy 管理
        run_server()
    
    elif server_mode == "服务端" and current_config.USE_DESKTOP_VIEW:
        # 现有代码完全保持不变
        logging.info("以服务端模式启动，不启动WebView2")
        # ... 服务端模式代码不变 ...
    
    elif server_mode == "客户端" and current_config.USE_DESKTOP_VIEW:
        # 现有代码完全保持不变
        import webview
        # ... 客户端模式代码不变 ...
    
    else:
        # 现有代码完全保持不变
        logging.info("以开发模式启动")
        # ... 开发模式代码不变 ...
```

**关键设计**：
- `is_android()` 分支在所有现有分支**之前**判断，确保 Android 走独立路径
- 现有的服务端模式、客户端模式、开发模式代码**完全不变**
- Android 分支中不导入 `webview`、`tkinter`、`pystray`，避免导入错误

### 4.3 Android 适配层

新建 `utils/android_adapter.py` 独立文件，提供 Android 上的替代实现：

```python
# utils/android_adapter.py — 新增文件

"""
Android 平台适配层

提供 Android 环境下的路径映射、环境配置和桌面依赖的空模块替换。
此文件仅在 Android 环境下被使用，不影响 Windows/Docker 端的任何逻辑。
"""

import os
import sys
import logging
import types

logger = logging.getLogger(__name__)

# ==================== 路径映射 ====================

_android_context = None

def set_android_context(context):
    """设置 Android Context（由 Chaquopy 调用）"""
    global _android_context
    _android_context = context

def get_android_context():
    """获取 Android Context"""
    return _android_context

def get_files_dir():
    """
    获取 Android 内部存储路径（等同于 Context.getFilesDir()）
    Chaquopy 环境下通过 sys.path 推断，或通过 Context 获取
    """
    if _android_context is not None:
        try:
            return str(_android_context.getFilesDir().getAbsolutePath())
        except Exception:
            pass
    
    # 备用方案：从 sys.path 推断
    for path in sys.path:
        if 'files' in path and 'chaquopy' in path.lower():
            return os.path.dirname(path)
    
    # 最终回退
    return os.getcwd()

def get_cache_dir():
    """获取 Android 缓存路径"""
    if _android_context is not None:
        try:
            return str(_android_context.getCacheDir().getAbsolutePath())
        except Exception:
            pass
    return os.path.join(get_files_dir(), 'cache')

def get_database_path(db_name='dorm.db'):
    """获取数据库文件路径"""
    return os.path.join(get_files_dir(), 'data', db_name)

# ==================== 环境配置 ====================

def setup_android_env():
    """
    设置 Android 环境变量
    
    在 Flask 启动前调用，确保所有环境检测正确识别 Android 平台。
    """
    # 设置 Android 环境标识（与 DOCKER_ENV 机制一致）
    os.environ['ANDROID_ENV'] = 'true'
    
    # 强制客户端模式
    os.environ['SERVER_MODE'] = '客户端'
    
    # 禁用桌面视图
    os.environ['USE_DESKTOP_VIEW'] = 'false'
    
    # 设置数据目录
    files_dir = get_files_dir()
    os.environ.setdefault('APP_DATA_DIR', files_dir)
    
    # 配置 Python 路径
    app_dir = files_dir
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    
    logger.info(f"Android 环境配置完成: files_dir={files_dir}")

# ==================== 空模块替换（Stub） ====================

def _create_stub_module(name, attrs=None):
    """
    创建空模块替换
    
    在 Android 上替换 tkinter、pywebview、pystray、psutil 等不可用的桌面依赖。
    模块提供空函数/类，确保 import 不报错，但调用时抛出明确异常。
    """
    module = types.ModuleType(name)
    module.__file__ = f'<android_stub:{name}>'
    module.__package__ = name
    
    if attrs:
        for attr_name, attr_value in attrs.items():
            setattr(module, attr_name, attr_value)
    
    return module

def _stub_function(name):
    """创建一个调用时抛出异常的空函数"""
    def _func(*args, **kwargs):
        raise RuntimeError(
            f"{name}() 不可用：当前运行在 Android 平台，"
            f"此功能需要桌面环境支持。"
        )
    _func.__name__ = name
    return _func

def install_stub_modules():
    """
    安装空模块替换
    
    在 Android 上替换以下不可用的桌面依赖：
    - tkinter: GUI 工具包
    - pywebview: 桌面 WebView
    - pystray: 系统托盘
    - psutil: 进程管理（Android 使用 Activity 生命周期替代）
    
    注意：仅在 Android 环境下调用，Windows/Docker 端不受影响。
    """
    if not os.environ.get('ANDROID_ENV', 'false').lower() == 'true':
        logger.debug("非 Android 环境，跳过 stub 模块安装")
        return
    
    # tkinter stub
    if 'tkinter' not in sys.modules:
        tkinter_stub = _create_stub_module('tkinter', {
            'Tk': type('Tk', (), {'__init__': _stub_function('tkinter.Tk')}),
            'Frame': type('Frame', (), {}),
            'Label': type('Label', (), {}),
            'Button': type('Button', (), {}),
            'messagebox': _create_stub_module('tkinter.messagebox', {
                'showinfo': _stub_function('messagebox.showinfo'),
                'showwarning': _stub_function('messagebox.showwarning'),
                'showerror': _stub_function('messagebox.showerror'),
            }),
        })
        sys.modules['tkinter'] = tkinter_stub
        sys.modules['tkinter.messagebox'] = tkinter_stub.messagebox
    
    # pywebview stub
    if 'webview' not in sys.modules:
        webview_stub = _create_stub_module('webview', {
            'create_window': _stub_function('webview.create_window'),
            'start': _stub_function('webview.start'),
        })
        sys.modules['webview'] = webview_stub
    
    # pystray stub
    if 'pystray' not in sys.modules:
        pystray_stub = _create_stub_module('pystray', {
            'Icon': type('Icon', (), {'__init__': _stub_function('pystray.Icon')}),
        })
        sys.modules['pystray'] = pystray_stub
    
    # psutil stub（Android 使用 Activity 生命周期替代进程管理）
    if 'psutil' not in sys.modules:
        psutil_stub = _create_stub_module('psutil', {
            'Process': type('Process', (), {'__init__': _stub_function('psutil.Process')}),
            'process_iter': _stub_function('psutil.process_iter'),
            'pid_exists': _stub_function('psutil.pid_exists'),
        })
        sys.modules['psutil'] = psutil_stub
    
    logger.info("Android stub 模块安装完成")

# ==================== Flask 启动适配 ====================

def start_flask_server():
    """
    Android 端 Flask 服务器启动入口
    
    由 Chaquopy 从 Android 端调用，完成以下步骤：
    1. 安装 stub 模块
    2. 设置 Android 环境变量
    3. 启动 Flask+waitress 服务器
    """
    # 1. 安装 stub 模块（必须在所有 import 之前）
    install_stub_modules()
    
    # 2. 设置环境变量
    setup_android_env()
    
    # 3. 导入并启动 Flask
    from main import init_flask_app
    app, process_cleaner, run_server = init_flask_app()
    
    logger.info("Android 端 Flask 应用初始化完成")
    
    # 4. 启动 waitress 服务器
    run_server()
    
    return app
```

### 4.4 config.py 适配

在 `config.py` 中新增 `ANDROID_ENV` 分支，遵循现有 `DOCKER_ENV` 的设计模式：

```python
# config.py — 新增内容（不修改现有代码逻辑）

class Config:
    # ... 现有配置保持不变 ...
    
    # 判断环境
    is_docker = os.environ.get('DOCKER_ENV', 'false').lower() == 'true'
    is_android = os.environ.get('ANDROID_ENV', 'false').lower() == 'true'  # 新增
    
    # 备份目录配置（新增 Android 分支）
    if is_android:                                          # 新增
        # Android 环境 - 使用内部存储
        APP_DIR = os.environ.get('APP_DATA_DIR', os.getcwd())
        BACKUP_DIR = os.path.join(APP_DIR, 'data', 'backups')
    elif os.environ.get('DOCKER_ENV', 'false').lower() == 'true':
        BACKUP_DIR = '/data/backups'    # Docker环境
    elif getattr(sys, 'frozen', False):
        APP_DIR = get_app_dir()
        BACKUP_DIR = os.path.join(APP_DIR, 'data', 'backups')
    else:
        BACKUP_DIR = os.path.join(BASE_DIR, 'data', 'backups')
    
    # 桌面视图配置（新增 Android 分支）
    if is_android:                                          # 新增
        USE_DESKTOP_VIEW = False  # Android 无桌面环境
    elif is_docker:
        USE_DESKTOP_VIEW = False
    else:
        USE_DESKTOP_VIEW = True


class ProductionConfig(Config):
    # ... 现有配置保持不变 ...
    
    # SERVER_HOST 配置（新增 Android 分支）
    if os.environ.get('ANDROID_ENV', 'false').lower() == 'true':   # 新增
        SERVER_HOST = '127.0.0.1'  # Android 强制本地访问
    elif os.environ.get('DOCKER_ENV', 'false').lower() == 'true':
        SERVER_HOST = '0.0.0.0'
    else:
        server_mode = db_config.get('SERVER_MODE', '客户端')
        SERVER_HOST = '0.0.0.0' if server_mode == '服务端' else '127.0.0.1'


class DevelopmentConfig(Config):
    # ... 现有配置保持不变 ...
    
    # SERVER_HOST 配置（新增 Android 分支，与 ProductionConfig 一致）
    if os.environ.get('ANDROID_ENV', 'false').lower() == 'true':   # 新增
        SERVER_HOST = '127.0.0.1'
    elif os.environ.get('DOCKER_ENV', 'false').lower() == 'true':
        SERVER_HOST = '0.0.0.0'
    else:
        server_mode = db_config.get('SERVER_MODE', '客户端')
        SERVER_HOST = '0.0.0.0' if server_mode == '服务端' else '127.0.0.1'
```

**关键设计**：
- `ANDROID_ENV` 分支始终在 `DOCKER_ENV` 分支**之前**判断
- Android 环境下 `USE_DESKTOP_VIEW = False`，`SERVER_HOST = '127.0.0.1'`
- 现有的 `DOCKER_ENV` 分支和默认分支**完全不变**

### 4.5 数据库路径适配

Android 上 SQLite 数据库文件存储在内部存储区域：

```python
# utils/db_config.py — 需要新增 Android 路径适配

# 现有逻辑（保持不变）：
# - Windows: BASE_DIR/data/dorm.db
# - Docker: /data/dorm.db（数据卷映射）

# 新增 Android 路径适配：
def get_sqlite_path():
    """获取 SQLite 数据库路径"""
    from utils.system_detector import is_android
    
    if is_android():
        # Android: 使用内部存储
        from utils.android_adapter import get_database_path
        return get_database_path('dorm.db')
    
    # 现有逻辑保持不变
    # ...
```

**路径映射表**：

| 路径类型 | Windows | Docker | Android |
|---------|---------|--------|---------|
| **数据库** | `BASE_DIR/data/dorm.db` | `/data/dorm.db` | `getFilesDir()/data/dorm.db` |
| **日志** | `BASE_DIR/logs/` | `/data/logs/` | `getFilesDir()/logs/` |
| **备份** | `BACKUP_DIR` | `/data/backups/` | `getFilesDir()/data/backups/` |
| **上传文件** | `BASE_DIR/uploads/` | `/app/uploads/` | `getFilesDir()/uploads/` |
| **配置文件** | `BASE_DIR/db_config.json` | `/app/db_config.json` | `getFilesDir()/db_config.json` |

### 4.6 移除桌面端依赖的方式

采用 **空模块 stub 替换** 策略，而非条件导入：

| 依赖 | Windows 用途 | Android 替代方案 | Stub 策略 |
|------|-------------|-----------------|----------|
| `tkinter` | 服务端 GUI | 无（Android 无桌面） | 空模块 + 空类 |
| `pywebview` | 客户端桌面窗口 | Android WebView | 空模块 + 空函数 |
| `pystray` | 系统托盘 | 无（Android 通知系统） | 空模块 + 空类 |
| `psutil` | 进程管理 | Activity 生命周期 | 空模块 + 空函数 |

**为什么选择 stub 替换而非条件导入**：
1. **最小侵入性**：不需要修改现有代码中的 `import tkinter` 等语句
2. **零风险**：stub 模块仅在 Android 环境下安装，Windows/Docker 端使用真实模块
3. **一致性**：与 `DOCKER_ENV` 跳过 tkinter GUI 的方式保持一致
4. **可调试**：stub 函数调用时抛出明确异常，便于排查问题

```python
# stub 模块安装时机（在 android_adapter.py 中）
# 必须在所有其他 import 之前执行：
# 1. Chaquopy 启动 Python 解释器
# 2. 调用 android_adapter.install_stub_modules()  ← 第一步
# 3. 调用 android_adapter.setup_android_env()      ← 第二步
# 4. 导入 main 模块，启动 Flask                    ← 第三步
```

---

## 5. 前端适配方案

### 5.1 WebView 配置

Android WebView 需要正确配置以支持 Flask 渲染的页面：

```kotlin
// MainActivity.kt — WebView 配置

class MainActivity : AppCompatActivity() {
    private lateinit var webView: WebView
    private var python: Python? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        // 初始化 Chaquopy Python
        python = Python.getInstance()
        
        // 启动 Flask 后台服务
        startFlaskServer()
        
        // 配置 WebView
        webView = findViewById(R.id.webview)
        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            useWideViewPort = true
            loadWithOverviewMode = true
            setSupportZoom(true)
            builtInZoomControls = true
            displayZoomControls = false
            cacheMode = WebSettings.LOAD_DEFAULT
            allowFileAccess = true
            allowContentAccess = true
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            userAgentString = userAgentString + " DormManagement/Android"
        }
        
        // WebViewClient — 仅允许加载本地 Flask 服务
        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(
                view: WebView?, request: WebResourceRequest?
            ): Boolean {
                val url = request?.url?.toString() ?: return false
                if (url.startsWith("http://127.0.0.1:35168") ||
                    url.startsWith("http://localhost:35168")) {
                    return false
                }
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
                startActivity(intent)
                return true
            }
            
            override fun onReceivedError(
                view: WebView?, request: WebResourceRequest?,
                error: WebResourceError?
            ) {
                super.onReceivedError(view, request, error)
                view?.loadUrl("about:blank")
                showErrorPage("服务连接失败，请稍后重试")
            }
        }
        
        webView.webChromeClient = DormWebChromeClient(this)
        waitForServerAndLoad()
    }
    
    private fun startFlaskServer() {
        Thread {
            val androidAdapter = python!!.getModule("android_adapter")
            androidAdapter.callAttr("set_android_context", this)
            androidAdapter.callAttr("start_flask_server")
        }.start()
    }
    
    private fun waitForServerAndLoad() {
        Thread {
            var retries = 0
            val maxRetries = 60
            while (retries < maxRetries) {
                try {
                    val url = URL("http://127.0.0.1:35168/login")
                    val conn = url.openConnection() as HttpURLConnection
                    conn.requestMethod = "GET"
                    conn.connectTimeout = 2000
                    conn.responseCode
                    runOnUiThread { webView.loadUrl("http://127.0.0.1:35168/login") }
                    return@Thread
                } catch (e: Exception) {
                    retries++
                    Thread.sleep(500)
                }
            }
            runOnUiThread { showErrorPage("服务器启动超时，请重启应用") }
        }.start()
    }
}
```

### 5.2 JS Bridge

WebView 与 Android 原生功能通过 JS Bridge 交互：

```kotlin
// JsBridgeInterface.kt

class JsBridgeInterface(private val activity: Activity) {
    
    @JavascriptInterface
    fun chooseFile(acceptTypes: String): String {
        val intent = Intent(Intent.ACTION_GET_CONTENT)
        intent.type = acceptTypes.ifEmpty { "*/*" }
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        activity.startActivityForResult(intent, REQUEST_FILE_CHOOSER)
        return ""
    }
    
    @JavascriptInterface
    fun takePhoto(): String {
        val intent = Intent(MediaStore.ACTION_IMAGE_CAPTURE)
        if (intent.resolveActivity(activity.packageManager) != null) {
            val photoFile = createImageFile()
            val uri = FileProvider.getUriForFile(
                activity, "${activity.packageName}.fileprovider", photoFile
            )
            intent.putExtra(MediaStore.EXTRA_OUTPUT, uri)
            activity.startActivityForResult(intent, REQUEST_CAMERA)
        }
        return ""
    }
    
    @JavascriptInterface
    fun showNotification(title: String, message: String) {
        val notificationManager = activity.getSystemService(
            Context.NOTIFICATION_SERVICE
        ) as NotificationManager
        val channel = NotificationChannel(
            "dorm_management", "宿舍管理", NotificationManager.IMPORTANCE_DEFAULT
        )
        notificationManager.createNotificationChannel(channel)
        val notification = NotificationCompat.Builder(activity, "dorm_management")
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(message)
            .setAutoCancel(true)
            .build()
        notificationManager.notify(1, notification)
    }
    
    @JavascriptInterface
    fun getDeviceInfo(): String {
        return JSONObject().apply {
            put("platform", "android")
            put("deviceModel", Build.MODEL)
            put("androidVersion", Build.VERSION.RELEASE)
            put("appId", activity.packageName)
        }.toString()
    }
    
    @JavascriptInterface
    fun exitApp() { activity.finish() }
    
    companion object {
        private const val REQUEST_FILE_CHOOSER = 1001
        private const val REQUEST_CAMERA = 1002
    }
}

// 注册 JS Bridge
webView.addJavascriptInterface(JsBridgeInterface(this), "AndroidBridge")
```

**前端 JS 调用示例**：

```javascript
// 检测 Android 环境
function isAndroid() {
    return typeof AndroidBridge !== 'undefined';
}

// 文件选择
function chooseFile(acceptTypes) {
    if (isAndroid()) {
        AndroidBridge.chooseFile(acceptTypes || '*/*');
    } else {
        document.getElementById('file-input').click();
    }
}

// 拍照
function takePhoto() {
    if (isAndroid()) {
        AndroidBridge.takePhoto();
    } else {
        alert('此功能仅支持移动端');
    }
}
```

### 5.3 响应式布局适配

现有前端使用 Tailwind CSS，已具备响应式能力，需针对移动端优化：

```html
<!-- header.html 中添加移动端 viewport 和适配样式 -->
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">

{% if config.get('ANDROID_ENV', false) %}
<style>
    body { -webkit-overflow-scrolling: touch; overscroll-behavior: none; }
    .sidebar { transform: translateX(-100%); transition: transform 0.3s ease; z-index: 1000; }
    .sidebar.open { transform: translateX(0); }
    .table-responsive { overflow-x: auto; -webkit-overflow-scrolling: touch; }
    .safe-area-bottom { padding-bottom: env(safe-area-inset-bottom, 0px); }
</style>
{% endif %}
```

### 5.4 文件/相机桥接

```kotlin
// WebChromeClient 扩展 — 支持文件上传
class DormWebChromeClient(private val activity: Activity) : WebChromeClient() {
    private var filePathCallback: ValueCallback<Array<Uri>>? = null
    
    override fun onShowFileChooser(
        webView: WebView?,
        filePathCallback: ValueCallback<Array<Uri>>?,
        fileChooserParams: FileChooserParams?
    ): Boolean {
        this.filePathCallback = filePathCallback
        val intent = fileChooserParams?.createIntent()
        try {
            activity.startActivityForResult(intent, REQUEST_FILE_CHOOSER)
            return true
        } catch (e: ActivityNotFoundException) {
            this.filePathCallback = null
            return false
        }
    }
}
```

### 5.5 启动屏动画过渡方案

采用 **SplashScreen API + 兼容回退 + Lottie 动画** 三层方案：

```xml
<!-- res/values/themes.xml — Android 12+ SplashScreen -->
<style name="Theme.DormManagement.Splash" parent="Theme.SplashScreen">
    <item name="windowSplashScreenBackground">@color/splash_background</item>
    <item name="windowSplashScreenAnimatedIcon">@drawable/splash_icon_animated</item>
    <item name="windowSplashScreenAnimationDuration">1500</item>
    <item name="postSplashScreenTheme">@style/Theme.DormManagement</item>
</style>
```

```kotlin
// build.gradle.kts 依赖
implementation("androidx.core:core-splashscreen:1.0.1")
implementation("com.airbnb.android:lottie:6.1.0")
```

**启动流程**：

```
1. Android 系统启动屏（SplashScreen API / 兼容库）
   └─ 显示应用图标 + 品牌色背景，持续 1.5 秒

2. Lottie 动画加载屏（Flask 初始化期间）
   └─ 显示 Lottie 动画 + "正在启动服务..." + 进度条 0%~100%
   └─ 通过 Chaquopy 回调获取 Flask 初始化进度

3. WebView 加载页面
   └─ 隐藏 Lottie 动画，WebView 显示 Flask 渲染的登录页面
```

---

## 6. 数据库方案

### 6.1 SQLite 路径映射

Android 上 SQLite 数据库存储在应用内部存储区域：

```python
# 路径映射逻辑（在 db_config.py 中新增）
def get_database_path():
    from utils.system_detector import is_android, is_docker
    if is_android():
        from utils.android_adapter import get_database_path
        return get_database_path('dorm.db')
    if is_docker():
        return '/data/dorm.db'
    return os.path.join(BASE_DIR, 'data', 'dorm.db')
```

**Android 数据目录初始化**：

```kotlin
// MainActivity.kt — 首次启动创建数据目录
private fun ensureDataDirectories() {
    val dirs = listOf("data", "logs", "backups", "uploads", "static", "temp")
    dirs.forEach { dir -> File(filesDir, dir).mkdirs() }
}
```

**路径映射表**：

| 路径类型 | Windows | Docker | Android |
|---------|---------|--------|---------|
| **数据库** | `BASE_DIR/data/dorm.db` | `/data/dorm.db` | `getFilesDir()/data/dorm.db` |
| **日志** | `BASE_DIR/logs/` | `/data/logs/` | `getFilesDir()/logs/` |
| **备份** | `BACKUP_DIR` | `/data/backups/` | `getFilesDir()/data/backups/` |
| **上传文件** | `BASE_DIR/uploads/` | `/app/uploads/` | `getFilesDir()/uploads/` |
| **配置文件** | `BASE_DIR/db_config.json` | `/app/db_config.json` | `getFilesDir()/db_config.json` |

### 6.2 MySQL 远程连接

Android 端同样支持 MySQL 远程连接，配置方式与 Windows/Docker 一致：

```json
{
    "SQL_TYPE": "MYSQL",
    "MYSQL_HOST": "192.168.1.100",
    "MYSQL_PORT": 3306,
    "MYSQL_USER": "dorm_user",
    "MYSQL_PASSWORD": "encrypted_password",
    "MYSQL_DATABASE": "dorm_management",
    "SERVER_PORT": 35168,
    "SERVER_MODE": "客户端"
}
```

**注意**：Android 上 MySQL 连接需要 `INTERNET` 权限，建议使用 SSL 加密，网络不稳定时自动回退到 SQLite（现有逻辑已支持）。

### 6.3 数据迁移

| 场景 | 方案 |
|------|------|
| **首次安装** | 自动创建 SQLite 数据库（Flask-Migrate 已支持） |
| **应用更新** | 通过 Flask-Migrate 自动执行数据库迁移 |
| **Windows → Android** | 导出 Windows 端 SQLite 文件，通过文件共享传输到 Android |
| **Android → Windows** | 从 Android 内部存储导出 SQLite 文件 |
| **MySQL 同步** | 多端共享 MySQL 数据库，无需迁移 |

---

## 7. 项目结构设计

### 7.1 Android 项目目录结构

```
android/                                    # Android 项目根目录
├── app/
│   ├── src/
│   │   ├── main/
│   │   │   ├── java/com/dorm/management/
│   │   │   │   ├── MainActivity.kt        # 主 Activity
│   │   │   │   ├── FlaskService.kt        # Flask 后台服务
│   │   │   │   ├── JsBridgeInterface.kt   # JS Bridge
│   │   │   │   ├── DormWebChromeClient.kt # WebView 文件选择/相机
│   │   │   │   └── SplashActivity.kt      # 启动屏
│   │   │   ├── res/
│   │   │   │   ├── layout/activity_main.xml
│   │   │   │   ├── values/{strings,colors,themes}.xml
│   │   │   │   ├── drawable/splash_icon_animated.xml
│   │   │   │   ├── raw/splash_animation.json
│   │   │   │   └── xml/{file_paths,network_security_config}.xml
│   │   │   └── AndroidManifest.xml
│   │   ├── debug/
│   │   └── release/
│   ├── build.gradle.kts
│   └── proguard-rules.pro
├── gradle/wrapper/
├── build.gradle.kts
├── settings.gradle.kts
├── gradle.properties
└── local.properties
```

### 7.2 Chaquopy Python 集成

```kotlin
// app/build.gradle.kts — Chaquopy 配置

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python") version "15.0.1"
}

android {
    namespace = "com.dorm.management"
    compileSdk = 34
    
    defaultConfig {
        applicationId = "com.dorm.management"
        minSdk = 26          // Android 8 (API 26)
        targetSdk = 34
        versionCode = 1
        versionName = "5.0"
        
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }
    
    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
}

chaquopy {
    python {
        version = "3.8"
        
        pip {
            // 优先使用 Chaquopy 官方预编译包
            install("Flask==2.3.3")
            install("Flask-SQLAlchemy==3.1.1")
            install("Flask-WTF==1.2.1")
            install("Flask-Login==0.6.3")
            install("Flask-Migrate==4.0.5")
            install("Jinja2==3.1.2")
            install("Werkzeug==2.3.7")
            install("openpyxl==3.1.2")
            install("python-dotenv==1.0.0")
            install("PyMySQL==1.1.0")
            install("cryptography==41.0.7")
            install("schedule==1.2.0")
            install("xlsxwriter==3.2.5")
            install("waitress==2.1.2")
            install("requests==2.31.0")
            install("Pillow==10.4.0")
            install("SQLAlchemy==2.0.23")
            install("Alembic==1.13.1")
            install("MarkupSafe==2.1.3")
            install("itsdangerous==2.1.2")
            install("click==8.1.7")
            install("blinker==1.7.0")
            
            // 重型包：优先使用 Chaquopy 预编译包
            install("pandas==2.0.3")
            install("numpy==1.24.4")
            
            // 桌面端专用包：不在 Android 上安装
            // pywebview、pystray、psutil — 通过 stub 替换
        }
        
        sourceSets {
            getByName("main") {
                srcDir("../")
            }
        }
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")
    implementation("androidx.webkit:webkit:1.9.0")
    implementation("androidx.core:core-splashscreen:1.0.1")
    implementation("com.airbnb.android:lottie:6.1.0")
}
```

### 7.3 Python 源码打包策略

```kotlin
// Chaquopy Python 源码打包配置

chaquopy {
    python {
        sourceSets {
            getByName("main") {
                srcDir("../")
                // 排除不需要的文件
                exclude("Auto_Setup/**")
                exclude(".github/**")
                exclude(".joycode/**")
                exclude("*.bat")
                exclude("*.spec")
                exclude("dockerfile")
                exclude(".dockerignore")
                exclude("requirements.txt")
                exclude("LICENSE")
                exclude("README.md")
                exclude("Android_Build_Plan.md")
            }
        }
    }
}
```

**打包内容**：

| 包含 | 排除 |
|------|------|
| `blueprints/` — 路由逻辑 | `Auto_Setup/` — Windows 打包 |
| `models/` — 数据模型 | `.github/` — CI/CD |
| `templates/` — Jinja2 模板 | `*.bat` — Windows 批处理 |
| `static/` — 静态资源 | `*.spec` — PyInstaller |
| `utils/` — 工具函数 | `dockerfile` — Docker |
| `config.py` — 配置 | `.joycode/` — 开发工具 |
| `main.py` — 入口 | `requirements.txt` — 通过 pip 管理 |

### 7.4 三端共享代码管理

```
项目根目录/
├── blueprints/          ← 三端共享（不修改）
├── models/              ← 三端共享（不修改）
├── templates/           ← 三端共享（不修改）
├── static/              ← 三端共享（不修改）
├── utils/
│   ├── db.py            ← 三端共享（不修改）
│   ├── db_config.py     ← 三端共享（新增 Android 路径分支）
│   ├── auth.py          ← 三端共享（不修改）
│   ├── log.py           ← 三端共享（不修改）
│   ├── system_detector.py ← 三端共享（新增 is_android 函数）
│   ├── android_adapter.py ← Android 专用（新增文件）
│   ├── server_gui.py    ← Windows 专用（Android 通过 stub 跳过）
│   ├── webview_injector.py ← Windows 专用（Android 通过 stub 跳过）
│   ├── process_cleaner.py ← 三端共享（Android 通过 stub 替代 psutil）
│   └── ...
├── config.py            ← 三端共享（新增 ANDROID_ENV 分支）
├── main.py              ← 三端共享（新增 Android 入口分支）
│
├── android/             ← Android 专用（新增目录）
│   ├── app/             ← Android 原生代码
│   └── ...
│
├── Auto_Setup/          ← Windows 专用（不修改）
│   ├── dorm_management.spec
│   ├── installer_script.iss
│   └── ...
│
└── .github/workflows/   ← CI/CD（新增 build-android job）
    └── build.yml
```

**代码修改总结**：

| 文件 | 修改类型 | 影响范围 |
|------|---------|---------|
| `utils/system_detector.py` | 新增 `is_android()` 函数 | 不影响现有函数 |
| `utils/android_adapter.py` | **新增文件** | 仅 Android 使用 |
| `config.py` | 新增 `ANDROID_ENV` 分支 | 不影响现有分支 |
| `main.py` | 新增 Android 入口分支 | 不影响现有入口 |
| `utils/db_config.py` | 新增 Android 路径分支 | 不影响现有路径逻辑 |
| `android/` | **新增目录** | Android 原生代码 |
| `.github/workflows/build.yml` | 新增 `build-android` job | 不影响现有 job |

### 7.5 构建配置

```xml
<!-- AndroidManifest.xml -->
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    xmlns:tools="http://schemas.android.com/tools">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.WRITE_EXTERNAL_STORAGE"
        android:maxSdkVersion="28" />
    <uses-permission android:name="android.permission.READ_EXTERNAL_STORAGE"
        android:maxSdkVersion="32" />
    <uses-permission android:name="android.permission.CAMERA" />
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS" />
    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />

    <application
        android:name=".DormApplication"
        android:allowBackup="true"
        android:icon="@mipmap/ic_launcher"
        android:label="@string/app_name"
        android:networkSecurityConfig="@xml/network_security_config"
        android:requestLegacyExternalStorage="true"
        android:theme="@style/Theme.DormManagement.Splash"
        tools:targetApi="34">

        <activity
            android:name=".MainActivity"
            android:configChanges="orientation|screenSize|keyboardHidden"
            android:exported="true"
            android:windowSoftInputMode="adjustResize">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <service
            android:name=".FlaskService"
            android:enabled="true"
            android:exported="false"
            android:foregroundServiceType="dataSync" />

        <provider
            android:name="androidx.core.content.FileProvider"
            android:authorities="${applicationId}.fileprovider"
            android:exported="false"
            android:grantUriPermissions="true">
            <meta-data
                android:name="android.support.FILE_PROVIDER_PATHS"
                android:resource="@xml/file_paths" />
        </provider>
    </application>
</manifest>
```

```xml
<!-- res/xml/network_security_config.xml — 允许 localhost HTTP -->
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <domain-config cleartextTrafficPermitted="true">
        <domain includeSubdomains="true">127.0.0.1</domain>
        <domain includeSubdomains="true">localhost</domain>
    </domain-config>
</network-security-config>
```

---

## 8. 构建与打包流程（三平台同步）

### 8.1 GitHub Actions 三平台 CI/CD

基于现有 `build.yml` 扩展，新增 `build-android` job：

```yaml
# .github/workflows/build.yml — 三平台 CI/CD

name: 自动化打包构建

on:
  push:
    branches: [ main, master ]
    tags: [ 'v*' ]
  workflow_dispatch:
    inputs:
      build_windows:
        description: '构建 Windows 版本'
        required: false
        default: true
        type: boolean
      build_docker:
        description: '构建 Docker 镜像'
        required: false
        default: true
        type: boolean
      build_android:                          # 新增
        description: '构建 Android APK'
        required: false
        default: true
        type: boolean

env:
  PYTHON_VERSION: '3.8'
  APP_NAME: '行政后勤管理系统'
  DOCKER_IMAGE_NAME: 'dorm-management-system'
  PYTHONIOENCODING: 'utf-8'

permissions:
  contents: write

jobs:
  # ============================================
  # Windows 平台打包 (PyInstaller + Inno Setup)
  # 现有 job — 完全保持不变
  # ============================================
  build-windows:
    name: 🖥️ Windows 打包
    runs-on: windows-latest
    if: >
      github.event_name == 'push' ||
      (github.event_name == 'workflow_dispatch' && inputs.build_windows)
    # ... 现有步骤完全不变 ...

  # ============================================
  # Docker 镜像构建
  # 现有 job — 完全保持不变
  # ============================================
  build-docker:
    name: 🐳 Docker 构建
    runs-on: ubuntu-latest
    if: >
      github.event_name == 'push' ||
      (github.event_name == 'workflow_dispatch' && inputs.build_docker)
    # ... 现有步骤完全不变 ...

  # ============================================
  # Android APK 构建（新增）
  # ============================================
  build-android:
    name: 📱 Android 打包
    runs-on: ubuntu-latest
    if: >
      github.event_name == 'push' ||
      (github.event_name == 'workflow_dispatch' && inputs.build_android)

    steps:
      - name: 📥 检出代码
        uses: actions/checkout@v7

      - name: 🔖 提取版本号
        id: version
        run: |
          HAS_VERSION=false
          if [[ "$GITHUB_REF" == refs/tags/v* ]]; then
            TAG_NAME="${GITHUB_REF#refs/tags/}"
            HAS_VERSION=true
          else
            COMMIT_MSG="${{ github.event.head_commit.message }}"
            TAG_NAME=$(echo "$COMMIT_MSG" | grep -oiE 'v[0-9]+\.[0-9]+(\.[0-9]+)?' | head -1 || true)
            if [ -n "$TAG_NAME" ]; then
              HAS_VERSION=true
            fi
          fi
          if [ "$HAS_VERSION" = true ]; then
            VERSION="${TAG_NAME#v}"
            echo "tag=$TAG_NAME" >> $GITHUB_OUTPUT
            echo "version=$VERSION" >> $GITHUB_OUTPUT
            echo "has_version=true" >> $GITHUB_OUTPUT
            echo "✅ 检测到版本号: $TAG_NAME"
          else
            echo "version=" >> $GITHUB_OUTPUT
            echo "has_version=false" >> $GITHUB_OUTPUT
            echo "ℹ️ 未检测到版本号，跳过发布"
          fi

      - name: ☕ 设置 JDK 17
        uses: actions/setup-java@v4
        with:
          java-version: '17'
          distribution: 'temurin'

      - name: 🤖 设置 Android SDK
        uses: android-actions/setup-android@v3

      - name: 📦 缓存 Gradle 依赖
        uses: actions/cache@v4
        with:
          path: |
            ~/.gradle/caches
            ~/.gradle/wrapper
            android/.gradle
            android/app/build
          key: gradle-android-${{ hashFiles('android/**/*.gradle*', 'android/**/gradle-wrapper.properties') }}
          restore-keys: gradle-android-

      - name: 🔑 解码签名密钥
        if: steps.version.outputs.has_version == 'true'
        run: |
          echo "${{ secrets.ANDROID_KEYSTORE_BASE64 }}" | base64 -d > android/app/release.keystore
          echo "KEYSTORE_PASSWORD=${{ secrets.ANDROID_KEYSTORE_PASSWORD }}" >> $GITHUB_ENV
          echo "KEY_ALIAS=${{ secrets.ANDROID_KEY_ALIAS }}" >> $GITHUB_ENV
          echo "KEY_PASSWORD=${{ secrets.ANDROID_KEY_PASSWORD }}" >> $GITHUB_ENV

      - name: 🏗️ 构建 Debug APK（无版本号时）
        if: steps.version.outputs.has_version != 'true'
        working-directory: android
        run: |
          chmod +x gradlew
          ./gradlew assembleDebug
          mkdir -p ../dist/android
          cp app/build/outputs/apk/debug/*.apk ../dist/android/DormManagement-debug.apk

      - name: 🏗️ 构建 Release APK（有版本号时）
        if: steps.version.outputs.has_version == 'true'
        working-directory: android
        run: |
          chmod +x gradlew
          ./gradlew assembleRelease \
            -PversionCode=$(echo "${{ steps.version.outputs.version }}" | tr -d '.') \
            -PversionName="${{ steps.version.outputs.version }}"
          mkdir -p ../dist/android
          cp app/build/outputs/apk/release/*.apk ../dist/android/
          cd ../dist/android
          APK_FILE=$(ls *.apk | head -1)
          mv "$APK_FILE" "DormManagement_v${{ steps.version.outputs.version }}.apk"

      - name: 📤 上传 Android APK
        uses: actions/upload-artifact@v7
        with:
          name: DormManagement_Android
          path: dist/android/
          retention-days: 30

      - name: 🚀 发布到 Release
        if: steps.version.outputs.has_version == 'true'
        uses: softprops/action-gh-release@v3
        with:
          tag_name: ${{ steps.version.outputs.tag }}
          files: dist/android/*.apk
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

  # ============================================
  # 构建总结（更新为三平台）
  # ============================================
  build-summary:
    name: 📊 构建总结
    runs-on: ubuntu-latest
    needs: [build-windows, build-docker, build-android]  # 新增 build-android
    if: always()

    steps:
      - name: 📋 输出构建结果
        run: |
          echo "========================================"
          echo "  行政后勤管理系统 - Build Summary"
          echo "========================================"
          echo ""
          echo "Windows 构建: ${{ needs.build-windows.result }}"
          echo "Docker 构建:  ${{ needs.build-docker.result }}"
          echo "Android 构建: ${{ needs.build-android.result }}"
          echo ""
          if [ "${{ needs.build-windows.result }}" = "success" ]; then
            echo "✅ Windows 版本构建成功"
          else
            echo "❌ Windows 版本构建失败或被跳过"
          fi
          if [ "${{ needs.build-docker.result }}" = "success" ]; then
            echo "✅ Docker 镜像构建成功"
          else
            echo "❌ Docker 镜像构建失败或被跳过"
          fi
          if [ "${{ needs.build-android.result }}" = "success" ]; then
            echo "✅ Android APK 构建成功"
          else
            echo "❌ Android APK 构建失败或被跳过"
          fi
          echo ""
          echo "========================================"
```

### 8.2 构建触发方式

| 触发方式 | Windows | Docker | Android |
|---------|---------|--------|---------|
| **Push 到 main/master** | ✅ 自动 | ✅ 自动 | ✅ 自动 |
| **Push tag (v\*)** | ✅ 自动 + Release | ✅ 自动 + Release | ✅ 自动 + Release |
| **手动触发（全选）** | ✅ | ✅ | ✅ |
| **手动触发（仅 Windows）** | ✅ | ❌ | ❌ |
| **手动触发（仅 Docker）** | ❌ | ✅ | ❌ |
| **手动触发（仅 Android）** | ❌ | ❌ | ✅ |
| **手动触发（任意组合）** | ✅ 可选 | ✅ 可选 | ✅ 可选 |

### 8.3 APK 签名配置

```properties
# android/gradle.properties — 签名配置
ANDROID_KEYSTORE_FILE=release.keystore
ANDROID_KEYSTORE_PASSWORD=${KEYSTORE_PASSWORD}
ANDROID_KEY_ALIAS=${KEY_ALIAS}
ANDROID_KEY_PASSWORD=${KEY_PASSWORD}
```

```kotlin
// android/app/build.gradle.kts — 签名配置
android {
    signingConfigs {
        create("release") {
            storeFile = file(System.getenv("KEYSTORE_FILE") ?: "release.keystore")
            storePassword = System.getenv("KEYSTORE_PASSWORD") ?: ""
            keyAlias = System.getenv("KEY_ALIAS") ?: ""
            keyPassword = System.getenv("KEY_PASSWORD") ?: ""
        }
    }
    
    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
            isMinifyEnabled = true
            isShrinkResources = true
        }
    }
}
```

**GitHub Secrets 配置**：

| Secret 名称 | 说明 |
|-------------|------|
| `ANDROID_KEYSTORE_BASE64` | Base64 编码的 keystore 文件 |
| `ANDROID_KEYSTORE_PASSWORD` | keystore 密码 |
| `ANDROID_KEY_ALIAS` | 签名密钥别名 |
| `ANDROID_KEY_PASSWORD` | 签名密钥密码 |

**生成签名密钥**：

```bash
keytool -genkey -v \
  -keystore release.keystore \
  -alias dorm_management \
  -keyalg RSA \
  -keysize 2048 \
  -validity 10000 \
  -storepass <password> \
  -keypass <password>

# Base64 编码（用于 GitHub Secrets）
base64 -w 0 release.keystore > keystore_base64.txt
```

### 8.4 双架构构建说明

```kotlin
// android/app/build.gradle.kts — 双架构配置
android {
    defaultConfig {
        ndk {
            // arm64-v8a: 主流手机（华为、小米、OPPO 等）
            // x86_64: Android 模拟器、少数 Chromebook
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }
    
    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a", "x86_64")
            isUniversalApk = true  // 同时生成通用 APK
        }
    }
}
```

| ABI | 设备类型 | 市场占比 | 备注 |
|-----|---------|---------|------|
| `arm64-v8a` | 主流手机 | ~99% | 必须支持 |
| `x86_64` | 模拟器/Chromebook | ~1% | 开发调试用 |
| `armeabi-v7a` | 旧款手机 | <1% | API 26+ 设备极少 |
| `x86` | 旧模拟器 | <1% | 已被 x86_64 取代 |

### 8.5 包体积预估

| 组件 | 预估大小 | 说明 |
|------|---------|------|
| Android 原生代码 | ~2 MB | Kotlin 代码 + 资源 |
| Chaquopy Python 运行时 | ~15 MB | arm64-v8a |
| Python 标准库 | ~10 MB | |
| Flask + 依赖 | ~8 MB | Flask, SQLAlchemy, Jinja2 等 |
| pandas + numpy | ~25 MB | 预编译包 |
| 项目 Python 源码 | ~3 MB | blueprints, models, utils 等 |
| 模板 + 静态资源 | ~5 MB | Jinja2, CSS, JS, 图片, 字体 |
| **APK 总计（单架构）** | **~68 MB** | arm64-v8a |
| **APK 总计（通用）** | **~90 MB** | 包含双架构 |

**优化措施**：
- Release 构建启用 `minifyEnabled` 和 `shrinkResources`
- 使用 ProGuard/R8 代码混淆和压缩
- 排除 `__pycache__`、`.pyc`、测试文件等
- 考虑按需下载 pandas/numpy（首次启动时下载）

---

## 9. 兼容性与性能

### 9.1 Android 8+ 兼容性（API 26）

| API Level | Android 版本 | 市场占比 | 支持状态 |
|-----------|-------------|---------|---------|
| 26 | Android 8.0 | ~5% | ✅ 最低支持 |
| 27 | Android 8.1 | ~3% | ✅ |
| 28 | Android 9 | ~15% | ✅ |
| 29 | Android 10 | ~20% | ✅ |
| 30 | Android 11 | ~25% | ✅ |
| 31 | Android 12 | ~15% | ✅ |
| 32 | Android 12L | ~2% | ✅ |
| 33 | Android 13 | ~10% | ✅ |
| 34 | Android 14 | ~5% | ✅ |

**API 26 关键限制**：
- `NotificationChannel` 必须创建（Android 8+ 强制要求）
- 后台服务限制（需使用 `Foreground Service`）
- `WebView` 安全更新通过 Chrome 更新机制
- `doze` 模式影响后台网络和 CPU

**兼容性处理**：

```kotlin
// 通知渠道（Android 8+ 必需）
private fun createNotificationChannel() {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        val channel = NotificationChannel(
            "flask_service", "Flask 后台服务",
            NotificationManager.IMPORTANCE_LOW
        ).apply { description = "保持 Flask 服务器在后台运行" }
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(channel)
    }
}

// 前台服务（Android 8+ 后台限制）
private fun startFlaskForegroundService() {
    val intent = Intent(this, FlaskService::class.java)
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        startForegroundService(intent)
    } else {
        startService(intent)
    }
}
```

### 9.2 Python 包 ARM 兼容性

**Chaquopy 预编译包策略**（优先使用预编译包，避免在设备上编译）：

| Python 包 | Chaquopy 预编译 | ARM64 兼容性 | 备注 |
|-----------|----------------|-------------|------|
| Flask | ✅ 有 | ✅ 纯 Python | 无问题 |
| SQLAlchemy | ✅ 有 | ✅ 纯 Python | 无问题 |
| Jinja2 | ✅ 有 | ✅ 纯 Python | 无问题 |
| Werkzeug | ✅ 有 | ✅ 纯 Python | 无问题 |
| openpyxl | ✅ 有 | ✅ 纯 Python | 无问题 |
| Pillow | ✅ 有 | ✅ 预编译 C 扩展 | Chaquopy 提供 |
| cryptography | ✅ 有 | ✅ 预编译 C 扩展 | Chaquopy 提供 |
| PyMySQL | ✅ 有 | ✅ 纯 Python | 无问题 |
| pandas | ⚠️ 需确认 | ⚠️ C 扩展 | 优先使用 Chaquopy 预编译包 |
| numpy | ⚠️ 需确认 | ⚠️ C 扩展 + Fortran | 优先使用 Chaquopy 预编译包 |
| waitress | ✅ 有 | ✅ 纯 Python | 无问题 |
| schedule | ✅ 有 | ✅ 纯 Python | 无问题 |
| xlsxwriter | ✅ 有 | ✅ 纯 Python | 无问题 |
| requests | ✅ 有 | ✅ 纯 Python | 无问题 |
| python-dotenv | ✅ 有 | ✅ 纯 Python | 无问题 |

**pandas/numpy ARM 兼容性风险应对**：

1. **优先使用 Chaquopy 官方预编译包**
2. **备选：使用较旧版本**（pandas 2.0.3 / numpy 1.24.4 已有成熟的 ARM 编译支持）
3. **备选：使用 openpyxl + xlsxwriter 替代 pandas 的 Excel 功能**
4. **极端备选：首次启动时从 CDN 下载预编译 wheel**
5. **最终备选：禁用 Excel 导入/导出功能（仅 Android 端）**

### 9.3 启动优化

**启动流程优化**：

```
冷启动时间目标：< 8 秒

阶段1: Android 启动屏（系统控制）         ~1.5s
阶段2: Lottie 动画 + Flask 初始化         ~5s
  ├── Chaquopy Python 初始化              ~1s
  ├── stub 模块安装 + 环境配置             ~0.1s
  ├── Flask 应用初始化                     ~2s
  │   ├── 导入 Flask + 扩展               ~0.5s
  │   ├── 注册蓝图                         ~0.5s
  │   └── 初始化数据库                     ~1s
  └── waitress 服务器启动                  ~1s
阶段3: WebView 加载登录页                  ~1.5s
```

**优化措施**：

1. **延迟导入**：利用现有 `lazy_imports.py` 机制，pandas/numpy 在首次使用时才加载
2. **数据库预热**：首次启动时预创建表和索引
3. **静态资源缓存**：WebView 启用缓存，减少重复加载
4. **Chaquopy 预加载**：在 Application 类中预初始化 Python 运行时

```kotlin
// DormApplication.kt — 预加载 Python
class DormApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }
    }
}
```

### 9.4 内存管理

| 场景 | 内存使用 | 优化措施 |
|------|---------|---------|
| **Flask 空闲** | ~50 MB | 足够 |
| **Flask + 1 用户** | ~80 MB | 正常 |
| **pandas 加载** | +30-50 MB | 延迟加载，用完释放 |
| **WebView 渲染** | +50-80 MB | 启用硬件加速 |
| **峰值** | ~200 MB | 需 2GB+ 内存设备 |

**内存优化措施**：

1. **pandas 延迟加载**：仅在导入/导出 Excel 时加载，操作完成后释放
2. **WebView 内存控制**：`onPause` 时释放 WebView 缓存
3. **图片压缩**：上传图片前压缩到合理尺寸
4. **数据库连接池**：配置 SQLAlchemy 连接池大小

```kotlin
// MainActivity.kt — 内存管理
override fun onPause() {
    super.onPause()
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
        webView.pauseTimers()
    }
}

override fun onResume() {
    super.onResume()
    if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
        webView.resumeTimers()
    }
}

override fun onTrimMemory(level: Int) {
    super.onTrimMemory(level)
    if (level >= TRIM_MEMORY_MODERATE) {
        webView.clearCache(false)
    }
}

override fun onDestroy() {
    webView.destroy()
    super.onDestroy()
}
```

---

## 10. 测试方案

### 10.1 三端回归测试

**确保 Windows/Docker 功能不受 Android 适配影响**：

| 测试类别 | Windows 端 | Docker 端 | Android 端 |
|---------|-----------|----------|-----------|
| **启动测试** | ✅ 客户端模式启动 | ✅ Docker 容器启动 | ✅ APK 启动 |
| | ✅ 服务端模式启动 | ✅ 端口 35168 监听 | ✅ Flask 服务就绪 |
| | ✅ Win7 兼容模式 | ✅ 数据卷挂载 | ✅ WebView 加载 |
| **核心功能** | ✅ 用户登录/登出 | ✅ 用户登录/登出 | ✅ 用户登录/登出 |
| | ✅ 数据 CRUD 操作 | ✅ 数据 CRUD 操作 | ✅ 数据 CRUD 操作 |
| | ✅ Excel 导入/导出 | ✅ Excel 导入/导出 | ✅ Excel 导入/导出 |
| | ✅ 数据备份/恢复 | ✅ 数据备份/恢复 | ✅ 数据备份/恢复 |
| **平台特有** | ✅ pywebview 窗口 | ✅ 环境变量检测 | ✅ WebView 文件选择 |
| | ✅ tkinter GUI | ✅ 无桌面 GUI | ✅ JS Bridge 调用 |
| | ✅ pystray 系统托盘 | ✅ waitress 服务 | ✅ 后台服务保活 |
| | ✅ psutil 进程管理 | ✅ 数据持久化 | ✅ Activity 生命周期 |

**回归测试流程**：

```
每次 Android 适配代码修改后：
1. 在 Windows 端运行完整功能测试
2. 在 Docker 端运行完整功能测试
3. 确认 is_android() 在 Windows/Docker 上返回 False
4. 确认 is_docker() 在 Docker 上仍返回 True
5. 确认 get_environment() 返回值正确
6. 确认 config.py 中 ANDROID_ENV 分支不影响 Windows/Docker
7. 确认 main.py 中 Android 分支不影响 Windows/Docker 入口
```

### 10.2 Android 功能测试

| 测试场景 | 测试内容 | 预期结果 |
|---------|---------|---------|
| **首次启动** | 安装 APK 后首次启动 | 启动屏 → Flask 初始化 → 加载登录页 |
| **冷启动** | 杀死进程后重新启动 | < 8 秒加载完成 |
| **热启动** | 从后台恢复 | WebView 恢复，无需重新加载 |
| **登录** | 输入用户名密码登录 | 成功登录，跳转主页 |
| **数据浏览** | 浏览宿舍/房间/人员列表 | 列表正常显示，滚动流畅 |
| **数据编辑** | 新增/修改/删除记录 | 操作成功，数据持久化 |
| **Excel 导出** | 导出数据为 Excel | 文件保存到内部存储 |
| **Excel 导入** | 从文件选择器选择 Excel | 数据正确导入 |
| **相机拍照** | 通过 JS Bridge 调用相机 | 拍照后图片上传 |
| **后台运行** | 切换到其他应用 | Flask 服务继续运行 |
| **内存不足** | 系统内存不足时 | 优雅降级，不崩溃 |
| **网络切换** | WiFi ↔ 移动数据切换 | 本地功能不受影响 |
| **MySQL 连接** | 配置 MySQL 远程连接 | 成功连接并操作数据 |
| **SQLite 回退** | MySQL 不可用时 | 自动回退到 SQLite |

### 10.3 兼容性测试

| 设备类别 | 测试设备 | Android 版本 | 测试重点 |
|---------|---------|-------------|---------|
| **主流手机** | 小米/华为/OPPO | 12-14 | WebView 兼容性、性能 |
| **中端手机** | 红米/荣耀 | 10-11 | 内存管理、启动速度 |
| **旧款手机** | 各品牌 | 8-9 | API 26 兼容性 |
| **平板** | 三星/华为平板 | 11-14 | 响应式布局 |
| **模拟器** | Android Emulator (x86_64) | 8-14 | 开发调试 |

### 10.4 性能测试

| 指标 | 目标值 | 测试方法 |
|------|-------|---------|
| **冷启动时间** | < 8 秒 | adb shell am start -W |
| **热启动时间** | < 2 秒 | 从后台恢复计时 |
| **内存占用（空闲）** | < 100 MB | Android Profiler |
| **内存占用（峰值）** | < 250 MB | Android Profiler |
| **页面加载时间** | < 3 秒 | WebView 性能监控 |
| **Excel 导出时间** | < 10 秒（1000 行） | 计时测试 |
| **APK 大小（单架构）** | < 80 MB | 构建产物测量 |

---

## 11. 风险与应对

### 11.1 pandas/numpy ARM 编译风险

| 风险等级 | 描述 | 影响 | 应对措施 |
|---------|------|------|---------|
| 🔴 高 | pandas/numpy 无 Chaquopy 预编译包 | ARM64 设备无法使用 Excel 导入/导出 | 1. 优先使用 Chaquopy 官方预编译包<br>2. 使用较旧稳定版本<br>3. 使用 openpyxl + xlsxwriter 替代 pandas<br>4. 首次启动时下载预编译 wheel |
| 🟡 中 | numpy Fortran 编译失败 | 部分 numpy 函数不可用 | 使用 numpy 的纯 Python 子集 |
| 🟢 低 | Pillow 预编译包版本不匹配 | 图片处理功能受限 | Chaquopy 通常提供 Pillow 预编译包 |

**渐进式应对策略**：

```
Step 1: 尝试 Chaquopy 官方预编译包
  ↓ 失败
Step 2: 尝试指定版本的 wheel 文件
  ↓ 失败
Step 3: 使用 openpyxl + xlsxwriter 替代 pandas 的 Excel 功能
  ↓ 失败
Step 4: 首次启动时从 CDN 下载预编译 wheel
  ↓ 失败
Step 5: 禁用 Excel 导入/导出功能（仅 Android 端）
```

### 11.2 后台进程保活

| 风险等级 | 描述 | 影响 | 应对措施 |
|---------|------|------|---------|
| 🔴 高 | Android 杀死后台 Flask 服务 | 用户切换应用后服务中断 | 1. 使用 Foreground Service + 通知<br>2. 服务重启机制（onTaskRemoved）<br>3. AlarmManager 定时检查服务状态 |
| 🟡 中 | Doze 模式限制后台网络 | MySQL 远程连接中断 | 本地 SQLite 缓存，网络恢复后同步 |
| 🟢 低 | 用户手动杀死应用 | 数据可能未保存 | waitress 优雅关闭 + 数据库 WAL 模式 |

**Foreground Service 实现**：

```kotlin
// FlaskService.kt — 前台服务保活
class FlaskService : Service() {
    private val CHANNEL_ID = "flask_service"
    private val NOTIFICATION_ID = 1
    
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        createNotificationChannel()
        
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("行政后勤管理系统")
            .setContentText("服务运行中")
            .setSmallIcon(R.drawable.ic_notification)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .build()
        startForeground(NOTIFICATION_ID, notification)
        
        Thread {
            val python = Python.getInstance()
            val adapter = python.getModule("android_adapter")
            adapter.callAttr("start_flask_server")
        }.start()
        
        return START_STICKY  // 服务被杀后自动重启
    }
    
    override fun onTaskRemoved(rootIntent: Intent?) {
        // 用户从最近任务中移除应用 → 重启服务
        val restartIntent = Intent(this, FlaskService::class.java)
        val pendingIntent = PendingIntent.getService(
            this, 1, restartIntent,
            PendingIntent.FLAG_ONE_SHOT or PendingIntent.FLAG_IMMUTABLE
        )
        val alarmManager = getSystemService(ALARM_SERVICE) as AlarmManager
        alarmManager.set(AlarmManager.ELAPSED_REALTIME, 1000, pendingIntent)
        super.onTaskRemoved(rootIntent)
    }
    
    override fun onBind(intent: Intent?): IBinder? = null
    
    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID, "Flask 后台服务",
                NotificationManager.IMPORTANCE_LOW
            )
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }
}
```

### 11.3 三端代码冲突风险

| 风险等级 | 描述 | 影响 | 应对措施 |
|---------|------|------|---------|
| 🔴 高 | `is_android()` 误判导致 Windows/Docker 走 Android 分支 | Windows/Docker 功能异常 | 1. `ANDROID_ENV` 仅在 Chaquopy 启动时设置<br>2. `is_android()` 优先检查环境变量<br>3. 三端回归测试覆盖 |
| 🟡 中 | `config.py` 中 `ANDROID_ENV` 分支覆盖 `DOCKER_ENV` | Docker 环境配置错误 | 1. `ANDROID_ENV` 分支在 `DOCKER_ENV` 之前判断<br>2. 两者互斥<br>3. 单元测试覆盖 |
| 🟢 低 | stub 模块在 Windows/Docker 上意外安装 | 导入错误 | 1. `install_stub_modules()` 首先检查 `ANDROID_ENV`<br>2. 仅在 Android 环境下安装<br>3. 启动日志记录 stub 安装状态 |

**代码冲突防护措施**：

```python
# 防护措施1: 环境变量互斥检查
def get_environment() -> str:
    # Android 优先检测（Android 不可能同时是 Docker）
    if SystemDetector.is_android():
        return "android"
    if SystemDetector.is_docker():
        return "docker"
    return SystemDetector.get_os()

# 防护措施2: stub 安装守卫
def install_stub_modules():
    if not os.environ.get('ANDROID_ENV', 'false').lower() == 'true':
        logger.debug("非 Android 环境，跳过 stub 模块安装")
        return  # 安全守卫

# 防护措施3: CI/CD 三端同步验证
# 每次 PR 合并前自动运行三端测试
```

### 11.4 其他风险

| 风险等级 | 描述 | 影响 | 应对措施 |
|---------|------|------|---------|
| 🟡 中 | WebView 安全漏洞 | 中间人攻击 | 1. 仅允许 localhost 连接<br>2. 禁用混合内容<br>3. 定期更新 Android System WebView |
| 🟡 中 | Chaquopy 版本更新不兼容 | 构建失败 | 锁定 Chaquopy 版本，测试后再升级 |
| 🟢 低 | Google Play 政策限制 | 无法上架 | 不上架应用商店，APK 直接分发 |
| 🟢 低 | Android 权限变更 | 新版 Android 需要新权限 | targetSdk 逐步升级，适配新权限模型 |

---

## 12. 实施路线图

### 阶段 1：基础架构搭建（1-2 周）

**目标**：建立 Android 项目骨架，实现 Flask 在 Android 上运行

| 任务 | 交付物 | 验证标准 |
|------|-------|---------|
| 创建 Android 项目目录 | `android/` 目录 | Gradle 构建成功 |
| 配置 Chaquopy | `build.gradle.kts` | Python 运行时可用 |
| 实现 `is_android()` | `system_detector.py` 修改 | Windows/Docker 端测试通过 |
| 实现 `android_adapter.py` | 新文件 | stub 模块安装正常 |
| 修改 `config.py` | ANDROID_ENV 分支 | Windows/Docker 端测试通过 |
| 修改 `main.py` | Android 入口分支 | Windows/Docker 端测试通过 |
| Flask 在 Android 上启动 | APK 可安装运行 | `http://127.0.0.1:35168` 可访问 |

**三端同步验证节点**：
- ✅ Windows 端：客户端模式 + 服务端模式正常启动
- ✅ Docker 端：容器正常启动，端口 35168 可访问
- ✅ Android 端：APK 安装后 Flask 启动，浏览器可访问

### 阶段 2：前端适配（1-2 周）

**目标**：WebView 正确加载 Flask 页面，实现基本交互

| 任务 | 交付物 | 验证标准 |
|------|-------|---------|
| WebView 配置 | `MainActivity.kt` | 页面正常加载 |
| 启动屏实现 | SplashScreen + Lottie | 启动动画流畅 |
| Flask 就绪检测 | 等待逻辑 | 启动屏正确过渡 |
| JS Bridge 基础接口 | `JsBridgeInterface.kt` | JS 可调用原生功能 |
| 响应式布局适配 | CSS 调整 | 移动端布局正常 |
| 文件选择桥接 | `DormWebChromeClient.kt` | 可选择文件上传 |

**三端同步验证节点**：
- ✅ Windows 端：pywebview 窗口正常显示
- ✅ Docker 端：浏览器访问正常
- ✅ Android 端：WebView 加载登录页，可登录

### 阶段 3：功能完善（2-3 周）

**目标**：所有核心功能在 Android 端可用

| 任务 | 交付物 | 验证标准 |
|------|-------|---------|
| 相机拍照桥接 | JS Bridge 扩展 | 拍照上传正常 |
| 数据库路径适配 | `db_config.py` 修改 | SQLite 正常读写 |
| MySQL 远程连接 | 网络权限 + 配置 | MySQL 连接正常 |
| Excel 导入/导出 | pandas/numpy 预编译 | Excel 功能正常 |
| 数据备份/恢复 | 路径适配 | 备份文件正确保存 |
| 后台服务保活 | `FlaskService.kt` | 切换应用后服务不中断 |
| 通知功能 | Android 通知 | 通知正常显示 |

**三端同步验证节点**：
- ✅ Windows 端：所有功能正常（回归测试）
- ✅ Docker 端：所有功能正常（回归测试）
- ✅ Android 端：核心功能可用（功能测试）

### 阶段 4：CI/CD 与打包（1-2 周）

**目标**：三平台同步构建和发布

| 任务 | 交付物 | 验证标准 |
|------|-------|---------|
| `build-android` job | `build.yml` 修改 | GitHub Actions 构建成功 |
| APK 签名配置 | keystore + secrets | Release APK 可安装 |
| 双架构构建 | arm64-v8a + x86_64 | 两种架构 APK 均可运行 |
| Release 发布集成 | 三平台产物 | Release 包含 exe + tar + apk |
| `build-summary` 更新 | 三平台构建结果 | 构建总结包含 Android |
| 包体积优化 | ProGuard + 资源压缩 | APK < 80 MB |

**三端同步验证节点**：
- ✅ Windows 端：`build-windows` job 不受影响
- ✅ Docker 端：`build-docker` job 不受影响
- ✅ Android 端：`build-android` job 构建成功
- ✅ Release：三平台产物完整发布

### 阶段 5：测试与发布（1-2 周）

**目标**：全面测试，准备发布

| 任务 | 交付物 | 验证标准 |
|------|-------|---------|
| 三端回归测试 | 测试报告 | Windows/Docker 功能不受影响 |
| Android 兼容性测试 | 多设备测试报告 | Android 8-14 均可运行 |
| 性能测试 | 性能报告 | 冷启动 < 8s，内存 < 250MB |
| 内存泄漏测试 | LeakCanary 报告 | 无内存泄漏 |
| 文档更新 | README + 部署文档 | 文档包含 Android 安装说明 |
| 首个 Release 发布 | v5.0 Release | 三平台产物完整 |

**三端同步验证节点（最终）**：
- ✅ Windows 端：完整功能测试通过
- ✅ Docker 端：完整功能测试通过
- ✅ Android 端：完整功能测试通过
- ✅ 三平台同步发布 v5.0

---

## 附录

### A. 环境变量汇总

| 环境变量 | Windows | Docker | Android | 说明 |
|---------|---------|--------|---------|------|
| `DOCKER_ENV` | 未设置 | `true` | 未设置 | Docker 环境标识 |
| `ANDROID_ENV` | 未设置 | 未设置 | `true` | Android 环境标识 |
| `USE_DESKTOP_VIEW` | `True` | `False` | `False` | 桌面窗口模式 |
| `SERVER_MODE` | 配置文件决定 | `服务端` | `客户端` | 服务端/客户端模式 |
| `SERVER_HOST` | 配置文件决定 | `0.0.0.0` | `127.0.0.1` | 监听地址 |
| `SERVER_PORT` | 配置文件决定 | `35168` | `35168` | 监听端口 |
| `APP_DATA_DIR` | 未设置 | 未设置 | `getFilesDir()` | 应用数据目录 |

### B. 修改文件清单

| 文件 | 修改类型 | 修改内容 | 影响范围 |
|------|---------|---------|---------|
| `utils/system_detector.py` | 扩展 | 新增 `is_android()` + `get_environment()` 更新 | 不影响现有函数 |
| `utils/android_adapter.py` | **新增** | Android 适配层（stub + 环境配置 + 路径映射） | 仅 Android 使用 |
| `config.py` | 扩展 | 新增 `ANDROID_ENV` 分支 | 不影响现有分支 |
| `main.py` | 扩展 | 新增 Android 入口分支 + 卸载判断 | 不影响现有入口 |
| `utils/db_config.py` | 扩展 | 新增 Android 路径分支 | 不影响现有路径 |
| `android/` | **新增** | Android 原生项目（Kotlin + Gradle + Chaquopy） | 独立目录 |
| `.github/workflows/build.yml` | 扩展 | 新增 `build-android` job + 更新 `build-summary` | 不影响现有 job |

### C. Chaquopy 依赖兼容性矩阵

| Python 包 | 版本 | Chaquopy 预编译 | ARM64 | x86_64 | 备注 |
|-----------|------|----------------|-------|--------|------|
| Flask | 2.3.3 | ✅ | ✅ | ✅ | 纯 Python |
| Flask-SQLAlchemy | 3.1.1 | ✅ | ✅ | ✅ | 纯 Python |
| Flask-WTF | 1.2.1 | ✅ | ✅ | ✅ | 纯 Python |
| Flask-Login | 0.6.3 | ✅ | ✅ | ✅ | 纯 Python |
| Flask-Migrate | 4.0.5 | ✅ | ✅ | ✅ | 纯 Python |
| Jinja2 | 3.1.2 | ✅ | ✅ | ✅ | 纯 Python |
| Werkzeug | 2.3.7 | ✅ | ✅ | ✅ | 纯 Python |
| SQLAlchemy | 2.0.23 | ✅ | ✅ | ✅ | C 扩展可选 |
| openpyxl | 3.1.2 | ✅ | ✅ | ✅ | 纯 Python |
| pandas | 2.0.3 | ⚠️ | ⚠️ | ⚠️ | C 扩展，优先预编译 |
| numpy | 1.24.4 | ⚠️ | ⚠️ | ⚠️ | C + Fortran，优先预编译 |
| Pillow | 10.4.0 | ✅ | ✅ | ✅ | Chaquopy 提供预编译 |
| cryptography | 41.0.7 | ✅ | ✅ | ✅ | Chaquopy 提供预编译 |
| PyMySQL | 1.1.0 | ✅ | ✅ | ✅ | 纯 Python |
| waitress | 2.1.2 | ✅ | ✅ | ✅ | 纯 Python |
| schedule | 1.2.0 | ✅ | ✅ | ✅ | 纯 Python |
| xlsxwriter | 3.2.5 | ✅ | ✅ | ✅ | 纯 Python |
| requests | 2.31.0 | ✅ | ✅ | ✅ | 纯 Python |
| python-dotenv | 1.0.0 | ✅ | ✅ | ✅ | 纯 Python |

> ✅ = 确认可用 | ⚠️ = 需要验证，有备选方案 | ❌ = 不可用

### D. 关键代码片段索引

| 片段 | 位置 | 用途 |
|------|------|------|
| `is_android()` | 第 4.1 节 | Android 平台检测 |
| `install_stub_modules()` | 第 4.3 节 | 桌面依赖 stub 替换 |
| `setup_android_env()` | 第 4.3 节 | Android 环境变量配置 |
| `start_flask_server()` | 第 4.3 节 | Android 端 Flask 启动入口 |
| `config.py ANDROID_ENV` | 第 4.4 节 | 配置分支 |
| `main.py Android 入口` | 第 4.2 节 | 主程序 Android 分支 |
| `WebView 配置` | 第 5.1 节 | WebView 初始化 |
| `JS Bridge` | 第 5.2 节 | 原生功能桥接 |
| `FlaskService` | 第 11.2 节 | 后台服务保活 |
| `build-android job` | 第 8.1 节 | CI/CD 构建 |
```