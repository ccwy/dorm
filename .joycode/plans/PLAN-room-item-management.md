# 房间物品管理模块开发方案

## 一、概述

在宿舍管理系统(Flask + SQLAlchemy + Jinja2)中新增"房间物品管理"模块，实现对房间内物品的增删改查、分配/归还、状态变更(损坏/丢失/报废)、房间间转移、以及宿舍操作(换宿/互换/退宿)后的物品确认处理。

## 二、项目规则

- 前端尽量使用HTML，少用JS
- 使用flash消息与后端通信
- 使用logging模块记录日志(log_operation只记录操作类日志)
- 代码简单化，不复杂化
- 不使用CSRF
- 开发环境，不考虑数据迁移

---

## 三、数据模型设计

### 3.1 RoomItem模型

**文件**: `models/room/room_item.py`

```python
from datetime import datetime
from utils.db import db
import logging

class RoomItem(db.Model):
    """房间物品模型"""
    __tablename__ = 'room_items'

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='CASCADE'), nullable=False, comment='关联的房间ID')
    name = db.Column(db.String(100), nullable=False, comment='物品名称')
    item_type = db.Column(db.String(20), nullable=False, comment='物品类型：room_bound(房间绑定)/transferable(可转移)')
    total_quantity = db.Column(db.Integer, default=1, nullable=False, comment='总数量')
    available_quantity = db.Column(db.Integer, default=1, nullable=False, comment='可用数量')
    status = db.Column(db.String(20), default='正常', nullable=False, comment='物品状态：正常/损坏/丢失/报废')
    remark = db.Column(db.String(500), nullable=True, comment='备注')
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')

    # 关系
    room = db.relationship('Room', backref=db.backref('room_items', lazy='dynamic'))
    records = db.relationship('RoomItemRecord', backref='item', lazy='dynamic', cascade='all, delete-orphan')
    assignments = db.relationship('RoomItemAssignment', backref='item', lazy='dynamic', cascade='all, delete-orphan')

    # 索引
    __table_args__ = (
        db.Index('idx_room_item_room_id', 'room_id'),
        db.Index('idx_room_item_status', 'status'),
    )

    ITEM_TYPE_MAP = {'room_bound': '房间绑定', 'transferable': '可转移'}
    STATUS_MAP = {'正常': '正常', '损坏': '损坏', '丢失': '丢失', '报废': '报废'}

    @classmethod
    def create_item(cls, room_id, name, item_type, total_quantity=1, remark=None):
        """创建物品"""
        item = cls(
            room_id=room_id,
            name=name,
            item_type=item_type,
            total_quantity=total_quantity,
            available_quantity=total_quantity,
            remark=remark
        )
        db.session.add(item)
        logging.info(f"创建房间物品: 房间ID={room_id}, 名称={name}, 类型={item_type}, 数量={total_quantity}")
        return item

    def __repr__(self):
        return f"<RoomItem {self.name} 房间{self.room_id}>"
```

**数量逻辑说明**:
- `total_quantity`: 物品总数(包括已分配的)
- `available_quantity`: 当前可分配的数量
- 分配给用户时: `available_quantity`减少
- 用户归还时: `available_quantity`增加
- 始终保持 `0 <= available_quantity <= total_quantity`

### 3.2 RoomItemRecord模型

**文件**: `models/room/room_item_record.py`

