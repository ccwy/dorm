from flask import Blueprint, render_template, request, flash, redirect, url_for
from utils.db import db
from models.room import Room, RoomStatus
from models.dorm import Dorm
from models.user import User  # 添加User模型导入
from flask_login import login_required, current_user
from utils.log import log_operation
import logging
# 导入admin_required装饰器
from blueprints.system_settings import admin_required
from models.utility_room_bill_record import RoomUtilityRecord
from models.room_facility import RoomFacility  # 新增：导入房间设施模型
from utils.room_photo import RoomPhotoManager

# 定义蓝图
room_bp = Blueprint(
    'room', 
    __name__, 
    url_prefix='/room', 
    template_folder='../templates',
    static_folder='../static',
    static_url_path='/room/static'
)

# 定义枚举中文映射常量（新增）
ENUM_CHINESE_MAPPING = {
    # 房间状态映射
    RoomStatus.AVAILABLE.value: "可用",
    RoomStatus.FULL.value: "已住满",
    RoomStatus.MAINTENANCE.value: "维修中",
    RoomStatus.CLOSED.value: "已关闭"
}

# 生成枚举映射的工具函数（只保留一个正确版本）
def get_enum_chinese_mapping(enum_class):
    """生成{枚举value: 中文文本}的映射字典"""
    mapping = {}
    for item in enum_class:
        if item.value in ENUM_CHINESE_MAPPING:
            mapping[item.value] = ENUM_CHINESE_MAPPING[item.value]
        else:
            # 记录未映射的枚举值，便于调试
            logging.warning(f"枚举值 {item.value} 未配置中文映射")
            mapping[item.value] = f"未知({item.value})"
    return mapping

# 分页工具函数
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
    
# 导入其他操作模块
from . import room_operations
from . import room_import_export

# 房间管理页面
@room_bp.route('/manage', methods=['GET'])
@login_required
@admin_required
def manage():
    try:
        # 获取请求参数
        search = request.args.get('search', '').strip()
        page = request.args.get('page', 1, type=int)
        # 获取前端传递的分页大小参数，设置默认值为20以匹配前端选项
        page_size = request.args.get('per_page', request.args.get('page_size', 20, type=int), type=int)
        building = request.args.get('building', '').strip()
        room_level = request.args.get('level', '').strip()
        room_type = request.args.get('type', '').strip()
        room_status = request.args.get('status', '').strip()
        gender_restriction = request.args.get('gender', '').strip()
        
        # 参数校验
        if page < 1:
            page = 1
        # 确保page_size在合理范围内，与前端选项匹配
        page_size = max(10, min(100, page_size))
        
        # 生成映射表
        status_mapping = get_enum_chinese_mapping(RoomStatus)
        # 性别限制直接使用中文，无需映射
        gender_mapping = {}
        valid_gender_restrictions = Room.get_valid_gender_restrictions()
        for gender in valid_gender_restrictions:
            gender_mapping[gender] = gender
        # 从当前所有房间提取不重复的房间类型
        room_types = sorted([str(rt[0]) for rt in db.session.query(Room.room_type).distinct().all() if rt[0]])
        # 创建房间类型映射（值到显示文本，两者相同）
        type_mapping = {t: t for t in room_types}
        # 从当前所有房间提取不重复的房间级别
        room_levels = sorted([str(rl[0]) for rl in db.session.query(Room.room_level).distinct().all() if rl[0]])
        # 创建房间级别映射（值到显示文本，两者相同）
        level_mapping = {l: l for l in room_levels}
        # 获取所有楼栋
        buildings = sorted([str(b[0]) for b in db.session.query(Room.building).distinct().all()])
        
        # 构建查询
        query = Room.query.order_by(Room.id.desc())
        if search:
            query = query.filter(
                (Room.building.ilike(f'%{search}%')) |
                (Room.room_number.ilike(f'%{search}%'))
            )
        if building:
            query = query.filter(Room.building == building)
        if room_type:
            query = query.filter(Room.room_type == room_type)  # 移除int()转换
        if room_level:
            query = query.filter(Room.room_level == room_level)
        if room_status:
            query = query.filter(Room.status == room_status)
        if gender_restriction:
            query = query.filter(Room.gender_restriction == gender_restriction)
        
        # 分页查询
        pagination = query.paginate(page=page, per_page=page_size, error_out=False)
        rooms = pagination.items
        total_rooms = pagination.total
        total_pages = pagination.pages
        current_page = pagination.page
        page_range = generate_page_range(current_page, total_pages)
        
        # 统计数据
        available_rooms = Room.query.filter_by(status=RoomStatus.AVAILABLE.value).count()
        full_rooms = Room.query.filter_by(status=RoomStatus.FULL.value).count()
        maintenance_rooms = Room.query.filter_by(status=RoomStatus.MAINTENANCE.value).count()
        # 记录访问日志
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='records',
            action="访问房间管理页面",
            result="成功"
        )
        logging.info(f"加载房间管理页面，当前用户ID: {current_user.id}")
        return render_template(
            'room_manage/room_manage.html',
            title="房间管理",
            # 筛选数据
            buildings=buildings,
            type_mapping=type_mapping,
            level_mapping=level_mapping,
            status_mapping=status_mapping,
            gender_mapping=gender_mapping,
            # 房间数据
            rooms=rooms,
            total_rooms=total_rooms,
            available_rooms=available_rooms,
            full_rooms=full_rooms,
            maintenance_rooms=maintenance_rooms,
            # 分页参数
            search=search,
            current_page=current_page,
            page_size=page_size,
            total_pages=total_pages,
            page_range=page_range,
            # 反向映射（用于筛选框回显）
            
            # 性别限制直接使用中文，无需反向映射
            reverse_gender={},
            reverse_status={v: k for k, v in status_mapping.items()},
            # 枚举类
            
            RoomStatus=RoomStatus,
            # 当前筛选条件
            building=building,
            room_level=room_level,
            room_type=room_type,
            room_status=room_status,
            gender_restriction=gender_restriction
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='records',
            action=f"加载房间管理页面失败: {str(e)}",
            result="失败"
        )
        flash(f'加载房间数据失败，请联系管理员', 'danger')
        logging.error(f"加载房间管理页面失败: {str(e)}")
        return render_template(
            'room_manage/room_manage.html',
            title=f"房间管理",
            rooms=[],
            buildings=[],
            type_mapping={},
            level_mapping={},
            status_mapping={},
            gender_mapping={},
            total_rooms=0,
            available_rooms=0,
            full_rooms=0,
            maintenance_rooms=0,
            search=search,
            current_page=1,
            page_size=page_size,
            total_pages=0,
            page_range=[],
            reverse_type={},
            reverse_gender={},
            reverse_status={},
            
            RoomStatus=RoomStatus,
            building='',
            room_level='',
            room_type='',
            room_status=''
        )

