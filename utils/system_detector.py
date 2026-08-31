import os
import platform
import logging

# 模块级变量，用于跟踪Docker检测错误是否已记录
docker_detection_error_logged = False

class SystemDetector:
    """系统环境检测工具类，提供操作系统和容器环境判断功能"""
    
    @staticmethod
    def is_docker() -> bool:
        """
        判断当前环境是否为Docker容器
        
        返回:
            bool: 如果在Docker容器中返回True，否则返回False
        """
        # 首先检查环境变量，这是最可靠和最快的方法
        if os.getenv('DOCKER_ENV', 'false').lower() == 'true':
            return True
            
        try:
            # 检查Docker特有的文件
            if os.path.exists('/.dockerenv'):
                return True
                
            # 检查进程控制组信息（仅在非Windows系统尝试）
            if platform.system().lower() != "windows":
                with open('/proc/1/cgroup', 'rt') as f:
                    if 'docker' in f.read():
                        return True
                    
        except (FileNotFoundError, PermissionError, OSError) as e:
            # 只记录一次错误，避免重复日志
            global docker_detection_error_logged
            if not docker_detection_error_logged:
                logging.debug(f"Docker环境检测出错: {str(e)}")
                docker_detection_error_logged = True
        
        return False

    @staticmethod
    def get_os() -> str:
        """
        获取操作系统类型
        
        返回:
            str: 操作系统类型，可能值为"windows"、"linux"、"macos"或"unknown"
        """
        system = platform.system().lower()
        
        if system == "windows":
            return "windows"
        elif system == "linux":
            return "linux"
        elif system == "darwin":
            return "macos"
        else:
            return "unknown"

    @staticmethod
    def get_environment() -> str:
        """
        获取综合环境类型（优先判断容器环境）
        
        返回:
            str: 环境类型，可能值为"docker"、"windows"、"linux"、"macos"或"unknown"
        """
        # 容器环境优先
        if SystemDetector.is_docker():
            return "docker"
            
        # 否则返回操作系统类型
        return SystemDetector.get_os()

    @staticmethod
    def is_linux() -> bool:
        """判断是否为Linux系统（非Docker容器）"""
        return not SystemDetector.is_docker() and SystemDetector.get_os() == "linux"

    @staticmethod
    def is_windows() -> bool:
        """判断是否为Windows系统"""
        return SystemDetector.get_os() == "windows" and not SystemDetector.is_docker()

# 提供便捷的直接调用接口
def is_docker() -> bool:
    """便捷函数：判断是否为Docker环境"""
    return SystemDetector.is_docker()

def get_environment() -> str:
    """便捷函数：获取综合环境类型"""
    return SystemDetector.get_environment()

def get_os() -> str:
    """便捷函数：获取操作系统类型"""
    return SystemDetector.get_os()


# ========== Windows版本检测功能（Win7兼容支持） ==========

# 模块级缓存，避免重复检测
_win_version_cache = None
_is_win7_cache = None
_is_webview2_available_cache = None


