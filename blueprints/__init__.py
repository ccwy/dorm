# 导出所有蓝图供主程序注册
# 认证相关
from .login import login_bp

# 用户管理相关
from .user import user_bp, user_api_bp, user_operations_bp, user_import_export_bp  # 用户蓝图（含API、操作、导入导出）

# 宿舍与房间管理相关
from .room import room_bp, room_api_bp, room_import_export_bp  # 房间蓝图（含API、导入导出）
from .dorm import dorm_bp, dorm_import_export_bp  # 宿舍蓝图（含导入导出）

# 系统配置与日志相关
from .system_settings import system_config_bp  # 系统配置蓝图
from .log import log_bp    # 操作日志蓝图

# 水电费相关
# 水电费相关
from .utility import (
    utility_index_bp,
    utility_room_meter_bp,
    utility_room_meter_import_export_bp,
    utility_room_bill_records_bp,
    utility_room_bill_occupants_bp,
    utility_room_bill_checkout_bp,
    utility_user_records_detail_bp
)

from .fee_subsidy import fee_subsidy_bp, fee_subsidy_import_export_bp  # 补贴蓝图（含导入导出）


# 文件共享与其他功能
from .other import file_sharing_bp, other_bp

# 留言管理相关
from .ticket import ticket_user_bp, ticket_admin_bp  # 留言蓝图

# 待办事项相关
from .todo import todo_bp


# 聊天功能
from .chat import chat_bp

# 固定资产管理相关
from .fixed_asset import fixed_asset_bp, fixed_asset_api_bp, fixed_asset_import_export_bp

# 部门管理相关
from .department import department_bp, department_api_bp, department_import_export_bp

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