import schedule
import time
from datetime import datetime
from threading import Thread
import logging

# 导入DatabaseConfig类
from utils.db_config import DatabaseConfig

# 获取生成日期配置
def get_generation_day():
    """从db_config读取配置，获取自定义抄表日作为生成日期"""
    try:
        config = DatabaseConfig.load_config()
        
        # 检查是否启用了自定义抄表日
        enable_custom_day = config.get('ENABLE_CUSTOM_METER_READING_DAY', False)
        
        if enable_custom_day:
            # 使用自定义抄表日
            day = config.get('CUSTOM_METER_READING_DAY', 1)
            #logging.info(f"检查是否需要生成费用主表记录，使用自定义抄表日: {day} 号")
        else:
            # 不启用自定义抄表日时使用默认值1号
            day = 1
            #logging.info(f"检查是否需要生成费用主表记录，未启用自定义抄表日，使用默认日期: {day}号")
        
        # 获取当前年份和月份，用于动态计算最大天数
        current_year = datetime.now().year
        current_month = datetime.now().month
        import calendar  # 导入calendar模块用于获取月份天数
        # 获取当前月份的实际最大天数
        max_days = calendar.monthrange(current_year, current_month)[1]
        
        # 确保返回值是整数且在有效范围内
        if isinstance(day, int) and 1 <= day <= max_days:
            return day
        # 如果设置的天数超过当月最大天数，返回当月最大天数
        elif isinstance(day, int) and day > max_days:
            logging.warning(f"配置的生成日期{day}超过了{current_year}年{current_month}月的最大天数{max_days}，已自动调整为{max_days}")
            return max_days
        return 1
    except Exception as e:
        logging.error(f"获取费用主表生成日期失败: {str(e)}")
        return 1



# 直接在应用上下文中执行数据库操作
def generate_monthly_utility_records():
    """
    每月生成费用主表记录
    """
    try:
        # 内部导入所需模型
        from models.utility_room_bill_record import RoomUtilityRecord
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
    检查是否需要生成记录并执行
    """
    try:
        generation_day = get_generation_day()
        if datetime.now().day == generation_day:
            logging.info("开始检查是否需要生成费用主表记录")
            logging.debug(f"生成日期: {generation_day}, 当前日期: {datetime.now().day}")
            logging.info(f"当前日期: {generation_day}，符合生成条件，开始执行生成任务")
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
            # 初始化变量
            current_generation_day = None
            current_job = None
            
            # 固定时间为01:00
            FIXED_GENERATION_TIME = '01:00'
            
            # 循环执行任务
            while True:
                # 获取生成日期配置
                new_generation_day = get_generation_day()
                
                # 检查日期配置是否变更
                if new_generation_day != current_generation_day:
                    # 如果有变更，先清除旧任务
                    if current_job:
                        schedule.cancel_job(current_job)
                        logging.info(f"已取消旧的定时任务（日期: {current_generation_day}）")
                    
                    # 创建新任务
                    current_job = schedule.every().day.at(FIXED_GENERATION_TIME).do(lambda: execute_with_context(app, check_and_generate_records))
                    current_generation_day = new_generation_day
                    logging.info(f"费用主表记录自动生成调度器已更新，将在每月{new_generation_day}日的{FIXED_GENERATION_TIME}执行任务，每60秒检查一次")
                #else:
                #    logging.info(f"未满足生成条件，当前日期={datetime.now().day}，任务日期：每月{current_generation_day}日的{FIXED_GENERATION_TIME}执行任务，每60秒检查一次")
                
                # 运行待执行的任务
                schedule.run_pending()
                time.sleep(60)  # 每60秒检查一次
                
    except Exception as e:
        logging.error(f"调度器运行出错: {str(e)}", exc_info=True)

# 在应用上下文中执行函数
def execute_with_context(app, func):
    """在应用上下文中执行指定函数"""
    with app.app_context():
        return func()

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

