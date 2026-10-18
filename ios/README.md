# 宿舍管理系统 iOS 客户端

iOS 原生壳应用，通过 WKWebView 加载本地 Flask 服务器（127.0.0.1:35168）提供的宿舍管理系统页面。架构与 Android 客户端完全对称：Swift 壳负责 UI 与生命周期，Python 运行时（由 kivy-ios 编译的 Python.framework 提供）在后台运行 Flask + waitress 服务器。

## 最低系统要求

- iOS 12.0+
- 纯 UIKit 实现（无 SwiftUI、无 SceneDelegate）
- Xcode 10.2+ / Swift 5.0

## 项目结构

```
ios/
├── DormManagement/               # 应用源码
│   ├── AppDelegate.swift         # 应用生命周期、窗口创建
│   ├── ViewController.swift      # WKWebView 容器、进度轮询、下载/上传处理
│   ├── PythonBridge.swift        # Python C API 桥接（dlopen + 函数指针）
│   ├── LoadingView.swift         # 启动加载页（图标脉冲 + 进度条）
│   ├── ErrorView.swift           # 错误页（重试按钮）
│   ├── Info.plist                # 应用配置（ATS、权限、方向）
│   ├── LaunchScreen.storyboard   # 启动屏
│   └── Assets.xcassets/          # 图标资源（AppIcon 占位）
├── DormManagement.xcodeproj/     # Xcode 工程文件
├── build_python_framework.sh     # kivy-ios 工具链构建脚本
└── Frameworks/                   # Python.framework 存放目录（构建后生成）
```

## 工作原理

1. 启动时 `PythonBridge` 通过 `dlopen` 加载 Python.framework
2. 注入 `IOS_ENV`、`IOS_DOCUMENT_DIR` 环境变量并初始化 Python 解释器
3. 调用 `utils/ios_adapter.py` 中的 `start_flask_server()` 在后台线程启动 Flask
4. Swift 端以 0.5s 间隔轮询 `get_progress()` 获取启动进度
5. HTTP 探测 `/login` 返回 200（服务就绪）后 WKWebView 加载 `http://127.0.0.1:35168`
6. 服务器最大等待时间 300 秒，超时显示错误页

## 本地构建

### 1. 构建 Python.framework

```bash
cd ios
./build_python_framework.sh
```

脚本会自动完成：
- 检查 macOS / Xcode / kivy-ios 环境
- 用 kivy-ios toolchain 编译 python3、cryptography、Pillow
- 生成 Python.framework 并复制到 `ios/Frameworks/`
- 安装纯 Python 依赖（flask、waitress、sqlalchemy 等）到 site-packages

> 首次构建约需 1-2 小时，占用约 10GB 磁盘空间。

### 2. 打开 Xcode 工程

```bash
open ios/DormManagement.xcodeproj
```

### 3. 配置签名

- 在 Xcode → Signing & Capabilities 中选择你的开发者团队
- 或将 `DEVELOPMENT_TEAM` 留空使用自动签名

### 4. 构建

- 选择目标设备或模拟器
- `Cmd+R` 运行

> 注意：Python.framework 仅包含真机架构时，模拟器运行会失败。如需模拟器调试，构建脚本已包含 x86_64 架构。

## GitHub Actions 自动构建

项目支持通过 GitHub Actions 自动构建 IPA。工作流文件位于 `.github/workflows/build.yml`（build-ios job），触发条件为推送 tag `v*`、push 到 main/master 分支，或手动触发 workflow_dispatch。

工作流步骤：
1. 在 macOS runner 上安装 kivy-ios
2. 执行 `build_python_framework.sh`
3. 用 xcodebuild 构建 archive（无签名）
4. 导出未签名 IPA 并上传为 artifact

## 自签名安装（无需付费开发者账号）

### Sideloadly（推荐）

1. 从 [sideloadly.io](https://sideloadly.io) 下载安装
2. 用数据线连接 iPhone 到电脑
3. 打开 Sideloadly，拖入 IPA 文件
4. 输入 Apple ID 进行侧载
5. 在 iPhone 上信任开发者：设置 → 通用 → VPN与设备管理

> 免费账号签名有效期 7 天，到期后需重新侧载。

### AltStore

1. 在电脑上安装 AltServer
2. iPhone 通过 AltStore 安装应用
3. AltStore 会自动续期（需同一 WiFi 下电脑开机）

## AppIcon 图标

`Assets.xcassets/AppIcon.appiconset/` 当前为空占位。生成图标：

```bash
cd android
python generate_icons.py   # 复用 Android 图标生成脚本产出 PNG
```

将产出的图标 PNG 按尺寸放入 appiconset 并在 Contents.json 中登记，或直接在 Xcode 的 Asset Catalog 中拖入 1024x1024 图标自动生成。

## 常见问题

**Q: 构建时报 "Python.framework not found"？**
A: 先运行 `build_python_framework.sh`，确认 `ios/Frameworks/Python.framework` 存在。

**Q: 模拟器启动白屏？**
A: Python.framework 需包含 x86_64 架构。重新运行构建脚本并确认 ARCHS 配置。

**Q: 真机运行闪退？**
A: 检查签名是否有效，以及 iOS 版本是否 >= 12.0。

**Q: 文件上传按钮无反应？**
A: iOS 14+ 支持 WKUIDelegate 文件选择器；iOS 12/13 不支持原生上传，需通过其他方式（如剪贴板）。