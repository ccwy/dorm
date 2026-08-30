# 行政后勤管理系统 Windows 7 专用独立版本可行性开发方案

---

## 一、项目概述

### 1.1 定位说明

本方案描述的是**Win7专用独立版本**，而非主版本的兼容模式。Win7版本是一个独立构建、独立分发的专用版本，与主版本（Win10/Win11）共用业务代码，但运行模式、依赖版本、打包管线完全独立。

**核心定位**：
- 这是一个**专用版本**，不是主版本的兼容补丁
- 不需要检测系统版本、不需要模式切换、不需要WebView2回退逻辑
- Win7版本只有一种运行方式：**Flask + waitress + tkinter GUI + 系统浏览器**
- 与主版本的关系：共用业务代码（blueprints、models、templates、static、utils大部分），独立入口逻辑和构建管线

### 1.2 核心设计原则

| 原则 | 说明 |
|------|------|
| **SERVER_MODE硬编码为"服务端"** | 不支持切换到客户端模式，Win7版本不存在客户端模式概念 |
| **pywebview完全移除** | 不是回退，是根本不存在这个依赖。requirements、spec文件、安装脚本中均不包含pywebview |
| **依赖直接钉死Win7最终兼容版本** | 不需要运行时版本检测，所有依赖版本在构建时确定 |
| **tkinter GUI + 系统浏览器** | 唯一的运行方式，复用现有`utils/server_gui.py`的全部功能 |
| **独立构建管线** | Win7版本有自己的requirements_win7.txt、spec文件、安装脚本，与主版本互不影响 |

### 1.3 与主版本的关系

```
主版本（Win10/Win11）              Win7专用版本
┌─────────────────────┐          ┌─────────────────────┐
│ Python 3.10+        │          │ Python 3.8.18       │
│ pywebview 3.7       │          │ （无pywebview）      │
│ SERVER_MODE可配置    │          │ SERVER_MODE="服务端" │
│ WebView2 / tkinter   │          │ tkinter + 系统浏览器 │
├─────────────────────┤          ├─────────────────────┤
│ blueprints/  ───────┼──共用────┼── blueprints/       │
│ models/     ───────┼──共用────┼── models/            │
│ templates/  ───────┼──共用────┼── templates/         │
│ static/     ───────┼──共用────┼── static/            │
│ utils/(大部分)──────┼──共用────┼── utils/(部分修改)   │
├─────────────────────┤          ├─────────────────────┤
│ main.py（双模式）    │          │ main.py（仅服务端）  │
│ requirements.txt    │          │ requirements_win7.txt│
│ dorm_management.spec│          │ dorm_management_win7.spec│
│ installer_script.iss│          │ installer_script_win7.iss│
└─────────────────────┘          └─────────────────────┘
```

---

## 二、架构设计

### 2.1 Win7版运行架构

```
用户启动程序
    │
    ▼
main.py（硬编码服务端模式）
    │
    ├── 启动 Flask 服务器（waitress 作为 WSGI 服务器）
    │
    ├── 启动 tkinter GUI（utils/server_gui.py）
    │     ├── ServerGUI 类
    │     │   ├── 配置管理（数据库配置、端口配置）
    │     │   ├── 服务启停控制
    │     │   ├── 系统托盘（pystray Icon + Menu）
    │     │   └── 浏览器打开（webbrowser.open()）
    │     └── run_server_gui() 入口函数
    │
    └── 自动打开系统默认浏览器
          └── http://localhost:{SERVER_PORT}
```

### 2.2 与主版本的代码差异对比

