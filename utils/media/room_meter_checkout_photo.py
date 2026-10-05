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
            app_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            media_root = os.path.join(app_root, 'data', 'photo', 'room_meter_photo')
        
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
        # 构建目录路径：data/photo/room_meter_photo/{账期}/{房间ID}/checkout/{用户ID}
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
        
        # 诊断日志：打印目录路径
        print(f"[退宿照片诊断] get_media_files 查找目录: {checkout_dir}, billing_period={billing_period}, room_id={room_id}, user_id={user_id}")
        
        # 检查目录是否存在
        if not os.path.exists(checkout_dir):
            print(f"[退宿照片诊断] 目录不存在: {checkout_dir}")
            return media_files
        
        print(f"[退宿照片诊断] 目录存在，列出文件: {os.listdir(checkout_dir)}")
        
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

    # ========== 临时文件方法（退宿申请/审核页面使用，账期尚未确定时） ==========

    @staticmethod
    def get_temp_dir(create=True):
        """获取临时上传目录的根目录
        
        临时文件存储在 media_root 的 __temp__ 子目录下，
        按 room_id/checkout/user_id 组织：data/photo/room_meter_photo/__temp__/{room_id}/checkout/{user_id}/
        
        Args:
            create: 是否自动创建目录，默认True。查询时传False避免空目录产生。
            
        Returns:
            str: 临时目录的根目录绝对路径
        """
        media_root = RoomMeterCheckoutPhotoManager.get_media_root_dir()
        temp_root = os.path.join(media_root, '__temp__')
        if create:
            os.makedirs(temp_root, exist_ok=True)
        return temp_root

    @staticmethod
    def get_temp_checkout_dir(room_id, user_id, create=True):
        """获取指定房间和用户的退宿临时上传目录
        
        Args:
            room_id: 房间ID
            user_id: 用户ID
            create: 是否自动创建目录，默认True。查询时传False避免空目录产生。
            
        Returns:
            str: 用户退宿临时目录的绝对路径
        """
        temp_root = RoomMeterCheckoutPhotoManager.get_temp_dir(create=False)
        user_temp_dir = os.path.join(temp_root, str(room_id), 'checkout', str(user_id))
        if create:
            os.makedirs(user_temp_dir, exist_ok=True)
        return user_temp_dir

    @staticmethod
    def upload_to_temp(file, room_id, user_id):
        """上传文件到临时目录（退宿申请/审核页面使用，此时账期尚未确定）
        
        Args:
            file: Flask文件对象
            room_id: 房间ID
            user_id: 用户ID
            
        Returns:
            str: 保存的文件名，如果上传失败则返回None
        """
        if not RoomMeterCheckoutPhotoManager.allowed_file(file.filename):
            return None
        
        user_temp_dir = RoomMeterCheckoutPhotoManager.get_temp_checkout_dir(room_id, user_id)
        new_filename = secure_filename(file.filename)
        
        # 如果文件名已存在，添加时间戳避免覆盖
        target_path = os.path.join(user_temp_dir, new_filename)
        if os.path.exists(target_path):
            name, ext = os.path.splitext(new_filename)
            new_filename = f"{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}{ext}"
        
        try:
            file.save(os.path.join(user_temp_dir, new_filename))
            return new_filename
        except Exception as e:
            print(f"上传临时文件失败: {str(e)}")
            return None

    @staticmethod
    def get_temp_files(room_id, user_id):
        """获取指定房间和用户临时目录中的所有媒体文件
        
        Args:
            room_id: 房间ID
            user_id: 用户ID
            
        Returns:
            list: 媒体文件列表
        """
        media_files = []
        # 查询时不自动创建目录
        user_temp_dir = RoomMeterCheckoutPhotoManager.get_temp_checkout_dir(room_id, user_id, create=False)
        
        if not os.path.exists(user_temp_dir):
            return media_files
        
        for filename in os.listdir(user_temp_dir):
            file_path = os.path.join(user_temp_dir, filename)
            
            if os.path.isdir(file_path):
                continue
            
            if not RoomMeterCheckoutPhotoManager.allowed_file(filename):
                continue
            
            file_type = 'image' if RoomMeterCheckoutPhotoManager.is_image_file(filename) else 'video'
            
            media_files.append({
                'filename': filename,
                'type': file_type,
                'path': file_path,
                'upload_time': datetime.fromtimestamp(os.path.getmtime(file_path))
            })
        
        return media_files

    @staticmethod
    def delete_temp_file(filename, room_id, user_id):
        """删除临时目录中的指定文件，删除后若目录为空则自动清理
        
        Args:
            filename: 文件名
            room_id: 房间ID
            user_id: 用户ID
            
        Returns:
            bool: 是否删除成功
        """
        user_temp_dir = RoomMeterCheckoutPhotoManager.get_temp_checkout_dir(room_id, user_id, create=False)
        file_path = os.path.join(user_temp_dir, secure_filename(filename))
        
        if not os.path.exists(file_path):
            return False
        
        try:
            os.remove(file_path)
            # 删除后检查目录是否为空，为空则清理
            RoomMeterCheckoutPhotoManager._cleanup_empty_temp_dir(user_temp_dir)
            return True
        except Exception as e:
            print(f"删除临时文件失败: {str(e)}")
            return False

    @staticmethod
    def move_temp_to_billing_period(room_id, user_id, billing_period):
        """将房间用户的临时目录中的所有文件移动到正式的账期目录
        
        在退宿记录确认时调用，此时账期已确定。
        如果目标目录已有同名文件，添加时间戳避免覆盖。
        移动完成后自动清理空的临时目录。
        
        Args:
            room_id: 房间ID
            user_id: 用户ID
            billing_period: 账期，格式 'YYYY-MM'
            
        Returns:
            dict: {'moved': int, 'errors': list} 移动数量和错误信息
        """
        # 诊断日志
        print(f"[退宿照片诊断] move_temp_to_billing_period 调用: room_id={room_id}, user_id={user_id}, billing_period={billing_period}")
        
        # 查询临时目录时不自动创建
        user_temp_dir = RoomMeterCheckoutPhotoManager.get_temp_checkout_dir(room_id, user_id, create=False)
        
        if not os.path.exists(user_temp_dir):
            print(f"[退宿照片诊断] 临时目录不存在: {user_temp_dir}")
            return {'moved': 0, 'errors': []}
        
        print(f"[退宿照片诊断] 临时目录存在: {user_temp_dir}, 文件列表: {os.listdir(user_temp_dir)}")
        
        # 目标目录需要创建（这是正式保存，需要确保目录存在）
        target_dir = RoomMeterCheckoutPhotoManager.get_checkout_dir(billing_period, room_id, user_id, create=True)
        print(f"[退宿照片诊断] 目标目录: {target_dir}")
        
        moved = 0
        errors = []
        
        for filename in os.listdir(user_temp_dir):
            file_path = os.path.join(user_temp_dir, filename)
            
            if os.path.isdir(file_path):
                continue
            
            if not RoomMeterCheckoutPhotoManager.allowed_file(filename):
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
        RoomMeterCheckoutPhotoManager._cleanup_empty_temp_dir(user_temp_dir)
        
        print(f"[退宿照片诊断] move_temp_to_billing_period 完成: moved={moved}, errors={errors}, target_dir={target_dir}")
        return {'moved': moved, 'errors': errors}

    @staticmethod
    def get_temp_file_path(filename, room_id, user_id):
        """获取临时目录中文件的绝对路径
        
        Args:
            filename: 文件名
            room_id: 房间ID
            user_id: 用户ID
            
        Returns:
            str: 文件的绝对路径
        """
        # 不自动创建目录，仅拼接路径
        user_temp_dir = RoomMeterCheckoutPhotoManager.get_temp_checkout_dir(room_id, user_id, create=False)
        return os.path.join(user_temp_dir, secure_filename(filename))

    @staticmethod
    def get_temp_media_url(filename, room_id, user_id):
        """获取临时文件的URL路径
        
        Args:
            filename: 文件名
            room_id: 房间ID
            user_id: 用户ID
            
        Returns:
            str: 文件的URL路径
        """
        return f"/utility-checkout/temp_media/{room_id}/checkout/{user_id}/{filename}"

    @staticmethod
    def _cleanup_empty_temp_dir(user_temp_dir):
        """清理空的临时目录，向上递归删除空的父目录直到__temp__为止
        
        Args:
            user_temp_dir: 用户临时目录路径
        """
        try:
            # 检查用户临时目录是否为空，为空则删除
            if os.path.exists(user_temp_dir) and not os.listdir(user_temp_dir):
                os.rmdir(user_temp_dir)
            
            # 检查checkout目录是否为空，为空则删除
            checkout_dir = os.path.dirname(user_temp_dir)
            if os.path.exists(checkout_dir) and os.path.basename(checkout_dir) == 'checkout' and not os.listdir(checkout_dir):
                os.rmdir(checkout_dir)
            
            # 检查房间临时目录是否为空，为空则删除
            room_temp_dir = os.path.dirname(checkout_dir)
            if os.path.exists(room_temp_dir) and not os.listdir(room_temp_dir):
                os.rmdir(room_temp_dir)
            
            # 检查__temp__根目录是否为空，为空也删除
            temp_root = RoomMeterCheckoutPhotoManager.get_temp_dir(create=False)
            if os.path.exists(temp_root) and not os.listdir(temp_root):
                os.rmdir(temp_root)
        except Exception:
            pass

    @staticmethod
    def clear_user_temp_files(room_id, user_id):
        """清理指定房间用户的临时目录中的所有媒体文件

        Args:
            room_id: 房间ID
            user_id: 用户ID

        Returns:
            dict: {'deleted': int, 'errors': list} 删除数量和错误信息
        """
        user_temp_dir = RoomMeterCheckoutPhotoManager.get_temp_checkout_dir(room_id, user_id, create=False)

        if not os.path.exists(user_temp_dir):
            return {'deleted': 0, 'errors': []}

        deleted = 0
        errors = []

        for filename in os.listdir(user_temp_dir):
            file_path = os.path.join(user_temp_dir, filename)

            if os.path.isdir(file_path):
                continue

            if not RoomMeterCheckoutPhotoManager.allowed_file(filename):
                continue

            try:
                os.remove(file_path)
                deleted += 1
            except Exception as e:
                errors.append(f"删除文件 {filename} 失败: {str(e)}")

        # 清理空的临时目录
        RoomMeterCheckoutPhotoManager._cleanup_empty_temp_dir(user_temp_dir)

        return {'deleted': deleted, 'errors': errors}

    @staticmethod
    def clear_all_temp_files():
        """清理所有房间用户的临时目录中的媒体文件

        Returns:
            dict: {'deleted': int, 'errors': list, 'users_cleared': int} 删除数量、错误信息和清理的用户数
        """
        temp_root = RoomMeterCheckoutPhotoManager.get_temp_dir(create=False)

        if not os.path.exists(temp_root):
            return {'deleted': 0, 'errors': [], 'users_cleared': 0}

        total_deleted = 0
        all_errors = []
        users_cleared = 0

        try:
            for room_name in os.listdir(temp_root):
                room_dir = os.path.join(temp_root, room_name)

                if not os.path.isdir(room_dir):
                    continue

                checkout_dir = os.path.join(room_dir, 'checkout')
                if not os.path.exists(checkout_dir):
                    continue

                for user_name in os.listdir(checkout_dir):
                    user_dir = os.path.join(checkout_dir, user_name)

                    if not os.path.isdir(user_dir):
                        continue

                    user_deleted = 0
                    for filename in os.listdir(user_dir):
                        file_path = os.path.join(user_dir, filename)

                        if os.path.isdir(file_path):
                            continue

                        if not RoomMeterCheckoutPhotoManager.allowed_file(filename):
                            continue

                        try:
                            os.remove(file_path)
                            user_deleted += 1
                            total_deleted += 1
                        except Exception as e:
                            all_errors.append(f"房间 {room_name} 用户 {user_name} 文件 {filename} 删除失败: {str(e)}")

                    if user_deleted > 0:
                        users_cleared += 1

                    # 清理空的用户临时目录
                    RoomMeterCheckoutPhotoManager._cleanup_empty_temp_dir(user_dir)

        except Exception as e:
            all_errors.append(f"遍历临时目录失败: {str(e)}")

        return {'deleted': total_deleted, 'errors': all_errors, 'users_cleared': users_cleared}

# 创建退宿照片管理单例对象供其他模块使用
room_meter_checkout_photo_manager = RoomMeterCheckoutPhotoManager()