from flask import Blueprint, request, jsonify, send_file, abort
import logging
from utils.db import db
from models.room.room import Room, RoomStatus
from models.dorm.dorm import Dorm
from models.user.user import User
from config import Config
from flask_login import login_required, current_user
from utils.auth import require_permission
from utils.log import log_operation
import traceback
from datetime import datetime  # 只保留datetime导入
from werkzeug.utils import secure_filename
import os

from utils.auth import require_permission
from models.system_config.system_config import SystemConfig  # 新增：导入系统配置模型
from utils.room_photo import RoomPhotoManager

room_api_bp = Blueprint('room_api', __name__, url_prefix='/api/rooms')

# 显示映射保持不变
REVERSE_STATUS_MAPPING = {
    RoomStatus.AVAILABLE.value: '可用',
    RoomStatus.FULL.value: '已满',
    RoomStatus.MAINTENANCE.value: '维护中',
    RoomStatus.CLOSED.value: '已关闭'
}

# 从系统配置获取房间类型映射
def get_room_type_mapping():
    """从系统配置获取房间类型及其显示名称的映射"""
    room_types = Room.get_valid_room_types()
    # 假设配置格式为 ["单人间", "双人间", "四人间", ...]
    # 如需更复杂的映射关系，可以在系统配置中使用字典格式
    return {room_type: room_type for room_type in room_types}


# 性别限制直接使用中文，无需映射

@room_api_bp.route('/<int:room_id>', methods=['GET'])
@login_required
@require_permission('room.view')
def get_room_detail(room_id):
    try:
        logging.debug(f"=== 处理房间详情请求：room_id={room_id} ===")
        
        room = Room.query.get(room_id)
        if not room:
            return jsonify({
                "success": False,
                "message": f"未找到ID为{room_id}的房间"
            }), 404
        # 获取房间类型映射
        room_type_mapping = get_room_type_mapping()
        # 严格匹配Dorm模型的status字段（仅active状态）
        active_dorms = Dorm.query.filter(
            Dorm.room_id == room_id,
            Dorm.status == 'active'  # 匹配Dorm模型定义的status有效值
        ).all()
        
        logging.debug(f"房间{room_id}有效入住记录数：{len(active_dorms)}")
       
        occupants = []
        for idx, dorm in enumerate(active_dorms):
            try:
                if not dorm.user_id:
                    logging.warning(f"入住记录ID={dorm.id}未关联用户ID，跳过")
                    continue
                
                user = User.query.get(dorm.user_id)
                if not user:
                    logging.error(f"未找到用户ID={dorm.user_id}（入住记录ID={dorm.id}）")
                    continue
                
                # 匹配Dorm模型的check_in_date字段（改为datetime类型）
                check_in_date = "未记录"
                days_stayed = "未记录"
                try:
                    # 明确检查check_in_date是否存在且为datetime类型
                    if dorm.check_in_date is not None and isinstance(dorm.check_in_date, datetime):
                        check_in_date = dorm.check_in_date.strftime('%Y-%m-%d %H:%M')  # 增加时间显示
                        # 使用与Dorm模型一致的天数计算方法
                        # 只比较日期部分，忽略时间
                        check_in_date_only = dorm.check_in_date.date()
                        today_date_only = datetime.today().date()
                        
                        # 计算日期差，加1天确保入住当天被计算在内
                        if today_date_only >= check_in_date_only:
                            delta_days = (today_date_only - check_in_date_only).days
                            days_stayed = delta_days + 1
                        else:
                            days_stayed = 0
                    else:
                        # 记录具体缺失情况以便排查
                        logging.warning(
                            f"入住记录ID={dorm.id}的check_in_date缺失或格式异常 "
                            f"(值: {dorm.check_in_date}, 类型: {type(dorm.check_in_date)})"
                        )
                except Exception as e:
                    logging.error(f"处理日期时发生错误：{str(e)}")
               
                # 严格匹配User模型字段
                occupant_data = {
                    "id": user.id,
                    "name": user.name or "-",  # 对应User.name字段
                    "age": str(user.get_age()) if user.get_age() is not None else "-",  # 调用模型方法
                    "student_id": user.student_id or "-",  # 对应User.student_id
                    "gender": user.gender or "-",  # 新增：对应User.gender字段
                    "department": user.department or "-",  # 对应User.department
                    "position": user.position or "-",  # 对应User.position
                    "phone": user.phone or "-",  # 对应User.phone
                    "check_in_date": check_in_date,  # 来自Dorm.check_in_date（datetime类型）
                    "days_stayed": days_stayed  # 基于日期部分计算
                }
                occupants.append(occupant_data)
                
            except Exception as e:
                logging.error(f"处理第{idx+1}条入住记录失败: {str(e)}")
                continue
        
        # 房间数据（匹配Room模型）
        room_data = {
            "id": room.id,
            "building": room.building,
            "room_number": room.room_number,
            "full_identifier": room.room_full_identifier,
            "room_id": f"{str(room.building).zfill(2)}{str(room.room_number).zfill(2)}",
            "room_type": room.room_type,
            "room_type_display": room_type_mapping.get(room.room_type, room.room_type),
            "room_level": room.room_level or "普通房间",
            "capacity": room.capacity,
            "current_occupancy": room.current_occupancy,
            "remaining_capacity": room.capacity - room.current_occupancy,
            "gender_restriction": room.gender_restriction,
            "status": room.status,
            "status_display": REVERSE_STATUS_MAPPING.get(room.status, room.status),
            "occupancy_rate": room.occupancy_rate,
            "average_age": float(room.average_age) if room.average_age is not None else None,
            "remark": room.remark or ""
        }
        
        response = {
            "success": True,
            "data": {
                "room": room_data,
                "occupants": occupants
            },
            "message": "查询成功"
        }
        
        log_operation(
            user_id=current_user.id,
            module='room',
            operation_type='room_api',
            action=f"查询房间详情 [ID: {room_id}]，入住{len(occupants)}人",
            result="成功"
        )
        
        return jsonify(response)
        
    except Exception as e:
        error_detail = f"房间详情接口错误（room_id={room_id}）: {str(e)}\n堆栈: {traceback.format_exc()}"
        logging.error(error_detail)
        
        try:
            log_operation(
                user_id=getattr(current_user, 'id', "未知"),
                module='room',
                operation_type='room_api',
                action=f"查询房间详情 [ID: {room_id}]失败: {str(e)}",
                result="失败"
            )
        except Exception as log_err:
            logging.error(f"记录日志失败: {str(log_err)}")
        
        return jsonify({
            "success": False,
            "data": None,
            "message": "获取房间详情失败" if not Config.DEBUG else error_detail
        }), 500