| 文件 | 主版本 | Win7版本 | 差异说明 |
|------|--------|---------|---------|
| [`main.py`](main.py) | 双模式启动（第379-481行） | 仅服务端模式启动 | 移除客户端模式分支（第411-481行），硬编码服务端模式 |
| [`utils/db_config.py`](utils/db_config.py) | SERVER_MODE默认"客户端"（第79行） | SERVER_MODE硬编码"服务端" | 不提供模式选择 |
| [`utils/process_cleaner.py`](utils/process_cleaner.py) | 包含webview关闭逻辑（第125-166行） | 移除webview相关代码 | 删除`close_webview()`、`_is_webview_available()`方法 |
| [`utils/webview_injector.py`](utils/webview_injector.py) | 存在 | **删除** | 浏览器模式下不需要JS注入 |
| [`utils/server_gui.py`](utils/server_gui.py) | 服务端模式使用 | **完全复用** | 无需修改 |
| [`Auto_Setup/dorm_management.spec`](Auto_Setup/dorm_management.spec) | 包含webview hiddenimport | 排除webview | 新建Win7专用spec |
| [`Auto_Setup/installer_script.iss`](Auto_Setup/installer_script.iss) | 包含WebView2检测和清理 | 移除WebView2相关 | 新建Win7专用iss |
| [`Auto_Setup/webview2_detection.bat`](Auto_Setup/webview2_detection.bat) | 存在 | **不包含** | Win7版安装包不需要此文件 |
| [`requirements.txt`](requirements.txt) | 包含pywebview==3.7 | 新建requirements_win7.txt | 排除pywebview，钉死兼容版本 |

### 2.3 需要移除的模块

| 模块 | 原因 |
|------|------|
| [`utils/webview_injector.py`](utils/webview_injector.py) | 浏览器模式下无法向系统浏览器注入JS，此模块无意义 |

### 2.4 需要修改的模块

#### [`main.py`](main.py)

**修改内容**：
1. 移除客户端模式分支（第411-481行），包括`import webview`、`webview.create_window()`、`webview.start()`、`start_delayed_injection()`等
2. 将SERVER_MODE硬编码为"服务端"，不再从配置读取
3. 移除对`utils/webview_injector.py`的导入
4. 保留服务端模式分支（第379-410行）作为唯一启动路径

**修改前逻辑**（第379-481行）：
```
server_mode = config_data.get("SERVER_MODE", "")
if server_mode == "服务端" → 服务端模式
elif server_mode == "客户端" → 客户端模式（WebView2）
else → 开发模式
```

**修改后逻辑**：
```
# Win7专用版本：仅服务端模式
启动Flask服务器
启动tkinter GUI（server_gui.py）
等待GUI关闭
退出应用
```

#### [`utils/db_config.py`](utils/db_config.py)

**修改内容**：
- 第79行：`"SERVER_MODE": "客户端"` → `"SERVER_MODE": "服务端"`
- 或者在Win7版本中直接忽略此配置项，由main.py硬编码决定

#### [`utils/process_cleaner.py`](utils/process_cleaner.py)

**修改内容**：
1. 移除`close_webview()`方法（第125-161行）
2. 移除`_is_webview_available()`方法（第163-169行）
3. 移除所有对webview模块的引用
4. 清理`set_resources()`中`webview_ref`参数相关逻辑

### 2.5 不需要修改的模块

| 模块 | 说明 |
|------|------|
| [`utils/server_gui.py`](utils/server_gui.py) | 完全复用，tkinter + pystray + webbrowser全部Win7兼容 |
| [`utils/reload_windows_service.py`](utils/reload_windows_service.py) | 使用ctypes调用Win32 API，不涉及webview |
| [`utils/system_detector.py`](utils/system_detector.py) | Docker检测功能不受影响，Win7版不需要新增系统版本检测 |
| [`utils/auth.py`](utils/auth.py) | 纯Flask认证逻辑，无平台依赖 |
| [`utils/backup.py`](utils/backup.py) | 数据库备份逻辑，无平台依赖 |
| [`utils/db.py`](utils/db.py) | 数据库连接，无平台依赖 |
| 所有blueprints/ | 业务逻辑，无平台依赖 |
| 所有models/ | 数据模型，无平台依赖 |
| 所有templates/ | 前端模板，无平台依赖 |
| 所有static/ | 静态资源，无平台依赖 |

### 2.6 不需要任何系统版本检测代码

Win7版本是专用版本，不需要：
- 检测操作系统版本
- 根据系统版本切换模式
- WebView2可用性检测
- 浏览器回退逻辑

所有这些逻辑属于主版本的兼容方案，不属于Win7专用版本。

---

## 三、依赖适配方案

### 3.1 Python 3.8.18锁定

**目标版本**：Python 3.8.18（Python 3.8系列最终版本）

