from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user
from utils.auth import require_permission
from models.room.room_item import RoomItem
from models.room.room_item_assignment import RoomItemAssignment
from models.room.room import Room
import logging
import traceback


room_item_api_bp = Blueprint('room_item_api', __name__, url_prefix='/api/room/items')


# API路由1: 获取指定房间的物品列表
@room_item_api_bp.route('/<int:room_id>', methods=['GET'])
@login_required
@require_permission('room_item.view')
def get_room_items(room_id):
    try:
        # 验证room_id存在
        room = Room.query.get(room_id)
        if not room:
            return jsonify({'success': False, 'message': '房间不存在'}), 404

        items = RoomItem.query.filter_by(room_id=room_id).order_by(RoomItem.id.desc()).all()
        result = []
        for item in items:
            result.append({
                'id': item.id,
                'room_id': item.room_id,
                'name': item.name,
                'item_type': item.item_type,
                'item_type_display': RoomItem.ITEM_TYPE_MAP.get(item.item_type, '未知类型'),
                'total_quantity': item.total_quantity,
                'available_quantity': item.available_quantity,
                'status': item.status,
                'remark': item.remark,
                'created_at': item.created_at.strftime('%Y-%m-%d %H:%M') if item.created_at else '',
                'updated_at': item.updated_at.strftime('%Y-%m-%d %H:%M') if item.updated_at else ''
            })
        return jsonify({'success': True, 'items': result})
    except Exception as e:
        logging.error(f"获取房间物品列表失败: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': '服务器内部错误'}), 500


# API路由2: 获取指定用户持有的物品列表
@room_item_api_bp.route('/assignments/<int:user_id>', methods=['GET'])
@login_required
@require_permission('room_item.view')
def get_user_assignments(user_id):
    try:
        # �权限验证：只能查看自己的分配记录，管理员可查看任意用户
        if current_user.id != user_id and not current_user.has_permission('room_item.view'):
            return jsonify({'success': False, 'message': '无权查看该用户的物品分配记录'}), 403

        assignments = RoomItemAssignment.query.filter_by(
            user_id=user_id, status='active'
        ).order_by(RoomItemAssignment.assigned_at.desc()).all()

        # 批量查询RoomItem，避免N+1查询
        item_ids = [a.item_id for a in assignments]
        item_map = {}
        if item_ids:
            items = RoomItem.query.filter(RoomItem.id.in_(item_ids)).all()
            item_map = {i.id: i for i in items}

        result = []
        for assignment in assignments:
            item = item_map.get(assignment.item_id)
            result.append({
                'id': assignment.id,
                'item_id': assignment.item_id,
                'item_name': item.name if item else '',
                'item_type': item.item_type if item else '',
                'item_type_display': RoomItem.ITEM_TYPE_MAP.get(item.item_type, '未知类型') if item else '',
                'room_id': item.room_id if item else None,
                'quantity': assignment.quantity,
                'status': assignment.status,
                'status_display': RoomItemAssignment.STATUS_MAP.get(assignment.status, assignment.status),
                'assigned_at': assignment.assigned_at.strftime('%Y-%m-%d %H:%M') if assignment.assigned_at else '',
                'remarks': assignment.remarks
            })
        return jsonify({'success': True, 'assignments': result})
    except Exception as e:
        logging.error(f"获取用户物品分配列表失败: {traceback.format_exc()}")
        return jsonify({'success': False, 'message': '服务器内部错误'}), 500