@room_api_bp.route('', methods=['GET'])
@login_required
@require_permission('room.view')
def get_rooms():
    try:
        logging.debug("\n=== 房间列表请求 ===")
        # 获取房间类型映射
        room_type_mapping = get_room_type_mapping()
        valid_room_types = list(room_type_mapping.keys())
        # 参数处理
        gender = request.args.get('gender', '').strip().lower()
        status = request.args.get('status', '').strip().lower()
        building = request.args.get('building', '').strip()
        room_number = request.args.get('room_number', '').strip()
        room_type = request.args.get('room_type', '').strip()
        room_level = request.args.get('room_level', '').strip()
        name = request.args.get('name', '').strip()  # 按User.name筛选
        exclude_user_id = request.args.get('exclude_user_id', '').strip()
        page = max(request.args.get('page', 1, type=int), 1)
        per_page = min(request.args.get('per_page', 20, type=int), 10000)
        
        logging.debug(f"参数：gender={gender}, status={status}, building={building}, room_number={room_number}, room_type={room_type}, name={name}")

        # 枚举值验证
        valid_statuses = [rs.value for rs in RoomStatus]
        valid_genders = Room.get_valid_gender_restrictions()
        

        # 构建查询
        query = Room.query
        
        # 排除特定用户住宿的房间
        if exclude_user_id.isdigit():
            # 获取该用户当前住宿的房间ID
            user_dorm = Dorm.query.filter(
                Dorm.user_id == int(exclude_user_id),
                Dorm.status == 'active'
            ).first()
            if user_dorm:
                query = query.filter(Room.id != user_dorm.room_id)
        
        # 性别筛选
        if gender in valid_genders:
            query = query.filter(
                (Room.gender_restriction == gender) | 
                (Room.gender_restriction == "无限制")
            )
        elif gender:
            # 尝试直接匹配中文值
            if gender in valid_genders:
                query = query.filter(
                    (Room.gender_restriction == gender) | 
                    (Room.gender_restriction == "无限制")
                )
        
        # 状态筛选
        if status in valid_statuses:
            query = query.filter(Room.status == status)
        elif status:
            status_map = {v: k for k, v in REVERSE_STATUS_MAPPING.items()}
            if status in status_map:
                query = query.filter(Room.status == status_map[status])
        
        # 房间类型筛选
        if room_type in valid_room_types:
            query = query.filter(Room.room_type == room_type)
        elif room_type:
            type_map = {v: k for k, v in room_type_mapping.items()}
            if room_type in type_map:
                query = query.filter(Room.room_type == type_map[room_type])
        
        # 房间级别筛选
        if room_level:
            query = query.filter(Room.room_level == room_level)
        
        # 楼栋和房间号筛选
        if building:
            query = query.filter(Room.building.ilike(f'%{building}%'))
        if room_number:
            query = query.filter(
                (Room.building.ilike(f'%{room_number.replace("-", "")}%')) |
                (Room.room_number.ilike(f'%{room_number.replace("-", "")}%'))
            )

        # 分页查询排序
        pagination = query.order_by(Room.id, Room.building, Room.room_number).paginate(
            page=page, per_page=per_page, error_out=False
        )

        # 导入FeeSubsidy模型
        from models.fee_subsidy.fee_subsidy import FeeSubsidy
        
        # 格式化房间数据
        room_list = []
        for room in pagination.items:
            try:
                # 关联查询（严格匹配模型关系）
                occupants = Dorm.query.filter(
                    Dorm.room_id == room.id,
                    Dorm.status == 'active'  # 匹配Dorm模型的status
                ).join(User).all()
                
                # 按姓名筛选（基于User.name字段）
                if name:
                    has_matching_name = any(
                        name.lower() in (occ.user.name or '').lower()
                        for occ in occupants
                    )
                    if not has_matching_name:
                        continue
                
                # 查询房间的当前费用减免信息
                current_subsidies = FeeSubsidy.query.filter(
                    FeeSubsidy.room_id == room.id,
                    FeeSubsidy.is_enabled == True
                ).all()
                
                # 计算当前有效的减免值
                electric_reduction = 0
                water_reduction = 0
                amount_reduction = 0
                
                for subsidy in current_subsidies:
                    if subsidy.fee_type == '房间水电按用量减免':
                        electric_reduction += float(subsidy.electric_reduction) if subsidy.electric_reduction else 0
                        water_reduction += float(subsidy.water_reduction) if subsidy.water_reduction else 0
                    elif subsidy.fee_type == '房间水电按金额减免' and subsidy.amount is not None:
                        amount_reduction += float(subsidy.amount)
                
                # 构建入住用户摘要信息，包含日期时间数据
                occupants_summary = []
                for occ in occupants[:3]:  # 只取前3位
                    check_in_date = "未记录"
                    try:
                        if occ.check_in_date is not None and isinstance(occ.check_in_date, datetime):
                            check_in_date = occ.check_in_date.strftime('%Y-%m-%d %H:%M')  # 增加时间显示
                        else:
                            logging.warning(
                                f"入住记录ID={occ.id}的check_in_date缺失或格式异常 "
                                f"(值: {occ.check_in_date}, 类型: {type(occ.check_in_date)})"
                            )
                    except Exception as e:
                        logging.error(f"处理入住记录ID={occ.id}的日期时出错: {str(e)}")
                    
                    occupants_summary.append({
                        "id": occ.user.id,
                        "name": occ.user.name,
                        "gender": occ.user.gender,
                        "check_in_date": check_in_date  # 包含日期时间
                    })
                
                # 构建房间数据
                room_list.append({
                    "id": room.id,
                    "building": room.building,
                    "room_number": room.room_number,
                    "full_identifier": room.room_full_identifier,
                    "room_id": f"{str(room.building).zfill(2)}{str(room.room_number).zfill(2)}",
                    "room_type": room.room_type,
                    "room_type_display": room_type_mapping.get(room.room_type, room.room_type),
                    "room_level": room.room_level or "普通房间",
                    "capacity": room.capacity,
                    "current_occupancy": room.current_occupancy,
                    "remaining_capacity": room.capacity - room.current_occupancy,
                    "gender_restriction": room.gender_restriction,
                    "status": room.status,
                    "status_display": REVERSE_STATUS_MAPPING.get(room.status, room.status),
                    "is_available": room.is_available(),
                    "occupancy_rate": room.occupancy_rate,
                    "average_age": float(room.average_age) if room.average_age is not None else None,
                    "occupants_summary": occupants_summary,  # 使用包含日期时间的摘要信息
                    "total_occupants": len(occupants),
                    "electric_reduction": electric_reduction,
                    "water_reduction": water_reduction,
                    "amount_reduction": amount_reduction
                })
            except Exception as e:
                logging.error(f"格式化房间数据失败（ID: {room.id}）: {str(e)}")
                continue

        response = {
            "success": True,
            "data": {
                "rooms": room_list,
                "pagination": {
                    "total": pagination.total,
                    "page": page,
                    "per_page": per_page,
                    "pages": pagination.pages
                }
            },
            "message": "查询成功"
        }

        log_operation(
            user_id=getattr(current_user, 'id', "未知"),
            module='room',
            operation_type='room_api',
            action=f"调用房间列表接口成功，返回{len(room_list)}条数据",
            result="成功"
        )
        
        return jsonify(response)

    except Exception as e:
        error_detail = f"房间列表接口错误: {str(e)}\n堆栈: {traceback.format_exc()}"
        logging.error(error_detail)
        
        try:
            log_operation(
                user_id=getattr(current_user, 'id', "未知"),
                module='room',
                operation_type='room_api',
                action=f"调用房间列表接口失败: {str(e)}",
                result="失败"
            )
        except Exception as log_err:
            logging.error(f"记录日志失败: {str(log_err)}")
        
        return jsonify({
            "success": False,
            "data": None,
            "message": "获取房间列表失败" if not Config.DEBUG else error_detail
        }), 500


