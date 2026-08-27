
import os
import shutil
import random
import mimetypes
from flask import current_app
from datetime import datetime

# 支持的文件格式分类
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm'}
ALLOWED_DOCUMENT_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv'}


class AssetPhotoManager:
    """资产照片管理工具类，处理资产照片和附件的上传、存储和访问"""

    @staticmethod
    def get_media_root_dir():
        """获取媒体文件的根目录，确保正确目录存在
        根据不同环境(Docker、Windows打包、开发环境)返回正确的数据存储路径
        """
        import sys

        # 检查是否是Docker环境
        if os.environ.get('DOCKER_ENV') == 'true':
            # Docker环境下，数据存储在/data目录
            media_root = '/data/photo/asset_photo'
        # 检查是否是PyInstaller打包环境
        elif getattr(sys, 'frozen', False):
            # 获取打包后可执行文件所在目录
            app_dir = os.path.dirname(os.path.abspath(sys.executable))
            # 在可执行文件同级目录创建data/photo/asset_photo
            media_root = os.path.join(app_dir, 'data', 'photo', 'asset_photo')
        else:
            # 开发环境下使用相对路径
            app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            media_root = os.path.join(app_root, 'data', 'photo', 'asset_photo')

        # 确保目录存在
        os.makedirs(media_root, exist_ok=True)
        return media_root

    @staticmethod
    def ensure_asset_directory_exists(asset_id):
        """确保特定资产的照片目录存在

        Args:
            asset_id: 资产ID（数据库中的主键）

        Returns:
            str: 资产照片目录的绝对路径
        """
        # 获取媒体根目录
        media_root = AssetPhotoManager.get_media_root_dir()
        # 构建资产目录路径：data/photo/asset_photo/{asset_id}
        asset_dir = os.path.join(media_root, str(asset_id))
        # 确保目录存在
        os.makedirs(asset_dir, exist_ok=True)
        return asset_dir

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
    def is_document_file(filename):
        """检查文件是否是文档格式

        Args:
            filename: 文件名

        Returns:
            bool: 是否是文档文件
        """
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in ALLOWED_DOCUMENT_EXTENSIONS

    @staticmethod
    def get_file_type(filename):
        """根据文件扩展名判断文件类型

        Args:
            filename: 文件名

        Returns:
            str: 文件类型 ('image', 'video', 'document', 'other')
        """
        if AssetPhotoManager.is_image_file(filename):
            return 'image'
        elif AssetPhotoManager.is_video_file(filename):
            return 'video'
        elif AssetPhotoManager.is_document_file(filename):
            return 'document'
        else:
            return 'other'

    @staticmethod
    def upload_file(asset_id, file):
        """上传文件到指定资产的照片目录

        Args:
            asset_id: 资产ID（数据库中的主键）
            file: Flask文件对象

        Returns:
            str: 保存的文件名，如果上传失败则返回None
        """
        # 确保资产目录存在
        asset_dir = AssetPhotoManager.ensure_asset_directory_exists(asset_id)

        # 从原始文件名提取扩展名
        original_filename = file.filename or ''
        ext = ''
        if '.' in original_filename:
            ext = '.' + original_filename.rsplit('.', 1)[1].lower()

        # 使用时间戳+随机数+保留原始扩展名的命名策略，避免中文文件名问题
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        random_hex = '%04x' % random.randint(0, 0xFFFF)
        unique_filename = f"{timestamp}_{random_hex}{ext}"

        # 保存文件
        file.save(os.path.join(asset_dir, unique_filename))

        return unique_filename

    @staticmethod
    def delete_file(asset_id, filename):
        """删除指定资产照片目录中的文件

        Args:
            asset_id: 资产ID（数据库中的主键）
            filename: 文件名

        Returns:
            bool: 是否删除成功
        """
        try:
            # 获取资产目录
            asset_dir = AssetPhotoManager.ensure_asset_directory_exists(asset_id)
            # 构建文件完整路径
            file_path = os.path.join(asset_dir, filename)
            # 检查文件是否存在并删除
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception:
            return False

    @staticmethod
    def get_media_files(asset_id):
        """获取指定资产的所有媒体文件，返回包含详细信息的列表

        Args:
            asset_id: 资产ID（数据库中的主键）

        Returns:
            list: 包含媒体文件详细信息的列表
        """
        # 获取资产目录
        asset_dir = AssetPhotoManager.ensure_asset_directory_exists(asset_id)

        # 初始化结果列表
        media_files = []

        # 遍历资产目录中的所有文件
        if os.path.exists(asset_dir):
            for filename in os.listdir(asset_dir):
                # 构建文件完整路径
                file_path = os.path.join(asset_dir, filename)
                # 检查文件是否是普通文件（非目录）
                if os.path.isfile(file_path):
                    # 获取文件信息
                    file_info = {
                        'filename': filename,
                        'url': AssetPhotoManager.get_media_url(filename, asset_id),
                        'path': file_path,
                        # 使用文件修改时间作为上传时间的近似值
                        'upload_time': datetime.fromtimestamp(os.path.getmtime(file_path)),
                        # 根据扩展名分类文件类型
                        'type': AssetPhotoManager.get_file_type(filename)
                    }
                    media_files.append(file_info)

        # 按上传时间倒序排序
        media_files.sort(key=lambda x: x['upload_time'], reverse=True)

        return media_files

    @staticmethod
    def get_file_path(asset_id, filename):
        """获取照片文件的完整路径

        Args:
            asset_id: 资产ID（数据库中的主键）
            filename: 文件名

        Returns:
            str: 文件的完整路径，如果文件不存在则返回None
        """
        # 获取资产目录
        asset_dir = AssetPhotoManager.ensure_asset_directory_exists(asset_id)
        # 构建文件完整路径
        file_path = os.path.join(asset_dir, filename)
        # 检查文件是否存在
        if os.path.exists(file_path):
            return file_path
        return None

    @staticmethod
    def get_media_url(filename, asset_id):
        """生成照片文件的访问URL

        Args:
            filename: 文件名
            asset_id: 资产ID（数据库中的主键）

        Returns:
            str: 照片文件的访问URL
        """
        # 注意：这里返回的是相对URL，需要与fixed_asset_api_bp的URL前缀匹配
        return f"/api/fixed_assets/media/{asset_id}/{filename}"

    @staticmethod
    def delete_all_files(asset_id):
        """删除整个资产的照片目录

        Args:
            asset_id: 资产ID（数据库中的主键）

        Returns:
            bool: 是否删除成功
        """
        try:
            # 获取资产目录
            asset_dir = AssetPhotoManager.ensure_asset_directory_exists(asset_id)
            # 如果目录存在，则删除
            if os.path.exists(asset_dir) and os.path.isdir(asset_dir):
                shutil.rmtree(asset_dir)
                return True
            return False
        except Exception:
            return False


# 创建一个全局实例，方便直接导入使用
asset_photo_manager = AssetPhotoManager()