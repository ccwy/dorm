# Asset Agent 技术方案设计文档

> **第十一次修订** | 唯一性+采集+打包集成优化 | 双向同步：✅ 已设计 | 编辑配置脚本：✅ 已设计 | API 端点：19 个 | 客户端：C语言 + Win32 API + cJSON
>
> **第十一次修订变更摘要**：
> - 新增：§6.5 Agent 全局设置页面（/agent_manage/settings），集中管理所有 agent_config 配置项
> - 新增：§4.3.9 配置端点扩展，GET/PUT /api/agent/config 支持全部10个 agent_config 配置项
> - 修改：§6.3 Agent 管理页面增加"全局设置"链接入口
> - 修改：PUT /api/agent/config 不再处理 agent_enabled，统一由 POST /api/agent/toggle 管理
>
> **第十次修订变更摘要**：
> - 新增：`logged_in_user` 采集项（GetUserNameW / WTSQuerySessionInformationW）
> - 新增：设备指纹（SHA-256硬件绑定哈希）+ UUID（服务端分配v4）
> - 新增：注册端点三级查重策略（device_fingerprint → hostname+mac → mac_address）
> - 新增：心跳端点 UUID 校验（防止 agent_id 伪造）
> - 新增：GitHub Actions CI/CD + Docker集成 + 安卓端方案
> - 新增：`collect_user.c` / `fingerprint.c` 采集模块

### 前端页面（3个）：
- Agent管理页面（/agent_manage/）：全局开关、服务器配置、API Key管理、下载区、设备概览
- Agent全局设置页面（/agent_manage/settings）：心跳参数、日志设置、远程控制、迁移配置、下载注入配置
- 固定资产详情页设备信息卡片

## 1. 概述

### 1.1 项目背景

行政后勤管理系统（dorm）是一个基于 Flask 的综合管理系统，包含固定资产管理模块。当前固定资产管理仅支持手工录入和静态管理，无法实时获取设备的实际运行状态和基础信息。为提升固定资产管理的自动化水平，需要设计一个轻量级客户端程序（Asset Agent），部署在被管理的计算机上，实时采集并上报设备基础信息和在线状态。

### 1.2 设计目标

- **无感运行**：客户端完全隐藏运行，无窗口、无系统托盘图标、不可见，最小化资源占用（内存 < 10MB，CPU 空闲时接近 0%）
- **一键即用**：用户下载时自动注入服务器地址和 API Key 配置，解压后双击运行即可，无需任何手动配置
- **自动化采集**：自动采集计算机的主机名、操作系统、CPU、内存、磁盘、MAC地址、IP地址等基础信息
- **实时在线监控**：通过心跳机制定时上报在线状态，使管理人员可实时掌握设备在线情况
- **资产关联**：通过资产编号将设备信息与系统中的固定资产记录关联
- **项目内分发**：从固定资产管理前端页面直接下载已注入配置的客户端（exe + config.json 打包为 zip）
- **集中管理**：提供 Web 管理页面集中管理 Agent 系统的开关、配置、API Key 和下载，方便运维人员一站式操作

#### 语言选择说明

本项目选择 **C语言 + Win32 API + cJSON** 作为客户端实现语言，主要基于以下兼容性和可靠性考虑：

| 语言 | XP支持 | Win7+支持 | 单二进制 | 内存占用 | 推荐度 |
|------|--------|-----------|----------|----------|--------|
| C (Win32 API) | ✅ 原生支持 | ✅ 支持 | ✅ 静态链接 | 1~3 MB | ⭐推荐 |
| Go 1.20 | ⚠️ 部分兼容 | ✅ 支持 | ✅ | 10~15 MB | 不推荐（已EOL） |
| Go 1.21+ | ❌ 不支持 | ✅ 支持(64位) | ✅ | 10~15 MB | 不推荐 |
| Rust | ❌ 不支持 | ✅ 支持 | ✅ | 3~5 MB | 不推荐 |

选择 C + Win32 API 的理由：
- **Go 1.20 已 EOL**：Go 1.20 于 2024 年 2 月停止官方支持，不再接收安全补丁，存在长期维护风险
- **XP 原生兼容**：Win32 API 从 Windows 2000 起就稳定支持，无需任何兼容层或 workaround
- **零外部依赖**：Win32 API 和 WinINet 均为操作系统自带组件，cJSON 为单文件嵌入库，无第三方运行时
- **极低资源占用**：无运行时（Go runtime 约 10MB），静态链接后二进制 1~3MB，内存占用 1~3MB
- **TLS 兼容**：WinINet 使用系统 IE/Windows 的 TLS 栈，XP SP3 支持 TLS 1.0/1.1，Win7+ 完整支持 TLS 1.2

C/Win32 API XP 兼容性说明：
- Win32 API 从 Windows 2000 起就稳定支持，所有系统信息采集 API 均原生可用
- WinINet 从 IE5 起自带（XP SP2+ 完整支持），提供 HTTP/HTTPS 通信能力
- `GetVersionEx` 在 Win8.1+ 需要应用清单声明，但 `RtlGetVersion`（ntdll.dll 导出）可替代
- `GetAdaptersInfo` 在 XP 上原生支持，`GetAdaptersAddresses` 在 XP SP1+ 支持
- cJSON 无系统依赖，纯 ANSI C 实现，~500行代码直接嵌入源码
- 编译：MSVC (VS2019+) 或 MinGW-w64，静态链接 CRT（`/MT`）确保零运行时依赖

### 1.3 整体架构

```
┌─────────────────┐     HTTP/API      ┌─────────────────────┐     读写      ┌──────────┐
│  Asset Agent    │ ──────────────────>│  Flask Server       │ ───────────> │  SQLite   │
│  (C 客户端)     │ <──────────────────│  (新增API端点)      │ <─────────── │  / MySQL  │
│  隐藏后台进程    │    JSON Response   │  /api/agent/*      │              └──────────┘
│  运行在被管理PC  │                    └─────────────────────┘
└─────────────────┘                              │
                                                 │ 读取 + 下载分发 + 管理
                                                 v
                                          ┌─────────────────────┐
                                          │  固定资产管理前端     │
                                          │  (展示在线状态)       │
                                          │  (下载Agent按钮)     │
                                          └─────────────────────┘
```

**数据流**：
1. Asset Agent 启动时采集设备基础信息，首次上报发送完整信息
2. 之后按心跳间隔（默认120秒）定时发送心跳包
3. 服务端收到心跳后更新设备在线状态和最后心跳时间
4. 前端通过现有固定资产API获取设备在线状态并展示
5. Agent管理页面提供全局开关、配置管理、API Key管理和客户端下载
6. 固定资产详情页（电脑类别）提供资产关联客户端下载按钮

---

## 2. 系统架构设计

### 2.1 组件关系

| 组件 | 技术栈 | 职责 |
|------|--------|------|
| Asset Agent | C (Win32 API + WinINet + cJSON) | 采集设备信息、发送心跳、隐藏后台进程运行 |
| Flask API | Python/Flask (新增 Blueprint) | 接收Agent上报、管理API Key、提供状态查询、提供下载 |
| 数据库 | SQLAlchemy (SQLite/MySQL) | 存储设备信息、心跳记录、API Key |
| 前端 | Jinja2 + JavaScript | 展示设备在线状态和基础信息、提供Agent下载入口 |
| Agent管理页面 | Jinja2 + Bootstrap + JavaScript | 集中管理Agent系统开关、配置、API Key、下载和设备状态概览 |
| 打包集成 | C编译(MSVC/MinGW) + Inno Setup + 脚本 | 编译通用Agent二进制、打包进安装程序 |

### 2.2 数据流详图

```
Agent启动 ──> 采集设备信息 ──> 发送注册请求(/api/agent/register) ──> 服务端创建/更新设备记录
    │                                                              │
    │                                                              v
    │                                                    关联固定资产(如提供asset_number)
    │                                                              │
    v                                                              v
定时心跳(120s) ──> 发送心跳(/api/agent/heartbeat) ──> 服务端更新last_heartbeat_at和status
    │                                                              │
    │                                                              v
设备信息变更 ──> 发送信息更新(/api/agent/report)  ──> 服务端更新设备信息字段
                                                                    │
                                                                    v
                                                           前端查询固定资产列表
                                                                    │
                                                                    v
                                                           JOIN设备表获取在线状态
```

### 2.3 下载分发流程

Agent 客户端支持两种下载模式，分别面向不同使用场景：

#### 2.3.1 通用客户端下载（Agent管理页面）

适用于批量分发场景，下载的客户端不关联具体固定资产，用户安装后需手动关联。

```
管理员访问 Agent管理页面
          │
          v
点击"下载通用客户端"按钮
          │
          v
GET /api/agent/download ──> Flask路由动态打包
          │                    1. 使用管理页面配置的 server_url 和 api_key
          │                       （用户可在管理页面修改注入的值）
          │                    2. 生成 config.json（不含 asset_number）
          │                    3. 将 exe + config.json 打包成 zip
          │                    4. 返回 zip 下载
          v
用户解压得到 asset-agent.exe + config.json
          │
          v
双击运行 asset-agent.exe
          │
          ├── 同目录有 config.json ──> 自动读取配置 ──> 进入隐藏后台模式
          │
          └── 无 config.json ──> 弹出配置窗口 ──> 用户输入服务器地址和API Key ──> 保存并进入隐藏后台模式
          │
          v
用户在客户端通过 --edit-info 或客户端UI手动关联固定资产
```

#### 2.3.2 资产关联客户端下载（固定资产详情页）

适用于单台设备部署场景，下载的客户端自动关联到指定固定资产。

```
管理员查看固定资产详情页（资产类别为"电脑"）
          │
          v
点击"下载客户端"按钮
          │
          v
GET /api/agent/download/<asset_number> ──> Flask路由动态打包
           │                                       1. 使用管理页面配置的 server_url 和 api_key
           │                                       2. 从固定资产记录中读取 location/department/responsible_person
           │                                       3. 生成 config.json（含 asset_number + location + department + responsible_person）
           │                                       4. 将 exe + config.json 打包成 zip
           │                                       5. 返回 zip 下载
           v
用户解压得到 asset-agent.exe + config.json（含 asset_number + 手动字段）
           │
           v
双击运行 asset-agent.exe
           │
           v
自动读取配置（含 asset_number + 手动字段）──> 注册时自动关联到该固定资产 ──> 进入隐藏后台模式
```

**两种模式对比**：

| 对比项 | 通用客户端下载 | 资产关联客户端下载 |
|--------|---------------|-------------------|
| 入口 | Agent管理页面 | 固定资产详情页（电脑类别） |
| API | `GET /api/agent/download` | `GET /api/agent/download/<asset_number>` |
| config.json | 不含 asset_number | 含 asset_number + location + department + responsible_person |
| 关联方式 | 安装后手动关联 | 自动关联 |
| 适用场景 | 批量分发、预先部署 | 单台设备精确部署 |

---

## 3. C 客户端设计

### 3.1 功能模块

```
asset-agent/
├── main.c               # 入口，WinMain + ShowWindow(SW_HIDE) 隐藏窗口
├── config.c             # 配置管理（读取本地配置文件，支持多路径查找）
├── config.h             # 配置结构体与接口声明
├── collector.c          # 系统信息采集（Win32 API）
├── collector.h          # 采集接口声明
├── collect_user.c       # 登录用户名采集（GetUserNameW / WTSQuerySessionInformationW）
├── collect_user.h       # 登录用户名采集接口声明
├── fingerprint.c        # 设备指纹生成（SHA-256硬件绑定哈希）
├── fingerprint.h        # 设备指纹接口声明
├── reporter.c           # 上报逻辑（注册、心跳、信息更新）
├── reporter.h           # 上报接口声明
├── service.c            # Agent主循环（心跳调度、离线恢复）
├── service.h            # 服务接口声明
├── autostart.c          # 注册表自启动管理（RegOpenKeyEx等）
├── autostart.h          # 自启动接口声明
├── setup_ui.c           # 首次运行配置窗口（无配置文件时的兜底）
├── cli.c                # CLI命令处理（stop/uninstall/edit-info）
├── ipc.c                # 进程间通信（CreateFile/WriteFile命名管道）
├── ipc.h                # IPC接口声明
├── info_ui.c            # 手动信息编辑窗口（存放位置/部门/责任人）
├── cJSON.c              # cJSON库（单文件嵌入，约500行）
├── cJSON.h              # cJSON头文件
├── Makefile             # MinGW-w64 构建脚本
└── resource.rc          # Windows资源文件（图标、版本信息）
```

采集模块说明：
- **collector.c**：采集主机名、操作系统、CPU、内存、磁盘、网络等基础信息
- **collect_user.c**：采集当前 Windows 登录用户名（`GetUserNameW`），在 SYSTEM 账户下使用 `WTSGetActiveConsoleSessionId` + `WTSQuerySessionInformationW` 获取实际登录用户
- **fingerprint.c**：生成设备指纹，算法为 `SHA-256(hostname + "|" + mac_address + "|" + disk_serial)`，用于客户端唯一性判断

### 3.2 采集信息项

| 类别 | 字段名 | 说明 | 采集方式 |
|------|--------|------|----------|
| 主机 | `hostname` | 主机名 | `GetComputerNameExW()` |
| 系统 | `os_name` | 操作系统名称 | `RtlGetVersion()` + 版本号映射 |
| 系统 | `os_version` | 操作系统版本 | `RtlGetVersion()->dwMajorVersion.dwMinorVersion.dwBuildNumber` |
| 系统 | `os_arch` | 系统架构(x86/x64) | `GetNativeSystemInfo()->wProcessorArchitecture` |
| CPU | `cpu_model` | CPU型号 | `RegQueryValueExW(HKEY_LOCAL_MACHINE,\HARDWARE\DESCRIPTION\System\CentralProcessor\0)` |
| CPU | `cpu_cores` | CPU核心数 | `GetNativeSystemInfo()->dwNumberOfProcessors` |
| 内存 | `total_memory_mb` | 总内存(MB) | `GlobalMemoryStatusEx()->ullTotalPhys` |
| 内存 | `available_memory_mb` | 可用内存(MB) | `GlobalMemoryStatusEx()->ullAvailPhys` |
| 磁盘 | `disks` | 磁盘列表(JSON) | `GetLogicalDriveStringsW()` + `GetDiskFreeSpaceExW()` |
| 网络 | `mac_address` | 主MAC地址 | `GetAdaptersInfo()` / `GetAdaptersAddresses()` |
| 网络 | `ip_address` | 主IP地址 | `GetAdaptersInfo()` / `gethostname()` + `gethostbyname()` |
| 网络 | `network_interfaces` | 网卡列表(JSON) | `GetAdaptersAddresses()` |
| 用户 | `logged_in_user` | 当前登录用户名 | `GetUserNameW()` |
| 标识 | `agent_version` | Agent版本号 | 编译时常量（`#define AGENT_VERSION` 宏定义） |
| 标识 | `device_fingerprint` | 设备指纹(SHA-256 hex) | `SHA-256(hostname+mac+disk_serial)` |
| 关联 | `asset_number` | 关联资产编号 | 配置文件指定 |

#### 自动采集 vs 手动录入

| 类别 | 字段 | 说明 | 来源 |
|------|------|------|------|
| 手动 | `location` | 存放位置 | 用户在客户端录入 |
| 手动 | `department` | 所属部门 | 用户在客户端录入 |
| 手动 | `responsible_person` | 责任人 | 用户在客户端录入 |

> **登录用户名采集说明**：使用 `GetUserNameW()` 获取当前交互式登录用户名。在服务运行场景（SYSTEM账户）下，通过 `WTSGetActiveConsoleSessionId()` + `WTSQuerySessionInformationW(WTSUserName)` 获取实际登录用户。若两者均无法获取，记录空字符串。

说明：这三个字段由用户在客户端手动填写，随心跳/注册请求一并上传，服务端存入 agent_devices 表并关联到 fixed_assets。

**手动字段来源方式**：
1. **通用客户端下载**：config.json 中这三个字段初始为空字符串，用户安装后通过 `--edit-info` 命令或客户端 UI 手动填写
2. **资产关联客户端下载**：从固定资产记录（fixed_assets 表）中自动读取并注入 config.json，客户端安装后这些字段自动填充，无需手动录入
3. **Web管理页面编辑**：管理员可通过 Agent 管理页面的"编辑手动信息"模态框，直接修改已注册设备的这些字段（调用 `PUT /api/agent/devices/<agent_id>/manual-fields` 端点）

### 3.3 心跳机制

```c
/* 心跳配置 */
typedef struct {
    int interval_secs;       /* 心跳间隔，默认120秒 */
    int retry_count;         /* 重试次数，默认3次 */
    int retry_delay_secs;    /* 重试延迟，默认10秒 */
    int report_interval_secs;/* 完整信息上报间隔，默认3600秒(1小时) */
} HeartbeatConfig;
```

**心跳策略**：
- 首次启动：发送完整设备信息（注册请求）
- 常规心跳：每120秒发送轻量心跳包，仅包含 `agent_id` + `timestamp`
- 信息变更检测：每次心跳前检测设备信息是否变化，变化时附带完整信息
- 定时全量上报：每1小时强制上报一次完整设备信息
- 失败重试：心跳失败后重试3次，间隔10秒，全部失败后等待下一个心跳周期
- 离线恢复：连续5次心跳失败后进入离线模式，每5分钟尝试一次恢复

### 3.4 配置管理（通用二进制 + 下载时配置注入）

C 二进制只编译一次，不含任何服务器信息。用户下载时，Flask 的 `/api/agent/download` 端点动态生成包含服务器地址和 API Key 的配置文件，与 exe 一起打包成 zip 返回。客户端运行时按优先级查找配置文件，使用 cJSON 解析 JSON。

#### 下载时配置注入流程

```
用户点击"下载Asset Agent"
    → GET /api/agent/download
    → Flask路由：
        1. 生成新 API Key（或使用预生成的）
        2. 读取当前服务器地址（host:port）
        3. 生成 config.json 内容
        4. 将 static/agent/asset-agent.exe + config.json 打包成 zip
        5. 返回 zip 下载
    → 用户解压得到 asset-agent.exe + config.json
    → 双击运行 exe，自动读取同目录 config.json
    → 注册、开始心跳
```

#### config.json 格式

```json
{
    "server_url": "http://192.168.1.100:35168",
    "api_key": "AGENT_a1b2c3d4...",
    "heartbeat_interval": 120,
    "asset_number": "",
    "device_fingerprint": "",
    "uuid": "",
    "location": "",
    "department": "",
    "responsible_person": ""
}
```

说明：location/department/responsible_person 初始为空字符串。通用客户端下载时这三个字段为空，用户通过 `asset-agent.exe edit-info` 命令或客户端UI填写；资产关联客户端下载时这三个字段从固定资产记录中自动注入，客户端安装后自动填充。

#### 三字段取值优先级与双向同步

location/department/responsible_person 三字段的取值遵循以下优先级：

1. **已关联固定资产**（config.json 中 asset_number 非空且服务端确认关联存在）：
   - 三字段取值自固定资产记录（storage_location / 使用部门名称 / responsible_person）
   - 客户端本地修改后，下次心跳时服务端会将修改同步到固定资产记录
   - 固定资产侧修改后，下次心跳响应中携带最新值，客户端自动更新本地 config.json

2. **未关联固定资产**（asset_number 为空或关联不存在）：
   - 三字段取值自客户端本地 config.json 中的值
   - 用户通过 `--edit-info` 命令或编辑脚本修改

3. **双向同步策略**：
   - 采用"最后修改者胜出"策略，基于 `updated_at` 时间戳比较
   - Agent 侧修改（Web管理页面/客户端编辑）：即时同步到 fixed_assets
   - 固定资产侧修改：即时同步到 agent_devices
   - 心跳校验：每次心跳时检查一致性，不一致时以较新时间戳为准同步

#### `config.c` / `config.h` 配置读取逻辑

```c
/* config.h - 配置结构体与接口声明 */
#ifndef CONFIG_H
#define CONFIG_H

#define MAX_URL_LEN      256
#define MAX_KEY_LEN      64
#define MAX_ID_LEN       32
#define MAX_FIELD_LEN    128
#define MAX_FP_LEN       65       // SHA-256 hex = 64 chars + null
#define MAX_UUID_LEN     37       // UUID v4 = 36 chars + null

typedef struct {
    char server_url[MAX_URL_LEN];
    char api_key[MAX_KEY_LEN];
    int  heartbeat_interval;
    char asset_number[MAX_FIELD_LEN];
    char device_fingerprint[MAX_FP_LEN];  // 设备指纹（硬件绑定哈希）
    char uuid[MAX_UUID_LEN];              // 服务端分配的UUID
    char agent_id[MAX_ID_LEN];
    char server_url_override[MAX_URL_LEN]; /* 服务端下发的URL覆盖，优先级最高 */
    char location[MAX_FIELD_LEN];          /* 存放位置（手动录入） */
    char department[MAX_FIELD_LEN];        /* 所属部门（手动录入） */
    char responsible_person[MAX_FIELD_LEN];/* 责任人（手动录入） */
} AgentConfig;

AgentConfig* LoadConfig(void);
int  SaveConfig(const AgentConfig *config);
int  SaveConfigTo(const AgentConfig *config, const char *path);
const char* EffectiveServerURL(const AgentConfig *config);
void ApplyServerUpdate(AgentConfig *config, const char *new_url, int new_interval);
void FreeConfig(AgentConfig *config);

#endif /* CONFIG_H */
```

