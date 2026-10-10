# 宿舍管理系统床位管理统一方案

## 任务概述

将分散在5个蓝图端点和4个模型方法中的床位分配逻辑统一收归Bed模型，解决并发安全隐患、代码重复和贫血模型问题，使床位管理逻辑集中化、一致化。

## 背景

宿舍管理系统中床位分配逻辑分散在5个蓝图端点和4个模型方法中，存在以下问题：
1. **并发安全隐患**：蓝图层create_allocation和add端点查Bed无`with_for_update()`锁，模型层change_dorm有锁，不统一
2. **代码重复**：性别验证蓝图层/模型层各一次、房间满员检查重复、床位查找3处重复、补贴禁用3处重复
3. **贫血模型**：Bed模型只有数据字段+2个property，无业务方法

## 设计决策

1. **统一床位管理方法放在Bed模型**（`models/room/room_bed.py`），充实贫血模型为充血模型
2. **bed_id=None即自动分配，bed_id=具体值即手动指定**，不需要额外auto_assign参数
3. **与DormApplication.target_bed_id的"可空则自动分配"设计风格一致**
4. **不在Bed模型中关联user_id**，用Dorm表的bed_id+status='active'查询即可
5. **新增系统设置开关**：ROOM_BED_MANAGEMENT_ENABLED，category='room'，type='bool'，default='true'

## 涉及文件及变更详情

### 1. `models/room/room_bed.py` — Bed模型新增3个方法

当前状态：Bed模型只有数据字段+2个property(full_identifier, status_display)，无业务方法

新增方法：
- `get_available_beds(room_id)` — 类方法，查询指定房间的可用床位列表（带锁）
- `find_and_occupy(room_id, bed_id=None)` — 类方法，bed_id=None自动分配，bed_id=具体值手动指定，返回bed对象并标记occupied
- `release()` — 实例方法，释放床位（标记available）

方法内部逻辑：
- 读取ROOM_BED_MANAGEMENT_ENABLED配置，禁用时跳过床位级操作（直接按房间容量管理）
- find_and_occupy中自动分配时用`with_for_update()`锁防止并发
- release()中标记bed.status='available'

### 2. `models/system_config/system_config.py` — 新增配置项

在`_init_default_configs()`类方法中room配置区域新增：
```python
SystemConfig(
    config_key='ROOM_BED_MANAGEMENT_ENABLED',
    config_value='true',
    config_type='bool',
    category='room',
    description='是否启用床位管理功能',
    sort_order=6
)
```

### 3. `models/dorm/dorm.py` — Dorm模型适配

- `create_allocation()`(行227)：修改签名增加bed_id默认None参数，床位占用逻辑改为调用`Bed.find_and_occupy(room_id, bed_id)`
- `check_out()`(行316)：床位释放改为调用`bed.release()`
- `change_dorm()`(行385)：换宿自动查床位逻辑(行465-468)改为调用`Bed.find_and_occupy(new_room_id)`
- `exchange_dorm()`(行550)：交换宿舍的床位操作也统一调用Bed方法

### 4. `blueprints/dorm/dorm_operations.py` — 蓝图层移除床位查询

- `create_allocation`端点(行34)：移除Bed.query.filter_by(room_id, status='available')无锁查询(行189)，改为传bed_id参数给模型层
- `add`端点(行275)：移除Bed查询(行348)，改为传bed_id参数

### 5. `blueprints/dorm/dorm_service.py` — 适配

- `do_allocation()`(行17)：接收bed_id参数，传递给Dorm.create_allocation()

### 6. `models/dorm/dorm_application.py` — 适配

- `approve()`方法(行219)中Bed查询(行279)改为调用Bed.find_and_occupy()

### 7. `blueprints/dorm/dorm_import_export.py` — 适配

- 导入分配中Bed查询(行498)改为调用Bed方法

### 8. 前端系统设置

- 前端系统设置页面会自动通过API `/system/api/configs/room` 加载和展示新配置项（现有机制，无需额外开发）

## 已发现的Bug

- `models/dorm/dorm.py` change_dorm行518有`db.session.add()`无参数，疑似bug，需修复

## 实施步骤

### TODO: 步骤1 — Bed模型新增3个方法
- [ ] 在`models/room/room_bed.py`中新增`get_available_beds(room_id)`类方法
- [ ] 新增`find_and_occupy(room_id, bed_id=None)`类方法
- [ ] 新增`release()`实例方法
- [ ] 方法内读取ROOM_BED_MANAGEMENT_ENABLED配置，禁用时跳过床位级操作

### TODO: 步骤2 — 新增系统配置项
- [ ] 在`models/system_config/system_config.py`的`_init_default_configs()`中room区域新增ROOM_BED_MANAGEMENT_ENABLED

### TODO: 步骤3 — Dorm模型适配Bed方法
- [ ] `create_allocation()`增加bed_id参数，调用Bed.find_and_occupy()
- [ ] `check_out()`调用bed.release()
- [ ] `change_dorm()`调用Bed.find_and_occupy(new_room_id)
- [ ] `exchange_dorm()`统一调用Bed方法

### TODO: 步骤4 — DormApplication适配
- [ ] `approve()`中Bed查询改为调用Bed.find_and_occupy()

### TODO: 步骤5 — dorm_service适配
- [ ] `do_allocation()`接收bed_id参数并传递

### TODO: 步骤6 — 蓝图层移除床位查询
- [ ] `dorm_operations.py` create_allocation端点移除Bed查询，传bed_id参数
- [ ] `dorm_operations.py` add端点移除Bed查询，传bed_id参数

### TODO: 步骤7 — 导入导出适配
- [ ] `dorm_import_export.py`导入分配中Bed查询改为调用Bed方法

### TODO: 步骤8 — Bug修复
- [ ] 修复`models/dorm/dorm.py` change_dorm行518 `db.session.add()`无参数bug

## 验证要点

- [ ] 并发安全：所有床位查询都通过Bed方法带锁
- [ ] 功能等价：自动分配/手动分配行为与修改前一致
- [ ] 配置开关：禁用床位管理时，床位级操作跳过，按房间容量管理
- [ ] 无循环替换问题
- [ ] 不使用CSRF