**锁定原因**：
- Python 3.9+已移除Win7支持，3.8.18是最后支持Win7的版本
- Python 3.8支持walrus operator（:=）、f-strings、dataclasses等，项目代码无需修改
- Python 3.8 EOL为2024年10月，已停止官方支持，但功能稳定

**构建环境**：
- 在Win10/Win11开发机上安装Python 3.8.18
- 使用虚拟环境隔离Win7构建环境
- PyInstaller使用5.13.2（最后稳定支持Python 3.8的版本）

### 3.2 完整的requirements_win7.txt

```
# Win7专用版本依赖清单
# Python 版本：3.8.18（最后支持Win7的版本）
# PyInstaller 版本：5.13.2（最后稳定支持Python 3.8的版本）

# Web 框架（兼容 Python 3.8，版本不变）
Flask==2.3.3
Flask-SQLAlchemy==3.1.1
Flask-WTF==1.2.1
Flask-Login==0.6.3
Flask-Migrate==4.0.5
Werkzeug==2.3.7
Jinja2==3.1.2

# 数据处理（降级至 Python 3.8 兼容版本）
pandas==2.0.3
numpy==1.24.4
openpyxl==3.1.2
xlsxwriter==3.2.5

# 数据库
PyMySQL==1.1.0

# 安全与加密（降级至 Win7 预编译 wheel 版本）
cryptography==36.0.2

# 系统工具（降级至 Win7 兼容版本）
psutil==5.9.8
Pillow==9.5.0
python-dotenv==1.0.0

# 任务调度
schedule==1.2.0

# WSGI 服务器
waitress==2.1.2

# HTTP 请求
requests==2.31.0

# 系统托盘（Win7 兼容）
pystray==0.19.5

# tkinter — Python 3.8 内置，无需安装

# ============================================================
# 注意：pywebview 已完全移除
# Win7专用版本使用 tkinter GUI + 系统浏览器，不需要 WebView2
# ============================================================
```

### 3.3 每个降级依赖的兼容性说明

| 依赖包 | 主版本要求 | Win7锁定版本 | 降级原因 | 兼容性说明 |
|--------|-----------|------------|---------|-----------|
| **Python** | 3.10 | **3.8.18** | 3.9+不支持Win7 | 最后支持Win7的版本，语言特性无损失 |
| **numpy** | >=1.26.3 | **1.24.4** | 1.26+要求Python 3.9+ | 1.24.4是最后支持Python 3.8的版本，API高度兼容，核心数组操作无变化 |
| **pandas** | >=2.3 | **2.0.3** | 2.3+要求Python 3.9+ | 2.0.3是最后支持Python 3.8的版本，DataFrame/Series API稳定，Excel读写功能兼容 |
| **Pillow** | >=12.0 | **9.5.0** | 12+要求Python 3.10+ | 9.5.0是最后支持Python 3.8的版本，项目仅用于加载ICO格式托盘图标，影响极小 |
| **psutil** | >=7.0.0 | **5.9.8** | 确保Win7兼容 | API高度稳定，5.9.8在Win7上经过广泛验证，进程管理功能完全正常 |
| **cryptography** | >=41.0.7 | **36.0.2** | 36+移除Win7预编译wheel | 最后提供Win7预编译wheel的版本，加密功能完整，安全性可接受 |
| **PyInstaller** | 6.x | **5.13.2** | 6.x对Python 3.8支持不稳定 | 最后稳定支持Python 3.8的版本，spec文件语法兼容 |

### 3.4 完全兼容的依赖（无需降级）

| 依赖包 | 版本 | 说明 |
|--------|------|------|
| Flask | 2.3.3 | Flask 2.3支持Python 3.8 |
| Flask-SQLAlchemy | 3.1.1 | 兼容 |
| Flask-Login | 0.6.3 | 兼容 |
| Flask-WTF | 1.2.1 | 兼容 |
| Flask-Migrate | 4.0.5 | 兼容 |
| openpyxl | 3.1.2 | 兼容 |
| waitress | 2.1.2 | 兼容 |
| schedule | 1.2.0 | 兼容 |
| xlsxwriter | 3.2.5 | 兼容 |
| requests | 2.31.0 | 兼容 |
| PyMySQL | 1.1.0 | 兼容 |
| python-dotenv | 1.0.0 | 兼容 |
| pystray | 0.19.5 | Win7可用，使用Win32 API创建系统托盘 |
| tkinter | 内置 | Python 3.8内置，Win7完全可用 |

