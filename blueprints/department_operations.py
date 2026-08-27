from flask import render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from utils.db import db
from models.department import Department
from models.fixed_asset import FixedAsset
from utils.log import log_operation
from utils.auth import admin_required
import logging
import traceback
from datetime import datetime
from .department import department_bp


# ========== 路由：新增部门 ==========
@department_bp.route('/operations/add', methods=['POST'])
@login_required
@admin_required
def add_department():
    """新增部门"""
    try:
        name = request.form.get('name', '').strip()
        company = request.form.get('company', '').strip() or None
        description = request.form.get('description', '').strip() or None
        status = request.form.get('status', '正常').strip() or '正常'
        created_date_str = request.form.get('created_date', '')
        created_date = None
        if created_date_str:
            try:
                created_date = datetime.strptime(created_date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        # 必填字段校验
        if not name:
            flash('部门名称不能为空', 'danger')
            return redirect(url_for('department.add_page'))

        # 状态值校验
        if status not in ['正常', '停用']:
            status = '正常'

        # 检查名称是否重复（同公司下唯一）
        if Department.is_name_exists(name, company=company):
            if company:
                flash(f'公司"{company}"下已存在部门"{name}"', 'danger')
            else:
                flash(f'已存在部门"{name}"（未指定公司）', 'danger')
            return redirect(url_for('department.add_page'))
        department = Department.create(name=name, description=description, company=company, created_date=created_date, status=status)

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='department_add',
            action=f"新增部门: {name}" + (f"（所属公司: {company}）" if company else ""),
            result="成功"
        )

        flash(f'新增部门成功: {name}', 'success')
        logging.info(f"新增部门成功，部门ID: {department.id}, 名称: {name}")

        if request.form.get('action') == 'continue':
            return redirect(url_for('department.add_page'))
        return redirect(url_for('department.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='department_add',
            action=f"新增部门失败: {str(e)}",
            result="失败"
        )
        flash(f'新增部门失败: {str(e)}', 'danger')
        logging.error(f"新增部门失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('department.add_page'))


# ========== 路由：编辑部门 ==========
@department_bp.route('/operations/edit/<int:id>', methods=['POST'])
@login_required
@admin_required
def edit_department(id):
    """编辑部门 - 支持名称变更时级联更新User和FixedAsset"""
    try:
        department = Department.query.get_or_404(id)
        old_name = department.name
        old_company = department.company

        # 获取表单数据
        new_name = request.form.get('name', '').strip()
        new_company = request.form.get('company', '').strip() or None
        new_description = request.form.get('description', '').strip() or None
        new_status = request.form.get('status', '正常').strip() or '正常'

        # 状态值校验
        if new_status not in ['正常', '停用']:
            new_status = '正常'

        # 必填字段校验
        if not new_name:
            flash('部门名称不能为空', 'danger')
            return redirect(url_for('department.edit_page', id=id))

        # 检查名称是否重复（排除自身）
        if Department.is_name_exists(new_name, company=new_company, exclude_id=id):
            if new_company:
                flash(f'公司"{new_company}"下已存在部门"{new_name}"', 'danger')
            else:
                flash(f'已存在部门"{new_name}"（未指定公司）', 'danger')
            return redirect(url_for('department.edit_page', id=id))

        # 记录变更
        changes = []
        if old_name != new_name:
            changes.append(f"名称: {old_name} → {new_name}")
        if old_company != new_company:
            changes.append(f"公司: {old_company or '无'} → {new_company or '无'}")
        if department.description != new_description:
            changes.append("描述已更新")
        if department.status != new_status:
            changes.append(f"状态: {department.status} → {new_status}")

        # 如果名称变更，User通过department_id FK自动关联，无需级联更新
        # FixedAsset也通过department_using_id/department_owning_id FK自动关联

        # 如果公司变更，级联更新关联FixedAsset的company字段
        if old_company != new_company:
            # 更新FK引用的资产（使用部门或归属部门指向当前部门的资产）
            company_count = FixedAsset.query.filter(
                db.or_(
                    FixedAsset.department_using_id == department.id,
                    FixedAsset.department_owning_id == department.id
                )
            ).update({'company': new_company}, synchronize_session='fetch')
            if company_count > 0:
                changes.append(f"同步更新{company_count}个资产的公司")

        # 更新部门信息
        department.name = new_name
        department.company = new_company
        department.description = new_description
        department.status = new_status
        db.session.commit()

        # 记录操作日志
        change_summary = '，'.join(changes) if changes else '无变更'
        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='department_edit',
            action=f"编辑部门: {old_name} → {new_name}，{change_summary}",
            result="成功"
        )

        flash(f'编辑部门成功: {new_name}', 'success')
        logging.info(f"编辑部门成功，部门ID: {id}, 变更: {change_summary}")
        return redirect(url_for('department.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='department_edit',
            action=f"编辑部门失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'编辑部门失败: {str(e)}', 'danger')
        logging.error(f"编辑部门失败，部门ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('department.index'))


# ========== 路由：删除部门 ==========
@department_bp.route('/operations/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_department(id):
    """删除部门 - 检查使用情况，被引用时拒绝删除"""
    try:
        department = Department.query.get_or_404(id)
        dept_name = department.name

        # 检查使用情况
        usage = Department.check_usage(id)
        if usage['used']:
            details = usage['details']
            parts = []
            if details['user_count'] > 0:
                parts.append(f"{details['user_count']}个用户")
            if details['asset_using_count'] > 0:
                parts.append(f"{details['asset_using_count']}个使用资产")
            if details['asset_owning_count'] > 0:
                parts.append(f"{details['asset_owning_count']}个归属资产")
            usage_detail = '、'.join(parts)
            flash(f'部门"{dept_name}"正在被使用（{usage_detail}），无法删除', 'danger')
            return redirect(url_for('department.index'))

        # 删除部门
        db.session.delete(department)
        db.session.commit()

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='department_delete',
            action=f"删除部门: {dept_name}",
            result="成功"
        )

        flash(f'删除部门成功: {dept_name}', 'success')
        logging.info(f"删除部门成功，部门ID: {id}, 名称: {dept_name}")
        return redirect(url_for('department.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='department_delete',
            action=f"删除部门失败 [ID: {id}]: {str(e)}",
            result="失败"
        )
        flash(f'删除部门失败: {str(e)}', 'danger')
        logging.error(f"删除部门失败，部门ID: {id}, 错误: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('department.index'))


# ========== 路由：批量删除 ==========
@department_bp.route('/operations/batch-delete', methods=['POST'])
@login_required
@admin_required
def batch_delete_departments():
    """批量删除部门"""
    try:
        id_strings = request.form.getlist('department_ids[]')
        if not id_strings:
            flash('请选择要删除的部门', 'danger')
            return redirect(url_for('department.index'))

        # 转换并验证ID
        department_ids = []
        invalid_ids = []
        for id_str in id_strings:
            try:
                dept_id = int(id_str.strip())
                department_ids.append(dept_id)
            except ValueError:
                invalid_ids.append(id_str)

        if invalid_ids:
            invalid_ids_str = ', '.join(invalid_ids)
            logging.warning(f"批量删除包含无效ID: {invalid_ids_str}")

        if not department_ids:
            flash('未提供有效的部门ID', 'danger')
            return redirect(url_for('department.index'))

        # 批量处理删除
        deleted_count = 0
        errors = []

        for dept_id in department_ids:
            try:
                department = Department.query.get(dept_id)
                if not department:
                    errors.append(f"部门ID {dept_id} 不存在")
                    continue

                dept_name = department.name

                # 检查使用情况
                usage = Department.check_usage(dept_id)
                if usage['used']:
                    details = usage['details']
                    parts = []
                    if details['user_count'] > 0:
                        parts.append(f"{details['user_count']}个用户")
                    if details['asset_using_count'] > 0:
                        parts.append(f"{details['asset_using_count']}个使用资产")
                    if details['asset_owning_count'] > 0:
                        parts.append(f"{details['asset_owning_count']}个归属资产")
                    usage_detail = '、'.join(parts)
                    errors.append(f'部门"{dept_name}"正在被使用（{usage_detail}），无法删除')
                    continue

                # 删除部门
                db.session.delete(department)
                deleted_count += 1
                logging.info(f"批量删除部门: {dept_name}")

            except Exception as e:
                errors.append(f"部门ID {dept_id} 删除失败: {str(e)}")
                logging.error(f"批量删除部门ID {dept_id} 异常: {str(e)}")

        # 统一提交事务
        db.session.commit()

        # 记录操作日志
        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='department_delete',
            action=f"批量删除部门，共{len(department_ids)}个，成功删除{deleted_count}个，失败{len(errors)}个",
            result="成功"
        )

        if errors:
            for error in errors:
                flash(error, 'warning')

        flash(f'批量删除完成，成功删除{deleted_count}个部门', 'success')
        logging.info(f"批量删除完成，总数: {len(department_ids)}, 成功: {deleted_count}, 失败: {len(errors)}")
        return redirect(url_for('department.index'))

    except Exception as e:
        db.session.rollback()
        log_operation(
            user_id=current_user.id,
            module='department',
            operation_type='department_delete',
            action=f"批量删除部门失败: {str(e)}",
            result="失败"
        )
        flash(f'批量删除失败: {str(e)}', 'danger')
        logging.error(f"批量删除部门失败: {str(e)}\n{traceback.format_exc()}")
        return redirect(url_for('department.index'))


# ========== 路由：检查部门名称是否重复（API） ==========
@department_bp.route('/operations/check-name', methods=['POST'])
@login_required
@admin_required
def check_name():
    """AJAX检查部门名称是否重复"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        company = data.get('company', '').strip() or None
        exclude_id = data.get('exclude_id')

        if not name:
            return jsonify({'exists': False})

        exists = Department.is_name_exists(name, company=company, exclude_id=exclude_id)
        return jsonify({'exists': exists})

    except Exception as e:
        logging.error(f"检查部门名称失败: {str(e)}")
        return jsonify({'error': str(e)}), 500