```python
from datetime import datetime
from utils.db import db
import logging

class RoomItemRecord(db.Model):
    """物品操作记录模型"""
    __tablename__ = 'room_item_records'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('room_items.id', ondelete='CASCADE'), nullable=False, comment='关联的物品ID')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, comment='操作涉及的用户ID')
    from_room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='SET NULL'), nullable=True, comment='来源房间ID')
    to_room_id = db.Column(db.Integer, db.ForeignKey('rooms.id', ondelete='SET NULL'), nullable=True, comment='目标房间ID')
    operation_type = db.Column(db.String(20), nullable=False, comment='操作类型：allocate/return/transfer/damage/loss/scrap/dorm_transfer/dorm_exchange/dorm_checkout')
    quantity = db.Column(db.Integer, nullable=False, comment='操作数量')
    before_quantity = db.Column(db.Integer, nullable=True, comment='操作前可用数量')
    after_quantity = db.Column(db.Integer, nullable=True, comment='操作后可用数量')
    operator_id = db.Column(db.Integer, nullable=True, comment='操作人ID')
    remarks = db.Column(db.String(500), nullable=True, comment='备注')
    operated_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='操作时间')

    # 关系
    user = db.relationship('User', foreign_keys=[user_id])
    from_room = db.relationship('Room', foreign_keys=[from_room_id])
    to_room = db.relationship('Room', foreign_keys=[to_room_id])

    # 索引
    __table_args__ = (
        db.Index('idx_item_record_item_id', 'item_id'),
        db.Index('idx_item_record_user_id', 'user_id'),
        db.Index('idx_item_record_type', 'operation_type'),
        db.Index('idx_item_record_time', 'operated_at'),
    )

    OPERATION_TYPE_MAP = {
        'allocate': '分配', 'return': '归还', 'transfer': '转移',
        'damage': '损坏', 'loss': '丢失', 'scrap': '报废',
        'dorm_transfer': '换宿触发', 'dorm_exchange': '互换触发', 'dorm_checkout': '退宿触发'
    }

    @classmethod
    def add_record(cls, item_id, operation_type, quantity, before_quantity=None, after_quantity=None,
                   user_id=None, from_room_id=None, to_room_id=None, operator_id=None, remarks=None):
        """添加操作记录"""
        record = cls(
            item_id=item_id, operation_type=operation_type, quantity=quantity,
            before_quantity=before_quantity, after_quantity=after_quantity,
            user_id=user_id, from_room_id=from_room_id, to_room_id=to_room_id,
            operator_id=operator_id, remarks=remarks
        )
        db.session.add(record)
        logging.info(f"物品操作记录: 物品ID={item_id}, 类型={operation_type}, 数量={quantity}")
        return record
```

### 3.3 RoomItemAssignment模型

**文件**: `models/room/room_item_assignment.py`

```python
from datetime import datetime
from utils.db import db
import logging

class RoomItemAssignment(db.Model):
    """物品分配记录模型"""
    __tablename__ = 'room_item_assignments'

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('room_items.id', ondelete='CASCADE'), nullable=False, comment='关联的物品ID')
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='RESTRICT'), nullable=False, comment='分配给的用户ID')
    quantity = db.Column(db.Integer, default=1, nullable=False, comment='分配数量')
    status = db.Column(db.String(20), default='active', nullable=False, comment='状态：active/returned/damaged/lost')
    dorm_id = db.Column(db.Integer, db.ForeignKey('dorms.id', ondelete='SET NULL'), nullable=True, comment='关联的住宿记录ID')
    assigned_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='分配时间')
    returned_at = db.Column(db.DateTime, nullable=True, comment='归还时间')
    remarks = db.Column(db.String(500), nullable=True, comment='备注')

    # 关系
    user = db.relationship('User', foreign_keys=[user_id])
    dorm = db.relationship('Dorm', foreign_keys=[dorm_id])

    # 索引
    __table_args__ = (
        db.Index('idx_item_assignment_item_id', 'item_id'),
        db.Index('idx_item_assignment_user_id', 'user_id'),
        db.Index('idx_item_assignment_status', 'status'),
    )

    STATUS_MAP = {'active': '持有中', 'returned': '已归还', 'damaged': '已损坏', 'lost': '已丢失'}

    @classmethod
    def create_assignment(cls, item_id, user_id, quantity=1, dorm_id=None, remarks=None):
        """创建分配记录"""
        assignment = cls(
            item_id=item_id, user_id=user_id, quantity=quantity,
            dorm_id=dorm_id, remarks=remarks
        )
        db.session.add(assignment)
        logging.info(f"分配物品: 物品ID={item_id}, 用户ID={user_id}, 数量={quantity}")
        return assignment
```