### 3.5 移除pywebview的影响分析

**移除的依赖**：pywebview==3.7

**影响范围**：

| 影响项 | 说明 | 处理方式 |
|--------|------|---------|
| [`main.py`](main.py) 客户端模式 | 第411-481行使用webview创建窗口 | 整个分支移除 |
| [`utils/webview_injector.py`](utils/webview_injector.py) | 依赖webview模块注入JS | 整个文件删除 |
| [`utils/process_cleaner.py`](utils/process_cleaner.py) | `close_webview()`、`_is_webview_available()` | 移除这两个方法 |
| [`Auto_Setup/dorm_management.spec`](Auto_Setup/dorm_management.spec) | hiddenimports包含'webview' | Win7专用spec中排除 |
| 打包体积 | pywebview及其依赖约30-50MB | Win7版本包体积减小30-50MB |

**不影响的部分**：
- 服务端模式代码（`main.py`第379-410行）不依赖pywebview
- [`utils/server_gui.py`](utils/server_gui.py)不依赖pywebview
- 所有业务逻辑（blueprints、models）不依赖pywebview
- 前端模板和静态资源不依赖pywebview

---

## 四、代码修改方案

### 4.1 main.py修改

**修改范围**：第379-481行

**修改内容**：

1. **移除客户端模式分支**（第411-481行）：
   - 移除`import webview`（第413行）
   - 移除`webview.create_window()`（第431-438行）
   - 移除`webview.start()`（第461行）
   - 移除`from utils.webview_injector import start_delayed_injection`（第449行）
   - 移除`injection_thread = start_delayed_injection()`（第450行）
   - 移除WebView窗口关闭后的资源清理逻辑（第463-481行）

2. **硬编码服务端模式**：
   - 不再从`config_data.get("SERVER_MODE", "")`读取配置
   - 直接执行服务端模式启动逻辑（现有第379-410行代码）
   - 移除`server_mode`变量和条件判断

3. **简化process_cleaner调用**：
   - 移除`webview_ref`参数（Win7版本不存在webview引用）
   - `process_cleaner.set_resources(app=app, server_thread=server_thread)`即可

**修改前**（简化表示）：
```python
server_mode = config_data.get("SERVER_MODE", "")
if server_mode == "服务端" and current_config.USE_DESKTOP_VIEW:
    # 服务端模式逻辑（第379-410行）
elif server_mode == "客户端" and current_config.USE_DESKTOP_VIEW:
    # 客户端模式逻辑（第411-481行）— 移除
else:
    # 开发模式逻辑
```

**修改后**（简化表示）：
```python
# Win7专用版本：仅服务端模式
# 启动Flask服务器
server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()

# 等待服务器启动
time.sleep(1)

# 设置资源引用
process_cleaner.set_resources(app=app, server_thread=server_thread)
process_cleaner.register_signal_handlers()

# 启动服务端GUI
from utils.server_gui import run_server_gui
gui_thread = threading.Thread(target=lambda: run_server_gui(on_exit_callback=None), daemon=False)
gui_thread.start()
gui_thread.join()
```

### 4.2 db_config.py修改

**修改位置**：第79行

**修改内容**：
- `"SERVER_MODE": "客户端"` → `"SERVER_MODE": "服务端"`

**说明**：虽然main.py已硬编码服务端模式，但为保持配置一致性，默认值也应改为"服务端"。

### 4.3 process_cleaner.py修改

**修改范围**：第125-169行

**修改内容**：

1. **移除`close_webview()`方法**（第125-161行）：
   - 此方法通过`import webview`关闭WebView2窗口
   - Win7版本不存在webview模块，此方法无意义

2. **移除`_is_webview_available()`方法**（第163-169行）：
   - 此方法检测webview模块是否可导入
   - Win7版本不存在webview模块，此方法永远返回False

3. **清理`set_resources()`方法**：
   - 移除`webview_ref`参数
   - 移除对`self.webview_ref`的赋值和引用

4. **清理`cleanup_all_resources()`方法**：
   - 移除对`close_webview()`的调用

### 4.4 webview_injector.py：删除

**文件**：[`utils/webview_injector.py`](utils/webview_injector.py)

