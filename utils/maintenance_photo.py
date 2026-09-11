import os
import sys
import shutil
import uuid
import logging
from flask import current_app
from werkzeug.utils import secure_filename
from datetime import datetime

# 支持的图片和视频格式
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv'}
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS.union(ALLOWED_VIDEO_EXTENSIONS)


class MaintenancePhotoManager:
    """维修工单照片管理工具类，处理维修工单照片和视频的上传、存储和访问"""
    
    @staticmethod
    def get_media_root_dir():
        """获取媒体文件的根目录，确保正确目录存在
        根据不同环境(Docker、Windows打包、开发环境)返回正确的数据存储路径
        """
        # 检查是否是Docker环境
        if os.environ.get('DOCKER_ENV') == 'true':
            # Docker环境下，数据存储在/data目录
            media_root = '/data/photo/maintenance_photo'
        # 检查是否是Android环境
        elif os.environ.get('ANDROID_ENV', 'false').lower() == 'true':
            media_root = os.path.join(os.environ.get('APP_DATA_DIR', '/data'), 'photo', 'maintenance_photo')
        # 检查是否是PyInstaller打包环境
        elif getattr(sys, 'frozen', False):
            # 获取打包后可执行文件所在目录
            app_dir = os.path.dirname(os.path.abspath(sys.executable))
            # 在可执行文件同级目录创建data/photo/maintenance_photo
            media_root = os.path.join(app_dir, 'data', 'photo', 'maintenance_photo')
        else:
            # 开发环境下使用相对路径
            app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            media_root = os.path.join(app_root, 'data', 'photo', 'maintenance_photo')
        
        # 确保目录存在
        os.makedirs(media_root, exist_ok=True)
        return media_root
    
    @staticmethod
    def get_temp_root_dir(create=True):
        """获取临时文件的根目录
        根据不同环境(Docker、Windows打包、开发环境)返回正确的数据存储路径
        
        Args:
            create: 是否自动创建目录，默认True。查询/清理时传False避免空目录产生。
        
        Returns:
            str: 临时根目录的绝对路径
        """
        # 检查是否是Docker环境
        if os.environ.get('DOCKER_ENV') == 'true':
            # Docker环境下，数据存储在/data目录
            temp_root = '/data/photo/maintenance_temp'
        # 检查是否是Android环境
        elif os.environ.get('ANDROID_ENV', 'false').lower() == 'true':
            temp_root = os.path.join(os.environ.get('APP_DATA_DIR', '/data'), 'photo', 'maintenance_temp')
        # 检查是否是PyInstaller打包环境
        elif getattr(sys, 'frozen', False):
            # 获取打包后可执行文件所在目录
            app_dir = os.path.dirname(os.path.abspath(sys.executable))
            # 在可执行文件同级目录创建data/photo/maintenance_temp
            temp_root = os.path.join(app_dir, 'data', 'photo', 'maintenance_temp')
        else:
            # 开发环境下使用相对路径
            app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            temp_root = os.path.join(app_root, 'data', 'photo', 'maintenance_temp')
        
        # 仅在create=True时创建目录
        if create:
            os.makedirs(temp_root, exist_ok=True)
        return temp_root
    
    @staticmethod
    def ensure_order_directory_exists(order_id):
        """确保特定工单的媒体目录存在
        
        Args:
            order_id: 维修工单ID（数据库中的主键）
        
        Returns:
            str: 工单媒体目录的绝对路径
        """
        # 获取媒体根目录
        media_root = MaintenancePhotoManager.get_media_root_dir()
        # 构建工单目录路径：data/photo/maintenance_photo/工单ID
        order_dir = os.path.join(media_root, str(order_id))
        # 确保目录存在
        os.makedirs(order_dir, exist_ok=True)
        return order_dir
    
    @staticmethod
    def ensure_temp_directory_exists(user_id):
        """确保特定用户的临时目录存在
        
        Args:
            user_id: 用户ID
        
        Returns:
            str: 用户临时目录的绝对路径
        """
        # 获取临时根目录
        temp_root = MaintenancePhotoManager.get_temp_root_dir()
        # 构建用户临时目录路径：data/photo/maintenance_temp/用户ID
        temp_dir = os.path.join(temp_root, str(user_id))
        # 确保目录存在
        os.makedirs(temp_dir, exist_ok=True)
        return temp_dir
    
    @staticmethod
    def allowed_file(filename):
        """检查文件是否是允许的格式
        
        Args:
            filename: 文件名
        
        Returns:
            bool: 是否允许的文件格式
        """
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
    
    @staticmethod
    def is_image_file(filename):
        """检查文件是否是图片格式
        
        Args:
            filename: 文件名
        
        Returns:
            bool: 是否是图片文件
        """
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS
    
    @staticmethod
    def is_video_file(filename):
        """检查文件是否是视频格式
        
        Args:
            filename: 文件名
        
        Returns:
            bool: 是否是视频文件
        """
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS
    
    @staticmethod
    def upload_file(file, order_id):
        """上传文件到指定工单的媒体目录
        
        Args:
            file: Flask文件对象
            order_id: 维修工单ID（数据库中的主键）
        
        Returns:
            str: 保存的文件名，如果上传失败则返回None
        """
        # 检查文件格式是否允许
        if not MaintenancePhotoManager.allowed_file(file.filename):
            return None
        
        # 确保工单目录存在
        order_dir = MaintenancePhotoManager.ensure_order_directory_exists(order_id)
        
        # 使用原始文件名，但确保文件名安全
        unique_filename = secure_filename(file.filename)
        
        # 如果secure_filename返回空（如纯中文文件名），使用UUID作为文件名
        if not unique_filename or unique_filename.startswith('.'):
            import uuid as _uuid
            ext = os.path.splitext(file.filename)[1].lower() if file.filename else ''
            unique_filename = f"{_uuid.uuid4().hex[:8]}{ext}"
        
        # 如果文件名已存在，添加UUID前缀避免冲突
        file_path = os.path.join(order_dir, unique_filename)
        if os.path.exists(file_path):
            name, ext = os.path.splitext(unique_filename)
            unique_filename = f"{name}_{uuid.uuid4().hex[:8]}{ext}"
        
        # 保存文件
        file.save(os.path.join(order_dir, unique_filename))
        
        return unique_filename
    
    @staticmethod
    def upload_temp_file(file, user_id):
        """上传文件到临时目录
        
        Args:
            file: Flask文件对象
            user_id: 用户ID
        
        Returns:
            str: 保存的文件名，如果上传失败则返回None
        """
        # 检查文件格式是否允许
        if not MaintenancePhotoManager.allowed_file(file.filename):
            return None
        
        # 确保用户临时目录存在
        temp_dir = MaintenancePhotoManager.ensure_temp_directory_exists(user_id)
        
        # 使用原始文件名，但确保文件名安全
        unique_filename = secure_filename(file.filename)
        
        # 如果文件名已存在，添加UUID前缀避免冲突
        file_path = os.path.join(temp_dir, unique_filename)
        if os.path.exists(file_path):
            name, ext = os.path.splitext(unique_filename)
            unique_filename = f"{name}_{uuid.uuid4().hex[:8]}{ext}"
        
        # 保存文件
        file.save(os.path.join(temp_dir, unique_filename))
        
        return unique_filename
    
    @staticmethod
    def move_temp_to_formal(user_id, order_id, filenames):
        """将临时文件移动到正式目录，移动完成后自动清理空的临时目录
        
        Args:
            user_id: 用户ID
            order_id: 维修工单ID
            filenames: 文件名列表
        
        Returns:
            list: 成功移动的文件名列表
        """
        moved_files = []
        temp_dir = MaintenancePhotoManager.ensure_temp_directory_exists(user_id)
        order_dir = MaintenancePhotoManager.ensure_order_directory_exists(order_id)
        
        for filename in filenames:
            if not filename:
                continue
            temp_path = os.path.join(temp_dir, filename)
            if os.path.exists(temp_path):
                formal_path = os.path.join(order_dir, filename)
                # 如果正式目录已有同名文件，添加UUID前缀
                if os.path.exists(formal_path):
                    name, ext = os.path.splitext(filename)
                    new_filename = f"{name}_{uuid.uuid4().hex[:8]}{ext}"
                    formal_path = os.path.join(order_dir, new_filename)
                    filename = new_filename
                shutil.move(temp_path, formal_path)
                moved_files.append(filename)
        
        # 移动完成后清理空的临时目录
        MaintenancePhotoManager._cleanup_empty_temp_dir(temp_dir)
        
        return moved_files
    
    @staticmethod
    def delete_file(filename, order_id):
        """删除指定工单媒体目录中的文件
        
        Args:
            filename: 文件名
            order_id: 维修工单ID（数据库中的主键）
        
        Returns:
            bool: 是否删除成功
        """
        try:
            # 获取工单目录
            order_dir = MaintenancePhotoManager.ensure_order_directory_exists(order_id)
            # 构建文件完整路径
            file_path = os.path.join(order_dir, filename)
            # 检查文件是否存在并删除
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception:
            return False
    
    @staticmethod
    def delete_temp_file(filename, user_id):
        """删除临时目录中的文件，删除后若目录为空则自动清理
        
        Args:
            filename: 文件名
            user_id: 用户ID
        
        Returns:
            bool: 是否删除成功
        """
        try:
            # 获取用户临时目录（不自动创建）
            temp_dir = os.path.join(MaintenancePhotoManager.get_temp_root_dir(create=False), str(user_id))
            # 构建文件完整路径
            file_path = os.path.join(temp_dir, filename)
            # 检查文件是否存在并删除
            if os.path.exists(file_path):
                os.remove(file_path)
                # 删除后检查目录是否为空，为空则清理
                MaintenancePhotoManager._cleanup_empty_temp_dir(temp_dir)
                return True
            return False
        except Exception:
            return False
    
    @staticmethod
    def _cleanup_empty_temp_dir(user_temp_dir):
        """清理空的用户临时目录，向上递归删除空的父目录直到临时根目录为止
        
        Args:
            user_temp_dir: 用户临时目录路径
        """
        try:
            # 检查用户临时目录是否为空，为空则删除
            if os.path.exists(user_temp_dir) and not os.listdir(user_temp_dir):
                os.rmdir(user_temp_dir)
            
            # 检查临时根目录是否为空，为空也删除
            temp_root = MaintenancePhotoManager.get_temp_root_dir(create=False)
            if os.path.exists(temp_root) and not os.listdir(temp_root):
                os.rmdir(temp_root)
        except Exception:
            pass
    
    @staticmethod
    def cleanup_temp_files(user_id):
        """清理用户所有临时文件及目录
        
        Args:
            user_id: 用户ID
        
        Returns:
            bool: 是否清理成功
        """
        try:
            temp_dir = os.path.join(MaintenancePhotoManager.get_temp_root_dir(create=False), str(user_id))
            if os.path.exists(temp_dir) and os.path.isdir(temp_dir):
                shutil.rmtree(temp_dir)
                # 清理可能变空的临时根目录
                temp_root = MaintenancePhotoManager.get_temp_root_dir(create=False)
                if os.path.exists(temp_root) and not os.listdir(temp_root):
                    os.rmdir(temp_root)
                return True
            return False
        except Exception:
            return False
    
    @staticmethod
    def clear_all_temp_files():
        """清理所有用户临时目录中的媒体文件
        
        Returns:
            dict: {'deleted': int, 'errors': list, 'users_cleared': int} 删除数量、错误信息和清理的用户数
        """
        temp_root = MaintenancePhotoManager.get_temp_root_dir(create=False)
        
        if not os.path.exists(temp_root):
            return {'deleted': 0, 'errors': [], 'users_cleared': 0}
        
        total_deleted = 0
        all_errors = []
        users_cleared = 0
        
        try:
            for user_dir_name in os.listdir(temp_root):
                user_dir = os.path.join(temp_root, user_dir_name)
                
                if not os.path.isdir(user_dir):
                    continue
                
                user_deleted = 0
                for filename in os.listdir(user_dir):
                    file_path = os.path.join(user_dir, filename)
                    
                    if os.path.isdir(file_path):
                        continue
                    
                    if not MaintenancePhotoManager.allowed_file(filename):
                        continue
                    
                    try:
                        os.remove(file_path)
                        user_deleted += 1
                        total_deleted += 1
                    except Exception as e:
                        all_errors.append(f"用户 {user_dir_name} 文件 {filename} 删除失败: {str(e)}")
                
                if user_deleted > 0:
                    users_cleared += 1
                
                # 清理空的用户临时目录
                MaintenancePhotoManager._cleanup_empty_temp_dir(user_dir)
        
        except Exception as e:
            all_errors.append(f"遍历临时目录失败: {str(e)}")
        
        return {'deleted': total_deleted, 'errors': all_errors, 'users_cleared': users_cleared}
    
    @staticmethod
    def cleanup_old_temp_files(max_age_hours=24):
        """清理超过指定时间的临时文件和空目录
        
        作为定时任务的安全网，清理因异常未及时删除的临时文件。
        
        Args:
            max_age_hours: 文件最大保留时间（小时），默认24小时
        
        Returns:
            dict: 清理结果统计 {'deleted_files': int, 'deleted_dirs': int, 'errors': int}
        """
        result = {'deleted_files': 0, 'deleted_dirs': 0, 'errors': 0}
        try:
            temp_root = MaintenancePhotoManager.get_temp_root_dir(create=False)
            if not os.path.exists(temp_root) or not os.path.isdir(temp_root):
                return result
            
            now = datetime.now().timestamp()
            max_age_seconds = max_age_hours * 3600
            
            # 遍历所有用户临时目录
            for user_dir_name in os.listdir(temp_root):
                user_dir_path = os.path.join(temp_root, user_dir_name)
                if not os.path.isdir(user_dir_path):
                    continue
                
                try:
                    # 遍历用户目录中的文件
                    files_remaining = False
                    for filename in os.listdir(user_dir_path):
                        file_path = os.path.join(user_dir_path, filename)
                        if os.path.isfile(file_path):
                            file_age = now - os.path.getmtime(file_path)
                            if file_age > max_age_seconds:
                                os.remove(file_path)
                                result['deleted_files'] += 1
                            else:
                                files_remaining = True
                    
                    # 如果目录为空，删除用户目录
                    if not files_remaining and not os.listdir(user_dir_path):
                        os.rmdir(user_dir_path)
                        result['deleted_dirs'] += 1
                except Exception as e:
                    result['errors'] += 1
                    logging.warning(f"清理用户临时目录 {user_dir_path} 时出错: {str(e)}")
            
            if result['deleted_files'] > 0 or result['deleted_dirs'] > 0:
                logging.info(f"临时文件清理完成: 删除 {result['deleted_files']} 个文件, "
                           f"{result['deleted_dirs']} 个空目录, {result['errors']} 个错误")
            return result
        except Exception as e:
            logging.error(f"清理临时文件时发生错误: {str(e)}")
            result['errors'] += 1
            return result
    
    @staticmethod
    def get_media_files(order_id):
        """获取指定工单的所有媒体文件，返回包含详细信息的列表
        
        Args:
            order_id: 维修工单ID（数据库中的主键）
        
        Returns:
            list: 包含媒体文件详细信息的列表
        """
        # 获取工单目录
        order_dir = MaintenancePhotoManager.ensure_order_directory_exists(order_id)
        
        # 初始化结果列表
        media_files = []
        
        # 遍历工单目录中的所有文件
        if os.path.exists(order_dir):
            for filename in os.listdir(order_dir):
                # 构建文件完整路径
                file_path = os.path.join(order_dir, filename)
                # 检查文件是否是普通文件（非目录）
                if os.path.isfile(file_path):
                    # 获取文件信息
                    file_info = {
                        'filename': filename,
                        'url': MaintenancePhotoManager.get_media_url(order_id, filename),
                        # 使用文件修改时间作为上传时间的近似值
                        'upload_time': datetime.fromtimestamp(os.path.getmtime(file_path))
                    }
                    
                    # 根据文件类型设置type字段
                    if MaintenancePhotoManager.is_image_file(filename):
                        file_info['type'] = 'image'
                        media_files.append(file_info)
                    elif MaintenancePhotoManager.is_video_file(filename):
                        file_info['type'] = 'video'
                        media_files.append(file_info)
        
        # 按上传时间倒序排序
        media_files.sort(key=lambda x: x['upload_time'], reverse=True)
        
        return media_files
    
    @staticmethod
    def get_temp_files(user_id):
        """获取用户临时文件列表
        
        Args:
            user_id: 用户ID
        
        Returns:
            list: 包含临时文件详细信息的列表
        """
        # 获取用户临时目录
        temp_dir = MaintenancePhotoManager.ensure_temp_directory_exists(user_id)
        
        # 初始化结果列表
        temp_files = []
        
        # 遍历临时目录中的所有文件
        if os.path.exists(temp_dir):
            for filename in os.listdir(temp_dir):
                # 构建文件完整路径
                file_path = os.path.join(temp_dir, filename)
                # 检查文件是否是普通文件（非目录）
                if os.path.isfile(file_path):
                    # 获取文件信息
                    file_info = {
                        'filename': filename,
                        'url': MaintenancePhotoManager.get_temp_url(user_id, filename),
                        # 使用文件修改时间作为上传时间的近似值
                        'upload_time': datetime.fromtimestamp(os.path.getmtime(file_path))
                    }
                    
                    # 根据文件类型设置type字段
                    if MaintenancePhotoManager.is_image_file(filename):
                        file_info['type'] = 'image'
                        temp_files.append(file_info)
                    elif MaintenancePhotoManager.is_video_file(filename):
                        file_info['type'] = 'video'
                        temp_files.append(file_info)
        
        # 按上传时间倒序排序
        temp_files.sort(key=lambda x: x['upload_time'], reverse=True)
        
        return temp_files
    
    @staticmethod
    def get_file_path(filename, order_id):
        """获取媒体文件的完整路径
        
        Args:
            filename: 文件名
            order_id: 维修工单ID（数据库中的主键）
        
        Returns:
            str: 文件的完整路径，如果文件不存在则返回None
        """
        # 获取工单目录
        order_dir = MaintenancePhotoManager.ensure_order_directory_exists(order_id)
        # 构建文件完整路径
        file_path = os.path.join(order_dir, filename)
        # 检查文件是否存在
        if os.path.exists(file_path):
            return file_path
        return None
    
    @staticmethod
    def get_temp_file_path(filename, user_id):
        """获取临时文件的完整路径
        
        Args:
            filename: 文件名
            user_id: 用户ID
        
        Returns:
            str: 文件的完整路径，如果文件不存在则返回None
        """
        # 获取用户临时目录
        temp_dir = MaintenancePhotoManager.ensure_temp_directory_exists(user_id)
        # 构建文件完整路径
        file_path = os.path.join(temp_dir, filename)
        # 检查文件是否存在
        if os.path.exists(file_path):
            return file_path
        return None
    
    @staticmethod
    def get_media_url(order_id, filename):
        """生成媒体文件的访问URL
        
        Args:
            order_id: 维修工单ID（数据库中的主键）
            filename: 文件名
        
        Returns:
            str: 媒体文件的访问URL
        """
        return f"/api/maintenance/media/{order_id}/{filename}"
    
    @staticmethod
    def get_temp_url(user_id, filename):
        """生成临时文件的访问URL
        
        Args:
            user_id: 用户ID
            filename: 文件名
        
        Returns:
            str: 临时文件的访问URL
        """
        return f"/api/maintenance/temp/{user_id}/{filename}"
    
    @staticmethod
    def delete_all_files(order_id):
        """删除工单所有文件
        
        Args:
            order_id: 维修工单ID（数据库中的主键）
        
        Returns:
            bool: 是否删除成功
        """
        try:
            # 获取工单目录
            order_dir = MaintenancePhotoManager.ensure_order_directory_exists(order_id)
            # 如果目录存在，则删除
            if os.path.exists(order_dir) and os.path.isdir(order_dir):
                shutil.rmtree(order_dir)
                return True
            return False
        except Exception:
            return False


# 创建一个全局实例，方便直接导入使用
maintenance_photo_manager = MaintenancePhotoManager()