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
            str: 操作系统类型，可能值为"windows"、"android"、"linux"、"macos"或"unknown"
        """
        # Android底层也是Linux，需要优先判断
        if SystemDetector.is_android():
            return "android"
            
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
        获取综合环境类型（优先判断容器环境，其次判断Android平台）
        
        返回:
            str: 环境类型，可能值为"docker"、"android"、"windows"、"linux"、"macos"或"unknown"
        """
        # 容器环境优先
        if SystemDetector.is_docker():
            return "docker"
            
        # Android平台判断（在OS判断之前，因为Android底层也是Linux）
        if SystemDetector.is_android():
            return "android"
            
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

    @staticmethod
    def is_android() -> bool:
        """
        判断当前环境是否为Android平台
        
        通过ANDROID_ENV环境变量检测，该变量在Chaquopy环境中由应用设置
        
        返回:
            bool: 如果在Android平台返回True，否则返回False
        """
        try:
            is_android_env = os.getenv('ANDROID_ENV', 'false').lower() == 'true'
            if is_android_env:
                logging.debug("检测到Android环境（ANDROID_ENV=true）")
            return is_android_env
        except Exception as e:
            logging.debug(f"Android环境检测出错: {str(e)}")
            return False

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

def is_windows() -> bool:
    """便捷函数：判断是否为Windows系统"""
    return SystemDetector.is_windows()

def is_android() -> bool:
    """便捷函数：判断是否为Android平台"""
    return SystemDetector.is_android()

def is_win7() -> bool:
    """检测当前系统是否为Windows 7"""
    if not is_windows():
        return False
    try:
        import ctypes
        class OSVERSIONINFOEXW(ctypes.Structure):
            _fields_ = [
                ('dwOSVersionInfoSize', ctypes.c_ulong),
                ('dwMajorVersion', ctypes.c_ulong),
                ('dwMinorVersion', ctypes.c_ulong),
                ('dwBuildNumber', ctypes.c_ulong),
                ('dwPlatformId', ctypes.c_ulong),
                ('szCSDVersion', ctypes.c_wchar * 128),
            ]
        osvi = OSVERSIONINFOEXW()
        osvi.dwOSVersionInfoSize = ctypes.sizeof(OSVERSIONINFOEXW)
        ntdll = ctypes.windll.ntdll
        ntdll.RtlGetVersion(ctypes.byref(osvi))
        return osvi.dwMajorVersion == 6 and osvi.dwMinorVersion == 1
    except Exception:
        return False
    