**删除原因**：
- 此模块的功能是在WebView2窗口中注入JavaScript检查登录状态
- Win7版本使用系统浏览器，无法向外部浏览器注入JavaScript
- 此模块完全依赖`import webview`，Win7版本不存在此依赖

**影响**：
- `main.py`中`from utils.webview_injector import start_delayed_injection`调用需同步移除
- 无其他模块引用此文件

### 4.5 其他需要修改的文件

#### [`config.py`](config.py)

**当前代码**（第66-70行）：
```python
is_docker = os.environ.get('DOCKER_ENV', 'false').lower() == 'true'
if is_docker:
    USE_DESKTOP_VIEW = False
else:
    USE_DESKTOP_VIEW = True
```

**修改**：Win7版本中`USE_DESKTOP_VIEW`始终为`True`（桌面模式），此逻辑无需修改。但如果需要简化，可以硬编码为`True`。

#### [`Auto_Setup/dorm_management.spec`](Auto_Setup/dorm_management.spec)

**修改**：不修改此文件，而是创建Win7专用spec文件（见第六节）。

---

## 五、前端兼容性

### 5.1 Tailwind CSS Play CDN兼容性

项目前端通过[`templates/static.html`](templates/static.html)加载核心依赖，使用Tailwind CSS 3.4.17 Play CDN模式（本地文件`static/js/3.4.17.js`）。

**Play CDN核心API兼容性**：

| API | 用途 | Chrome 109 | Firefox 115 ESR |
|-----|------|-----------|----------------|
| Proxy | 响应式对象代理 | ✅ Chrome 49+ | ✅ Firefox 18+ |
| WeakMap | 样式缓存 | ✅ Chrome 51+ | ✅ Firefox 38+ |
| MutationObserver | DOM变动监听 | ✅ Chrome 26+ | ✅ Firefox 14+ |
| CSS Custom Properties | CSS变量 | ✅ Chrome 49+ | ✅ Firefox 31+ |
| CSS.supports() | 特性检测 | ✅ Chrome 28+ | ✅ Firefox 22+ |
| Promise | 异步操作 | ✅ Chrome 33+ | ✅ Firefox 29+ |

**Tailwind CSS Play CDN功能支持**：

| 功能 | Chrome 109 | Firefox 115 ESR |
|------|-----------|----------------|
| JIT编译器 | ✅ | ✅ |
| tailwind.config | ✅ | ✅ |
| @apply | ✅ | ✅ |
| 自定义变体 | ✅ | ✅ |
| 插件系统 | ✅ | ✅ |
| 暗色模式 | ✅ | ✅ |

**结论**：Chrome 109和Firefox 115 ESR完全支持Tailwind CSS Play CDN的全部功能。

### 5.2 其他前端依赖兼容性

| 依赖 | 版本 | Chrome 109 | Firefox 115 ESR |
|------|------|-----------|----------------|
| jQuery | 3.6.0 | ✅ 最低Chrome 49+ | ✅ 最低Firefox 52+ |
| Font Awesome | 4.7.0 | ✅ 纯CSS+字体 | ✅ 纯CSS+字体 |

### 5.3 不需要IE11兼容

IE11缺乏Proxy、WeakMap、MutationObserver等基础API，Tailwind CSS Play CDN脚本无法执行。Win7版本明确不支持IE11，不需要任何IE11适配工作。

### 5.4 浏览器最低版本要求

| 浏览器 | 最低要求 | Win7最后可用版本 | 状态 |
|--------|---------|----------------|------|
| Google Chrome | 49+ | 109（2023年2月停止更新） | ✅ 推荐 |
| Mozilla Firefox | 52+ | 115 ESR（2023年8月停止更新） | ✅ 推荐 |
| Internet Explorer | - | 11 | ❌ 不支持 |

**说明**：Chrome 109和Firefox 115 ESR虽已停止更新，但对现代Web标准的支持足以运行本项目全部前端功能。

---

## 六、打包与安装

### 6.1 Win7专用spec文件设计

创建`Auto_Setup/dorm_management_win7.spec`，基于现有[`dorm_management.spec`](Auto_Setup/dorm_management.spec)修改：

**与主版本spec的关键差异**：

