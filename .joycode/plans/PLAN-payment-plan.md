# 付款计划功能方案

## 一、需求概述

在合同管理模块中新增"付款计划"功能，付款计划依附于合同，一份合同可包含多个付款计划。付款计划支持灵活的付款方式（一次性、按月、按季度、按年等），支持固定金额和实际产生金额两种金额类型，并包含完整的审批流程（添加→预计付款时间→发票登记→对账单上传→提交审核→财务审核→付款完成）。

## 二、现有项目分析

### 2.1 合同模块现有结构

| 层级 | 文件路径 | 说明 |
|------|---------|------|
| 模型 | `models/contract/contract.py` | Contract 主模型 |
| 模型 | `models/contract/contract_operation_record.py` | 合同操作记录模型 |
| 蓝图 | `blueprints/contract/contract.py` | 主路由（列表、详情、表单页） |
| 蓝图 | `blueprints/contract/contract_api.py` | API 路由（JSON 接口） |
| 蓝图 | `blueprints/contract/contract_operations.py` | CRUD 操作路由 |
| 蓝图 | `blueprints/contract/contract_import_export.py` | 导入导出路由 |
| 模板 | `templates/contract_manage/contract_list.html` | 合同列表页 |
| 模板 | `templates/contract_manage/contract_detail.html` | 合同详情页 |
| 模板 | `templates/contract_manage/contract_form.html` | 合同表单页 |
| 工具 | `utils/contract_attachment.py` | 合同附件文件管理（纯文件系统） |

### 2.2 文件管理模式

项目采用**纯文件系统**模式管理附件，不使用数据库模型记录文件信息。参考 `utils/contract_attachment.py` 和 `utils/room_meter_photo.py`：

- 目录结构：`data/photo/{模块目录}/{实体ID}/`
- 支持多环境：Docker (`/data/`)、Android、PyInstaller 打包、开发环境
- 文件类型校验：图片、视频、文档、压缩包
- 核心方法：`upload_file()`、`get_media_files()`、`delete_file()`、`download_file()`

付款计划的发票和对账单文件管理将遵循相同模式，创建 `utils/payment_plan_file.py`。

### 2.3 操作记录模式

参考 `ContractOperationRecord` 模型：
- 记录字段：`operation_type`、`operator_id`、`operator_name`、`operation_time`、`change_detail`(JSON)、`summary`
- 提供 `create_record()` 类方法快速创建记录
- 付款计划的操作记录**复用** `ContractOperationRecord`，通过 `operation_type` 前缀区分（如 `payment_plan_add`、`payment_plan_edit` 等）

### 2.4 日志系统

项目使用 `utils/log.py` 中的 `log_operation()` 函数记录全局日志：
- 需在 `MODULE_MAP` 中新增 `'payment_plan': '付款计划管理'`
- 需在 `OPERATION_TYPE_MAP` 中新增付款计划相关操作类型映射

### 2.5 权限系统

使用 `utils/auth.py` 的 `@require_permission()` 装饰器，权限码格式为 `模块.操作`。需新增：
- `payment_plan.view` - 查看付款计划
- `payment_plan.create` - 创建付款计划
- `payment_plan.edit` - 编辑付款计划
- `payment_plan.delete` - 删除付款计划
- `payment_plan.submit_review` - 提交审核
- `payment_plan.finance_review` - 财务审核
- `payment_plan.complete_payment` - 确认付款完成

## 三、数据模型设计

### 3.1 付款计划主表 `PaymentPlan`

文件：`models/contract/payment_plan.py`

