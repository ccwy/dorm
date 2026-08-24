# 导出所有蓝图供主程序注册
# 认证相关
from .login import login_bp

# 用户管理相关
from .user import user_bp
from .user_api import user_api_bp
from .user_operations import user_operations_bp  # 人员操作蓝图
from .user_import_export import user_import_export_bp  # 人员导入导出蓝图

# 宿舍与房间管理相关
from .room import room_bp
from .room_api import room_api_bp
from .room_import_export import room_import_export_bp
from .dorm import dorm_bp

from .dorm_import_export import dorm_import_export_bp

# 系统配置与日志相关
from .system_settings import system_config_bp  # 系统配置蓝图
from .log import log_bp    # 操作日志蓝图

# 水电费相关
from .utility_room_meter import utility_room_meter_bp    # 抄表记录蓝图
from .utility_room_meter_import_export import utility_room_meter_import_export_bp    # 抄表记录蓝图

from .utility_index import utility_index_bp    # 水电费首页蓝图

from .utility_room_bill_records import utility_room_bill_records_bp  # 主表蓝图
from .utility_room_bill_occupants import utility_room_bill_occupants_bp  # 子表蓝图
from .utility_room_bill_checkout import utility_room_bill_checkout_bp #退宿人员子表蓝图
from .utility_user_records_detail import utility_user_records_detail_bp #用户水电费详情蓝图

from .fee_subsidy import fee_subsidy_bp #补贴蓝图
from .fee_subsidy_import_export import fee_subsidy_import_export_bp #补贴导入导出蓝图


# 文件共享相关
from .file_sharing import file_sharing_bp

# 留言管理相关
from .ticket_user import ticket_user_bp
from .ticket_admin import ticket_admin_bp

# 待办事项相关
from .todo import todo_bp

# 其他功能入口
from .other import other_bp

# 聊天功能
from .chat import chat_bp