```c
/* config.c - 配置管理实现 */
#include "config.h"
#include "cJSON.h"
#include <windows.h>
#include <shlobj.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define PROGRAM_DATA_DIR   "C:\\ProgramData\\AssetAgent"
#define PROGRAM_DATA_CFG   "C:\\ProgramData\\AssetAgent\\config.json"

/* generate_agent_id: 生成 "ag_" + 16位hex字符串 */
static void generate_agent_id(char *buf, size_t bufsize) {
    HCRYPTPROV hProv;
    BYTE bytes[8];
    if (CryptAcquireContext(&hProv, NULL, NULL, PROV_RSA_FULL,
                            CRYPT_VERIFYCONTEXT | CRYPT_SILENT)) {
        CryptGenRandom(hProv, 8, bytes);
        CryptReleaseContext(hProv, 0);
    } else {
        /* 回退：使用 GetTickCount + QueryPerformanceCounter */
        DWORD seed = GetTickCount();
        LARGE_INTEGER perf;
        QueryPerformanceCounter(&perf);
        seed ^= (DWORD)(perf.QuadPart & 0xFFFFFFFF);
        for (int i = 0; i < 8; i++)
            bytes[i] = (BYTE)((seed >> (i % 4 * 8)) ^ i);
    }
    snprintf(buf, bufsize, "ag_%02x%02x%02x%02x%02x%02x%02x%02x",
             bytes[0], bytes[1], bytes[2], bytes[3],
             bytes[4], bytes[5], bytes[6], bytes[7]);
}

/* generate_device_fingerprint: 生成设备指纹
 * 算法：SHA-256(hostname + "|" + mac_address + "|" + disk_serial)
 * 返回64字符hex字符串
 */
static void generate_device_fingerprint(char *buf, size_t bufsize,
                                         const char *hostname,
                                         const char *mac_address,
                                         const char *disk_serial) {
    char combined[512];
    snprintf(combined, sizeof(combined), "%s|%s|%s", hostname, mac_address, disk_serial);

    /* 使用Windows Cryptography API计算SHA-256 */
    HCRYPTPROV hProv = 0;
    HCRYPTHASH hHash = 0;
    DWORD hashLen = 32;
    BYTE hashData[32];

    if (CryptAcquireContext(&hProv, NULL, NULL, PROV_RSA_AES, CRYPT_VERIFYCONTEXT) &&
        CryptCreateHash(hProv, CALG_SHA_256, 0, 0, &hHash)) {
        CryptHashData(hHash, (BYTE*)combined, (DWORD)strlen(combined), 0);
        CryptGetHashParam(hHash, HP_HASHVAL, hashData, &hashLen, 0);
        CryptDestroyHash(hHash);
        CryptReleaseContext(hProv, 0);
    }

    /* 转为hex字符串 */
    for (DWORD i = 0; i < hashLen && i * 2 < bufsize - 1; i++) {
        sprintf(buf + i * 2, "%02x", hashData[i]);
    }
    buf[hashLen * 2] = '\0';
}

/* get_disk_serial: 获取系统盘序列号
 * 使用 GetVolumeInformationW 获取C:卷序列号
 */
static void get_disk_serial(char *buf, size_t bufsize) {
    DWORD serial = 0;
    if (GetVolumeInformationW(L"C:\\", NULL, 0, &serial, NULL, NULL, NULL, 0)) {
        snprintf(buf, bufsize, "%08X", serial);
    } else {
        strncpy(buf, "unknown", bufsize - 1);
    }
}

/* local_config_path: 获取exe同目录下的config.json路径 */
static int local_config_path(char *buf, size_t bufsize) {
    if (!GetModuleFileNameA(NULL, buf, (DWORD)bufsize)) return 0;
    char *last_sep = strrchr(buf, '\\');
    if (!last_sep) return 0;
    if (strlen(last_sep + 1) + strlen("\\config.json") + 1 > MAX_PATH) return 0;
    strcpy(last_sep + 1, "config.json");
    DWORD attr = GetFileAttributesA(buf);
    return (attr != INVALID_FILE_ATTRIBUTES &&
            !(attr & FILE_ATTRIBUTE_DIRECTORY));
}

/* parse_config_from_json: 从cJSON对象解析配置 */
static void parse_config_from_json(cJSON *json, AgentConfig *config) {
    cJSON *item;
    if ((item = cJSON_GetObjectItem(json, "server_url")))
        strncpy(config->server_url, item->valuestring, MAX_URL_LEN - 1);
    if ((item = cJSON_GetObjectItem(json, "api_key")))
        strncpy(config->api_key, item->valuestring, MAX_KEY_LEN - 1);
    if ((item = cJSON_GetObjectItem(json, "heartbeat_interval")))
        config->heartbeat_interval = item->valueint;
    if ((item = cJSON_GetObjectItem(json, "asset_number")))
        strncpy(config->asset_number, item->valuestring, MAX_FIELD_LEN - 1);
    if ((item = cJSON_GetObjectItem(json, "device_fingerprint")))
        strncpy(config->device_fingerprint, item->valuestring, MAX_FP_LEN - 1);
    if ((item = cJSON_GetObjectItem(json, "uuid")))
        strncpy(config->uuid, item->valuestring, MAX_UUID_LEN - 1);
    if ((item = cJSON_GetObjectItem(json, "agent_id")))
        strncpy(config->agent_id, item->valuestring, MAX_ID_LEN - 1);
    if ((item = cJSON_GetObjectItem(json, "server_url_override")))
        strncpy(config->server_url_override, item->valuestring, MAX_URL_LEN - 1);
    if ((item = cJSON_GetObjectItem(json, "location")))
        strncpy(config->location, item->valuestring, MAX_FIELD_LEN - 1);
    if ((item = cJSON_GetObjectItem(json, "department")))
        strncpy(config->department, item->valuestring, MAX_FIELD_LEN - 1);
    if ((item = cJSON_GetObjectItem(json, "responsible_person")))
        strncpy(config->responsible_person, item->valuestring, MAX_FIELD_LEN - 1);
}

/* read_json_file: 读取文件并解析为cJSON对象 */
static cJSON* read_json_file(const char *path) {
    FILE *fp = fopen(path, "rb");
    if (!fp) return NULL;
    fseek(fp, 0, SEEK_END);
    long fsize = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    char *data = (char*)malloc(fsize + 1);
    if (!data) { fclose(fp); return NULL; }
    fread(data, 1, fsize, fp);
    data[fsize] = '\0';
    fclose(fp);
    cJSON *json = cJSON_Parse(data);
    free(data);
    return json;
}

/* LoadConfig: 加载配置，优先级为 服务端下发 > 同目录config.json > ProgramData/config.json > 首次配置窗口 */
AgentConfig* LoadConfig(void) {
    AgentConfig *config = (AgentConfig*)calloc(1, sizeof(AgentConfig));
    if (!config) return NULL;
    config->heartbeat_interval = 120;

    /* 1. 尝试从exe同目录读取 config.json（下载时注入的配置） */
    char local_path[MAX_PATH];
    if (local_config_path(local_path, MAX_PATH)) {
        cJSON *json = read_json_file(local_path);
        if (json) {
            parse_config_from_json(json, config);
            cJSON_Delete(json);
            if (config->agent_id[0] == '\0')
                generate_agent_id(config->agent_id, MAX_ID_LEN);
            /* 首次运行或设备指纹为空时，生成设备指纹 */
            if (config->device_fingerprint[0] == '\0') {
                char disk_serial[32];
                get_disk_serial(disk_serial, sizeof(disk_serial));
                generate_device_fingerprint(config->device_fingerprint, MAX_FP_LEN,
                                             config->hostname, config->mac_address, disk_serial);
            }
            /* uuid由服务端注册成功后返回，此处不生成 */
            /* 确保ProgramData目录也有配置（用于自启动后的配置查找） */
            CreateDirectoryA(PROGRAM_DATA_DIR, NULL);
            SaveConfigTo(config, PROGRAM_DATA_CFG);
            return config;
        }
    }

    /* 2. 尝试从 ProgramData 读取（自启动后exe路径可能不同） */
    cJSON *json = read_json_file(PROGRAM_DATA_CFG);
    if (json) {
        parse_config_from_json(json, config);
        cJSON_Delete(json);
        if (config->agent_id[0] == '\0') {
            generate_agent_id(config->agent_id, MAX_ID_LEN);
            SaveConfig(config);
        }
        /* 首次运行或设备指纹为空时，生成设备指纹 */
        if (config->device_fingerprint[0] == '\0') {
            char disk_serial[32];
            get_disk_serial(disk_serial, sizeof(disk_serial));
            generate_device_fingerprint(config->device_fingerprint, MAX_FP_LEN,
                                         config->hostname, config->mac_address, disk_serial);
            SaveConfig(config);
        }
        return config;
    }

    /* 3. 无任何配置文件，返回空配置（将触发配置窗口） */
    generate_agent_id(config->agent_id, MAX_ID_LEN);
    /* 生成设备指纹（首次运行） */
    {
        char disk_serial[32];
        get_disk_serial(disk_serial, sizeof(disk_serial));
        generate_device_fingerprint(config->device_fingerprint, MAX_FP_LEN,
                                     config->hostname, config->mac_address, disk_serial);
    }
    return config;
}

/* EffectiveServerURL: 获取当前生效的服务器URL */
const char* EffectiveServerURL(const AgentConfig *config) {
    return (config->server_url_override[0] != '\0')
           ? config->server_url_override : config->server_url;
}

/* ApplyServerUpdate: 应用服务端下发的配置更新 */
void ApplyServerUpdate(AgentConfig *config, const char *new_url, int new_interval) {
    log_write("收到服务端配置更新: server_url=%s", new_url);
    strncpy(config->server_url_override, new_url, MAX_URL_LEN - 1);
    if (new_interval > 0)
        config->heartbeat_interval = new_interval;
    SaveConfig(config);
}

/* build_config_json: 将配置序列化为cJSON对象 */
static cJSON* build_config_json(const AgentConfig *config) {
    cJSON *root = cJSON_CreateObject();
    if (config->server_url[0])
        cJSON_AddStringToObject(root, "server_url", config->server_url);
    if (config->api_key[0])
        cJSON_AddStringToObject(root, "api_key", config->api_key);
    cJSON_AddNumberToObject(root, "heartbeat_interval", config->heartbeat_interval);
    if (config->asset_number[0])
        cJSON_AddStringToObject(root, "asset_number", config->asset_number);
    if (config->device_fingerprint[0])
        cJSON_AddStringToObject(root, "device_fingerprint", config->device_fingerprint);
    if (config->uuid[0])
        cJSON_AddStringToObject(root, "uuid", config->uuid);
    if (config->agent_id[0])
        cJSON_AddStringToObject(root, "agent_id", config->agent_id);
    if (config->server_url_override[0])
        cJSON_AddStringToObject(root, "server_url_override", config->server_url_override);
    if (config->location[0])
        cJSON_AddStringToObject(root, "location", config->location);
    if (config->department[0])
        cJSON_AddStringToObject(root, "department", config->department);
    if (config->responsible_person[0])
        cJSON_AddStringToObject(root, "responsible_person", config->responsible_person);
    return root;
}

/* SaveConfig: 保存到ProgramData默认路径 */
int SaveConfig(const AgentConfig *config) {
    CreateDirectoryA(PROGRAM_DATA_DIR, NULL);
    return SaveConfigTo(config, PROGRAM_DATA_CFG);
}

/* SaveTo: 保存到指定路径 */
int SaveConfigTo(const AgentConfig *config, const char *path) {
    cJSON *root = build_config_json(config);
    if (!root) return -1;
    char *data = cJSON_Print(root);
    cJSON_Delete(root);
    if (!data) return -1;
    FILE *fp = fopen(path, "w");
    if (!fp) { free(data); return -1; }
    fputs(data, fp);
    fclose(fp);
    free(data);
    return 0;
}

/* FreeConfig: 释放配置内存 */
void FreeConfig(AgentConfig *config) {
    free(config);
}
```

**配置读取优先级**（从高到低）：

1. **服务端下发**（`server_url_override`）：心跳响应中 `config_update.server_url` 下发的地址，优先级最高
2. **同目录 config.json**：与 exe 同目录的配置文件（下载时注入），优先级次高
3. **ProgramData config.json**（`C:\ProgramData\AssetAgent\config.json`）：首次运行后同步保存的配置
4. **首次运行配置窗口**：以上均无配置时弹出，作为兜底方案

当从同目录 `config.json` 读取到配置后，会同步保存到 `ProgramData` 目录，确保开机自启动后（exe 路径可能不同）仍能找到配置。

#### 首次运行配置窗口（兜底方案）

如果 exe 所在目录和 ProgramData 都没有 config.json，弹出最小配置窗口让用户输入服务器地址和 API Key。此场景适用于手动分发 exe 的情况。

**`setup_ui.c`**：

```c
/* 仅在无配置文件时使用 */
int showSetupWindow(char *server_url, size_t url_bufsize,
                    char *api_key, size_t key_bufsize) {
    /* 使用 Win32 API CreateWindowEx 创建最小化对话框 */
    /* 窗口内容：
    *   - 服务器地址输入框（预填 http://:35168）
    *   - API Key 输入框
    *   - 确认按钮
    * 点击确认后窗口销毁，返回 1（成功）
    * 点击关闭则返回 0（取消）
    * TODO: 实现 Win32 最小化配置窗口
    */
    return 0;
}
```

### 3.5 隐藏后台进程模式

Agent 以隐藏后台进程方式运行，不使用 Windows Service，不创建系统托盘图标：

**`Makefile` 关键配置**：

```makefile
CC = gcc
CFLAGS = -Wall -O2 -DUNICODE -D_UNICODE -DAGENT_VERSION=\"1.0.0\"
LDFLAGS = -mwindows -lwininet -ladvapi32 -lcrypt32 -lole32 -liphlpapi -lwtsapi32

SOURCES = main.c config.c collector.c collect_user.c fingerprint.c reporter.c service.c \
          autostart.c setup_ui.c cli.c ipc.c info_ui.c cJSON.c
HEADERS = config.h collector.h collect_user.h fingerprint.h reporter.h service.h autostart.h ipc.h cJSON.h
OBJECTS = $(SOURCES:.c=.o)
TARGET = asset-agent.exe

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CC) -o $@ $^ $(LDFLAGS)

%.o: %.c $(HEADERS)
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	del /Q *.o $(TARGET) 2>nul
```

**隐藏进程编译方式**：

C 通过 `WinMain` 入口 + `ShowWindow(SW_HIDE)` 实现隐藏控制台窗口：

```bash
# MinGW-w64 编译（64位，Win7+ 64位，推荐日常使用）
gcc -Wall -O2 -DAGENT_VERSION=\"1.0.0\" -mwindows -o asset-agent.exe ^
    main.c config.c collector.c reporter.c service.c ^
    autostart.c setup_ui.c cli.c ipc.c info_ui.c cJSON.c ^
    -lwininet -ladvapi32 -lcrypt32 -lole32 -liphlpapi

# 32位版本（XP~Win11 全系统兼容，用于需要XP支持的场景）
gcc -Wall -O2 -DAGENT_VERSION=\"1.0.0\" -m32 -mwindows -o asset-agent-x86.exe ^
    main.c config.c collector.c reporter.c service.c ^
    autostart.c setup_ui.c cli.c ipc.c info_ui.c cJSON.c ^
    -lwininet -ladvapi32 -lcrypt32 -lole32 -liphlpapi -lws2_32
```

`-mwindows` 链接选项等效于 Go 的 `-H windowsgui`，编译后的 exe 不创建控制台窗口。

**`main.c` 隐藏进程入口**：

```c
#include "config.h"
#include "service.h"
#include "autostart.h"
#include <windows.h>
#include <stdio.h>

/* 版本号通过编译时宏注入：-DAGENT_VERSION=\"1.0.0\" */
#ifndef AGENT_VERSION
#define AGENT_VERSION "1.0.0"
#endif

int WINAPI WinMain(HINSTANCE hInst, HINSTANCE hPrevInst,
                   LPSTR lpCmdLine, int nCmdShow)
{
    /* 隐藏窗口 */
    ShowWindow(GetConsoleWindow(), SW_HIDE);

    /* 解析命令行参数 */
    if (__argc > 1) {
        if (strcmp(__argv[1], "--stop") == 0)
            return execute_stop();
        if (strcmp(__argv[1], "--uninstall") == 0)
            return execute_uninstall();
        if (strcmp(__argv[1], "--edit-info") == 0)
            return execute_edit_info();
    }

    /* 加载配置（按优先级：同目录config.json > ProgramData/config.json > 空） */
    AgentConfig *config = LoadConfig();

    /* 无配置文件时弹出配置窗口（兜底方案） */
    if (config->server_url[0] == '\0' || config->api_key[0] == '\0') {
        char url[MAX_URL_LEN], key[MAX_KEY_LEN];
        if (showSetupWindow(url, MAX_URL_LEN, key, MAX_KEY_LEN)) {
            strncpy(config->server_url, url, MAX_URL_LEN - 1);
            strncpy(config->api_key, key, MAX_KEY_LEN - 1);
            SaveConfig(config);
        } else {
            FreeConfig(config);
            return 0; /* 用户取消，退出 */
        }
    }

    /* 确保开机自启 */
    ensure_autostart();

    /* 初始化日志（写入文件，不输出到控制台） */
    init_logger();

    log_write("Asset Agent 启动，版本: %s", AGENT_VERSION);

    /* 创建并运行 Agent */
    Agent *agent = agent_create(config);
    agent_run(agent);
    agent_destroy(agent);
    FreeConfig(config);
    return 0;
}

/* init_logger: 简单的文件日志初始化 */
void init_logger(void) {
    /* 日志写入 C:\ProgramData\AssetAgent\agent.log */
    /* 最大10MB，保留3个文件 */
    CreateDirectoryA(PROGRAM_DATA_DIR, NULL);
    g_log_file = fopen(PROGRAM_DATA_DIR "\\agent.log", "a");
}

typedef struct {
    AgentConfig  *config;
    SystemInfo   *last_info;
    Reporter     *reporter;
    int           heartbeat_counter;
    int           consecutive_failures;
    int           offline_mode;
} Agent;

Agent* agent_create(AgentConfig *config) {
    Agent *a = (Agent*)calloc(1, sizeof(Agent));
    a->config = config;
    a->reporter = reporter_create(config);
    a->last_info = collector_collect();
    return a;
}

void agent_run(Agent *a) {
    /* 首次注册 */
    SystemInfo *info = collector_collect();
    if (reporter_register(a->reporter, info) != 0) {
        log_write("注册失败");
    } else {
        log_write("注册成功");
    }

    /* 心跳主循环 */
    while (1) {
        int interval = a->config->heartbeat_interval;
        if (a->offline_mode)
            interval = 300; /* 离线模式：5分钟一次 */
        Sleep(interval * 1000);

        a->heartbeat_counter++;

        /* 检测设备信息变更 */
        SystemInfo *current_info = collector_collect();
        int info_changed = (memcmp(current_info, a->last_info,
                                   sizeof(SystemInfo)) != 0);

        /* 发送心跳 */
        int err;
        if (info_changed || a->heartbeat_counter % 30 == 0) {
            /* 信息变更或每30个周期(约1小时)全量上报 */
            err = reporter_heartbeat_with_info(a->reporter, current_info);
        } else {
            err = reporter_heartbeat(a->reporter);
        }

        if (err != 0) {
            a->consecutive_failures++;
            if (a->consecutive_failures >= 5)
                a->offline_mode = 1;
        } else {
            a->consecutive_failures = 0;
            a->offline_mode = 0;
        }

        free(a->last_info);
        a->last_info = current_info;
    }
}
```

### 3.6 开机自启（注册表 Run 键）

**`autostart.c` / `autostart.h`**：

```c
/* autostart.h */
#ifndef AUTOSTART_H
#define AUTOSTART_H
void ensure_autostart(void);
void remove_autostart(void);
#endif

/* autostart.c */
#include "autostart.h"
#include <windows.h>
#include <stdio.h>

#define AUTOSTART_KEY_PATH L"Software\\Microsoft\\Windows\\CurrentVersion\\Run"
#define APP_NAME_W        L"AssetAgent"

/* ensure_autostart: 确保开机自启已注册 */
void ensure_autostart(void) {
    char exe_path[MAX_PATH];
    if (!GetModuleFileNameA(NULL, exe_path, MAX_PATH)) {
        log_write("获取exe路径失败: %lu", GetLastError());
        return;
    }

    /* 检查是否已注册 */
    HKEY hKey;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, AUTOSTART_KEY_PATH,
                       0, KEY_QUERY_VALUE, &hKey) == ERROR_SUCCESS) {
        wchar_t val[MAX_PATH];
        DWORD val_size = sizeof(val);
        if (RegQueryValueExW(hKey, APP_NAME_W, NULL, NULL,
                              (LPBYTE)val, &val_size) == ERROR_SUCCESS) {
            RegCloseKey(hKey);
            /* 已注册，无需重复写入 */
            return;
        }
        RegCloseKey(hKey);
    }

    /* 注册到 HKCU\Software\Microsoft\Windows\CurrentVersion\Run */
    /* 使用 HKCU 而非 HKLM，无需管理员权限 */
    wchar_t w_exe_path[MAX_PATH];
    MultiByteToWideChar(CP_ACP, 0, exe_path, -1, w_exe_path, MAX_PATH);
    if (RegOpenKeyExW(HKEY_CURRENT_USER, AUTOSTART_KEY_PATH,
                       0, KEY_SET_VALUE, &hKey) == ERROR_SUCCESS) {
        RegSetValueExW(hKey, APP_NAME_W, 0, REG_SZ,
                        (const BYTE*)w_exe_path,
                        (DWORD)(wcslen(w_exe_path) + 1) * sizeof(wchar_t));
        RegCloseKey(hKey);
    }
}

/* remove_autostart: 移除开机自启（卸载时调用） */
void remove_autostart(void) {
    HKEY hKey;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, AUTOSTART_KEY_PATH,
                       0, KEY_SET_VALUE, &hKey) == ERROR_SUCCESS) {
        RegDeleteValueW(hKey, APP_NAME_W);
        RegCloseKey(hKey);
    }
}
```

**为什么选择注册表 Run 键而非 Windows Service**：

| 对比项 | 注册表 Run 键 | Windows Service |
|--------|---------------|-----------------|
| 实现复杂度 | 极低，几行 Win32 API 调用 | 高，需实现 ServiceMain 和控制处理器 |
| 管理员权限 | 不需要（HKCU） | 需要管理员权限注册 |
| 资源占用 | 极低 | Service 控制管理器额外开销 |
| 开机自启 | 用户登录后启动 | 系统启动即运行（无需登录） |
| 适用场景 | 轻量级后台程序 | 需要系统级服务 |
| 二进制体积 | 无额外依赖 | 需链接 advapi32，增加约 50KB |

对于本项目的场景（用户登录后采集信息并上报），注册表 Run 键是最轻量的方案。

### 3.7 依赖精简

仅使用 Windows 系统 API，零外部依赖（cJSON 除外，单文件嵌入）：

| 依赖 | 用途 | 来源 | 备注 |
|------|------|------|------|
| `WinINet` | HTTP 请求 | Windows 系统DLL | XP SP2+ 原生支持，无需第三方库 |
| `cJSON` | JSON 序列化/反序列化 | 单文件嵌入（~500行） | 零外部依赖，MIT 许可 |
| `AdvAPI32` | 注册表操作 | Windows 系统DLL | `RegOpenKeyExW`/`RegSetValueExW` 等 |
| `IPHLPAPI` | 网络适配器信息 | Windows 系统DLL | `GetAdaptersInfo`/`GetAdaptersAddresses` |
| `Kernel32` | 系统信息、文件操作 | Windows 系统DLL | `GetComputerNameExW`/`GlobalMemoryStatusEx` 等 |
| `Crypt32` | 随机数生成 | Windows 系统DLL | `CryptAcquireContext`/`CryptGenRandom` |
| `Ole32` | COM初始化（网络信息） | Windows 系统DLL | `CoInitialize`/`CoUninitialize` |

**C/Win32 API 优势**：
- `WinINet` 替代 `net/http`/`reqwest`：系统自带，XP 原生支持，零依赖
- `cJSON` 替代 `encoding/json`/`serde_json`：单文件嵌入，约500行代码，极轻量
- `AdvAPI32` 替代 `golang.org/x/sys/windows/registry`：系统DLL，直接调用
- `Crypt32` 替代 `crypto/rand`：系统API，无需额外库
- 总计仅 1 个嵌入源文件（cJSON），其余全部为 Windows 系统 API

### 3.8 服务器迁移与配置热更新

当服务器地址变更（IP/端口/域名迁移）时，已部署的客户端需要能够自动跟随服务器迁移，无需重新下载或手动修改配置。

#### 3.8.1 心跳响应扩展

在 `/api/agent/heartbeat` 的响应中增加可选的 `config_update` 字段：

```json
{
    "success": true,
    "data": {
        "heartbeat_interval": 120,
        "config_update": {
            "server_url": "http://new-server:35168",  // 可选，服务端迁移时下发
            "heartbeat_interval": 180                  // 可选，动态调整心跳间隔
        },
        "commands": []
    }
}
```

`config_update` 仅在服务端配置了迁移目标 URL 时才包含，正常情况下心跳响应不含此字段。

#### 3.8.2 客户端迁移处理逻辑

```c
/* handle_heartbeat_response: 处理心跳响应中的配置更新 */
void handle_heartbeat_response(Agent *a, const HeartbeatResponse *resp) {
    if (resp->config_update.server_url[0] == '\0' &&
        resp->config_update.heartbeat_interval <= 0) {
        return; /* 无配置更新 */
    }

    /* 处理服务器URL变更 */
    if (resp->config_update.server_url[0] != '\0') {
        log_write("收到服务器迁移通知: %s -> %s",
                  EffectiveServerURL(a->config), resp->config_update.server_url);

        /* 保存旧URL用于回退 */
        char old_url[MAX_URL_LEN];
        strncpy(old_url, EffectiveServerURL(a->config), MAX_URL_LEN - 1);

        /* 应用新配置 */
        ApplyServerUpdate(a->config, resp->config_update.server_url,
                          resp->config_update.heartbeat_interval);

        /* 立即尝试用新URL发送心跳验证可达性 */
        if (reporter_test_heartbeat(a->reporter,
                                     resp->config_update.server_url) != 0) {
            log_write("新服务器心跳失败，回退到旧地址");
            strncpy(a->config->server_url_override, old_url, MAX_URL_LEN - 1);
            SaveConfig(a->config);
            a->migration_fail_count++;
        } else {
            log_write("新服务器心跳成功，迁移完成");
            a->migration_confirmed = 1;
            a->migration_fail_count = 0;
        }
    } else if (resp->config_update.heartbeat_interval > 0) {
        /* 仅调整心跳间隔 */
        a->config->heartbeat_interval = resp->config_update.heartbeat_interval;
        SaveConfig(a->config);
    }
}
```

#### 3.8.3 迁移确认机制

客户端在新服务器上首次心跳成功后，发送迁移确认请求：

```
POST /api/agent/heartbeat  (使用新服务器URL)
Body:
{
    "agent_id": "ag_abc123",
    "timestamp": "2026-09-08T10:35:00Z",
    "migration_confirmed": true,       // 标记迁移已确认
    "previous_server_url": "http://old-server:35168"  // 旧服务器地址
}
```

旧服务器收到迁移确认后（通过管理端API），可将该客户端标记为"已迁移"。

#### 3.8.4 失败回退策略

