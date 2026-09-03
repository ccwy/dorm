from flask import Blueprint, request, jsonify, send_file
import logging
from utils.db import db
from flask_login import login_required, current_user
from utils.log import log_operation
import traceback
import os
from utils.auth import require_permission
from models.system_config.system_config import SystemConfig
from models.department.department import Department
from models.fixed_asset.fixed_asset import FixedAsset
from models.fixed_asset.asset_operation_record import AssetOperationRecord
from utils.asset_photo import AssetPhotoManager
from config import Config
from models.room.room import Room
from models.user.user import User

fixed_asset_api_bp = Blueprint('fixed_asset_api', __name__, url_prefix='/api/fixed_assets')


# ========== 获取资产列表JSON（分页+筛选） ==========
@fixed_asset_api_bp.route('/list', methods=['GET'])
@login_required
@require_permission('fixed_asset.view')
def get_asset_list():
    """获取资产列表JSON，支持分页和多条件筛选"""
    try:
        # 获取筛选参数
        category = request.args.get('category', '').strip()
        status = request.args.get('status', '').strip()
        dept_using = request.args.get('dept_using', '').strip()
        dept_owning = request.args.get('dept_owning', '').strip()
        company = request.args.get('company', '').strip()
        keyword = request.args.get('keyword', '').strip()

        # 分页参数
        page = max(request.args.get('page', 1, type=int), 1)
        per_page = min(max(request.args.get('per_page', 20, type=int), 1), 100)

        # 构建查询
        query = FixedAsset.query.order_by(FixedAsset.id.desc())

        if category:
            query = query.filter(FixedAsset.asset_category == category)
        if status:
            query = query.filter(FixedAsset.status == status)
        if dept_using:
            # 按部门名称查找ID再筛选
            dept = Department.query.filter_by(name=dept_using).first()
            if dept:
                query = query.filter(FixedAsset.department_using_id == dept.id)
            else:
                query = query.filter(FixedAsset.department_using_id == -1)  # 无匹配
        if dept_owning:
            dept = Department.query.filter_by(name=dept_owning).first()
            if dept:
                query = query.filter(FixedAsset.department_owning_id == dept.id)
            else:
                query = query.filter(FixedAsset.department_owning_id == -1)  # 无匹配
        if company:
            query = query.filter(FixedAsset.company == company)
        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    FixedAsset.asset_number.ilike(search_filter),
                    FixedAsset.asset_name.ilike(search_filter),
                    FixedAsset.specification.ilike(search_filter)
                )
            )

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # 格式化资产数据
        asset_list = []
        for asset in pagination.items:
            asset_data = {
                "id": asset.id,
                "asset_number": asset.asset_number,
                "display_number": asset.display_number,
                "asset_name": asset.asset_name,
                "asset_category": asset.asset_category,
                "specification": asset.specification,
                "brand": asset.brand,
                "supplier": asset.supplier,
                "quantity": asset.quantity,
                "unit": asset.unit,
                "original_value": float(asset.original_value) if asset.original_value else 0.0,
                "net_value": float(asset.net_value) if asset.net_value else 0.0,
                "purchase_date": asset.purchase_date.isoformat() if asset.purchase_date else None,
                "warranty_expiry": asset.warranty_expiry.isoformat() if asset.warranty_expiry else None,
                "storage_location": asset.storage_location,
                "company": asset.company,
                "department_using": asset.department_using,
                "department_owning": asset.department_owning,
                "department_using_id": asset.department_using_id,
                "department_owning_id": asset.department_owning_id,
                "responsible_person": asset.responsible_person,
                "room_id": asset.room_id,
                "room_display": asset.room_display,
                "responsible_user_id": asset.responsible_user_id,
                "responsible_user_name": asset.responsible_user_name,
                "asset_source": asset.asset_source,
            "success": True,
            "data": asset_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages
            }
        }

        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_api',
            action=f"调用资产列表接口，返回{len(asset_list)}条数据",
            result="成功"
        )

        return jsonify(response)

    except Exception as e:
        error_detail = f"资产列表接口错误: {str(e)}\n堆栈: {traceback.format_exc()}"
        logging.error(error_detail)

        try:
            log_operation(
                user_id=getattr(current_user, 'id', "未知"),
                module='asset',
                operation_type='asset_api',
                action=f"调用资产列表接口失败: {str(e)}",
                result="失败"
            )
        except Exception as log_err:
            logging.error(f"记录日志失败: {str(log_err)}")

        return jsonify({
            "success": False,
            "message": "获取资产列表失败" if not Config.DEBUG else error_detail
        }), 500