@room_api_bp.route('/user-rooms/batch', methods=['POST'])
@login_required
@require_permission('room.view')
def get_batch_user_rooms():
    try:
        data = request.get_json()
        user_ids = data.get('user_ids', [])
        
        if not user_ids or not isinstance(user_ids, list):
            return jsonify({
                "success": False,
                "message": "请提供有效的user_ids列表"
            }), 400
        # 获取房间类型映射
        room_type_mapping = get_room_type_mapping()
        results = []
        for user_id in user_ids:
            # 匹配Dorm模型的status字段
            active_dorm = Dorm.query.filter(
                Dorm.user_id == user_id,
                Dorm.status == 'active'
            ).first()
            
            if active_dorm:
                room = Room.query.get(active_dorm.room_id)
                # 补充用户基本信息（基于User模型）
                user = User.query.get(user_id)
                user_info = {
                    "id": user.id,
                    "name": user.name,
                    "student_id": user.student_id,
                    "gender": user.gender
                } if user else None
                
                # 处理入住日期时间
                check_in_date = "未记录"
                days_stayed = "未记录"
                if active_dorm.check_in_date is not None and isinstance(active_dorm.check_in_date, datetime):
                    check_in_date = active_dorm.check_in_date.strftime('%Y-%m-%d %H:%M')  # 增加时间显示
                    # 转换为date类型计算天数差
                    days_stayed = (datetime.today().date() - active_dorm.check_in_date.date()).days
                
                results.append({
                    "user_id": user_id,
                    "user_info": user_info,  # 新增：用户基本信息
                    "has_room": True,
                    "room_id": room.id if room else None,
                    "building": room.building if room else None,
                    "room_number": room.room_number if room else None,
                    "full_identifier": room.room_full_identifier if room else None,
                    "room_type": room.room_type if room else None,
                    "room_type_display": room_type_mapping.get(room.room_type, room.room_type) if room else None,
                    "check_in_date": check_in_date,
                    "days_stayed": days_stayed
                })
            else:
                results.append({
                    "user_id": user_id,
                    "has_room": False
                })
        
        # 过滤出未分配宿舍的用户
        unassigned_users = [user for user in results if not user['has_room']]
        
        return jsonify({
            "success": True,
            "data": unassigned_users,
            "total_unassigned": len(unassigned_users),
            "total_requested": len(results)
        })
        
    except Exception as e:
        logging.error(f"批量查询用户住宿状态失败: {str(e)}")
        return jsonify({
            "success": False,
            "message": "批量查询失败"
        }), 500