### 3.4 Dorm模型修改

**文件**: `models/dorm/dorm.py`

在Dorm模型中添加字段:

```python
# 在Dorm类中添加
pending_item_action = db.Column(db.Boolean, default=False, nullable=False, comment='是否有待处理的物品确认')
```

---

## 四、模型注册

### 4.1 修改 `models/room/__init__.py`

```python
from .room import Room, RoomStatus
from .room_bed import Bed, BedStatus
from .room_facility import RoomFacility
from .room_item import RoomItem
from .room_item_record import RoomItemRecord
from .room_item_assignment import RoomItemAssignment
```

### 4.2 修改 `models/__init__.py`

在现有Room导入行中添加新模型:

```python
from .room import Room, RoomStatus, Bed, BedStatus, RoomFacility, RoomItem, RoomItemRecord, RoomItemAssignment
```

---

## 五、蓝图设计

### 5.1 物品管理主蓝图

**文件**: `blueprints/room/room_item.py`

- `url_prefix='/room/item'`
- `template_folder='../../templates'`
- `static_folder='../../static'`

| 方法 | 路由 | 功能 | 权限 |
|------|------|------|------|
| GET | `/list/<room_id>` | 房间物品列表(嵌入房间详情页) | room_item.view |
| GET | `/manage` | 物品管理主页(所有房间物品汇总) | room_item.view |
| GET | `/add/<room_id>` | 添加物品页面 | room_item.create |
| POST | `/add/<room_id>` | 添加物品 | room_item.create |
| GET | `/edit/<item_id>` | 编辑物品页面 | room_item.edit |
| POST | `/edit/<item_id>` | 编辑物品 | room_item.edit |
| POST | `/delete/<item_id>` | 删除物品 | room_item.delete |
| GET | `/allocate/<item_id>` | 分配物品给用户页面 | room_item.allocate |
| POST | `/allocate/<item_id>` | 分配物品给用户 | room_item.allocate |
| POST | `/return/<assignment_id>` | 归还物品 | room_item.return |
| POST | `/damage/<item_id>` | 标记损坏 | room_item.operate |
| POST | `/loss/<item_id>` | 标记丢失 | room_item.operate |
| POST | `/scrap/<item_id>` | 标记报废 | room_item.operate |
| GET | `/transfer/<item_id>` | 转移物品页面 | room_item.operate |
| POST | `/transfer/<item_id>` | 转移物品 | room_item.operate |
| GET | `/records/<item_id>` | 物品流转记录 | room_item.view |
| GET | `/confirm_dorm_operation/<dorm_id>/<operation_type>` | 宿舍操作物品确认页面 | room_item.operate |
| POST | `/confirm_dorm_operation` | 确认宿舍操作物品处理 | room_item.operate |

### 5.2 API蓝图

**文件**: `blueprints/room/room_item_api.py`

- `url_prefix='/api/room/items'`

| 方法 | 路由 | 功能 |
|------|------|------|
| GET | `/<room_id>` | 获取房间物品列表(JSON) |
| GET | `/assignments/<user_id>` | 获取用户持有物品列表(JSON) |

---

## 六、蓝图注册

### 6.1 修改 `blueprints/room/__init__.py`

```python
from .room import room_bp, generate_page_range
from .room_api import room_api_bp
from .room_import_export import room_import_export_bp
from .room_item import room_item_bp
from .room_item_api import room_item_api_bp
```

### 6.2 修改 `blueprints/__init__.py`

在room相关导入行添加:

```python
from .room import room_bp, room_api_bp, room_import_export_bp, room_item_bp, room_item_api_bp
```

### 6.3 修改 `main.py`