# ========== 获取资产详情JSON ==========
@fixed_asset_api_bp.route('/<int:id>', methods=['GET'])
@login_required
@require_permission('fixed_asset.view')
def get_asset_detail(id):
    """获取资产详情JSON，包含照片列表和操作记录"""
    try:
        asset = FixedAsset.query.get(id)
        if not asset:
            return jsonify({"success": False, "message": f"未找到ID为{id}的资产"}), 404

        # 获取照片列表
        media_files = AssetPhotoManager.get_media_files(asset.id)
        photos = []
        for media in media_files:
            photos.append({
                "filename": media['filename'],
                "url": media['url'],
                "type": media.get('type', 'image'),
                "upload_time": media['upload_time'].isoformat() if hasattr(media['upload_time'], 'isoformat') else str(media['upload_time'])
            })

        # 获取操作记录（按时间倒序）
        operation_records = AssetOperationRecord.query.filter_by(
            asset_id=id
        ).order_by(AssetOperationRecord.operation_time.desc()).all()

        records = []
        for record in operation_records:
            records.append({
                "id": record.id,
                "operation_type": record.operation_type,
                "operator_name": record.operator_name,
                "operation_time": record.operation_time.strftime('%Y-%m-%d %H:%M') if record.operation_time else None,
                "summary": record.summary,
                "change_detail": record.change_detail
            })

        asset_data = {
            "id": asset.id,
            "asset_number": asset.asset_number,
            "display_number": asset.display_number,
            "asset_name": asset.asset_name,
            "asset_category": asset.asset_category,
            "specification": asset.specification,
            "brand": asset.brand,
            "supplier": asset.supplier,
            "quantity": asset.quantity,
            "unit": asset.unit,
            "original_value": float(asset.original_value) if asset.original_value else 0.0,
            "net_value": float(asset.net_value) if asset.net_value else 0.0,
            "purchase_date": asset.purchase_date.isoformat() if asset.purchase_date else None,
            "warranty_expiry": asset.warranty_expiry.isoformat() if asset.warranty_expiry else None,
            "storage_location": asset.storage_location,
            "company": asset.company,
            "department_using": asset.department_using,
            "department_owning": asset.department_owning,
            "department_using_id": asset.department_using_id,
            "department_owning_id": asset.department_owning_id,
            "responsible_person": asset.responsible_person,
            "room_id": asset.room_id,
            "room_display": asset.room_display,
            "responsible_user_id": asset.responsible_user_id,
            "responsible_user_name": asset.responsible_user_name,
            "asset_source": asset.asset_source,
            "scrap_reason": asset.scrap_reason,
            "sale_date": asset.sale_date.isoformat() if asset.sale_date else None,
            "sale_price": float(asset.sale_price) if asset.sale_price else None,
            "sale_buyer": asset.sale_buyer,
            "created_at": asset.created_at.strftime('%Y-%m-%d %H:%M') if asset.created_at else None,
            "updated_at": asset.updated_at.strftime('%Y-%m-%d %H:%M') if asset.updated_at else None,
            "photos": photos,
            "operation_records": records
        }

        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_api',
            action=f"查询资产详情 [ID: {id}, {asset.display_number}]",
            result="成功"
        )

        return jsonify({"success": True, "data": asset_data})

    except Exception as e:
        error_detail = f"资产详情接口错误（id={id}）: {str(e)}\n堆栈: {traceback.format_exc()}"
        logging.error(error_detail)

        try:
            log_operation(
                user_id=getattr(current_user, 'id', "未知"),
                module='asset',
                operation_type='asset_api',
                action=f"查询资产详情失败 [ID: {id}]: {str(e)}",
                result="失败"
            )
        except Exception as log_err:
            logging.error(f"记录日志失败: {str(log_err)}")

        return jsonify({
            "success": False,
            "message": "获取资产详情失败" if not Config.DEBUG else error_detail
        }), 500


