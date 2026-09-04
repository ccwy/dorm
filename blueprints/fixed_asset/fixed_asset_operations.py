from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from utils.db import db
from models.fixed_asset.fixed_asset import FixedAsset
from models.fixed_asset.asset_operation_record import AssetOperationRecord
from models.fixed_asset.asset_inventory import AssetInventory
from models.fixed_asset.asset_inventory_detail import AssetInventoryDetail
from utils.log import log_operation
from utils.asset_photo import AssetPhotoManager
from utils.auth import require_permission
from models.system_config.system_config import SystemConfig
from models.department.department import Department
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import json
import logging
import traceback
from .fixed_asset import fixed_asset_bp


# ========== 工具函数 ==========


def _ensure_supplier_exists(name, operator_user_id=None, handler_user_id=None):
    """确保供应商存在，不存在则自动创建（固定资产自定义输入时同步保存）"""
    if not name:
        return
    from models.supply.supplier import Supplier
    existing = Supplier.query.filter_by(name=name).first()
    if not existing:
        Supplier.create(
            name=name,
            status='启用',
            operator_user_id=operator_user_id,
            handler_user_id=handler_user_id
        )


def _ensure_storage_location_exists(name, operator_user_id=None, usage_type='固定资产', handler_user_id=None):
    """确保存放位置存在，不存在则自动创建（固定资产自定义输入时同步保存）"""
    if not name:
        return
    from models.supply.storage_location import StorageLocation
    existing = StorageLocation.query.filter_by(name=name, usage_type=usage_type).first()
    if not existing:
        StorageLocation.create(
            name=name,
            status='启用',
            usage_type=usage_type,
            operator_user_id=operator_user_id,
            handler_user_id=handler_user_id
        )


def _ensure_department_exists(name, company=None):
    """确保部门存在，不存在则自动创建（按name+company联合查找）"""
    if not name:
        return
    # 按name+company查找
    query = Department.query.filter_by(name=name)
    if company:
        query = query.filter(db.or_(Department.company == company, Department.company.is_(None)))
    else:
        query = query.filter(Department.company.is_(None))
    existing = query.first()
    if not existing:
        Department.create(name=name, company=company, status='正常')

def _parse_date(date_str):
    """将日期字符串转换为date对象，空字符串返回None"""
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str.strip(), '%Y-%m-%d').date()
    except ValueError:
        logging.warning(f"日期格式无效: {date_str}")
        return None


def _parse_decimal(value_str):
    """将字符串转换为Decimal，空字符串返回None"""
    if not value_str or not str(value_str).strip():
        return None
    try:
        return Decimal(str(value_str).strip())
    except (InvalidOperation, ValueError):
        logging.warning(f"金额格式无效: {value_str}")
        return None


