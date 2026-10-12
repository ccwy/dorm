from flask import Blueprint, render_template, request, flash, redirect, url_for
from utils.db import db
from models.room.room_item import RoomItem
from models.room.room_item_record import RoomItemRecord
from models.room.room_item_assignment import RoomItemAssignment
from models.room.room import Room
from models.dorm.dorm import Dorm
from models.user.user import User
from flask_login import login_required, current_user
from utils.log import log_operation
from utils.auth import require_permission
from datetime import datetime
import logging
import traceback

room_item_bp = Blueprint(
    'room_item',
    __name__,
    url_prefix='/room/item',
    template_folder='../../templates',
    static_folder='../../static',
    static_url_path='/room/item/static'
)


def escape_like(value):
    """转义SQL LIKE中的特殊字符%和_"""
    return value.replace('%', '\\%').replace('_', '\\_')


def generate_page_range(current_page, total_pages, show_pages=5):
    if total_pages <= show_pages:
        return list(range(1, total_pages + 1))
    half = show_pages // 2
    start = max(1, current_page - half)
    end = min(total_pages, start + show_pages - 1)
    if end - start < show_pages - 1:
        start = max(1, end - show_pages + 1)
    page_range = []
    if start > 1:
        page_range.append(1)
        if start > 2:
            page_range.append('...')
    page_range.extend(range(start, end + 1))
    if end < total_pages:
        if end < total_pages - 1:
            page_range.append('...')
        page_range.append(total_pages)
    return page_range


def _get_operator_id():
    """获取当前操作用户ID"""
    return current_user.id if hasattr(current_user, 'id') else None