```python
class PaymentPlan(db.Model):
    __tablename__ = 'payment_plans'
    
    id = db.Column(db.Integer, primary_key=True)
    contract_id = db.Column(db.Integer, db.ForeignKey('contracts.id', ondelete='CASCADE'), nullable=False, comment='关联合同ID')
    
    # 基本信息
    plan_name = db.Column(db.String(255), nullable=False, comment='计划名称')
    plan_number = db.Column(db.String(50), unique=True, nullable=True, comment='计划编号（自动生成）')
    
    # 付款方式
    payment_method = db.Column(db.String(20), nullable=False, comment='付款方式：one_time/monthly/quarterly/yearly')
    
    # 金额类型
    amount_type = db.Column(db.String(20), nullable=False, comment='金额类型：fixed/actual')
    fixed_amount = db.Column(db.Numeric(14, 2), nullable=True, comment='固定金额（amount_type=fixed时使用）')
    
    # 付款计划明细（JSON格式，存储各期付款安排）
    # 格式: [{"period": "2026-01", "expected_date": "2026-01-15", "amount": 10000.00, "status": "pending"}, ...]
    payment_schedule = db.Column(db.Text, nullable=True, comment='付款计划明细（JSON格式）')
    
    # 时间信息
    start_date = db.Column(db.Date, nullable=True, comment='计划开始日期')
    end_date = db.Column(db.Date, nullable=True, comment='计划结束日期')
    
    # 状态流转
    status = db.Column(db.String(20), default='draft', nullable=False, comment='状态：draft/submitted/finance_reviewed/completed/cancelled')
    
    # 备注
    remark = db.Column(db.Text, nullable=True, comment='备注')
    
    # 操作人
    operator_user_id = db.Column(db.Integer, nullable=True, comment='操作人ID')
    created_by = db.Column(db.Integer, nullable=True, comment='创建人ID')
    
    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False, comment='更新时间')
    
    # 关系
    contract = db.relationship('Contract', backref=db.backref('payment_plans', lazy='dynamic', cascade='all, delete-orphan'))
    
    # 索引
    __table_args__ = (
        db.Index('idx_pp_contract_id', 'contract_id'),
        db.Index('idx_pp_status', 'status'),
        db.Index('idx_pp_contract_status', 'contract_id', 'status'),
    )
```

### 3.2 付款计划明细表 `PaymentPlanItem`

文件：`models/contract/payment_plan_item.py`

每期付款的独立记录，从 `payment_schedule` JSON 拆分为独立表以支持更灵活的查询和状态管理：

```python
class PaymentPlanItem(db.Model):
    __tablename__ = 'payment_plan_items'
    
    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('payment_plans.id', ondelete='CASCADE'), nullable=False, comment='关联付款计划ID')
    
    # 期次信息
    period_number = db.Column(db.Integer, nullable=False, comment='期次序号')
    period_label = db.Column(db.String(50), nullable=True, comment='期次标签（如"2026年1月"、"第1期"）')
    
    # 金额
    planned_amount = db.Column(db.Numeric(14, 2), nullable=True, comment='计划付款金额')
    actual_amount = db.Column(db.Numeric(14, 2), nullable=True, comment='实际付款金额')
    
    # 时间
    expected_payment_date = db.Column(db.Date, nullable=True, comment='预计付款日期')
    actual_payment_date = db.Column(db.Date, nullable=True, comment='实际付款日期')
    
    # 发票信息
    has_invoice = db.Column(db.Boolean, default=False, comment='是否有发票')
    invoice_number = db.Column(db.String(100), nullable=True, comment='发票号码')
    invoice_amount = db.Column(db.Numeric(14, 2), nullable=True, comment='发票金额')
    invoice_date = db.Column(db.Date, nullable=True, comment='发票日期')
    invoice_registered_at = db.Column(db.DateTime, nullable=True, comment='发票登记时间')
    invoice_registered_by = db.Column(db.Integer, nullable=True, comment='发票登记人ID')
    
    # 对账单信息
    has_statement = db.Column(db.Boolean, default=False, comment='是否有对账单')
    statement_uploaded_at = db.Column(db.DateTime, nullable=True, comment='对账单上传时间')
    statement_uploaded_by = db.Column(db.Integer, nullable=True, comment='对账单上传人ID')
    
    # 状态
    status = db.Column(db.String(20), default='pending', nullable=False, 
                       comment='状态：pending/invoiced/statement_uploaded/submitted/finance_approved/paid/cancelled')
    
    # 备注
    remark = db.Column(db.Text, nullable=True, comment='备注')
    
    # 时间记录
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    # 关系
    payment_plan = db.relationship('PaymentPlan', backref=db.backref('items', lazy='dynamic', cascade='all, delete-orphan'))
    
    # 索引
    __table_args__ = (
        db.Index('idx_ppi_plan_id', 'plan_id'),
        db.Index('idx_ppi_status', 'status'),
        db.Index('idx_ppi_expected_date', 'expected_payment_date'),
    )
```

### 3.3 模型关系图

```
Contract (1) ──── (N) PaymentPlan (1) ──── (N) PaymentPlanItem
     │                        │
     │                        └── 文件目录: data/photo/payment_plan_files/{plan_id}/invoices/
     │                        └── 文件目录: data/photo/payment_plan_files/{plan_id}/statements/
     │
     └──── (N) ContractOperationRecord (复用，通过 operation_type 前缀区分)
```

## 四、文件管理设计

### 4.1 文件管理工具类

文件：`utils/payment_plan_file.py`

