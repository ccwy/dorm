import os
import shutil
import mimetypes
import logging
from werkzeug.utils import secure_filename
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
        # 检查是否是Android环境
        elif os.environ.get('ANDROID_ENV', 'false').lower() == 'true':
            media_root = os.path.join(os.environ.get('APP_DATA_DIR', '/data'), 'photo', 'contract_attachments')
        # 检查是否是PyInstaller打包环境
        elif getattr(sys, 'frozen', False):
            app_dir = os.path.dirname(os.path.abspath(sys.executable))
            media_root = os.path.join(app_dir, 'data', 'photo', 'contract_attachments')
        else:
            app_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
        # 验证contract_id为有效正整数
        try:
            contract_id = int(contract_id)
            if contract_id <= 0:
                raise ValueError(f"contract_id必须为正整数，收到: {contract_id}")
        except (ValueError, TypeError) as e:
            raise ValueError(f"无效的contract_id: {contract_id}") from e
        # 获取媒体根目录
        media_root = ContractAttachmentManager.get_media_root_dir()
        # 构建合同目录路径
        contract_dir = os.path.join(media_root, str(contract_id))
        # 安全验证：确保路径仍在预期根目录下
        contract_dir = os.path.realpath(contract_dir)
        if not contract_dir.startswith(os.path.realpath(media_root)):
            raise ValueError(f"路径遍历检测: contract_id={contract_id}")
        # 确保目录存在
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

        # 确保合同目录存在（同时验证contract_id合法性）
        contract_dir = ContractAttachmentManager.ensure_contract_directory_exists(contract_id)

        # 使用secure_filename保留原始文件名
        saved_filename = secure_filename(original_filename)
        if not saved_filename:
            # secure_filename结果为空时使用默认名
            ext = ''
            if '.' in original_filename:
                ext = '.' + original_filename.rsplit('.', 1)[1].lower()
            saved_filename = f"untitled{ext}"

        # 文件名冲突时追加数字后缀避免覆盖
        if os.path.exists(os.path.join(contract_dir, saved_filename)):
            name, ext = os.path.splitext(saved_filename)
            counter = 1
            while os.path.exists(os.path.join(contract_dir, f"{name}_{counter}{ext}")):
                counter += 1
            saved_filename = f"{name}_{counter}{ext}"

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
            # 安全处理filename，防止路径遍历
            filename = secure_filename(filename) if filename else ''
            if not filename:
                return False
            # 获取合同目录（同时验证contract_id合法性）
            contract_dir = ContractAttachmentManager.ensure_contract_directory_exists(contract_id)
            # 构建文件完整路径
            file_path = os.path.join(contract_dir, filename)
            # 安全验证：确保路径仍在预期目录下
            file_path = os.path.realpath(file_path)
            if not file_path.startswith(os.path.realpath(contract_dir)):
                return False
            # 检查文件是否存在并删除
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
                    mime_type, _ = mimetypes.guess_type(filename)
                    file_info = {
                        'filename': filename,
                        'url': ContractAttachmentManager.get_media_url(filename, contract_id),
                        'path': file_path,
                        'upload_time': datetime.fromtimestamp(os.path.getmtime(file_path)),
                        'type': ContractAttachmentManager.get_file_type(filename),
                        'file_size': os.path.getsize(file_path),
                        'mime_type': mime_type or 'application/octet-stream'
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
        # 安全处理filename，防止路径遍历
        filename = secure_filename(filename) if filename else ''
        if not filename:
            return None
        # 获取合同目录（同时验证contract_id合法性）
        contract_dir = ContractAttachmentManager.ensure_contract_directory_exists(contract_id)
        # 构建文件完整路径
        file_path = os.path.join(contract_dir, filename)
        # 安全验证：确保路径仍在预期目录下
        file_path = os.path.realpath(file_path)
        if not file_path.startswith(os.path.realpath(contract_dir)):
            return None
        # 检查文件是否存在
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

    # ========== 临时上传方法（用于新增合同时，合同尚未创建的场景） ==========

    @staticmethod
    def get_temp_dir(create=True):
        """获取临时上传目录的根目录

        临时文件存储在 media_root 的 __temp__ 子目录下，
        按 temp_key 组织：data/photo/contract_attachments/__temp__/{temp_key}/

        Args:
            create: 是否自动创建目录，默认True。查询时传False避免空目录产生。

        Returns:
            str: 临时目录的根目录绝对路径
        """
        media_root = ContractAttachmentManager.get_media_root_dir()
        temp_root = os.path.join(media_root, '__temp__')
        if create:
            os.makedirs(temp_root, exist_ok=True)
        return temp_root

    @staticmethod
    def get_temp_key_dir(temp_key, create=True):
        """获取指定temp_key的临时上传目录

        Args:
            temp_key: 临时标识key（如 contract_add_timestamp_random）
            create: 是否自动创建目录，默认True。查询时传False避免空目录产生。

        Returns:
            str: 临时目录的绝对路径
        """
        # 安全处理temp_key，防止路径遍历
        temp_key = secure_filename(temp_key) if temp_key else ''
        if not temp_key:
            raise ValueError("无效的temp_key参数")
        temp_root = ContractAttachmentManager.get_temp_dir(create=False)
        key_temp_dir = os.path.join(temp_root, str(temp_key))
        # 安全验证：确保路径仍在预期根目录下
        key_temp_dir = os.path.realpath(key_temp_dir)
        if not key_temp_dir.startswith(os.path.realpath(temp_root)):
            raise ValueError(f"路径遍历检测: temp_key={temp_key}")
        if create:
            os.makedirs(key_temp_dir, exist_ok=True)
        return key_temp_dir

    @staticmethod
    def upload_temp_file(file, temp_key):
        """上传文件到临时目录（新增合同页面使用，此时合同尚未创建）

        Args:
            file: Flask文件对象
            temp_key: 临时标识key

        Returns:
            str: 保存的文件名，如果上传失败则返回None
        """
        if not ContractAttachmentManager.is_allowed_file(file.filename):
            return None

        key_temp_dir = ContractAttachmentManager.get_temp_key_dir(temp_key)

        # 使用secure_filename保留原始文件名
        original_filename = file.filename or ''
        saved_filename = secure_filename(original_filename)
        if not saved_filename:
            # secure_filename结果为空时使用默认名
            ext = ''
            if '.' in original_filename:
                ext = '.' + original_filename.rsplit('.', 1)[1].lower()
            saved_filename = f"untitled{ext}"

        # 文件名冲突时追加数字后缀避免覆盖
        if os.path.exists(os.path.join(key_temp_dir, saved_filename)):
            name, ext = os.path.splitext(saved_filename)
            counter = 1
            while os.path.exists(os.path.join(key_temp_dir, f"{name}_{counter}{ext}")):
                counter += 1
            saved_filename = f"{name}_{counter}{ext}"

        try:
            file.save(os.path.join(key_temp_dir, saved_filename))
            return saved_filename
        except Exception as e:
            logging.error(f"上传临时文件失败: {str(e)}")
            return None

    @staticmethod
    def get_temp_media_files(temp_key):
        """获取指定temp_key临时目录中的所有媒体文件

        Args:
            temp_key: 临时标识key

        Returns:
            list: 媒体文件列表，每项包含 filename, type, url, upload_time
        """
        media_files = []
        key_temp_dir = ContractAttachmentManager.get_temp_key_dir(temp_key, create=False)

        if not os.path.exists(key_temp_dir):
            return media_files

        for filename in os.listdir(key_temp_dir):
            file_path = os.path.join(key_temp_dir, filename)

            if os.path.isdir(file_path):
                continue

            if not ContractAttachmentManager.is_allowed_file(filename):
                continue

            file_type = ContractAttachmentManager.get_file_type(filename)
            mime_type, _ = mimetypes.guess_type(filename)

            media_files.append({
                'filename': filename,
                'type': file_type,
                'url': ContractAttachmentManager.get_temp_media_url(filename, temp_key),
                'path': file_path,
                'upload_time': datetime.fromtimestamp(os.path.getmtime(file_path)),
                'file_size': os.path.getsize(file_path),
                'mime_type': mime_type or 'application/octet-stream'
            })

        # 按上传时间倒序排序
        media_files.sort(key=lambda x: x['upload_time'], reverse=True)
        return media_files

    @staticmethod
    def get_temp_media_url(filename, temp_key):
        """获取临时文件的URL路径

        Args:
            filename: 文件名
            temp_key: 临时标识key

        Returns:
            str: 文件的URL路径
        """
        return f"/api/contracts/temp_media/{temp_key}/{filename}"

    @staticmethod
    def get_temp_file_path(filename, temp_key):
        """获取临时目录中文件的绝对路径

        Args:
            filename: 文件名
            temp_key: 临时标识key

        Returns:
            str: 文件的绝对路径，不存在或路径异常返回None
        """
        # 安全处理filename，防止路径遍历
        filename = secure_filename(filename) if filename else ''
        if not filename:
            return None
        key_temp_dir = ContractAttachmentManager.get_temp_key_dir(temp_key, create=False)
        file_path = os.path.join(key_temp_dir, filename)
        # 安全验证：确保路径仍在预期目录下
        file_path = os.path.realpath(file_path)
        key_temp_dir_real = os.path.realpath(key_temp_dir)
        if not file_path.startswith(key_temp_dir_real):
            return None
        return file_path

    @staticmethod
    def delete_temp_file(filename, temp_key):
        """删除临时目录中的指定文件，删除后若目录为空则自动清理

        Args:
            filename: 文件名
            temp_key: 临时标识key

        Returns:
            bool: 是否删除成功
        """
        # 安全处理filename，防止路径遍历
        filename = secure_filename(filename) if filename else ''
        if not filename:
            return False
        key_temp_dir = ContractAttachmentManager.get_temp_key_dir(temp_key, create=False)
        file_path = os.path.join(key_temp_dir, filename)
        # 安全验证：确保路径仍在预期目录下
        file_path = os.path.realpath(file_path)
        key_temp_dir_real = os.path.realpath(key_temp_dir)
        if not file_path.startswith(key_temp_dir_real):
            return False

        if not os.path.exists(file_path):
            return False

        try:
            os.remove(file_path)
            # 删除后检查目录是否为空，为空则清理
            ContractAttachmentManager._cleanup_empty_temp_dir(key_temp_dir)
            return True
        except Exception as e:
            logging.error(f"删除临时文件失败: {str(e)}")
            return False

    @staticmethod
    def clear_temp_files(temp_key):
        """清理指定temp_key临时目录中的所有媒体文件

        Args:
            temp_key: 临时标识key

        Returns:
            dict: {'deleted': int, 'errors': list} 删除数量和错误信息
        """
        key_temp_dir = ContractAttachmentManager.get_temp_key_dir(temp_key, create=False)

        if not os.path.exists(key_temp_dir):
            return {'deleted': 0, 'errors': []}

        deleted = 0
        errors = []

        for filename in os.listdir(key_temp_dir):
            file_path = os.path.join(key_temp_dir, filename)

            if os.path.isdir(file_path):
                continue

            if not ContractAttachmentManager.is_allowed_file(filename):
                continue

            try:
                os.remove(file_path)
                deleted += 1
            except Exception as e:
                errors.append(f"删除文件 {filename} 失败: {str(e)}")

        # 清理空的临时目录
        ContractAttachmentManager._cleanup_empty_temp_dir(key_temp_dir)

        return {'deleted': deleted, 'errors': errors}

    @staticmethod
    def move_temp_to_permanent(temp_key, contract_id):
        """将临时目录中的所有文件移动到正式的合同附件目录

        在合同创建成功后调用，此时合同ID已确定。
        如果目标目录已有同名文件，添加时间戳避免覆盖。
        移动完成后自动清理空的临时目录。

        Args:
            temp_key: 临时标识key
            contract_id: 合同ID

        Returns:
            dict: {'moved': int, 'errors': list} 移动数量和错误信息
        """
        key_temp_dir = ContractAttachmentManager.get_temp_key_dir(temp_key, create=False)

        if not os.path.exists(key_temp_dir):
            logging.info(f"move_temp_to_permanent: 临时目录不存在, temp_key={temp_key}, path={key_temp_dir}")
            return {'moved': 0, 'errors': []}

        # 目标目录需要创建（这是正式保存，需要确保目录存在）
        target_dir = ContractAttachmentManager.ensure_contract_directory_exists(contract_id)
        logging.info(f"move_temp_to_permanent: temp_key={temp_key}, contract_id={contract_id}, source={key_temp_dir}, target={target_dir}")

        moved = 0
        errors = []

        for filename in os.listdir(key_temp_dir):
            file_path = os.path.join(key_temp_dir, filename)

            if os.path.isdir(file_path):
                continue

            if not ContractAttachmentManager.is_allowed_file(filename):
                logging.debug(f"move_temp_to_permanent: 跳过不允许的文件类型: {filename}")
                continue

            target_path = os.path.join(target_dir, filename)

            # 如果目标已有同名文件，添加时间戳
            if os.path.exists(target_path):
                name, ext = os.path.splitext(filename)
                new_filename = f"{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
                target_path = os.path.join(target_dir, new_filename)
                logging.info(f"move_temp_to_permanent: 目标文件已存在，重命名为 {new_filename}")

            try:
                shutil.move(file_path, target_path)
                moved += 1
                logging.info(f"move_temp_to_permanent: 成功移动文件 {filename} -> {target_path}")
            except Exception as e:
                errors.append(f"移动文件 {filename} 失败: {str(e)}")
                logging.error(f"move_temp_to_permanent: 移动临时文件失败: {str(e)}, file={filename}, source={file_path}, target={target_path}")

        # 移动完成后清理空的临时目录
        ContractAttachmentManager._cleanup_empty_temp_dir(key_temp_dir)

        logging.info(f"move_temp_to_permanent: 完成, moved={moved}, errors={len(errors)}, temp_key={temp_key}, contract_id={contract_id}")
        return {'moved': moved, 'errors': errors}

    @staticmethod
    def _cleanup_empty_temp_dir(key_temp_dir):
        """清理空的临时目录，向上递归删除空的父目录直到__temp__为止

        Args:
            key_temp_dir: 临时目录路径
        """
        try:
            # 检查key临时目录是否为空，为空则删除
            if os.path.exists(key_temp_dir) and not os.listdir(key_temp_dir):
                os.rmdir(key_temp_dir)

            # 检查__temp__根目录是否为空，为空也删除
            temp_root = ContractAttachmentManager.get_temp_dir(create=False)
            if os.path.exists(temp_root) and not os.listdir(temp_root):
                os.rmdir(temp_root)
        except Exception as e:
            logging.warning(f"清理临时目录失败: {str(e)}")

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
            temp_root = ContractAttachmentManager.get_temp_dir(create=False)
            if not os.path.exists(temp_root) or not os.path.isdir(temp_root):
                return result

            now = datetime.now().timestamp()
            max_age_seconds = max_age_hours * 3600

            # 遍历所有temp_key临时目录
            for temp_key_name in os.listdir(temp_root):
                temp_key_path = os.path.join(temp_root, temp_key_name)
                if not os.path.isdir(temp_key_path):
                    continue

                try:
                    # 遍历临时目录中的文件
                    files_remaining = False
                    for filename in os.listdir(temp_key_path):
                        file_path = os.path.join(temp_key_path, filename)
                        if os.path.isfile(file_path):
                            file_age = now - os.path.getmtime(file_path)
                            if file_age > max_age_seconds:
                                os.remove(file_path)
                                result['deleted_files'] += 1
                            else:
                                files_remaining = True

                    # 如果目录为空，删除临时目录
                    if not files_remaining and not os.listdir(temp_key_path):
                        os.rmdir(temp_key_path)
                        result['deleted_dirs'] += 1
                except Exception as e:
                    result['errors'] += 1
                    logging.warning(f"清理合同临时目录 {temp_key_path} 时出错: {str(e)}")

            if result['deleted_files'] > 0 or result['deleted_dirs'] > 0:
                logging.info(f"合同临时文件清理完成: 删除 {result['deleted_files']} 个文件, "
                           f"{result['deleted_dirs']} 个空目录, {result['errors']} 个错误")
            return result
        except Exception as e:
            result['errors'] += 1
            logging.error(f"清理合同临时文件时发生错误: {str(e)}")
            return result


# 创建一个全局实例，方便直接导入使用
contract_attachment_manager = ContractAttachmentManager()