# 固定资产管理蓝图包
from .fixed_asset import fixed_asset_bp
# 注意：fixed_asset_operations 的路由直接注册在 fixed_asset_bp 上，无需单独导出蓝图
from .fixed_asset_api import fixed_asset_api_bp
from .fixed_asset_import_export import fixed_asset_import_export_bp