在蓝图导入部分添加 `room_item_bp, room_item_api_bp`，并在注册部分添加:

```python
app.register_blueprint(room_item_bp)
app.register_blueprint(room_item_api_bp)
```

---

## 七、宿舍操作物品确认机制

### 7.1 核心逻辑

1. 换宿/互换/退宿操作完成后，检查旧房间是否有物品分配给用户
2. 如果有，设置 `Dorm.pending_item_action = True`
3. 在宿舍操作完成后的flash消息中提示"该用户有待处理的房间物品，请前往确认"
4. 管理员点击提示链接进入确认页面

### 7.2 触发时机

在以下宿舍操作完成后触发检查:
- **换宿** (`blueprints/dorm/dorm_operations.py` 的换宿路由)
- **互换** (`blueprints/dorm/dorm_operations.py` 的互换路由)
- **退宿** (`blueprints/dorm/dorm_operations.py` 的退宿路由)

### 7.3 检查逻辑伪代码

```python
def check_pending_items_after_dorm_operation(user_id, old_room_id, dorm_id):
    """宿舍操作后检查是否有待处理物品"""
    assignments = RoomItemAssignment.query.filter_by(
        user_id=user_id, status='active'
    ).join(RoomItem).filter(RoomItem.room_id == old_room_id).all()

    if assignments:
        dorm = Dorm.query.get(dorm_id)
        if dorm:
            dorm.pending_item_action = True
            db.session.commit()
        return True
    return False
```

### 7.4 确认页面流程

1. 展示用户在旧房间持有的所有物品(RoomItemAssignment, status='active')
2. 每个物品旁边有操作选择: 归还/损坏/丢失/转移到新房间
3. 管理员选择后提交
4. 批量处理物品变更并记录

---

## 八、导入导出合并

### 8.1 房间导出修改

**文件**: `blueprints/room/room_import_export.py`

在导出数据中增加"房间物品"列，格式: `物品名:类型:总数:可用数,物品名:类型:总数:可用数`

```python
# 在export函数的data.append中添加
items = RoomItem.query.filter_by(room_id=room.id).all()
items_str = ','.join([f'{i.name}:{i.item_type}:{i.total_quantity}:{i.available_quantity}' for i in items])
# 添加到data字典
'房间物品': items_str,
```

### 8.2 房间导入修改

在导入的 `optional_columns` 中添加 `'房间物品'`，解析并创建RoomItem:

```python
optional_columns['房间物品'] = lambda room, val: parse_and_create_room_items(room.id, val)

def parse_and_create_room_items(room_id, val):
    if not val:
        return
    for item_str in val.split(','):
        parts = item_str.split(':')
        if len(parts) == 4:
            name, item_type, total, avail = parts
            RoomItem.create_item(room_id, name.strip(), item_type.strip(),
                               int(total.strip()), remark=None)
            # 可用数量单独设置
            item = RoomItem.query.filter_by(room_id=room_id).order_by(RoomItem.id.desc()).first()
            if item:
                item.available_quantity = int(avail.strip())
```

### 8.3 用户导出修改

**文件**: `blueprints/user/user_import_export.py`

在导出数据中增加"持有物品"列，格式: `物品名:数量,物品名:数量`

```python
# 获取用户持有的物品
assignments = RoomItemAssignment.query.filter_by(user_id=user.id, status='active').all()
items_str = ','.join([f'{a.item.name}:{a.quantity}' for a in assignments if a.item])
# 添加到data字典
'持有物品': items_str,
```

---

## 九、房间详情页集成

### 9.1 修改 `templates/room_manage/room_view.html`

在"房间设施"区块下方、"居住用户"区块上方，添加"房间物品"区块:

