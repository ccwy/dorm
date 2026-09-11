
import os
import shutil
from flask import current_app
from werkzeug.utils import secure_filename
from datetime import datetime

# 支持的图片和视频格式
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv'}
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS.union(ALLOWED_VIDEO_EXTENSIONS)

class RoomPhotoManager:
    """媒体文件管理工具类，处理房间照片和视频的上传、存储和访问"""
    
    @staticmethod
    def get_media_root_dir():
        """获取媒体文件的根目录，确保正确目录存在
        根据不同环境(Docker、Windows打包、开发环境)返回正确的数据存储路径
        """
        import os
        import sys
        
        # 检查是否是Docker环境
        if os.environ.get('DOCKER_ENV') == 'true':
            # Docker环境下，数据存储在/data目录
            media_root = '/data/photo/room_photo'
        # 检查是否是Android环境
        elif os.environ.get('ANDROID_ENV', 'false').lower() == 'true':
            media_root = os.path.join(os.environ.get('APP_DATA_DIR', '/data'), 'photo', 'room_photo')
        # 检查是否是PyInstaller打包环境
        elif getattr(sys, 'frozen', False):
            # 获取打包后可执行文件所在目录
            app_dir = os.path.dirname(os.path.abspath(sys.executable))
            # 在可执行文件同级目录创建data/photo/room_photo
            media_root = os.path.join(app_dir, 'data', 'photo', 'room_photo')
        else:
            # 开发环境下使用相对路径
            app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            media_root = os.path.join(app_root, 'data', 'photo', 'room_photo')
        
        # 确保目录存在
        os.makedirs(media_root, exist_ok=True)
        return media_root
    
    @staticmethod
    def ensure_room_directory_exists(room_id):
        """确保特定房间的媒体目录存在
        
        Args:
            room_id: 房间ID（数据库中的主键）
        
        Returns:
            str: 房间媒体目录的绝对路径
        """
        # 获取媒体根目录
        media_root = RoomPhotoManager.get_media_root_dir()
        # 构建房间目录路径：data/photo/room_photo/房间ID
        room_dir = os.path.join(media_root, str(room_id))
        # 确保目录存在
        os.makedirs(room_dir, exist_ok=True)
        return room_dir
    
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
    def upload_file(file, room_id):
        """上传文件到指定房间的媒体目录
        
        Args:
            file: Flask文件对象
            room_id: 房间ID（数据库中的主键）
        
        Returns:
            str: 保存的文件名，如果上传失败则返回None
        """
        # 检查文件格式是否允许
        if not RoomPhotoManager.allowed_file(file.filename):
            return None
        
        # 确保房间目录存在
        room_dir = RoomPhotoManager.ensure_room_directory_exists(room_id)
        
        # 使用原始文件名，但确保文件名安全
        unique_filename = secure_filename(file.filename)
        
        # 保存文件
        file.save(os.path.join(room_dir, unique_filename))
        
        return unique_filename
    
    @staticmethod
    def delete_file(filename, room_id):
        """删除指定房间媒体目录中的文件
        
        Args:
            filename: 文件名
            room_id: 房间ID（数据库中的主键）
        
        Returns:
            bool: 是否删除成功
        """
        try:
            # 获取房间目录
            room_dir = RoomPhotoManager.ensure_room_directory_exists(room_id)
            # 构建文件完整路径
            file_path = os.path.join(room_dir, filename)
            # 检查文件是否存在并删除
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception:
            return False
    
    @staticmethod
    def get_media_files(room_id):
        """获取指定房间的所有媒体文件，返回包含详细信息的列表
        
        Args:
            room_id: 房间ID（数据库中的主键）
        
        Returns:
            list: 包含媒体文件详细信息的列表
        """
        # 获取房间目录
        room_dir = RoomPhotoManager.ensure_room_directory_exists(room_id)
        
        # 初始化结果列表
        media_files = []
        
        # 遍历房间目录中的所有文件
        if os.path.exists(room_dir):
            for filename in os.listdir(room_dir):
                # 构建文件完整路径
                file_path = os.path.join(room_dir, filename)
                # 检查文件是否是普通文件（非目录）
                if os.path.isfile(file_path):
                    # 获取文件信息
                    file_info = {
                        'filename': filename,
                        'url': RoomPhotoManager.get_media_url(filename, room_id),
                        'path': file_path,
                        # 使用文件修改时间作为上传时间的近似值
                        'upload_time': datetime.fromtimestamp(os.path.getmtime(file_path))
                    }
                    
                    # 根据文件类型设置type字段
                    if RoomPhotoManager.is_image_file(filename):
                        file_info['type'] = 'image'
                        media_files.append(file_info)
                    elif RoomPhotoManager.is_video_file(filename):
                        file_info['type'] = 'video'
                        media_files.append(file_info)
        
        # 按上传时间倒序排序
        media_files.sort(key=lambda x: x['upload_time'], reverse=True)
        
        return media_files
    
    @staticmethod
    def get_file_path(filename, room_id):
        """获取媒体文件的完整路径
        
        Args:
            filename: 文件名
            room_id: 房间ID（数据库中的主键）
        
        Returns:
            str: 文件的完整路径，如果文件不存在则返回None
        """
        # 获取房间目录
        room_dir = RoomPhotoManager.ensure_room_directory_exists(room_id)
        # 构建文件完整路径
        file_path = os.path.join(room_dir, filename)
        # 检查文件是否存在
        if os.path.exists(file_path):
            return file_path
        return None
    
    @staticmethod
    def get_media_url(filename, room_id):
        """生成媒体文件的访问URL
        
        Args:
            filename: 文件名
            room_id: 房间ID（数据库中的主键）
        
        Returns:
            str: 媒体文件的访问URL
        """
        # 注意：这里返回的是相对URL，需要与room_api_bp的URL前缀匹配
        return f"/api/rooms/media/{room_id}/{filename}"
    
    @staticmethod
    def delete_room_directory(room_id):
        """删除整个房间的媒体目录
        
        Args:
            room_id: 房间ID（数据库中的主键）
        
        Returns:
            bool: 是否删除成功
        """
        try:
            # 获取房间目录
            room_dir = RoomPhotoManager.ensure_room_directory_exists(room_id)
            # 如果目录存在，则删除
            if os.path.exists(room_dir) and os.path.isdir(room_dir):
                shutil.rmtree(room_dir)
                return True
            return False
        except Exception:
            return False

# 创建一个全局实例，方便直接导入使用
room_photo_manager = RoomPhotoManager()
