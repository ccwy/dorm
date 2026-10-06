from flask import Blueprint, request, jsonify, send_file, abort
import logging
import os
import mimetypes
from werkzeug.utils import secure_filename
from utils.db import db
from flask_login import login_required, current_user
from utils.log import log_operation
import traceback
from utils.auth import require_permission
from models.contract.contract import Contract
from models.contract.contract_operation_record import ContractOperationRecord
from models.supply.supplier import Supplier
from utils.media.contract_attachment import ContractAttachmentManager
from sqlalchemy.orm import aliased
from datetime import datetime

contract_api_bp = Blueprint('contract_api', __name__, url_prefix='/api/contracts')


# ========== 合同列表JSON（分页+筛选） ==========
@contract_api_bp.route('/', methods=['GET'])
@login_required
@require_permission('contract.view')
def get_contract_list():
    """获取合同列表JSON，支持分页和多条件筛选"""
    try:
        # 获取筛选参数
        keyword = request.args.get('keyword', '').strip()
        status = request.args.get('status', '').strip()
        contract_type = request.args.get('contract_type', '').strip()
        is_renewal = request.args.get('is_renewal', '').strip()

        # 分页参数
        page = max(request.args.get('page', 1, type=int), 1)
        per_page = min(max(request.args.get('per_page', 20, type=int), 1), 100)

        # 构建查询 - 使用aliased join Supplier匹配甲乙方名称
        PartyASupplier = aliased(Supplier)
        PartyBSupplier = aliased(Supplier)

        query = Contract.query.outerjoin(
            PartyASupplier, Contract.party_a_id == PartyASupplier.id
        ).outerjoin(
            PartyBSupplier, Contract.party_b_id == PartyBSupplier.id
        )

        # keyword搜索: 合同编号、合同名称，以及甲乙方名称
        if keyword:
            search_filter = f'%{keyword}%'
            query = query.filter(
                db.or_(
                    Contract.contract_number.ilike(search_filter),
                    Contract.contract_name.ilike(search_filter),
                    PartyASupplier.name.ilike(search_filter),
                    PartyBSupplier.name.ilike(search_filter)
                )
            )

        if status:
            query = query.filter(Contract.status == status)

        if contract_type:
            query = query.filter(Contract.contract_type == contract_type)

        if is_renewal:
            if is_renewal == 'true' or is_renewal == '1':
                query = query.filter(Contract.previous_contract_id.isnot(None))
            elif is_renewal == 'false' or is_renewal == '0':
                query = query.filter(Contract.previous_contract_id.is_(None))

        query = query.order_by(Contract.id.desc())

        # 分页查询
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # 格式化合同数据
        contract_list = []
        for c in pagination.items:
            contract_data = {
                "id": c.id,
                "contract_number": c.contract_number or '',
                "contract_name": c.contract_name or '',
                "party_a_name": c.party_a_name,
                "party_b_name": c.party_b_name,
                "contract_type": c.contract_type or '',
                "contract_category": c.contract_category or '',
                "contract_amount": float(c.contract_amount) if c.contract_amount else 0.00,
                "currency": c.currency or 'CNY',
                "tax_rate": float(c.tax_rate) if c.tax_rate else None,
                "status": c.status or '草稿',
                "display_status": c.display_status,
                "status_color": c.status_color,
                "signing_date": c.signing_date.strftime('%Y-%m-%d') if c.signing_date else None,
                "start_date": c.start_date.strftime('%Y-%m-%d') if c.start_date else None,
                "end_date": c.end_date.strftime('%Y-%m-%d') if c.end_date else None,
                "days_until_expiry": c.days_until_expiry,
                "is_renewal": c.is_renewal,
                "previous_contract_id": c.previous_contract_id,
                "handler_name": c.handler_name,
                "department_name": c.department_name,
                "storage_location_name": c.storage_location_name if c.storage_location else '',
                "created_at": c.created_at.strftime('%Y-%m-%d %H:%M') if c.created_at else None,
                "updated_at": c.updated_at.strftime('%Y-%m-%d %H:%M') if c.updated_at else None
            }
            contract_list.append(contract_data)

        response = {
            "success": True,
            "data": contract_list,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": pagination.total,
                "pages": pagination.pages
            }
        }

        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='api_query',
            action=f"API查询合同列表，页码:{page}，每页:{per_page}",
            result="成功"
        )

        return jsonify(response)

    except Exception as e:
        logging.error(f"API获取合同列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
        }), 500