# 路由1: 物品管理主页
@room_item_bp.route('/manage', methods=['GET'])
@login_required
@require_permission('room_item.view')
def manage():
    try:
        # 获取筛选参数
        building = request.args.get('building', '').strip()
        room_number = request.args.get('room_number', '').strip()
        item_name = request.args.get('item_name', '').strip()
        status = request.args.get('status', '').strip()

        # 分页参数
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 20, type=int)
        if page < 1:
            page = 1
        per_page = max(10, min(100, per_page))

        # 构建查询
        query = RoomItem.query.join(Room, RoomItem.room_id == Room.id)

        if building:
            query = query.filter(Room.building.like(f'%{escape_like(building)}%', escape='\\'))
        if room_number:
            query = query.filter(Room.room_number.like(f'%{escape_like(room_number)}%', escape='\\'))
        if item_name:
            query = query.filter(RoomItem.name.like(f'%{escape_like(item_name)}%', escape='\\'))
        if status:
            query = query.filter(RoomItem.status == status)

        query = query.order_by(RoomItem.id.desc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        # 获取所有楼栋列表用于筛选
        buildings = [r[0] for r in db.session.query(Room.building).distinct().all() if r[0]]
        # 获取所有房间列表用于新增物品选择
        rooms = Room.query.order_by(Room.building, Room.room_number).all()

        return render_template('room_manage/room_item_list.html',
                               items=pagination.items,
                               pagination=pagination,
                               page_range=generate_page_range(page, pagination.pages),
                               buildings=buildings,
                               rooms=rooms,
                               building=building,
                               room_number=room_number,
                               item_name=item_name,
                               status=status)
    except Exception as e:
        logging.error(f"物品管理主页加载失败: {str(e)}\n{traceback.format_exc()}")
        flash('加载物品列表失败', 'error')
        return render_template('room_manage/room_item_list.html',
                               items=[], pagination=None, page_range=[],
                               buildings=[], rooms=[],
                               building='', room_number='',
                               item_name='', status='')


# 路由2: 添加物品
@room_item_bp.route('/add/<int:room_id>', methods=['GET', 'POST'])
@login_required
@require_permission('room_item.create')
def add(room_id):
    try:
        room = Room.query.get_or_404(room_id)

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            item_type = request.form.get('item_type', 'room_bound').strip()
            total_quantity = request.form.get('total_quantity', 1, type=int)
            remark = request.form.get('remark', '').strip()

            if not name:
                flash('物品名称不能为空', 'error')
                return render_template('room_manage/room_item_add.html', room=room)

            if total_quantity < 1:
                flash('数量必须大于0', 'error')
                return render_template('room_manage/room_item_add.html', room=room)

            # 创建物品
            item = RoomItem.create_item(
                room_id=room_id,
                name=name,
                item_type=item_type,
                total_quantity=total_quantity,
                remark=remark
            )
            db.session.flush()  # 确保item获得id后再记录操作

            # 记录操作
            RoomItemRecord.add_record(
                item_id=item.id,
                operation_type='create',
                quantity=total_quantity,
                before_quantity=0,
                after_quantity=total_quantity,
                operator_id=_get_operator_id(),
                remarks=f'新增物品: {name}'
            )

            db.session.commit()
            log_operation(user_id=current_user.id, action=f'新增房间物品: {name}, 房间: {room.building}{room.room_number}', module='room_item')
            flash(f'物品"{name}"添加成功', 'success')
            return redirect(url_for('room.view', id=room_id))

        return render_template('room_manage/room_item_add.html', room=room)
    except Exception as e:
        db.session.rollback()
        logging.error(f"添加物品失败: {str(e)}\n{traceback.format_exc()}")
        flash(f'添加物品失败: {str(e)}', 'error')
        return redirect(url_for('room_item.manage'))


# 路由3: 编辑物品
@room_item_bp.route('/edit/<int:item_id>', methods=['GET', 'POST'])
@login_required
@require_permission('room_item.edit')
def edit(item_id):
    try:
        item = RoomItem.query.get_or_404(item_id)

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            total_quantity = request.form.get('total_quantity', 1, type=int)
            status = request.form.get('status', '正常').strip()
            remark = request.form.get('remark', '').strip()

            if not name:
                flash('物品名称不能为空', 'error')
                return render_template('room_manage/room_item_edit.html', item=item)

            # 状态转换验证：不允许从非正常状态恢复为正常
            valid_transitions = {
                '正常': ['损坏', '丢失', '报废'],
                '损坏': ['丢失', '报废'],
                '丢失': ['报废'],
                '报废': []
            }
            old_status = item.status
            if status != old_status:
                if old_status not in valid_transitions or status not in valid_transitions[old_status]:
                    flash(f'不允许从"{old_status}"变更为"{status}"', 'error')
                    return render_template('room_manage/room_item_edit.html', item=item)
                # 验证新状态值合法
                RoomItem.validate_status(status)

            if total_quantity < 1:
                flash('总数量必须大于0', 'error')
                return render_template('room_manage/room_item_edit.html', item=item)

            # 验证可用数量不超过总数量
            assigned_count = item.total_quantity - item.available_quantity
            if total_quantity < assigned_count:
                flash(f'总数量不能小于已分配数量({assigned_count})', 'error')
                return render_template('room_manage/room_item_edit.html', item=item)

            before_available = item.available_quantity
            item.name = name
            item.total_quantity = total_quantity
            item.available_quantity = total_quantity - assigned_count
            item.status = status
            item.remark = remark
            # 当状态变为非正常时，如果仍有数量，提示使用专用操作
            if status != '正常' and (item.total_quantity > 0 or item.available_quantity > 0):
                flash('请使用详情页的损坏/丢失/报废按钮进行操作，支持指定数量', 'error')
                return render_template('room_manage/room_item_edit.html', item=item)

            # 记录编辑操作
            RoomItemRecord.add_record(
                item_id=item_id,
                operation_type='edit',
                quantity=total_quantity,
                before_quantity=before_available,
                after_quantity=item.available_quantity,
                operator_id=_get_operator_id(),
                remarks=f'编辑物品: {name}'
            )

            db.session.commit()
            log_operation(user_id=current_user.id, action=f'编辑房间物品: {name}, ID={item_id}', module='room_item')
            flash(f'物品"{name}"更新成功', 'success')
            return redirect(url_for('room_item.manage'))

        return render_template('room_manage/room_item_edit.html', item=item)
    except Exception as e:
        db.session.rollback()
        logging.error(f"编辑物品失败: {str(e)}\n{traceback.format_exc()}")
        flash(f'编辑物品失败: {str(e)}', 'error')
        return redirect(url_for('room_item.manage'))


# 路由4: 删除物品
@room_item_bp.route('/delete/<int:item_id>', methods=['POST'])
@login_required
@require_permission('room_item.delete')
def delete(item_id):
    try:
        item = RoomItem.query.get_or_404(item_id)

        # 验证无active分配记录
        active_assignments = RoomItemAssignment.query.filter_by(
            item_id=item_id, status='active'
        ).count()

        if active_assignments > 0:
            flash(f'该物品有{active_assignments}条活跃分配记录，无法删除', 'error')
            return redirect(url_for('room_item.manage'))

        item_name = item.name
        room_id = item.room_id
        item_info = f'名称={item_name}, 总数量={item.total_quantity}, 可用={item.available_quantity}, 房间ID={room_id}'

        # 记录删除操作（在级联删除之前）
        RoomItemRecord.add_record(
            item_id=item_id,
            operation_type='delete',
            quantity=item.total_quantity,
            before_quantity=item.available_quantity,
            after_quantity=0,
            operator_id=_get_operator_id(),
            remarks=f'删除物品: {item_name}'
        )

        # 删除物品（关联的records会被级联删除）
        db.session.delete(item)
        db.session.commit()
        log_operation(user_id=current_user.id, action=f'删除房间物品: {item_info}, ID={item_id}', module='room_item')
        flash(f'物品"{item_name}"删除成功', 'success')
    except Exception as e:
        db.session.rollback()
        logging.error(f"删除物品失败: {str(e)}\n{traceback.format_exc()}")
        flash(f'删除物品失败: {str(e)}', 'error')

    return redirect(url_for('room_item.manage'))


# 路由5: 分配物品给用户
@room_item_bp.route('/allocate/<int:item_id>', methods=['GET', 'POST'])
@login_required
@require_permission('room_item.allocate')
def allocate(item_id):
    try:
        item = RoomItem.query.get_or_404(item_id)
        room = Room.query.get_or_404(item.room_id)

        if request.method == 'POST':
            user_id = request.form.get('user_id', type=int)
            quantity = request.form.get('quantity', 1, type=int)
            remarks = request.form.get('remarks', '').strip()

            # 查询当前房间在住用户列表（POST错误返回需要）
            active_dorms = Dorm.query.filter_by(room_id=room.id, status='active').all()
            user_ids = [d.user_id for d in active_dorms]
            users = User.query.filter(User.id.in_(user_ids)).all() if user_ids else []

            if not user_id:
                flash('请选择用户', 'error')
                return render_template('room_manage/room_item_allocate.html', item=item, room=room, users=users)

            if quantity < 1:
                flash('分配数量必须大于0', 'error')
                return render_template('room_manage/room_item_allocate.html', item=item, room=room, users=users)

            # 验证可用数量
            if quantity > item.available_quantity:
                flash(f'可用数量不足，当前可用: {item.available_quantity}', 'error')
                return render_template('room_manage/room_item_allocate.html', item=item, room=room, users=users)

            before_available = item.available_quantity

            # 查询用户当前住宿记录以关联dorm_id
            user_dorm = Dorm.query.filter_by(user_id=user_id, room_id=room.id, status='active').first()

            # 创建分配记录
            assignment = RoomItemAssignment.create_assignment(
                item_id=item_id,
                user_id=user_id,
                quantity=quantity,
                dorm_id=user_dorm.id if user_dorm else None,
                remarks=remarks
            )

            # 记录操作（available_quantity已由create_assignment扣减）
            RoomItemRecord.add_record(
                item_id=item_id,
                operation_type='allocate',
                quantity=quantity,
                before_quantity=before_available,
                after_quantity=item.available_quantity,
                user_id=user_id,
                from_room_id=item.room_id,
                operator_id=_get_operator_id(),
                remarks=remarks
            )

            db.session.commit()
            log_operation(user_id=current_user.id, action=f'分配物品: {item.name} 给用户ID={user_id}, 数量={quantity}', module='room_item')
            flash(f'物品"{item.name}"分配成功', 'success')
            return redirect(url_for('room_item.manage'))

        # GET: 列出当前房间的在住用户
        active_dorms = Dorm.query.filter_by(room_id=room.id, status='active').all()
        user_ids = [d.user_id for d in active_dorms]
        users = User.query.filter(User.id.in_(user_ids)).all() if user_ids else []

        return render_template('room_manage/room_item_allocate.html',
                               item=item, room=room, users=users)
    except Exception as e:
        db.session.rollback()
        logging.error(f"分配物品失败: {str(e)}\n{traceback.format_exc()}")
        flash(f'分配物品失败: {str(e)}', 'error')
        return redirect(url_for('room_item.manage'))


# 路由6: 归还物品
@room_item_bp.route('/return/<int:assignment_id>', methods=['POST'])
@login_required
@require_permission('room_item.return')
def return_item(assignment_id):
    try:
        assignment = RoomItemAssignment.query.get_or_404(assignment_id)
        item = RoomItem.query.get_or_404(assignment.item_id)

        if assignment.status != 'active':
            flash('该分配记录已处理，无法归还', 'error')
            return redirect(url_for('room_item.manage'))

        # 验证物品状态
        if item.status != '正常':
            flash(f'物品状态为"{item.status}"，无法归还，请先恢复正常状态', 'error')
            return redirect(url_for('room_item.manage'))

        before_available = item.available_quantity

        # 更新分配状态
        assignment.status = 'returned'
        assignment.returned_at = datetime.now()

        # 增加可用数量
        item.available_quantity += assignment.quantity

        # 记录操作
        RoomItemRecord.add_record(
            item_id=item.id,
            operation_type='return',
            quantity=assignment.quantity,
            before_quantity=before_available,
            after_quantity=item.available_quantity,
            user_id=assignment.user_id,
            from_room_id=item.room_id,
            operator_id=_get_operator_id(),
            remarks='归还物品'
        )

        db.session.commit()
        log_operation(user_id=current_user.id, action=f'归还物品: {item.name}, 用户ID={assignment.user_id}, 数量={assignment.quantity}', module='room_item')
        flash(f'物品"{item.name}"归还成功', 'success')
    except Exception as e:
        db.session.rollback()
        logging.error(f"归还物品失败: {str(e)}\n{traceback.format_exc()}")
        flash(f'归还物品失败: {str(e)}', 'error')

    return redirect(url_for('room_item.manage'))


# 公共方法：修改物品状态（损坏/丢失/报废），支持指定数量
def _change_item_status(item_id, new_status, assignment_status, op_type, remark, quantity=1):
    """修改物品状态，支持部分数量操作
    
    Args:
        item_id: 物品ID
        new_status: 物品新状态（'损坏'/'丢失'/'报废'）
        assignment_status: 分配新状态（'damaged'/'lost'/'scrapped'）
        op_type: 操作类型（'damage'/'loss'/'scrap'）
        remark: 操作备注
        quantity: 操作数量（默认1）
    """
    item = RoomItem.query.get_or_404(item_id)

    # 验证数量
    if quantity < 1:
        flash('操作数量必须大于0', 'error')
        return redirect(url_for('room_item.detail', item_id=item_id))
    if quantity > item.total_quantity:
        flash(f'操作数量不能大于总数量({item.total_quantity})', 'error')
        return redirect(url_for('room_item.detail', item_id=item_id))
    if quantity > item.available_quantity:
        flash(f'可用数量不足，当前可用{item.available_quantity}，请先归还已分配的物品', 'error')
        return redirect(url_for('room_item.detail', item_id=item_id))

    before_available = item.available_quantity
    before_total = item.total_quantity

    # 减少数量
    item.total_quantity -= quantity
    item.available_quantity -= quantity

    # 如果total变为0，设置物品状态并更新active分配
    if item.total_quantity == 0:
        item.status = new_status
        active_assignments = RoomItemAssignment.query.filter_by(
            item_id=item_id, status='active'
        ).all()
        for assignment in active_assignments:
            assignment.status = assignment_status
            assignment.returned_at = datetime.now()

    # 记录操作
    RoomItemRecord.add_record(
        item_id=item_id,
        operation_type=op_type,
        quantity=quantity,
        before_quantity=before_available,
        after_quantity=item.available_quantity,
        operator_id=_get_operator_id(),
        remarks=f'{remark}, 数量={quantity}'
    )

    db.session.commit()
    log_operation(user_id=current_user.id, action=f'{remark}: {item.name}, 数量={quantity}, ID={item_id}', module='room_item')
    if item.total_quantity == 0:
        flash(f'物品"{item.name}"已全部{remark}（{quantity}），状态变为{new_status}', 'success')
    else:
        flash(f'物品"{item.name}"{remark} {quantity} 个，剩余{item.total_quantity}个', 'success')


# 路由7: 标记损坏
@room_item_bp.route('/damage/<int:item_id>', methods=['POST'])
@login_required
@require_permission('room_item.operate')
def damage(item_id):
    try:
        quantity = request.form.get('quantity', 1, type=int)
        _change_item_status(item_id, '损坏', 'damaged', 'damage', '标记损坏', quantity=quantity)
    except Exception as e:
        db.session.rollback()
        logging.error(f"标记损坏失败: {str(e)}\n{traceback.format_exc()}")
        flash(f'标记损坏失败: {str(e)}', 'error')

    return redirect(url_for('room_item.detail', item_id=item_id))


# 路由8: 标记丢失
@room_item_bp.route('/loss/<int:item_id>', methods=['POST'])
@login_required
@require_permission('room_item.operate')
def loss(item_id):
    try:
        quantity = request.form.get('quantity', 1, type=int)
        _change_item_status(item_id, '丢失', 'lost', 'loss', '标记丢失', quantity=quantity)
    except Exception as e:
        db.session.rollback()
        logging.error(f"标记丢失失败: {str(e)}\n{traceback.format_exc()}")
        flash(f'标记丢失失败: {str(e)}', 'error')

    return redirect(url_for('room_item.detail', item_id=item_id))


# 路由9: 标记报废
@room_item_bp.route('/scrap/<int:item_id>', methods=['POST'])
@login_required
@require_permission('room_item.operate')
def scrap(item_id):
    try:
        quantity = request.form.get('quantity', 1, type=int)
        _change_item_status(item_id, '报废', 'scrapped', 'scrap', '标记报废', quantity=quantity)
    except Exception as e:
        db.session.rollback()
        logging.error(f"标记报废失败: {str(e)}\n{traceback.format_exc()}")
        flash(f'标记报废失败: {str(e)}', 'error')

    return redirect(url_for('room_item.detail', item_id=item_id))


# 路由10: 转移物品
@room_item_bp.route('/transfer/<int:item_id>', methods=['GET', 'POST'])
@login_required
@require_permission('room_item.operate')
def transfer(item_id):
    try:
        item = RoomItem.query.get_or_404(item_id)

        if request.method == 'POST':
            target_room_id = request.form.get('target_room_id', type=int)
            quantity = request.form.get('quantity', 1, type=int)
            remarks = request.form.get('remarks', '').strip()

            # 查询可选房间列表（POST错误返回需要）
            rooms = Room.query.filter(Room.id != item.room_id).order_by(Room.building, Room.room_number).all()

            if not target_room_id:
                flash('请选择目标房间', 'error')
                return render_template('room_manage/room_item_transfer.html', item=item, rooms=rooms)

            # 验证物品类型
            if item.item_type != 'transferable':
                flash('该物品类型不可转移', 'error')
                return render_template('room_manage/room_item_transfer.html', item=item, rooms=rooms)

            # 验证物品状态
            if item.status != '正常':
                flash(f'物品状态为"{item.status}"，无法转移', 'error')
                return render_template('room_manage/room_item_transfer.html', item=item, rooms=rooms)

            # 验证数量
            if quantity < 1:
                flash('转移数量必须大于0', 'error')
                return render_template('room_manage/room_item_transfer.html', item=item, rooms=rooms)
            if quantity > item.available_quantity:
                flash(f'转移数量不能大于可用数量({item.available_quantity})', 'error')
                return render_template('room_manage/room_item_transfer.html', item=item, rooms=rooms)

            target_room = Room.query.get_or_404(target_room_id)
            before_available = item.available_quantity
            from_room_id = item.room_id

            if quantity >= item.total_quantity:
                # 整件转移：物品直接换房间
                item.room_id = target_room_id
                RoomItemRecord.add_record(
                    item_id=item_id,
                    operation_type='transfer',
                    quantity=quantity,
                    before_quantity=before_available,
                    after_quantity=item.available_quantity,
                    from_room_id=from_room_id,
                    to_room_id=target_room_id,
                    operator_id=_get_operator_id(),
                    remarks=remarks
                )
            else:
                # 部分转移：源物品减少数量，目标房间合并或新建
                item.total_quantity -= quantity
                item.available_quantity -= quantity

                # 查找目标房间是否有同名同类物品
                target_item = RoomItem.query.filter_by(
                    room_id=target_room_id,
                    name=item.name,
                    item_type=item.item_type,
                    status='正常'
                ).first()

                if target_item:
                    # 合到已有物品
                    target_item.total_quantity += quantity
                    target_item.available_quantity += quantity
                    RoomItemRecord.add_record(
                        item_id=target_item.id,
                        operation_type='transfer',
                        quantity=quantity,
                        before_quantity=target_item.available_quantity - quantity,
                        after_quantity=target_item.available_quantity,
                        from_room_id=from_room_id,
                        to_room_id=target_room_id,
                        operator_id=_get_operator_id(),
                        remarks=f'从其他房间转入: {remarks}'
                    )
                else:
                    # 新建物品
                    new_item = RoomItem.create_item(
                        room_id=target_room_id,
                        name=item.name,
                        item_type=item.item_type,
                        total_quantity=quantity,
                        remark=f'从房间转移而来: {remarks}' if remarks else '从其他房间转移而来'
                    )
                    db.session.flush()
                    RoomItemRecord.add_record(
                        item_id=new_item.id,
                        operation_type='transfer',
                        quantity=quantity,
                        before_quantity=0,
                        after_quantity=quantity,
                        from_room_id=from_room_id,
                        to_room_id=target_room_id,
                        operator_id=_get_operator_id(),
                        remarks=remarks
                    )

                # 源物品记录
                RoomItemRecord.add_record(
                    item_id=item_id,
                    operation_type='transfer',
                    quantity=quantity,
                    before_quantity=before_available,
                    after_quantity=item.available_quantity,
                    from_room_id=from_room_id,
                    to_room_id=target_room_id,
                    operator_id=_get_operator_id(),
                    remarks=f'转移到房间ID={target_room_id}: {remarks}'
                )

            db.session.commit()
            log_operation(user_id=current_user.id, action=f'转移物品: {item.name}, 数量={quantity}, 从房间ID={from_room_id} 到房间ID={target_room_id}', module='room_item')
            flash(f'物品"{item.name}"转移成功，数量: {quantity}', 'success')
            return redirect(url_for('room_item.detail', item_id=item_id))

        # GET: 列出可选目标房间
        rooms = Room.query.filter(Room.id != item.room_id).order_by(Room.building, Room.room_number).all()
        return render_template('room_manage/room_item_transfer.html', item=item, rooms=rooms)
    except Exception as e:
        db.session.rollback()
        logging.error(f"转移物品失败: {str(e)}\n{traceback.format_exc()}")
        flash(f'转移物品失败: {str(e)}', 'error')
        return redirect(url_for('room_item.detail', item_id=item_id))


# 路由11: 物品详情
@room_item_bp.route('/detail/<int:item_id>', methods=['GET'])
@login_required
@require_permission('room_item.view')
def detail(item_id):
    try:
        item = RoomItem.query.get_or_404(item_id)
        # 获取活跃分配记录
        active_assignments = (RoomItemAssignment.query
            .filter_by(item_id=item_id, status='active')
            .order_by(RoomItemAssignment.assigned_at.desc()).all())
        # 获取最近操作记录
        recent_records = (RoomItemRecord.query
            .filter_by(item_id=item_id)
            .order_by(RoomItemRecord.operated_at.desc()).limit(20).all())
        # 获取所有分配记录（含历史）
        all_assignments = (RoomItemAssignment.query
            .filter_by(item_id=item_id)
            .order_by(RoomItemAssignment.assigned_at.desc()).all())

        log_operation(
            user_id=current_user.id,
            action=f'查看物品详情: {item.name}, ID={item_id}',
            module='room_item',
            operation_type='view'
        )
        logging.info(f"查看物品详情，物品ID: {item_id}")

        return render_template('room_manage/room_item_detail.html',
                               item=item,
                               active_assignments=active_assignments,
                               recent_records=recent_records,
                               all_assignments=all_assignments)
    except Exception as e:
        logging.error(f"查看物品详情失败: {str(e)}\n{traceback.format_exc()}")
        flash('查看物品详情失败', 'error')
        return redirect(url_for('room_item.manage'))


# 路由12: 物品流转记录
@room_item_bp.route('/records/<int:item_id>', methods=['GET'])
@login_required
@require_permission('room_item.view')
def records(item_id):
    try:
        item = RoomItem.query.get_or_404(item_id)
        record_list = (RoomItemRecord.query.filter_by(item_id=item_id)
            .order_by(RoomItemRecord.operated_at.desc()).all())
        return render_template('room_manage/room_item_records.html',
                               item=item, records=record_list)
    except Exception as e:
        logging.error(f"获取物品记录失败: {str(e)}\n{traceback.format_exc()}")
        flash('获取物品记录失败', 'error')
        return redirect(url_for('room_item.manage'))


# 路由12: 宿舍操作物品确认页面
@room_item_bp.route('/confirm_dorm_operation/<int:dorm_id>/<operation_type>', methods=['GET'])
@login_required
@require_permission('room_item.operate')
def confirm_dorm_operation(dorm_id, operation_type):
    try:
        # 白名单校验
        valid_operation_types = ('dorm_transfer', 'dorm_exchange', 'dorm_checkout')
        if operation_type not in valid_operation_types:
            flash('无效的操作类型', 'error')
            return redirect(url_for('room_item.manage'))

        dorm = Dorm.query.get_or_404(dorm_id)

        # 获取dorm关联用户在当前房间的active assignments（限定room_id）
        active_assignments = RoomItemAssignment.query.filter_by(
            user_id=dorm.user_id, status='active'
        ).join(
            RoomItem, RoomItemAssignment.item_id == RoomItem.id
        ).filter(
            RoomItem.room_id == dorm.room_id
        ).all()

        # 获取关联的物品信息
        item_ids = [a.item_id for a in active_assignments]
        items = RoomItem.query.filter(RoomItem.id.in_(item_ids)).all() if item_ids else []
        item_map = {i.id: i for i in items}

        # 获取目标房间ID（换宿场景需要新房间）
        target_room_id = None
        if operation_type == 'dorm_transfer' and dorm.user_id:
            new_dorm = Dorm.query.filter(
                Dorm.user_id == dorm.user_id,
                Dorm.status == 'active',
                Dorm.id != dorm_id
            ).first()
            if new_dorm:
                target_room_id = new_dorm.room_id

        return render_template('room_manage/room_item_confirm_dorm.html',
                               dorm=dorm,
                               operation_type=operation_type,
                               assignments=active_assignments,
                               item_map=item_map,
                               target_room_id=target_room_id)
    except Exception as e:
        logging.error(f"加载物品确认页面失败: {str(e)}\n{traceback.format_exc()}")
        flash('加载物品确认页面失败', 'error')
        return redirect(url_for('room_item.manage'))


# 路由13: 确认宿舍操作物品处理
@room_item_bp.route('/confirm_dorm_operation', methods=['POST'])
@login_required
@require_permission('room_item.operate')
def process_dorm_operation():
    try:
        dorm_id = request.form.get('dorm_id', type=int)
        operation_type = request.form.get('operation_type', '')
        dorm = Dorm.query.get_or_404(dorm_id)

        # 严重2修复: 按room_id过滤，与确认页面一致
        active_assignments = RoomItemAssignment.query.filter_by(
            user_id=dorm.user_id, status='active'
        ).join(
            RoomItem, RoomItemAssignment.item_id == RoomItem.id
        ).filter(
            RoomItem.room_id == dorm.room_id
        ).all()

        # 严重6修复: 获取目标房间ID（换宿场景需要新房间）
        target_room_id = request.form.get('target_room_id', type=int)

        # 操作类型到dorm_*记录类型的映射（警告12修复）
        dorm_op_map = {
            'dorm_transfer': 'dorm_transfer',
            'dorm_exchange': 'dorm_exchange',
            'dorm_checkout': 'dorm_checkout'
        }
        dorm_record_type = dorm_op_map.get(operation_type, 'dorm_checkout')

        for assignment in active_assignments:
            action = request.form.get(f'action_{assignment.id}', 'return')
            item = RoomItem.query.get(assignment.item_id)
            if not item:
                continue

            # 严重3修复: 非正常状态物品跳过处理
            if item.status != '正常':
                logging.warning(f"物品ID={item.id}状态为{item.status}，跳过处理")
                continue

            before_available = item.available_quantity
            before_total = item.total_quantity

            if action == 'return':
                # 归还
                assignment.status = 'returned'
                assignment.returned_at = datetime.now()
                # 严重5修复: available上界保护
                item.available_quantity = min(item.total_quantity, item.available_quantity + assignment.quantity)
                RoomItemRecord.add_record(
                    item_id=item.id,
                    operation_type=dorm_record_type,
                    quantity=assignment.quantity,
                    before_quantity=before_available,
                    after_quantity=item.available_quantity,
                    user_id=assignment.user_id,
                    from_room_id=item.room_id,
                    operator_id=_get_operator_id(),
                    remarks='宿舍操作-归还'
                )
            elif action == 'damage':
                quantity = request.form.get(f'quantity_{assignment.id}', assignment.quantity, type=int)
                if quantity < 1:
                    quantity = 1
                if quantity > assignment.quantity:
                    quantity = assignment.quantity
                # 减少总数量
                item.total_quantity -= quantity
                # 剩余数量自动归还
                remaining = assignment.quantity - quantity
                if remaining > 0:
                    item.available_quantity = min(item.total_quantity, item.available_quantity + remaining)
                # 记录损坏操作
                RoomItemRecord.add_record(
                    item_id=item.id,
                    operation_type=dorm_record_type,
                    quantity=quantity,
                    before_quantity=before_available,
                    after_quantity=item.available_quantity,
                    user_id=assignment.user_id,
                    from_room_id=item.room_id,
                    operator_id=_get_operator_id(),
                    remarks=f'宿舍操作-损坏, 数量={quantity}'
                )
                # 记录自动归还操作
                if remaining > 0:
                    RoomItemRecord.add_record(
                        item_id=item.id,
                        operation_type=dorm_record_type,
                        quantity=remaining,
                        before_quantity=item.available_quantity - remaining,
                        after_quantity=item.available_quantity,
                        user_id=assignment.user_id,
                        from_room_id=item.room_id,
                        operator_id=_get_operator_id(),
                        remarks=f'宿舍操作-自动归还, 数量={remaining}'
                    )
                # 标记分配状态
                assignment.status = 'damaged' if quantity >= assignment.quantity else 'returned'
                assignment.returned_at = datetime.now()
                # 如果总数量为0，设置物品状态并级联更新其他分配
                if item.total_quantity <= 0:
                    item.total_quantity = 0
                    item.available_quantity = 0
                    item.status = '损坏'
                    other_assignments = RoomItemAssignment.query.filter(
                        RoomItemAssignment.item_id == item.id,
                        RoomItemAssignment.status == 'active',
                        RoomItemAssignment.id != assignment.id
                    ).all()
                    for other_a in other_assignments:
                        other_a.status = 'damaged'
                        other_a.returned_at = datetime.now()
            elif action == 'loss':
                quantity = request.form.get(f'quantity_{assignment.id}', assignment.quantity, type=int)
                if quantity < 1:
                    quantity = 1
                if quantity > assignment.quantity:
                    quantity = assignment.quantity
                item.total_quantity -= quantity
                remaining = assignment.quantity - quantity
                if remaining > 0:
                    item.available_quantity = min(item.total_quantity, item.available_quantity + remaining)
                RoomItemRecord.add_record(
                    item_id=item.id,
                    operation_type=dorm_record_type,
                    quantity=quantity,
                    before_quantity=before_available,
                    after_quantity=item.available_quantity,
                    user_id=assignment.user_id,
                    from_room_id=item.room_id,
                    operator_id=_get_operator_id(),
                    remarks=f'宿舍操作-丢失, 数量={quantity}'
                )
                if remaining > 0:
                    RoomItemRecord.add_record(
                        item_id=item.id,
                        operation_type=dorm_record_type,
                        quantity=remaining,
                        before_quantity=item.available_quantity - remaining,
                        after_quantity=item.available_quantity,
                        user_id=assignment.user_id,
                        from_room_id=item.room_id,
                        operator_id=_get_operator_id(),
                        remarks=f'宿舍操作-自动归还, 数量={remaining}'
                    )
                assignment.status = 'lost' if quantity >= assignment.quantity else 'returned'
                assignment.returned_at = datetime.now()
                if item.total_quantity <= 0:
                    item.total_quantity = 0
                    item.available_quantity = 0
                    item.status = '丢失'
                    other_assignments = RoomItemAssignment.query.filter(
                        RoomItemAssignment.item_id == item.id,
                        RoomItemAssignment.status == 'active',
                        RoomItemAssignment.id != assignment.id
                    ).all()
                    for other_a in other_assignments:
                        other_a.status = 'lost'
                        other_a.returned_at = datetime.now()
            elif action == 'scrap':
                quantity = request.form.get(f'quantity_{assignment.id}', assignment.quantity, type=int)
                if quantity < 1:
                    quantity = 1
                if quantity > assignment.quantity:
                    quantity = assignment.quantity
                item.total_quantity -= quantity
                remaining = assignment.quantity - quantity
                if remaining > 0:
                    item.available_quantity = min(item.total_quantity, item.available_quantity + remaining)
                RoomItemRecord.add_record(
                    item_id=item.id,
                    operation_type=dorm_record_type,
                    quantity=quantity,
                    before_quantity=before_available,
                    after_quantity=item.available_quantity,
                    user_id=assignment.user_id,
                    from_room_id=item.room_id,
                    operator_id=_get_operator_id(),
                    remarks=f'宿舍操作-报废, 数量={quantity}'
                )
                if remaining > 0:
                    RoomItemRecord.add_record(
                        item_id=item.id,
                        operation_type=dorm_record_type,
                        quantity=remaining,
                        before_quantity=item.available_quantity - remaining,
                        after_quantity=item.available_quantity,
                        user_id=assignment.user_id,
                        from_room_id=item.room_id,
                        operator_id=_get_operator_id(),
                        remarks=f'宿舍操作-自动归还, 数量={remaining}'
                    )
                assignment.status = 'scrapped' if quantity >= assignment.quantity else 'returned'
                assignment.returned_at = datetime.now()
                if item.total_quantity <= 0:
                    item.total_quantity = 0
                    item.available_quantity = 0
                    item.status = '报废'
                    other_assignments = RoomItemAssignment.query.filter(
                        RoomItemAssignment.item_id == item.id,
                        RoomItemAssignment.status == 'active',
                        RoomItemAssignment.id != assignment.id
                    ).all()
                    for other_a in other_assignments:
                        other_a.status = 'scrapped'
                        other_a.returned_at = datetime.now()
                        RoomItemRecord.add_record(
                            item_id=item.id,
                            operation_type=dorm_record_type,
                            quantity=other_a.quantity,
                            before_quantity=before_available,
                            after_quantity=0,
                            user_id=other_a.user_id,
                            from_room_id=item.room_id,
                            operator_id=_get_operator_id(),
                            remarks='宿舍操作-报废(级联)'
                        )
            elif action == 'transfer':
                # 严重6修复: 转移到新房间（仅transferable类型）
                if item.item_type != 'transferable':
                    logging.warning(f"物品ID={item.id}类型为{item.item_type}，不可转移，跳过")
                    continue
                if not target_room_id:
                    logging.warning(f"未提供目标房间ID，跳过转移")
                    continue
                from_room_id = item.room_id
                item.room_id = target_room_id
                RoomItemRecord.add_record(
                    item_id=item.id,
                    operation_type=dorm_record_type,
                    quantity=assignment.quantity,
                    before_quantity=before_available,
                    after_quantity=item.available_quantity,
                    user_id=assignment.user_id,
                    from_room_id=from_room_id,
                    to_room_id=target_room_id,
                    operator_id=_get_operator_id(),
                    remarks='宿舍操作-转移'
                )

        # 设置dorm.pending_item_action=False
        dorm.pending_item_action = False

        db.session.commit()
        log_operation(user_id=current_user.id, action=f'处理宿舍操作物品: 宿舍记录ID={dorm_id}', module='room_item')
        flash('物品处理完成', 'success')
    except Exception as e:
        db.session.rollback()
        logging.error(f"处理宿舍操作物品失败: {str(e)}\n{traceback.format_exc()}")
        flash(f'处理宿舍操作物品失败: {str(e)}', 'error')

    return redirect(url_for('room_item.manage'))