# 宿舍申请系统设计方案

## 一、任务概述

在现有宿舍管理系统基础上，增加用户申请/审批流程。用户可申请宿舍、换宿、退宿；管理员审核通过后调用现有Dorm模型方法完成实际操作。

---

## 二、数据模型设计 — DormApplication

### 2.1 表名：`dorm_applications`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK | 主键 |
| application_no | String(50) | UNIQUE, NOT NULL | 申请编号，格式：SQ+日期+3位序号（如SQ20260929001） |
| applicant_id | Integer | FK→users.id, NOT NULL | 申请人ID |
| application_type | String(20) | NOT NULL | 申请类型：`allocate`（申请宿舍）/ `change`（申请换宿）/ `checkout`（申请退宿） |
| status | String(20) | NOT NULL, DEFAULT='pending' | 状态：`pending`（待审核）/ `approved`（已通过）/ `rejected`（已拒绝）/ `cancelled`（已取消） |
| reason | Text | NULL | 申请原因（用户填写） |
| **申请宿舍字段** | | | |
| target_room_id | Integer | FK→rooms.id, NULLABLE | 目标房间ID（申请宿舍/换宿时填写） |
| target_bed_id | Integer | FK→room_beds.id, NULLABLE | 目标床位ID（管理员可调整） |
| effective_date | DateTime | NULLABLE | 生效日期（入住日期/换宿日期/退宿日期，必填） |
| **换宿附加字段** | | | |
| current_room_id | Integer | FK→rooms.id, NULLABLE | 当前房间ID（换宿时自动填充） |
| current_bed_id | Integer | FK→room_beds.id, NULLABLE | 当前床位ID（换宿时自动填充） |
| **审核字段** | | |
| reviewer_id | Integer | NULLABLE | 审核人ID（不与User表关联，与Dorm.operator_user_id一致） |
| review_date | DateTime | NULLABLE | 审核时间 |
| review_remark | Text | NULLABLE | 审核备注（管理员填写，如调整原因） |
| **结果关联** | | |
| result_dorm_id | Integer | FK→dorms.id, NULLABLE | 审核通过后生成的住宿记录ID |
| **时间戳** | | |
| created_at | DateTime | DEFAULT=now | 创建时间 |
| updated_at | DateTime | DEFAULT=now, ON UPDATE=now | 更新时间 |

### 2.2 约束与索引

```python
__table_args__ = (
    db.CheckConstraint(
        "application_type IN ('allocate', 'change', 'checkout')",
        name='check_application_type_valid'
    ),
    db.CheckConstraint(
        "status IN ('pending', 'approved', 'rejected', 'cancelled')",
        name='check_application_status_valid'
    ),
    db.Index('idx_app_applicant', 'applicant_id'),
    db.Index('idx_app_status', 'status'),
    db.Index('idx_app_type', 'application_type'),
    db.Index('idx_app_created', 'created_at'),
)
```

### 2.3 关系定义

```python
applicant = db.relationship('User', foreign_keys=[applicant_id])
target_room = db.relationship('Room', foreign_keys=[target_room_id])
target_bed = db.relationship('Bed', foreign_keys=[target_bed_id])
current_room = db.relationship('Room', foreign_keys=[current_room_id])
result_dorm = db.relationship('Dorm', foreign_keys=[result_dorm_id])
```

### 2.4 状态流转

```
pending ──→ approved   （管理员审核通过）
pending ──→ rejected   （管理员审核拒绝）
pending ──→ cancelled  （用户自行取消）
```

- 只有 `pending` 状态可转换到其他状态
- `approved`/`rejected`/`cancelled` 为终态，不可再变更

---

## 三、权限码设计

在 `utils/auth.py` 的 `PERMISSIONS` 字典中新增：

```python
'dorm_application': {
    'name': '宿舍申请',
    'actions': {
        'view': '查看',        # 用户查看自己的申请
        'create': '新增',      # 用户提交申请
        'cancel': '取消',      # 用户取消待审核的申请
        'manage': '管理',      # 管理员查看所有申请
        'approve': '审核',     # 管理员审核（通过/拒绝）
    }
}
```

