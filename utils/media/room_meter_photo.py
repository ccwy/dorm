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
        # 检查是否是Android环境
        elif os.environ.get('ANDROID_ENV', 'false').lower() == 'true':
            media_root = os.path.join(os.environ.get('APP_DATA_DIR', '/data'), 'photo', 'room_meter_photo')
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
    def get_room_directory(billing_period, room_id, create=True):
        """获取指定账期和room_id的房间目录
        
        Args:
            billing_period: 账期，格式应为 'YYYY-MM'
            room_id: 房间ID
            create: 是否自动创建目录，默认True。查询文件时传False避免空目录产生。
            
        Returns:
            str: 房间目录的绝对路径
        """
        # 获取账期目录
        billing_dir = RoomMeterManager.get_billing_period_dir(billing_period) if create else os.path.join(RoomMeterManager.get_media_root_dir(), secure_filename(billing_period))
        # 构建房间目录路径：data/room_meter_photo/YYYY-MM/房间ID
        room_dir = os.path.join(billing_dir, str(room_id))
        # 仅在create=True时确保目录存在
        if create:
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
        # 不自动创建目录，仅拼接路径
        room_dir = RoomMeterManager.get_room_directory(billing_period, room_id, create=False)
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
        # 查询时不自动创建目录，避免打开页面时产生空目录
        room_dir = RoomMeterManager.get_room_directory(billing_period, room_id, create=False)
        
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

    @staticmethod
    def get_temp_dir(create=True):
        """获取临时上传目录的根目录
        
        临时文件存储在 media_root 的 __temp__ 子目录下，
        按 room_id 组织：data/photo/room_meter_photo/__temp__/{room_id}/
        
        Args:
            create: 是否自动创建目录，默认True。查询时传False避免空目录产生。
            
        Returns:
            str: 临时目录的根目录绝对路径
        """
        media_root = RoomMeterManager.get_media_root_dir()
        temp_root = os.path.join(media_root, '__temp__')
        if create:
            os.makedirs(temp_root, exist_ok=True)
        return temp_root
    
    @staticmethod
    def get_temp_room_dir(room_id, create=True):
        """获取指定房间的临时上传目录
        
        Args:
            room_id: 房间ID
            create: 是否自动创建目录，默认True。查询时传False避免空目录产生。
            
        Returns:
            str: 房间临时目录的绝对路径
        """
        temp_root = RoomMeterManager.get_temp_dir(create=False)
        room_temp_dir = os.path.join(temp_root, str(room_id))
        if create:
            os.makedirs(room_temp_dir, exist_ok=True)
        return room_temp_dir
    
    @staticmethod
    def upload_to_temp(file, room_id):
        """上传文件到临时目录（抄表登记页面使用，此时账期尚未确定）
        
        Args:
            file: Flask文件对象
            room_id: 房间ID
            
        Returns:
            str: 保存的文件名，如果上传失败则返回None
        """
        if not RoomMeterManager.allowed_file(file.filename):
            return None
        
        room_temp_dir = RoomMeterManager.get_temp_room_dir(room_id)
        new_filename = secure_filename(file.filename)
        
        # 如果文件名已存在，添加时间戳避免覆盖
        target_path = os.path.join(room_temp_dir, new_filename)
        if os.path.exists(target_path):
            name, ext = os.path.splitext(new_filename)
            new_filename = f"{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
        
        try:
            file.save(os.path.join(room_temp_dir, new_filename))
            return new_filename
        except Exception as e:
            print(f"上传临时文件失败: {str(e)}")
            return None
    
    @staticmethod
    def get_temp_files(room_id):
        """获取指定房间临时目录中的所有媒体文件
        
        Args:
            room_id: 房间ID
            
        Returns:
            list: 媒体文件列表
        """
        media_files = []
        # 查询时不自动创建目录
        room_temp_dir = RoomMeterManager.get_temp_room_dir(room_id, create=False)
        
        if not os.path.exists(room_temp_dir):
            return media_files
        
        for filename in os.listdir(room_temp_dir):
            file_path = os.path.join(room_temp_dir, filename)
            
            if os.path.isdir(file_path):
                continue
            
            if not RoomMeterManager.allowed_file(filename):
                continue
            
            file_type = 'image' if RoomMeterManager.is_image_file(filename) else 'video'
            
            media_files.append({
                'filename': filename,
                'type': file_type,
                'path': file_path,
                'upload_time': datetime.fromtimestamp(os.path.getmtime(file_path))
            })
        
        return media_files
    
    @staticmethod
    def delete_temp_file(filename, room_id):
        """删除临时目录中的指定文件，删除后若目录为空则自动清理
        
        Args:
            filename: 文件名
            room_id: 房间ID
            
        Returns:
            bool: 是否删除成功
        """
        room_temp_dir = RoomMeterManager.get_temp_room_dir(room_id, create=False)
        file_path = os.path.join(room_temp_dir, secure_filename(filename))
        
        if not os.path.exists(file_path):
            return False
        
        try:
            os.remove(file_path)
            # 删除后检查目录是否为空，为空则清理
            RoomMeterManager._cleanup_empty_temp_dir(room_temp_dir)
            return True
        except Exception as e:
            print(f"删除临时文件失败: {str(e)}")
            return False
    
    @staticmethod
    def move_temp_to_billing_period(room_id, billing_period):
        """将房间临时目录中的所有文件移动到正式的账期目录
        
        在保存抄表记录时调用，此时账期已确定。
        如果目标目录已有同名文件，添加时间戳避免覆盖。
        移动完成后自动清理空的临时目录。
        
        Args:
            room_id: 房间ID
            billing_period: 账期，格式 'YYYY-MM'
            
        Returns:
            dict: {'moved': int, 'errors': list} 移动数量和错误信息
        """
        # 查询临时目录时不自动创建
        room_temp_dir = RoomMeterManager.get_temp_room_dir(room_id, create=False)
        
        if not os.path.exists(room_temp_dir):
            return {'moved': 0, 'errors': []}
        
        # 目标目录需要创建（这是正式保存，需要确保目录存在）
        target_dir = RoomMeterManager.get_room_directory(billing_period, room_id, create=True)
        
        moved = 0
        errors = []
        
        for filename in os.listdir(room_temp_dir):
            file_path = os.path.join(room_temp_dir, filename)
            
            if os.path.isdir(file_path):
                continue
            
            if not RoomMeterManager.allowed_file(filename):
                continue
            
            target_path = os.path.join(target_dir, filename)
            
            # 如果目标已有同名文件，添加时间戳
            if os.path.exists(target_path):
                name, ext = os.path.splitext(filename)
                new_filename = f"{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
                target_path = os.path.join(target_dir, new_filename)
            
            try:
                shutil.move(file_path, target_path)
                moved += 1
            except Exception as e:
                errors.append(f"移动文件 {filename} 失败: {str(e)}")
                print(f"移动临时文件失败: {str(e)}")
        
        # 移动完成后清理空的临时目录
        RoomMeterManager._cleanup_empty_temp_dir(room_temp_dir)
        
        return {'moved': moved, 'errors': errors}
    
    @staticmethod
    def get_temp_file_path(filename, room_id):
        """获取临时目录中文件的绝对路径
        
        Args:
            filename: 文件名
            room_id: 房间ID
            
        Returns:
            str: 文件的绝对路径
        """
        # 不自动创建目录，仅拼接路径
        room_temp_dir = RoomMeterManager.get_temp_room_dir(room_id, create=False)
        return os.path.join(room_temp_dir, secure_filename(filename))
    
    @staticmethod
    def get_temp_media_url(filename, room_id):
        """获取临时文件的URL路径
        
        Args:
            filename: 文件名
            room_id: 房间ID
            
        Returns:
            str: 文件的URL路径
        """
        return f"/utility-meter/temp_media/{room_id}/{filename}"

    @staticmethod
    def _cleanup_empty_temp_dir(room_temp_dir):
        """清理空的临时目录，向上递归删除空的父目录直到__temp__为止
        
        Args:
            room_temp_dir: 房间临时目录路径
        """
        try:
            # 检查房间临时目录是否为空，为空则删除
            if os.path.exists(room_temp_dir) and not os.listdir(room_temp_dir):
                os.rmdir(room_temp_dir)
            
            # 检查__temp__根目录是否为空，为空也删除
            temp_root = RoomMeterManager.get_temp_dir(create=False)
            if os.path.exists(temp_root) and not os.listdir(temp_root):
                os.rmdir(temp_root)
        except Exception:
            pass

    @staticmethod
    def clear_room_temp_files(room_id):
        """清理指定房间临时目录中的所有媒体文件

        Args:
            room_id: 房间ID

        Returns:
            dict: {'deleted': int, 'errors': list} 删除数量和错误信息
        """
        room_temp_dir = RoomMeterManager.get_temp_room_dir(room_id, create=False)

        if not os.path.exists(room_temp_dir):
            return {'deleted': 0, 'errors': []}

        deleted = 0
        errors = []

        for filename in os.listdir(room_temp_dir):
            file_path = os.path.join(room_temp_dir, filename)

            if os.path.isdir(file_path):
                continue

            if not RoomMeterManager.allowed_file(filename):
                continue

            try:
                os.remove(file_path)
                deleted += 1
            except Exception as e:
                errors.append(f"删除文件 {filename} 失败: {str(e)}")

        # 清理空的临时目录
        RoomMeterManager._cleanup_empty_temp_dir(room_temp_dir)

        return {'deleted': deleted, 'errors': errors}

    @staticmethod
    def clear_all_temp_files():
        """清理所有房间临时目录中的媒体文件

        Returns:
            dict: {'deleted': int, 'errors': list, 'rooms_cleared': int} 删除数量、错误信息和清理的房间数
        """
        temp_root = RoomMeterManager.get_temp_dir(create=False)

        if not os.path.exists(temp_root):
            return {'deleted': 0, 'errors': [], 'rooms_cleared': 0}

        total_deleted = 0
        all_errors = []
        rooms_cleared = 0

        try:
            for room_name in os.listdir(temp_root):
                room_dir = os.path.join(temp_root, room_name)

                if not os.path.isdir(room_dir):
                    continue

                room_deleted = 0
                for filename in os.listdir(room_dir):
                    file_path = os.path.join(room_dir, filename)

                    if os.path.isdir(file_path):
                        continue

                    if not RoomMeterManager.allowed_file(filename):
                        continue

                    try:
                        os.remove(file_path)
                        room_deleted += 1
                        total_deleted += 1
                    except Exception as e:
                        all_errors.append(f"房间 {room_name} 文件 {filename} 删除失败: {str(e)}")

                if room_deleted > 0:
                    rooms_cleared += 1

                # 清理空的房间临时目录
                RoomMeterManager._cleanup_empty_temp_dir(room_dir)

        except Exception as e:
            all_errors.append(f"遍历临时目录失败: {str(e)}")

        return {'deleted': total_deleted, 'errors': all_errors, 'rooms_cleared': rooms_cleared}

# 创建room_meter单例对象供其他模块使用
room_meter_manager = RoomMeterManager()