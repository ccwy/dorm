# 房间模块床位管理前端展示方案

## 一、需求概述

1. 房间查看页面（room_view.html）增加床位状态卡片区域
2. 每个床位显示：床位号、状态（可用/已占用/维护中/已关闭）
3. 已占用床位显示入住人员姓名
4. 前端受 `ROOM_BED_MANAGEMENT_ENABLED` 系统配置控制——禁用时不显示床位卡片

## 二、当前状态分析

### 数据模型关系
- `Room` → `room_beds` relationship → `Bed` 列表
- `Bed` 有 `status`（available/occupied/maintenance/closed）、`bed_number`
- `Dorm` 有 `bed_id` FK → `Bed.id`，`status='active'` 表示在住
- `Dorm` → `user` relationship → 用户姓名

### 现有模板
- `room_view.html`：房间详情页，已有"居住用户"表格（current_residents），但无床位信息
- `room_manage.html`：房间列表页，表格形式，显示容量/已住/入住率

### 系统配置访问方式
- 模板中可用 `get_config_value('ROOM_BED_MANAGEMENT_ENABLED', True)` 
- 已在 `main.py:246` 注册为 Jinja2 全局函数

## 三、方案设计

### 步骤1：后端 — room view 路由传递床位数据

**文件**: `blueprints/room/room.py` 的 `view()` 函数

**修改内容**:
- 查询房间的所有床位：`beds = Bed.query.filter_by(room_id=room.id).order_by(Bed.bed_number).all()`
- 为每个已占用床位关联查询入住用户名：
  ```python
  bed_info_list = []
  for bed in beds:
      occupant_name = None
      if bed.status == 'occupied':
          dorm = Dorm.query.filter_by(bed_id=bed.id, status='active').first()
          if dorm and dorm.user:
              occupant_name = dorm.user.name
      bed_info_list.append({
          'bed_number': bed.bed_number,
          'status': bed.status,
          'status_display': bed.status_display,  # 利用已有property
          'occupant_name': occupant_name,
          'remark': bed.remark
      })
  ```
- 传递 `bed_info_list` 和 `bed_management_enabled` 到模板

**注意**: `bed.status_display` 是 Bed 模型已有的 `@property`，返回中文状态文本

### 步骤2：前端 — room_view.html 增加床位卡片区域

**文件**: `templates/room_manage/room_view.html`

**位置**: 在"居住用户"表格之前（约行352之前），增加"床位状态"区域

**实现方式**: 纯HTML + Jinja2，不使用JS

```html
<!-- 床位状态区域 - 受系统配置控制 -->
{% if bed_management_enabled %}
<div class="mb-8">
    <h3 class="text-lg font-medium mb-4 pb-2 border-b border-gray-200 flex items-center">
        <i class="fa fa-bed text-primary mr-2"></i>床位状态
    </h3>
    <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-4">
        {% for bed in bed_info_list %}
        <div class="border rounded-lg p-3 text-center 
            {% if bed.status == 'available' %}border-green-200 bg-green-50
            {% elif bed.status == 'occupied' %}border-blue-200 bg-blue-50
            {% elif bed.status == 'maintenance' %}border-yellow-200 bg-yellow-50
            {% elif bed.status == 'closed' %}border-gray-200 bg-gray-50
            {% else %}border-gray-200 bg-white{% endif %}">
            <div class="text-sm font-medium text-gray-700">床位 {{ bed.bed_number }}</div>
            <div class="mt-1">
                {% if bed.status == 'available' %}
                    <span class="text-xs px-2 py-0.5 bg-green-100 text-green-700 rounded-full">可用</span>
                {% elif bed.status == 'occupied' %}
                    <span class="text-xs px-2 py-0.5 bg-blue-100 text-blue-700 rounded-full">{{ bed.occupant_name or '已占用' }}</span>
                {% elif bed.status == 'maintenance' %}
                    <span class="text-xs px-2 py-0.5 bg-yellow-100 text-yellow-700 rounded-full">维护中</span>
                {% elif bed.status == 'closed' %}
                    <span class="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded-full">已关闭</span>
                {% endif %}
            </div>
            {% if bed.remark %}
            <div class="text-xs text-gray-400 mt-1">{{ bed.remark }}</div>
            {% endif %}
        </div>
        {% endfor %}
        {% if not bed_info_list %}
        <p class="text-gray-500 col-span-full text-center py-4">暂无床位信息</p>
        {% endif %}
    </div>
</div>
{% endif %}
```

### 步骤3：前端 — room_manage.html 列表页增加床位简要信息（可选）

**文件**: `templates/room_manage/room_manage.html`

**修改内容**: 在表格"已住"列旁边，受配置控制显示"可用床位"列

**后端**: `manage()` 函数需传递 `bed_management_enabled` 配置值

**前端**: 在表头和表体增加条件列：
```html
{% if bed_management_enabled %}
<th>可用床位</th>
{% endif %}
...
{% if bed_management_enabled %}
<td>{{ room.room_beds|selectattr('status', 'equalto', 'available')|list|length }}</td>
{% endif %}
```

**注意**: `room.room_beds` 是已加载的 relationship，无需额外查询。但列表页分页加载时需注意 N+1 问题，可考虑在 Room 查询时 `joinedload('room_beds')`。

## 四、影响范围

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `blueprints/room/room.py` | 修改 | view() 增加床位数据查询和传递；manage() 传递配置值 |
| `templates/room_manage/room_view.html` | 修改 | 增加床位状态卡片区域 |
| `templates/room_manage/room_manage.html` | 修改（可选） | 列表页增加可用床位列 |

## 五、不做的事

- 不修改 Bed 模型（已有 `status_display` property 可直接使用）
- 不修改 Room 模型
- 不增加新的 API 接口
- 不使用 JavaScript（遵循项目规则：前端尽量用HTML，少用JS）
- 不修改 room_add/room_edit 页面（创建/编辑房间时床位自动生成，无需手动操作）

## 六、验证要点

1. `ROOM_BED_MANAGEMENT_ENABLED=true` 时，房间详情页显示床位卡片
2. `ROOM_BED_MANAGEMENT_ENABLED=false` 时，床位卡片区域不显示
3. 已占用床位显示入住人员姓名
4. 可用床位显示"可用"标签
5. 维护中/已关闭床位正确显示对应状态
6. 床位按 bed_number 排序显示
7. 无床位时不报错，显示"暂无床位信息"