# ========== 临时文件上传API（新增合同时使用，此时合同尚未创建） ==========

@contract_api_bp.route('/temp_media/upload', methods=['POST'])
@login_required
@require_permission('contract.add')
def upload_temp_media():
    """上传临时媒体文件（新增合同页面使用，此时合同尚未创建）"""
    try:
        temp_key = request.form.get('temp_key')
        
        if not temp_key:
            return jsonify({'success': False, 'message': '缺少临时标识参数'}), 400
        
        # 安全处理temp_key，防止路径遍历
        temp_key = secure_filename(temp_key)
        if not temp_key:
            return jsonify({'success': False, 'message': '无效的临时标识参数'}), 400
        
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': '没有文件被上传'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '没有选择文件'}), 400
        
        filename = ContractAttachmentManager.upload_temp_file(file, temp_key)
        if not filename:
            logging.warning(f"用户 {current_user.id} 上传临时合同附件失败: 文件格式不支持, temp_key={temp_key}")
            return jsonify({'success': False, 'message': '不支持的文件格式'}), 400
        
        file_url = ContractAttachmentManager.get_temp_media_url(filename, temp_key)
        file_type = ContractAttachmentManager.get_file_type(filename)
        
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='upload_attachment',
            action=f"上传临时合同附件: {filename} (temp_key={temp_key})",
            result="成功"
        )
        
        return jsonify({
            'success': True,
            'message': '上传成功',
            'filename': filename,
            'url': file_url,
            'type': file_type
        })
        
    except Exception as e:
        logging.error(f"上传临时合同附件失败: {str(e)}")
        return jsonify({'success': False, 'message': f'上传失败: {str(e)}'})


@contract_api_bp.route('/temp_media/files', methods=['GET'])
@login_required
@require_permission('contract.add')
def get_temp_media_files():
    """获取指定temp_key临时目录中的所有媒体文件"""
    try:
        temp_key = request.args.get('temp_key')
        
        if not temp_key:
            return jsonify({'success': False, 'message': '缺少临时标识参数'}), 400
        
        # 安全处理temp_key，防止路径遍历
        temp_key = secure_filename(temp_key)
        if not temp_key:
            return jsonify({'success': False, 'message': '无效的临时标识参数'}), 400
        
        media_files = ContractAttachmentManager.get_temp_media_files(temp_key)
        logging.debug(f"获取临时合同附件列表: temp_key={temp_key}, 文件数={len(media_files)}")
        
        result_files = []
        for file in media_files:
            result_files.append({
                'filename': file['filename'],
                'type': file['type'],
                'url': file['url'],
                'upload_time': file.get('upload_time').isoformat() if file.get('upload_time') else None
            })
        
        return jsonify({
            'success': True,
            'files': result_files
        })
        
    except Exception as e:
        logging.error(f"获取临时合同附件列表失败: {str(e)}")
        return jsonify({'success': False, 'message': f'获取失败: {str(e)}'})


@contract_api_bp.route('/temp_media/delete', methods=['POST'])
@login_required
@require_permission('contract.add')
def delete_temp_media():
    """删除临时目录中的媒体文件"""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'success': False, 'message': '请求数据格式无效'}), 400
        temp_key = data.get('temp_key')
        filename = data.get('filename')
        
        if not temp_key or not filename:
            return jsonify({'success': False, 'message': '缺少必要参数'}), 400
        
        # 安全处理temp_key，防止路径遍历
        temp_key = secure_filename(temp_key)
        if not temp_key:
            return jsonify({'success': False, 'message': '无效的临时标识参数'}), 400
        
        # 安全处理filename
        filename = secure_filename(filename)
        if not filename:
            return jsonify({'success': False, 'message': '无效的文件名'}), 400
        
        success = ContractAttachmentManager.delete_temp_file(filename, temp_key)
        
        if success:
            log_operation(
                user_id=current_user.id,
                module='contract',
                operation_type='delete_attachment',
                action=f"删除临时合同附件: {filename} (temp_key={temp_key})",
                result="成功"
            )
            return jsonify({'success': True, 'message': '文件删除成功'})
        else:
            return jsonify({'success': False, 'message': '文件删除失败或文件不存在'})
            
    except Exception as e:
        logging.error(f"删除临时合同附件失败: {str(e)}")
        return jsonify({'success': False, 'message': f'删除失败: {str(e)}'})