| 配置项 | 主版本spec | Win7专用spec |
|--------|-----------|-------------|
| Python环境 | 3.10 | 3.8.18 |
| hiddenimports | 包含`'webview'` | **排除**`'webview'`、`'pywebview'` |
| excludes | 无 | 添加`'webview'`、`'pywebview'` |
| numpy | 1.26+ | 1.24.4 |
| pandas | 2.3+ | 2.0.3 |
| Pillow | 12+ | 9.5.0 |
| cryptography | 41+ | 36.0.2 |
| psutil | 7+ | 5.9.8 |
| 打包体积 | 较大（含pywebview约30-50MB） | 较小（排除pywebview） |

**排除pywebview的方法**：
- 在spec文件的`excludes`列表中添加`'webview'`、`'pywebview'`
- 从`hiddenimports`中移除`'webview'`
- 这将显著减小Win7版本的打包体积

### 6.2 Inno Setup脚本修改

创建`Auto_Setup/installer_script_win7.iss`，基于现有[`installer_script.iss`](Auto_Setup/installer_script.iss)修改：

**关键修改**：

**1. 移除WebView2相关内容**：
- 移除`[Components]`中的`webview2`组件定义（第31行）
- 移除`[Files]`中的`webview2_detection.bat`（第37行）
- 移除`[Tasks]`中的`checkwebview2`任务（第62行）
- 移除`[Code]`中的WebView2检测逻辑（第92-116行）
- 移除`[UninstallDelete]`中的WebView2缓存清理（第136-149行）

**2. 添加运行时依赖检测**：

| 依赖 | 检测方式 | 处理方式 |
|------|---------|---------|
| **VC++ Redistributable 2015-2022** | 检测注册表`HKLM\SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\X64`（或X86） | 缺失则自动安装（打包vcredist_x64.exe / vcredist_x86.exe） |
| **KB2999226补丁** | 检测已安装更新列表 | 缺失则提示安装（提供离线安装包或下载链接） |

**3. 添加浏览器可用性检测**：
- 检测Chrome安装路径：`%ProgramFiles%\Google\Chrome\Application\chrome.exe`
- 检测Firefox安装路径：`%ProgramFiles%\Mozilla Firefox\firefox.exe`
- 若均未检测到，显示提示："建议安装Chrome或Firefox浏览器以获得最佳体验"
- 提供"继续安装"选项（不强制阻止安装）

**4. 安装界面提示**：
- 安装完成页面显示："本系统使用系统浏览器运行，请确保已安装Chrome或Firefox浏览器"

**5. 安装包命名**：
- 输出文件名：`行政后勤管理系统_Win7_Setup_v1.0.exe`
- 与主版本安装包区分

### 6.3 运行时依赖

| 依赖 | 说明 | 处理方式 |
|------|------|---------|
| **Visual C++ Redistributable 2015-2022** | Python 3.8运行时依赖 | 安装程序自动检测并安装 |
| **Universal C Runtime（KB2999226）** | Python 3.8在Win7上的必要补丁 | 安装程序检测，缺失则提示安装 |
| **Chrome 109+ 或 Firefox 115 ESR** | 浏览器模式必需 | 安装程序检测，缺失则提示安装 |

**KB2999226补丁说明**：
- 此补丁为Win7提供Universal C Runtime支持，Python 3.8运行必需
- Win7 SP1通常已通过Windows Update安装此补丁
- 若未安装，Python程序启动时报错"api-ms-win-crt-xxx.dll缺失"
- 建议在安装程序中检测并提供离线安装包

### 6.4 打包体积对比

| 项目 | 主版本 | Win7版本 | 差异 |
|------|--------|---------|------|
| pywebview及依赖 | ~30-50MB | 0MB | -30~50MB |
| numpy | 1.26+ | 1.24.4 | 略小 |
| pandas | 2.3+ | 2.0.3 | 略小 |
| Pillow | 12+ | 9.5.0 | 略小 |
| cryptography | 41+ | 36.0.2 | 略小 |
| **总体** | 较大 | 减少约30-50MB | 主要来自排除pywebview |

---

## 七、测试验证

### 7.1 测试环境