参考 `utils/contract_attachment.py` 的模式，创建 `PaymentPlanFileManager` 类：

```python
class PaymentPlanFileManager:
    """付款计划文件管理工具类（发票、对账单）
    基于纯文件系统模式，不依赖数据库记录
    """
    
    # 目录结构：data/photo/payment_plan_files/{plan_id}/invoices/  - 发票文件
    #           data/photo/payment_plan_files/{plan_id}/statements/ - 对账单文件
    
    @staticmethod
    def get_media_root_dir():
        """获取付款计划文件根目录"""
        # 支持 Docker/Android/PyInstaller/开发环境
        
    @staticmethod
    def get_plan_directory(plan_id, file_type='invoices'):
        """获取指定付款计划的文件目录
        file_type: 'invoices' 或 'statements'
        """
        
    @staticmethod
    def upload_file(plan_id, file, file_type='invoices'):
        """上传文件"""
        
    @staticmethod
    def get_files(plan_id, file_type='invoices'):
        """获取文件列表"""
        
    @staticmethod
    def delete_file(plan_id, filename, file_type='invoices'):
        """删除文件"""
        
    @staticmethod
    def download_file(plan_id, filename, file_type='invoices'):
        """下载文件"""
```

### 4.2 目录结构

```
data/
  photo/
    payment_plan_files/
      {plan_id}/
        invoices/        # 发票文件
          invoice_001.pdf
          invoice_002.jpg
        statements/      # 对账单文件
          statement_001.pdf
          statement_002.xlsx
```

## 五、蓝图路由设计

### 5.1 页面路由蓝图

文件：`blueprints/contract/payment_plan.py`

```python
payment_plan_bp = Blueprint('payment_plan', __name__, url_prefix='/contract/payment-plan')

# 付款计划列表页（按合同ID筛选）
@payment_plan_bp.route('/<int:contract_id>', methods=['GET'])
def index(contract_id):

# 付款计划详情页
@payment_plan_bp.route('/detail/<int:id>', methods=['GET'])
def detail(id):

# 添加付款计划页面
@payment_plan_bp.route('/add/<int:contract_id>', methods=['GET'])
def add_page(contract_id):

# 编辑付款计划页面
@payment_plan_bp.route('/edit/<int:id>', methods=['GET'])
def edit_page(id):
```

### 5.2 API 路由蓝图

文件：`blueprints/contract/payment_plan_api.py`

```python
payment_plan_api_bp = Blueprint('payment_plan_api', __name__, url_prefix='/api/payment-plans')

# 获取付款计划列表JSON
@payment_plan_api_bp.route('/<int:contract_id>', methods=['GET'])

# 获取付款计划详情JSON
@payment_plan_api_bp.route('/detail/<int:id>', methods=['GET'])

# 创建付款计划
@payment_plan_api_bp.route('/', methods=['POST'])

# 更新付款计划
@payment_plan_api_bp.route('/<int:id>', methods=['PUT'])

# 删除付款计划
@payment_plan_api_bp.route('/<int:id>', methods=['DELETE'])

# 提交审核
@payment_plan_api_bp.route('/<int:id>/submit', methods=['POST'])

# 财务审核
@payment_plan_api_bp.route('/<int:id>/finance-review', methods=['POST'])

# 确认付款完成
@payment_plan_api_bp.route('/<int:id>/complete', methods=['POST'])

# 取消付款计划
@payment_plan_api_bp.route('/<int:id>/cancel', methods=['POST'])

# === 付款明细操作 ===

# 更新明细状态（登记发票、上传对账单等）
@payment_plan_api_bp.route('/items/<int:item_id>', methods=['PUT'])

# 登记发票
@payment_plan_api_bp.route('/items/<int:item_id>/register-invoice', methods=['POST'])

# 上传对账单文件
@payment_plan_api_bp.route('/items/<int:item_id>/upload-statement', methods=['POST'])

# 上传发票文件
@payment_plan_api_bp.route('/items/<int:item_id>/upload-invoice', methods=['POST'])

# 获取发票文件列表
@payment_plan_api_bp.route('/items/<int:item_id>/invoices', methods=['GET'])

# 获取对账单文件列表
@payment_plan_api_bp.route('/items/<int:item_id>/statements', methods=['GET'])

# 删除发票文件
@payment_plan_api_bp.route('/items/<int:item_id>/invoices/<filename>', methods=['DELETE'])

# 删除对账单文件
@payment_plan_api_bp.route('/items/<int:item_id>/statements/<filename>', methods=['DELETE'])
```

## 六、状态流转设计

### 6.1 付款计划状态

