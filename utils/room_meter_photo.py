import os
import shutil
from werkzeug.utils import secure_filename
from datetime import datetime

# 支持的图片和视频格式
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv'}
ALLOWED_EXTENSIONS = ALLOWED_IMAGE_EXTENSIONS.union(ALLOWED_VIDEO_EXTENSIONS)

class RoomMeterManager:
    """抄表媒体文件管理工具类，处理抄表照片和视频的上传、存储和访问"""
    
    @staticmethod
    def get_media_root_dir():
        """获取抄表媒体文件的根目录，确保正确目录存在
        根据不同环境(Docker、Windows打包、开发环境)返回正确的数据存储路径
        """
        import os
        import sys
        
        # 检查是否是Docker环境
        if os.environ.get('DOCKER_ENV') == 'true':
            # Docker环境下，数据存储在/data目录
            media_root = '/data/photo/room_meter_photo'
        # 检查是否是PyInstaller打包环境
        elif getattr(sys, 'frozen', False):
            # 获取打包后可执行文件所在目录
            app_dir = os.path.dirname(os.path.abspath(sys.executable))
            # 在可执行文件同级目录创建data/photo/room_meter_photo
            media_root = os.path.join(app_dir, 'data', 'photo', 'room_meter_photo')
        else:
            # 开发环境下使用相对路径
            app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            media_root = os.path.join(app_root, 'data', 'photo', 'room_meter_photo')
        
        # 确保目录存在
        os.makedirs(media_root, exist_ok=True)
        return media_root
    
    @staticmethod
    def get_billing_period_dir(billing_period):
        """获取指定账期的目录，确保账期目录存在
        
        Args:
            billing_period: 账期，格式应为 'YYYY-MM'
            
        Returns:
            str: 账期目录的绝对路径
        """
        # 获取媒体根目录
        media_root = RoomMeterManager.get_media_root_dir()
        # 构建账期目录路径：data/photo/room_meter_photo/YYYY-MM
        billing_dir = os.path.join(media_root, secure_filename(billing_period))
        # 确保目录存在
        os.makedirs(billing_dir, exist_ok=True)
        return billing_dir
    
    @staticmethod
    def get_room_directory(billing_period, room_id):
        """获取指定账期和room_id的房间目录，确保目录存在
        
        Args:
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 房间ID
            
        Returns:
            str: 房间目录的绝对路径
        """
        # 获取账期目录
        billing_dir = RoomMeterManager.get_billing_period_dir(billing_period)
        # 构建房间目录路径：data/room_meter_photo/YYYY-MM/房间ID
        room_dir = os.path.join(billing_dir, str(room_id))
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
    def upload_file(file, billing_period, room_id):
        """上传文件到指定账期和room_id的房间目录
        
        Args:
            file: Flask文件对象
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 房间ID
            
        Returns:
            str: 保存的文件名，如果上传失败则返回None
        """
        # 检查文件格式是否允许
        if not RoomMeterManager.allowed_file(file.filename):
            return None
        
        # 确保目录存在
        room_dir = RoomMeterManager.get_room_directory(billing_period, room_id)
        
        # 使用原始文件名，但确保文件名安全
        new_filename = secure_filename(file.filename)
        
        # 保存文件
        try:
            file.save(os.path.join(room_dir, new_filename))
            return new_filename
        except Exception as e:
            print(f"上传文件失败: {str(e)}")
            return None
    
    @staticmethod
    def get_file_path(filename, billing_period, room_id):
        """获取文件的绝对路径
        
        Args:
            filename: 文件名
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 房间ID
            
        Returns:
            str: 文件的绝对路径
        """
        room_dir = RoomMeterManager.get_room_directory(billing_period, room_id)
        return os.path.join(room_dir, secure_filename(filename))
    
    @staticmethod
    def get_media_files(billing_period, room_id):
        """获取指定账期和room_id的所有媒体文件
        
        Args:
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 房间ID
            
        Returns:
            list: 媒体文件列表，每个元素包含文件名、类型和相对路径
        """
        media_files = []
        room_dir = RoomMeterManager.get_room_directory(billing_period, room_id)
        
        # 检查目录是否存在
        if not os.path.exists(room_dir):
            return media_files
        
        # 获取目录中的所有文件
        for filename in os.listdir(room_dir):
            file_path = os.path.join(room_dir, filename)
            
            # 跳过目录
            if os.path.isdir(file_path):
                continue
            
            # 检查文件是否是允许的格式
            if not RoomMeterManager.allowed_file(filename):
                continue
            
            # 确定文件类型
            file_type = 'image' if RoomMeterManager.is_image_file(filename) else 'video'
            
            # 添加文件信息到列表
            media_files.append({
                'filename': filename,
                'type': file_type,
                'path': file_path,
                # 使用文件修改时间作为上传时间的近似值
                'upload_time': datetime.fromtimestamp(os.path.getmtime(file_path))
            })
        
        return media_files
    
    @staticmethod
    def delete_file(filename, billing_period, room_id):
        """删除指定的文件
        
        Args:
            filename: 文件名
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 房间ID
            
        Returns:
            bool: 是否删除成功
        """
        file_path = RoomMeterManager.get_file_path(filename, billing_period, room_id)
        
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
    def get_media_url(filename, billing_period, room_id):
        """获取文件的URL路径
        
        Args:
            filename: 文件名
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 房间ID
            
        Returns:
            str: 文件的URL路径
        """
        # 构建URL路径，这个路径将被Flask路由处理
        return f"/utility-meter/media/{billing_period}/{room_id}/{filename}"
    
    @staticmethod
    def delete_media_by_billing_period(billing_period, room_id=None):
        """按账期删除媒体文件，可以选择指定房间
        
        Args:
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 可选，房间ID。如果提供，则只删除该房间的媒体文件；否则删除整个账期的所有媒体文件
            
        Returns:
            bool: 是否删除成功
        """
        if room_id is not None:
            # 获取指定账期下的指定房间目录
            room_dir = RoomMeterManager.get_room_directory(billing_period, room_id)
            
            # 检查房间目录是否存在
            if not os.path.exists(room_dir):
                return True  # 目录不存在，视为删除成功
            
            # 删除房间目录及其所有内容
            try:
                shutil.rmtree(room_dir)
                print(f"成功删除账期 {billing_period} 下房间 {room_id} 的所有媒体文件")
                return True
            except Exception as e:
                print(f"删除账期 {billing_period} 下房间 {room_id} 的媒体文件失败: {str(e)}")
                return False
        else:
            # 如果未提供room_id，则保持原有逻辑，删除整个账期的所有媒体文件
            # 获取账期目录
            billing_dir = RoomMeterManager.get_billing_period_dir(billing_period)
            
            # 检查目录是否存在
            if not os.path.exists(billing_dir):
                return True  # 目录不存在，视为删除成功
            
            # 删除账期目录及其所有内容
            try:
                shutil.rmtree(billing_dir)
                print(f"成功删除账期 {billing_period} 下的所有媒体文件")
                return True
            except Exception as e:
                print(f"删除账期 {billing_period} 下的媒体文件失败: {str(e)}")
                return False
    
    @staticmethod
    def delete_media_by_room(room_id):
        """按房间删除所有媒体文件（跨所有账期）
        
        Args:
            room_id: 房间ID
            
        Returns:
            bool: 是否删除成功（如果所有找到的房间目录都被成功删除）
        """
        # 获取媒体根目录
        media_root = RoomMeterManager.get_media_root_dir()
        
        # 安全的房间ID字符串
        safe_room_id = f"room_{secure_filename(str(room_id))}"
        
        # 标记是否所有删除操作都成功
        all_success = True
        
        # 遍历所有账期目录
        try:
            for billing_period in os.listdir(media_root):
                billing_dir = os.path.join(media_root, billing_period)
                
                # 跳过非目录项
                if not os.path.isdir(billing_dir):
                    continue
                
                # 构建房间目录路径
                room_dir = os.path.join(billing_dir, safe_room_id)
                
                # 如果房间目录存在，则删除
                if os.path.exists(room_dir):
                    try:
                        shutil.rmtree(room_dir)
                        print(f"成功删除账期 {billing_period} 下房间 {room_id} 的所有媒体文件")
                    except Exception as e:
                        print(f"删除账期 {billing_period} 下房间 {room_id} 的媒体文件失败: {str(e)}")
                        all_success = False
            
            return all_success
        except Exception as e:
            print(f"遍历账期目录时发生错误: {str(e)}")
            return False

# 创建room_meter单例对象供其他模块使用
room_meter_manager = RoomMeterManager()