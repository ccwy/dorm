# 单版本兼容Win7方案分析

## 一、方案核心思路
在现有代码中增加运行时系统版本检测：Win7系统自动以服务端模式启动并禁止切换为客户端，Win10+系统正常启动。从而实现一个打包版本同时兼容Win7和Win10+，消除维护两套构建管线的负担。

## 二、可行性评估
✅ 技术可行，但需权衡依赖版本

有利条件：
1. 所有webview导入均为延迟导入（main.py:413、webview_injector.py:9、process_cleaner.py:133/166），不在模块顶层，Win7上不触发客户端分支即不会导入
2. 服务端模式已证明无webview可正常运行（main.py:380-410整个分支不导入webview）
3. 已有安全跳过先例：process_cleaner.py:163-169的_is_webview_available()已实现try/except ImportError
4. 系统版本检测成本极低：platform.version()或ctypes调用Win32 API即可获取版本号

核心约束：
- 单版本必须用Python 3.8.x构建（最后支持Win7的版本），这意味着所有用户（包括Win10+）都将使用降级依赖

## 三、依赖版本影响

| 包 | 当前主版本 | Win7兼容版本 | 影响 |
|---|---|---|---|
| numpy | >=1.26.3 | ==1.24.4 | 性能和API差异较小 |
| pandas | >=2.3 | ==2.0.3 | 部分新API不可用 |
| Pillow | >=12.0 | ==9.5.0 | 图片处理功能差异 |
| cryptography | >=41.0.7 | ==36.0.2 | 安全更新缺失 |
| psutil | >=7.0.0 | ==5.9.8 | 功能差异小 |
| pywebview | ==3.7 | 保留（Win10+使用） | Win7上不触发导入 |
| pywin32 | 不含 | ==305 | 新增依赖（Win7需win32api） |

结论：Win10+用户将使用较旧的依赖版本，但功能上无实质影响。cryptography降级需关注安全合规。

## 四、需要修改的文件及具体改动

### 1. utils/system_detector.py — 新增版本检测

新增函数：
- is_win7() → bool：检测当前系统是否为Win7/Server 2008 R2
- get_windows_version() → tuple：(major, minor, build)
- is_webview2_available() → bool：检测WebView2运行时是否可用

实现方式：
- platform.version() 解析版本号（简单但可能被兼容模式影响）
- 或 ctypes调用RtlGetVersion（准确，不受兼容模式影响）

### 2. main.py — 模式决策逻辑修改

当前逻辑（第379行起）：
  server_mode = config_data.get("SERVER_MODE", "")
  if server_mode == "服务端" and USE_DESKTOP_VIEW: ...

修改为：
  server_mode = config_data.get("SERVER_MODE", "")
  # Win7强制服务端模式
  if is_win7():
      logging.info("检测到Win7系统，强制使用服务端模式")
      server_mode = "服务端"
  if server_mode == "服务端" and USE_DESKTOP_VIEW: ...

同时：客户端模式分支（第411行起）需增加webview可用性检查：
  elif server_mode == "客户端" and USE_DESKTOP_VIEW:
      if not is_webview2_available():
          logging.warning("WebView2不可用，回退到服务端模式")
          server_mode = "服务端"
          # 走服务端模式逻辑
      else:
          # 正常客户端模式

### 3. utils/server_gui.py — GUI禁用客户端模式

修改点：
- _on_mode_change()：Win7下阻止切换到客户端，弹出提示
- 客户端Radiobutton：Win7下设置state=DISABLED
- _save_config()：Win7下强制SERVER_MODE="服务端"
- 界面提示：Win7下显示"当前系统不支持客户端模式（需要WebView2）"

### 4. blueprints/system_settings.py — API层防护

修改点（仿照Docker环境禁止改服务端的逻辑，第266行）：
- Win7环境下禁止将SERVER_MODE改为"客户端"（返回403）
- 与现有Docker防护逻辑结构一致

### 5. utils/db_config.py — 默认配置适配

修改点（第79行）：
- 当前默认值："SERVER_MODE": "客户端"
- 修改为：根据is_win7()动态决定默认值
- Win7 → "服务端"，其他 → "客户端"

### 6. utils/process_cleaner.py — webview导入安全增强

修改点：
- close_webview()（第133行）：已有_is_webview_available()检查，无需修改
- 但建议在main.py的客户端分支也增加try/except，防止意外ImportError

### 7. utils/webview_injector.py — 无需修改

Win7下不会进入客户端模式，此文件不会被调用。

## 五、打包配置修改

### Auto_Setup/dorm_management.spec — 合并为单spec

修改点：
- hiddenimports：同时包含'webview'和'win32api'/'win32con'
- 不再排除webview（Win10+需要）
- EXE name：恢复为"行政后勤管理系统"（不再区分Win7）
- app_unique_suffix：统一使用"dorm_mgmt_v1.0"

### requirements.txt — 降级为Python 3.8兼容版本

合并requirements_win7.txt的版本约束：
- numpy==1.24.4
- pandas==2.0.3
- Pillow==9.5.0
- cryptography==36.0.2
- psutil==5.9.8
- pywin32==305（新增）
- pywebview==3.7（保留）

### 可废弃的文件

| 文件 | 处理 |
|------|------|
| Auto_Setup/dorm_management_win7.spec | 废弃 |
| Auto_Setup/installer_script_win7.iss | 废弃 |
| Auto_Setup/直接打包成单文件_Win7.bat | 废弃 |
| requirements_win7.txt | 废弃 |
| Auto_Setup/build.yml中Win7相关CI步骤 | 移除 |

## 六、风险分析

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| Python 3.8 EOL（2024.10已停止支持） | 🟡中 | 无安全更新，但Win7本身也已EOL，风险对等 |
| 依赖降级影响Win10+用户体验 | 🟢低 | 降级版本功能完整，仅缺少最新优化 |
| cryptography 36.0.2安全漏洞 | 🟡中 | 关注CVE，必要时手动backport补丁 |
| Win7兼容模式导致版本检测不准 | 🟢低 | 使用RtlGetVersion替代platform.version() |
| pywebview在Win7上import失败 | 🟢低 | 所有导入均为延迟导入+try/except保护 |
| 打包体积增大（同时含webview和pywin32） | 🟢低 | 增加约5-10MB，可接受 |

## 七、推荐方案

推荐采用单版本方案，理由：

1. 代码改动量小：核心修改仅6个文件，每个文件改动5-20行
2. 消除双构建管线：不再维护独立的Win7 spec/iss/requirements/bat文件
3. 运行时安全：webview延迟导入+服务端模式分支已验证无webview可运行
4. 用户体验统一：一个安装包适配所有Windows系统
5. 维护成本降低：bug修复和新功能只需测试一个版本

实施顺序建议：
1. 先在system_detector.py添加版本检测函数
2. 修改main.py添加Win7强制服务端逻辑
3. 修改server_gui.py禁用Win7的客户端选项
4. 修改system_settings.py添加API层防护
5. 修改db_config.py适配默认值
6. 合并spec文件和requirements
7. 在Win7和Win10环境分别测试