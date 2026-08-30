import os
import shutil
import random
import mimetypes
from flask import current_app
from datetime import datetime


# 支持的文件格式分类
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'svg'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv', 'webm'}
ALLOWED_DOCUMENT_EXTENSIONS = {'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx', 'txt', 'csv', 'ofd'}
ALLOWED_COMPRESSED_EXTENSIONS = {'zip', 'rar', '7z', 'tar', 'gz'}

# 合同附件允许的所有扩展名
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS | ALLOWED_VIDEO_EXTENSIONS | ALLOWED_DOCUMENT_EXTENSIONS | ALLOWED_COMPRESSED_EXTENSIONS


class ContractAttachmentManager:
    """合同附件管理工具类，处理合同附件的上传、存储和访问
    基于纯文件系统模式，不依赖数据库记录
    """

    @staticmethod
    def get_media_root_dir():
        """获取合同附件的根目录，确保正确目录存在
        根据不同环境(Docker、Windows打包、开发环境)返回正确的数据存储路径
        路径规范: data/photo/contract_attachments/
        """
        import sys

        # 检查是否是Docker环境
        if os.environ.get('DOCKER_ENV') == 'true':
            media_root = '/data/photo/contract_attachments'
        # 检查是否是PyInstaller打包环境
        elif getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(os.path.abspath(sys.executable))
            media_root = os.path.join(app_dir, 'data', 'photo', 'contract_attachments')
        else:
            app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            media_root = os.path.join(app_root, 'data', 'photo', 'contract_attachments')

        os.makedirs(media_root, exist_ok=True)
        return media_root

    @staticmethod
    def ensure_contract_directory_exists(contract_id):
        """确保指定合同的附件目录存在

        Args:
            contract_id: 合同ID

        Returns:
            str: 合同附件目录的绝对路径
        """
        media_root = ContractAttachmentManager.get_media_root_dir()
        contract_dir = os.path.join(media_root, str(contract_id))
        os.makedirs(contract_dir, exist_ok=True)
        return contract_dir

    @staticmethod
    def is_allowed_file(filename):
        """检查文件扩展名是否允许"""
        if '.' not in filename:
            return False
        ext = filename.rsplit('.', 1)[1].lower()
        return ext in ALLOWED_EXTENSIONS

    @staticmethod
    def is_image_file(filename):
        """检查文件是否是图片格式"""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

    @staticmethod
    def is_video_file(filename):
        """检查文件是否是视频格式"""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in ALLOWED_VIDEO_EXTENSIONS

    @staticmethod
    def is_document_file(filename):
        """检查文件是否是文档格式"""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in ALLOWED_DOCUMENT_EXTENSIONS

    @staticmethod
    def is_compressed_file(filename):
        """检查文件是否是压缩文件格式"""
        return '.' in filename and \
               filename.rsplit('.', 1)[1].lower() in ALLOWED_COMPRESSED_EXTENSIONS

    @staticmethod
    def get_file_type(filename):
        """根据文件扩展名判断文件类型

        Args:
            filename: 文件名

        Returns:
            str: 文件类型 ('image', 'video', 'document', 'compressed', 'other')
        """
        if ContractAttachmentManager.is_image_file(filename):
            return 'image'
        elif ContractAttachmentManager.is_video_file(filename):
            return 'video'
        elif ContractAttachmentManager.is_document_file(filename):
            return 'document'
        elif ContractAttachmentManager.is_compressed_file(filename):
            return 'compressed'
        else:
            return 'other'

    @staticmethod
    def upload_file(contract_id, file):
        """上传合同附件

        Args:
            contract_id: 合同ID
            file: Flask文件对象

        Returns:
            str: 保存的文件名，如果上传失败则返回None
        """
        original_filename = file.filename or ''

        # 校验文件类型
        if not ContractAttachmentManager.is_allowed_file(original_filename):
            return None

        # 确保合同目录存在
        contract_dir = ContractAttachmentManager.ensure_contract_directory_exists(contract_id)

        # 保留原始文件名，处理重名
        saved_filename = original_filename
        base_name, ext = os.path.splitext(original_filename)
        counter = 1
        while os.path.exists(os.path.join(contract_dir, saved_filename)):
            saved_filename = f"{base_name}_{counter}{ext}"
            counter += 1

        # 保存文件
        file.save(os.path.join(contract_dir, saved_filename))

        return saved_filename

    @staticmethod
    def delete_file(contract_id, filename):
        """删除指定合同附件目录中的文件

        Args:
            contract_id: 合同ID
            filename: 文件名

        Returns:
            bool: 是否删除成功
        """
        try:
            contract_dir = ContractAttachmentManager.ensure_contract_directory_exists(contract_id)
            file_path = os.path.join(contract_dir, filename)
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
        except Exception:
            return False

    @staticmethod
    def get_media_files(contract_id):
        """获取指定合同的所有附件文件，返回包含详细信息的列表

        Args:
            contract_id: 合同ID

        Returns:
            list: 包含附件文件详细信息的列表，每项包含:
                - filename: 文件名
                - url: 访问URL
                - path: 完整路径
                - upload_time: 上传时间
                - type: 文件类型
                - file_size: 文件大小(字节)
        """
        contract_dir = ContractAttachmentManager.ensure_contract_directory_exists(contract_id)

        media_files = []

        if os.path.exists(contract_dir):
            for filename in os.listdir(contract_dir):
                file_path = os.path.join(contract_dir, filename)
                if os.path.isfile(file_path):
                    file_info = {
                        'filename': filename,
                        'url': ContractAttachmentManager.get_media_url(filename, contract_id),
                        'path': file_path,
                        'upload_time': datetime.fromtimestamp(os.path.getmtime(file_path)),
                        'type': ContractAttachmentManager.get_file_type(filename),
                        'file_size': os.path.getsize(file_path)
                    }
                    media_files.append(file_info)

        # 按上传时间倒序排序
        media_files.sort(key=lambda x: x['upload_time'], reverse=True)

        return media_files

    @staticmethod
    def get_file_path(contract_id, filename):
        """获取附件文件的完整路径

        Args:
            contract_id: 合同ID
            filename: 文件名

        Returns:
            str: 文件的完整路径，如果文件不存在则返回None
        """
        contract_dir = ContractAttachmentManager.ensure_contract_directory_exists(contract_id)
        file_path = os.path.join(contract_dir, filename)
        if os.path.exists(file_path):
            return file_path
        return None

    @staticmethod
    def get_media_url(filename, contract_id):
        """生成合同附件文件的访问URL

        Args:
            filename: 文件名
            contract_id: 合同ID

        Returns:
            str: 附件文件的访问URL
        """
        return f"/api/contracts/media/{contract_id}/{filename}"

    @staticmethod
    def delete_all_files(contract_id):
        """删除整个合同的附件目录

        Args:
            contract_id: 合同ID

        Returns:
            bool: 是否删除成功
        """
        try:
            contract_dir = ContractAttachmentManager.ensure_contract_directory_exists(contract_id)
            if os.path.exists(contract_dir) and os.path.isdir(contract_dir):
                shutil.rmtree(contract_dir)
                return True
            return False
        except Exception:
            return False


# 创建一个全局实例，方便直接导入使用
contract_attachment_manager = ContractAttachmentManager()