```c
#define MIGRATION_MAX_RETRIES 3

/* check_migration_fallback: 迁移失败回退逻辑（集成在心跳主循环中） */
void check_migration_fallback(Agent *a) {
    if (a->migration_fail_count >= MIGRATION_MAX_RETRIES) {
        log_write("新服务器连续%d次心跳失败，自动回退到旧服务器地址",
                  MIGRATION_MAX_RETRIES);
        /* 清除服务端下发的覆盖URL，回退到本地config.json中的server_url */
        a->config->server_url_override[0] = '\0';
        SaveConfig(a->config);
        a->migration_fail_count = 0;
        a->migration_confirmed = 0;
    }
}
```

**回退规则**：
- 新服务器连续 3 次心跳失败，自动回退到旧服务器地址
- 回退时清除 `server_url_override`，使用本地配置文件中的 `server_url`
- 如果本地配置文件的 `server_url` 也不可达，Agent 进入离线模式等待恢复
- 回退事件记录到本地日志文件

#### 3.8.5 迁移流程时序

```
管理员调用 POST /api/agent/migrate（设置新服务器URL）
          │
          v
服务端设置 migration_new_url 和 migration_enabled（存储在 agent_config 表）
          │
          v
Agent下次心跳 → 服务端在响应中附带 config_update.server_url
          │
          v
Agent收到新URL → 写入本地config.json（server_url_override）
          │
          v
Agent尝试用新URL发送心跳
     ┌─────┴─────┐
     │           │
  成功          失败
     │           │
     v           v
  标记迁移完成   记录失败次数
     │           │
     v           v
  后续心跳使用   重试（最多3次）
  新服务器URL       │
                    v
              连续3次失败 → 回退旧URL
```

### 3.9 客户端 CLI 命令

Agent 支持以下命令行参数，实现手动退出、卸载和信息编辑：

| 命令 | 说明 | 实现方式 | 备注 |
|------|------|----------|------|
| `asset-agent.exe` | 正常启动（无参数） | 启动隐藏后台进程 | - |
| `asset-agent.exe --stop` | 停止正在运行的 Agent | 通过命名管道发送 stop 指令 | 次要方式，推荐使用管理页面生成的停止脚本 |
| `asset-agent.exe --uninstall` | 卸载 Agent | 停止进程 + 清理注册表 + 删除 ProgramData 目录 | 次要方式，推荐使用管理页面生成的卸载脚本 |
| `asset-agent.exe --edit-info` | 编辑手动信息 | 弹出信息编辑窗口（存放位置/部门/责任人） | - |

#### 3.9.1 进程间通信（命名管道）

Agent 启动时创建命名管道 `\\.\pipe\AssetAgent`，用于接收 CLI 命令：

```c
/* ipc.h */
#ifndef IPC_H
#define IPC_H
void start_ipc_server(void);
int  send_ipc_command(const char *command);
#endif

/* ipc.c - 进程间通信（命名管道） */
#include "ipc.h"
#include "cJSON.h"
#include <windows.h>
#include <stdio.h>

#define PIPE_NAME L"\\\\.\\pipe\\AssetAgent"
#define PIPE_BUFFER_SIZE 256

/* IpcCommand: IPC命令结构 */
typedef struct {
    char command[64]; /* "stop", "uninstall", "edit_info", "report_now" */
} IpcCommand;

static HANDLE g_pipe_thread = NULL;

/* ipc_server_thread: 命名管道服务端线程 */
static DWORD WINAPI ipc_server_thread(LPVOID param) {
    char cmd_chan[64] = {0};
    while (1) {
        HANDLE hPipe = CreateNamedPipeW(PIPE_NAME,
            PIPE_ACCESS_DUPLEX | FILE_FLAG_OVERLAPPED,
            PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
            1, PIPE_BUFFER_SIZE, PIPE_BUFFER_SIZE, 0, NULL);
        if (hPipe == INVALID_HANDLE_VALUE) continue;

        if (ConnectNamedPipe(hPipe, NULL) || GetLastError() == ERROR_PIPE_CONNECTED) {
            char buf[PIPE_BUFFER_SIZE] = {0};
            DWORD bytes_read = 0;
            if (ReadFile(hPipe, buf, PIPE_BUFFER_SIZE - 1, &bytes_read, NULL) && bytes_read > 0) {
                buf[bytes_read] = '\0';
                cJSON *json = cJSON_Parse(buf);
                if (json) {
                    cJSON *cmd = cJSON_GetObjectItem(json, "command");
                    if (cmd && cmd->valuestring[0]) {
                        strncpy(cmd_chan, cmd->valuestring, sizeof(cmd_chan) - 1);
                        /* 在此处理命令：stop/uninstall/edit_info/report_now */
                    }
                    cJSON_Delete(json);
                }
            }
        }
        DisconnectNamedPipe(hPipe);
        CloseHandle(hPipe);
    }
    return 0;
}

/* start_ipc_server: 启动命名管道服务端 */
void start_ipc_server(void) {
    g_pipe_thread = CreateThread(NULL, 0, ipc_server_thread, NULL, 0, NULL);
}

/* send_ipc_command: 发送IPC命令到命名管道 */
int send_ipc_command(const char *command) {
    HANDLE hPipe = CreateFileW(PIPE_NAME, GENERIC_WRITE, 0,
                                NULL, OPEN_EXISTING, 0, NULL);
    if (hPipe == INVALID_HANDLE_VALUE) return -1; /* Agent 未在运行 */

    cJSON *root = cJSON_CreateObject();
    cJSON_AddStringToObject(root, "command", command);
    char *data = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);

    DWORD bytes_written = 0;
    WriteFile(hPipe, data, (DWORD)strlen(data), &bytes_written, NULL);
    free(data);
    CloseHandle(hPipe);
    return 0;
}
```

CLI 命令执行流程：
1. `asset-agent.exe --stop` 启动后连接命名管道
2. 发送 `Stop` 命令
3. 正在运行的 Agent 收到命令后优雅退出
4. CLI 进程退出

#### 3.9.2 停止命令（--stop）

```c
/* cli.c - 停止命令 */
int execute_stop(void) {
    /* 1. 连接命名管道 \\.\pipe\AssetAgent */
    /* 2. 发送 stop 命令 */
    /* 3. 等待确认或超时（5秒） */
    /* 4. 若管道不存在，提示"Agent 未在运行" */
    if (send_ipc_command("stop") == 0) {
        printf("Agent 已停止\n");
    } else {
        printf("Agent 未在运行\n");
    }
    return 0;
}
```

#### 3.9.3 卸载命令（--uninstall）

```c
/* cli.c - 卸载命令 */
int execute_uninstall(void) {
    /* 1. 尝试通过命名管道发送 stop 命令 */
    send_ipc_command("stop");
    /* 2. 等待进程退出（最多10秒） */
    Sleep(10000);
    /* 3. 删除注册表 Run 键：HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run\AssetAgent */
    remove_autostart();
    /* 4. 删除 ProgramData 目录：C:\ProgramData\AssetAgent\ */
    char cmd[MAX_PATH + 32];
    snprintf(cmd, sizeof(cmd), "rd /s /q \"%s\"", PROGRAM_DATA_DIR);
    system(cmd);
    /* 5. 提示用户手动删除 exe 所在目录 */
    printf("Agent 已卸载，请手动删除安装目录\n");
    return 0;
}
```

#### 3.9.4 编辑信息命令（--edit-info）

弹出信息编辑窗口，包含三个输入框：
- 存放位置（location）
- 所属部门（department）
- 责任人（responsible_person）

用户填写后保存到 config.json（同目录和 ProgramData 都更新），下次心跳时上传到服务端。

```c
/* info_ui.c */
int show_info_editor(const AgentConfig *current,
                     char *location, size_t loc_bufsize,
                     char *department, size_t dept_bufsize,
                     char *responsible_person, size_t resp_bufsize) {
    /* 弹出 Win32 对话框，预填当前值 */
    /* 用户编辑后点击确认返回 1（成功） */
    /* 点击取消返回 0 */
    /* TODO: 实现 Win32 信息编辑对话框 */
    return 0;
}
```

> **注意**：`--edit-info` CLI 命令为次要方式，推荐使用管理页面生成的 `edit-info-agent.bat` 脚本（见§3.13.4）。

### 3.10 服务端远程控制

通过心跳响应的 `commands` 字段，服务端可以向 Agent 下发控制指令。Agent 收到指令后立即执行，并在下一次心跳中上报执行结果。

#### 3.10.1 指令定义

| 指令 | 说明 | 参数 | 执行动作 |
|------|------|------|----------|
| `report_now` | 立即上报 | 无 | 立即采集完整系统信息并发送 /api/agent/report |
| `update_interval` | 修改心跳间隔 | `{"interval": 60}` | 更新本地心跳间隔（秒），最小30秒 |
| `refresh_config` | 刷新配置 | 无 | 重新从服务端拉取完整配置 |
| `stop` | 停止 Agent | 无 | 优雅退出 Agent 进程 |
| `restart` | 重启 Agent | 无 | 退出后重新启动自身（使用 `CreateProcess`） |

#### 3.10.2 指令执行流程

```
Agent 发送心跳 ──> 服务端响应包含 commands: ["report_now", "update_interval", {"interval": 60}]
                    │
Agent 收到指令 ──> 逐条执行：
                    ├── report_now → 立即采集并上报
                    ├── update_interval → 更新本地 tick_interval
                    └── 记录执行结果
                    │
下次心跳 ──> 携带 command_results 字段上报执行结果：
                    "command_results": [
                        {"command": "report_now", "status": "ok"},
                        {"command": "update_interval", "status": "ok", "detail": "60s"}
                    ]
```

#### 3.10.3 安全限制

- 指令仅通过 HTTPS 心跳响应下发，不开放独立指令端口
- `stop` 和 `restart` 指令需在 agent_config 表中显式启用（`allow_remote_stop: false` 默认关闭）
- 指令执行超时时间为 30 秒，超时视为失败
- Agent 端可配置指令白名单，拒绝不信任的指令

### 3.11 服务端主动连接分析

#### 为什么不支持服务端主动发起连接

在当前架构下，**不建议**实现服务端主动向 Agent 发起连接，原因如下：

| 限制因素 | 说明 |
|----------|------|
| NAT 穿透 | 大多数客户端位于 NAT 网关之后，服务端无法直接访问内网 IP |
| 防火墙策略 | 企业防火墙通常只允许出站 HTTP/HTTPS，阻止入站连接 |
| 安全风险 | Agent 开放监听端口会增加攻击面，可能被恶意利用 |
| 端口冲突 | 客户端可能已有服务占用相同端口 |
| 运维复杂度 | 需要管理客户端端口、证书、认证等 |

#### 替代方案：心跳指令通道

当前设计已通过心跳响应的 `commands` 字段实现等效功能：

- **实时性**：心跳间隔 120 秒，指令最长延迟 2 分钟
- **可靠性**：基于 HTTP/HTTPS，无需额外端口
- **安全性**：复用 API Key 认证，无需额外认证机制
- **简洁性**：无需 WebSocket 长连接维护

#### 未来扩展（可选）

若业务需要更高实时性，可在后续版本中增加 **WebSocket 升级**：
- Agent 在心跳时协商升级为 WebSocket 长连接
- 服务端通过 WebSocket 主动推送指令
- 保持 HTTP 心跳作为降级方案

当前版本暂不实现 WebSocket，心跳指令通道已满足需求。

### 3.12 系统兼容性分析

#### C/Win32 API 兼容性优势

C 语言 + Win32 API 方案在 Windows 兼容性上具有天然优势：

| 特性 | C + Win32 API | 说明 |
|------|---------------|------|
| Windows XP 支持 | ✅ 原生支持 | Win32 API 是 XP 的原生接口，无兼容层 |
| Windows 7+ 支持 | ✅ 原生支持 | 所有 API 在 Win7+ 上完整可用 |
| Windows 10/11 支持 | ✅ 原生支持 | Win32 API 向后兼容 |
| 单二进制输出 | ✅ 静态链接 CRT | `/MT` 编译选项，无外部运行时依赖 |
| 二进制体积 | 1~3 MB | 远小于 Go/Rust 方案 |
| 内存占用 | 1~3 MB | 仅系统 API 调用，无运行时开销 |
| 第三方依赖 | 0 个（cJSON 嵌入） | cJSON 单文件嵌入，约500行代码 |
| HTTP 通信 | WinINet | 系统自带，XP SP2+ 原生支持 |
| 系统信息采集 | Win32 API | 直接调用，无第三方库 |

#### Win32 API XP 兼容性说明

本项目使用的 Win32 API 在 Windows XP 上的兼容性：

- **`GetComputerNameExW()`**：✅ XP 原生支持
- **`RtlGetVersion()` / `GetVersionEx()`**：✅ XP 原生支持（`GetVersionEx` 在 Win8.1+ 需 manifest，`RtlGetVersion` 无此限制）
- **`GetNativeSystemInfo()`**：✅ XP 原生支持
- **`GlobalMemoryStatusEx()`**：✅ XP SP2+ 支持
- **`GetLogicalDriveStringsW()` + `GetDiskFreeSpaceExW()`**：✅ XP 原生支持
- **`GetAdaptersInfo()`**：✅ XP 原生支持（推荐优先使用，`GetAdaptersAddresses` 在 XP SP1 上有限制）
- **`RegOpenKeyExW()` / `RegSetValueExW()`**：✅ XP 原生支持
- **`WinINet` HTTP API**：✅ XP SP2+ 支持（XP SP3 的 WinINet 支持 TLS 1.0，TLS 1.2 需额外配置）
- **`CreateNamedPipeW()`**：✅ XP 原生支持
- **`CryptAcquireContext()` / `CryptGenRandom()`**：✅ XP 原生支持

#### 编译配置说明

```bash
# MinGW-w64 编译（64位，Win7+ 64位，推荐日常使用）
gcc -Wall -O2 -DAGENT_VERSION=\"1.0.0\" -mwindows -o asset-agent.exe \
    main.c config.c collector.c collect_user.c fingerprint.c reporter.c service.c \
    autostart.c setup_ui.c cli.c ipc.c info_ui.c cJSON.c \
    -lwininet -ladvapi32 -lcrypt32 -lole32 -liphlpapi -lwtsapi32

# MinGW-w64 编译（32位，XP~Win11 全系统兼容）
gcc -Wall -O2 -DAGENT_VERSION=\"1.0.0\" -m32 -mwindows -o asset-agent-x86.exe \
    main.c config.c collector.c collect_user.c fingerprint.c reporter.c service.c \
    autostart.c setup_ui.c cli.c ipc.c info_ui.c cJSON.c \
    -lwininet -ladvapi32 -lcrypt32 -lole32 -liphlpapi -lwtsapi32 -lws2_32

# MSVC 编译（64位，静态链接CRT，无运行时依赖）
cl /O2 /MT /D AGENT_VERSION=\"1.0.0\" /DUNICODE /D_UNICODE \
   main.c config.c collector.c reporter.c service.c \
   autostart.c setup_ui.c cli.c ipc.c info_ui.c cJSON.c \
   /link /SUBSYSTEM:WINDOWS wininet.lib advapi32.lib crypt32.lib ole32.lib iphlpapi.lib

# MSVC 编译（32位，XP 兼容，使用 v141_xp 工具集）
cl /O2 /MT /D AGENT_VERSION=\"1.0.0\" /DUNICODE /D_UNICODE \
   main.c config.c collector.c reporter.c service.c \
   autostart.c setup_ui.c cli.c ipc.c info_ui.c cJSON.c \
   /link /SUBSYSTEM:WINDOWS,5.01 wininet.lib advapi32.lib crypt32.lib ole32.lib iphlpapi.lib
```

编译参数说明：
- `-mwindows` / `/SUBSYSTEM:WINDOWS`：设置 Windows 子系统为 GUI，不创建控制台窗口
- `-m32`：32 位架构，支持 XP；默认 64 位架构仅 Win7+
- `/MT`：静态链接 CRT（MSVC），无外部运行时依赖
- `/SUBSYSTEM:WINDOWS,5.01`：MSVC XP 兼容子系统版本号
- `-DAGENT_VERSION`：通过宏定义注入版本号

#### 风险提示

1. **WinINet TLS 版本**：XP SP3 的 WinINet 默认支持 TLS 1.0，TLS 1.2 需注册表启用或服务端兼容 TLS 1.0。建议服务端同时支持 TLS 1.0+，或在内网环境使用 HTTP
2. **32 位限制**：32 位进程地址空间限制为 2GB，对本项目（内存目标 < 3MB）无影响
3. **`GetAdaptersAddresses`**：在 XP SP1 上有内存泄漏问题，优先使用 `GetAdaptersInfo`
4. **字符编码**：统一使用 `W` 后缀的宽字符 API（如 `RegOpenKeyExW`），确保 Unicode 兼容

### 3.13 停止与卸载脚本

除了 CLI 命令方式（`--stop` / `--uninstall`），管理页面还提供可下载的 `.bat` 脚本，方便用户在无命令行经验的情况下停止或卸载 Agent。

#### 3.13.1 停止脚本（stop-agent.bat）

```bat
@echo off
chcp 65001 >nul
echo 正在停止 Asset Agent...
taskkill /IM asset-agent.exe /F >nul 2>&1
if %errorlevel% equ 0 (
    echo Asset Agent 已成功停止
) else (
    echo Asset Agent 未在运行或停止失败
)
timeout /t 3 >nul
```

#### 3.13.2 卸载脚本（uninstall-agent.bat）

```bat
@echo off
chcp 65001 >nul
echo 正在卸载 Asset Agent...
:: 停止进程
taskkill /IM asset-agent.exe /F >nul 2>&1
:: 删除注册表自启键
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v AssetAgent /f >nul 2>&1
:: 删除配置目录
rd /s /q "%ProgramData%\AssetAgent" 2>nul
:: 删除同目录配置文件
if exist "%~dp0config.json" del "%~dp0config.json" >nul 2>&1
echo.
echo Asset Agent 已卸载，请手动删除 asset-agent.exe 文件
echo.
timeout /t 5 >nul
```

#### 3.13.3 脚本生成方式

脚本由服务端 API 端点动态生成并返回下载：

- `GET /api/agent/stop-script` - 返回停止脚本
- `GET /api/agent/uninstall-script` - 返回卸载脚本

两个端点均返回 `Content-Type: application/octet-stream`，`Content-Disposition: attachment; filename="stop-agent.bat"` 或 `uninstall-agent.bat`，触发浏览器下载。

**脚本 vs CLI 命令对比**：

| 对比项 | 管理页面脚本（推荐） | CLI 命令（次要） |
|--------|---------------------|-----------------|
| 使用方式 | 双击 .bat 文件 | 命令行输入参数 |
| 用户门槛 | 低，无需命令行知识 | 中，需了解命令行 |
| 停止方式 | taskkill 强制终止 | 命名管道优雅退出 |
| 卸载完整度 | 清理注册表+ProgramData+同目录配置 | 同左 + 提示删除 exe |
| 获取方式 | 管理页面下载 | 需已有 agent exe |

#### 3.13.4 编辑配置脚本（edit-info-agent.bat）

用于触发客户端重新编辑配置信息（location/department/responsible_person），无需命令行知识：

```bat
@echo off
chcp 65001 >nul 2>&1
title Asset Agent - 编辑配置信息

echo ========================================
echo   Asset Agent 配置编辑工具
echo ========================================
echo.

:: 通过命名管道发送 edit_info 指令
echo 正在触发Agent编辑窗口...

:: 检查Agent是否运行
tasklist /FI "IMAGENAME eq asset-agent.exe" 2>NUL | find /I "asset-agent.exe" >NUL
if %ERRORLEVEL% neq 0 (
    echo [错误] Agent 未运行，无法发送编辑指令
    echo.
    echo 请先启动 Asset Agent，或直接编辑配置文件：
    echo %APPDATA%\AssetAgent\config.json
    echo.
    pause
    exit /b 1
)

:: 通过命名管道发送 edit_info 指令
echo edit_info> \\.\pipe\asset-agent-ipc

if %ERRORLEVEL% equ 0 (
    echo [成功] 已触发编辑窗口，请在弹出的窗口中修改配置信息
) else (
    echo [提示] 命名管道通信失败，尝试直接打开配置文件...
    start notepad "%APPDATA%\AssetAgent\config.json"
    echo.
    echo 请手动编辑 location、department、responsible_person 字段
    echo 保存后重启 Agent 使配置生效
)

echo.
pause
```

**脚本说明**：
- 优先通过命名管道 IPC 发送 `edit_info` 指令，触发客户端弹出信息编辑窗口
- 若命名管道通信失败（Agent未运行或管道异常），则回退为直接用记事本打开 config.json
- 用户编辑保存后，Agent 下次读取配置时自动加载新值，心跳时同步到服务端

---

## 4. 服务端 API 设计

### 4.1 新增 Blueprint

文件路径：`blueprints/agent/agent_api.py`

```python
from flask import Blueprint
agent_api_bp = Blueprint('agent_api', __name__, url_prefix='/api/agent')
```

在 `main.py` 中注册：
```python
from blueprints.agent.agent_api import agent_api_bp
app.register_blueprint(agent_api_bp)
```

### 4.2 认证方案：API Key

**设计原则**：Agent 不依赖浏览器的 session/cookie 机制，使用独立的 API Key 认证。

**API Key 格式**：`AGENT_{32位随机hex字符串}`，例如 `AGENT_a1b2c3d4e5f6...`

**认证流程**：
1. 请求头携带 `X-Agent-API-Key: AGENT_xxx`
2. 服务端验证 API Key 是否存在于 `agent_api_keys` 表且状态为启用
3. 验证通过后从表中获取关联的 `agent_id`

**权限装饰器**：

```python
# blueprints/agent/auth.py
from functools import wraps
from flask import request, jsonify
from models.agent.agent_api_key import AgentApiKey

def require_agent_key(f):
    """Agent API Key认证装饰器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get('X-Agent-API-Key')
        if not api_key:
            return jsonify({"success": False, "message": "缺少API Key"}), 401

        key_record = AgentApiKey.query.filter_by(
            api_key=api_key, is_active=True
        ).first()
        if not key_record:
            return jsonify({"success": False, "message": "无效的API Key"}), 403

        # 将agent_id注入请求上下文
        request.agent_id = key_record.agent_id
        return f(*args, **kwargs)
    return decorated
```

### 4.3 API 端点

#### 4.3.1 Agent 注册

```
POST /api/agent/register
Headers: X-Agent-API-Key: AGENT_xxx
Body:
{
    "hostname": "PC-DESKTOP-01",
    "os_name": "Windows 10 Pro",
    "os_version": "10.0.19045",
    "os_arch": "x86_64",
    "cpu_model": "Intel(R) Core(TM) i7-10700",
    "cpu_cores": 8,
    "total_memory_mb": 16384,
    "available_memory_mb": 8192,
    "disks": [{"name": "C:", "total_gb": 512, "available_gb": 256, "fs_type": "NTFS"}],
    "mac_address": "00:1A:2B:3C:4D:5E",
    "ip_address": "192.168.1.50",
    "network_interfaces": [{"name": "以太网", "mac": "00:1A:2B:3C:4D:5E", "ips": ["192.168.1.50"]}],
    "agent_version": "1.0.0",
    "logged_in_user": "zhangsan",
    "device_fingerprint": "a1b2c3d4e5f6...（64字符SHA-256 hex）",
    "platform": "windows",
    "asset_number": "ZC2026010001"  // 可选
}

Response:
{
    "success": true,
    "data": {
        "agent_id": "ag_abc123",
        "uuid": "550e8400-e29b-41d4-a716-446655440000",
        "heartbeat_interval": 120,
        "report_interval": 3600
    }
}
```

**逻辑**：
1. 验证 API Key
2. 唯一性判断（三级查重策略）：
   a. 优先通过 `device_fingerprint` 查找已有设备记录（最可靠，硬件绑定）
   b. 若未找到，通过 `(hostname + mac_address)` 组合查找（兼容旧客户端无指纹场景）
   c. 若仍未找到，仅通过 `mac_address` 查找（最宽松匹配，兼容极端情况）
3. 若找到已有记录：
   - 更新所有采集字段（包括 `logged_in_user`）
   - 更新 `device_fingerprint`（若旧记录无指纹）
   - 保持原有 `agent_id` 和 `uuid` 不变
   - 更新 `last_heartbeat_at` 和 `status`
4. 若未找到已有记录（新设备）：
   - 创建新记录，生成 `agent_id`（服务端生成 "ag_" + 16位hex）
   - 生成 UUID v4（服务端使用 Python `uuid.uuid4()`）
   - 将 UUID 与 API Key 关联记录
   - 若提供了 `asset_number`，尝试关联固定资产记录