```
draft (草稿) → submitted (已提交审核) → finance_reviewed (财务已审核) → completed (已完成)
    ↓               ↓                        ↓
cancelled (已取消)  cancelled (已取消)        cancelled (已取消)
```

### 6.2 付款明细状态

```
pending (待付款) → invoiced (已登记发票) → statement_uploaded (已上传对账单) 
    → submitted (已提交) → finance_approved (财务已审批) → paid (已付款)
    
任意状态 → cancelled (已取消)
```

### 6.3 状态说明

| 付款计划状态 | 说明 | 可执行操作 |
|-------------|------|-----------|
| draft | 草稿，可编辑 | 编辑、删除、提交审核 |
| submitted | 已提交审核，等待财务 | 财务审核、取消 |
| finance_reviewed | 财务已审核 | 确认完成、取消 |
| completed | 付款完成 | 查看 |
| cancelled | 已取消 | 查看 |

| 付款明细状态 | 说明 |
|-------------|------|
| pending | 待处理，等待登记发票或上传对账单 |
| invoiced | 已登记发票信息 |
| statement_uploaded | 已上传对账单文件 |
| submitted | 已提交审批 |
| finance_approved | 财务已审批 |
| paid | 已完成付款 |

## 七、页面设计

### 7.1 合同列表页修改

在 `templates/contract_manage/contract_list.html` 的操作列中，为每行合同增加"付款计划"按钮：

```html
<button onclick="window.location.href='{{ url_for('payment_plan.index', contract_id=contract.id) }}'" 
        class="btn-effect bg-indigo-500 text-white px-2 py-1 rounded-md text-sm flex items-center">
    <i class="fa fa-calendar-check-o mr-1"></i>付款计划
</button>
```

### 7.2 合同详情页修改

在 `templates/contract_manage/contract_detail.html` 中：

1. **操作按钮区**增加"添加付款计划"按钮：
```html
<a href="{{ url_for('payment_plan.add_page', contract_id=contract.id) }}" 
   class="px-4 py-2 bg-indigo-500 text-white rounded-md hover:bg-indigo-600 btn-hover inline-flex items-center">
    <i class="fa fa-calendar-plus-o mr-1"></i>添加付款计划
</a>
```

2. **左侧信息区**增加"当前在用付款计划"卡片，显示该合同下状态为 `draft`/`submitted`/`finance_reviewed` 的付款计划摘要。

### 7.3 新增模板文件

| 文件路径 | 说明 |
|---------|------|
| `templates/contract_manage/payment_plan_list.html` | 付款计划列表页 |
| `templates/contract_manage/payment_plan_detail.html` | 付款计划详情页 |
| `templates/contract_manage/payment_plan_form.html` | 付款计划添加/编辑表单页 |

### 7.4 付款计划列表页布局

- 顶部：合同信息摘要卡片（合同编号、名称、金额、状态）
- 功能按钮：添加付款计划、返回合同详情
- 筛选区：状态筛选
- 表格列：计划编号、计划名称、付款方式、金额类型、金额、状态、创建时间、操作
- 操作按钮：查看、编辑、删除、提交审核（按状态显示）

### 7.5 付款计划详情页布局

- 顶部：计划基本信息 + 状态标签
- 操作按钮：编辑、提交审核、财务审核、确认完成、取消（按状态显示）
- 付款明细表格：
  - 期次、期次标签、计划金额、实际金额、预计付款日期、实际付款日期
  - 发票状态（有/无，点击查看/登记）、对账单状态（有/无，点击查看/上传）
  - 明细状态、操作按钮
- 右侧：操作记录时间线（复用合同操作记录）

### 7.6 付款计划表单页布局

- 基本信息：计划名称、付款方式（下拉：一次性/按月/按季度/按年）、金额类型（固定/实际产生）
- 固定金额输入（金额类型为"固定"时显示）
- 计划日期范围：开始日期、结束日期
- 付款明细预览区：根据付款方式和日期范围自动生成期次列表
  - 一次性：1期
  - 按月：每月1期
  - 按季度：每季度1期
  - 按年：每年1期
- 每期可设置：预计付款日期、计划金额
- 备注

## 八、操作记录设计

付款计划的操作记录**复用** `ContractOperationRecord` 模型，通过 `operation_type` 前缀区分：