| 环境 | 操作系统 | 位数 | 说明 |
|------|---------|------|------|
| 环境1 | Windows 7 SP1 | 64位 | 主要测试环境 |
| 环境2 | Windows 7 SP1 | 32位 | 需验证32位兼容性 |
| 环境3 | Windows 10 | 64位 | 回归测试，确保主版本不受影响 |

### 7.2 功能测试清单

| 类别 | 测试项 | 验证内容 |
|------|--------|---------|
| **启动** | 程序启动 | Flask服务器正常启动，tkinter GUI正常显示 |
| **启动** | 浏览器自动打开 | webbrowser.open()成功打开系统默认浏览器 |
| **启动** | 系统托盘 | pystray托盘图标正常显示，右键菜单可用 |
| **GUI** | 配置管理 | 数据库配置、端口配置可正常修改 |
| **GUI** | 服务启停 | 启动/停止服务按钮正常工作 |
| **GUI** | 浏览器打开 | "打开浏览器"按钮正常工作 |
| **核心** | 数据库操作 | SQLite/MySQL连接、CRUD操作正常 |
| **核心** | 导入导出 | Excel导入导出（pandas 2.0.3 + openpyxl）正常 |
| **核心** | 用户认证 | 登录、登出、权限控制正常 |
| **核心** | 数据备份 | 自动备份、手动备份正常 |
| **前端** | Tailwind CSS | 页面样式正常渲染 |
| **前端** | jQuery交互 | AJAX请求、DOM操作正常 |
| **前端** | Font Awesome | 图标正常显示 |
| **进程** | 正常退出 | GUI关闭后进程完全退出 |
| **进程** | 异常退出 | 服务线程被正确清理 |
| **安装** | 全新安装 | 安装程序正常运行，VC++检测正常 |
| **安装** | 升级安装 | 覆盖安装正常，数据保留 |

### 7.3 回归测试

确保主版本（Win10/Win11）不受Win7版本代码修改的影响：

| 测试项 | 验证内容 |
|--------|---------|
| 主版本客户端模式 | WebView2窗口正常启动和运行 |
| 主版本服务端模式 | tkinter GUI + 浏览器模式正常 |
| 主版本打包 | 现有spec文件和iss脚本正常工作 |
| 主版本安装 | 安装程序WebView2检测正常 |

**关键**：Win7版本的代码修改通过独立文件（requirements_win7.txt、spec、iss）和条件分支实现，主版本的代码路径不受影响。

---

## 八、风险评估

### 8.1 高风险项

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| **pandas 2.0.3与2.3的API差异** | Excel导入导出功能可能出错 | 中 | 详细测试所有Excel操作；pandas 2.0→2.3 API变化较小，主要影响废弃API |
| **cryptography 36.0.2的安全性** | 使用较旧版本的加密库 | 低 | 36.x仍修复关键安全漏洞；评估安全风险可接受 |
| **Win7已停止官方支持** | 系统安全风险、用户环境不可控 | 高 | 明确告知用户风险；建议升级系统；Win7版本可设定支持终止日期 |

### 8.2 中风险项

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| **浏览器模式用户体验差异** | 无内嵌窗口，浏览器与GUI分离 | 高 | 优化tkinter GUI信息展示；自动打开浏览器；添加使用说明 |
| **numpy 1.24.4与1.26的API差异** | 数组操作可能出错 | 低 | numpy小版本间API高度兼容；全面测试导入导出功能 |
| **PyInstaller 5.13.2与6.x的差异** | 打包配置可能需调整 | 中 | spec文件语法基本兼容；需测试打包结果 |

### 8.3 低风险项

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| **Pillow 9.5.0与12.0的差异** | 图像处理功能受限 | 低 | 项目仅用于托盘图标加载（ICO格式），影响极小 |
| **psutil版本降级** | 进程管理功能 | 低 | psutil API高度稳定，5.9.8广泛验证 |
| **tkinter在Win7上的字体渲染** | 中文字体显示 | 低 | tkinter使用Win32原生控件，SimHei字体在Win7上可用 |
| **pystray在Win7上的托盘图标** | 系统托盘功能 | 低 | pystray使用Shell_NotifyIcon Win32 API，Win7原生支持 |

---

## 九、工作量估算