权限码格式：
- `dorm_application.view` — 用户查看自己的申请列表
- `dorm_application.create` — 用户提交申请
- `dorm_application.cancel` — 用户取消待审核申请
- `dorm_application.manage` — 管理员查看所有申请列表
- `dorm_application.approve` — 管理员审核操作

---

## 四、路由设计

### 4.1 用户端蓝图 — `dorm_application_user_bp`

URL前缀：`/user/dorm_application`

| 路由 | 方法 | 权限码 | 说明 |
|------|------|--------|------|
| `/list` | GET | `dorm_application.view` | 我的申请列表 |
| `/create_allocate` | GET,POST | `dorm_application.create` | 申请宿舍（GET:表单页, POST:提交） |
| `/create_change` | GET,POST | `dorm_application.create` | 申请换宿 |
| `/create_checkout` | GET,POST | `dorm_application.create` | 申请退宿 |
| `/detail/<id>` | GET | `dorm_application.view` | 申请详情 |
| `/cancel/<id>` | POST | `dorm_application.cancel` | 取消申请 |
| `/api/available_rooms` | GET | `dorm_application.create` | 获取可用房间列表（页面加载时过滤用） |

### 4.2 管理端蓝图 — `dorm_application_admin_bp`

URL前缀：`/admin/dorm_application`

| 路由 | 方法 | 权限码 | 说明 |
|------|------|--------|------|
| `/list` | GET | `dorm_application.manage` | 所有申请列表（支持筛选） |
| `/detail/<id>` | GET | `dorm_application.manage` | 审核详情页 |
| `/approve/<id>` | POST | `dorm_application.approve` | 审核通过（可调整房间/床位） |
| `/reject/<id>` | POST | `dorm_application.approve` | 审核拒绝 |
| `/api/available_rooms` | GET | `dorm_application.approve` | 获取可用房间（审核调整用） |

---

## 五、验证逻辑设计

### 5.1 页面加载时过滤（前端+后端API `/api/available_rooms`）

**申请宿舍（allocate）：**
1. 获取当前用户性别
2. 查询房间：`status='available'` 且 `current_occupancy < capacity`
3. 性别过滤：若用户性别为"男"，排除 `gender_restriction='女'`；若为"女"，排除 `gender_restriction='男'`
4. 排除 `gender_restriction` 不匹配的房间
5. 每个可用房间附带可用床位列表（`status='available'`）

**申请换宿（change）：**
1. 验证用户当前有活跃住宿记录
2. 获取当前房间信息
3. 可用房间过滤逻辑同上，但排除当前所在房间
4. 返回当前房间信息 + 可用目标房间列表

**申请退宿（checkout）：**
1. 验证用户当前有活跃住宿记录
2. 返回当前住宿信息（房间、床位、入住日期）

### 5.2 提交时后端验证

**申请宿舍（allocate）：**
1. 用户状态必须为"在职"
2. 用户不能已有活跃住宿记录（`Dorm.status='active'`）
3. 用户不能有待审核的申请宿舍申请（`DormApplication.status='pending' AND type='allocate'`）
4. 目标房间必须存在且 `status='available'`
5. 性别匹配验证（调用 `Dorm._validate_gender_match()`）
6. 目标房间必须有可用床位
7. `effective_date` 必填且不能早于当天

**申请换宿（change）：**
1. 用户必须有活跃住宿记录
2. 用户不能有待审核的换宿申请
3. 目标房间验证同上
4. 目标房间不能是当前房间
5. `effective_date` 必填且不早于当前入住日期

**申请退宿（checkout）：**
1. 用户必须有活跃住宿记录
2. 用户不能有待审核的退宿申请
3. `effective_date` 必填且不早于当前入住日期

### 5.3 审核时后端验证

**审核通过（approve）：**
1. 申请状态必须为 `pending`
2. 管理员可调整 `target_room_id` 和 `target_bed_id`
3. 对调整后的房间/床位重新执行上述验证
4. 使用 `with_for_update()` 行级锁防止并发