@room_api_bp.route('/media/<room_id>/<filename>', methods=['GET'])
@login_required
@require_permission('room.view')
def get_room_media(room_id, filename):
    """获取房间的媒体文件（照片或视频）"""
    try:
        # 安全处理参数
        room_id = secure_filename(room_id)
        filename = secure_filename(filename)
        
        # 获取文件完整路径
        file_path = RoomPhotoManager.get_file_path(filename, room_id)
        
        # 检查文件是否存在
        if not file_path:
            abort(404, description="文件不存在")
        
        # 发送文件
        return send_file(file_path, as_attachment=False)
    except Exception as e:
        logging.error(f"获取房间媒体文件时发生错误: {str(e)}")
        abort(500, description=f"获取文件时发生错误: {str(e)}")


@room_api_bp.route('/media/list', methods=['GET'])
@login_required
@require_permission('room.view')
def get_room_media_list():
    """获取房间的所有媒体文件列表"""
    try:
        # 从查询参数中获取room_id
        room_id = request.args.get('room_id')
        
        # 验证参数
        if not room_id:
            return jsonify({
                "success": False,
                "message": "缺少房间ID参数"
            }), 400
        
        # 安全处理参数
        room_id = secure_filename(room_id)
        
        # 获取媒体文件列表
        media_files = RoomPhotoManager.get_media_files(room_id)
        
        # 格式化为前端期望的结构
        formatted_media_files = []
        for media in media_files:
            formatted_media_files.append({
                'filename': media['filename'],
                'url': media['url'],
                'type': 'photo' if media['type'] == 'image' else 'video',  # 转换为前端期望的类型
                'upload_time': media['upload_time'].isoformat()  # 添加上传时间字段，转换为ISO格式字符串
            })
        
        return jsonify({
            "success": True,
            "media_files": formatted_media_files
        })
    except Exception as e:
        logging.error(f"获取房间媒体文件列表时发生错误: {str(e)}")
        return jsonify({
            "success": False,
            "message": "获取媒体文件列表失败",
            "error": str(e)
        }), 500


