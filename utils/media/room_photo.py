
import os
import shutil
import time
import random
import mimetypes
import logging
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
            app_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
        # 验证room_id为有效正整数
        try:
            room_id = int(room_id)
            if room_id <= 0:
                raise ValueError(f"room_id必须为正整数，收到: {room_id}")
        except (ValueError, TypeError) as e:
            raise ValueError(f"无效的room_id: {room_id}") from e
        # 获取媒体根目录
        media_root = RoomPhotoManager.get_media_root_dir()
        # 构建房间目录路径：data/photo/room_photo/房间ID
        room_dir = os.path.join(media_root, str(room_id))
        # 安全验证：确保路径仍在预期根目录下
        room_dir = os.path.realpath(room_dir)
        if not room_dir.startswith(os.path.realpath(media_root)):
            raise ValueError(f"路径遍历检测: room_id={room_id}")
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
        
        # 使用原始扩展名，用时间戳+随机数生成唯一文件名，避免 secure_filename 破坏中文
        original_filename = file.filename or ''
        ext = ''
        if '.' in original_filename:
            ext = '.' + original_filename.rsplit('.', 1)[1].lower()
        # 生成唯一文件名：时间戳 + 随机数 + 原始扩展名
        unique_filename = f"{int(time.time())}_{random.randint(1000, 9999)}{ext}"
        
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
            # 安全处理filename，防止路径遍历
            filename = secure_filename(filename) if filename else ''
            if not filename:
                return False
            # 获取房间目录
            room_dir = RoomPhotoManager.ensure_room_directory_exists(room_id)
            # 构建文件完整路径
            file_path = os.path.join(room_dir, filename)
            # 安全验证：确保路径仍在预期目录下
            file_path = os.path.realpath(file_path)
            if not file_path.startswith(os.path.realpath(room_dir)):
                return False
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
                    
                    # 根据扩展名推断 MIME 类型
                    mime_type, _ = mimetypes.guess_type(filename)
                    file_info['mime_type'] = mime_type or 'application/octet-stream'
                    
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
        # 安全处理filename，防止路径遍历
        filename = secure_filename(filename) if filename else ''
        if not filename:
            return None
        # 获取房间目录
        room_dir = RoomPhotoManager.ensure_room_directory_exists(room_id)
        # 构建文件完整路径
        file_path = os.path.join(room_dir, filename)
        # 安全验证：确保路径仍在预期目录下
        file_path = os.path.realpath(file_path)
        if not file_path.startswith(os.path.realpath(room_dir)):
            return None
        # 棋查文件是否存在
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

    # ========== 临时上传方法（用于添加房间时，房间尚未创建的场景） ==========
    
    @staticmethod
    def get_temp_dir(create=True):
        """获取临时上传目录的根目录
        
        临时文件存储在 media_root 的 __temp__ 子目录下，
        按 temp_key 组织：data/photo/room_photo/__temp__/{temp_key}/
        
        Args:
            create: 是否自动创建目录，默认True。查询时传False避免空目录产生。
            
        Returns:
            str: 临时目录的根目录绝对路径
        """
        media_root = RoomPhotoManager.get_media_root_dir()
        temp_root = os.path.join(media_root, '__temp__')
        if create:
            os.makedirs(temp_root, exist_ok=True)
        return temp_root
    
    @staticmethod
    def get_temp_key_dir(temp_key, create=True):
        """获取指定temp_key的临时上传目录
        
        Args:
            temp_key: 临时标识key（如 room_add_timestamp_random）
            create: 是否自动创建目录，默认True。查询时传False避免空目录产生。
            
        Returns:
            str: 临时目录的绝对路径
        """
        # 安全处理temp_key，防止路径遍历
        temp_key = secure_filename(temp_key) if temp_key else ''
        if not temp_key:
            raise ValueError("无效的temp_key参数")
        temp_root = RoomPhotoManager.get_temp_dir(create=False)
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
        """上传文件到临时目录（添加房间页面使用，此时房间尚未创建）
        
        Args:
            file: Flask文件对象
            temp_key: 临时标识key
            
        Returns:
            str: 保存的文件名，如果上传失败则返回None
        """
        if not RoomPhotoManager.allowed_file(file.filename):
            return None
        
        key_temp_dir = RoomPhotoManager.get_temp_key_dir(temp_key)
        
        # 使用原始扩展名，用时间戳+随机数生成唯一文件名
        original_filename = file.filename or ''
        ext = ''
        if '.' in original_filename:
            ext = '.' + original_filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{int(time.time())}_{random.randint(1000, 9999)}{ext}"
        
        try:
            file.save(os.path.join(key_temp_dir, unique_filename))
            return unique_filename
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
        key_temp_dir = RoomPhotoManager.get_temp_key_dir(temp_key, create=False)
        
        if not os.path.exists(key_temp_dir):
            return media_files
        
        for filename in os.listdir(key_temp_dir):
            file_path = os.path.join(key_temp_dir, filename)
            
            if os.path.isdir(file_path):
                continue
            
            if not RoomPhotoManager.allowed_file(filename):
                continue
            
            file_type = 'image' if RoomPhotoManager.is_image_file(filename) else ('video' if RoomPhotoManager.is_video_file(filename) else 'other')
            
            media_files.append({
                'filename': filename,
                'type': file_type,
                'url': RoomPhotoManager.get_temp_media_url(filename, temp_key),
                'path': file_path,
                'upload_time': datetime.fromtimestamp(os.path.getmtime(file_path))
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
        return f"/api/rooms/temp_media/{temp_key}/{filename}"
    
    @staticmethod
    def get_temp_file_path(filename, temp_key):
        """获取临时目录中文件的绝对路径
        
        Args:
            filename: 文件名
            temp_key: 临时标识key
            
        Returns:
            str: 文件的绝对路径
        """
        # 安全处理filename，防止路径遍历
        filename = secure_filename(filename) if filename else ''
        if not filename:
            return None
        key_temp_dir = RoomPhotoManager.get_temp_key_dir(temp_key, create=False)
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
        key_temp_dir = RoomPhotoManager.get_temp_key_dir(temp_key, create=False)
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
            RoomPhotoManager._cleanup_empty_temp_dir(key_temp_dir)
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
        key_temp_dir = RoomPhotoManager.get_temp_key_dir(temp_key, create=False)
        
        if not os.path.exists(key_temp_dir):
            return {'deleted': 0, 'errors': []}
        
        deleted = 0
        errors = []
        
        for filename in os.listdir(key_temp_dir):
            file_path = os.path.join(key_temp_dir, filename)
            
            if os.path.isdir(file_path):
                continue
            
            if not RoomPhotoManager.allowed_file(filename):
                continue
            
            try:
                os.remove(file_path)
                deleted += 1
            except Exception as e:
                errors.append(f"删除文件 {filename} 失败: {str(e)}")
        
        # 清理空的临时目录
        RoomPhotoManager._cleanup_empty_temp_dir(key_temp_dir)
        
        return {'deleted': deleted, 'errors': errors}
    
    @staticmethod
    def move_temp_to_permanent(temp_key, room_id):
        """将临时目录中的所有文件移动到正式的房间目录
        
        在房间创建成功后调用，此时房间ID已确定。
        如果目标目录已有同名文件，添加时间戳避免覆盖。
        移动完成后自动清理空的临时目录。
        
        Args:
            temp_key: 临时标识key
            room_id: 房间ID（数据库中的主键）
            
        Returns:
            dict: {'moved': int, 'errors': list} 移动数量和错误信息
        """
        key_temp_dir = RoomPhotoManager.get_temp_key_dir(temp_key, create=False)
        
        if not os.path.exists(key_temp_dir):
            logging.info(f"move_temp_to_permanent: 临时目录不存在, temp_key={temp_key}, path={key_temp_dir}")
            return {'moved': 0, 'errors': []}
        
        # 目标目录需要创建（这是正式保存，需要确保目录存在）
        target_dir = RoomPhotoManager.ensure_room_directory_exists(room_id)
        logging.info(f"move_temp_to_permanent: temp_key={temp_key}, room_id={room_id}, source={key_temp_dir}, target={target_dir}")
        
        moved = 0
        errors = []
        
        for filename in os.listdir(key_temp_dir):
            file_path = os.path.join(key_temp_dir, filename)
            
            if os.path.isdir(file_path):
                continue
            
            if not RoomPhotoManager.allowed_file(filename):
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
        RoomPhotoManager._cleanup_empty_temp_dir(key_temp_dir)
        
        logging.info(f"move_temp_to_permanent: 完成, moved={moved}, errors={len(errors)}, temp_key={temp_key}, room_id={room_id}")
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
            temp_root = RoomPhotoManager.get_temp_dir(create=False)
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
            temp_root = RoomPhotoManager.get_temp_dir(create=False)
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
                    logging.warning(f"清理房间临时目录 {temp_key_path} 时出错: {str(e)}")
            
            if result['deleted_files'] > 0 or result['deleted_dirs'] > 0:
                logging.info(f"房间临时文件清理完成: 删除 {result['deleted_files']} 个文件, "
                           f"{result['deleted_dirs']} 个空目录, {result['errors']} 个错误")
            return result
        except Exception as e:
            logging.error(f"清理房间临时文件时发生错误: {str(e)}")
            result['errors'] += 1
            return result

# 创建一个全局实例，方便直接导入使用
room_photo_manager = RoomPhotoManager()
