# 部门管理蓝图包
from .department import department_bp
# 注意：department_operations 的路由直接注册在 department_bp 上，无需单独导出蓝图
from .department_api import department_api_bp
from .department_import_export import department_import_export_bp