5. 返回 `agent_id`、`uuid`、`heartbeat_interval`、`report_interval`
6. 客户端收到 `uuid` 后存入 `config.json`，后续心跳携带 `uuid`

**注册端点代码示例**：

```python
import uuid as uuid_module

@agent_api_bp.route('/register', methods=['POST'])
def agent_register():
    """Agent注册端点 - 三级查重策略"""
    api_key = request.headers.get('X-Agent-API-Key', '')
    key_record = AgentApiKey.query.filter_by(api_key=api_key, is_active=True).first()
    if not key_record:
        return jsonify(success=False, message='无效的API Key'), 401

    data = request.get_json()
    if not data or not data.get('hostname'):
        return jsonify(success=False, message='缺少必要字段'), 400

    device = None

    # 三级查重策略
    # 1. 优先通过 device_fingerprint 查找（最可靠）
    fp = data.get('device_fingerprint', '')
    if fp:
        device = AgentDevice.query.filter_by(device_fingerprint=fp).first()

    # 2. 通过 (hostname + mac_address) 组合查找
    if not device:
        hostname = data.get('hostname', '')
        mac = data.get('mac_address', '')
        if hostname and mac:
            device = AgentDevice.query.filter_by(
                hostname=hostname, mac_address=mac
            ).first()

    # 3. 仅通过 mac_address 查找（最宽松）
    if not device and mac:
        device = AgentDevice.query.filter_by(mac_address=mac).first()

    if device:
        # 已有记录：更新所有采集字段
        device.hostname = data.get('hostname', device.hostname)
        device.os_name = data.get('os_name', device.os_name)
        device.os_version = data.get('os_version', device.os_version)
        device.os_arch = data.get('os_arch', device.os_arch)
        device.cpu_model = data.get('cpu_model', device.cpu_model)
        device.cpu_cores = data.get('cpu_cores', device.cpu_cores)
        device.total_memory_mb = data.get('total_memory_mb', device.total_memory_mb)
        device.available_memory_mb = data.get('available_memory_mb', device.available_memory_mb)
        device.disks = data.get('disks', device.disks)
        device.mac_address = data.get('mac_address', device.mac_address)
        device.ip_address = data.get('ip_address', device.ip_address)
        device.network_interfaces = data.get('network_interfaces', device.network_interfaces)
        device.agent_version = data.get('agent_version', device.agent_version)
        device.logged_in_user = data.get('logged_in_user', device.logged_in_user)
        device.platform = data.get('platform', device.platform)
        # 更新设备指纹（若旧记录无指纹）
        if not device.device_fingerprint and fp:
            device.device_fingerprint = fp
        # 保持原有 agent_id 和 uuid 不变
        device.last_heartbeat_at = datetime.now()
        device.status = 'online'
    else:
        # 新设备：创建记录
        agent_id = 'ag_' + uuid_module.uuid4().hex[:16]
        new_uuid = str(uuid_module.uuid4())
        device = AgentDevice(
            agent_id=agent_id,
            uuid=new_uuid,
            hostname=data.get('hostname'),
            os_name=data.get('os_name'),
            os_version=data.get('os_version'),
            os_arch=data.get('os_arch'),
            cpu_model=data.get('cpu_model'),
            cpu_cores=data.get('cpu_cores'),
            total_memory_mb=data.get('total_memory_mb'),
            available_memory_mb=data.get('available_memory_mb'),
            disks=json.dumps(data.get('disks', [])),
            mac_address=data.get('mac_address'),
            ip_address=data.get('ip_address'),
            network_interfaces=json.dumps(data.get('network_interfaces', [])),
            agent_version=data.get('agent_version'),
            logged_in_user=data.get('logged_in_user', ''),
            device_fingerprint=fp,
            platform=data.get('platform', 'windows'),
            asset_number=data.get('asset_number', ''),
            status='online',
            last_heartbeat_at=datetime.now(),
            first_seen_at=datetime.now(),
        )
        # UUID 与 API Key 关联
        key_record.uuid = new_uuid
        db.session.add(device)

        # 若提供了 asset_number，尝试关联固定资产
        asset_number = data.get('asset_number', '')
        if asset_number:
            asset = FixedAsset.query.filter_by(asset_number=asset_number).first()
            if asset:
                device.asset_id = asset.id
                device.asset_number = asset_number

    db.session.commit()

    # 获取心跳和上报间隔
    config = AgentConfig.get_config()
    heartbeat_interval = config.heartbeat_interval if config else 120
    report_interval = config.report_interval if hasattr(config, 'report_interval') and config.report_interval else 3600

    return jsonify(success=True, data={
        'agent_id': device.agent_id,
        'uuid': device.uuid,
        'heartbeat_interval': heartbeat_interval,
        'report_interval': report_interval,
    })
```

#### 4.3.2 心跳上报

```
POST /api/agent/heartbeat
Headers: X-Agent-API-Key: AGENT_xxx
Body:
{
    "agent_id": "ag_abc123",
    "uuid": "550e8400-e29b-41d4-a716-446655440000",
    "logged_in_user": "zhangsan",
    "timestamp": "2026-09-08T10:30:00Z",
    "location": "3号楼201室",
    "department": "行政部",
    "responsible_person": "张三",
    "command_results": [
        {"command": "report_now", "status": "ok"}
    ],
    "info_changed": false,           // 设备信息是否变更
    "info": { ... }                  // 可选，info_changed=true时携带完整信息
}

Response:
{
    "success": true,
    "data": {
        "heartbeat_interval": 120,  // 服务器可动态调整心跳间隔
        "config_update": {           // 可选，服务器迁移或配置变更时下发
            "server_url": "http://new-server:35168",  // 可选，新服务器地址
            "heartbeat_interval": 180                  // 可选，动态调整心跳间隔
        },
        "commands": [                // 服务器下发的控制指令
            {"type": "report_now"},
            {"type": "update_interval", "params": {"interval": 60}}
        ]
    }
}
```

**逻辑**：
1. 验证 API Key
2. 通过 `agent_id` 查找设备记录
3. 校验 `uuid` 与记录中的 `uuid` 一致（防止 `agent_id` 被窃取后伪造）
4. 若 `uuid` 不匹配，返回 401 错误，要求重新注册
5. 更新 `agent_devices` 表的 `last_heartbeat_at` 和 `status='online'`，以及 `logged_in_user`
6. 如果 `info_changed=true`，同步更新设备信息字段
7. **双向同步校验**：比较 agent_devices 与关联 fixed_assets 的三字段（location↔storage_location, department↔dept_using.name, responsible_person），若不一致则以 `updated_at` 较新者为准同步到另一侧
8. 记录心跳日志到 `agent_heartbeat_logs`（可配置是否记录）
9. 检查 agent_config 表中的 `migration_enabled` 和 `migration_new_url`，如果迁移已启用，在响应中附带 `config_update` 字段通知客户端切换到新服务器

#### 4.3.3 设备信息更新

```
POST /api/agent/report
Headers: X-Agent-API-Key: AGENT_xxx
Body:
{
    "agent_id": "ag_abc123",
    "hostname": "PC-DESKTOP-01",
    "os_name": "Windows 10 Pro",
    ... // 完整设备信息
}

Response:
{
    "success": true,
    "message": "设备信息已更新"
}
```

#### 4.3.4 离线通知

```
POST /api/agent/offline
Headers: X-Agent-API-Key: AGENT_xxx
Body:
{
    "agent_id": "ag_abc123",
    "reason": "shutdown"  // shutdown/restart/update
}

Response:
{
    "success": true
}
```

#### 4.3.5 管理端 API Key 管理（需登录）

```
GET  /api/agent/keys          # 列出所有API Key
POST /api/agent/keys          # 生成新API Key
PUT  /api/agent/keys/<id>     # 更新API Key（启用/禁用/备注）
DELETE /api/agent/keys/<id>   # 删除API Key
```

这些端点使用现有的 `@login_required` + `@require_permission('agent.manage')` 认证。

#### 4.3.6 设备状态查询（供前端使用）

```
GET /api/agent/devices?asset_number=ZC2026010001
GET /api/agent/devices/<agent_id>

Response:
{
    "success": true,
    "data": {
        "agent_id": "ag_abc123",
        "hostname": "PC-DESKTOP-01",
        "status": "online",
        "last_heartbeat_at": "2026-09-08T10:30:00",
        "os_name": "Windows 10 Pro",
        "cpu_model": "Intel(R) Core(TM) i7-10700",
        "total_memory_mb": 16384,
        "asset_number": "ZC2026010001",
        "asset_id": 42,
        "asset_name": "办公电脑"
    }
}
```

#### 4.3.7 Agent 下载端点

##### 通用客户端下载

```
GET /api/agent/download
Headers: Cookie (需登录认证 + agent.manage 权限)
Response: application/zip, 文件名 asset-agent.zip

逻辑：
1. 验证用户已登录且有 agent.manage 权限
2. 使用管理页面配置的 server_url 和 api_key（用户可在管理页面自定义注入值）
3. 如果未自定义，使用当前服务器地址和新建的 API Key
4. 生成 config.json（包含 server_url、api_key、heartbeat_interval，不含 asset_number）
5. 将 static/agent/asset-agent.exe + config.json 打包成 zip
6. 返回 zip 下载
```

```python
# blueprints/agent/agent_api.py 中的通用下载端点
@agent_api_bp.route('/download', methods=['GET'])
@login_required
@require_permission('agent.manage')
def download_agent():
    """下载通用Asset Agent客户端（动态注入配置打包为zip，不关联具体设备）"""
    agent_path = os.path.join(current_app.static_folder, 'agent', 'asset-agent.exe')
    if not os.path.exists(agent_path):
        return jsonify({"success": False, "message": "Agent文件不存在，请联系管理员"}), 404

    # 读取管理页面配置的注入值（用户可自定义）
    from models.agent.agent_config import AgentConfig
    inject_server_url = AgentConfig.get_value('inject_server_url', default='')
    inject_api_key = AgentConfig.get_value('inject_api_key', default='')

    # 如果未配置注入值，使用当前服务器地址和新建 API Key
    if not inject_server_url:
        server_host = request.host.split(':')[0] if ':' in request.host else request.host
        server_port = request.host.split(':')[1] if ':' in request.host else '35168'
        scheme = request.scheme
        inject_server_url = f"{scheme}://{server_host}:{server_port}"

    if not inject_api_key:
        api_key_str = f"AGENT_{secrets.token_hex(16)}"
        key_record = AgentApiKey(
            api_key=api_key_str,
            name=f"通用下载 - {request.remote_addr}",
            is_active=True,
            created_by=getattr(request, 'user_id', None),
        )
        db.session.add(key_record)
        db.session.commit()
    else:
        api_key_str = inject_api_key

    # 生成 config.json（不含 asset_number）
    config_data = {
        "server_url": inject_server_url,
        "api_key": api_key_str,
        "heartbeat_interval": 120,
        "asset_number": "",
        "location": "",
        "department": "",
        "responsible_person": ""
    }

    # 打包为 zip
    memory_zip = io.BytesIO()
    with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(agent_path, 'asset-agent.exe')
        zf.writestr('config.json', json.dumps(config_data, indent=4, ensure_ascii=False))
    memory_zip.seek(0)

    return send_file(
        memory_zip,
        as_attachment=True,
        download_name='asset-agent.zip',
        mimetype='application/zip'
    )
```

##### 资产关联客户端下载

```
GET /api/agent/download/<asset_number>
Headers: Cookie (需登录认证 + agent.manage 权限)
Response: application/zip, 文件名 asset-agent-{asset_number}.zip

逻辑：
1. 验证用户已登录且有 agent.manage 权限
2. 验证 asset_number 对应的固定资产存在且类别为"电脑"
3. 使用管理页面配置的 server_url 和 api_key
4. 从固定资产记录中读取 storage_location/dept_using.name/responsible_person（映射为 location/department/responsible_person）
5. 生成 config.json（包含 server_url、api_key、heartbeat_interval、asset_number、location、department、responsible_person）
6. 将 static/agent/asset-agent.exe + config.json 打包成 zip
7. 返回 zip 下载

> **双向同步说明**：下载时从固定资产读取的三字段值会被写入 agent_devices 表。此后若固定资产侧或 Agent 侧修改了这三字段，心跳或手动同步时会按 `updated_at` 时间戳比较，以较新者为准同步到另一侧。
```

```python
@agent_api_bp.route('/download/<asset_number>', methods=['GET'])
@login_required
@require_permission('agent.manage')
def download_agent_for_asset(asset_number):
    """下载资产关联Asset Agent客户端（config.json包含asset_number及资产的手动字段，自动关联）"""
    from models.fixed_asset.fixed_asset import FixedAsset
    asset = FixedAsset.query.filter_by(asset_number=asset_number).first()
    if not asset:
        return jsonify({"success": False, "message": "固定资产不存在"}), 404
    if asset.category != '电脑':
        return jsonify({"success": False, "message": "仅电脑类资产支持Agent下载"}), 400

    agent_path = os.path.join(current_app.static_folder, 'agent', 'asset-agent.exe')
    if not os.path.exists(agent_path):
        return jsonify({"success": False, "message": "Agent文件不存在，请联系管理员"}), 404

    # 读取管理页面配置的注入值
    from models.agent.agent_config import AgentConfig
    inject_server_url = AgentConfig.get_value('inject_server_url', default='')
    inject_api_key = AgentConfig.get_value('inject_api_key', default='')

    if not inject_server_url:
        server_host = request.host.split(':')[0] if ':' in request.host else request.host
        server_port = request.host.split(':')[1] if ':' in request.host else '35168'
        scheme = request.scheme
        inject_server_url = f"{scheme}://{server_host}:{server_port}"

    if not inject_api_key:
        api_key_str = f"AGENT_{secrets.token_hex(16)}"
        key_record = AgentApiKey(
            api_key=api_key_str,
            name=f"资产关联 - {asset_number}",
            is_active=True,
            created_by=getattr(request, 'user_id', None),
        )
        db.session.add(key_record)
        db.session.commit()
    else:
        api_key_str = inject_api_key

    # 从固定资产记录中读取手动字段（字段映射：storage_location→location, dept_using.name→department）
    location = asset.storage_location or ''
    department = asset.dept_using.name if asset.dept_using else ''
    responsible_person = asset.responsible_person or ''

    # 生成 config.json（含 asset_number + 手动字段）
    config_data = {
        "server_url": inject_server_url,
        "api_key": api_key_str,
        "heartbeat_interval": 120,
        "asset_number": asset_number,
        "location": location,
        "department": department,
        "responsible_person": responsible_person
    }

    # 打包为 zip
    memory_zip = io.BytesIO()
    with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(agent_path, 'asset-agent.exe')
        zf.writestr('config.json', json.dumps(config_data, indent=4, ensure_ascii=False))
    memory_zip.seek(0)

    return send_file(
        memory_zip,
        as_attachment=True,
        download_name=f'asset-agent-{asset_number}.zip',
        mimetype='application/zip'
    )
```

#### 4.3.8 停止与卸载脚本端点

```
GET /api/agent/stop-script
Headers: Cookie (需登录认证 + agent.manage 权限)
Response: application/octet-stream, 文件名 stop-agent.bat

GET /api/agent/uninstall-script
Headers: Cookie (需登录认证 + agent.manage 权限)
Response: application/octet-stream, 文件名 uninstall-agent.bat
```

```python
@agent_api_bp.route('/stop-script', methods=['GET'])
@login_required
@require_permission('agent.manage')
def download_stop_script():
    """下载停止Agent脚本"""
    script_content = """@echo off
chcp 65001 >nul
echo 正在停止 Asset Agent...
taskkill /IM asset-agent.exe /F >nul 2>&1
if %errorlevel% equ 0 (
    echo Asset Agent 已成功停止
) else (
    echo Asset Agent 未在运行或停止失败
)
timeout /t 3 >nul
"""
    return send_file(
        io.BytesIO(script_content.encode('utf-8')),
        as_attachment=True,
        download_name='stop-agent.bat',
        mimetype='application/octet-stream'
    )

@agent_api_bp.route('/uninstall-script', methods=['GET'])
@login_required
@require_permission('agent.manage')
def download_uninstall_script():
    """下载卸载Agent脚本"""
    script_content = """@echo off
chcp 65001 >nul
echo 正在卸载 Asset Agent...
:: 停止进程
taskkill /IM asset-agent.exe /F >nul 2>&1
:: 删除注册表自启键
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v AssetAgent /f >nul 2>&1
:: 删除配置目录
rd /s /q "%ProgramData%\\AssetAgent" 2>nul
:: 删除同目录配置文件
if exist "%~dp0config.json" del "%~dp0config.json" >nul 2>&1
echo.
echo Asset Agent 已卸载，请手动删除 asset-agent.exe 文件
echo.
timeout /t 5 >nul
"""
    return send_file(
        io.BytesIO(script_content.encode('utf-8')),
        as_attachment=True,
        download_name='uninstall-agent.bat',
        mimetype='application/octet-stream'
    )
```

#### 4.3.9 Agent 管理页面配置端点

```
GET /api/agent/config
Headers: Cookie (需登录认证 + agent.manage 权限)
Response:
{
    "success": true,
    "data": {
        "agent_enabled": true,                          // Agent系统全局开关（来自SystemConfig）
        "server_url": "http://192.168.1.100:35168",    // 当前服务器地址
        "inject_server_url": "",                        // 注入到下载客户端的服务器地址（空则使用当前服务器地址）
        "inject_api_key": "",                           // 注入到下载客户端的API Key（空则下载时新建）
        "migration_enabled": "false",                   // 是否启用服务器迁移通知
        "migration_new_url": "",                        // 服务器迁移目标URL
        "heartbeat_interval": "120",                    // Agent心跳间隔（秒）
        "offline_threshold": "360",                     // Agent离线判定阈值（秒）
        "heartbeat_log_enabled": "false",               // 是否记录心跳日志
        "heartbeat_log_retention_days": "30",           // 心跳日志保留天数
        "allow_remote_stop": "false",                   // 是否允许远程停止Agent
        "online_devices": 15,                           // 在线设备数
        "offline_devices": 5                            // 离线设备数
    }
}

PUT /api/agent/config
Headers: Cookie (需登录认证 + agent.manage 权限)
Body:
{
    "server_url": "http://192.168.1.100:35168",  // 可选，修改服务器地址
    "inject_server_url": "",                     // 可选，修改注入的服务器地址
    "inject_api_key": "",                        // 可选，修改注入的API Key
    "migration_enabled": "false",                // 可选，启用/禁用迁移通知
    "migration_new_url": "",                     // 可选，迁移目标URL
    "heartbeat_interval": "120",                 // 可选，心跳间隔（秒）
    "offline_threshold": "360",                  // 可选，离线判定阈值（秒）
    "heartbeat_log_enabled": "false",            // 可选，心跳日志开关
    "heartbeat_log_retention_days": "30",        // 可选，日志保留天数
    "allow_remote_stop": "false"                 // 可选，远程停止开关
}
Response:
{
    "success": true,
    "message": "配置已更新"
}

注：AGENT_ENABLED 全局开关不通过此端点修改，请使用 POST /api/agent/toggle 端点。
```

```python
@agent_api_bp.route('/config', methods=['GET'])
@login_required
@require_permission('agent.manage')
def get_agent_config():
    """获取Agent管理页面配置"""
    from models.system_config.system_config import SystemConfig
    from models.agent.agent_config import AgentConfig
    from models.agent.agent_device import AgentDevice
    from sqlalchemy import func

    # AGENT_ENABLED 保留在 SystemConfig（系统级开关）
    agent_enabled = SystemConfig.get_value('AGENT_ENABLED', default='true').lower() == 'true'
    # 其余配置从 agent_config 表读取
    server_url = AgentConfig.get_value('server_url', default='')
    inject_server_url = AgentConfig.get_value('inject_server_url', default='')
    inject_api_key = AgentConfig.get_value('inject_api_key', default='')
    migration_enabled = AgentConfig.get_value('migration_enabled', default='false')
    migration_new_url = AgentConfig.get_value('migration_new_url', default='')
    heartbeat_interval = AgentConfig.get_value('heartbeat_interval', default='120')
    offline_threshold = AgentConfig.get_value('offline_threshold', default='360')
    heartbeat_log_enabled = AgentConfig.get_value('heartbeat_log_enabled', default='false')
    heartbeat_log_retention_days = AgentConfig.get_value('heartbeat_log_retention_days', default='30')
    allow_remote_stop = AgentConfig.get_value('allow_remote_stop', default='false')

    online_count = AgentDevice.query.filter_by(status='online').count()
    offline_count = AgentDevice.query.filter_by(status='offline').count()

    return jsonify({
        "success": True,
        "data": {
            "agent_enabled": agent_enabled,
            "server_url": server_url,
            "inject_server_url": inject_server_url,
            "inject_api_key": inject_api_key,
            "migration_enabled": migration_enabled,
            "migration_new_url": migration_new_url,
            "heartbeat_interval": heartbeat_interval,
            "offline_threshold": offline_threshold,
            "heartbeat_log_enabled": heartbeat_log_enabled,
            "heartbeat_log_retention_days": heartbeat_log_retention_days,
            "allow_remote_stop": allow_remote_stop,
            "online_devices": online_count,
            "offline_devices": offline_count
        }
    })

@agent_api_bp.route('/config', methods=['PUT'])
@login_required
@require_permission('agent.manage')
def update_agent_config():
    """更新Agent管理页面配置（AGENT_ENABLED 请使用 /api/agent/toggle 端点）"""
    from models.agent.agent_config import AgentConfig
    data = request.get_json()

    # 所有配置项写入 agent_config 表
    config_map = {
        'server_url': 'server_url',
        'inject_server_url': 'inject_server_url',
        'inject_api_key': 'inject_api_key',
        'migration_enabled': 'migration_enabled',
        'migration_new_url': 'migration_new_url',
        'heartbeat_interval': 'heartbeat_interval',
        'offline_threshold': 'offline_threshold',
        'heartbeat_log_enabled': 'heartbeat_log_enabled',
        'heartbeat_log_retention_days': 'heartbeat_log_retention_days',
        'allow_remote_stop': 'allow_remote_stop',
    }
    for json_key, config_key in config_map.items():
        if json_key in data:
            AgentConfig.set_value(config_key, str(data[json_key]))

    return jsonify({"success": True, "message": "配置已更新"})
```

#### 4.3.10 Agent 系统开关切换端点

```
POST /api/agent/toggle
Headers: Cookie (需登录认证 + agent.manage 权限)
Body:
{
    "enabled": false   // true=启用，false=禁用
}
Response:
{
    "success": true,
    "message": "Agent系统已禁用"
}
```

**禁用效果**：Agent 系统禁用后，所有 Agent API 端点（注册、心跳、上报）返回 403 Forbidden，已运行的客户端将进入离线重试模式。

```python
@agent_api_bp.route('/toggle', methods=['POST'])
@login_required
@require_permission('agent.manage')
def toggle_agent_system():
    """切换Agent系统开关"""
    from models.system_config.system_config import SystemConfig
    data = request.get_json()
    enabled = data.get('enabled', True)
    SystemConfig.set_value('AGENT_ENABLED', str(enabled).lower())

    status_text = "启用" if enabled else "禁用"
    return jsonify({"success": True, "message": f"Agent系统已{status_text}"})
```

**Agent API 中间件增加全局开关检查**：

```python
# blueprints/agent/auth.py 中增加全局开关检查
def check_agent_enabled():
    """检查Agent系统是否启用，未启用时返回403"""
    from models.system_config.system_config import SystemConfig
    enabled = SystemConfig.get_value('AGENT_ENABLED', default='true').lower() == 'true'
    if not enabled:
        return jsonify({"success": False, "message": "Agent系统已禁用"}), 403
    return None

# 在注册、心跳、上报端点前调用
@agent_api_bp.route('/register', methods=['POST'])
@require_agent_key
def register():
    if err := check_agent_enabled():
        return err
    # ... 原有注册逻辑
```

#### 4.3.11 服务器迁移通知

管理员调用此 API 后，系统将迁移目标 URL 写入配置，所有在线 Agent 在下次心跳时收到 `config_update`，自动切换到新服务器。

```
POST /api/agent/migrate
Headers: Cookie (需登录 + fixed_asset.manage 权限)
Body:
{
    "new_server_url": "http://new-server:35168",
    "migrate_at": "2026-09-10T00:00:00Z"  // 可选，计划迁移时间
}

Response:
{
    "success": true,
    "data": {
        "notified_agents": 15,   // 已通知的在线Agent数量
        "total_agents": 20       // 总Agent数量
    }
}
```

