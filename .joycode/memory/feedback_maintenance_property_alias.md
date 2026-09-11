---
name: maintenance-property-alias
description: SQLAlchemy @property aliases不可靠地解析在Jinja2模板中，应使用直接字段访问
type: feedback
---

**规则**: 不要在模型上使用@property别名来为Jinja2模板提供替代字段名，它们在模板中不可靠地解析。

**Why**: MaintenanceOrder模型的@property别名(order_number→order_no, room_info→room_number等)在模板中返回空白值，可能因SQLAlchemy代理行为。

**How to apply**: 用直接列名(order.order_no)和显式关系遍历(order.assigned_user.name if order.assigned_user else '未分配')；列表查询加joinedload()防N+1。@property在Python代码中可用但不要用于模板。