# 查看房间详情
@room_bp.route('/view/<int:id>', methods=['GET'])
@login_required
@admin_required
def view(id):
    try:
        room = Room.query.get_or_404(id)
        # 获取房间的设施列表（包含数量）
        # 直接查询RoomFacility表获取当前房间的设施列表
        current_facilities = RoomFacility.query.filter_by(room_id=room.id).all()
        facilities = [{'name': f.name, 'quantity': f.quantity} for f in current_facilities]

        current_dorms = Dorm.query.filter_by(room_id=id, status='active').all()
        room.current_occupants = len(current_dorms) if current_dorms else 0

        # 获取房间的所有住宿历史记录
        all_dorms = Dorm.query.filter_by(room_id=id).order_by(Dorm.check_in_date.desc()).all()
        # 获取在住人员明细
        current_residents = []
        for dorm in current_dorms:
            user = User.query.get(dorm.user_id)
            if user:
                current_residents.append({
                    'user': user,
                    'dorm': dorm
                })
        # 获取房间类型映射
        room_types = Room.get_valid_room_types()
        type_mapping = {t: t for t in room_types}
        # 获取房间的水电费记录
        utility_records = RoomUtilityRecord.query.filter_by(room_id=id).order_by(RoomUtilityRecord.billing_period.desc()).all()
        # 获取房间的媒体文件
        media_files = RoomPhotoManager.get_media_files(room.id)
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='room_view',
            action=f"查看房间 [ID: {id}, {room.building}{room.room_number}]",
            result="成功"
        )
        logging.info(f"查看房间详情，房间ID: {id}")
        return render_template(
            'room_manage/room_view.html',
            title=f"查看房间 - {room.building}{room.room_number}",
            room=room,
            current_dorms=current_dorms,
            current_residents=current_residents,
            all_dorms=all_dorms,  # 传递所有住宿历史记录
            reverse_type=type_mapping,
            facilities=facilities,  # 传递包含数量的设施列表
            # 性别限制直接使用中文，无需映射
            reverse_gender={},
            reverse_status=get_enum_chinese_mapping(RoomStatus),
            utility_records=utility_records,
            media_files=media_files  # 传递房间媒体文件
        )
    except Exception as e:
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='room_view',
            action=f"尝试查看房间 [ID: {id}]失败: {str(e)}",
            result="失败"
        )
        flash(f'查看房间失败，请重试', 'danger')
        return redirect(url_for('room.manage'))

