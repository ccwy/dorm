import os
import shutil
from werkzeug.utils import secure_filename
from datetime import datetime

# 支持的图片和视频格式
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv'}
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS.union(ALLOWED_VIDEO_EXTENSIONS)

class RoomMeterCheckoutPhotoManager:
    """退宿照片管理工具类，处理退宿照片和视频的上传、存储和访问"""
    
    @staticmethod
    def get_media_root_dir():
        """获取退宿照片的根目录，确保正确目录存在
        根据不同环境(Docker、Android、PyInstaller、开发环境)返回正确的数据存储路径
        """
        import os
        import sys
        
        # 检查是否是Docker环境
        if os.environ.get('DOCKER_ENV') == 'true':
            # Docker环境下，数据存储在/data目录
            media_root = '/data/room_meter_photo'
        # 检查是否是Android环境
        elif os.environ.get('ANDROID_ENV', 'false').lower() == 'true':
            media_root = os.path.join(os.environ.get('APP_DATA_DIR', '/data'), 'room_meter_photo')
        # 检查是否是PyInstaller打包环境
        elif getattr(sys, 'frozen', False):
            # 获取打包后可执行文件所在目录
            app_dir = os.path.dirname(os.path.abspath(sys.executable))
            # 在可执行文件同级目录创建data/room_meter_photo
            media_root = os.path.join(app_dir, 'data', 'room_meter_photo')
        else:
            # 开发环境下使用相对路径
            app_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            media_root = os.path.join(app_root, 'data', 'room_meter_photo')
        
        # 确保目录存在
        os.makedirs(media_root, exist_ok=True)
        return media_root
    
    @staticmethod
    def get_checkout_dir(billing_period, room_id, user_id, create=True):
        """获取指定账期、房间和用户的退宿照片目录
        
        Args:
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 房间ID
            user_id: 用户ID
            create: 是否自动创建目录，默认True。查询文件时传False避免空目录产生。
            
        Returns:
            str: 退宿照片目录的绝对路径
        """
        media_root = RoomMeterCheckoutPhotoManager.get_media_root_dir()
        # 构建目录路径：data/room_meter_photo/{账期}/{房间ID}/checkout/{用户ID}
        checkout_dir = os.path.join(
            media_root,
            secure_filename(billing_period),
            str(room_id),
            'checkout',
            str(user_id)
        )
        if create:
            os.makedirs(checkout_dir, exist_ok=True)
        return checkout_dir
    
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
    def upload_file(file, billing_period, room_id, user_id):
        """上传文件到指定账期、房间和用户目录
        
        Args:
            file: Flask文件对象
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 房间ID
            user_id: 用户ID
            
        Returns:
            str: 保存的文件名，如果上传失败则返回None
        """
        # 检查文件格式是否允许
        if not RoomMeterCheckoutPhotoManager.allowed_file(file.filename):
            return None
        
        # 确保目录存在
        checkout_dir = RoomMeterCheckoutPhotoManager.get_checkout_dir(billing_period, room_id, user_id)
        
        # 使用原始文件名，但确保文件名安全
        new_filename = secure_filename(file.filename)
        
        # 如果文件名已存在，添加时间戳避免覆盖
        target_path = os.path.join(checkout_dir, new_filename)
        if os.path.exists(target_path):
            name, ext = os.path.splitext(new_filename)
            new_filename = f"{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
        
        # 保存文件
        try:
            file.save(os.path.join(checkout_dir, new_filename))
            return new_filename
        except Exception as e:
            print(f"上传文件失败: {str(e)}")
            return None
    
    @staticmethod
    def delete_file(filename, billing_period, room_id, user_id):
        """删除指定的文件
        
        Args:
            filename: 文件名
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 房间ID
            user_id: 用户ID
            
        Returns:
            bool: 是否删除成功
        """
        file_path = RoomMeterCheckoutPhotoManager.get_file_path(filename, billing_period, room_id, user_id)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            return False
        
        # 删除文件
        try:
            os.remove(file_path)
            return True
        except Exception as e:
            print(f"删除文件失败: {str(e)}")
            return False
    
    @staticmethod
    def delete_checkout_directory(billing_period, room_id, user_id):
        """删除整个退宿照片目录
        
        Args:
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 房间ID
            user_id: 用户ID
            
        Returns:
            bool: 是否删除成功
        """
        checkout_dir = RoomMeterCheckoutPhotoManager.get_checkout_dir(billing_period, room_id, user_id, create=False)
        
        # 检查目录是否存在
        if not os.path.exists(checkout_dir):
            return True  # 目录不存在，视为删除成功
        
        # 删除目录及其所有内容
        try:
            shutil.rmtree(checkout_dir)
            print(f"成功删除账期 {billing_period} 下房间 {room_id} 用户 {user_id} 的所有媒体文件")
            return True
        except Exception as e:
            print(f"删除账期 {billing_period} 下房间 {room_id} 用户 {user_id} 的媒体文件失败: {str(e)}")
            return False
    
    @staticmethod
    def delete_media_by_billing_period(billing_period, room_id):
        """删除某账期某房间的所有退宿照片
        
        Args:
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 房间ID
            
        Returns:
            bool: 是否删除成功
        """
        media_root = RoomMeterCheckoutPhotoManager.get_media_root_dir()
        room_dir = os.path.join(media_root, secure_filename(billing_period), str(room_id))
        
        # 检查目录是否存在
        if not os.path.exists(room_dir):
            return True  # 目录不存在，视为删除成功
        
        # 删除房间目录及其所有内容
        try:
            shutil.rmtree(room_dir)
            print(f"成功删除账期 {billing_period} 下房间 {room_id} 的所有退宿照片")
            return True
        except Exception as e:
            print(f"删除账期 {billing_period} 下房间 {room_id} 的退宿照片失败: {str(e)}")
            return False
    
    @staticmethod
    def get_file_path(filename, billing_period, room_id, user_id):
        """获取文件的绝对路径
        
        Args:
            filename: 文件名
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 房间ID
            user_id: 用户ID
            
        Returns:
            str: 文件的绝对路径
        """
        # 不自动创建目录，仅拼接路径
        checkout_dir = RoomMeterCheckoutPhotoManager.get_checkout_dir(billing_period, room_id, user_id, create=False)
        return os.path.join(checkout_dir, secure_filename(filename))
    
    @staticmethod
    def get_media_url(filename, billing_period, room_id, user_id):
        """获取文件的URL路径
        
        Args:
            filename: 文件名
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 房间ID
            user_id: 用户ID
            
        Returns:
            str: 文件的URL路径
        """
        # 构建URL路径，这个路径将被Flask路由处理
        return f"/utility-checkout/media/{billing_period}/{room_id}/checkout/{user_id}/{filename}"
    
    @staticmethod
    def get_media_files(billing_period, room_id, user_id):
        """获取指定账期、房间和用户的所有媒体文件
        
        Args:
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 房间ID
            user_id: 用户ID
            
        Returns:
            list: 媒体文件列表，每个元素包含文件名、类型和相对路径
        """
        media_files = []
        # 查询时不自动创建目录，避免打开页面时产生空目录
        checkout_dir = RoomMeterCheckoutPhotoManager.get_checkout_dir(billing_period, room_id, user_id, create=False)
        
        # 检查目录是否存在
        if not os.path.exists(checkout_dir):
            return media_files
        
        # 获取目录中的所有文件
        for filename in os.listdir(checkout_dir):
            file_path = os.path.join(checkout_dir, filename)
            
            # 跳过目录
            if os.path.isdir(file_path):
                continue
            
            # 检查文件是否是允许的格式
            if not RoomMeterCheckoutPhotoManager.allowed_file(filename):
                continue
            
            # 确定文件类型
            file_type = 'image' if RoomMeterCheckoutPhotoManager.is_image_file(filename) else 'video'
            
            # 添加文件信息到列表
            media_files.append({
                'filename': filename,
                'type': file_type,
                'path': file_path,
                # 使用文件修改时间作为上传时间的近似值
                'upload_time': datetime.fromtimestamp(os.path.getmtime(file_path))
            })
        
        return media_files

# 创建退宿照片管理单例对象供其他模块使用
room_meter_checkout_photo_manager = RoomMeterCheckoutPhotoManager()