# check_webview2_sh2

Windows 系统环境检查工具，用于检测运行依赖是否已安装。

## 功能

- **Windows 7** — 检查 SHA2 代码签名补丁（KB4474419 / KB4490628）是否已安装
- **Windows 10/11** — 检查 Microsoft Edge WebView2 运行时是否已安装
- 未安装时提供可点击的下载链接（网盘下载 + 官方下载）
- 检测结果文字可选中复制

## 界面

```
系统环境检查结果
─────────────────────────
操作系统:  Windows 10 x64 (Build 19045)
WebView2运行时:  未安装 ✗    官方下载  官方下载页面
                              [关闭]
```

```
系统环境检查结果
─────────────────────────
操作系统:  Windows 7 x86 (Build 7601)
SHA2代码签名补丁:  未安装 ✗    网盘下载 (x86)  官方下载
                              [关闭]
```

## 编译

### MSVC（推荐，CI 使用）

```cmd
rc resource.rc
cl check_env.c resource.res /MT /O2 /Fe:check_env.exe advapi32.lib version.lib shell32.lib comctl32.lib user32.lib gdi32.lib
```

### MinGW-w64

```sh
windres resource.rc -o resource.o
gcc check_env.c resource.o -static -mwindows -o check_env.exe -ladvapi32 -lversion -lshell32 -lcomctl32 -luser32 -lgdi32
```

## 技术细节

- 纯 Win32 API，无第三方依赖，单文件编译
- 使用 SysLink 控件实现可点击超链接（需 Common Controls v6 manifest）
- DPI 感知布局，支持高分辨率屏幕
- Unicode 转义序列硬编码中文，避免编码问题
- Windows 11 通过 Build 号（≥22000）正确识别
- 仅链接系统 DLL：advapi32、version、shell32、comctl32、user32、gdi32

## 项目结构

| 文件 | 说明 |
|------|------|
| `check_env.c` | 主程序源码 |
| `resource.rc` | 资源文件，引用 manifest |
| `app.manifest` | 应用清单，启用视觉样式和 DPI 感知 |
| `Makefile` | 支持 MinGW 和 MSVC 编译 |

## License

[MIT](LICENSE)