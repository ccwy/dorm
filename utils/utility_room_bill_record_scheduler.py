import schedule
import time
from datetime import datetime
from threading import Thread
import logging

# 每月生成费用主表记录的日期（固定为1号）
GENERATION_DAY = 1



# 直接在应用上下文中执行数据库操作
def generate_monthly_utility_records():
    """
    每月生成费用主表记录
    """
    try:
        # 内部导入所需模型
        from models.utility.utility_room_bill_record import RoomUtilityRecord
        from utils.db import db  # 导入数据库实例
        # 获取当前年月作为账期 - 修改为带连字符的格式
        current_year = datetime.now().year
        current_month = datetime.now().month
        billing_period = f"{current_year}-{current_month:02d}"  # 格式：YYYY-MM
        
        logging.info(f"开始生成{current_year}年{current_month}月费用主表记录")
        created_count = RoomUtilityRecord.create_empty_records_for_period(billing_period)
        if created_count > 0:
            db.session.commit()  # 提交事务
            logging.info(f"成功生成{current_year}年{current_month}月费用主表记录并提交事务")
            return True
        else:
            logging.info(f"费用主表记录生成完成：账期{billing_period}的所有房间记录已存在，无需创建新记录")
            return True  # 即使没有新记录，也返回成功
    except Exception as e:
        db.session.rollback()  # 出错时回滚事务
        logging.error(f"生成费用主表记录时发生错误: {str(e)}", exc_info=True)
        return False

# 检查是否需要生成记录并执行
def check_and_generate_records():
    """
    每月1号检查是否需要生成记录并执行
    """
    try:
        if datetime.now().day == GENERATION_DAY:
            logging.info(f"当前日期为每月{GENERATION_DAY}号，符合生成条件，开始执行生成任务")
            generate_monthly_utility_records()
        return True
    except Exception as e:
        logging.error(f"检查并生成记录时发生错误: {str(e)}", exc_info=True)
        return False

# 启动调度器
def start_scheduler(app):
    """
    启动调度器
    """
    try:
        # 在应用上下文中执行
        with app.app_context():
            # 固定时间为01:00
            FIXED_GENERATION_TIME = '01:00'
            # 维修临时文件清理时间：每天02:00
            MAINTENANCE_CLEANUP_TIME = '02:00'
            
            # 注册费用主表记录生成任务（每天01:00检查，每月1号执行生成）
            schedule.every().day.at(FIXED_GENERATION_TIME).do(lambda: execute_with_context(app, check_and_generate_records))
            logging.info(f"费用主表记录自动生成调度器已启动，将在每月{GENERATION_DAY}日的{FIXED_GENERATION_TIME}执行任务，每60秒检查一次")
            
            # 维修临时文件清理任务（每天02:00执行一次）
            schedule.every().day.at(MAINTENANCE_CLEANUP_TIME).do(lambda: execute_with_context(app, cleanup_maintenance_temp_files))
            logging.info(f"维修临时文件定时清理任务已注册，将在每天{MAINTENANCE_CLEANUP_TIME}执行")
            
            # 房间临时文件清理任务（每天02:30执行一次）
            ROOM_CLEANUP_TIME = '02:30'
            schedule.every().day.at(ROOM_CLEANUP_TIME).do(lambda: execute_with_context(app, cleanup_room_temp_files))
            logging.info(f"房间临时文件定时清理任务已注册，将在每天{ROOM_CLEANUP_TIME}执行")
            
            # 循环执行任务
            while True:
                schedule.run_pending()
                time.sleep(60)  # 每60秒检查一次
                
    except Exception as e:
        logging.error(f"调度器运行出错: {str(e)}", exc_info=True)

# 在应用上下文中执行函数
def execute_with_context(app, func):
    """在应用上下文中执行指定函数"""
    with app.app_context():
        return func()

# 清理维修临时文件
def cleanup_maintenance_temp_files():
    """清理超过24小时的维修临时文件"""
    try:
        from utils.media.maintenance_photo import MaintenancePhotoManager
        result = MaintenancePhotoManager.cleanup_old_temp_files(max_age_hours=24)
        if result['deleted_files'] > 0 or result['deleted_dirs'] > 0:
            logging.info(f"维修临时文件定时清理: 删除 {result['deleted_files']} 个文件, "
                        f"{result['deleted_dirs']} 个空目录, {result['errors']} 个错误")
        return True
    except Exception as e:
        logging.error(f"清理维修临时文件时发生错误: {str(e)}", exc_info=True)
        return False

# 清理房间临时文件
def cleanup_room_temp_files():
    """清理超过24小时的房间临时文件"""
    try:
        from utils.media.room_photo import RoomPhotoManager
        result = RoomPhotoManager.cleanup_old_temp_files(max_age_hours=24)
        if result['deleted_files'] > 0 or result['deleted_dirs'] > 0:
            logging.info(f"房间临时文件定时清理: 删除 {result['deleted_files']} 个文件, "
                        f"{result['deleted_dirs']} 个空目录, {result['errors']} 个错误")
        return True
    except Exception as e:
        logging.error(f"清理房间临时文件时发生错误: {str(e)}", exc_info=True)
        return False

# 初始化调度器
def init_scheduler(app):
    """
    初始化调度器，在应用启动时调用
    """
    try:
        # 固定为开启状态
        logging.info("费用主表记录自动生成功能已启用，正在启动调度器...")
        # 创建并启动调度器线程
        scheduler_thread = Thread(target=lambda: start_scheduler(app), daemon=True)
        scheduler_thread.start()
        logging.info("费用主表记录自动生成调度器已在后台启动")
                
    except Exception as e:
        logging.error(f"初始化调度器时发生错误: {str(e)}", exc_info=True)