```html
<!-- 房间物品部分 -->
<div class="mb-8">
    <div class="flex items-center justify-between mb-4 pb-2 border-b border-gray-200">
        <h3 class="text-lg font-medium">房间物品</h3>
        {% if current_user.has_permission('room_item.create') %}
        <a href="{{ url_for('room_item.add', room_id=room.id) }}" class="px-3 py-1 bg-primary text-white text-sm rounded-md hover:bg-primary/90">
            <i class="fa fa-plus mr-1"></i>添加物品
        </a>
        {% endif %}
    </div>

    <div class="overflow-x-auto">
        <table class="min-w-full divide-y divide-gray-200">
            <thead class="bg-gray-50">
                <tr>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500">物品名称</th>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500">类型</th>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500">总数/可用</th>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500">状态</th>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500">备注</th>
                    <th class="px-4 py-3 text-left text-xs font-medium text-gray-500">操作</th>
                </tr>
            </thead>
            <tbody class="bg-white divide-y divide-gray-200">
                {% if room_items and room_items|length > 0 %}
                    {% for item in room_items %}
                    <tr>
                        <td class="px-4 py-3">{{ item.name }}</td>
                        <td class="px-4 py-3">
                            {% if item.item_type == 'room_bound' %}房间绑定
                            {% elif item.item_type == 'transferable' %}可转移
                            {% else %}{{ item.item_type }}{% endif %}
                        </td>
                        <td class="px-4 py-3">{{ item.total_quantity }} / {{ item.available_quantity }}</td>
                        <td class="px-4 py-3">
                            {% if item.status == '正常' %}
                                <span class="px-2 py-1 bg-green-100 text-green-800 rounded-full text-xs">{{ item.status }}</span>
                            {% elif item.status == '损坏' %}
                                <span class="px-2 py-1 bg-yellow-100 text-yellow-800 rounded-full text-xs">{{ item.status }}</span>
                            {% elif item.status == '丢失' %}
                                <span class="px-2 py-1 bg-red-100 text-red-800 rounded-full text-xs">{{ item.status }}</span>
                            {% elif item.status == '报废' %}
                                <span class="px-2 py-1 bg-gray-100 text-gray-800 rounded-full text-xs">{{ item.status }}</span>
                            {% else %}{{ item.status }}{% endif %}
                        </td>
                        <td class="px-4 py-3">{{ item.remark or '-' }}</td>
                        <td class="px-4 py-3">
                            {% if current_user.has_permission('room_item.allocate') and item.available_quantity > 0 and item.status == '正常' %}
                            <a href="{{ url_for('room_item.allocate', item_id=item.id) }}" class="text-primary hover:underline text-sm mr-2">分配</a>
                            {% endif %}
                            {% if current_user.has_permission('room_item.edit') %}
                            <a href="{{ url_for('room_item.edit', item_id=item.id) }}" class="text-primary hover:underline text-sm mr-2">编辑</a>
                            {% endif %}
                            {% if current_user.has_permission('room_item.view') %}
                            <a href="{{ url_for('room_item.records', item_id=item.id) }}" class="text-primary hover:underline text-sm">流转记录</a>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                {% else %}
                    <tr>
                        <td colspan="6" class="px-4 py-8 text-center text-gray-500">
                            <i class="fa fa-info-circle mr-2"></i>暂无物品信息
                        </td>
                    </tr>
                {% endif %}
            </tbody>
        </table>
    </div>
</div>
```

### 9.2 修改房间详情路由

在 `blueprints/room/room.py` 的 `view` 路由中，添加查询房间物品的逻辑:

```python
from models.room.room_item import RoomItem

# 在view函数中添加
room_items = RoomItem.query.filter_by(room_id=room.id).all()
# 传递给模板
```

---

## 十、权限设置

### 10.1 需要的权限码

| 权限码 | 说明 |
|--------|------|
| `room_item.view` | 查看物品 |
| `room_item.create` | 创建物品 |
| `room_item.edit` | 编辑物品 |
| `room_item.delete` | 删除物品 |
| `room_item.allocate` | 分配物品 |
| `room_item.return` | 归还物品 |
| `room_item.operate` | 物品操作(损坏/丢失/报废/转移) |

