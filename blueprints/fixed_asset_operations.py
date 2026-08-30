from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from utils.db import db
from models.fixed_asset import FixedAsset
from models.asset_operation_record import AssetOperationRecord
from models.asset_inventory import AssetInventory
from models.asset_inventory_detail import AssetInventoryDetail
from utils.log import log_operation
from utils.asset_photo import AssetPhotoManager
from utils.auth import require_permission
from models.system_config import SystemConfig
from models.department import Department
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


def _ensure_storage_location_exists(name, operator_user_id=None, usage_type='fixed_asset', handler_user_id=None):
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

        # 资产编号：为空则自动生成
        if not asset_number:
            asset_number = None  # create方法内部会自动生成

        # FK字段转换：room_id和responsible_user_id
        room_id = int(room_id_str) if room_id_str else None
        responsible_user_id = int(responsible_user_id_str) if responsible_user_id_str else None

        # 如果选择了关联用户，将responsible_person也设为用户姓名（冗余存储方便显示）
        if responsible_user_id:
            from models.user import User
            user = User.query.get(responsible_user_id)
            if user:
                responsible_person = user.name

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
            responsible_user_id=responsible_user_id
        )

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
            'department_using_id': asset.department_using_id,
            'department_owning_id': asset.department_owning_id,
            'responsible_person': asset.responsible_person,
            'room_id': asset.room_id,
            'room_display': asset.room_display,
            'responsible_user_id': asset.responsible_user_id,
            'responsible_user_name': asset.responsible_user_name,
            'asset_source': asset.asset_source,
        }

        AssetOperationRecord.create_record(
            asset_id=asset.id,
            operation_type='add',
            operator_id=current_user.id,
            operator_name=current_user.username if hasattr(current_user, 'username') else None,
            change_detail=change_detail,
            summary=f"新增资产: {asset.asset_name}"
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

        # FK字段：room_id
        room_id_str = request.form.get('room_id', '').strip()
        new_room_id = int(room_id_str) if room_id_str else None
        old_room_id = asset.room_id
        if old_room_id != new_room_id:
            old_room_display = asset.room_display or ''
            # 查找新房间显示名
            new_room_display = ''
            if new_room_id:
                from models.room import Room
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
                from models.user import User
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

        # 数量字段
        quantity_str = request.form.get('quantity', '').strip()
        if quantity_str:
            try:
                new_quantity = int(quantity_str)
                if new_quantity != asset.quantity:
                    if new_quantity <= 0:
                        flash('数量必须大于0', 'danger')
                        return redirect(url_for('fixed_asset.detail', id=id))
                    changes.append({
                        'field': 'quantity',
                        'field_display': '数量',
                        'old': str(asset.quantity),
                        'new': str(new_quantity)
                    })
                    asset.quantity = new_quantity
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
        AssetOperationRecord.create_record(
            asset_id=asset.id,
            operation_type='edit',
            operator_id=current_user.id,
            operator_name=current_user.username if hasattr(current_user, 'username') else None,
            change_detail=changes,
            summary=f"编辑资产: {asset.asset_name}，修改了{changed_field_names}"
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
@require_permission('fixed_asset.edit')
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

        # 记录转移前信息
        from_location = asset.storage_location or ''
        from_company = asset.company or ''
        from_department_using = asset.department_using or ''
        from_department_owning = asset.department_owning or ''
        from_responsible_person = asset.responsible_person or ''
        from_room_display = asset.room_display or ''
        from_responsible_user_name = asset.responsible_user_name or ''
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
            from models.user import User
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

        # 更新资产字段
        asset.storage_location = to_location
        asset.company = to_company
        asset.department_using_id = to_dept_using_id
        asset.department_owning_id = to_dept_owning_id
        asset.responsible_person = to_responsible_person
        asset.room_id = to_room_id
        asset.responsible_user_id = to_responsible_user_id
        asset.transfer_date = transfer_date
        asset.operator_user_id = current_user.id

        # 查找转移后的显示名（用于变更记录）
        to_room_display = ''
        if to_room_id:
            from models.room import Room
            new_room = Room.query.get(to_room_id)
            if new_room:
                to_room_display = f"{new_room.building}{new_room.room_number}"
        to_responsible_user_display = ''
        if to_responsible_user_id:
            from models.user import User
            new_user = User.query.get(to_responsible_user_id)
            if new_user:
                to_responsible_user_display = new_user.name

        # 处理转移数量：部分转移时只减少数量，不改变状态
        if quantity < original_quantity:
            asset.quantity = original_quantity - quantity

        db.session.commit()

        # 创建操作记录
        change_detail = {
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
        summary = f"资产转移: {asset.asset_name}，转移数量: {quantity}，从{from_location or '无'}转移到{to_location or '无'}，责任人: {from_responsible_person or '无'}→{to_responsible_person or '无'}，转移日期: {transfer_date.isoformat()}"

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
@require_permission('fixed_asset.create')
def create_inventory():
    """创建盘点单 - 生成盘点单号，获取所有在用/闲置状态资产创建盘点明细"""
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

        # 获取所有在用/闲置状态资产
        assets = FixedAsset.query.filter(
            FixedAsset.status.in_(['在用', '闲置'])
        ).all()

        # 创建盘点主表
        inventory = AssetInventory(
            inventory_number=inventory_number,
            title=title,
            inventory_date=inventory_date,
            status='进行中',
            total_count=len(assets),
            checked_count=0,
            normal_count=0,
            abnormal_count=0,
            remark=remark or None,
            operator_user_id=current_user.id
        )
        db.session.add(inventory)
        db.session.flush()  # 获取inventory.id

        # 创建盘点明细
        for asset in assets:
            detail = AssetInventoryDetail(
                inventory_id=inventory.id,
                asset_id=asset.id,
                inventory_result='未盘点',
                inventory_remark=None,
                checked_by=None,
                checked_at=None
            )
            db.session.add(detail)

        db.session.commit()

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='inventory_create',
            action=f"创建盘点单: {inventory_number}，标题: {title}，应盘{len(assets)}项",
            result="成功"
        )

        flash(f'创建盘点单成功: {inventory_number}，应盘{len(assets)}项资产', 'success')
        logging.info(f"创建盘点单成功，盘点单号: {inventory_number}, 应盘: {len(assets)}项")
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
@require_permission('fixed_asset.edit')
def check_inventory():
    """执行盘点 - 逐条确认，更新盘点明细和主表统计"""
    try:
        inventory_id = request.form.get('inventory_id', type=int)
        asset_id = request.form.get('asset_id', type=int)
        inventory_result = request.form.get('inventory_result', '').strip()
        inventory_remark = request.form.get('inventory_remark', '').strip()
        actual_quantity_str = request.form.get('actual_quantity', '').strip()

        # 参数校验
        if not inventory_id or not asset_id:
            return jsonify({'success': False, 'message': '缺少必要参数'}), 400

        if inventory_result not in ('正常', '异常'):
            return jsonify({'success': False, 'message': '盘点结果必须为"正常"或"异常"'}), 400

        # 获取盘点明细记录
        detail = AssetInventoryDetail.query.filter_by(
            inventory_id=inventory_id,
            asset_id=asset_id
        ).first()

        if not detail:
            return jsonify({'success': False, 'message': '未找到对应的盘点明细记录'}), 404

        # 获取资产信息
        asset = FixedAsset.query.get(asset_id)
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
@require_permission('fixed_asset.edit')
def complete_inventory(id):
    """完成盘点 - 更新盘点状态为已完成"""
    try:
        inventory = AssetInventory.query.get_or_404(id)

        # 检查盘点状态
        if inventory.status != '进行中':
            flash('该盘点单不在进行中状态，无法完成', 'warning')
            return redirect(url_for('fixed_asset.inventory'))

        # 更新盘点状态
        inventory.status = '已完成'

        # 处理盘点结果：更新资产数量并生成变动记录
        details = AssetInventoryDetail.query.filter_by(inventory_id=id).all()
        surplus_count = 0  # 盘盈数
        shortage_count = 0  # 盘亏数

        for detail in details:
            if detail.inventory_result == '未盘点':
                continue

            asset = FixedAsset.query.get(detail.asset_id) if detail.asset_id else None
            if not asset:
                continue

            # 构建变动记录基础信息
            change_detail = {
                'inventory_id': id,
                'inventory_number': inventory.inventory_number,
                'asset_id': asset.id,
                'asset_name': asset.asset_name,
                'result': detail.inventory_result,
                'remark': detail.inventory_remark or ''
            }

            # 检查是否有数量差异
            if detail.actual_quantity is not None and detail.actual_quantity != asset.quantity:
                old_quantity = asset.quantity
                diff = detail.actual_quantity - old_quantity

                if diff > 0:
                    surplus_count += 1
                    change_type = '盘盈'
                else:
                    shortage_count += 1
                    change_type = '盘亏'

                change_detail['old_quantity'] = old_quantity
                change_detail['new_quantity'] = detail.actual_quantity
                change_detail['difference'] = diff
                change_detail['quantity_change'] = f'{change_type}：账面{old_quantity}{asset.unit or "台"}，实盘{detail.actual_quantity}{asset.unit or "台"}，差异{"+" if diff > 0 else ""}{diff}{asset.unit or "台"}'

                summary = f"盘点{change_type}：{asset.asset_name}，结果{detail.inventory_result}，账面{old_quantity}{asset.unit or '台'}，实盘{detail.actual_quantity}{asset.unit or '台'}"

                # 更新资产数量
                asset.quantity = detail.actual_quantity
            else:
                summary = f"资产盘点：{asset.asset_name}，结果{detail.inventory_result}"

            # 生成一条变动记录
            AssetOperationRecord.create_record(
                asset_id=asset.id,
                operation_type='inventory',
                operator_id=current_user.id,
                operator_name=current_user.username if hasattr(current_user, 'username') else None,
                change_detail=change_detail,
                summary=summary
            )

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


# ========== 路由：执行报废 ==========
@fixed_asset_bp.route('/operations/scrap/<int:id>', methods=['POST'])
@login_required
@require_permission('fixed_asset.edit')
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

        # 处理报废数量：部分报废时只减少数量，不改变状态；全部报废时更新状态
        if quantity < original_quantity:
            asset.quantity = original_quantity - quantity
            asset.operator_user_id = current_user.id
        else:
            # 更新资产状态
            asset.status = '已报废'
            asset.scrap_date = scrap_date
            asset.scrap_reason = scrap_reason
            asset.operator_user_id = current_user.id

        db.session.commit()

        # 创建操作记录
        change_detail = {
            'scrap_date': scrap_date.isoformat(),
            'scrap_reason': scrap_reason,
            'old_status': old_status,
            'new_status': '已报废' if quantity >= original_quantity else old_status,
            'quantity': quantity,
            'remaining_quantity': asset.quantity
        }
        summary = f"资产报废: {asset.asset_name}，报废数量: {quantity}，原因: {scrap_reason}"

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
@require_permission('fixed_asset.edit')
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

        # 处理出售数量：部分出售时只减少数量，不改变状态；全部出售时更新状态
        if quantity < original_quantity:
            asset.quantity = original_quantity - quantity
            asset.operator_user_id = current_user.id
        else:
            # 更新资产状态
            asset.status = '已出售'
            asset.sale_date = sale_date
            asset.sale_price = sale_price
            asset.sale_buyer = sale_buyer or None
            asset.sale_remark = sale_remark or None
            asset.operator_user_id = current_user.id

        db.session.commit()

        # 创建操作记录
        change_detail = {
            'sale_date': sale_date.isoformat(),
            'sale_price': str(sale_price) if sale_price else '',
            'sale_buyer': sale_buyer or '',
            'sale_remark': sale_remark or '',
            'old_status': old_status,
            'new_status': '已出售' if quantity >= original_quantity else old_status,
            'quantity': quantity,
            'remaining_quantity': asset.quantity
        }
        price_display = f"{sale_price}元" if sale_price else "未填写"
        buyer_display = sale_buyer or "未填写"
        summary = f"资产出售: {asset.asset_name}，出售数量: {quantity}，金额: {price_display}，买方: {buyer_display}"

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
        logging.info(f"资产出售成功，资产ID: {id}, 金额: {price_display}, 买方: {buyer_display}")
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