@contract_api_bp.route('/temp_media/clear', methods=['POST'])
@login_required
@require_permission('contract.add')
def clear_temp_media():
    """清理指定temp_key临时目录中的所有媒体文件"""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({'success': False, 'message': '请求数据格式无效'}), 400
        temp_key = data.get('temp_key')
        
        if not temp_key:
            return jsonify({'success': False, 'message': '缺少临时标识参数'}), 400
        
        # 安全处理temp_key，防止路径遍历
        temp_key = secure_filename(temp_key)
        if not temp_key:
            return jsonify({'success': False, 'message': '无效的临时标识参数'}), 400
        
        result = ContractAttachmentManager.clear_temp_files(temp_key)
        
        log_operation(
            user_id=current_user.id,
            module='contract',
            operation_type='delete_attachment',
            action=f"清理临时合同附件 (temp_key={temp_key}) [删除: {result['deleted']}]",
            result="成功" if not result['errors'] else "部分成功"
        )
        
        return jsonify({
            'success': True,
            'deleted': result['deleted'],
            'errors': result['errors'],
            'message': f"成功清理 {result['deleted']} 个文件" + (f"，{len(result['errors'])} 个失败" if result['errors'] else "")
        })
        
    except Exception as e:
        logging.error(f"清理临时合同附件失败: {str(e)}")
        return jsonify({'success': False, 'message': f'清理失败: {str(e)}'})


@contract_api_bp.route('/temp_media/<temp_key>/<filename>', methods=['GET'])
@login_required
@require_permission('contract.add')
def serve_temp_media(temp_key, filename):
    """提供临时目录中媒体文件的访问"""
    try:
        # 安全处理参数
        temp_key = secure_filename(temp_key)
        filename = secure_filename(filename)
        
        # 防止空参数导致路径遍历
        if not temp_key:
            abort(400, description="无效的临时标识参数")
        if not filename:
            abort(400, description="无效的文件名参数")
        
        # 获取文件完整路径
        file_path = ContractAttachmentManager.get_temp_file_path(filename, temp_key)
        
        # 检查文件是否存在
        if not file_path or not os.path.exists(file_path):
            abort(404, description="文件不存在")
        
        # 发送文件，根据扩展名推断 mimetype
        mime_type, _ = mimetypes.guess_type(file_path)
        return send_file(file_path, as_attachment=False, mimetype=mime_type or 'application/octet-stream')
    except Exception as e:
        logging.error(f"获取临时合同附件时发生错误: {str(e)}")
        abort(500, description=f"获取文件时发生错误: {str(e)}")