**逻辑**：
1. 验证管理员登录状态和 `agent.manage` 权限
2. 验证 `new_server_url` 格式（仅允许 `http://` 或 `https://` 开头）
3. 将 `migration_new_url` 写入 agent_config 表，值为 `new_server_url`
4. 将 `migration_enabled` 写入 agent_config 表，值为 `true`
5. 如果指定了 `migrate_at`（计划迁移时间），仅在到达该时间后才启用迁移通知
6. 统计当前在线 Agent 数量，返回通知情况

**服务端心跳响应处理**（在 4.3.2 心跳端点中集成）：

```python
# blueprints/agent/agent_api.py 中的心跳端点迁移逻辑
from models.agent.agent_config import AgentConfig

def _get_migration_config():
    """获取迁移配置，如果迁移已启用则返回新URL"""
    enabled = AgentConfig.get_value('migration_enabled', default='false')
    if enabled.lower() != 'true':
        return None
    new_url = AgentConfig.get_value('migration_new_url', default='')
    if not new_url:
        return None
    return new_url

# 在心跳响应中附带 config_update
@agent_api_bp.route('/heartbeat', methods=['POST'])
@require_agent_key
def heartbeat():
    # ... 原有心跳逻辑 ...
    
    response_data = {
        "heartbeat_interval": heartbeat_interval,
        "commands": []
    }
    
    # 检查是否有迁移通知
    migration_url = _get_migration_config()
    if migration_url:
        response_data["config_update"] = {
            "server_url": migration_url
        }
    
    return jsonify({"success": True, "data": response_data})
```

#### 4.3.12 设备手动字段更新端点

管理员可通过此端点在 Web 管理页面编辑已注册设备的手动录入字段（存放位置/部门/责任人），更新后自动同步到关联的固定资产记录。

```
PUT /api/agent/devices/<agent_id>/manual-fields
Headers: Cookie (需登录认证 + agent.manage 权限)
Body:
{
    "location": "3号楼201室",
    "department": "技术部",
    "responsible_person": "张三"
}

响应:
{
    "success": true,
    "message": "手动字段已更新，已同步到固定资产",
    "device": {
        "agent_id": "ag_xxxx",
        "location": "3号楼201室",
        "department": "技术部",
        "responsible_person": "张三"
    },
    "synced_asset": {
        "asset_number": "FA-2024-001",
        "storage_location": "3号楼201室",
        "department": "技术部",
        "responsible_person": "张三"
    }
}
```

```python
@agent_api_bp.route('/devices/<agent_id>/manual-fields', methods=['PUT'])
@login_required
@require_permission('agent.manage')
def update_device_manual_fields(agent_id):
    """更新设备的手动录入字段（存放位置/部门/责任人），并同步到固定资产"""
    from models.agent.agent_device import AgentDevice
    from models.fixed_asset.fixed_asset import FixedAsset
    from models.department.department import Department
    device = AgentDevice.query.filter_by(agent_id=agent_id).first()
    if not device:
        return jsonify({"success": False, "message": "设备不存在"}), 404

    data = request.get_json()
    new_location = data.get('location', device.location)
    new_department = data.get('department', device.department)
    new_responsible_person = data.get('responsible_person', device.responsible_person)

    # 更新 agent_devices 表
    device.location = new_location
    device.department = new_department
    device.responsible_person = new_responsible_person
    device.updated_at = datetime.now()

    # 双向同步：写回 fixed_assets 表
    synced_asset_info = None
    if device.asset_number:
        asset = FixedAsset.query.filter_by(asset_number=device.asset_number).first()
        if asset:
            asset.storage_location = new_location
            # department → dept_using.name：通过部门名查找 dept_id
            dept = Department.query.filter_by(name=new_department).first()
            if dept:
                asset.dept_id = dept.id
            asset.responsible_person = new_responsible_person
            asset.updated_at = datetime.now()
            synced_asset_info = {
                "asset_number": asset.asset_number,
                "storage_location": asset.storage_location,
                "department": new_department,
                "responsible_person": asset.responsible_person
            }

    db.session.commit()

    result = {
        "success": True,
        "message": "手动字段已更新" + ("，已同步到固定资产" if synced_asset_info else ""),
        "device": {
            "agent_id": device.agent_id,
            "location": device.location,
            "department": device.department,
            "responsible_person": device.responsible_person
        }
    }
    if synced_asset_info:
        result["synced_asset"] = synced_asset_info
    return jsonify(result)
```

#### 4.3.13 固定资产侧同步端点

当固定资产信息在固定资产管理模块中被修改时，通过此端点将三字段变更同步到关联的 agent_devices 记录。采用"最后修改者胜出"策略——比较两表的 `updated_at` 时间戳，以较新者为准。

```
POST /api/agent/sync-from-asset/<asset_id>
Headers: Cookie (需登录认证 + fixed_asset.manage 权限)
Body: (可选，若提供则覆盖资产当前值)
{
    "storage_location": "3号楼201室",
    "department": "技术部",
    "responsible_person": "张三"
}

响应:
{
    "success": true,
    "message": "已从固定资产同步到Agent设备",
    "synced_fields": {
        "location": "3号楼201室",
        "department": "技术部",
        "responsible_person": "张三"
    },
    "device_agent_id": "ag_xxxx"
}
```

```python
@agent_api_bp.route('/sync-from-asset/<int:asset_id>', methods=['POST'])
@login_required
@require_permission('fixed_asset.manage')
def sync_from_asset(asset_id):
    """从固定资产侧同步三字段到关联的 agent_devices 记录"""
    from models.fixed_asset.fixed_asset import FixedAsset
    from models.agent.agent_device import AgentDevice
    asset = FixedAsset.query.get(asset_id)
    if not asset:
        return jsonify({"success": False, "message": "固定资产不存在"}), 404

    # 查找关联的 agent_device
    device = AgentDevice.query.filter_by(asset_number=asset.asset_number).first()
    if not device:
        return jsonify({"success": False, "message": "该资产无关联的Agent设备"}), 404

    # 若请求体提供了字段值则使用请求体，否则从资产记录读取
    data = request.get_json(silent=True) or {}
    new_location = data.get('storage_location', asset.storage_location or '')
    new_department = data.get('department',
                              asset.dept_using.name if asset.dept_using else '')
    new_responsible_person = data.get('responsible_person',
                                      asset.responsible_person or '')

    # 双向同步：比较 updated_at，仅当资产侧更新时间 >= 设备侧时才同步
    if asset.updated_at and device.updated_at and asset.updated_at < device.updated_at:
        return jsonify({
            "success": False,
            "message": "Agent设备侧数据较新，跳过同步（最后修改者胜出）",
            "device_updated_at": device.updated_at.isoformat(),
            "asset_updated_at": asset.updated_at.isoformat()
        }), 409

    # 写入 agent_devices
    device.location = new_location
    device.department = new_department
    device.responsible_person = new_responsible_person
    device.updated_at = datetime.now()
    db.session.commit()

    return jsonify({
        "success": True,
        "message": "已从固定资产同步到Agent设备",
        "synced_fields": {
            "location": device.location,
            "department": device.department,
            "responsible_person": device.responsible_person
        },
        "device_agent_id": device.agent_id
    })
```

#### 4.3.14 编辑配置脚本下载端点

提供 `edit-info-agent.bat` 脚本的下载，管理员可分发给已部署 Agent 的用户，用户双击即可打开编辑窗口修改三字段。

```
GET /api/agent/edit-info-script
Headers: Cookie (需登录认证 + agent.manage 权限）
Response: application/octet-stream, 文件名 edit-info-agent.bat

逻辑：
1. 验证用户已登录且有 agent.manage 权限
2. 读取管理页面配置的 server_url（注入到脚本中，使脚本知道向哪个服务器请求编辑页面）
3. 生成 edit-info-agent.bat 脚本内容（含 server_url）
4. 返回 .bat 文件下载
```

```python
@agent_api_bp.route('/edit-info-script', methods=['GET'])
@login_required
@require_permission('agent.manage')
def download_edit_info_script():
    """下载编辑配置信息脚本（edit-info-agent.bat）"""
    from models.agent.agent_config import AgentConfig
    # 读取管理页面配置的服务器地址
    inject_server_url = AgentConfig.get_value('inject_server_url', default='')
    if not inject_server_url:
        server_host = request.host.split(':')[0] if ':' in request.host else request.host
        server_port = request.host.split(':')[1] if ':' in request.host else '35168'
        scheme = request.scheme
        inject_server_url = f"{scheme}://{server_host}:{server_port}"

    script_content = f"""@echo off
chcp 65001 >nul
echo ========================================
echo   Asset Agent - 编辑配置信息
echo ========================================
echo.

:: 获取当前目录
set "SCRIPT_DIR=%~dp0"
set "CONFIG_FILE=%SCRIPT_DIR%config.json"

:: 检查配置文件是否存在
if not exist "%CONFIG_FILE%" (
    echo [错误] 未找到 config.json，请确认此脚本与 asset-agent.exe 在同一目录
    pause
    exit /b 1
)

:: 通过命名管道发送编辑命令给运行中的 Agent
set "PIPE_NAME=\\\\.\\pipe\\AssetAgent"

:: 检查 Agent 是否在运行
tasklist /FI "IMAGENAME eq asset-agent.exe" 2>nul | find /I "asset-agent.exe" >nul
if %errorlevel% neq 0 (
    echo [错误] Asset Agent 未在运行，请先启动 Asset Agent
    pause
    exit /b 1
)

:: 发送编辑命令（Agent 会打开内嵌浏览器访问编辑页面）
echo 正在打开编辑窗口...
echo edit-info| "{inject_server_url}" > "%PIPE_NAME%"

echo 编辑窗口已打开，请在浏览器中修改信息后点击保存
echo 关闭此窗口不会影响编辑操作
timeout /t 5 >nul
"""
    return send_file(
        io.BytesIO(script_content.encode('utf-8')),
        as_attachment=True,
        download_name='edit-info-agent.bat',
        mimetype='application/octet-stream'
    )
```

---

## 5. 数据库模型设计

### 5.1 Agent API Key 表

文件路径：`models/agent/agent_api_key.py`

```python
class AgentApiKey(db.Model):
    """Agent API Key管理表"""
    __tablename__ = 'agent_api_keys'

    id = db.Column(db.Integer, primary_key=True)
    api_key = db.Column(db.String(64), unique=True, nullable=False,
                        comment='API Key，格式: AGENT_{32位hex}')
    agent_id = db.Column(db.String(64), nullable=True,
                         comment='关联的Agent设备ID，首次注册时回填')
    name = db.Column(db.String(100), nullable=True,
                     comment='Key名称，如"三楼办公区PC"')
    remark = db.Column(db.String(255), nullable=True,
                       comment='Key备注/说明')
    is_active = db.Column(db.Boolean, default=True, comment='是否启用')
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    expires_at = db.Column(db.DateTime, nullable=True, comment='过期时间，空表示永不过期')
    last_used_at = db.Column(db.DateTime, nullable=True, comment='最后使用时间')
    created_by = db.Column(db.Integer, nullable=True, comment='创建人用户ID')

    __table_args__ = (
        db.Index('idx_agent_api_key', 'api_key'),
        db.Index('idx_agent_api_key_active', 'is_active'),
    )
```

### 5.2 Agent 设备信息表

文件路径：`models/agent/agent_device.py`

```python
class AgentDevice(db.Model):
    """Agent设备信息表 - 存储被管理PC的基础信息"""
    __tablename__ = 'agent_devices'

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.String(64), unique=True, nullable=False,
                         comment='Agent唯一标识，由Agent首次生成')

    # 关联固定资产
    asset_id = db.Column(db.Integer, db.ForeignKey('fixed_assets.id'), nullable=True,
                         comment='关联固定资产ID')
    asset_number = db.Column(db.String(50), nullable=True,
                             comment='关联资产编号（冗余，便于查询）')

    # 主机信息
    hostname = db.Column(db.String(255), nullable=True, comment='主机名')

    # 操作系统信息
    os_name = db.Column(db.String(255), nullable=True, comment='操作系统名称')
    os_version = db.Column(db.String(100), nullable=True, comment='操作系统版本')
    os_arch = db.Column(db.String(20), nullable=True, comment='系统架构')

    # CPU信息
    cpu_model = db.Column(db.String(255), nullable=True, comment='CPU型号')
    cpu_cores = db.Column(db.Integer, nullable=True, comment='CPU核心数')

    # 内存信息
    total_memory_mb = db.Column(db.Integer, nullable=True, comment='总内存(MB)')
    available_memory_mb = db.Column(db.Integer, nullable=True, comment='可用内存(MB)')

    # 磁盘信息（JSON存储）
    disks = db.Column(db.Text, nullable=True, comment='磁盘列表JSON')

    # 网络信息
    mac_address = db.Column(db.String(17), nullable=True, comment='主MAC地址')
    ip_address = db.Column(db.String(45), nullable=True, comment='主IP地址(IPv4/IPv6)')
    network_interfaces = db.Column(db.Text, nullable=True, comment='网卡列表JSON')

    # Agent信息
    agent_version = db.Column(db.String(20), nullable=True, comment='Agent版本号')
    logged_in_user = db.Column(db.String(100), comment='当前登录用户名')
    device_fingerprint = db.Column(db.String(64), comment='设备指纹(SHA-256 hex)')
    uuid = db.Column(db.String(36), unique=True, comment='服务端分配UUID v4')
    platform = db.Column(db.String(20), default='windows', comment='客户端平台标识，当前仅支持windows')

    # 手动录入信息
    location = db.Column(db.String(200), nullable=True, comment='存放位置（手动录入，可通过Web管理页面编辑）')
    department = db.Column(db.String(100), nullable=True, comment='所属部门（手动录入，可通过Web管理页面编辑）')
    responsible_person = db.Column(db.String(50), nullable=True, comment='责任人（手动录入，可通过Web管理页面编辑）')

    # 在线状态
    status = db.Column(db.String(20), default='offline',
                       comment='在线状态: online/offline')
    last_heartbeat_at = db.Column(db.DateTime, nullable=True, comment='最后心跳时间')
    first_seen_at = db.Column(db.DateTime, default=datetime.now, comment='首次上报时间')

    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now,
                           comment='更新时间')

    # 关系
    asset = db.relationship('FixedAsset', foreign_keys=[asset_id], lazy='select')

    __table_args__ = (
        db.CheckConstraint(
            "status IN ('online', 'offline')",
            name='check_agent_device_status_valid'
        ),
        db.UniqueConstraint('agent_id'),
        db.UniqueConstraint('uuid'),
        db.Index('idx_agent_device_agent_id', 'agent_id'),
        db.Index('idx_agent_device_mac', 'mac_address'),
        db.Index('idx_agent_device_asset_id', 'asset_id'),
        db.Index('idx_agent_device_asset_number', 'asset_number'),
        db.Index('idx_agent_device_status', 'status'),
        db.Index('idx_agent_device_hostname', 'hostname'),
        db.Index('ix_agent_devices_device_fingerprint', 'device_fingerprint'),
        db.Index('ix_agent_devices_hostname_mac', 'hostname', 'mac_address'),
        db.Index('ix_agent_devices_platform', 'platform'),
    )
```

**双向同步字段映射表**

agent_devices 表与 fixed_assets 表的三字段双向同步映射关系如下：

| agent_devices 字段 | fixed_assets 字段 | 映射说明 |
|---|---|---|
| `location` | `storage_location` | 直接映射，字段名不同 |
| `department` | `dept_using.name` | FK→名称解析：agent_devices 存部门名称字符串，fixed_assets 通过 `dept_id` 关联 `departments` 表的 `name` |
| `responsible_person` | `responsible_person` | 直接映射，字段名相同 |

**同步策略**：最后修改者胜出——比较两表的 `updated_at` 时间戳，以较新者为准同步到另一侧。同步触发点包括：
1. 心跳时校验（§3.3 心跳端点补充）
2. 管理页面手动编辑（§4.3.12 端点）
3. 固定资产侧修改触发（§4.3.13 端点）

> **新增字段说明**：`logged_in_user`、`device_fingerprint`、`uuid`、`platform` 为自动采集字段，不参与双向同步。其中 `uuid` 由服务端在注册时生成并返回客户端，用于心跳校验防止 `agent_id` 伪造；`device_fingerprint` 由客户端生成，用于三级查重策略中的设备唯一性判断。

### 5.3 心跳日志表（简化）

文件路径：`models/agent/agent_heartbeat_log.py`

```python
class AgentHeartbeatLog(db.Model):
    """Agent心跳日志表 - 简化版，仅记录关键信息"""
    __tablename__ = 'agent_heartbeat_logs'

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.String(64), nullable=False, comment='Agent唯一标识')
    heartbeat_at = db.Column(db.DateTime, default=datetime.now, comment='心跳时间')
    ip_address = db.Column(db.String(45), nullable=True, comment='IP地址')

    __table_args__ = (
        db.Index('idx_heartbeat_agent_id', 'agent_id'),
        db.Index('idx_heartbeat_time', 'heartbeat_at'),
    )
```

**简化说明**：相比原方案，移除了 `hostname` 和 `info_changed` 冗余字段。`hostname` 可通过 JOIN `agent_devices` 表获取，`info_changed` 信息价值低且增加写入量。默认可通过 agent_config 表的 `heartbeat_log_enabled` 配置关闭心跳日志记录以减少数据库写入。

### 5.4 离线状态判定

服务端不依赖心跳日志表判断在线状态，而是通过定时任务扫描：

```python
# 定时任务（可集成到现有调度器中）
def update_offline_devices():
    """将超过3个心跳周期未上报的设备标记为offline"""
    threshold = datetime.now() - timedelta(seconds=360)  # 3 * 120秒
    AgentDevice.query.filter(
        AgentDevice.status == 'online',
        AgentDevice.last_heartbeat_at < threshold
    ).update({'status': 'offline'})
    db.session.commit()
```

### 5.5 Agent 管理页面配置存储

Agent 管理页面的全局开关使用现有的 `SystemConfig` 表存储，其余 Agent 业务配置存储在独立的 `agent_config` 表中（见§5.6）。

SystemConfig 中仅保留以下配置项：

| 配置键 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `AGENT_ENABLED` | bool | `true` | Agent 系统全局开关，禁用后所有 Agent API 返回 403 |

**说明**：
- `AGENT_ENABLED` 作为系统级开关保留在 SystemConfig 中，因为它是全局功能开关，与系统启停相关
- 其余 Agent 业务配置（服务器地址、注入配置、迁移配置、心跳参数等）已迁移至独立的 `agent_config` 表（见§5.6），由 Agent 管理页面直接管理

### 5.6 agent_config 表设计

为将 Agent 业务配置与系统级配置分离，新增独立的 `agent_config` 表，采用 key-value 结构存储 Agent 相关配置项，由 Agent 管理页面直接读写。

文件路径：`models/agent/agent_config.py`

```python
class AgentConfig(db.Model):
    """Agent业务配置表 - 独立于SystemConfig，专用于Agent管理"""
    __tablename__ = 'agent_config'

    id = db.Column(db.Integer, primary_key=True)
    config_key = db.Column(db.String(100), nullable=False, unique=True,
                           comment='配置键')
    config_value = db.Column(db.Text, nullable=False, default='',
                             comment='配置值')
    description = db.Column(db.String(200), nullable=True,
                            comment='配置说明')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now,
                           comment='更新时间')

    __table_args__ = (
        db.Index('idx_agent_config_key', 'config_key'),
    )

    @staticmethod
    def get_value(key, default=''):
        """获取配置值，不存在则返回默认值"""
        config = AgentConfig.query.filter_by(config_key=key).first()
        return config.config_value if config else default

    @staticmethod
    def set_value(key, value, description=None):
        """设置配置值，不存在则创建"""
        config = AgentConfig.query.filter_by(config_key=key).first()
        if config:
            config.config_value = str(value)
            if description:
                config.description = description
        else:
            config = AgentConfig(
                config_key=key,
                config_value=str(value),
                description=description
            )
            db.session.add(config)
        db.session.commit()
```

**初始化配置项**（首次运行时自动插入）：

| config_key | 默认值 | 说明 |
|------------|--------|------|
| `server_url` | `''` | 当前服务器地址（host:port），供管理页面显示和配置 |
| `inject_server_url` | `''` | 注入到下载客户端的服务器地址，空则使用当前服务器地址 |
| `inject_api_key` | `''` | 注入到下载客户端的 API Key，空则下载时新建 |
| `migration_new_url` | `''` | 服务器迁移目标URL（为空表示不迁移） |
| `migration_enabled` | `false` | 是否启用服务器迁移通知（在线Agent下次心跳时收到新地址） |
| `heartbeat_interval` | `120` | Agent心跳间隔（秒） |
| `offline_threshold` | `360` | Agent离线判定阈值（秒），超过此时间无心跳则标记为离线 |
| `heartbeat_log_enabled` | `false` | 是否记录心跳日志（关闭可减少数据库写入） |
| `heartbeat_log_retention_days` | `30` | 心跳日志保留天数 |
| `allow_remote_stop` | `false` | 是否允许服务端远程停止/重启Agent（安全开关，默认关闭） |

**初始化SQL**：

```sql
INSERT INTO agent_config (config_key, config_value, description) VALUES
    ('server_url', '', '当前服务器地址（host:port）'),
    ('inject_server_url', '', '注入到下载客户端的服务器地址'),
    ('inject_api_key', '', '注入到下载客户端的API Key'),
    ('migration_new_url', '', '服务器迁移目标URL'),
    ('migration_enabled', 'false', '是否启用服务器迁移通知'),
    ('heartbeat_interval', '120', 'Agent心跳间隔（秒）'),
    ('offline_threshold', '360', 'Agent离线判定阈值（秒）'),
    ('heartbeat_log_enabled', 'false', '是否记录心跳日志'),
    ('heartbeat_log_retention_days', '30', '心跳日志保留天数'),
    ('allow_remote_stop', 'false', '是否允许服务端远程停止Agent');
```

**与 SystemConfig 的分工**：
- `SystemConfig`：仅保留 `AGENT_ENABLED` 全局开关，属于系统级配置
- `AgentConfig`：存储所有 Agent 业务配置，由 Agent 管理页面直接管理
- 两者接口一致（`get_value` / `set_value`），但数据源不同，便于独立管理和扩展

---

## 6. 前端展示设计

### 6.1 固定资产列表页

文件：`templates/fixed_asset_manage/fixed_asset_manage.html`

在资产列表表格中新增"设备状态"列：

```html
<!-- 在表头添加 -->
<th>设备状态</th>

<!-- 在数据行添加 -->
<td>
  {% if device_status_map.get(asset.id) == 'online' %}
    <span class="badge bg-success">在线</span>
  {% elif device_status_map.get(asset.id) == 'offline' %}
    <span class="badge bg-secondary">离线</span>
  {% else %}
    <span class="badge bg-light text-muted">未绑定</span>
  {% endif %}
</td>
```

### 6.2 固定资产详情页

文件：`templates/fixed_asset_manage/fixed_asset_detail.html`

#### 6.2.1 下载关联客户端按钮

当资产类别为"电脑"时，在详情页操作区显示"下载关联客户端"按钮：

```html
{% if asset.category == '电脑' %}
<a href="/api/agent/download/{{ asset.asset_number }}" class="btn btn-primary btn-sm">
    <i class="bi bi-download me-1"></i>下载关联客户端
</a>
{% endif %}
```

**说明**：
- 仅当 `asset.category == '电脑'` 时显示按钮，其他类别不显示
- 点击后调用 `GET /api/agent/download/<asset_number>` 端点，下载包含 `asset_number` 的关联客户端
- 下载的 `config.json` 中包含 `asset_number` 字段，客户端注册时自动关联到该固定资产
- 下载的 `config.json` 中还包含该资产的存放位置、部门、责任人信息（从固定资产记录中读取），客户端安装后这些字段自动填充，无需手动录入
- 需要用户已登录且具有 `agent.manage` 权限

#### 6.2.2 设备信息卡片

在详情页添加"设备信息"卡片，展示关联设备的实时状态和硬件信息：

```html
<!-- 设备信息卡片 -->
<div class="card mt-3" id="device-info-card" style="display:none;">
  <div class="card-header">
    <h5 class="mb-0">
      <i class="bi bi-pc-display me-2"></i>设备信息
      <span id="device-status-badge" class="badge ms-2"></span>
    </h5>
  </div>
  <div class="card-body">
    <div class="row">
      <div class="col-md-6">
        <table class="table table-sm">
          <tr><td width="120">主机名</td><td id="dev-hostname">-</td></tr>
          <tr><td>操作系统</td><td id="dev-os">-</td></tr>
          <tr><td>CPU</td><td id="dev-cpu">-</td></tr>
          <tr><td>内存</td><td id="dev-memory">-</td></tr>
      </div>
      <div class="col-md-6">
        <table class="table table-sm">
          <tr><td width="120">IP地址</td><td id="dev-ip">-</td></tr>
          <tr><td>MAC地址</td><td id="dev-mac">-</td></tr>
          <tr><td>磁盘</td><td id="dev-disks">-</td></tr>
          <tr><td>最后心跳</td><td id="dev-heartbeat">-</td></tr>
        </table>
      </div>
    </div>
  </div>
</div>
```

