import sys
import os
import shutil
import time
import sys
import winreg


def handle_uninstall():
    """处理卸载清理操作"""
    print("执行卸载清理操作...")
    
    try:
        # 获取应用数据目录，使用统一的独特命名规范
        app_unique_suffix = "dorm_mgmt_v1.0"
        app_data_dir = os.path.join(os.path.expanduser("~"), "Documents", f"dorm_mgmt_system_{app_unique_suffix}")
            
        # 清理日志文件
        if os.path.exists(app_data_dir):
            print(f"清理日志目录: {app_data_dir}")
            # 等待2秒确保没有文件被锁定
            time.sleep(2)
            try:
                shutil.rmtree(app_data_dir)
            except Exception as e:
                print(f"清理日志目录时出错: {str(e)}")
        
        # 清理可能的临时文件 - 使用更独特的目录名称便于识别
        app_unique_suffix = "dorm_mgmt_v1.0"
        temp_locations = [
            # 系统临时目录
            os.path.join(os.environ.get('TEMP', 'C:\Windows\Temp'), f"dorm_mgmt_system_{app_unique_suffix}"),
            os.path.join(os.environ.get('TMP', 'C:\Windows\Temp'), f"dorm_mgmt_system_{app_unique_suffix}"),
            # 用户缓存目录
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp", f"dorm_mgmt_system_{app_unique_suffix}"),
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Cache", f"dorm_mgmt_system_{app_unique_suffix}"),
            os.path.join(os.path.expanduser("~"), "AppData", "Roaming", f"dorm_mgmt_system_{app_unique_suffix}"),
            # 打包环境特殊临时位置 - 更精确匹配PyInstaller临时目录
            os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp"),  # 扫描所有以dorm_mgmt_system_开头的目录
            os.environ.get('TEMP', 'C:\Windows\Temp')  # 扫描系统临时目录中所有以dorm_mgmt_system_开头的目录
        ]
        
        for temp_dir in temp_locations:
            if os.path.exists(temp_dir):
                # 检查是否是需要扫描子目录的情况（处理PyInstaller临时目录）
                if temp_dir.endswith(('Temp', 'TMP')):
                    # 扫描目录中所有以_MEI开头的文件夹
                    print(f"扫描目录: {temp_dir} 中的PyInstaller临时文件")
                    try:
                        for item in os.listdir(temp_dir):
                            item_path = os.path.join(temp_dir, item)
                            if os.path.isdir(item_path) and item.startswith('_MEI'):
                                print(f"清理PyInstaller临时目录: {item_path}")
                                try:
                                    shutil.rmtree(item_path)
                                except Exception as e:
                                    print(f"清理PyInstaller临时目录时出错: {str(e)}")
                    except Exception as e:
                        print(f"扫描临时目录时出错: {str(e)}")
                else:
                    # 普通目录直接清理
                    print(f"清理临时文件目录: {temp_dir}")
                    try:
                        shutil.rmtree(temp_dir)
                    except Exception as e:
                        print(f"清理临时文件目录时出错: {str(e)}")
        
        # 清理注册表项
        try:
            # 定义要清理的注册表路径列表
            reg_paths = [
                # 主应用注册表项
                r"Software\Dormitory Management System",
                # Explorer历史记录和使用痕迹
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\FeatureUsage\AppSwitched",
                # 兼容性助手记录
                r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Compatibility Assistant\Store"
            ]
            
            # 应用程序可执行文件名（用于匹配注册表值）
            app_exe_names = ["行政后勤管理系统.exe", "dorm_management.exe"]
            
            # 清理用户注册表项
            for reg_path in reg_paths:
                try:
                    # 打开注册表键
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE)
                    
                    # 检查是否是需要删除特定值的路径
                    if reg_path.endswith("AppSwitched") or reg_path.endswith("Store"):
                        # 获取所有值的名称
                        values_count = winreg.QueryInfoKey(key)[1]
                        values_to_delete = []
                        
                        for i in range(values_count):
                            try:
                                value_name = winreg.EnumValue(key, i)[0]
                                # 检查值名称是否包含应用程序文件名
                                if any(exe_name in value_name for exe_name in app_exe_names):
                                    values_to_delete.append(value_name)
                            except OSError:
                                # 枚举值时出错，跳过
                                continue
                        
                        # 删除匹配的值
                        for value_name in values_to_delete:
                            try:
                                winreg.DeleteValue(key, value_name)
                                print(f"清理用户注册表值: {reg_path}\{value_name} 成功")
                            except Exception as e:
                                print(f"清理用户注册表值时出错: {str(e)}")
                        
                        winreg.CloseKey(key)
                    else:
                        # 删除整个键
                        winreg.CloseKey(key)
                        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, reg_path)
                        print(f"清理用户注册表项: {reg_path} 成功")
                except FileNotFoundError:
                    print(f"用户注册表项不存在: {reg_path}")
                except Exception as e:
                    print(f"清理用户注册表项时出错: {str(e)}")
            
            # 清理系统注册表项（需要管理员权限）
            try:
                # 清理BAM服务状态
                bam_path = r"SYSTEM\CurrentControlSet\Services\bam\State\UserSettings"
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, bam_path, 0, winreg.KEY_READ)
                
                # 获取所有子键（用户SID）
                subkeys_count = winreg.QueryInfoKey(key)[0]
                
                for i in range(subkeys_count):
                    try:
                        subkey_name = winreg.EnumKey(key, i)
                        subkey_path = f"{bam_path}\{subkey_name}"
                        subkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey_path, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE)
                        
                        # 获取所有值
                        values_count = winreg.QueryInfoKey(subkey)[1]
                        values_to_delete = []
                        
                        for j in range(values_count):
                            try:
                                value_name = winreg.EnumValue(subkey, j)[0]
                                # 检查值名称是否包含应用程序文件名
                                if any(exe_name in value_name for exe_name in app_exe_names):
                                    values_to_delete.append(value_name)
                            except OSError:
                                continue
                        
                        # 删除匹配的值
                        for value_name in values_to_delete:
                            try:
                                winreg.DeleteValue(subkey, value_name)
                                print(f"清理系统注册表值: {subkey_path}\{value_name} 成功")
                            except Exception as e:
                                print(f"清理系统注册表值时出错: {str(e)}")
                        
                        winreg.CloseKey(subkey)
                    except Exception as e:
                        print(f"访问用户SID子键时出错: {str(e)}")
                
                winreg.CloseKey(key)
            except (FileNotFoundError, PermissionError):
                print("系统注册表项不存在或没有管理员权限访问")
            except Exception as e:
                print(f"清理系统注册表项时出错: {str(e)}")
        except Exception as e:
            print(f"清理注册表过程中发生错误: {str(e)}")
        
        print("卸载清理操作完成")
    except Exception as e:
        print(f"卸载清理过程中发生错误: {str(e)}")
    
    # 确保程序退出
    sys.exit(0)