# ========== 获取资产照片列表 ==========
@fixed_asset_api_bp.route('/<int:asset_id>/photos', methods=['GET'])
@login_required
@require_permission('fixed_asset.view')
def get_photos(asset_id):
    """获取资产照片列表"""
    try:
        asset = FixedAsset.query.get(asset_id)
        if not asset:
            return jsonify({"success": False, "message": f"未找到ID为{asset_id}的资产"}), 404

        files = AssetPhotoManager.get_media_files(asset_id)
        photo_list = []
        for f in files:
            photo_list.append({
                "filename": f['filename'],
                "url": f['url'],
                "type": f.get('type', 'image'),
                "upload_time": f['upload_time'].isoformat() if hasattr(f['upload_time'], 'isoformat') else str(f['upload_time'])
            })

        return jsonify({"success": True, "files": photo_list}), 200

    except Exception as e:
        logging.error(f"获取资产照片列表失败（asset_id={asset_id}）: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"success": False, "message": "获取照片列表失败"}), 500


# ========== 上传资产照片 ==========
@fixed_asset_api_bp.route('/<int:asset_id>/photos/upload', methods=['POST'])
@login_required
@require_permission('fixed_asset.edit')
def upload_photo(asset_id):
    """上传资产照片"""
    try:
        asset = FixedAsset.query.get(asset_id)
        if not asset:
            return jsonify({"success": False, "message": f"未找到ID为{asset_id}的资产"}), 404

        if 'photo' not in request.files:
            return jsonify({"success": False, "message": "未选择文件"}), 400

        file = request.files['photo']
        if file.filename == '':
            return jsonify({"success": False, "message": "未选择文件"}), 400

        filename = AssetPhotoManager.upload_file(asset_id, file)
        if filename:
            log_operation(
                user_id=current_user.id,
                module='asset',
                operation_type='upload_photo',
                action=f"上传资产照片: {asset.display_number}",
                result="成功"
            )
            return jsonify({"success": True, "filename": filename}), 200

        return jsonify({"success": False, "message": "上传失败"}), 500

    except Exception as e:
        logging.error(f"上传资产照片失败（asset_id={asset_id}）: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"success": False, "message": "上传照片失败"}), 500


# ========== 删除资产照片 ==========
@fixed_asset_api_bp.route('/<int:asset_id>/photos/<path:filename>/delete', methods=['POST'])
@login_required
@require_permission('fixed_asset.edit')
def delete_photo(asset_id, filename):
    """删除资产照片"""
    try:
        asset = FixedAsset.query.get(asset_id)
        if not asset:
            return jsonify({"success": False, "message": f"未找到ID为{asset_id}的资产"}), 404

        success = AssetPhotoManager.delete_file(asset_id, filename)
        if success:
            log_operation(
                user_id=current_user.id,
                module='asset',
                operation_type='delete_photo',
                action=f"删除资产照片: {filename}",
                result="成功"
            )
            return jsonify({"success": True}), 200

        return jsonify({"success": False, "message": "删除失败，文件不存在"}), 404

    except Exception as e:
        logging.error(f"删除资产照片失败（asset_id={asset_id}, filename={filename}）: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"success": False, "message": "删除照片失败"}), 500


# ========== 获取资产操作记录JSON ==========
@fixed_asset_api_bp.route('/<int:id>/operation-records', methods=['GET'])
@login_required
@require_permission('fixed_asset.view')
def get_operation_records(id):
    """获取资产操作记录JSON，按时间倒序"""
    try:
        asset = FixedAsset.query.get(id)
        if not asset:
            return jsonify({"success": False, "message": f"未找到ID为{id}的资产"}), 404

        records = AssetOperationRecord.query.filter_by(
            asset_id=id
        ).order_by(AssetOperationRecord.operation_time.desc()).all()

        record_list = []
        for record in records:
            record_list.append({
                "id": record.id,
                "operation_type": record.operation_type,
                "operator_name": record.operator_name,
                "operation_time": record.operation_time.strftime('%Y-%m-%d %H:%M') if record.operation_time else None,
                "summary": record.summary,
                "change_detail": record.change_detail
            })

        return jsonify({"success": True, "records": record_list}), 200

    except Exception as e:
        logging.error(f"获取资产操作记录失败（id={id}）: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"success": False, "message": "获取操作记录失败"}), 500


# ========== 获取资产分类列表 ==========
@fixed_asset_api_bp.route('/categories', methods=['GET'])
@login_required
@require_permission('fixed_asset.view')
def get_categories():
    """获取资产分类列表（从SystemConfig读取）"""
    try:
        categories = SystemConfig.get_config_value(
            'ASSET_CATEGORIES',
            ['办公设备', '家具', '交通工具', '电子设备', '机械设备', '其他']
        )
        return jsonify({"success": True, "data": categories}), 200

    except Exception as e:
        logging.error(f"获取资产分类列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"success": False, "message": "获取分类列表失败"}), 500


# ========== 获取部门列表 ==========
@fixed_asset_api_bp.route('/departments', methods=['GET'])
@login_required
@require_permission('fixed_asset.view')
def get_departments():
    """获取部门名称列表（支持按公司筛选，用于datalist）"""
    try:
        company = request.args.get('company', '').strip()
        departments = Department.get_active_by_company(company if company else None)
        dept_names = [d.name for d in departments]
        return jsonify({
            "success": True,
            "data": {
                "departments": dept_names
            }
        }), 200

    except Exception as e:
        logging.error(f"获取部门列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({"success": False, "message": "获取部门列表失败"}), 500


# ========== 获取资产统计概览数据 ==========
@fixed_asset_api_bp.route('/stats', methods=['GET'])
@login_required
@require_permission('fixed_asset.view')
def get_stats():
    """获取资产统计概览数据：总数、按分类统计、按状态统计、总原值、总净值"""
    try:
        # 总数
        total = FixedAsset.query.count()

        # 按分类统计
        by_category = {}
        category_rows = db.session.query(
            FixedAsset.asset_category,
            db.func.count(FixedAsset.id)
        ).group_by(FixedAsset.asset_category).all()
        for category, count in category_rows:
            by_category[category] = count

        # 按状态统计
        by_status = {}
        status_rows = db.session.query(
            FixedAsset.status,
            db.func.count(FixedAsset.id)
        ).group_by(FixedAsset.status).all()
        for status, count in status_rows:
            by_status[status] = count

        # 总原值和总净值
        value_result = db.session.query(
            db.func.sum(FixedAsset.original_value),
            db.func.sum(FixedAsset.net_value)
        ).first()
        total_value = float(value_result[0]) if value_result[0] else 0.0
        total_net_value = float(value_result[1]) if value_result[1] else 0.0

        response = {
            "success": True,
            "data": {
                "total": total,
                "by_category": by_category,
                "by_status": by_status,
                "total_value": total_value,
                "total_net_value": total_net_value
            }
        }

        log_operation(
            user_id=current_user.id,
            module='asset',
            operation_type='asset_api',
            action="调用资产统计接口",
            result="成功"
        )

        return jsonify(response)

    except Exception as e:
        error_detail = f"资产统计接口错误: {str(e)}\n堆栈: {traceback.format_exc()}"
        logging.error(error_detail)

        try:
            log_operation(
                user_id=getattr(current_user, 'id', "未知"),
                module='asset',
                operation_type='asset_api',
                action=f"调用资产统计接口失败: {str(e)}",
                result="失败"
            )
        except Exception as log_err:
            logging.error(f"记录日志失败: {str(log_err)}")

        return jsonify({
            "success": False,
            "message": "获取资产统计失败" if not Config.DEBUG else error_detail
        }), 500


# ========== 获取资产照片文件（静态文件服务） ==========
@fixed_asset_api_bp.route('/media/<asset_id>/<path:filename>', methods=['GET'])
@login_required
def get_asset_media(asset_id, filename):
    """获取资产的媒体文件（照片、视频、文档等）"""
    try:
        file_path = AssetPhotoManager.get_file_path(asset_id, filename)
        if file_path and os.path.exists(file_path):
            return send_file(file_path, as_attachment=False)
        return jsonify({'error': '文件不存在'}), 404
    except Exception as e:
        logging.error(f"获取资产媒体文件时发生错误: {str(e)}")
        return jsonify({'error': f"获取文件时发生错误: {str(e)}"}), 500


# ========== 搜索房间（模态框选择用） ==========
@fixed_asset_api_bp.route('/rooms/search', methods=['GET'])
@login_required
@require_permission('fixed_asset.view')
def search_rooms():
    """搜索房间（模态框选择用）"""
    try:
        query = request.args.get('query', '').strip()
        rooms = Room.query
        if query:
            rooms = rooms.filter(
                db.or_(
                    Room.building.ilike(f'%{query}%'),
                    Room.room_number.ilike(f'%{query}%')
                )
            )
        rooms = rooms.order_by(Room.building, Room.room_number).limit(50).all()
        return jsonify([{
            'id': r.id,
            'building': r.building,
            'room_number': r.room_number,
            'display': f"{r.building}{r.room_number}",
            'status': r.status
        } for r in rooms])
    except Exception as e:
        logging.error(f"搜索房间失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify([]), 500


# ========== 搜索用户（模态框选择责任人用） ==========
@fixed_asset_api_bp.route('/users/search', methods=['GET'])
@login_required
@require_permission('fixed_asset.view')
def search_users():
    """搜索用户（模态框选择责任人用）"""
    try:
        query = request.args.get('query', '').strip()
        users = User.query.filter(User.status == '在职')
        if query:
            users = users.filter(
                db.or_(
                    User.name.ilike(f'%{query}%'),
                    User.student_id.ilike(f'%{query}%'),
                    User.phone.ilike(f'%{query}%')
                )
            )
        users = users.order_by(User.name).limit(50).all()
        return jsonify([{
            'id': u.id,
            'name': u.name,
            'student_id': u.student_id or '',
            'department': u.department or '',
            'phone': u.phone or ''
        } for u in users])
    except Exception as e:
        logging.error(f"搜索用户失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify([]), 500