### 6.3 Agent 管理页面

文件：`templates/agent_manage/agent_manage.html`

页面路径：`/agent_manage/`，权限要求：`agent.manage`

**配置存储说明**：Agent 管理页面的配置分为两部分存储：
- **全局开关**（`AGENT_ENABLED`）：存储在 `SystemConfig` 表，属于系统级配置
- **业务配置**（服务器地址、注入配置、迁移配置、心跳参数等）：存储在独立的 `agent_config` 表（见§5.6），由管理页面直接读写

#### 页面布局

```
┌─────────────────────────────────────────────────────────────┐
│  Agent 管理页面                                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─ 全局开关 ────────────────────────────────────────────┐  │
│  │  Agent 系统：[启用/禁用 开关]                          │  │
│  │  禁用后所有Agent心跳返回403，不处理注册/心跳/上报       │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ 服务器配置 ──────────────────────────────────────────┐  │
│  │  当前服务器地址：[http://192.168.1.100:35168]  [保存]  │  │
│  │  修改后新下载的客户端使用新地址                         │  │
│  │  已运行的客户端通过心跳响应的 config_update 更新        │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ API Key 管理 ────────────────────────────────────────┐  │
│  │  [创建新Key]                                           │  │
│  │  ┌──────┬──────────┬──────┬──────┬──────────┬──────┐  │  │
│  │  │ 名称 │ Key(脱敏) │ 状态 │设备数│ 创建时间 │ 操作 │  │  │
│  │  ├──────┼──────────┼──────┼──────┼──────────┼──────┤  │  │
│  │  │ ...  │ AGENT_*** │ 启用 │  3   │ 2026-09 │ 编辑 │  │  │
│  │  └──────┴──────────┴──────┴──────┴──────────┴──────┘  │  │
│  │                                                        │  │
│  │  注入配置：                                             │  │
│  │  下载时注入的服务器地址：[自定义地址]  [使用当前服务器]  │  │
│  │  下载时注入的API Key：  [自定义Key]   [新建Key]        │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ 下载区 ──────────────────────────────────────────────┐  │
│  │  [下载通用客户端]  [下载停止脚本]  [下载卸载脚本]      │  │
│  │  [下载编辑配置脚本]                                   │  │
│  │                                                        │  │
│  │  通用客户端：只注入 server_url + api_key，不关联设备    │  │
│  │  停止脚本：stop-agent.bat，强制终止Agent进程            │  │
│  │  卸载脚本：uninstall-agent.bat，清理注册表和配置文件     │  │
│  │  编辑配置脚本：edit-info-agent.bat，双击修改三字段信息   │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ 设备状态概览 ────────────────────────────────────────┐  │
│  │  在线设备：15 台  离线设备：5 台  [查看详情]           │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  [全局设置]  链接到 /agent_manage/settings                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 全局开关区域

```html
<!-- 全局开关 -->
<div class="card mb-3">
  <div class="card-header"><h5 class="mb-0"><i class="bi bi-power me-2"></i>全局开关</h5></div>
  <div class="card-body">
    <div class="form-check form-switch">
      <input class="form-check-input" type="checkbox" id="agent-enabled-switch"
             onchange="toggleAgentSystem(this.checked)">
      <label class="form-check-label" for="agent-enabled-switch">启用 Agent 系统</label>
    </div>
    <small class="text-muted">禁用后所有Agent心跳返回403，不处理注册/心跳/上报</small>
  </div>
</div>
```

#### 服务器配置区域

```html
<!-- 服务器配置 -->
<div class="card mb-3">
  <div class="card-header"><h5 class="mb-0"><i class="bi bi-gear me-2"></i>服务器配置</h5></div>
  <div class="card-body">
    <div class="row mb-2">
      <label class="col-sm-3 col-form-label">当前服务器地址</label>
      <div class="col-sm-6">
        <input type="text" class="form-control" id="server-url" placeholder="http://192.168.1.100:35168">
      </div>
      <div class="col-sm-3">
        <button class="btn btn-primary" onclick="saveServerConfig()">保存</button>
      </div>
    </div>
    <small class="text-muted">修改后新下载的客户端使用新地址，已运行的客户端通过心跳响应的 config_update 更新</small>
  </div>
</div>
```

#### API Key 管理区域

```html
<!-- API Key 管理 -->
<div class="card mb-3">
  <div class="card-header d-flex justify-content-between align-items-center">
    <h5 class="mb-0"><i class="bi bi-key me-2"></i>API Key 管理</h5>
    <button class="btn btn-sm btn-primary" onclick="createNewKey()">创建新Key</button>
  </div>
  <div class="card-body">
    <!-- Key 列表表格 -->
    <table class="table table-sm">
      <thead><tr><th>名称</th><th>Key(脱敏)</th><th>状态</th><th>关联设备数</th><th>创建时间</th><th>操作</th></tr></thead>
      <tbody id="api-keys-table"><!-- 动态填充 --></tbody>
    </table>

    <!-- 注入配置 -->
    <hr>
    <h6>下载时注入配置</h6>
    <small class="text-muted">可自定义下载客户端时注入的server_url和api_key，不一定使用当前服务器地址和新建Key</small>
    <div class="row mt-2">
      <label class="col-sm-3 col-form-label">注入服务器地址</label>
      <div class="col-sm-6">
        <input type="text" class="form-control" id="inject-server-url" placeholder="留空则使用当前服务器地址">
      </div>
      <div class="col-sm-3">
        <button class="btn btn-outline-secondary btn-sm" onclick="resetInjectServerUrl()">使用当前服务器</button>
      </div>
    </div>
    <div class="row mt-2">
      <label class="col-sm-3 col-form-label">注入API Key</label>
      <div class="col-sm-6">
        <input type="text" class="form-control" id="inject-api-key" placeholder="留空则下载时新建Key">
      </div>
      <div class="col-sm-3">
        <button class="btn btn-outline-secondary btn-sm" onclick="resetInjectApiKey()">新建Key</button>
      </div>
    </div>
  </div>
</div>
```

#### 下载区域

```html
<!-- 下载区 -->
<div class="card mb-3">
  <div class="card-header"><h5 class="mb-0"><i class="bi bi-download me-2"></i>下载</h5></div>
  <div class="card-body">
    <a href="/api/agent/download" class="btn btn-primary me-2">
      <i class="bi bi-pc-display me-1"></i>下载通用客户端
    </a>
    <a href="/api/agent/stop-script" class="btn btn-outline-warning me-2">
      <i class="bi bi-stop-circle me-1"></i>下载停止脚本
    </a>
    <a href="/api/agent/uninstall-script" class="btn btn-outline-danger me-2">
      <i class="bi bi-trash me-1"></i>下载卸载脚本
    </a>
    <a href="/api/agent/edit-info-script" class="btn btn-outline-info">
      <i class="bi bi-pencil-square me-1"></i>下载编辑配置脚本
    </a>
    <div class="mt-2">
      <small class="text-muted">
        通用客户端：只注入 server_url + api_key，不关联具体设备，安装后需手动关联<br>
        停止脚本：强制终止Agent进程<br>
        卸载脚本：清理注册表自启键和配置文件，需手动删除exe<br>
        编辑配置脚本：双击打开编辑窗口，修改存放位置/部门/责任人，修改后自动同步到固定资产
      </small>
    </div>
  </div>
</div>
```

#### 设备状态概览

```html
<!-- 设备状态概览 -->
<div class="card mb-3">
  <div class="card-header"><h5 class="mb-0"><i class="bi bi-diagram-3 me-2"></i>设备状态概览</h5></div>
  <div class="card-body">
    <div class="row text-center">
      <div class="col-md-4">
        <h3 id="online-count">-</h3>
        <small class="text-success">在线设备</small>
      </div>
      <div class="col-md-4">
        <h3 id="offline-count">-</h3>
        <small class="text-secondary">离线设备</small>
      </div>
      <div class="col-md-4">
        <a href="/agent_manage/devices" class="btn btn-outline-primary btn-sm">查看设备详情</a>
      </div>
    </div>
  </div>
</div>

<div class="text-center mt-3">
  <a href="/agent_manage/settings" class="btn btn-outline-primary">
    <i class="bi bi-gear me-1"></i>全局设置
  </a>
</div>
```

#### 设备手动字段编辑模态框

在设备列表的每一行增加"编辑"按钮，点击弹出模态框，可编辑 location/department/responsible_person：

```html
<!-- 编辑手动字段模态框 -->
<div class="modal fade" id="editManualFieldsModal" tabindex="-1">
  <div class="modal-dialog">
    <div class="modal-content">
      <div class="modal-header">
        <h5 class="modal-title">编辑设备手动信息</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
      </div>
      <div class="modal-body">
        <input type="hidden" id="edit-agent-id">
        <div class="mb-3">
          <label class="form-label">存放位置</label>
          <input type="text" class="form-control" id="edit-location" placeholder="如：3号楼201室">
        </div>
        <div class="mb-3">
          <label class="form-label">所属部门</label>
          <input type="text" class="form-control" id="edit-department" placeholder="如：技术部">
        </div>
        <div class="mb-3">
          <label class="form-label">责任人</label>
          <input type="text" class="form-control" id="edit-responsible-person" placeholder="如：张三">
        </div>
        <div class="alert alert-info small mb-0">
          <i class="bi bi-info-circle me-1"></i>
          修改后自动同步到关联的固定资产记录（存放位置/部门/责任人），采用"最后修改者胜出"策略。
        </div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">取消</button>
        <button type="button" class="btn btn-primary" onclick="saveManualFields()">保存</button>
      </div>
    </div>
  </div>
</div>
```

### 6.4 JavaScript 查询逻辑

在固定资产详情页的 JS 中添加：

```javascript
// 查询设备信息
async function loadDeviceInfo(assetId) {
    try {
        const resp = await fetch(`/api/agent/devices?asset_id=${assetId}`);
        const data = await resp.json();
        if (data.success && data.data) {
            const dev = data.data;
            document.getElementById('device-info-card').style.display = '';
            document.getElementById('device-status-badge').textContent =
                dev.status === 'online' ? '在线' : '离线';
            document.getElementById('device-status-badge').className =
                'badge ms-2 ' + (dev.status === 'online' ? 'bg-success' : 'bg-secondary');
            document.getElementById('dev-hostname').textContent = dev.hostname || '-';
            document.getElementById('dev-os').textContent =
                (dev.os_name || '') + ' ' + (dev.os_version || '');
            document.getElementById('dev-cpu').textContent = dev.cpu_model || '-';
            document.getElementById('dev-memory').textContent =
                dev.total_memory_mb ? (dev.total_memory_mb / 1024).toFixed(1) + ' GB' : '-';
            document.getElementById('dev-ip').textContent = dev.ip_address || '-';
            document.getElementById('dev-mac').textContent = dev.mac_address || '-';
            document.getElementById('dev-disks').textContent = dev.disks || '-';
            document.getElementById('dev-heartbeat').textContent =
                dev.last_heartbeat_at ? new Date(dev.last_heartbeat_at).toLocaleString() : '-';
        }
    } catch (e) {
        console.log('未查询到设备信息');
    }
}
```

**Agent 管理页面 - 设备手动字段编辑 JavaScript**：

```javascript
// 编辑设备手动字段（打开模态框并填充当前值）
function editManualFields(agentId, location, department, responsiblePerson) {
    document.getElementById('edit-agent-id').value = agentId;
    document.getElementById('edit-location').value = location || '';
    document.getElementById('edit-department').value = department || '';
    document.getElementById('edit-responsible-person').value = responsiblePerson || '';
    new bootstrap.Modal(document.getElementById('editManualFieldsModal')).show();
}

