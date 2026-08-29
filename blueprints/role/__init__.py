# 角色管理蓝图包
from .role import role_bp
# 注意：role_operations 的路由直接注册在 role_bp 上，无需单独导出蓝图
# 注意：role_api 的路由直接注册在 role_bp 上，无需单独导出蓝图