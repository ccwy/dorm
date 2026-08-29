# 低值易耗品管理总入口
from .supply_index import supply_index_bp

# 供应商管理相关
from .supplier import supplier_bp
from .supplier_api import supplier_api_bp
from .supplier_import_export import supplier_import_export_bp
# 注意：supplier_operations 的路由直接注册在 supplier_bp 上，无需单独导出蓝图

# 基础物料资料相关
from .supply_item import supply_item_bp
from .supply_item_api import supply_item_api_bp
from .supply_item_import_export import supply_item_import_export_bp
# 注意：supply_item_operations 的路由直接注册在 supply_item_bp 上，无需单独导出蓝图

# 存放位置管理相关
from .storage_location import storage_location_bp
from .storage_location_api import storage_location_api_bp
from .storage_location_import_export import storage_location_import_export_bp
# 注意：storage_location_operations 的路由直接注册在 storage_location_bp 上，无需单独导出蓝图

# 库存明细管理相关
from .supply_stock_detail import supply_stock_detail_bp
from .supply_stock_detail_api import supply_stock_detail_api_bp
# 注意：库存明细由系统自动维护，不支持手动新增/编辑/删除，无操作蓝图和导入导出蓝图

# 入库管理相关
from .stock_in import stock_in_bp
from .stock_in_api import stock_in_api_bp
from .stock_in_import_export import stock_in_import_export_bp
# 注意：stock_in_operations 的路由直接注册在 stock_in_bp 上，无需单独导出蓝图

# 出库管理相关
from .stock_out import stock_out_bp
from .stock_out_api import stock_out_api_bp
from .stock_out_import_export import stock_out_import_export_bp
# 注意：stock_out_operations 的路由直接注册在 stock_out_bp 上，无需单独导出蓝图

# 盘点管理相关
from .supply_inventory import supply_inventory_bp
from .supply_inventory_api import supply_inventory_api_bp
from .supply_inventory_import_export import supply_inventory_import_export_bp
# 注意：supply_inventory_operations 的路由直接注册在 supply_inventory_bp 上，无需单独导出蓝图

# 进出库记录相关
from .supply_stock_record import supply_stock_record_bp
from .supply_stock_record_api import supply_stock_record_api_bp
# 注意：进出库记录由系统自动生成，不支持手动CRUD，无操作蓝图和导入导出蓝图