**审核拒绝（reject）：**
1. 申请状态必须为 `pending`
2. 必须填写 `review_remark`

---

## 六、审核通过后业务逻辑

### 6.1 申请宿舍 → 调用 `Dorm.create_allocation()`

```python
# 审核通过 - 申请宿舍
new_dorm = Dorm.create_allocation(
    user_id=application.applicant_id,
    room_id=application.target_room_id,
    bed_id=application.target_bed_id,
    check_in_date=application.effective_date,
    remarks=f"通过申请{application.application_no}分配"
)
application.result_dorm_id = new_dorm.id
```

### 6.2 申请换宿 → 调用 `Dorm.change_dorm()`

```python
# 审核通过 - 申请换宿
new_dorm = Dorm.change_dorm(
    user_id=application.applicant_id,
    target_room_id=application.target_room_id,
    reason=f"通过申请{application.application_no}换宿",
    change_date=application.effective_date
)
application.result_dorm_id = new_dorm.id
```

### 6.3 申请退宿 → 调用 `Dorm.check_out()`

```python
# 审核通过 - 申请退宿
current_dorm = Dorm.query.filter_by(
    user_id=application.applicant_id,
    status='active'
).first()
current_dorm.check_out(
    check_out_date=application.effective_date,
    remarks=f"通过申请{application.application_no}退宿"
)
application.result_dorm_id = current_dorm.id
```

---

## 七、并发安全设计

1. **申请提交时**：检查是否有重复待审核申请时使用 `with_for_update()` 锁定申请记录
2. **审核通过时**：
   - 锁定申请记录：`DormApplication.query.filter_by(id=id).with_for_update().first()`
   - 锁定目标房间：`Room.query.filter_by(id=room_id).with_for_update().first()`
   - 锁定目标床位：`Bed.query.filter_by(id=bed_id).with_for_update().first()`
   - 整个审核操作包裹在 `db.session.begin()` 事务中
3. **Dorm模型方法**：`create_allocation()`/`check_out()`/`change_dorm()` 已内置行级锁，无需额外处理

---

## 八、文件结构设计

### 8.1 新增文件列表

```
models/dorm/
  └── dorm_application.py          # DormApplication数据模型

blueprints/dorm/
  ├── dorm_application_user.py     # 用户端蓝图（申请/查看/取消）
  └── dorm_application_admin.py   # 管理端蓝图（审核/管理）

templates/dorm_manage/
  ├── user_application_list.html      # 用户-我的申请列表
  ├── user_application_create.html   # 用户-申请表单（宿舍/换宿/退宿共用，按type切换）
  ├── user_application_detail.html   # 用户-申请详情
  ├── admin_application_list.html    # 管理-申请列表
  └── admin_application_detail.html  # 管理-审核详情（含审核操作）
```

### 8.2 修改文件列表

| 文件 | 修改内容 |
|------|----------|
| `models/dorm/__init__.py` | 导出 `DormApplication` |
| `models/__init__.py` | 导入 `DormApplication` |
| `blueprints/dorm/__init__.py` | 导出 `dorm_application_user_bp`, `dorm_application_admin_bp` |
| `main.py` | 注册两个新蓝图 |
| `utils/auth.py` | PERMISSIONS新增 `dorm_application` 模块 |
| `templates/header.html` | 导航栏新增"宿舍申请"入口 |

---

## 九、与现有系统集成点

### 9.1 模型层集成
- `DormApplication` 通过 `applicant_id` 关联 `User`
- 通过 `target_room_id`/`target_bed_id` 关联 `Room`/`Bed`
- 通过 `result_dorm_id` 关联 `Dorm`（审核通过后回写）
- 复用 `Dorm._validate_gender_match()` 性别验证
- 复用 `Dorm.create_allocation()`/`check_out()`/`change_dorm()` 核心业务

### 9.2 蓝图层集成
- 遵循 `ticket`/`maintenance` 模块的用户端/管理端分离模式
- 用户端蓝图 `url_prefix='/user/dorm_application'`
- 管理端蓝图 `url_prefix='/admin/dorm_application'`