# ========== 合同详情JSON ==========
@contract_api_bp.route('/<int:id>', methods=['GET'])
@login_required
@require_permission('contract.view')
def get_contract_detail(id):
    """获取合同详情JSON，含附件列表和续签关系链"""
    try:
        contract = Contract.query.get_or_404(id)

        # 附件列表（纯文件系统模式）
        attachments = ContractAttachmentManager.get_media_files(id)
        attachment_list = [{
            "filename": a['filename'],
            "url": a['url'],
            "file_size": a['file_size'],
            "type": a['type'],
            "upload_time": a['upload_time'].strftime('%Y-%m-%d %H:%M') if a.get('upload_time') else None
        } for a in attachments]

        # 续签关系链
        renewal_chain = contract.renewal_chain
        chain_list = [{
            "id": rc.id,
            "contract_number": rc.contract_number or '',
            "contract_name": rc.contract_name or '',
            "status": rc.status or '',
            "start_date": rc.start_date.strftime('%Y-%m-%d') if rc.start_date else None,
            "end_date": rc.end_date.strftime('%Y-%m-%d') if rc.end_date else None
        } for rc in renewal_chain]

        contract_data = {
            "id": contract.id,
            "contract_number": contract.contract_number or '',
            "contract_name": contract.contract_name or '',
            "party_a_id": contract.party_a_id,
            "party_a_name": contract.party_a_name,
            "party_b_id": contract.party_b_id,
            "party_b_name": contract.party_b_name,
            "contract_type": contract.contract_type or '',
            "contract_category": contract.contract_category or '',
            "contract_amount": float(contract.contract_amount) if contract.contract_amount else 0.00,
            "currency": contract.currency or 'CNY',
            "tax_rate": float(contract.tax_rate) if contract.tax_rate else None,
            "status": contract.status or '草稿',
            "display_status": contract.display_status,
            "status_color": contract.status_color,
            "signing_date": contract.signing_date.strftime('%Y-%m-%d') if contract.signing_date else None,
            "start_date": contract.start_date.strftime('%Y-%m-%d') if contract.start_date else None,
            "end_date": contract.end_date.strftime('%Y-%m-%d') if contract.end_date else None,
            "days_until_expiry": contract.days_until_expiry,
            "is_renewal": contract.is_renewal,
            "previous_contract_id": contract.previous_contract_id,
            "handler_user_id": contract.handler_user_id,
            "handler_name": contract.handler_name,
            "department_id": contract.department_id,
            "department_name": contract.department_name,
            "storage_location_name": contract.storage_location_name if contract.storage_location else '',
            "remark": contract.remark or '',
            "created_at": contract.created_at.strftime('%Y-%m-%d %H:%M') if contract.created_at else None,
            "updated_at": contract.updated_at.strftime('%Y-%m-%d %H:%M') if contract.updated_at else None,
            "attachments": attachment_list,
            "renewal_chain": chain_list
        }

        return jsonify({
            "success": True,
            "data": contract_data
        })

    except Exception as e:
        logging.error(f"API获取合同详情失败 [ID: {id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
        }), 500