// 保存设备手动字段
async function saveManualFields() {
    const agentId = document.getElementById('edit-agent-id').value;
    const data = {
        location: document.getElementById('edit-location').value,
        department: document.getElementById('edit-department').value,
        responsible_person: document.getElementById('edit-responsible-person').value
    };
    const resp = await fetch(`/api/agent/devices/${agentId}/manual-fields`, {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    });
    const result = await resp.json();
    if (result.success) {
        bootstrap.Modal.getInstance(document.getElementById('editManualFieldsModal')).hide();
        loadDeviceOverview(); // 刷新设备列表
    } else {
        alert(result.message || '更新失败');
    }
}
```

### 6.5 Agent 全局设置页面

文件：`templates/agent_manage/agent_settings.html`

页面路径：`/agent_manage/settings`，权限要求：`agent.manage`

**设计目的**：将 `agent_config` 表中的所有配置项按功能分组集中展示，提供统一的全局客户端行为控制界面。AGENT_ENABLED 开关因存储在 SystemConfig 中，单独调用 `/api/agent/toggle` 端点。

#### 页面布局

```
┌─────────────────────────────────────────────────────────────┐
│  Agent 全局设置                              [恢复默认]     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  在线设备：15 台   离线设备：5 台                            │
│                                                             │
│  ┌─ 基础设置 ────────────────────────────────────────────┐  │
│  │  Agent 系统开关：  [启用/禁用 开关]                    │  │
│  │  服务器地址：      [http://192.168.1.100:35168]       │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ 心跳与在线检测 ──────────────────────────────────────┐  │
│  │  心跳间隔（秒）：  [120]  范围 30-600                  │  │
│  │  离线判定阈值（秒）：[360]  范围 60-1800               │  │
│  │  说明：超过此时间未收到心跳则判定为离线                │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ 日志设置 ────────────────────────────────────────────┐  │
│  │  心跳日志记录：    [关/开 开关]  默认关闭              │  │
│  │  日志保留天数：    [30]  范围 1-365                    │  │
│  │  说明：开启后每次心跳记录日志，用于调试；保留天数到期  │  │
│  │        自动清理                                        │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ 远程控制 ────────────────────────────────────────────┐  │
│  │  允许远程停止：    [关/开 开关]  默认关闭              │  │
│  │  说明：开启后可通过管理页面远程停止客户端进程          │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ 服务器迁移 ──────────────────────────────────────────┐  │
│  │  启用迁移通知：    [关/开 开关]  默认关闭              │  │
│  │  新服务器地址：    [https://new-server.example.com]    │  │
│  │                     （仅迁移启用时可编辑）             │  │
│  │  说明：启用后，客户端心跳响应中包含新服务器地址，      │  │
│  │        客户端自动迁移                                  │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌─ 下载注入配置 ────────────────────────────────────────┐  │
│  │  注入服务器地址：  [  ]  留空使用当前服务器地址        │  │
│  │  注入API Key：    [  ]  留空则下载时新建Key            │  │
│  │  说明：下载客户端时注入的配置，可自定义指向其他服务器  │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│                                        [保存所有设置]       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 完整 HTML 代码

```html
{% extends "base.html" %}
{% block title %}Agent 全局设置{% endblock %}
{% block content %}
<div class="container py-4">
  <div class="d-flex justify-content-between align-items-center mb-4">
    <h3><i class="bi bi-gear me-2"></i>Agent 全局设置</h3>
    <button class="btn btn-outline-secondary" onclick="resetDefaults()">
      <i class="bi bi-arrow-counterclockwise me-1"></i>恢复默认
    </button>
  </div>

  <!-- 设备统计 -->
  <div class="row mb-4">
    <div class="col-md-6">
      <div class="card">
        <div class="card-body text-center">
          <h4 id="settings-online-count">-</h4>
          <small class="text-success">在线设备</small>
        </div>
      </div>
    </div>
    <div class="col-md-6">
      <div class="card">
        <div class="card-body text-center">
          <h4 id="settings-offline-count">-</h4>
          <small class="text-secondary">离线设备</small>
        </div>
      </div>
    </div>
  </div>

  <form id="agent-settings-form">

    <!-- 基础设置 -->
    <div class="card mb-3">
      <div class="card-header"><h5 class="mb-0"><i class="bi bi-sliders me-2"></i>基础设置</h5></div>
      <div class="card-body">
        <div class="mb-3">
          <div class="form-check form-switch">
            <input class="form-check-input" type="checkbox" id="setting-agent-enabled"
                   onchange="toggleAgentSystem(this.checked)">
            <label class="form-check-label" for="setting-agent-enabled">Agent 系统开关</label>
          </div>
          <small class="text-muted">禁用后所有Agent心跳返回403，不处理注册/心跳/上报</small>
        </div>
        <div class="mb-3">
          <label class="form-label">服务器地址</label>
          <input type="text" class="form-control" name="server_url" id="setting-server-url"
                 placeholder="http://192.168.1.100:35168">
          <small class="text-muted">修改后新下载的客户端使用新地址，已运行的客户端通过心跳响应的 config_update 更新</small>
        </div>
      </div>
    </div>

    <!-- 心跳与在线检测 -->
    <div class="card mb-3">
      <div class="card-header"><h5 class="mb-0"><i class="bi bi-heart-pulse me-2"></i>心跳与在线检测</h5></div>
      <div class="card-body">
        <div class="mb-3">
          <label class="form-label">心跳间隔（秒）</label>
          <input type="number" class="form-control" name="heartbeat_interval" id="setting-heartbeat-interval"
                 min="30" max="600" value="120">
          <small class="text-muted">Agent 发送心跳的间隔时间，范围 30-600 秒，默认 120</small>
        </div>
        <div class="mb-3">
          <label class="form-label">离线判定阈值（秒）</label>
          <input type="number" class="form-control" name="offline_threshold" id="setting-offline-threshold"
                 min="60" max="1800" value="360">
          <small class="text-muted">超过此时间未收到心跳则判定为离线，范围 60-1800 秒，默认 360</small>
        </div>
      </div>
    </div>

    <!-- 日志设置 -->
    <div class="card mb-3">
      <div class="card-header"><h5 class="mb-0"><i class="bi bi-journal-text me-2"></i>日志设置</h5></div>
      <div class="card-body">
        <div class="mb-3">
          <div class="form-check form-switch">
            <input class="form-check-input" type="checkbox" name="heartbeat_log_enabled"
                   id="setting-heartbeat-log-enabled">
            <label class="form-check-label" for="setting-heartbeat-log-enabled">心跳日志记录</label>
          </div>
          <small class="text-muted">开启后每次心跳记录日志，用于调试；关闭可减少数据库写入</small>
        </div>
        <div class="mb-3">
          <label class="form-label">日志保留天数</label>
          <input type="number" class="form-control" name="heartbeat_log_retention_days"
                 id="setting-log-retention-days" min="1" max="365" value="30">
          <small class="text-muted">保留天数到期自动清理，范围 1-365 天，默认 30</small>
        </div>
      </div>
    </div>

    <!-- 远程控制 -->
    <div class="card mb-3">
      <div class="card-header"><h5 class="mb-0"><i class="bi bi-remote me-2"></i>远程控制</h5></div>
      <div class="card-body">
        <div class="form-check form-switch">
          <input class="form-check-input" type="checkbox" name="allow_remote_stop"
                 id="setting-allow-remote-stop">
          <label class="form-check-label" for="setting-allow-remote-stop">允许远程停止</label>
        </div>
        <small class="text-muted">开启后可通过管理页面远程停止客户端进程（安全开关，默认关闭）</small>
      </div>
    </div>

    <!-- 服务器迁移 -->
    <div class="card mb-3">
      <div class="card-header"><h5 class="mb-0"><i class="bi bi-arrow-left-right me-2"></i>服务器迁移</h5></div>
      <div class="card-body">
        <div class="mb-3">
          <div class="form-check form-switch">
            <input class="form-check-input" type="checkbox" name="migration_enabled"
                   id="setting-migration-enabled"
                   onchange="toggleMigrationUrl(this.checked)">
            <label class="form-check-label" for="setting-migration-enabled">启用迁移通知</label>
          </div>
          <small class="text-muted">启用后，客户端心跳响应中包含新服务器地址，客户端自动迁移</small>
        </div>
        <div class="mb-3">
          <label class="form-label">新服务器地址</label>
          <input type="text" class="form-control" name="migration_new_url" id="setting-migration-new-url"
                 placeholder="https://new-server.example.com" disabled>
          <small class="text-muted">仅迁移启用时可编辑</small>
        </div>
      </div>
    </div>

    <!-- 下载注入配置 -->
    <div class="card mb-3">
      <div class="card-header"><h5 class="mb-0"><i class="bi bi-download me-2"></i>下载注入配置</h5></div>
      <div class="card-body">
        <div class="mb-3">
          <label class="form-label">注入服务器地址</label>
          <input type="text" class="form-control" name="inject_server_url" id="setting-inject-server-url"
                 placeholder="留空使用当前服务器地址">
          <small class="text-muted">下载客户端时注入的服务器地址，留空则使用当前服务器地址</small>
        </div>
        <div class="mb-3">
          <label class="form-label">注入 API Key</label>
          <input type="text" class="form-control" name="inject_api_key" id="setting-inject-api-key"
                 placeholder="留空则下载时新建Key">
          <small class="text-muted">下载客户端时注入的 API Key，留空则下载时自动新建</small>
        </div>
      </div>
    </div>

    <!-- 保存按钮 -->
    <div class="text-end">
      <button type="button" class="btn btn-primary btn-lg" onclick="saveAllSettings()">
        <i class="bi bi-check-lg me-1"></i>保存所有设置
      </button>
    </div>

  </form>
</div>
{% endblock %}
```

#### JavaScript 逻辑

```javascript
// 默认配置值
const DEFAULTS = {
    heartbeat_interval: '120',
    offline_threshold: '360',
    heartbeat_log_enabled: false,
    heartbeat_log_retention_days: '30',
    allow_remote_stop: false,
    migration_enabled: false,
    migration_new_url: '',
    server_url: '',
    inject_server_url: '',
    inject_api_key: ''
};

// 页面加载时获取配置
async function loadSettings() {
    try {
        const resp = await fetch('/api/agent/config');
        const result = await resp.json();
        if (result.success) {
            const data = result.data;
            // 基础设置
            document.getElementById('setting-agent-enabled').checked = data.agent_enabled;
            document.getElementById('setting-server-url').value = data.server_url || '';
            // 心跳与在线检测
            document.getElementById('setting-heartbeat-interval').value =
                data.heartbeat_interval || DEFAULTS.heartbeat_interval;
            document.getElementById('setting-offline-threshold').value =
                data.offline_threshold || DEFAULTS.offline_threshold;
            // 日志设置
            document.getElementById('setting-heartbeat-log-enabled').checked =
                data.heartbeat_log_enabled === 'true' || data.heartbeat_log_enabled === true;
            document.getElementById('setting-log-retention-days').value =
                data.heartbeat_log_retention_days || DEFAULTS.heartbeat_log_retention_days;
            // 远程控制
            document.getElementById('setting-allow-remote-stop').checked =
                data.allow_remote_stop === 'true' || data.allow_remote_stop === true;
            // 服务器迁移
            const migrationEnabled = data.migration_enabled === 'true' || data.migration_enabled === true;
            document.getElementById('setting-migration-enabled').checked = migrationEnabled;
            document.getElementById('setting-migration-new-url').value =
                data.migration_new_url || '';
            document.getElementById('setting-migration-new-url').disabled = !migrationEnabled;
            // 下载注入配置
            document.getElementById('setting-inject-server-url').value =
                data.inject_server_url || '';
            document.getElementById('setting-inject-api-key').value =
                data.inject_api_key || '';
            // 设备统计
            document.getElementById('settings-online-count').textContent =
                data.online_devices ?? '-';
            document.getElementById('settings-offline-count').textContent =
                data.offline_devices ?? '-';
        }
    } catch (e) {
        console.error('加载配置失败:', e);
        alert('加载配置失败，请刷新重试');
    }
}

// Agent 系统开关（单独调用 toggle 端点）
async function toggleAgentSystem(enabled) {
    try {
        const resp = await fetch('/api/agent/toggle', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({enabled: enabled})
        });
        const result = await resp.json();
        if (result.success) {
            showToast(enabled ? 'Agent 系统已启用' : 'Agent 系统已禁用');
        } else {
            // 恢复开关状态
            document.getElementById('setting-agent-enabled').checked = !enabled;
            alert(result.message || '操作失败');
        }
    } catch (e) {
        document.getElementById('setting-agent-enabled').checked = !enabled;
        alert('操作失败，请重试');
    }
}

// 迁移开关联动
function toggleMigrationUrl(enabled) {
    document.getElementById('setting-migration-new-url').disabled = !enabled;
    if (!enabled) {
        document.getElementById('setting-migration-new-url').value = '';
    }
}

// 保存所有设置（AGENT_ENABLED 除外，它通过 toggle 端点单独控制）
async function saveAllSettings() {
    // 数值范围校验
    const heartbeatInterval = parseInt(document.getElementById('setting-heartbeat-interval').value);
    const offlineThreshold = parseInt(document.getElementById('setting-offline-threshold').value);
    const logRetentionDays = parseInt(document.getElementById('setting-log-retention-days').value);

    if (heartbeatInterval < 30 || heartbeatInterval > 600) {
        alert('心跳间隔范围为 30-600 秒');
        return;
    }
    if (offlineThreshold < 60 || offlineThreshold > 1800) {
        alert('离线判定阈值范围为 60-1800 秒');
        return;
    }
    if (logRetentionDays < 1 || logRetentionDays > 365) {
        alert('日志保留天数范围为 1-365 天');
        return;
    }

    const data = {
        server_url: document.getElementById('setting-server-url').value.trim(),
        heartbeat_interval: String(heartbeatInterval),
        offline_threshold: String(offlineThreshold),
        heartbeat_log_enabled: document.getElementById('setting-heartbeat-log-enabled').checked ? 'true' : 'false',
        heartbeat_log_retention_days: String(logRetentionDays),
        allow_remote_stop: document.getElementById('setting-allow-remote-stop').checked ? 'true' : 'false',
        migration_enabled: document.getElementById('setting-migration-enabled').checked ? 'true' : 'false',
        migration_new_url: document.getElementById('setting-migration-new-url').value.trim(),
        inject_server_url: document.getElementById('setting-inject-server-url').value.trim(),
        inject_api_key: document.getElementById('setting-inject-api-key').value.trim()
    };

    try {
        const resp = await fetch('/api/agent/config', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        const result = await resp.json();
        if (result.success) {
            showToast('设置已保存');
        } else {
            alert(result.message || '保存失败');
        }
    } catch (e) {
        alert('保存失败，请重试');
    }
}

// 恢复默认值
async function resetDefaults() {
    if (!confirm('确定恢复所有设置为默认值？此操作将保存默认值到服务器。')) {
        return;
    }
    // 恢复表单默认值
    document.getElementById('setting-server-url').value = DEFAULTS.server_url;
    document.getElementById('setting-heartbeat-interval').value = DEFAULTS.heartbeat_interval;
    document.getElementById('setting-offline-threshold').value = DEFAULTS.offline_threshold;
    document.getElementById('setting-heartbeat-log-enabled').checked = DEFAULTS.heartbeat_log_enabled;
    document.getElementById('setting-log-retention-days').value = DEFAULTS.heartbeat_log_retention_days;
    document.getElementById('setting-allow-remote-stop').checked = DEFAULTS.allow_remote_stop;
    document.getElementById('setting-migration-enabled').checked = DEFAULTS.migration_enabled;
    document.getElementById('setting-migration-new-url').value = DEFAULTS.migration_new_url;
    document.getElementById('setting-migration-new-url').disabled = true;
    document.getElementById('setting-inject-server-url').value = DEFAULTS.inject_server_url;
    document.getElementById('setting-inject-api-key').value = DEFAULTS.inject_api_key;
    // 保存到服务器
    await saveAllSettings();
}

// Toast 提示
function showToast(message) {
    const toast = document.createElement('div');
    toast.className = 'toast align-items-center text-bg-success border-0 position-fixed top-0 end-0 m-3';
    toast.style.zIndex = '9999';
    toast.innerHTML = `<div class="d-flex"><div class="toast-body">${message}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
    document.body.appendChild(toast);
    const bsToast = new bootstrap.Toast(toast, {delay: 2000});
    bsToast.show();
    toast.addEventListener('hidden.bs.toast', () => toast.remove());
}

// 页面加载
document.addEventListener('DOMContentLoaded', loadSettings);
```

---

## 7. 打包集成方案

### 7.1 整体流程

```
1. C 项目编译一次通用二进制（不含任何服务器信息）
         │
         v
2. 将 asset-agent.exe 复制到 static/agent/ 目录
         │
         v
3. PyInstaller 打包 Flask 应用（包含 static/agent/asset-agent.exe）
         │
         v
4. Inno Setup 打包安装程序
         │
         v
5. 用户下载时，Flask 动态生成 config.json + exe 打包为 zip
```

**关键变化**：C 项目只需编译一次通用二进制，无需每次部署重新编译。服务器配置在下载时动态注入，而非编译时嵌入。

### 7.2 Agent 独立构建

Agent 作为独立 C 项目构建，生成单个通用 `.exe` 文件（不含任何服务器配置）：

```bash
# 在 asset-agent/ 目录下
# 64位版本（Win7+ 64位）
gcc -Wall -O2 -DAGENT_VERSION=\"1.0.0\" -mwindows -o asset-agent.exe \
    main.c config.c collector.c collect_user.c fingerprint.c reporter.c service.c \
    autostart.c setup_ui.c cli.c ipc.c info_ui.c cJSON.c \
    -lwininet -ladvapi32 -lcrypt32 -lole32 -liphlpapi -lwtsapi32
# 产物: asset-agent.exe
# 预期体积: 1~3 MB（静态链接 + strip 优化后）

# 32位版本（XP~Win11 全系统兼容）
gcc -Wall -O2 -DAGENT_VERSION=\"1.0.0\" -m32 -mwindows -o asset-agent-x86.exe \
    main.c config.c collector.c collect_user.c fingerprint.c reporter.c service.c \
    autostart.c setup_ui.c cli.c ipc.c info_ui.c cJSON.c \
    -lwininet -ladvapi32 -lcrypt32 -lole32 -liphlpapi -lwtsapi32 -lws2_32
# 产物: asset-agent-x86.exe
# 预期体积: 0.8~2 MB
```

构建完成后，将 `asset-agent.exe` 放入 `static/agent/` 目录即可。后续项目打包流程无需重新编译 C。

### 7.3 打包脚本

`Auto_Setup/build_agent.py` 仅负责编译和复制，不再生成嵌入配置：

```python
"""构建Asset Agent通用二进制（C/Win32 API版本）"""
import os
import sys
import subprocess
import shutil

AGENT_DIR = os.path.join(os.path.dirname(__file__), '..', 'asset-agent')
STATIC_AGENT_DIR = os.path.join(os.path.dirname(__file__), '..', 'static', 'agent')

SOURCES = [
    'main.c', 'config.c', 'collector.c', 'collect_user.c', 'fingerprint.c',
    'reporter.c', 'service.c', 'autostart.c', 'setup_ui.c', 'cli.c',
    'ipc.c', 'info_ui.c', 'cJSON.c'
]
LIBS = ['-lwininet', '-ladvapi32', '-lcrypt32', '-lole32', '-liphlpapi', '-lwtsapi32']

def build_agent(arch='x64'):
    """编译C Agent（通用二进制，不含服务器配置）"""
    print(f"正在编译 Asset Agent ({arch})...")
    output_name = 'asset-agent.exe' if arch == 'x64' else 'asset-agent-x86.exe'

    cmd = ['gcc', '-Wall', '-O2', '-DAGENT_VERSION=\"1.0.0\"']
    if arch == 'x86':
        cmd.append('-m32')
    cmd.append('-mwindows')
    cmd.extend(SOURCES)
    cmd.extend(['-o', output_name])
    cmd.extend(LIBS)
    if arch == 'x86':
        cmd.append('-lws2_32')

    result = subprocess.run(cmd, cwd=AGENT_DIR,
                            capture_output=True, text=True)
    if result.returncode != 0:
        print(f"编译失败:\n{result.stderr}")
        sys.exit(1)
    print("编译成功")
    return output_name

def copy_to_static(filename):
    """将编译产物复制到static目录"""
    os.makedirs(STATIC_AGENT_DIR, exist_ok=True)
    src = os.path.join(AGENT_DIR, filename)
    dst = os.path.join(STATIC_AGENT_DIR, filename)
    shutil.copy2(src, dst)
    print(f"已复制到: {dst}")

def main():
    # 步骤1: 编译64位通用Agent二进制
    output_64 = build_agent('x64')
    copy_to_static(output_64)

    # 步骤2（可选）: 编译32位版本（XP兼容）
    # output_32 = build_agent('x86')
    # copy_to_static(output_32)

    print(f"\n===== 构建完成 =====")
    print(f"Agent文件: {os.path.join(STATIC_AGENT_DIR, 'asset-agent.exe')}")
    print(f"注意: 服务器配置在用户下载时由Flask动态注入，无需编译时嵌入")

if __name__ == '__main__':
    main()
```

### 7.4 批处理脚本集成

修改 `Auto_Setup/直接打包成安装包单文件版.bat`（或新增专用脚本），在打包流程中增加：

```batch
REM ===== 步骤1: 构建Agent（仅首次或Agent代码更新时需要）=====
echo 正在构建Asset Agent...
python build_agent.py
if %ERRORLEVEL% NEQ 0 (
    echo Agent构建失败！
    pause
    exit /b 1
)

REM ===== 步骤2: 继续PyInstaller打包 =====
echo 正在打包Flask应用...
...

REM ===== 步骤3: Inno Setup打包 =====
echo 正在打包安装程序...
...
```

**注意**：Agent 二进制只需编译一次，后续项目打包时如果 Agent 代码未变更，可跳过步骤1直接使用已有的 `static/agent/asset-agent.exe`。C 编译需要安装 MinGW-w64 或 MSVC 工具链。

### 7.5 Inno Setup 脚本修改

在 `Auto_Setup/installer_script.iss` 中添加：

```iss
[Files]
; Asset Agent 程序文件（已包含在static目录中，PyInstaller会自动打包）
; 无需额外添加，Agent通过Flask路由 /api/agent/download 提供下载

[UninstallRun]
; 卸载时清理Agent自启动注册表项（如果Agent曾在本机运行）
Filename: "reg"; Parameters: "delete ""HKCU\Software\Microsoft\Windows\CurrentVersion\Run"" /v ""AssetAgent"" /f"; Flags: runhidden
```

**注意**：Agent 不再随安装程序自动安装到用户机器上，而是通过 Web 下载分发（zip 包含 exe + config.json）。安装程序仅需在卸载时清理可能存在的注册表项。

### 7.6 GitHub Actions CI/CD

利用 GitHub Actions 实现 Agent 二进制编译 → 服务端打包的完整依赖链。项目已有 `.github/workflows/build.yml` 包含 `build-windows`、`build-docker`、`build-android` 三个 job，需新增 `build-agent` job 作为前置依赖。

#### 7.6.1 整体流程

```
阶段1：构建Agent二进制（build-agent）
  │  编译 asset-agent.exe（x64 + x86）
  │  产物上传为 GitHub Artifact
  v
阶段2：服务端打包（依赖build-agent完成）
  ├── build-windows（PyInstaller + Inno Setup）
  ├── build-docker（Docker镜像构建）
  └── build-android（APK构建）
  │  下载Agent产物 → 放入 static/agent/
  │  随服务端一起打包分发
  v
阶段3：Release发布（可选，tag触发）
```

#### 7.6.2 Workflow 配置

修改 `.github/workflows/build.yml`，新增 `build-agent` job 并建立依赖关系：

```yaml
name: 自动化打包构建

on:
  push:
    branches: [ main, master ]
    tags: [ 'v*' ]
    paths:
      - 'agent/**'
      - 'static/agent/**'
      - '.github/workflows/build.yml'
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
      build_android:
        description: '构建 Android APK'
        required: false
        default: true
        type: boolean

jobs:
  # ============================================
  # 阶段1：构建 Agent 二进制
  # ============================================
  build-agent:
    name: 🔧 构建 Asset Agent
    runs-on: windows-latest
    strategy:
      matrix:
        arch: [x64, x86]
    steps:
      - name: 📥 检出代码
        uses: actions/checkout@v4

      - name: 🔧 Setup MinGW-w64
        uses: egor-tensin/setup-mingw@v2
        with:
          platform: ${{ matrix.arch }}

      - name: 🔨 Build Agent
        run: |
          cd agent
          gcc -o asset-agent.exe main.c config.c collect.c collect_user.c fingerprint.c http.c ipc.c cJSON/cJSON.c -lwininet -ladvapi32 -lkernel32 -lole32 -lwbemuuid -lwtsapi32 -m${{ matrix.arch == 'x86' && '32' || '64' }} -O2 -s

      - name: 📤 Upload Artifact
        uses: actions/upload-artifact@v4
        with:
          name: asset-agent-${{ matrix.arch }}
          path: agent/asset-agent.exe

  # ============================================
  # 阶段2：服务端打包（依赖Agent构建完成）
  # ============================================
  build-windows:
    name: 🖥️ Windows 打包
    needs: build-agent
    runs-on: windows-latest
    steps:
      - name: 📥 检出代码
        uses: actions/checkout@v4

      - name: 📥 Download Agent x64
        uses: actions/download-artifact@v4
        with:
          name: asset-agent-x64
          path: static/agent/

      - name: 📥 Download Agent x86
        uses: actions/download-artifact@v4
        with:
          name: asset-agent-x86
          path: static/agent/

      - name: ✅ Verify Agent binaries
        run: |
          dir static\agent\
          if not exist static\agent\asset-agent.exe exit 1

      # ... 后续 PyInstaller + Inno Setup 打包步骤保持不变 ...

  build-docker:
    name: 🐳 Docker 构建
    needs: build-agent
    runs-on: ubuntu-latest
    steps:
      - name: 📥 检出代码
        uses: actions/checkout@v4

      - name: 📥 Download Agent x64
        uses: actions/download-artifact@v4
        with:
          name: asset-agent-x64
          path: static/agent/

      - name: ✅ Verify Agent binary
        run: |
          ls -la static/agent/
          test -f static/agent/asset-agent.exe || exit 1

      # ... 后续 Docker build & push 步骤保持不变 ...

  build-android:
    name: 📱 Android APK 构建
    needs: build-agent
    runs-on: ubuntu-latest
    steps:
      - name: 📥 检出代码
        uses: actions/checkout@v4

      - name: 📥 Download Agent x64
        uses: actions/download-artifact@v4
        with:
          name: asset-agent-x64
          path: static/agent/

      # 将Agent二进制复制到安卓assets目录
      - name: 📋 Copy Agent to Android assets
        run: |
          mkdir -p android/app/src/main/assets/agent
          cp static/agent/asset-agent.exe android/app/src/main/assets/agent/

      # ... 后续 Gradle build 步骤保持不变 ...

  # ============================================
  # 阶段3：Release发布（tag触发）
  # ============================================
  release:
    name: 📦 发布 Release
    needs: [build-windows, build-docker, build-android]
    runs-on: ubuntu-latest
    if: startsWith(github.ref, 'refs/tags/agent-') || startsWith(github.ref, 'refs/tags/v')
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: asset-agent-x64

      - uses: actions/download-artifact@v4
        with:
          name: asset-agent-x86

      - name: Create Release
        uses: softprops/action-gh-release@v1
        with:
          files: asset-agent-*.exe
```

#### 7.6.3 触发策略

- **自动触发**：`agent/` 目录下代码变更时自动编译并触发服务端打包
- **手动触发**：GitHub Actions 页面手动点击 Run workflow，可选择构建平台
- **Release 触发**：推送 `agent-v*` 格式 tag 时自动创建 Release（仅发布Agent二进制）；推送 `v*` 格式 tag 时触发完整构建+发布

#### 7.6.4 产物使用

- Agent 构建产物自动上传为 GitHub Artifact
- 服务端打包 job 下载 Agent 产物后放入 `static/agent/` 目录，随服务端一起打包
- Docker 镜像通过 `COPY . .` 指令自动包含 `static/agent/` 目录
- Android APK 通过 gradle 构建步骤将 Agent 二进制复制到 `assets/agent/` 目录
- Release 版本可通过 GitHub Releases API 下载，实现服务端自动更新 Agent 二进制

### 7.7 Docker 集成

Docker 部署的是 Flask 服务端，Agent 二进制已内置在 Docker 镜像的 `static/agent/` 目录中。用户通过 Web 管理页面下载 Agent zip 包（Flask 动态生成），在 Windows 客户端机器上运行。Docker 容器不运行 Agent，Agent 运行在连接到 Docker 服务端的 Windows 客户端机器上。

#### 7.7.1 Docker 镜像构建集成

Agent 二进制通过项目已有的 `Auto_Setup/dockerfile` 中的 `COPY . .` 指令自动包含在 Docker 镜像中，无需额外配置。前提是构建前 `static/agent/asset-agent.exe` 已存在。

```dockerfile
# Auto_Setup/dockerfile 片段（已有配置，无需修改）
FROM python:3.8-slim
WORKDIR /app
COPY . .          # static/agent/asset-agent.exe 随项目一起复制到镜像中
# ... 后续 pip install 等步骤 ...
```

**前提条件**：Docker 镜像构建前，`static/agent/asset-agent.exe` 必须已编译完成。

#### 7.7.2 构建顺序保障

Docker 构建前需确保 Agent 二进制已编译。两种方式：

1. **本地构建**：先运行 `python Auto_Setup/build_agent.py` 编译 Agent 并复制到 `static/agent/`，再执行 `docker build`
2. **CI/CD**：GitHub Actions 中 `build-agent` job 先完成 Agent 编译，再执行 `build-docker` job（详见 §7.6）

#### 7.7.3 Docker 部署时的 Agent 分发

Docker 容器中的 Flask 通过 `/api/agent/download` 端点提供 Agent 下载，与 Windows 部署完全一致。用户在 Windows 客户端机器上下载 zip 包并运行，Agent 通过 HTTP 连接到 Docker 容器中的 Flask 服务端上报设备信息。

```
┌─────────────────┐     HTTP/HTTPS     ┌──────────────────────┐
│ Windows 客户端   │ ─────────────────> │ Docker 容器           │
│ Asset Agent     │ <───────────────── │ Flask 服务端          │
│ (asset-agent.exe)│   下载zip/上报心跳 │ /api/agent/*         │
└─────────────────┘                    │ static/agent/ 内置   │
                                       └──────────────────────┘
```

### 7.8 安卓端集成

安卓端部署的是 Flask 服务端（通过 Chaquopy 嵌入 Python 运行），不是 Agent 客户端。Agent 客户端仅支持 Windows。安卓服务端需要能分发 Agent 二进制给 Windows 客户端下载。

#### 7.8.1 方案说明

安卓端运行的是 Flask 服务端（通过 `android/` 目录中集成的 Chaquopy 运行 Python），与 Windows 和 Docker 部署的服务端功能完全一致。Agent 客户端仅支持 Windows 平台，安卓端不需要实现 Agent 采集功能。安卓服务端需要能将内置的 Agent 二进制通过 `/api/agent/download` 端点分发给 Windows 客户端下载。

#### 7.8.2 Agent 二进制内嵌方案

构建时将 `static/agent/asset-agent.exe` 复制到 `android/app/src/main/assets/agent/` 目录，Chaquopy 的 Python 运行时可通过 assets 路径访问。

```
android/app/src/main/assets/
└── agent/
    └── asset-agent.exe    # 从 static/agent/ 复制，构建前确保已编译
```

Chaquopy 访问 assets 文件的方式：
- 方式一：通过 `chaquopy.getAssets()` 获取 assets 路径
- 方式二：APK 安装后，将 assets 中的文件解压到应用内部存储，Flask 路由从内部存储读取

#### 7.8.3 安卓端 Flask 路由适配

安卓端 Flask 需要适配 Agent 二进制文件路径，因为 APK 中 assets 目录与 Windows/Docker 的 `static/agent/` 路径不同。

```python
# utils/android_adapter.py 中增加 Agent 二进制路径适配
def get_agent_binary_path():
    """获取 Agent 二进制文件路径（兼容 Windows 部署和安卓部署）"""
    if is_android():
        # 安卓：从内部存储读取（APK安装时已从assets解压）
        # Chaquopy 初始化时将 assets/agent/ 解压到内部存储
        import chaquopy
        internal_dir = chaquopy.getFilesDir()  # 应用内部存储
        return os.path.join(internal_dir, 'agent', 'asset-agent.exe')
    else:
        # Windows/Docker：直接从 static 目录读取
        return os.path.join(os.path.dirname(__file__), '..', 'static', 'agent', 'asset-agent.exe')
```

Flask 下载端点需调用 `get_agent_binary_path()` 获取文件路径：

```python
# blueprints/agent/agent_api.py 中下载端点适配
from utils.android_adapter import get_agent_binary_path

@agent_api.route('/api/agent/download', methods=['GET'])
def download_agent():
    agent_path = get_agent_binary_path()
    if not os.path.exists(agent_path):
        return jsonify({'error': 'Agent binary not found'}), 404
    # ... 后续生成 zip 下载逻辑 ...
```

#### 7.8.4 安卓构建集成

在 `android/app/build.gradle` 的 Chaquopy 配置中确保 `static/agent/` 被包含，或在 gradle 构建前自动复制 Agent 二进制到 assets 目录：

```groovy
// android/app/build.gradle 片段
android {
    // ...
    sourceSets {
        main {
            assets.srcDirs += ['src/main/assets']
        }
    }
}

// 构建前自动复制 Agent 二进制到 assets 目录
tasks.register('copyAgentBinary') {
    doLast {
        def agentDir = file('src/main/assets/agent')
        agentDir.mkdirs()
        def sourceFile = file('../../static/agent/asset-agent.exe')
        if (sourceFile.exists()) {
            copy {
                from sourceFile
                into agentDir
            }
            println "Agent binary copied to assets"
        } else {
            println "WARNING: Agent binary not found at ${sourceFile}"
        }
    }
}

// 确保 Chaquopy Python 初始化前复制完成
preBuild.dependsOn copyAgentBinary
```

#### 7.8.5 构建顺序

与 Docker 类似，APK 构建前需确保 Agent 二进制已编译：

1. **本地构建**：先运行 `python Auto_Setup/build_agent.py` 编译 Agent 并复制到 `static/agent/`，再执行 `./gradlew assembleRelease`
2. **CI/CD**：GitHub Actions 中 `build-agent` job 先完成 Agent 编译，再执行 `build-android` job（详见 §7.6），gradle 构建步骤自动将 Agent 二进制复制到 assets 目录

---

## 8. 安装与部署

### 8.1 一键安装流程

```
管理员在固定资产管理页面点击"下载Asset Agent"
         │
         v
浏览器下载 asset-agent.zip
         │
         v
用户解压得到 asset-agent.exe + config.json
         │
         v
双击运行 asset-agent.exe
         │
         ├── 同目录有 config.json（下载时注入）
         │       │
         │       v
         │   自动读取配置（server_url、api_key）
         │       │
         │       v
         │   配置同步到 C:\ProgramData\AssetAgent\config.json
         │       │
         │       v
         │   自动注册开机自启（注册表Run键）
         │       │
         │       v
         │   首次心跳 → POST /api/agent/register
         │       │
         │       v
         │   进入隐藏后台模式，常规心跳循环（每120秒）
         │
         └── 无 config.json（手动分发场景）
                │
                v
            弹出配置窗口，用户输入服务器地址和API Key
                │
                v
            点击确认，窗口消失
                │
                v
            配置保存到 C:\ProgramData\AssetAgent\config.json
                │
                v
            自动注册开机自启
                │
                v
            首次心跳 → POST /api/agent/register
                │
                v
            进入隐藏后台模式，常规心跳循环
```

### 8.2 Agent 运行特征

| 特征 | 说明 |
|------|------|
| 进程可见性 | 任务管理器中可见进程名 `asset-agent.exe`，无窗口 |
| 系统托盘 | 不创建系统托盘图标 |
| 内存占用 | 目标 < 3MB |
| CPU占用 | 空闲时接近 0%，心跳时短暂 CPU 活动 |
| 网络活动 | 每120秒一次 HTTP POST 请求 |
| 自启动 | 注册表 `HKCU\...\Run` 键，用户登录后自动启动 |
| 配置文件 | exe同目录 `config.json`（优先）或 `C:\ProgramData\AssetAgent\config.json` |
| 日志文件 | `C:\ProgramData\AssetAgent\agent.log`（最大10MB，保留3个） |
| 卸载方式 | 删除 exe 文件 + 清理注册表 Run 键 + 删除 ProgramData 目录 |

### 8.3 API Key 分发

**场景一：下载时自动注入**（推荐）
- 用户点击下载时，Flask 自动生成 API Key 并写入数据库
- API Key 随 config.json 与 exe 一起打包为 zip 返回
- 用户解压后直接运行，无需任何手动配置

**场景二：手动配置窗口**（兜底）
- 手动分发 exe（无 config.json）时，首次运行弹出配置窗口
- 管理员需提前在管理后台生成 API Key，告知用户
- 用户在配置窗口中输入服务器地址和 API Key
- 配置保存到本地，后续启动不再显示窗口

**场景三：资产编号关联**
- 下载时 config.json 中 `asset_number` 为空，用户可在管理后台手动关联
- 或在管理后台手动将设备与固定资产关联

### 8.4 停止与卸载 Agent

#### 8.4.1 停止 Agent

**推荐方式：使用管理页面下载的停止脚本**

在 Agent 管理页面（`/agent_manage/`）点击"下载停止脚本"按钮，获取 `stop-agent.bat`，双击运行即可停止 Agent 进程。此方式无需命令行知识，适合普通用户。

```bat
@echo off
chcp 65001 >nul
echo 正在停止 Asset Agent...
taskkill /IM asset-agent.exe /F >nul 2>&1
if %errorlevel% equ 0 (
    echo Asset Agent 已成功停止
) else (
    echo Asset Agent 未在运行或停止失败
)
timeout /t 3 >nul
```

**其他方式**：

```bash
# 方式一：CLI 命令（通过命名管道优雅退出）
asset-agent.exe --stop

# 方式二：任务管理器
# 在任务管理器中找到 asset-agent.exe，结束进程

# 方式三：命令行
taskkill /IM asset-agent.exe /F
```

#### 8.4.2 卸载 Agent

**推荐方式：使用管理页面下载的卸载脚本**

在 Agent 管理页面（`/agent_manage/`）点击"下载卸载脚本"按钮，获取 `uninstall-agent.bat`，双击运行即可完成卸载。脚本会自动停止进程、清理注册表自启键、删除配置目录。

```bat
@echo off
chcp 65001 >nul
echo 正在卸载 Asset Agent...
:: 停止进程
taskkill /IM asset-agent.exe /F >nul 2>&1
:: 删除注册表自启键
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v AssetAgent /f >nul 2>&1
:: 删除配置目录
rd /s /q "%ProgramData%\AssetAgent" 2>nul
:: 删除同目录配置文件
if exist "%~dp0config.json" del "%~dp0config.json" >nul 2>&1
echo.
echo Asset Agent 已卸载，请手动删除 asset-agent.exe 文件
echo.
timeout /t 5 >nul
```

**其他方式**：

```bash
# 方式一：CLI 命令（自动清理所有痕迹）
asset-agent.exe --uninstall

# 方式二：手动卸载
# 1. 停止 Agent 进程
taskkill /IM asset-agent.exe /F
# 2. 删除注册表自启键
reg delete "HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Run" /v AssetAgent /f
# 3. 删除 ProgramData 目录
rmdir /S /Q "C:\ProgramData\AssetAgent"
# 4. 删除 exe 所在目录
```

#### 8.4.3 编辑配置信息

已部署的 Agent 可通过 `edit-info-agent.bat` 脚本修改三字段信息（存放位置/部门/责任人），无需手动编辑 config.json。

**操作步骤**：
1. 从 Agent 管理页面下载 `edit-info-agent.bat` 脚本
2. 将脚本复制到 Agent 所在目录（与 `asset-agent.exe` 同目录）
3. 双击运行脚本，Agent 会打开内嵌浏览器显示编辑页面
4. 在编辑页面修改信息后点击保存
5. 保存后 Agent 更新本地 config.json 并通过心跳同步到服务端
6. 服务端收到更新后自动同步到关联的固定资产记录

**注意事项**：
- 脚本需要 Agent 正在运行才能工作（通过命名管道 IPC 通信）
- 修改后的信息会自动双向同步到固定资产表
- 如果脚本与 Agent 不在同一目录，需手动修改脚本中的路径

#### 8.4.4 远程停止

服务端可通过心跳指令下发 `stop` 命令远程停止 Agent（需在 agent_config 表中启用 `allow_remote_stop`）。

---

## 9. 安全考虑

### 9.1 API Key 安全

| 措施 | 说明 |
|------|------|
| Key 生成 | 使用 `secrets.token_hex(16)` 生成密码学安全的随机 Key，下载时动态生成 |
| Key 传输 | 支持 HTTPS 时通过加密通道传输；内网 HTTP 部署时依赖网络隔离 |
| Key 存储（下载注入） | 随 config.json 打包在 zip 中，用户解压后以文件形式存储；配置文件设置权限仅当前用户可读 |
| Key 存储（本地配置） | 配置文件存储在 `C:\ProgramData\AssetAgent\`，设置文件权限仅当前用户可读 |
| Key 轮换 | 支持通过管理后台禁用旧 Key、生成新 Key |
| Key 过期 | 支持设置过期时间，过期后 Agent 需重新下载获取新 Key |
| 速率限制 | API 端点实施请求频率限制，防止暴力破解 |
| 一次性下载 | 每次下载生成独立 API Key，避免多设备共用同一 Key |
| 权限控制 | Agent 管理页面及所有管理端 API（Key 管理、下载、配置等）均需 `agent.manage` 权限，确保仅授权用户可操作 |

### 9.2 通信安全

```
内网部署（默认）:
  Agent ──HTTP──> Server (端口35168)
  依赖内网隔离保障安全

外网/敏感部署:
  Agent ──HTTPS──> Nginx反向代理 ──HTTP──> Server
  在Nginx层终止TLS，Server无需修改
```

**Nginx 配置示例**：
```nginx
server {
    listen 443 ssl;
    server_name asset.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location /api/agent/ {
        proxy_pass http://127.0.0.1:35168;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

### 9.3 数据隐私

| 数据项 | 处理方式 |
|--------|----------|
| MAC地址 | 仅用于设备唯一标识，不对外暴露原始值 |
| IP地址 | 仅管理后台可见，API返回时脱敏处理 |
| 主机名 | 用于设备识别，管理后台可见 |
| 硬件信息 | 仅管理后台可见，用于资产核对 |

### 9.4 Agent 端安全

- 以当前用户权限运行，无需管理员权限（注册表 HKCU Run 键）
- 配置文件权限限制为仅当前用户可读（包括同目录 config.json 和 ProgramData 中的配置）
- 日志文件不记录 API Key 明文
- 进程异常退出时由心跳超时机制自动标记为离线
- 二进制经过 strip 优化（gcc -s 或 MSVC /RELEASE），增加逆向难度
- 通用二进制不含任何服务器信息，即使 exe 被单独获取也无法连接服务器
- 命名管道 `\\.\pipe\AssetAgent` 仅允许本机连接
- IPC 命令不携带敏感信息，管道通信不加密
- `--uninstall` 命令需管理员权限（清理 ProgramData 和注册表）

### 9.5 下载安全

**客户端下载安全**：
- 下载端点需登录认证 + `agent.manage` 权限（通用客户端和资产关联客户端均需此权限）
- 每次下载动态生成独立 API Key，避免多设备共用
- 返回 `application/zip` 格式，包含 exe + config.json，触发浏览器下载
- 文件路径校验，防止路径遍历攻击
- config.json 中的服务器地址基于当前请求的 host 自动生成（或使用管理页面配置的注入值），确保客户端连接到正确的服务器
- zip 包在内存中生成，不落盘，避免临时文件泄露

**脚本下载安全**：
- 停止脚本（`stop-agent.bat`）和卸载脚本（`uninstall-agent.bat`）下载端点需登录认证 + `agent.manage` 权限
- 脚本内容为固定模板，不接受用户输入参数，防止命令注入
- 脚本使用 `chcp 65001` 确保中文正确显示
- 卸载脚本仅清理注册表当前用户键（HKCU）和 ProgramData 目录，不涉及系统级操作
- 脚本返回 `Content-Type: application/octet-stream`，触发浏览器下载而非直接执行

### 9.6 迁移安全

| 措施 | 说明 |
|------|------|
| 权限控制 | 迁移通知 API（`POST /api/agent/migrate`）需管理员登录 + `fixed_asset.manage` 权限 |
| URL 格式验证 | 新服务器 URL 仅允许 `http://` 或 `https://` 开头，拒绝其他协议（如 `file://`、`ftp://`） |
| 可达性验证 | 客户端在切换前先验证新服务器可达（发送测试心跳），防止恶意重定向导致失联 |
| 失败自动回退 | 新服务器连续 3 次心跳失败后自动回退到旧地址，确保不会因迁移导致永久失联 |
| 迁移确认机制 | 客户端在新服务器首次心跳成功后发送迁移确认，旧服务器可标记该客户端已迁移 |
| 配置持久化 | 迁移 URL 写入本地配置文件，即使 Agent 重启也能记住新地址 |
| 操作审计 | 迁移操作记录到系统日志，包含操作人、目标URL、时间等信息 |

---

## 10. 开发计划

### 阶段一：C 客户端核心（2周）

| 任务 | 说明 |
|------|------|
| C 项目初始化 | 创建 `asset-agent/` 项目，配置 Makefile + cJSON 嵌入 |
| 系统信息采集模块 | 实现 `collector.c`，Win32 API 采集所有定义的信息项（含登录用户名采集 `collect_user.c`、设备指纹生成 `fingerprint.c`） |
| 配置管理模块 | 实现 `config.c`，cJSON 解析，支持多路径配置查找（同目录 > ProgramData > 配置窗口），设备指纹生成与缓存，UUID 存储与验证 |
| 首次运行配置窗口 | 实现 `setup_ui.c`，无配置文件时弹出最小配置窗口 |
| HTTP 上报模块 | 实现 `reporter.c`，WinINet 注册/心跳/信息更新请求 |
| 隐藏进程入口 | 实现 `main.c`，WinMain + ShowWindow(SW_HIDE) 无窗口运行 |
| 开机自启模块 | 实现 `autostart.c`，注册表 Run 键管理（RegOpenKeyExW） |
| IPC 命名管道通信 | 实现 `ipc.c`，CreateNamedPipeW 服务端与客户端通信 |
| CLI 命令 | 实现 `cli.c`，支持 --stop/--uninstall/--edit-info 命令 |
| 手动信息编辑窗口 | 实现 `info_ui.c`，编辑存放位置/部门/责任人 |
| 服务端远程控制指令处理 | 在心跳响应中解析 commands 字段并执行指令 |

### 阶段二：服务端开发（1.5周）

| 任务 | 说明 |
|------|------|
| 数据库模型 | 创建 `models/agent/` 目录，实现4个模型（AgentConfig配置表 + 简化心跳日志表） |
| API Blueprint | 创建 `blueprints/agent/agent_api.py`，实现所有API端点（含注册端点三级查重策略、UUID生成与API Key关联、心跳端点UUID校验） |
| 下载端点 | 实现 `/api/agent/download` 动态打包 exe + config.json 为 zip |
| 双向同步端点 | 实现 `/api/agent/sync-from-asset/<asset_id>` 固定资产侧同步，心跳时比较 updated_at 以较新者为准 |
| 编辑配置脚本下载端点 | 实现 `/api/agent/edit-info-script` 生成含 server_url 的 edit-info-agent.bat |
| API Key 管理 | 实现生成、验证、禁用逻辑 |
| 离线检测定时任务 | 实现超时设备自动标记为 offline（阈值360秒） |
| Blueprint 注册 | 在 `main.py` 中注册新 Blueprint |

### 阶段三：前端集成（1周）

| 任务 | 说明 |
|------|------|
| 列表页状态展示 | 固定资产列表添加"设备状态"列 |
| 详情页设备信息 | 固定资产详情页添加"设备信息"卡片 |
| 详情页下载按钮 | 固定资产详情页（资产类别为"电脑"时）添加"下载关联客户端"按钮，调用 `/api/agent/download/<asset_number>` |
| Agent 管理页面 | 创建 `templates/agent_manage/agent_manage.html`，实现全局开关、服务器配置、API Key 管理、注入配置、下载区（通用客户端/停止脚本/卸载脚本/编辑配置脚本）、设备状态概览、手动字段编辑模态框（含双向同步提示） |
| Agent 管理页面路由 | 创建 `blueprints/agent/agent_manage.py`，实现页面渲染和导航菜单集成 |
| API Key 管理页面 | 系统设置中添加 API Key 管理入口 |

### 阶段四：打包集成（1周）

| 任务 | 说明 |
|------|------|
| 构建脚本 | 实现 `Auto_Setup/build_agent.py`，C 编译通用二进制+复制到static |
| 批处理集成 | 修改打包批处理，加入Agent构建步骤（可选，已有二进制时可跳过） |
| static目录放置 | 确保 `static/agent/asset-agent.exe` 被PyInstaller打包 |
| 下载端点测试 | 测试下载端点动态生成 config.json 和 zip 打包 |
| 配置读取测试 | 测试同目录 config.json 优先读取、ProgramData 回退、配置窗口兜底 |
| GitHub Actions CI/CD | 配置 `.github/workflows/build-agent.yml`，自动编译 Agent 二进制 |
| Docker 镜像集成测试 | 验证 Docker 镜像中 Agent 二进制可正常下载 |
| 安卓服务端Agent集成 | 安卓APK内嵌Agent二进制，Flask路由适配assets路径 |

### 阶段五：测试与优化（1周）

| 任务 | 说明 |
|------|------|
| 端到端测试 | 安装→注册→心跳→前端展示→下载 |
| 双向同步测试 | 验证 Agent 侧/固定资产侧修改三字段后，另一侧自动同步（updated_at 时间戳比较） |
| 编辑配置脚本测试 | 验证 edit-info-agent.bat 双击后打开编辑窗口，保存后同步到服务端和固定资产 |
| 资源占用测试 | 验证内存 < 3MB，CPU空闲接近0% |
| 隐藏性测试 | 验证无窗口、无托盘图标、无控制台 |
| 自启动测试 | 重启后验证Agent自动运行 |
| 压力测试 | 多设备并发心跳测试 |
| 二进制优化 | 验证 gcc -s / MSVC /RELEASE strip 后体积 |

### 阶段六：文档与收尾（0.5周）

| 任务 | 说明 |
|------|------|
| 心跳日志清理 | 实现心跳日志自动清理（保留30天） |
| 用户文档 | Agent 下载和安装说明（页面内嵌） |
| 管理文档 | API Key 管理和设备关联说明 |

---

## 附录

### A. C 项目依赖

```
项目结构：
asset-agent/
├── main.c               # 入口，WinMain + ShowWindow(SW_HIDE)
├── config.c / config.h  # 配置管理（cJSON解析，设备指纹生成，UUID存储）
├── collector.c / .h     # 系统信息采集（Win32 API）
├── collect_user.c / .h  # 登录用户名采集（GetUserNameW / WTSQuerySessionInformationW）
├── fingerprint.c / .h   # 设备指纹生成（SHA-256硬件绑定哈希）
├── reporter.c / .h      # 上报逻辑（WinINet HTTP）
├── service.c / .h       # Agent主循环
├── autostart.c / .h     # 注册表自启动管理
├── setup_ui.c           # 首次运行配置窗口
├── cli.c                # CLI命令处理
├── ipc.c / ipc.h        # 进程间通信（命名管道）
├── info_ui.c            # 手动信息编辑窗口
├── cJSON.c / cJSON.h   # cJSON库（单文件嵌入，~500行）
├── Makefile             # MinGW-w64 构建脚本
└── resource.rc          # Windows资源文件（图标、版本信息）
```

**依赖说明**：

| 依赖 | 来源 | 用途 |
|------|------|------|
| `WinINet` | Windows 系统DLL | HTTP 请求（XP SP2+ 原生支持） |
| `cJSON` | 单文件嵌入 | JSON 序列化/反序列化（~500行，MIT许可） |
| `AdvAPI32` | Windows 系统DLL | 注册表操作（`RegOpenKeyExW`/`RegSetValueExW`） |
| `IPHLPAPI` | Windows 系统DLL | 网络适配器信息（`GetAdaptersInfo`） |
| `Kernel32` | Windows 系统DLL | 系统信息、文件操作 |
| `Crypt32` | Windows 系统DLL | 随机数生成（`CryptGenRandom`） |
| `Ole32` | Windows 系统DLL | COM初始化 |
| `WtsApi32` | Windows 系统DLL | 终端会话信息（`WTSGetActiveConsoleSessionId`/`WTSQuerySessionInformationW`，获取SYSTEM账户下实际登录用户名） |
| `AdvAPI32`（扩展） | Windows 系统DLL | SHA-256哈希（`CryptAcquireContext`/`CryptCreateHash`/`CryptHashData`，PROV_RSA_AES提供者）、登录用户名（`GetUserNameW`） |
| `Kernel32`（扩展） | Windows 系统DLL | 磁盘序列号（`GetVolumeInformationW`，设备指纹生成） |

**零外部依赖**：除 cJSON 单文件嵌入外，全部使用 Windows 系统 API，无需安装任何第三方库。

### B. 新增文件清单

```
models/agent/
├── __init__.py
├── agent_api_key.py          # API Key模型
├── agent_config.py           # Agent业务配置模型（独立于SystemConfig）
├── agent_device.py           # 设备信息模型
└── agent_heartbeat_log.py    # 心跳日志模型（简化版）

blueprints/agent/
├── __init__.py
├── agent_api.py              # Agent API端点（含下载端点、脚本端点、配置端点、设备手动字段更新端点、固定资产侧同步端点、编辑配置脚本下载端点）
├── agent_manage.py           # Agent管理页面路由（页面渲染、导航集成）
└── auth.py                   # API Key认证装饰器 + 全局开关检查

templates/agent_manage/
├── agent_manage.html         # Agent管理页面（全局开关、服务器配置、API Key管理、下载区、设备概览、设备手动字段编辑模态框）
└── agent_devices.html        # 设备详情列表页

asset-agent/                   # C项目根目录
├── Makefile                  # MinGW-w64 构建脚本
├── resource.rc               # Windows资源文件（图标、版本信息）
├── main.c                    # 入口，WinMain + ShowWindow(SW_HIDE) 隐藏窗口
├── config.c / config.h       # 配置管理（多路径查找：同目录 > ProgramData > 配置窗口，设备指纹生成与UUID存储）
├── collector.c / collector.h # 系统信息采集（Win32 API）
├── collect_user.c / collect_user.h # 登录用户名采集（GetUserNameW / WTSQuerySessionInformationW）
├── fingerprint.c / fingerprint.h   # 设备指纹生成（SHA-256硬件绑定哈希）
├── reporter.c / reporter.h   # 上报逻辑（WinINet HTTP）
├── service.c / service.h     # Agent主循环（心跳调度、离线恢复）
├── autostart.c / autostart.h # 注册表自启动管理（RegOpenKeyExW等）
├── setup_ui.c                # 首次运行配置窗口（无配置文件时的兜底）
├── cli.c                     # CLI命令处理（stop/uninstall/edit-info）
├── ipc.c / ipc.h             # 进程间通信（CreateFile/WriteFile命名管道）
├── info_ui.c                 # 手动信息编辑窗口（存放位置/部门/责任人）
└── cJSON.c / cJSON.h        # cJSON库（单文件嵌入，~500行）

static/agent/
└── asset-agent.exe           # 通用Agent二进制（不含服务器配置，下载时动态注入）

Auto_Setup/
└── build_agent.py            # Agent构建脚本（仅编译+复制，不含嵌入配置生成）

.github/
└── workflows/
    └── build-agent.yml       # GitHub Actions CI/CD（自动编译Agent二进制）

utils/android_agent_adapter.py    # 安卓端Agent二进制路径适配（如需）
```

### C. 权限注册扩展

在 `utils/auth.py` 的 `PERMISSIONS` 字典中添加：

```python
'agent': {
    'name': '资产代理管理',
    'actions': {
        'view': '查看',
        'manage': '管理',
        'create_key': '生成Key',
        'revoke_key': '吊销Key',
    }
},
```

> **第七次修订确认**：新增的两个端点无需注册新权限——`POST /api/agent/sync-from-asset/<asset_id>` 使用已有的 `fixed_asset.manage` 权限，`GET /api/agent/edit-info-script` 使用已有的 `agent.manage` 权限。

### D. SystemConfig 新增配置项

在 `models/system_config/system_config.py` 的 `_get_default_configs()` 中仅添加 `AGENT_ENABLED` 全局开关：

```python
# 资产代理配置 (category: agent) — 仅保留系统级全局开关
{
    'config_key': 'AGENT_ENABLED',
    'config_value': 'true',
    'config_type': 'bool',
    'category': 'agent',
    'description': 'Agent系统全局开关，禁用后所有Agent API返回403',
    'is_editable': True,
    'sort_order': 1,
},
```

> **注意**：其余 Agent 业务配置（`AGENT_SERVER_URL`、`AGENT_INJECT_SERVER_URL`、`AGENT_INJECT_API_KEY`、`AGENT_MIGRATION_NEW_URL`、`AGENT_MIGRATION_ENABLED`、`AGENT_HEARTBEAT_INTERVAL`、`AGENT_OFFLINE_THRESHOLD`、`AGENT_HEARTBEAT_LOG_ENABLED`、`AGENT_HEARTBEAT_LOG_RETENTION_DAYS`、`AGENT_ALLOW_REMOTE_STOP`）已迁移至独立的 `agent_config` 表，见§5.6。

### E. C 编译配置（Makefile）

```makefile
CC = gcc
CFLAGS = -Wall -O2 -DUNICODE -D_UNICODE -DAGENT_VERSION=\"1.0.0\"
LDFLAGS = -mwindows -lwininet -ladvapi32 -lcrypt32 -lole32 -liphlpapi -lwtsapi32

SOURCES = main.c config.c collector.c collect_user.c fingerprint.c reporter.c service.c \
          autostart.c setup_ui.c cli.c ipc.c info_ui.c cJSON.c
HEADERS = config.h collector.h collect_user.h fingerprint.h reporter.h service.h autostart.h ipc.h cJSON.h
OBJECTS = $(SOURCES:.c=.o)
TARGET = asset-agent.exe

all: $(TARGET)

$(TARGET): $(OBJECTS)
	$(CC) -o $@ $^ $(LDFLAGS)

%.o: %.c $(HEADERS)
	$(CC) $(CFLAGS) -c $< -o $@

# 64位版本（Win7+ 64位）
release-x64: clean
	$(CC) $(CFLAGS) $(SOURCES) $(LDFLAGS) -o asset-agent.exe

# 32位版本（XP~Win11 全系统）
release-x86: clean
	$(CC) $(CFLAGS) -m32 $(SOURCES) $(LDFLAGS) -lws2_32 -o asset-agent-x86.exe

clean:
	-del /Q *.o asset-agent.exe asset-agent-x86.exe 2>nul
```

**编译参数说明**：
- `-mwindows`：设置 Windows 子系统为 GUI，不创建控制台窗口
- `-m32`：32 位架构，支持 XP；默认 64 位架构仅 Win7+
- `-Wall -O2`：开启所有警告 + 二级优化
- `-DAGENT_VERSION=\"1.0.0\"`：通过宏定义注入版本号
- `-DUNICODE -D_UNICODE`：启用 Unicode 宽字符 API
- `-lwininet`：链接 WinINet 库（HTTP 通信）
- `-ladvapi32`：链接 AdvAPI32 库（注册表操作）
- `-lcrypt32`：链接 Crypt32 库（随机数生成）
- `-lole32`：链接 Ole32 库（COM 初始化）
- `-liphlpapi`：链接 IPHLPAPI 库（网络适配器信息）
- `-lwtsapi32`：链接 WtsApi32 库（终端会话信息，获取SYSTEM账户下实际登录用户名）

**MSVC 编译（可选）**：
```bash
# 64位版本，静态链接CRT（/MT），无运行时依赖
cl /O2 /MT /D AGENT_VERSION=\"1.0.0\" /DUNICODE /D_UNICODE ^
   main.c config.c collector.c collect_user.c fingerprint.c reporter.c service.c ^
   autostart.c setup_ui.c cli.c ipc.c info_ui.c cJSON.c ^
   /link /SUBSYSTEM:WINDOWS wininet.lib advapi32.lib crypt32.lib ole32.lib iphlpapi.lib wtsapi32.lib

# 32位版本，XP兼容（v141_xp工具集）
cl /O2 /MT /D AGENT_VERSION=\"1.0.0\" /DUNICODE /D_UNICODE ^
   main.c config.c collector.c collect_user.c fingerprint.c reporter.c service.c ^
   autostart.c setup_ui.c cli.c ipc.c info_ui.c cJSON.c ^
   /link /SUBSYSTEM:WINDOWS,5.01 wininet.lib advapi32.lib crypt32.lib ole32.lib iphlpapi.lib wtsapi32.lib
```