| operation_type | 中文说明 |
|---------------|---------|
| payment_plan_add | 创建付款计划 |
| payment_plan_edit | 编辑付款计划 |
| payment_plan_delete | 删除付款计划 |
| payment_plan_submit | 提交审核 |
| payment_plan_finance_review | 财务审核 |
| payment_plan_complete | 付款完成 |
| payment_plan_cancel | 取消付款计划 |
| payment_plan_invoice_register | 登记发票 |
| payment_plan_statement_upload | 上传对账单 |
| payment_plan_invoice_file_upload | 上传发票文件 |
| payment_plan_invoice_file_delete | 删除发票文件 |
| payment_plan_statement_file_delete | 删除对账单文件 |

`change_detail` JSON 格式示例：
```json
{
    "plan_id": 1,
    "plan_name": "2026年度物业费付款计划",
    "changes": {
        "status": {"old": "draft", "new": "submitted"}
    }
}
```

## 九、日志系统扩展

在 `utils/log.py` 中新增：

```python
# MODULE_MAP
'payment_plan': '付款计划管理',

# OPERATION_TYPE_MAP
('payment_plan', 'payment_plan_add'): '创建付款计划',
('payment_plan', 'payment_plan_edit'): '编辑付款计划',
('payment_plan', 'payment_plan_delete'): '删除付款计划',
('payment_plan', 'payment_plan_submit'): '提交审核',
('payment_plan', 'payment_plan_finance_review'): '财务审核',
('payment_plan', 'payment_plan_complete'): '付款完成',
('payment_plan', 'payment_plan_cancel'): '取消付款计划',
('payment_plan', 'invoice_register'): '登记发票',
('payment_plan', 'statement_upload'): '上传对账单',
('payment_plan', 'records'): '访问页面',
('payment_plan', 'payment_plan_api'): '调用接口',
```

## 十、实现步骤

### 阶段一：数据模型与基础设施

1. **创建模型文件**
   - [ ] `models/contract/payment_plan.py` - PaymentPlan 模型
   - [ ] `models/contract/payment_plan_item.py` - PaymentPlanItem 模型
   - [ ] 更新 `models/contract/__init__.py` 导出新模型

2. **创建文件管理工具**
   - [ ] `utils/payment_plan_file.py` - PaymentPlanFileManager 类

3. **扩展日志系统**
   - [ ] 更新 `utils/log.py` 添加 payment_plan 模块映射

4. **数据库迁移**
   - [ ] 在 `main.py` 中确保新表创建（db.create_all()）

### 阶段二：蓝图与路由

5. **创建蓝图文件**
   - [ ] `blueprints/contract/payment_plan.py` - 页面路由
   - [ ] `blueprints/contract/payment_plan_api.py` - API 路由

6. **注册蓝图**
   - [ ] 更新 `blueprints/contract/__init__.py` 导出新蓝图
   - [ ] 更新 `main.py` 注册新蓝图

### 阶段三：前端页面

7. **创建模板文件**
   - [ ] `templates/contract_manage/payment_plan_list.html`
   - [ ] `templates/contract_manage/payment_plan_detail.html`
   - [ ] `templates/contract_manage/payment_plan_form.html`

8. **修改现有页面**
   - [ ] 修改 `templates/contract_manage/contract_list.html` 增加付款计划按钮
   - [ ] 修改 `templates/contract_manage/contract_detail.html` 增加付款计划区域和按钮

### 阶段四：功能完善

9. **权限配置**
   - [ ] 在系统权限配置中添加 payment_plan 相关权限

10. **操作记录集成**
    - [ ] 在各操作中调用 ContractOperationRecord.create_record()

11. **测试验证**
    - [ ] 付款计划 CRUD 功能
    - [ ] 状态流转功能
    - [ ] 发票登记和对账单上传
    - [ ] 操作记录记录
    - [ ] 文件上传/下载/删除

## 十一、关键设计决策

| 决策项 | 方案 | 理由 |
|-------|------|------|
| 文件管理 | 纯文件系统，不建模型 | 与项目现有模式一致（合同附件、抄表照片） |
| 操作记录 | 复用 ContractOperationRecord | 付款计划依附于合同，操作记录归属合同更合理 |
| 付款明细 | 独立表 PaymentPlanItem | 支持灵活查询和独立状态管理，优于JSON字段 |
| 计划编号 | 自动生成 | 格式：PP-YYYYMMDD-NNN，确保唯一性 |
| 金额类型 | 固定/实际产生 | 固定金额在创建时确定每期金额，实际产生金额在付款时填写 |
| 付款方式 | 一次性/按月/按季/按年 | 创建时根据方式自动生成期次，用户可调整每期日期和金额 |
| 蓝图组织 | 放在 contract 模块下 | 付款计划是合同的子功能，保持模块内聚性 |