# ========== 获取供应商列表（用于甲乙方下拉选择） ==========
@contract_api_bp.route('/suppliers', methods=['GET'])
@login_required
@require_permission('contract.view')
def get_suppliers():
    """获取启用状态的供应商列表，含tax_rate字段，用于甲乙方下拉选择"""
    try:
        suppliers = Supplier.query.filter_by(status='启用').order_by(Supplier.name).all()

        supplier_list = [{
            "id": s.id,
            "name": s.name,
            "tax_rate": float(s.tax_rate) if s.tax_rate else 0
        } for s in suppliers]

        return jsonify({
            "success": True,
            "data": supplier_list
        })

    except Exception as e:
        logging.error(f"API获取供应商列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取指定供应商税率 ==========
@contract_api_bp.route('/suppliers/<int:id>/tax-rate', methods=['GET'])
@login_required
@require_permission('contract.view')
def get_supplier_tax_rate(id):
    """获取指定供应商的税率"""
    try:
        supplier = Supplier.query.get_or_404(id)
        tax_rate = float(supplier.tax_rate) if supplier.tax_rate else 0

        return jsonify({
            "success": True,
            "data": {"tax_rate": tax_rate}
        })

    except Exception as e:
        logging.error(f"API获取供应商税率失败 [ID: {id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取即将到期合同列表 ==========
@contract_api_bp.route('/expiring', methods=['GET'])
@login_required
@require_permission('contract.view')
def get_expiring_contracts():
    """获取即将到期的合同列表"""
    try:
        days = request.args.get('days', 30, type=int)
        contracts = Contract.get_expiring_contracts(days=days)

        contract_list = [{
            "id": c.id,
            "contract_number": c.contract_number or '',
            "contract_name": c.contract_name or '',
            "party_a_name": c.party_a_name,
            "party_b_name": c.party_b_name,
            "contract_type": c.contract_type or '',
            "status": c.status or '',
            "display_status": c.display_status,
            "status_color": c.status_color,
            "start_date": c.start_date.strftime('%Y-%m-%d') if c.start_date else None,
            "end_date": c.end_date.strftime('%Y-%m-%d') if c.end_date else None,
            "days_until_expiry": c.days_until_expiry,
            "handler_name": c.handler_name,
            "department_name": c.department_name
        } for c in contracts]

        return jsonify({
            "success": True,
            "data": contract_list
        })

    except Exception as e:
        logging.error(f"API获取即将到期合同列表失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取续签关系链 ==========
@contract_api_bp.route('/<int:id>/renewal-chain', methods=['GET'])
@login_required
@require_permission('contract.view')
def get_renewal_chain(id):
    """获取合同的续签关系链"""
    try:
        contract = Contract.query.get_or_404(id)
        renewal_chain = contract.renewal_chain

        chain_list = [{
            "id": rc.id,
            "contract_number": rc.contract_number or '',
            "contract_name": rc.contract_name or '',
            "status": rc.status or '',
            "start_date": rc.start_date.strftime('%Y-%m-%d') if rc.start_date else None,
            "end_date": rc.end_date.strftime('%Y-%m-%d') if rc.end_date else None
        } for rc in renewal_chain]

        return jsonify({
            "success": True,
            "data": chain_list
        })

    except Exception as e:
        logging.error(f"API获取续签关系链失败 [ID: {id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取合同附件列表 ==========
@contract_api_bp.route('/<int:id>/attachments', methods=['GET'])
@login_required
@require_permission('contract.view')
def get_contract_attachments(id):
    """获取合同附件列表（纯文件系统模式）"""
    try:
        attachments = ContractAttachmentManager.get_media_files(id)

        attachment_list = [{
            "filename": a['filename'],
            "url": a['url'],
            "file_size": a['file_size'],
            "type": a['type'],
            "upload_time": a['upload_time'].strftime('%Y-%m-%d %H:%M') if a.get('upload_time') else None
        } for a in attachments]

        return jsonify({
            "success": True,
            "data": attachment_list
        })

    except Exception as e:
        logging.error(f"API获取合同附件列表失败 [ID: {id}]: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== 获取合同附件文件（静态文件服务） ==========
@contract_api_bp.route('/media/<int:contract_id>/<path:filename>', methods=['GET'])
@login_required
@require_permission('contract.view')
def get_contract_media(contract_id, filename):
    """获取合同的媒体文件（附件、图片、文档等）"""
    try:
        # 纵深防御：安全处理filename，防止路径遍历
        filename = secure_filename(filename)
        if not filename:
            return jsonify({'error': '无效的文件名参数'}), 400
        file_path = ContractAttachmentManager.get_file_path(contract_id, filename)
        if file_path and os.path.exists(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            return send_file(file_path, as_attachment=False, mimetype=mime_type or 'application/octet-stream')
        return jsonify({'error': '文件不存在'}), 404
    except Exception as e:
        logging.error(f"获取合同媒体文件时发生错误: {str(e)}")
        return jsonify({'error': f"获取文件时发生错误: {str(e)}"}), 500


# ========== 自动生成合同编号 ==========
@contract_api_bp.route('/generate-number', methods=['GET'])
@login_required
@require_permission('contract.create')
def generate_contract_number():
    """自动生成合同编号，格式: HT+年月+4位序号 (如 HT2026080001)"""
    try:
        now = datetime.now()
        prefix = f"HT{now.strftime('%Y%m')}"

        # 查询当月已有最大编号
        max_contract = Contract.query.filter(
            Contract.contract_number.like(f"{prefix}%")
        ).order_by(Contract.contract_number.desc()).first()

        if max_contract and max_contract.contract_number:
            # 提取序号部分并+1
            number_part = max_contract.contract_number[len(prefix):]
            try:
                seq = int(number_part) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1

        contract_number = f"{prefix}{seq:04d}"

        return jsonify({
            "success": True,
            "data": {"contract_number": contract_number}
        })

    except Exception as e:
        logging.error(f"API生成合同编号失败: {str(e)}\n{traceback.format_exc()}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500