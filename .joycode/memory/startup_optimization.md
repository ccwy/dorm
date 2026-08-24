---
name: startup-optimization
description: 启动性能优化记录：延迟导入策略和打包环境优化
type: project
---

## 启动性能优化总结

### 核心策略：延迟导入（Lazy Import）
- 使用 `utils/lazy_imports.py` 中的 `_LazyModule` 和 `_LazyAttr` 代理模式
- pandas、openpyxl 等重型库仅在首次使用时才加载
- **关键规则**：任何模块不得在顶层 `import pandas` 或 `import pymysql`，否则会绕过延迟机制

### 已修复的延迟导入绕过点
1. `utils/excel_date_utils.py` - `import pandas` → `from utils.lazy_imports import pd`
2. `utils/user_utils.py` - 删除未使用的 `import pandas`
3. `utils/db.py` - `import pymysql` 移至 `_force_create_mysql_database()` 内部
4. `models/system_config.py` - 删除未使用的 `import pymysql`
5. `blueprints/system_settings_initialize.py` - `import pymysql` 移至 MySQL 操作代码块内部
6. `utils/backup.py` - `import pymysql` 移至 `create_database_backup()` 和 `restore_database_backup()` 内部

### 打包环境优化
- MySQL连接URI添加 `connect_timeout=3`（默认30s会阻塞启动）
- 两个spec文件禁用UPX压缩（`upx=False`，解压开销拖慢启动）
- excludes列表扩展到24项（排除tkinter/unittest/setuptools/asyncio等）

### 验证结果（开发环境）
- 所有核心导入：~1.2s（Flask 0.3s + config 0.4s + db 0.2s + User 0.1s + blueprints 0.2s）
- pymysql/pandas/openpyxl 在蓝图导入后均未加载 ✓