### 10.2 权限注册方式

通过系统设置的角色权限管理界面手动添加，或在数据库初始化脚本中添加。

---

## 十一、模板文件

### 11.1 需要创建的模板

| 文件路径 | 功能 |
|----------|------|
| `templates/room_manage/room_item_list.html` | 物品管理主页(所有房间物品汇总) |
| `templates/room_manage/room_item_add.html` | 添加物品 |
| `templates/room_manage/room_item_edit.html` | 编辑物品 |
| `templates/room_manage/room_item_allocate.html` | 分配物品给用户 |
| `templates/room_manage/room_item_transfer.html` | 转移物品 |
| `templates/room_manage/room_item_records.html` | 物品流转记录 |
| `templates/room_manage/room_item_confirm_dorm.html` | 宿舍操作物品确认页面 |

### 11.2 模板设计规范

- 使用 `{% include 'static.html' %}` 引入CDN
- 使用 `{% include 'header.html' %}` 引入导航
- 使用 `{% include 'footer.html' %}` 引入页脚
- 使用 Tailwind CSS 样式
- 使用 Font Awesome 图标
- 表单提交使用标准HTML form + POST，不使用JS/AJAX
- 操作反馈使用flash消息
- 权限控制使用 `current_user.has_permission('room_item.xxx')`

---

## 十二、导航菜单

### 12.1 首页导航

在 `templates/index.html` 的房间管理卡片区域附近，添加"物品管理"入口:

```html
<!-- 物品管理 -->
{% if current_user.has_permission('room_item.view') %}
<div class="bg-white rounded-xl p-6 card-shadow btn-hover nav-card">
    <a href="{{ url_for('room_item.manage') }}" class="flex flex-col items-center text-center">
        <div class="w-16 h-16 bg-teal-500/10 rounded-full flex items-center justify-center mb-4">
            <i class="fa fa-cube text-xl md:text-2xl text-teal-500"></i>
        </div>
        <h3 class="text-base md:text-lg font-medium text-dark mb-2">物品管理</h3>
        <p class="text-gray-500 text-sm">管理房间物品分配与流转</p>
    </a>
</div>
{% endif %}
```

### 12.2 侧边栏导航

在 `templates/header.html` 中添加物品管理导航项样式和链接。

---

## 十三、开发任务清单

### 阶段1: 数据模型 (优先级: 最高)

- [ ] 创建 `models/room/room_item.py` - RoomItem模型
- [ ] 创建 `models/room/room_item_record.py` - RoomItemRecord模型
- [ ] 创建 `models/room/room_item_assignment.py` - RoomItemAssignment模型
- [ ] 修改 `models/room/__init__.py` - 添加新模型导出
- [ ] 修改 `models/__init__.py` - 添加新模型导入
- [ ] 修改 `models/dorm/dorm.py` - 添加 pending_item_action 字段

### 阶段2: 蓝图核心功能 (优先级: 高)

- [ ] 创建 `blueprints/room/room_item.py` - 物品管理主蓝图
- [ ] 创建 `blueprints/room/room_item_api.py` - API蓝图
- [ ] 修改 `blueprints/room/__init__.py` - 添加新蓝图导出
- [ ] 修改 `blueprints/__init__.py` - 添加新蓝图导入
- [ ] 修改 `main.py` - 注册新蓝图

### 阶段3: 模板文件 (优先级: 高)

- [ ] 创建 `templates/room_manage/room_item_list.html`
- [ ] 创建 `templates/room_manage/room_item_add.html`
- [ ] 创建 `templates/room_manage/room_item_edit.html`
- [ ] 创建 `templates/room_manage/room_item_allocate.html`
- [ ] 创建 `templates/room_manage/room_item_transfer.html`
- [ ] 创建 `templates/room_manage/room_item_records.html`
- [ ] 创建 `templates/room_manage/room_item_confirm_dorm.html`

