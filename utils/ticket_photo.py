import os
import shutil
import uuid
from flask import current_app
from werkzeug.utils import secure_filename
from datetime import datetime

# 支持的图片和视频格式
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv'}
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS.union(ALLOWED_VIDEO_EXTENSIONS)

class TicketPhotoManager:
    """留言照片管理工具类，处理留言照片和视频的上传、存储和访问"""
    
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
            media_root = '/data/photo/ticket_photo'
        # 检查是否是PyInstaller打包环境
        elif getattr(sys, 'frozen', False):
            # 获取打包后可执行文件所在目录
            app_dir = os.path.dirname(os.path.abspath(sys.executable))
            # 在可执行文件同级目录创建data/photo/ticket_photo
            media_root = os.path.join(app_dir, 'data', 'photo', 'ticket_photo')
        else:
            # 开发环境下使用相对路径
            app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            media_root = os.path.join(app_root, 'data', 'photo', 'ticket_photo')
        
        # 确保目录存在
        os.makedirs(media_root, exist_ok=True)
        return media_root
    
    @staticmethod
    def ensure_ticket_directory_exists(ticket_id):
        """确保特定留言的媒体目录存在
        
        Args:
            ticket_id: 留言ID（数据库中的主键）
        
        Returns:
            str: 留言媒体目录的绝对路径
        """
        # 获取媒体根目录
        media_root = TicketPhotoManager.get_media_root_dir()
        # 构建留言目录路径：data/photo/ticket_photo/留言ID
        ticket_dir = os.path.join(media_root, str(ticket_id))
        # 确保目录存在
        os.makedirs(ticket_dir, exist_ok=True)
        return ticket_dir
    
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
    def upload_file(file, ticket_id):
        """上传文件到指定留言的媒体目录
        
        Args:
            file: Flask文件对象
            ticket_id: 留言ID（数据库中的主键）
        
        Returns:
            str: 保存的文件名，如果上传失败则返回None
        """
        # 检查文件格式是否允许
        if not TicketPhotoManager.allowed_file(file.filename):
            return None
        
        # 确保留言目录存在
        ticket_dir = TicketPhotoManager.ensure_ticket_directory_exists(ticket_id)
        
        # 使用原始文件名，但确保文件名安全
        unique_filename = secure_filename(file.filename)
        
        # 保存文件
        file.save(os.path.join(ticket_dir, unique_filename))
        
        return unique_filename
    
    @staticmethod
    def delete_file(filename, ticket_id):
        """删除指定留言媒体目录中的文件
        
        Args:
            filename: 文件名
            ticket_id: 留言ID（数据库中的主键）
        
        Returns:
            bool: 是否删除成功
        """
        try:
            # 获取留言目录
            ticket_dir = TicketPhotoManager.ensure_ticket_directory_exists(ticket_id)
            # 构建文件完整路径
            file_path = os.path.join(ticket_dir, filename)
            # 检查文件是否存在并删除
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception:
            return False
    
    @staticmethod
    def get_media_files(ticket_id, is_admin=False):
        """获取指定留言的所有媒体文件，返回包含详细信息的列表
        
        Args:
            ticket_id: 留言ID（数据库中的主键）
            is_admin: 是否为管理端获取，默认为False
            
        Returns:
            list: 包含媒体文件详细信息的列表
        """
        # 获取留言目录
        ticket_dir = TicketPhotoManager.ensure_ticket_directory_exists(ticket_id)
        
        # 初始化结果列表
        media_files = []
        
        # 遍历留言目录中的所有文件
        if os.path.exists(ticket_dir):
            for filename in os.listdir(ticket_dir):
                # 构建文件完整路径
                file_path = os.path.join(ticket_dir, filename)
                # 检查文件是否是普通文件（非目录）
                if os.path.isfile(file_path):
                    # 获取文件信息
                    file_info = {
                        'filename': filename,
                        'url': TicketPhotoManager.get_media_url(ticket_id, filename, is_admin),
                        # 使用文件修改时间作为上传时间的近似值
                        'upload_time': datetime.fromtimestamp(os.path.getmtime(file_path))
                    }
                    
                    # 根据文件类型设置type字段
                    if TicketPhotoManager.is_image_file(filename):
                        file_info['type'] = 'image'
                        media_files.append(file_info)
                    elif TicketPhotoManager.is_video_file(filename):
                        file_info['type'] = 'video'
                        media_files.append(file_info)
        
        # 按上传时间倒序排序
        media_files.sort(key=lambda x: x['upload_time'], reverse=True)
        
        return media_files
    
    @staticmethod
    def get_file_path(filename, ticket_id):
        """获取媒体文件的完整路径
        
        Args:
            filename: 文件名
            ticket_id: 留言ID（数据库中的主键）
        
        Returns:
            str: 文件的完整路径，如果文件不存在则返回None
        """
        # 获取留言目录
        ticket_dir = TicketPhotoManager.ensure_ticket_directory_exists(ticket_id)
        # 构建文件完整路径
        file_path = os.path.join(ticket_dir, filename)
        # 检查文件是否存在
        if os.path.exists(file_path):
            return file_path
        return None
    
    @staticmethod
    def get_media_url(ticket_id, filename, is_admin=False):
        """生成媒体文件的访问URL
        
        Args:
            ticket_id: 留言ID（数据库中的主键）
            filename: 文件名
            is_admin: 是否为管理端URL，默认为False
            
        Returns:
            str: 媒体文件的访问URL
        """
        if is_admin:
            return f"/admin/ticket/media/{ticket_id}/{filename}"
        else:
            # 用户端URL，与ticket_user蓝图的URL前缀匹配
            return f"/user/ticket/media/{ticket_id}/{filename}"
    
    @staticmethod
    def delete_ticket_directory(ticket_id):
        """删除整个留言的媒体目录
        
        Args:
            ticket_id: 留言ID（数据库中的主键）
        
        Returns:
            bool: 是否删除成功
        """
        try:
            # 获取留言目录
            ticket_dir = TicketPhotoManager.ensure_ticket_directory_exists(ticket_id)
            # 如果目录存在，则删除
            if os.path.exists(ticket_dir) and os.path.isdir(ticket_dir):
                shutil.rmtree(ticket_dir)
                return True
            return False
        except Exception:
            return False

# 创建一个全局实例，方便直接导入使用
ticket_photo_manager = TicketPhotoManager()