def _generate_inventory_number():
    """生成盘点单号：PD + 年月 + 4位序号"""
    today = datetime.now()
    prefix = f"PD{today.strftime('%Y%m')}"
    last_inventory = AssetInventory.query.filter(
        AssetInventory.inventory_number.like(f"{prefix}%")
    ).order_by(AssetInventory.id.desc()).first()
    if last_inventory and last_inventory.inventory_number:
        try:
            seq = int(last_inventory.inventory_number[-4:]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"


# ========== 路由：新增资产 ==========
@fixed_asset_bp.route('/operations/add', methods=['POST'])
@login_required
@require_permission('fixed_asset.create')
def add_asset():
    """新增资产"""
    try:
        # 获取表单字段
        asset_number = request.form.get('asset_number', '').strip()
        asset_name = request.form.get('asset_name', '').strip()
        asset_category = request.form.get('asset_category', '').strip()
        specification = request.form.get('specification', '').strip()
        brand = request.form.get('brand', '').strip()
        supplier = request.form.get('supplier', '').strip()
        quantity_str = request.form.get('quantity', '1').strip()
        unit = request.form.get('unit', '台').strip()
        original_value_str = request.form.get('original_value', '').strip()
        net_value_str = request.form.get('net_value', '').strip()
        purchase_date_str = request.form.get('purchase_date', '').strip()
        warranty_expiry_str = request.form.get('warranty_expiry', '').strip()
        storage_location = request.form.get('storage_location', '').strip()
        company = request.form.get('company', '').strip() or None
        department_using_name = request.form.get('department_using', '').strip()
        department_owning_name = request.form.get('department_owning', '').strip()
        supply_item_id_str = request.form.get('supply_item_id', '').strip()

        # 验证选择的物料基础资料是否为启用状态
        if supply_item_id_str:
            from models.supply.supply_item import SupplyItem
            selected_item = SupplyItem.query.get(int(supply_item_id_str))
            if not selected_item or selected_item.status != '启用':
                flash('所选物料基础资料已停用，请重新选择', 'danger')
                return redirect(url_for('fixed_asset.index'))

        # 同步保存自定义供应商到供应商模块
        if supplier:
            _ensure_supplier_exists(supplier, current_user.id, handler_user_id=current_user.id)

        # 同步保存自定义存放位置到存放位置模块
        if storage_location:
            _ensure_storage_location_exists(storage_location, current_user.id, handler_user_id=current_user.id)

        # 通过部门名称+公司查找部门ID，不存在则自动创建
        dept_using_id = None
        dept_owning_id = None

        if department_using_name:
            _ensure_department_exists(department_using_name, company)
            dept_query = Department.query.filter_by(name=department_using_name)
            if company:
                dept_query = dept_query.filter(db.or_(Department.company == company, Department.company.is_(None)))
            else:
                dept_query = dept_query.filter(Department.company.is_(None))
            dept = dept_query.first()
            if dept:
                dept_using_id = dept.id
                if not company and dept.company:
                    company = dept.company

        if department_owning_name:
            _ensure_department_exists(department_owning_name, company)
            dept_query = Department.query.filter_by(name=department_owning_name)
            if company:
                dept_query = dept_query.filter(db.or_(Department.company == company, Department.company.is_(None)))
            else:
                dept_query = dept_query.filter(Department.company.is_(None))
            dept = dept_query.first()
            if dept:
                dept_owning_id = dept.id
                if not company and dept.company:
                    company = dept.company

        responsible_person = request.form.get('responsible_person', '').strip()
        room_id_str = request.form.get('room_id', '').strip()
        responsible_user_id_str = request.form.get('responsible_user_id', '').strip()
        asset_source = request.form.get('asset_source', '采购').strip()
        status = request.form.get('status', '在用').strip()
        remark = request.form.get('remark', '').strip()

        # 必填字段校验
        if not asset_name:
            flash('资产名称不能为空', 'danger')
            return redirect(url_for('fixed_asset.index'))
        if not asset_category:
            flash('资产分类不能为空', 'danger')
            return redirect(url_for('fixed_asset.index'))

        # 数量处理
        try:
            quantity = int(quantity_str)
            if quantity <= 0:
                flash('数量必须大于0', 'danger')
                return redirect(url_for('fixed_asset.index'))
        except ValueError:
            flash('数量格式无效', 'danger')
            return redirect(url_for('fixed_asset.index'))

        # 日期处理
        purchase_date = _parse_date(purchase_date_str)
        warranty_expiry = _parse_date(warranty_expiry_str)

        # 金额处理
        original_value = _parse_decimal(original_value_str)
        net_value = _parse_decimal(net_value_str)

        # FK字段转换：room_id和responsible_user_id
        room_id = int(room_id_str) if room_id_str else None
        responsible_user_id = int(responsible_user_id_str) if responsible_user_id_str else None

        # 如果选择了关联用户，将responsible_person也设为用户姓名（冗余存储方便显示）
        if responsible_user_id:
            from models.user.user import User
            user = User.query.get(responsible_user_id)
            if user:
                responsible_person = user.name

        # 资产编号：为空则预生成（需在创建物料前确定，以便同步为物品编号）
        if not asset_number:
            from models.fixed_asset.fixed_asset import FixedAsset as FA
            asset_number = FA.generate_asset_number()

        # 同步保存到物料基础资料（每次新增资产都创建新的物料记录，物品编号=资产编号）
        supply_item_id = None
        if asset_name:
            from models.supply.supply_item import SupplyItem
            new_item = SupplyItem.create(
                name=asset_name, category='固定资产',
                specification=specification or None, brand=brand or None,
                unit=unit or None, status='启用',
                operator_user_id=current_user.id,
                item_number=asset_number
            )
            supply_item_id = new_item.id

        # 调用模型创建资产
        asset = FixedAsset.create(
            asset_number=asset_number,
            asset_name=asset_name,
            asset_category=asset_category,
            specification=specification or None,
            brand=brand or None,
            supplier=supplier or None,
            quantity=quantity,
            unit=unit or '台',
            original_value=original_value,
            net_value=net_value,
            purchase_date=purchase_date,
            warranty_expiry=warranty_expiry,
            storage_location=storage_location or None,
            department_using_id=dept_using_id,
            department_owning_id=dept_owning_id,
            company=company,
            responsible_person=responsible_person or None,
            asset_source=asset_source or '采购',
            status=status or '在用',
            remark=remark or None,
            operator_user_id=current_user.id,
            room_id=room_id,
            responsible_user_id=responsible_user_id,
            supply_item_id=supply_item_id
        )

        # 创建库存明细记录（入库）
        from models.fixed_asset.asset_stock_item import AssetStockItem
        from models.fixed_asset.asset_stock_record import AssetStockRecord
        stock_item = AssetStockItem.add_stock(
            asset_id=asset.id,
            quantity=quantity,
            storage_location=storage_location or None,
            room_id=room_id,
            company=company,
            department_using_id=dept_using_id,
            department_owning_id=dept_owning_id,
            responsible_person=responsible_person or None,
            responsible_user_id=responsible_user_id,
            operator_user_id=current_user.id
        )
        # 创建库存变动记录
        AssetStockRecord.create_record(
            asset_id=asset.id,
            record_type='入库',
            record_subtype='新增入库',
            quantity=quantity,
            to_stock_item_id=stock_item.id if stock_item else None,
            storage_location=storage_location or None,
            room_id=room_id,
            company=company,
            department_using_id=dept_using_id,
            department_owning_id=dept_owning_id,
            operator_user_id=current_user.id,
            operator_name=current_user.username if hasattr(current_user, 'username') else None,
            remark='新增资产入库'
        )

        # 构建详细摘要
        summary_parts = [f"新增资产: {asset.asset_name}({asset.display_number})"]
        summary_parts.append(f"分类: {asset.asset_category}")
        if asset.specification:
            summary_parts.append(f"规格: {asset.specification}")
        if asset.brand:
            summary_parts.append(f"品牌: {asset.brand}")
        summary_parts.append(f"数量: {asset.quantity}{asset.unit or '台'}")
        if asset.original_value:
            summary_parts.append(f"原值: {asset.original_value}元")
        if asset.net_value:
            summary_parts.append(f"净值: {asset.net_value}元")
        if asset.purchase_date:
            summary_parts.append(f"购置日期: {asset.purchase_date.isoformat()}")
        if asset.storage_location:
            summary_parts.append(f"存放位置: {asset.storage_location}")
        if asset.department_using:
            summary_parts.append(f"使用部门: {asset.department_using}")
        if asset.department_owning:
            summary_parts.append(f"归属部门: {asset.department_owning}")
        if asset.responsible_person:
            summary_parts.append(f"责任人: {asset.responsible_person}")
        if asset.company:
            summary_parts.append(f"所属公司: {asset.company}")
        if asset.asset_source:
            summary_parts.append(f"来源: {asset.asset_source}")
        summary_parts.append(f"状态: {asset.status}")
        summary = "，".join(summary_parts)

        # 创建操作记录（完整资产信息JSON）
        change_detail = {
            'asset_number': asset.asset_number,
            'asset_name': asset.asset_name,
            'asset_category': asset.asset_category,
            'specification': asset.specification,
            'brand': asset.brand,
            'supplier': asset.supplier,
            'quantity': asset.quantity,
            'unit': asset.unit,
            'original_value': str(asset.original_value) if asset.original_value else None,
            'net_value': str(asset.net_value) if asset.net_value else None,
            'purchase_date': asset.purchase_date.isoformat() if asset.purchase_date else None,
            'warranty_expiry': asset.warranty_expiry.isoformat() if asset.warranty_expiry else None,
            'storage_location': asset.storage_location,
            'company': asset.company,
            'department_using': asset.department_using,
            'department_owning': asset.department_owning,
            'responsible_person': asset.responsible_person,
            'room_display': asset.room_display,
            'responsible_user_name': asset.responsible_user_name,
            'asset_source': asset.asset_source,
            'status': asset.status,
        }

        AssetOperationRecord.create_record(
            asset_id=asset.id,
            operation_type='add',
            operator_id=current_user.id,
            operator_name=current_user.username if hasattr(current_user, 'username') else None,
            change_detail=change_detail,
            summary=summary
        )

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_add',
            action=f"新增资产: {asset.asset_name}({asset.display_number})",
            result="成功"
        )

        flash(f'新增资产成功: {asset.asset_name}({asset.display_number})', 'success')
        logging.info(f"新增资产成功，资产ID: {asset.id}, 资产编号: {asset.display_number}")
        if request.form.get('action') == 'return':
            return redirect(url_for('fixed_asset.index'))
        else:
            #flash(f'可继续添加新资产', 'info')
            return redirect(url_for('fixed_asset.add_page'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_add',
            action=f"新增资产失败: {str(e)}",
            result="失败"
        )
        flash(f'新增资产失败: {str(e)}', 'danger')
        logging.error(f"新增资产失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('fixed_asset.index'))


# ========== 路由：编辑资产 ==========
@fixed_asset_bp.route('/operations/edit/<int:id>', methods=['POST'])
@login_required
@require_permission('fixed_asset.edit')
def edit_asset(id):
    """编辑资产 - 逐字段对比，仅记录变更字段"""
    from models.fixed_asset.asset_stock_item import AssetStockItem
    from models.fixed_asset.asset_stock_record import AssetStockRecord
    try:
        asset = FixedAsset.query.get_or_404(id)

        # 记录变更字段的列表
        changes = []

        # 处理部门和公司字段（编辑模板发送department_using/department_owning名称+company）
        company = request.form.get('company', '').strip() or None
        dept_using_name = request.form.get('department_using', '').strip()
        dept_owning_name = request.form.get('department_owning', '').strip()

        # 通过部门名称+公司查找/创建部门获取ID
        new_dept_using_id = None
        new_dept_owning_id = None

        if dept_using_name:
            _ensure_department_exists(dept_using_name, company)
            dept_query = Department.query.filter_by(name=dept_using_name)
            if company:
                dept_query = dept_query.filter(db.or_(Department.company == company, Department.company.is_(None)))
            else:
                dept_query = dept_query.filter(Department.company.is_(None))
            dept = dept_query.first()
            if dept:
                new_dept_using_id = dept.id
                if not company and dept.company:
                    company = dept.company

        if dept_owning_name:
            _ensure_department_exists(dept_owning_name, company)
            dept_query = Department.query.filter_by(name=dept_owning_name)
            if company:
                dept_query = dept_query.filter(db.or_(Department.company == company, Department.company.is_(None)))
            else:
                dept_query = dept_query.filter(Department.company.is_(None))
            dept = dept_query.first()
            if dept:
                new_dept_owning_id = dept.id
                if not company and dept.company:
                    company = dept.company

        # 比较并更新 company 字段
        old_company = asset.company
        if old_company != company:
            changes.append({
                'field': 'company',
                'field_display': '所属公司',
                'old': str(old_company) if old_company else '',
                'new': str(company) if company else ''
            })
            asset.company = company

        # 比较并更新 department_using_id 字段
        old_dept_using_id = asset.department_using_id
        if old_dept_using_id != new_dept_using_id:
            old_dept_using_name = asset.department_using or ''
            changes.append({
                'field': 'department_using_id',
                'field_display': '使用部门',
                'old': old_dept_using_name,
                'new': dept_using_name or ''
            })
            asset.department_using_id = new_dept_using_id

        # 比较并更新 department_owning_id 字段
        old_dept_owning_id = asset.department_owning_id
        if old_dept_owning_id != new_dept_owning_id:
            old_dept_owning_name = asset.department_owning or ''
            changes.append({
                'field': 'department_owning_id',
                'field_display': '归属部门',
                'old': old_dept_owning_name,
                'new': dept_owning_name or ''
            })
            asset.department_owning_id = new_dept_owning_id

        # 定义可编辑字段及其表单名和显示名（不含部门/公司，已单独处理）
        editable_fields = {
            'asset_name': ('asset_name', '资产名称'),
            'asset_category': ('asset_category', '资产分类'),
            'specification': ('specification', '规格型号'),
            'brand': ('brand', '品牌'),
            'supplier': ('supplier', '供应商'),
            'unit': ('unit', '单位'),
            'storage_location': ('storage_location', '存放位置'),
            'responsible_person': ('responsible_person', '责任人'),
            'asset_source': ('asset_source', '资产来源'),
            'status': ('status', '资产状态'),
            'remark': ('remark', '备注'),
        }

        # 逐字段对比（文本字段）
        for field_name, (form_key, display_name) in editable_fields.items():
            new_value = request.form.get(form_key, '').strip() or None
            old_value = getattr(asset, field_name)
            # 统一None和空字符串比较
            old_normalized = old_value if old_value else None
            new_normalized = new_value if new_value else None
            if old_normalized != new_normalized:
                changes.append({
                    'field': field_name,
                    'field_display': display_name,
                    'old': str(old_value) if old_value else '',
                    'new': str(new_value) if new_value else ''
                })
                setattr(asset, field_name, new_value)

        # 同步保存自定义供应商到供应商模块
        new_supplier = request.form.get('supplier', '').strip()
        if new_supplier:
            _ensure_supplier_exists(new_supplier, current_user.id, handler_user_id=current_user.id)

        # 同步保存自定义存放位置到存放位置模块
        new_storage_location = request.form.get('storage_location', '').strip()
        if new_storage_location:
            _ensure_storage_location_exists(new_storage_location, current_user.id, handler_user_id=current_user.id)

        # 处理物料基础资料关联
        supply_item_id_str = request.form.get('supply_item_id', '').strip()
        new_supply_item_id = int(supply_item_id_str) if supply_item_id_str else None
        # 验证选择的物料是否为启用状态
        if new_supply_item_id:
            from models.supply.supply_item import SupplyItem
            selected_item = SupplyItem.query.get(new_supply_item_id)
            if not selected_item or selected_item.status != '启用':
                flash('所选物料基础资料已停用，请重新选择', 'danger')
                return redirect(url_for('fixed_asset.edit_page', id=id))
        # 编辑时：始终确保有对应的物料记录，物品编号=资产编号
        if not new_supply_item_id and asset.asset_name:
            from models.supply.supply_item import SupplyItem
            # 资产编号作为物品编号传递到物料基础资料
            new_item = SupplyItem.create(
                name=asset.asset_name,
                category='固定资产',
                specification=asset.specification or None,
                brand=asset.brand or None,
                unit=asset.unit or None,
                status='启用',
                operator_user_id=current_user.id,
                item_number=asset.asset_number
            )
            new_supply_item_id = new_item.id
        # 比较并更新 supply_item_id 字段
        old_supply_item_id = asset.supply_item_id
        if old_supply_item_id != new_supply_item_id:
            old_supply_item_name = ''
            new_supply_item_name = ''
            from models.supply.supply_item import SupplyItem
            if old_supply_item_id:
                old_item = SupplyItem.query.get(old_supply_item_id)
                if old_item:
                    old_supply_item_name = old_item.name
            if new_supply_item_id:
                new_item = SupplyItem.query.get(new_supply_item_id)
                if new_item:
                    new_supply_item_name = new_item.name
            changes.append({
                'field': 'supply_item_id',
                'field_display': '关联物料',
                'old': old_supply_item_name,
                'new': new_supply_item_name
            })
            asset.supply_item_id = new_supply_item_id

        # FK字段：room_id
        room_id_str = request.form.get('room_id', '').strip()
        new_room_id = int(room_id_str) if room_id_str else None
        old_room_id = asset.room_id
        if old_room_id != new_room_id:
            old_room_display = asset.room_display or ''
            # 查找新房间显示名
            new_room_display = ''
            if new_room_id:
                from models.room.room import Room
                new_room = Room.query.get(new_room_id)
                if new_room:
                    new_room_display = f"{new_room.building}{new_room.room_number}"
            changes.append({
                'field': 'room_id',
                'field_display': '关联房间',
                'old': old_room_display,
                'new': new_room_display
            })
            asset.room_id = new_room_id

        # FK字段：responsible_user_id
        responsible_user_id_str = request.form.get('responsible_user_id', '').strip()
        new_responsible_user_id = int(responsible_user_id_str) if responsible_user_id_str else None
        old_responsible_user_id = asset.responsible_user_id
        if old_responsible_user_id != new_responsible_user_id:
            old_user_name = asset.responsible_user_name or ''
            # 查找新用户显示名
            new_user_name = ''
            if new_responsible_user_id:
                from models.user.user import User
                new_user = User.query.get(new_responsible_user_id)
                if new_user:
                    new_user_name = new_user.name
            changes.append({
                'field': 'responsible_user_id',
                'field_display': '责任人用户',
                'old': old_user_name,
                'new': new_user_name
            })
            asset.responsible_user_id = new_responsible_user_id
            # 同步更新responsible_person为用户姓名（冗余存储方便显示）
            if new_responsible_user_id and new_user_name:
                asset.responsible_person = new_user_name
            elif not new_responsible_user_id:
                # 用户清空了关联用户，responsible_person保留表单输入值（已在上面editable_fields处理）
                pass

        # 数量字段 - 通过库存明细调整
        quantity_str = request.form.get('quantity', '').strip()
        if quantity_str:
            try:
                new_quantity = int(quantity_str)
                old_quantity = asset.total_quantity
                if new_quantity != old_quantity:
                    if new_quantity <= 0:
                        flash('数量必须大于0', 'danger')
                        return redirect(url_for('fixed_asset.detail', id=id))
                    if new_quantity < old_quantity:
                        # 数量减少：从库存明细中扣减（优先从第一条扣减）
                        reduce_amount = old_quantity - new_quantity
                        stock_items = AssetStockItem.query.filter_by(asset_id=asset.id).order_by(AssetStockItem.id).all()
                        remaining = reduce_amount
                        for item in stock_items:
                            if remaining <= 0:
                                break
                            deduct = min(item.quantity, remaining)
                            item.quantity -= deduct
                            remaining -= deduct
                            if item.quantity == 0:
                                db.session.delete(item)
                        # 创建编辑调整出库记录
                        AssetStockRecord.create_record(
                            asset_id=asset.id,
                            record_type='出库',
                            record_subtype='编辑调整',
                            quantity=reduce_amount,
                            from_stock_item_id=stock_items[0].id if stock_items else None,
                            storage_location=stock_items[0].storage_location if stock_items else '',
                            room_id=stock_items[0].room_id if stock_items else None,
                            company=stock_items[0].company if stock_items else '',
                            department_using_id=stock_items[0].department_using_id if stock_items else None,
                            department_owning_id=stock_items[0].department_owning_id if stock_items else None,
                            operator_user_id=current_user.id,
                            operator_name=current_user.username if hasattr(current_user, 'username') else None,
                            remark=f'编辑调整：数量从{old_quantity}减少到{new_quantity}'
                        )
                    else:
                        # 数量增加：增加到第一条库存明细或创建新明细
                        add_amount = new_quantity - old_quantity
                        stock_items = AssetStockItem.query.filter_by(asset_id=asset.id).order_by(AssetStockItem.id).all()
                        if stock_items:
                            # 增加到第一条库存明细
                            stock_items[0].quantity += add_amount
                            AssetStockRecord.create_record(
                                asset_id=asset.id,
                                record_type='入库',
                                record_subtype='编辑调整',
                                quantity=add_amount,
                                to_stock_item_id=stock_items[0].id,
                                storage_location=stock_items[0].storage_location,
                                room_id=stock_items[0].room_id,
                                company=stock_items[0].company,
                                department_using_id=stock_items[0].department_using_id,
                                department_owning_id=stock_items[0].department_owning_id,
                                operator_user_id=current_user.id,
                                operator_name=current_user.username if hasattr(current_user, 'username') else None,
                                remark=f'编辑调整：数量从{old_quantity}增加到{new_quantity}'
                            )
                        else:
                            # 没有库存明细，创建新的
                            AssetStockItem.add_stock(
                                asset_id=asset.id,
                                quantity=add_amount,
                                storage_location=asset.storage_location or '',
                                room_id=asset.room_id,
                                company=asset.company or '',
                                department_using_id=asset.department_using_id,
                                department_owning_id=asset.department_owning_id,
                                responsible_person=asset.responsible_person or '',
                                responsible_user_id=asset.responsible_user_id
                            )
                            AssetStockRecord.create_record(
                                asset_id=asset.id,
                                record_type='入库',
                                record_subtype='编辑调整',
                                quantity=add_amount,
                                storage_location=asset.storage_location or '',
                                room_id=asset.room_id,
                                company=asset.company or '',
                                department_using_id=asset.department_using_id,
                                department_owning_id=asset.department_owning_id,
                                operator_user_id=current_user.id,
                                operator_name=current_user.username if hasattr(current_user, 'username') else None,
                                remark=f'编辑调整：数量从{old_quantity}增加到{new_quantity}'
                            )
                    # 同步主表quantity
                    asset.quantity = new_quantity
                    changes.append({
                        'field': 'quantity',
                        'field_display': '数量',
                        'old': str(old_quantity),
                        'new': str(new_quantity)
                    })
            except ValueError:
                flash('数量格式无效', 'danger')
                return redirect(url_for('fixed_asset.detail', id=id))

        # 日期字段
        date_fields = {
            'purchase_date': ('purchase_date', '购置日期'),
            'warranty_expiry': ('warranty_expiry', '质保到期日'),
        }
        for field_name, (form_key, display_name) in date_fields.items():
            date_str = request.form.get(form_key, '').strip()
            new_date = _parse_date(date_str)
            old_date = getattr(asset, field_name)
            if old_date != new_date:
                changes.append({
                    'field': field_name,
                    'field_display': display_name,
                    'old': old_date.isoformat() if old_date else '',
                    'new': new_date.isoformat() if new_date else ''
                })
                setattr(asset, field_name, new_date)

        # 金额字段
        decimal_fields = {
            'original_value': ('original_value', '原值'),
            'net_value': ('net_value', '净值'),
        }
        for field_name, (form_key, display_name) in decimal_fields.items():
            value_str = request.form.get(form_key, '').strip()
            new_value = _parse_decimal(value_str)
            old_value = getattr(asset, field_name)
            # 比较Decimal值
            old_decimal = old_value if old_value is not None else Decimal('0.00')
            new_decimal = new_value if new_value is not None else Decimal('0.00')
            if old_decimal != new_decimal:
                changes.append({
                    'field': field_name,
                    'field_display': display_name,
                    'old': str(old_value) if old_value else '',
                    'new': str(new_value) if new_value else ''
                })
                setattr(asset, field_name, new_value)

        # 如果没有变更
        if not changes:
            flash('没有检测到任何变更', 'info')
            return redirect(url_for('fixed_asset.detail', id=id))

        # 更新操作用户
        asset.operator_user_id = current_user.id
        db.session.commit()

        # 创建操作记录（变更字段数组）
        changed_field_names = '、'.join([c['field_display'] for c in changes])
        # 构建详细变更描述
        change_descriptions = []
        for c in changes:
            old_val = c.get('old', '')
            new_val = c.get('new', '')
            if old_val and new_val:
                change_descriptions.append(f"{c['field_display']}: {old_val}→{new_val}")
            elif new_val:
                change_descriptions.append(f"{c['field_display']}: (空)→{new_val}")
            elif old_val:
                change_descriptions.append(f"{c['field_display']}: {old_val}→(空)")
        detail_summary = '；'.join(change_descriptions)
        summary = f"编辑资产: {asset.asset_name}({asset.display_number})，修改了：{detail_summary}"

        AssetOperationRecord.create_record(
            asset_id=asset.id,
            operation_type='edit',
            operator_id=current_user.id,
            operator_name=current_user.username if hasattr(current_user, 'username') else None,
            change_detail=changes,
            summary=summary
        )

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_edit',
            action=f"编辑资产: {asset.asset_name}({asset.display_number})，修改了{changed_field_names}",
            result="成功"
        )

        flash(f'编辑资产成功: {asset.asset_name}({asset.display_number})', 'success')
        logging.info(f"编辑资产成功，资产ID: {id}, 修改字段: {changed_field_names}")
        return redirect(url_for('fixed_asset.detail', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_edit',
            action=f"编辑资产失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'编辑资产失败: {str(e)}', 'danger')
        logging.error(f"编辑资产失败，资产ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('fixed_asset.detail', id=id))


# ========== 路由：删除资产 ==========
@fixed_asset_bp.route('/operations/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('fixed_asset.delete')
def delete_asset(id):
    """删除资产 - 仅写OperationLog，不写AssetOperationRecord（会被级联删除）"""
    try:
        asset = FixedAsset.query.get_or_404(id)
        asset_name = asset.asset_name
        asset_number = asset.display_number

        # 显式删除磁盘照片文件
        AssetPhotoManager.delete_all_files(asset.id)

        # 删除资产（级联删除 operation_records 和 inventory_details）
        db.session.delete(asset)
        db.session.commit()

        # 仅写 OperationLog 记录摘要（AssetOperationRecord已被级联删除）
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_delete',
            action=f"删除资产: {asset_name}({asset_number})",
            result="成功"
        )

        flash(f'删除资产成功: {asset_name}({asset_number})', 'success')
        logging.info(f"删除资产成功，资产ID: {id}, 资产编号: {asset_number}")
        return redirect(url_for('fixed_asset.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_delete',
            action=f"删除资产失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'删除资产失败: {str(e)}', 'danger')
        logging.error(f"删除资产失败，资产ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('fixed_asset.index'))


# ========== 路由：批量删除 ==========
@fixed_asset_bp.route('/operations/batch-delete', methods=['POST'])
@login_required
@require_permission('fixed_asset.delete')
def batch_delete_assets():
    """批量删除资产"""
    try:
        id_strings = request.form.getlist('asset_ids[]')
        if not id_strings:
            flash('请选择要删除的资产', 'danger')
            return redirect(url_for('fixed_asset.index'))

        # 转换并验证ID
        asset_ids = []
        invalid_ids = []
        for id_str in id_strings:
            try:
                asset_id = int(id_str.strip())
                asset_ids.append(asset_id)
            except ValueError:
                invalid_ids.append(id_str)

        if invalid_ids:
            logging.warning(f"批量删除包含无效ID: {', '.join(invalid_ids)}")

        if not asset_ids:
            flash('未提供有效的资产ID', 'danger')
            return redirect(url_for('fixed_asset.index'))

        # 批量处理删除
        deleted_count = 0
        errors = []

        for asset_id in asset_ids:
            try:
                asset = FixedAsset.query.get(asset_id)
                if not asset:
                    errors.append(f"资产ID {asset_id} 不存在")
                    continue

                asset_name = asset.asset_name
                asset_number = asset.display_number

                # 显式删除磁盘照片文件
                AssetPhotoManager.delete_all_files(asset.id)

                # 删除资产（级联删除关联记录）
                db.session.delete(asset)
                deleted_count += 1
                logging.info(f"批量删除资产: {asset_name}({asset_number})")

            except Exception as e:
                errors.append(f"资产ID {asset_id} 删除失败: {str(e)}")
                logging.error(f"批量删除资产ID {asset_id} 异常: {str(e)}")

        # 统一提交事务
        db.session.commit()

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_delete',
            action=f"批量删除资产，共{len(asset_ids)}个，成功删除{deleted_count}个，失败{len(errors)}个",
            result="成功"
        )

        if errors:
            for error in errors:
                flash(error, 'warning')

        flash(f'批量删除完成，成功删除{deleted_count}个资产', 'success')
        logging.info(f"批量删除完成，总数: {len(asset_ids)}, 成功: {deleted_count}, 失败: {len(errors)}")
        return redirect(url_for('fixed_asset.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_delete',
            action=f"批量删除资产失败: {str(e)}",
            result="失败"
        )
        flash(f'批量删除失败: {str(e)}', 'danger')
        logging.error(f"批量删除资产失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('fixed_asset.index'))


# ========== 路由：资产转移 ==========
@fixed_asset_bp.route('/operations/transfer/<int:id>', methods=['POST'])
@login_required
@require_permission('fixed_asset.transfer')
def transfer_asset(id):
    """资产转移 - 更新位置/部门/责任人，记录转移前后信息"""
    try:
        asset = FixedAsset.query.get_or_404(id)

        # 检查资产状态
        if asset.status in ('已报废', '已出售'):
            flash('该资产已报废或已出售，无法进行转移操作', 'warning')
            return redirect(url_for('fixed_asset.detail', id=id))

        # 获取转移数量
        quantity_str = request.form.get('quantity', '').strip()
        try:
            quantity = int(quantity_str) if quantity_str else asset.quantity
        except (ValueError, TypeError):
            quantity = asset.quantity
        if quantity < 1 or quantity > asset.quantity:
            flash(f'转移数量无效，有效范围为1~{asset.quantity}', 'danger')
            return redirect(url_for('fixed_asset.detail', id=id))

        # 记录转移前信息（将在库存明细转移逻辑中从库存明细获取）
        original_quantity = asset.quantity

        # 获取转移后信息（字段名与模板fixed_asset_transfer.html一致）
        to_location = request.form.get('storage_location', '').strip() or None
        to_company = request.form.get('to_company', '').strip() or None
        to_department_using_name = request.form.get('to_department_using', '').strip()
        to_department_owning_name = request.form.get('to_department_owning', '').strip()

        # 通过部门名称+公司查找/创建部门获取ID
        to_dept_using_id = None
        to_dept_owning_id = None

        if to_department_using_name:
            _ensure_department_exists(to_department_using_name, to_company)
            dept_query = Department.query.filter_by(name=to_department_using_name)
            if to_company:
                dept_query = dept_query.filter(db.or_(Department.company == to_company, Department.company.is_(None)))
            else:
                dept_query = dept_query.filter(Department.company.is_(None))
            dept = dept_query.first()
            if dept:
                to_dept_using_id = dept.id
                if not to_company and dept.company:
                    to_company = dept.company

        if to_department_owning_name:
            _ensure_department_exists(to_department_owning_name, to_company)
            dept_query = Department.query.filter_by(name=to_department_owning_name)
            if to_company:
                dept_query = dept_query.filter(db.or_(Department.company == to_company, Department.company.is_(None)))
            else:
                dept_query = dept_query.filter(Department.company.is_(None))
            dept = dept_query.first()
            if dept:
                to_dept_owning_id = dept.id
                if not to_company and dept.company:
                    to_company = dept.company

        # 获取转移后部门名称（用于变更记录）
        to_department_using = to_department_using_name or ''
        to_department_owning = to_department_owning_name or ''

        to_responsible_person = request.form.get('responsible_person', '').strip() or None
        # FK字段：room_id和responsible_user_id
        to_room_id_str = request.form.get('to_room_id', '').strip()
        to_room_id = int(to_room_id_str) if to_room_id_str else None
        to_responsible_user_id_str = request.form.get('to_responsible_user_id', '').strip()
        to_responsible_user_id = int(to_responsible_user_id_str) if to_responsible_user_id_str else None

        # 如果选择了关联用户，将to_responsible_person也设为用户姓名（冗余存储方便显示）
        if to_responsible_user_id:
            from models.user.user import User
            to_user = User.query.get(to_responsible_user_id)
            if to_user:
                to_responsible_person = to_user.name
        reason = request.form.get('reason', '').strip() or None

        # 转移日期
        transfer_date_str = request.form.get('transfer_date', '').strip()
        transfer_date = _parse_date(transfer_date_str)
        if not transfer_date:
            transfer_date = date.today()

        # 同步保存自定义存放位置到存放位置模块
        if to_location:
            _ensure_storage_location_exists(to_location, current_user.id, handler_user_id=current_user.id)

        # ========== 库存明细转移逻辑 ==========
        from models.fixed_asset.asset_stock_item import AssetStockItem
        from models.fixed_asset.asset_stock_record import AssetStockRecord

        # 获取源库存明细ID（从前端传入，或默认取第一条）
        from_stock_item_id_str = request.form.get('from_stock_item_id', '').strip()
        from_stock_item_id = int(from_stock_item_id_str) if from_stock_item_id_str else None

        # 查找源库存明细
        from_stock_item = None
        if from_stock_item_id:
            from_stock_item = AssetStockItem.query.filter_by(id=from_stock_item_id, asset_id=asset.id).first()
        if not from_stock_item:
            # 默认取第一条库存明细
            from_stock_item = AssetStockItem.query.filter_by(asset_id=asset.id).first()

        # 记录源位置信息（用于变更记录）
        if from_stock_item:
            from_location = from_stock_item.storage_location or ''
            from_company = from_stock_item.company or ''
            from_department_using = from_stock_item.department_using or ''
            from_department_owning = from_stock_item.department_owning or ''
            from_responsible_person = from_stock_item.responsible_person or ''
            from_room_display = from_stock_item.room_display or ''
            from_responsible_user_name = from_stock_item.responsible_user_name or ''
            from_stock_item_id_actual = from_stock_item.id
        else:
            # 无库存明细时，从主表获取
            from_location = asset.storage_location or ''
            from_company = asset.company or ''
            from_department_using = asset.department_using or ''
            from_department_owning = asset.department_owning or ''
            from_responsible_person = asset.responsible_person or ''
            from_room_display = asset.room_display or ''
            from_responsible_user_name = asset.responsible_user_name or ''
            from_stock_item_id_actual = None

        # 减少源库存明细数量
        if from_stock_item:
            if from_stock_item.quantity < quantity:
                flash(f'源位置库存不足，当前库存: {from_stock_item.quantity}', 'danger')
                return redirect(url_for('fixed_asset.detail', id=id))
            from_stock_item.quantity -= quantity
            from_stock_item.operator_user_id = current_user.id
            from_stock_item.updated_at = datetime.now()
            # 如果数量为0，删除该条记录
            if from_stock_item.quantity <= 0:
                db.session.delete(from_stock_item)

        # 增加目标库存明细数量
        to_stock_item = AssetStockItem.add_stock(
            asset_id=asset.id,
            quantity=quantity,
            storage_location=to_location,
            room_id=to_room_id,
            company=to_company,
            department_using_id=to_dept_using_id,
            department_owning_id=to_dept_owning_id,
            responsible_person=to_responsible_person,
            responsible_user_id=to_responsible_user_id,
            operator_user_id=current_user.id
        )

        # 创建库存变动记录
        AssetStockRecord.create_record(
            asset_id=asset.id,
            record_type='转移',
            record_subtype='转移调拨',
            quantity=quantity,
            from_stock_item_id=from_stock_item_id_actual,
            to_stock_item_id=to_stock_item.id if to_stock_item else None,
            storage_location=from_location or None,
            room_id=from_stock_item.room_id if from_stock_item else asset.room_id,
            company=from_company or None,
            department_using_id=from_stock_item.department_using_id if from_stock_item else asset.department_using_id,
            department_owning_id=from_stock_item.department_owning_id if from_stock_item else asset.department_owning_id,
            to_storage_location=to_location,
            to_room_id=to_room_id,
            to_company=to_company,
            to_department_using_id=to_dept_using_id,
            to_department_owning_id=to_dept_owning_id,
            operator_user_id=current_user.id,
            operator_name=current_user.username if hasattr(current_user, 'username') else None,
            remark=reason or '资产转移'
        )

        # 更新资产主表字段（兼容旧逻辑，取第一条库存明细或目标位置）
        asset.storage_location = to_location
        asset.company = to_company
        asset.department_using_id = to_dept_using_id
        asset.department_owning_id = to_dept_owning_id
        asset.responsible_person = to_responsible_person
        asset.room_id = to_room_id
        asset.responsible_user_id = to_responsible_user_id
        asset.transfer_date = transfer_date
        asset.operator_user_id = current_user.id
        # 主表quantity从库存明细汇总（转移不改变总数量）
        asset.quantity = sum(item.quantity for item in asset.stock_items)

        # 查找转移后的显示名（用于变更记录）
        to_room_display = ''
        if to_room_id:
            from models.room.room import Room
            new_room = Room.query.get(to_room_id)
            if new_room:
                to_room_display = f"{new_room.building}{new_room.room_number}"
        to_responsible_user_display = ''
        if to_responsible_user_id:
            from models.user.user import User
            new_user = User.query.get(to_responsible_user_id)
            if new_user:
                to_responsible_user_display = new_user.name

        db.session.commit()

        # 创建操作记录
        change_detail = {
            'asset_number': asset.asset_number or asset.display_number,
            'asset_name': asset.asset_name,
            'asset_category': asset.asset_category,
            'specification': asset.specification,
            'brand': asset.brand,
            'from_location': from_location,
            'to_location': to_location or '',
            'from_company': from_company,
            'to_company': to_company or '',
            'from_department_using': from_department_using,
            'to_department_using': to_department_using or '',
            'from_department_owning': from_department_owning,
            'to_department_owning': to_department_owning or '',
            'from_responsible_person': from_responsible_person,
            'to_responsible_person': to_responsible_person or '',
            'from_room_display': from_room_display,
            'to_room_display': to_room_display,
            'from_responsible_user_name': from_responsible_user_name,
            'to_responsible_user_name': to_responsible_user_display,
            'reason': reason or '',
            'transfer_date': transfer_date.isoformat(),
            'quantity': quantity,
            'original_quantity': original_quantity,
            'remaining_quantity': asset.quantity
        }
        # 构建详细转移摘要
        transfer_parts = [f"资产转移: {asset.asset_name}({asset.display_number})"]
        transfer_parts.append(f"转移数量: {quantity}")
        if from_location != (to_location or ''):
            transfer_parts.append(f"存放位置: {from_location or '无'}→{to_location or '无'}")
        if from_company != (to_company or ''):
            transfer_parts.append(f"所属公司: {from_company or '无'}→{to_company or '无'}")
        if from_department_using != (to_department_using or ''):
            transfer_parts.append(f"使用部门: {from_department_using or '无'}→{to_department_using or '无'}")
        if from_department_owning != (to_department_owning or ''):
            transfer_parts.append(f"归属部门: {from_department_owning or '无'}→{to_department_owning or '无'}")
        if from_responsible_person != (to_responsible_person or ''):
            transfer_parts.append(f"责任人: {from_responsible_person or '无'}→{to_responsible_person or '无'}")
        if from_room_display != (to_room_display or ''):
            transfer_parts.append(f"关联房间: {from_room_display or '无'}→{to_room_display or '无'}")
        transfer_parts.append(f"转移日期: {transfer_date.isoformat()}")
        if reason:
            transfer_parts.append(f"转移原因: {reason}")
        summary = "，".join(transfer_parts)

        AssetOperationRecord.create_record(
            asset_id=asset.id,
            operation_type='transfer',
            operator_id=current_user.id,
            operator_name=current_user.username if hasattr(current_user, 'username') else None,
            change_detail=change_detail,
            summary=summary
        )

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_transfer',
            action=summary,
            result="成功"
        )

        flash(f'资产转移成功: {asset.asset_name}({asset.display_number})', 'success')
        logging.info(f"资产转移成功，资产ID: {id}, {summary}")
        return redirect(url_for('fixed_asset.detail', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_transfer',
            action=f"资产转移失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'资产转移失败: {str(e)}', 'danger')
        logging.error(f"资产转移失败，资产ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('fixed_asset.detail', id=id))


# ========== 路由：创建盘点单 ==========
@fixed_asset_bp.route('/operations/inventory/create', methods=['POST'])
@login_required
@require_permission('fixed_asset.inventory')
def create_inventory():
    """创建盘点单 - 生成盘点单号，获取所有在用/闲置状态资产的库存明细创建盘点明细"""
    from models.fixed_asset.asset_stock_item import AssetStockItem
    try:
        title = request.form.get('title', '').strip()
        inventory_date_str = request.form.get('inventory_date', '').strip()
        remark = request.form.get('remark', '').strip()

        # 必填字段校验
        if not title:
            flash('盘点标题不能为空', 'danger')
            return redirect(url_for('fixed_asset.inventory'))

        inventory_date = _parse_date(inventory_date_str)
        if not inventory_date:
            inventory_date = date.today()

        # 生成盘点单号
        inventory_number = _generate_inventory_number()

        # 获取所有在用/闲置状态资产的库存明细（按位置维度）
        stock_items = AssetStockItem.query.join(
            FixedAsset, AssetStockItem.asset_id == FixedAsset.id
        ).filter(
            FixedAsset.status.in_(['在用', '闲置']),
            AssetStockItem.quantity > 0
        ).all()

        # 创建盘点主表
        inventory = AssetInventory(
            inventory_number=inventory_number,
            title=title,
            inventory_date=inventory_date,
            status='进行中',
            total_count=len(stock_items),
            checked_count=0,
            normal_count=0,
            abnormal_count=0,
            remark=remark or None,
            operator_user_id=current_user.id
        )
        db.session.add(inventory)
        db.session.flush()  # 获取inventory.id

        # 创建盘点明细（按库存明细维度，每个位置一条）
        for si in stock_items:
            detail = AssetInventoryDetail(
                inventory_id=inventory.id,
                asset_id=si.asset_id,
                stock_item_id=si.id,
                inventory_result='未盘点',
                inventory_remark=None,
                checked_by=None,
                checked_at=None,
                # 快照位置信息
                storage_location=si.storage_location,
                room_id=si.room_id,
                company=si.company,
                department_using_id=si.department_using_id,
                department_owning_id=si.department_owning_id,
                responsible_person=si.responsible_person,
            )
            db.session.add(detail)

        db.session.commit()

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='inventory_create',
            action=f"创建盘点单: {inventory_number}，标题: {title}，应盘{len(stock_items)}项",
            result="成功"
        )

        flash(f'创建盘点单成功: {inventory_number}，应盘{len(stock_items)}项资产', 'success')
        logging.info(f"创建盘点单成功，盘点单号: {inventory_number}, 应盘: {len(stock_items)}项")
        return redirect(url_for('fixed_asset.inventory'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='inventory_create',
            action=f"创建盘点单失败: {str(e)}",
            result="失败"
        )
        flash(f'创建盘点单失败: {str(e)}', 'danger')
        logging.error(f"创建盘点单失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('fixed_asset.inventory'))


# ========== 路由：执行盘点 ==========
@fixed_asset_bp.route('/operations/inventory/check', methods=['POST'])
@login_required
@require_permission('fixed_asset.inventory')
def check_inventory():
    """执行盘点 - 逐条确认，更新盘点明细和主表统计"""
    try:
        inventory_id = request.form.get('inventory_id', type=int)
        detail_id = request.form.get('detail_id', type=int)
        inventory_result = request.form.get('inventory_result', '').strip()
        inventory_remark = request.form.get('inventory_remark', '').strip()
        actual_quantity_str = request.form.get('actual_quantity', '').strip()

        # 参数校验
        if not inventory_id or not detail_id:
            return jsonify({'success': False, 'message': '缺少必要参数'}), 400

        if inventory_result not in ('正常', '异常'):
            return jsonify({'success': False, 'message': '盘点结果必须为"正常"或"异常"'}), 400

        # 获取盘点明细记录（按detail_id查找）
        detail = AssetInventoryDetail.query.filter_by(
            id=detail_id,
            inventory_id=inventory_id
        ).first()

        if not detail:
            return jsonify({'success': False, 'message': '未找到对应的盘点明细记录'}), 404

        # 获取资产信息
        asset = FixedAsset.query.get(detail.asset_id)
        if not asset:
            return jsonify({'success': False, 'message': '未找到对应的资产'}), 404

        # 获取盘点主表
        inventory = AssetInventory.query.get(inventory_id)
        if not inventory:
            return jsonify({'success': False, 'message': '未找到对应的盘点单'}), 404

        # 检查盘点状态
        if inventory.status != '进行中':
            return jsonify({'success': False, 'message': '该盘点单已结束，无法继续盘点'}), 400

        # 记录原状态
        old_result = detail.inventory_result

        # 更新盘点明细
        detail.inventory_result = inventory_result
        detail.inventory_remark = inventory_remark or None
        # 更新实盘数量
        if actual_quantity_str:
            try:
                detail.actual_quantity = int(actual_quantity_str)
            except ValueError:
                detail.actual_quantity = None
        else:
            detail.actual_quantity = None
        detail.checked_by = current_user.username if hasattr(current_user, 'username') else str(current_user.id)
        detail.checked_at = datetime.now()

        # 更新盘点主表统计
        # 如果之前未盘点，增加已盘数
        if old_result == '未盘点':
            inventory.checked_count = (inventory.checked_count or 0) + 1

        # 更新正常/异常计数
        if inventory_result == '正常':
            inventory.normal_count = (inventory.normal_count or 0) + 1
            # 如果之前是异常，减少异常计数
            if old_result == '异常':
                inventory.abnormal_count = max(0, (inventory.abnormal_count or 0) - 1)
        elif inventory_result == '异常':
            inventory.abnormal_count = (inventory.abnormal_count or 0) + 1
            # 如果之前是正常，减少正常计数
            if old_result == '正常':
                inventory.normal_count = max(0, (inventory.normal_count or 0) - 1)

        db.session.commit()

        # 获取库存明细的账面数量（用于记录）
        book_qty = detail.stock_item.quantity if detail.stock_item else asset.quantity
        location_info = detail.storage_location or (detail.stock_item.storage_location if detail.stock_item else None) or ''

        # 创建盘点操作记录
        AssetOperationRecord.create_record(
            asset_id=asset.id,
            operation_type='inventory',
            operator_id=current_user.id,
            operator_name=current_user.username if hasattr(current_user, 'username') else None,
            change_detail={
                'inventory_id': inventory_id,
                'inventory_number': inventory.inventory_number,
                'asset_number': asset.asset_number or asset.display_number,
                'asset_name': asset.asset_name,
                'inventory_result': inventory_result,
                'inventory_remark': inventory_remark or '',
                'actual_quantity': int(actual_quantity_str) if actual_quantity_str else None,
                'book_quantity': book_qty,
                'storage_location': location_info,
                'checked_by': current_user.username if hasattr(current_user, 'username') else str(current_user.id),
            },
            summary=f"资产盘点确认: {asset.asset_name}({asset.display_number})，结果: {inventory_result}，盘点单: {inventory.inventory_number}{f'，位置: {location_info}' if location_info else ''}{f'，实盘数量: {actual_quantity_str}' if actual_quantity_str else ''}{f'，备注: {inventory_remark}' if inventory_remark else ''}"
        )

        result_text = '正常' if inventory_result == '正常' else '异常'
        logging.info(f"资产盘点成功，盘点单: {inventory.inventory_number}, 资产: {asset.asset_name}, 结果: {inventory_result}")

        return jsonify({
            'success': True,
            'message': f'盘点确认成功: {asset.asset_name} - {result_text}',
            'checked_count': inventory.checked_count,
            'normal_count': inventory.normal_count,
            'abnormal_count': inventory.abnormal_count
        })

    except Exception as e:
        db.session.rollback()
        logging.error(f"执行盘点失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({'success': False, 'message': f'盘点确认失败: {str(e)}'}), 500


# ========== 路由：完成盘点 ==========
@fixed_asset_bp.route('/operations/inventory/complete/<int:id>', methods=['POST'])
@login_required
@require_permission('fixed_asset.inventory')
def complete_inventory(id):
    """完成盘点 - 更新盘点状态为已完成，按库存明细维度处理盘盈盘亏"""
    from models.fixed_asset.asset_stock_item import AssetStockItem
    from models.fixed_asset.asset_stock_record import AssetStockRecord
    try:
        inventory = AssetInventory.query.get_or_404(id)

        # 检查盘点状态
        if inventory.status != '进行中':
            flash('该盘点单不在进行中状态，无法完成', 'warning')
            return redirect(url_for('fixed_asset.inventory'))

        # 获取盘点明细
        details = AssetInventoryDetail.query.filter_by(inventory_id=id).all()

        # 先检查是否存在无效明细（资产已非在用），阻止审核
        invalid_items = []
        for detail in details:
            asset = FixedAsset.query.get(detail.asset_id) if detail.asset_id else None
            if not asset:
                continue
            if asset.status != '在用':
                invalid_items.append({
                    'asset_name': asset.asset_name,
                    'asset_number': asset.display_number if hasattr(asset, 'display_number') else asset.asset_number,
                    'status': asset.status,
                    'unit': asset.unit or '台'
                })

        if invalid_items:
            invalid_msgs = [f"{item['asset_name']}({item['asset_number']})：状态为{item['status']}" for item in invalid_items]
            flash(f'存在无效盘点明细（资产已非在用状态），请先删除后再审核：{"、".join(invalid_msgs)}', 'danger')
            return redirect(url_for('fixed_asset.inventory_detail', id=id))

        # 检查通过，更新盘点状态
        inventory.status = '已完成'

        # 处理盘点结果：按库存明细维度更新数量并生成变动记录
        surplus_count = 0  # 盘盈数
        shortage_count = 0  # 盘亏数

        for detail in details:
            if detail.inventory_result == '未盘点':
                continue

            asset = FixedAsset.query.get(detail.asset_id) if detail.asset_id else None
            if not asset:
                continue

            # 安全防护：跳过非在用资产（防止盘点处理覆盖已报废/已出售等终态资产的状态）
            if asset.status != '在用':
                continue

            # 获取关联的库存明细
            stock_item = AssetStockItem.query.get(detail.stock_item_id) if detail.stock_item_id else None
            book_qty = stock_item.quantity if stock_item else asset.quantity

            # 构建变动记录基础信息
            change_detail = {
                'inventory_id': id,
                'inventory_number': inventory.inventory_number,
                'asset_id': asset.id,
                'asset_number': asset.asset_number or asset.display_number,
                'asset_name': asset.asset_name,
                'asset_category': asset.asset_category,
                'specification': asset.specification,
                'brand': asset.brand,
                'result': detail.inventory_result,
                'remark': detail.inventory_remark or '',
                'storage_location': detail.storage_location or (stock_item.storage_location if stock_item else '') or '',
                'department_using': detail.department_using or '',
                'responsible_person': detail.responsible_person or '',
                'original_value': str(asset.original_value) if asset.original_value else '',
                'net_value': str(asset.net_value) if asset.net_value else '',
                'stock_item_id': detail.stock_item_id,
                'book_quantity': book_qty,
            }

            # 保存盘点前账面数量和状态（用于反审核回滚）
            detail.book_quantity = book_qty
            detail.book_status = asset.status

            # 检查是否有数量差异
            if detail.actual_quantity is not None and detail.actual_quantity != book_qty:
                old_quantity = book_qty
                diff = detail.actual_quantity - old_quantity

                change_detail['old_quantity'] = old_quantity
                change_detail['new_quantity'] = detail.actual_quantity
                change_detail['difference'] = diff

                if diff > 0:
                    # 盘盈：增加库存明细数量
                    surplus_count += 1
                    change_type = '盘盈'
                    if stock_item:
                        stock_item.quantity = detail.actual_quantity
                        stock_item.updated_at = datetime.now()
                        # 同步主表quantity
                        asset.quantity = sum(item.quantity for item in asset.stock_items)
                        # 创建库存变动记录
                        AssetStockRecord.create_record(
                            record_type='入库',
                            record_subtype='盘盈',
                            asset_id=asset.id,
                            quantity=diff,
                            to_stock_item_id=stock_item.id,
                            storage_location=stock_item.storage_location,
                            room_id=stock_item.room_id,
                            company=stock_item.company,
                            department_using_id=stock_item.department_using_id,
                            department_owning_id=stock_item.department_owning_id,
                            operator_user_id=current_user.id,
                            operator_name=current_user.username if hasattr(current_user, 'username') else None,
                            remark=f'盘点盘盈：账面{old_quantity}{asset.unit or "台"}，实盘{detail.actual_quantity}{asset.unit or "台"}，差异+{diff}{asset.unit or "台"}'
                        )
                    else:
                        asset.quantity = detail.actual_quantity
                    change_detail['quantity_change'] = f'盘盈：账面{old_quantity}{asset.unit or "台"}，实盘{detail.actual_quantity}{asset.unit or "台"}，差异+{diff}{asset.unit or "台"}'
                    summary = f"盘点盘盈：{asset.asset_name}，结果{detail.inventory_result}，账面{old_quantity}{asset.unit or '台'}，实盘{detail.actual_quantity}{asset.unit or '台'}，差异{diff}{asset.unit or '台'}，账面盘盈{diff}{asset.unit or '台'}，库存调整为{detail.actual_quantity}{asset.unit or '台'}"
                else:
                    # 盘亏：减少库存明细数量
                    shortage_count += 1
                    change_type = '盘亏'
                    if detail.actual_quantity == 0:
                        # 全部盘亏：设置资产为已报废状态
                        asset.status = '已报废'
                        asset.scrap_date = date.today()
                        asset.scrap_reason = '盘亏报废'
                        if stock_item:
                            stock_item.quantity = 0
                            stock_item.updated_at = datetime.now()
                            asset.quantity = sum(item.quantity for item in asset.stock_items)
                            AssetStockRecord.create_record(
                                record_type='出库',
                                record_subtype='报废出库',
                                asset_id=asset.id,
                                quantity=old_quantity,
                                from_stock_item_id=stock_item.id,
                                storage_location=stock_item.storage_location,
                                room_id=stock_item.room_id,
                                company=stock_item.company,
                                department_using_id=stock_item.department_using_id,
                                department_owning_id=stock_item.department_owning_id,
                                operator_user_id=current_user.id,
                                operator_name=current_user.username if hasattr(current_user, 'username') else None,
                                remark=f'盘点盘亏报废：账面{old_quantity}{asset.unit or "台"}，实盘0{asset.unit or "台"}'
                            )
                        else:
                            asset.quantity = 0
                        change_detail['quantity_change'] = f'盘亏：账面{old_quantity}{asset.unit or "台"}，实盘{detail.actual_quantity}{asset.unit or "台"}，差异{diff}{asset.unit or "台"}，已自动报废'
                        change_detail['auto_scrap'] = True
                        summary = f"盘点盘亏：{asset.asset_name}，账面{old_quantity}{asset.unit or '台'}，实盘{detail.actual_quantity}{asset.unit or '台'}，差异{diff}{asset.unit or '台'}，账面盘亏{diff}{asset.unit or '台'}，已自动报废"
                    else:
                        # 部分盘亏：减少库存明细数量
                        if stock_item:
                            stock_item.quantity = detail.actual_quantity
                            stock_item.updated_at = datetime.now()
                            asset.quantity = sum(item.quantity for item in asset.stock_items)
                            AssetStockRecord.create_record(
                                record_type='出库',
                                record_subtype='盘亏',
                                asset_id=asset.id,
                                quantity=abs(diff),
                                from_stock_item_id=stock_item.id,
                                storage_location=stock_item.storage_location,
                                room_id=stock_item.room_id,
                                company=stock_item.company,
                                department_using_id=stock_item.department_using_id,
                                department_owning_id=stock_item.department_owning_id,
                                operator_user_id=current_user.id,
                                operator_name=current_user.username if hasattr(current_user, 'username') else None,
                                remark=f'盘点盘亏：账面{old_quantity}{asset.unit or "台"}，实盘{detail.actual_quantity}{asset.unit or "台"}，差异{diff}{asset.unit or "台"}'
                            )
                        else:
                            asset.quantity = detail.actual_quantity
                        change_detail['quantity_change'] = f'盘亏：账面{old_quantity}{asset.unit or "台"}，实盘{detail.actual_quantity}{asset.unit or "台"}，差异{diff}{asset.unit or "台"}'
                        summary = f"盘点盘亏：{asset.asset_name}，结果{detail.inventory_result}，账面{old_quantity}{asset.unit or '台'}，实盘{detail.actual_quantity}{asset.unit or '台'}，差异{diff}{asset.unit or '台'}，账面盘亏{diff}{asset.unit or '台'}，库存调整为{detail.actual_quantity}{asset.unit or '台'}"
            else:
                summary = f"资产盘点：{asset.asset_name}，结果{detail.inventory_result}"

            # 注意：操作记录已在check_inventory逐条确认时创建，此处不再重复创建

        # 未盘点的资产自动标记为异常
        unchecked_details = AssetInventoryDetail.query.filter_by(inventory_id=id, inventory_result='未盘点').all()
        for detail in unchecked_details:
            detail.inventory_result = '异常'
            inventory.abnormal_count = (inventory.abnormal_count or 0) + 1

        db.session.commit()

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='inventory_complete',
            action=f"完成盘点单: {inventory.inventory_number}，已盘{inventory.checked_count}/{inventory.total_count}项，盘盈{surplus_count}项，盘亏{shortage_count}项",
            result="成功"
        )

        flash(f'盘点单 {inventory.inventory_number} 已完成，盘盈{surplus_count}项，盘亏{shortage_count}项', 'success')
        logging.info(f"完成盘点单，盘点单号: {inventory.inventory_number}")
        return redirect(url_for('fixed_asset.inventory'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='inventory_complete',
            action=f"完成盘点单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'完成盘点失败: {str(e)}', 'danger')
        logging.error(f"完成盘点失败，盘点ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('fixed_asset.inventory'))


# ========== 路由：反审核盘点单 ==========
@fixed_asset_bp.route('/operations/inventory/unapprove/<int:id>', methods=['POST'])
@login_required
@require_permission('fixed_asset.inventory_unapprove')
def unapprove_inventory(id):
    """反审核盘点单 - 检查开关→检查状态→调用模型方法→错误处理"""
    from models.system_config.system_config import SystemConfig
    unapprove_enabled = SystemConfig.get_config_value('asset_inventory_unapprove_enabled', True)
    if not unapprove_enabled:
        flash('固定资产盘点反审核功能已关闭，请联系管理员开启', 'warning')
        return redirect(url_for('fixed_asset.inventory_detail', id=id))

    inventory = AssetInventory.query.get_or_404(id)
    if inventory.status != '已完成':
        flash('仅已完成状态的盘点单可以反审核', 'warning')
        return redirect(url_for('fixed_asset.inventory_detail', id=id))

    try:
        result = AssetInventory.unapprove(id, current_user.id, current_user.username if hasattr(current_user, 'username') else None)

        if result is None:
            flash('反审核失败，盘点单状态异常', 'danger')
            return redirect(url_for('fixed_asset.inventory_detail', id=id))

        if isinstance(result, dict) and 'error' in result:
            # 库存不足错误
            error_msg = result['error']
            details = result.get('details', [])
            if details:
                detail_msgs = [f"{d['asset_name']}({d.get('asset_number', '')})：当前{d['current_quantity']}{d.get('unit', '台')}，需扣减{d['need_deduct']}{d.get('unit', '台')}" for d in details]
                error_msg += '：' + '、'.join(detail_msgs)
            flash(error_msg, 'danger')
            return redirect(url_for('fixed_asset.inventory_detail', id=id))

        # 反审核成功
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='inventory_unapprove',
            action=f"反审核盘点单: {inventory.inventory_number}",
            result="成功"
        )
        flash(f'盘点单 {inventory.inventory_number} 已反审核，资产数量已回滚，盘点单恢复为进行中状态', 'success')
        logging.info(f"反审核盘点单，盘点单号: {inventory.inventory_number}")
        return redirect(url_for('fixed_asset.inventory_detail', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='inventory_unapprove',
            action=f"反审核盘点单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'反审核盘点失败: {str(e)}', 'danger')
        logging.error(f"反审核盘点失败，盘点ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('fixed_asset.inventory_detail', id=id))


# ========== 路由：删除盘点单 ==========
@fixed_asset_bp.route('/operations/inventory/delete/<int:id>', methods=['POST'])
@login_required
@require_permission('fixed_asset.delete')
def delete_inventory(id):
    """删除盘点单 - 仅允许删除进行中状态的盘点单"""
    try:
        inventory = AssetInventory.query.get_or_404(id)

        # 检查盘点状态，仅允许删除进行中的盘点单
        if inventory.status != '进行中':
            flash('仅允许删除进行中状态的盘点单', 'warning')
            return redirect(url_for('fixed_asset.inventory'))

        inventory_number = inventory.inventory_number
        title = inventory.title

        # 删除盘点单（级联删除明细）
        db.session.delete(inventory)
        db.session.commit()

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='inventory_delete',
            action=f"删除盘点单: {inventory_number}，标题: {title}",
            result="成功"
        )

        flash(f'删除盘点单成功: {inventory_number}', 'success')
        logging.info(f"删除盘点单成功，盘点单号: {inventory_number}")
        return redirect(url_for('fixed_asset.inventory'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='inventory_delete',
            action=f"删除盘点单失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'删除盘点单失败: {str(e)}', 'danger')
        logging.error(f"删除盘点单失败，盘点ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('fixed_asset.inventory'))


# ========== 路由：删除盘点明细 ==========
@fixed_asset_bp.route('/operations/inventory/detail/delete/<int:detail_id>', methods=['POST'])
@login_required
@require_permission('fixed_asset.inventory')
def delete_inventory_detail(detail_id):
    """删除盘点明细 - 仅允许删除进行中状态盘点单的明细"""
    try:
        detail = AssetInventoryDetail.query.get_or_404(detail_id)
        inventory = AssetInventory.query.get_or_404(detail.inventory_id)

        # 仅允许删除进行中状态的盘点单明细
        if inventory.status != '进行中':
            flash('仅允许删除进行中状态盘点单的明细', 'warning')
            return redirect(url_for('fixed_asset.inventory_detail', id=inventory.id))

        asset_name = detail.asset.asset_name if detail.asset else '未知'
        asset_number = detail.asset.display_number if detail.asset and hasattr(detail.asset, 'display_number') else '未知'

        # 更新盘点单计数
        inventory.total_count = max(0, (inventory.total_count or 0) - 1)
        if detail.inventory_result != '未盘点':
            inventory.checked_count = max(0, (inventory.checked_count or 0) - 1)
        if detail.inventory_result == '正常':
            inventory.normal_count = max(0, (inventory.normal_count or 0) - 1)
        elif detail.inventory_result == '异常':
            inventory.abnormal_count = max(0, (inventory.abnormal_count or 0) - 1)

        db.session.delete(detail)
        db.session.commit()

        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='inventory_detail_delete',
            action=f"删除盘点明细: {asset_name}({asset_number})，盘点单号: {inventory.inventory_number}",
            result="成功"
        )
        flash(f'已删除盘点明细: {asset_name}({asset_number})', 'success')
        logging.info(f"删除盘点明细，资产: {asset_name}({asset_number})，盘点单号: {inventory.inventory_number}")
        return redirect(url_for('fixed_asset.inventory_detail', id=inventory.id))

    except Exception as e:
        db.session.rollback()
        flash(f'删除盘点明细失败: {str(e)}', 'danger')
        logging.error(f"删除盘点明细失败，detail_id: {detail_id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('fixed_asset.inventory'))


# ========== 路由：批量删除盘点明细 ==========
@fixed_asset_bp.route('/operations/inventory/detail/batch-delete', methods=['POST'])
@login_required
@require_permission('fixed_asset.inventory')
def batch_delete_inventory_details():
    """批量删除盘点明细 - 仅进行中状态可删除"""
    try:
        inventory_id = request.form.get('inventory_id', type=int)
        detail_ids = request.form.getlist('detail_ids', type=int)

        if not inventory_id:
            flash('缺少盘点单ID', 'danger')
            return redirect(url_for('fixed_asset.inventory'))

        if not detail_ids:
            flash('未选择要删除的明细', 'warning')
            return redirect(url_for('fixed_asset.inventory_detail', id=inventory_id))

        inventory = AssetInventory.query.get_or_404(inventory_id)

        # 检查盘点状态
        if inventory.status != '进行中':
            flash('仅进行中状态的盘点单可以删除明细', 'warning')
            return redirect(url_for('fixed_asset.inventory_detail', id=inventory_id))

        # 查询要删除的明细
        details = AssetInventoryDetail.query.filter(
            AssetInventoryDetail.id.in_(detail_ids),
            AssetInventoryDetail.inventory_id == inventory_id
        ).all()

        if not details:
            flash('未找到要删除的明细', 'warning')
            return redirect(url_for('fixed_asset.inventory_detail', id=inventory_id))

        # 更新盘点主表统计
        for detail in details:
            if detail.inventory_result != '未盘点':
                inventory.checked_count = max(0, (inventory.checked_count or 0) - 1)
            if detail.inventory_result == '正常':
                inventory.normal_count = max(0, (inventory.normal_count or 0) - 1)
            elif detail.inventory_result == '异常':
                inventory.abnormal_count = max(0, (inventory.abnormal_count or 0) - 1)
            inventory.total_count = max(0, (inventory.total_count or 0) - 1)

        # 批量删除
        for detail in details:
            db.session.delete(detail)

        db.session.commit()

        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='inventory_detail_batch_delete',
            action=f"批量删除盘点明细: 盘点单 {inventory.inventory_number}，删除{len(details)}条",
            result="成功"
        )

        flash(f'已批量删除{len(details)}条盘点明细', 'success')
        logging.info(f"批量删除盘点明细，盘点单: {inventory.inventory_number}, 删除{len(details)}条")
        return redirect(url_for('fixed_asset.inventory_detail', id=inventory_id))

    except Exception as e:
        db.session.rollback()
        flash(f'批量删除盘点明细失败: {str(e)}', 'danger')
        logging.error(f"批量删除盘点明细失败, inventory_id: {request.form.get('inventory_id')}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('fixed_asset.inventory'))


# ========== 路由：执行报废 ==========
@fixed_asset_bp.route('/operations/scrap/<int:id>', methods=['POST'])
@login_required
@require_permission('fixed_asset.scrap')
def scrap_asset(id):
    """执行报废 - 检查状态，更新为已报废，记录报废信息"""
    try:
        asset = FixedAsset.query.get_or_404(id)

        # 检查资产状态
        if asset.status in ('已报废', '已出售'):
            flash('该资产已报废或已出售，无法再次操作', 'warning')
            return redirect(url_for('fixed_asset.detail', id=id))

        # 获取报废数量
        quantity_str = request.form.get('quantity', '').strip()
        try:
            quantity = int(quantity_str) if quantity_str else asset.quantity
        except (ValueError, TypeError):
            quantity = asset.quantity
        if quantity < 1 or quantity > asset.quantity:
            flash(f'报废数量无效，有效范围为1~{asset.quantity}', 'danger')
            return redirect(url_for('fixed_asset.detail', id=id))

        # 获取报废信息
        scrap_date_str = request.form.get('scrap_date', '').strip()
        scrap_reason = request.form.get('scrap_reason', '').strip()

        # 必填校验
        if not scrap_reason:
            flash('报废原因不能为空', 'danger')
            return redirect(url_for('fixed_asset.detail', id=id))

        # 日期处理
        scrap_date = _parse_date(scrap_date_str)
        if not scrap_date:
            scrap_date = date.today()

        # 记录原状态
        old_status = asset.status
        original_quantity = asset.quantity

        # ========== 库存明细出库逻辑 ==========
        from models.fixed_asset.asset_stock_item import AssetStockItem
        from models.fixed_asset.asset_stock_record import AssetStockRecord

        # 获取出库位置（从前端传入，或默认取第一条库存明细）
        from_stock_item_id_str = request.form.get('from_stock_item_id', '').strip()
        from_stock_item_id = int(from_stock_item_id_str) if from_stock_item_id_str else None

        # 查找出库库存明细
        from_stock_item = None
        if from_stock_item_id:
            from_stock_item = AssetStockItem.query.filter_by(id=from_stock_item_id, asset_id=asset.id).first()
        if not from_stock_item:
            # 默认取第一条库存明细
            from_stock_item = AssetStockItem.query.filter_by(asset_id=asset.id).first()

        # 减少库存明细数量
        if from_stock_item:
            if from_stock_item.quantity < quantity:
                flash(f'出库位置库存不足，当前库存: {from_stock_item.quantity}', 'danger')
                return redirect(url_for('fixed_asset.detail', id=id))
            from_stock_item.quantity -= quantity
            from_stock_item.operator_user_id = current_user.id
            from_stock_item.updated_at = datetime.now()
            # 如果数量为0，删除该条记录
            if from_stock_item.quantity <= 0:
                db.session.delete(from_stock_item)
            # 创建库存变动记录
            AssetStockRecord.create_record(
                asset_id=asset.id,
                record_type='出库',
                record_subtype='报废出库',
                quantity=quantity,
                from_stock_item_id=from_stock_item.id,
                storage_location=from_stock_item.storage_location,
                room_id=from_stock_item.room_id,
                company=from_stock_item.company,
                department_using_id=from_stock_item.department_using_id,
                department_owning_id=from_stock_item.department_owning_id,
                operator_user_id=current_user.id,
                operator_name=current_user.username if hasattr(current_user, 'username') else None,
                remark=f'报废出库: {scrap_reason}'
            )
        else:
            # 无库存明细时，创建变动记录（仅记录，不影响明细）
            AssetStockRecord.create_record(
                asset_id=asset.id,
                record_type='出库',
                record_subtype='报废出库',
                quantity=quantity,
                storage_location=asset.storage_location,
                room_id=asset.room_id,
                company=asset.company,
                department_using_id=asset.department_using_id,
                department_owning_id=asset.department_owning_id,
                operator_user_id=current_user.id,
                operator_name=current_user.username if hasattr(current_user, 'username') else None,
                remark=f'报废出库: {scrap_reason}'
            )

        # 处理报废数量：部分报废时只减少数量，不改变状态；全部报废时更新状态
        # 主表quantity从库存明细汇总
        asset.quantity = sum(item.quantity for item in asset.stock_items)
        asset.operator_user_id = current_user.id
        if quantity >= original_quantity or asset.quantity <= 0:
            # 更新资产状态
            asset.status = '已报废'
            asset.scrap_date = scrap_date
            asset.scrap_reason = scrap_reason

        db.session.commit()

        # 创建操作记录
        change_detail = {
            'asset_number': asset.asset_number or asset.display_number,
            'asset_name': asset.asset_name,
            'asset_category': asset.asset_category,
            'specification': asset.specification,
            'brand': asset.brand,
            'scrap_date': scrap_date.isoformat(),
            'scrap_reason': scrap_reason,
            'old_status': old_status,
            'new_status': '已报废' if quantity >= original_quantity else old_status,
            'quantity': quantity,
            'original_quantity': original_quantity,
            'remaining_quantity': asset.quantity,
            'original_value': str(asset.original_value) if asset.original_value else '',
            'net_value': str(asset.net_value) if asset.net_value else '',
            'storage_location': asset.storage_location or '',
            'department_using': asset.department_using or '',
            'responsible_person': asset.responsible_person or '',
        }
        # 构建详细报废摘要
        scrap_parts = [f"资产报废: {asset.asset_name}({asset.display_number})"]
        scrap_parts.append(f"报废数量: {quantity}")
        if quantity < original_quantity:
            scrap_parts.append(f"部分报废，剩余数量: {asset.quantity}")
        scrap_parts.append(f"报废日期: {scrap_date.isoformat()}")
        scrap_parts.append(f"报废原因: {scrap_reason}")
        scrap_parts.append(f"原状态: {old_status}→{'已报废' if quantity >= original_quantity else old_status}")
        if asset.original_value:
            scrap_parts.append(f"原值: {asset.original_value}元")
        if asset.net_value:
            scrap_parts.append(f"净值: {asset.net_value}元")
        summary = "，".join(scrap_parts)

        AssetOperationRecord.create_record(
            asset_id=asset.id,
            operation_type='scrap',
            operator_id=current_user.id,
            operator_name=current_user.username if hasattr(current_user, 'username') else None,
            change_detail=change_detail,
            summary=summary
        )

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_scrap',
            action=summary,
            result="成功"
        )

        flash(f'资产报废成功: {asset.asset_name}({asset.display_number})', 'success')
        logging.info(f"资产报废成功，资产ID: {id}, 原因: {scrap_reason}")
        return redirect(url_for('fixed_asset.detail', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_scrap',
            action=f"资产报废失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'资产报废失败: {str(e)}', 'danger')
        logging.error(f"资产报废失败，资产ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('fixed_asset.detail', id=id))


# ========== 路由：执行出售 ==========
@fixed_asset_bp.route('/operations/sell/<int:id>', methods=['POST'])
@login_required
@require_permission('fixed_asset.sell')
def sell_asset(id):
    """执行出售 - 检查状态，更新为已出售，记录出售信息"""
    try:
        asset = FixedAsset.query.get_or_404(id)

        # 检查资产状态
        if asset.status in ('已报废', '已出售'):
            flash('该资产已报废或已出售，无法再次操作', 'warning')
            return redirect(url_for('fixed_asset.detail', id=id))

        # 获取出售数量
        quantity_str = request.form.get('quantity', '').strip()
        try:
            quantity = int(quantity_str) if quantity_str else asset.quantity
        except (ValueError, TypeError):
            quantity = asset.quantity
        if quantity < 1 or quantity > asset.quantity:
            flash(f'出售数量无效，有效范围为1~{asset.quantity}', 'danger')
            return redirect(url_for('fixed_asset.detail', id=id))

        # 获取出售信息
        sale_date_str = request.form.get('sale_date', '').strip()
        sale_price_str = request.form.get('sale_price', '').strip()
        sale_buyer = request.form.get('sale_buyer', '').strip()
        sale_remark = request.form.get('sale_remark', '').strip()

        # 日期处理
        sale_date = _parse_date(sale_date_str)
        if not sale_date:
            sale_date = date.today()

        # 金额处理
        sale_price = _parse_decimal(sale_price_str)

        # 记录原状态
        old_status = asset.status
        original_quantity = asset.quantity

        # ========== 库存明细出库逻辑 ==========
        from models.fixed_asset.asset_stock_item import AssetStockItem
        from models.fixed_asset.asset_stock_record import AssetStockRecord

        # 获取出库位置（从前端传入，或默认取第一条库存明细）
        from_stock_item_id_str = request.form.get('from_stock_item_id', '').strip()
        from_stock_item_id = int(from_stock_item_id_str) if from_stock_item_id_str else None

        # 查找出库库存明细
        from_stock_item = None
        if from_stock_item_id:
            from_stock_item = AssetStockItem.query.filter_by(id=from_stock_item_id, asset_id=asset.id).first()
        if not from_stock_item:
            # 默认取第一条库存明细
            from_stock_item = AssetStockItem.query.filter_by(asset_id=asset.id).first()

        # 减少库存明细数量
        if from_stock_item:
            if from_stock_item.quantity < quantity:
                flash(f'出库位置库存不足，当前库存: {from_stock_item.quantity}', 'danger')
                return redirect(url_for('fixed_asset.detail', id=id))
            from_stock_item.quantity -= quantity
            from_stock_item.operator_user_id = current_user.id
            from_stock_item.updated_at = datetime.now()
            # 如果数量为0，删除该条记录
            if from_stock_item.quantity <= 0:
                db.session.delete(from_stock_item)
            # 创建库存变动记录
            AssetStockRecord.create_record(
                asset_id=asset.id,
                record_type='出库',
                record_subtype='出售出库',
                quantity=quantity,
                from_stock_item_id=from_stock_item.id,
                storage_location=from_stock_item.storage_location,
                room_id=from_stock_item.room_id,
                company=from_stock_item.company,
                department_using_id=from_stock_item.department_using_id,
                department_owning_id=from_stock_item.department_owning_id,
                operator_user_id=current_user.id,
                operator_name=current_user.username if hasattr(current_user, 'username') else None,
                remark=f'出售出库: 买方{sale_buyer or "未知"}, 金额{sale_price or "0"}元'
            )
        else:
            # 无库存明细时，创建变动记录（仅记录，不影响明细）
            AssetStockRecord.create_record(
                asset_id=asset.id,
                record_type='出库',
                record_subtype='出售出库',
                quantity=quantity,
                storage_location=asset.storage_location,
                room_id=asset.room_id,
                company=asset.company,
                department_using_id=asset.department_using_id,
                department_owning_id=asset.department_owning_id,
                operator_user_id=current_user.id,
                operator_name=current_user.username if hasattr(current_user, 'username') else None,
                remark=f'出售出库: 买方{sale_buyer or "未知"}, 金额{sale_price or "0"}元'
            )

        # 处理出售数量：部分出售时只减少数量，不改变状态；全部出售时更新状态
        # 主表quantity从库存明细汇总
        asset.quantity = sum(item.quantity for item in asset.stock_items)
        asset.operator_user_id = current_user.id
        if quantity >= original_quantity or asset.quantity <= 0:
            # 更新资产状态
            asset.status = '已出售'
            asset.sale_date = sale_date
            asset.sale_price = sale_price
            asset.sale_buyer = sale_buyer or None
            asset.sale_remark = sale_remark or None

        db.session.commit()

        # 创建操作记录
        change_detail = {
            'asset_number': asset.asset_number or asset.display_number,
            'asset_name': asset.asset_name,
            'asset_category': asset.asset_category,
            'specification': asset.specification,
            'brand': asset.brand,
            'sale_date': sale_date.isoformat(),
            'sale_price': str(sale_price) if sale_price else '',
            'sale_buyer': sale_buyer or '',
            'sale_remark': sale_remark or '',
            'old_status': old_status,
            'new_status': '已出售' if quantity >= original_quantity else old_status,
            'quantity': quantity,
            'original_quantity': original_quantity,
            'remaining_quantity': asset.quantity,
            'original_value': str(asset.original_value) if asset.original_value else '',
            'net_value': str(asset.net_value) if asset.net_value else '',
            'storage_location': asset.storage_location or '',
            'department_using': asset.department_using or '',
            'responsible_person': asset.responsible_person or '',
        }
        # 构建详细出售摘要
        sell_parts = [f"资产出售: {asset.asset_name}({asset.display_number})"]
        sell_parts.append(f"出售数量: {quantity}")
        if quantity < original_quantity:
            sell_parts.append(f"部分出售，剩余数量: {asset.quantity}")
        sell_parts.append(f"出售日期: {sale_date.isoformat()}")
        sell_parts.append(f"出售金额: {sale_price or 0}元")
        if sale_buyer:
            sell_parts.append(f"买方: {sale_buyer}")
        sell_parts.append(f"原状态: {old_status}→{'已出售' if quantity >= original_quantity else old_status}")
        if asset.original_value:
            sell_parts.append(f"原值: {asset.original_value}元")
        if asset.net_value:
            sell_parts.append(f"净值: {asset.net_value}元")
        if sale_remark:
            sell_parts.append(f"出售备注: {sale_remark}")
        summary = "，".join(sell_parts)

        AssetOperationRecord.create_record(
            asset_id=asset.id,
            operation_type='sell',
            operator_id=current_user.id,
            operator_name=current_user.username if hasattr(current_user, 'username') else None,
            change_detail=change_detail,
            summary=summary
        )

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_sell',
            action=summary,
            result="成功"
        )

        flash(f'资产出售成功: {asset.asset_name}({asset.display_number})', 'success')
        logging.info(f"资产出售成功，资产ID: {id}, 金额: {sale_price}, 买方: {sale_buyer or ''}")
        return redirect(url_for('fixed_asset.detail', id=id))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_sell',
            action=f"资产出售失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'资产出售失败: {str(e)}', 'danger')
        logging.error(f"资产出售失败，资产ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('fixed_asset.detail', id=id))