@room_api_bp.route('/buildings', methods=['GET'])
@login_required
@require_permission('room.view')
def get_buildings():
    """获取所有楼栋信息"""
    try:
        logging.debug("=== 处理获取楼栋列表请求 ===")
        
        # 查询所有唯一的楼栋信息
        buildings = Room.query.with_entities(Room.building).distinct().all()
        
        # 格式化结果
        building_list = [building[0] for building in buildings]
        
        # 按楼栋名称排序（尝试按数字和字符混合排序）
        def sort_building(b):
            # 尝试提取数字部分进行排序
            import re
            match = re.search(r'\d+', b)
            if match:
                # 同时返回数字部分和原始字符串，以便正确排序
                return (int(match.group()), b)
            else:
                # 如果没有数字，使用原始字符串排序
                return (float('inf'), b)
        
        building_list.sort(key=sort_building)
        
        response = {
            "success": True,
            "data": building_list,
            "total": len(building_list),
            "message": "查询成功"
        }
        
        log_operation(
            user_id=getattr(current_user, 'id', "未知"),
            module='room',
            operation_type='room_api',
            action=f"调用获取楼栋列表接口成功，返回{len(building_list)}条数据",
            result="成功"
        )
        
        return jsonify(response)
        
    except Exception as e:
        error_detail = f"获取楼栋列表接口错误: {str(e)}\n堆栈: {traceback.format_exc()}"
        logging.error(error_detail)
        
        try:
            log_operation(
                user_id=getattr(current_user, 'id', "未知"),
                module='room',
                operation_type='room_api',
                action=f"调用获取楼栋列表接口失败: {str(e)}",
                result="失败"
            )
        except Exception as log_err:
            logging.error(f"记录日志失败: {str(log_err)}")
        
        return jsonify({
            "success": False,
            "data": None,
            "message": "获取楼栋列表失败" if not Config.DEBUG else error_detail
        }), 500
