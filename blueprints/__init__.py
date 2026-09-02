# 导出所有蓝图供主程序注册
# 认证相关
from .login import login_bp

# 用户管理相关
from .user import user_bp
from .user_api import user_api_bp
from .user_operations import user_operations_bp  # 人员操作蓝图
from .user_import_export import user_import_export_bp  # 导入导出蓝图（pandas已延迟导入）

# 宿舍与房间管理相关
from .room import room_bp
from .room_api import room_api_bp
from .room_import_export import room_import_export_bp  # 导入导出蓝图（pandas已延迟导入）
from .dorm import dorm_bp
from .dorm_import_export import dorm_import_export_bp  # 导入导出蓝图（pandas/openpyxl已延迟导入）

# 系统配置与日志相关
from .system_settings import system_config_bp  # 系统配置蓝图
from .log import log_bp    # 操作日志蓝图

# 水电费相关
from .utility_room_meter import utility_room_meter_bp    # 抄表记录蓝图
from .utility_room_meter_import_export import utility_room_meter_import_export_bp  # 导入导出蓝图（openpyxl/pandas已延迟导入）

from .utility_index import utility_index_bp    # 水电费首页蓝图

from .utility_room_bill_records import utility_room_bill_records_bp  # 主表蓝图
from .utility_room_bill_occupants import utility_room_bill_occupants_bp  # 子表蓝图
from .utility_room_bill_checkout import utility_room_bill_checkout_bp #退宿人员子表蓝图
from .utility_user_records_detail import utility_user_records_detail_bp #用户水电费详情蓝图

from .fee_subsidy import fee_subsidy_bp #补贴蓝图
from .fee_subsidy_import_export import fee_subsidy_import_export_bp  # 导入导出蓝图（openpyxl/pandas已延迟导入）


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

# 固定资产管理相关

from .fixed_asset import fixed_asset_bp
from . import fixed_asset_operations  # 先导入 operations，它会从 fixed_asset 导入 bp 并注册路由
# 注意：fixed_asset_operations 的路由直接注册在 fixed_asset_bp 上，无需单独导入蓝图
from .fixed_asset_api import fixed_asset_api_bp
from .fixed_asset_import_export import fixed_asset_import_export_bp

# 部门管理相关
from .department import department_bp
# 注意：department_operations 的路由直接注册在 department_bp 上，无需单独导入蓝图
from .department_api import department_api_bp
from .department_import_export import department_import_export_bp

# 低值易耗品进销存管理相关
from .supply import (
    supply_index_bp,
    supplier_bp, supplier_api_bp, supplier_import_export_bp,
    supply_item_bp, supply_item_api_bp, supply_item_import_export_bp,
    storage_location_bp, storage_location_api_bp, storage_location_import_export_bp,
    supply_stock_detail_bp, supply_stock_detail_api_bp,
    stock_in_bp, stock_in_api_bp, stock_in_import_export_bp,
    stock_out_bp, stock_out_api_bp, stock_out_import_export_bp,
    supply_inventory_bp, supply_inventory_api_bp, supply_inventory_import_export_bp,
    supply_stock_record_bp, supply_stock_record_api_bp
)

# 角色管理相关
from .role import role_bp

# 合同管理相关
from .contract import contract_bp, contract_api_bp, contract_import_export_bp

# 后勤维修管理相关
from .maintenance import maintenance_user_bp, maintenance_admin_bp, maintenance_staff_bp, maintenance_api_bp