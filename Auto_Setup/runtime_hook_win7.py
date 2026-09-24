# -*- coding: utf-8 -*-
"""
PyInstaller 运行时钩子 - Windows 7 兼容性检测

在程序启动前（早于 multiprocessing 钩子）检测运行环境，
如果检测到 Windows 7 且缺少 UCRT，则显示友好提示并退出。

错误场景：
  ImportError: DLL load failed while importing _socket: 参数错误

根因：
  - Python 3.9+ 已不支持 Windows 7
  - Windows 7 未安装 KB2999226 (Universal C Runtime 补丁)
  - 打包时未包含 UCRT DLL

注意：此钩子必须放在 spec 文件 runtime_hooks 列表的最前面，
      确保在 PyInstaller 内置的 multiprocessing 钩子之前执行。
"""
import sys
import os
import ctypes


def _is_win7_or_earlier():
    """检测是否为 Windows 7 或更早版本（不依赖 _socket 等可能缺失的模块）"""
    if sys.platform != 'win32':
        return False

    # 方法1: 通过 ctypes 调用 Windows API 获取真实版本号
    # 这是唯一可靠的方式，因为 Python 3.9+ 在 Win7 上可能返回错误版本
    try:
        # GetVersionEx 在 Win8.1+ 会被谎言化，但对 Win7 返回真实值
        # 对于我们的用例（检测是否是 Win7），这足够了
        class OSVERSIONINFOEXW(ctypes.Structure):
            _fields_ = [
                ('dwOSVersionInfoSize', ctypes.c_ulong),
                ('dwMajorVersion', ctypes.c_ulong),
                ('dwMinorVersion', ctypes.c_ulong),
                ('dwBuildNumber', ctypes.c_ulong),
                ('dwPlatformId', ctypes.c_ulong),
                ('szCSDVersion', ctypes.c_wchar * 128),
                ('wServicePackMajor', ctypes.c_ushort),
                ('wServicePackMinor', ctypes.c_ushort),
                ('wSuiteMask', ctypes.c_ushort),
                ('wProductType', ctypes.c_byte),
                ('wReserved', ctypes.c_byte),
            ]

        osvi = OSVERSIONINFOEXW()
        osvi.dwOSVersionInfoSize = ctypes.sizeof(OSVERSIONINFOEXW)
        # RtlGetVersion 返回真实版本号，不受兼容性谎言影响
        ntdll = ctypes.windll.ntdll
        ntdll.RtlGetVersion(ctypes.byref(osvi))

        # Windows 7 = 6.1, Server 2008 R2 = 6.1
        # Windows 8 = 6.2, Windows 8.1 = 6.3, Windows 10 = 10.0
        if osvi.dwMajorVersion < 6:
            return True  # XP 或更早
        if osvi.dwMajorVersion == 6 and osvi.dwMinorVersion <= 1:
            return True  # Windows 7 或更早（6.0=Vista, 6.1=Win7）
        return False
    except Exception:
        pass

    # 方法2: 备用检测（不太可靠，但作为后备）
    try:
        winver = sys.winver
        if winver and winver.startswith(('7', '6', '5', '4', '3', '2', '1', '0')):
            return True
    except (AttributeError, IndexError):
        pass

    return False


def _check_ucrt_dll_exists():
    """
    检测 UCRT DLL 是否存在于系统目录
    不通过 import 检测（因为 import _socket 会崩溃），
    而是直接检查 DLL 文件是否存在
    """
    # UCRT 的核心 DLL 文件名
    ucrt_dlls = [
        'ucrtbase.dll',
        'api-ms-win-crt-runtime-l1-1-0.dll',
        'api-ms-win-crt-stdio-l1-1-0.dll',
    ]

    system_dir = os.environ.get('SystemRoot', r'C:\Windows')
    system32 = os.path.join(system_dir, 'System32')

    for dll_name in ucrt_dlls:
        dll_path = os.path.join(system32, dll_name)
        if os.path.isfile(dll_path):
            return True

    # 也检查 SysWOW64（32位程序在64位系统上）
    syswow64 = os.path.join(system_dir, 'SysWOW64')
    if os.path.isdir(syswow64):
        for dll_name in ucrt_dlls:
            dll_path = os.path.join(syswow64, dll_name)
            if os.path.isfile(dll_path):
                return True

    return False


def _show_error_dialog():
    """使用 Windows API 显示错误对话框（不依赖 tkinter，更可靠）"""
    error_title = "系统组件缺失"
    error_msg = (
        "当前系统为 Windows 7，缺少运行所需的通用 C 运行时 (UCRT) 组件。\n\n"
        "请安装以下补丁之一后重试：\n"
        "1. Windows 更新 KB2999226（通用 C 运行时补丁）\n"
        "2. Visual C++ Redistributable 2015-2022\n\n"
        "下载地址：\n"
        "KB2999226: https://www.microsoft.com/en-us/download/details.aspx?id=49082\n"
        "VC++ Redist: https://aka.ms/vs/17/release/vc_redist.x86.exe\n\n"
        "注意：如果已安装上述补丁仍报错，\n"
        "请确认打包时使用 Python 3.8.x（最后支持 Win7 的版本）。"
    )

    # 使用 Windows API MessageBoxW 显示对话框
    # MB_OK = 0, MB_ICONERROR = 0x10, MB_SETFOREGROUND = 0x10000
    try:
        ctypes.windll.user32.MessageBoxW(
            0,  # hWnd = NULL (no owner)
            error_msg,
            error_title,
            0x10 | 0x10000  # MB_ICONERROR | MB_SETFOREGROUND
        )
    except Exception:
        # 如果 MessageBoxW 也失败，打印到 stderr
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"错误: {error_title}", file=sys.stderr)
        print(error_msg, file=sys.stderr)
        print(f"{'='*60}\n", file=sys.stderr)


# ===== 执行检测 =====
# 此代码在 PyInstaller 运行时钩子阶段执行，早于 multiprocessing 钩子
if _is_win7_or_earlier() and not _check_ucrt_dll_exists():
    _show_error_dialog()
    sys.exit(1)