### 阶段4: 页面集成 (优先级: 中)

- [ ] 修改 `templates/room_manage/room_view.html` - 添加物品区块
- [ ] 修改 `blueprints/room/room.py` - view路由添加物品查询
- [ ] 修改 `templates/index.html` - 添加物品管理导航
- [ ] 修改 `templates/header.html` - 添加侧边栏导航

### 阶段5: 宿舍操作物品确认 (优先级: 中)

- [ ] 修改 `blueprints/dorm/dorm_operations.py` - 换宿/互换/退宿后检查物品
- [ ] 实现确认页面路由和模板
- [ ] 实现批量物品处理逻辑

### 阶段6: 导入导出 (优先级: 低)

- [ ] 修改 `blueprints/room/room_import_export.py` - 添加物品导出/导入
- [ ] 修改 `blueprints/user/user_import_export.py` - 添加持有物品导出

### 阶段7: 权限与测试 (优先级: 低)

- [ ] 添加权限码到角色权限系统
- [ ] 功能测试和代码审查

---

## 十四、关键业务逻辑说明

### 14.1 物品分配流程

```
1. 管理员选择物品 -> 点击"分配"
2. 选择用户 -> 输入分配数量
3. 验证: available_quantity >= 分配数量
4. 创建 RoomItemAssignment (status='active')
5. 更新 RoomItem.available_quantity -= 分配数量
6. 创建 RoomItemRecord (operation_type='allocate')
7. flash成功消息
```

### 14.2 物品归还流程

```
1. 管理员在分配记录中点击"归还"
2. 更新 RoomItemAssignment.status = 'returned', returned_at = now
3. 更新 RoomItem.available_quantity += 归还数量
4. 创建 RoomItemRecord (operation_type='return')
5. flash成功消息
```

### 14.3 物品状态变更流程(损坏/丢失/报废)

```
1. 管理员选择物品 -> 点击对应状态按钮
2. 更新 RoomItem.status = 新状态
3. 如果有用户持有(assignment status='active'):
   - 损坏: assignment.status = 'damaged'
   - 丢失: assignment.status = 'lost'
4. 创建 RoomItemRecord (operation_type=damage/loss/scrap)
5. flash成功消息
```

### 14.4 物品转移流程(仅transferable类型)

```
1. 管理员选择可转移物品 -> 点击"转移"
2. 选择目标房间
3. 验证: item.item_type == 'transferable'
4. 更新 RoomItem.room_id = 目标房间ID
5. 创建 RoomItemRecord (operation_type='transfer', from_room_id, to_room_id)
6. flash成功消息
```

### 14.5 宿舍操作物品确认流程

```
1. 换宿/互换/退宿完成 -> 检查旧房间物品分配
2. 如有待处理物品 -> Dorm.pending_item_action = True
3. flash提示"有待处理物品"
4. 管理员进入确认页面
5. 逐项选择: 归还/损坏/丢失/转移到新房间
6. 批量处理:
   - 归还: assignment.status='returned', item.available_quantity += qty
   - 损坏: assignment.status='damaged', item.status='损坏'
   - 丢失: assignment.status='lost', item.status='丢失'
   - 转移: item.room_id=新房间ID (仅transferable类型)
7. Dorm.pending_item_action = False
8. 创建对应RoomItemRecord
```

---

## 十五、注意事项

1. **不使用@property别名**: 根据项目经验，SQLAlchemy @property别名在Jinja2模板中不可靠，模板中直接使用字段名
2. **不使用CSRF**: 项目未使用CSRF保护，所有表单不加CSRF token
3. **日志规范**: logging模块记录所有失败和提示类日志，log_operation只记录操作类日志
4. **代码简单化**: 避免过度抽象，保持代码简洁直接
5. **flash消息**: 所有操作反馈通过flash消息传递，不使用JSON API返回操作结果(除API蓝图外)
6. **开发环境**: 不需要考虑数据迁移，直接创建新表即可