| 阶段 | 工作内容 | 预计工时 | 关键产出 |
|------|---------|---------|---------|
| **阶段一** | 环境与依赖适配 | 2-3天 | `requirements_win7.txt`、Python 3.8构建环境 |
| **阶段二** | 代码修改 | 2-3天 | main.py、db_config.py、process_cleaner.py修改，webview_injector.py删除 |
| **阶段三** | 打包与安装程序适配 | 2-3天 | Win7专用spec文件、Inno Setup脚本 |
| **阶段四** | 测试验证 | 3-5天 | Win7 SP1 32/64位测试报告、主版本回归测试 |
| **合计** | | **9-14天** | |

### 阶段详细说明

**阶段一：环境与依赖适配（2-3天）**
- 安装Python 3.8.18构建环境
- 创建`requirements_win7.txt`
- 验证所有降级依赖可正常安装
- 运行现有测试确保功能正常
- 安装PyInstaller 5.13.2并验证打包

**阶段二：代码修改（2-3天）**
- 修改`main.py`：移除客户端模式分支，硬编码服务端模式
- 修改`utils/db_config.py`：SERVER_MODE默认值改为"服务端"
- 修改`utils/process_cleaner.py`：移除webview相关方法
- 删除`utils/webview_injector.py`
- 验证修改后的代码在Python 3.8环境下正常运行

**阶段三：打包与安装程序适配（2-3天）**
- 创建`Auto_Setup/dorm_management_win7.spec`
- 创建`Auto_Setup/installer_script_win7.iss`
- 集成VC++ Redist和KB2999226检测
- 集成浏览器可用性检测
- 测试打包和安装流程

**阶段四：测试验证（3-5天）**
- Win7 SP1 64位干净环境安装测试
- Win7 SP1 32位干净环境安装测试
- 核心功能测试：数据库、导入导出、系统托盘、进程清理
- 主版本回归测试（确保不影响Win10/Win11版本）

---

## 十、结论

### 可行性结论：**可行，Win7专用独立版本是最佳方案**

Win7专用独立版本在技术上是完全可行的。核心策略是**硬编码服务端模式**——复用现有[`utils/server_gui.py`](utils/server_gui.py)的全部功能，以tkinter GUI + 系统浏览器作为唯一运行方式。

**方案核心优势**：

1. **架构最简**：不需要系统版本检测、不需要模式切换、不需要WebView2回退逻辑，代码路径单一清晰
2. **改动最小**：仅需移除客户端模式代码和webview依赖，核心业务代码零修改
3. **完全复用**：[`utils/server_gui.py`](utils/server_gui.py)的全部功能（tkinter GUI、pystray系统托盘、webbrowser打开浏览器）在Win7上完全可用
4. **前端兼容**：Tailwind CSS 3.4.17 Play CDN在Chrome 109和Firefox 115 ESR上完全正常运行
5. **包体积减小**：排除pywebview，减少约30-50MB
6. **独立维护**：Win7版本有自己的requirements、spec文件、安装脚本，与主版本互不影响

**与兼容性方案的关键区别**：

| 对比项 | 兼容性方案 | 专用独立版本方案 |
|--------|-----------|----------------|
| 系统版本检测 | 需要 | 不需要 |
| 模式切换逻辑 | 需要 | 不需要 |
| WebView2回退 | 需要 | 不存在 |
| 代码复杂度 | 较高（多分支） | 最低（单路径） |
| 维护成本 | 较高（需同步维护兼容逻辑） | 较低（独立管线） |
| 主版本影响 | 有（需修改主版本代码） | 无（独立文件） |

**主要工作量**：
1. **依赖版本降级**（机械性工作，风险可控，2-3天）
2. **代码修改**（移除客户端模式、删除webview依赖，2-3天）
3. **打包配置适配**（新建Win7专用spec和iss，2-3天）
4. **测试验证**（3-5天）

### 建议

1. **推荐采用Win7专用独立版本方案**，这是最简洁、最安全、维护成本最低的方案
2. **明确Win7浏览器要求**：必须安装Chrome 109+或Firefox 115 ESR，不支持IE11
3. **明确告知Win7用户**：系统已停止官方支持，建议升级至Win10/11
4. **设定Win7版本支持终止日期**（如2027年底），届时停止维护
5. **考虑打包离线浏览器安装包**：Chrome/Firefox离线安装包可随安装程序分发，降低用户安装门槛