def get_windows_version():
    """
    获取准确的Windows版本号（不受兼容模式影响）
    
    使用ctypes调用ntdll.dll的RtlGetVersion，这是获取Windows版本最准确的方式，
    不受应用程序兼容性清单(shim)的影响。
    
    返回:
        tuple: (major, minor, build) 版本号元组
               非Windows系统返回 (0, 0, 0)
    """
    global _win_version_cache
    
    if _win_version_cache is not None:
        return _win_version_cache
    
    # 非Windows系统直接返回
    if platform.system() != 'Windows':
        _win_version_cache = (0, 0, 0)
        return _win_version_cache
    
    try:
        import ctypes
        from ctypes import wintypes
        
        # 定义OSVERSIONINFOEXW结构体
        class OSVERSIONINFOEXW(ctypes.Structure):
            _fields_ = [
                ('dwOSVersionInfoSize', wintypes.DWORD),
                ('dwMajorVersion', wintypes.DWORD),
                ('dwMinorVersion', wintypes.DWORD),
                ('dwBuildNumber', wintypes.DWORD),
                ('dwPlatformId', wintypes.DWORD),
                ('szCSDVersion', ctypes.c_wchar * 128),
                ('wServicePackMajor', wintypes.WORD),
                ('wServicePackMinor', wintypes.WORD),
                ('wSuiteMask', wintypes.WORD),
                ('wProductType', wintypes.BYTE),
                ('wReserved', wintypes.BYTE),
            ]
        
        # 调用RtlGetVersion
        ntdll = ctypes.windll.ntdll
        osvi = OSVERSIONINFOEXW()
        osvi.dwOSVersionInfoSize = ctypes.sizeof(OSVERSIONINFOEXW)
        
        # RtlGetVersion返回NTSTATUS，0表示成功
        result = ntdll.RtlGetVersion(ctypes.byref(osvi))
        if result == 0:
            _win_version_cache = (osvi.dwMajorVersion, osvi.dwMinorVersion, osvi.dwBuildNumber)
            logging.info(f"检测到Windows版本: {osvi.dwMajorVersion}.{osvi.dwMinorVersion}.{osvi.dwBuildNumber}")
        else:
            logging.warning(f"RtlGetVersion调用失败，返回值: {result}")
            _win_version_cache = (0, 0, 0)
    except Exception as e:
        logging.warning(f"获取Windows版本号失败: {str(e)}")
        _win_version_cache = (0, 0, 0)
    
    return _win_version_cache


def is_win7():
    """
    检测当前系统是否为Windows 7或Windows Server 2008 R2
    
    Windows 7和Server 2008 R2的版本号均为6.1
    
    返回:
        bool: 如果是Win7/Server 2008 R2返回True，否则返回False
    """
    global _is_win7_cache
    
    if _is_win7_cache is not None:
        return _is_win7_cache
    
    major, minor, _ = get_windows_version()
    _is_win7_cache = (major == 6 and minor == 1)
    
    if _is_win7_cache:
        logging.info("检测到Windows 7 / Server 2008 R2系统")
    
    return _is_win7_cache


def is_webview2_available():
    """
    检测WebView2运行时是否可用
    
    通过检查注册表中WebView2的客户端GUID是否存在来判断。
    检查两个位置：
    - HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEB-6731AEBF4D1A} (64位系统上的32位注册表重定向)
    - HKLM\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BEB-6731AEBF4D1A} (原生位置)
    
    返回:
        bool: 如果WebView2运行时可用返回True，否则返回False
              非Windows系统返回False
    """
    global _is_webview2_available_cache
    
    if _is_webview2_available_cache is not None:
        return _is_webview2_available_cache
    
    # 非Windows系统不支持WebView2
    if platform.system() != 'Windows':
        _is_webview2_available_cache = False
        return _is_webview2_available_cache
    
    try:
        import winreg
        
        # WebView2运行时的客户端GUID
        webview2_guid = '{F3017226-FE2A-4295-8BEB-6731AEBF4D1A}'
        
        # 要检查的注册表路径列表
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, f'SOFTWARE\\WOW6432Node\\Microsoft\\EdgeUpdate\\Clients\\{webview2_guid}'),
            (winreg.HKEY_LOCAL_MACHINE, f'SOFTWARE\\Microsoft\\EdgeUpdate\\Clients\\{webview2_guid}'),
        ]
        
        for hive, path in reg_paths:
            try:
                key = winreg.OpenKey(hive, path, 0, winreg.KEY_READ)
                winreg.CloseKey(key)
                _is_webview2_available_cache = True
                logging.info("检测到WebView2运行时已安装")
                return _is_webview2_available_cache
            except FileNotFoundError:
                continue
            except OSError:
                continue
        
        _is_webview2_available_cache = False
        logging.info("未检测到WebView2运行时")
    except ImportError:
        # winreg模块不可用（非Windows环境）
        _is_webview2_available_cache = False
        logging.debug("winreg模块不可用，无法检测WebView2")
    except Exception as e:
        _is_webview2_available_cache = False
        logging.warning(f"检测WebView2运行时失败: {str(e)}")
    
    return _is_webview2_available_cache
    