### 9.3 权限层集成
- 在 `PERMISSIONS` 字典新增 `dorm_application` 模块
- 遵循 `module.action` 权限码格式
- 模板中使用 `{% if current_user.has_permission('dorm_application.xxx') %}`

### 9.4 模板层集成
- 使用 Tailwind CSS + Font Awesome 风格
- 使用 `{% include 'static.html' %}` + `{% include 'header.html' %}`
- 导航栏入口：有 `dorm_application.manage` 权限跳转管理端，否则跳转用户端

### 9.5 日志集成
- 使用 `utils.log.log_operation()` 记录操作日志
- module='dorm_application'

---

## 十、DormApplication 模型核心方法设计

```python
class DormApplication(db.Model):
    # ... 字段定义见第二节 ...

    @classmethod
    def generate_application_no(cls):
        """生成申请编号：SQ+日期+3位序号"""
        today = datetime.now().strftime('%Y%m%d')
        prefix = f'SQ{today}'
        last = cls.query.filter(
            cls.application_no.like(f'{prefix}%')
        ).order_by(cls.application_no.desc()).first()
        new_seq = (int(last.application_no[-3:]) + 1) if last else 1
        return f'{prefix}{new_seq:03d}'

    @classmethod
    def create_allocate_application(cls, applicant_id, target_room_id,
                                    target_bed_id, effective_date, reason):
        """创建申请宿舍申请（含验证）"""
        # 1. 验证用户状态
        # 2. 验证无活跃住宿
        # 3. 验证无重复待审核申请
        # 4. 性别验证
        # 5. 房间/床位可用性验证
        # 6. 创建申请记录

    @classmethod
    def create_change_application(cls, applicant_id, target_room_id,
                                  target_bed_id, effective_date, reason):
        """创建换宿申请（含验证）"""

    @classmethod
    def create_checkout_application(cls, applicant_id, effective_date, reason):
        """创建退宿申请（含验证）"""

    def approve(self, reviewer_id, review_remark=None,
                adjusted_room_id=None, adjusted_bed_id=None):
        """审核通过（可调整房间/床位，调用Dorm核心方法）"""
        # 1. 状态验证
        # 2. 行级锁
        # 3. 如有调整，重新验证
        # 4. 根据application_type调用对应Dorm方法
        # 5. 回写result_dorm_id
        # 6. 更新申请状态

    def reject(self, reviewer_id, review_remark):
        """审核拒绝"""

    def cancel(self):
        """用户取消申请"""
```

---

## 十一、导航栏入口设计

在 `templates/header.html` 中，宿舍导航项旁新增：

```html
{% if current_user.has_permission('dorm_application.view') %}
<a href="{{ url_for('dorm_application_admin.admin_application_list' if current_user.has_permission('dorm_application.manage') else 'dorm_application_user.user_application_list') }}"
   class="nav-item ...">
   <i class="fa fa-file-text-o mr-2"></i>宿舍申请
</a>
{% endif %}
```

---

## 十二、实现步骤（TODO）

- [ ] 1. 创建 `models/dorm/dorm_application.py` 数据模型
- [ ] 2. 修改 `models/dorm/__init__.py` 和 `models/__init__.py` 导出模型
- [ ] 3. 在 `utils/auth.py` 新增 `dorm_application` 权限模块
- [ ] 4. 创建 `blueprints/dorm/dorm_application_user.py` 用户端蓝图
- [ ] 5. 创建 `blueprints/dorm/dorm_application_admin.py` 管理端蓝图
- [ ] 6. 修改 `blueprints/dorm/__init__.py` 导出新蓝图
- [ ] 7. 修改 `main.py` 注册新蓝图
- [ ] 8. 创建用户端模板（列表/表单/详情）
- [ ] 9. 创建管理端模板（列表/审核详情）
- [ ] 10. 修改 `templates/header.html` 添加导航入口
- [ ] 11. 数据库迁移（创建 dorm_applications 表）
- [ ] 12. 测试验证（申请流程、审核流程、并发场景）